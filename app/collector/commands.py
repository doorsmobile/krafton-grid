"""Command bus handlers — the only way the web tier changes collector state.

The web RPUSHes ``{id, cmd, args}`` to ``cmd``; the collector runs the handler under the engine
lock, republishes every read model, and only then replies on ``reply:{id}``. So when the browser
reloads after an action, Redis already holds the new state.

Handlers raise ``LookupError`` (→ 404) or ``ValueError`` (→ 400); anything else is a 500.
"""
from __future__ import annotations

import re

from .. import config
from ..sim import vendors as V
from ..sim.alerts import SEVERITY_ORDER
from ..sim.scenarios import MODES


def _need(ok, what: str):
    if not ok:
        raise LookupError(f"{what} not found")
    return ok


def build(eng) -> dict:
    am = eng.alerts

    def sim_mode(mode: str = "normal"):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        eng.set_mode(mode)
        return {"ok": True, "mode": mode}

    def sim_start(id: str, duration_s: float | None = None):
        try:
            return {"ok": True, "run": eng.run_scenario(id, duration_s)}
        except KeyError:
            raise LookupError("scenario not found") from None

    def sim_stop(id: str):
        return {"ok": eng.stop_scenario(id)}

    def alert_inject(severity: str = "warning", category: str = "platform", title: str = "", text: str = "", entities: str = ""):
        if severity not in ("info", "warning", "critical"):
            raise ValueError("severity must be info|warning|critical")
        with eng.lock:
            a = am.inject(eng.now, severity, category, title or "Manual test alert", text or "Injected from the Simulation console",
                          [x for x in re.split(r"[,\s]+", entities or "") if x], config.ALERTS_LIVE_DELIVERY, config.SLACK_WEBHOOK_URL)
        return {"ok": True, "alert": a}

    def alert_clear():
        with eng.lock:
            am.clear_manual(eng.now)
        return {"ok": True}

    def alert_ack(id: str, by: str = "operator"):
        with eng.lock:
            _need(am.ack(id, by, eng.now), "active alert")
        return {"ok": True}

    def incident_ack(id: str, by: str = "operator"):
        with eng.lock:
            _need(am.ack_incident(id, by, eng.now), "incident")
        return {"ok": True}

    def alert_test(target: str = "slack:#grid-alerts"):
        with eng.lock:
            return am.test_delivery(target, eng.now, config.ALERTS_LIVE_DELIVERY, config.SLACK_WEBHOOK_URL)

    def integration_update(id: str, patch: dict):
        with eng.lock:
            integ = _need(am.integrations.get(id), "integration")
            for k in ("enabled", "default_channel", "webhook_url", "url", "mode"):
                if k in patch:
                    integ[k] = patch[k]
            if isinstance(patch.get("channels"), dict):
                integ.setdefault("channels", {}).update({str(k): str(v) for k, v in patch["channels"].items()})
            return integ

    def rule_update(id: str, patch: dict):
        with eng.lock:
            rule = _need(am.rules.get(id), "rule")
            if "threshold" in patch:
                rule.threshold = float(patch["threshold"])
            if "for_ticks" in patch:
                rule.for_ticks = max(1, int(patch["for_ticks"]))
            if patch.get("severity") in SEVERITY_ORDER:
                rule.severity = patch["severity"]
            if "enabled" in patch:
                rule.enabled = bool(patch["enabled"])
            return rule.public()

    def routes_replace(routes: list):
        if not isinstance(routes, list):
            raise ValueError("routes must be a list")
        clean = []
        for r in routes:
            if not isinstance(r, dict) or r.get("min_severity") not in SEVERITY_ORDER:
                raise ValueError("min_severity must be info|warning|critical")
            clean.append({"id": str(r.get("id") or f"r-{len(clean)}"), "match_category": str(r.get("match_category", "*")),
                          "min_severity": r["min_severity"], "targets": [str(t) for t in r.get("targets", [])]})
        with eng.lock:
            am.routes = clean
        return {"routes": clean}

    def relay_set(id: str, enabled: bool):
        from ..readmodel.ops import RELAYS, relay_state
        _need(id in {r["id"] for r in RELAYS}, "relay")
        with eng.lock:
            eng.relay_enabled[id] = bool(enabled)
            return relay_state(eng)

    def node_drain(id: str, reason: str = "operator drain"):
        _need(eng.drain_node(id, reason or "operator drain"), "node")
        return {"ok": True, "node": id, "state": "drain"}

    def node_resume(id: str):
        _need(eng.resume_node(id), "node")
        return {"ok": True, "node": id}

    def gpu_xid(id: str, code: int = 79):
        from ..sim.fleet import XID_CODES
        if int(code) not in XID_CODES:
            raise ValueError(f"unsupported Xid {code}")
        _need(eng.inject_xid(id, int(code)), "GPU")
        return {"ok": True, "gpu": id, "xid": int(code)}

    def job_submit(project: str = "research-sandbox", profile: str = "finetune", size: int = 8, name: str | None = None,
                   user: str | None = None):
        return eng.submit_job(project, profile, size, name, user)

    def budget_create(payload: dict):
        with eng.lock:
            return eng.cost.create_request(payload or {}, eng.now)

    def budget_act(id: str, action: str):
        with eng.lock:
            try:
                return eng.cost.act(id, action, eng.now)
            except KeyError:
                raise LookupError("request not found") from None

    def vendor_sample(id: str):
        import time
        v = _need(V.VENDOR_BY_ID.get(id), "vendor")
        t0 = time.perf_counter()
        with eng.lock:
            body = V.sample(id, eng)
        return {"vendor": v, "request": v["endpoint"], "latency_ms": round((time.perf_counter() - t0) * 1000 + 12, 1), "response": body}

    return {
        "sim.mode": sim_mode, "sim.scenario.start": sim_start, "sim.scenario.stop": sim_stop,
        "sim.alert.inject": alert_inject, "sim.alert.clear": alert_clear,
        "alerts.ack": alert_ack, "alerts.incident.ack": incident_ack, "alerts.test": alert_test,
        "alerts.integration.update": integration_update, "alerts.rule.update": rule_update, "alerts.routes.replace": routes_replace,
        "relay.set": relay_set,
        "gpu.node.drain": node_drain, "gpu.node.resume": node_resume, "gpu.xid": gpu_xid, "gpu.job.submit": job_submit,
        "budget.create": budget_create, "budget.act": budget_act,
        "vendor.sample": vendor_sample,
    }


READ_ONLY = {"vendor.sample"}   # probes change nothing — no republish needed

# Detail entities a command can change immediately. Page views are always republished after a command;
# everything a command sets in motion physically (scenarios, modes) reaches entities on the normal cadence.
REFRESH = {
    "gpu.node.drain": {"gpu_node", "rack", "gpu_job"}, "gpu.node.resume": {"gpu_node", "rack", "gpu_job"},
    "gpu.xid": {"gpu_node", "rack", "gpu_pod"}, "gpu.job.submit": {"gpu_job"},
}
