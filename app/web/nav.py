"""Sidebar tree and the page ↔ API catalog (Developers → API Catalog, GET /api/catalog)."""
from __future__ import annotations

NAV = [
    {"label": "Main", "href": "/", "icon": "grid", "api": ["/api/main", "/api/live", "/api/stream"],
     "desc": "Facility · AI · Cloud at a glance"},
    {"label": "Campus Aerial", "href": "/campus-aerial", "icon": "map", "api": ["/api/campus"],
     "desc": "100 MW master plan with live overlays"},
    {"label": "Facility", "icon": "bolt", "children": [
        {"label": "Overview", "href": "/facility", "api": ["/api/facility"], "desc": "Power, cooling, halls, modules"},
        {"label": "Power", "href": "/facility/power", "api": ["/api/facility/power", "/api/facility/power/{device_id}"], "desc": "2N chain · UPS · gensets"},
        {"label": "Cooling", "href": "/facility/cooling", "api": ["/api/facility/cooling", "/api/facility/cooling/{device_id}"], "desc": "CDUs · chillers · free cooling"},
        {"label": "Capacity", "href": "/facility/capacity", "api": ["/api/facility/capacity"], "desc": "M1–M5 build-out · headroom planner"},
        {"label": "Energy & ESG", "href": "/facility/energy", "api": ["/api/facility/energy"], "desc": "PUE · WUE · CUE · carbon · energy flow", "new": True},
    ]},
    {"label": "IT Cluster", "icon": "cpu", "children": [
        {"label": "GPU Monitoring", "href": "/gpu-fleet", "api": ["/api/gpu/fleet", "/api/gpu/heatmap", "/api/gpu/nodes"], "desc": "Fleet explorer · 5,000 B300"},
        {"label": "Storage", "href": "/storage", "api": ["/api/storage", "/api/storage/cluster/{cluster_id}"], "desc": "IBM Storage Scale · 100 PB"},
        {"label": "Network", "href": "/network", "api": ["/api/network", "/api/network/device/{device_id}"], "desc": "Arista + Quantum-2 IB"},
        {"label": "Kubernetes", "href": "/kubernetes", "api": ["/api/kubernetes", "/api/kubernetes/node/{node_id}"], "desc": "Dell XE9680 × 30"},
    ]},
    {"label": "GPU Platform", "icon": "layers", "children": [
        {"label": "Overview", "href": "/gpu-platform", "api": ["/api/gpu-platform"], "desc": "Console · projects · notices"},
        {"label": "Workloads", "href": "/gpu-platform/workloads", "api": ["/api/gpu-platform/workloads"], "desc": "Jobs · MIG · RCS · images"},
        {"label": "Ops", "href": "/gpu-platform/ops", "api": ["/api/gpu-platform/ops"], "desc": "Quota · RBAC · nodes · reports"},
    ]},
    {"label": "Cloud", "icon": "cloud", "children": [
        {"label": "Overview", "href": "/cloud", "api": ["/api/cloud"], "desc": "AWS → GCP → NHN top talkers"},
        {"label": "AWS GPUaaS", "href": "/cloud/aws", "api": ["/api/cloud/aws", "/api/cloud/aws/instance/{instance_id}"], "desc": "EC2 · Capacity Blocks"},
        {"label": "GCP Storage", "href": "/cloud/gcp", "api": ["/api/cloud/gcp", "/api/cloud/gcp/bucket/{bucket}"], "desc": "GCS · Persistent Disk"},
        {"label": "NHN GPUaaS", "href": "/cloud/nhn", "api": ["/api/cloud/nhn", "/api/cloud/nhn/instance/{instance_id}"], "desc": "GPU instances · KR1"},
    ]},
    {"label": "Observability", "icon": "pulse", "children": [
        {"label": "Overview", "href": "/observability", "api": ["/api/observability"], "desc": "Solutions hub"},
        {"label": "Explore", "href": "/observability/explore", "api": ["/api/observability/events", "/api/observability/metrics/query"], "desc": "Metrics + logs + events"},
        {"label": "Metrics", "href": "/observability/metrics", "api": ["/api/observability/metrics/query", "/api/observability/metrics/catalog"], "desc": "PromQL-style"},
        {"label": "Logs", "href": "/observability/logs", "api": ["/api/observability/logs/query"], "desc": "LogQL-style"},
        {"label": "Telemetry Relay", "href": "/observability/telemetry-relay", "api": ["/api/observability/relay"], "desc": "OTLP / HEC forwarding"},
        {"label": "Resource Usage", "href": "/observability/resource-usage", "api": ["/api/observability/usage"], "desc": "Usage + cost by project"},
        {"label": "Mission Control", "href": "/observability/mission-control", "api": ["/api/observability/agent", "/api/observability/agent/stream"], "desc": "Claude-powered investigation"},
    ]},
    {"label": "Operations", "icon": "wrench", "children": [
        {"label": "Inventory", "href": "/inventory", "api": ["/api/inventory"], "desc": "Every asset, one list"},
        {"label": "Rack View", "href": "/rack-view", "api": ["/api/racks", "/api/rack/{rack_id}"], "desc": "All halls · every rack"},
        {"label": "Alerts", "href": "/alerts", "api": ["/api/alerts", "/api/incidents"], "desc": "Incidents · correlation · ack"},
        {"label": "Slack / Webhooks", "href": "/alerts/integrations", "api": ["/api/alerts/integrations", "/api/alerts/deliveries"], "desc": "Fan-out & delivery log"},
        {"label": "Alert Config", "href": "/alerts/config", "api": ["/api/alerts/config"], "desc": "Rules · thresholds · routing"},
    ]},
    {"label": "Developers", "icon": "code", "children": [
        {"label": "API Catalog", "href": "/developers/api", "api": ["/api/catalog", "/openapi.json"], "desc": "Page ↔ API map · try it"},
    ]},
    {"label": "Platform", "icon": "gear", "children": [
        {"label": "Tech Spec", "href": "/platform/tech-spec", "api": ["/api/platform/tech-spec"], "desc": "Stack · models · code map"},
        {"label": "Vendors & API", "href": "/platform/vendors", "api": ["/api/vendors", "/api/vendor/{vendor_id}/sample"], "desc": "Facility · IT · Cloud integrations"},
        {"label": "Simulation", "href": "/platform/simulation", "api": ["/api/sim", "/api/sim/mode", "/api/sim/scenario/{scenario_id}/start"], "desc": "Scenarios · modes · Redis"},
        {"label": "Requirements", "href": "/platform/requirements", "api": ["/platform/requirements.md"], "desc": "Canonical spec · download"},
    ]},
    {"label": "Cost", "icon": "coin", "children": [
        {"label": "Summary", "href": "/cost", "api": ["/api/cost"], "desc": "DC + Cloud · MoM · YTD"},
        {"label": "DC", "href": "/cost/dc", "api": ["/api/cost/dc"], "desc": "전기요금 · 세금 · 관리비 · 인건비"},
        {"label": "Cloud", "href": "/cost/cloud", "api": ["/api/cost/cloud"], "desc": "AWS · GCP · NHN"},
        {"label": "Budget", "href": "/cost/budget", "api": ["/api/cost/budget", "/api/cost/budget/requests"], "desc": "예산 대비 실적 · 이관/증액/환입 신청", "new": True},
    ]},
    {"label": "Server Status", "href": "/server", "icon": "server", "api": ["/api/server", "/api/meta"],
     "desc": "This host: CPU · memory · disk · Redis"},
]

DETAIL_PAGES = [
    {"title": "Power device detail", "group": "Facility", "href": "/facility/power/{device_id}", "api": ["/api/facility/power/{device_id}"]},
    {"title": "Cooling device detail", "group": "Facility", "href": "/facility/cooling/{device_id}", "api": ["/api/facility/cooling/{device_id}"]},
    {"title": "Hall detail", "group": "Facility", "href": "/facility/hall/{hall_id}", "api": ["/api/facility/hall/{hall_id}"]},
    {"title": "GPU node detail", "group": "IT Cluster", "href": "/gpu-fleet/node/{node_id}", "api": ["/api/gpu/node/{node_id}", "/api/gpu/node/{node_id}/drain"]},
    {"title": "GPU device detail", "group": "IT Cluster", "href": "/gpu-fleet/device/{gpu_id}", "api": ["/api/gpu/device/{gpu_id}"]},
    {"title": "Slurm job detail", "group": "IT Cluster", "href": "/gpu-fleet/job/{job_id}", "api": ["/api/gpu/job/{job_id}"]},
    {"title": "Pod detail", "group": "IT Cluster", "href": "/gpu-fleet/pod/{pod}", "api": ["/api/gpu/pod/{pod}"]},
    {"title": "Storage cluster detail", "group": "IT Cluster", "href": "/storage/cluster/{cluster_id}", "api": ["/api/storage/cluster/{cluster_id}"]},
    {"title": "Storage top talkers", "group": "IT Cluster", "href": "/storage/toptalkers", "api": ["/api/storage/toptalkers"]},
    {"title": "Network device detail", "group": "IT Cluster", "href": "/network/device/{device_id}", "api": ["/api/network/device/{device_id}"]},
    {"title": "Network uplinks", "group": "IT Cluster", "href": "/network/uplinks", "api": ["/api/network"]},
    {"title": "Network top talkers", "group": "IT Cluster", "href": "/network/toptalkers", "api": ["/api/network"]},
    {"title": "Network inventory", "group": "IT Cluster", "href": "/network/inventory", "api": ["/api/network"]},
    {"title": "Kubernetes node detail", "group": "IT Cluster", "href": "/kubernetes/node/{node_id}", "api": ["/api/kubernetes/node/{node_id}"]},
    {"title": "AWS instance detail", "group": "Cloud", "href": "/cloud/aws/instance/{instance_id}", "api": ["/api/cloud/aws/instance/{instance_id}"]},
    {"title": "GCP bucket detail", "group": "Cloud", "href": "/cloud/gcp/bucket/{bucket}", "api": ["/api/cloud/gcp/bucket/{bucket}"]},
    {"title": "GCP disk detail", "group": "Cloud", "href": "/cloud/gcp/disk/{disk_id}", "api": ["/api/cloud/gcp/disk/{disk_id}"]},
    {"title": "NHN instance detail", "group": "Cloud", "href": "/cloud/nhn/instance/{instance_id}", "api": ["/api/cloud/nhn/instance/{instance_id}"]},
    {"title": "Rack elevation", "group": "Operations", "href": "/rack/{rack_id}", "api": ["/api/rack/{rack_id}"]},
]


def flat_pages() -> list[dict]:
    out = []
    for item in NAV:
        if "children" in item:
            for c in item["children"]:
                out.append({"title": c["label"] if c["label"] not in ("Overview", "Summary") else f"{item['label']} {c['label']}",
                            "group": item["label"], "href": c["href"], "api": c.get("api", []), "desc": c.get("desc", "")})
        else:
            out.append({"title": item["label"], "group": item["label"], "href": item["href"], "api": item.get("api", []),
                        "desc": item.get("desc", "")})
    return out


def catalog() -> list[dict]:
    return flat_pages() + [{**d, "desc": d.get("desc", "detail page")} for d in DETAIL_PAGES]


def crumbs(path: str) -> list[dict]:
    for item in NAV:
        if item.get("href") == path:
            return [{"label": item["label"], "href": item["href"]}]
        for c in item.get("children", []):
            if c["href"] == path:
                return [{"label": item["label"], "href": item["children"][0]["href"]}, {"label": c["label"], "href": c["href"]}]
    best = None
    for item in NAV:
        for c in item.get("children", []):
            if path.startswith(c["href"] + "/") and (best is None or len(c["href"]) > len(best[1]["href"])):
                best = (item, c)
    if best:
        return [{"label": best[0]["label"], "href": best[0]["children"][0]["href"]}, {"label": best[1]["label"], "href": best[1]["href"]}]
    return []
