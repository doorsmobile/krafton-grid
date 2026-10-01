"""Web tier. Reads read models from the store (Redis) and sends commands to the collector.

It never imports the simulator's state. If no collector is running (``GRID_COLLECTOR=auto``) or the
store is in-process, it starts one in a background thread — the read path stays exactly the same.
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from . import config
from .store import get_store
from .web.data import NotReady, hub, rm
from .web.routers import (auth, core, cost, cloud, developers, facility, gpu_platform, it, main_campus,
                          observability, operations, platform)
from .web.templating import render

log = logging.getLogger("grid.web")
state: dict = {"collector": None}


async def _collector_present(store, wait_s: float) -> bool:
    end = time.time() + wait_s
    while time.time() < end:
        if await asyncio.to_thread(store.lease_holder):
            return True
        await asyncio.sleep(0.25)
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = get_store()
    rm.bind(store)
    hub.start(store)
    mode = config.GRID_COLLECTOR
    embed = mode == "embedded" or (mode == "auto" and (store.mode == "memory" or not await _collector_present(store, 3.0)))
    if embed:
        from .collector import Collector
        state["collector"] = Collector(store, role="embedded").start()
        log.warning("no external collector — running one inside the web process (store: %s)", store.mode)
    yield
    hub.stop()
    if state["collector"]:
        state["collector"].stop()


app = FastAPI(title="Krafton Grid · AIDC DCIM (grid-claude)", version=config.APP_VERSION, lifespan=lifespan,
              description="100 MW AIDC digital twin. Collector → Redis → web: every page and API reads published read models. "
                          "See /developers/api.")

PUBLIC = ("/static/", "/login", "/logout", "/healthz", "/favicon.ico")


@app.middleware("http")
async def gate_and_time(request: Request, call_next):
    t0 = time.perf_counter()
    path = request.url.path
    if config.AUTH_ENABLED and not path.startswith(PUBLIC) and not request.session.get("user"):
        if path.startswith("/api/") and "text/html" not in request.headers.get("accept", ""):
            return JSONResponse({"error": "unauthorized", "login": "/login"}, status_code=401)
        nxt = path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/login?next={quote(nxt, safe='')}", status_code=302)
    resp = await call_next(request)
    if path.startswith("/static/"):
        # vendor files never change and our JS/CSS carry ?v=<release>.<mtime>: no revalidation round-trips on navigation
        immutable = path.startswith("/static/vendor/") or "v" in request.query_params
        resp.headers["cache-control"] = "public, max-age=31536000, immutable" if immutable else "public, max-age=3600"
    resp.headers["x-grid-release"] = config.RELEASE_NAME
    resp.headers["server-timing"] = f"app;dur={(time.perf_counter() - t0) * 1000:.1f}"
    return resp


app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET, same_site="lax", max_age=12 * 3600)
app.mount("/static", StaticFiles(directory=str(config.APP_DIR / "static")), name="static")

for r in (core, main_campus, facility, it, gpu_platform, cloud, observability, operations, developers, platform, cost, auth):
    app.include_router(r.router)


WARMING = """<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="2"><title>Starting · Krafton Grid</title>
<body style="background:#000;color:#c9ccd3;font:14px/1.6 -apple-system,Inter,sans-serif;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center"><div style="font-size:18px;color:#fff;font-weight:600">Collector is publishing the first read models…</div>
<div>{detail} · this page retries every 2 s</div></div></body>"""


@app.exception_handler(NotReady)
async def not_ready(request: Request, exc: NotReady):
    if request.url.path.startswith("/api/") or "text/html" not in request.headers.get("accept", ""):
        return JSONResponse({"error": "warming up", "detail": str(exc), "status": 503}, status_code=503, headers={"retry-after": "2"})
    return HTMLResponse(WARMING.format(detail=str(exc)), status_code=503, headers={"retry-after": "2"})


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/") or "text/html" not in request.headers.get("accept", ""):
        return JSONResponse({"error": exc.detail or "error", "status": exc.status_code}, status_code=exc.status_code)
    return render(request, "error.html", f"{exc.status_code}", {"status": exc.status_code, "detail": exc.detail},
                  status_code=exc.status_code)
