"""GPU fleet live ranking helpers (pods + Slurm/CubeFlow nodes)."""

from __future__ import annotations

import math
import random
from typing import Any

from app.sim.it.gpu import build_gpu_pods
from app.sim.telemetry import stable_seed


def sample_pod_metrics(pod: dict[str, Any], *, tick: int, mode: str = "normal") -> dict[str, Any]:
    seed = stable_seed(pod["id"])
    online = pod.get("status") == "online"
    base = 55 + seed * 35 if online else (10 + seed * 15 if pod.get("status") == "commissioning" else 0)
    wave = 0.55 + 0.45 * math.sin(tick / 16.0 + seed * 4)
    factor = 1.2 if mode == "stress" else (0.65 if mode == "maintenance" else 1.0)
    util = round(min(97.0, base * wave * factor + random.uniform(-2, 2)), 1) if base else 0.0
    active = int(pod["gpu_count"] * (util / 100.0) * (0.85 + 0.1 * seed)) if online else 0
    power = round(pod["gpu_count"] * 1.05 * (util / 100.0) * factor, 1)
    temp = round(36 + util * 0.32 + random.uniform(-1, 1), 1) if online else 28.0
    return {
        "pod_id": pod["id"],
        "name": pod["name"],
        "module_id": pod["module_id"],
        "gpu_count": pod["gpu_count"],
        "gpu_util_pct": util,
        "gpu_active": active,
        "power_kw": power,
        "temp_c": temp,
        "status": pod["status"],
        "score": util,
    }


def enrich_slurm_nodes(nodes: list[dict[str, Any]], *, tick: int, mode: str = "normal") -> list[dict[str, Any]]:
    """Re-jitter CubeFlow metrics each request for live feel + ranking."""
    out = []
    for n in nodes:
        seed = stable_seed(n["id"] + str(tick // 5))
        st = n["slurm_state"]
        base = n["cubeflow"]["gpu_util_pct"]
        wave = 0.9 + 0.1 * math.sin(tick / 11.0 + seed * 3)
        factor = 1.15 if mode == "stress" else 1.0
        util = round(min(98.0, base * wave * factor), 1)
        mem = round(min(97.0, n["cubeflow"]["gpu_mem_pct"] * wave), 1)
        row = {
            **n,
            "cubeflow": {
                **n["cubeflow"],
                "gpu_util_pct": util,
                "gpu_mem_pct": mem,
                "power_w": int(4200 + util * 35),
                "temp_c": round(38 + util * 0.28, 1),
            },
            "score": util,
        }
        out.append(row)
    return out


def rank_gpu_talkers(nodes: list[dict[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    ranked = sorted(nodes, key=lambda n: n.get("score", 0), reverse=True)
    out = []
    for i, n in enumerate(ranked[:limit], start=1):
        row = {
            "rank": i,
            "id": n["id"],
            "hostname": n["hostname"],
            "rack": n["rack"],
            "slurm_state": n["slurm_state"],
            "partition": n["partition"],
            "gpu_util_pct": n["cubeflow"]["gpu_util_pct"],
            "gpu_mem_pct": n["cubeflow"]["gpu_mem_pct"],
            "power_w": n["cubeflow"]["power_w"],
            "temp_c": n["cubeflow"]["temp_c"],
            "job": n.get("slurm_job") or "—",
            "user": n.get("user") or "—",
        }
        out.append(row)
    return out


def build_pod_nodes(pod: dict[str, Any], slurm_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach a sample of fleet nodes to a pod for detail view."""
    # Map pod index to node slice
    idx = int(pod["id"].split("-")[-1])
    start = (idx - 1) * 4
    return slurm_nodes[start : start + 6] or slurm_nodes[:6]
