"""Flat SKU inventory rows for Operations Inventory page."""

from __future__ import annotations

from typing import Any

from app.sim.it.constants import (
    ARISTA_LEAF,
    ARISTA_MODEL_LEAF,
    ARISTA_MODEL_SPINE,
    ARISTA_SPINE,
    DELL_K8S_NODES,
    DELL_MODEL,
    GPU_COUNT,
    GPU_MODEL,
    GPU_NODE_COUNT,
    GPU_RACK_COUNT,
    NVIDIA_IB_MODEL,
    NVIDIA_IB_SWITCHES,
    STORAGE_CAPACITY_PB,
    STORAGE_CLUSTER_COUNT,
    STORAGE_VENDOR,
)
from app.sim.it.summary import build_inventory_summary

def build_asset_rows() -> list[dict[str, Any]]:
    """Flat inventory rows for Inventory page (aggregated + key SKUs)."""
    s = build_inventory_summary()
    return [
        {
            "sku": GPU_MODEL,
            "category": "GPU",
            "vendor": "NVIDIA",
            "qty": GPU_COUNT,
            "unit": "GPU",
            "location": f"{GPU_RACK_COUNT} racks / {GPU_NODE_COUNT} nodes",
            "status": "online",
        },
        {
            "sku": "HGX B300 Node",
            "category": "Compute",
            "vendor": "NVIDIA OEM",
            "qty": GPU_NODE_COUNT,
            "unit": "server",
            "location": "GPU halls M1–M5",
            "status": "mixed",
        },
        {
            "sku": f"{STORAGE_VENDOR} Parallel Storage",
            "category": "Storage",
            "vendor": STORAGE_VENDOR,
            "qty": STORAGE_CAPACITY_PB,
            "unit": "PB",
            "location": f"{STORAGE_CLUSTER_COUNT} clusters",
            "status": "online",
        },
        {
            "sku": ARISTA_MODEL_SPINE,
            "category": "Network",
            "vendor": "Arista",
            "qty": ARISTA_SPINE,
            "unit": "switch",
            "location": "Spine fabric",
            "status": "online",
        },
        {
            "sku": ARISTA_MODEL_LEAF,
            "category": "Network",
            "vendor": "Arista",
            "qty": ARISTA_LEAF,
            "unit": "switch",
            "location": "Leaf fabric",
            "status": "online",
        },
        {
            "sku": NVIDIA_IB_MODEL,
            "category": "Network",
            "vendor": "NVIDIA",
            "qty": NVIDIA_IB_SWITCHES,
            "unit": "switch",
            "location": "IB compute fabric",
            "status": "online",
        },
        {
            "sku": DELL_MODEL,
            "category": "Kubernetes",
            "vendor": "Dell",
            "qty": DELL_K8S_NODES,
            "unit": "server",
            "location": "K8s racks",
            "status": "Ready",
        },
        {
            "sku": "Facility CDU / UPS / PDU",
            "category": "Facility",
            "vendor": "Multi",
            "qty": 1,
            "unit": "campus",
            "location": "See Facility menus",
            "status": "online",
        },
    ]

