"""Web read path. Everything a page, API, SSE stream or the Mission Control agent shows comes
from here, and everything here comes from the store (Redis) — never from the collector's objects.

    rm.live()                      live snapshot                      (key: live)
    rm.view(name)                  page read model                    (key: view:{name})
    rm.entity(kind, id)            detail-page read model             (hash: ent:{kind})
    rm.tsdb                        time series · PromQL source        (keys: ts:catalog, ts:{metric})
    rm.logs(q, …)                  LogQL over published log lines     (list: logs)
    rm.cmd(name, **args)           command bus → collector            (lists: cmd, reply:{id})
"""
from __future__ import annotations

import asyncio
import json
import threading
import time

import numpy as np
from fastapi import HTTPException

from .. import config
from ..sim import topology as T
from ..sim.logs import query_lines
from ..sim.tsdb import _to_points
from ..store import TS_HEADER, CommandTimeout, get_store


class NotReady(RuntimeError):
    """The collector has not published this read model yet (start-up)."""


# ============================================================================ time series
class RemoteMetric:
    """Same surface as ``sim.tsdb.Metric`` (labels · column · window) backed by a store blob."""

    def __init__(self, store, row: dict):
        self.store = store
        self.name, self.tier, self.help = row["name"], row["tier"], row["help"]
        self.unit, self.kind = row["unit"], row["kind"]
        self.labels: list[dict] = row.get("label_sets") or [{}]
        self._n: int | None = None
        self._isz = 4

    @property
    def width(self) -> int:
        return len(self.labels)

    def column(self, **match) -> int | None:
        for i, lab in enumerate(self.labels):
            if all(lab.get(k) == v for k, v in match.items()):
                return i
        return None

    def _read(self, cols: list[int] | None) -> tuple[np.ndarray, np.ndarray]:
        key = f"ts:{self.name}"
        h = TS_HEADER.size
        for _ in range(3):
            if self._n is None:
                raw = self.store.getranges(key, [(0, h)])[0]
                if len(raw) < h:
                    raise NotReady(f"series {self.name} not published yet")
                self._n, _, self._isz, _ = TS_HEADER.unpack(raw)
            n, w, isz = self._n, self.width, self._isz
            dtype = "<f2" if isz == 2 else "<f4"
            base = h + 8 * n
            whole = cols is None or len(cols) > 24
            if whole:
                ranges = [(0, h), (h, base), (base, base + isz * n * w)]
            else:
                ranges = [(0, h), (h, base)] + [(base + isz * n * c, base + isz * n * (c + 1)) for c in cols]
            parts = self.store.getranges(key, ranges)
            if len(parts[0]) < h or TS_HEADER.unpack(parts[0])[0::2] != (n, isz):
                self._n = None                     # ring grew, was replaced or changed precision — retry
                continue
            ts = np.frombuffer(parts[1], dtype="<f8")
            if whole:
                mat = np.frombuffer(parts[2], dtype=dtype).reshape(w, n).T.astype(np.float32)
                vals = mat if cols is None else mat[:, cols]
            else:
                vals = (np.stack([np.frombuffer(p, dtype=dtype) for p in parts[2:]], axis=1).astype(np.float32)
                        if cols else np.zeros((n, 0), np.float32))
            return ts, vals
        raise NotReady(f"series {self.name} is being rewritten")

    def window(self, seconds: float | None = None, now: float | None = None, cols: list[int] | None = None):
        ts, vals = self._read(cols)
        if seconds is None or not len(ts):
            return ts, vals
        end = now if now is not None else ts[-1]
        mask = ts >= end - seconds
        return ts[mask], vals[mask]


class RemoteTSDB:
    """Drop-in for ``sim.tsdb.TSDB`` as far as PromQL and /api/series are concerned."""

    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self._metrics: dict[str, RemoteMetric] = {}
        self._catalog: list[dict] = []
        self._loaded = 0.0

    @property
    def metrics(self) -> dict[str, RemoteMetric]:
        if time.time() - self._loaded > 300 or not self._metrics:
            rows = self.store.get_json("ts:catalog")
            if not rows:
                raise NotReady("metric catalog not published yet")
            self._metrics = {r["name"]: RemoteMetric(self.store, r) for r in rows}
            self._catalog = [{k: v for k, v in r.items() if k != "label_sets"} for r in rows]
            self._loaded = time.time()
        return self._metrics

    def catalog(self) -> list[dict]:
        self.metrics  # noqa: B018 — refresh
        return self._catalog

    def series(self, name: str, col: int = 0, seconds: float | None = None, max_points: int = 900) -> list[list]:
        m = self.metrics.get(name)
        if m is None:
            return []
        ts, vals = m.window(seconds, cols=[col])
        return _to_points(ts, vals[:, 0] if vals.size else np.array([]), max_points)

    def series_multi(self, name: str, cols: list[int], seconds: float | None = None, max_points: int = 600) -> list[list[list]]:
        m = self.metrics.get(name)
        if m is None:
            return [[] for _ in cols]
        ts, vals = m.window(seconds, cols=list(cols))
        return [_to_points(ts, vals[:, i], max_points) if vals.size else [] for i in range(len(cols))]


# ============================================================================ read model
class ReadModel:
    def __init__(self, store=None):
        self._store = store
        self._tsdb: RemoteTSDB | None = None

    @property
    def store(self):
        if self._store is None:
            self._store = get_store()
        return self._store

    def bind(self, store) -> None:
        self._store, self._tsdb = store, None

    @property
    def tsdb(self) -> RemoteTSDB:
        if self._tsdb is None or self._tsdb.store is not self.store:
            self._tsdb = RemoteTSDB(self.store)
        return self._tsdb

    # ------------------------------------------------------------------ plain reads
    def live(self) -> dict:
        v = self.store.get_json("live")
        if v is None:
            raise NotReady("live snapshot not published yet")
        return v

    def live_or_empty(self) -> dict:
        try:
            return self.live()
        except Exception:  # noqa: BLE001 — error pages must render even with no data
            return {}

    def view(self, name: str) -> dict:
        v = self.store.get_json(f"view:{name}")
        if v is None:
            raise NotReady(f"view {name} not published yet")
        return v

    def entity(self, kind: str, eid: str) -> dict | None:
        v = self.store.hget_json(f"ent:{kind}", eid)
        if v is None and not self.store.hkeys(f"ent:{kind}"):
            raise NotReady(f"{kind} entities not published yet")
        return v

    def meta(self) -> dict | None:
        return self.store.get_json("meta")

    def ready(self) -> bool:
        m = self.meta()
        return bool(m) and time.time() - m["published_at"] < 30

    def wait_ready(self, timeout: float = 30.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.ready() and self.store.hkeys("ent:gpu_node"):
                    return True
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.1)
        return False

    def logs(self, q: str, window_s: float, limit: int) -> dict:
        raw = self.store.lrange("logs", -5000, -1)
        lines = [json.loads(x) for x in raw]
        now = (self.meta() or {}).get("sim_now") or time.time()
        return query_lines(lines, q, now, window_s, limit)

    # ------------------------------------------------------------------ commands
    def cmd(self, _cmd: str, _timeout: float = 6.0, **args):
        try:
            return self.store.call(_cmd, args, timeout=_timeout)
        except LookupError as e:
            raise HTTPException(404, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except CommandTimeout as e:
            raise HTTPException(503, str(e)) from None

    async def acmd(self, _cmd: str, _timeout: float = 6.0, **args):
        return await asyncio.to_thread(self.cmd, _cmd, _timeout, **args)

    # ------------------------------------------------------------------ projections over read models
    def gpu_device(self, gid: str) -> dict | None:
        gi = T.parse_gpu_id(gid.lower())
        if gi is None:
            return None
        node = self.entity("gpu_node", T.NODE_IDS[gi // 8])
        if node is None:
            return None
        slot = gi % 8
        gpus = node["gpus"]
        rec = gpus[slot]
        siblings = [{"id": g["id"], "slot": i, "util": g["util"], "temp": g["temp_c"], "self": i == slot} for i, g in enumerate(gpus)]
        return {"gpu": rec, "siblings": siblings, "xids": node["xids"].get(str(slot), []), "series_col": gi, "limits": node["limits"]}

    def gpu_nodes(self, q: str = "", state: str = "", partition: str = "", rack: str = "", sort: str = "id", limit: int = 700) -> dict:
        rows = self.view("gpu_nodes")["rows"]
        if q:
            ql = q.lower()
            rows = [r for r in rows if ql in r["id"] or ql in r["job"].lower() or ql in r["user"].lower() or ql in r["project"].lower()]
        if state:
            rows = [r for r in rows if r["state"] == state]
        if partition:
            rows = [r for r in rows if r["partition"] == partition]
        if rack:
            rows = [r for r in rows if r["rack"] == rack.upper()]
        key = {"util": lambda r: -r["util"], "temp": lambda r: -r["temp"], "power": lambda r: -r["power_kw"],
               "mem": lambda r: -r["mem_gb"]}.get(sort)
        if key:
            rows = sorted(rows, key=key)
        return {"total": len(rows), "rows": rows[:limit]}

    def inventory(self, q: str = "", domain: str = "") -> dict:
        d = self.view("inventory")
        items = d["items"]
        if q:
            ql = q.lower()
            items = [i for i in items if ql in i["id"].lower() or ql in (i["model"] or "").lower() or ql in (i["vendor"] or "").lower()]
        if domain:
            items = [i for i in items if i["domain"] == domain]
        return {**d, "items": items, "total": len(items)}

    def events(self, window_s: float) -> list[dict]:
        now = (self.meta() or {}).get("sim_now") or time.time()
        return [e for e in self.view("events")["events"] if e["t"] >= now - window_s]

    def search(self, q: str, pages: list[dict]) -> list[dict]:
        from ..sim.scenarios import SCENARIOS
        ql = (q or "").strip().lower()
        if not ql:
            return [{"kind": "page", **p} for p in pages[:12]]
        out = [{"kind": "page", **p} for p in pages
               if ql in p["title"].lower() or ql in p.get("group", "").lower() or ql in p["href"]]
        for s in SCENARIOS:
            if ql in s["name"].lower() or ql in s["id"] or "scenario" in ql or "시나리오" in ql:
                out.append({"kind": "action", "title": f"Run scenario · {s['name']}", "href": f"/platform/simulation?run={s['id']}",
                            "group": "Simulation", "action": {"method": "POST", "url": f"/api/sim/scenario/{s['id']}/start"}})
        for rk in T.RACKS:
            if ql == rk.id.lower() or (len(ql) >= 2 and rk.id.lower().startswith(ql)):
                out.append({"kind": "rack", "title": f"Rack {rk.id}", "href": f"/rack/{rk.id}", "group": f"{rk.hall} · {rk.label}"})
        if ql.startswith("kg-"):
            for nid in T.NODE_IDS:
                if nid.startswith(ql):
                    out.append({"kind": "node", "title": nid, "href": f"/gpu-fleet/node/{nid}", "group": "GPU node"})
                    if len(out) > 30:
                        break
            if "-g" in ql and T.parse_gpu_id(ql) is not None:
                out.insert(0, {"kind": "gpu", "title": ql, "href": f"/gpu-fleet/device/{ql}", "group": "GPU device"})
        for d in T.NET_DEVICES:
            if ql in d["id"]:
                out.append({"kind": "device", "title": d["id"], "href": f"/network/device/{d['id']}", "group": f"{d['vendor']} {d['model']}"})
        for d in T.POWER_DEVICES + T.COOLING_DEVICES:
            if ql in d["id"].lower():
                base = "/facility/power/" if d in T.POWER_DEVICES else "/facility/cooling/"
                out.append({"kind": "equipment", "title": d["id"], "href": base + d["id"], "group": d["name"]})
        for n in T.K8S_NODES:
            if ql in n["id"]:
                out.append({"kind": "k8s", "title": n["id"], "href": f"/kubernetes/node/{n['id']}", "group": "Kubernetes node"})
        for p in T.PROJECTS:
            if ql in p["id"] or ql in p["name"].lower():
                out.append({"kind": "project", "title": p["name"], "href": f"/gpu-platform/ops?tab=projects#{p['id']}", "group": p["team"]})
        try:
            for a in self.view("alerts")["active"]:
                if ql in a["name"].lower() or ql in a["summary"].lower():
                    out.append({"kind": "alert", "title": a["name"], "href": f"/alerts?focus={a['id']}", "group": a["severity"]})
        except NotReady:
            pass
        return out[:40]


rm = ReadModel()

# process-local runtime facts the web tier reports (/healthz, warm-up page); set by app.main
runtime: dict = {"collector": None, "store_note": None, "started": time.time()}


def collector_state() -> dict:
    c = runtime["collector"]
    if c is not None:
        info = c.info()
    else:
        m = rm.meta() if rm._store is not None else None
        info = {"status": "external" if m else "none", "owner": (m or {}).get("owner"), "last_error": None}
    return {**info, "store_note": runtime["store_note"]}


# ============================================================================ live fan-out (SSE)
class LiveHub:
    """One store subscription per web process, fanned out to every SSE client."""

    def __init__(self):
        self.clients: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        self.stop_evt = threading.Event()
        self.thread: threading.Thread | None = None
        self.received = 0

    def start(self, store) -> None:
        """(Re)subscribe to the store's live channel — called again if the app switches stores."""
        self.stop_evt.set()
        self.stop_evt = threading.Event()
        self.thread = threading.Thread(target=store.listen, args=("live", self._on_message, self.stop_evt),
                                       name="grid-live-hub", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_evt.set()

    def _on_message(self, payload: str) -> None:
        self.received += 1
        for loop, q in list(self.clients):
            try:
                loop.call_soon_threadsafe(_offer, q, payload)
            except RuntimeError:
                self.clients.discard((loop, q))

    def subscribe(self, loop) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=4)
        self.clients.add((loop, q))
        return q

    def unsubscribe(self, loop, q) -> None:
        self.clients.discard((loop, q))


def _offer(q: asyncio.Queue, payload: str) -> None:
    if q.full():
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    q.put_nowait(payload)


hub = LiveHub()


def need(v, what: str):
    if v is None:
        raise HTTPException(404, f"{what} not found")
    return v


__all__ = ["rm", "hub", "need", "NotReady", "config"]
