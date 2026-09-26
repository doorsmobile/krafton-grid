"""Gate all HTML/API routes behind login (except allowlist)."""

from __future__ import annotations

from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.auth.session import get_session_user

# Paths that must stay public
_PUBLIC_EXACT = {
    "/login",
    "/logout",
    "/health",
    "/healthz",
    "/favicon.ico",
}
_PUBLIC_PREFIX = (
    "/static/",
    "/login?",
)


def _is_public(path: str) -> bool:
    if path in _PUBLIC_EXACT:
        return True
    return any(path.startswith(p) for p in _PUBLIC_PREFIX)


class AuthGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if _is_public(path):
            return await call_next(request)

        user = get_session_user(request)
        if user is not None:
            request.state.user = user
            return await call_next(request)

        # API clients get 401 JSON; browsers get login redirect
        accept = request.headers.get("accept", "")
        is_api = path.startswith("/api/") or "application/json" in accept
        if is_api and "text/html" not in accept:
            return JSONResponse(
                {"error": "unauthorized", "login": "/login"},
                status_code=401,
            )

        nxt = path
        if request.url.query:
            nxt = f"{path}?{request.url.query}"
        return RedirectResponse(url=f"/login?next={quote(nxt, safe='')}", status_code=302)
