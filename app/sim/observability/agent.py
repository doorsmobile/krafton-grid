"""Mission Control Agent — conversational investigation over live telemetry (sim)."""

from __future__ import annotations

from typing import Any


def ask_mission_control(engine: Any, question: str, context_path: str | None = None) -> dict[str, Any]:
    live = engine.get_live()
    q = (question or "").strip()
    q_l = q.lower()
    evidence: list[dict[str, Any]] = []
    answer_parts: list[str] = []

    if any(k in q_l for k in ("gpu", "b300", "sm util", "xid", "thermal")):
        util = live.get("gpu_utilization_pct")
        answer_parts.append(
            f"GPU fleet SM utilization is **{util}%**. "
            "Check GPU Monitoring Fleet Explorer for idle funnel, thermal, and XID monitors."
        )
        evidence.append({"kind": "metric", "name": "gpu_utilization_pct", "value": util, "href": "/gpu-fleet"})
        evidence.append({"kind": "page", "name": "GPU Monitoring", "href": "/gpu-fleet"})

    if any(k in q_l for k in ("pue", "power", "it load", "ups")):
        answer_parts.append(
            f"IT load is **{live.get('it_load_mw')} MW** with PUE **{live.get('pue')}** "
            f"(UPS load {live.get('ups_load_pct')}%). Facility Power page has the chain detail."
        )
        evidence.append({"kind": "metric", "name": "it_load_mw", "value": live.get("it_load_mw"), "href": "/power"})
        evidence.append({"kind": "metric", "name": "pue", "value": live.get("pue"), "href": "/facility"})

    if any(k in q_l for k in ("cool", "cdu", "liquid", "leak")):
        answer_parts.append(
            f"Cooling load **{live.get('cooling_load_pct')}%**, liquid loop **{live.get('liquid_loop_temp_c')}°C**. "
            "Review Cooling stage detail and Alerts for leak / vibration events."
        )
        evidence.append({"kind": "page", "name": "Cooling", "href": "/cooling"})

    if any(k in q_l for k in ("alert", "slack", "alarm", "page")):
        alerts = engine.get_alerts(5)
        answer_parts.append(
            f"There are **{live.get('active_alerts')}** open alerts. "
            "All alarms fan out to Slack (webhook / OAuth) when routing is enabled — see Alert Integrations."
        )
        for a in alerts[:3]:
            evidence.append(
                {
                    "kind": "alert",
                    "severity": a.get("severity"),
                    "message": a.get("message"),
                    "href": "/alerts",
                }
            )
        evidence.append({"kind": "page", "name": "Slack integrations", "href": "/alerts/integrations"})

    if any(k in q_l for k in ("storage", "ibm", "iops", "rebuild")):
        answer_parts.append(
            f"IBM Storage used **{live.get('storage_used_pb')} PB**. "
            "Use Storage Top Talkers and cluster detail pages; API: GET /api/storage."
        )
        evidence.append({"kind": "page", "name": "Storage", "href": "/storage"})

    if any(k in q_l for k in ("network", "arista", "optics", "fabric")):
        answer_parts.append(
            f"Ethernet fabric util **{live.get('eth_fabric_util_pct')}%**. "
            "Network overview → device detail for optics / errors."
        )
        evidence.append({"kind": "page", "name": "Network", "href": "/network"})

    if any(k in q_l for k in ("cost", "usage", "bill")):
        answer_parts.append(
            "Resource Usage and Cost pages track compute / storage / network spend. "
            "Developers: GET /api/observability/usage and GET /api/cost."
        )
        evidence.append({"kind": "page", "name": "Resource Usage", "href": "/observability/resource-usage"})
        evidence.append({"kind": "page", "name": "Cost", "href": "/cost"})

    if any(k in q_l for k in ("api", "developer", "promql", "logql")):
        answer_parts.append(
            "Every operator page has a paired JSON API. Browse **/developers/api** or GET /api/catalog. "
            "Metrics: POST /api/observability/metrics/query · Logs: POST /api/observability/logs/query."
        )
        evidence.append({"kind": "page", "name": "API Catalog", "href": "/developers/api"})

    if not answer_parts:
        answer_parts.append(
            f"Live mode **{live.get('mode')}**, tick {live.get('tick')}. "
            "Ask about GPU, PUE/power, cooling, alerts/Slack, storage, network, cost, or APIs. "
            f"Context path: {context_path or '/observability/mission-control'}."
        )
        evidence.append({"kind": "metric", "name": "mode", "value": live.get("mode")})

    # Deduplicate evidence by href/name
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for e in evidence:
        key = f"{e.get('kind')}:{e.get('name')}:{e.get('href')}:{e.get('message', '')}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)

    return {
        "question": q,
        "context_path": context_path or "/observability/mission-control",
        "answer": " ".join(answer_parts),
        "evidence": uniq,
        "suggested_followups": [
            "Why is GPU util high right now?",
            "Which critical alerts went to Slack?",
            "Show PromQL for IT load and PUE",
            "Where is the API for Network device detail?",
        ],
        "write_tools_enabled": False,
        "preview": "Mission Control Agent (sim) — read-only investigation with evidence links.",
    }
