"""AWS / GCP / NHN cloud service catalogs."""

from __future__ import annotations

from typing import Any

def build_nhn_gpuaas() -> dict[str, Any]:
    instances = []
    flavors = [
        ("g2.b300.1x", 1, "NVIDIA B300"),
        ("g2.b300.4x", 4, "NVIDIA B300"),
        ("g2.b300.8x", 8, "NVIDIA B300"),
    ]
    for i in range(1, 13):
        fl, gpus, model = flavors[i % len(flavors)]
        instances.append(
            {
                "id": f"nhn-gpu-{i:03d}",
                "name": f"gpuaas-prod-{i:02d}",
                "region": "KR1" if i % 2 else "KR2",
                "flavor": fl,
                "gpu_model": model,
                "gpus": gpus,
                "status": "ACTIVE" if i <= 10 else "BUILD",
                "util_pct": round(40 + (i * 3.7) % 50, 1),
                "hourly_krw": 4200 * gpus,
            }
        )
    return {
        "provider": "NHN Cloud",
        "service": "GPUaaS",
        "api": {
            "protocol": "REST",
            "base_url": "https://api-gpuaas.nhncloud.com/v1",
            "auth": "AppKey + Secret",
            "endpoints": ["/instances", "/flavors", "/metrics", "/billing"],
            "sample_metric": "cloud.nhn.gpu_util_pct",
        },
        "instances": instances,
        "summary": {
            "instances": len(instances),
            "gpus_total": sum(x["gpus"] for x in instances),
            "active": sum(1 for x in instances if x["status"] == "ACTIVE"),
        },
    }

def build_gcp_storage() -> dict[str, Any]:
    buckets = [
        {"id": "kg-aidc-train", "location": "asia-northeast3", "class": "STANDARD", "used_tb": 820.4, "objects": 12_400_000},
        {"id": "kg-aidc-ckpt", "location": "asia-northeast3", "class": "NEARLINE", "used_tb": 1_450.0, "objects": 88_200},
        {"id": "kg-aidc-dataset", "location": "asia-northeast3", "class": "STANDARD", "used_tb": 2_100.5, "objects": 4_200_000},
        {"id": "kg-aidc-archive", "location": "asia-northeast3", "class": "COLDLINE", "used_tb": 3_600.0, "objects": 510_000},
        {"id": "kg-aidc-logs", "location": "asia-northeast3", "class": "STANDARD", "used_tb": 95.2, "objects": 91_000_000},
    ]
    disks = [
        {"id": "pd-ssd-train-01", "type": "pd-ssd", "size_tb": 64, "attached": "gke-train-pool"},
        {"id": "pd-ssd-train-02", "type": "pd-ssd", "size_tb": 64, "attached": "gke-train-pool"},
        {"id": "pd-balanced-ckpt", "type": "pd-balanced", "size_tb": 128, "attached": "ckpt-nfs"},
    ]
    return {
        "provider": "Google Cloud",
        "service": "Cloud Storage + Persistent Disk",
        "api": {
            "protocol": "REST / JSON API",
            "base_url": "https://storage.googleapis.com/storage/v1",
            "auth": "OAuth2 / ADC",
            "endpoints": ["/b", "/b/{bucket}/o", "/projects/.../metrics"],
            "sample_metric": "cloud.gcp.storage_used_tb",
        },
        "buckets": buckets,
        "disks": disks,
        "summary": {
            "buckets": len(buckets),
            "used_tb": round(sum(b["used_tb"] for b in buckets), 1),
            "disks": len(disks),
        },
    }

def build_aws_gpuaas() -> dict[str, Any]:
    """AWS GPUaaS-style capacity (EC2 P/G + SageMaker / Capacity Blocks demo)."""
    instances = []
    types = [
        ("p5e.48xlarge", 8, "NVIDIA B300", "ap-northeast-2"),
        ("p5.48xlarge", 8, "NVIDIA H100", "ap-northeast-2"),
        ("g6e.48xlarge", 8, "NVIDIA L40S", "ap-northeast-2"),
    ]
    for i in range(1, 11):
        itype, gpus, model, region = types[i % len(types)]
        instances.append(
            {
                "id": f"i-aws{i:08d}",
                "name": f"aws-gpuaas-{i:02d}",
                "instance_type": itype,
                "gpu_model": model,
                "gpus": gpus,
                "region": region,
                "az": f"{region}a",
                "state": "running" if i <= 8 else "pending",
                "util_pct": round(35 + (i * 4.1) % 55, 1),
                "hourly_usd": round(32.0 * (gpus / 8), 2),
            }
        )
    return {
        "provider": "Amazon Web Services",
        "service": "GPUaaS (EC2 / Capacity Blocks)",
        "api": {
            "protocol": "AWS SDK / CloudWatch",
            "base_url": "https://ec2.ap-northeast-2.amazonaws.com",
            "auth": "IAM SigV4",
            "endpoints": ["DescribeInstances", "GetMetricData", "GetCostAndUsage"],
            "sample_metric": "cloud.aws.gpu_util_pct",
        },
        "instances": instances,
        "summary": {
            "instances": len(instances),
            "gpus_total": sum(x["gpus"] for x in instances),
            "running": sum(1 for x in instances if x["state"] == "running"),
        },
    }

def build_cloud_catalog() -> dict[str, Any]:
    return {
        "aws": build_aws_gpuaas(),
        "gcp": build_gcp_storage(),
        "nhn": build_nhn_gpuaas(),
    }


# ---- Cost: DC (power/tax/mgmt/labor) + Cloud (AWS/GCP/NHN) ----

