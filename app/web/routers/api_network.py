from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.sim import engine

router = APIRouter(prefix="/api/network", tags=["api-network"])

@router.get("")
async def api_network_bundle():
    return engine.get_network_bundle()



@router.get("/uplinks")
async def api_network_uplinks(limit: int = 40):
    return engine.get_network_uplinks(limit=limit)



@router.get("/toptalkers")
async def api_network_toptalkers(limit: int = 25, window: int = 15):
    return engine.get_network_toptalkers(limit=limit, window_minutes=window)



@router.get("/topology")
async def api_network_topology():
    return engine.get_network_topology()



@router.get("/inventory")
async def api_network_inventory(q: str = ""):
    return engine.get_network_inventory(q=q)



@router.get("/device/{device_id}")
async def api_network_device(device_id: str):
    detail = engine.get_network_device(device_id)
    if not detail:
        return JSONResponse({"error": "device not found"}, status_code=404)
    return detail



@router.get("/iface/{device_id}/{iface_name:path}")
async def api_network_iface_history(device_id: str, iface_name: str, limit: int = 60):
    iface_id = f"{device_id}:{iface_name}"
    return engine.get_iface_history(iface_id, limit=limit)


