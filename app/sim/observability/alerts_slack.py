"""Alert destinations — Slack OAuth / Slack webhook / generic webhook / in-app."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import REDIS_KEY_PREFIX
from app.sim.observability.catalog import ALERT_CATALOG

DEFAULT_DESTINATIONS = [
    {
        "id": "dest-inapp",
        "type": "in_app",
        "name": "In-app (Alert history)",
        "status": "active",
        "enabled": True,
        "readonly": True,
        "detail": "Always on — alerts appear on /alerts",
    },
    {
        "id": "dest-slack-webhook",
        "type": "slack_webhook",
        "name": "Slack · #kg-aidc-alarms",
        "status": "active",
        "enabled": True,
        "webhook_url": "https://hooks.slack.com/services/SIM/KRAFTON/grid-aidc",
        "channel": "#kg-aidc-alarms",
        "detail": "Incoming webhook — simulated delivery log in Redis",
    },
    {
        "id": "dest-slack-oauth",
        "type": "slack_oauth",
        "name": "Slack OAuth · Mission Control app",
        "status": "configured",
        "enabled": False,
        "workspace": "krafton-enterprise",
        "channels": ["#kg-aidc-alarms", "#kg-gpu-oncall"],
        "detail": "OAuth app supports threading + multi-channel (sim)",
    },
    {
        "id": "dest-generic-webhook",
        "type": "generic_webhook",
        "name": "Pager / incident webhook",
        "status": "active",
        "enabled": True,
        "endpoint": "https://incident.krafton.local/hooks/kg-aidc",
        "signing_secret_set": True,
        "detail": "HTTPS + X-Krafton-Signature (sim)",
    },
]


def _dest_key() -> str:
    return f"{REDIS_KEY_PREFIX}:o11y:alert_destinations"


def _routing_key() -> str:
    return f"{REDIS_KEY_PREFIX}:o11y:alert_routing"


def _delivery_key() -> str:
    return f"{REDIS_KEY_PREFIX}:o11y:alert_deliveries"


def _ensure(redis: Any) -> None:
    if not redis.exists(_dest_key()):
        redis.set(_dest_key(), json.dumps(DEFAULT_DESTINATIONS))
    if not redis.exists(_routing_key()):
        # Default: critical+warning → Slack webhook + in-app; info → in-app only
        routing: dict[str, dict[str, bool]] = {}
        for alert in ALERT_CATALOG:
            routing[alert["id"]] = {
                "in_app": True,
                "slack_webhook": alert["severity"] in {"critical", "warning"},
                "slack_oauth": False,
                "generic_webhook": alert["severity"] == "critical",
            }
        redis.set(_routing_key(), json.dumps(routing))


def get_integrations_bundle(redis: Any) -> dict[str, Any]:
    _ensure(redis)
    destinations = json.loads(redis.get(_dest_key()) or "[]")
    return {
        "destinations": destinations,
        "limits": {
            "slack": "At most one Slack destination (OAuth or webhook) active at a time in production; sim allows both for demo.",
            "generic_webhook": "One generic webhook destination.",
            "in_app": "Always enabled.",
        },
        "destination_types": [
            {"type": "in_app", "label": "In-app", "description": "Default channel on Alert history"},
            {"type": "slack_oauth", "label": "Slack OAuth", "description": "Mission Control app · threading · multi-channel"},
            {"type": "slack_webhook", "label": "Slack webhook", "description": "Incoming webhook URL · single channel"},
            {"type": "generic_webhook", "label": "Generic webhook", "description": "HTTPS endpoint + optional signature"},
        ],
    }


def upsert_destination(redis: Any, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure(redis)
    destinations = json.loads(redis.get(_dest_key()) or "[]")
    dest_type = payload.get("type") or "slack_webhook"
    dest_id = payload.get("id") or f"dest-{uuid4().hex[:8]}"
    existing = next((d for d in destinations if d["id"] == dest_id), None)
    row = {
        **(existing or {}),
        "id": dest_id,
        "type": dest_type,
        "name": payload.get("name") or (existing or {}).get("name") or dest_type,
        "status": payload.get("status") or "active",
        "enabled": bool(payload.get("enabled", True)),
        "detail": payload.get("detail") or (existing or {}).get("detail") or "",
    }
    if dest_type == "slack_webhook":
        row["webhook_url"] = payload.get("webhook_url") or row.get("webhook_url") or "https://hooks.slack.com/services/SIM/…"
        row["channel"] = payload.get("channel") or row.get("channel") or "#kg-aidc-alarms"
    elif dest_type == "slack_oauth":
        row["workspace"] = payload.get("workspace") or row.get("workspace") or "krafton-enterprise"
        row["channels"] = payload.get("channels") or row.get("channels") or ["#kg-aidc-alarms"]
    elif dest_type == "generic_webhook":
        row["endpoint"] = payload.get("endpoint") or row.get("endpoint") or "https://example.local/hooks"
        row["signing_secret_set"] = bool(payload.get("signing_secret_set", True))
    destinations = [d for d in destinations if d["id"] != dest_id] + [row]
    redis.set(_dest_key(), json.dumps(destinations))
    return row


def get_alert_config(redis: Any) -> dict[str, Any]:
    _ensure(redis)
    routing = json.loads(redis.get(_routing_key()) or "{}")
    categories: dict[str, list[dict[str, Any]]] = {}
    for alert in ALERT_CATALOG:
        row = {**alert, "routing": routing.get(alert["id"], {"in_app": True})}
        categories.setdefault(alert["category"], []).append(row)
    return {
        "categories": [
            {"name": name, "alerts": rows, "count": len(rows)}
            for name, rows in categories.items()
        ],
        "channels": ["in_app", "slack_webhook", "slack_oauth", "generic_webhook"],
    }


def set_alert_routing(redis: Any, alert_id: str, routing: dict[str, bool]) -> dict[str, Any]:
    _ensure(redis)
    all_routing = json.loads(redis.get(_routing_key()) or "{}")
    current = all_routing.get(alert_id, {"in_app": True})
    current.update({k: bool(v) for k, v in routing.items()})
    current["in_app"] = True  # never disable in-app
    all_routing[alert_id] = current
    redis.set(_routing_key(), json.dumps(all_routing))
    return {"id": alert_id, "routing": current}


def deliver_alert_to_destinations(redis: Any, alert: dict[str, Any]) -> list[dict[str, Any]]:
    """Simulate fan-out of an alert to enabled destinations (Slack first)."""
    _ensure(redis)
    destinations = json.loads(redis.get(_dest_key()) or "[]")
    routing = json.loads(redis.get(_routing_key()) or "{}")
    # Match alert to catalog by severity if no explicit id
    alert_id = alert.get("catalog_id")
    if not alert_id:
        sev = alert.get("severity", "info")
        match = next((a for a in ALERT_CATALOG if a["severity"] == sev), ALERT_CATALOG[0])
        alert_id = match["id"]
    route = routing.get(alert_id, {"in_app": True, "slack_webhook": True})

    deliveries: list[dict[str, Any]] = []
    ts = datetime.now(timezone.utc).isoformat()
    for dest in destinations:
        if not dest.get("enabled", True):
            continue
        dtype = dest["type"]
        if dtype == "in_app" and not route.get("in_app", True):
            continue
        if dtype == "slack_webhook" and not route.get("slack_webhook"):
            continue
        if dtype == "slack_oauth" and not route.get("slack_oauth"):
            continue
        if dtype == "generic_webhook" and not route.get("generic_webhook"):
            continue
        if dtype == "in_app":
            continue  # already on alert list
        channel = dest.get("channel") or (dest.get("channels") or ["#ops"])[0]
        delivery = {
            "id": f"DLV-{uuid4().hex[:10]}",
            "ts": ts,
            "alert_id": alert.get("id"),
            "catalog_id": alert_id,
            "destination_id": dest["id"],
            "destination_type": dtype,
            "channel": channel if "slack" in dtype else dest.get("endpoint"),
            "status": "delivered",
            "preview": _slack_preview(alert, channel) if "slack" in dtype else _webhook_preview(alert),
        }
        deliveries.append(delivery)
        redis.lpush(_delivery_key(), json.dumps(delivery))
    redis.ltrim(_delivery_key(), 0, 199)
    return deliveries


def _slack_preview(alert: dict[str, Any], channel: str) -> str:
    sev = (alert.get("severity") or "info").upper()
    return (
        f"[{sev}] Krafton Grid · {alert.get('source', 'DCIM')}\n"
        f"{alert.get('message')}\n"
        f"→ {channel} · <https://grid.krafton.local/alerts|Open Alert Console>"
    )


def _webhook_preview(alert: dict[str, Any]) -> str:
    return json.dumps(
        {
            "severity": alert.get("severity"),
            "source": alert.get("source"),
            "message": alert.get("message"),
            "ts": alert.get("ts"),
        }
    )


def get_alert_deliveries(redis: Any, limit: int = 40) -> list[dict[str, Any]]:
    _ensure(redis)
    rows = redis.lrange(_delivery_key(), 0, limit - 1)
    return [json.loads(r) for r in rows]
