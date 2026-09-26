"""IT vendor API catalog entries (NVIDIA / Arista / Dell / IBM)."""

from __future__ import annotations

from app.sim.it.constants import DELL_MODEL

IT_VENDORS_EXTRA = [
    {
        "id": "nvidia",
        "name": "NVIDIA",
        "category": "GPU & IB Fabric",
        "products": ["B300", "HGX", "Quantum-2 QM9700", "DOCA / UFM"],
        "api": {
            "protocol": "NVML / DCGM / UFM REST",
            "base_url": "https://api.nvidia-ufm.local/v1",
            "auth": "API Token",
            "endpoints": ["/gpus", "/ib/switches", "/telemetry", "/jobs"],
            "sample_metric": "gpu.sm_utilization_pct",
        },
        "coverage": ["GPU", "IB Switch", "Fabric Manager"],
        "status": "connected",
        "latency_ms": 35,
    },
    {
        "id": "arista",
        "name": "Arista",
        "category": "Ethernet Fabric",
        "products": ["7800R3", "7060X6", "CloudVision"],
        "api": {
            "protocol": "eAPI / CloudVision REST",
            "base_url": "https://api.arista-cvp.local/api/v3",
            "auth": "Token",
            "endpoints": ["/devices", "/interfaces", "/telemetry", "/events"],
            "sample_metric": "switch.port.utilization_pct",
        },
        "coverage": ["Spine", "Leaf", "Optics"],
        "status": "connected",
        "latency_ms": 44,
    },
    {
        "id": "dell",
        "name": "Dell Technologies",
        "category": "K8s Servers",
        "products": [DELL_MODEL, "iDRAC9", "OpenManage"],
        "api": {
            "protocol": "Redfish / iDRAC",
            "base_url": "https://api.dell-ome.local/api/v1",
            "auth": "Basic / X-Auth",
            "endpoints": ["/Systems", "/Chassis", "/Managers", "/EventService"],
            "sample_metric": "server.power_watts",
        },
        "coverage": ["Server", "BMC", "Firmware"],
        "status": "connected",
        "latency_ms": 52,
    },
    {
        "id": "ibm",
        "name": "IBM Storage",
        "category": "Parallel Storage",
        "products": ["IBM Storage Scale", "ESS", "Object Gateway"],
        "api": {
            "protocol": "REST / Prometheus",
            "base_url": "https://api.ibm-storage.local/v1",
            "auth": "API Key",
            "endpoints": ["/clusters", "/volumes", "/metrics", "/alerts"],
            "sample_metric": "storage.used_pb",
        },
        "coverage": ["Cluster", "Volume", "Throughput"],
        "status": "connected",
        "latency_ms": 48,
    },
]

