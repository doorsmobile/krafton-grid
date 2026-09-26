"""Arista + NVIDIA IB rich device inventory."""

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

def build_network_devices_rich() -> list[dict[str, Any]]:
    """Inventory-grade device list with rack / management IP / EOS version."""
    devices: list[dict[str, Any]] = []
    for i in range(1, ARISTA_SPINE + 1):
        devices.append(
            {
                "id": f"AR-SP-{i:02d}",
                "hostname": f"kg-sp-{i:02d}.net.krafton.local",
                "role": "spine",
                "vendor": "Arista",
                "model": ARISTA_MODEL_SPINE,
                "os": "EOS 4.32.2F",
                "ports": 576,
                "status": "online",
                "fabric": "ethernet",
                "rack_id": f"R-NET-SP-{(i - 1) // 4 + 1:02d}",
                "mgmt_ip": f"10.64.1.{i}",
                "serial": f"JPE{7800 + i:04d}A{i:02d}",
                "location": "Spine Network Room",
            }
        )
    for i in range(1, ARISTA_LEAF + 1):
        hall = (i - 1) // 10 + 1
        devices.append(
            {
                "id": f"AR-LF-{i:02d}",
                "hostname": f"kg-lf-{i:02d}.net.krafton.local",
                "role": "leaf",
                "vendor": "Arista",
                "model": ARISTA_MODEL_LEAF,
                "os": "EOS 4.32.2F",
                "ports": 64,
                "status": "online" if i <= 36 else "commissioning",
                "fabric": "ethernet",
                "rack_id": f"R-NET-LF-{(i - 1) // 8 + 1:02d}",
                "mgmt_ip": f"10.64.2.{i}",
                "serial": f"JPE{7060 + i:04d}B{i:02d}",
                "location": f"Hall M{min(hall, 5)} ToR",
            }
        )
    for i in range(1, NVIDIA_IB_SWITCHES + 1):
        devices.append(
            {
                "id": f"IB-Q-{i:02d}",
                "hostname": f"kg-ib-{i:02d}.ib.krafton.local",
                "role": "ib-switch",
                "vendor": "NVIDIA",
                "model": NVIDIA_IB_MODEL,
                "os": "MLNX-OS 3.11",
                "ports": 64,
                "status": "online" if i <= 12 else "commissioning",
                "fabric": "infiniband",
                "rack_id": f"R-NET-IB-{(i - 1) // 4 + 1:02d}",
                "mgmt_ip": f"10.65.1.{i}",
                "serial": f"MTQ{9700 + i:04d}",
                "location": "IB compute fabric",
            }
        )
    return devices

