from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_VERSION_FILE = _ROOT / "VERSION"


def _read_version() -> str:
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
PROJECT_SLUG = "dcim-cursor"
APP_VERSION = os.getenv("APP_VERSION", _read_version())
RELEASE_NAME = f"{PROJECT_SLUG}-v{APP_VERSION}"
LOCAL_CODE_ROOT = os.getenv("LOCAL_CODE_ROOT", "/Users/logan/code")

SITE_NAME = "Krafton Grid"
SITE_CODE = "KG-AIDC-01"
# Modular campus: first center 20 MW, full site investment / master plan 100 MW
MODULE_MW = 20.0
MODULE_COUNT = 5
DESIGN_CAPACITY_MW = MODULE_MW * MODULE_COUNT  # 100 MW
FIRST_MODULE_ID = "M1"
CRITICAL_IT_MW = MODULE_MW  # Phase-1 online modular center
TARGET_PUE = 1.18
REDIS_KEY_PREFIX = "dcim:aidc100:cursor"
SIM_INTERVAL_SEC = float(os.getenv("SIM_INTERVAL_SEC", "2.0"))
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8002"))

# Auth — local demo now; set AUTH_PROVIDER=krafton when SSO is ready
AUTH_PROVIDER = os.getenv("AUTH_PROVIDER", "local")
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "krafton")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "krafton-grid")
SESSION_SECRET = os.getenv("SESSION_SECRET", "krafton-grid-dcim-dev-secret-change-me")
SESSION_HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "0") in {"1", "true", "True", "yes"}
