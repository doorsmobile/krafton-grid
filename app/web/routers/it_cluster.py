from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import REDIS_KEY_PREFIX
from app.sim import engine
from app.web.deps import page_ctx, templates

router = APIRouter(tags=["it-cluster"])


# ── Storage ──────────────────────────────────────────────────────────────


@router.get("/storage", response_class=HTMLResponse)
async def storage_overview(request: Request):
    data = engine.get_storage_overview()
    it = engine.get_it_bundle()
    return templates.TemplateResponse(
        request,
        "storage.html",
        page_ctx(
            "storage",
            clusters=data["clusters"],
            talkers=data["talkers"],
            window_minutes=data["window_minutes"],
            totals=data["totals"],
            collector=data.get("collector") or {},
            summary=it["summary"],
            it_live=it["live"],
        ),
    )


@router.get("/storage/toptalkers", response_class=HTMLResponse)
async def storage_toptalkers_page(request: Request):
    data = engine.get_storage_toptalkers(limit=40)
    return templates.TemplateResponse(
        request,
        "storage_toptalkers.html",
        page_ctx(
            "storage",
            talkers=data["talkers"],
            window_minutes=data["window_minutes"],
            collector=data.get("collector") or {},
        ),
    )


@router.get("/storage/cluster/{cluster_id}", response_class=HTMLResponse)
async def storage_cluster_page(request: Request, cluster_id: str):
    detail = engine.get_storage_cluster_detail(cluster_id)
    if not detail:
        return RedirectResponse(url="/storage", status_code=302)
    return templates.TemplateResponse(
        request,
        "storage_cluster.html",
        page_ctx(
            "storage",
            detail=detail,
            cluster=detail["cluster"],
            volumes=detail["volumes"],
            totals=detail["totals"],
            series_json=json.dumps(detail.get("series") or {}),
            collector=engine.redis.hgetall(f"{REDIS_KEY_PREFIX}:st:collector"),
        ),
    )


# ── Kubernetes ───────────────────────────────────────────────────────────


@router.get("/kubernetes", response_class=HTMLResponse)
async def kubernetes_overview(request: Request):
    data = engine.get_k8s_overview()
    it = engine.get_it_bundle()
    return templates.TemplateResponse(
        request,
        "kubernetes.html",
        page_ctx(
            "kubernetes",
            nodes=data["nodes"],
            talkers=data["talkers"],
            k8s_summary=data["summary"],
            summary=it["summary"],
            it_live=it["live"],
        ),
    )


@router.get("/kubernetes/node/{node_id}", response_class=HTMLResponse)
async def kubernetes_node_page(request: Request, node_id: str):
    detail = engine.get_k8s_node_detail(node_id)
    if not detail:
        return RedirectResponse(url="/kubernetes", status_code=302)
    return templates.TemplateResponse(
        request,
        "kubernetes_node.html",
        page_ctx(
            "kubernetes",
            node=detail["node"],
            metrics=detail["metrics"],
            pods=detail["pods"],
            series_json=json.dumps(detail.get("series") or []),
        ),
    )


# ── GPU Fleet ────────────────────────────────────────────────────────────


@router.get("/gpu-fleet", response_class=HTMLResponse)
async def gpu_fleet_overview(request: Request):
    data = engine.get_gpu_overview()
    it = engine.get_it_bundle()
    return templates.TemplateResponse(
        request,
        "gpu_fleet.html",
        page_ctx(
            "gpu-fleet",
            pods=data["pods"],
            talkers=data["talkers"],
            slurm_queue=data["slurm_queue"],
            slurm_nodes=data["slurm_nodes"],
            monitoring=data["monitoring"],
            gpu_summary=data["summary"],
            summary=it["summary"],
            it_live=it["live"],
        ),
    )


@router.get("/gpu-fleet/pod/{pod_id}", response_class=HTMLResponse)
async def gpu_pod_page(request: Request, pod_id: str):
    detail = engine.get_gpu_pod_detail(pod_id)
    if not detail:
        return RedirectResponse(url="/gpu-fleet", status_code=302)
    return templates.TemplateResponse(
        request,
        "gpu_pod.html",
        page_ctx(
            "gpu-fleet",
            pod=detail["pod"],
            metrics=detail["metrics"],
            nodes=detail["nodes"],
            series_json=json.dumps(detail.get("series") or []),
        ),
    )


@router.get("/gpu-fleet/node/{node_id}", response_class=HTMLResponse)
async def gpu_node_page(request: Request, node_id: str):
    detail = engine.get_gpu_node_detail(node_id)
    if not detail:
        return RedirectResponse(url="/gpu-fleet", status_code=302)
    return templates.TemplateResponse(
        request,
        "gpu_node.html",
        page_ctx(
            "gpu-fleet",
            node=detail["node"],
            host=detail.get("host"),
            devices=detail.get("devices") or [],
            processes=detail.get("processes") or [],
            queue=detail["queue"],
        ),
    )


@router.get("/gpu-fleet/device/{device_id}", response_class=HTMLResponse)
async def gpu_device_page(request: Request, device_id: str):
    detail = engine.get_gpu_device_detail(device_id)
    if not detail:
        return RedirectResponse(url="/gpu-fleet", status_code=302)
    return templates.TemplateResponse(
        request,
        "gpu_device.html",
        page_ctx(
            "gpu-fleet",
            device=detail["device"],
            host_devices=detail["host_devices"],
            processes=detail["processes"],
            pods=detail["pods"],
            recommendations=detail["recommendations"],
            series_json=json.dumps(detail["series"]),
        ),
    )
