"""Tiered in-memory time-series store.

Each metric is a *vector* ring: one column per label set, one row per sample.
Tiers trade resolution for retention, the way a real TSDB downsamples:

                                standard   large (GRID_DATA_PROFILE=large · ~130 MB Redis, ~350 MB collector)
    t1   every tick (2 s)       1 h        3 h     facility / fleet / hall / rack aggregates
    t2   every 5 ticks (10 s)   1 h        12 h    per node, per device, per volume
    t3   every 15 ticks (30 s)  1 h        12 h    per GPU (5,000 columns)
    t4   every 30 ticks (60 s)  24 h       7 d     site-level trend lines
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

import numpy as np

from .. import config
from ..store import TS_HEADER

_CAPS = {"standard": (1800, 360, 120, 1440), "large": (5400, 4320, 1440, 10080)}[
    "large" if config.DATA_LARGE else "standard"]
TIERS = {
    "t1": {"every": 1, "cap": _CAPS[0]},
    "t2": {"every": 5, "cap": _CAPS[1]},
    "t3": {"every": 15, "cap": _CAPS[2]},
    "t4": {"every": 30, "cap": _CAPS[3]},
}


@dataclass
class Metric:
    name: str
    tier: str
    help: str
    unit: str
    labels: list[dict]
    kind: str = "gauge"  # gauge | counter
    buf: np.ndarray = field(init=False, repr=False)
    ts: np.ndarray = field(init=False, repr=False)
    head: int = 0
    size: int = 0

    def __post_init__(self) -> None:
        cap = TIERS[self.tier]["cap"]
        self.buf = np.full((cap, len(self.labels)), np.nan, dtype=np.float32)
        self.ts = np.zeros(cap, dtype=np.float64)

    @property
    def width(self) -> int:
        return len(self.labels)

    def push(self, t: float, values) -> None:
        cap = self.buf.shape[0]
        self.buf[self.head] = values
        self.ts[self.head] = t
        self.head = (self.head + 1) % cap
        self.size = min(self.size + 1, cap)

    def ordered(self) -> tuple[np.ndarray, np.ndarray]:
        cap = self.buf.shape[0]
        if self.size < cap:
            return self.ts[: self.size], self.buf[: self.size]
        idx = np.r_[self.head:cap, 0:self.head]
        return self.ts[idx], self.buf[idx]

    def window(self, seconds: float | None = None, now: float | None = None, cols: list[int] | None = None) -> tuple[np.ndarray, np.ndarray]:
        ts, vals = self.ordered()
        if cols is not None:
            vals = vals[:, cols]
        if seconds is None or not len(ts):
            return ts, vals
        end = now if now is not None else ts[-1]
        mask = ts >= end - seconds
        return ts[mask], vals[mask]

    def encode(self) -> bytes:
        """Ring snapshot for the store: header(n, width, itemsize) · ts float64[n] · values column-major [width × n].

        Column-major lets a reader GETRANGE exactly one series (e.g. one GPU) without pulling the matrix.
        Per-node / per-GPU gauges (tiers t2, t3) are bounded physical values (%, °C, W, kW, GB) and are
        stored as float16 — 0.05 % relative precision, half the bytes. Site-level series, counters and
        anything outside ±30,000 (e.g. ₩) stay float32.
        """
        ts, vals = self.ordered()
        small = self.tier in ("t2", "t3") and self.kind == "gauge"
        if small and vals.size:
            finite = vals[np.isfinite(vals)]
            small = not finite.size or float(np.abs(finite).max()) < 30000
        dtype = "<f2" if small else "<f4"
        return (TS_HEADER.pack(len(ts), self.width, 2 if small else 4, 0) + ts.astype("<f8").tobytes()
                + np.ascontiguousarray(vals.T, dtype=dtype).tobytes())

    def latest(self) -> np.ndarray:
        if not self.size:
            return np.full(self.width, np.nan, dtype=np.float32)
        return self.buf[(self.head - 1) % self.buf.shape[0]]

    def column(self, **match) -> int | None:
        for i, lab in enumerate(self.labels):
            if all(lab.get(k) == v for k, v in match.items()):
                return i
        return None


class TSDB:
    def __init__(self) -> None:
        self.metrics: dict[str, Metric] = {}
        self.lock = threading.RLock()

    def register(self, name: str, tier: str, help: str, unit: str = "", labels: list[dict] | None = None,
                 kind: str = "gauge") -> Metric:
        m = Metric(name=name, tier=tier, help=help, unit=unit, labels=labels or [{}], kind=kind)
        self.metrics[name] = m
        return m

    def record(self, tick: int, t: float, values: dict[str, object], force: bool = False) -> None:
        with self.lock:
            for name, v in values.items():
                m = self.metrics.get(name)
                if m is None or (not force and tick % TIERS[m.tier]["every"]):
                    continue
                m.push(t, v)

    def series(self, name: str, col: int = 0, seconds: float | None = None, max_points: int = 900) -> list[list]:
        """Single column as [[ms, value], ...] — the shape Highcharts wants."""
        with self.lock:
            m = self.metrics.get(name)
            if m is None:
                return []
            ts, vals = m.window(seconds)
            col_vals = vals[:, col] if vals.size else np.array([])
        return _to_points(ts, col_vals, max_points)

    def series_multi(self, name: str, cols: list[int], seconds: float | None = None, max_points: int = 600) -> list[list[list]]:
        with self.lock:
            m = self.metrics.get(name)
            if m is None:
                return [[] for _ in cols]
            ts, vals = m.window(seconds)
        return [_to_points(ts, vals[:, c], max_points) if vals.size else [] for c in cols]

    def catalog(self, with_labels: bool = False) -> list[dict]:
        out = []
        for m in self.metrics.values():
            keys = sorted({k for lab in m.labels for k in lab})
            row = {"name": m.name, "help": m.help, "unit": m.unit, "kind": m.kind, "tier": m.tier,
                   "series": m.width, "labels": keys,
                   "resolution_s": TIERS[m.tier]["every"] * 2, "retention_points": TIERS[m.tier]["cap"]}
            if with_labels:
                row["label_sets"] = m.labels
            out.append(row)
        return sorted(out, key=lambda x: x["name"])


def _to_points(ts: np.ndarray, vals: np.ndarray, max_points: int) -> list[list]:
    if not len(ts):
        return []
    step = max(1, len(ts) // max_points)
    ts, vals = ts[::step], vals[::step]
    out = []
    for t, v in zip(ts.tolist(), vals.tolist()):
        out.append([int(t * 1000), None if v != v else round(v, 3)])
    return out


_DUR = re.compile(r"^(\d+)([smhd])$")


def parse_duration(s: str) -> float:
    m = _DUR.match(s.strip())
    if not m:
        raise ValueError(f"bad duration: {s}")
    return int(m.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]
