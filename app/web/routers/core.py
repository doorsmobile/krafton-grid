from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse

from ... import config
from .. import nav
from ..data import collector_state, hub, rm

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
def healthz():
    m = rm.meta() or {}
    age = round(time.time() - m["published_at"], 1) if m else None
    cs = collector_state()
    return {"ok": bool(m) and age is not None and age < 15, "release": config.RELEASE_NAME, "port": config.APP_PORT,
            "store": rm.store.mode, "collector": m.get("owner"), "tick": m.get("tick"), "tick_ms": m.get("tick_ms"),
            "build_ms": m.get("build_ms"), "data_age_s": age, "sse_clients": len(hub.clients),
            "collector_status": cs.get("status"), "collector_error": cs.get("last_error"), "store_note": cs.get("store_note")}


@router.get("/api/live", tags=["core"], summary="Current live snapshot (facility · IT · cloud · cost · alerts) — from Redis")
def api_live():
    return rm.live()


@router.get("/api/meta", tags=["core"], summary="Collector heartbeat: tick, publish cost, bytes published, store mode")
def api_meta():
    return rm.meta() or {}


@router.get("/api/stream", tags=["core"], summary="Server-Sent Events: the live snapshot each time the collector publishes")
async def api_stream(request: Request):
    loop = asyncio.get_running_loop()
    q = hub.subscribe(loop)
    first = await asyncio.to_thread(rm.store.get, "live")

    async def gen():
        try:
            yield "retry: 3000\n\n"
            if first:
                yield f"event: live\ndata: {first.decode()}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"event: live\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            hub.unsubscribe(loop, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/api/series/{metric}", tags=["core"], summary="Time series for one metric column (Highcharts [[ms, v]]) — from Redis")
def api_series(metric: str, col: int = 0, cols: str | None = None, label: str | None = None, value: str | None = None,
               minutes: float | None = Query(None, ge=1, le=1440), points: int = Query(600, ge=10, le=3000)):
    tsdb = rm.tsdb
    m = tsdb.metrics.get(metric)
    if m is None:
        raise HTTPException(404, f"unknown metric {metric}")
    secs = minutes * 60 if minutes else None
    if label and value is not None:
        c = m.column(**{label: value})
        if c is None:
            raise HTTPException(404, f"no series {label}={value}")
        col = c
    if cols:
        idx = [int(x) for x in cols.split(",") if x.strip().isdigit() and int(x) < m.width][:40]
        return {"metric": metric, "unit": m.unit, "labels": [m.labels[i] for i in idx],
                "series": tsdb.series_multi(metric, idx, secs, points)}
    if col >= m.width:
        raise HTTPException(404, "column out of range")
    return {"metric": metric, "unit": m.unit, "help": m.help, "labels": m.labels[col],
            "points": tsdb.series(metric, col, secs, points)}


@router.get("/api/search", tags=["core"], summary="Command palette search: pages, racks, nodes, GPUs, devices, alerts, scenarios")
def api_search(q: str = ""):
    return {"q": q, "results": rm.search(q, nav.flat_pages())}


@router.get("/api/catalog", tags=["developers"], summary="Every operator page mapped to its JSON API")
def api_catalog(request: Request):
    routes = []
    for r in iter_routes(request.app.routes):
        methods = sorted(getattr(r, "methods", []) or [])
        path = getattr(r, "path", "")
        if path.startswith("/api/") or path in ("/openapi.json", "/platform/requirements.md"):
            routes.append({"path": path, "methods": [m for m in methods if m not in ("HEAD", "OPTIONS")],
                           "summary": getattr(r, "summary", None) or (getattr(r, "endpoint", None).__doc__ or "").strip().split("\n")[0],
                           "tags": getattr(r, "tags", [])})
    return {"release": config.RELEASE_NAME, "pages": nav.catalog(), "apis": sorted(routes, key=lambda x: x["path"])}


def iter_routes(routes):
    """Flatten app routes; FastAPI ≥0.142 keeps included routers nested."""
    for r in routes:
        orig = getattr(r, "original_router", None)
        if orig is not None:
            yield from iter_routes(orig.routes)
        else:
            yield r


# ------------------------------------------------ legacy paths (v1.0 · cursor spec)
LEGACY = {
    "/it/gpu-fleet": "/gpu-fleet", "/it/storage": "/storage", "/it/network": "/network", "/it/kubernetes": "/kubernetes",
    "/operations/inventory": "/inventory", "/operations/rack-view": "/rack-view", "/operations/alerts": "/alerts",
    "/power": "/facility/power", "/cooling": "/facility/cooling", "/capacity": "/facility/capacity",
    "/tech-spec": "/platform/tech-spec", "/vendors": "/platform/vendors", "/simulation": "/platform/simulation",
    "/requirements": "/platform/requirements", "/racks": "/rack-view", "/network/topology": "/network",
    "/fractos": "/gpu-platform", "/fractos/partition": "/gpu-platform/workloads?tab=partition",
    "/fractos/jobs": "/gpu-platform/workloads?tab=jobs", "/fractos/rcs": "/gpu-platform/workloads?tab=rcs",
    "/fractos/images": "/gpu-platform/workloads?tab=images", "/fractos/projects": "/gpu-platform/ops?tab=projects",
    "/fractos/nodes": "/gpu-platform/ops?tab=nodes", "/fractos/monitor": "/gpu-platform/ops?tab=monitor",
    "/fractos/ecosystem": "/gpu-platform/ops?tab=ecosystem", "/fractos/reports": "/gpu-platform/ops?tab=reports",
}


def _redirect_to(target: str):
    def handler():
        return RedirectResponse(target, status_code=308)
    return handler


for _src, _dst in LEGACY.items():
    router.add_api_route(_src, _redirect_to(_dst), methods=["GET"], include_in_schema=False)
