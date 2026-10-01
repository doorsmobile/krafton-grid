"""Structured log stream + LogQL-lite.

    {service="slurmctld", level=~"error|warn"} |= "Xid" != "debug"
    count_over_time({service="dcgm"} |= "Xid" [10m])
"""
from __future__ import annotations

import re
import threading
from collections import deque

import numpy as np

from . import topology as T

SERVICES = {
    "slurmctld": "slurm-ctl-01", "slurmd": None, "dcgm-exporter": None, "nvidia-fabricmanager": None,
    "ufm": "ufm-01", "arista-eos": None, "bms": "bms-niagara-01", "ups-snmp": "ups-gw-01", "cdu-modbus": "cdu-gw-01",
    "kubelet": None, "mmfs": None, "cubeflow": "cubeflow-api", "gpu-platform-api": "gp-api", "vllm": None,
    "scale-gui": "scale-mgmt-01", "grid-sim": "grid-claude",
}

LOGQL = re.compile(r"^\s*\{(?P<sel>[^}]*)\}(?P<pipe>.*)$", re.S)
MATCHER = re.compile(r'\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|!~|!=|=)\s*"((?:[^"\\]|\\.)*)"\s*,?')
FILTER = re.compile(r'\s*(\|=|!=|\|~|!~)\s*"((?:[^"\\]|\\.)*)"')
METRIC_Q = re.compile(r"^\s*(count_over_time|rate)\s*\((?P<inner>.*)\[(?P<rng>\d+[smhd])\]\s*\)\s*$", re.S)


class LogStore:
    def __init__(self, rng: np.random.Generator, cap: int = 30000):
        self.rng = rng
        self.lines: deque[dict] = deque(maxlen=cap)
        self.lock = threading.Lock()
        self.seq = 0

    def emit(self, t: float, service: str, level: str, msg: str, host: str | None = None, **labels) -> None:
        self.seq += 1
        with self.lock:
            self.lines.append({"seq": self.seq, "t": t, "service": service, "level": level, "msg": msg,
                               "host": host or SERVICES.get(service) or "grid", **labels})

    def background(self, t: float, eng) -> None:
        rng = self.rng
        fleet = eng.fleet
        if rng.random() < 0.6:
            n = int(rng.integers(0, T.NODE_COUNT))
            self.emit(t, "slurmd", "info", f"node {T.NODE_IDS[n]} state={fleet.node_state[n]} cpu_load={fleet.node_cpu[n]:.0f}%",
                      host=T.NODE_IDS[n], rack=T.NODE_RACK[n])
        if rng.random() < 0.5:
            gi = int(rng.integers(0, T.GPU_COUNT))
            self.emit(t, "dcgm-exporter", "debug",
                      f"gpu={gi % 8} DCGM_FI_DEV_GPU_UTIL={fleet.util[gi]:.0f} DCGM_FI_DEV_GPU_TEMP={fleet.temp[gi]:.0f} "
                      f"DCGM_FI_DEV_POWER_USAGE={fleet.power[gi]:.0f}", host=T.NODE_IDS[gi // 8], rack=T.NODE_RACK[gi // 8])
        if rng.random() < 0.25:
            s = eng.storage.clusters["ss-hot"]
            self.emit(t, "mmfs", "info", f"fs=hot throughput read={s['read_gbs']:.0f}GB/s write={s['write_gbs']:.0f}GB/s latency={s['latency_ms']:.2f}ms",
                      host="nsd-hot-0" + str(int(rng.integers(1, 9))))
        if rng.random() < 0.2:
            leaf = T.IB_LEAVES[int(rng.integers(0, len(T.IB_LEAVES)))]["id"]
            d = eng.network.dev[leaf]
            lvl = "warn" if d["links_down"] else "info"
            self.emit(t, "ufm", lvl, f"switch={leaf} util={d['util_pct']:.0f}% symbol_err_rate={d['err_rate']:.2e} links_down={d['links_down']}")
        if rng.random() < 0.18:
            leaf = T.ETH_LEAVES[int(rng.integers(0, len(T.ETH_LEAVES)))]["id"]
            self.emit(t, "arista-eos", "info", f"%LINEPROTO-5-UPDOWN: interfaces stable, util {eng.network.dev[leaf]['util_pct']:.0f}%", host=leaf)
        if rng.random() < 0.15:
            k = T.K8S_NODES[int(rng.integers(0, len(T.K8S_NODES)))]["id"]
            self.emit(t, "kubelet", "info", f"SyncLoop (PLEG): pods={eng.k8s.nodes[k]['pods']} cpu={eng.k8s.nodes[k]['cpu_pct']:.0f}%", host=k)
        if rng.random() < 0.12:
            snap = eng.facility.snapshot
            if snap:
                self.emit(t, "bms", "info", f"PUE={snap['pue']:.3f} CHWS={snap['cooling']['chw_supply_c']:.1f}C FWS={snap['cooling']['fws_supply_c']:.1f}C OAT={snap['ambient']['dry_c']:.1f}C")
        if rng.random() < 0.1:
            self.emit(t, "vllm", "info", f"Avg prompt throughput: {rng.uniform(8000, 22000):.0f} tokens/s, running: {int(rng.integers(40, 220))} reqs",
                      host=f"kg-r3{int(rng.integers(1, 6))}-n{int(rng.integers(1, 16)):02d}")

    # ------------------------------------------------------------------ query
    def query(self, q: str, now: float, window_s: float = 3600, limit: int = 200) -> dict:
        with self.lock:
            lines = list(self.lines)
        return query_lines(lines, q, now, window_s, limit)

    def since(self, seq: int) -> list[dict]:
        """Lines emitted after ``seq`` — what the collector appends to Redis each tick."""
        with self.lock:
            return [l for l in self.lines if l["seq"] > seq]

    def services(self) -> list[str]:
        return sorted(SERVICES)


# ------------------------------------------------------------------ LogQL over any list of lines
def query_lines(lines: list[dict], q: str, now: float, window_s: float = 3600, limit: int = 200) -> dict:
    mq = METRIC_Q.match(q)
    if mq:
        from .tsdb import parse_duration
        rng = parse_duration(mq.group("rng"))
        sel = select_lines(lines, mq.group("inner").strip(), now, window_s)
        buckets = max(1, int(window_s // rng))
        edges = np.linspace(now - window_s, now, buckets + 1)
        counts = np.histogram([l["t"] for l in sel], bins=edges)[0].astype(float)
        if mq.group(1) == "rate":
            counts = counts / rng
        pts = [[int(edges[i + 1] * 1000), round(float(c), 4)] for i, c in enumerate(counts)]
        return {"resultType": "matrix", "result": [{"metric": {"query": mq.group("inner").strip()}, "values": pts}],
                "lines": [], "total": len(sel)}
    sel = select_lines(lines, q, now, window_s)
    edges = np.linspace(now - window_s, now, 61)
    hist = np.histogram([l["t"] for l in sel], bins=edges)[0]
    by_level: dict[str, int] = {}
    for l in sel:
        by_level[l["level"]] = by_level.get(l["level"], 0) + 1
    return {"resultType": "streams", "lines": list(reversed(sel[-limit:])), "total": len(sel),
            "histogram": [[int(edges[i + 1] * 1000), int(c)] for i, c in enumerate(hist)], "by_level": by_level}


def select_lines(lines: list[dict], q: str, now: float, window_s: float) -> list[dict]:
    m = LOGQL.match(q)
    if not m:
        raise ValueError('LogQL needs a stream selector, e.g. {service="slurmctld"}')
    matchers = []
    sel = m.group("sel").strip()
    pos = 0
    while pos < len(sel):
        mm = MATCHER.match(sel, pos)
        if not mm:
            raise ValueError(f"bad label matcher near: {sel[pos:pos + 20]!r}")
        matchers.append((mm.group(1), mm.group(2), mm.group(3)))
        pos = mm.end()
    filters = []
    pipe = m.group("pipe").strip()
    pos = 0
    while pos < len(pipe):
        fm = FILTER.match(pipe, pos)
        if not fm:
            if pipe[pos:].strip().startswith("| json") or pipe[pos:].strip().startswith("| logfmt"):
                break
            raise ValueError(f"bad pipeline stage near: {pipe[pos:pos + 20]!r}")
        filters.append((fm.group(1), fm.group(2)))
        pos = fm.end()
    start = now - window_s
    out = []
    for line in lines:
        if line["t"] < start:
            continue
        ok = True
        for lab, op, raw in matchers:
            v = str(line.get(lab, ""))
            if (op == "=" and v != raw) or (op == "!=" and v == raw) or \
               (op == "=~" and not re.fullmatch(raw, v)) or (op == "!~" and re.fullmatch(raw, v)):
                ok = False
                break
        if not ok:
            continue
        for op, raw in filters:
            msg = line["msg"]
            if (op == "|=" and raw not in msg) or (op == "!=" and raw in msg) or \
               (op == "|~" and not re.search(raw, msg)) or (op == "!~" and re.search(raw, msg)):
                ok = False
                break
        if ok:
            out.append(line)
    return out
