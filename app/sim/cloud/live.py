"""Live cloud + cost metric jitter for sim ticks."""

from __future__ import annotations

import math
import random
from typing import Any

from app.sim.cloud.cost import build_cloud_cost_baseline, build_dc_cost_baseline


def live_cost_snapshot(tick: int, mode: str = "normal") -> dict[str, Any]:
    """Slight monthly burn jitter for live Cost tiles."""
    factor = 1.0 + 0.02 * math.sin(tick / 30.0) + (0.03 if mode == "stress" else 0)
    dc = build_dc_cost_baseline()
    cloud = build_cloud_cost_baseline()
    dc_live = {ln["id"]: int(ln["amount"] * factor * (1 + random.uniform(-0.01, 0.01))) for ln in dc["lines"]}
    cloud_live = {ln["id"]: int(ln["amount"] * factor * (1 + random.uniform(-0.015, 0.015))) for ln in cloud["lines"]}
    return {
        "dc": {
            **dc,
            "live": dc_live,
            "live_total": sum(dc_live.values()),
        },
        "cloud": {
            **cloud,
            "live": cloud_live,
            "live_total": sum(cloud_live.values()),
        },
        "grand_total": sum(dc_live.values()) + sum(cloud_live.values()),
    }

def live_cloud_metrics(tick: int) -> dict[str, Any]:
    return {
        "nhn_gpu_util_pct": round(min(96.0, 58 + 12 * math.sin(tick / 17.0) + random.uniform(-3, 3)), 1),
        "nhn_active_instances": 10,
        "aws_gpu_util_pct": round(min(95.0, 52 + 14 * math.sin(tick / 19.0) + random.uniform(-3, 3)), 1),
        "aws_running_instances": 8,
        "gcp_storage_used_tb": round(8065 + 40 * math.sin(tick / 40.0) + random.uniform(-8, 8), 1),
        "gcp_ops_per_s": int(12000 + 2000 * math.sin(tick / 11.0) + random.uniform(-400, 400)),
        "slurm_jobs_running": 3,
        "slurm_jobs_pending": 2,
        "cubeflow_avg_gpu_util_pct": round(min(97.0, 72 + 10 * math.sin(tick / 15.0) + random.uniform(-4, 4)), 1),
    }

