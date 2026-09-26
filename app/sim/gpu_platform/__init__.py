"""GPU Platform sim backend (formerly fractos module)."""

from app.sim.gpu_platform.live import live_fractos_metrics
from app.sim.gpu_platform.static_bundle import build_fractos_bundle_static

__all__ = ["build_fractos_bundle_static", "live_fractos_metrics"]
