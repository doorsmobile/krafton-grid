"""Facility live enrichment — power stages, cooling loop, halls."""

from __future__ import annotations

import math
import random
from typing import Any

from app.sim.facility.vendors import COOLING_CHAIN, POWER_CHAIN
from app.sim.facility.models import HALLS, MODULAR_CENTERS
from app.sim.telemetry import stable_seed


def enrich_power_chain(live: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    live = live or {}
    ups = float(live.get("ups_load_pct") or 74)
    it = float(live.get("it_load_mw") or 14.8)
    out = []
    for i, step in enumerate(POWER_CHAIN, start=1):
        seed = stable_seed(step["stage"])
        base = float(step.get("load_pct") or 70)
        # bias UPS stage toward live ups metric
        if "UPS" in step["stage"]:
            load = round(ups + random.uniform(-1.5, 1.5), 1)
        else:
            load = round(min(96.0, base * (0.92 + 0.08 * (it / 20.0)) + (seed - 0.5) * 4), 1)
        kw = round(it * 1000 * (0.12 + seed * 0.18) if i < len(POWER_CHAIN) else it * 1000 * 0.95, 1)
        row = {
            "id": f"PWR-{i:02d}",
            "stage": step["stage"],
            "vendor": step["vendor"],
            "rating": step["rating"],
            "load_pct": load,
            "power_kw": kw,
            "status": "online" if load < 90 else "warn",
            "score": load,
        }
        out.append(row)
    return out


def enrich_cooling_chain(live: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    live = live or {}
    cool = float(live.get("cooling_load_pct") or 68)
    supply = float(live.get("liquid_loop_temp_c") or 28.4)
    ret = float(live.get("return_temp_c") or 36.2)
    out = []
    for i, step in enumerate(COOLING_CHAIN, start=1):
        seed = stable_seed(step["stage"])
        load = round(min(95.0, cool * (0.85 + seed * 0.25) + random.uniform(-2, 2)), 1)
        delta = round((ret - supply) * (0.7 + seed * 0.5), 2)
        row = {
            "id": f"CLG-{i:02d}",
            "stage": step["stage"],
            "vendor": step["vendor"],
            "mode": step["mode"],
            "load_pct": load,
            "supply_c": round(supply + (seed - 0.5) * 1.2, 1),
            "return_c": round(ret + (seed - 0.5) * 1.5, 1),
            "delta_t_c": delta,
            "flow_lpm": round(180 + seed * 420 + load * 2.2, 1),
            "status": "online" if load < 88 else "warn",
            "score": load,
        }
        out.append(row)
    return out


def enrich_halls(live: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    live = live or {}
    hall_loads = live.get("hall_loads") or {}
    out = []
    for h in HALLS:
        live_mw = float(hall_loads.get(h.id, h.design_mw * 0.72))
        util = round(min(100.0, (live_mw / h.design_mw) * 100), 1) if h.design_mw else 0
        row = {
            "id": h.id,
            "name": h.name,
            "module_id": h.module_id,
            "design_mw": h.design_mw,
            "live_mw": round(live_mw, 2),
            "rack_count": h.rack_count,
            "avg_rack_kw": h.avg_rack_kw,
            "cooling": h.cooling,
            "liquid_pct": h.liquid_pct,
            "util_pct": util,
            "headroom_mw": round(h.design_mw - live_mw, 2),
            "status": "online",
            "score": util,
        }
        out.append(row)
    return out


def enrich_modules(live: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    live = live or {}
    module_loads = live.get("module_loads") or {}
    out = []
    for m in MODULAR_CENTERS:
        live_mw = float(module_loads.get(m.id, m.design_mw * 0.74 if m.status == "online" else 0))
        if m.status == "planned":
            live_mw = 0.0
        elif m.status == "commissioning":
            live_mw = min(live_mw, m.design_mw * 0.25)
        util = round(min(100.0, (live_mw / m.design_mw) * 100), 1) if m.design_mw else 0
        out.append({
            "id": m.id,
            "name": m.name,
            "design_mw": m.design_mw,
            "live_mw": round(live_mw, 2),
            "phase": m.phase,
            "status": m.status,
            "halls": m.halls,
            "note": m.note,
            "util_pct": util,
            "score": util,
        })
    return out


def sample_stage_series(entity_id: str, *, metric: str, tick: int, base: float, n: int = 60) -> list[dict[str, Any]]:
    """Synthetic 1h minute series for facility entity charts."""
    import time
    from datetime import datetime, timezone

    now = int(time.time())
    seed = stable_seed(entity_id + metric)
    pts = []
    for age in range(n - 1, -1, -1):
        wave = 0.92 + 0.08 * math.sin((tick - age) / 11.0 + seed * 6)
        val = round(base * wave + (seed - 0.5) * 2.5, 2)
        pts.append({
            "t": datetime.fromtimestamp(now - age * 60, tz=timezone.utc).isoformat(),
            "v": max(0.0, val),
        })
    return pts


def rank_by_score(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda r: r.get("score", 0), reverse=True)
    out = []
    for i, r in enumerate(ranked[:limit], start=1):
        row = dict(r)
        row["rank"] = i
        out.append(row)
    return out
