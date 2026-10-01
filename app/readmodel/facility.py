from __future__ import annotations

import numpy as np

from .. import config
from ..sim import topology as T
from ..sim.fleet import G


def _status_level(s: str) -> str:
    s = (s or "").lower()
    if s in ("fault", "failed", "tripped", "lost", "down"):
        return "critical"
    if s in ("on-battery", "starting", "degraded", "maintenance", "cooldown", "online · genset"):
        return "warning"
    if s in ("standby", "planned"):
        return "idle"
    return "ok"


def overview(eng) -> dict:
    fs = eng.facility.snapshot
    L = eng.live
    halls = []
    for h in T.HALLS:
        hv = fs["halls"][h["id"]]
        racks = [r for r in T.RACKS if r.hall == h["id"]]
        halls.append({**hv, "racks": len(racks), "gpu_racks": sum(1 for r in racks if r.kind == "gpu"),
                      "cooling": h["cooling"]})
    stages_power = []
    for d in T.POWER_DEVICES:
        if d["kind"] in ("utility", "transformer", "ups"):
            st = _power_state(eng, d["id"])
            stages_power.append({"id": d["id"], "name": d["name"], "kind": d["kind"], "side": d["side"], **st})
    stages_cool = []
    for d in T.COOLING_DEVICES:
        if d["kind"] in ("chiller", "cdu"):
            st = _cooling_state(eng, d["id"])
            stages_cool.append({"id": d["id"], "name": d["name"], "kind": d["kind"], **st})
    return {
        "site": {k: fs[k] for k in ("it_mw", "facility_mw", "capacity_mw", "util_pct", "pue", "wue", "cue", "ambient",
                                     "breakdown_mw", "heat_mw")},
        "target_pue": config.TARGET_PUE,
        "power_redundancy": fs["power"]["redundancy"], "cooling_redundancy": fs["cooling"]["redundancy"],
        "halls": halls, "modules": T.MODULES, "power_stages": stages_power, "cooling_stages": stages_cool,
        "cooling": {k: fs["cooling"][k] for k in ("chw_supply_c", "chw_return_c", "fws_supply_c", "fws_return_c",
                                                   "free_cooling_pct", "tcs_supply_avg_c", "tcs_supply_max_c", "chillers_running")},
        "energy": fs["energy"], "rate": eng.cost.current_rate(),
        "alerts": [a for a in L["alerts"]["recent"] if True][:5],
        "sankey": energy_sankey(fs),
    }


def energy_sankey(fs: dict) -> list[list]:
    b = fs["breakdown_mw"]
    heat = fs["heat_mw"]
    mech = b["chillers"] + b["towers"] + b["pumps"] + b["crah"]
    return [
        ["KEPCO 154 kV", "Main TR A/B", round(fs["facility_mw"], 3)],
        ["Main TR A/B", "TR losses", b["tx_loss"]],
        ["Main TR A/B", "UPS A/B", round(b["it"] + b["ups_loss"], 3)],
        ["Main TR A/B", "Mechanical", round(mech, 3)],
        ["Main TR A/B", "Lighting · office", b["misc"]],
        ["UPS A/B", "UPS losses", b["ups_loss"]],
        ["UPS A/B", "IT load", b["it"]],
        ["IT load", "Liquid · CDU", heat["liquid"]],
        ["IT load", "Air · CRAH", round(max(0.0, b["it"] - heat["liquid"]), 3)],
        ["Mechanical", "Chillers", b["chillers"]],
        ["Mechanical", "Towers · fans", b["towers"]],
        ["Mechanical", "Pumps", b["pumps"]],
        ["Mechanical", "CRAH fans", b["crah"]],
    ]


def _power_state(eng, did: str) -> dict:
    p = eng.facility.snapshot["power"]
    d = T.POWER_BY_ID[did]
    if d["kind"] == "utility":
        u = p["utility"][did]
        return {"status": u["status"], "level": _status_level(u["status"]), "load_mw": u["mw"],
                "load_pct": round(u["mw"] / d["rating_mw"] * 100, 1), "detail": f"{u['kv']} kV"}
    if d["kind"] == "transformer":
        t = p["tx"][did]
        return {"status": "energized", "level": "ok", "load_mw": t["load_mw"], "load_pct": t["load_pct"],
                "detail": f"oil {t['temp_c']} °C · loss {t['loss_mw'] * 1000:.0f} kW"}
    if d["kind"] == "switchgear":
        side = d["side"]
        live = p["utility"]["UTIL-1" if side == "A" else "UTIL-2"]["status"] == "energized"
        return {"status": "closed" if live else "on-genset", "level": "ok" if live else "warning",
                "load_mw": p["side_mw"][side], "load_pct": round(p["side_mw"][side] / d["rating_mw"] * 100, 1),
                "detail": f"{p['pq']['mv_kv']} kV · PF {p['pq']['pf']}"}
    if d["kind"] == "ups":
        u = p["ups"][did]
        return {"status": u["status"], "level": _status_level(u["status"]), "load_mw": u["load_mw"],
                "load_pct": u["load_pct"], "detail": f"η {u['eff']}% · SOC {u['soc']:.0f}% · {u['runtime_min']} min"}
    if d["kind"] == "busway":
        b = p["busway"][did]
        return {"status": "energized", "level": "warning" if b["load_pct"] > 80 else "ok", "load_mw": round(b["load_kw"] / 1000, 3),
                "load_pct": b["load_pct"], "detail": f"{b['load_kw']:.0f} kW"}
    g = p["gens"][did]
    return {"status": g["status"], "level": _status_level(g["status"]) if g["status"] != "running" else "warning",
            "load_mw": g["load_mw"], "load_pct": round(g["load_mw"] / d["rating_mw"] * 100, 1),
            "detail": f"fuel {g['fuel_pct']:.0f}%"}


def _cooling_state(eng, did: str) -> dict:
    c = eng.facility.snapshot["cooling"]
    d = T.COOLING_BY_ID[did]
    if d["kind"] == "chiller":
        ch = c["chillers"][did]
        return {"status": ch["status"], "level": _status_level(ch["status"]) if ch["status"] != "standby" else "idle",
                "load_pct": ch["load_pct"], "detail": f"COP {ch['cop']} · {ch['kw']:.0f} kW · LWT {ch['leaving_c']} °C",
                "kw": ch["kw"], "run_h": round(ch["run_h"])}
    if d["kind"] == "cdu":
        cd = c["cdus"][did]
        det = f"{cd['supply_c']}→{cd['return_c']} °C · {cd['flow_lpm']:.0f} L/min"
        if cd.get("covering"):
            det = f"covering row {cd['covering']} · " + det
        return {"status": cd["status"], "level": "critical" if cd["status"] == "failed" or cd["leak"] else
                ("idle" if cd["status"] == "standby" else "ok"), "load_pct": cd["load_pct"], "detail": det,
                "leak": cd["leak"]}
    if d["kind"] == "tower":
        tw = c["towers"][did]
        return {"status": tw["status"], "level": "ok" if tw["status"] == "running" else "idle",
                "load_pct": tw["fan_pct"], "detail": f"fan {tw['fan_pct']}%"}
    if d["kind"] == "crah":
        cr = c["crah"][did]
        return {"status": "running", "level": "ok", "load_pct": cr["fan_pct"],
                "detail": f"supply {cr['supply_c']} °C · return {cr['return_c']} °C"}
    return {"status": "running" if c["free_cooling_pct"] > 0 else "bypass", "level": "ok",
            "load_pct": c["free_cooling_pct"], "detail": f"free cooling {c['free_cooling_pct']}%"}


def power(eng) -> dict:
    fs = eng.facility.snapshot
    p = fs["power"]
    groups = {}
    for d in T.POWER_DEVICES:
        if d.get("planned"):
            continue
        groups.setdefault(d["kind"], []).append({**{k: d.get(k) for k in ("id", "name", "side", "hall", "row", "rating_mw", "vendor")},
                                                 **_power_state(eng, d["id"])})
    halls = []
    for h in ("HA", "HB", "HC"):
        a, b = p["ups"][f"UPS-A-{h}"], p["ups"][f"UPS-B-{h}"]
        halls.append({"hall": h, "name": T.HALL_BY_ID[h]["name"], "it_mw": fs["halls"][h]["it_mw"],
                      "a": {"id": f"UPS-A-{h}", **a}, "b": {"id": f"UPS-B-{h}", **b}})
    rack_kw = [{"rack": r.id, "kw": round(float(eng.rack_kw_vec[i]), 1), "design_kw": r.design_kw, "row": r.row, "hall": r.hall}
               for i, r in enumerate(T.GPU_RACK_LIST)]
    for rk, kw in eng.hallc.items():
        r = T.RACK_BY_ID[rk]
        rack_kw.append({"rack": rk, "kw": round(kw, 1), "design_kw": r.design_kw, "row": r.row, "hall": r.hall})
    hist = np.histogram([r["kw"] for r in rack_kw], bins=[0, 20, 40, 60, 90, 120, 140, 160, 180, 220])
    return {
        "redundancy": p["redundancy"], "side_mw": p["side_mw"], "pq": p["pq"], "utility": p["utility"],
        "it_mw": fs["it_mw"], "facility_mw": fs["facility_mw"], "ups_loss_mw": fs["breakdown_mw"]["ups_loss"],
        "groups": groups, "halls": halls,
        "gens_running": sum(1 for g in p["gens"].values() if g["status"] == "running"),
        "rack_density": [{"bin": f"{int(hist[1][i])}–{int(hist[1][i + 1])} kW", "count": int(c)} for i, c in enumerate(hist[0])],
        "top_racks": sorted(rack_kw, key=lambda r: -r["kw"])[:10],
        "energy": fs["energy"], "rate": eng.cost.current_rate(),
    }


def power_device(eng, did: str) -> dict | None:
    d = T.POWER_BY_ID.get(did.upper())
    if not d:
        return None
    did = d["id"]
    st = _power_state(eng, did) if not d.get("planned") else {"status": "planned", "level": "idle", "load_mw": 0,
                                                              "load_pct": 0, "detail": "not yet installed"}
    children = [c for c in T.POWER_DEVICES if c.get("parent") == did]
    parent = T.POWER_BY_ID.get(d.get("parent") or "")
    series = None
    if d["kind"] == "ups" and not d.get("planned"):
        m = eng.tsdb.metrics["ups_load_pct"]
        series = {"metric": "ups_load_pct", "col": m.column(ups=did), "label": "Load %"}
    elif d["kind"] in ("utility", "transformer", "switchgear"):
        series = {"metric": "power_side_mw", "col": 0 if d["side"] == "A" else 1, "label": f"{d['side']}-path MW"}
    return {"device": d, "state": st, "parent": parent, "children": children,
            "series": series, "redundancy": eng.facility.snapshot["power"]["redundancy"],
            "peer": _peer(d), "events": [e for e in eng.events if did in e["text"]][:12]}


def _peer(d: dict) -> str | None:
    if d.get("side") in ("A", "B") and d["kind"] in ("utility", "transformer", "switchgear", "ups", "busway"):
        other = "B" if d["side"] == "A" else "A"
        cand = d["id"].replace(f"-{d['side']}-", f"-{other}-").replace(f"-{d['side']}", f"-{other}") \
            if d["kind"] != "utility" else ("UTIL-2" if d["id"] == "UTIL-1" else "UTIL-1")
        if d["kind"] == "busway":
            cand = d["id"][:-1] + other
        return cand if cand in T.POWER_BY_ID else None
    return None


def cooling(eng) -> dict:
    fs = eng.facility.snapshot
    c = fs["cooling"]
    rows = []
    for row, cdu in T.ROW_CDU.items():
        racks = [r for r in T.GPU_RACK_LIST if r.row == row]
        idx = [T.RACK_INDEX[r.id] for r in racks]
        f = eng.fleet
        gmask = np.isin(f.gpu_rack, idx)
        rows.append({"row": row, "hall": "H" + row[0], "cdu": cdu, "cdu_status": c["cdus"][cdu]["status"],
                     "supply_c": c["row_supply_c"][row], "return_c": c["row_return_c"][row],
                     "heat_kw": round(float(eng.rack_kw_vec[idx].sum()) * 0.88, 0),
                     "gpu_temp_max": round(float(f.temp[gmask].max()), 1), "gpu_temp_avg": round(float(f.temp[gmask].mean()), 1),
                     "throttling": int((f.throttle[gmask] == 1).sum()), "racks": [r.id for r in racks]})
    groups = {}
    for d in T.COOLING_DEVICES:
        groups.setdefault(d["kind"], []).append({**{k: d.get(k) for k in ("id", "name", "vendor", "capacity_mw", "hall", "row")},
                                                 **_cooling_state(eng, d["id"])})
    return {"summary": {k: c[k] for k in ("redundancy", "chw_supply_c", "chw_return_c", "fws_supply_c", "fws_return_c",
                                          "free_cooling_pct", "tcs_supply_avg_c", "tcs_supply_max_c", "chillers_running",
                                          "chiller_load_mw", "cooling_kw", "water_lph")},
            "ambient": fs["ambient"], "heat_mw": fs["heat_mw"], "wue": fs["wue"], "pue": fs["pue"],
            "rows": rows, "groups": groups, "halls": fs["halls"]}


def cooling_device(eng, did: str) -> dict | None:
    d = T.COOLING_BY_ID.get(did.upper())
    if not d:
        return None
    did = d["id"]
    st = _cooling_state(eng, did)
    extra = {}
    series = None
    if d["kind"] == "cdu":
        extra["raw"] = eng.facility.snapshot["cooling"]["cdus"][did]
        row = d.get("row") or extra["raw"].get("covering")
        if row:
            m = eng.tsdb.metrics["cooling_tcs_supply_c"]
            series = {"metric": "cooling_tcs_supply_c", "col": m.column(row=row), "label": f"Row {row} TCS supply °C"}
            extra["racks"] = [r.id for r in T.GPU_RACK_LIST if r.row == row]
        m2 = eng.tsdb.metrics["cdu_load_pct"]
        extra["load_series"] = {"metric": "cdu_load_pct", "col": m2.column(cdu=did)}
    elif d["kind"] == "chiller":
        extra["raw"] = eng.facility.snapshot["cooling"]["chillers"][did]
        series = {"metric": "cooling_chw_supply_c", "col": 0, "label": "CHW supply °C"}
    elif d["kind"] == "crah":
        extra["raw"] = eng.facility.snapshot["cooling"]["crah"][did]
        m = eng.tsdb.metrics["hall_inlet_c"]
        series = {"metric": "hall_inlet_c", "col": m.column(hall=d["hall"]), "label": "Hall inlet °C"}
    else:
        series = {"metric": "cooling_fws_supply_c", "col": 0, "label": "FWS supply °C"}
    return {"device": d, "state": st, "series": series, **extra,
            "events": [e for e in eng.events if did in e["text"]][:12]}


def capacity(eng) -> dict:
    fs = eng.facility.snapshot
    f = eng.fleet
    halls = []
    for h in T.HALLS:
        hid = h["id"]
        racks = [r for r in T.RACKS if r.hall == hid]
        design = h["design_mw"] * 1000
        used = fs["halls"][hid]["it_mw"] * 1000
        alloc = sum(r.design_kw for r in racks if r.kind != "reserved")
        halls.append({"id": hid, "name": h["name"], "purpose": h["purpose"], "design_kw": design, "used_kw": round(used),
                      "allocated_kw": alloc, "racks": len(racks), "racks_used": sum(1 for r in racks if r.kind != "reserved"),
                      "stranded_kw": max(0, round(alloc - used)), "free_kw": round(max(0.0, design - used)),
                      "util_pct": round(used / design * 100, 1)})
    node_kw_peak = G * 1.1 + 2.35 + 0.3
    rack_peak = node_kw_peak * 16 + 2.2
    headroom_kw = sum(h["free_kw"] for h in halls if h["id"] in ("HA", "HB", "HD")) * 0.9
    reserved = sum(1 for r in T.RACKS if r.kind == "reserved")
    addable = min(int(headroom_kw // rack_peak), reserved)
    return {
        "campus_mw": T.CAMPUS_MW, "module_mw": T.MODULE_MW, "modules": T.MODULES, "buildout": T.BUILDOUT,
        "m1": {"design_mw": T.MODULE_MW, "it_mw": fs["it_mw"], "util_pct": fs["util_pct"],
               "gpu_peak_mw": round((T.GPU_COUNT * T.GPU_TDP_W + T.NODE_COUNT * T.NODE_BASE_W) / 1e6, 2)},
        "halls": halls,
        "planner": {"node_peak_kw": round(node_kw_peak, 2), "rack_nodes": 16, "rack_peak_kw": round(rack_peak, 1),
                    "headroom_kw": round(headroom_kw), "power_limited_racks": int(headroom_kw // rack_peak),
                    "space_limited_racks": reserved, "addable_racks": addable, "addable_gpus": addable * 16 * G,
                    "binding": "floor space (Hall D positions)" if addable == reserved else "power",
                    "cooling_headroom_mw": round(sum(1 for c in T.COOLING_DEVICES if c["kind"] == "chiller") * 4.9 - fs["cooling"]["chiller_load_mw"] - 4.9, 2)},
        "fleet": {"gpus": T.GPU_COUNT, "nodes": T.NODE_COUNT, "racks": T.GPU_RACKS, "alloc_pct": round(float((f.gpu_job >= 0).mean() * 100), 1)},
        "space": {"racks_total": len(T.RACKS), "racks_reserved": sum(1 for r in T.RACKS if r.kind == "reserved")},
    }


def hall(eng, hid: str) -> dict | None:
    h = T.HALL_BY_ID.get(hid.upper())
    if not h:
        return None
    hid = h["id"]
    fs = eng.facility.snapshot
    f = eng.fleet
    rows = []
    for row in [r for r in T.ROWS if r["hall"] == hid]:
        racks = []
        for rk in [r for r in T.RACKS if r.row == row["id"]]:
            if rk.kind == "gpu":
                i = T.RACK_INDEX[rk.id]
                gm = f.gpu_rack == i
                racks.append({"id": rk.id, "kind": "gpu", "label": rk.label, "kw": round(float(eng.rack_kw_vec[i]), 1),
                              "temp_max": round(float(f.temp[gm].max()), 1), "util": round(float(f.util[gm].mean()), 1),
                              "throttle": int((f.throttle[gm] == 1).sum()), "failed": int((f.health[gm] == 2).sum()),
                              "design_kw": rk.design_kw})
            else:
                racks.append({"id": rk.id, "kind": rk.kind, "label": rk.label, "kw": round(eng.hallc.get(rk.id, 0.0), 1),
                              "temp_max": None, "util": None, "throttle": 0, "failed": 0, "design_kw": rk.design_kw})
        rows.append({"id": row["id"], "kind": row["kind"], "cdu": row.get("cdu"),
                     "cdu_status": fs["cooling"]["cdus"].get(row.get("cdu") or "", {}).get("status"),
                     "supply_c": fs["cooling"]["row_supply_c"].get(row["id"]), "racks": racks})
    crah = {k: v for k, v in fs["cooling"]["crah"].items() if v["hall"] == hid}
    return {"hall": h, "state": fs["halls"][hid], "rows": rows, "crah": crah,
            "ups": {k: v for k, v in fs["power"]["ups"].items() if v.get("hall") == hid}}


def energy(eng) -> dict:
    fs = eng.facility.snapshot
    e = fs["energy"]
    rate = eng.cost.current_rate()
    return {"pue": fs["pue"], "wue": fs["wue"], "cue": fs["cue"], "target_pue": config.TARGET_PUE,
            "energy": e, "ambient": fs["ambient"], "breakdown_mw": fs["breakdown_mw"], "sankey": energy_sankey(fs),
            "rate": rate, "grid_factor": 0.4594, "free_cooling_pct": fs["cooling"]["free_cooling_pct"],
            "today_krw": round(eng.cost.today_power_krw),
            "renewable": {"ppa_mw": 0.0, "rec_pct": 12.0, "note": "REC purchases cover 12% of consumption (assumed)"}}
