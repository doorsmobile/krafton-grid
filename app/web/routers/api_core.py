from __future__ import annotations

from fastapi import APIRouter

from app.sim import engine

router = APIRouter(prefix="/api", tags=["api"])

@router.get("/live")
async def api_live():
    return engine.get_live()



@router.get("/history")
async def api_history(limit: int = 60):
    return engine.get_history(limit)



@router.get("/series/{metric}")
async def api_series(metric: str, limit: int = 60):
    return engine.get_series(metric, limit)



@router.get("/alerts")
async def api_alerts(limit: int = 30):
    return engine.get_alerts(limit)



@router.get("/halls")
async def api_halls():
    halls = engine.get_json("halls") or []
    loads = engine.get_live().get("hall_loads", {})
    for h in halls:
        h["live_mw"] = loads.get(h["id"], 0)
        h["util_pct"] = round((h["live_mw"] / h["design_mw"]) * 100, 1) if h["design_mw"] else 0
    return halls



@router.get("/modules")
async def api_modules():
    return engine.get_modules()



@router.get("/it")
async def api_it():
    return engine.get_it_bundle()



@router.get("/cloud")
async def api_cloud():
    return engine.get_cloud_overview()


@router.get("/facility")
async def api_facility():
    return engine.get_facility_overview()



@router.get("/cost")
async def api_cost():
    return engine.get_cost_bundle()



@router.get("/fractos")

@router.get("/gpu-platform")
async def api_gpu_platform():
    return engine.get_fractos_bundle()



@router.get("/site")
async def api_site():
    return engine.get_json("site")


