"""GPU partitioning / aggregation catalogs."""

from __future__ import annotations

import random
from typing import Any

def build_gpu_slices() -> list[dict[str, Any]]:
    """Physical GPUs sliced into fractions (MIG-style / soft partition)."""
    slices: list[dict[str, Any]] = []
    # Sample from B300 fleet — 16 physical GPUs with mixed slice profiles
    profiles = [
        [("full", 96)],
        [("1/2", 48), ("1/2", 48)],
        [("1/4", 24), ("1/4", 24), ("1/2", 48)],
        [("1/8", 12), ("1/8", 12), ("1/4", 24), ("1/2", 48)],
        [("1/4", 24), ("1/4", 24), ("1/4", 24), ("1/4", 24)],
    ]
    for i in range(1, 17):
        prof = profiles[i % len(profiles)]
        for j, (frac, mem) in enumerate(prof, 1):
            slices.append(
                {
                    "id": f"SLICE-{i:02d}-{j}",
                    "physical_gpu": f"GPU-{i:02d}",
                    "node": f"hgx-b300-{(i - 1) // 8 + 1:03d}",
                    "vendor": "NVIDIA" if i % 7 else "AMD",
                    "model": "B300" if i % 7 else "MI300X",
                    "fraction": frac,
                    "vram_gb": mem,
                    "mig_profile": f"mig-{frac}" if frac != "full" else "none",
                    "status": "allocated" if (i + j) % 3 else "idle",
                    "project": f"PRJ-{(i % 5) + 1:02d}" if (i + j) % 3 else None,
                    "util_pct": round(random.uniform(40, 96), 1) if (i + j) % 3 else round(random.uniform(0, 8), 1),
                }
            )
    return slices

def build_gpu_aggregations() -> list[dict[str, Any]]:
    return [
        {
            "id": "AGG-01",
            "name": "elastic-train-256g",
            "gpus": ["GPU-01", "GPU-02"],
            "vram_gb": 256,
            "mode": "elastic-training",
            "nodes": ["hgx-b300-001"],
            "status": "running",
            "job": "JOB-20441",
        },
        {
            "id": "AGG-02",
            "name": "multi-node-512g",
            "gpus": ["GPU-05", "GPU-06", "GPU-07", "GPU-08"],
            "vram_gb": 512,
            "mode": "multi-node",
            "nodes": ["hgx-b300-001", "hgx-b300-002"],
            "status": "running",
            "job": "JOB-20512",
        },
        {
            "id": "AGG-03",
            "name": "infer-pool-96g",
            "gpus": ["GPU-12"],
            "vram_gb": 96,
            "mode": "single",
            "nodes": ["hgx-b300-002"],
            "status": "idle",
            "job": None,
        },
    ]


# ---- Projects / Users / Quota / RBAC ----

