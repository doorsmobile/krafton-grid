"""Cloud providers in fixed display order: AWS (GPUaaS) → GCP (Storage) → NHN (GPUaaS).

AWS also acts as the burst target: when the on-prem Slurm queue backs up,
eligible jobs are offloaded onto a reserved EC2 Capacity Block.
"""
from __future__ import annotations

import math
import zlib

import numpy as np

USD_KRW = 1392.0
PROVIDER_ORDER = ["aws", "gcp", "nhn"]

AWS_TYPES = {
    "p5en.48xlarge": {"gpu": "H200 141GB", "gpus": 8, "usd_hr": 63.30, "net_gbps": 3200},
    "p6-b200.48xlarge": {"gpu": "B200 180GB", "gpus": 8, "usd_hr": 77.40, "net_gbps": 3200},
}
NHN_FLAVORS = {
    "g3.h100.8x": {"gpu": "H100 80GB", "gpus": 8, "krw_hr": 78400},
    "g2.a100.8x": {"gpu": "A100 80GB", "gpus": 8, "krw_hr": 39200},
    "g2.l40s.4x": {"gpu": "L40S 48GB", "gpus": 4, "krw_hr": 13600},
}
GCS_CLASS_USD_GB_MO = {"STANDARD": 0.023, "NEARLINE": 0.010, "COLDLINE": 0.004, "ARCHIVE": 0.0012}


def _hid(prefix: str, *parts) -> str:
    h = zlib.crc32("|".join(map(str, parts)).encode())
    return f"{prefix}{h:08x}{(h * 2654435761) % 0xFFFFFFFFF:09x}"


class Cloud:
    def __init__(self, rng: np.random.Generator, now: float):
        self.rng = rng
        self.aws_instances: list[dict] = []
        self.capacity_blocks = [
            {"id": "cr-0b7e1f24c9a6d3e51", "type": "p6-b200.48xlarge", "count": 40, "az": "ap-northeast-2a",
             "start": now - 3 * 86400, "end": now + 11 * 86400, "status": "active", "upfront_usd": 40 * 77.40 * 24 * 14},
            {"id": "cr-04c9d1ab27e8f6c30", "type": "p5en.48xlarge", "count": 8, "az": "ap-northeast-2c",
             "start": now + 5 * 86400, "end": now + 12 * 86400, "status": "scheduled", "upfront_usd": 8 * 63.30 * 24 * 7},
        ]
        seeds = [("p5en.48xlarge", "on-demand", "inference-prod", "ondemand-serve"), ("p5en.48xlarge", "on-demand", "pubg-ally", "ally-eval"),
                 ("p5en.48xlarge", "on-demand", "vision-gen", "vision-render")]
        for i in range(6):
            t, purchase, proj, name = seeds[i % 3]
            self._launch(t, purchase, proj, f"{name}-{i:02d}", now - rng.uniform(3600, 86400 * 3), "running")
        for i in range(10):
            self._launch("p6-b200.48xlarge", "capacity-block", "llm-pretrain", f"cb-finetune-{i:02d}",
                         now - rng.uniform(600, 86400), "running", cb="cr-0b7e1f24c9a6d3e51")
        self.burst_jobs: list[dict] = []

        self.buckets = [
            {"name": "kg-datasets-apne3", "class": "STANDARD", "location": "asia-northeast3", "size_tb": 1840.0, "objects_m": 412.0, "purpose": "Training datasets mirror"},
            {"name": "kg-ckpt-archive", "class": "ARCHIVE", "location": "asia-northeast3", "size_tb": 3620.0, "objects_m": 18.4, "purpose": "Checkpoint DR archive"},
            {"name": "kg-model-registry-dr", "class": "NEARLINE", "location": "asia-northeast3", "size_tb": 418.0, "objects_m": 2.1, "purpose": "Model registry replica"},
            {"name": "kg-telemetry-coldline", "class": "COLDLINE", "location": "asia-northeast3", "size_tb": 262.0, "objects_m": 980.0, "purpose": "Telemetry long-term (relay sink)"},
            {"name": "kg-game-assets-cdn", "class": "STANDARD", "location": "asia", "size_tb": 38.5, "objects_m": 61.0, "purpose": "Generated game assets · CDN origin"},
        ]
        for b in self.buckets:
            b.update(ops_a_s=0.0, ops_b_s=0.0, egress_gbps=0.0, ingress_gbps=0.0, id=b["name"])
        self.disks = []
        for i, (kind, size, iops, mbps) in enumerate([("hyperdisk-ml", 64000, 0, 12000), ("hyperdisk-ml", 64000, 0, 12000),
                                                      ("hyperdisk-balanced", 16000, 160000, 2400), ("pd-ssd", 8000, 100000, 1200),
                                                      ("pd-ssd", 4000, 60000, 960), ("hyperdisk-throughput", 32000, 0, 2400)]):
            self.disks.append({"id": f"disk-{kind}-{i + 1:02d}", "name": f"{kind}-{i + 1:02d}", "type": kind,
                               "size_gb": size, "zone": f"asia-northeast3-{'abc'[i % 3]}",
                               "attached": f"gce-transfer-{(i % 3) + 1:02d}", "iops_limit": iops, "mbps_limit": mbps,
                               "iops": 0.0, "mbps": 0.0, "used_pct": float(rng.uniform(48, 88)), "status": "READY"})
        self.transfer = {"job": "kg-ckpt-dr-nightly", "status": "running", "progress": 0.34, "rate_gbps": 0.0}

        self.nhn = []
        for i in range(14):
            fl = ["g3.h100.8x", "g3.h100.8x", "g2.a100.8x", "g2.l40s.4x"][i % 4]
            proj = ["inference-prod", "speech-voice", "inzoi-smartzoi", "research-sandbox"][i % 4]
            self.nhn.append({"id": _hid("nhn-", "inst", i), "name": f"nhn-{proj.split('-')[0]}-{i + 1:02d}", "flavor": fl,
                             "zone": "KR1-A" if i % 2 else "KR1-B", "project": proj, "status": "ACTIVE",
                             "launched": now - float(rng.uniform(3600, 86400 * 20)), "util": 0.0, "gpu_mem_pct": 0.0,
                             **NHN_FLAVORS[fl]})
        self.cost_today_krw = {"aws": 0.0, "gcp": 0.0, "nhn": 0.0}
        self.cost_month_krw = {"aws": 0.0, "gcp": 0.0, "nhn": 0.0}
        self.snapshot: dict = {}

    def _launch(self, itype: str, purchase: str, project: str, name: str, t: float, state: str, cb: str | None = None) -> dict:
        spec = AWS_TYPES[itype]
        inst = {"id": _hid("i-", name, t), "name": name, "type": itype, "purchase": purchase, "project": project,
                "az": "ap-northeast-2a" if cb else "ap-northeast-2" + "abc"[len(self.aws_instances) % 3],
                "state": state, "launch_t": t, "capacity_block": cb, "util": 0.0, "gpu_mem_pct": 0.0,
                "net_gbps": 0.0, "usd_hr": spec["usd_hr"], "gpus": spec["gpus"], "gpu": spec["gpu"], "until": None}
        self.aws_instances.append(inst)
        return inst

    def accept_burst(self, job, now: float) -> bool:
        cb = self.capacity_blocks[0]
        in_cb = [i for i in self.aws_instances if i["capacity_block"] == cb["id"] and i["state"] in ("running", "pending")]
        need = max(1, math.ceil(job.gpu_count / 8))
        if len(in_cb) + need > cb["count"]:
            return False
        for k in range(need):
            inst = self._launch(cb["type"], "capacity-block", job.project, f"burst-{job.id}-{k}", now, "pending", cb=cb["id"])
            inst["until"] = now + job.work_s * (1 - job.progress) / 1.1
            inst["burst_job"] = job.id
        self.burst_jobs.insert(0, {"job": job.id, "name": job.name, "project": job.project, "gpus": job.gpu_count,
                                   "instances": need, "t": now})
        del self.burst_jobs[40:]
        return True

    def step(self, now: float, dt: float, diurnal: float, demand: float, faults: set[str]) -> None:
        rng = self.rng
        for inst in list(self.aws_instances):
            if inst["state"] == "pending" and now - inst["launch_t"] > 20:
                inst["state"] = "running"
            if inst["until"] and now >= inst["until"]:
                inst["state"] = "shutting-down"
                inst["until"] = None
                inst["term_t"] = now
            if inst["state"] == "shutting-down" and now - inst.get("term_t", now) > 30:
                self.aws_instances.remove(inst)
                continue
            if inst["state"] == "running":
                base = 88.0 if inst["purchase"] == "capacity-block" else 55.0 * diurnal * demand + 10
                inst["util"] = round(float(np.clip(base + rng.normal(0, 4), 0, 100)), 1)
                inst["gpu_mem_pct"] = round(float(np.clip(inst["util"] * 0.85 + rng.normal(0, 3), 0, 100)), 1)
                inst["net_gbps"] = round(inst["util"] / 100 * 380 * float(rng.uniform(0.8, 1.1)), 1)
            else:
                inst["util"] = 0.0
        for b in self.buckets:
            hot = b["class"] == "STANDARD"
            b["ops_a_s"] = round(float((380 if hot else 22) * rng.uniform(0.7, 1.3)), 0)
            b["ops_b_s"] = round(float((5200 if hot else 90) * diurnal * rng.uniform(0.7, 1.3)), 0)
            b["egress_gbps"] = round(float((6.5 if b["name"].endswith("cdn") else (2.2 if hot else 0.1)) * diurnal * rng.uniform(0.6, 1.4)), 2)
            b["ingress_gbps"] = round(float((4.8 if "ckpt" in b["name"] else 0.6) * rng.uniform(0.5, 1.5)), 2)
            b["size_tb"] = round(b["size_tb"] + b["ingress_gbps"] * dt / 8 / 1000 * 0.2, 2)
        for d in self.disks:
            d["iops"] = round(float(d["iops_limit"] * rng.uniform(0.2, 0.7)), 0) if d["iops_limit"] else 0.0
            d["mbps"] = round(float(d["mbps_limit"] * rng.uniform(0.25, 0.8)), 0)
        self.transfer["progress"] = (self.transfer["progress"] + dt / 7200) % 1.0
        self.transfer["rate_gbps"] = round(float(rng.uniform(3.8, 5.6)), 2)
        for n in self.nhn:
            n["status"] = "SHUTOFF" if n["id"] in faults else "ACTIVE"
            if n["status"] == "ACTIVE":
                base = (62.0 if n["project"] == "inference-prod" else 48.0) * (0.7 + 0.3 * diurnal) * demand
                n["util"] = round(float(np.clip(base + rng.normal(0, 5), 0, 100)), 1)
                n["gpu_mem_pct"] = round(float(np.clip(n["util"] * 0.9 + rng.normal(0, 4), 0, 100)), 1)
            else:
                n["util"] = n["gpu_mem_pct"] = 0.0

        aws_hr = sum(i["usd_hr"] for i in self.aws_instances if i["state"] in ("running", "pending")) * USD_KRW
        gcs_hr = sum(b["size_tb"] * 1000 * GCS_CLASS_USD_GB_MO[b["class"]] / 730 for b in self.buckets) * USD_KRW
        gcs_hr += sum(b["egress_gbps"] * 3600 / 8 * 0.08 for b in self.buckets) * USD_KRW / 10
        gcs_hr += sum(d["size_gb"] * 0.00016 for d in self.disks) * USD_KRW
        nhn_hr = sum(n["krw_hr"] for n in self.nhn if n["status"] == "ACTIVE")
        for k, v in (("aws", aws_hr), ("gcp", gcs_hr), ("nhn", nhn_hr)):
            self.cost_today_krw[k] += v * dt / 3600
            self.cost_month_krw[k] += v * dt / 3600
        running = [i for i in self.aws_instances if i["state"] == "running"]
        nhn_active = [n for n in self.nhn if n["status"] == "ACTIVE"]
        self.snapshot = {
            "order": PROVIDER_ORDER,
            "aws": {"running": len(running), "pending": sum(1 for i in self.aws_instances if i["state"] == "pending"),
                    "gpus": sum(i["gpus"] for i in running),
                    "gpu_util": round(float(np.mean([i["util"] for i in running])) if running else 0.0, 1),
                    "cost_hr_krw": round(aws_hr), "cb_used": sum(1 for i in self.aws_instances if i["capacity_block"]),
                    "cb_capacity": self.capacity_blocks[0]["count"], "burst_jobs": len(self.burst_jobs),
                    "dx_gbps": round(sum(i["net_gbps"] for i in running) * 0.02 + 8, 1)},
            "gcp": {"buckets": len(self.buckets), "used_tb": round(sum(b["size_tb"] for b in self.buckets), 1),
                    "ops_s": round(sum(b["ops_a_s"] + b["ops_b_s"] for b in self.buckets)),
                    "egress_gbps": round(sum(b["egress_gbps"] for b in self.buckets), 2),
                    "disks": len(self.disks), "disk_tb": round(sum(d["size_gb"] for d in self.disks) / 1000, 1),
                    "cost_hr_krw": round(gcs_hr), "transfer": self.transfer,
                    "ic_gbps": round(self.transfer["rate_gbps"] + sum(b["ingress_gbps"] for b in self.buckets), 1)},
            "nhn": {"active": len(nhn_active), "instances": len(self.nhn),
                    "gpus": sum(n["gpus"] for n in nhn_active),
                    "gpu_util": round(float(np.mean([n["util"] for n in nhn_active])) if nhn_active else 0.0, 1),
                    "cost_hr_krw": round(nhn_hr), "link_gbps": round(4 + 6 * diurnal, 1)},
            "total_cost_hr_krw": round(aws_hr + gcs_hr + nhn_hr),
            "today_krw": {k: round(v) for k, v in self.cost_today_krw.items()},
        }

    def border_gbps(self) -> dict:
        s = self.snapshot
        if not s:
            return {"aws": 8.0, "gcp": 5.0, "nhn": 6.0}
        return {"aws": s["aws"]["dx_gbps"], "gcp": s["gcp"]["ic_gbps"], "nhn": s["nhn"]["link_gbps"]}
