"""Storage (IBM Storage Scale), network fabric (Arista + NVIDIA IB) and Dell K8s.

Load is derived from the fleet: training reads and synchronous checkpoint
writes land on the storage tiers, collectives land on the IB fabric, storage
and north-south traffic land on Ethernet.
"""
from __future__ import annotations

import math
import zlib
from collections import deque

import numpy as np

from . import topology as T


# ============================================================== storage
class Storage:
    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        nsd = T.SU_COUNT * T.NSD_PER_BLOCK
        self.clusters = {
            "ss-hot": {"used_pb": 84.6, "read_gbs": 0.0, "write_gbs": 0.0, "iops_k": 0.0, "latency_ms": 0.3,
                       "queue": 2.0, "meta_kops": 0.0, "health": "healthy", "nsd_up": nsd, "nsd_total": nsd},
            "ss-cold": {"used_pb": 211.8, "read_gbs": 0.0, "write_gbs": 0.0, "iops_k": 0.0, "latency_ms": 4.5,
                        "queue": 3.0, "meta_kops": 0.0, "health": "healthy", "nsd_up": nsd, "nsd_total": nsd},
        }
        self.volumes = []
        quotas = {"llm-pretrain": (32000, 96000), "pubg-ally": (8000, 28000), "inzoi-smartzoi": (6800, 24000),
                  "speech-voice": (3200, 14000), "vision-gen": (6000, 36000), "inference-prod": (2000, 6000),
                  "research-sandbox": (2400, 12000)}
        for pid, (hot_q, cold_q) in quotas.items():
            self.volumes.append({"id": f"hot-{pid}", "cluster": "ss-hot", "path": f"/gpfs/hot/{pid}", "project": pid,
                                 "quota_tb": hot_q, "used_tb": round(hot_q * rng.uniform(0.55, 0.9), 1)})
            self.volumes.append({"id": f"cold-{pid}", "cluster": "ss-cold", "path": f"/gpfs/cold/{pid}",
                                 "project": pid, "quota_tb": cold_q, "used_tb": round(cold_q * rng.uniform(0.5, 0.85), 1)})
        for vid, cl, path, q in [("hot-datasets", "ss-hot", "/gpfs/hot/datasets", 18000),
                                 ("hot-scratch", "ss-hot", "/gpfs/hot/scratch", 7000),
                                 ("cold-datasets-raw", "ss-cold", "/gpfs/cold/datasets-raw", 60000),
                                 ("cold-home", "ss-cold", "/gpfs/cold/home", 4000),
                                 ("cold-ckpt", "ss-cold", "/gpfs/cold/checkpoints", 50000),
                                 ("cold-telemetry", "ss-cold", "/gpfs/cold/telemetry", 12000)]:
            self.volumes.append({"id": vid, "cluster": cl, "path": path, "project": "shared", "quota_tb": q,
                                 "used_tb": round(q * rng.uniform(0.6, 0.85), 1)})
        for v in self.volumes:
            v.update(read_gbs=0.0, write_gbs=0.0, iops_k=0.0, latency_ms=0.3, queue=1.0)
        self.vol_by_id = {v["id"]: v for v in self.volumes}

    def step(self, dt: float, read_gbs: float, write_gbs: float, io_by_project: dict, faults: set[str],
             storm: float, now: float = 0.0) -> None:
        rng = self.rng
        if storm and (now % 60) < 22:  # aligned checkpoint boundaries every minute
            write_gbs += storm * 380.0
        # hot takes training reads and synchronous checkpoints; cold takes raw-dataset staging and the
        # ILM migration of older checkpoints off hot (policy-driven, steady)
        demand = {"ss-hot": (read_gbs * 0.82, write_gbs * 0.92),
                  "ss-cold": (read_gbs * 0.18 + 24.0 + rng.uniform(0, 8), write_gbs * 0.08 + 40.0 + rng.uniform(0, 12))}
        for cid, (r, w) in demand.items():
            c = self.clusters[cid]
            spec = T.STORAGE_BY_ID[cid]
            degraded = f"NSD-{cid}" in faults
            c["nsd_up"] = c["nsd_total"] - (T.NSD_PER_BLOCK if degraded else 0)   # one building block offline
            cap_r = spec["peak_read_gbs"] * c["nsd_up"] / c["nsd_total"]
            cap_w = spec["peak_write_gbs"] * c["nsd_up"] / c["nsd_total"]
            r_eff = min(r, cap_r * 0.97)
            w_eff = min(w, cap_w * 0.97)
            c["read_gbs"] += (r_eff * rng.uniform(0.95, 1.05) - c["read_gbs"]) * 0.5
            c["write_gbs"] += (w_eff * rng.uniform(0.95, 1.05) - c["write_gbs"]) * 0.6
            util = max(c["read_gbs"] / cap_r, c["write_gbs"] / cap_w)
            base = {"ss-hot": 0.28, "ss-cold": 4.2}[cid]
            c["latency_ms"] = round(base * (1 + 6 * util ** 3) + rng.normal(0, base * 0.03), 3)
            io_kb = {"ss-hot": 512, "ss-cold": 2048}[cid]
            c["iops_k"] = round((c["read_gbs"] + c["write_gbs"]) * 1e6 / io_kb / 1000, 1)
            c["queue"] = round(1 + 30 * util ** 2, 1)
            c["meta_kops"] = round((18 + 60 * util) * (1.0 if cid == "ss-hot" else 0.35) + rng.normal(0, 2), 1)
            c["util_pct"] = round(util * 100, 1)
            c["health"] = "degraded" if degraded else ("busy" if util > 0.85 else "healthy")
            c["used_pb"] = min(T.STORAGE_BY_ID[cid]["capacity_pb"] * 0.995,
                               c["used_pb"] + (c["write_gbs"] - c["read_gbs"] * 0.02) * dt / 1e6 * 0.02)
        # volumes: attribute cluster I/O by project demand share
        tot_r = sum(v[0] for v in io_by_project.values()) or 1.0
        tot_w = sum(v[1] for v in io_by_project.values()) or 1.0
        for v in self.volumes:
            c = self.clusters[v["cluster"]]
            if v["project"] == "shared":
                rs, ws = (0.22, 0.02) if "datasets" in v["id"] else (0.04, 0.06)
            else:
                pr, pw = io_by_project.get(v["project"], (0.0, 0.0))
                rs, ws = pr / tot_r * 0.7, pw / tot_w * 0.9
            v["read_gbs"] = round(c["read_gbs"] * rs * rng.uniform(0.9, 1.1), 2)
            v["write_gbs"] = round(c["write_gbs"] * ws * rng.uniform(0.9, 1.1), 2)
            io_kb = 512 if v["cluster"] == "ss-hot" else 2048
            v["iops_k"] = round((v["read_gbs"] + v["write_gbs"]) * 1e6 / io_kb / 1000, 1)
            v["latency_ms"] = round(c["latency_ms"] * rng.uniform(0.9, 1.25), 3)
            v["queue"] = round(c["queue"] * rng.uniform(0.3, 1.0), 1)
            v["used_tb"] = round(min(v["quota_tb"] * 0.999, v["used_tb"] + v["write_gbs"] * dt / 1000 * 0.01), 1)

    def summary(self) -> dict:
        used = sum(c["used_pb"] for c in self.clusters.values())
        return {
            "used_pb": round(used, 2), "total_pb": T.STORAGE_TOTAL_PB, "used_pct": round(used / T.STORAGE_TOTAL_PB * 100, 1),
            "read_gbs": round(sum(c["read_gbs"] for c in self.clusters.values()), 1),
            "write_gbs": round(sum(c["write_gbs"] for c in self.clusters.values()), 1),
            "iops_k": round(sum(c["iops_k"] for c in self.clusters.values()), 1),
            "latency_ms": self.clusters["ss-hot"]["latency_ms"],
            "clusters": {k: {**v, **{"capacity_pb": T.STORAGE_BY_ID[k]["capacity_pb"], "name": T.STORAGE_BY_ID[k]["name"]}}
                         for k, v in self.clusters.items()},
        }


# ============================================================== network
class Network:
    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.dev = {}
        for d in T.NET_DEVICES:
            self.dev[d["id"]] = {"util_pct": 0.0, "in_gbps": 0.0, "out_gbps": 0.0, "errors": int(rng.integers(0, 40)),
                                 "discards": int(rng.integers(0, 200)), "err_rate": 0.0, "links_down": 0,
                                 "temp_c": 42.0, "status": "up", "cpu_pct": 12.0,
                                 "uptime_d": int(rng.integers(40, 190))}
        self.ib_penalty = np.zeros(T.GPU_RACKS, np.float32)
        self.flows: list[dict] = []
        self.border = {"aws_dx_gbps": 0.0, "gcp_ic_gbps": 0.0, "nhn_gbps": 0.0, "internet_gbps": 0.0}

    def step(self, dt: float, node_ib: np.ndarray, node_eth: np.ndarray, storage_gbs: float, faults: set[str],
             cloud_gbps: dict) -> None:
        rng = self.rng
        node_rack = np.array(T.NODE_RACK_IDX)
        rack_ib = np.bincount(node_rack, weights=node_ib, minlength=T.GPU_RACKS)
        rack_eth = np.bincount(node_rack, weights=node_eth, minlength=T.GPU_RACKS)
        rack_nodes = np.bincount(node_rack, minlength=T.GPU_RACKS)
        self.ib_penalty[:] = 0.0

        ib_leaf_util = {}
        for leaf in T.IB_LEAVES:
            # one rail of the SU: every node puts 1/8 of its IB traffic (one 800G CX-8 port) on this leaf
            racks = [T.RACK_INDEX[r] for r in leaf["serves"]]
            frac = float(rack_ib[racks].sum() / (rack_nodes[racks].sum() * 6400.0 + 1e-9))
            util = min(98.0, frac * 100 * 1.08 * rng.uniform(0.97, 1.03))
            d = self.dev[leaf["id"]]
            flap = leaf["id"] in faults
            if flap:
                d["links_down"] = int(rng.integers(2, 7))
                d["errors"] += int(rng.integers(800, 4000))
                d["err_rate"] = round(float(rng.uniform(1e-6, 8e-6)), 9)
                util *= rng.uniform(0.35, 0.6)
                self.ib_penalty[racks] = float(rng.uniform(0.35, 0.55))
                d["status"] = "degraded"
            else:
                d["links_down"] = 0
                d["errors"] += int(rng.poisson(0.05 * dt))
                d["err_rate"] = round(float(rng.uniform(0, 4e-10)), 12)
                d["status"] = "up"
            cap = T.NODES_PER_SU * leaf["speed_g"]  # 72 uplinks × 800G
            d["util_pct"] = round(util, 1)
            d["in_gbps"] = round(util / 100 * cap * rng.uniform(0.96, 1.02), 0)
            d["out_gbps"] = round(util / 100 * cap * rng.uniform(0.96, 1.02), 0)
            d["temp_c"] = round(44 + util * 0.18 + rng.normal(0, 0.3), 1)
            ib_leaf_util[leaf["id"]] = util
        for sp in T.IB_SPINES:
            d = self.dev[sp["id"]]
            util = float(np.mean([ib_leaf_util[x] for x in T.IB_PLANE_LEAVES[sp["plane"]]])) * rng.uniform(0.9, 1.08)
            cap = sp["ports"] * sp["speed_g"]
            d.update(util_pct=round(util, 1), in_gbps=round(util / 100 * cap * 0.5, 0),
                     out_gbps=round(util / 100 * cap * 0.5, 0), temp_c=round(46 + util * 0.15, 1),
                     status="down" if sp["id"] in faults else "up")
            d["errors"] += int(rng.poisson(0.02 * dt))

        eth_leaf_util = []
        for leaf in T.ETH_LEAVES:
            d = self.dev[leaf["id"]]
            role = leaf.get("role")
            if role == "gpu-tor":
                i = T.RACK_INDEX[leaf["rack"]]
                gbps = float(rack_eth[i]) * 1.0
                cap = 8 * 400.0
            elif role == "storage":
                gbps = storage_gbs * 8 / (T.STORAGE_RACKS // T.STORAGE_RACKS_PER_LEAF) * rng.uniform(0.9, 1.1)
                cap = 16 * 400.0
            elif role == "k8s":
                gbps = float(rng.uniform(180, 420))
                cap = 32 * 800.0
            else:
                gbps = sum(cloud_gbps.values()) / 2 + float(rng.uniform(20, 60))
                cap = 16 * 800.0
            util = min(99.0, gbps / cap * 100)
            d.update(util_pct=round(util, 1), in_gbps=round(gbps * rng.uniform(0.45, 0.6), 1),
                     out_gbps=round(gbps * rng.uniform(0.4, 0.55), 1), temp_c=round(40 + util * 0.2, 1),
                     status="down" if leaf["id"] in faults else "up")
            d["errors"] += int(rng.poisson(0.03 * dt))
            d["discards"] += int(rng.poisson((0.2 + util / 30) * dt))
            eth_leaf_util.append(util)
        for sp in T.ETH_SPINES:
            d = self.dev[sp["id"]]
            util = float(np.mean(eth_leaf_util)) * 1.25 * rng.uniform(0.92, 1.08)
            d.update(util_pct=round(util, 1), in_gbps=round(util / 100 * 144 * 400 * 0.5, 0),
                     out_gbps=round(util / 100 * 144 * 400 * 0.5, 0), temp_c=round(47 + util * 0.15, 1),
                     status="down" if sp["id"] in faults else "up")
        for d in self.dev.values():
            d["cpu_pct"] = round(max(3.0, min(90.0, 8 + d["util_pct"] * 0.2 + rng.normal(0, 1))), 1)
        self.border = {"aws_dx_gbps": round(cloud_gbps.get("aws", 0.0), 1), "gcp_ic_gbps": round(cloud_gbps.get("gcp", 0.0), 1),
                       "nhn_gbps": round(cloud_gbps.get("nhn", 0.0), 1),
                       "internet_gbps": round(float(38 + 22 * rng.random()), 1)}

    def interfaces(self, dev_id: str) -> list[dict]:
        spec = T.NET_BY_ID[dev_id]
        d = self.dev[dev_id]
        rng = np.random.default_rng(zlib.crc32(dev_id.encode()))
        live = self.rng
        out = []
        ib = spec["fabric"] == "infiniband"
        n_up = (T.NODES_PER_SU if ib else 8) if spec["tier"] == "leaf" else 0
        if ib and spec["tier"] == "leaf":
            su = T.SU_BY_ID[spec["su"]]
            su_nodes = [T.NODE_IDS[n] for n in range(su["node_start"], su["node_start"] + su["node_count"])]
        for p in range(1, spec["ports"] + 1):
            if spec["tier"] == "leaf":
                if p <= n_up:
                    if ib:   # 72 uplinks spread over the 6 spines of this rail's plane, 12 each
                        peer = T.IB_PLANE_SPINES[spec["plane"]][(p - 1) // T.IB_LINKS_PER_SPINE]
                    else:
                        peer = T.ETH_SPINES[(p - 1) % len(T.ETH_SPINES)]["id"]
                    role = "uplink"
                else:
                    role = "downlink"
                    rack = spec.get("rack", "")
                    peer = (f"{su_nodes[p - n_up - 1]}/mlx5_{spec['rail'] - 1}" if ib
                            else f"{rack.lower()}-host{p - n_up:02d}")
            else:
                role = "downlink"
                if ib:       # spine: 12 links to each of the 12 same-rail leaves
                    peer = T.IB_PLANE_LEAVES[spec["plane"]][(p - 1) // T.IB_LINKS_PER_SPINE]
                else:
                    peer = T.ETH_LEAVES[(p - 1) % len(T.ETH_LEAVES)]["id"]
            name = f"Ethernet{p}/1" if not ib else f"IB1/{(p + 1) // 2}/{2 - p % 2}"
            share = float(rng.uniform(0.6, 1.3))
            unused = not ib and role == "downlink" and p > (spec["ports"] * 0.85)
            util = 0.0 if unused else min(99.0, d["util_pct"] * share * live.uniform(0.9, 1.1))
            speed = spec["speed_g"]
            down = spec["fabric"] == "infiniband" and d["links_down"] > 0 and role == "uplink" and p <= d["links_down"]
            out.append({
                "name": name, "role": role, "peer": peer, "speed_g": speed,
                "status": "down" if (down or unused) else "up",
                "util_pct": 0.0 if (down or unused) else round(util, 1),
                "in_bps": 0 if (down or unused) else int(util / 100 * speed * 1e9 * float(live.uniform(0.45, 0.55))),
                "out_bps": 0 if (down or unused) else int(util / 100 * speed * 1e9 * float(live.uniform(0.45, 0.55))),
                "errors": int(d["errors"] * share / spec["ports"]), "discards": int(d["discards"] * share / spec["ports"]),
            })
        return out

    def summary(self) -> dict:
        ib = [self.dev[d["id"]] for d in T.IB_LEAVES + T.IB_SPINES]
        eth = [self.dev[d["id"]] for d in T.ETH_LEAVES + T.ETH_SPINES]
        return {
            "ib_util_pct": round(float(np.mean([d["util_pct"] for d in ib])), 1),
            "eth_util_pct": round(float(np.mean([d["util_pct"] for d in eth])), 1),
            "ib_tbps": round(sum(d["in_gbps"] for d in ib if d is not None) / 1000, 1),
            "eth_tbps": round(sum(d["in_gbps"] + d["out_gbps"] for d in eth) / 1000, 1),
            "ib_links_down": sum(d["links_down"] for d in ib),
            "devices_down": sum(1 for d in self.dev.values() if d["status"] == "down"),
            "devices_degraded": sum(1 for d in self.dev.values() if d["status"] == "degraded"),
            "devices": len(self.dev), "border": self.border,
        }


# ============================================================== kubernetes
K8S_NAMESPACES = {
    "kube-system": (30, "system"), "cubeflow": (26, "mlops"), "inference-gw": (12, "serving"),
    "observability": (18, "platform"), "gpu-platform": (14, "platform"), "registry": (6, "platform"),
    "rcs": (22, "dev"), "slurm-bridge": (6, "scheduling"), "ingress": (6, "network"), "argocd": (7, "gitops"),
    "vector-db": (9, "serving"), "feature-store": (8, "data"),
}
POD_APPS = {
    "kube-system": ["cilium", "coredns", "kube-proxy", "node-exporter", "csi-scale"],
    "cubeflow": ["pipeline-api", "katib-controller", "notebook-controller", "training-operator", "mlflow", "minio-gw"],
    "inference-gw": ["gateway"], "observability": ["prometheus", "loki", "tempo", "grafana", "vector", "alertmanager"],
    "gpu-platform": ["platform-api", "quota-svc", "scheduler-bridge", "usage-collector", "console-web"],
    "registry": ["harbor-core", "harbor-registry", "trivy"], "rcs": ["rcs-controller", "rcs-session"],
    "slurm-bridge": ["slinky-operator", "slurmrestd"], "ingress": ["ingress-nginx"],
    "argocd": ["argocd-server", "argocd-repo", "argocd-app-ctrl"], "vector-db": ["milvus-query", "milvus-data"],
    "feature-store": ["feast-server", "redis-feature"],
}


class Kubernetes:
    def __init__(self, rng: np.random.Generator, now: float):
        self.rng = rng
        self.nodes = {n["id"]: {"status": "Ready", "cpu_pct": 0.0, "mem_pct": 0.0, "pods": 0,
                                "kubelet": "v1.34.2", "cond": []} for n in T.K8S_NODES}
        self.pods: list[dict] = []
        workers = [n["id"] for n in T.K8S_NODES if n["role"] == "worker"]
        cps = [n["id"] for n in T.K8S_NODES if n["role"] == "control-plane"]
        k = 0
        for ns, (count, tier) in K8S_NAMESPACES.items():
            apps = POD_APPS[ns]
            for i in range(count):
                app = apps[i % len(apps)]
                node = cps[i % 3] if ns == "kube-system" and i < 6 else workers[(k * 7 + i) % len(workers)]
                self.pods.append({
                    "name": f"{app}-{zlib.crc32(f'{ns}{i}'.encode()) % 0xFFFFF:05x}", "namespace": ns, "app": app, "tier": tier,
                    "node": node, "status": "Running", "restarts": int(rng.poisson(0.3)),
                    "cpu_m": float(rng.uniform(600, 14000)), "mem_mi": float(rng.uniform(2048, 160000)),
                    "age_s": float(rng.uniform(3600, 86400 * 30)), "ready": True,
                })
                k += 1
        self.rps = 0.0
        self.gw_replicas = 12
        self.events: deque = deque(maxlen=200)

    def step(self, now: float, dt: float, diurnal: float, demand: float, faults: set[str]) -> None:
        rng = self.rng
        self.rps = 42000 * diurnal * demand * rng.uniform(0.96, 1.04)
        want = int(max(6, min(48, math.ceil(self.rps / 3500))))
        gw = [p for p in self.pods if p["namespace"] == "inference-gw"]
        workers = [n["id"] for n in T.K8S_NODES if n["role"] == "worker"]
        if want > len(gw):
            for i in range(want - len(gw)):
                self.pods.append({"name": f"gateway-{int(rng.integers(0, 0xFFFFF)):05x}", "namespace": "inference-gw",
                                  "app": "gateway", "tier": "serving", "node": workers[int(rng.integers(0, len(workers)))],
                                  "status": "ContainerCreating", "restarts": 0, "cpu_m": 900.0, "mem_mi": 2048.0,
                                  "age_s": 0.0, "ready": False})
            self.events.appendleft({"t": now, "kind": "scale", "text": f"HPA inference-gw/gateway {len(gw)} → {want} (rps {self.rps:,.0f})"})
        elif want < len(gw) - 2:
            for p in gw[want:]:
                self.pods.remove(p)
            self.events.appendleft({"t": now, "kind": "scale", "text": f"HPA inference-gw/gateway {len(gw)} → {want}"})
        for p in self.pods:
            p["age_s"] += dt
            if p["status"] == "ContainerCreating" and p["age_s"] > 8:
                p["status"], p["ready"] = "Running", True
            if p["status"] == "CrashLoopBackOff" and rng.random() < 0.02 * dt:
                p["status"], p["ready"] = "Running", True
            if p["status"] == "Running" and rng.random() < 0.00002 * dt:
                p["status"], p["ready"] = "CrashLoopBackOff", False
                p["restarts"] += 1
                self.events.appendleft({"t": now, "kind": "crash", "text": f"{p['namespace']}/{p['name']} CrashLoopBackOff"})
            load = self.rps / 42000 if p["namespace"] == "inference-gw" else rng.uniform(0.85, 1.15)
            p["cpu_now"] = round(p["cpu_m"] * load * rng.uniform(0.7, 1.1), 0)
            p["mem_now"] = round(p["mem_mi"] * rng.uniform(0.85, 1.0), 0)
        for nid, n in self.nodes.items():
            mine = [p for p in self.pods if p["node"] == nid]
            spec = T.K8S_BY_ID[nid]
            cpu = sum(p.get("cpu_now", 0.0) for p in mine) / (spec["cpu_cores"] * 1000) * 100 + 6
            mem = sum(p.get("mem_now", 0.0) for p in mine) / (spec["mem_gb"] * 1024) * 100 + 8
            n["cpu_pct"] = round(min(98.0, cpu + rng.normal(0, 0.6)), 1)
            n["mem_pct"] = round(min(97.0, mem + rng.normal(0, 0.3)), 1)
            n["pods"] = len(mine)
            n["status"] = "NotReady" if nid in faults else "Ready"

    def summary(self) -> dict:
        running = sum(1 for p in self.pods if p["status"] == "Running")
        return {
            "nodes": len(self.nodes), "ready": sum(1 for n in self.nodes.values() if n["status"] == "Ready"),
            "control_plane": 3, "workers": 27, "pods": len(self.pods), "pods_running": running,
            "pods_pending": sum(1 for p in self.pods if p["status"] in ("Pending", "ContainerCreating")),
            "pods_crashloop": sum(1 for p in self.pods if p["status"] == "CrashLoopBackOff"),
            "cpu_pct": round(float(np.mean([n["cpu_pct"] for n in self.nodes.values()])), 1),
            "mem_pct": round(float(np.mean([n["mem_pct"] for n in self.nodes.values()])), 1),
            "rps": round(self.rps), "gw_replicas": sum(1 for p in self.pods if p["namespace"] == "inference-gw"),
            "namespaces": len(K8S_NAMESPACES),
        }
