"""Operator pages — Observability hub (CoreWeave Observe–inspired)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.sim import engine
from app.sim.observability import (
    get_alert_config,
    get_alert_deliveries,
    get_integrations_bundle,
    get_observability_overview,
    get_page_api_catalog,
    get_relay_bundle,
    get_resource_usage,
    run_logql,
    run_promql,
)
from app.web.deps import page_ctx, templates

router = APIRouter(tags=["observability"])


@router.get("/observability", response_class=HTMLResponse)
async def observability_hub(request: Request):
    data = get_observability_overview(engine.get_live())
    return templates.TemplateResponse(
        request,
        "observability.html",
        page_ctx("o11y-overview", o11y=data),
    )


@router.get("/observability/explore", response_class=HTMLResponse)
async def observability_explore(request: Request):
    metrics = run_promql(engine, "kg_gpu_util_pct", limit=40)
    logs = run_logql(engine, '{job="krafton-grid"}', limit=20)
    return templates.TemplateResponse(
        request,
        "observability_explore.html",
        page_ctx(
            "o11y-explore",
            metrics=metrics,
            logs=logs,
            events=engine.get_alerts(12),
        ),
    )


@router.get("/observability/metrics", response_class=HTMLResponse)
async def observability_metrics(request: Request):
    sample = run_promql(engine, "kg_it_load_mw", limit=60)
    return templates.TemplateResponse(
        request,
        "observability_metrics.html",
        page_ctx("o11y-metrics", sample=sample),
    )


@router.get("/observability/logs", response_class=HTMLResponse)
async def observability_logs(request: Request):
    sample = run_logql(engine, '{job="krafton-grid"}', limit=40)
    return templates.TemplateResponse(
        request,
        "observability_logs.html",
        page_ctx("o11y-logs", sample=sample),
    )


@router.get("/observability/telemetry-relay", response_class=HTMLResponse)
async def observability_relay(request: Request):
    data = get_relay_bundle(engine.redis, engine.get_live())
    return templates.TemplateResponse(
        request,
        "observability_relay.html",
        page_ctx("o11y-relay", relay=data),
    )


@router.get("/observability/resource-usage", response_class=HTMLResponse)
async def observability_usage(request: Request):
    data = get_resource_usage(engine)
    return templates.TemplateResponse(
        request,
        "observability_usage.html",
        page_ctx("o11y-usage", usage=data),
    )


@router.get("/observability/mission-control", response_class=HTMLResponse)
async def observability_agent(request: Request):
    return templates.TemplateResponse(
        request,
        "observability_agent.html",
        page_ctx("o11y-agent"),
    )


@router.get("/developers/api", response_class=HTMLResponse)
async def developers_api(request: Request):
    catalog = get_page_api_catalog()
    return templates.TemplateResponse(
        request,
        "developers_api.html",
        page_ctx("dev-api", catalog=catalog),
    )


@router.get("/alerts/integrations", response_class=HTMLResponse)
async def alerts_integrations(request: Request):
    data = get_integrations_bundle(engine.redis)
    deliveries = get_alert_deliveries(engine.redis, limit=30)
    return templates.TemplateResponse(
        request,
        "alerts_integrations.html",
        page_ctx("alerts-integrations", integrations=data, deliveries=deliveries),
    )


@router.get("/alerts/config", response_class=HTMLResponse)
async def alerts_config(request: Request):
    data = get_alert_config(engine.redis)
    return templates.TemplateResponse(
        request,
        "alerts_config.html",
        page_ctx("alerts-config", config=data),
    )
