"""Auth provider interface — local now, Krafton account system later."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AuthUser:
    id: str
    username: str
    display_name: str
    provider: str


class AuthProvider(Protocol):
    name: str

    def authenticate(self, username: str, password: str) -> AuthUser | None:
        """Validate credentials. Return user or None."""

    def get_user(self, user_id: str) -> AuthUser | None:
        """Resolve a session user id (for future SSO token refresh)."""


class LocalAuthProvider:
    """Simple shared demo credentials. Replace with Krafton SSO later."""

    name = "local"

    def __init__(self) -> None:
        self._username = os.getenv("AUTH_USERNAME", "krafton")
        self._password = os.getenv("AUTH_PASSWORD", "krafton-grid")
        self._user = AuthUser(
            id="local:krafton",
            username=self._username,
            display_name="Krafton Grid Operator",
            provider=self.name,
        )

    def authenticate(self, username: str, password: str) -> AuthUser | None:
        if username == self._username and password == self._password:
            return self._user
        return None

    def get_user(self, user_id: str) -> AuthUser | None:
        if user_id == self._user.id:
            return self._user
        return None


class KraftonAuthProvider:
    """Placeholder for Krafton corporate account integration.

    Wire OIDC / SAML / internal IdP here later. Until then, always reject
    so misconfiguration cannot accidentally open the gate.
    """

    name = "krafton"

    def authenticate(self, username: str, password: str) -> AuthUser | None:
        return None

    def get_user(self, user_id: str) -> AuthUser | None:
        return None


def get_auth_provider() -> AuthProvider:
    kind = (os.getenv("AUTH_PROVIDER") or "local").strip().lower()
    if kind == "krafton":
        return KraftonAuthProvider()
    return LocalAuthProvider()
