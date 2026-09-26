"""Per-device interface catalogs (DCIM focus set)."""

from __future__ import annotations

import hashlib
from typing import Any

from app.sim.it.constants import ARISTA_LEAF, ARISTA_SPINE
from app.sim.network.constants import (
    BW_IB_LINK,
    BW_LEAF_HOST,
    BW_LEAF_PEER,
    BW_MGMT,
    BW_SPINE_UPLINK,
)

def _stable_seed(s: str) -> float:
    h = hashlib.md5(s.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF

def _speed_label(bps: int) -> str:
    if bps >= 1_000_000_000_000:
        return f"{bps // 1_000_000_000_000}TbE"
    if bps >= 1_000_000_000:
        g = bps // 1_000_000_000
        return f"{g}GbE" if bps % 1_000_000_000 == 0 else f"{bps / 1_000_000_000:.1f}GbE"
    if bps >= 1_000_000:
        return f"{bps // 1_000_000}MbE"
    return f"{bps}bps"

def build_device_interfaces(device: dict[str, Any]) -> list[dict[str, Any]]:
    """Representative interfaces per device (not every physical port — DCIM focus set)."""
    did = device["id"]
    role = device["role"]
    ifaces: list[dict[str, Any]] = []

    def add(
        name: str,
        *,
        if_role: str,
        description: str,
        speed_bps: int,
        peer: str | None = None,
        uplink: bool = False,
    ) -> None:
        ifaces.append(
            {
                "id": f"{did}:{name}",
                "device_id": did,
                "name": name,
                "role": if_role,
                "description": description,
                "speed_bps": speed_bps,
                "speed_label": _speed_label(speed_bps),
                "peer": peer,
                "uplink": uplink,
                "admin": "up",
                "oper": "up" if device["status"] == "online" else "down",
            }
        )

    add("Management1", if_role="mgmt", description="OOB management", speed_bps=BW_MGMT)

    if role == "spine":
        # Each spine faces a subset of leaves (full mesh demo: every spine ↔ every leaf would be huge;
        # we keep 12 leaf-facing + 2 peer for UI density).
        leaf_offset = ((_stable_seed(did) * ARISTA_LEAF) % max(1, ARISTA_LEAF - 11))
        for j in range(12):
            leaf_idx = int(leaf_offset + j) % ARISTA_LEAF + 1
            leaf_id = f"AR-LF-{leaf_idx:02d}"
            et = f"Ethernet{j + 1}/1"
            add(
                et,
                if_role="fabric",
                description=f"to {leaf_id}",
                speed_bps=BW_SPINE_UPLINK,
                peer=leaf_id,
                uplink=True,
            )
        add("Ethernet49/1", if_role="peer", description="spine peer-link", speed_bps=BW_LEAF_PEER, peer=None)
        add("Ethernet50/1", if_role="peer", description="spine peer-link", speed_bps=BW_LEAF_PEER, peer=None)

    elif role == "leaf":
        # Uplinks to all spines (or first 8)
        for j in range(1, ARISTA_SPINE + 1):
            sp_id = f"AR-SP-{j:02d}"
            add(
                f"Ethernet{48 + j}/1",
                if_role="uplink",
                description=f"uplink to {sp_id}",
                speed_bps=BW_SPINE_UPLINK,
                peer=sp_id,
                uplink=True,
            )
        # Host / storage downlinks (sample 6 — DCIM focus set)
        for j in range(1, 7):
            add(
                f"Ethernet{j}/1",
                if_role="access",
                description=f"host/storage downlink {j}",
                speed_bps=BW_LEAF_HOST,
                peer=None,
                uplink=False,
            )
        add("Ethernet33/1", if_role="peer", description="MLAG peer", speed_bps=BW_LEAF_PEER, peer=None)

    elif role == "ib-switch":
        for j in range(1, 17):
            add(
                f"IB{j}/1",
                if_role="ib-fabric",
                description=f"GPU fabric port {j}",
                speed_bps=BW_IB_LINK,
                peer=None,
                uplink=j <= 4,
            )
        add("mgmt0", if_role="mgmt", description="IB mgmt", speed_bps=BW_MGMT)

    return ifaces

def build_all_interfaces(devices: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    devices = devices or build_network_devices_rich()
    out: list[dict[str, Any]] = []
    for d in devices:
        out.extend(build_device_interfaces(d))
    return out

