"""The collector: gathers state, publishes read models to the store, serves the command bus.

Today its source is the physics simulator (demo data). A real deployment swaps the engine for
adapters (DCGM / Redfish / SNMP / Modbus / cloud APIs) that fill the same state — the publisher,
the Redis key layout and the whole web tier stay unchanged.

Exactly one collector writes at a time: it holds ``lease:collector`` and renews it every tick.
A second collector (or a web process in ``GRID_COLLECTOR=auto`` mode) waits as a standby.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import traceback
import uuid

from .. import config
from ..store import get_store
from . import commands as C
from .publisher import Publisher

log = logging.getLogger("grid.collector")


class Collector:
    def __init__(self, store=None, owner: str | None = None, role: str = "external"):
        self.store = store or get_store()
        self.role = role
        self.owner = owner or f"{role}@{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.eng = None
        self.pub: Publisher | None = None
        self.handlers: dict = {}
        self.stop_evt = threading.Event()
        self.ready = threading.Event()
        self.threads: list[threading.Thread] = []

    # ---------------------------------------------------------------- lifecycle
    def wait_for_lease(self) -> bool:
        while not self.stop_evt.is_set():
            if self.store.acquire_lease(self.owner, config.COLLECTOR_LEASE_S):
                return True
            self.stop_evt.wait(1.0)
        return False

    def start(self) -> "Collector":
        """Non-blocking: acquires the lease, boots the engine and starts tick + command threads."""
        t = threading.Thread(target=self._boot, name="grid-collector-boot", daemon=True)
        t.start()
        self.threads.append(t)
        return self

    def _boot(self) -> None:
        if not self.wait_for_lease():
            return
        from ..sim.engine import Engine     # heavy import + ~2 s warm-up/backfill
        self.eng = Engine()
        self.pub = Publisher(self.eng, self.store, self.owner)
        self.handlers = C.build(self.eng)
        self.pub.reset()
        self.pub.publish(force=True, full=True)
        self.eng.hooks.append(self._on_tick)
        self.eng.start()
        cmd = threading.Thread(target=self._commands, name="grid-collector-cmd", daemon=True)
        cmd.start()
        self.threads.append(cmd)
        self.ready.set()
        log.info("collector %s publishing to %s (%s)", self.owner, self.store.url, self.store.mode)

    def stop(self) -> None:
        self.stop_evt.set()
        if self.eng:
            self.eng.stop()
        try:
            self.store.release_lease(self.owner)
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- tick → publish
    def _on_tick(self, eng) -> None:
        try:
            if not self.store.acquire_lease(self.owner, config.COLLECTOR_LEASE_S):
                log.warning("lost collector lease — another collector is writing; stopping")
                self.stop()
                return
            self.pub.publish()
        except Exception:  # noqa: BLE001 — never kill the tick loop over a store hiccup
            eng.logs.emit(time.time(), "grid-collector", "error", "publish failed: " + traceback.format_exc()[-300:])

    # ---------------------------------------------------------------- command bus
    def _commands(self) -> None:
        while not self.stop_evt.is_set():
            try:
                msg = self.store.next_command(timeout=1.0)
            except Exception:  # noqa: BLE001 — store restarting
                self.stop_evt.wait(1.0)
                continue
            if not msg:
                continue
            self.handle(msg)

    def handle(self, msg: dict) -> None:
        rid, name, args = msg.get("id"), msg.get("cmd"), msg.get("args") or {}
        if time.time() - float(msg.get("t", 0)) > 20:        # the caller has long given up — don't act late
            self.store.reply(rid, {"ok": False, "status": 408, "error": "command expired before it was processed"})
            return
        fn = self.handlers.get(name)
        if fn is None:
            self.store.reply(rid, {"ok": False, "status": 400, "error": f"unknown command {name!r}"})
            return
        try:
            result = fn(**args)
            if name not in C.READ_ONLY:           # the reply only goes out once Redis reflects the change
                self.pub.publish(force=True, kinds=C.REFRESH.get(name))
            self.store.reply(rid, {"ok": True, "result": result})
        except LookupError as e:
            self.store.reply(rid, {"ok": False, "status": 404, "error": str(e).strip("'")})
        except (ValueError, TypeError) as e:
            self.store.reply(rid, {"ok": False, "status": 400, "error": str(e)})
        except Exception as e:  # noqa: BLE001
            self.store.reply(rid, {"ok": False, "status": 500, "error": f"{type(e).__name__}: {e}"})
