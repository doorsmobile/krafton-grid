"""Jobs, RCS services, custom images."""

from __future__ import annotations

from typing import Any

def build_fractos_jobs() -> list[dict[str, Any]]:
    return [
        {
            "id": "JOB-20441",
            "name": "llama70b-sft",
            "project": "PRJ-01",
            "type": "train",
            "mode": "multi-node",
            "gpus": 64,
            "nodes": 8,
            "image": "img/pytorch-2.5-cuda12:latest",
            "status": "Running",
            "schedule": "immediate",
            "user": "user03",
            "created": "2026-09-23T08:10:00Z",
            "runtime": "1d 04h",
        },
        {
            "id": "JOB-20512",
            "name": "rlhf-rollout",
            "project": "PRJ-01",
            "type": "train",
            "mode": "multi-gpu",
            "gpus": 32,
            "nodes": 4,
            "image": "img/pytorch-2.5-cuda12:latest",
            "status": "Running",
            "schedule": "cron:0 */6 * * *",
            "user": "user07",
            "created": "2026-09-24T01:00:00Z",
            "runtime": "11h",
        },
        {
            "id": "JOB-20601",
            "name": "batch-eval-suite",
            "project": "PRJ-02",
            "type": "batch",
            "mode": "single",
            "gpus": 8,
            "nodes": 1,
            "image": "img/eval-harness:1.4",
            "status": "Queued",
            "schedule": "batch-template:eval-nightly",
            "user": "user11",
            "created": "2026-09-24T04:20:00Z",
            "runtime": "—",
        },
        {
            "id": "JOB-20655",
            "name": "oneclick-jupyter",
            "project": "PRJ-04",
            "type": "notebook",
            "mode": "fraction",
            "gpus": 1,
            "nodes": 1,
            "image": "img/jupyter-cuda:2025.06",
            "status": "Running",
            "schedule": "one-click",
            "user": "user02",
            "created": "2026-09-24T05:01:00Z",
            "runtime": "2h",
        },
        {
            "id": "JOB-20710",
            "name": "infer-api-canary",
            "project": "PRJ-04",
            "type": "serve",
            "mode": "rcs",
            "gpus": 4,
            "nodes": 2,
            "image": "img/vllm-openai:0.6",
            "status": "Running",
            "schedule": "rcs-deploy",
            "user": "user01",
            "created": "2026-09-22T12:00:00Z",
            "runtime": "2d",
        },
        {
            "id": "JOB-20788",
            "name": "pretrain-ckpt-resume",
            "project": "PRJ-01",
            "type": "train",
            "mode": "multi-node",
            "gpus": 128,
            "nodes": 16,
            "image": "img/megatron-lm:core024",
            "status": "Pending",
            "schedule": "queued-priority:high",
            "user": "user03",
            "created": "2026-09-24T06:40:00Z",
            "runtime": "—",
        },
    ]


# ---- Cluster nodes ----

def build_rcs_services() -> list[dict[str, Any]]:
    return [
        {
            "id": "RCS-01",
            "name": "npc-infer",
            "project": "PRJ-04",
            "image": "img/vllm-openai:0.6",
            "replicas": 3,
            "ready": 3,
            "service_type": "ClusterIP",
            "ingress": "npc-infer.aidc.krafton.local",
            "version": "v1.4.2",
            "status": "Healthy",
            "autoscaling": "HPA 2–8",
            "gpus_per_pod": 1,
        },
        {
            "id": "RCS-02",
            "name": "asr-gateway",
            "project": "PRJ-03",
            "image": "img/tritonserver:24.12",
            "replicas": 2,
            "ready": 2,
            "service_type": "NodePort",
            "ingress": "asr.aidc.krafton.local",
            "version": "v0.9.1",
            "status": "Healthy",
            "autoscaling": "HPA 1–4",
            "gpus_per_pod": 1,
        },
        {
            "id": "RCS-03",
            "name": "llm-api-canary",
            "project": "PRJ-01",
            "image": "img/vllm-openai:0.6",
            "replicas": 4,
            "ready": 3,
            "service_type": "Ingress",
            "ingress": "llm-canary.aidc.krafton.local",
            "version": "v2.0.0-rc1",
            "status": "Progressing",
            "autoscaling": "HPA 2–12",
            "gpus_per_pod": 2,
        },
    ]


# ---- Custom images ----

def build_images() -> list[dict[str, Any]]:
    return [
        {"id": "IMG-01", "name": "pytorch-2.5-cuda12", "tag": "latest", "size_gb": 18.4, "project": "shared", "framework": "PyTorch", "updated": "2026-09-20"},
        {"id": "IMG-02", "name": "jupyter-cuda", "tag": "2025.06", "size_gb": 12.1, "project": "shared", "framework": "Jupyter", "updated": "2026-09-18"},
        {"id": "IMG-03", "name": "megatron-lm", "tag": "core024", "size_gb": 22.0, "project": "PRJ-01", "framework": "Megatron", "updated": "2026-09-22"},
        {"id": "IMG-04", "name": "vllm-openai", "tag": "0.6", "size_gb": 9.8, "project": "shared", "framework": "vLLM", "updated": "2026-09-15"},
        {"id": "IMG-05", "name": "eval-harness", "tag": "1.4", "size_gb": 6.2, "project": "PRJ-02", "framework": "Eval", "updated": "2026-09-12"},
        {"id": "IMG-06", "name": "tritonserver", "tag": "24.12", "size_gb": 14.5, "project": "PRJ-03", "framework": "Triton", "updated": "2026-09-10"},
    ]


# ---- AI Ecosystem ----

