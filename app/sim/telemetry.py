"""Shared minute-ring helpers for IT telemetry (Redis LPUSH/LTRIM)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.config import REDIS_KEY_PREFIX

HISTORY_LEN = 60
SAMPLE_INTERVAL_SEC = 60


def stable_seed(s: str) -> float:
    h = hashlib.md5(s.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def hist_key(domain: str, entity_id: str) -> str:
    safe = entity_id.replace(":", "/").replace(" ", "_")
    return f"{REDIS_KEY_PREFIX}:{domain}:hist:{safe}"


def dumps_point(point: dict[str, Any]) -> str:
    return json.dumps(point, separators=(",", ":"))


def loads_point(raw: str) -> dict[str, Any]:
    return json.loads(raw)


def now_minute() -> int:
    return int(datetime.now(timezone.utc).timestamp() // 60)


def minute_iso(minute: int) -> str:
    return datetime.fromtimestamp(minute * 60, tz=timezone.utc).isoformat()
