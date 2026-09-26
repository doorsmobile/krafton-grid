"""Storage Redis collector + query mixin (1-min volume samples)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from app.config import REDIS_KEY_PREFIX
from app.sim.storage import (
    build_storage_clusters_rich,
    build_storage_volumes,
    format_iops,
    rank_storage_talkers,
    sample_volume_metrics,
)
from app.sim.telemetry import HISTORY_LEN, dumps_point, hist_key, loads_point, minute_iso, now_minute


class StorageStoreMixin:
    def _ensure_storage_catalog(self) -> None:
        if getattr(self, "_st_volumes", None):
            return
        clusters = self.get_json("storage_clusters_rich") or build_storage_clusters_rich()
        vols = self.get_json("storage_volumes") or build_storage_volumes(clusters)
        self._st_clusters = clusters
        self._st_volumes = vols
        self._st_vol_by_id = {v["id"]: v for v in vols}

    def _seed_storage_history(self) -> None:
        self._ensure_storage_catalog()
        probe = self._st_volumes[0]["id"] if self._st_volumes else None
        if probe and self.redis.llen(hist_key("st", probe)) >= HISTORY_LEN:
            if self.redis.get(f"{REDIS_KEY_PREFIX}:st:latest"):
                return
        minute = now_minute()
        mode = self.state.mode
        latest: list[dict[str, Any]] = []
        batch: list = []

        def flush() -> None:
            if not batch:
                return
            pipe = self.redis.pipeline()
            for op in batch:
                op(pipe)
            pipe.execute()
            batch.clear()

        for vol in self._st_volumes:
            key = hist_key("st", vol["id"])

            def _ops(pipe, vol=vol, key=key):
                pipe.delete(key)
                for age in range(HISTORY_LEN - 1, -1, -1):
                    m = sample_volume_metrics(vol, tick_minute=minute - age, mode=mode)
                    m["ts"] = minute_iso(minute - age)
                    pipe.rpush(key, dumps_point({k: m[k] for k in (
                        "ts", "iops", "read_iops", "write_iops", "throughput_mbs",
                        "latency_read_ms", "latency_write_ms", "used_pct", "queue_depth", "errors",
                    )}))
                    if age == 0:
                        latest.append(m)
                pipe.ltrim(key, -HISTORY_LEN, -1)

            batch.append(_ops)
            if len(batch) >= 30:
                flush()
        flush()
        self.redis.set(f"{REDIS_KEY_PREFIX}:st:latest", json.dumps(latest))
        self.redis.hset(
            f"{REDIS_KEY_PREFIX}:st:collector",
            mapping={
                "last_sample_ts": datetime.now(timezone.utc).isoformat(),
                "last_sample_minute": str(minute),
                "volume_count": str(len(self._st_volumes)),
            },
        )
        self._last_st_sample_min = minute

    def _maybe_sample_storage(self) -> None:
        minute = now_minute()
        if getattr(self, "_last_st_sample_min", -1) == minute:
            return
        self._ensure_storage_catalog()
        if not self._st_volumes:
            return
        mode = self.state.mode
        latest: list[dict[str, Any]] = []
        pipe = self.redis.pipeline()
        for vol in self._st_volumes:
            m = sample_volume_metrics(vol, tick_minute=minute, mode=mode)
            m["ts"] = minute_iso(minute)
            latest.append(m)
            key = hist_key("st", vol["id"])
            pipe.rpush(key, dumps_point({k: m[k] for k in (
                "ts", "iops", "read_iops", "write_iops", "throughput_mbs",
                "latency_read_ms", "latency_write_ms", "used_pct", "queue_depth", "errors",
            )}))
            pipe.ltrim(key, -HISTORY_LEN, -1)
        pipe.set(f"{REDIS_KEY_PREFIX}:st:latest", json.dumps(latest))
        pipe.hset(
            f"{REDIS_KEY_PREFIX}:st:collector",
            mapping={
                "last_sample_ts": datetime.now(timezone.utc).isoformat(),
                "last_sample_minute": str(minute),
                "volume_count": str(len(latest)),
            },
        )
        pipe.execute()
        self._last_st_sample_min = minute

    def get_storage_latest(self) -> list[dict[str, Any]]:
        raw = self.redis.get(f"{REDIS_KEY_PREFIX}:st:latest")
        if not raw:
            self._seed_storage_history()
            raw = self.redis.get(f"{REDIS_KEY_PREFIX}:st:latest")
        return json.loads(raw) if raw else []

    def get_storage_clusters(self) -> list[dict[str, Any]]:
        return self.get_json("storage_clusters_rich") or build_storage_clusters_rich()

    def get_storage_volumes(self) -> list[dict[str, Any]]:
        return self.get_json("storage_volumes") or build_storage_volumes(self.get_storage_clusters())

    def get_storage_toptalkers(self, limit: int = 20, window_minutes: int = 15) -> dict[str, Any]:
        latest = self.get_storage_latest()
        candidates = rank_storage_talkers(latest, limit=max(limit * 2, 20))
        enriched = []
        for c in candidates:
            hist = self.get_storage_volume_history(c["volume_id"], limit=window_minutes)
            if hist:
                peak = max(h["iops"] for h in hist)
                avg_iops = int(sum(h["iops"] for h in hist) / len(hist))
                avg_lat = round(sum(h["latency_write_ms"] for h in hist) / len(hist), 3)
            else:
                peak, avg_iops, avg_lat = c["iops"], c["iops"], c["latency_write_ms"]
            row = dict(c)
            row["window_peak_iops"] = peak
            row["window_avg_iops"] = avg_iops
            row["window_avg_lat_ms"] = avg_lat
            row["iops_h"] = format_iops(c["iops"])
            row["peak_iops_h"] = format_iops(peak)
            enriched.append(row)
        enriched.sort(key=lambda r: r["window_peak_iops"], reverse=True)
        for i, r in enumerate(enriched[:limit], start=1):
            r["rank"] = i
        return {
            "talkers": enriched[:limit],
            "window_minutes": window_minutes,
            "collector": self.redis.hgetall(f"{REDIS_KEY_PREFIX}:st:collector"),
        }

    def get_storage_volume_history(self, volume_id: str, limit: int = HISTORY_LEN) -> list[dict[str, Any]]:
        rows = self.redis.lrange(hist_key("st", volume_id), -limit, -1)
        meta = getattr(self, "_st_vol_by_id", {}).get(volume_id)
        if not meta:
            meta = next((v for v in self.get_storage_volumes() if v["id"] == volume_id), {"id": volume_id})
        out = []
        for raw in rows:
            p = loads_point(raw)
            out.append({**meta, **p, "volume_id": volume_id})
        return out

    def get_storage_cluster_detail(self, cluster_id: str) -> dict[str, Any] | None:
        cluster = next((c for c in self.get_storage_clusters() if c["id"] == cluster_id), None)
        if not cluster:
            return None
        latest = {s["volume_id"]: s for s in self.get_storage_latest() if s["cluster_id"] == cluster_id}
        vols = []
        series = {}
        for v in self.get_storage_volumes():
            if v["cluster_id"] != cluster_id:
                continue
            m = latest.get(v["id"], {})
            row = {
                **v,
                "iops": m.get("iops", 0),
                "read_iops": m.get("read_iops", 0),
                "write_iops": m.get("write_iops", 0),
                "throughput_mbs": m.get("throughput_mbs", 0),
                "latency_read_ms": m.get("latency_read_ms", 0),
                "latency_write_ms": m.get("latency_write_ms", 0),
                "used_pct": m.get("used_pct", 0),
                "queue_depth": m.get("queue_depth", 0),
                "errors": m.get("errors", 0),
                "iops_h": format_iops(m.get("iops", 0)),
            }
            vols.append(row)
            hist = self.get_storage_volume_history(v["id"])
            series[v["id"]] = [
                {
                    "t": h["ts"],
                    "iops": h["iops"],
                    "thr": h["throughput_mbs"],
                    "lr": h["latency_read_ms"],
                    "lw": h["latency_write_ms"],
                }
                for h in hist
            ]
        totals = {
            "iops": sum(v["iops"] for v in vols),
            "throughput_mbs": round(sum(v["throughput_mbs"] for v in vols), 1),
            "used_pct": round(sum(v["used_pct"] for v in vols) / len(vols), 1) if vols else 0,
        }
        totals["iops_h"] = format_iops(totals["iops"])
        return {"cluster": cluster, "volumes": vols, "series": series, "totals": totals}

    def get_storage_overview(self) -> dict[str, Any]:
        talkers = self.get_storage_toptalkers(limit=10)
        clusters = self.get_storage_clusters()
        latest = self.get_storage_latest()
        by_c: dict[str, list] = {}
        for s in latest:
            by_c.setdefault(s["cluster_id"], []).append(s)
        rows = []
        for c in clusters:
            samples = by_c.get(c["id"], [])
            iops = sum(s["iops"] for s in samples)
            thr = round(sum(s["throughput_mbs"] for s in samples), 1)
            lat = round(sum(s["latency_write_ms"] for s in samples) / len(samples), 3) if samples else 0
            used = round(sum(s["used_pct"] for s in samples) / len(samples), 1) if samples else 0
            rows.append({
                **c,
                "iops": iops,
                "iops_h": format_iops(iops),
                "throughput_mbs": thr,
                "latency_write_ms": lat,
                "used_pct": used,
                "volume_count": len(samples),
            })
        return {
            "clusters": rows,
            "talkers": talkers["talkers"],
            "window_minutes": talkers["window_minutes"],
            "collector": talkers["collector"],
            "totals": {
                "iops": sum(r["iops"] for r in rows),
                "iops_h": format_iops(sum(r["iops"] for r in rows)),
                "throughput_mbs": round(sum(r["throughput_mbs"] for r in rows), 1),
                "clusters": len(rows),
                "volumes": len(latest),
            },
        }
