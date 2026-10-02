"""Named failure / load scenarios.

A scenario only sets *causes* (a failed device, hotter air, more jobs). The
physics and scheduler produce the symptoms, and the alert manager groups the
symptoms back under the scenario's root cause.
"""
from __future__ import annotations

import numpy as np

from . import topology as T

SCENARIOS = [
    {"id": "cdu-failure", "name": "CDU pump failure · Row A2", "domain": "cooling", "duration_s": 360,
     "faults": ["CDU-A2"], "affects": ["facility.cooling", "it.gpu"],
     "desc": "Primary pump VFD on CDU-A2 trips. Row A2 (SU02 · R05–R08) coolant supply climbs until the Hall A spare CDU "
             "takes the row over the N+1 manifold (~24 s), then settles several degrees warmer.",
     "root_cause": "CDU-A2 primary pump VFD fault", "impact": "Row A2 · SU02 · R05–R08 · 576 GPUs · thermal excursion"},
    {"id": "cdu-double", "name": "CDU failure with spare offline · Row B4", "domain": "cooling", "duration_s": 300,
     "faults": ["CDU-B4", "CDU-BS"], "affects": ["facility.cooling", "it.gpu", "platform"],
     "desc": "CDU-B4 fails while the Hall B spare is out for service. No failover path: the inference SU (SU10 · R37–R40) "
             "thermal-throttles until the scenario clears.",
     "root_cause": "CDU-B4 failure while CDU-BS unavailable (spare under maintenance)",
     "impact": "Row B4 · SU10 · inference partition · sustained throttling"},
    {"id": "chiller-trip", "name": "Chiller CH-1 trip", "domain": "cooling", "duration_s": 300,
     "faults": ["CH-1"], "affects": ["facility.cooling"],
     "desc": "Lead chiller trips on a compressor fault. CHW supply rises until a standby chiller starts (~90 s).",
     "root_cause": "CH-1 compressor high-discharge-pressure trip", "impact": "Air-side CHW excursion · Hall C inlet +1–2 °C"},
    {"id": "ups-fault", "name": "UPS-A-HB fault · loss of 2N", "domain": "power", "duration_s": 300,
     "faults": ["UPS-A-HB"], "affects": ["facility.power"],
     "desc": "UPS A-side for Hall B faults to bypass-off. B-side carries 100% of Hall B — still up, but one failure from an outage.",
     "root_cause": "UPS-A-HB rectifier module fault", "impact": "Hall B running on single path (N)"},
    {"id": "utility-loss", "name": "KEPCO line 1 loss → A-side gensets", "domain": "power", "duration_s": 240,
     "faults": ["UTIL-1"], "affects": ["facility.power"],
     "desc": "154 kV line 1 drops. A-side UPS ride through on Li-ion while GEN-01..05 start and pick up (~12 s).",
     "root_cause": "KEPCO 154 kV line 1 feeder trip", "impact": "A-side on gensets · B-side on utility"},
    {"id": "blackout", "name": "Dual utility loss · black start", "domain": "power", "duration_s": 180,
     "faults": ["UTIL-1", "UTIL-2"], "affects": ["facility.power"],
     "desc": "Both 154 kV feeds lost. All UPS on battery, all ten gensets start and carry the campus.",
     "root_cause": "Regional grid disturbance — both KEPCO feeders tripped", "impact": "Campus on gensets · fuel burn"},
    {"id": "ib-flap", "name": "InfiniBand rail leaf flap · ib-leaf-05", "domain": "network", "duration_s": 300,
     "faults": ["ib-leaf-05"], "affects": ["it.network", "it.gpu", "platform"],
     "desc": "Transceivers on ib-leaf-05 (SU01 · rail 5) flap. Every all-reduce spanning SU01 (R01–R04) waits on that rail: "
             "step time balloons, some jobs hit NCCL timeouts.",
     "root_cause": "ib-leaf-05 OSFP transceivers — symbol errors / link down", "impact": "SU01 · R01–R04 · rail 5 · all-reduce slowdown"},
    {"id": "xid-storm", "name": "XID storm · rack R12", "domain": "gpu", "duration_s": 240,
     "faults": [], "xid_racks": ["R12"], "affects": ["it.gpu", "platform"],
     "desc": "A bad firmware push on R12 causes repeated Xid 79/119 events. Health checks drain nodes; jobs fail over.",
     "root_cause": "R12 GPU firmware regression (GSP timeouts / fall off bus)", "impact": "R12 nodes draining"},
    {"id": "heatwave", "name": "Heat wave · +9 °C ambient", "domain": "cooling", "duration_s": 600,
     "faults": [], "heat_delta": 9.0, "affects": ["facility.cooling", "facility.power"],
     "desc": "Ambient dry-bulb +9 °C. Free cooling drops, trim chillers stage up, PUE climbs.",
     "root_cause": "Ambient heat wave — wet-bulb above free-cooling limit", "impact": "PUE ↑ · chiller load ↑"},
    {"id": "checkpoint-storm", "name": "Synchronized checkpoint storm", "domain": "storage", "duration_s": 180,
     "faults": [], "storage_storm": 5.6, "affects": ["it.storage"],
     "desc": "Several large jobs checkpoint on the same boundary; the hot tier absorbs a write burst and latency spikes.",
     "root_cause": "Aligned checkpoint schedules across llm-pretrain jobs", "impact": "ss-hot latency · write GB/s spike"},
    {"id": "nsd-degraded", "name": "Scale NSD servers down · hot tier", "domain": "storage", "duration_s": 300,
     "faults": ["NSD-ss-hot"], "affects": ["it.storage"],
     "desc": "The NSD server pair of one hot-tier building block (one SU's 10 PB) goes offline; bandwidth drops by 1/12 "
             "and latency rises under load.",
     "root_cause": "NSD building block power-supply failure", "impact": "ss-hot bandwidth −8.3% (1 of 12 blocks)"},
    {"id": "k8s-node-down", "name": "Kubernetes worker NotReady · k8s-w-07", "domain": "k8s", "duration_s": 240,
     "faults": ["k8s-w-07"], "affects": ["it.k8s"],
     "desc": "Kubelet on k8s-w-07 stops reporting. Pods are rescheduled after the eviction timeout.",
     "root_cause": "k8s-w-07 kernel soft-lockup", "impact": "Platform pods rescheduling"},
    {"id": "cloud-burst", "name": "Queue surge → AWS burst", "domain": "cloud", "duration_s": 420,
     "faults": [], "arrival_mult": 3.2, "affects": ["platform", "cloud"],
     "desc": "Fine-tune demand spikes before a milestone. Slurm backlog grows and eligible jobs burst onto the AWS Capacity Block.",
     "root_cause": "Milestone-driven fine-tune submission surge", "impact": "Queue ↑ · AWS spend ↑"},
    {"id": "demand-surge", "name": "Game launch inference surge ×2.2", "domain": "platform", "duration_s": 420,
     "faults": [], "inference_demand": 2.2, "affects": ["it.k8s", "platform", "cloud"],
     "desc": "A live-ops event triples player traffic. Inference GPUs saturate and the gateway HPA scales out.",
     "root_cause": "PUBG live-ops event traffic", "impact": "Inference util ↑ · gateway replicas ↑"},
    {"id": "leak", "name": "Leak detected · CDU-B1 manifold", "domain": "cooling", "duration_s": 180,
     "faults": ["LEAK-CDU-B1"], "affects": ["facility.cooling"],
     "desc": "Rope sensor under the Row B1 (SU07) manifold trips. No thermal impact yet — a people problem, fast.",
     "root_cause": "Quick-disconnect weep on R25 manifold", "impact": "Row B1 · SU07 · leak response"},
]
SCENARIO_BY_ID = {s["id"]: s for s in SCENARIOS}

MODES = {
    "normal": {"desc": "Baseline operations"},
    "stress": {"desc": "Heavy training demand and inference traffic", "arrival_mult": 2.0, "inference_demand": 1.5},
    "maintenance": {"desc": "Planned maintenance window — CH-3 and UPS-B-HC out of service, alerts suppressed on them",
                    "maint": ["CH-3", "UPS-B-HC"]},
    "failover": {"desc": "UPS failover drill (starts the ups-fault scenario)", "scenario": "ups-fault"},
}


class ScenarioRunner:
    def __init__(self) -> None:
        self.active: list[dict] = []
        self.history: list[dict] = []
        self.mode = "normal"

    def start(self, sid: str, now: float, duration_s: float | None = None) -> dict:
        spec = SCENARIO_BY_ID.get(sid)
        if spec is None:
            raise KeyError(sid)
        self.active = [a for a in self.active if a["id"] != sid]
        run = {"id": sid, "name": spec["name"], "started": now, "ends": now + (duration_s or spec["duration_s"]),
               "key": f"scn:{sid}:{int(now)}", "domain": spec["domain"]}
        self.active.append(run)
        self.history.insert(0, {**run, "state": "running"})
        del self.history[50:]
        return run

    def stop(self, sid: str, now: float) -> bool:
        before = len(self.active)
        self.active = [a for a in self.active if a["id"] != sid]
        for h in self.history:
            if h["id"] == sid and h.get("state") == "running":
                h["state"], h["stopped"] = "stopped", now
        return len(self.active) < before

    def set_mode(self, mode: str, now: float) -> None:
        if mode not in MODES:
            raise KeyError(mode)
        self.mode = mode
        sc = MODES[mode].get("scenario")
        if sc:
            self.start(sc, now)

    def expire(self, now: float) -> list[dict]:
        done = [a for a in self.active if a["ends"] <= now]
        for a in done:
            for h in self.history:
                if h["key"] == a["key"]:
                    h["state"], h["stopped"] = "completed", now
        self.active = [a for a in self.active if a["ends"] > now]
        return done

    def modifiers(self) -> dict:
        faults, maint = set(), set()
        heat, storm, arrival, demand = 0.0, 0.0, 1.0, 1.0
        xid = np.zeros(T.GPU_RACKS, np.float32)
        mode = MODES[self.mode]
        maint |= set(mode.get("maint", []))
        arrival = max(arrival, mode.get("arrival_mult", 1.0))
        demand = max(demand, mode.get("inference_demand", 1.0))
        for a in self.active:
            s = SCENARIO_BY_ID[a["id"]]
            faults |= set(s.get("faults", []))
            heat = max(heat, s.get("heat_delta", 0.0))
            storm = max(storm, s.get("storage_storm", 0.0))
            arrival = max(arrival, s.get("arrival_mult", 1.0))
            demand = max(demand, s.get("inference_demand", 1.0))
            for rk in s.get("xid_racks", []):
                xid[T.RACK_INDEX[rk]] = 0.0009
        return {"faults": faults, "maint": maint, "heat_delta": heat, "storage_storm": storm,
                "arrival_mult": arrival, "inference_demand": demand, "xid_rate_rack": xid}

    def correlation(self) -> dict[str, dict]:
        """category -> correlation hint from the most recent scenario affecting it."""
        out: dict[str, dict] = {}
        for a in self.active:
            s = SCENARIO_BY_ID[a["id"]]
            hint = {"key": a["key"], "title": s["name"], "root_cause": s["root_cause"], "impact": s["impact"],
                    "scenario": a["id"]}
            for cat in s.get("affects", []):
                out[cat] = hint
        return out

    def public(self, now: float) -> dict:
        return {
            "mode": self.mode, "modes": {k: v["desc"] for k, v in MODES.items()},
            "active": [{**a, "remaining_s": max(0, round(a["ends"] - now)),
                        "progress": round(min(1.0, (now - a["started"]) / max(1.0, a["ends"] - a["started"])) * 100, 1)}
                       for a in self.active],
            "history": self.history[:20],
            "catalog": SCENARIOS,
        }
