"""Alert rules, alert lifecycle, incident correlation and notification fan-out.

Rules evaluate against the engine every tick. Firing alerts that share a
correlation key (a scenario's root cause, or the same row / IB leaf) roll up
into one incident, so a CDU failure shows up as one incident with its
downstream thermal and throttling symptoms attached — not twelve pages.
"""
from __future__ import annotations

import json
import threading
import uuid
from collections import deque
from dataclasses import dataclass

import httpx

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}
RESOLVE_AFTER_TICKS = 8  # hysteresis: a condition must stay clear 16 s before an alert resolves
CATEGORIES = ["facility.power", "facility.cooling", "it.gpu", "it.network", "it.storage", "it.k8s", "cloud", "cost", "platform"]


@dataclass
class Rule:
    id: str
    name: str
    category: str
    severity: str
    metric: str
    op: str
    threshold: float
    for_ticks: int
    enabled: bool = True
    description: str = ""
    runbook: str = ""

    def public(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "name", "category", "severity", "metric", "op", "threshold",
                                              "for_ticks", "enabled", "description", "runbook")}


DEFAULT_RULES = [
    Rule("pue-high", "PUE above target band", "facility.power", "warning", "site.pue", ">", 1.23, 15,
         description="Site PUE drifted above 1.23 (target 1.18) for 30 s", runbook="Check free-cooling %, chiller staging, CRAH fan speed."),
    Rule("ups-redundancy", "Loss of 2N power redundancy", "facility.power", "critical", "power.ups_faults", ">", 0, 1,
         description="A UPS is faulted — surviving side carries 100% of the hall", runbook="Dispatch electrical on-call; verify static bypass; freeze changes."),
    Rule("ups-battery", "UPS on battery", "facility.power", "critical", "power.ups_on_battery", ">", 0, 1,
         runbook="Confirm genset start/sync; watch SOC and runtime."),
    Rule("utility-loss", "Utility feed lost", "facility.power", "critical", "power.utility_lost", ">", 0, 1,
         runbook="KEPCO call-out; confirm ATS transfer and genset fuel."),
    Rule("busway-load", "Busway above 80% of rating", "facility.power", "warning", "power.busway_max_pct", ">", 80, 5),
    Rule("cdu-fail", "CDU pump failure", "facility.cooling", "critical", "cooling.cdu_failed", ">", 0, 1,
         runbook="Verify spare CDU took the row; inspect pump VFD; open leak-check."),
    Rule("tcs-supply-high", "Rack coolant supply high", "facility.cooling", "warning", "cooling.tcs_supply_max_c", ">", 38.5, 3,
         description="Technology cooling loop supply above 38.5 °C on at least one row"),
    Rule("tcs-supply-crit", "Rack coolant supply critical", "facility.cooling", "critical", "cooling.tcs_supply_max_c", ">", 45.0, 2),
    Rule("chiller-trip", "Chiller tripped", "facility.cooling", "critical", "cooling.chillers_tripped", ">", 0, 1,
         runbook="Confirm lag chiller start; check compressor fault code on BMS."),
    Rule("chw-high", "CHW supply above setpoint", "facility.cooling", "warning", "cooling.chw_supply_c", ">", 19.2, 3),
    Rule("cooling-redundancy", "Cooling redundancy degraded (N)", "facility.cooling", "warning", "cooling.redundancy_lost", ">", 0, 2),
    Rule("leak", "Liquid leak detected", "facility.cooling", "critical", "cooling.leaks", ">", 0, 1,
         runbook="Isolate row manifold valves; dispatch technician with absorbents."),
    Rule("gpu-thermal", "GPU thermal throttling", "it.gpu", "warning", "gpu.thermal_throttle", ">", 8, 3,
         description="More than 8 GPUs throttling on temperature"),
    Rule("gpu-hot", "GPU temperature > 85 °C", "it.gpu", "warning", "gpu.max_temp", ">", 85, 3),
    Rule("gpu-xid-fatal", "Fatal XID on GPU", "it.gpu", "critical", "gpu.fatal_xid_recent", ">", 0, 1,
         runbook="Node auto-drained. Collect nvidia-bug-report; RMA if Xid 48/95 recurs."),
    Rule("gpu-idle-alloc", "Allocated GPUs idle", "it.gpu", "info", "gpu.idle_allocated", ">", 260, 30,
         description="More than 260 allocated GPUs below 5% util for 1 min", runbook="Nudge notebook owners; enable idle culling."),
    Rule("slurm-queue", "Slurm queue backlog", "platform", "warning", "slurm.pending_gpus", ">", 3200, 20,
         description="Pending jobs are requesting more than 3,200 GPUs", runbook="Review fair-share; consider AWS Capacity Block burst."),
    Rule("ib-errors", "InfiniBand link errors", "it.network", "critical", "network.ib_links_down", ">", 0, 1,
         runbook="Check UFM for flapping ports; reseat/replace transceivers on affected leaf."),
    Rule("eth-down", "Ethernet device down", "it.network", "critical", "network.devices_down", ">", 0, 1),
    Rule("storage-latency", "Storage latency high (hot tier)", "it.storage", "warning", "storage.latency_ms", ">", 1.5, 3,
         description="IBM Scale hot tier latency above 1.5 ms — often a checkpoint storm"),
    Rule("storage-full", "Storage above 85% used", "it.storage", "warning", "storage.used_pct", ">", 85, 5),
    Rule("nsd-down", "Storage NSD server down", "it.storage", "critical", "storage.nsd_down", ">", 0, 1),
    Rule("k8s-notready", "Kubernetes node NotReady", "it.k8s", "critical", "k8s.not_ready", ">", 0, 2),
    Rule("k8s-crashloop", "Pods in CrashLoopBackOff", "it.k8s", "warning", "k8s.crashloop", ">", 2, 5),
    Rule("cloud-spend", "Cloud burn rate high", "cloud", "warning", "cloud.cost_hr_krw", ">", 38_000_000, 10,
         description="Cloud spend above ₩38M/hour"),
    Rule("peak-tou", "Peak TOU band with high load", "cost", "info", "cost.peak_high_load", ">", 0, 30,
         description="최대부하 time-of-use band while facility load > 10 MW"),
]


class AlertManager:
    def __init__(self) -> None:
        self.rules: dict[str, Rule] = {r.id: r for r in DEFAULT_RULES}
        self.pending: dict[str, int] = {}
        self.clear: dict[str, int] = {}
        self.active: dict[str, dict] = {}
        self.history: deque[dict] = deque(maxlen=500)
        self.incidents: dict[str, dict] = {}
        self.incident_order: deque[str] = deque(maxlen=200)
        self.deliveries: deque[dict] = deque(maxlen=400)
        self.silences: list[dict] = []
        self.lock = threading.RLock()
        self.base_url = "http://127.0.0.1:8003"
        self.integrations = {
            "slack": {"id": "slack", "kind": "slack", "name": "Slack · Krafton Grid workspace", "enabled": True,
                      "mode": "webhook", "webhook_url": "", "default_channel": "#grid-alerts",
                      "channels": {"critical": "#grid-critical", "facility": "#grid-facility", "it": "#grid-it",
                                   "cost": "#grid-finops"}},
            "webhook": {"id": "webhook", "kind": "webhook", "name": "Generic webhook · ITSM", "enabled": True,
                        "url": "https://itsm.example.internal/hooks/dcim", "secret_set": True},
            "pagerduty": {"id": "pagerduty", "kind": "pagerduty", "name": "PagerDuty · DC on-call", "enabled": False,
                          "routing_key_set": False},
        }
        self.routes = [
            {"id": "r-crit", "match_category": "*", "min_severity": "critical", "targets": ["slack:#grid-critical", "webhook", "pagerduty"]},
            {"id": "r-fac", "match_category": "facility.*", "min_severity": "warning", "targets": ["slack:#grid-facility"]},
            {"id": "r-it", "match_category": "it.*", "min_severity": "warning", "targets": ["slack:#grid-it"]},
            {"id": "r-plat", "match_category": "platform", "min_severity": "warning", "targets": ["slack:#grid-it"]},
            {"id": "r-cost", "match_category": "cost", "min_severity": "info", "targets": ["slack:#grid-finops"]},
            {"id": "r-cloud", "match_category": "cloud", "min_severity": "warning", "targets": ["slack:#grid-finops"]},
        ]

    # --------------------------------------------------------------- evaluate
    def evaluate(self, now: float, metrics: dict[str, float], context: dict[str, dict], corr: dict[str, dict],
                 maint: set[str], live_delivery: bool, slack_url: str) -> list[dict]:
        fired, resolved = [], []
        with self.lock:
            for rule in self.rules.values():
                if not rule.enabled or rule.metric not in metrics:
                    continue
                v = metrics[rule.metric]
                hit = v > rule.threshold if rule.op == ">" else v < rule.threshold
                fp = rule.id
                if hit:
                    self.clear.pop(fp, None)
                    self.pending[fp] = self.pending.get(fp, 0) + 1
                    if fp not in self.active and self.pending[fp] >= rule.for_ticks:
                        ctx = context.get(rule.metric, {})
                        c = corr.get(rule.category) or corr.get(rule.metric) or {}
                        suppressed = bool(maint & set(ctx.get("entities", [])))
                        a = {"id": uuid.uuid4().hex[:10], "fingerprint": fp, "rule": rule.id, "name": rule.name,
                             "category": rule.category, "severity": rule.severity, "metric": rule.metric,
                             "value": round(float(v), 3), "threshold": rule.threshold, "started": now,
                             "state": "firing", "acked": False, "ack_by": None, "ack_t": None,
                             "entities": ctx.get("entities", []), "summary": ctx.get("summary", rule.description or rule.name),
                             "href": ctx.get("href"), "runbook": rule.runbook, "suppressed": suppressed,
                             "correlation": c.get("key") or ctx.get("corr") or f"{rule.category}:{fp}",
                             "root_cause": c.get("root_cause")}
                        self.active[fp] = a
                        self.history.appendleft(dict(a))
                        fired.append(a)
                        self._correlate(a, now, c)
                    elif fp in self.active:
                        a = self.active[fp]
                        a["value"] = round(float(v), 3)
                        ctx = context.get(rule.metric, {})
                        if ctx.get("summary"):
                            a["summary"] = ctx["summary"]
                        if ctx.get("entities"):
                            a["entities"] = ctx["entities"]
                else:
                    self.pending.pop(fp, None)
                    self.clear[fp] = self.clear.get(fp, 0) + 1
                    if fp in self.active and self.clear[fp] >= RESOLVE_AFTER_TICKS:
                        a = self.active.pop(fp)
                        a["state"], a["resolved"] = "resolved", now
                        self.history.appendleft(dict(a))
                        resolved.append(a)
                        self._resolve_in_incident(a, now)
            for a in fired + resolved:
                if not a.get("suppressed"):
                    self._fan_out(a, now, live_delivery, slack_url)
        return fired

    def _correlate(self, a: dict, now: float, c: dict) -> None:
        key = a["correlation"]
        inc = next((self.incidents[i] for i in self.incident_order
                    if self.incidents[i]["key"] == key and self.incidents[i]["status"] != "resolved"), None)
        if inc is None:
            inc_id = f"INC-{int(now) % 100000:05d}{len(self.incidents) % 10}"
            inc = {"id": inc_id, "key": key, "title": c.get("title") or a["name"], "status": "open",
                   "severity": a["severity"], "opened": now, "acked": None, "resolved": None,
                   "root_cause": c.get("root_cause") or "Under investigation", "alerts": [], "timeline": [],
                   "domain": a["category"].split(".")[0], "scenario": c.get("scenario"), "impact": c.get("impact", "")}
            self.incidents[inc_id] = inc
            self.incident_order.appendleft(inc_id)
            inc["timeline"].append({"t": now, "kind": "opened", "text": f"Incident opened by {a['name']}"})
        inc["alerts"].append(a["id"])
        a["incident"] = inc["id"]
        if SEVERITY_ORDER[a["severity"]] > SEVERITY_ORDER[inc["severity"]]:
            inc["severity"] = a["severity"]
        inc["timeline"].append({"t": now, "kind": "alert", "text": f"{a['severity'].upper()} · {a['name']} ({a['value']})",
                                "alert": a["id"]})

    def _resolve_in_incident(self, a: dict, now: float) -> None:
        inc = self.incidents.get(a.get("incident", ""))
        if not inc:
            return
        inc["timeline"].append({"t": now, "kind": "resolved", "text": f"Recovered · {a['name']}"})
        still = [x for x in self.active.values() if x.get("incident") == inc["id"]]
        if not still:
            inc["status"], inc["resolved"] = "resolved", now
            inc["timeline"].append({"t": now, "kind": "closed", "text": "All alerts recovered — incident auto-resolved"})
        elif inc["status"] == "open":
            inc["status"] = "mitigating"

    def ack(self, alert_id: str, who: str, now: float) -> bool:
        with self.lock:
            for a in self.active.values():
                if a["id"] == alert_id:
                    a.update(acked=True, ack_by=who, ack_t=now)
                    inc = self.incidents.get(a.get("incident", ""))
                    if inc and not inc["acked"]:
                        inc["acked"] = now
                        inc["timeline"].append({"t": now, "kind": "ack", "text": f"Acknowledged by {who}"})
                    return True
        return False

    def ack_incident(self, inc_id: str, who: str, now: float) -> bool:
        with self.lock:
            inc = self.incidents.get(inc_id)
            if not inc:
                return False
            inc["acked"] = inc["acked"] or now
            inc["timeline"].append({"t": now, "kind": "ack", "text": f"Acknowledged by {who}"})
            for a in self.active.values():
                if a.get("incident") == inc_id:
                    a.update(acked=True, ack_by=who, ack_t=now)
            return True

    def inject(self, now: float, severity: str, category: str, title: str, text: str, entities: list[str],
               live_delivery: bool, slack_url: str) -> dict:
        with self.lock:
            fp = f"manual-{uuid.uuid4().hex[:6]}"
            a = {"id": uuid.uuid4().hex[:10], "fingerprint": fp, "rule": "manual", "name": title, "category": category,
                 "severity": severity, "metric": "manual", "value": 1, "threshold": 0, "started": now, "state": "firing",
                 "acked": False, "ack_by": None, "ack_t": None, "entities": entities, "summary": text, "href": None,
                 "runbook": "Injected from Simulation console", "suppressed": False, "correlation": f"manual:{fp}",
                 "root_cause": "Manual injection", "manual": True}
            self.active[fp] = a
            self.history.appendleft(dict(a))
            self._correlate(a, now, {"title": title, "root_cause": "Manual injection from Simulation console"})
            self._fan_out(a, now, live_delivery, slack_url)
            return a

    def clear_manual(self, now: float) -> None:
        with self.lock:
            for fp in [fp for fp, a in self.active.items() if a.get("manual")]:
                a = self.active.pop(fp)
                a["state"], a["resolved"] = "resolved", now
                self.history.appendleft(dict(a))
                self._resolve_in_incident(a, now)

    # ---------------------------------------------------------------- fan-out
    def _targets(self, a: dict) -> list[str]:
        out = []
        for r in self.routes:
            mc = r["match_category"]
            cat_ok = mc == "*" or mc == a["category"] or (mc.endswith(".*") and a["category"].startswith(mc[:-1]))
            if cat_ok and SEVERITY_ORDER[a["severity"]] >= SEVERITY_ORDER[r["min_severity"]]:
                for t in r["targets"]:
                    if t not in out:
                        out.append(t)
        return out

    def slack_payload(self, a: dict, channel: str) -> dict:
        color = {"critical": "#F9423A", "warning": "#F5B942", "info": "#4C9BF5"}[a["severity"]]
        state = "RESOLVED" if a["state"] == "resolved" else a["severity"].upper()
        return {
            "channel": channel,
            "text": f"[{state}] {a['name']} — {a['summary']}",
            "attachments": [{"color": "#3DDC97" if a["state"] == "resolved" else color, "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*{state} · {a['name']}*\n{a['summary']}"}},
                {"type": "context", "elements": [
                    {"type": "mrkdwn", "text": f"`{a['category']}` · value *{a['value']}* (threshold {a['threshold']})"},
                    {"type": "mrkdwn", "text": f"incident {a.get('incident', '—')} · {', '.join(a['entities'][:4]) or 'site'}"}]},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Open in Krafton Grid"},
                     "url": f"{self.base_url}/alerts?focus={a['id']}"},
                    {"type": "button", "text": {"type": "plain_text", "text": "Acknowledge"}, "value": a["id"]}]},
            ]}],
        }

    def _fan_out(self, a: dict, now: float, live_delivery: bool, slack_url: str) -> None:
        for t in self._targets(a):
            kind, _, chan = t.partition(":")
            integ = self.integrations.get(kind)
            if not integ or not integ.get("enabled"):
                continue
            if kind == "slack":
                payload = self.slack_payload(a, chan or integ["default_channel"])
            else:
                payload = {"event": "alert." + a["state"], "alert": {k: a[k] for k in ("id", "name", "severity", "category", "value", "summary")},
                           "incident": a.get("incident"), "source": "krafton-grid/grid-claude"}
            status, detail = "dry-run", "delivery simulated (set ALERTS_LIVE_DELIVERY=1 and a webhook URL to send)"
            url = (slack_url or integ.get("webhook_url")) if kind == "slack" else None
            if live_delivery and kind == "slack" and url:
                try:
                    r = httpx.post(url, json=payload, timeout=4.0)
                    status, detail = ("delivered" if r.status_code < 300 else "failed"), f"HTTP {r.status_code}"
                except httpx.HTTPError as e:
                    status, detail = "failed", str(e)[:120]
            self.deliveries.appendleft({"id": uuid.uuid4().hex[:8], "t": now, "target": t, "kind": kind,
                                        "alert": a["id"], "alert_name": a["name"], "severity": a["severity"],
                                        "state": a["state"], "status": status, "detail": detail,
                                        "payload": json.dumps(payload, ensure_ascii=False)[:4000]})

    def test_delivery(self, target: str, now: float, live_delivery: bool, slack_url: str) -> dict:
        a = {"id": "test", "name": "Test notification from Krafton Grid", "summary": "Routing test — no action needed",
             "severity": "info", "category": "platform", "value": 0, "threshold": 0, "state": "firing", "entities": [],
             "incident": None}
        kind, _, chan = target.partition(":")
        integ = self.integrations.get(kind, {})
        payload = self.slack_payload(a, chan or integ.get("default_channel", "#grid-alerts")) if kind == "slack" else {"event": "test"}
        rec = {"id": uuid.uuid4().hex[:8], "t": now, "target": target, "kind": kind, "alert": "test",
               "alert_name": a["name"], "severity": "info", "state": "test", "status": "dry-run",
               "detail": "test payload rendered", "payload": json.dumps(payload, ensure_ascii=False)}
        if live_delivery and kind == "slack" and (slack_url or integ.get("webhook_url")):
            try:
                r = httpx.post(slack_url or integ.get("webhook_url"), json=payload, timeout=4.0)
                rec["status"], rec["detail"] = ("delivered" if r.status_code < 300 else "failed"), f"HTTP {r.status_code}"
            except httpx.HTTPError as e:
                rec["status"], rec["detail"] = "failed", str(e)[:120]
        self.deliveries.appendleft(rec)
        return rec

    # ---------------------------------------------------------------- views
    def counts(self) -> dict:
        with self.lock:
            act = [a for a in self.active.values() if not a.get("suppressed")]
            return {"firing": len(act), "critical": sum(1 for a in act if a["severity"] == "critical"),
                    "warning": sum(1 for a in act if a["severity"] == "warning"),
                    "info": sum(1 for a in act if a["severity"] == "info"),
                    "unacked": sum(1 for a in act if not a["acked"]),
                    "incidents_open": sum(1 for i in self.incidents.values() if i["status"] != "resolved")}

    def incident_list(self, limit: int = 50) -> list[dict]:
        with self.lock:
            return [self.incidents[i] for i in list(self.incident_order)[:limit]]

    def mtt_stats(self) -> dict:
        with self.lock:
            acked = [i["acked"] - i["opened"] for i in self.incidents.values() if i["acked"]]
            res = [i["resolved"] - i["opened"] for i in self.incidents.values() if i["resolved"]]
        return {"mtta_s": round(sum(acked) / len(acked)) if acked else None,
                "mttr_s": round(sum(res) / len(res)) if res else None,
                "incidents": len(self.incidents)}
