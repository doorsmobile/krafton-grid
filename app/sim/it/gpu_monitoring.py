"""Datadog-inspired GPU Monitoring fleet model (sim).

Mirrors concepts from https://docs.datadoghq.com/gpu_monitoring/ and
/gpu_monitoring/fleet/: funnel (total/allocated/active/effective/idle),
provisioning vs performance views, OOTB monitors, recommendations,
connected entities (pods / processes / Slurm), and device telemetry
(SM util, saturation, memory, PCIe, NVLink, power, temp, ECC, XID).
"""

from __future__ import annotations

import math
import random
import time
from datetime import datetime, timezone
from typing import Any

from app.sim.it.constants import GPU_COUNT, GPU_MODEL, GPUS_PER_NODE
from app.sim.telemetry import stable_seed

# ~$4.2/GPU-hr on-prem equivalent for idle cost demos
_GPU_HOURLY_USD = 4.2


def _iso(age_min: int = 0) -> str:
    return datetime.fromtimestamp(int(time.time()) - age_min * 60, tz=timezone.utc).isoformat()


def build_gpu_devices(slurm_nodes: list[dict[str, Any]], *, tick: int = 0, mode: str = "normal") -> list[dict[str, Any]]:
    """Sample device inventory (one GPU per listed Slurm node × GPUs_PER_NODE subset)."""
    devices: list[dict[str, Any]] = []
    # Cap device rows for UI (demo sample of fleet)
    host_slice = slurm_nodes[:24]
    for ni, node in enumerate(host_slice):
        n_gpu = min(GPUS_PER_NODE, int(node.get("gpus_total") or GPUS_PER_NODE))
        for gi in range(n_gpu):
            did = f"{node['id']}-gpu{gi}"
            seed = stable_seed(did + str(tick // 4))
            alloc = node.get("slurm_state", "").startswith("ALLOC") or node.get("slurm_state") == "MIXED"
            base_sm = float(node.get("cubeflow", {}).get("gpu_util_pct", 40))
            wave = 0.88 + 0.12 * math.sin(tick / 14.0 + seed * 5 + gi)
            factor = 1.2 if mode == "stress" else (0.65 if mode == "maintenance" else 1.0)
            # Simulate zombie / idle allocations on some GPUs
            zombie = alloc and (gi % 5 == 4 or (node.get("slurm_state") == "MIXED" and gi % 2 == 1))
            if not alloc:
                sm = round(seed * 4, 1)
            elif zombie:
                sm = round(seed * 3.5, 1)
            else:
                sm = round(min(99.0, base_sm * wave * factor * (0.85 + 0.15 * seed)), 1)
            active = sm > 5.0
            effective = sm > 35.0
            mem = round(min(98.0, (sm * (0.75 + 0.2 * seed) + random.uniform(-2, 2)) if active else seed * 12), 1)
            sat = round(min(100.0, sm * (0.7 + 0.35 * seed)), 1)
            power_w = int(280 + sm * 42 + seed * 80)
            power_limit = 700
            temp = round(32 + sm * 0.38 + random.uniform(-1.5, 1.5), 1)
            throttle = sm > 92 and power_w > power_limit * 0.92
            ecc = int(max(0, (temp - 78) * 0.4 + random.uniform(0, 0.6))) if temp > 78 else 0
            xid = 1 if (seed < 0.04 and mode == "stress") or (temp > 85 and seed < 0.15) else 0
            pcie_rx = round((40 + seed * 180) * (sm / 100) * 1e6, 0)
            pcie_tx = round((35 + seed * 160) * (sm / 100) * 1e6, 0)
            nv_rx = round((8 + seed * 40) * (sm / 100) * 1e9, 0)
            nv_tx = round((7 + seed * 38) * (sm / 100) * 1e9, 0)
            team = ["ml-platform", "foundation", "inference", "research"][ni % 4]
            service = ["train-llm", "sft-70b", "serve-api", "eval-bench"][ni % 4]
            devices.append(
                {
                    "id": did,
                    "index": gi,
                    "host_id": node["id"],
                    "hostname": node["hostname"],
                    "rack": node.get("rack"),
                    "device_type": GPU_MODEL,
                    "provider": "on-prem",
                    "cluster": "kg-aidc-m1",
                    "region": "KR-AIDC",
                    "datacenter": "Krafton Grid M1",
                    "team": team,
                    "service": service,
                    "partition": node.get("partition"),
                    "allocated": alloc,
                    "active": active,
                    "effective": effective,
                    "idle": alloc and not active,
                    "sm_util_pct": sm,
                    "gpu_saturation_pct": sat,
                    "gpu_memory_pct": mem,
                    "graphics_activity_pct": round(sm * 0.95, 1),
                    "power_w": power_w,
                    "power_limit_w": power_limit,
                    "power_cap_throttle": throttle,
                    "temp_c": temp,
                    "sm_clock_mhz": int(1200 + sm * 8),
                    "pcie_rx_bps": pcie_rx,
                    "pcie_tx_bps": pcie_tx,
                    "nvlink_rx_bps": nv_rx,
                    "nvlink_tx_bps": nv_tx,
                    "nvlink_active_links": 18 if active else (4 if alloc else 0),
                    "ecc_errors": ecc,
                    "xid_errors": xid,
                    "slurm_job": node.get("slurm_job") or "—",
                    "user": node.get("user") or "—",
                    "score": sm,
                    "hourly_usd": _GPU_HOURLY_USD,
                    "idle_cost_usd_h": round(_GPU_HOURLY_USD if (alloc and not active) else 0, 2),
                }
            )
    return devices


def build_connected_pods(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_svc: dict[str, list] = {}
    for d in devices:
        if not d["allocated"]:
            continue
        by_svc.setdefault(d["service"], []).append(d)
    pods = []
    for i, (svc, devs) in enumerate(by_svc.items(), start=1):
        sm = round(sum(d["sm_util_pct"] for d in devs) / len(devs), 1)
        mem = round(sum(d["gpu_memory_pct"] for d in devs) / len(devs), 1)
        pods.append(
            {
                "id": f"k8s/{svc}",
                "name": svc,
                "namespace": "gpu-ops" if i % 2 else "ml-training",
                "team": devs[0]["team"],
                "gpus": len(devs),
                "sm_util_pct": sm,
                "gpu_memory_pct": mem,
                "status": "Running" if sm > 5 else "Idle",
                "score": sm,
            }
        )
    return pods


def build_connected_processes(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    procs = []
    for i, d in enumerate(devices[:18]):
        if not d["active"]:
            continue
        seed = stable_seed(d["id"] + "-proc")
        procs.append(
            {
                "pid": 20000 + i * 17,
                "name": ["python", "torchrun", "tritonserver", "vllm"][i % 4],
                "cmdline": f"{['train.py','sft.py','serve','bench'][i % 4]} --gpus 8",
                "device_id": d["id"],
                "host_id": d["host_id"],
                "sm_util_pct": round(d["sm_util_pct"] * (0.7 + 0.3 * seed), 1),
                "gpu_memory_mb": int(12000 + seed * 60000),
                "user": d["user"],
                "team": d["team"],
            }
        )
    return procs


def build_ootb_monitors(devices: list[dict[str, Any]], unmet_requests: int = 0) -> list[dict[str, Any]]:
    hot = [d for d in devices if d["temp_c"] >= 80]
    throttle = [d for d in devices if d["power_cap_throttle"]]
    xid = [d for d in devices if d["xid_errors"] > 0]
    ecc = [d for d in devices if d["ecc_errors"] > 0]
    idle = [d for d in devices if d["idle"]]
    bursty = [d for d in devices if d["sm_util_pct"] > 95]
    monitors = [
        {
            "id": "temp-spike",
            "name": "Temperature spikes",
            "severity": "critical" if any(d["temp_c"] >= 85 for d in hot) else ("warn" if hot else "ok"),
            "count": len(hot),
            "metric": "gpu.temperature",
            "threshold": "≥ 80°C",
            "remediation": [
                "Identify affected devices in Performance inventory",
                "Check CDU / cold-plate flow and rack inlet temp",
                "Drain or cordon host if thermal throttling persists",
            ],
        },
        {
            "id": "power-cap",
            "name": "Power cap throttling",
            "severity": "warn" if throttle else "ok",
            "count": len(throttle),
            "metric": "gpu.power.usage",
            "threshold": "> 92% of power limit",
            "remediation": [
                "Raise rack power budget or reduce concurrent jobs",
                "Verify HGX power policy / nvidia-smi power limit",
                "Move bursty jobs to underutilized partitions",
            ],
        },
        {
            "id": "unmet-gpu",
            "name": "Unmet GPU requests",
            "severity": "warn" if unmet_requests else "ok",
            "count": unmet_requests,
            "metric": "kubernetes_state.container.gpu_requested",
            "threshold": "pending > 0",
            "remediation": [
                "Reclaim idle allocated devices (zombie processes)",
                "Check Slurm / K8s queue fairness for team quotas",
                "Forecast capacity — consider next modular block",
            ],
        },
        {
            "id": "xid-critical",
            "name": "Critical XID errors",
            "severity": "critical" if xid else "ok",
            "count": len(xid),
            "metric": "gpu.errors.xid.total",
            "threshold": "XID > 0",
            "remediation": [
                "Map XID code to NVIDIA guide (driver / HW)",
                "Isolate device; recreate workload on healthy GPU",
                "Open RMA if ECC remapped rows escalate",
            ],
        },
        {
            "id": "ecc",
            "name": "ECC errors",
            "severity": "warn" if ecc else "ok",
            "count": len(ecc),
            "metric": "gpu.errors.ecc.uncorrected",
            "threshold": "uncorrected > 0",
            "remediation": [
                "Inspect remapped rows on the device",
                "Schedule host maintenance window",
                "Track recurrence — escalate to vendor if rising",
            ],
        },
        {
            "id": "bursty",
            "name": "Bursty workloads",
            "severity": "info" if bursty else "ok",
            "count": len(bursty),
            "metric": "gpu.sm_active",
            "threshold": "SM util > 95%",
            "remediation": [
                "Confirm batch size / tensor parallelism is intentional",
                "Watch NVLink / PCIe saturation for fabric bottlenecks",
            ],
        },
        {
            "id": "idle-devices",
            "name": "Idle devices",
            "severity": "warn" if len(idle) >= 3 else ("info" if idle else "ok"),
            "count": len(idle),
            "metric": "gpu.gr_engine_active",
            "threshold": "allocated & engine idle",
            "remediation": [
                "Kill zombie processes holding GPU context",
                "Release Slurm allocation or scale K8s replicas down",
                "Attribute idle cost to owning team for chargeback",
            ],
        },
    ]
    return monitors


def build_recommendations(monitors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for m in monitors:
        if m["severity"] in ("critical", "warn") and m["count"] > 0:
            out.append(
                {
                    "id": m["id"],
                    "title": m["name"],
                    "severity": m["severity"],
                    "affected": m["count"],
                    "steps": m["remediation"],
                }
            )
    return out


def fleet_funnel(devices: list[dict[str, Any]], *, fleet_total: int = GPU_COUNT) -> dict[str, Any]:
    sample = len(devices)
    # Scale sample counts to fleet for funnel display
    scale = fleet_total / sample if sample else 1
    allocated = sum(1 for d in devices if d["allocated"])
    active = sum(1 for d in devices if d["active"])
    effective = sum(1 for d in devices if d["effective"])
    idle = sum(1 for d in devices if d["idle"])
    total_cost_h = round(fleet_total * _GPU_HOURLY_USD, 0)
    idle_cost_h = round(idle * scale * _GPU_HOURLY_USD, 0)
    return {
        "total": fleet_total,
        "allocated": int(allocated * scale),
        "active": int(active * scale),
        "effective": int(effective * scale),
        "idle": int(idle * scale),
        "unallocated": int((sample - allocated) * scale),
        "sample_size": sample,
        "total_cost_usd_h": total_cost_h,
        "idle_cost_usd_h": idle_cost_h,
        "total_cost_usd_mo": int(total_cost_h * 24 * 30),
        "idle_cost_usd_mo": int(idle_cost_h * 24 * 30),
    }


def allocation_series(funnel: dict[str, Any], *, tick: int, n: int = 60) -> list[dict[str, Any]]:
    pts = []
    for age in range(n - 1, -1, -1):
        wave = 0.94 + 0.06 * math.sin((tick - age) / 18.0)
        pts.append(
            {
                "t": _iso(age),
                "total": funnel["total"],
                "allocated": int(funnel["allocated"] * wave),
                "active": int(funnel["active"] * wave * 0.98),
                "forecast": int(funnel["allocated"] * (1.02 + 0.01 * (n - age) / n)),
            }
        )
    return pts


def device_type_breakdown(devices: list[dict[str, Any]], funnel: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": GPU_MODEL,
            "allocated": funnel["allocated"],
            "total": funnel["total"],
            "pct": round(100 * funnel["allocated"] / funnel["total"], 1) if funnel["total"] else 0,
        },
        {
            "type": "NVIDIA H100 (legacy)",
            "allocated": 0,
            "total": 0,
            "pct": 0,
        },
    ]


def provider_breakdown() -> list[dict[str, Any]]:
    return [
        {"name": "On-prem AIDC", "y": 92},
        {"name": "AWS GPUaaS", "y": 5},
        {"name": "NHN GPUaaS", "y": 3},
    ]


def sample_device_series(device: dict[str, Any], *, tick: int, n: int = 60) -> dict[str, list]:
    seed = stable_seed(device["id"])
    keys = {
        "sm": device["sm_util_pct"],
        "mem": device["gpu_memory_pct"],
        "power": device["power_w"],
        "temp": device["temp_c"],
        "graphics": device["graphics_activity_pct"],
        "sat": device["gpu_saturation_pct"],
    }
    out: dict[str, list] = {k: [] for k in keys}
    for age in range(n - 1, -1, -1):
        wave = 0.9 + 0.1 * math.sin((tick - age) / 11.0 + seed * 4)
        t = _iso(age)
        for k, base in keys.items():
            out[k].append({"t": t, "v": round(max(0, base * wave + (seed - 0.5) * 2), 2)})
    return out


def rank_devices(devices: list[dict[str, Any]], *, limit: int = 20, key: str = "sm_util_pct") -> list[dict[str, Any]]:
    ranked = sorted(devices, key=lambda d: d.get(key, 0), reverse=True)
    out = []
    for i, d in enumerate(ranked[:limit], start=1):
        row = dict(d)
        row["rank"] = i
        out.append(row)
    return out


def build_gpu_monitoring_bundle(
    *,
    pods_static: list[dict[str, Any]],
    slurm_nodes: list[dict[str, Any]],
    slurm_queue: list[dict[str, Any]],
    live: dict[str, Any],
) -> dict[str, Any]:
    tick = int(live.get("tick", 0))
    mode = live.get("mode", "normal")
    devices = build_gpu_devices(slurm_nodes, tick=tick, mode=mode)
    funnel = fleet_funnel(devices)
    monitors = build_ootb_monitors(devices, unmet_requests=int(live.get("slurm_jobs_pending") or 0))
    connected_pods = build_connected_pods(devices)
    processes = build_connected_processes(devices)
    return {
        "funnel": funnel,
        "allocation_series": allocation_series(funnel, tick=tick),
        "device_types": device_type_breakdown(devices, funnel),
        "providers": provider_breakdown(),
        "monitors": monitors,
        "recommendations": build_recommendations(monitors),
        "devices": devices,
        "hosts": _aggregate_hosts(devices),
        "hot_devices": rank_devices(devices, limit=12),
        "idle_devices": [d for d in devices if d["idle"]][:10],
        "connected_pods": connected_pods,
        "processes": processes,
        "slurm_jobs": slurm_queue,
        "pods": pods_static,
        "view": "performance",
        "filters": {
            "providers": ["on-prem", "aws", "nhn"],
            "device_types": [GPU_MODEL],
            "teams": sorted({d["team"] for d in devices}),
            "clusters": ["kg-aidc-m1"],
        },
    }


def _aggregate_hosts(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_host: dict[str, list] = {}
    for d in devices:
        by_host.setdefault(d["host_id"], []).append(d)
    hosts = []
    for hid, devs in by_host.items():
        sm = round(sum(d["sm_util_pct"] for d in devs) / len(devs), 1)
        mem = round(sum(d["gpu_memory_pct"] for d in devs) / len(devs), 1)
        temp = round(sum(d["temp_c"] for d in devs) / len(devs), 1)
        hosts.append(
            {
                "id": hid,
                "hostname": devs[0]["hostname"],
                "rack": devs[0]["rack"],
                "provider": "on-prem",
                "instance_type": "HGX B300",
                "device_count": len(devs),
                "allocated": sum(1 for d in devs if d["allocated"]),
                "active": sum(1 for d in devs if d["active"]),
                "sm_util_pct": sm,
                "gpu_memory_pct": mem,
                "temp_c": temp,
                "cpu_util_pct": round(20 + sm * 0.35, 1),
                "host_mem_pct": round(40 + sm * 0.25, 1),
                "team": devs[0]["team"],
                "partition": devs[0]["partition"],
                "score": sm,
            }
        )
    hosts.sort(key=lambda h: h["score"], reverse=True)
    return hosts


def get_device_detail(
    device_id: str,
    *,
    slurm_nodes: list[dict[str, Any]],
    live: dict[str, Any],
) -> dict[str, Any] | None:
    tick = int(live.get("tick", 0))
    mode = live.get("mode", "normal")
    devices = build_gpu_devices(slurm_nodes, tick=tick, mode=mode)
    device = next((d for d in devices if d["id"] == device_id), None)
    if not device:
        return None
    host_devs = [d for d in devices if d["host_id"] == device["host_id"]]
    procs = [p for p in build_connected_processes(devices) if p["device_id"] == device_id]
    pods = [p for p in build_connected_pods(devices) if any(d["service"] == p["name"] for d in host_devs)]
    recs = []
    if device["power_cap_throttle"]:
        recs.append({"title": "Power cap throttling", "steps": [
            "Check rack PDU headroom",
            "Lower concurrent SM-heavy kernels or raise power limit",
        ]})
    if device["temp_c"] >= 80:
        recs.append({"title": "Thermal hotspot", "steps": [
            "Verify liquid loop ΔT on this rack",
            "Reduce clock or migrate job if inlet high",
        ]})
    if device["idle"]:
        recs.append({"title": "Idle allocated GPU", "steps": [
            "Inspect connected processes for zombies",
            "Release Slurm allocation to reclaim cost",
        ]})
    return {
        "device": device,
        "host_devices": host_devs,
        "processes": procs,
        "pods": pods,
        "recommendations": recs,
        "series": sample_device_series(device, tick=tick),
    }
