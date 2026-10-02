from __future__ import annotations

import json
import time

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .. import config
from . import nav
from ..fmt import f_ago, f_dur, f_krw, f_kst, f_num
from .data import rm

templates = Jinja2Templates(directory=str(config.APP_DIR / "templates"))
env = templates.env


LEVEL = {"ok": "ok", "running": "ok", "online": "ok", "up": "ok", "healthy": "ok", "ready": "ok", "energized": "ok",
         "active": "ok", "alloc": "ok", "mix": "ok", "serving": "ok", "closed": "ok", "completed": "ok", "approved": "ok",
         "idle": "idle", "standby": "idle", "planned": "idle", "registered": "idle", "shutoff": "idle", "draft": "idle",
         "warning": "warn", "warn": "warn", "degraded": "warn", "drain": "warn", "busy": "warn", "starting": "warn",
         "on-battery": "warn", "cooldown": "warn", "maintenance": "warn", "pending": "warn", "watch": "warn",
         "mitigating": "warn", "submitted": "info", "team_lead": "info", "finance": "info", "info": "info",
         "online · genset": "warn", "containercreating": "warn", "scheduled": "info", "on-genset": "warn",
         "critical": "crit", "failed": "crit", "fault": "crit", "tripped": "crit", "down": "crit", "lost": "crit",
         "notready": "crit", "crashloopbackoff": "crit", "open": "crit", "over": "crit", "rejected": "crit", "alert": "crit",
         "error": "crit", "resolved": "ok", "shutting-down": "idle"}


def f_level(status) -> str:
    s = str(status or "").lower()
    if s in ("2n", "n+1"):
        return "ok"
    if s.startswith("n ("):
        return "crit"
    return LEVEL.get(s, "idle")


env.filters.update(num=f_num, krw=f_krw, dur=f_dur, ago=f_ago, kst=f_kst, level=f_level,
                   jsonattr=lambda v: json.dumps(v, ensure_ascii=False, default=str))
env.tests["contains"] = lambda seq, v: v in (seq or ())
env.globals.update(NAV=nav.NAV, RELEASE=config.RELEASE_NAME, VERSION=config.APP_VERSION, SITE_NAME=config.SITE_NAME,
                   AGENT=config.AGENT_NAME, PORT=config.APP_PORT, TARGET_PUE=config.TARGET_PUE, AUTH_ENABLED=config.AUTH_ENABLED)


_asset = {"at": 0.0, "v": ""}


def asset_v() -> str:
    """Cache-busting token: release + newest mtime of our own JS/CSS. Static files are served with a long
    max-age, so the browser revalidates nothing on navigation — this token is what invalidates them."""
    now = time.time()
    if now - _asset["at"] > 2:
        roots = [config.APP_DIR / "static" / d for d in ("js", "css")]
        newest = max((f.stat().st_mtime for r in roots for f in r.glob("*") if f.is_file()), default=0)
        _asset.update(at=now, v=f"{config.APP_VERSION}.{int(newest)}")
    return _asset["v"]


env.globals["asset_v"] = asset_v
env.globals.update(DATA_LARGE=config.DATA_LARGE, MAX_WINDOW_MIN=config.MAX_WINDOW_MIN)


def render(request: Request, template: str, title: str, data: dict | None = None, status_code: int = 200, **ctx):
    path = request.url.path
    return templates.TemplateResponse(request, template, status_code=status_code, context={
        "title": title, "path": path, "crumbs": nav.crumbs(path), "d": data or {}, "live": rm.live_or_empty(),
        "auth_enabled": config.AUTH_ENABLED, "user": request.session.get("user") if "session" in request.scope else None,
        **ctx,
    })
