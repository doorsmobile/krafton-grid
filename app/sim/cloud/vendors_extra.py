"""Cloud vendor API catalog entries."""

from __future__ import annotations

CLOUD_VENDORS_EXTRA = [
    {
        "id": "aws",
        "name": "Amazon Web Services",
        "category": "Cloud GPUaaS",
        "products": ["EC2 P/G", "Capacity Blocks", "CloudWatch", "Cost Explorer"],
        "api": {
            "protocol": "AWS SDK / CloudWatch",
            "base_url": "https://ec2.ap-northeast-2.amazonaws.com",
            "auth": "IAM SigV4",
            "endpoints": ["DescribeInstances", "GetMetricData", "GetCostAndUsage"],
            "sample_metric": "cloud.aws.gpu_util_pct",
        },
        "coverage": ["GPU instance", "Metrics", "Cost"],
        "status": "connected",
        "latency_ms": 95,
    },
    {
        "id": "gcp",
        "name": "Google Cloud",
        "category": "Cloud Storage",
        "products": ["Cloud Storage", "Persistent Disk", "Monitoring"],
        "api": {
            "protocol": "REST / JSON API",
            "base_url": "https://storage.googleapis.com/storage/v1",
            "auth": "OAuth2 / ADC",
            "endpoints": ["/b", "/b/{bucket}/o", "/projects/.../metrics"],
            "sample_metric": "cloud.gcp.storage_used_tb",
        },
        "coverage": ["Bucket", "Object", "PD"],
        "status": "connected",
        "latency_ms": 90,
    },
    {
        "id": "nhn",
        "name": "NHN Cloud",
        "category": "Cloud GPUaaS",
        "products": ["GPUaaS", "Instance API", "Billing API"],
        "api": {
            "protocol": "REST",
            "base_url": "https://api-gpuaas.nhncloud.com/v1",
            "auth": "AppKey + Secret",
            "endpoints": ["/instances", "/flavors", "/metrics", "/billing"],
            "sample_metric": "cloud.nhn.gpu_util_pct",
        },
        "coverage": ["GPU instance", "Utilization", "Billing"],
        "status": "connected",
        "latency_ms": 85,
    },
]

