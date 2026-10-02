"""The collector: gathers state, publishes read models to the store, serves the command bus.

Today its source is the physics simulator (demo data). A real deployment swaps the engine for
adapters (DCGM / Redfish / SNMP / Modbus / cloud APIs) that fill the same state — the publisher,
the Redis key layout and the whole web tier stay unchanged.

Exactly one collector writes at a time: it holds ``lease:collector``. The lease is taken only once the
engine has booted, and a heartbeat thread renews it every 2 s independently of tick or publish
duration — so a slow boot, a long publish or a laptop waking from sleep never lets it lapse by accident.
A second collector (or a web process in ``GRID_COLLECTOR=auto`` mode) waits as a standby.

Failures never kill it silently: the last error and a status are kept for /healthz, publishing is
retried with back-off, and a store that is full (Redis ``maxmemory``) is reported through
``on_store_full`` so the host process can fall back to the in-memory store.
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
from ..store import get_store, is_full_error, redact
from . import commands as C
from .publisher import Publisher

HOST_METRICS = [  # Server Status time series (name, tier, help, unit)
    ("host_cpu_pct", "t1", "Host CPU utilization", "%"), ("host_mem_pct", "t1", "Host memory used", "%"),
    ("host_disk_pct", "t1", "Host root disk used", "%"), ("host_load1", "t1", "Host load average (1 min)", ""),
    ("host_net_rx_mbps", "t1", "Host network receive", "Mb/s"), ("host_net_tx_mbps", "t1", "Host network transmit", "Mb/s"),
    ("host_disk_read_mbs", "t1", "Host disk read", "MB/s"), ("host_disk_write_mbs", "t1", "Host disk write", "MB/s"),
    ("store_used_mb", "t1", "Read-model store memory used", "MB"), ("store_ops_per_sec", "t1", "Read-model store operations", "ops/s"),
    ("host_cpu_pct_24h", "t4", "Host CPU utilization (24 h)", "%"), ("host_mem_pct_24h", "t4", "Host memory used (24 h)", "%"),
]

log = logging.getLogger("grid.collector")


class Collector:
    def __init__(self, store=None, owner: str | None = None, role: str = "external", on_store_full=None):
        self.store = store or get_store()
        self.role = role
        self.owner = owner or f"{role}@{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.on_store_full = on_store_full
        self.eng = None
        self.pub: Publisher | None = None
        self.handlers: dict = {}
        self.stop_evt = threading.Event()
        self.ready = threading.Event()
        self.threads: list[threading.Thread] = []
        self.status = "starting"
        self.last_error: str | None = None
        self.errors = 0
        self._lock = threading.RLock()     # serialises publishes and store rebinds
        self.host = None
        self.host_sample: dict = {}
        self.store_info: dict = {}

    # ---------------------------------------------------------------- lifecycle
    def start(self) -> "Collector":
        """Non-blocking: acquires the lease, boots the engine and starts tick + command threads."""
        t = threading.Thread(target=self._run, name="grid-collector-boot", daemon=True)
        t.start()
        self.threads.append(t)
        return self

    def _wait_for_lease(self) -> bool:
        self.status = "waiting for lease"
        while not self.stop_evt.is_set():
            try:
                if self.store.acquire_lease(self.owner, config.COLLECTOR_LEASE_S):
                    return True
            except Exception as e:  # noqa: BLE001 — store not reachable yet
                self._fail(e)
            self.stop_evt.wait(1.0)
        return False

    def _run(self) -> None:
        try:
            self.status = "booting engine"
            from ..sim.engine import Engine     # heavy import + warm-up/backfill (seconds; longer on small CPUs)
            self.eng = Engine()
            self.pub = Publisher(self.eng, self.store, self.owner)
            self.handlers = C.build(self.eng)
            self._init_host()
            if not self._wait_for_lease():       # only now — a booting collector must not sit on the lease
                return
            hb = threading.Thread(target=self._heartbeat, name="grid-collector-lease", daemon=True)
            hb.start()
            self.threads.append(hb)
            self._first_publish()
            if self.stop_evt.is_set():
                return
            self.eng.hooks.append(self._on_tick)
            self.eng.start()
            cmd = threading.Thread(target=self._commands, name="grid-collector-cmd", daemon=True)
            cmd.start()
            self.threads.append(cmd)
            self.status = "publishing"
            self.ready.set()
            log.info("collector %s publishing to %s (%s)", self.owner, self.store.url, self.store.mode)
        except Exception as e:  # noqa: BLE001
            self._fail(e)
            self.status = "failed"
            log.error("collector boot failed: %s", traceback.format_exc())

    def _first_publish(self) -> None:
        delay = 2.0
        while not self.stop_evt.is_set():
            try:
                with self._lock:
                    self.pub.reset()
                    self.pub.publish(force=True, full=True)
                self.last_error = None
                return
            except Exception as e:  # noqa: BLE001
                self._fail(e)
                if is_full_error(e) and self._store_full():
                    continue                       # rebound to a store with room — retry at once
                self.status = f"retrying in {delay:.0f}s"
                self.stop_evt.wait(delay)
                delay = min(delay * 2, 30.0)
                try:
                    self.store.acquire_lease(self.owner, config.COLLECTOR_LEASE_S)
                except Exception:  # noqa: BLE001
                    pass

    def _heartbeat(self) -> None:
        """Renew the lease every 2 s no matter how long a tick or publish takes."""
        misses = 0
        while not self.stop_evt.wait(2.0):
            try:
                with self._lock:
                    held = self.store.acquire_lease(self.owner, config.COLLECTOR_LEASE_S)
                if not held:
                    log.warning("lost collector lease to %s — stopping", self.store.lease_holder())
                    self.stop()
                    return
                misses = 0
            except Exception as e:  # noqa: BLE001 — store hiccup: keep trying until the lease would lapse
                misses += 1
                self._fail(e)
                if misses * 2 >= config.COLLECTOR_LEASE_S:
                    self.status = "store unreachable"

    # ---------------------------------------------------------------- Server Status
    def _init_host(self) -> None:
        from .host import HostMonitor
        for name, tier, help_, unit in HOST_METRICS:
            self.eng.tsdb.register(name, tier, help_, unit)
        self.host = HostMonitor()
        self.pub.extra["server"] = self._server_view
        self._sample_host(force=True)

    def _sample_host(self, force: bool = False) -> None:
        tick = self.eng.tick_n
        try:
            h = self.host.sample()
        except Exception as e:  # noqa: BLE001
            self._fail(e)
            return
        try:
            si = self.store.server_info(key_stats=force or tick % 15 == 0)
            if si.get("groups") is None and self.store_info.get("groups"):
                si["groups"], si["our_keys"] = self.store_info["groups"], self.store_info.get("our_keys")
            self.store_info = si
        except Exception as e:  # noqa: BLE001
            self.store_info = {**self.store_info, "error": redact(str(e))[:200]}
        self.host_sample = h
        self.eng.tsdb.record(tick, self.eng.now, {
            "host_cpu_pct": h["cpu_pct"], "host_mem_pct": h["mem"]["pct"], "host_disk_pct": h["disk"]["pct"],
            "host_load1": h["load"][0], "host_net_rx_mbps": h["net_rx_mbps"], "host_net_tx_mbps": h["net_tx_mbps"],
            "host_disk_read_mbs": h["disk_read_mbs"], "host_disk_write_mbs": h["disk_write_mbs"],
            "store_used_mb": self.store_info.get("used_mb", 0.0), "store_ops_per_sec": self.store_info.get("ops_per_sec") or 0,
            "host_cpu_pct_24h": h["cpu_pct"], "host_mem_pct_24h": h["mem"]["pct"]}, force=force)

    def _server_view(self) -> dict:
        m = self.pub.last.get("meta") or {}
        return {"host": self.host.static if self.host else {}, "now": self.host_sample, "store": self.store_info,
                "collector": {"owner": self.owner, "role": self.role, "status": self.status, "tick": self.eng.tick_n,
                              "tick_ms": round(self.eng.tick_ms, 1), "build_ms": m.get("build_ms"), "publish_bytes": m.get("bytes"),
                              "tick_s": config.SIM_TICK_SEC, "started": self.eng.boot},
                "release": config.RELEASE_NAME, "sampled_at": time.time()}

    def _fail(self, e: BaseException) -> None:
        self.errors += 1
        self.last_error = redact(f"{type(e).__name__}: {e}")[:300]
        log.warning("collector error: %s", self.last_error)

    def _store_full(self) -> bool:
        """Ask the host for a store with room. True when the collector was rebound to it."""
        if not self.on_store_full:
            return False
        try:
            mem = self.store.memory()
        except Exception:  # noqa: BLE001
            mem = {}
        new = self.on_store_full(self, mem)
        if new is None:
            return False
        self.rebind(new)
        return True

    def rebind(self, store) -> None:
        with self._lock:
            try:
                self.store.release_lease(self.owner)
            except Exception:  # noqa: BLE001
                pass
            self.store = store
            if self.pub:
                self.pub.store = store
                self.pub.last.pop("catalog_sent", None)
                self.pub.log_seq = 0
            store.acquire_lease(self.owner, config.COLLECTOR_LEASE_S)
        log.warning("collector %s now publishing to %s (%s)", self.owner, store.url, store.mode)

    def stop(self) -> None:
        self.stop_evt.set()
        self.status = "stopped"
        if self.eng:
            self.eng.stop()
        try:
            self.store.release_lease(self.owner)
        except Exception:  # noqa: BLE001
            pass

    def info(self) -> dict:
        return {"owner": self.owner, "role": self.role, "status": self.status, "last_error": self.last_error,
                "errors": self.errors, "store": self.store.mode}

    # ---------------------------------------------------------------- tick → publish
    def _on_tick(self, eng) -> None:
        if self.stop_evt.is_set():
            return
        try:
            self._sample_host()
            with self._lock:
                self.pub.publish()
            if self.status != "publishing":
                self.status, self.last_error = "publishing", None
        except Exception as e:  # noqa: BLE001 — never kill the tick loop over a store hiccup
            self._fail(e)
            self.status = "publish failing"
            if is_full_error(e) and self._store_full():
                try:
                    with self._lock:
                        self.pub.publish(force=True, full=True)
                    self.status, self.last_error = "publishing", None
                except Exception as e2:  # noqa: BLE001
                    self._fail(e2)
            eng.logs.emit(time.time(), "grid-collector", "error", "publish failed: " + (self.last_error or "ok after fallback"))

    # ---------------------------------------------------------------- command bus
    def _commands(self) -> None:
        while not self.stop_evt.is_set():
            store = self.store
            try:
                msg = store.next_command(timeout=1.0)
            except Exception:  # noqa: BLE001 — store restarting
                self.stop_evt.wait(1.0)
                continue
            if msg:
                self.handle(msg, store)

    def handle(self, msg: dict, store=None) -> None:
        store = store or self.store
        rid, name, args = msg.get("id"), msg.get("cmd"), msg.get("args") or {}
        if time.time() - float(msg.get("t", 0)) > 20:        # the caller has long given up — don't act late
            store.reply(rid, {"ok": False, "status": 408, "error": "command expired before it was processed"})
            return
        fn = self.handlers.get(name)
        if fn is None:
            store.reply(rid, {"ok": False, "status": 400, "error": f"unknown command {name!r}"})
            return
        try:
            result = fn(**args)
            if name not in C.READ_ONLY:           # the reply only goes out once the store reflects the change
                with self._lock:
                    self.pub.publish(force=True, kinds=C.REFRESH.get(name))
            store.reply(rid, {"ok": True, "result": result})
        except LookupError as e:
            store.reply(rid, {"ok": False, "status": 404, "error": str(e).strip("'")})
        except (ValueError, TypeError) as e:
            store.reply(rid, {"ok": False, "status": 400, "error": str(e)})
        except Exception as e:  # noqa: BLE001
            store.reply(rid, {"ok": False, "status": 500, "error": redact(f"{type(e).__name__}: {e}")})
