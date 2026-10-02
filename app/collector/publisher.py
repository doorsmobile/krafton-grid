"""Publisher — turns the collector's state into read models and writes them to the store.

Cadence (2 s ticks):
    every tick                  live snapshot (+ PUBLISH for SSE) · every page view · heatmaps · changed time-series tiers
    every HEAVY_EVERY_TICKS     large list views (node table, workloads, platform ops, inventory)
    every ENTITY_EVERY_TICKS    detail-page entities (625 nodes, racks, devices, jobs, pods, cloud resources)
    force=True                  every view + entity — right after a command, so the next read reflects it
    full=True                   force + every time-series ring — at start-up

Builders read engine state under the engine lock (a consistent cut); encoding happens under the
same lock so no command can mutate a dict mid-serialisation. The store write itself is outside it.
"""
from __future__ import annotations

import os
import threading
import time

from .. import config
from ..readmodel import biz as BV
from ..readmodel import facility as FV
from ..readmodel import it as IV
from ..readmodel import ops as OV
from ..sim import topology as T
from ..sim.fleet import G, THROTTLE_C, XID_CODES
from ..sim.tsdb import TIERS
from ..store import dumps, dumpz

LOG_CAP = config.LOG_CAP   # 5,000 lines (~1 MB) · 30,000 with GRID_DATA_PROFILE=large

FAST_VIEWS = {
    "main": OV.main, "campus": OV.campus,
    "facility": FV.overview, "power": FV.power, "cooling": FV.cooling, "capacity": FV.capacity, "energy": FV.energy,
    "facility_snapshot": lambda e: e.facility.snapshot,
    "gpu_fleet": IV.gpu_fleet, "storage": IV.storage, "storage_toptalkers": IV.storage_toptalkers,
    "network": IV.network, "topology": IV.topology, "kubernetes": IV.kubernetes,
    "gpu_platform": OV.gpu_platform,
    "cloud": OV.cloud, "cloud_aws": OV.cloud_aws, "cloud_gcp": OV.cloud_gcp, "cloud_nhn": OV.cloud_nhn,
    "racks": OV.racks, "alerts": OV.alerts, "integrations": OV.integrations, "alert_config": OV.alert_config,
    "incidents": lambda e: {"incidents": e.alerts.incident_list(100)},
    "deliveries": lambda e: {"deliveries": list(e.alerts.deliveries)[:400]},
    "observability": OV.observability, "relay": OV.relay_state, "usage": OV.resource_usage,
    "events": lambda e: {"events": OV.explore_events(e, 86400)},
    "cost": BV.summary, "cost_dc": BV.dc, "cost_cloud": BV.cloud, "budget": BV.budget,
    "budget_requests": lambda e: {"requests": e.cost.requests},
    "cost_months": lambda e: {"months": e.monthly()},
    "simulation": OV.simulation, "vendors": OV.vendors, "tech_spec": OV.tech_spec,
    **{f"heatmap:{m}": (lambda e, m=m: IV.heatmap(e, m)) for m in IV.HEAT_METRICS},
    "gpu_alloc": lambda e: {"alloc": (e.fleet.gpu_job >= 0).astype(int).tolist()},
}
COLLECTOR_VIEWS = {"server"}   # built by the Collector itself (host + store telemetry), see Collector._server_view

HEAVY_VIEWS = {
    "gpu_nodes": IV.gpu_nodes, "workloads": OV.gpu_workloads, "gpu_ops": OV.gpu_ops, "inventory": OV.inventory,
}


# ------------------------------------------------------------------------------ entities
def _slim_job(j):
    return {k: v for k, v in j.items() if k != "node_list"} if isinstance(j, dict) else j


def _node_entities(e) -> dict:
    xids: dict[int, list] = {}
    for t, gi, c in e.fleet.xid_ts:
        xids.setdefault(gi, []).append({"t": t, "code": c, "desc": XID_CODES[c][0]})
    limits = {"tdp_w": T.GPU_TDP_W, "throttle_c": THROTTLE_C, "hbm_gb": T.GPU_HBM_GB}
    out = {}
    for n, nid in enumerate(T.NODE_IDS):
        d = IV.gpu_node(e, nid)
        for g in d["gpus"]:
            g["job"] = _slim_job(g.get("job"))
        d["xids"] = {str(g): xids.get(n * G + g, [])[-10:][::-1] for g in range(G)}
        d["limits"] = limits
        out[nid] = d
    return out


def _job_entities(e) -> dict:
    out = {str(jid): IV.gpu_job(e, str(jid)) for jid in list(e.fleet.jobs)}
    for fin in e.fleet.finished:
        out.setdefault(str(fin["id"]), {"job": fin, "finished": True, "gpus": []})
    return out


def _pod_entities(e) -> dict:
    out = {}
    for gi, inst in e.fleet.mig.items():
        rec = e.fleet.gpu_record(gi, e.now)
        rec["job"] = _slim_job(rec.get("job"))
        for x in inst:
            out[x["pod"]] = {"pod": x, "gpu": rec, "kind": "mig-inference", "siblings": inst}
    for p in e.k8s.pods:
        out.setdefault(p["name"], {"pod": p, "gpu": None, "kind": "k8s", "siblings": []})
    return out


ENTITIES = {
    "gpu_node": _node_entities,
    "gpu_job": _job_entities,
    "gpu_pod": _pod_entities,
    "rack": lambda e: {r.id: OV.rack(e, r.id) for r in T.RACKS},
    "power_device": lambda e: {d["id"]: FV.power_device(e, d["id"]) for d in T.POWER_DEVICES},
    "cooling_device": lambda e: {d["id"]: FV.cooling_device(e, d["id"]) for d in T.COOLING_DEVICES},
    "hall": lambda e: {h["id"]: FV.hall(e, h["id"]) for h in T.HALLS},
    "storage_cluster": lambda e: {c["id"]: IV.storage_cluster(e, c["id"]) for c in T.STORAGE_CLUSTERS},
    "network_device": lambda e: {d["id"]: IV.network_device(e, d["id"]) for d in T.NET_DEVICES},
    "k8s_node": lambda e: {n["id"]: IV.k8s_node(e, n["id"]) for n in T.K8S_NODES},
    "aws_instance": lambda e: {i["id"]: OV.aws_instance(e, i["id"]) for i in e.cloud.aws_instances},
    "gcp_bucket": lambda e: {b["name"]: OV.gcp_bucket(e, b["name"]) for b in e.cloud.buckets},
    "gcp_disk": lambda e: {d["id"]: OV.gcp_disk(e, d["id"]) for d in e.cloud.disks},
    "nhn_instance": lambda e: {n["id"]: OV.nhn_instance(e, n["id"]) for n in e.cloud.nhn},
}


class Publisher:
    def __init__(self, eng, store, owner: str):
        self.eng, self.store, self.owner = eng, store, owner
        self.lock = threading.Lock()          # tick thread and command thread both publish
        self.log_seq = 0
        self.last: dict = {}
        self.published = 0
        self.extra: dict = {}                 # collector-level read models (e.g. Server Status): name → () -> dict

    def reset(self) -> None:
        """A fresh collector owns the keyspace: drop read models left by a previous run."""
        self.store.delete_prefix("ent:")
        self.store.delete(["logs", "meta", "scenarios", "incidents", "events", "alerts:active", "budget:requests"])  # + v2.0 mirror keys

    def publish(self, force: bool = False, full: bool = False, kinds: set[str] | None = None) -> dict:
        """force: every view (after a command) + the entity ``kinds`` it touched. full: everything incl. all rings (start-up)."""
        e, tick = self.eng, self.eng.tick_n
        with self.lock:
            t0 = time.perf_counter()
            strings: dict[str, str | bytes] = {}
            hashes: dict[str, dict[str, str]] = {}
            lists: dict[str, tuple[list[str], int]] = {}
            heavy = force or full or tick % config.HEAVY_EVERY_TICKS == 0
            on_cadence = full or tick % config.ENTITY_EVERY_TICKS == 0
            entity_kinds = set(ENTITIES) if on_cadence else set(kinds or ())
            with e.lock:
                live = dumps(e.live)
                strings["live"] = live
                for name, fn in FAST_VIEWS.items():
                    strings[f"view:{name}"] = dumpz(fn(e))
                for name, fn in self.extra.items():
                    strings[f"view:{name}"] = dumpz(fn())
                if heavy:
                    for name, fn in HEAVY_VIEWS.items():
                        strings[f"view:{name}"] = dumpz(fn(e))
                for kind in entity_kinds:
                    hashes[f"ent:{kind}"] = {k: dumpz(v) for k, v in ENTITIES[kind](e).items() if v is not None}
                for m in e.tsdb.metrics.values():
                    if full or tick % TIERS[m.tier]["every"] == 0:
                        strings[f"ts:{m.name}"] = m.encode()
                if not self.last.get("catalog_sent"):          # labels are fixed at registration — publish once
                    strings["ts:catalog"] = dumpz(e.tsdb.catalog(with_labels=True))
                    self.last["catalog_sent"] = True
                new_logs = e.logs.since(self.log_seq)
                if new_logs:
                    self.log_seq = new_logs[-1]["seq"]
                    lists["logs"] = ([dumps(l) for l in new_logs], LOG_CAP)
                build_ms = (time.perf_counter() - t0) * 1000
            self.published += 1
            meta = {"tick": tick, "tick_ms": round(e.tick_ms, 2), "build_ms": round(build_ms, 1),
                    "published_at": time.time(), "boot": e.boot, "sim_now": e.now, "owner": self.owner, "pid": os.getpid(),
                    "store": self.store.mode, "release": config.RELEASE_NAME, "tick_s": config.SIM_TICK_SEC,
                    "bytes": sum(len(v) for v in strings.values()) + sum(len(v) for h in hashes.values() for v in h.values()),
                    "views": len([k for k in strings if k.startswith("view:")]), "entities": {k: len(v) for k, v in hashes.items()},
                    "force": force, "full": full, "published": self.published}
            if on_cadence:
                self.last["entities_at"] = meta["published_at"]
            meta["entities_at"] = self.last.get("entities_at")
            strings["meta"] = dumps(meta)
            self.store.write(strings=strings, hashes=hashes, lists=lists, publish={"live": live})
            meta["write_ms"] = round((time.perf_counter() - t0) * 1000 - build_ms, 1)
            self.last["meta"] = meta
            return meta
