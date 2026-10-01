"""Simulation engine — owns every domain model and advances them one tick at a time.

Tick order follows causality: scenarios -> scheduler -> GPU physics -> racks ->
facility heat/power -> storage/network/k8s/cloud -> billing -> TSDB -> alerts ->
logs -> live snapshot -> post-tick hooks (the collector's publisher writes the read models to Redis).

The engine knows nothing about the web tier or the store: it is the demo *source* of collected state.
"""
from __future__ import annotations

import threading
import time
import traceback
from collections import deque
from datetime import datetime

import numpy as np

from .. import config
from . import cost as cost_mod
from . import topology as T
from .alerts import AlertManager
from .cloud import Cloud
from .cost import Cost
from .facility import Facility
from .fleet import G, N_GPU, N_NODE, Fleet
from .itinfra import Kubernetes, Network, Storage
from .logs import LogStore
from .scenarios import ScenarioRunner
from .tsdb import TIERS, TSDB

RACK_OVERHEAD_KW = 2.2  # ToR + share of IB leaf + mgmt switch + rear-door fans


class Engine:
    def __init__(self) -> None:
        now = time.time()
        self.boot = now
        self.now = now
        self.rng = np.random.default_rng(config.SIM_SEED)
        self.lock = threading.RLock()
        self.tick_n = 0
        self.tick_ms = 0.0
        self.running = False
        self.thread: threading.Thread | None = None
        self.hooks: list = []          # called after every live tick (the collector's publisher)
        self.events: deque[dict] = deque(maxlen=800)

        self.fleet = Fleet(self.rng, now)
        self.facility = Facility(self.rng, now)
        self.storage = Storage(self.rng)
        self.network = Network(self.rng)
        self.k8s = Kubernetes(self.rng, now)
        self.cloud = Cloud(self.rng, now)
        self.cost = Cost(now)
        self.alerts = AlertManager()
        self.alerts.base_url = f"http://127.0.0.1:{config.APP_PORT}"
        self.logs = LogStore(self.rng)
        self.scen = ScenarioRunner()
        self.tsdb = TSDB()
        self.mods = self.scen.modifiers()
        self.rack_kw_vec = np.zeros(len(T.GPU_RACK_LIST))
        self.hallc = {}
        self.live: dict = {}
        self.relay_enabled: dict[str, bool] = {}
        self.monthly_cache: tuple[float, list] = (0.0, [])
        self.fatal_xid_ts: deque[tuple[float, int]] = deque(maxlen=200)
        self._register_metrics()
        self._day_key = None
        self._month_key = None

        # let the physics converge (utilisation, temperatures, loops) before anything is recorded
        warm = 18
        for i in range(warm):
            self.tick(now - (warm - 1 - i) * config.SIM_TICK_SEC, first=True, force=(i == warm - 1), record=(i == warm - 1))
        cost_mod.CURRENT_MW["value"] = self.facility.snapshot["facility_mw"]
        self._seed_energy(now)
        self._backfill(now)
        self._emit_event(now, "system", "info", f"{config.RELEASE_NAME} simulator online · {N_GPU:,} GPUs · {N_NODE} nodes")

    # ================================================================ metrics
    def _register_metrics(self) -> None:
        R = self.tsdb.register
        for name, help_, unit in [
            ("site_pue", "Power usage effectiveness", ""), ("site_it_mw", "Critical IT load", "MW"),
            ("site_facility_mw", "Total facility load", "MW"), ("site_util_pct", "M1 IT capacity used", "%"),
            ("site_wue", "Water usage effectiveness", "L/kWh"), ("site_cue", "Carbon usage effectiveness", "kgCO2/kWh"),
            ("ambient_dry_c", "Outdoor dry-bulb", "°C"), ("ambient_wet_c", "Outdoor wet-bulb", "°C"),
            ("cooling_chw_supply_c", "Chilled water supply", "°C"), ("cooling_fws_supply_c", "Facility (warm) water supply", "°C"),
            ("cooling_free_pct", "Free-cooling share", "%"), ("cooling_mw", "Mechanical cooling power", "MW"),
            ("gpu_util_avg", "Fleet GPU utilization", "%"), ("gpu_sm_avg", "Fleet SM activity", "%"),
            ("gpu_temp_avg", "Fleet GPU temperature (avg)", "°C"), ("gpu_temp_max", "Fleet GPU temperature (max)", "°C"),
            ("gpu_power_mw", "GPU node power", "MW"), ("gpu_alloc_pct", "GPUs allocated", "%"),
            ("gpu_throttle_count", "GPUs throttling", ""), ("gpu_idle_alloc", "Allocated but idle GPUs", ""),
            ("slurm_jobs_running", "Running jobs", ""), ("slurm_jobs_pending", "Pending jobs", ""),
            ("slurm_pending_gpus", "GPUs requested by pending jobs", ""),
            ("net_ib_util_pct", "InfiniBand fabric utilization", "%"), ("net_eth_util_pct", "Ethernet fabric utilization", "%"),
            ("k8s_cpu_pct", "K8s cluster CPU", "%"), ("k8s_mem_pct", "K8s cluster memory", "%"),
            ("k8s_pods_running", "Running pods", ""), ("k8s_rps", "Inference gateway requests/s", "req/s"),
            ("cost_rate_krw_kwh", "Electricity TOU rate", "₩/kWh"), ("alerts_firing", "Alerts firing", ""),
            ("storage_read_total_gbs", "Storage read (all tiers)", "GB/s"), ("storage_write_total_gbs", "Storage write (all tiers)", "GB/s"),
        ]:
            R(name, "t1", help_, unit)
        R("power_side_mw", "t1", "Load per power path", "MW", [{"side": "A"}, {"side": "B"}])
        ups = [d["id"] for d in T.POWER_DEVICES if d["kind"] == "ups" and not d.get("planned")]
        R("ups_load_pct", "t1", "UPS output load", "%", [{"ups": u, "hall": u[-2:], "side": u[4]} for u in ups])
        R("ups_soc_pct", "t1", "UPS battery state of charge", "%", [{"ups": u, "hall": u[-2:], "side": u[4]} for u in ups])
        R("cooling_tcs_supply_c", "t1", "Rack coolant (TCS) supply per row", "°C", [{"row": r, "hall": "H" + r[0]} for r in T.ROW_CDU])
        cdus = [d["id"] for d in T.COOLING_DEVICES if d["kind"] == "cdu"]
        R("cdu_load_pct", "t1", "CDU heat load", "%", [{"cdu": c} for c in cdus])
        R("hall_it_mw", "t1", "IT load per hall", "MW", [{"hall": h["id"]} for h in T.HALLS])
        R("hall_inlet_c", "t1", "Hall inlet air", "°C", [{"hall": h["id"]} for h in T.HALLS])
        rack_labels = [{"rack": r.id, "hall": r.hall, "row": r.row, "partition": T.RACK_PARTITION[r.id]} for r in T.GPU_RACK_LIST]
        R("rack_power_kw", "t1", "Rack power", "kW", rack_labels)
        R("rack_temp_max_c", "t1", "Hottest GPU in rack", "°C", rack_labels)
        R("rack_gpu_util", "t1", "Rack GPU utilization", "%", rack_labels)
        clusters = [c["id"] for c in T.STORAGE_CLUSTERS]
        for name, help_, unit in [("storage_read_gbs", "Read throughput", "GB/s"), ("storage_write_gbs", "Write throughput", "GB/s"),
                                  ("storage_latency_ms", "Latency", "ms"), ("storage_iops_k", "IOPS", "k")]:
            R(name, "t1", help_, unit, [{"cluster": c} for c in clusters])
        R("cloud_cost_hr_krw", "t1", "Cloud burn rate", "₩/h", [{"provider": p} for p in ("aws", "gcp", "nhn")])
        R("cloud_gpu_util", "t1", "Cloud GPU utilization", "%", [{"provider": "aws"}, {"provider": "nhn"}])

        node_labels = [{"node": T.NODE_IDS[n], "rack": T.NODE_RACK[n], "hall": T.RACK_BY_ID[T.NODE_RACK[n]].hall,
                        "partition": T.RACK_PARTITION[T.NODE_RACK[n]]} for n in range(N_NODE)]
        R("node_gpu_util", "t2", "Node GPU utilization (mean of 8)", "%", node_labels)
        R("node_power_kw", "t2", "Node power", "kW", node_labels)
        R("node_temp_max_c", "t2", "Hottest GPU in node", "°C", node_labels)
        R("node_ib_gbps", "t2", "Node InfiniBand throughput", "Gb/s", node_labels)
        R("node_cpu_pct", "t2", "Node host CPU", "%", node_labels)
        dev_labels = [{"device": d["id"], "fabric": d["fabric"], "tier": d["tier"]} for d in T.NET_DEVICES]
        R("net_device_util_pct", "t2", "Switch utilization", "%", dev_labels)
        R("net_device_in_gbps", "t2", "Switch ingress", "Gb/s", dev_labels)
        R("net_device_out_gbps", "t2", "Switch egress", "Gb/s", dev_labels)
        R("net_device_errors_total", "t2", "Switch error counter", "", dev_labels, kind="counter")
        R("net_device_discards_total", "t2", "Switch discard counter", "", dev_labels, kind="counter")
        vol_labels = [{"volume": v["id"], "cluster": v["cluster"], "project": v["project"]} for v in self.storage.volumes]
        R("storage_volume_iops_k", "t2", "Fileset IOPS", "k", vol_labels)
        R("storage_volume_read_gbs", "t2", "Fileset read", "GB/s", vol_labels)
        R("storage_volume_write_gbs", "t2", "Fileset write", "GB/s", vol_labels)
        R("storage_volume_latency_ms", "t2", "Fileset latency", "ms", vol_labels)
        k8s_labels = [{"node": n["id"], "role": n["role"]} for n in T.K8S_NODES]
        R("k8s_node_cpu_pct", "t2", "K8s node CPU", "%", k8s_labels)
        R("k8s_node_mem_pct", "t2", "K8s node memory", "%", k8s_labels)
        R("k8s_node_pods", "t2", "K8s node pods", "", k8s_labels)
        proj_labels = [{"project": p["id"]} for p in T.PROJECTS]
        R("project_gpus_used", "t2", "GPUs in use by project", "", proj_labels)
        R("project_gpu_util", "t2", "Project GPU utilization", "%", proj_labels)
        R("aws_instance_util", "t2", "AWS instances running", "", [{"provider": "aws"}])

        gpu_labels = [{"gpu": T.gpu_id(i), "node": T.NODE_IDS[i // G], "rack": T.NODE_RACK[i // G],
                       "hall": T.RACK_BY_ID[T.NODE_RACK[i // G]].hall, "partition": T.RACK_PARTITION[T.NODE_RACK[i // G]],
                       "slot": str(i % G)} for i in range(N_GPU)]
        for name, help_, unit in [("gpu_util_pct", "GPU utilization", "%"), ("gpu_sm_pct", "SM activity", "%"),
                                  ("gpu_temp_c", "GPU temperature", "°C"), ("gpu_power_w", "GPU power", "W"),
                                  ("gpu_mem_gb", "HBM used", "GB")]:
            R(name, "t3", help_, unit, gpu_labels)

        for name, help_, unit in [("site_pue_24h", "PUE (24 h)", ""), ("site_it_mw_24h", "IT load (24 h)", "MW"),
                                  ("site_facility_mw_24h", "Facility load (24 h)", "MW"), ("gpu_util_avg_24h", "Fleet GPU util (24 h)", "%"),
                                  ("gpu_alloc_pct_24h", "GPU allocation (24 h)", "%"), ("ambient_dry_c_24h", "Outdoor temperature (24 h)", "°C"),
                                  ("cooling_mw_24h", "Cooling power (24 h)", "MW"), ("storage_read_gbs_24h", "Storage read (24 h)", "GB/s"),
                                  ("storage_write_gbs_24h", "Storage write (24 h)", "GB/s"), ("net_ib_util_24h", "IB utilization (24 h)", "%"),
                                  ("cloud_cost_hr_24h", "Cloud burn (24 h)", "₩/h"), ("k8s_rps_24h", "Gateway req/s (24 h)", "req/s"),
                                  ("cost_rate_24h", "TOU rate (24 h)", "₩/kWh"), ("site_wue_24h", "WUE (24 h)", "L/kWh")]:
            R(name, "t4", help_, unit)

    # ================================================================== tick
    def tick(self, now: float | None = None, first: bool = False, force: bool = False, record: bool = True) -> None:
        t0 = time.perf_counter()
        now = now or time.time()
        dt = config.SIM_TICK_SEC
        with self.lock:
            self.now = now
            for done in self.scen.expire(now):
                self._emit_event(now, "scenario", "info", f"Scenario completed · {done['name']}", domain=done["domain"])
            self.mods = m = self.scen.modifiers()
            self.fleet.arrival_mult = m["arrival_mult"]
            self.fleet.inference_demand = m["inference_demand"]
            self._rollover(now)

            self.fleet.schedule(now, dt, lambda job: self.cloud.accept_burst(job, now))
            row_supply = self.facility.row_supply
            self.fleet.step(now, dt, row_supply, self.network.ib_penalty, m["xid_rate_rack"], power_cap_w=T.GPU_TDP_W)
            for ts_, gi, code in list(self.fleet.xid_ts)[-12:]:
                if ts_ >= now - 0.01 and code in (48, 79, 95):
                    self.fatal_xid_ts.append((now, gi))

            node_kw = self.fleet.node_power / 1000.0
            self.rack_kw_vec = np.bincount(self.fleet.node_rack, weights=node_kw, minlength=len(T.GPU_RACK_LIST)) + RACK_OVERHEAD_KW
            rack_kw = {rk.id: float(self.rack_kw_vec[i]) for i, rk in enumerate(T.GPU_RACK_LIST)}
            hallc_kw = self._hall_c_kw()

            self.storage.step(dt, self.fleet.train_read_gbs, self.fleet.ckpt_write_gbs, self.fleet.io_by_project,
                              m["faults"], m["storage_storm"], now)
            st_sum = self.storage.summary()
            self.cloud.step(now, dt, self.fleet.diurnal, m["inference_demand"], m["faults"])
            self.network.step(dt, self.fleet.node_ib, self.fleet.node_eth, st_sum["read_gbs"] + st_sum["write_gbs"],
                              m["faults"], self.cloud.border_gbps())
            self.k8s.step(now, dt, self.fleet.diurnal, m["inference_demand"], m["faults"])

            rate = self.cost.rate or cost_mod.energy_rate(datetime.fromtimestamp(now, cost_mod.KST))[0]
            fs = self.facility.step(now, dt, rack_kw, hallc_kw, m["faults"], m["maint"], m["heat_delta"], rate)
            self.cost.tick(now, dt, fs["facility_mw"] * 1000)
            cost_mod.CURRENT_MW["value"] += (fs["facility_mw"] - cost_mod.CURRENT_MW["value"]) * 0.0005

            self.tick_n += 1
            gsum = self.fleet.summary(now)
            if record:
                self._record(now, fs, gsum, st_sum, force)
            if not first:
                metrics, context = self._alert_inputs(now, fs, gsum, st_sum)
                fired = self.alerts.evaluate(now, metrics, context, self.scen.correlation(), m["maint"],
                                             config.ALERTS_LIVE_DELIVERY, config.SLACK_WEBHOOK_URL)
                for a in fired:
                    self._emit_event(now, "alert", a["severity"], f"{a['name']} — {a['summary']}", domain=a["category"],
                                     href=f"/alerts?focus={a['id']}")
                    self.logs.emit(now, "grid-sim", "error" if a["severity"] == "critical" else "warn",
                                   f"ALERT {a['severity'].upper()} {a['name']}: {a['summary']}", alert=a["id"])
                self._drain_fleet_events(now)
                self.logs.background(now, self)
            self.live = self._build_live(now, fs, gsum, st_sum)
        self.tick_ms = (time.perf_counter() - t0) * 1000
        if not first:
            for hook in self.hooks:
                hook(self)

    def _rollover(self, now: float) -> None:
        kst = time.gmtime(now + 9 * 3600)
        day, month = (kst.tm_year, kst.tm_yday), (kst.tm_year, kst.tm_mon)
        if self._day_key is None:
            self._day_key, self._month_key = day, month
            return
        if day != self._day_key:
            self._day_key = day
            self.cost.today_power_krw = 0.0
            self.cloud.cost_today_krw = {k: 0.0 for k in self.cloud.cost_today_krw}
            self.fleet.gpu_seconds_today = {k: 0.0 for k in self.fleet.gpu_seconds_today}
            self.fleet.idle_alloc_seconds = {k: 0.0 for k in self.fleet.idle_alloc_seconds}
        if month != self._month_key:
            self._month_key = month
            self.cost.month_power_live = 0.0
            self.cost.boot = now
            self.cloud.cost_month_krw = {k: 0.0 for k in self.cloud.cost_month_krw}

    def _hall_c_kw(self) -> float:
        rng = self.rng
        st = self.storage.clusters
        kw = 0.0
        per = {}
        for c in T.STORAGE_CLUSTERS:
            u = st[c["id"]].get("util_pct", 30.0) / 100
            base, var = {"ss-hot": (22.0, 11.0), "ss-capacity": (17.5, 6.0), "ss-archive": (8.0, 2.0)}[c["id"]]
            for rk in c["racks"]:
                per[rk] = base + var * u + float(rng.normal(0, 0.2))
        k8s_cpu = self.k8s.summary()["cpu_pct"] / 100 if self.k8s.nodes else 0.3
        for rk in ("K01", "K02", "K03"):
            per[rk] = 10 * (1.1 + 0.9 * k8s_cpu)
        ib = self.network.summary()["ib_util_pct"] / 100 if self.network.dev else 0.5
        for i, rk in enumerate(("N01", "N02", "N03", "N04", "N05", "N06")):
            per[rk] = (11.5 if i < 4 else 5.5) * (0.8 + 0.3 * ib)
        per["MG1"] = 6.2
        self.hallc = per
        return sum(per.values())

    def _seed_energy(self, now: float) -> None:
        kst = time.gmtime(now + 9 * 3600)
        h_today = kst.tm_hour + kst.tm_min / 60
        h_month = (kst.tm_mday - 1) * 24 + h_today
        fs = self.facility.snapshot
        e = self.facility.energy
        e["kwh_total_today"] = fs["facility_mw"] * 1000 * h_today * 0.99
        e["kwh_it_today"] = fs["it_mw"] * 1000 * h_today * 0.99
        e["kwh_total_month"] = fs["facility_mw"] * 1000 * h_month * 0.985
        e["kwh_it_month"] = fs["it_mw"] * 1000 * h_month * 0.985
        e["water_l_today"] = fs["cooling"]["water_lph"] * h_today
        e["co2_t_today"] = fs["facility_mw"] * 0.4594 * h_today
        e["peak_kw_month"] = fs["facility_mw"] * 1000 * 1.06
        rate = cost_mod.energy_rate(datetime.fromtimestamp(now, cost_mod.KST))[0]
        self.cost.today_power_krw = e["kwh_total_today"] * rate * 0.92 * (1 + cost_mod.FUND_RATE) * (1 + cost_mod.VAT)
        cl = self.cloud.snapshot
        for k in ("aws", "gcp", "nhn"):
            self.cloud.cost_today_krw[k] = cl[k]["cost_hr_krw"] * h_today
        for p in T.PROJECTS:
            used = sum(len(j.gpus) for j in self.fleet.jobs.values() if j.project == p["id"] and j.state == "RUNNING")
            self.fleet.gpu_seconds_today[p["id"]] = used * h_today * 3600 * 0.96
            self.fleet.idle_alloc_seconds[p["id"]] = self.fleet.gpu_seconds_today[p["id"]] * (0.35 if p["id"] == "research-sandbox" else 0.04)

    def _record(self, now: float, fs: dict, g: dict, st: dict, force: bool = False) -> None:
        f = self.fleet
        rack_idx = f.node_rack
        n_racks = len(T.GPU_RACK_LIST)
        util_node = f.util.reshape(N_NODE, G).mean(axis=1)
        temp_node = f.temp.reshape(N_NODE, G).max(axis=1)
        rack_temp = np.full(n_racks, 0.0)
        np.maximum.at(rack_temp, rack_idx, temp_node)
        rack_util = np.bincount(rack_idx, weights=util_node, minlength=n_racks) / np.maximum(np.bincount(rack_idx, minlength=n_racks), 1)
        cool = fs["cooling"]
        cl = self.cloud.snapshot
        k = self.k8s.summary()
        net = self.network.summary()
        ups_ids = [lab["ups"] for lab in self.tsdb.metrics["ups_load_pct"].labels]
        cdu_ids = [lab["cdu"] for lab in self.tsdb.metrics["cdu_load_pct"].labels]
        values = {
            "site_pue": fs["pue"], "site_it_mw": fs["it_mw"], "site_facility_mw": fs["facility_mw"],
            "site_util_pct": fs["util_pct"], "site_wue": fs["wue"], "site_cue": fs["cue"],
            "ambient_dry_c": fs["ambient"]["dry_c"], "ambient_wet_c": fs["ambient"]["wet_c"],
            "cooling_chw_supply_c": cool["chw_supply_c"], "cooling_fws_supply_c": cool["fws_supply_c"],
            "cooling_free_pct": cool["free_cooling_pct"], "cooling_mw": cool["cooling_kw"] / 1000,
            "gpu_util_avg": g["avg_util"], "gpu_sm_avg": g["avg_sm"], "gpu_temp_avg": g["avg_temp"], "gpu_temp_max": g["max_temp"],
            "gpu_power_mw": g["power_mw"], "gpu_alloc_pct": g["allocation_pct"],
            "gpu_throttle_count": g["thermal_throttle"] + g["power_throttle"], "gpu_idle_alloc": g["idle_allocated"],
            "slurm_jobs_running": g["jobs_running"], "slurm_jobs_pending": g["jobs_pending"], "slurm_pending_gpus": g["pending_gpus"],
            "net_ib_util_pct": net["ib_util_pct"], "net_eth_util_pct": net["eth_util_pct"],
            "k8s_cpu_pct": k["cpu_pct"], "k8s_mem_pct": k["mem_pct"], "k8s_pods_running": k["pods_running"], "k8s_rps": k["rps"],
            "cost_rate_krw_kwh": self.cost.rate, "alerts_firing": self.alerts.counts()["firing"],
            "storage_read_total_gbs": st["read_gbs"], "storage_write_total_gbs": st["write_gbs"],
            "power_side_mw": [fs["power"]["side_mw"]["A"], fs["power"]["side_mw"]["B"]],
            "ups_load_pct": [fs["power"]["ups"][u]["load_pct"] for u in ups_ids],
            "ups_soc_pct": [fs["power"]["ups"][u]["soc"] for u in ups_ids],
            "cooling_tcs_supply_c": [cool["row_supply_c"][r] for r in T.ROW_CDU],
            "cdu_load_pct": [cool["cdus"][c]["load_pct"] for c in cdu_ids],
            "hall_it_mw": [fs["halls"][h["id"]]["it_mw"] for h in T.HALLS],
            "hall_inlet_c": [fs["halls"][h["id"]]["inlet_c"] for h in T.HALLS],
            "rack_power_kw": self.rack_kw_vec, "rack_temp_max_c": rack_temp, "rack_gpu_util": rack_util,
            "storage_read_gbs": [st["clusters"][c["id"]]["read_gbs"] for c in T.STORAGE_CLUSTERS],
            "storage_write_gbs": [st["clusters"][c["id"]]["write_gbs"] for c in T.STORAGE_CLUSTERS],
            "storage_latency_ms": [st["clusters"][c["id"]]["latency_ms"] for c in T.STORAGE_CLUSTERS],
            "storage_iops_k": [st["clusters"][c["id"]]["iops_k"] for c in T.STORAGE_CLUSTERS],
            "cloud_cost_hr_krw": [cl["aws"]["cost_hr_krw"], cl["gcp"]["cost_hr_krw"], cl["nhn"]["cost_hr_krw"]],
            "cloud_gpu_util": [cl["aws"]["gpu_util"], cl["nhn"]["gpu_util"]],
            "node_gpu_util": util_node, "node_power_kw": f.node_power / 1000, "node_temp_max_c": temp_node,
            "node_ib_gbps": f.node_ib, "node_cpu_pct": f.node_cpu,
            "net_device_util_pct": [self.network.dev[d["id"]]["util_pct"] for d in T.NET_DEVICES],
            "net_device_in_gbps": [self.network.dev[d["id"]]["in_gbps"] for d in T.NET_DEVICES],
            "net_device_out_gbps": [self.network.dev[d["id"]]["out_gbps"] for d in T.NET_DEVICES],
            "net_device_errors_total": [self.network.dev[d["id"]]["errors"] for d in T.NET_DEVICES],
            "net_device_discards_total": [self.network.dev[d["id"]]["discards"] for d in T.NET_DEVICES],
            "storage_volume_iops_k": [v["iops_k"] for v in self.storage.volumes],
            "storage_volume_read_gbs": [v["read_gbs"] for v in self.storage.volumes],
            "storage_volume_write_gbs": [v["write_gbs"] for v in self.storage.volumes],
            "storage_volume_latency_ms": [v["latency_ms"] for v in self.storage.volumes],
            "k8s_node_cpu_pct": [self.k8s.nodes[n["id"]]["cpu_pct"] for n in T.K8S_NODES],
            "k8s_node_mem_pct": [self.k8s.nodes[n["id"]]["mem_pct"] for n in T.K8S_NODES],
            "k8s_node_pods": [self.k8s.nodes[n["id"]]["pods"] for n in T.K8S_NODES],
            "gpu_util_pct": f.util, "gpu_sm_pct": f.sm, "gpu_temp_c": f.temp, "gpu_power_w": f.power, "gpu_mem_gb": f.mem,
            "aws_instance_util": [cl["aws"]["running"]],
            "site_pue_24h": fs["pue"], "site_it_mw_24h": fs["it_mw"], "site_facility_mw_24h": fs["facility_mw"],
            "gpu_util_avg_24h": g["avg_util"], "gpu_alloc_pct_24h": g["allocation_pct"],
            "ambient_dry_c_24h": fs["ambient"]["dry_c"], "cooling_mw_24h": cool["cooling_kw"] / 1000,
            "storage_read_gbs_24h": st["read_gbs"], "storage_write_gbs_24h": st["write_gbs"],
            "net_ib_util_24h": net["ib_util_pct"], "cloud_cost_hr_24h": cl["total_cost_hr_krw"],
            "k8s_rps_24h": k["rps"], "cost_rate_24h": self.cost.rate, "site_wue_24h": fs["wue"],
        }
        pu = {p["id"]: p for p in self.fleet.project_usage()} if (force or self.tick_n % TIERS["t2"]["every"] == 0) else None
        if pu:
            values["project_gpus_used"] = [pu[p["id"]]["used_gpus"] for p in T.PROJECTS]
            values["project_gpu_util"] = [pu[p["id"]]["util"] for p in T.PROJECTS]
        self.tsdb.record(self.tick_n, now, values, force=force)

    # ============================================================ alert inputs
    def _alert_inputs(self, now: float, fs: dict, g: dict, st: dict) -> tuple[dict, dict]:
        cool, pw = fs["cooling"], fs["power"]
        failed_cdus = [c for c, v in cool["cdus"].items() if v["status"] == "failed"]
        hot_rows = [r for r, v in cool["row_supply_c"].items() if v > 38.5]
        ups_fault = [u for u, v in pw["ups"].items() if v["status"] == "fault"]
        ups_batt = [u for u, v in pw["ups"].items() if v["status"] == "on-battery"]
        util_lost = [u for u, v in pw["utility"].items() if v["status"] == "lost"]
        tripped = [c for c, v in cool["chillers"].items() if v["status"] == "tripped"]
        leaks = [c for c, v in cool["cdus"].items() if v["leak"]]
        f = self.fleet
        thr = np.where(f.throttle == 1)[0]
        thr_racks = sorted({T.NODE_RACK[i // G] for i in thr})
        hottest = int(np.argmax(f.temp))
        fatal = [(t, gi) for t, gi in self.fatal_xid_ts if t >= now - 120]
        fatal_nodes = sorted({T.NODE_IDS[gi // G] for _, gi in fatal})
        ib_down = [d["id"] for d in T.IB_LEAVES if self.network.dev[d["id"]]["links_down"] > 0]
        dev_down = [k for k, v in self.network.dev.items() if v["status"] == "down"]
        nsd_down = [c for c, v in self.storage.clusters.items() if v["nsd_up"] < v["nsd_total"]]
        k8s_nr = [k for k, v in self.k8s.nodes.items() if v["status"] != "Ready"]
        spare_info = []
        for c in failed_cdus:
            spare = cool["cdus"].get(f"CDU-{c[4]}S", {})
            row = c.replace("CDU-", "")
            spare_info.append(f"{c} failed · {'spare CDU-' + c[4] + 'S covering ' + row if spare.get('covering') == row else 'no spare path — row running hot'}")
        metrics = {
            "site.pue": fs["pue"], "power.ups_faults": len(ups_fault), "power.ups_on_battery": len(ups_batt),
            "power.utility_lost": len(util_lost), "power.busway_max_pct": max(b["load_pct"] for b in self.facility.busway.values()),
            "cooling.cdu_failed": len(failed_cdus), "cooling.tcs_supply_max_c": cool["tcs_supply_max_c"],
            "cooling.chillers_tripped": len(tripped), "cooling.chw_supply_c": cool["chw_supply_c"],
            "cooling.redundancy_lost": 1 if cool["redundancy"] != "N+1" else 0, "cooling.leaks": len(leaks),
            "gpu.thermal_throttle": g["thermal_throttle"], "gpu.max_temp": g["max_temp"], "gpu.fatal_xid_recent": len(fatal),
            "gpu.idle_allocated": g["idle_allocated"], "slurm.pending_gpus": g["pending_gpus"],
            "network.ib_links_down": sum(self.network.dev[d]["links_down"] for d in ib_down), "network.devices_down": len(dev_down),
            "storage.latency_ms": st["clusters"]["ss-hot"]["latency_ms"], "storage.used_pct": st["used_pct"],
            "storage.nsd_down": len(nsd_down), "k8s.not_ready": len(k8s_nr),
            "k8s.crashloop": self.k8s.summary()["pods_crashloop"],
            "cloud.cost_hr_krw": self.cloud.snapshot["total_cost_hr_krw"],
            "cost.peak_high_load": 1 if (self.cost.band == "peak" and fs["facility_mw"] > 6.0) else 0,
        }
        row_corr = f"row:{hot_rows[0]}" if hot_rows else None
        context = {
            "site.pue": {"summary": f"PUE {fs['pue']:.3f} · free cooling {cool['free_cooling_pct']:.0f}% · OAT {fs['ambient']['dry_c']:.1f} °C",
                         "href": "/facility"},
            "power.ups_faults": {"entities": ups_fault, "summary": f"{', '.join(ups_fault)} faulted — redundancy {pw['redundancy']}",
                                 "href": "/facility/power"},
            "power.ups_on_battery": {"entities": ups_batt, "summary": f"{len(ups_batt)} UPS on battery · min SOC "
                                     f"{min([pw['ups'][u]['soc'] for u in ups_batt] or [100]):.0f}%", "href": "/facility/power"},
            "power.utility_lost": {"entities": util_lost, "summary": f"{', '.join(util_lost)} lost · gensets running "
                                   f"{sum(1 for v in pw['gens'].values() if v['status'] == 'running')}/10", "href": "/facility/power"},
            "power.busway_max_pct": {"summary": "Busway loading above 80%", "href": "/facility/power"},
            "cooling.cdu_failed": {"entities": failed_cdus, "summary": "; ".join(spare_info), "href": "/facility/cooling",
                                   "corr": f"row:{failed_cdus[0].replace('CDU-', '')}" if failed_cdus else None},
            "cooling.tcs_supply_max_c": {"entities": hot_rows, "summary": f"TCS supply {cool['tcs_supply_max_c']:.1f} °C on "
                                         f"row {', '.join(hot_rows) or '—'}", "href": "/facility/cooling", "corr": row_corr},
            "cooling.chillers_tripped": {"entities": tripped, "summary": f"{', '.join(tripped)} tripped · "
                                         f"{cool['chillers_running']} running", "href": "/facility/cooling"},
            "cooling.chw_supply_c": {"summary": f"CHW supply {cool['chw_supply_c']:.2f} °C (setpoint 18.0)", "href": "/facility/cooling"},
            "cooling.redundancy_lost": {"summary": f"Cooling running at {cool['redundancy']}", "href": "/facility/cooling"},
            "cooling.leaks": {"entities": leaks, "summary": f"Leak sensor tripped at {', '.join(leaks)}", "href": "/facility/cooling"},
            "gpu.thermal_throttle": {"entities": thr_racks, "summary": f"{len(thr)} GPUs thermal-throttling on {', '.join(thr_racks[:5])}",
                                     "href": "/gpu-fleet?metric=temp", "corr": row_corr},
            "gpu.max_temp": {"entities": [T.gpu_id(hottest)], "summary": f"{T.gpu_id(hottest)} at {float(f.temp[hottest]):.1f} °C",
                             "href": f"/gpu-fleet/device/{T.gpu_id(hottest)}", "corr": row_corr},
            "gpu.fatal_xid_recent": {"entities": fatal_nodes, "summary": f"Fatal Xid on {', '.join(fatal_nodes[:4])} — node(s) drained",
                                     "href": f"/gpu-fleet/node/{fatal_nodes[0]}" if fatal_nodes else "/gpu-fleet"},
            "gpu.idle_allocated": {"summary": f"{g['idle_allocated']} allocated GPUs idle (<5% util)", "href": "/gpu-fleet"},
            "slurm.pending_gpus": {"summary": f"{g['jobs_pending']} jobs pending · {g['pending_gpus']:,} GPUs requested", "href": "/gpu-platform/workloads"},
            "network.ib_links_down": {"entities": ib_down, "summary": f"{', '.join(ib_down)} link flaps · symbol errors rising",
                                      "href": f"/network/device/{ib_down[0]}" if ib_down else "/network"},
            "network.devices_down": {"entities": dev_down, "summary": f"{', '.join(dev_down)} down", "href": "/network"},
            "storage.latency_ms": {"summary": f"ss-hot latency {st['clusters']['ss-hot']['latency_ms']:.2f} ms · write "
                                   f"{st['clusters']['ss-hot']['write_gbs']:.0f} GB/s", "href": "/storage/cluster/ss-hot"},
            "storage.used_pct": {"summary": f"{st['used_pct']}% of 100 PB used", "href": "/storage"},
            "storage.nsd_down": {"entities": nsd_down, "summary": f"NSD servers down in {', '.join(nsd_down)}", "href": "/storage"},
            "k8s.not_ready": {"entities": k8s_nr, "summary": f"{', '.join(k8s_nr)} NotReady", "href": f"/kubernetes/node/{k8s_nr[0]}" if k8s_nr else "/kubernetes"},
            "k8s.crashloop": {"summary": "Pods crash-looping", "href": "/kubernetes"},
            "cloud.cost_hr_krw": {"summary": f"Cloud burn ₩{self.cloud.snapshot['total_cost_hr_krw']:,.0f}/h", "href": "/cloud"},
            "cost.peak_high_load": {"summary": f"최대부하 band · {self.cost.rate:.0f} ₩/kWh · load {fs['facility_mw']:.1f} MW", "href": "/cost/dc"},
        }
        return metrics, context

    def _drain_fleet_events(self, now: float) -> None:
        evs = list(self.fleet.events)
        self.fleet.events.clear()
        for e in reversed(evs[:40]):
            svc = "slurmctld" if e["kind"].startswith("job") else "dcgm-exporter"
            self.logs.emit(now, svc, e["level"], e["text"], project=e.get("project") or "")
            if e["kind"] == "xid" or e["level"] == "error":
                self._emit_event(now, "gpu", "warning" if e["level"] == "warn" else "critical" if e["level"] == "error" else "info",
                                 e["text"], domain="it.gpu")

    def _emit_event(self, now: float, kind: str, level: str, text: str, domain: str = "", href: str | None = None) -> None:
        self.events.appendleft({"t": now, "kind": kind, "level": level, "text": text, "domain": domain, "href": href})

    # ================================================================ backfill
    def _backfill(self, now: float) -> None:
        """Synthesise plausible history so every chart has a full window at boot."""
        rng = np.random.default_rng(7)
        with self.tsdb.lock:
            for m in self.tsdb.metrics.values():
                tier = TIERS[m.tier]
                step = tier["every"] * config.SIM_TICK_SEC
                cap = tier["cap"]
                cur = m.latest().astype(np.float64)
                if np.all(np.isnan(cur)):
                    continue
                n = cap - m.size
                if n <= 0:
                    continue
                ts = now - step * np.arange(n + m.size, m.size, -1)
                if m.tier == "t4":
                    vals = self._diurnal_backfill(m.name, ts, cur, rng)
                else:
                    rel = {"t1": 0.0045, "t2": 0.012, "t3": 0.018}[m.tier] if m.kind == "gauge" else 0.0
                    vals = _ar1(cur, n, rng, rel=rel, counter=m.kind == "counter", step_s=step)
                if m.name in ("ups_soc_pct", "cooling_free_pct"):
                    vals = np.repeat(cur[None, :], n, axis=0)
                old_ts, old_vals = m.ordered()
                full_ts = np.concatenate([ts, old_ts])
                full_vals = np.concatenate([vals.astype(np.float32), old_vals], axis=0)
                m.buf[: len(full_ts)] = full_vals[-cap:]
                m.ts[: len(full_ts)] = full_ts[-cap:]
                m.size = min(cap, len(full_ts))
                m.head = m.size % cap

    def _diurnal_backfill(self, name: str, ts: np.ndarray, cur: np.ndarray, rng) -> np.ndarray:
        hour = ((ts / 3600.0) + 9) % 24
        now_hour = ((time.time() / 3600.0) + 9) % 24
        s = lambda h, peak: np.sin((h - peak) / 24 * 2 * np.pi)  # noqa: E731
        base = cur[0]
        noise = rng.normal(0, 1, len(ts))
        if name == "ambient_dry_c_24h":
            v = base + 4.6 * (s(hour, 9) - s(np.array([now_hour]), 9)[0]) + noise * 0.25
        elif name in ("site_pue_24h",):
            v = base + 0.018 * (s(hour, 9) - s(np.array([now_hour]), 9)[0]) + noise * 0.002
        elif name in ("cooling_mw_24h", "site_wue_24h"):
            v = base * (1 + 0.12 * (s(hour, 9) - s(np.array([now_hour]), 9)[0])) + noise * base * 0.01
        elif name in ("k8s_rps_24h", "cloud_cost_hr_24h"):
            v = base * (0.62 + 0.38 * s(hour, 14)) / (0.62 + 0.38 * s(np.array([now_hour]), 14)[0]) * (1 + noise * 0.03)
        elif name == "cost_rate_24h":
            v = np.array([cost_mod.energy_rate(datetime.fromtimestamp(t, cost_mod.KST))[0] for t in ts])
        else:
            v = base * (1 + 0.035 * (s(hour, 16) - s(np.array([now_hour]), 16)[0])) + noise * base * 0.012
        return v[:, None]

    # ================================================================== live
    def _build_live(self, now: float, fs: dict, g: dict, st: dict) -> dict:
        cool, pw = fs["cooling"], fs["power"]
        cl = self.cloud.snapshot
        counts = self.alerts.counts()
        with self.alerts.lock:
            recent = sorted(self.alerts.active.values(), key=lambda a: -a["started"])[:6]
        return {
            "ts": now, "tick": self.tick_n, "tick_ms": round(self.tick_ms, 1), "release": config.RELEASE_NAME,
            "mode": self.scen.mode,
            "scenarios": [{"id": a["id"], "name": a["name"], "remaining_s": max(0, round(a["ends"] - now))} for a in self.scen.active],
            "site": {k: fs[k] for k in ("it_mw", "facility_mw", "capacity_mw", "util_pct", "pue", "wue", "cue",
                                         "ambient", "breakdown_mw", "heat_mw", "halls", "energy")},
            "power": {"redundancy": pw["redundancy"], "side_mw": pw["side_mw"], "pq": pw["pq"],
                      "utility": {k: {"status": v["status"], "mw": v["mw"]} for k, v in pw["utility"].items()},
                      "ups": {k: {"status": v["status"], "load_pct": v["load_pct"], "soc": round(v["soc"], 1), "eff": v["eff"]}
                              for k, v in pw["ups"].items()},
                      "gens_running": sum(1 for v in pw["gens"].values() if v["status"] == "running"),
                      "tx": {k: {"load_pct": v["load_pct"], "load_mw": v["load_mw"]} for k, v in pw["tx"].items()}},
            "cooling": {k: cool[k] for k in ("redundancy", "chw_supply_c", "chw_return_c", "fws_supply_c", "fws_return_c",
                                             "free_cooling_pct", "tcs_supply_avg_c", "tcs_supply_max_c", "chillers_running",
                                             "chiller_load_mw", "cooling_kw", "water_lph", "row_supply_c")}
                       | {"cdus": {k: {"status": v["status"], "supply_c": v["supply_c"], "load_pct": v["load_pct"],
                                       "covering": v.get("covering")} for k, v in cool["cdus"].items()}},
            "gpu": g,
            "storage": {k: st[k] for k in ("used_pb", "total_pb", "used_pct", "read_gbs", "write_gbs", "iops_k", "latency_ms")}
                       | {"clusters": {k: {"read_gbs": v["read_gbs"], "write_gbs": v["write_gbs"], "latency_ms": v["latency_ms"],
                                           "used_pb": round(v["used_pb"], 2), "util_pct": v.get("util_pct", 0), "health": v["health"]}
                                       for k, v in st["clusters"].items()}},
            "network": self.network.summary(),
            "k8s": self.k8s.summary(),
            "cloud": {"aws": cl["aws"], "gcp": {k: v for k, v in cl["gcp"].items() if k != "transfer"}, "nhn": cl["nhn"],
                      "total_cost_hr_krw": cl["total_cost_hr_krw"], "order": cl["order"]},
            "cost": {"rate": self.cost.current_rate(), "today_power_krw": round(self.cost.today_power_krw),
                     "today_cloud_krw": round(sum(self.cloud.cost_today_krw.values())),
                     "energy_kwh_today": round(fs["energy"]["kwh_total_today"])},
            "alerts": counts | {"recent": [{"id": a["id"], "name": a["name"], "severity": a["severity"], "summary": a["summary"],
                                            "started": a["started"], "href": a.get("href"), "incident": a.get("incident")}
                                           for a in recent]},
            "racks": {"id": [r.id for r in T.GPU_RACK_LIST], "kw": [round(float(x), 1) for x in self.rack_kw_vec]},
        }

    # ================================================================ lifecycle
    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, name="grid-sim", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False

    def _loop(self) -> None:
        nxt = time.time()
        while self.running:
            nxt += config.SIM_TICK_SEC
            try:
                self.tick()
            except Exception:  # keep ticking; surface the error in logs
                self.logs.emit(time.time(), "grid-sim", "error", "tick failed: " + traceback.format_exc()[-400:])
            time.sleep(max(0.0, nxt - time.time()))

    # ================================================================ actions
    def run_scenario(self, sid: str, duration_s: float | None = None) -> dict:
        with self.lock:
            now = self.now
            run = self.scen.start(sid, now, duration_s)
            self._emit_event(now, "scenario", "warning", f"Scenario started · {run['name']}", domain=run["domain"])
            self.logs.emit(now, "grid-sim", "warn", f"scenario start id={sid} ends_in={run['ends'] - now:.0f}s")
            return run

    def stop_scenario(self, sid: str) -> bool:
        with self.lock:
            ok = self.scen.stop(sid, self.now)
            if ok:
                self._emit_event(self.now, "scenario", "info", f"Scenario stopped · {sid}")
            return ok

    def set_mode(self, mode: str) -> None:
        with self.lock:
            self.scen.set_mode(mode, self.now)
            self._emit_event(self.now, "mode", "info", f"Simulation mode → {mode}")

    def drain_node(self, node_id: str, reason: str) -> bool:
        n = T.NODE_INDEX.get(node_id)
        if n is None:
            return False
        with self.lock:
            self.fleet.drain(n, self.now, reason or "operator drain")
            self._emit_event(self.now, "operator", "info", f"{node_id} drained by operator · {reason}", domain="it.gpu",
                             href=f"/gpu-fleet/node/{node_id}")
        return True

    def resume_node(self, node_id: str) -> bool:
        n = T.NODE_INDEX.get(node_id)
        if n is None:
            return False
        with self.lock:
            self.fleet.resume(n, self.now)
        return True

    def inject_xid(self, gpu: str, code: int) -> bool:
        gi = T.parse_gpu_id(gpu)
        if gi is None:
            return False
        with self.lock:
            self.fleet.inject_xid(gi, self.now, code)
            if code in (48, 79, 95):
                self.fatal_xid_ts.append((self.now, gi))
        return True

    def submit_job(self, project: str, profile: str, size: int, name: str | None, user: str | None) -> dict:
        from .fleet import PROFILES
        if project not in T.PROJECT_BY_ID:
            raise ValueError("unknown project")
        if profile not in PROFILES or profile == "inference":
            raise ValueError("profile must be pretrain|finetune|rlhf|eval|notebook|data")
        size = int(size)
        if not 1 <= size <= (256 if profile in ("pretrain", "finetune", "rlhf", "eval") else 8):
            raise ValueError("size out of range (nodes 1–256 for training/eval, GPUs 1–8 otherwise)")
        with self.lock:
            job = self.fleet._new_job(project, profile, size, self.now, orchestrator="cubeflow" if profile == "notebook" else "slurm")
            if name:
                job.name = name[:48]
            if user:
                job.user = user[:24]
            job.reason = "submitted from GPU Platform console"
            self._emit_event(self.now, "operator", "info", f"Job {job.id} {job.name} submitted · {project} · {profile} × {size}",
                             domain="platform", href=f"/gpu-fleet/job/{job.id}")
            self.logs.emit(self.now, "slurmctld", "info", f"_slurm_rpc_submit_batch_job: JobId={job.id} account={project} partition={job.partition}")
            return job.public(self.now)

    def monthly(self) -> list[dict]:
        now = time.time()
        if now - self.monthly_cache[0] > 5:
            rows = self.cost.monthly(now, self.facility.snapshot["facility_mw"], self.cloud.cost_month_krw)
            self.monthly_cache = (now, rows)
        return self.monthly_cache[1]

    def gpu_hours_month(self) -> float:
        kst = time.gmtime(time.time() + 9 * 3600)
        h = (kst.tm_mday - 1) * 24 + kst.tm_hour + kst.tm_min / 60
        return max(1.0, float((self.fleet.gpu_job >= 0).sum()) * h)


def _ar1(cur: np.ndarray, n: int, rng, rel: float, counter: bool, step_s: float) -> np.ndarray:
    """Backwards AR(1) walk that ends exactly at the current value."""
    width = cur.shape[0]
    if counter:
        rate = np.maximum(cur, 1) * 0.00002 * step_s
        back = cur[None, :] - rate[None, :] * np.arange(n, 0, -1)[:, None]
        return np.maximum(back, 0)
    scale = np.maximum(np.abs(np.nan_to_num(cur)), 1e-3) * rel
    steps = rng.normal(0, 1, (n, width)) * scale[None, :]
    walk = np.zeros((n, width))
    acc = np.zeros(width)
    for i in range(n - 1, -1, -1):
        acc = acc * 0.93 + steps[i]
        walk[i] = acc
    out = cur[None, :] + walk
    return np.where(np.isnan(out), np.nan, out)
