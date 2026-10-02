from __future__ import annotations

import numpy as np

from ..sim import topology as T
from ..sim.fleet import G, N_NODE, THROTTLE_C, XID_CODES
from ..sim.platform import CHARGEBACK_KRW_PER_GPU_HR

HEAT_METRICS = {"util": ("util", "%", 0, 100), "temp": ("temp", "°C", 25, 92), "power": ("power", "W", 100, 1150),
                "mem": ("mem", "GB", 0, 288), "sm": ("sm", "%", 0, 100)}


# ================================================================ GPU fleet
def gpu_fleet(eng) -> dict:
    f = eng.fleet
    s = f.summary(eng.now)
    idle_cost_hr = s["idle_allocated"] * CHARGEBACK_KRW_PER_GPU_HR
    monitors = [
        _monitor("GPU thermal throttling", s["thermal_throttle"] > 8, f"{s['thermal_throttle']} GPUs ≥ {THROTTLE_C:.0f} °C", "it.gpu"),
        _monitor("Fatal XID (48 / 79 / 95)", any(c in (48, 79, 95) for t, _, c in f.xid_ts if t > eng.now - 3600),
                 f"{s['xid_1h']} XID events in 1 h", "it.gpu"),
        _monitor("Double-bit ECC", s["ecc_dbe_total"] > 0, f"{s['ecc_dbe_total']} DBE total", "it.gpu"),
        _monitor("Idle allocated GPUs", s["idle_allocated"] > 260, f"{s['idle_allocated']} idle · ₩{idle_cost_hr:,.0f}/h", "it.gpu"),
        _monitor("Power-cap throttling", s["power_throttle"] > 400, f"{s['power_throttle']} GPUs at TDP cap", "it.gpu"),
        _monitor("Unavailable nodes (drain/down)", s["node_states"]["drain"] + s["node_states"]["down"] > 3,
                 f"{s['node_states']['drain']} drain · {s['node_states']['down']} down", "platform"),
        _monitor("Queue backlog", s["pending_gpus"] > 3200, f"{s['pending_gpus']:,} GPUs pending", "platform"),
        _monitor("NVLink degraded", False, f"{s['nvlink_tbs']} TB/s aggregate", "it.gpu"),
    ]
    usage = f.project_usage()
    recs = []
    for p in sorted(usage, key=lambda x: -x["idle_gpu_hours_today"]):
        if p["idle_gpu_hours_today"] > 20:
            recs.append({"kind": "reclaim", "title": f"Reclaim idle GPUs in {p['id']}",
                         "detail": f"{p['idle_gpu_hours_today']:,.0f} idle GPU-hours today ≈ ₩{p['idle_gpu_hours_today'] * CHARGEBACK_KRW_PER_GPU_HR:,.0f}. "
                                   "Enable 60-min idle culling for its RCS / notebook sessions.", "href": f"/gpu-platform/ops?tab=projects"})
    if s["power_throttle"] > 200:
        recs.append({"kind": "tune", "title": "Pretrain jobs are pinned at the 1,100 W cap",
                     "detail": f"{s['power_throttle']} GPUs run at TDP. With liquid headroom, a 1,200 W power-profile on train SUs SU01–SU04 (R01–R16) buys ~4% throughput.",
                     "href": "/gpu-fleet?tab=performance"})
    hot = int(np.argmax(f.temp))
    if f.temp[hot] > 78:
        recs.append({"kind": "inspect", "title": f"Inspect {T.NODE_RACK[hot // G]} cooling",
                     "detail": f"{T.gpu_id(hot)} peaks {f.temp[hot]:.1f} °C at coolant {f.coolant[hot]:.1f} °C.", "href": f"/rack/{T.NODE_RACK[hot // G]}"})
    if s["pending_gpus"] > 2000:
        recs.append({"kind": "burst", "title": "Offload fine-tunes to the AWS Capacity Block",
                     "detail": f"{s['jobs_pending']} jobs wait for {s['pending_gpus']:,} GPUs; the active block has spare p6-b200 capacity.",
                     "href": "/cloud/aws"})
    mix = {}
    for j in f.jobs.values():
        if j.state == "RUNNING":
            mix[j.profile] = mix.get(j.profile, 0) + len(j.gpus)
    return {
        "summary": s, "funnel": [
            {"stage": "Total", "gpus": s["total"]}, {"stage": "Available", "gpus": s["total"] - s["unavailable"]},
            {"stage": "Allocated", "gpus": s["allocated"]}, {"stage": "Active (>5% util)", "gpus": s["active"]},
            {"stage": "Effective (SM ≥ 40%)", "gpus": s["effective"]}],
        "idle": {"gpus": s["idle_allocated"], "cost_hr_krw": idle_cost_hr, "cost_day_krw": idle_cost_hr * 24},
        "monitors": monitors, "recommendations": recs[:5], "partitions": f.partition_summary(), "projects": usage,
        "workload_mix": [{"profile": k, "gpus": v} for k, v in sorted(mix.items(), key=lambda x: -x[1])],
        "device_mix": [{"device": "NVIDIA B300 · HGX 8-GPU (on-prem)", "gpus": T.GPU_COUNT},
                       {"device": "AWS p6-b200 / p5en", "gpus": eng.live["cloud"]["aws"]["gpus"]},
                       {"device": "NHN H100 / A100 / L40S", "gpus": eng.live["cloud"]["nhn"]["gpus"]}],
        "xid_recent": [{"t": t, "gpu": T.gpu_id(gi), "code": c, "desc": XID_CODES[c][0], "fatal": XID_CODES[c][1] >= 2}
                       for t, gi, c in list(f.xid_ts)[-12:][::-1]],
        "racks": rack_matrix(eng),
    }


def _monitor(name: str, alert: bool, detail: str, cat: str) -> dict:
    return {"name": name, "status": "alert" if alert else "ok", "detail": detail, "category": cat}


def rack_matrix(eng) -> list[dict]:
    f = eng.fleet
    out = []
    for i, rk in enumerate(T.GPU_RACK_LIST):
        gm = f.gpu_rack == i
        out.append({"id": rk.id, "row": rk.row, "hall": rk.hall, "su": rk.extra["su"], "partition": T.RACK_PARTITION[rk.id],
                    "kw": round(float(eng.rack_kw_vec[i]), 1), "util": round(float(f.util[gm].mean()), 1),
                    "temp_max": round(float(f.temp[gm].max()), 1), "throttle": int((f.throttle[gm] == 1).sum()),
                    "failed": int((f.health[gm] == 2).sum()), "alloc": int((f.gpu_job[gm] >= 0).sum()), "gpus": int(gm.sum())})
    return out


def heatmap(eng, metric: str) -> dict:
    f = eng.fleet
    key, unit, lo, hi = HEAT_METRICS.get(metric, HEAT_METRICS["util"])
    vec = getattr(f, key)
    cols = T.NODES_PER_RACK * G
    grid = np.full((T.GPU_RACKS, cols), -1.0, np.float32)
    for n in range(N_NODE):
        r = T.NODE_RACK_IDX[n]
        s = T.NODE_SLOT[n] - 1
        grid[r, s * G:(s + 1) * G] = vec[n * G:(n + 1) * G]
    status = np.zeros((T.GPU_RACKS, cols), np.int8)
    for n in range(N_NODE):
        r, s = T.NODE_RACK_IDX[n], T.NODE_SLOT[n] - 1
        st = f.node_state[n]
        code = np.where(f.health[n * G:(n + 1) * G] == 2, 3, np.where(f.throttle[n * G:(n + 1) * G] == 1, 2, 0))
        if st in ("drain", "down"):
            code = np.maximum(code, 4 if st == "down" else 1)
        status[r, s * G:(s + 1) * G] = code
    return {"metric": metric, "unit": unit, "min": lo, "max": hi, "racks": [r.id for r in T.GPU_RACK_LIST],
            "sus": [r.extra["su"] for r in T.GPU_RACK_LIST], "group": T.RACKS_PER_SU, "per": G,
            "cols": cols, "values": np.round(grid, 1).ravel().tolist(), "status": status.ravel().tolist(),
            "legend": {"0": "ok", "1": "drain", "2": "thermal throttle", "3": "failed", "4": "down"}}


def gpu_nodes(eng, q: str = "", state: str = "", partition: str = "", rack: str = "", sort: str = "id", limit: int = 700) -> dict:
    rows = eng.fleet.node_rows(eng.now)
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["id"] or ql in r["job"].lower() or ql in r["user"].lower() or ql in r["project"].lower()]
    if state:
        rows = [r for r in rows if r["state"] == state]
    if partition:
        rows = [r for r in rows if r["partition"] == partition]
    if rack:
        rows = [r for r in rows if r["rack"] == rack.upper()]
    key = {"util": lambda r: -r["util"], "temp": lambda r: -r["temp"], "power": lambda r: -r["power_kw"],
           "mem": lambda r: -r["mem_gb"]}.get(sort)
    if key:
        rows.sort(key=key)
    return {"total": len(rows), "rows": rows[:limit]}


def gpu_node(eng, node_id: str) -> dict | None:
    n = T.NODE_INDEX.get(node_id.lower())
    if n is None:
        return None
    f = eng.fleet
    rec = f.node_record(n, eng.now)
    gpus = [f.gpu_record(n * G + g, eng.now) for g in range(G)]
    rk = T.RACK_BY_ID[rec["rack"]]
    neighbors = []
    for nn in range(rk.node_start, rk.node_start + rk.node_count):
        neighbors.append({"id": T.NODE_IDS[nn], "slot": T.NODE_SLOT[nn], "state": str(f.node_state[nn]),
                          "util": round(float(f.util[nn * G:(nn + 1) * G].mean()), 1),
                          "temp": round(float(f.temp[nn * G:(nn + 1) * G].max()), 1), "self": nn == n})
    eth = eng.network.dev[rk.eth_leaf]
    m_util = eng.tsdb.metrics["node_gpu_util"]
    return {"node": rec, "gpus": gpus, "neighbors": neighbors,
            "fabric": {"ib_leaf": ib_rails(eng, rk), "ib_rails": ib_rails(eng, rk, detail=True),
                       "eth_leaf": {"id": rk.eth_leaf, **{k: eth[k] for k in ("util_pct", "status", "errors", "discards")}}},
            "cooling": {"cdu": rk.cdu, "cdu_status": eng.facility.cdu[rk.cdu]["status"],
                        "supply_c": round(eng.facility.row_supply[rk.row], 1)},
            "power": {"busway_a": f"BW-{rk.row}-A", "busway_b": f"BW-{rk.row}-B", "ups_a": f"UPS-A-{rk.hall}", "ups_b": f"UPS-B-{rk.hall}"},
            "series_col": n, "series_metric": [m.name for m in (m_util,)],
            "slurm": {"partition": rec["partition"], "state": rec["state"], "reason": rec["reason"],
                      "features": ["b300", "hgx8", "cx8", "liquid", rk.extra["su"].lower(), T.RACK_PARTITION[rec["rack"]]],
                      "gres": "gpu:b300:8"}}


def ib_rails(eng, rk, detail: bool = False):
    """A GPU rack's 8 InfiniBand rails (one Quantum-X800 leaf each). Summary = the worst rail, so a flap on any
    rail of the SU shows up on every rack and node in it."""
    rails = [{"id": lid, "rail": i + 1, **{k: eng.network.dev[lid][k] for k in ("util_pct", "links_down", "status", "errors")}}
             for i, lid in enumerate(rk.extra["ib_leaves"])]
    if detail:
        return rails
    worst = max(rails, key=lambda r: (r["links_down"], r["status"] != "up", r["util_pct"]))
    return {**worst, "rails": len(rails), "su": rk.extra["su"]}


def gpu_device(eng, gid: str) -> dict | None:
    gi = T.parse_gpu_id(gid.lower())
    if gi is None:
        return None
    f = eng.fleet
    rec = f.gpu_record(gi, eng.now)
    n = gi // G
    siblings = [{"id": T.gpu_id(n * G + g), "slot": g, "util": round(float(f.util[n * G + g]), 1),
                 "temp": round(float(f.temp[n * G + g]), 1), "self": g == gi % G} for g in range(G)]
    xids = [{"t": t, "code": c, "desc": XID_CODES[c][0]} for t, g2, c in f.xid_ts if g2 == gi][-10:][::-1]
    return {"gpu": rec, "siblings": siblings, "xids": xids, "series_col": gi,
            "limits": {"tdp_w": T.GPU_TDP_W, "throttle_c": THROTTLE_C, "hbm_gb": T.GPU_HBM_GB}}


def gpu_job(eng, jid: str) -> dict | None:
    f = eng.fleet
    try:
        j = f.jobs.get(int(jid))
    except ValueError:
        return None
    if j is None:
        fin = next((x for x in f.finished if x["id"] == str(jid)), None)
        return {"job": fin, "finished": True, "gpus": []} if fin else None
    pub = j.public(eng.now)
    idx = np.array(j.gpus) if j.gpus else np.array([], int)
    per_node = []
    for n in j.nodes[:64]:
        gsl = slice(n * G, (n + 1) * G)
        per_node.append({"node": T.NODE_IDS[n], "rack": T.NODE_RACK[n], "util": round(float(f.util[gsl].mean()), 1),
                         "temp": round(float(f.temp[gsl].max()), 1), "power_kw": round(float(f.node_power[n]) / 1000, 2),
                         "throttle": int((f.throttle[gsl] > 0).sum())})
    return {"job": pub, "finished": False,
            "stats": {"util": round(float(f.util[idx].mean()), 1) if len(idx) else 0, "temp_max": round(float(f.temp[idx].max()), 1) if len(idx) else 0,
                      "power_kw": round(float(f.power[idx].sum()) / 1000, 1) if len(idx) else 0,
                      "mem_gb": round(float(f.mem[idx].sum()), 0) if len(idx) else 0,
                      "throttling": int((f.throttle[idx] > 0).sum()) if len(idx) else 0},
            "nodes": per_node, "racks": sorted({T.NODE_RACK[n] for n in j.nodes})}


def gpu_pod(eng, name: str) -> dict | None:
    for gi, inst in eng.fleet.mig.items():
        for x in inst:
            if x["pod"] == name:
                return {"pod": x, "gpu": eng.fleet.gpu_record(gi, eng.now), "kind": "mig-inference",
                        "siblings": inst}
    for p in eng.k8s.pods:
        if p["name"] == name:
            return {"pod": p, "gpu": None, "kind": "k8s", "siblings": []}
    return None


# ================================================================ storage
def storage(eng) -> dict:
    s = eng.storage.summary()
    vols = sorted(eng.storage.volumes, key=lambda v: -(v["iops_k"]))
    return {"summary": {k: s[k] for k in ("used_pb", "total_pb", "used_pct", "read_gbs", "write_gbs", "iops_k", "latency_ms")},
            "clusters": [{"id": c["id"], "product": c["product"], "racks": c["racks"], "peak_read_gbs": c["peak_read_gbs"],
                          "peak_write_gbs": c["peak_write_gbs"], **s["clusters"][c["id"]]} for c in T.STORAGE_CLUSTERS],
            "toptalkers": vols[:10], "ckpt_jobs": len(eng.fleet.ckpt_jobs), "blocks": storage_blocks(eng, s)}


def storage_blocks(eng, s: dict) -> list[dict]:
    """One hot + one cold IBM building block per SU. NSD pairs go down from the last block (see storage_cluster)."""
    out = []
    for u in T.SUS:
        row = {"su": u["id"], "partition": T.RACK_PARTITION[u["racks"][0]], "gpu_racks": f"{u['racks'][0]}–{u['racks'][-1]}"}
        for c in T.STORAGE_CLUSTERS:
            live = s["clusters"][c["id"]]
            per = live["nsd_total"] // T.SU_COUNT
            up = (u["index"] + 1) * per <= live["nsd_up"]
            racks = u[f"{c['tier']}_racks"]
            row[c["tier"]] = {"racks": racks[0] if len(racks) == 1 else f"{racks[0]}–{racks[-1]}", "pb": c["per_su_pb"],
                              "status": "up" if up else "down", "read_gbs": round(live["read_gbs"] / T.SU_COUNT, 1)}
        out.append(row)
    return out


def storage_cluster(eng, cid: str) -> dict | None:
    spec = T.STORAGE_BY_ID.get(cid)
    if not spec:
        return None
    s = eng.storage.summary()["clusters"][cid]
    vols = sorted((v for v in eng.storage.volumes if v["cluster"] == cid), key=lambda v: -v["iops_k"])
    m = eng.tsdb.metrics["storage_volume_iops_k"]
    cols = [m.column(volume=v["id"]) for v in vols]
    per_block = s["nsd_total"] // T.SU_COUNT
    nsd = [{"id": f"nsd-{cid.split('-')[1]}-{i + 1:02d}", "status": "up" if i < s["nsd_up"] else "down",
            "su": T.SUS[i // per_block]["id"], "rack": T.SUS[i // per_block][f"{spec['tier']}_racks"][0]}
           for i in range(s["nsd_total"])]
    return {"cluster": {**spec, **s}, "volumes": vols, "volume_cols": cols,
            "cluster_col": [c["id"] for c in T.STORAGE_CLUSTERS].index(cid), "nsd": nsd}


def storage_toptalkers(eng) -> dict:
    vols = sorted(eng.storage.volumes, key=lambda v: -(v["read_gbs"] + v["write_gbs"]))
    return {"volumes": vols}


# ================================================================ network
def _dev_row(eng, d: dict) -> dict:
    live = eng.network.dev[d["id"]]
    return {**{k: d.get(k) for k in ("id", "fabric", "tier", "vendor", "model", "ports", "speed_g", "rack", "role")}, **live}


def network(eng) -> dict:
    net = eng.network.summary()
    devs = [_dev_row(eng, d) for d in T.NET_DEVICES]
    uplinks = []
    for d in T.ETH_LEAVES + T.IB_LEAVES:
        live = eng.network.dev[d["id"]]
        n_up = 8 if d["fabric"] == "ethernet" else T.NODES_PER_SU
        cap = n_up * d["speed_g"]
        uplinks.append({"device": d["id"], "fabric": d["fabric"], "rack": d.get("su") or d.get("rack"),
                        "uplinks": n_up, "capacity_gbps": cap,
                        "in_gbps": live["in_gbps"], "out_gbps": live["out_gbps"], "util_pct": live["util_pct"],
                        "status": live["status"], "links_down": live["links_down"]})
    talkers = sorted(devs, key=lambda x: -(x["in_gbps"] + x["out_gbps"]))[:12]
    return {"summary": net, "devices": devs, "uplinks": sorted(uplinks, key=lambda u: -u["util_pct"]),
            "toptalkers": talkers, "topology": topology(eng), "flows": flows(eng)}


def topology(eng) -> dict:
    nodes, links = [], []
    # IB leaves are listed by rail plane (all rail-1 leaves of the 12 SUs, then rail 2 …) so each plane's
    # leaf → spine links stay in their own column block when drawn
    order = (T.ETH_SPINES + T.ETH_LEAVES + T.IB_SPINES
             + sorted(T.IB_LEAVES, key=lambda d: (d["plane"], d["su"])))
    for d in order:
        live = eng.network.dev[d["id"]]
        nodes.append({"id": d["id"], "fabric": d["fabric"], "tier": d["tier"], "util": live["util_pct"], "status": live["status"],
                      "group": d.get("plane"), "su": d.get("su")})
    for leaf in T.ETH_LEAVES:
        for sp in T.ETH_SPINES:
            links.append({"a": leaf["id"], "b": sp["id"], "fabric": "ethernet",
                          "util": round(eng.network.dev[leaf["id"]]["util_pct"] * 0.9, 1)})
    for leaf in T.IB_LEAVES:
        d = eng.network.dev[leaf["id"]]
        plane = T.IB_PLANE_SPINES[leaf["plane"]]
        down = {plane[i // T.IB_LINKS_PER_SPINE] for i in range(d["links_down"])}
        for sp in plane:
            links.append({"a": leaf["id"], "b": sp, "fabric": "infiniband", "util": d["util_pct"], "down": sp in down})
    return {"nodes": nodes, "links": links}


def flows(eng) -> list[dict]:
    f = eng.fleet
    out = []
    for j in sorted((j for j in f.jobs.values() if j.state == "RUNNING" and len(j.nodes) >= 8), key=lambda j: -len(j.nodes))[:6]:
        tb = float(f.node_ib[j.nodes].sum()) / 1000
        racks = sorted({T.NODE_RACK[n] for n in j.nodes})
        out.append({"src": f"{j.name} ({racks[0]}–{racks[-1]})", "dst": "all-reduce · IB fabric", "fabric": "infiniband",
                    "gbps": round(tb * 1000, 0), "job": j.id})
    st = eng.storage.clusters["ss-hot"]
    out.append({"src": f"GPU racks R01–R{T.GPU_RACKS:02d} · {T.SU_COUNT} SU", "dst": "ss-hot (read)", "fabric": "ethernet", "gbps": round(st["read_gbs"] * 8, 0)})
    out.append({"src": "ckpt writers", "dst": "ss-hot (write)", "fabric": "ethernet", "gbps": round(st["write_gbs"] * 8, 0)})
    b = eng.network.border
    out.append({"src": "border leaves", "dst": "AWS Direct Connect", "fabric": "ethernet", "gbps": b["aws_dx_gbps"]})
    out.append({"src": "border leaves", "dst": "GCP Interconnect", "fabric": "ethernet", "gbps": b["gcp_ic_gbps"]})
    out.append({"src": "border leaves", "dst": "NHN Cloud", "fabric": "ethernet", "gbps": b["nhn_gbps"]})
    out.append({"src": "border leaves", "dst": "Internet transit", "fabric": "ethernet", "gbps": b["internet_gbps"]})
    return sorted(out, key=lambda x: -x["gbps"])


def network_device(eng, did: str) -> dict | None:
    d = T.NET_BY_ID.get(did)
    if not d:
        return None
    col = [x["id"] for x in T.NET_DEVICES].index(did)
    served = []
    if d["tier"] == "leaf" and d["fabric"] == "infiniband":
        served = d["serves"]
    elif d["tier"] == "leaf" and d.get("role") == "gpu-tor":
        served = [d["rack"]]
    return {"device": _dev_row(eng, d), "interfaces": eng.network.interfaces(did), "col": col, "serves": served}


# ================================================================ kubernetes
def kubernetes(eng) -> dict:
    k = eng.k8s
    nodes = []
    for n in T.K8S_NODES:
        live = k.nodes[n["id"]]
        nodes.append({**n, **live})
    ns = {}
    for p in k.pods:
        e = ns.setdefault(p["namespace"], {"namespace": p["namespace"], "pods": 0, "running": 0, "cpu_m": 0.0, "mem_mi": 0.0})
        e["pods"] += 1
        e["running"] += p["status"] == "Running"
        e["cpu_m"] += p.get("cpu_now", 0.0)
        e["mem_mi"] += p.get("mem_now", 0.0)
    problem = [p for p in k.pods if p["status"] != "Running"]
    return {"summary": k.summary(), "nodes": sorted(nodes, key=lambda x: -x["cpu_pct"]),
            "namespaces": sorted(ns.values(), key=lambda x: -x["cpu_m"]), "problem_pods": problem[:20],
            "events": [{"t": e["t"], "kind": e["kind"], "text": e["text"]} for e in list(k.events)[:15]]}


def k8s_node(eng, nid: str) -> dict | None:
    spec = T.K8S_BY_ID.get(nid)
    if not spec:
        return None
    live = eng.k8s.nodes[nid]
    pods = sorted([p for p in eng.k8s.pods if p["node"] == nid], key=lambda p: -p.get("cpu_now", 0))
    col = [n["id"] for n in T.K8S_NODES].index(nid)
    return {"node": {**spec, **live}, "pods": pods, "col": col,
            "conditions": [{"type": t, "status": "False" if t != "Ready" else ("True" if live["status"] == "Ready" else "Unknown")}
                           for t in ("Ready", "MemoryPressure", "DiskPressure", "PIDPressure", "NetworkUnavailable")],
            "hardware": {"cpu": "2× Intel Xeon Platinum 8580 (112 cores)", "memory": "2 TB DDR5-5600", "nic": "2× 400 GbE",
                         "bmc": f"idrac-{nid}.oob.grid", "os": "Ubuntu 24.04 LTS · containerd 2.1"}}
