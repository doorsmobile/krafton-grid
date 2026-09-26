from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.sim import engine
from app.web.deps import page_ctx, templates

router = APIRouter(tags=["cost"])

@router.get("/cost", response_class=HTMLResponse)
async def cost_summary(request: Request):
    cost = engine.get_cost_bundle()
    return templates.TemplateResponse(
        request,
        "cost_summary.html",
        page_ctx(
            "cost-summary",
            dc=cost["dc"],
            cloud=cost["cloud"],
            trends=cost["trends"],
            cost_live=cost["live"],
        ),
    )



@router.get("/cost/dc", response_class=HTMLResponse)
async def cost_dc(request: Request):
    cost = engine.get_cost_bundle()
    return templates.TemplateResponse(
        request,
        "cost_dc.html",
        page_ctx(
            "cost-dc",
            cost=cost["dc"],
            trends=cost["trends"],
            cost_live=cost["live"],
        ),
    )



@router.get("/cost/cloud", response_class=HTMLResponse)
async def cost_cloud(request: Request):
    cost = engine.get_cost_bundle()
    return templates.TemplateResponse(
        request,
        "cost_cloud.html",
        page_ctx(
            "cost-cloud",
            cost=cost["cloud"],
            trends=cost["trends"],
            cost_live=cost["live"],
        ),
    )


