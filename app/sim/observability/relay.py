"""Telemetry Relay — forward metrics/logs/audit to external endpoints (sim)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import REDIS_KEY_PREFIX

DEFAULT_DESTINATIONS = [
    {
        "id": "dest-https-siem",
        "name": "Corporate SIEM HTTPS",
        "type": "https",
        "endpoint": "https://siem.krafton.local/v1/otel",
        "status": "active",
        "signals": ["audit", "logs"],
    },
    {
        "id": "dest-otlp-collector",
        "name": "External OTLP Collector",
        "type": "otlp_http",
        "endpoint": "https://otel.partner.local/v1/metrics",
        "status": "active",
        "signals": ["metrics", "logs"],
    },
]

DEFAULT_PIPELINES = [
    {
        "id": "pipe-audit",
        "name": "Audit logs → SIEM",
        "destination_id": "dest-https-siem",
        "signal": "audit",
        "enabled": True,
        "filter": '{job="krafton-grid", namespace="audit"}',
    },
    {
        "id": "pipe-metrics",
        "name": "Facility + GPU metrics → OTLP",
        "destination_id": "dest-otlp-collector",
        "signal": "metrics",
        "enabled": True,
        "filter": "kg_it_load_mw|kg_gpu_util_pct|kg_pue",
    },
]


def _key(suffix: str) -> str:
    return f"{REDIS_KEY_PREFIX}:o11y:relay:{suffix}"


def _ensure(redis: Any) -> None:
    if not redis.exists(_key("destinations")):
        redis.set(_key("destinations"), json.dumps(DEFAULT_DESTINATIONS))
    if not redis.exists(_key("pipelines")):
        redis.set(_key("pipelines"), json.dumps(DEFAULT_PIPELINES))


def get_relay_bundle(redis: Any, live: dict[str, Any] | None = None) -> dict[str, Any]:
    _ensure(redis)
    destinations = json.loads(redis.get(_key("destinations")) or "[]")
    pipelines = json.loads(redis.get(_key("pipelines")) or "[]")
    live = live or {}
    # Simulated forwarding counters
    tick = int(live.get("tick") or 0)
    return {
        "destinations": destinations,
        "pipelines": pipelines,
        "stats": {
            "bytes_forwarded_1h": 12_400_000 + tick * 2400,
            "events_forwarded_1h": 84_000 + tick * 18,
            "drop_rate_pct": round(0.02 + (tick % 7) * 0.01, 2),
            "last_forward_ts": live.get("ts") or datetime.now(timezone.utc).isoformat(),
        },
        "limits": {
            "max_destinations": 5,
            "self_service_signals": ["audit", "metrics", "logs"],
            "note": "Simulated Telemetry Relay — configure destinations/pipelines via UI or API.",
        },
    }


def upsert_relay_destination(redis: Any, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure(redis)
    destinations = json.loads(redis.get(_key("destinations")) or "[]")
    dest_id = payload.get("id") or f"dest-{uuid4().hex[:8]}"
    row = {
        "id": dest_id,
        "name": payload.get("name") or "Custom HTTPS",
        "type": payload.get("type") or "https",
        "endpoint": payload.get("endpoint") or "https://example.local/ingest",
        "status": payload.get("status") or "active",
        "signals": payload.get("signals") or ["audit"],
    }
    destinations = [d for d in destinations if d["id"] != dest_id] + [row]
    redis.set(_key("destinations"), json.dumps(destinations))
    return row


def upsert_relay_pipeline(redis: Any, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure(redis)
    pipelines = json.loads(redis.get(_key("pipelines")) or "[]")
    pipe_id = payload.get("id") or f"pipe-{uuid4().hex[:8]}"
    row = {
        "id": pipe_id,
        "name": payload.get("name") or "Custom pipeline",
        "destination_id": payload.get("destination_id"),
        "signal": payload.get("signal") or "logs",
        "enabled": bool(payload.get("enabled", True)),
        "filter": payload.get("filter") or '{job="krafton-grid"}',
    }
    pipelines = [p for p in pipelines if p["id"] != pipe_id] + [row]
    redis.set(_key("pipelines"), json.dumps(pipelines))
    return row
