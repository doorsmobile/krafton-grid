"""Network Redis collector + query mixin (1-min samples, 1h rings)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from app.config import REDIS_KEY_PREFIX
from app.sim.network import (
    NET_HISTORY_LEN,
    build_all_interfaces,
    build_network_devices_rich,
    build_topology,
    compact_latest,
    device_detail_payload,
    format_bps,
    parse_redis_sample,
    rank_top_talkers,
    sample_iface_metrics,
    search_devices,
    serialize_sample_for_redis,
)


class NetworkStoreMixin:
    def _net_hist_key(self, iface_id: str) -> str:
        # iface_id like AR-LF-01:Ethernet1/1 → safe redis suffix
        safe = iface_id.replace(":", "/").replace(" ", "_")
        return f"{REDIS_KEY_PREFIX}:net:hist:{safe}"

    def _seed_network_history(self) -> None:
        """Fill last 60 minutes of interface samples so Top Talkers work immediately."""
        if not self._net_ifaces:
            rich = build_network_devices_rich()
            self._net_ifaces = build_all_interfaces(rich)
            self._net_iface_by_id = {i["id"]: i for i in self._net_ifaces}
        # Skip reseed if already warm
        probe = self._net_ifaces[0]["id"] if self._net_ifaces else None
        if probe and self.redis.llen(self._net_hist_key(probe)) >= NET_HISTORY_LEN:
            raw = self.redis.get(f"{REDIS_KEY_PREFIX}:net:latest")
            if raw:
                return
        now_min = int(time.time() // 60)
        mode = self.state.mode
        latest: list[dict[str, Any]] = []
        batch: list[Any] = []

        def flush() -> None:
            if batch:
                pipe = self.redis.pipeline()
                for op in batch:
                    op(pipe)
                pipe.execute()
                batch.clear()

        for iface in self._net_ifaces:
            key = self._net_hist_key(iface["id"])

            def _ops(pipe, iface=iface, key=key):  # noqa: B023
                pipe.delete(key)
                for age in range(NET_HISTORY_LEN - 1, -1, -1):
                    m = sample_iface_metrics(iface, tick_minute=now_min - age, mode=mode)
                    m["ts"] = datetime.fromtimestamp((now_min - age) * 60, tz=timezone.utc).isoformat()
                    pipe.rpush(key, serialize_sample_for_redis(m))
                    if age == 0:
                        latest.append(m)
                pipe.ltrim(key, -NET_HISTORY_LEN, -1)

            batch.append(_ops)
            if len(batch) >= 40:
                flush()
        flush()
        self.redis.set(f"{REDIS_KEY_PREFIX}:net:latest", json.dumps(latest))
        self.redis.hset(
            f"{REDIS_KEY_PREFIX}:net:collector",
            mapping={
                "last_sample_ts": datetime.now(timezone.utc).isoformat(),
                "last_sample_minute": str(now_min),
                "iface_count": str(len(self._net_ifaces)),
            },
        )
        self._last_net_sample_min = now_min

    def _maybe_sample_network(self) -> None:
        """Collect interface metrics once per calendar minute into Redis 1h rings."""
        now_min = int(time.time() // 60)
        if now_min == self._last_net_sample_min:
            return
        if not self._net_ifaces:
            self._seed_network_history()
            return
        mode = self.state.mode
        latest: list[dict[str, Any]] = []
        pipe = self.redis.pipeline()
        for iface in self._net_ifaces:
            m = sample_iface_metrics(iface, tick_minute=now_min, mode=mode)
            latest.append(m)
            key = self._net_hist_key(iface["id"])
            pipe.rpush(key, serialize_sample_for_redis(m))
            pipe.ltrim(key, -NET_HISTORY_LEN, -1)
        pipe.set(f"{REDIS_KEY_PREFIX}:net:latest", json.dumps(latest))
        pipe.hset(
            f"{REDIS_KEY_PREFIX}:net:collector",
            mapping={
                "last_sample_ts": datetime.now(timezone.utc).isoformat(),
                "last_sample_minute": str(now_min),
                "iface_count": str(len(latest)),
            },
        )
        pipe.execute()
        self._last_net_sample_min = now_min

    def get_network_latest(self) -> list[dict[str, Any]]:
        raw = self.redis.get(f"{REDIS_KEY_PREFIX}:net:latest")
        if not raw:
            self._seed_network_history()
            raw = self.redis.get(f"{REDIS_KEY_PREFIX}:net:latest")
        return json.loads(raw) if raw else []

    def get_network_devices(self) -> list[dict[str, Any]]:
        return self.get_json("network_devices") or build_network_devices_rich()

    def get_network_interfaces(self) -> list[dict[str, Any]]:
        cached = self.get_json("net:interfaces")
        if cached:
            return cached
        return build_all_interfaces(self.get_network_devices())

    def get_network_topology(self) -> dict[str, Any]:
        return self.get_json("net:topology") or build_topology(self.get_network_devices())

    def get_iface_history(self, iface_id: str, limit: int = NET_HISTORY_LEN) -> list[dict[str, Any]]:
        meta = self._net_iface_by_id.get(iface_id)
        if not meta:
            for i in self.get_network_interfaces():
                if i["id"] == iface_id:
                    meta = i
                    break
        if not meta:
            return []
        rows = self.redis.lrange(self._net_hist_key(iface_id), -limit, -1)
        return [parse_redis_sample(r, meta) for r in rows]

    def get_network_uplinks(self, limit: int = 40) -> dict[str, Any]:
        latest = self.get_network_latest()
        uplinks = rank_top_talkers(latest, limit=limit, uplink_only=True)
        for u in uplinks:
            u["in_bps_h"] = format_bps(u["in_bps"])
            u["out_bps_h"] = format_bps(u["out_bps"])
            u["peak_bps_h"] = format_bps(u["peak_bps"])
        total_in = sum(u["in_bps"] for u in uplinks)
        total_out = sum(u["out_bps"] for u in uplinks)
        return {
            "uplinks": uplinks,
            "totals": {
                "in_bps": total_in,
                "out_bps": total_out,
                "in_bps_h": format_bps(total_in),
                "out_bps_h": format_bps(total_out),
                "count": len(uplinks),
            },
            "collector": self.redis.hgetall(f"{REDIS_KEY_PREFIX}:net:collector"),
            "meta": self.get_json("net:meta") or {},
        }

    def get_network_toptalkers(self, limit: int = 25, window_minutes: int = 15) -> dict[str, Any]:
        """Rank interfaces by peak bps over the recent Redis window (fast path: latest + avg)."""
        latest = self.get_network_latest()
        # Enrich with window peak from history for top candidates
        candidates = rank_top_talkers(latest, limit=max(limit * 3, 40), uplink_only=False)
        enriched: list[dict[str, Any]] = []
        for c in candidates:
            hist = self.get_iface_history(c["iface_id"], limit=window_minutes)
            if hist:
                peak = max(max(h["in_bps"], h["out_bps"]) for h in hist)
                avg_in = int(sum(h["in_bps"] for h in hist) / len(hist))
                avg_out = int(sum(h["out_bps"] for h in hist) / len(hist))
                err_sum = sum(h["errors"] for h in hist)
                disc_sum = sum(h["discards"] for h in hist)
            else:
                peak = c["peak_bps"]
                avg_in, avg_out = c["in_bps"], c["out_bps"]
                err_sum = c["errors"]
                disc_sum = c["discards"]
            row = dict(c)
            row["window_peak_bps"] = peak
            row["window_avg_in_bps"] = avg_in
            row["window_avg_out_bps"] = avg_out
            row["window_errors"] = err_sum
            row["window_discards"] = disc_sum
            row["window_peak_bps_h"] = format_bps(peak)
            row["window_avg_in_bps_h"] = format_bps(avg_in)
            row["window_avg_out_bps_h"] = format_bps(avg_out)
            row["in_bps_h"] = format_bps(c["in_bps"])
            row["out_bps_h"] = format_bps(c["out_bps"])
            enriched.append(row)
        enriched.sort(key=lambda r: r["window_peak_bps"], reverse=True)
        for i, r in enumerate(enriched[:limit], start=1):
            r["rank"] = i
        return {
            "talkers": enriched[:limit],
            "window_minutes": window_minutes,
            "collector": self.redis.hgetall(f"{REDIS_KEY_PREFIX}:net:collector"),
            "meta": self.get_json("net:meta") or {},
        }

    def get_network_inventory(self, q: str = "") -> dict[str, Any]:
        devices = search_devices(self.get_network_devices(), q)
        latest = compact_latest(self.get_network_latest())
        # Attach quick util summary per device
        by_dev: dict[str, list[dict[str, Any]]] = {}
        for s in latest.values():
            by_dev.setdefault(s["device_id"], []).append(s)
        rows = []
        for d in devices:
            samples = by_dev.get(d["id"], [])
            peak = max((max(s["in_bps"], s["out_bps"]) for s in samples), default=0)
            avg_util = round(sum(s["util_pct"] for s in samples) / len(samples), 1) if samples else 0.0
            err = sum(s["errors"] for s in samples)
            disc = sum(s["discards"] for s in samples)
            rows.append(
                {
                    **d,
                    "iface_count": len(samples) or len([i for i in self._net_ifaces if i["device_id"] == d["id"]]),
                    "peak_bps": peak,
                    "peak_bps_h": format_bps(peak),
                    "avg_util_pct": avg_util,
                    "errors": err,
                    "discards": disc,
                }
            )
        return {
            "devices": rows,
            "query": q,
            "total": len(rows),
            "meta": self.get_json("net:meta") or {},
        }

    def get_network_device(self, device_id: str) -> dict[str, Any] | None:
        devices = self.get_network_devices()
        device = next((d for d in devices if d["id"] == device_id), None)
        if not device:
            return None
        ifaces = [i for i in self.get_network_interfaces() if i["device_id"] == device_id]
        latest = compact_latest(self.get_network_latest())
        payload = device_detail_payload(device, ifaces, latest)
        # Attach 1h series for each iface (for charts — keep slim)
        series = {}
        for iface in ifaces:
            hist = self.get_iface_history(iface["id"], limit=NET_HISTORY_LEN)
            series[iface["name"]] = [
                {"t": h["ts"], "in": h["in_bps"], "out": h["out_bps"], "u": h["util_pct"], "e": h["errors"], "d": h["discards"]}
                for h in hist
            ]
        payload["series"] = series
        payload["collector"] = self.redis.hgetall(f"{REDIS_KEY_PREFIX}:net:collector")
        return payload

    def get_network_bundle(self) -> dict[str, Any]:
        live = self.get_live()
        return {
            "devices": self.get_network_devices(),
            "topology": self.get_network_topology(),
            "uplinks": self.get_network_uplinks(),
            "toptalkers": self.get_network_toptalkers(),
            "meta": self.get_json("net:meta") or {},
            "collector": self.redis.hgetall(f"{REDIS_KEY_PREFIX}:net:collector"),
            "live": {
                "eth_fabric_util_pct": live.get("eth_fabric_util_pct"),
                "ib_fabric_util_pct": live.get("ib_fabric_util_pct"),
            },
        }


