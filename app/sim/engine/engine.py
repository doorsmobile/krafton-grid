"""Core simulation engine — tick loop, snapshot, Redis persist, live getters."""

from __future__ import annotations

import json
import math
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any

import redis

from app.config import (
    CRITICAL_IT_MW,
    DESIGN_CAPACITY_MW,
    MODULE_COUNT,
    MODULE_MW,
    REDIS_KEY_PREFIX,
    REDIS_URL,
    SIM_INTERVAL_SEC,
    SITE_CODE,
    SITE_NAME,
    TARGET_PUE,
    FIRST_MODULE_ID,
)
from app.sim.facility.models import HALLS, MODULAR_CENTERS, SimState
from app.sim.facility.vendors import VENDORS
from app.sim.it import GPU_COUNT, STORAGE_CAPACITY_PB
from app.sim.cloud import live_cloud_metrics, live_cost_snapshot
from app.sim.gpu_platform import live_fractos_metrics
from app.sim.engine.network_store import NetworkStoreMixin
from app.sim.engine.storage_store import StorageStoreMixin
from app.sim.engine.seed import SeedMixin
from app.sim.engine.bundles import BundlesMixin


class SimulationEngine(NetworkStoreMixin, StorageStoreMixin, SeedMixin, BundlesMixin):
    def __init__(self) -> None:
        self.redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        self.state = SimState(
            hall_loads={h.id: round(h.design_mw * 0.74, 2) for h in HALLS},
            module_loads={m.id: (round(CRITICAL_IT_MW * 0.74, 2) if m.status == "online" else 0.0) for m in MODULAR_CENTERS},
            vendor_health={v["id"]: v["status"] for v in VENDORS},
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._history_maxlen = 180
        self._net_ifaces: list[dict[str, Any]] = []
        self._net_iface_by_id: dict[str, dict[str, Any]] = {}
        self._last_net_sample_min: int = -1
        self._st_volumes: list[dict[str, Any]] = []
        self._st_clusters: list[dict[str, Any]] = []
        self._st_vol_by_id: dict[str, dict[str, Any]] = {}
        self._last_st_sample_min: int = -1

    def start(self) -> None:
        self._seed_static()
        self.tick_once()
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="dcim-sim", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(SIM_INTERVAL_SEC):
            try:
                self.tick_once()
            except Exception as exc:  # noqa: BLE001 — keep sim alive
                self.redis.hset(f"{REDIS_KEY_PREFIX}:meta", "last_error", str(exc))

    def set_mode(self, mode: str) -> None:
        if mode not in {"normal", "stress", "maintenance", "failover"}:
            raise ValueError("invalid mode")
        self.state.mode = mode
        self.redis.hset(f"{REDIS_KEY_PREFIX}:meta", "mode", mode)

    def inject_alert(self, severity: str, message: str) -> dict[str, Any]:
        alert = {
            "id": f"ALT-{int(time.time())}-{random.randint(100, 999)}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "severity": severity,
            "source": "Simulation Console",
            "message": message,
            "ack": False,
        }
        self.redis.lpush(f"{REDIS_KEY_PREFIX}:alerts", json.dumps(alert))
        self.redis.ltrim(f"{REDIS_KEY_PREFIX}:alerts", 0, 99)
        self.state.active_alerts = min(self.state.active_alerts + 1, 40)
        # Fan-out to Slack / webhook destinations (simulated)
        from app.sim.observability import deliver_alert_to_destinations

        alert["deliveries"] = deliver_alert_to_destinations(self.redis, alert)
        return alert

    def tick_once(self) -> dict[str, Any]:
        s = self.state
        s.tick += 1
        t = s.tick

        mode_factor = {
            "normal": 1.0,
            "stress": 1.12,
            "maintenance": 0.88,
            "failover": 0.95,
        }[s.mode]

        # Diurnal + noise
        diurnal = 0.04 * math.sin(t / 40.0)
        burst = 0.03 * math.sin(t / 7.3) if s.mode == "stress" else 0.0
        noise = random.uniform(-0.008, 0.008)

        # Phase-1 live IT sits inside first 20 MW modular center
        base_it = 14.8 * mode_factor
        s.it_load_mw = round(
            max(8.0, min(CRITICAL_IT_MW * 0.96, base_it * (1 + diurnal + burst + noise))),
            3,
        )

        # Facility overhead tracks cooling intensity
        outdoor = 18 + 10 * abs(math.sin(t / 90.0)) + random.uniform(-0.4, 0.4)
        s.outdoor_temp_c = round(outdoor, 2)
        cooling_drive = 0.14 + 0.02 * (outdoor - 20) / 10 + (0.04 if s.mode == "stress" else 0)
        s.facility_mw = round(s.it_load_mw * cooling_drive + random.uniform(-0.08, 0.08), 3)
        total = s.it_load_mw + s.facility_mw
        s.pue = round(total / s.it_load_mw, 3)

        s.ups_load_pct = round(min(96.0, (s.it_load_mw / CRITICAL_IT_MW) * 100 * 1.05 + random.uniform(-1, 1)), 2)
        s.cooling_load_pct = round(min(94.0, cooling_drive / 0.18 * 70 + random.uniform(-2, 2)), 2)
        s.liquid_loop_temp_c = round(27.5 + (0.8 if s.mode == "stress" else 0) + random.uniform(-0.3, 0.3), 2)
        s.return_temp_c = round(s.liquid_loop_temp_c + 7.5 + random.uniform(-0.4, 0.4), 2)
        s.humidity_pct = round(40 + 4 * math.sin(t / 55.0) + random.uniform(-1, 1), 1)
        s.renewable_pct = round(max(12.0, min(62.0, 34 + 12 * math.sin(t / 100.0) + random.uniform(-2, 2))), 1)
        s.bess_soc_pct = round(
            max(40.0, min(98.0, s.bess_soc_pct + random.uniform(-0.4, 0.35) + (2 if s.mode == "failover" else 0))),
            1,
        )

        # Distribute hall loads inside M1 proportional to design
        design_sum = sum(h.design_mw for h in HALLS)
        for h in HALLS:
            share = h.design_mw / design_sum
            jitter = 1 + random.uniform(-0.02, 0.02)
            s.hall_loads[h.id] = round(s.it_load_mw * share * jitter, 3)

        for m in MODULAR_CENTERS:
            if m.status == "online":
                s.module_loads[m.id] = s.it_load_mw
            elif m.status == "commissioning":
                s.module_loads[m.id] = round(random.uniform(0.2, 0.8), 3)
            else:
                s.module_loads[m.id] = 0.0

        # Vendor health wobble
        for v in VENDORS:
            if v["id"] == "siemens" and s.mode != "normal":
                s.vendor_health[v["id"]] = "degraded"
            elif random.random() < 0.01:
                s.vendor_health[v["id"]] = "degraded"
            elif random.random() < 0.05 and s.vendor_health.get(v["id"]) == "degraded":
                s.vendor_health[v["id"]] = "connected"
            elif v["status"] == "idle":
                s.vendor_health[v["id"]] = "idle"
            else:
                s.vendor_health[v["id"]] = s.vendor_health.get(v["id"], "connected")

        snapshot = self._snapshot()
        self._persist(snapshot)
        self._maybe_sample_network()
        self._maybe_sample_storage()
        return snapshot

    def _snapshot(self) -> dict[str, Any]:
        s = self.state
        campus_util = round((s.it_load_mw / DESIGN_CAPACITY_MW) * 100, 2)
        module_util = round((s.it_load_mw / CRITICAL_IT_MW) * 100, 2)
        online_mw = sum(m.design_mw for m in MODULAR_CENTERS if m.status == "online")
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tick": s.tick,
            "mode": s.mode,
            "site": SITE_NAME,
            "code": SITE_CODE,
            "design_capacity_mw": DESIGN_CAPACITY_MW,
            "critical_it_mw": CRITICAL_IT_MW,
            "module_mw": MODULE_MW,
            "module_count": MODULE_COUNT,
            "first_module_id": FIRST_MODULE_ID,
            "online_design_mw": online_mw,
            "it_load_mw": s.it_load_mw,
            "facility_mw": s.facility_mw,
            "total_mw": round(s.it_load_mw + s.facility_mw, 3),
            "pue": s.pue,
            "target_pue": TARGET_PUE,
            "utilization_pct": campus_util,
            "module_utilization_pct": module_util,
            "ups_load_pct": s.ups_load_pct,
            "cooling_load_pct": s.cooling_load_pct,
            "liquid_loop_temp_c": s.liquid_loop_temp_c,
            "return_temp_c": s.return_temp_c,
            "outdoor_temp_c": s.outdoor_temp_c,
            "humidity_pct": s.humidity_pct,
            "renewable_pct": s.renewable_pct,
            "bess_soc_pct": s.bess_soc_pct,
            "active_alerts": s.active_alerts,
            "hall_loads": s.hall_loads,
            "module_loads": s.module_loads,
            "vendor_health": s.vendor_health,
            "wue": round(0.28 + random.uniform(-0.02, 0.02), 3),
            "cue": round(0.92 + random.uniform(-0.03, 0.03), 3),
            "gpu_utilization_pct": round(min(98.0, 70 + 15 * math.sin(s.tick / 18.0) + random.uniform(-3, 3)), 1),
            "gpu_active_count": int(GPU_COUNT * (0.72 + 0.08 * math.sin(s.tick / 22.0))),
            "gpu_total_count": GPU_COUNT,
            "storage_used_pb": round(
                STORAGE_CAPACITY_PB * (0.41 + 0.03 * math.sin(s.tick / 50.0) + random.uniform(-0.01, 0.01)),
                2,
            ),
            "storage_total_pb": STORAGE_CAPACITY_PB,
            "storage_throughput_gbs": round(180 + 40 * math.sin(s.tick / 14.0) + random.uniform(-8, 8), 1),
            "eth_fabric_util_pct": round(min(92.0, 48 + 12 * math.sin(s.tick / 20.0) + random.uniform(-3, 3)), 1),
            "ib_fabric_util_pct": round(min(96.0, 62 + 18 * math.sin(s.tick / 16.0) + random.uniform(-4, 4)), 1),
            "k8s_pod_count": int(420 + 40 * math.sin(s.tick / 25.0) + random.uniform(-10, 10)),
            "k8s_node_ready": 30,
            "k8s_cpu_util_pct": round(min(90.0, 55 + 10 * math.sin(s.tick / 19.0) + random.uniform(-4, 4)), 1),
            **live_cloud_metrics(s.tick),
            **live_fractos_metrics(s.tick),
            "cost": live_cost_snapshot(s.tick, s.mode),
        }

    def _persist(self, snapshot: dict[str, Any]) -> None:
        key = f"{REDIS_KEY_PREFIX}:live"
        hist = f"{REDIS_KEY_PREFIX}:history"
        pipe = self.redis.pipeline()
        pipe.set(key, json.dumps(snapshot))
        pipe.lpush(hist, json.dumps(snapshot))
        pipe.ltrim(hist, 0, self._history_maxlen - 1)
        # Per-metric series for Highcharts
        for metric in (
            "it_load_mw",
            "facility_mw",
            "pue",
            "ups_load_pct",
            "cooling_load_pct",
            "liquid_loop_temp_c",
            "gpu_utilization_pct",
            "bess_soc_pct",
            "storage_used_pb",
            "storage_throughput_gbs",
            "eth_fabric_util_pct",
            "ib_fabric_util_pct",
            "k8s_cpu_util_pct",
            "nhn_gpu_util_pct",
            "aws_gpu_util_pct",
            "gcp_storage_used_tb",
            "cubeflow_avg_gpu_util_pct",
            "fractos_gpu_util_pct",
            "fractos_cpu_util_pct",
            "fractos_mem_util_pct",
            "fractos_power_kw",
            "fractos_gpu_temp_c",
        ):
            series_key = f"{REDIS_KEY_PREFIX}:series:{metric}"
            if metric not in snapshot:
                continue
            point = json.dumps({"t": snapshot["ts"], "v": snapshot[metric]})
            pipe.lpush(series_key, point)
            pipe.ltrim(series_key, 0, self._history_maxlen - 1)
        pipe.execute()

    def get_live(self) -> dict[str, Any]:
        raw = self.redis.get(f"{REDIS_KEY_PREFIX}:live")
        if not raw:
            return self.tick_once()
        return json.loads(raw)

    def get_history(self, limit: int = 60) -> list[dict[str, Any]]:
        rows = self.redis.lrange(f"{REDIS_KEY_PREFIX}:history", 0, limit - 1)
        return list(reversed([json.loads(r) for r in rows]))

    def get_series(self, metric: str, limit: int = 60) -> list[dict[str, Any]]:
        rows = self.redis.lrange(f"{REDIS_KEY_PREFIX}:series:{metric}", 0, limit - 1)
        return list(reversed([json.loads(r) for r in rows]))

    def get_json(self, suffix: str) -> Any:
        raw = self.redis.get(f"{REDIS_KEY_PREFIX}:{suffix}")
        return json.loads(raw) if raw else None

    def get_alerts(self, limit: int = 30) -> list[dict[str, Any]]:
        rows = self.redis.lrange(f"{REDIS_KEY_PREFIX}:alerts", 0, limit - 1)
        return [json.loads(r) for r in rows]

    def get_modules(self) -> list[dict[str, Any]]:
        modules = self.get_json("modules") or [m.__dict__ for m in MODULAR_CENTERS]
        loads = self.get_live().get("module_loads", {})
        for m in modules:
            live_mw = loads.get(m["id"], 0.0)
            m["live_mw"] = live_mw
            m["util_pct"] = round((live_mw / m["design_mw"]) * 100, 1) if m["design_mw"] else 0
        return modules

