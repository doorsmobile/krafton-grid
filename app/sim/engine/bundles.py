"""Domain bundle getters (IT / cloud / cost / GPU platform / dump)."""

from __future__ import annotations

from typing import Any

from app.config import REDIS_KEY_PREFIX
from app.sim.it import (
    build_asset_rows,
    build_gpu_pods,
    build_inventory_summary,
    build_k8s_nodes,
    build_network_devices,
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
    live_cost_snapshot,
)
from app.sim.gpu_platform import build_fractos_bundle_static
from app.sim.it.k8s_live import (
    build_k8s_nodes_rich,
    build_node_pods,
    rank_k8s_talkers,
    sample_node_metrics,
)
from app.sim.it.gpu_live import (
    build_pod_nodes,
    enrich_slurm_nodes,
    rank_gpu_talkers,
    sample_pod_metrics,
)
from app.sim.it.gpu import build_gpu_pods as build_gpu_pods_static
from app.sim.it.gpu_monitoring import (
    build_gpu_monitoring_bundle,
    get_device_detail,
)
from app.sim.facility.live import (
    enrich_cooling_chain,
    enrich_halls,
    enrich_modules,
    enrich_power_chain,
    rank_by_score,
    sample_stage_series,
)
from app.sim.cloud.live_rank import (
    enrich_aws_instances,
    enrich_gcp_buckets,
    enrich_gcp_disks,
    enrich_nhn_instances,
    rank_cloud,
    sample_cloud_series,
)


class BundlesMixin:
    def get_it_bundle(self) -> dict[str, Any]:
        live = self.get_live()
        return {
            "summary": self.get_json("it_summary") or build_inventory_summary(),
            "gpu_pods": self.get_json("gpu_pods") or build_gpu_pods(),
            "storage_clusters": self.get_json("storage_clusters") or build_storage_clusters(),
            "network_devices": self.get_network_devices() or build_network_devices(),
            "k8s_nodes": self.get_json("k8s_nodes") or build_k8s_nodes_rich(),
            "rack_map": self.get_json("rack_map") or build_rack_map(),
            "inventory": self.get_json("inventory") or build_asset_rows(),
            "slurm_nodes": self.get_json("slurm_nodes") or build_slurm_cubeflow_nodes(),
            "slurm_queue": self.get_json("slurm_queue") or build_slurm_queue(),
            "network": {
                "meta": self.get_json("net:meta") or {},
                "collector": self.redis.hgetall(f"{REDIS_KEY_PREFIX}:net:collector"),
            },
            "live": {
                "gpu_utilization_pct": live.get("gpu_utilization_pct"),
                "gpu_active_count": live.get("gpu_active_count"),
                "gpu_total_count": live.get("gpu_total_count"),
                "storage_used_pb": live.get("storage_used_pb"),
                "storage_total_pb": live.get("storage_total_pb"),
                "storage_throughput_gbs": live.get("storage_throughput_gbs"),
                "eth_fabric_util_pct": live.get("eth_fabric_util_pct"),
                "ib_fabric_util_pct": live.get("ib_fabric_util_pct"),
                "k8s_pod_count": live.get("k8s_pod_count"),
                "k8s_node_ready": live.get("k8s_node_ready"),
                "k8s_cpu_util_pct": live.get("k8s_cpu_util_pct"),
                "cubeflow_avg_gpu_util_pct": live.get("cubeflow_avg_gpu_util_pct"),
                "slurm_jobs_running": live.get("slurm_jobs_running"),
                "slurm_jobs_pending": live.get("slurm_jobs_pending"),
            },
        }

    def get_k8s_overview(self) -> dict[str, Any]:
        live = self.get_live()
        tick = int(live.get("tick", 0))
        mode = live.get("mode", "normal")
        nodes = self.get_json("k8s_nodes") or build_k8s_nodes_rich()
        samples = [sample_node_metrics(n, tick=tick, mode=mode) for n in nodes]
        talkers = rank_k8s_talkers(samples, limit=10)
        # merge sample into node rows for table
        by_id = {s["node_id"]: s for s in samples}
        rows = [{**n, **by_id.get(n["id"], {})} for n in nodes]
        return {
            "nodes": rows,
            "talkers": talkers,
            "live": {
                "k8s_pod_count": live.get("k8s_pod_count"),
                "k8s_node_ready": live.get("k8s_node_ready"),
                "k8s_cpu_util_pct": live.get("k8s_cpu_util_pct"),
            },
            "summary": (self.get_json("it_summary") or build_inventory_summary()).get("kubernetes", {}),
        }

    def get_k8s_node_detail(self, node_id: str) -> dict[str, Any] | None:
        live = self.get_live()
        tick = int(live.get("tick", 0))
        mode = live.get("mode", "normal")
        nodes = self.get_json("k8s_nodes") or build_k8s_nodes_rich()
        node = next((n for n in nodes if n["id"] == node_id), None)
        if not node:
            return None
        metrics = sample_node_metrics(node, tick=tick, mode=mode)
        pods = build_node_pods(node, metrics)
        # synthetic 1h spark from seed
        series = []
        for age in range(59, -1, -1):
            m = sample_node_metrics(node, tick=tick - age, mode=mode)
            series.append({
                "t": live.get("ts"),
                "cpu": m["cpu_util_pct"],
                "mem": m["mem_util_pct"],
                "pods": m["pod_count"],
                "net": m["net_mbs"],
            })
        # fix timestamps roughly
        import time as _t
        now = int(_t.time())
        for i, p in enumerate(series):
            p["t"] = __import__("datetime").datetime.fromtimestamp(
                now - (59 - i) * 60, tz=__import__("datetime").timezone.utc
            ).isoformat()
        return {"node": node, "metrics": metrics, "pods": pods, "series": series}

    def get_gpu_overview(self) -> dict[str, Any]:
        live = self.get_live()
        tick = int(live.get("tick", 0))
        mode = live.get("mode", "normal")
        pods = self.get_json("gpu_pods") or build_gpu_pods_static()
        pod_metrics = [sample_pod_metrics(p, tick=tick, mode=mode) for p in pods]
        slurm = enrich_slurm_nodes(
            self.get_json("slurm_nodes") or build_slurm_cubeflow_nodes(),
            tick=tick,
            mode=mode,
        )
        talkers = rank_gpu_talkers(slurm, limit=10)
        mon = build_gpu_monitoring_bundle(
            pods_static=[{**p, **next((m for m in pod_metrics if m["pod_id"] == p["id"]), {})} for p in pods],
            slurm_nodes=slurm,
            slurm_queue=self.get_json("slurm_queue") or build_slurm_queue(),
            live=live,
        )
        return {
            "pods": mon["pods"],
            "talkers": talkers,
            "slurm_queue": mon["slurm_jobs"],
            "slurm_nodes": slurm[:12],
            "monitoring": mon,
            "live": {
                "gpu_utilization_pct": live.get("gpu_utilization_pct"),
                "gpu_active_count": live.get("gpu_active_count"),
                "gpu_total_count": live.get("gpu_total_count"),
                "cubeflow_avg_gpu_util_pct": live.get("cubeflow_avg_gpu_util_pct"),
                "slurm_jobs_running": live.get("slurm_jobs_running"),
                "slurm_jobs_pending": live.get("slurm_jobs_pending"),
            },
            "summary": (self.get_json("it_summary") or build_inventory_summary()).get("gpu", {}),
        }

    def get_gpu_pod_detail(self, pod_id: str) -> dict[str, Any] | None:
        live = self.get_live()
        tick = int(live.get("tick", 0))
        mode = live.get("mode", "normal")
        pods = self.get_json("gpu_pods") or build_gpu_pods_static()
        pod = next((p for p in pods if p["id"] == pod_id), None)
        if not pod:
            return None
        metrics = sample_pod_metrics(pod, tick=tick, mode=mode)
        slurm = enrich_slurm_nodes(
            self.get_json("slurm_nodes") or build_slurm_cubeflow_nodes(),
            tick=tick,
            mode=mode,
        )
        nodes = build_pod_nodes(pod, slurm)
        series = []
        import time as _t
        from datetime import datetime, timezone
        now = int(_t.time())
        for age in range(59, -1, -1):
            m = sample_pod_metrics(pod, tick=tick - age, mode=mode)
            series.append({
                "t": datetime.fromtimestamp(now - (59 - age) * 60, tz=timezone.utc).isoformat(),
                "util": m["gpu_util_pct"],
                "power": m["power_kw"],
                "temp": m["temp_c"],
            })
        return {"pod": pod, "metrics": metrics, "nodes": nodes, "series": series}

    def get_gpu_node_detail(self, node_id: str) -> dict[str, Any] | None:
        live = self.get_live()
        tick = int(live.get("tick", 0))
        mode = live.get("mode", "normal")
        slurm = enrich_slurm_nodes(
            self.get_json("slurm_nodes") or build_slurm_cubeflow_nodes(),
            tick=tick,
            mode=mode,
        )
        node = next((n for n in slurm if n["id"] == node_id), None)
        if not node:
            return None
        mon = build_gpu_monitoring_bundle(
            pods_static=self.get_json("gpu_pods") or build_gpu_pods_static(),
            slurm_nodes=slurm,
            slurm_queue=self.get_json("slurm_queue") or build_slurm_queue(),
            live=live,
        )
        host = next((h for h in mon["hosts"] if h["id"] == node_id), None)
        devices = [d for d in mon["devices"] if d["host_id"] == node_id]
        processes = [p for p in mon["processes"] if p["host_id"] == node_id]
        return {
            "node": node,
            "host": host,
            "devices": devices,
            "processes": processes,
            "queue": mon["slurm_jobs"],
        }

    def get_gpu_device_detail(self, device_id: str) -> dict[str, Any] | None:
        live = self.get_live()
        slurm = enrich_slurm_nodes(
            self.get_json("slurm_nodes") or build_slurm_cubeflow_nodes(),
            tick=int(live.get("tick", 0)),
            mode=live.get("mode", "normal"),
        )
        return get_device_detail(device_id, slurm_nodes=slurm, live=live)

    def get_facility_overview(self) -> dict[str, Any]:
        live = self.get_live()
        power = enrich_power_chain(live)
        cooling = enrich_cooling_chain(live)
        halls = enrich_halls(live)
        modules = enrich_modules(live)
        return {
            "power": power,
            "cooling": cooling,
            "halls": halls,
            "modules": modules,
            "power_talkers": rank_by_score(power, limit=5),
            "cooling_talkers": rank_by_score(cooling, limit=5),
            "hall_talkers": rank_by_score(halls, limit=5),
            "live": {
                "it_load_mw": live.get("it_load_mw"),
                "pue": live.get("pue"),
                "ups_load_pct": live.get("ups_load_pct"),
                "cooling_load_pct": live.get("cooling_load_pct"),
                "liquid_loop_temp_c": live.get("liquid_loop_temp_c"),
                "return_temp_c": live.get("return_temp_c"),
                "utilization_pct": live.get("utilization_pct"),
                "critical_it_mw": live.get("critical_it_mw"),
                "design_capacity_mw": live.get("design_capacity_mw"),
                "bess_soc_pct": live.get("bess_soc_pct"),
            },
        }

    def get_power_stage_detail(self, stage_id: str) -> dict[str, Any] | None:
        live = self.get_live()
        tick = int(live.get("tick", 0))
        stages = enrich_power_chain(live)
        stage = next((s for s in stages if s["id"] == stage_id), None)
        if not stage:
            return None
        series = {
            "load": sample_stage_series(stage_id, metric="load", tick=tick, base=stage["load_pct"]),
            "power": sample_stage_series(stage_id, metric="kw", tick=tick, base=stage["power_kw"]),
        }
        return {"stage": stage, "chain": stages, "series": series}

    def get_cooling_stage_detail(self, stage_id: str) -> dict[str, Any] | None:
        live = self.get_live()
        tick = int(live.get("tick", 0))
        stages = enrich_cooling_chain(live)
        stage = next((s for s in stages if s["id"] == stage_id), None)
        if not stage:
            return None
        series = {
            "load": sample_stage_series(stage_id, metric="cload", tick=tick, base=stage["load_pct"]),
            "supply": sample_stage_series(stage_id, metric="sup", tick=tick, base=stage["supply_c"]),
            "return": sample_stage_series(stage_id, metric="ret", tick=tick, base=stage["return_c"]),
            "flow": sample_stage_series(stage_id, metric="flow", tick=tick, base=stage["flow_lpm"]),
        }
        return {"stage": stage, "chain": stages, "series": series}

    def get_hall_detail(self, hall_id: str) -> dict[str, Any] | None:
        live = self.get_live()
        tick = int(live.get("tick", 0))
        halls = enrich_halls(live)
        hall = next((h for h in halls if h["id"] == hall_id), None)
        if not hall:
            return None
        series = {
            "live_mw": sample_stage_series(hall_id, metric="mw", tick=tick, base=hall["live_mw"]),
            "util": sample_stage_series(hall_id, metric="util", tick=tick, base=hall["util_pct"]),
        }
        return {"hall": hall, "halls": halls, "modules": enrich_modules(live), "series": series}

    def get_cloud_bundle(self) -> dict[str, Any]:
        live = self.get_live()
        catalog = self.get_json("cloud_catalog") or build_cloud_catalog()
        return {
            "catalog": catalog,
            "live": {
                "nhn_gpu_util_pct": live.get("nhn_gpu_util_pct"),
                "nhn_active_instances": live.get("nhn_active_instances"),
                "aws_gpu_util_pct": live.get("aws_gpu_util_pct"),
                "aws_running_instances": live.get("aws_running_instances"),
                "gcp_storage_used_tb": live.get("gcp_storage_used_tb"),
                "gcp_ops_per_s": live.get("gcp_ops_per_s"),
            },
        }

    def get_cloud_overview(self) -> dict[str, Any]:
        live = self.get_live()
        tick = int(live.get("tick", 0))
        catalog = self.get_json("cloud_catalog") or build_cloud_catalog()
        aws = enrich_aws_instances(catalog["aws"]["instances"], tick=tick)
        nhn = enrich_nhn_instances(catalog["nhn"]["instances"], tick=tick)
        buckets = enrich_gcp_buckets(catalog["gcp"]["buckets"], tick=tick)
        disks = enrich_gcp_disks(catalog["gcp"]["disks"], tick=tick)
        return {
            "aws": {**catalog["aws"], "instances": aws},
            "gcp": {**catalog["gcp"], "buckets": buckets, "disks": disks},
            "nhn": {**catalog["nhn"], "instances": nhn},
            "aws_talkers": rank_cloud(aws, limit=8),
            "nhn_talkers": rank_cloud(nhn, limit=8),
            "gcp_talkers": rank_cloud(buckets, limit=5),
            "live": {
                "nhn_gpu_util_pct": live.get("nhn_gpu_util_pct"),
                "nhn_active_instances": live.get("nhn_active_instances"),
                "aws_gpu_util_pct": live.get("aws_gpu_util_pct"),
                "aws_running_instances": live.get("aws_running_instances"),
                "gcp_storage_used_tb": live.get("gcp_storage_used_tb"),
                "gcp_ops_per_s": live.get("gcp_ops_per_s"),
            },
        }

    def get_aws_instance_detail(self, instance_id: str) -> dict[str, Any] | None:
        live = self.get_live()
        tick = int(live.get("tick", 0))
        catalog = self.get_json("cloud_catalog") or build_cloud_catalog()
        instances = enrich_aws_instances(catalog["aws"]["instances"], tick=tick)
        inst = next((i for i in instances if i["id"] == instance_id), None)
        if not inst:
            return None
        series = sample_cloud_series(instance_id, base=inst["util_pct"], tick=tick)
        return {"instance": inst, "provider": catalog["aws"], "series": series}

    def get_nhn_instance_detail(self, instance_id: str) -> dict[str, Any] | None:
        live = self.get_live()
        tick = int(live.get("tick", 0))
        catalog = self.get_json("cloud_catalog") or build_cloud_catalog()
        instances = enrich_nhn_instances(catalog["nhn"]["instances"], tick=tick)
        inst = next((i for i in instances if i["id"] == instance_id), None)
        if not inst:
            return None
        series = sample_cloud_series(instance_id, base=inst["util_pct"], tick=tick)
        return {"instance": inst, "provider": catalog["nhn"], "series": series}

    def get_gcp_bucket_detail(self, bucket_id: str) -> dict[str, Any] | None:
        live = self.get_live()
        tick = int(live.get("tick", 0))
        catalog = self.get_json("cloud_catalog") or build_cloud_catalog()
        buckets = enrich_gcp_buckets(catalog["gcp"]["buckets"], tick=tick)
        bucket = next((b for b in buckets if b["id"] == bucket_id), None)
        if not bucket:
            return None
        series = {
            "ops": sample_cloud_series(bucket_id + "-ops", base=bucket["ops_per_s"], tick=tick),
            "used": sample_cloud_series(bucket_id + "-tb", base=bucket["used_tb"], tick=tick),
        }
        return {"bucket": bucket, "provider": catalog["gcp"], "series": series}

    def get_gcp_disk_detail(self, disk_id: str) -> dict[str, Any] | None:
        live = self.get_live()
        tick = int(live.get("tick", 0))
        catalog = self.get_json("cloud_catalog") or build_cloud_catalog()
        disks = enrich_gcp_disks(catalog["gcp"]["disks"], tick=tick)
        disk = next((d for d in disks if d["id"] == disk_id), None)
        if not disk:
            return None
        series = sample_cloud_series(disk_id, base=disk["iops"], tick=tick)
        return {"disk": disk, "provider": catalog["gcp"], "series": series}

    def get_cost_bundle(self) -> dict[str, Any]:
        live = self.get_live()
        return {
            "dc": self.get_json("cost_dc") or build_dc_cost_baseline(),
            "cloud": self.get_json("cost_cloud") or build_cloud_cost_baseline(),
            "trends": self.get_json("cost_trends") or build_cost_monthly_trends(),
            "live": live.get("cost") or live_cost_snapshot(live.get("tick", 0), live.get("mode", "normal")),
        }

    def get_fractos_bundle(self) -> dict[str, Any]:
        live = self.get_live()
        data = self.get_json("fractos") or build_fractos_bundle_static()
        data["live"] = {
            "fractos_gpu_util_pct": live.get("fractos_gpu_util_pct"),
            "fractos_cpu_util_pct": live.get("fractos_cpu_util_pct"),
            "fractos_mem_util_pct": live.get("fractos_mem_util_pct"),
            "fractos_disk_util_pct": live.get("fractos_disk_util_pct"),
            "fractos_net_gbps": live.get("fractos_net_gbps"),
            "fractos_power_kw": live.get("fractos_power_kw"),
            "fractos_gpu_temp_c": live.get("fractos_gpu_temp_c"),
            "fractos_pods_running": live.get("fractos_pods_running"),
        }
        return data

    def dump_simulation_bundle(self) -> dict[str, Any]:
        return {
            "site": self.get_json("site"),
            "live": self.get_live(),
            "modules": self.get_modules(),
            "halls": self.get_json("halls"),
            "zones": self.get_json("zones"),
            "vendors": self.get_json("vendors"),
            "power_chain": self.get_json("power_chain"),
            "cooling_chain": self.get_json("cooling_chain"),
            "it": self.get_it_bundle(),
            "cloud": self.get_cloud_bundle(),
            "cost": self.get_cost_bundle(),
            "fractos": self.get_fractos_bundle(),
            "network": self.get_network_bundle(),
            "storage": self.get_storage_overview() if hasattr(self, "get_storage_overview") else {},
            "alerts": self.get_alerts(20),
            "history_sample": self.get_history(20),
            "meta": self.redis.hgetall(f"{REDIS_KEY_PREFIX}:meta"),
        }


