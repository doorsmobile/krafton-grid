"""Dell Kubernetes node inventory."""

from __future__ import annotations

from typing import Any

from app.sim.it.constants import DELL_K8S_NODES, DELL_MODEL, K8S_CONTROL_PLANE

def build_k8s_nodes() -> list[dict[str, Any]]:
    nodes = []
    for i in range(1, DELL_K8S_NODES + 1):
        role = "control-plane" if i <= K8S_CONTROL_PLANE else "worker"
        nodes.append(
            {
                "id": f"K8S-{i:02d}",
                "hostname": f"dell-k8s-{i:02d}",
                "vendor": "Dell",
                "model": DELL_MODEL,
                "role": role,
                "cpu_sockets": 2,
                "ram_tb": 2.0 if role == "worker" else 1.0,
                "rack_id": f"R-K8S-{(i - 1) // 8 + 1:02d}",
                "ru": 1 + ((i - 1) % 8) * 5,
                "status": "Ready",
                "k8s_version": "1.31.2",
            }
        )
    return nodes

