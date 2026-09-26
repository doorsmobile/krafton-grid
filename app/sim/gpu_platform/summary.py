"""GPU Platform summary KPIs."""

from __future__ import annotations

from typing import Any

from app.sim.gpu_platform.partitions import build_gpu_aggregations, build_gpu_slices
from app.sim.gpu_platform.tenancy import build_projects, build_users
from app.sim.gpu_platform.workloads import build_fractos_jobs, build_images, build_rcs_services
from app.sim.gpu_platform.ops_catalog import build_fractos_nodes

def build_fractos_summary() -> dict[str, Any]:
    projects = build_projects()
    active = [p for p in projects if p["status"] == "active"]
    deleted = [p for p in projects if p["status"] == "deleted"]
    review = [p for p in projects if p["status"] == "review"]
    return {
        "product": "GPU Platform",
        "tier": "Full stack (sim)",
        "projects_active": len(active),
        "projects_review": len(review),
        "projects_deleted": len(deleted),
        "users": len(build_users()),
        "jobs_running": sum(1 for j in build_fractos_jobs() if j["status"] == "Running"),
        "jobs_queued": sum(1 for j in build_fractos_jobs() if j["status"] in ("Queued", "Pending")),
        "nodes_ready": sum(1 for n in build_fractos_nodes() if n["status"] == "Ready"),
        "nodes_total": len(build_fractos_nodes()),
        "slices_total": len(build_gpu_slices()),
        "slices_allocated": sum(1 for s in build_gpu_slices() if s["status"] == "allocated"),
        "rcs_services": len(build_rcs_services()),
        "features": [
            "GPU Partitioning & Aggregation",
            "MIG / NVIDIA+AMD mixed",
            "One-click scheduling",
            "Multi-GPU / Multi-node",
            "Batch jobs",
            "Projects · Users · Quota · RBAC",
            "Custom images",
            "RCS Rapid Container Service",
            "Resource & node monitoring",
            "AI Ecosystem (IDE / MLflow / LLMs)",
            "Usage reports · Notices",
        ],
    }

