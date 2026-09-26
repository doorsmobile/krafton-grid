from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.sim import engine
from app.web.deps import page_ctx, templates

router = APIRouter(tags=["gpu-platform"])


def _gpu_platform_page(request: Request, active: str, template: str, **extra: Any):
    fx = engine.get_fractos_bundle()
    return templates.TemplateResponse(
        request,
        template,
        page_ctx(active, fx=fx, fx_live=fx["live"], **extra),
    )


@router.get("/gpu-platform", response_class=HTMLResponse)
async def gpu_platform_overview(request: Request):
    return _gpu_platform_page(request, "gpu-overview", "gpu_overview.html")



@router.get("/gpu-platform/workloads", response_class=HTMLResponse)
async def gpu_platform_workloads(request: Request):
    return _gpu_platform_page(request, "gpu-workloads", "gpu_workloads.html")



@router.get("/gpu-platform/ops", response_class=HTMLResponse)
async def gpu_platform_ops(request: Request):
    return _gpu_platform_page(request, "gpu-ops", "gpu_ops.html")



@router.get("/fractos", response_class=HTMLResponse)

@router.get("/fractos/{path:path}", response_class=HTMLResponse)
async def fractos_legacy_redirect(path: str = ""):
    """Old AI Factory deep links → GPU Platform groups."""
    mapping = {
        "": "/gpu-platform",
        "partition": "/gpu-platform/workloads",
        "jobs": "/gpu-platform/workloads",
        "rcs": "/gpu-platform/workloads",
        "images": "/gpu-platform/workloads",
        "projects": "/gpu-platform/ops",
        "nodes": "/gpu-platform/ops",
        "monitor": "/gpu-platform/ops",
        "ecosystem": "/gpu-platform/ops",
        "reports": "/gpu-platform/ops",
    }
    return RedirectResponse(url=mapping.get(path, "/gpu-platform"), status_code=302)


