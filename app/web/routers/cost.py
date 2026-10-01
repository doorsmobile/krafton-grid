from fastapi import APIRouter, Body, Request

from ..data import rm
from ..templating import render

router = APIRouter()


@router.get("/cost", include_in_schema=False)
def page_summary(request: Request):
    return render(request, "cost/summary.html", "Cost Summary", rm.view("cost"))


@router.get("/api/cost", tags=["cost"], summary="DC + Cloud: MTD, forecast, MoM, YTD, 12-month trend, unit economics")
def api_summary():
    return rm.view("cost")


@router.get("/cost/dc", include_in_schema=False)
def page_dc(request: Request):
    return render(request, "cost/dc.html", "DC Cost", rm.view("cost_dc"))


@router.get("/api/cost/dc", tags=["cost"], summary="전기요금 · 세금 · 관리비 · 인건비 by month + live TOU billing")
def api_dc():
    return rm.view("cost_dc")


@router.get("/cost/cloud", include_in_schema=False)
def page_cloud(request: Request):
    return render(request, "cost/cloud.html", "Cloud Cost", rm.view("cost_cloud"))


@router.get("/api/cost/cloud", tags=["cost"], summary="AWS · GCP · NHN monthly spend + live burn")
def api_cloud():
    return rm.view("cost_cloud")


@router.get("/cost/budget", include_in_schema=False)
def page_budget(request: Request):
    return render(request, "cost/budget.html", "Budget", rm.view("budget"))


@router.get("/api/cost/budget", tags=["cost"], summary="FY budget vs actual vs forecast per budget item + requests")
def api_budget():
    return rm.view("budget")


@router.get("/api/cost/budget/requests", tags=["cost"], summary="예산 이관/증액/환입 · 예산항목 생성 requests")
def api_requests():
    return rm.view("budget_requests")


@router.post("/api/cost/budget/requests", tags=["cost"], summary="Create a budget request (transfer | increase | refund | new_item)")
def api_request_create(payload: dict = Body(...)):
    return rm.cmd("budget.create", payload=payload or {})


@router.post("/api/cost/budget/requests/{request_id}/{action}", tags=["cost"], summary="Advance a request: approve (next step) or reject")
def api_request_act(request_id: str, action: str):
    return rm.cmd("budget.act", id=request_id, action=action)
