"""IBM Storage fabric — clusters, volumes, IOPS / latency telemetry."""

from __future__ import annotations

import math
import random
from typing import Any

from app.sim.it.constants import (
    STORAGE_CAPACITY_PB,
    STORAGE_CLUSTER_COUNT,
    STORAGE_RACK_COUNT,
    STORAGE_VENDOR,
)
from app.sim.telemetry import stable_seed


def build_storage_clusters_rich() -> list[dict[str, Any]]:
    per = STORAGE_CAPACITY_PB / STORAGE_CLUSTER_COUNT
    out = []
    for i in range(1, STORAGE_CLUSTER_COUNT + 1):
        status = "online" if i <= 5 else ("commissioning" if i == 6 else "planned")
        out.append(
            {
                "id": f"ST-{i:02d}",
                "name": f"IBM Storage Cluster {i}",
                "vendor": STORAGE_VENDOR,
                "model": "IBM Storage Scale / ESS",
                "capacity_pb": round(per, 2),
                "racks": STORAGE_RACK_COUNT // STORAGE_CLUSTER_COUNT,
                "status": status,
                "protocol": "NVMe-oF",
                "controllers": 2 if status == "online" else 1,
                "mgmt_ip": f"10.70.1.{i}",
                "location": f"Storage row S{(i - 1) // 3 + 1}",
            }
        )
    return out


def build_storage_volumes(clusters: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    clusters = clusters or build_storage_clusters_rich()
    vols: list[dict[str, Any]] = []
    roles = ["gpu-scratch", "checkpoint", "dataset", "home", "object-gw", "metadata"]
    for c in clusters:
        n = 6 if c["status"] == "online" else (3 if c["status"] == "commissioning" else 0)
        cap = c["capacity_pb"] / max(n, 1)
        for j in range(1, n + 1):
            vols.append(
                {
                    "id": f"{c['id']}-VOL-{j:02d}",
                    "cluster_id": c["id"],
                    "name": f"{c['id'].lower()}-{roles[j - 1]}",
                    "role": roles[j - 1],
                    "capacity_pb": round(cap, 3),
                    "protocol": c["protocol"],
                    "status": c["status"],
                }
            )
    return vols


def sample_volume_metrics(vol: dict[str, Any], *, tick_minute: int, mode: str = "normal") -> dict[str, Any]:
    seed = stable_seed(vol["id"])
    online = vol.get("status") == "online"
    base_iops = 180_000 + seed * 420_000
    wave = 0.55 + 0.45 * math.sin(tick_minute / 6.0 + seed * 8)
    burst = 0.8 + 0.35 * math.sin(tick_minute / 2.5 + seed * 3)
    factor = 1.0
    if mode == "stress":
        factor = 1.35
    elif mode == "maintenance":
        factor = 0.55
    iops = int(base_iops * wave * burst * factor) if online else 0
    read_share = 0.55 + 0.2 * seed
    read_iops = int(iops * read_share)
    write_iops = iops - read_iops
    # ~32KB avg → throughput bytes/s
    thr_mbs = round(iops * 32 / 1024, 1) if online else 0.0
    lat_r = round(0.18 + (1.0 - wave) * 0.9 + random.uniform(0, 0.08), 3) if online else 0.0
    lat_w = round(0.28 + (1.0 - wave) * 1.2 + random.uniform(0, 0.1), 3) if online else 0.0
    if mode == "stress":
        lat_r *= 1.4
        lat_w *= 1.5
    used_pct = round(min(92.0, 28 + seed * 50 + 8 * math.sin(tick_minute / 40.0)), 1) if online else 0.0
    queue = round(max(0.2, iops / 85000 + random.uniform(-0.3, 0.5)), 2) if online else 0.0
    errors = int(max(0, round((lat_w - 1.2) * 4 + random.uniform(0, 0.4)))) if online and lat_w > 1.2 else 0
    return {
        "ts": None,  # filled by collector
        "volume_id": vol["id"],
        "cluster_id": vol["cluster_id"],
        "name": vol["name"],
        "role": vol["role"],
        "iops": iops,
        "read_iops": read_iops,
        "write_iops": write_iops,
        "throughput_mbs": thr_mbs,
        "latency_read_ms": round(lat_r, 3),
        "latency_write_ms": round(lat_w, 3),
        "used_pct": used_pct,
        "queue_depth": queue,
        "errors": errors,
        "capacity_pb": vol["capacity_pb"],
        "status": vol["status"],
    }


def rank_storage_talkers(samples: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    ranked = sorted(samples, key=lambda s: s.get("iops", 0), reverse=True)
    out = []
    for i, s in enumerate(ranked[:limit], start=1):
        row = dict(s)
        row["rank"] = i
        out.append(row)
    return out


def format_iops(v: int | float) -> str:
    v = float(v)
    if v >= 1_000_000:
        return f"{v / 1_000_000:.2f} M"
    if v >= 1_000:
        return f"{v / 1_000:.1f} K"
    return f"{v:.0f}"
