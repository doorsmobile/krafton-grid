"""Aggregated IT inventory summary for UI + Redis seed."""

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
    GPU_NODES_PER_RACK,
    GPU_RACK_COUNT,
    GPUS_PER_NODE,
    K8S_CONTROL_PLANE,
    K8S_WORKERS,
    NVIDIA_IB_MODEL,
    NVIDIA_IB_SWITCHES,
    STORAGE_CAPACITY_PB,
    STORAGE_CLUSTER_COUNT,
    STORAGE_RACK_COUNT,
    STORAGE_VENDOR,
)

def build_inventory_summary() -> dict[str, Any]:
    return {
        "gpu": {
            "model": GPU_MODEL,
            "count": GPU_COUNT,
            "nodes": GPU_NODE_COUNT,
            "gpus_per_node": GPUS_PER_NODE,
            "racks": GPU_RACK_COUNT,
            "vendor": "NVIDIA",
            "interconnect": "NVIDIA InfiniBand (Quantum-2)",
            "form_factor": "HGX B300 class",
        },
        "storage": {
            "vendor": STORAGE_VENDOR,
            "capacity_pb": STORAGE_CAPACITY_PB,
            "clusters": STORAGE_CLUSTER_COUNT,
            "racks": STORAGE_RACK_COUNT,
            "protocol": "NVMe-oF / S3 / parallel FS",
            "usable_pct_target": 85.0,
        },
        "network": {
            "ethernet": {
                "vendor": "Arista",
                "spine": ARISTA_SPINE,
                "leaf": ARISTA_LEAF,
                "spine_model": ARISTA_MODEL_SPINE,
                "leaf_model": ARISTA_MODEL_LEAF,
                "role": "Frontend / storage / K8s east-west",
            },
            "infiniband": {
                "vendor": "NVIDIA",
                "switches": NVIDIA_IB_SWITCHES,
                "model": NVIDIA_IB_MODEL,
                "role": "GPU compute fabric",
            },
        },
        "kubernetes": {
            "vendor": "Dell",
            "model": DELL_MODEL,
            "nodes": DELL_K8S_NODES,
            "control_plane": K8S_CONTROL_PLANE,
            "workers": K8S_WORKERS,
            "distro": "Upstream K8s + GPU operator",
            "racks": 4,
        },
    }

