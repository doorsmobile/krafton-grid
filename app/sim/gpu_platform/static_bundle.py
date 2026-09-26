"""Assemble GPU Platform static Redis bundle."""

from __future__ import annotations

from typing import Any

from app.sim.gpu_platform.ops_catalog import (
    build_cluster_events,
    build_ecosystem,
    build_fractos_nodes,
    build_notices,
    build_usage_report,
)
from app.sim.gpu_platform.partitions import build_gpu_aggregations, build_gpu_slices
from app.sim.gpu_platform.summary import build_fractos_summary
from app.sim.gpu_platform.tenancy import build_projects, build_users
from app.sim.gpu_platform.workloads import build_fractos_jobs, build_images, build_rcs_services

def build_fractos_bundle_static() -> dict[str, Any]:
    return {
        "summary": build_fractos_summary(),
        "slices": build_gpu_slices(),
        "aggregations": build_gpu_aggregations(),
        "projects": build_projects(),
        "users": build_users(),
        "jobs": build_fractos_jobs(),
        "nodes": build_fractos_nodes(),
        "events": build_cluster_events(),
        "rcs": build_rcs_services(),
        "images": build_images(),
        "ecosystem": build_ecosystem(),
        "notices": build_notices(),
        "usage_report": build_usage_report(),
    }

