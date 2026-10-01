import hmac

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ... import config
from ..templating import render

router = APIRouter()


def _safe_next(nxt: str) -> str:
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else "/"


@router.get("/login", include_in_schema=False)
def page_login(request: Request, next: str = "/"):
    if not config.AUTH_ENABLED:
        return RedirectResponse(_safe_next(next), status_code=302)
    return render(request, "login.html", "Sign in", {"next": _safe_next(next), "error": None})


@router.post("/login", include_in_schema=False)
def do_login(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/")):
    ok = bool(config.AUTH_PASSWORD) and hmac.compare_digest(username, config.AUTH_USERNAME) \
        and hmac.compare_digest(password, config.AUTH_PASSWORD)
    if not ok:
        return render(request, "login.html", "Sign in", {"next": _safe_next(next), "error": "Invalid ID or password"})
    request.session["user"] = username
    return RedirectResponse(_safe_next(next), status_code=303)


@router.get("/logout", include_in_schema=False)
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login" if config.AUTH_ENABLED else "/", status_code=302)
