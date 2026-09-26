"""Cloud live ranking helpers — instances / buckets as talkers."""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any

from app.sim.telemetry import stable_seed


def enrich_aws_instances(instances: list[dict[str, Any]], *, tick: int = 0) -> list[dict[str, Any]]:
    out = []
    for inst in instances:
        seed = stable_seed(inst["id"] + str(tick // 5))
        base = float(inst.get("util_pct") or 40)
        wave = 0.9 + 0.1 * math.sin(tick / 13.0 + seed * 4)
        util = round(min(98.0, base * wave), 1) if inst.get("state") == "running" else round(base * 0.2, 1)
        row = {
            **inst,
            "util_pct": util,
            "power_kw": round(inst["gpus"] * 1.05 * (util / 100.0), 2),
            "score": util,
        }
        out.append(row)
    return out


def enrich_nhn_instances(instances: list[dict[str, Any]], *, tick: int = 0) -> list[dict[str, Any]]:
    out = []
    for inst in instances:
        seed = stable_seed(inst["id"] + str(tick // 5))
        base = float(inst.get("util_pct") or 40)
        wave = 0.9 + 0.1 * math.sin(tick / 12.0 + seed * 3)
        active = inst.get("status") == "ACTIVE"
        util = round(min(97.0, base * wave), 1) if active else round(base * 0.15, 1)
        row = {
            **inst,
            "util_pct": util,
            "power_kw": round(inst["gpus"] * 1.0 * (util / 100.0), 2),
            "score": util,
        }
        out.append(row)
    return out


def enrich_gcp_buckets(buckets: list[dict[str, Any]], *, tick: int = 0) -> list[dict[str, Any]]:
    out = []
    for b in buckets:
        seed = stable_seed(b["id"] + str(tick // 7))
        ops = int(800 + seed * 12000 + 2000 * math.sin(tick / 9.0 + seed))
        thr = round(ops * (0.02 + seed * 0.08), 1)
        row = {
            **b,
            "ops_per_s": ops,
            "throughput_mbs": thr,
            "score": ops,
        }
        out.append(row)
    return out


def enrich_gcp_disks(disks: list[dict[str, Any]], *, tick: int = 0) -> list[dict[str, Any]]:
    out = []
    for d in disks:
        seed = stable_seed(d["id"])
        iops = int(12000 + seed * 80000 + 5000 * math.sin(tick / 10.0))
        lat = round(0.4 + (1 - seed) * 1.8, 2)
        row = {
            **d,
            "iops": iops,
            "latency_ms": lat,
            "util_pct": round(35 + seed * 45, 1),
            "score": iops,
        }
        out.append(row)
    return out


def sample_cloud_series(entity_id: str, *, base: float, tick: int, n: int = 60) -> list[dict[str, Any]]:
    now = int(time.time())
    seed = stable_seed(entity_id)
    pts = []
    for age in range(n - 1, -1, -1):
        wave = 0.88 + 0.12 * math.sin((tick - age) / 10.0 + seed * 5)
        pts.append({
            "t": datetime.fromtimestamp(now - age * 60, tz=timezone.utc).isoformat(),
            "v": round(max(0.0, base * wave), 2),
        })
    return pts


def rank_cloud(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda r: r.get("score", 0), reverse=True)
    out = []
    for i, r in enumerate(ranked[:limit], start=1):
        row = dict(r)
        row["rank"] = i
        out.append(row)
    return out
