from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.sim import engine

router = APIRouter(prefix="/api", tags=["api-it"])


@router.get("/storage")
async def api_storage_overview():
    return engine.get_storage_overview()


@router.get("/storage/toptalkers")
async def api_storage_toptalkers(limit: int = 25, window: int = 15):
    return engine.get_storage_toptalkers(limit=limit, window_minutes=window)


@router.get("/storage/cluster/{cluster_id}")
async def api_storage_cluster(cluster_id: str):
    detail = engine.get_storage_cluster_detail(cluster_id)
    if not detail:
        return JSONResponse({"error": "cluster not found"}, status_code=404)
    return detail


@router.get("/kubernetes")
async def api_k8s_overview():
    return engine.get_k8s_overview()


@router.get("/kubernetes/node/{node_id}")
async def api_k8s_node(node_id: str):
    detail = engine.get_k8s_node_detail(node_id)
    if not detail:
        return JSONResponse({"error": "node not found"}, status_code=404)
    return detail


@router.get("/gpu-fleet")
async def api_gpu_overview():
    return engine.get_gpu_overview()


@router.get("/gpu-fleet/pod/{pod_id}")
async def api_gpu_pod(pod_id: str):
    detail = engine.get_gpu_pod_detail(pod_id)
    if not detail:
        return JSONResponse({"error": "pod not found"}, status_code=404)
    return detail


@router.get("/gpu-fleet/node/{node_id}")
async def api_gpu_node(node_id: str):
    detail = engine.get_gpu_node_detail(node_id)
    if not detail:
        return JSONResponse({"error": "node not found"}, status_code=404)
    return detail


@router.get("/gpu-fleet/device/{device_id}")
async def api_gpu_device(device_id: str):
    detail = engine.get_gpu_device_detail(device_id)
    if not detail:
        return JSONResponse({"error": "device not found"}, status_code=404)
    return detail
