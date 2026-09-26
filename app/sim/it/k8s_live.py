"""Kubernetes node/pod live metrics (Dell cluster)."""

from __future__ import annotations

import math
import random
from typing import Any

from app.sim.it.constants import DELL_K8S_NODES, DELL_MODEL, K8S_CONTROL_PLANE
from app.sim.telemetry import stable_seed


def build_k8s_nodes_rich() -> list[dict[str, Any]]:
    nodes = []
    for i in range(1, DELL_K8S_NODES + 1):
        role = "control-plane" if i <= K8S_CONTROL_PLANE else "worker"
        nodes.append(
            {
                "id": f"K8S-{i:02d}",
                "hostname": f"dell-k8s-{i:02d}",
                "vendor": "Dell",
                "model": DELL_MODEL,
                "role": role,
                "cpu_cores": 128 if role == "worker" else 64,
                "cpu_sockets": 2,
                "ram_tb": 2.0 if role == "worker" else 1.0,
                "rack_id": f"R-K8S-{(i - 1) // 8 + 1:02d}",
                "ru": 1 + ((i - 1) % 8) * 5,
                "status": "Ready",
                "k8s_version": "1.31.2",
                "mgmt_ip": f"10.80.1.{i}",
            }
        )
    return nodes


def sample_node_metrics(node: dict[str, Any], *, tick: int, mode: str = "normal") -> dict[str, Any]:
    seed = stable_seed(node["id"])
    worker = node["role"] == "worker"
    base_cpu = (42 + seed * 40) if worker else (18 + seed * 20)
    wave = 0.6 + 0.4 * math.sin(tick / 14.0 + seed * 5)
    factor = 1.25 if mode == "stress" else (0.7 if mode == "maintenance" else 1.0)
    cpu = round(min(96.0, base_cpu * wave * factor + random.uniform(-2, 2)), 1)
    mem = round(min(94.0, (base_cpu * 0.85) * wave * factor + random.uniform(-2, 2)), 1)
    pods = int((28 + seed * 40) * wave * (1.1 if worker else 0.45))
    net_mbs = round((80 + seed * 400) * wave * factor, 1)
    disk_iops = int((2000 + seed * 12000) * wave)
    return {
        "node_id": node["id"],
        "hostname": node["hostname"],
        "role": node["role"],
        "cpu_util_pct": cpu,
        "mem_util_pct": mem,
        "pod_count": pods,
        "net_mbs": net_mbs,
        "disk_iops": disk_iops,
        "status": node["status"],
        "score": round(cpu * 0.5 + mem * 0.3 + min(pods, 80) * 0.2, 1),
    }


def build_node_pods(node: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    n = min(12, max(3, metrics.get("pod_count", 8) // 4))
    namespaces = ["gpu-ops", "ml-serving", "kube-system", "monitoring", "data"]
    pods = []
    for i in range(1, n + 1):
        seed = stable_seed(f"{node['id']}-p{i}")
        pods.append(
            {
                "name": f"{namespaces[i % len(namespaces)]}/ws-{node['id'].lower()}-{i:02d}",
                "namespace": namespaces[i % len(namespaces)],
                "cpu_m": int(200 + seed * 3500),
                "mem_mi": int(512 + seed * 14000),
                "restarts": int(seed * 4),
                "status": "Running" if seed > 0.08 else "Pending",
            }
        )
    return pods


def rank_k8s_talkers(samples: list[dict[str, Any]], *, limit: int = 15) -> list[dict[str, Any]]:
    ranked = sorted(samples, key=lambda s: s.get("score", 0), reverse=True)
    out = []
    for i, s in enumerate(ranked[:limit], start=1):
        row = dict(s)
        row["rank"] = i
        out.append(row)
    return out
