"""Mission Control — incident investigation over live telemetry.

Claude mode: a manual tool-use loop on the Messages API (claude-opus-5-5,
adaptive thinking with progress updates, server-side fallbacks). Each session
keeps its full message history append-only so thinking blocks stay valid.

Offline mode (no Anthropic credentials): a deterministic analyst walks the
same tools, correlates findings, and writes the answer itself — so the page
is useful on a laptop with no key configured.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, AsyncIterator

import numpy as np

from .. import config
from ..sim import topology as T
from ..sim.promql import PromQLError, query as promql_query

MAX_STEPS = 10
SESSIONS: "OrderedDict[str, dict]" = OrderedDict()

SYSTEM_PROMPT = """You are Mission Control for Krafton Grid, a 100 MW AI data-center campus in Korea.
Module M1 is live: 5,000 NVIDIA B300 GPUs in 625 HGX nodes across 40 liquid-cooled racks (Halls A/B), \
IBM Storage Scale 100 PB, Arista Ethernet and NVIDIA Quantum-2 InfiniBand fabrics, a 30-node Dell Kubernetes \
cluster, 2N power (KEPCO 154 kV ×2, UPS A/B per hall, 10 gensets) and N+1 liquid-first cooling (CDUs per row \
with a spare per hall, 5 chillers, free-cooling towers). Cloud overflow runs on AWS (GPUaaS), GCP (storage) and NHN (GPUaaS).

You answer operators' questions by investigating the live telemetry with your tools. Ground every statement in \
tool output: name the concrete entity (rack, node, GPU, CDU, UPS, switch) and the number. When something is wrong, \
explain the causal chain across facility and IT (for example CDU failure → coolant supply → GPU temperature → \
throttling → job slowdown), the impact, and the next action — use the runbook text returned with alerts when present. \
If the data shows everything is healthy, say so plainly rather than inventing issues.

Write for an on-call engineer: a one-line headline, then the evidence as short bullets, then recommended actions. \
Answer in the language of the question (Korean questions get Korean answers). Before your first tool call, write one \
short sentence saying what you will check."""

TOOLS: list[dict] = [
    {"name": "get_site_overview", "description": "Live campus snapshot: IT/facility MW, PUE, power and cooling redundancy, "
     "GPU fleet funnel and health, Slurm queue, storage, network, Kubernetes, cloud burn, alert counts and running scenarios. "
     "Start here for broad questions.", "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "list_alerts", "description": "Active alerts and open incidents with root cause, entities, runbook and correlation.",
     "input_schema": {"type": "object", "properties": {"include_resolved": {"type": "boolean", "description": "Also return the 10 most recently resolved incidents."}},
                      "additionalProperties": False}},
    {"name": "get_incident", "description": "Full timeline and member alerts of one incident (id like INC-12345).",
     "input_schema": {"type": "object", "properties": {"incident_id": {"type": "string"}}, "required": ["incident_id"], "additionalProperties": False}},
    {"name": "query_metrics", "description": "Run a PromQL-style query over the TSDB and get per-series min/max/mean/last. "
     "Supports selectors with =, !=, =~, !~; sum/avg/max/min/count by (label); topk/bottomk; rate/increase/avg_over_time/max_over_time/min_over_time "
     "over [5m]-style ranges; arithmetic. Useful metrics: site_pue, site_it_mw, cooling_tcs_supply_c{row}, rack_temp_max_c{rack,row,hall}, "
     "rack_power_kw, node_temp_max_c{node,rack}, node_gpu_util, gpu_temp_c{gpu,node,rack}, gpu_util_pct, storage_latency_ms{cluster}, "
     "storage_write_gbs, net_device_util_pct{device,fabric}, net_device_errors_total, k8s_node_cpu_pct, cloud_cost_hr_krw{provider}, "
     "slurm_pending_gpus, gpu_idle_alloc.",
     "input_schema": {"type": "object", "properties": {"promql": {"type": "string"},
                                                       "window_minutes": {"type": "integer", "description": "Lookback, 1–60 (default 15)."}},
                      "required": ["promql"], "additionalProperties": False}},
    {"name": "search_logs", "description": 'LogQL-style log search. Stream selector then filters, e.g. {service="dcgm-exporter", level=~"warn|error"} |= "Xid". '
     "Services: slurmctld, slurmd, dcgm-exporter, ufm, arista-eos, bms, ups-snmp, cdu-modbus, kubelet, mmfs, cubeflow, vllm, grid-sim.",
     "input_schema": {"type": "object", "properties": {"logql": {"type": "string"}, "window_minutes": {"type": "integer"},
                                                       "limit": {"type": "integer", "description": "Max lines, ≤ 50."}},
                      "required": ["logql"], "additionalProperties": False}},
    {"name": "find_hotspots", "description": "Rank racks, nodes or GPUs by temperature, power, utilization, or idle-but-allocated.",
     "input_schema": {"type": "object", "properties": {
         "metric": {"type": "string", "enum": ["temp", "power", "util", "idle"]},
         "level": {"type": "string", "enum": ["rack", "node", "gpu"]},
         "top_k": {"type": "integer"}}, "required": ["metric", "level"], "additionalProperties": False}},
    {"name": "get_rack", "description": "One GPU rack (R01–R40): power, temperatures, node states, jobs, its CDU and coolant supply, IB/Ethernet leaves.",
     "input_schema": {"type": "object", "properties": {"rack_id": {"type": "string"}}, "required": ["rack_id"], "additionalProperties": False}},
    {"name": "get_node", "description": "One HGX node (e.g. kg-r12-n05): Slurm state, jobs, per-GPU util/temp/power/XID/ECC, recent events.",
     "input_schema": {"type": "object", "properties": {"node_id": {"type": "string"}}, "required": ["node_id"], "additionalProperties": False}},
    {"name": "get_gpu", "description": "One GPU device (e.g. kg-r12-n05-g3): utilization, SM, HBM, power, temperatures, clocks, throttle reason, ECC, last XID, MIG slices.",
     "input_schema": {"type": "object", "properties": {"gpu_id": {"type": "string"}}, "required": ["gpu_id"], "additionalProperties": False}},
    {"name": "get_cooling_plant", "description": "Chillers, towers, CDUs (status, supply/return, load, which row a spare covers), per-row coolant supply, CHW/FWS loops, free cooling.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "get_power_chain", "description": "Utility feeds, main transformers, UPS per hall/side (load, efficiency, mode, SOC), gensets, busway peaks, power quality.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "get_jobs", "description": "Slurm / CubeFlow jobs: running or pending or recently finished, optionally one project.",
     "input_schema": {"type": "object", "properties": {"state": {"type": "string", "enum": ["running", "pending", "finished"]},
                                                       "project": {"type": "string"}, "limit": {"type": "integer"}},
                      "required": ["state"], "additionalProperties": False}},
    {"name": "get_cost_summary", "description": "Month-to-date DC and cloud cost (KRW), forecast, MoM, TOU electricity band, cost per GPU-hour vs cloud.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
]


def claude_available() -> bool:
    mode = config.MISSION_CONTROL_MODE
    if mode == "offline":
        return False
    if mode == "claude":
        return True
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_PROFILE")
                or (Path.home() / ".config" / "anthropic").exists())


# ============================================================== tool impl
class Toolbox:
    """Read-only tools over the published read models — the agent sees exactly what the pages see."""

    def __init__(self, rm):
        self.rm = rm
        self.now = (rm.meta() or {}).get("sim_now") or time.time()

    def run(self, name: str, args: dict) -> tuple[Any, str | None]:
        fn = getattr(self, "t_" + name, None)
        if fn is None:
            raise ValueError(f"unknown tool {name}")
        out = fn(**(args or {}))
        href = out.pop("_href", None) if isinstance(out, dict) else None
        return out, href

    def t_get_site_overview(self) -> dict:
        L = self.rm.live()
        s, g = L["site"], L["gpu"]
        return {
            "site": {"it_mw": s["it_mw"], "facility_mw": s["facility_mw"], "capacity_mw": s["capacity_mw"], "util_pct": s["util_pct"],
                     "pue": s["pue"], "target_pue": config.TARGET_PUE, "wue": s["wue"], "ambient": s["ambient"]},
            "power": {"redundancy": L["power"]["redundancy"], "utility": L["power"]["utility"], "gens_running": L["power"]["gens_running"]},
            "cooling": {k: L["cooling"][k] for k in ("redundancy", "chw_supply_c", "fws_supply_c", "free_cooling_pct",
                                                     "tcs_supply_max_c", "chillers_running")},
            "gpu": {k: g[k] for k in ("total", "allocated", "active", "effective", "idle_allocated", "avg_util", "max_temp",
                                      "thermal_throttle", "power_throttle", "failed", "xid_1h", "jobs_running", "jobs_pending",
                                      "pending_gpus", "node_states")},
            "storage": {k: L["storage"][k] for k in ("used_pct", "read_gbs", "write_gbs", "latency_ms")},
            "network": {k: L["network"][k] for k in ("ib_util_pct", "eth_util_pct", "ib_links_down", "devices_down")},
            "k8s": {k: L["k8s"][k] for k in ("ready", "nodes", "pods_running", "pods_crashloop", "cpu_pct", "rps")},
            "cloud_cost_hr_krw": L["cloud"]["total_cost_hr_krw"],
            "alerts": {k: v for k, v in L["alerts"].items() if k != "recent"},
            "scenarios": L["scenarios"], "_href": "/",
        }

    def t_list_alerts(self, include_resolved: bool = False) -> dict:
        v = self.rm.view("alerts")
        active = [{k: a[k] for k in ("id", "name", "severity", "category", "value", "threshold", "summary", "entities",
                                     "runbook", "acked", "incident") if k in a} | {"age_s": round(self.now - a["started"])}
                  for a in v["active"] if not a.get("suppressed")]
        incs = []
        for i in v["incidents"]:
            if i["status"] == "resolved" and not include_resolved:
                continue
            incs.append({"id": i["id"], "title": i["title"], "status": i["status"], "severity": i["severity"],
                         "root_cause": i["root_cause"], "impact": i.get("impact", ""), "alerts": len(i["alerts"]),
                         "age_s": round(self.now - i["opened"])})
        return {"active_alerts": active, "incidents": incs[:15], "_href": "/alerts"}

    def t_get_incident(self, incident_id: str) -> dict:
        inc = next((i for i in self.rm.view("incidents")["incidents"] if i["id"] == incident_id), None)
        if not inc:
            raise ValueError(f"incident {incident_id} not found")
        return {**{k: inc.get(k) for k in ("id", "title", "status", "severity", "root_cause", "impact", "domain")},
                "timeline": [{"t_ago_s": round(self.now - e["t"]), "text": e["text"]} for e in inc["timeline"][-25:]],
                "_href": f"/alerts?incident={incident_id}"}

    def t_query_metrics(self, promql: str, window_minutes: int = 15) -> dict:
        w = max(1, min(60, int(window_minutes or 15))) * 60
        try:
            res = promql_query(self.rm.tsdb, promql, window_s=w, max_series=20, max_points=60)
        except PromQLError as e:
            raise ValueError(str(e))
        if res["resultType"] == "scalar":
            return {"scalar": res["result"]}
        series = []
        for s in res["result"]:
            vals = [v for _, v in s["values"] if v is not None]
            if not vals:
                continue
            series.append({"labels": s["metric"], "last": s["last"], "min": round(min(vals), 3), "max": round(max(vals), 3),
                           "mean": round(sum(vals) / len(vals), 3)})
        return {"series": series, "total_series": res["series"], "window_min": w // 60,
                "_href": f"/observability/metrics?q={promql}"}

    def t_search_logs(self, logql: str, window_minutes: int = 30, limit: int = 30) -> dict:
        res = self.rm.logs(logql, window_s=max(1, min(60, int(window_minutes or 30))) * 60, limit=max(1, min(50, int(limit or 30))))
        if res["resultType"] == "matrix":
            return {"series": res["result"][0]["values"][-20:], "total_lines": res["total"]}
        return {"total": res["total"], "by_level": res["by_level"],
                "lines": [{"t_ago_s": round(self.now - l["t"]), "service": l["service"], "host": l["host"],
                           "level": l["level"], "msg": l["msg"][:240]} for l in res["lines"]],
                "_href": f"/observability/logs?q={logql}"}

    # -- fleet vectors rebuilt from the published heatmaps (grid order → GPU index order)
    def _vec(self, metric: str) -> tuple[np.ndarray, np.ndarray]:
        hm = self.rm.view(f"heatmap:{metric}")
        grid = np.array(hm["values"], dtype=np.float64).reshape(len(hm["racks"]), hm["cols"])
        status = np.array(hm["status"], dtype=np.int8).reshape(grid.shape)
        vec, st = np.empty(T.GPU_COUNT), np.empty(T.GPU_COUNT, np.int8)
        for n in range(T.NODE_COUNT):
            r, s = T.NODE_RACK_IDX[n], T.NODE_SLOT[n] - 1
            vec[n * 8:(n + 1) * 8] = grid[r, s * 8:(s + 1) * 8]
            st[n * 8:(n + 1) * 8] = status[r, s * 8:(s + 1) * 8]
        return vec, st

    def t_find_hotspots(self, metric: str, level: str, top_k: int = 8) -> dict:
        k = max(1, min(25, int(top_k or 8)))
        util, status = self._vec("util")
        temp, _ = self._vec("temp")
        if metric == "idle":
            alloc = np.array(self.rm.view("gpu_alloc")["alloc"], dtype=bool)
            vec = np.where(alloc, 100 - util, -1)
        else:
            vec = {"temp": temp, "power": self._vec("power")[0], "util": util}[metric]
        if level == "gpu":
            idx = np.argsort(-vec)[:k]
            rows = [{"gpu": T.gpu_id(int(i)), "rack": T.NODE_RACK[int(i) // 8], "value": round(float(vec[i]), 1),
                     "temp_c": round(float(temp[i]), 1), "util": round(float(util[i]), 1), "throttle": int(status[i] == 2)} for i in idx]
        elif level == "node":
            nv = vec.reshape(-1, 8).max(axis=1) if metric == "temp" else vec.reshape(-1, 8).mean(axis=1)
            states = {r["id"]: r["state"] for r in self.rm.view("gpu_nodes")["rows"]}
            idx = np.argsort(-nv)[:k]
            rows = [{"node": T.NODE_IDS[int(i)], "rack": T.NODE_RACK[int(i)], "value": round(float(nv[i]), 1),
                     "state": states.get(T.NODE_IDS[int(i)], "?")} for i in idx]
        else:
            nv = vec.reshape(-1, 8).max(axis=1) if metric == "temp" else vec.reshape(-1, 8).mean(axis=1)
            racks: dict[str, list[float]] = {}
            for n, v in enumerate(nv):
                racks.setdefault(T.NODE_RACK[n], []).append(float(v))
            agg = {r: (max(v) if metric == "temp" else sum(v) / len(v)) for r, v in racks.items()}
            supply = self.rm.live()["cooling"]["row_supply_c"]
            rows = [{"rack": r, "row": T.RACK_BY_ID[r].row, "value": round(v, 1),
                     "coolant_c": round(supply.get(T.RACK_BY_ID[r].row, 0.0), 1)}
                    for r, v in sorted(agg.items(), key=lambda x: -x[1])[:k]]
        return {"metric": metric, "level": level, "top": rows, "_href": f"/gpu-fleet?metric={metric}"}

    def t_get_rack(self, rack_id: str) -> dict:
        rid = rack_id.upper()
        rk = T.RACK_BY_ID.get(rid)
        if not rk or rk.kind != "gpu":
            raise ValueError(f"{rack_id} is not a GPU rack (R01–R40)")
        d = self.rm.entity("rack", rid)
        st, L = d["stats"], self.rm.live()
        states: dict[str, int] = {}
        for u in d["units"]:
            if u["kind"] == "node":
                states[u["status"]] = states.get(u["status"], 0) + 1
        cdu = L["cooling"]["cdus"].get(rk.cdu, {})
        ib = (self.rm.entity("network_device", rk.ib_leaf) or {}).get("device", {})
        return {"rack": rid, "hall": rk.hall, "row": rk.row, "partition": T.RACK_PARTITION[rid],
                "power_kw": st["kw"], "design_kw": rk.design_kw, "gpu_util_avg": st["util"], "gpu_temp_max": st["temp_max"],
                "gpu_temp_avg": st["temp_avg"], "throttling": st["throttle"], "failed_gpus": st["failed"], "node_states": states,
                "coolant_supply_c": round(L["cooling"]["row_supply_c"].get(rk.row, 0.0), 1),
                "cdu": {"id": rk.cdu, "status": cdu.get("status"), "load_pct": cdu.get("load_pct")},
                "ib_leaf": {"id": rk.ib_leaf, **{k: ib.get(k) for k in ("util_pct", "links_down", "status")}},
                "eth_leaf": rk.eth_leaf, "_href": f"/rack/{rid}"}

    def t_get_node(self, node_id: str) -> dict:
        d = self.rm.entity("gpu_node", node_id.lower())
        if d is None:
            raise ValueError(f"unknown node {node_id} (format kg-r01-n01)")
        rec = dict(d["node"])
        gpus = [{k: v for k, v in g.items() if k in ("id", "util", "temp_c", "power_w", "throttle", "health", "xid", "ecc_sbe", "ecc_dbe")}
                for g in d["gpus"]]
        rec["jobs"] = [{k: j.get(k) for k in ("id", "name", "project", "user", "state", "gpus", "speed", "step_ms")} for j in rec.get("jobs", [])]
        rec["events"] = [{"t_ago_s": round(self.now - e["t"]), "text": e["text"]} for e in rec.get("events", [])[:12]]
        return {**rec, "gpus": gpus, "_href": f"/gpu-fleet/node/{rec['id']}"}

    def t_get_gpu(self, gpu_id: str) -> dict:
        d = self.rm.gpu_device(gpu_id)
        if d is None:
            raise ValueError(f"unknown GPU {gpu_id} (format kg-r01-n01-g0)")
        rec = dict(d["gpu"])
        if rec.get("job"):
            rec["job"] = {k: rec["job"].get(k) for k in ("id", "name", "project", "user", "speed")}
        return {**rec, "_href": f"/gpu-fleet/device/{rec['id']}"}

    def t_get_cooling_plant(self) -> dict:
        c = self.rm.view("facility_snapshot")["cooling"]
        return {"redundancy": c["redundancy"], "chw_supply_c": c["chw_supply_c"], "fws_supply_c": c["fws_supply_c"],
                "free_cooling_pct": c["free_cooling_pct"], "row_supply_c": c["row_supply_c"],
                "chillers": {k: {"status": v["status"], "load_pct": v["load_pct"], "cop": v["cop"]} for k, v in c["chillers"].items()},
                "cdus": {k: {"status": v["status"], "supply_c": v["supply_c"], "load_pct": v["load_pct"], "covering": v.get("covering"),
                             "leak": v["leak"]} for k, v in c["cdus"].items()},
                "_href": "/facility/cooling"}

    def t_get_power_chain(self) -> dict:
        p = self.rm.view("facility_snapshot")["power"]
        bw = max(p["busway"].items(), key=lambda kv: kv[1]["load_pct"])
        return {"redundancy": p["redundancy"], "utility": p["utility"],
                "transformers": {k: {"load_pct": v["load_pct"], "temp_c": v["temp_c"]} for k, v in p["tx"].items()},
                "ups": {k: {"status": v["status"], "load_pct": v["load_pct"], "eff": v["eff"], "soc": round(v["soc"], 1)}
                        for k, v in p["ups"].items() if v["status"] != "planned"},
                "gensets": {k: {"status": v["status"], "load_mw": v["load_mw"], "fuel_pct": round(v["fuel_pct"], 1)} for k, v in p["gens"].items()},
                "busway_peak": {"id": bw[0], **bw[1]}, "pq": p["pq"], "_href": "/facility/power"}

    def t_get_jobs(self, state: str, project: str | None = None, limit: int = 12) -> dict:
        k = max(1, min(30, int(limit or 12)))
        w = self.rm.view("workloads")
        rows = {"finished": w["finished"], "running": w["running"]}.get(state, w["pending"])
        rows = [r for r in rows if not project or r["project"] == project]
        if state != "finished":
            rows = sorted(rows, key=lambda r: -r["gpus"])
        return {"jobs": [{kk: r[kk] for kk in ("id", "name", "project", "user", "partition", "state", "gpus", "progress",
                                                 "speed", "wait_s", "reason") if kk in r} for r in rows[:k]],
                "_href": "/gpu-platform/workloads"}

    def t_get_cost_summary(self) -> dict:
        v = self.rm.view("cost")
        s, last = v["summary"], v["last_full"]
        return {"current_month": s["month"], "mtd_krw": s["mtd"], "forecast_krw": s["forecast"], "mom_pct": s["mom_pct"],
                "last_full_month": {"month": last["month"], "dc_krw": last["dc_total"], "cloud_krw": last["cloud_total"]},
                "tou": s["rate"], "unit_economics_krw_per_gpu_hr": s["unit"], "_href": "/cost"}


# ============================================================ claude mode
def _session(sid: str | None) -> tuple[str, dict]:
    if sid and sid in SESSIONS:
        SESSIONS.move_to_end(sid)
        return sid, SESSIONS[sid]
    sid = uuid.uuid4().hex[:12]
    SESSIONS[sid] = {"messages": [], "created": time.time()}
    while len(SESSIONS) > 40:
        SESSIONS.popitem(last=False)
    return sid, SESSIONS[sid]


def _summarize(name: str, out: Any) -> str:
    if not isinstance(out, dict):
        return str(out)[:120]
    if name == "get_site_overview" and "site" in out:
        st, g = out["site"], out["gpu"]
        return (f"IT {st['it_mw']} MW · PUE {st['pue']} · GPU util {g['avg_util']}% · "
                f"power {out['power']['redundancy']} · cooling {out['cooling']['redundancy']}")
    if name == "query_metrics":
        s = out.get("series", [])
        return f"{len(s)} series" + (f" · top {s[0]['labels']} last={s[0]['last']}" if s else "")
    if name == "get_jobs":
        js = out.get("jobs", [])
        return f"{len(js)} jobs" + (f" · largest {js[0]['name']} ({js[0]['gpus']} GPUs)" if js else "")
    if name == "search_logs":
        return f"{out.get('total', out.get('total_lines', 0))} lines"
    if name == "list_alerts":
        return f"{len(out['active_alerts'])} active alerts · {len(out['incidents'])} incidents"
    if name == "find_hotspots":
        top = out["top"][:3]
        key = next((k for k in ("rack", "node", "gpu", "row") if top and k in top[0]), None)
        items = ", ".join(f"{t.get(key, '?')} {t.get('value')}" for t in top) if top else "—"
        return f"top {out['level']}s by {out['metric']}: {items}"
    return ", ".join(f"{k}={v}" for k, v in list(out.items())[:4] if not isinstance(v, (dict, list)))[:160]


async def ask_stream(rm, question: str, session_id: str | None = None) -> AsyncIterator[dict]:
    """Yield progress events: status · update · tool · answer · done · error."""
    question = (question or "").strip()[:2000]
    if not question:
        yield {"type": "error", "text": "Ask a question first."}
        return
    tb = Toolbox(rm)
    if not claude_available():
        async for ev in _offline(tb, question):
            yield ev
        return
    try:
        import anthropic
    except ImportError:
        async for ev in _offline(tb, question, note="anthropic SDK not installed"):
            yield ev
        return

    sid, sess = _session(session_id)
    msgs = sess["messages"]
    msgs.append({"role": "user", "content": question})
    client = anthropic.AsyncAnthropic()
    model = config.MISSION_CONTROL_MODEL
    yield {"type": "status", "mode": "claude", "model": model, "session": sid}
    usage = {"input": 0, "output": 0, "cache_read": 0}
    t0 = time.time()
    for step in range(MAX_STEPS):
        try:
            resp = await client.beta.messages.create(
                model=model,
                max_tokens=16000,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                tools=TOOLS,
                messages=msgs,
                thinking={"type": "adaptive", "display": "updates"},
                output_config={"effort": "medium"},
                fallbacks="default",
                betas=["server-side-fallback-2026-07-01", "thinking-display-updates-2026-08-18"],
            )
        except anthropic.AuthenticationError:
            msgs.pop()
            async for ev in _offline(tb, question, note="Anthropic credentials were rejected — answered by the built-in analyst"):
                yield ev
            return
        except anthropic.RateLimitError:
            yield {"type": "error", "text": "Claude API rate-limited this request — try again in a moment."}
            return
        except anthropic.APIStatusError as e:
            yield {"type": "error", "text": f"Claude API error {e.status_code}: {e.message[:200]}"}
            return
        except anthropic.APIConnectionError:
            msgs.pop()
            async for ev in _offline(tb, question, note="Claude API unreachable — answered by the built-in analyst"):
                yield ev
            return

        u = resp.usage
        usage["input"] += u.input_tokens or 0
        usage["output"] += u.output_tokens or 0
        usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
        msgs.append({"role": "assistant", "content": resp.content})

        for b in resp.content:
            if b.type == "thinking" and getattr(b, "thinking", ""):
                yield {"type": "update", "text": b.thinking}
            elif b.type == "fallback":
                yield {"type": "status", "mode": "claude", "model": b.to.model, "note": f"{b.from_.model} declined; continuing on {b.to.model}"}

        if resp.stop_reason == "refusal":
            cat = resp.stop_details.category if resp.stop_details else None
            yield {"type": "answer", "text": f"Claude declined this request (category: {cat or 'unspecified'}). Try rephrasing the question."}
            break
        if resp.stop_reason != "tool_use":
            text = "\n\n".join(b.text for b in resp.content if b.type == "text").strip()
            if resp.stop_reason == "max_tokens":
                text += "\n\n_(answer truncated at the token limit)_"
            yield {"type": "answer", "text": text or "(no answer text)"}
            break

        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            args = b.input if isinstance(b.input, dict) else {}
            try:
                out, href = await asyncio.to_thread(tb.run, b.name, dict(args))
                payload, is_err = json.dumps(out, default=str, ensure_ascii=False)[:14000], False
                yield {"type": "tool", "name": b.name, "input": args, "summary": _summarize(b.name, out), "href": href}
            except Exception as e:  # tool errors go back to Claude as is_error results
                payload, is_err = f"Error: {e}", True
                yield {"type": "tool", "name": b.name, "input": args, "summary": f"error: {e}", "error": True}
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": payload, "is_error": is_err})
        msgs.append({"role": "user", "content": results})
    else:
        yield {"type": "answer", "text": "Stopped after the maximum number of investigation steps."}
    yield {"type": "done", "session": sid, "usage": usage, "elapsed_s": round(time.time() - t0, 1), "model": model}


# ============================================================ offline analyst
async def _offline(tb: Toolbox, question: str, note: str | None = None) -> AsyncIterator[dict]:
    ko = any("가" <= ch <= "힣" for ch in question)
    q = question.lower()
    yield {"type": "status", "mode": "offline", "model": "grid-analyst (built-in)",
           "note": note or "No Anthropic credentials found — set ANTHROPIC_API_KEY to use Claude Opus 5.5"}
    steps = []

    def call(name, **args):
        out, href = tb.run(name, args)
        steps.append((name, args, out, href))
        return out, {"type": "tool", "name": name, "input": args, "summary": _summarize(name, out), "href": href}

    ov, ev = call("get_site_overview")
    yield ev
    al, ev = call("list_alerts")
    yield ev
    findings, actions, evidence = [], [], []

    def any_kw(*words):
        return any(w in q for w in words)

    for inc in al["incidents"]:
        findings.append((3 if inc["severity"] == "critical" else 2,
                         f"{inc['id']} · {inc['title']} — root cause: {inc['root_cause']}" + (f" · impact: {inc['impact']}" if inc.get("impact") else "")))
    runbooks = {a["runbook"] for a in al["active_alerts"] if a.get("runbook")}
    actions += list(runbooks)[:3]

    g = ov["gpu"]
    focus_thermal = any_kw("temp", "thermal", "hot", "cool", "cdu", "온도", "냉각", "과열", "스로틀")
    if g["thermal_throttle"] or g["max_temp"] > 80 or focus_thermal:
        hot, ev = call("find_hotspots", metric="temp", level="rack", top_k=5)
        yield ev
        top = hot["top"][0]
        rack, ev = call("get_rack", rack_id=top["rack"])
        yield ev
        findings.append((2 if g["thermal_throttle"] else 1,
                         f"Hottest rack {top['rack']} (row {top['row']}) peaks {top['value']} °C; coolant supply {rack['coolant_supply_c']} °C via "
                         f"{rack['cdu']['id']} ({rack['cdu']['status']}); {rack['throttling']} GPUs throttling"))
        if focus_thermal or rack["cdu"]["status"] == "failed":
            cp, ev = call("get_cooling_plant")
            yield ev
            failed = [k for k, v in cp["cdus"].items() if v["status"] == "failed"]
            if failed:
                cov = {k: v["covering"] for k, v in cp["cdus"].items() if v.get("covering")}
                findings.append((3, f"CDUs failed: {', '.join(failed)} · spares covering: {cov or 'none'} · cooling redundancy {cp['redundancy']}"))
    if g["xid_1h"] or g["failed"] or any_kw("xid", "gpu", "fail", "장애", "에러"):
        logs, ev = call("search_logs", logql='{service="dcgm-exporter", level=~"warn|error"} |= "Xid"', window_minutes=60, limit=10)
        yield ev
        if logs.get("total"):
            findings.append((2 if g["failed"] else 1, f"{logs['total']} Xid log lines in the last hour; {g['failed']} GPUs failed; "
                             f"nodes drained/down: {g['node_states'].get('drain', 0)}/{g['node_states'].get('down', 0)}"))
            evidence.append(logs["lines"][0]["msg"] if logs["lines"] else "")
    if ov["network"]["ib_links_down"] or any_kw("ib", "infiniband", "network", "nccl", "네트워크"):
        m, ev = call("query_metrics", promql='topk(3, net_device_errors_total{fabric="infiniband"})', window_minutes=15)
        yield ev
        if ov["network"]["ib_links_down"]:
            findings.append((3, f"InfiniBand: {ov['network']['ib_links_down']} links down — top error counters "
                             f"{[s['labels'].get('device') for s in m['series']]}"))
    if ov["storage"]["latency_ms"] > 1.0 or any_kw("storage", "스토리지", "checkpoint", "체크포인트", "latency"):
        m, ev = call("query_metrics", promql='max_over_time(storage_latency_ms{cluster="ss-hot"}[5m])', window_minutes=15)
        yield ev
        s = m["series"][0] if m["series"] else {"max": ov["storage"]["latency_ms"]}
        findings.append((2 if s["max"] > 1.5 else 0, f"Scale hot-tier latency now {ov['storage']['latency_ms']} ms (15-min max {s['max']}) · "
                         f"write {ov['storage']['write_gbs']} GB/s"))
    if ov["power"]["redundancy"] != "2N" or any_kw("power", "ups", "전력", "정전", "generator", "발전"):
        pc, ev = call("get_power_chain")
        yield ev
        faults = [k for k, v in pc["ups"].items() if v["status"] in ("fault", "on-battery")]
        findings.append((3 if faults else 0, f"Power redundancy {pc['redundancy']}; UPS issues: {faults or 'none'}; "
                         f"gensets running {sum(1 for v in pc['gensets'].values() if v['status'] == 'running')}/10"))
    if any_kw("idle", "waste", "유휴", "낭비", "utiliz", "활용"):
        idle, ev = call("find_hotspots", metric="idle", level="node", top_k=5)
        yield ev
        waste = g["idle_allocated"] * 2600
        findings.append((1, f"{g['idle_allocated']} allocated GPUs are idle (<5% util) ≈ ₩{waste:,.0f}/hour of chargeback; "
                         f"worst nodes {[r['node'] for r in idle['top'][:3]]}"))
        actions.append("Enable 60-min idle culling for RCS notebooks; nudge owners of idle allocations.")
    if any_kw("cost", "비용", "요금", "budget", "예산"):
        c, ev = call("get_cost_summary")
        yield ev
        findings.append((0, f"MTD {c['current_month']}: DC ₩{c['mtd_krw']['dc']:,.0f} · cloud ₩{c['mtd_krw']['cloud']:,.0f}; "
                         f"TOU {c['tou']['band_ko']} {c['tou']['krw_kwh']} ₩/kWh; on-prem TCO ₩{c['unit_economics_krw_per_gpu_hr']['tco_per_gpu_hr']:,}/GPU-h "
                         f"vs AWS B200 ₩{c['unit_economics_krw_per_gpu_hr']['aws_b200_per_gpu_hr']:,}"))
    if ov["site"]["pue"] > 1.21 or any_kw("pue", "efficien", "효율"):
        findings.append((1 if ov["site"]["pue"] > 1.21 else 0, f"PUE {ov['site']['pue']} vs target {ov['site']['target_pue']} · free cooling "
                         f"{ov['cooling']['free_cooling_pct']}% · outdoor {ov['site']['ambient']['dry_c']} °C"))
    if g["pending_gpus"] > 3200 or any_kw("queue", "대기", "pending", "slurm", "job", "잡"):
        jobs, ev = call("get_jobs", state="pending", limit=5)
        yield ev
        findings.append((1 if g["pending_gpus"] > 3200 else 0, f"Slurm queue: {g['jobs_pending']} pending jobs asking for {g['pending_gpus']:,} GPUs; "
                         f"largest {[(j['name'], j['gpus']) for j in jobs['jobs'][:3]]}"))

    if not findings or all(lv == 0 for lv, _ in findings):
        # general "how are we doing?" — give a short operational briefing instead of a bare OK
        if not any(n == "find_hotspots" for n, *_ in steps):
            hot, ev = call("find_hotspots", metric="temp", level="rack", top_k=3)
            yield ev
            racks = ", ".join(f"{r['rack']} {r['value']} °C" for r in hot["top"][:3])
            findings.append((0, (f"최고 온도 랙: {racks} (스로틀 87 °C) · 냉각수 공급 최대 {ov['cooling']['tcs_supply_max_c']} °C" if ko else
                                 f"Hottest racks: {racks} (throttle at 87 °C) · coolant max {ov['cooling']['tcs_supply_max_c']} °C")))
        if not any(n == "get_jobs" for n, *_ in steps):
            jobs, ev = call("get_jobs", state="pending", limit=3)
            yield ev
            findings.append((0, (f"Slurm/CubeFlow: 실행 {g['jobs_running']}건 · 대기 {g['jobs_pending']}건 (요청 GPU {g['pending_gpus']:,}개)" if ko else
                                 f"Slurm/CubeFlow: {g['jobs_running']} running · {g['jobs_pending']} pending ({g['pending_gpus']:,} GPUs requested)")))
        idle_krw = g["idle_allocated"] * 2600
        findings.append((0, (f"할당됐지만 유휴(<5%)인 GPU {g['idle_allocated']}개 ≈ 시간당 ₩{idle_krw:,.0f} 차지백" if ko else
                             f"{g['idle_allocated']} allocated GPUs idle (<5% util) ≈ ₩{idle_krw:,.0f}/h chargeback")))
        findings.append((0, (f"전력 {ov['power']['redundancy']} · 냉각 {ov['cooling']['redundancy']} · 외기 {ov['site']['ambient']['dry_c']} °C에서 프리쿨링 {ov['cooling']['free_cooling_pct']}%" if ko else
                             f"Power {ov['power']['redundancy']} · cooling {ov['cooling']['redundancy']} · free cooling {ov['cooling']['free_cooling_pct']}% "
                             f"at {ov['site']['ambient']['dry_c']} °C outdoor")))
    findings.sort(key=lambda x: -x[0])
    worst = findings[0][0] if findings else 0
    if ko:
        head = {3: "[CRITICAL] 즉시 대응이 필요한 장애가 진행 중입니다.", 2: "[WARNING] 성능·안정성 저하가 감지됐습니다.",
                1: "[NOTICE] 주의가 필요한 항목이 있습니다.", 0: "[OK] 캠퍼스는 정상 운영 중입니다."}[worst]
        state = (f"IT {ov['site']['it_mw']} MW / 시설 {ov['site']['facility_mw']} MW · PUE {ov['site']['pue']} · GPU 할당 "
                 f"{g['allocated']:,}/{g['total']:,} · 활성 알림 {ov['alerts']['firing']}건")
        lines = [f"**{head}**", state, "", "**근거**"] + [f"- {f}" for _, f in findings[:7]]
        if actions:
            lines += ["", "**권장 조치**"] + [f"- {a}" for a in actions[:4]]
    else:
        head = {3: "[CRITICAL] An active incident needs immediate attention.", 2: "[WARNING] Degradation detected.",
                1: "[NOTICE] A few items need attention.", 0: "[OK] The campus is operating normally."}[worst]
        state = (f"IT {ov['site']['it_mw']} MW / facility {ov['site']['facility_mw']} MW · PUE {ov['site']['pue']} · GPUs allocated "
                 f"{g['allocated']:,}/{g['total']:,} · {ov['alerts']['firing']} alerts firing")
        lines = [f"**{head}**", state, "", "**Evidence**"] + [f"- {f}" for _, f in findings[:7]]
        if actions:
            lines += ["", "**Recommended actions**"] + [f"- {a}" for a in actions[:4]]
    if not findings:
        lines.append("- " + ("모든 지표가 정상 범위입니다." if ko else "All monitored signals are within normal ranges."))
    yield {"type": "answer", "text": "\n".join(lines)}
    yield {"type": "done", "session": None, "usage": None, "elapsed_s": 0.1, "model": "grid-analyst", "steps": len(steps)}


async def ask(rm, question: str, session_id: str | None = None) -> dict:
    out = {"answer": "", "steps": [], "updates": [], "mode": None, "model": None, "session": None, "usage": None}
    async for ev in ask_stream(rm, question, session_id):
        t = ev["type"]
        if t == "status":
            out["mode"], out["model"] = ev.get("mode"), ev.get("model")
            out["note"] = ev.get("note")
        elif t == "tool":
            out["steps"].append(ev)
        elif t == "update":
            out["updates"].append(ev["text"])
        elif t == "answer":
            out["answer"] = ev["text"]
        elif t == "done":
            out["session"], out["usage"] = ev.get("session"), ev.get("usage")
        elif t == "error":
            out["error"] = ev["text"]
    return out

