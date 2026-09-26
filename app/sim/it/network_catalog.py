"""Basic network device catalog (legacy flat list — rich model in app.sim.network)."""

from __future__ import annotations

from typing import Any

from app.sim.it.constants import (
    ARISTA_LEAF,
    ARISTA_MODEL_LEAF,
    ARISTA_MODEL_SPINE,
    ARISTA_SPINE,
    NVIDIA_IB_MODEL,
    NVIDIA_IB_SWITCHES,
)

def build_network_devices() -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for i in range(1, ARISTA_SPINE + 1):
        devices.append(
            {
                "id": f"AR-SP-{i:02d}",
                "role": "spine",
                "vendor": "Arista",
                "model": ARISTA_MODEL_SPINE,
                "ports": 576,
                "status": "online",
                "fabric": "ethernet",
            }
        )
    for i in range(1, ARISTA_LEAF + 1):
        devices.append(
            {
                "id": f"AR-LF-{i:02d}",
                "role": "leaf",
                "vendor": "Arista",
                "model": ARISTA_MODEL_LEAF,
                "ports": 64,
                "status": "online" if i <= 36 else "commissioning",
                "fabric": "ethernet",
            }
        )
    for i in range(1, NVIDIA_IB_SWITCHES + 1):
        devices.append(
            {
                "id": f"IB-Q-{i:02d}",
                "role": "ib-switch",
                "vendor": "NVIDIA",
                "model": NVIDIA_IB_MODEL,
                "ports": 64,
                "status": "online" if i <= 12 else "commissioning",
                "fabric": "infiniband",
            }
        )
    return devices

