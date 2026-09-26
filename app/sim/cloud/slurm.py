"""Slurm + CubeFlow on-prem GPU node monitoring demo data."""

from __future__ import annotations

import random
from typing import Any

def build_slurm_cubeflow_nodes(sample: int = 24) -> list[dict[str, Any]]:
    """Representative HGX B300 nodes with Slurm state + CubeFlow resource metrics."""
    states = ["ALLOCATED", "ALLOCATED", "ALLOCATED", "IDLE", "MIXED", "DRAINED"]
    partitions = ["gpu-train", "gpu-infer", "gpu-batch", "debug"]
    nodes: list[dict[str, Any]] = []
    for i in range(1, sample + 1):
        st = states[i % len(states)]
        util = round(random.uniform(55, 98), 1) if st.startswith("ALLOC") or st == "MIXED" else round(random.uniform(0, 12), 1)
        mem = round(random.uniform(40, 96), 1) if util > 20 else round(random.uniform(2, 18), 1)
        nodes.append(
            {
                "id": f"gpu-{i:03d}",
                "hostname": f"hgx-b300-{i:03d}",
                "rack": f"R-GPU-{(i - 1) // 16 + 1:02d}",
                "slurm_state": st,
                "partition": partitions[i % len(partitions)],
                "gpus_alloc": 8 if st == "ALLOCATED" else (4 if st == "MIXED" else 0),
                "gpus_total": 8,
                "cubeflow": {
                    "gpu_util_pct": util,
                    "gpu_mem_pct": mem,
                    "sm_clock_mhz": int(1200 + util * 6),
                    "power_w": int(4200 + util * 35),
                    "temp_c": round(38 + util * 0.28, 1),
                    "job_id": f"CF-{18000 + i}" if util > 20 else None,
                },
                "slurm_job": f"{920000 + i}" if util > 20 else None,
                "user": f"team-{(i % 6) + 1}" if util > 20 else "—",
            }
        )
    return nodes

def build_slurm_queue() -> list[dict[str, Any]]:
    return [
        {"job_id": "920441", "name": "llm-sft-70b", "user": "team-1", "partition": "gpu-train", "gpus": 64, "state": "R", "time": "1-04:12"},
        {"job_id": "920512", "name": "rlhf-rollout", "user": "team-3", "partition": "gpu-train", "gpus": 32, "state": "R", "time": "0-11:40"},
        {"job_id": "920601", "name": "infer-batch", "user": "team-2", "partition": "gpu-infer", "gpus": 16, "state": "R", "time": "0-03:05"},
        {"job_id": "920710", "name": "pretrain-ckpt", "user": "team-1", "partition": "gpu-train", "gpus": 128, "state": "PD", "time": "0:00"},
        {"job_id": "920755", "name": "eval-suite", "user": "team-5", "partition": "gpu-batch", "gpus": 8, "state": "PD", "time": "0:00"},
    ]


# ---- Cloud: AWS GPUaaS / GCP Storage / NHN GPUaaS ----

