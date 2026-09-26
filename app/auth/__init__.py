"""Authentication package.

Swap providers later for Krafton account SSO without rewriting page routes:
- ``local`` — username/password (current demo)
- ``krafton`` — reserved; implement ``KraftonAuthProvider`` when ready
"""

from app.auth.backend import AuthUser, get_auth_provider
from app.auth.middleware import AuthGateMiddleware
from app.auth.session import SESSION_COOKIE, clear_session_user, get_session_user, set_session_user

__all__ = [
    "AuthGateMiddleware",
    "AuthUser",
    "SESSION_COOKIE",
    "clear_session_user",
    "get_auth_provider",
    "get_session_user",
    "set_session_user",
]
