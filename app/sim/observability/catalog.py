"""Observability solutions + operator page ↔ developer API catalog."""

from __future__ import annotations

from typing import Any

# CoreWeave Observe™–inspired pillars (Krafton Grid campus)
OBSERVABILITY_SOLUTIONS: list[dict[str, Any]] = [
    {
        "id": "explore",
        "name": "Explore",
        "href": "/observability/explore",
        "api": "/api/observability/explore",
        "audience": "operators",
        "summary": "Grafana-style explore for metrics, logs, and events across Facility · IT · Cloud.",
    },
    {
        "id": "metrics",
        "name": "Metrics (PromQL)",
        "href": "/observability/metrics",
        "api": "/api/observability/metrics/query",
        "audience": "both",
        "summary": "Query Prometheus-compatible metrics with PromQL against the Redis live store.",
    },
    {
        "id": "logs",
        "name": "Logs (LogQL)",
        "href": "/observability/logs",
        "api": "/api/observability/logs/query",
        "audience": "both",
        "summary": "Query correlated facility and fabric logs with a LogQL-style selector.",
    },
    {
        "id": "telemetry-relay",
        "name": "Telemetry Relay",
        "href": "/observability/telemetry-relay",
        "api": "/api/observability/relay",
        "audience": "both",
        "summary": "Forward metrics, logs, and audit events to external HTTPS / OTLP endpoints.",
    },
    {
        "id": "mission-control",
        "name": "Mission Control Agent",
        "href": "/observability/mission-control",
        "api": "/api/observability/agent",
        "audience": "operators",
        "summary": "Conversational investigation over current page context and live telemetry.",
    },
    {
        "id": "resource-usage",
        "name": "Resource Usage",
        "href": "/observability/resource-usage",
        "api": "/api/observability/usage",
        "audience": "both",
        "summary": "Compute, storage, and network usage for cost and performance optimization.",
    },
    {
        "id": "alerts",
        "name": "Alerts → Slack",
        "href": "/alerts",
        "api": "/api/alerts",
        "audience": "both",
        "summary": "Real-time notifications for clusters, facility, and ops — delivered in-app and to Slack.",
    },
]

# Every operator page has a matching developer API surface.
PAGE_API_CATALOG: list[dict[str, Any]] = [
    {"section": "Main", "page": "Main", "path": "/", "api": "GET /api/live", "methods": ["GET"], "notes": "Facility + IT live snapshot"},
    {"section": "Main", "page": "Campus Aerial", "path": "/campus-aerial", "api": "GET /api/site", "methods": ["GET"], "notes": "Site / campus meta"},
    {"section": "Facility", "page": "Overview", "path": "/facility", "api": "GET /api/facility", "methods": ["GET"], "notes": "Power · cooling · halls · modules"},
    {"section": "Facility", "page": "Power", "path": "/power", "api": "GET /api/facility/power", "methods": ["GET"], "notes": "Power chain"},
    {"section": "Facility", "page": "Power stage", "path": "/facility/power/stage/{id}", "api": "GET /api/facility/power/stage/{id}", "methods": ["GET"], "notes": "Stage detail + series"},
    {"section": "Facility", "page": "Cooling", "path": "/cooling", "api": "GET /api/facility/cooling", "methods": ["GET"], "notes": "Cooling chain"},
    {"section": "Facility", "page": "Cooling stage", "path": "/facility/cooling/stage/{id}", "api": "GET /api/facility/cooling/stage/{id}", "methods": ["GET"], "notes": "Stage detail + series"},
    {"section": "Facility", "page": "Capacity", "path": "/capacity", "api": "GET /api/facility/capacity", "methods": ["GET"], "notes": "Halls + modules"},
    {"section": "Facility", "page": "Hall detail", "path": "/facility/hall/{id}", "api": "GET /api/facility/hall/{id}", "methods": ["GET"], "notes": "Hall detail + series"},
    {"section": "IT Cluster", "page": "GPU Monitoring", "path": "/gpu-fleet", "api": "GET /api/gpu-fleet", "methods": ["GET"], "notes": "Fleet Explorer"},
    {"section": "IT Cluster", "page": "GPU device", "path": "/gpu-fleet/device/{id}", "api": "GET /api/gpu-fleet/device/{id}", "methods": ["GET"], "notes": "Device detail"},
    {"section": "IT Cluster", "page": "GPU node", "path": "/gpu-fleet/node/{id}", "api": "GET /api/gpu-fleet/node/{id}", "methods": ["GET"], "notes": "Node detail"},
    {"section": "IT Cluster", "page": "GPU pod", "path": "/gpu-fleet/pod/{id}", "api": "GET /api/gpu-fleet/pod/{id}", "methods": ["GET"], "notes": "Pod detail"},
    {"section": "IT Cluster", "page": "Storage", "path": "/storage", "api": "GET /api/storage", "methods": ["GET"], "notes": "Clusters + talkers"},
    {"section": "IT Cluster", "page": "Storage talkers", "path": "/storage/toptalkers", "api": "GET /api/storage/toptalkers", "methods": ["GET"], "notes": "IOPS ranking"},
    {"section": "IT Cluster", "page": "Storage cluster", "path": "/storage/cluster/{id}", "api": "GET /api/storage/cluster/{id}", "methods": ["GET"], "notes": "Cluster detail"},
    {"section": "IT Cluster", "page": "Network", "path": "/network", "api": "GET /api/network", "methods": ["GET"], "notes": "Fabric bundle"},
    {"section": "IT Cluster", "page": "Network device", "path": "/network/device/{id}", "api": "GET /api/network/device/{id}", "methods": ["GET"], "notes": "Device + ifaces"},
    {"section": "IT Cluster", "page": "Kubernetes", "path": "/kubernetes", "api": "GET /api/kubernetes", "methods": ["GET"], "notes": "Cluster overview"},
    {"section": "IT Cluster", "page": "K8s node", "path": "/kubernetes/node/{id}", "api": "GET /api/kubernetes/node/{id}", "methods": ["GET"], "notes": "Node detail"},
    {"section": "GPU Platform", "page": "Overview", "path": "/gpu-platform", "api": "GET /api/gpu-platform", "methods": ["GET"], "notes": "Console bundle"},
    {"section": "GPU Platform", "page": "Workloads", "path": "/gpu-platform/workloads", "api": "GET /api/gpu-platform", "methods": ["GET"], "notes": "Jobs · partition · RCS"},
    {"section": "GPU Platform", "page": "Ops", "path": "/gpu-platform/ops", "api": "GET /api/gpu-platform", "methods": ["GET"], "notes": "Projects · nodes · reports"},
    {"section": "Cloud", "page": "Overview", "path": "/cloud", "api": "GET /api/cloud", "methods": ["GET"], "notes": "AWS · GCP · NHN"},
    {"section": "Cloud", "page": "AWS", "path": "/cloud/aws", "api": "GET /api/cloud/aws", "methods": ["GET"], "notes": "GPUaaS catalog"},
    {"section": "Cloud", "page": "AWS instance", "path": "/cloud/aws/instance/{id}", "api": "GET /api/cloud/aws/instance/{id}", "methods": ["GET"], "notes": "Instance detail"},
    {"section": "Cloud", "page": "GCP", "path": "/cloud/gcp", "api": "GET /api/cloud/gcp", "methods": ["GET"], "notes": "Storage catalog"},
    {"section": "Cloud", "page": "GCP bucket", "path": "/cloud/gcp/bucket/{id}", "api": "GET /api/cloud/gcp/bucket/{id}", "methods": ["GET"], "notes": "Bucket detail"},
    {"section": "Cloud", "page": "GCP disk", "path": "/cloud/gcp/disk/{id}", "api": "GET /api/cloud/gcp/disk/{id}", "methods": ["GET"], "notes": "Disk detail"},
    {"section": "Cloud", "page": "NHN", "path": "/cloud/nhn", "api": "GET /api/cloud/nhn", "methods": ["GET"], "notes": "GPUaaS catalog"},
    {"section": "Cloud", "page": "NHN instance", "path": "/cloud/nhn/instance/{id}", "api": "GET /api/cloud/nhn/instance/{id}", "methods": ["GET"], "notes": "Instance detail"},
    {"section": "Operations", "page": "Inventory", "path": "/inventory", "api": "GET /api/inventory", "methods": ["GET"], "notes": "Unified asset catalog"},
    {"section": "Operations", "page": "Rack View", "path": "/rack-view", "api": "GET /api/racks", "methods": ["GET"], "notes": "Floor map"},
    {"section": "Operations", "page": "Alerts", "path": "/alerts", "api": "GET /api/alerts", "methods": ["GET"], "notes": "Active / recent alerts"},
    {"section": "Operations", "page": "Alert integrations", "path": "/alerts/integrations", "api": "GET /api/alerts/integrations", "methods": ["GET", "POST"], "notes": "Slack · webhook destinations"},
    {"section": "Operations", "page": "Alert config", "path": "/alerts/config", "api": "GET /api/alerts/config", "methods": ["GET", "PUT"], "notes": "Per-alert routing"},
    {"section": "Observability", "page": "Overview", "path": "/observability", "api": "GET /api/observability", "methods": ["GET"], "notes": "Solutions hub"},
    {"section": "Observability", "page": "Explore", "path": "/observability/explore", "api": "GET /api/observability/explore", "methods": ["GET"], "notes": "Multi-signal explore"},
    {"section": "Observability", "page": "Metrics", "path": "/observability/metrics", "api": "POST /api/observability/metrics/query", "methods": ["POST"], "notes": "PromQL"},
    {"section": "Observability", "page": "Logs", "path": "/observability/logs", "api": "POST /api/observability/logs/query", "methods": ["POST"], "notes": "LogQL"},
    {"section": "Observability", "page": "Telemetry Relay", "path": "/observability/telemetry-relay", "api": "GET /api/observability/relay", "methods": ["GET", "POST"], "notes": "Forwarding pipelines"},
    {"section": "Observability", "page": "Resource Usage", "path": "/observability/resource-usage", "api": "GET /api/observability/usage", "methods": ["GET"], "notes": "Usage & cost signals"},
    {"section": "Observability", "page": "Mission Control", "path": "/observability/mission-control", "api": "POST /api/observability/agent", "methods": ["POST"], "notes": "Conversational agent"},
    {"section": "Developers", "page": "API Catalog", "path": "/developers/api", "api": "GET /api/catalog", "methods": ["GET"], "notes": "This catalog as JSON"},
    {"section": "Cost", "page": "Summary", "path": "/cost", "api": "GET /api/cost", "methods": ["GET"], "notes": "DC + Cloud"},
    {"section": "Cost", "page": "DC", "path": "/cost/dc", "api": "GET /api/cost/dc", "methods": ["GET"], "notes": "Power · tax · mgmt · labor"},
    {"section": "Cost", "page": "Cloud", "path": "/cost/cloud", "api": "GET /api/cost/cloud", "methods": ["GET"], "notes": "AWS · GCP · NHN"},
    {"section": "Platform", "page": "Vendors", "path": "/vendors", "api": "GET /api/vendors", "methods": ["GET"], "notes": "Vendor health"},
    {"section": "Platform", "page": "Vendor sample", "path": "/vendors", "api": "GET /api/vendor/{id}/sample", "methods": ["GET"], "notes": "Simulated probe"},
    {"section": "Platform", "page": "Simulation", "path": "/simulation", "api": "GET /api/sim/dump", "methods": ["GET", "POST"], "notes": "Mode · alert inject · export"},
    {"section": "Platform", "page": "Tech Spec", "path": "/tech-spec", "api": "GET /api/catalog", "methods": ["GET"], "notes": "Cross-link to API catalog"},
    {"section": "Platform", "page": "Requirements", "path": "/platform/requirements", "api": "GET /platform/requirements.md", "methods": ["GET"], "notes": "Markdown download"},
]

ALERT_CATALOG: list[dict[str, Any]] = [
    {"id": "fac.power.ups_overload", "category": "Facility Power", "severity": "critical", "title": "UPS overload", "description": "UPS load exceeds 90% on any modular block"},
    {"id": "fac.power.feeder_trip", "category": "Facility Power", "severity": "critical", "title": "MV feeder trip", "description": "Medium-voltage feeder breaker open"},
    {"id": "fac.cooling.cdu_vibration", "category": "Facility Cooling", "severity": "warning", "title": "CDU pump vibration", "description": "Secondary pump vibration rising"},
    {"id": "fac.cooling.leak", "category": "Facility Cooling", "severity": "critical", "title": "Liquid leak", "description": "Manifold leak sensor trip"},
    {"id": "gpu.hw.thermal", "category": "GPU Hardware", "severity": "critical", "title": "GPU thermal violation", "description": "Device temperature above policy threshold"},
    {"id": "gpu.hw.xid", "category": "GPU Hardware", "severity": "critical", "title": "GPU XID error", "description": "NVIDIA XID fatal/error on device"},
    {"id": "gpu.hw.ecc", "category": "GPU Hardware", "severity": "warning", "title": "GPU ECC elevated", "description": "Correctable ECC rate above baseline"},
    {"id": "gpu.runtime.straggler", "category": "GPU Runtime", "severity": "warning", "title": "GPU straggler", "description": "Rank lagging in distributed training job"},
    {"id": "net.optics.rx_low", "category": "Network", "severity": "warning", "title": "Optics RX power low", "description": "Arista leaf/spine optics below threshold"},
    {"id": "net.ib.port_flap", "category": "Network", "severity": "warning", "title": "IB port flap storm", "description": "InfiniBand port flapping"},
    {"id": "st.rebuild", "category": "Storage", "severity": "info", "title": "Storage rebuild", "description": "IBM Storage cluster rebuild in progress"},
    {"id": "st.quota", "category": "Storage", "severity": "warning", "title": "Volume quota", "description": "Volume usage above soft quota"},
    {"id": "k8s.node_notready", "category": "Kubernetes", "severity": "critical", "title": "Node NotReady", "description": "Dell PowerEdge node NotReady"},
    {"id": "k8s.cordon", "category": "Kubernetes", "severity": "info", "title": "Node cordoned", "description": "Node cordoned for maintenance"},
    {"id": "cloud.aws.capacity", "category": "Cloud", "severity": "warning", "title": "AWS capacity block", "description": "Capacity Block utilization high"},
    {"id": "cloud.gcp.egress", "category": "Cloud", "severity": "info", "title": "GCP egress spike", "description": "GCS egress above daily baseline"},
]


def get_page_api_catalog(section: str | None = None) -> dict[str, Any]:
    rows = PAGE_API_CATALOG
    if section:
        key = section.strip().lower()
        rows = [r for r in rows if r["section"].lower() == key]
    sections = sorted({r["section"] for r in PAGE_API_CATALOG})
    return {
        "concept": {
            "operators": "Use HTML pages under Krafton Grid for day-2 operations.",
            "developers": "Consume the same data over JSON APIs — every page has a paired endpoint.",
        },
        "total": len(rows),
        "sections": sections,
        "pages": rows,
    }


def get_observability_overview(live: dict[str, Any] | None = None) -> dict[str, Any]:
    live = live or {}
    return {
        "brand": "Krafton Grid Observability",
        "tagline": "Metrics · logs · events for Facility, IT Cluster, and Cloud — operators on pages, developers on APIs.",
        "samples_per_sec_sim": 2_400_000,
        "solutions": OBSERVABILITY_SOLUTIONS,
        "kpis": {
            "active_alerts": live.get("active_alerts", 0),
            "gpu_util_pct": live.get("gpu_utilization_pct"),
            "it_load_mw": live.get("it_load_mw"),
            "pue": live.get("pue"),
            "storage_used_pb": live.get("storage_used_pb"),
            "eth_fabric_util_pct": live.get("eth_fabric_util_pct"),
        },
        "audiences": [
            {"id": "operators", "label": "Operators", "use": "Navigate Observability + Alerts pages for investigation and Slack routing."},
            {"id": "developers", "label": "Developers", "use": "Pull every page’s data via /api/* and discover mappings in /developers/api."},
        ],
    }
