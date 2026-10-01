"""Main · Campus · GPU Platform · Cloud · Operations · Observability views."""
from __future__ import annotations

import numpy as np

from .. import config
from ..fmt import f_krw
from ..sim import platform as P
from ..sim import topology as T
from ..sim import cost as C
from ..sim.cloud import AWS_TYPES, GCS_CLASS_USD_GB_MO
from ..sim.fleet import G, MIG_LAYOUTS, B300_MIG_PROFILES
from ..sim.vendors import VENDORS, health as vendor_health
from . import facility as FV
from . import it as IV


# ================================================================ main
def main(eng) -> dict:
    L = eng.live
    s, g = L["site"], L["gpu"]
    st, k, cl = L["storage"], L["k8s"], L["cloud"]
    kpis = [
            {"id": "it", "label": "Critical IT load", "value": s["it_mw"], "unit": "MW", "sub": f"of {s['capacity_mw']:.0f} MW M1 · {s['util_pct']}%", "path": "site.it_mw", "fmt": "f2"},
            {"id": "pue", "label": "PUE", "value": s["pue"], "unit": "", "sub": f"target {config.TARGET_PUE}", "path": "site.pue", "fmt": "f3"},
            {"id": "gpu", "label": "GPU utilization", "value": g["avg_util"], "unit": "%", "sub": f"{g['allocated']:,} / {g['total']:,} allocated", "path": "gpu.avg_util", "fmt": "f1"},
            {"id": "jobs", "label": "Jobs running", "value": g["jobs_running"], "unit": "", "sub": f"{g['jobs_pending']} pending", "path": "gpu.jobs_running", "fmt": "int"},
            {"id": "alerts", "label": "Open incidents", "value": L["alerts"]["incidents_open"], "unit": "", "sub": f"{L['alerts']['firing']} alerts firing", "path": "alerts.incidents_open", "fmt": "int"},
            {"id": "power_today", "label": "Electricity today", "value": L["cost"]["today_power_krw"], "unit": "", "sub": f"{L['cost']['rate']['band_ko']} · {L['cost']['rate']['krw_kwh']} ₩/kWh", "path": "cost.today_power_krw", "fmt": "krw"},
    ]
    for k in kpis:
        v = k["value"]
        k["display"] = {"f1": f"{v:,.1f}", "f2": f"{v:,.2f}", "f3": f"{v:,.3f}", "int": f"{v:,.0f}"}.get(k["fmt"]) or f_krw(v)
    return {
        "kpis": kpis,
        "facility": {"it_mw": s["it_mw"], "facility_mw": s["facility_mw"], "pue": s["pue"], "util_pct": s["util_pct"],
                     "redundancy": L["power"]["redundancy"], "cooling_red": L["cooling"]["redundancy"],
                     "free_cooling": L["cooling"]["free_cooling_pct"], "tcs_max": L["cooling"]["tcs_supply_max_c"],
                     "chw": L["cooling"]["chw_supply_c"], "ambient": s["ambient"]["dry_c"], "modules": T.MODULES},
        "ai": {"gpu": g, "k8s": k, "storage": st},
        "cloud": {"order": cl["order"], "aws": cl["aws"], "gcp": cl["gcp"], "nhn": cl["nhn"], "total_cost_hr_krw": cl["total_cost_hr_krw"]},
        "racks": IV.rack_matrix(eng),
        "incidents": [i for i in eng.alerts.incident_list(8) if i["status"] != "resolved"][:5],
        "events": list(eng.events)[:8],
        "scenarios": L["scenarios"],
    }


def campus(eng) -> dict:
    L = eng.live
    s = L["site"]
    hotspots = [
        {"id": "phase1", "x": 25.5, "y": 30.5, "w": 9.5, "h": 26, "title": "Phase 1 · M1 (ACTIVE)", "href": "/facility",
         "lines": [f"IT {s['it_mw']:.2f} MW / 20 MW", f"PUE {s['pue']:.3f}", f"{L['gpu']['total']:,} B300 · {L['gpu']['avg_util']}% util"],
         "level": "critical" if L["alerts"]["critical"] else ("warning" if L["alerts"]["warning"] else "ok")},
        {"id": "substation", "x": 4, "y": 28, "w": 10.5, "h": 16, "title": "154 kV substation", "href": "/facility/power",
         "lines": [f"Utility {sum(u['mw'] for u in L['power']['utility'].values()):.2f} MW", f"Redundancy {L['power']['redundancy']}",
                   f"Gensets running {L['power']['gens_running']}/10"],
         "level": "ok" if L["power"]["redundancy"] == "2N" else "critical"},
    ]
    x0 = 36
    for i, m in enumerate(T.MODULES[1:]):
        hotspots.append({"id": m["id"].lower(), "x": x0 + i * 12.8, "y": 18.5, "w": 11, "h": 31,
                         "title": f"Phase {m['phase']} · {m['id']} ({m['status'].upper()})", "href": "/facility/capacity",
                         "lines": [f"{m['it_mw']:.0f} MW critical IT", f"RFS {m['rfs']}", m["label"]], "level": "idle"})
    hotspots += [
        {"id": "ops", "x": 32, "y": 53, "w": 19, "h": 14, "title": "Operation Room (NOC)", "href": "/alerts",
         "lines": [f"{L['alerts']['incidents_open']} open incidents", f"{L['alerts']['firing']} alerts firing"],
         "level": "critical" if L["alerts"]["critical"] else "ok"},
        {"id": "labs", "x": 59, "y": 55, "w": 12, "h": 12, "title": "AI Labs", "href": "/gpu-platform",
         "lines": [f"{L['gpu']['jobs_running']} jobs running", f"{L['gpu']['jobs_pending']} pending"], "level": "ok"},
        {"id": "storage", "x": 74, "y": 55, "w": 16, "h": 13, "title": "Storage & Logistics", "href": "/storage",
         "lines": [f"IBM Scale {L['storage']['used_pb']:.1f} / 100 PB", f"{L['storage']['read_gbs']:.0f} GB/s read"], "level": "ok"},
        {"id": "gate", "x": 47, "y": 80, "w": 9, "h": 8, "title": "Main gate · security", "href": "/inventory",
         "lines": ["Badge access · CCTV · 24×7"], "level": "ok"},
    ]
    return {"image": "/static/img/campus-aerial.jpg", "hotspots": hotspots, "modules": T.MODULES, "buildout": T.BUILDOUT,
            "campus_mw": T.CAMPUS_MW, "live": {"it_mw": s["it_mw"], "pue": s["pue"]}}


# ================================================================ GPU platform
def gpu_platform(eng) -> dict:
    f = eng.fleet
    s = f.summary(eng.now)
    return {"summary": s, "projects": f.project_usage(), "notices": P.NOTICES, "partitions": f.partition_summary(),
            "llm": P.llm_catalog(f), "recent": list(f.finished)[:8]}


def gpu_workloads(eng) -> dict:
    f = eng.fleet
    now = eng.now
    running = sorted((j.public(now) for j in f.jobs.values() if j.state == "RUNNING"), key=lambda x: -x["gpus"])
    pending = sorted((j.public(now) for j in f.jobs.values() if j.state == "PENDING"), key=lambda x: -x["wait_s"])
    mig = []
    for gi, inst in list(f.mig.items()):
        mig.append({"gpu": T.gpu_id(gi), "node": T.NODE_IDS[gi // G], "util": round(float(f.util[gi]), 1),
                    "mem_gb": round(float(f.mem[gi]), 0), "instances": inst})
    return {"running": running, "pending": pending, "finished": list(f.finished)[:40], "mig": mig,
            "mig_profiles": B300_MIG_PROFILES, "mig_layouts": MIG_LAYOUTS,
            "rcs": P.rcs_sessions(f, now), "images": P.IMAGES, "burst": eng.cloud.burst_jobs[:10],
            "partitions": f.partition_summary()}


def gpu_ops(eng) -> dict:
    f = eng.fleet
    usage = f.project_usage()
    reports = []
    for p in usage:
        seeded = p["quota_gpus"] * 24 * 22 * 0.71
        mtd = seeded + p["gpu_hours_today"]
        reports.append({"project": p["id"], "name": p["name"], "team": p["team"], "gpu_hours_today": p["gpu_hours_today"],
                        "gpu_hours_mtd": round(mtd), "idle_gpu_hours_today": p["idle_gpu_hours_today"],
                        "chargeback_krw": round(mtd * P.CHARGEBACK_KRW_PER_GPU_HR)})
    return {"projects": usage, "rbac": [
        {"role": "Platform Admin", "scope": "cluster", "members": 4, "can": "all"},
        {"role": "Project Lead", "scope": "project", "members": 11, "can": "quota requests · member admin · job priority"},
        {"role": "Researcher", "scope": "project", "members": 138, "can": "submit jobs · RCS sessions · images"},
        {"role": "Viewer", "scope": "project", "members": 42, "can": "read-only dashboards"},
        {"role": "Finance", "scope": "org", "members": 3, "can": "usage & chargeback reports"}],
        "nodes": IV.gpu_nodes(eng)["rows"], "ecosystem": P.ecosystem_status(eng.k8s), "llm": P.llm_catalog(f),
        "reports": reports, "chargeback_rate": P.CHARGEBACK_KRW_PER_GPU_HR,
        "resource": {"gpu": eng.live["gpu"], "k8s": eng.live["k8s"], "storage": eng.live["storage"], "network": eng.live["network"]}}


# ================================================================ cloud
def cloud(eng) -> dict:
    c = eng.cloud
    L = eng.live["cloud"]
    top_aws = sorted((i for i in c.aws_instances if i["state"] == "running"), key=lambda i: -i["usd_hr"] * i["util"])[:5]
    top_gcp = sorted(c.buckets, key=lambda b: -(b["ops_a_s"] + b["ops_b_s"]))[:5]
    top_nhn = sorted((n for n in c.nhn if n["status"] == "ACTIVE"), key=lambda n: -n["util"])[:5]
    rows = eng.monthly()
    months = [{"month": r["month"], "partial": r["partial"], **r["cloud"], "total": r["cloud_total"]} for r in rows[-7:]]
    cur = rows[-1]
    frac = max(cur["month_frac"], C.MIN_FRAC)
    forecast = {k: round(v / frac) for k, v in cur["cloud"].items()}
    gpu_hr = {"aws": round(77.40 / 8 * 1392), "nhn": 9800,
              "on_prem": round(eng.cost.summary(eng.now, rows, eng.gpu_hours_month())["unit"]["tco_per_gpu_hr"])}
    return {"order": L["order"], "aws": L["aws"], "gcp": L["gcp"], "nhn": L["nhn"], "total_cost_hr_krw": L["total_cost_hr_krw"],
            "today_krw": c.cost_today_krw, "top": {"aws": top_aws, "gcp": top_gcp, "nhn": top_nhn},
            "burst": c.burst_jobs[:8], "capacity_blocks": c.capacity_blocks, "months": months,
            "mtd": cur["cloud"], "forecast": forecast, "gpu_hr_krw": gpu_hr,
            "interconnect": eng.network.border}


def cloud_aws(eng) -> dict:
    c = eng.cloud
    return {"summary": eng.live["cloud"]["aws"], "instances": c.aws_instances, "capacity_blocks": c.capacity_blocks,
            "burst": c.burst_jobs, "types": AWS_TYPES}


def cloud_gcp(eng) -> dict:
    c = eng.cloud
    return {"summary": eng.live["cloud"]["gcp"], "buckets": c.buckets, "disks": c.disks, "transfer": c.transfer}


def cloud_nhn(eng) -> dict:
    c = eng.cloud
    return {"summary": eng.live["cloud"]["nhn"], "instances": c.nhn}


def aws_instance(eng, iid: str) -> dict | None:
    inst = next((i for i in eng.cloud.aws_instances if i["id"] == iid), None)
    if not inst:
        return None
    cb = next((b for b in eng.cloud.capacity_blocks if b["id"] == inst.get("capacity_block")), None)
    return {"instance": inst, "capacity_block": cb, "krw_hr": round(inst["usd_hr"] * 1392),
            "uptime_s": round(eng.now - inst["launch_t"])}


def gcp_bucket(eng, bid: str) -> dict | None:
    b = next((x for x in eng.cloud.buckets if x["name"] == bid), None)
    if not b:
        return None
    return {"bucket": b, "monthly_krw": round(b["size_tb"] * 1000 * GCS_CLASS_USD_GB_MO[b["class"]] * 1392),
            "lifecycle": [{"action": "SetStorageClass NEARLINE", "age_days": 30}, {"action": "SetStorageClass ARCHIVE", "age_days": 180}]
            if b["class"] == "STANDARD" else [{"action": "Delete", "age_days": 3650}]}


def gcp_disk(eng, did: str) -> dict | None:
    d = next((x for x in eng.cloud.disks if x["id"] == did), None)
    return {"disk": d} if d else None


def nhn_instance(eng, iid: str) -> dict | None:
    n = next((x for x in eng.cloud.nhn if x["id"] == iid), None)
    return {"instance": n, "uptime_s": round(eng.now - n["launched"])} if n else None


# ================================================================ operations
def inventory(eng, q: str = "", kind: str = "") -> dict:
    items = []
    for d in T.POWER_DEVICES:
        items.append({"id": d["id"], "domain": "Facility · Power", "kind": d["kind"], "vendor": d.get("vendor"), "model": d["name"],
                      "location": d.get("hall") or "Substation", "href": f"/facility/power/{d['id']}",
                      "status": "planned" if d.get("planned") else FV._power_state(eng, d["id"])["status"]})
    for d in T.COOLING_DEVICES:
        items.append({"id": d["id"], "domain": "Facility · Cooling", "kind": d["kind"], "vendor": d.get("vendor"), "model": d["name"],
                      "location": d.get("hall") or "Central plant", "href": f"/facility/cooling/{d['id']}",
                      "status": FV._cooling_state(eng, d["id"])["status"]})
    f = eng.fleet
    for n in range(T.NODE_COUNT):
        items.append({"id": T.NODE_IDS[n], "domain": "IT · GPU", "kind": "hgx-node", "vendor": "NVIDIA", "model": T.NODE_MODEL,
                      "location": f"{T.NODE_RACK[n]} · U{3 + (T.NODE_SLOT[n] - 1) * 3}", "href": f"/gpu-fleet/node/{T.NODE_IDS[n]}",
                      "status": str(f.node_state[n])})
    for d in T.NET_DEVICES:
        items.append({"id": d["id"], "domain": "IT · Network", "kind": f"{d['fabric']}-{d['tier']}", "vendor": d["vendor"],
                      "model": d["model"], "location": d.get("rack"), "href": f"/network/device/{d['id']}",
                      "status": eng.network.dev[d["id"]]["status"]})
    for c in T.STORAGE_CLUSTERS:
        items.append({"id": c["id"], "domain": "IT · Storage", "kind": "scale-cluster", "vendor": "IBM", "model": c["product"],
                      "location": f"{c['racks'][0]}–{c['racks'][-1]}", "href": f"/storage/cluster/{c['id']}",
                      "status": eng.storage.clusters[c["id"]]["health"]})
    for n in T.K8S_NODES:
        items.append({"id": n["id"], "domain": "IT · Kubernetes", "kind": n["role"], "vendor": "Dell", "model": n["model"],
                      "location": n["rack"], "href": f"/kubernetes/node/{n['id']}", "status": eng.k8s.nodes[n["id"]]["status"]})
    counts = {}
    for it in items:
        counts[it["domain"]] = counts.get(it["domain"], 0) + 1
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i["id"].lower() or ql in (i["model"] or "").lower() or ql in (i["vendor"] or "").lower()]
    if kind:
        items = [i for i in items if i["domain"] == kind]
    return {"total": len(items), "counts": counts, "items": items,
            "headline": {"gpus": T.GPU_COUNT, "nodes": T.NODE_COUNT, "gpu_racks": T.GPU_RACKS, "storage_pb": T.STORAGE_TOTAL_PB,
                         "eth_switches": len(T.ETH_LEAVES) + len(T.ETH_SPINES), "ib_switches": len(T.IB_LEAVES) + len(T.IB_SPINES),
                         "k8s_nodes": len(T.K8S_NODES)}}


def racks(eng) -> dict:
    f = eng.fleet
    halls = []
    for h in T.HALLS:
        rows = []
        for row in [r for r in T.ROWS if r["hall"] == h["id"]]:
            rr = []
            for rk in [r for r in T.RACKS if r.row == row["id"]]:
                if rk.kind == "gpu":
                    i = T.RACK_INDEX[rk.id]
                    gm = f.gpu_rack == i
                    rr.append({"id": rk.id, "kind": "gpu", "kw": round(float(eng.rack_kw_vec[i]), 1), "design_kw": rk.design_kw,
                               "temp": round(float(f.temp[gm].max()), 1), "util": round(float(f.util[gm].mean()), 1),
                               "throttle": int((f.throttle[gm] == 1).sum()), "failed": int((f.health[gm] == 2).sum()),
                               "drain": int(sum(1 for n in range(rk.node_start, rk.node_start + rk.node_count)
                                                if f.node_state[n] in ("drain", "down"))),
                               "label": rk.label, "partition": T.RACK_PARTITION[rk.id]})
                else:
                    rr.append({"id": rk.id, "kind": rk.kind, "kw": round(eng.hallc.get(rk.id, 0.0), 1), "design_kw": rk.design_kw,
                               "temp": None, "util": None, "throttle": 0, "failed": 0, "drain": 0, "label": rk.label})
            rows.append({"id": row["id"], "kind": row["kind"], "racks": rr,
                         "supply_c": eng.facility.row_supply.get(row["id"]),
                         "cdu_status": eng.facility.cdu.get(row.get("cdu") or "", {}).get("status")})
        halls.append({"id": h["id"], "name": h["name"], "purpose": h["purpose"], "rows": rows,
                      "it_mw": eng.facility.snapshot["halls"][h["id"]]["it_mw"]})
    return {"halls": halls, "total_racks": len(T.RACKS)}


def rack(eng, rid: str) -> dict | None:
    rk = T.RACK_BY_ID.get(rid.upper())
    if not rk:
        return None
    f = eng.fleet
    units = []
    if rk.kind == "gpu":
        units.append({"u": 52, "size": 1, "kind": "switch", "id": rk.eth_leaf, "label": f"Arista 7060X6 · {rk.eth_leaf}",
                      "href": f"/network/device/{rk.eth_leaf}", "status": eng.network.dev[rk.eth_leaf]["status"]})
        units.append({"u": 51, "size": 1, "kind": "mgmt", "id": f"oob-{rk.id.lower()}", "label": "OOB mgmt switch", "status": "up"})
        for n in range(rk.node_start, rk.node_start + rk.node_count):
            gsl = slice(n * G, (n + 1) * G)
            slot = T.NODE_SLOT[n]
            units.append({"u": 48 - (slot - 1) * 3, "size": 3, "kind": "node", "id": T.NODE_IDS[n], "label": T.NODE_IDS[n],
                          "href": f"/gpu-fleet/node/{T.NODE_IDS[n]}", "status": str(f.node_state[n]),
                          "util": round(float(f.util[gsl].mean()), 1), "temp": round(float(f.temp[gsl].max()), 1),
                          "power_kw": round(float(f.node_power[n]) / 1000, 2),
                          "gpus": [{"util": round(float(f.util[g]), 0), "temp": round(float(f.temp[g]), 0),
                                    "health": int(f.health[g]), "throttle": int(f.throttle[g])} for g in range(n * G, (n + 1) * G)]})
        units.append({"u": 1, "size": 2, "kind": "power", "id": f"ps-{rk.id.lower()}", "label": "Power shelf · A/B busway taps", "status": "up"})
        i = T.RACK_INDEX[rk.id]
        gm = f.gpu_rack == i
        stats = {"kw": round(float(eng.rack_kw_vec[i]), 1), "util": round(float(f.util[gm].mean()), 1),
                 "temp_max": round(float(f.temp[gm].max()), 1), "temp_avg": round(float(f.temp[gm].mean()), 1),
                 "throttle": int((f.throttle[gm] == 1).sum()), "failed": int((f.health[gm] == 2).sum()),
                 "alloc": int((f.gpu_job[gm] >= 0).sum()), "gpus": int(gm.sum()), "col": i}
    else:
        stats = {"kw": round(eng.hallc.get(rk.id, 0.0), 1), "col": None}
    return {"rack": {**{k: getattr(rk, k) for k in ("id", "hall", "row", "pos", "kind", "design_kw", "label", "cdu", "eth_leaf", "ib_leaf")},
                     "partition": T.RACK_PARTITION.get(rk.id)},
            "units": units, "stats": stats,
            "cooling": {"cdu": rk.cdu, "status": eng.facility.cdu.get(rk.cdu, {}).get("status"),
                        "supply_c": round(eng.facility.row_supply.get(rk.row, 0.0), 1) if rk.row in eng.facility.row_supply else None},
            "power": {"a": f"BW-{rk.row}-A", "b": f"BW-{rk.row}-B"}}


def alerts(eng) -> dict:
    am = eng.alerts
    with am.lock:
        active = sorted(am.active.values(), key=lambda a: (-{"critical": 2, "warning": 1, "info": 0}[a["severity"]], -a["started"]))
        history = list(am.history)[:80]
    return {"counts": am.counts(), "active": active, "incidents": am.incident_list(40), "history": history,
            "mtt": am.mtt_stats(), "deliveries": list(am.deliveries)[:12]}


def integrations(eng) -> dict:
    am = eng.alerts
    return {"integrations": list(am.integrations.values()), "routes": am.routes, "deliveries": list(am.deliveries)[:60],
            "live_delivery": config.ALERTS_LIVE_DELIVERY, "slack_env": bool(config.SLACK_WEBHOOK_URL)}


def alert_config(eng) -> dict:
    from ..sim.alerts import CATEGORIES
    return {"rules": [r.public() for r in eng.alerts.rules.values()], "routes": eng.alerts.routes, "categories": CATEGORIES}


# ================================================================ observability
RELAYS = [
    {"id": "grafana-cloud", "name": "Grafana Cloud · OTLP", "protocol": "OTLP/HTTP", "endpoint": "https://otlp-gateway-prod-ap-northeast-0.grafana.net/otlp",
     "signals": ["metrics", "logs"], "enabled": True, "filter": 'service=~".*"'},
    {"id": "datadog", "name": "Datadog · GPU Monitoring", "protocol": "Datadog API", "endpoint": "https://api.ap1.datadoghq.com",
     "signals": ["metrics"], "enabled": True, "filter": "gpu_* · node_* · rack_*"},
    {"id": "splunk", "name": "Splunk HEC · SOC", "protocol": "HEC", "endpoint": "https://splunk.krafton.internal:8088",
     "signals": ["logs", "events"], "enabled": False, "filter": 'level=~"warn|error"'},
    {"id": "gcs-archive", "name": "GCS cold archive", "protocol": "OTLP → Parquet", "endpoint": "gs://kg-telemetry-coldline",
     "signals": ["metrics", "logs", "events"], "enabled": True, "filter": "all"},
]


def observability(eng) -> dict:
    cat = eng.tsdb.catalog()
    return {"metrics": len(cat), "series": sum(m["series"] for m in cat), "log_lines": len(eng.logs.lines),
            "log_services": eng.logs.services(), "events": len(eng.events), "relays": relay_state(eng)["relays"],
            "solutions": [
                {"id": "explore", "title": "Explore", "href": "/observability/explore", "desc": "Metrics, logs and events on one timeline."},
                {"id": "metrics", "title": "Metrics", "href": "/observability/metrics", "desc": "PromQL-style queries over 5,000 GPUs and the plant."},
                {"id": "logs", "title": "Logs", "href": "/observability/logs", "desc": "LogQL-style search across Slurm, DCGM, UFM, EOS, BMS."},
                {"id": "relay", "title": "Telemetry Relay", "href": "/observability/telemetry-relay", "desc": "Forward to Grafana, Datadog, Splunk, GCS."},
                {"id": "usage", "title": "Resource Usage", "href": "/observability/resource-usage", "desc": "Compute, storage, network by project with cost."},
                {"id": "agent", "title": "Mission Control", "href": "/observability/mission-control", "desc": "Ask Claude to investigate live telemetry."},
                {"id": "alerts", "title": "Alerts → Slack", "href": "/alerts/integrations", "desc": "Route incidents to Slack and webhooks."}],
            "catalog": cat[:12], "tick_ms": eng.tick_ms, "tick": eng.tick_n}


def relay_state(eng) -> dict:
    rng = np.random.default_rng(int(eng.now) // 10)
    out = []
    for r in RELAYS:
        on = eng.relay_enabled.get(r["id"], r["enabled"])
        eps = float(rng.uniform(12000, 42000)) if on else 0.0
        out.append({**r, "enabled": on, "eps": round(eps), "mb_s": round(eps * 0.00031, 2),
                    "dropped_pct": round(float(rng.uniform(0, 0.03)), 3) if on else 0.0,
                    "lag_ms": round(float(rng.uniform(80, 420))) if on else None})
    return {"relays": out}


def resource_usage(eng) -> dict:
    f = eng.fleet
    usage = f.project_usage()
    vols = {}
    for v in eng.storage.volumes:
        vols.setdefault(v["project"], {"used_tb": 0.0, "iops_k": 0.0, "read_gbs": 0.0, "write_gbs": 0.0})
        e = vols[v["project"]]
        e["used_tb"] += v["used_tb"]
        e["iops_k"] += v["iops_k"]
        e["read_gbs"] += v["read_gbs"]
        e["write_gbs"] += v["write_gbs"]
    rows = []
    for p in usage:
        running = [j for j in f.jobs.values() if j.project == p["id"] and j.state == "RUNNING"]
        nodes = sorted({n for j in running for n in j.nodes})
        ib = float(f.node_ib[nodes].sum()) / 1000 if nodes else 0.0
        st = vols.get(p["id"], {"used_tb": 0.0, "iops_k": 0.0, "read_gbs": 0.0, "write_gbs": 0.0})
        gpu_krw_hr = p["used_gpus"] * P.CHARGEBACK_KRW_PER_GPU_HR
        rows.append({"project": p["id"], "name": p["name"], "gpus": p["used_gpus"], "util": p["util"],
                     "gpu_hours_today": p["gpu_hours_today"], "storage_tb": round(st["used_tb"]), "iops_k": round(st["iops_k"], 1),
                     "io_gbs": round(st["read_gbs"] + st["write_gbs"], 1), "ib_tbps": round(ib, 2),
                     "cost_hr_krw": round(gpu_krw_hr + st["used_tb"] * 32), "idle_gpu_hours_today": p["idle_gpu_hours_today"]})
    return {"projects": sorted(rows, key=lambda r: -r["cost_hr_krw"]), "rate": P.CHARGEBACK_KRW_PER_GPU_HR}


def explore_events(eng, window_s: float = 3600) -> list[dict]:
    cutoff = eng.now - window_s
    out = [e for e in eng.events if e["t"] >= cutoff]
    with eng.alerts.lock:
        for a in list(eng.alerts.history)[:120]:
            if a["started"] >= cutoff:
                out.append({"t": a.get("resolved") or a["started"], "kind": "alert", "level": a["severity"] if a["state"] != "resolved" else "ok",
                            "text": f"{'RESOLVED · ' if a['state'] == 'resolved' else ''}{a['name']} — {a['summary']}",
                            "domain": a["category"], "href": f"/alerts?focus={a['id']}"})
    out.sort(key=lambda e: -e["t"])
    return out[:200]


# ================================================================ platform
def vendors(eng) -> dict:
    faults = eng.mods["faults"]
    return {"vendors": [{**v, **vendor_health(v["id"], eng.now, faults)} for v in VENDORS],
            "groups": ["Facility", "IT", "Cloud"], "cloud_order": ["aws", "gcp", "nhn"]}


def simulation(eng) -> dict:
    return {"scenarios": eng.scen.public(eng.now), "tick": eng.tick_n, "tick_ms": round(eng.tick_ms, 2),
            "tick_s": config.SIM_TICK_SEC, "boot": eng.boot, "uptime_s": round(eng.now - eng.boot),
            "seed": config.SIM_SEED, "prefix": config.REDIS_PREFIX,
            "tsdb": {"metrics": len(eng.tsdb.metrics), "series": sum(m.width for m in eng.tsdb.metrics.values())}}


# ================================================================ platform · tech spec
def tech_spec(eng) -> dict:
    return {
        "release": config.RELEASE_NAME, "version": config.APP_VERSION, "port": config.APP_PORT, "redis": config.REDIS_PREFIX,
        "tick_s": config.SIM_TICK_SEC, "tick_ms": round(eng.tick_ms, 2), "metrics": len(eng.tsdb.metrics),
        "series": sum(m.width for m in eng.tsdb.metrics.values()),
        "stack": [("Language", "Python 3.14"), ("Web", "FastAPI + Uvicorn + Jinja2 · Server-Sent Events (one stream per browser)"),
                  ("Data path", "collector → Redis read models → web (pages · APIs · SSE read Redis only)"),
                  ("Simulation", "numpy-vectorised physics · 5,000 GPUs per 2 s tick (the demo collector)"),
                  ("State", f"Redis {config.REDIS_PREFIX}:* — live · view:* · ent:* · ts:* · logs · meta · cmd bus"),
                  ("Charts", "Highcharts 13 local vendor (heatmap · sankey · xrange · solid-gauge) + canvas heat grid"),
                  ("Query", "PromQL-lite + LogQL-lite evaluated in the web tier over Redis data"),
                  ("AI", f"Claude ({config.MISSION_CONTROL_MODEL}) tool-use agent over the read models · offline analyst fallback"),
                  ("Auth", "Optional session login (AUTH_ENABLED=1)")],
        "model": [
            ("GPU fleet", f"{T.GPU_COUNT:,} × {T.GPU_MODEL} · {T.NODE_COUNT} HGX nodes · {T.GPU_RACKS} racks (R01–R25 × 16, R26–R40 × 15)"),
            ("GPU physics", f"P = {T.GPU_IDLE_W:.0f} W + ({T.GPU_TDP_W:.0f} − {T.GPU_IDLE_W:.0f}) · util^0.9 · T = T_coolant + 0.0275 °C/W · P · throttle at 87 °C"),
            ("Node power", f"8 GPUs + {T.NODE_BASE_W / 1000:.2f} kW base (CPU, DRAM, 8× CX-8, BlueField-3) scaled by host CPU"),
            ("Cooling", "88% of rack heat to liquid (CDU → FWS → towers / free-cooling HX), 12% + Hall C to air (CRAH → CHW → chillers)"),
            ("Power", "2N: KEPCO 154 kV ×2 → 40 MVA TR A/B → 22.9 kV MV → UPS A/B per hall (η curve) → busways → dual-corded racks"),
            ("Scheduler", "Slurm partitions train / infer / dev / batch · topology-aware placement · queue-depth driven arrivals · AWS burst"),
            ("Cost", "KEPCO 산업용(을) 고압C TOU billed per tick · 12-month history anchored to M1 build-out"),
            ("Alerts", f"{len(eng.alerts.rules)} rules · for-duration + 16 s resolve hysteresis · incident correlation by root cause / row"),
            ("Publishing", f"every tick: live + page views · every {config.HEAVY_EVERY_TICKS} ticks: large lists · every "
                           f"{config.ENTITY_EVERY_TICKS} ticks: detail entities · time series at tier cadence"),
        ],
        "codemap": [
            ("app/collector/", "collector process: runs the demo collector (simulator), publishes read models, serves the command bus"),
            ("app/readmodel/", "read-model builders — collected state → one dict per page / detail entity"),
            ("app/store.py", "Redis contract (key layout, lease, command bus) + in-process fallback"),
            ("app/sim/topology.py", "campus, halls, racks, 625 nodes, power & cooling chains, fabric, storage, K8s"),
            ("app/sim/fleet.py", "5,000-GPU vectorised physics, Slurm scheduler, MIG, XID/ECC health"),
            ("app/sim/facility.py", "2N power, liquid-first N+1 cooling, PUE/WUE/CUE, gensets, energy"),
            ("app/sim/itinfra.py · cloud.py · cost.py", "Storage Scale, fabrics, K8s · AWS → GCP → NHN · KEPCO TOU, budget"),
            ("app/sim/alerts.py · scenarios.py", "rules, incidents, Slack fan-out; 15 causal scenarios"),
            ("app/web/data.py", "web read path: views · entities · Redis time series · logs · command client"),
            ("app/web/routers/*", "page + API routers per domain — read Redis, send commands"),
            ("app/sim/agent.py", "Mission Control — Claude tool-use loop + offline analyst over the read models"),
        ],
    }
