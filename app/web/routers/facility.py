from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.sim import engine
from app.web.deps import page_ctx, templates

router = APIRouter(tags=["facility"])


@router.get("/facility", response_class=HTMLResponse)
async def facility_overview(request: Request):
    data = engine.get_facility_overview()
    return templates.TemplateResponse(
        request,
        "facility.html",
        page_ctx(
            "facility-overview",
            power=data["power"],
            cooling=data["cooling"],
            halls=data["halls"],
            modules=data["modules"],
            power_talkers=data["power_talkers"],
            cooling_talkers=data["cooling_talkers"],
            hall_talkers=data["hall_talkers"],
            fac_live=data["live"],
        ),
    )


@router.get("/power", response_class=HTMLResponse)
async def power_page(request: Request):
    data = engine.get_facility_overview()
    return templates.TemplateResponse(
        request,
        "power.html",
        page_ctx(
            "power",
            chain=data["power"],
            fac_live=data["live"],
        ),
    )


@router.get("/cooling", response_class=HTMLResponse)
async def cooling_page(request: Request):
    data = engine.get_facility_overview()
    return templates.TemplateResponse(
        request,
        "cooling.html",
        page_ctx(
            "cooling",
            chain=data["cooling"],
            fac_live=data["live"],
        ),
    )


@router.get("/capacity", response_class=HTMLResponse)
async def capacity_page(request: Request):
    data = engine.get_facility_overview()
    return templates.TemplateResponse(
        request,
        "capacity.html",
        page_ctx(
            "capacity",
            halls=data["halls"],
            modules=data["modules"],
            fac_live=data["live"],
        ),
    )


@router.get("/facility/power/stage/{stage_id}", response_class=HTMLResponse)
async def power_stage_page(request: Request, stage_id: str):
    detail = engine.get_power_stage_detail(stage_id)
    if not detail:
        return RedirectResponse(url="/facility", status_code=302)
    return templates.TemplateResponse(
        request,
        "facility_power_stage.html",
        page_ctx(
            "power",
            stage=detail["stage"],
            chain=detail["chain"],
            series_json=json.dumps(detail["series"]),
        ),
    )


@router.get("/facility/cooling/stage/{stage_id}", response_class=HTMLResponse)
async def cooling_stage_page(request: Request, stage_id: str):
    detail = engine.get_cooling_stage_detail(stage_id)
    if not detail:
        return RedirectResponse(url="/facility", status_code=302)
    return templates.TemplateResponse(
        request,
        "facility_cooling_stage.html",
        page_ctx(
            "cooling",
            stage=detail["stage"],
            chain=detail["chain"],
            series_json=json.dumps(detail["series"]),
        ),
    )


@router.get("/facility/hall/{hall_id}", response_class=HTMLResponse)
async def hall_page(request: Request, hall_id: str):
    detail = engine.get_hall_detail(hall_id)
    if not detail:
        return RedirectResponse(url="/facility", status_code=302)
    return templates.TemplateResponse(
        request,
        "facility_hall.html",
        page_ctx(
            "capacity",
            hall=detail["hall"],
            halls=detail["halls"],
            modules=detail["modules"],
            series_json=json.dumps(detail["series"]),
        ),
    )
