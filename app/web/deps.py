"""Shared FastAPI/Jinja dependencies for page routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates

from app.config import APP_VERSION, PROJECT_SLUG, RELEASE_NAME, SITE_CODE, SITE_NAME
from app.sim import engine
from app.web.nav import NAV

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _nav_parent_open(active: str) -> set[str]:
    open_ids: set[str] = set()
    for item in NAV:
        kids = item.get("children") or []
        if any(c["id"] == active for c in kids):
            open_ids.add(item["id"])
    return open_ids


def page_ctx(active: str, **extra: Any) -> dict[str, Any]:
    live = engine.get_live()
    # `live` is reserved for facility KPIs in base.html — always win over extras.
    extra.pop("live", None)
    return {
        "nav": NAV,
        "active": active,
        "nav_open": _nav_parent_open(active),
        "site_name": SITE_NAME,
        "site_code": SITE_CODE,
        "app_version": APP_VERSION,
        "project_slug": PROJECT_SLUG,
        "release_name": RELEASE_NAME,
        **extra,
        "live": live,
    }
