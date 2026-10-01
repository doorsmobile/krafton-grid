"""Read-model store — the only contract between the collector and the web tier.

    collector (simulated or real telemetry)  ──write──▶  Redis  ◀──read──  web (pages · APIs · SSE)
                     ▲                                              │
                     └──────────── command bus (cmd / reply:*) ◀────┘

Key layout under ``{REDIS_PREFIX}:`` (default ``dcim:aidc100:claude``):

    live                 JSON   current snapshot, rewritten every tick (+ PUBLISH on channel ``live``)
    view:{name}          JSON   one precomputed read model per page (overview / list pages)
    ent:{kind}           HASH   id → JSON, one precomputed read model per detail page
    ts:catalog           JSON   metric catalog (name, tier, labels, unit …)
    ts:{metric}          BYTES  ring snapshot: header(n, width) · ts float64[n] · values float32[width × n] column-major
    logs                 LIST   JSON log lines (capped)
    meta                 JSON   collector heartbeat: tick, tick_ms, publish_ms, published_at, pid …
    lease:collector      STR    owner id of the one collector allowed to write (PX lease)
    cmd / reply:{id}     LIST   command bus: web RPUSHes a command, collector BLPOPs it and RPUSHes the reply

``RedisStore`` is the real thing. ``MemoryStore`` implements the same contract in-process
so the app (and the test-suite) still runs where no Redis is installed — the read path is
identical either way: the web tier never touches the simulator's objects.
"""
from __future__ import annotations

import json
import queue
import struct
import threading
import time
import uuid
from typing import Any, Callable

from . import config

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

TS_HEADER = struct.Struct("<ii")  # n samples, width columns


class StoreError(RuntimeError):
    pass


class CommandTimeout(StoreError):
    pass


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False, separators=(",", ":"))


# ============================================================================ redis
class RedisStore:
    mode = "redis"

    def __init__(self, url: str, prefix: str):
        if redis is None:
            raise StoreError("redis-py not installed")
        self.url, self.prefix = url, prefix
        self.r = redis.Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=5, health_check_interval=30)
        self.r.ping()

    def k(self, name: str) -> str:
        return f"{self.prefix}:{name}"

    # ----------------------------------------------------------------- write (collector)
    def write(self, strings: dict[str, str | bytes] | None = None, hashes: dict[str, dict[str, str]] | None = None,
              lists: dict[str, tuple[list[str], int]] | None = None, publish: dict[str, str] | None = None) -> None:
        """One round-trip: SET strings, atomically replace hashes, append+trim lists, then PUBLISH."""
        p = self.r.pipeline(transaction=False)
        for name, v in (strings or {}).items():
            p.set(self.k(name), v)
        for name, mapping in (hashes or {}).items():
            tmp = self.k(name + ":tmp")
            p.delete(tmp)
            if mapping:
                p.hset(tmp, mapping=mapping)
                p.rename(tmp, self.k(name))   # readers never see a half-written hash
        for name, (items, cap) in (lists or {}).items():
            if items:
                p.rpush(self.k(name), *items)
                p.ltrim(self.k(name), -cap, -1)
        for ch, msg in (publish or {}).items():
            p.publish(self.k(ch), msg)
        p.execute()

    def delete(self, names: list[str]) -> None:
        if names:
            self.r.delete(*[self.k(n) for n in names])

    def delete_prefix(self, prefix: str) -> None:
        keys = list(self.r.scan_iter(match=self.k(prefix) + "*", count=500))
        if keys:
            self.r.delete(*keys)

    # ----------------------------------------------------------------- read (web)
    def get(self, name: str) -> bytes | None:
        return self.r.get(self.k(name))

    def get_json(self, name: str):
        raw = self.r.get(self.k(name))
        return json.loads(raw) if raw else None

    def hget_json(self, name: str, field: str):
        raw = self.r.hget(self.k(name), field)
        return json.loads(raw) if raw else None

    def hkeys(self, name: str) -> list[str]:
        return [k.decode() for k in self.r.hkeys(self.k(name))]

    def getranges(self, name: str, ranges: list[tuple[int, int]]) -> list[bytes]:
        p = self.r.pipeline(transaction=True)   # MULTI/EXEC: all slices come from the same blob version
        for a, b in ranges:
            p.getrange(self.k(name), a, b - 1)
        return p.execute()

    def lrange(self, name: str, start: int, end: int) -> list[bytes]:
        return self.r.lrange(self.k(name), start, end)

    def browse(self, limit: int = 60) -> dict:
        try:
            keys = []
            for kk in self.r.scan_iter(match=f"{self.prefix}:*", count=500):
                key = kk.decode()
                t = self.r.type(kk).decode()
                size = {"string": self.r.strlen, "list": self.r.llen, "hash": self.r.hlen, "stream": self.r.xlen}.get(t, lambda _: None)(kk)
                keys.append({"key": key, "type": t, "size": size, "ttl": self.r.ttl(kk)})
            keys.sort(key=lambda x: x["key"])
            info = self.r.info("memory")
            return {"ok": True, "mode": self.mode, "url": self.url, "prefix": self.prefix, "total_keys": len(keys),
                    "keys": keys[:limit], "used_memory_human": info.get("used_memory_human")}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "mode": self.mode, "url": self.url, "prefix": self.prefix, "error": str(e)[:160], "keys": []}

    # ----------------------------------------------------------------- live fan-out (web)
    def listen(self, channel: str, on_message: Callable[[str], None], stop: threading.Event) -> None:
        """Blocking pub/sub loop — run it in a daemon thread; reconnects on errors."""
        while not stop.is_set():
            try:
                ps = self.r.pubsub(ignore_subscribe_messages=True)
                ps.subscribe(self.k(channel))
                while not stop.is_set():
                    m = ps.get_message(timeout=1.0)
                    if m and m["type"] == "message":
                        on_message(m["data"].decode())
            except Exception:  # noqa: BLE001 — Redis restarted; retry
                time.sleep(1.0)

    # ----------------------------------------------------------------- command bus
    def call(self, cmd: str, args: dict, timeout: float = 5.0):
        rid = uuid.uuid4().hex
        self.r.rpush(self.k("cmd"), dumps({"id": rid, "cmd": cmd, "args": args, "t": time.time()}))
        got = self.r.blpop([self.k(f"reply:{rid}")], timeout=timeout)
        if not got:
            raise CommandTimeout(f"collector did not answer {cmd!r} within {timeout:.0f}s")
        return _unwrap(json.loads(got[1]))

    def next_command(self, timeout: float = 1.0) -> dict | None:
        got = self.r.blpop([self.k("cmd")], timeout=timeout)
        return json.loads(got[1]) if got else None

    def reply(self, rid: str, payload: dict) -> None:
        p = self.r.pipeline(transaction=False)
        p.rpush(self.k(f"reply:{rid}"), dumps(payload))
        p.expire(self.k(f"reply:{rid}"), 30)
        p.execute()

    # ----------------------------------------------------------------- collector lease
    def acquire_lease(self, owner: str, ttl_s: float) -> bool:
        key = self.k("lease:collector")
        if self.r.set(key, owner, nx=True, px=int(ttl_s * 1000)):
            return True
        if (self.r.get(key) or b"").decode() == owner:
            self.r.pexpire(key, int(ttl_s * 1000))
            return True
        return False

    def lease_holder(self) -> str | None:
        v = self.r.get(self.k("lease:collector"))
        return v.decode() if v else None

    def release_lease(self, owner: str) -> None:
        key = self.k("lease:collector")
        if (self.r.get(key) or b"").decode() == owner:
            self.r.delete(key)


# ============================================================================ memory
class MemoryStore:
    """Same contract, in-process. Used when Redis is unavailable and by the tests."""
    mode = "memory"

    def __init__(self, prefix: str = "mem"):
        self.url, self.prefix = "memory://", prefix
        self._s: dict[str, bytes] = {}
        self._h: dict[str, dict[str, bytes]] = {}
        self._l: dict[str, list[bytes]] = {}
        self._lock = threading.RLock()
        self._subs: dict[str, list[Callable[[str], None]]] = {}
        self._cmd: queue.Queue = queue.Queue()
        self._replies: dict[str, queue.Queue] = {}
        self._lease: tuple[str, float] | None = None

    @staticmethod
    def _b(v) -> bytes:
        return v if isinstance(v, bytes) else str(v).encode()

    def write(self, strings=None, hashes=None, lists=None, publish=None) -> None:
        with self._lock:
            for name, v in (strings or {}).items():
                self._s[name] = self._b(v)
            for name, mapping in (hashes or {}).items():
                self._h[name] = {f: self._b(v) for f, v in mapping.items()}
            for name, (items, cap) in (lists or {}).items():
                lst = self._l.setdefault(name, [])
                lst.extend(self._b(i) for i in items)
                del lst[:-cap]
        for ch, msg in (publish or {}).items():
            for fn in list(self._subs.get(ch, [])):
                fn(msg)

    def delete(self, names):
        with self._lock:
            for n in names:
                self._s.pop(n, None), self._h.pop(n, None), self._l.pop(n, None)

    def delete_prefix(self, prefix):
        with self._lock:
            for d in (self._s, self._h, self._l):
                for k in [k for k in d if k.startswith(prefix)]:
                    d.pop(k)

    def get(self, name):
        return self._s.get(name)

    def get_json(self, name):
        raw = self._s.get(name)
        return json.loads(raw) if raw else None

    def hget_json(self, name, field):
        raw = self._h.get(name, {}).get(field)
        return json.loads(raw) if raw else None

    def hkeys(self, name):
        return list(self._h.get(name, {}))

    def getranges(self, name, ranges):
        with self._lock:
            blob = self._s.get(name, b"")
            return [blob[a:b] for a, b in ranges]

    def lrange(self, name, start, end):
        with self._lock:
            lst = self._l.get(name, [])
            n = len(lst)
            a = start if start >= 0 else max(0, n + start)
            b = (end if end >= 0 else n + end) + 1
            return lst[a:b]

    def browse(self, limit=60):
        with self._lock:
            keys = [{"key": f"{self.prefix}:{k}", "type": "string", "size": len(v), "ttl": -1} for k, v in self._s.items()]
            keys += [{"key": f"{self.prefix}:{k}", "type": "hash", "size": len(v), "ttl": -1} for k, v in self._h.items()]
            keys += [{"key": f"{self.prefix}:{k}", "type": "list", "size": len(v), "ttl": -1} for k, v in self._l.items()]
        keys.sort(key=lambda x: x["key"])
        return {"ok": True, "mode": self.mode, "url": self.url, "prefix": self.prefix, "total_keys": len(keys),
                "keys": keys[:limit], "used_memory_human": "in-process"}

    def listen(self, channel, on_message, stop):
        self._subs.setdefault(channel, []).append(on_message)
        stop.wait()
        self._subs[channel].remove(on_message)

    def call(self, cmd, args, timeout=5.0):
        rid = uuid.uuid4().hex
        q: queue.Queue = queue.Queue(maxsize=1)
        self._replies[rid] = q
        self._cmd.put({"id": rid, "cmd": cmd, "args": args, "t": time.time()})
        try:
            return _unwrap(q.get(timeout=timeout))
        except queue.Empty:
            raise CommandTimeout(f"collector did not answer {cmd!r} within {timeout:.0f}s") from None
        finally:
            self._replies.pop(rid, None)

    def next_command(self, timeout=1.0):
        try:
            return self._cmd.get(timeout=timeout)
        except queue.Empty:
            return None

    def reply(self, rid, payload):
        q = self._replies.get(rid)
        if q is not None:
            q.put(json.loads(dumps(payload)))  # same JSON round-trip as Redis

    def acquire_lease(self, owner, ttl_s):
        with self._lock:
            now = time.time()
            if self._lease is None or self._lease[0] == owner or self._lease[1] < now:
                self._lease = (owner, now + ttl_s)
                return True
            return False

    def lease_holder(self):
        return self._lease[0] if self._lease and self._lease[1] >= time.time() else None

    def release_lease(self, owner):
        if self._lease and self._lease[0] == owner:
            self._lease = None


def _unwrap(payload: dict):
    if payload.get("ok"):
        return payload.get("result")
    err = payload.get("error") or "command failed"
    if payload.get("status") == 404:
        raise LookupError(err)
    raise ValueError(err)


# ============================================================================ factory
_STORE = None
_STORE_LOCK = threading.Lock()


def get_store():
    """GRID_STORE=auto (Redis if reachable, else in-process) | redis | memory."""
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            want = config.GRID_STORE
            if want in ("auto", "redis"):
                try:
                    _STORE = RedisStore(config.REDIS_URL, config.REDIS_PREFIX)
                except Exception as e:  # noqa: BLE001
                    if want == "redis":
                        raise StoreError(f"Redis unavailable at {config.REDIS_URL}: {e}") from e
            if _STORE is None:
                _STORE = MemoryStore(config.REDIS_PREFIX)
        return _STORE


def reset_store(store=None) -> None:
    """Tests: swap the process-wide store."""
    global _STORE
    with _STORE_LOCK:
        _STORE = store
