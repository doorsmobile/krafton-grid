"""Static Redis catalog seed mixin."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from app.config import (
    CRITICAL_IT_MW,
    DESIGN_CAPACITY_MW,
    FIRST_MODULE_ID,
    MODULE_COUNT,
    MODULE_MW,
    REDIS_KEY_PREFIX,
    SITE_CODE,
    SITE_NAME,
    TARGET_PUE,
)
from app.sim.facility.models import HALLS, MODULAR_CENTERS, ZONES
from app.sim.facility.vendors import COOLING_CHAIN, POWER_CHAIN, VENDORS
from app.sim.it import (
    build_asset_rows,
    build_gpu_pods,
    build_inventory_summary,
    build_rack_map,
    build_storage_clusters,
)
from app.sim.cloud import (
    build_cloud_catalog,
    build_cloud_cost_baseline,
    build_cost_monthly_trends,
    build_dc_cost_baseline,
    build_slurm_cubeflow_nodes,
    build_slurm_queue,
)
from app.sim.gpu_platform import build_fractos_bundle_static
from app.sim.network import (
    NET_HISTORY_LEN,
    NET_SAMPLE_INTERVAL_SEC,
    build_all_interfaces,
    build_network_devices_rich,
    build_topology,
)
from app.sim.storage import build_storage_clusters_rich, build_storage_volumes
from app.sim.it.k8s_live import build_k8s_nodes_rich
from app.sim.telemetry import HISTORY_LEN as ST_HISTORY_LEN
from app.sim.telemetry import SAMPLE_INTERVAL_SEC as ST_SAMPLE_INTERVAL_SEC


class SeedMixin:
    def _seed_static(self) -> None:
        pipe = self.redis.pipeline()
        pipe.set(
            f"{REDIS_KEY_PREFIX}:site",
            json.dumps(
                {
                    "name": SITE_NAME,
                    "code": SITE_CODE,
                    "design_capacity_mw": DESIGN_CAPACITY_MW,
                    "critical_it_mw": CRITICAL_IT_MW,
                    "module_mw": MODULE_MW,
                    "module_count": MODULE_COUNT,
                    "first_module_id": FIRST_MODULE_ID,
                    "build_model": f"{MODULE_COUNT}×{MODULE_MW:.0f} MW modular centers → {DESIGN_CAPACITY_MW:.0f} MW campus",
                    "target_pue": TARGET_PUE,
                    "topology": "Modular 20 MW blocks / 2N power / N+1 cooling / liquid-first",
                    "commissioned": "2025-Q4 (M1 online)",
                    "region": "APAC — Metro Edge Campus",
                }
            ),
        )
        pipe.set(f"{REDIS_KEY_PREFIX}:modules", json.dumps([m.__dict__ for m in MODULAR_CENTERS]))
        pipe.set(f"{REDIS_KEY_PREFIX}:halls", json.dumps([h.__dict__ for h in HALLS]))
        pipe.set(f"{REDIS_KEY_PREFIX}:zones", json.dumps(ZONES))
        pipe.set(f"{REDIS_KEY_PREFIX}:vendors", json.dumps(VENDORS))
        pipe.set(f"{REDIS_KEY_PREFIX}:power_chain", json.dumps(POWER_CHAIN))
        pipe.set(f"{REDIS_KEY_PREFIX}:cooling_chain", json.dumps(COOLING_CHAIN))
        pipe.set(f"{REDIS_KEY_PREFIX}:it_summary", json.dumps(build_inventory_summary()))
        pipe.set(f"{REDIS_KEY_PREFIX}:gpu_pods", json.dumps(build_gpu_pods()))
        pipe.set(f"{REDIS_KEY_PREFIX}:storage_clusters", json.dumps(build_storage_clusters()))
        st_clusters = build_storage_clusters_rich()
        st_vols = build_storage_volumes(st_clusters)
        self._st_clusters = st_clusters
        self._st_volumes = st_vols
        self._st_vol_by_id = {v["id"]: v for v in st_vols}
        pipe.set(f"{REDIS_KEY_PREFIX}:storage_clusters_rich", json.dumps(st_clusters))
        pipe.set(f"{REDIS_KEY_PREFIX}:storage_volumes", json.dumps(st_vols))
        pipe.set(
            f"{REDIS_KEY_PREFIX}:st:meta",
            json.dumps(
                {
                    "sample_interval_sec": ST_SAMPLE_INTERVAL_SEC,
                    "history_minutes": ST_HISTORY_LEN,
                    "cluster_count": len(st_clusters),
                    "volume_count": len(st_vols),
                    "collector": "IBM Storage Scale / Prometheus (simulated)",
                }
            ),
        )
        rich_devices = build_network_devices_rich()
        net_ifaces = build_all_interfaces(rich_devices)
        self._net_ifaces = net_ifaces
        self._net_iface_by_id = {i["id"]: i for i in net_ifaces}
        pipe.set(f"{REDIS_KEY_PREFIX}:network_devices", json.dumps(rich_devices))
        pipe.set(f"{REDIS_KEY_PREFIX}:net:interfaces", json.dumps(net_ifaces))
        pipe.set(f"{REDIS_KEY_PREFIX}:net:topology", json.dumps(build_topology(rich_devices)))
        pipe.set(
            f"{REDIS_KEY_PREFIX}:net:meta",
            json.dumps(
                {
                    "sample_interval_sec": NET_SAMPLE_INTERVAL_SEC,
                    "history_minutes": NET_HISTORY_LEN,
                    "iface_count": len(net_ifaces),
                    "device_count": len(rich_devices),
                    "collector": "Arista eAPI / CVP + NVIDIA UFM (simulated)",
                }
            ),
        )
        pipe.set(f"{REDIS_KEY_PREFIX}:k8s_nodes", json.dumps(build_k8s_nodes_rich()))
        pipe.set(f"{REDIS_KEY_PREFIX}:rack_map", json.dumps(build_rack_map()))
        pipe.set(f"{REDIS_KEY_PREFIX}:inventory", json.dumps(build_asset_rows()))
        pipe.set(f"{REDIS_KEY_PREFIX}:slurm_nodes", json.dumps(build_slurm_cubeflow_nodes()))
        pipe.set(f"{REDIS_KEY_PREFIX}:slurm_queue", json.dumps(build_slurm_queue()))
        pipe.set(f"{REDIS_KEY_PREFIX}:cloud_catalog", json.dumps(build_cloud_catalog()))
        pipe.set(f"{REDIS_KEY_PREFIX}:cost_dc", json.dumps(build_dc_cost_baseline()))
        pipe.set(f"{REDIS_KEY_PREFIX}:cost_cloud", json.dumps(build_cloud_cost_baseline()))
        pipe.set(f"{REDIS_KEY_PREFIX}:cost_trends", json.dumps(build_cost_monthly_trends()))
        pipe.set(f"{REDIS_KEY_PREFIX}:fractos", json.dumps(build_fractos_bundle_static()))
        pipe.hset(
            f"{REDIS_KEY_PREFIX}:meta",
            mapping={"mode": self.state.mode, "started_at": datetime.now(timezone.utc).isoformat()},
        )
        # Seed a few realistic alerts
        if self.redis.llen(f"{REDIS_KEY_PREFIX}:alerts") == 0:
            seeds = [
                ("warning", "M1 Hall Beta CDU-03 secondary pump vibration rising (Vertiv)"),
                ("info", "M2 modular block busway energization window opens in 6h"),
                ("critical", "CoolIT manifold leak sensor M1-B12 intermittent trip — auto-isolated"),
                ("warning", "NVIDIA UFM: IB switch IB-Q-14 port flap storm (Quantum-2)"),
                ("info", "IBM Storage Cluster ST-06 rebuild at 42% — capacity still online"),
                ("warning", "Arista leaf AR-LF-41 optics RX power low on eth1/32"),
                ("info", "Dell K8s node K8S-17 cordoned for firmware window"),
            ]
            for sev, msg in seeds:
                alert = {
                    "id": f"ALT-SEED-{sev}-{msg[:12].replace(' ', '')}",
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "severity": sev,
                    "source": "DCIM Correlation",
                    "message": msg,
                    "ack": False,
                }
                pipe.lpush(f"{REDIS_KEY_PREFIX}:alerts", json.dumps(alert))
        pipe.execute()
        # Fan-out seed alerts to Slack / webhook destinations (once)
        from app.sim.observability import deliver_alert_to_destinations, get_alert_deliveries

        if not get_alert_deliveries(self.redis, limit=1):
            for alert in self.get_alerts(20):
                deliver_alert_to_destinations(self.redis, alert)
        self._seed_network_history()
        self._seed_storage_history()


