"""Nodes, events, ecosystem, notices, usage reports."""

from __future__ import annotations

import random
from typing import Any

def build_fractos_nodes(count: int = 16) -> list[dict[str, Any]]:
    nodes = []
    for i in range(1, count + 1):
        util = round(random.uniform(35, 94), 1)
        nodes.append(
            {
                "id": f"NODE-{i:02d}",
                "hostname": f"hgx-b300-{i:03d}",
                "role": "gpu-worker",
                "status": "Ready" if i != 14 else "NotReady",
                "vendor_mix": "NVIDIA" if i % 5 else "NVIDIA+AMD",
                "gpus": 8,
                "gpu_util_pct": util,
                "cpu_util_pct": round(util * 0.55 + random.uniform(-5, 5), 1),
                "mem_util_pct": round(util * 0.7 + random.uniform(-8, 8), 1),
                "disk_util_pct": round(random.uniform(28, 72), 1),
                "net_gbps": round(random.uniform(40, 180), 1),
                "gpu_temp_c": round(42 + util * 0.32, 1),
                "power_w": int(3800 + util * 42),
                "pods": int(4 + util / 12),
                "images": int(18 + i % 7),
                "registry_ok": i != 14,
            }
        )
    return nodes

def build_cluster_events() -> list[dict[str, Any]]:
    return [
        {"ts": "2026-09-24T05:12:01Z", "type": "Normal", "object": "NODE-03", "message": "CubeFlow agent heartbeat ok"},
        {"ts": "2026-09-24T05:08:44Z", "type": "Warning", "object": "NODE-14", "message": "Kubelet not ready — restarting"},
        {"ts": "2026-09-24T04:55:10Z", "type": "Normal", "object": "JOB-20512", "message": "Scheduled on AGG-02"},
        {"ts": "2026-09-24T04:40:22Z", "type": "Normal", "object": "PRJ-01", "message": "Quota soft-limit GPU 75%"},
        {"ts": "2026-09-24T03:11:09Z", "type": "Warning", "object": "NODE-07", "message": "GPU-07 temp spike 86°C — throttled"},
        {"ts": "2026-09-24T02:02:33Z", "type": "Normal", "object": "RCS-svc-npc", "message": "RollingUpdate to v1.4.2 complete"},
    ]


# ---- RCS (Rapid Container Service) ----

def build_ecosystem() -> dict[str, Any]:
    return {
        "ide": ["VS Code Server", "JupyterLab", "PyCharm Gateway"],
        "experiment_tracking": ["MLflow", "Weights & Biases", "TensorBoard"],
        "pipeline": ["Kubeflow Pipelines", "Airflow", "Argo Workflows"],
        "training": ["PyTorch", "Megatron-LM", "DeepSpeed", "JAX"],
        "serving": ["vLLM", "Triton", "TorchServe", "TensorRT-LLM"],
        "llms": [
            {"name": "Llama-3.2-1B", "params": "1B", "task": "edge"},
            {"name": "Llama-3.3-70B-Instruct", "params": "70B", "task": "chat"},
            {"name": "Llama-3.2-90B-Vision-Instruct", "params": "90B", "task": "vision"},
            {"name": "Ministral-8B-Instruct", "params": "8B", "task": "chat"},
            {"name": "Mixtral-8x22B", "params": "8x22B", "task": "moe"},
            {"name": "Falcon-40B-Instruct", "params": "40B", "task": "chat"},
        ],
    }

def build_notices() -> list[dict[str, Any]]:
    return [
        {"id": "NTC-01", "level": "info", "title": "GPU Platform maintenance", "body": "Registry GC Sunday 02:00 KST", "ts": "2026-09-23"},
        {"id": "NTC-02", "level": "warn", "title": "GPU quota near limit", "body": "PRJ-01 at 75% GPU quota", "ts": "2026-09-24"},
        {"id": "NTC-03", "level": "error", "title": "NODE-14 NotReady", "body": "Kubelet restart in progress", "ts": "2026-09-24"},
    ]

def build_usage_report() -> list[dict[str, Any]]:
    return [
        {"project": "PRJ-01", "gpu_hours": 18420, "cpu_hours": 92000, "storage_tb_days": 4200, "cost_krw": 92_000_000},
        {"project": "PRJ-02", "gpu_hours": 6100, "cpu_hours": 24000, "storage_tb_days": 1100, "cost_krw": 28_500_000},
        {"project": "PRJ-03", "gpu_hours": 980, "cpu_hours": 4200, "storage_tb_days": 260, "cost_krw": 4_800_000},
        {"project": "PRJ-04", "gpu_hours": 12100, "cpu_hours": 51000, "storage_tb_days": 2800, "cost_krw": 61_200_000},
    ]

