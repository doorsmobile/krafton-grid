"""Leaf–spine + IB topology graph for SVG map."""

from __future__ import annotations

from typing import Any

from app.sim.it.constants import ARISTA_LEAF, ARISTA_SPINE, NVIDIA_IB_SWITCHES
from app.sim.network.devices import build_network_devices_rich

def build_topology(devices: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Leaf–spine + IB nodes and fabric links for topology view."""
    devices = devices or build_network_devices_rich()
    nodes = []
    for d in devices:
        tier = {"spine": 0, "leaf": 1, "ib-switch": 2}.get(d["role"], 3)
        nodes.append(
            {
                "id": d["id"],
                "label": d["id"],
                "role": d["role"],
                "vendor": d["vendor"],
                "model": d["model"],
                "status": d["status"],
                "fabric": d["fabric"],
                "tier": tier,
            }
        )

    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    # Full mesh demo between spines and first 24 leaves (readable topology)
    for i in range(1, ARISTA_SPINE + 1):
        sp = f"AR-SP-{i:02d}"
        for j in range(1, min(ARISTA_LEAF, 24) + 1):
            lf = f"AR-LF-{j:02d}"
            a, b = sorted((sp, lf))
            key = (a, b)
            if key in seen:
                continue
            seen.add(key)
            links.append(
                {
                    "id": f"{a}-{b}",
                    "source": sp,
                    "target": lf,
                    "kind": "ethernet-fabric",
                    "speed_label": "400GbE",
                    "uplink": True,
                }
            )
    # Spine peers
    for i in range(1, ARISTA_SPINE, 2):
        a, b = f"AR-SP-{i:02d}", f"AR-SP-{i + 1:02d}"
        links.append(
            {
                "id": f"{a}-{b}",
                "source": a,
                "target": b,
                "kind": "spine-peer",
                "speed_label": "400GbE",
                "uplink": False,
            }
        )
    # IB chain for visual fabric
    for i in range(1, min(NVIDIA_IB_SWITCHES, 12)):
        a, b = f"IB-Q-{i:02d}", f"IB-Q-{i + 1:02d}"
        links.append(
            {
                "id": f"{a}-{b}",
                "source": a,
                "target": b,
                "kind": "ib-fabric",
                "speed_label": "NDR",
                "uplink": False,
            }
        )

    return {
        "nodes": nodes,
        "links": links,
        "summary": {
            "spines": ARISTA_SPINE,
            "leaves": ARISTA_LEAF,
            "ib_switches": NVIDIA_IB_SWITCHES,
            "eth_links": sum(1 for L in links if L["kind"].startswith("ethernet") or L["kind"] == "spine-peer"),
            "ib_links": sum(1 for L in links if L["kind"] == "ib-fabric"),
        },
    }

