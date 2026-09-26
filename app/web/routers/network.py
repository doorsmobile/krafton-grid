from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.sim import engine
from app.web.deps import page_ctx, templates

router = APIRouter(tags=["network"])


@router.get("/network", response_class=HTMLResponse)
async def network_overview(request: Request):
    uplinks = engine.get_network_uplinks(limit=12)
    talkers = engine.get_network_toptalkers(limit=12, window_minutes=15)
    topo = engine.get_network_topology()
    inventory = engine.get_network_inventory(q="")
    it = engine.get_it_bundle()
    return templates.TemplateResponse(
        request,
        "network.html",
        page_ctx(
            "network",
            uplinks=uplinks["uplinks"][:8],
            uplink_totals=uplinks["totals"],
            talkers=talkers["talkers"][:8],
            window_minutes=talkers["window_minutes"],
            topology=topo,
            devices=inventory["devices"][:12],
            device_total=inventory["total"],
            collector=uplinks.get("collector") or {},
            net_meta=uplinks.get("meta") or {},
            it_live=it["live"],
            summary=it["summary"],
        ),
    )


@router.get("/network/uplinks", response_class=HTMLResponse)
async def network_uplinks_page(request: Request):
    data = engine.get_network_uplinks(limit=40)
    return templates.TemplateResponse(
        request,
        "network_uplink.html",
        page_ctx(
            "network",
            uplinks=data["uplinks"],
            totals=data["totals"],
            collector=data["collector"],
            net_meta=data["meta"],
            it_live=engine.get_it_bundle()["live"],
        ),
    )


@router.get("/network/toptalkers", response_class=HTMLResponse)
async def network_toptalkers_page(request: Request):
    data = engine.get_network_toptalkers()
    return templates.TemplateResponse(
        request,
        "network_toptalkers.html",
        page_ctx(
            "network",
            talkers=data["talkers"],
            window_minutes=data["window_minutes"],
            collector=data["collector"],
            net_meta=data["meta"],
        ),
    )


@router.get("/network/inventory", response_class=HTMLResponse)
async def network_inventory_page(request: Request, q: str = ""):
    data = engine.get_network_inventory(q=q)
    return templates.TemplateResponse(
        request,
        "network_inventory.html",
        page_ctx(
            "network",
            devices=data["devices"],
            query=data["query"],
            total=data["total"],
            net_meta=data["meta"],
        ),
    )


@router.get("/network/topology")
async def network_topology_redirect():
    return RedirectResponse(url="/network", status_code=302)


@router.get("/network/device/{device_id}", response_class=HTMLResponse)
async def network_device_page(request: Request, device_id: str):
    detail = engine.get_network_device(device_id)
    if not detail:
        return RedirectResponse(url="/network", status_code=302)
    return templates.TemplateResponse(
        request,
        "network_device.html",
        page_ctx(
            "network",
            detail=detail,
            device=detail["device"],
            interfaces=detail["interfaces"],
            series_json=json.dumps(detail.get("series") or {}),
            collector=detail.get("collector") or {},
        ),
    )
