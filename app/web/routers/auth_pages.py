"""Login / logout pages."""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import clear_session_user, get_auth_provider, set_session_user
from app.config import RELEASE_NAME, SITE_NAME
from app.web.deps import templates

router = APIRouter(tags=["auth"])


def _safe_next(raw: str | None) -> str:
    if not raw:
        return "/"
    path = unquote(raw)
    if not path.startswith("/") or path.startswith("//"):
        return "/"
    if path.startswith("/login"):
        return "/"
    return path


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    from app.auth import get_session_user

    if get_session_user(request):
        return RedirectResponse(url=_safe_next(next), status_code=302)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "site_name": SITE_NAME,
            "release_name": RELEASE_NAME,
            "next": _safe_next(next),
            "error": None,
            "provider": get_auth_provider().name,
        },
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    user = get_auth_provider().authenticate(username.strip(), password)
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "site_name": SITE_NAME,
                "release_name": RELEASE_NAME,
                "next": _safe_next(next),
                "error": "Invalid ID or password.",
                "provider": get_auth_provider().name,
            },
            status_code=401,
        )
    set_session_user(request, user)
    return RedirectResponse(url=_safe_next(next), status_code=303)


@router.get("/logout")
@router.post("/logout")
async def logout(request: Request):
    clear_session_user(request)
    return RedirectResponse(url="/login", status_code=303)


@router.get("/health")
@router.get("/healthz")
async def health():
    return {"ok": True, "service": "krafton-grid-dcim"}
