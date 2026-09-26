"""Session helpers — cookie-backed via Starlette SessionMiddleware."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request

from app.auth.backend import AuthUser, get_auth_provider

SESSION_COOKIE = "kg_session"
SESSION_USER_KEY = "auth_user"


def set_session_user(request: Request, user: AuthUser) -> None:
    request.session[SESSION_USER_KEY] = {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "provider": user.provider,
    }


def clear_session_user(request: Request) -> None:
    request.session.pop(SESSION_USER_KEY, None)


def get_session_user(request: Request) -> AuthUser | None:
    raw: Any = request.session.get(SESSION_USER_KEY)
    if not isinstance(raw, dict):
        return None
    user_id = raw.get("id")
    if not user_id:
        return None
    # Re-validate against active provider (allows future Krafton revoke)
    user = get_auth_provider().get_user(str(user_id))
    if user:
        return user
    # Fallback to session payload for local provider continuity
    if raw.get("provider") == "local" and raw.get("username"):
        return AuthUser(
            id=str(raw["id"]),
            username=str(raw["username"]),
            display_name=str(raw.get("display_name") or raw["username"]),
            provider="local",
        )
    return None
