"""GPU Platform catalogs: notices, image registry, ecosystem, RCS sessions, chargeback."""
from __future__ import annotations

from . import topology as T

NOTICES = [
    {"date": "2026-09-29", "level": "info", "title": "B300 driver 580.95 · CUDA 13.0.2 rollout",
     "text": "Rolling update on train partition racks R01–R16 completed; R17–R30 scheduled this week (no job impact, drain-and-resume)."},
    {"date": "2026-09-26", "level": "warning", "title": "IB fabric maintenance window",
     "text": "UFM firmware upgrade on ib-spine-01..06 · 2026-10-04 02:00–04:00 KST. Multi-node jobs spanning spines will be held."},
    {"date": "2026-09-22", "level": "info", "title": "MIG profile 3g.144gb available on infer",
     "text": "Inference pools can now request half-GPU slices with 144 GB HBM for 30B-class models."},
    {"date": "2026-09-18", "level": "info", "title": "Idle GPU culling for notebooks",
     "text": "RCS / Jupyter sessions idle for 60 min release their GPUs automatically starting 2026-10-01."},
]

IMAGES = [
    {"repo": "grid/pytorch", "tag": "2.9-cuda13.0-b300", "size_gb": 12.4, "cuda": "13.0", "updated": "2026-09-27", "pulls_7d": 18420, "crit": 0, "high": 1, "signed": True},
    {"repo": "grid/nemo", "tag": "25.09", "size_gb": 21.8, "cuda": "13.0", "updated": "2026-09-24", "pulls_7d": 9310, "crit": 0, "high": 0, "signed": True},
    {"repo": "grid/megatron-lm", "tag": "core-0.14-moe", "size_gb": 17.2, "cuda": "13.0", "updated": "2026-09-21", "pulls_7d": 12880, "crit": 0, "high": 2, "signed": True},
    {"repo": "grid/vllm", "tag": "0.11.2-b300", "size_gb": 9.6, "cuda": "13.0", "updated": "2026-09-28", "pulls_7d": 6410, "crit": 0, "high": 0, "signed": True},
    {"repo": "grid/tensorrt-llm", "tag": "1.2.0", "size_gb": 14.1, "cuda": "13.0", "updated": "2026-09-19", "pulls_7d": 3920, "crit": 0, "high": 1, "signed": True},
    {"repo": "grid/jax", "tag": "0.7-cuda13", "size_gb": 10.3, "cuda": "13.0", "updated": "2026-09-12", "pulls_7d": 1180, "crit": 0, "high": 0, "signed": True},
    {"repo": "team-ally/ally-rl", "tag": "grpo-v3.1", "size_gb": 15.9, "cuda": "13.0", "updated": "2026-09-29", "pulls_7d": 2240, "crit": 1, "high": 3, "signed": False},
    {"repo": "team-zoi/persona-train", "tag": "2026.09.3", "size_gb": 13.6, "cuda": "12.9", "updated": "2026-09-25", "pulls_7d": 1970, "crit": 0, "high": 2, "signed": True},
    {"repo": "grid/rcs-dev", "tag": "vscode-jupyter-1.8", "size_gb": 8.2, "cuda": "13.0", "updated": "2026-09-20", "pulls_7d": 4470, "crit": 0, "high": 0, "signed": True},
]

ECOSYSTEM = [
    {"name": "JupyterHub / VS Code (RCS)", "kind": "Dev environment", "ns": "rcs", "url": "https://rcs.grid.krafton.internal"},
    {"name": "CubeFlow Pipelines", "kind": "MLOps orchestration", "ns": "cubeflow", "url": "https://cubeflow.grid.krafton.internal"},
    {"name": "MLflow Tracking", "kind": "Experiment tracking", "ns": "cubeflow", "url": "https://mlflow.grid.krafton.internal"},
    {"name": "Model Registry & LLM Catalog", "kind": "Model registry", "ns": "gpu-platform", "url": "https://models.grid.krafton.internal"},
    {"name": "Milvus", "kind": "Vector database", "ns": "vector-db", "url": "grpc://milvus.grid:19530"},
    {"name": "Feast", "kind": "Feature store", "ns": "feature-store", "url": "https://feast.grid.krafton.internal"},
    {"name": "Harbor", "kind": "Container registry", "ns": "registry", "url": "https://harbor.grid.krafton.internal"},
    {"name": "Grafana · Loki · Tempo", "kind": "Observability", "ns": "observability", "url": "https://observe.grid.krafton.internal"},
]

LLM_CATALOG = [
    {"model": "KG-LLM-70B-Instruct", "owner": "llm-pretrain", "kind": "in-house", "params_b": 70, "ctx_k": 128, "serving": "vllm-kg-70b", "precision": "FP8"},
    {"model": "KG-LLM-8B-Distill", "owner": "llm-pretrain", "kind": "in-house", "params_b": 8, "ctx_k": 64, "serving": "trtllm-ally-8b", "precision": "FP8"},
    {"model": "Ally-CPC-8B", "owner": "pubg-ally", "kind": "in-house", "params_b": 8, "ctx_k": 32, "serving": "trtllm-ally-8b", "precision": "NVFP4"},
    {"model": "Zoi-Persona-13B", "owner": "inzoi-smartzoi", "kind": "in-house", "params_b": 13, "ctx_k": 32, "serving": "zoi-dialogue-svc", "precision": "FP8"},
    {"model": "KG-Voice-TTS-KR v3", "owner": "speech-voice", "kind": "in-house", "params_b": 1.2, "ctx_k": 0, "serving": "tts-stream", "precision": "BF16"},
    {"model": "E5-multilingual-large", "owner": "inference-prod", "kind": "open-weights", "params_b": 0.56, "ctx_k": 0.5, "serving": "embed-e5", "precision": "FP16"},
]

CHARGEBACK_KRW_PER_GPU_HR = 2600


def ecosystem_status(k8s) -> list[dict]:
    out = []
    for e in ECOSYSTEM:
        pods = [p for p in k8s.pods if p["namespace"] == e["ns"]]
        bad = sum(1 for p in pods if p["status"] != "Running")
        out.append({**e, "pods": len(pods), "unhealthy": bad,
                    "status": "healthy" if bad == 0 else ("degraded" if bad < max(2, len(pods) // 3) else "down")})
    return out


def rcs_sessions(fleet, now: float) -> list[dict]:
    out = []
    for j in fleet.jobs.values():
        if j.profile != "notebook" or j.state != "RUNNING":
            continue
        idx = j.gpus
        util = float(fleet.util[idx].mean()) if idx else 0.0
        out.append({"id": f"rcs-{j.id % 100000:05d}", "job": j.id, "user": j.user, "project": j.project,
                    "image": "grid/rcs-dev:vscode-jupyter-1.8" if j.name != "jupyter" else "grid/pytorch:2.9-cuda13.0-b300",
                    "kind": {"jupyter": "JupyterLab", "vscode-remote": "VS Code", "rcs-dev": "Shell"}.get(j.name, "JupyterLab"),
                    "gpus": len(idx), "node": T.NODE_IDS[idx[0] // 8] if idx else "—", "util": round(util, 1),
                    "uptime_s": round(now - j.start_t), "idle": util < 5,
                    "url": f"https://rcs.grid.krafton.internal/s/{j.id % 100000:05d}"})
    return sorted(out, key=lambda r: -r["uptime_s"])


def llm_catalog(fleet) -> list[dict]:
    services = {}
    for j in fleet.jobs.values():
        if j.service and j.state == "RUNNING":
            services.setdefault(j.name, []).append(j)
    out = []
    for m in LLM_CATALOG:
        js = services.get(m["serving"], [])
        gpus = sum(len(j.gpus) for j in js)
        mig = sum(1 for gi, inst in fleet.mig.items() for x in inst if x["service"] == m["serving"])
        out.append({**m, "replicas": len(js), "gpus": gpus, "mig_slices": mig,
                    "status": "serving" if (js or mig) else "registered"})
    return out
