from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"


def _read_version() -> str:
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0"


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


PROJECT_SLUG = "grid-claude"
APP_VERSION = os.getenv("APP_VERSION", _read_version())
RELEASE_NAME = f"{PROJECT_SLUG}-v{APP_VERSION}"
AGENT_NAME = "Claude"

# Local per-agent port convention: ChatGPT 8001 · Cursor 8002 · Claude 8003
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8003"))
PUBLIC_URL = os.getenv("PUBLIC_URL", f"http://127.0.0.1:{APP_PORT}").rstrip("/")   # links in Slack / webhook payloads

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_PREFIX = os.getenv("REDIS_PREFIX", "dcim:aidc100:claude")

# Data path: collector ──▶ Redis ──▶ web. The web tier only ever reads the store.
#   GRID_STORE      auto (Redis if reachable, else in-process) · redis · memory
#   GRID_COLLECTOR  auto (use a running collector, else start one inside the web process) · embedded · external
GRID_STORE = os.getenv("GRID_STORE", "auto").lower()
GRID_COLLECTOR = os.getenv("GRID_COLLECTOR", "auto").lower()
COLLECTOR_LEASE_S = float(os.getenv("COLLECTOR_LEASE_S", "10"))
ENTITY_EVERY_TICKS = int(os.getenv("ENTITY_EVERY_TICKS", "5"))   # detail-page read models (10 s at 2 s ticks)
HEAVY_EVERY_TICKS = int(os.getenv("HEAVY_EVERY_TICKS", "3"))     # large list views (inventory, node tables …)

SIM_TICK_SEC = float(os.getenv("SIM_TICK_SEC", "2.0"))
SIM_SEED = int(os.getenv("SIM_SEED", "20260930"))

SITE_NAME = "Krafton Grid"
SITE_CODE = "KG-AIDC-01"
TIMEZONE = "Asia/Seoul"
TARGET_PUE = 1.18

REQUIREMENTS_MD = ROOT / "docs" / "REQUIREMENTS.md"
# Durable operator state (budget requests & approvals) — survives restarts; the twin itself is recomputed.
DATA_DIR = Path(os.getenv("GRID_DATA_DIR", str(ROOT / ".data")))

# Optional login gate — off for local side-by-side comparison, on for shared deployments.
AUTH_ENABLED = _flag("AUTH_ENABLED", "0")
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "krafton")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "grid-claude-dev-session-secret")
# Behind HTTPS the login cookie is only ever sent over TLS.
SESSION_HTTPS_ONLY = _flag("SESSION_HTTPS_ONLY", "1" if PUBLIC_URL.startswith("https://") else "0")

# Mission Control uses Claude when a key is present; otherwise the built-in analyst answers.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MISSION_CONTROL_MODEL = os.getenv("MISSION_CONTROL_MODEL", "claude-opus-5-5")
MISSION_CONTROL_MODE = os.getenv("MISSION_CONTROL_MODE", "auto").lower()  # auto | claude | offline

# Alert fan-out stays dry-run unless explicitly enabled with real endpoints.
ALERTS_LIVE_DELIVERY = _flag("ALERTS_LIVE_DELIVERY", "0")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
