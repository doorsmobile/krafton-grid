"""Resource Usage — compute / storage / network for cost & performance."""

from __future__ import annotations

from typing import Any


def get_resource_usage(engine: Any) -> dict[str, Any]:
    live = engine.get_live()
    it = engine.get_it_bundle()
    cost = engine.get_cost_bundle()
    summary = it.get("summary") or {}
    gpu = summary.get("gpu") or {}
    storage = summary.get("storage") or {}
    network = summary.get("network") or {}

    compute = {
        "gpu_count": gpu.get("count"),
        "gpu_util_pct": live.get("gpu_utilization_pct"),
        "k8s_nodes": (summary.get("kubernetes") or {}).get("nodes"),
        "k8s_cpu_util_pct": live.get("k8s_cpu_util_pct"),
        "k8s_pod_count": live.get("k8s_pod_count"),
        "it_load_mw": live.get("it_load_mw"),
    }
    storage_block = {
        "capacity_pb": storage.get("capacity_pb"),
        "used_pb": live.get("storage_used_pb"),
        "util_pct": round(
            (float(live.get("storage_used_pb") or 0) / float(storage.get("capacity_pb") or 1)) * 100,
            1,
        ),
        "clusters": storage.get("clusters"),
    }
    network_block = {
        "eth_fabric_util_pct": live.get("eth_fabric_util_pct"),
        "devices": network.get("devices") or network.get("switches"),
        "ib_util_pct": live.get("ib_fabric_util_pct") or live.get("ib_util_pct"),
    }
    cloud_block = {
        "aws_gpu_util_pct": live.get("aws_gpu_util_pct"),
        "nhn_gpu_util_pct": live.get("nhn_gpu_util_pct"),
        "gcp_storage_used_tb": live.get("gcp_storage_used_tb"),
    }

    dc_live = (cost.get("dc") or {}).get("live") or cost.get("dc_live") or {}
    cloud_live = (cost.get("cloud") or {}).get("live") or cost.get("cloud_live") or {}

    return {
        "compute": compute,
        "storage": storage_block,
        "network": network_block,
        "cloud": cloud_block,
        "cost_signals": {
            "dc": dc_live,
            "cloud": cloud_live,
        },
        "recommendations": [
            {
                "id": "idle-gpu",
                "severity": "info",
                "title": "Review idle GPU allocations",
                "detail": "Fleet Explorer idle funnel often shows reclaimable capacity during off-peak.",
                "href": "/gpu-fleet",
            },
            {
                "id": "storage-talkers",
                "severity": "info",
                "title": "Check storage Top Talkers",
                "detail": "High IOPS volumes drive rebuild risk and cooling load.",
                "href": "/storage/toptalkers",
            },
            {
                "id": "cost-cloud",
                "severity": "info",
                "title": "Cloud GPUaaS vs on-prem mix",
                "detail": "Compare AWS/NHN util against on-prem GPU util on Cost → Cloud.",
                "href": "/cost/cloud",
            },
        ],
        "apis": {
            "usage": "GET /api/observability/usage",
            "cost": "GET /api/cost",
            "gpu": "GET /api/gpu-fleet",
            "storage": "GET /api/storage",
            "network": "GET /api/network",
        },
    }
