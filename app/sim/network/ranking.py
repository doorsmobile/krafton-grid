"""Top Talkers / uplink ranking + inventory search helpers."""

from __future__ import annotations

from typing import Any

def rank_top_talkers(
    samples: list[dict[str, Any]],
    *,
    limit: int = 20,
    uplink_only: bool = False,
) -> list[dict[str, Any]]:
    rows = [s for s in samples if s.get("oper") == "up"]
    if uplink_only:
        rows = [s for s in rows if s.get("uplink")]
    ranked = sorted(rows, key=lambda s: max(s.get("in_bps", 0), s.get("out_bps", 0)), reverse=True)
    out = []
    for i, s in enumerate(ranked[:limit], start=1):
        row = dict(s)
        row["rank"] = i
        row["peak_bps"] = max(s.get("in_bps", 0), s.get("out_bps", 0))
        out.append(row)
    return out

def format_bps(bps: int | float) -> str:
    bps = float(bps)
    if bps >= 1e12:
        return f"{bps / 1e12:.2f} Tbps"
    if bps >= 1e9:
        return f"{bps / 1e9:.2f} Gbps"
    if bps >= 1e6:
        return f"{bps / 1e6:.2f} Mbps"
    if bps >= 1e3:
        return f"{bps / 1e3:.1f} Kbps"
    return f"{bps:.0f} bps"

def search_devices(
    devices: list[dict[str, Any]],
    q: str,
) -> list[dict[str, Any]]:
    q = (q or "").strip().lower()
    if not q:
        return devices
    out = []
    for d in devices:
        blob = " ".join(
            str(d.get(k, ""))
            for k in ("id", "hostname", "role", "vendor", "model", "mgmt_ip", "rack_id", "serial", "location", "status", "fabric")
        ).lower()
        if q in blob:
            out.append(d)
    return out

def device_detail_payload(
    device: dict[str, Any],
    ifaces: list[dict[str, Any]],
    latest_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows = []
    for iface in ifaces:
        m = latest_by_id.get(iface["id"], {})
        rows.append(
            {
                **iface,
                "in_bps": m.get("in_bps", 0),
                "out_bps": m.get("out_bps", 0),
                "util_pct": m.get("util_pct", 0),
                "errors": m.get("errors", 0),
                "discards": m.get("discards", 0),
                "in_bps_h": format_bps(m.get("in_bps", 0)),
                "out_bps_h": format_bps(m.get("out_bps", 0)),
            }
        )
    return {"device": device, "interfaces": rows, "iface_count": len(rows)}

def compact_latest(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Index latest samples by iface_id for O(1) device detail lookups."""
    return {s["iface_id"]: s for s in samples if "iface_id" in s}

