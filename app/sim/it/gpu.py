"""GPU pod aggregates."""

from __future__ import annotations

from typing import Any

from app.sim.it.constants import GPU_COUNT, GPU_MODEL, GPU_NODES_PER_RACK, GPUS_PER_NODE

def build_gpu_pods() -> list[dict[str, Any]]:
    """Aggregate 5000 GPUs into pods for UI (not per-GPU rows)."""
    pods = []
    remaining = GPU_COUNT
    # 5 pods aligned to modular story; M1 holds first share online
    shares = [1200, 1000, 1000, 1000, 800]  # sum 5000
    statuses = ["online", "online", "commissioning", "planned", "planned"]
    for i, (share, st) in enumerate(zip(shares, statuses), start=1):
        nodes = share // GPUS_PER_NODE
        racks = max(1, (nodes + GPU_NODES_PER_RACK - 1) // GPU_NODES_PER_RACK)
        pods.append(
            {
                "id": f"POD-{i}",
                "name": f"GPU Pod {i}",
                "module_id": f"M{i}",
                "gpu_model": GPU_MODEL,
                "gpu_count": share,
                "nodes": nodes,
                "racks": racks,
                "status": st,
                "power_kw_design": round(share * 1.2, 1),  # ~1.2 kW/GPU class envelope
            }
        )
        remaining -= share
    return pods

