"""Sidebar navigation tree."""

NAV = [
    {"id": "dashboard", "href": "/", "label": "Main"},
    {"id": "campus-aerial", "href": "/campus-aerial", "label": "Campus Aerial"},
    {
        "id": "facility",
        "label": "Facility",
        "children": [
            {"id": "facility-overview", "href": "/facility", "label": "Overview"},
            {"id": "power", "href": "/power", "label": "Power"},
            {"id": "cooling", "href": "/cooling", "label": "Cooling"},
            {"id": "capacity", "href": "/capacity", "label": "Capacity"},
        ],
    },
    {
        "id": "it-cluster",
        "label": "IT Cluster",
        "children": [
            {"id": "gpu-fleet", "href": "/gpu-fleet", "label": "GPU Monitoring"},
            {"id": "storage", "href": "/storage", "label": "Storage"},
            {"id": "network", "href": "/network", "label": "Network"},
            {"id": "kubernetes", "href": "/kubernetes", "label": "Kubernetes"},
        ],
    },
    {
        "id": "gpu-platform",
        "label": "GPU Platform",
        "children": [
            {"id": "gpu-overview", "href": "/gpu-platform", "label": "Overview"},
            {"id": "gpu-workloads", "href": "/gpu-platform/workloads", "label": "Workloads"},
            {"id": "gpu-ops", "href": "/gpu-platform/ops", "label": "Ops"},
        ],
    },
    {
        "id": "cloud",
        "label": "Cloud",
        "children": [
            {"id": "cloud-overview", "href": "/cloud", "label": "Overview"},
            {"id": "cloud-aws", "href": "/cloud/aws", "label": "AWS GPUaaS"},
            {"id": "cloud-gcp", "href": "/cloud/gcp", "label": "GCP Storage"},
            {"id": "cloud-nhn", "href": "/cloud/nhn", "label": "NHN GPUaaS"},
        ],
    },
    {
        "id": "observability",
        "label": "Observability",
        "children": [
            {"id": "o11y-overview", "href": "/observability", "label": "Overview"},
            {"id": "o11y-explore", "href": "/observability/explore", "label": "Explore"},
            {"id": "o11y-metrics", "href": "/observability/metrics", "label": "Metrics"},
            {"id": "o11y-logs", "href": "/observability/logs", "label": "Logs"},
            {"id": "o11y-relay", "href": "/observability/telemetry-relay", "label": "Telemetry Relay"},
            {"id": "o11y-usage", "href": "/observability/resource-usage", "label": "Resource Usage"},
            {"id": "o11y-agent", "href": "/observability/mission-control", "label": "Mission Control"},
        ],
    },
    {
        "id": "operations",
        "label": "Operations",
        "children": [
            {"id": "inventory", "href": "/inventory", "label": "Inventory"},
            {"id": "rack-view", "href": "/rack-view", "label": "Rack View"},
            {"id": "alerts", "href": "/alerts", "label": "Alerts"},
            {"id": "alerts-integrations", "href": "/alerts/integrations", "label": "Slack / Webhooks"},
            {"id": "alerts-config", "href": "/alerts/config", "label": "Alert Config"},
        ],
    },
    {
        "id": "developers",
        "label": "Developers",
        "children": [
            {"id": "dev-api", "href": "/developers/api", "label": "API Catalog"},
        ],
    },
    {
        "id": "platform",
        "label": "Platform",
        "children": [
            {"id": "tech-spec", "href": "/tech-spec", "label": "Tech Spec"},
            {"id": "vendors", "href": "/vendors", "label": "Vendors & API"},
            {"id": "simulation", "href": "/simulation", "label": "Simulation"},
            {"id": "requirements", "href": "/platform/requirements", "label": "Requirements"},
        ],
    },
    {
        "id": "cost",
        "label": "Cost",
        "children": [
            {"id": "cost-summary", "href": "/cost", "label": "Summary"},
            {"id": "cost-dc", "href": "/cost/dc", "label": "DC"},
            {"id": "cost-cloud", "href": "/cost/cloud", "label": "Cloud"},
        ],
    },
]
