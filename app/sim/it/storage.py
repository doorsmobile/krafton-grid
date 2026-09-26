"""IBM Storage cluster catalog."""

from __future__ import annotations

from typing import Any

from app.sim.it.constants import STORAGE_CAPACITY_PB, STORAGE_CLUSTER_COUNT, STORAGE_RACK_COUNT, STORAGE_VENDOR

def build_storage_clusters() -> list[dict[str, Any]]:
    per = STORAGE_CAPACITY_PB / STORAGE_CLUSTER_COUNT
    out = []
    for i in range(1, STORAGE_CLUSTER_COUNT + 1):
        out.append(
            {
                "id": f"ST-{i:02d}",
                "name": f"IBM Storage Cluster {i}",
                "vendor": STORAGE_VENDOR,
                "capacity_pb": round(per, 2),
                "racks": STORAGE_RACK_COUNT // STORAGE_CLUSTER_COUNT,
                "status": "online" if i <= 5 else ("commissioning" if i == 6 else "planned"),
                "protocol": "NVMe-oF",
            }
        )
    return out

