from fastapi import APIRouter, Body, Request

from ..data import need, rm
from ..templating import render

router = APIRouter()


@router.get("/gpu-platform", include_in_schema=False)
def page_overview(request: Request):
    return render(request, "gpu_platform/overview.html", "GPU Platform", rm.view("gpu_platform"))


@router.get("/api/gpu-platform", tags=["gpu-platform"], summary="GPU Platform overview: console, projects, notices, LLM catalog")
def api_overview():
    return rm.view("gpu_platform")


@router.get("/api/fractos", tags=["gpu-platform"], summary="Legacy alias of /api/gpu-platform", include_in_schema=False)
def api_fractos():
    return rm.view("gpu_platform")


@router.get("/gpu-platform/workloads", include_in_schema=False)
def page_workloads(request: Request):
    return render(request, "gpu_platform/workloads.html", "Workloads", rm.view("workloads"),
                  tab=request.query_params.get("tab", "jobs"))


@router.get("/api/gpu-platform/workloads", tags=["gpu-platform"], summary="Jobs & schedule, MIG partitioning, RCS sessions, images")
def api_workloads():
    return rm.view("workloads")


@router.get("/gpu-platform/ops", include_in_schema=False)
def page_ops(request: Request):
    return render(request, "gpu_platform/ops.html", "Ops", rm.view("gpu_ops"), tab=request.query_params.get("tab", "projects"))


@router.get("/api/gpu-platform/ops", tags=["gpu-platform"], summary="Projects/quota/RBAC, nodes, resource monitor, ecosystem, usage reports")
def api_ops():
    return rm.view("gpu_ops")


@router.post("/api/gpu-platform/jobs", tags=["gpu-platform"], summary="Submit a job (one-click notebook, multi-node training, batch eval/data)")
def api_submit(payload: dict = Body(...)):
    p = payload or {}
    return rm.cmd("gpu.job.submit", project=p.get("project", "research-sandbox"), profile=p.get("profile", "finetune"),
                  size=p.get("size", 8), name=p.get("name"), user=p.get("user"))
