"""JSON APIs for Observability + Alerts integrations + Developer catalog."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.sim import engine
from app.sim.observability import (
    ask_mission_control,
    get_alert_config,
    get_alert_deliveries,
    get_integrations_bundle,
    get_observability_overview,
    get_page_api_catalog,
    get_relay_bundle,
    get_resource_usage,
    run_logql,
    run_promql,
    set_alert_routing,
    upsert_destination,
    upsert_relay_destination,
    upsert_relay_pipeline,
)

router = APIRouter(prefix="/api", tags=["api-observability"])


@router.get("/observability")
async def api_observability():
    return get_observability_overview(engine.get_live())


@router.get("/observability/explore")
async def api_explore(limit: int = 40):
    live = engine.get_live()
    metrics = run_promql(engine, "kg_gpu_util_pct", limit=limit)
    logs = run_logql(engine, '{job="krafton-grid"}', limit=min(limit, 20))
    return {
        "live": {
            "ts": live.get("ts"),
            "mode": live.get("mode"),
            "it_load_mw": live.get("it_load_mw"),
            "pue": live.get("pue"),
            "gpu_utilization_pct": live.get("gpu_utilization_pct"),
            "active_alerts": live.get("active_alerts"),
        },
        "metrics_sample": metrics,
        "logs_sample": logs,
        "events": engine.get_alerts(10),
    }


@router.post("/observability/metrics/query")
async def api_metrics_query(payload: dict):
    query = payload.get("query") or "kg_it_load_mw"
    limit = int(payload.get("limit") or 60)
    return run_promql(engine, query, limit=limit)


@router.get("/observability/metrics/query")
async def api_metrics_query_get(query: str = "kg_it_load_mw", limit: int = 60):
    return run_promql(engine, query, limit=limit)


@router.post("/observability/logs/query")
async def api_logs_query(payload: dict):
    query = payload.get("query") or '{job="krafton-grid"}'
    limit = int(payload.get("limit") or 40)
    return run_logql(engine, query, limit=limit)


@router.get("/observability/logs/query")
async def api_logs_query_get(query: str = '{job="krafton-grid"}', limit: int = 40):
    return run_logql(engine, query, limit=limit)


@router.get("/observability/relay")
async def api_relay():
    return get_relay_bundle(engine.redis, engine.get_live())


@router.post("/observability/relay/destinations")
async def api_relay_dest(payload: dict):
    return upsert_relay_destination(engine.redis, payload)


@router.post("/observability/relay/pipelines")
async def api_relay_pipe(payload: dict):
    return upsert_relay_pipeline(engine.redis, payload)


@router.get("/observability/usage")
async def api_usage():
    return get_resource_usage(engine)


@router.post("/observability/agent")
async def api_agent(payload: dict):
    question = payload.get("question") or payload.get("q") or ""
    context_path = payload.get("context_path")
    if not question.strip():
        return JSONResponse({"error": "question required"}, status_code=400)
    return ask_mission_control(engine, question, context_path=context_path)


@router.get("/catalog")
async def api_catalog(section: str | None = None):
    return get_page_api_catalog(section=section)


@router.get("/alerts/integrations")
async def api_alert_integrations():
    return get_integrations_bundle(engine.redis)


@router.post("/alerts/integrations")
async def api_alert_integrations_upsert(payload: dict):
    return upsert_destination(engine.redis, payload)


@router.get("/alerts/config")
async def api_alert_config():
    return get_alert_config(engine.redis)


@router.put("/alerts/config/{alert_id}")
async def api_alert_config_put(alert_id: str, payload: dict):
    routing = payload.get("routing") or payload
    return set_alert_routing(engine.redis, alert_id, routing)


@router.get("/alerts/deliveries")
async def api_alert_deliveries(limit: int = 40):
    return get_alert_deliveries(engine.redis, limit=limit)


# ── Fill page ↔ API gaps (facility / cloud / cost / inventory / racks) ──


@router.get("/facility/power")
async def api_facility_power():
    data = engine.get_facility_overview()
    return {"power": data["power"], "live": data["live"]}


@router.get("/facility/cooling")
async def api_facility_cooling():
    data = engine.get_facility_overview()
    return {"cooling": data["cooling"], "live": data["live"]}


@router.get("/facility/capacity")
async def api_facility_capacity():
    data = engine.get_facility_overview()
    return {"halls": data["halls"], "modules": data["modules"], "live": data["live"]}


@router.get("/facility/power/stage/{stage_id}")
async def api_power_stage(stage_id: str):
    detail = engine.get_power_stage_detail(stage_id)
    if not detail:
        return JSONResponse({"error": "stage not found"}, status_code=404)
    return detail


@router.get("/facility/cooling/stage/{stage_id}")
async def api_cooling_stage(stage_id: str):
    detail = engine.get_cooling_stage_detail(stage_id)
    if not detail:
        return JSONResponse({"error": "stage not found"}, status_code=404)
    return detail


@router.get("/facility/hall/{hall_id}")
async def api_hall(hall_id: str):
    detail = engine.get_hall_detail(hall_id)
    if not detail:
        return JSONResponse({"error": "hall not found"}, status_code=404)
    return detail


@router.get("/cloud/aws")
async def api_cloud_aws():
    data = engine.get_cloud_overview()
    return {"provider": data["aws"], "talkers": data["aws_talkers"], "live": data["live"]}


@router.get("/cloud/gcp")
async def api_cloud_gcp():
    data = engine.get_cloud_overview()
    return {"provider": data["gcp"], "talkers": data["gcp_talkers"], "live": data["live"]}


@router.get("/cloud/nhn")
async def api_cloud_nhn():
    data = engine.get_cloud_overview()
    return {"provider": data["nhn"], "talkers": data["nhn_talkers"], "live": data["live"]}


@router.get("/cloud/aws/instance/{instance_id}")
async def api_aws_instance(instance_id: str):
    detail = engine.get_aws_instance_detail(instance_id)
    if not detail:
        return JSONResponse({"error": "instance not found"}, status_code=404)
    return detail


@router.get("/cloud/nhn/instance/{instance_id}")
async def api_nhn_instance(instance_id: str):
    detail = engine.get_nhn_instance_detail(instance_id)
    if not detail:
        return JSONResponse({"error": "instance not found"}, status_code=404)
    return detail


@router.get("/cloud/gcp/bucket/{bucket_id}")
async def api_gcp_bucket(bucket_id: str):
    detail = engine.get_gcp_bucket_detail(bucket_id)
    if not detail:
        return JSONResponse({"error": "bucket not found"}, status_code=404)
    return detail


@router.get("/cloud/gcp/disk/{disk_id}")
async def api_gcp_disk(disk_id: str):
    detail = engine.get_gcp_disk_detail(disk_id)
    if not detail:
        return JSONResponse({"error": "disk not found"}, status_code=404)
    return detail


@router.get("/cost/dc")
async def api_cost_dc():
    bundle = engine.get_cost_bundle()
    return {"dc": bundle.get("dc"), "monthly": (bundle.get("monthly") or {}).get("dc"), "live": bundle.get("live")}


@router.get("/cost/cloud")
async def api_cost_cloud():
    bundle = engine.get_cost_bundle()
    return {
        "cloud": bundle.get("cloud"),
        "monthly": (bundle.get("monthly") or {}).get("cloud"),
        "live": bundle.get("live"),
    }


@router.get("/inventory")
async def api_inventory():
    it = engine.get_it_bundle()
    return {"summary": it["summary"], "assets": it["inventory"]}


@router.get("/racks")
async def api_racks():
    it = engine.get_it_bundle()
    return {"racks": it["rack_map"], "summary": it["summary"]}
