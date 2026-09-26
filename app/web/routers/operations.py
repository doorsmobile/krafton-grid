from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.sim import engine
from app.web.deps import page_ctx, templates

router = APIRouter(tags=["operations"])

@router.get("/inventory", response_class=HTMLResponse)
async def inventory(request: Request):
    it = engine.get_it_bundle()
    return templates.TemplateResponse(
        request,
        "inventory.html",
        page_ctx("inventory", summary=it["summary"], assets=it["inventory"]),
    )



@router.get("/rack-view", response_class=HTMLResponse)
async def rack_view(request: Request):
    it = engine.get_it_bundle()
    return templates.TemplateResponse(
        request,
        "rack_view.html",
        page_ctx("rack-view", racks=it["rack_map"], summary=it["summary"]),
    )



@router.get("/racks", response_class=HTMLResponse)
async def racks_redirect():
    return RedirectResponse(url="/rack-view", status_code=302)



@router.get("/alerts", response_class=HTMLResponse)
async def alerts(request: Request):
    from app.sim.observability import get_alert_deliveries, get_integrations_bundle

    integrations = get_integrations_bundle(engine.redis)
    slack_dests = [
        d
        for d in integrations.get("destinations") or []
        if d.get("enabled") and "slack" in (d.get("type") or "")
    ]
    return templates.TemplateResponse(
        request,
        "alerts.html",
        page_ctx(
            "alerts",
            alerts=engine.get_alerts(40),
            deliveries=get_alert_deliveries(engine.redis, limit=20),
            slack_dests=slack_dests,
        ),
    )


