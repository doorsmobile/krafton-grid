"""1-minute interface metric synthesis + Redis sample codec."""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone
from typing import Any

from app.sim.network.constants import NET_HISTORY_LEN
from app.sim.network.interfaces import _speed_label, _stable_seed

def sample_iface_metrics(
    iface: dict[str, Any],
    *,
    tick_minute: int,
    mode: str = "normal",
) -> dict[str, Any]:
    """Synthesize one-minute interface counters (bps, errors, discards, util)."""
    seed = _stable_seed(iface["id"])
    speed = max(1, iface["speed_bps"])
    role = iface["role"]

    # Base utilization envelopes by role
    if role in {"fabric", "uplink"}:
        base = 0.42 + 0.28 * seed
    elif role == "access":
        base = 0.18 + 0.45 * seed
    elif role == "ib-fabric":
        base = 0.55 + 0.30 * seed
    elif role == "peer":
        base = 0.12 + 0.15 * seed
    else:
        base = 0.02 + 0.05 * seed

    wave = 0.5 + 0.5 * math.sin(tick_minute / 7.0 + seed * 6.28)
    burst = 0.5 + 0.5 * math.sin(tick_minute / 3.0 + seed * 12.0)
    util = base * (0.75 + 0.35 * wave) * (0.85 + 0.25 * burst)

    if mode == "stress":
        util = min(0.97, util * 1.45)
    elif mode == "maintenance":
        util *= 0.55
    elif mode == "failover":
        util = min(0.95, util * (1.2 if iface.get("uplink") else 0.7))

    # Asymmetry in/out
    in_share = 0.45 + 0.2 * seed
    in_bps = int(speed * util * in_share)
    out_bps = int(speed * util * (1.0 - in_share * 0.85))
    util_pct = round(max(in_bps, out_bps) / speed * 100, 2)

    err_rate = 0.0
    disc_rate = 0.0
    if util_pct > 85:
        err_rate = (util_pct - 85) * (0.4 + seed)
        disc_rate = (util_pct - 85) * (0.8 + seed * 1.2)
    if mode == "stress" and seed > 0.7:
        err_rate += random.uniform(1, 8)
        disc_rate += random.uniform(2, 12)

    errors = int(max(0, round(err_rate + random.uniform(0, 0.6))))
    discards = int(max(0, round(disc_rate + random.uniform(0, 0.8))))

    oper = iface.get("oper", "up")
    if oper != "up":
        in_bps = out_bps = 0
        util_pct = 0.0
        errors = discards = 0

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "device_id": iface["device_id"],
        "iface": iface["name"],
        "iface_id": iface["id"],
        "role": role,
        "uplink": bool(iface.get("uplink")),
        "speed_bps": speed,
        "speed_label": iface.get("speed_label") or _speed_label(speed),
        "in_bps": in_bps,
        "out_bps": out_bps,
        "util_pct": util_pct,
        "errors": errors,
        "discards": discards,
        "oper": oper,
        "description": iface.get("description", ""),
        "peer": iface.get("peer"),
    }

def seed_iface_history(
    ifaces: list[dict[str, Any]],
    *,
    minutes: int = NET_HISTORY_LEN,
    mode: str = "normal",
) -> list[list[dict[str, Any]]]:
    """Pre-fill ~1h of minute samples (newest last within each iface list)."""
    now_min = int(datetime.now(timezone.utc).timestamp() // 60)
    histories: list[list[dict[str, Any]]] = []
    for iface in ifaces:
        series: list[dict[str, Any]] = []
        for age in range(minutes - 1, -1, -1):
            m = sample_iface_metrics(iface, tick_minute=now_min - age, mode=mode)
            # backdate ts
            ts = datetime.fromtimestamp((now_min - age) * 60, tz=timezone.utc).isoformat()
            m["ts"] = ts
            series.append(m)
        histories.append(series)
    return histories

def serialize_sample_for_redis(sample: dict[str, Any]) -> str:
    # Keep Redis values small
    slim = {
        "t": sample["ts"],
        "in": sample["in_bps"],
        "out": sample["out_bps"],
        "u": sample["util_pct"],
        "e": sample["errors"],
        "d": sample["discards"],
    }
    return json.dumps(slim, separators=(",", ":"))

def parse_redis_sample(raw: str, meta: dict[str, Any]) -> dict[str, Any]:
    p = json.loads(raw)
    return {
        "ts": p["t"],
        "device_id": meta["device_id"],
        "iface": meta["name"],
        "iface_id": meta["id"],
        "role": meta.get("role"),
        "uplink": bool(meta.get("uplink")),
        "speed_bps": meta["speed_bps"],
        "speed_label": meta.get("speed_label"),
        "in_bps": p["in"],
        "out_bps": p["out"],
        "util_pct": p["u"],
        "errors": p["e"],
        "discards": p["d"],
        "oper": meta.get("oper", "up"),
        "description": meta.get("description", ""),
        "peer": meta.get("peer"),
    }

