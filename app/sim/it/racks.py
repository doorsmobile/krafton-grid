"""Unified Facility+IT rack map tiles."""

from __future__ import annotations

from typing import Any

from app.sim.it.constants import (
    DELL_MODEL,
    GPU_NODES_PER_RACK,
    GPU_RACK_COUNT,
    GPUS_PER_NODE,
    STORAGE_RACK_COUNT,
)

def build_rack_map() -> list[dict[str, Any]]:
    """Representative rack map for Facility+IT unified rack view."""
    racks: list[dict[str, Any]] = []
    # GPU racks (show first 24 for UI density; meta carries full count)
    for i in range(1, min(GPU_RACK_COUNT, 24) + 1):
        racks.append(
            {
                "id": f"R-GPU-{i:02d}",
                "row": f"A{(i - 1) // 8 + 1}",
                "type": "gpu",
                "label": "B300 HGX",
                "kw": 96,
                "u_used": 42,
                "status": "online" if i <= 18 else "commissioning",
                "assets": f"{GPU_NODES_PER_RACK}× HGX / {GPU_NODES_PER_RACK * GPUS_PER_NODE}× B300",
            }
        )
    for i in range(1, STORAGE_RACK_COUNT // 2 + 1):  # sample half for view
        racks.append(
            {
                "id": f"R-ST-{i:02d}",
                "row": f"S{(i - 1) // 6 + 1}",
                "type": "storage",
                "label": "IBM Storage",
                "kw": 28,
                "u_used": 40,
                "status": "online" if i <= 8 else "planned",
                "assets": "IBM Storage Scale / ESS NVMe-oF",
            }
        )
    for i in range(1, 7):
        racks.append(
            {
                "id": f"R-NET-{i:02d}",
                "row": "N1",
                "type": "network",
                "label": "Arista+IB",
                "kw": 12,
                "u_used": 36,
                "status": "online",
                "assets": "Spine/Leaf + Quantum IB",
            }
        )
    for i in range(1, 5):
        racks.append(
            {
                "id": f"R-K8S-{i:02d}",
                "row": "K1",
                "type": "kubernetes",
                "label": "Dell K8s",
                "kw": 18,
                "u_used": 30,
                "status": "online",
                "assets": f"Dell {DELL_MODEL}",
            }
        )
    return racks

