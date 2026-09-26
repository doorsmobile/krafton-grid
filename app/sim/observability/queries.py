"""PromQL / LogQL–style query simulation against Redis live + series."""

from __future__ import annotations

import re
import time
from typing import Any

# Friendly metric aliases → Redis series / live keys
METRIC_ALIASES: dict[str, str] = {
    "kg_it_load_mw": "it_load_mw",
    "kg_pue": "pue",
    "kg_gpu_util_pct": "gpu_utilization_pct",
    "kg_cooling_load_pct": "cooling_load_pct",
    "kg_liquid_loop_temp_c": "liquid_loop_temp_c",
    "kg_storage_used_pb": "storage_used_pb",
    "kg_eth_fabric_util_pct": "eth_fabric_util_pct",
    "kg_k8s_cpu_util_pct": "k8s_cpu_util_pct",
    "kg_aws_gpu_util_pct": "aws_gpu_util_pct",
    "kg_nhn_gpu_util_pct": "nhn_gpu_util_pct",
    "kg_gcp_storage_used_tb": "gcp_storage_used_tb",
}


def _extract_metric_name(query: str) -> str | None:
    q = query.strip()
    # rate(kg_gpu_util_pct[5m]) or kg_gpu_util_pct{hall="M1-A"}
    m = re.search(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\{|\(|$|\[)", q)
    if not m:
        return None
    name = m.group(1)
    if name in {"rate", "avg", "sum", "max", "min", "histogram_quantile"}:
        inner = re.search(r"\(\s*([a-zA-Z_][a-zA-Z0-9_]*)", q)
        return inner.group(1) if inner else None
    return name


def run_promql(engine: Any, query: str, limit: int = 60) -> dict[str, Any]:
    """Evaluate a simplified PromQL against live Redis series."""
    started = time.perf_counter()
    name = _extract_metric_name(query or "")
    if not name:
        return {
            "status": "error",
            "error": "unable to parse metric name",
            "query": query,
            "resultType": "vector",
            "result": [],
        }
    series_key = METRIC_ALIASES.get(name, name)
    series = engine.get_series(series_key, limit=limit)
    live = engine.get_live()
    value = live.get(series_key)
    if value is None and series:
        value = series[-1].get("v")
    points = [{"ts": p.get("ts"), "value": p.get("v")} for p in series]
    ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "status": "success",
        "query": query,
        "metric": name,
        "series_key": series_key,
        "resultType": "matrix" if points else "vector",
        "result": [
            {
                "metric": {"__name__": name, "site": "KG-AIDC-01"},
                "value": [time.time(), value],
                "values": [[p["ts"], p["value"]] for p in points],
            }
        ],
        "stats": {"exec_ms": ms, "samples": len(points)},
        "hint": "Aliases: " + ", ".join(sorted(METRIC_ALIASES)),
    }


_LOG_STREAMS = [
    ("facility", "power", "UPS load {v}% on M1 A-side"),
    ("facility", "cooling", "CDU loop supply {v}°C"),
    ("gpu", "runtime", "SM util {v}% across B300 fleet"),
    ("network", "fabric", "Eth fabric util {v}%"),
    ("storage", "ibm", "Storage used {v} PB"),
    ("kubernetes", "controlplane", "K8s CPU util {v}%"),
    ("cloud", "aws", "AWS GPUaaS util {v}%"),
    ("alerts", "correlation", "Active alerts {v}"),
]


def run_logql(engine: Any, query: str, limit: int = 40) -> dict[str, Any]:
    """Return synthetic log lines filtered by a LogQL-like selector."""
    started = time.perf_counter()
    live = engine.get_live()
    q = (query or '{job="krafton-grid"}').strip()
    # Parse {job="x", namespace="y"} loosely
    labels = dict(re.findall(r'([a-zA-Z_]+)="([^"]*)"', q))
    job = labels.get("job", "krafton-grid")
    namespace = labels.get("namespace") or labels.get("source")

    value_map = {
        "facility/power": live.get("ups_load_pct"),
        "facility/cooling": live.get("liquid_loop_temp_c"),
        "gpu/runtime": live.get("gpu_utilization_pct"),
        "network/fabric": live.get("eth_fabric_util_pct"),
        "storage/ibm": live.get("storage_used_pb"),
        "kubernetes/controlplane": live.get("k8s_cpu_util_pct"),
        "cloud/aws": live.get("aws_gpu_util_pct"),
        "alerts/correlation": live.get("active_alerts"),
    }

    lines: list[dict[str, Any]] = []
    for ns, stream, tmpl in _LOG_STREAMS:
        if namespace and namespace not in {ns, f"{ns}/{stream}", stream}:
            continue
        key = f"{ns}/{stream}"
        v = value_map.get(key, live.get("tick"))
        lines.append(
            {
                "ts": live.get("ts"),
                "labels": {"job": job, "namespace": ns, "stream": stream, "site": "KG-AIDC-01"},
                "line": tmpl.format(v=v),
                "level": "info",
            }
        )

    # Append recent alerts as log events
    for a in engine.get_alerts(min(limit, 15)):
        if namespace and namespace not in {"alerts", a.get("source", "").lower()}:
            continue
        lines.append(
            {
                "ts": a.get("ts"),
                "labels": {"job": job, "namespace": "alerts", "stream": "console", "severity": a.get("severity")},
                "line": f"[{a.get('severity')}] {a.get('source')}: {a.get('message')}",
                "level": a.get("severity", "info"),
            }
        )

    lines = lines[:limit]
    ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "status": "success",
        "query": q,
        "resultType": "streams",
        "result": lines,
        "stats": {"exec_ms": ms, "lines": len(lines)},
        "examples": [
            '{job="krafton-grid"}',
            '{job="krafton-grid", namespace="gpu"}',
            '{namespace="alerts"}',
            '{namespace="facility"} |= "CDU"',
        ],
    }
