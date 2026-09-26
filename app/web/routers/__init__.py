"""Register all HTTP routers on the FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI

from app.web.routers import (
    api_core,
    api_it,
    api_network,
    api_observability,
    api_sim,
    auth_pages,
    cloud,
    cost,
    facility,
    gpu_platform,
    it_cluster,
    main_pages,
    network,
    observability,
    operations,
    platform,
)


def include_routers(app: FastAPI) -> None:
    app.include_router(auth_pages.router)
    app.include_router(main_pages.router)
    app.include_router(facility.router)
    app.include_router(it_cluster.router)
    app.include_router(network.router)
    app.include_router(gpu_platform.router)
    app.include_router(cloud.router)
    app.include_router(cost.router)
    app.include_router(observability.router)
    app.include_router(operations.router)
    app.include_router(platform.router)
    app.include_router(api_core.router)
    app.include_router(api_network.router)
    app.include_router(api_it.router)
    app.include_router(api_sim.router)
    app.include_router(api_observability.router)
