from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.sim import engine

router = APIRouter(prefix="/api", tags=["api-sim"])

@router.get("/vendors")
async def api_vendors():
    vendors = engine.get_json("vendors") or []
    live = engine.get_live()
    health = live.get("vendor_health", {})
    for v in vendors:
        v["runtime_status"] = health.get(v["id"], v.get("status"))
    return vendors



@router.post("/sim/mode")
async def api_set_mode(payload: dict[str, str]):
    mode = payload.get("mode", "normal")
    try:
        engine.set_mode(mode)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True, "mode": mode, "live": engine.tick_once()}



@router.post("/sim/alert")
async def api_inject_alert(payload: dict[str, str]):
    severity = payload.get("severity", "warning")
    message = payload.get("message", "Operator-injected simulation event")
    alert = engine.inject_alert(severity, message)
    return {"ok": True, "alert": alert}



@router.get("/sim/dump")
async def api_dump():
    return engine.dump_simulation_bundle()



@router.get("/sim/export.json")
async def api_export():
    data = json.dumps(engine.dump_simulation_bundle(), indent=2)
    return StreamingResponse(
        iter([data]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=aidc100-dcim-sim.json"},
    )



@router.get("/vendor/{vendor_id}/sample")
async def api_vendor_sample(vendor_id: str):
    """Simulated vendor API proxy response."""
    vendors = engine.get_json("vendors") or []
    vendor = next((v for v in vendors if v["id"] == vendor_id), None)
    if not vendor:
        return JSONResponse({"error": "vendor not found"}, status_code=404)
    live = engine.get_live()
    metric_key = vendor["api"]["sample_metric"]
    samples = {
        "ups.output.power_kw": round(live["it_load_mw"] * 1000 * 0.34, 1),
        "cdu.loop.supply_temp_c": live["liquid_loop_temp_c"],
        "busway.section.load_kw": round(live["it_load_mw"] * 1000 / 48, 1),
        "mv.feeder.active_power_mw": round(live["total_mw"] / 2, 3),
        "bms.ahu.fan_speed_pct": round(live["cooling_load_pct"] * 0.9, 1),
        "crac.return_air_c": round(live["return_temp_c"] - 4.2, 2),
        "dlc.rack.flow_lpm": round(18 + live["gpu_utilization_pct"] / 10, 1),
        "rear_door.delta_t_c": round(live["return_temp_c"] - live["liquid_loop_temp_c"], 2),
        "capacity.rack.available_kw": round(120 - live["gpu_utilization_pct"] * 0.6, 1),
        "env.cabinet.temp_c": round(24.5 + live["gpu_utilization_pct"] / 40, 2),
        "gpu.sm_utilization_pct": live.get("gpu_utilization_pct"),
        "switch.port.utilization_pct": live.get("eth_fabric_util_pct"),
        "server.power_watts": round(2800 + live.get("k8s_cpu_util_pct", 50) * 12, 0),
        "storage.used_pb": live.get("storage_used_pb"),
        "cloud.nhn.gpu_util_pct": live.get("nhn_gpu_util_pct"),
        "cloud.aws.gpu_util_pct": live.get("aws_gpu_util_pct"),
        "cloud.gcp.storage_used_tb": live.get("gcp_storage_used_tb"),
    }
    return {
        "vendor": vendor["name"],
        "endpoint": f"{vendor['api']['base_url']}{vendor['api']['endpoints'][0]}",
        "protocol": vendor["api"]["protocol"],
        "auth": vendor["api"]["auth"],
        "status": live.get("vendor_health", {}).get(vendor_id, vendor["status"]),
        "latency_ms": vendor["latency_ms"],
        "metric": metric_key,
        "value": samples.get(metric_key, None),
        "ts": live["ts"],
        "correlation_id": f"sim-{live['tick']}-{vendor_id}",
    }

