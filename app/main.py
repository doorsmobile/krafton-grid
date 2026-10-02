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
from .store import get_store, memory_store
from .web.data import NotReady, collector_state, hub, rm, runtime as state
from .web.routers import (auth, core, cost, cloud, developers, facility, gpu_platform, it, main_campus,
                          observability, operations, platform)
from .web.templating import render

log = logging.getLogger("grid.web")


def _store_full(collector, mem: dict):
    """The embedded collector hit Redis maxmemory. In auto mode keep serving from the in-memory store."""
    if config.GRID_STORE != "auto" or collector.role != "embedded":
        return None
    state["store_note"] = (f"Redis is full (used {mem.get('used_mb')} MB of maxmemory {mem.get('max_mb')} MB, "
                           f"policy {mem.get('policy')}) — serving from the in-memory store; give Redis ≥ 64 MB to use it")
    log.error(state["store_note"])
    mem_store = memory_store()
    rm.bind(mem_store)
    hub.start(mem_store)
    return mem_store


def _start_embedded(store) -> None:
    from .collector import Collector
    state["collector"] = Collector(store, role="embedded", on_store_full=_store_full).start()
    log.warning("no external collector — running one inside the web process (store: %s)", store.mode)


async def _collector_present(store, wait_s: float) -> bool:
    end = time.time() + wait_s
    while time.time() < end:
        try:
            if await asyncio.to_thread(store.lease_holder):
                return True
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(0.25)
    return False


async def _watchdog() -> None:
    """auto mode: when no collector has held the lease for 15 s (rolling deploy, crashed collector) start one here.

    Requiring three consecutive free observations avoids stealing the role from a healthy collector whose
    lease merely expired while the machine was asleep — it renews within 2 s of waking.
    """
    free = 0
    while True:
        await asyncio.sleep(5)
        try:
            c = state["collector"]
            if c is not None and c.status == "failed":
                log.warning("embedded collector failed (%s) — restarting in 10 s", c.last_error)
                c.stop()
                state["collector"] = None
                await asyncio.sleep(10)
            elif c is not None and c.status == "stopped":      # lost the lease to another collector
                state["collector"] = None
            if state["collector"] is None:
                free = 0 if await asyncio.to_thread(rm.store.lease_holder) else free + 1
                if free >= 3:
                    log.warning("collector lease free for 15 s — starting a collector in this process")
                    free = 0
                    _start_embedded(rm.store)
        except Exception as e:  # noqa: BLE001
            log.warning("watchdog: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    store = get_store()
    rm.bind(store)
    hub.start(store)
    mode = config.GRID_COLLECTOR
    if mode == "embedded" or (mode == "auto" and (store.mode == "memory" or not await _collector_present(store, 3.0))):
        _start_embedded(store)
    dog = asyncio.create_task(_watchdog()) if mode == "auto" and store.mode == "redis" else None
    yield
    if dog:
        dog.cancel()
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


WARMING = """<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="3"><title>Starting · Krafton Grid</title>
<body style="background:#000;color:#c9ccd3;font:14px/1.6 -apple-system,Inter,sans-serif;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center;max-width:720px;padding:0 16px"><div style="font-size:18px;color:#fff;font-weight:600">Collector is publishing the first read models…</div>
<div>{detail} · this page retries every 3 s</div>
<div style="margin-top:14px;font-size:12.5px;color:#8b8f98">collector: <b style="color:#c9ccd3">{status}</b> · up {uptime}s{error}</div></div></body>"""


@app.exception_handler(NotReady)
async def not_ready(request: Request, exc: NotReady):
    cs = collector_state()
    if request.url.path.startswith("/api/") or "text/html" not in request.headers.get("accept", ""):
        return JSONResponse({"error": "warming up", "detail": str(exc), "collector": cs, "status": 503},
                            status_code=503, headers={"retry-after": "3"})
    err = f'<br><span style="color:#fbbf24">last error: {cs["last_error"]}</span>' if cs.get("last_error") else ""
    html = WARMING.format(detail=str(exc), status=cs.get("status"), uptime=round(time.time() - state["started"]), error=err)
    return HTMLResponse(html, status_code=503, headers={"retry-after": "3"})


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/") or "text/html" not in request.headers.get("accept", ""):
        return JSONResponse({"error": exc.detail or "error", "status": exc.status_code}, status_code=exc.status_code)
    return render(request, "error.html", f"{exc.status_code}", {"status": exc.status_code, "detail": exc.detail},
                  status_code=exc.status_code)
