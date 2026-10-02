import json

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse

from ... import config
from .. import agent as A
from ...sim.logs import SERVICES
from ...sim.promql import PromQLError, query as promql
from ..data import rm
from ..templating import render

router = APIRouter()

EXAMPLES_PROMQL = [
    ("Hottest racks", "topk(5, rack_temp_max_c)"),
    ("PUE (5 m avg)", "avg_over_time(site_pue[5m])"),
    ("GPU util by hall", "avg by (hall) (gpu_util_pct)"),
    ("Row coolant supply", "cooling_tcs_supply_c"),
    ("Hot-tier latency", 'storage_latency_ms{cluster="ss-hot"}'),
    ("IB leaf error rate", 'topk(5, rate(net_device_errors_total{fabric="infiniband"}[5m]))'),
    ("Node power R01–R04", 'sum by (rack) (node_power_kw{rack=~"R0[1-4]"})'),
    ("Cloud burn ₩/h", "cloud_cost_hr_krw"),
    ("Idle allocated GPUs", "gpu_idle_alloc"),
    ("Partition utilization", "avg by (partition) (node_gpu_util)"),
]
EXAMPLES_LOGQL = [
    ("GPU XID events", '{service="dcgm-exporter", level=~"warn|error"} |= "Xid"'),
    ("Slurm job failures", '{service="slurmctld", level="error"}'),
    ("IB fabric warnings", '{service="ufm", level="warn"}'),
    ("Alerts raised", '{service="grid-sim"} |= "ALERT"'),
    ("Storage throughput", '{service="mmfs"} |= "throughput"'),
    ("vLLM throughput", '{service="vllm"}'),
    ("XID rate / 5 m", 'count_over_time({service="dcgm-exporter"} |= "Xid" [5m])'),
]


@router.get("/observability", include_in_schema=False)
def page_hub(request: Request):
    return render(request, "observability/hub.html", "Observability", rm.view("observability"))


@router.get("/api/observability", tags=["observability"], summary="Observability hub: solutions, metric/log/event counts, relays")
def api_hub():
    return rm.view("observability")


@router.get("/observability/explore", include_in_schema=False)
def page_explore(request: Request):
    return render(request, "observability/explore.html", "Explore", {"examples": EXAMPLES_PROMQL, "log_examples": EXAMPLES_LOGQL})


@router.get("/api/observability/events", tags=["observability"], summary="Unified event timeline (alerts, scenarios, operator actions, XIDs)")
def api_events(minutes: int = 60):
    return {"events": rm.events(max(1, min(config.MAX_WINDOW_MIN, minutes)) * 60)}


@router.get("/observability/metrics", include_in_schema=False)
def page_metrics(request: Request):
    return render(request, "observability/metrics.html", "Metrics",
                  {"examples": EXAMPLES_PROMQL, "catalog": rm.tsdb.catalog()}, q=request.query_params.get("q", ""))


@router.get("/api/observability/metrics/catalog", tags=["observability"], summary="Metric catalog: name, labels, unit, tier, retention")
def api_metric_catalog():
    return {"metrics": rm.tsdb.catalog()}


@router.post("/api/observability/metrics/query", tags=["observability"], summary="PromQL-style range query")
def api_metrics_query(payload: dict = Body(...)):
    q = (payload or {}).get("query", "").strip()
    if not q:
        raise HTTPException(400, "query required")
    window = int((payload or {}).get("window_minutes", 15))
    try:
        return {"query": q, **promql(rm.tsdb, q, window_s=max(1, min(config.MAX_WINDOW_MIN, window)) * 60,
                                      max_series=int(payload.get("max_series", 40)))}
    except PromQLError as e:
        raise HTTPException(400, str(e))


@router.get("/observability/logs", include_in_schema=False)
def page_logs(request: Request):
    return render(request, "observability/logs.html", "Logs", {"examples": EXAMPLES_LOGQL, "services": sorted(SERVICES)},
                  q=request.query_params.get("q", ""))


@router.post("/api/observability/logs/query", tags=["observability"], summary="LogQL-style log query (streams or count_over_time/rate)")
def api_logs_query(payload: dict = Body(...)):
    q = (payload or {}).get("query", "").strip()
    try:
        return {"query": q, **rm.logs(q, window_s=max(1, min(config.MAX_WINDOW_MIN, int(payload.get("window_minutes", 30)))) * 60,
                                      limit=max(1, min(500, int(payload.get("limit", 200)))))}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/observability/telemetry-relay", include_in_schema=False)
def page_relay(request: Request):
    return render(request, "observability/relay.html", "Telemetry Relay", rm.view("relay"))


@router.get("/api/observability/relay", tags=["observability"], summary="Telemetry relay destinations and throughput")
def api_relay():
    return rm.view("relay")


@router.post("/api/observability/relay/{relay_id}", tags=["observability"], summary="Enable / disable a relay destination")
def api_relay_toggle(relay_id: str, payload: dict = Body(...)):
    return rm.cmd("relay.set", id=relay_id, enabled=bool((payload or {}).get("enabled")))


@router.get("/observability/resource-usage", include_in_schema=False)
def page_usage(request: Request):
    return render(request, "observability/usage.html", "Resource Usage", rm.view("usage"))


@router.get("/api/observability/usage", tags=["observability"], summary="Compute / storage / network usage per project with cost signal")
def api_usage():
    return rm.view("usage")


@router.get("/observability/mission-control", include_in_schema=False)
def page_agent(request: Request):
    return render(request, "observability/mission_control.html", "Mission Control",
                  {"claude": A.claude_available(), "model": config.MISSION_CONTROL_MODEL, "mode": config.MISSION_CONTROL_MODE,
                   "tools": [{"name": t["name"], "desc": t["description"].split(".")[0]} for t in A.TOOLS],
                   "suggestions": ["지금 캠퍼스에 문제 있어?", "Which racks are running hottest and why?",
                                   "GPU 유휴 자원 낭비가 얼마나 돼?", "Is the InfiniBand fabric healthy?",
                                   "이번 달 전기요금이랑 클라우드 비용 요약해줘", "Why is the Slurm queue backed up?"]})


@router.post("/api/observability/agent", tags=["observability"], summary="Ask Mission Control (Claude tool-use over live telemetry)")
async def api_agent(payload: dict = Body(...)):
    return await A.ask(rm, (payload or {}).get("question", ""), (payload or {}).get("session"))


@router.get("/api/observability/agent/stream", tags=["observability"], summary="Mission Control as Server-Sent Events (status/update/tool/answer/done)")
async def api_agent_stream(q: str, session: str | None = None):
    async def gen():
        async for ev in A.ask_stream(rm, q, session):
            yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
