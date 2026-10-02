"""GPU fleet: 6,912 B300 GPUs, 864 HGX nodes in 12 SUs, Slurm + CubeFlow scheduling.

Per-GPU physics is vectorised with numpy. Heat flows one way: job profile ->
utilisation -> power -> (coolant supply + R_th * power) -> temperature ->
throttling -> effective speed -> job progress. Coolant supply per row comes
from the facility model, which is how a CDU failure reaches a training job.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from . import topology as T

N_GPU = T.GPU_COUNT
N_NODE = T.NODE_COUNT
G = T.GPUS_PER_NODE

R_TH = 0.0275          # °C per W, cold-plate junction-to-coolant
THROTTLE_C = 87.0
WARN_C = 80.0
CKPT_GB_PER_GPU = 3.4  # sharded weights + optimizer state per GPU per checkpoint
READ_GBS_PER_GPU = {"pretrain": 0.085, "finetune": 0.06, "rlhf": 0.03, "eval": 0.05, "data": 0.12}

PROFILES = {
    #            util band      sm band      mem GB       ib frac      cpu %      ckpt(s) dur(s)
    "pretrain":  dict(util=(91, 98), sm=(82, 94), mem=(248, 284), ib=(0.48, 0.78), cpu=(22, 40), ckpt=300, ckpt_dur=28, nvl=(950, 1500)),
    "finetune":  dict(util=(76, 93), sm=(62, 86), mem=(170, 262), ib=(0.18, 0.42), cpu=(25, 45), ckpt=240, ckpt_dur=18, nvl=(420, 900)),
    "rlhf":      dict(util=(50, 90), sm=(40, 80), mem=(190, 270), ib=(0.12, 0.35), cpu=(30, 55), ckpt=360, ckpt_dur=20, nvl=(300, 800)),
    "inference": dict(util=(24, 72), sm=(18, 60), mem=(90, 210), ib=(0.01, 0.04), cpu=(18, 38), ckpt=0, ckpt_dur=0, nvl=(40, 220)),
    "eval":      dict(util=(52, 82), sm=(38, 70), mem=(120, 240), ib=(0.03, 0.10), cpu=(30, 50), ckpt=0, ckpt_dur=0, nvl=(60, 300)),
    "notebook":  dict(util=(0, 34), sm=(0, 25), mem=(8, 120), ib=(0.0, 0.01), cpu=(4, 20), ckpt=0, ckpt_dur=0, nvl=(0, 40)),
    "data":      dict(util=(6, 26), sm=(3, 18), mem=(20, 90), ib=(0.0, 0.02), cpu=(55, 88), ckpt=0, ckpt_dur=0, nvl=(0, 20)),
}
PROFILE_PARTITION = {"pretrain": "train", "finetune": "train", "rlhf": "train", "inference": "infer",
                     "eval": "batch", "notebook": "dev", "data": "batch"}
PENDING_TARGET = {"train": 3, "batch": 2, "dev": 3}
WORK_S = {"pretrain": (7200, 21600), "finetune": (900, 3600), "rlhf": (1200, 3600), "eval": (300, 1200),
          "notebook": (1200, 5400), "data": (600, 2400), "inference": (10 ** 9, 10 ** 9)}


def _partition_of(profile: str, size: int) -> str:
    if profile == "eval" and size >= 8:
        return "train" if size > 16 else "batch"
    return PROFILE_PARTITION[profile]

# project -> list of (profile, weight, node sizes or gpu counts)
PROJECT_MIX = {
    "llm-pretrain":     [("pretrain", 0.55, [72, 144]), ("finetune", 0.30, [8, 16, 32]), ("eval", 0.15, [8, 16])],  # pretrain = whole SUs
    "pubg-ally":        [("finetune", 0.40, [8, 16, 24]), ("rlhf", 0.30, [8, 16]), ("eval", 0.20, [8]), ("notebook", 0.10, [1, 2])],
    "inzoi-smartzoi":   [("finetune", 0.40, [8, 16]), ("rlhf", 0.20, [8, 12]), ("eval", 0.20, [8, 16]), ("notebook", 0.20, [1, 2, 4])],
    "speech-voice":     [("finetune", 0.50, [2, 4, 8]), ("eval", 0.25, [4, 8]), ("notebook", 0.25, [1, 2])],
    "vision-gen":       [("finetune", 0.50, [4, 8, 16]), ("eval", 0.20, [8]), ("notebook", 0.30, [1, 2, 4])],
    "research-sandbox": [("notebook", 0.50, [1, 2, 4, 8]), ("finetune", 0.30, [2, 4]), ("data", 0.20, [4, 8])],
}
JOB_NAMES = {
    "pretrain": ["kg-llm-70b-stage2", "kg-llm-moe-200b", "kg-llm-34b-longctx", "kg-llm-8b-distill"],
    "finetune": ["sft-dialogue-v4", "ally-policy-sft", "zoi-persona-lora", "tts-kr-v3", "vision-3d-diffusion", "code-assist-sft"],
    "rlhf": ["ally-grpo-rl", "zoi-dpo-align", "llm-rlhf-ppo"],
    "inference": ["vllm-kg-70b", "trtllm-ally-8b", "tts-stream", "zoi-dialogue-svc", "embed-e5"],
    "eval": ["mmlu-kr-eval", "ally-arena-eval", "safety-redteam", "asr-wer-bench"],
    "notebook": ["jupyter", "vscode-remote", "rcs-dev"],
    "data": ["tokenize-shard", "dedup-minhash", "video-decode"],
}
USERS = {
    "llm-pretrain": ["hjpark", "sykim", "mjlee", "dhchoi", "jwkang"],
    "pubg-ally": ["tykim", "hsyoon", "jhlim"],
    "inzoi-smartzoi": ["eunji.o", "mskwon", "yjseo"],
    "speech-voice": ["shpark", "kyjung"],
    "vision-gen": ["jmhan", "dwshin", "sjbaek"],
    "research-sandbox": ["intern01", "wjcho", "hrmoon", "sbnam"],
    "inference-prod": ["svc-inference"],
}
XID_CODES = {
    13: ("Graphics Engine Exception", 0), 31: ("GPU memory page fault", 0), 43: ("GPU stopped processing", 1),
    48: ("Double-bit ECC error", 2), 63: ("Row remapping event", 0), 74: ("NVLink error", 1),
    79: ("GPU has fallen off the bus", 2), 94: ("Contained ECC error", 1), 95: ("Uncontained ECC error", 2),
    119: ("GSP RPC timeout", 1), 120: ("GSP error", 1),
}

B300_MIG_PROFILES = {
    "1g.36gb": 7, "2g.72gb": 3, "3g.144gb": 2, "4g.144gb": 1, "7g.288gb": 1,
}
MIG_LAYOUTS = [
    ["1g.36gb"] * 7,
    ["2g.72gb"] * 3 + ["1g.36gb"],
    ["3g.144gb", "3g.144gb"],
    ["4g.144gb", "2g.72gb", "1g.36gb"],
]


@dataclass
class Job:
    id: int
    name: str
    project: str
    user: str
    profile: str
    partition: str
    size: int                      # nodes for exclusive jobs, GPUs otherwise
    exclusive: bool
    work_s: float
    submit_t: float
    orchestrator: str = "slurm"
    state: str = "PENDING"
    start_t: float = 0.0
    end_t: float = 0.0
    progress: float = 0.0
    speed: float = 1.0
    gpus: list = field(default_factory=list)
    nodes: list = field(default_factory=list)
    ckpt_phase: float = 0.0
    reason: str = ""
    service: bool = False
    step_ms: float = 0.0

    @property
    def gpu_count(self) -> int:
        return len(self.gpus) if self.gpus else (self.size * G if self.exclusive else self.size)

    def public(self, now: float) -> dict:
        run = (now - self.start_t) if self.start_t else 0.0
        eta = None
        if self.state == "RUNNING" and not self.service and self.speed > 0.01:
            eta = max(0.0, (1 - self.progress) * self.work_s / self.speed)
        return {
            "id": f"{self.id}", "name": self.name, "project": self.project, "user": self.user,
            "profile": self.profile, "partition": self.partition, "orchestrator": self.orchestrator,
            "state": self.state, "gpus": self.gpu_count, "nodes": len(self.nodes) or (self.size if self.exclusive else 0),
            "progress": round(self.progress * 100, 1), "speed": round(self.speed, 3),
            "runtime_s": round(run), "eta_s": None if eta is None else round(eta),
            "wait_s": round((self.start_t or now) - self.submit_t), "reason": self.reason,
            "service": self.service, "step_ms": round(self.step_ms, 1),
            "node_list": [T.NODE_IDS[n] for n in self.nodes[:64]],
        }


class Fleet:
    def __init__(self, rng: np.random.Generator, now: float):
        self.rng = rng
        self.gpu_rack = np.repeat(np.array(T.NODE_RACK_IDX), G)
        self.node_rack = np.array(T.NODE_RACK_IDX)
        self.node_su = np.array([T.SU_BY_ID[s]["index"] for s in T.NODE_SU])
        self.rack_row = [rk.row for rk in T.GPU_RACK_LIST]
        self.node_partition = np.array([T.RACK_PARTITION[r] for r in T.NODE_RACK])
        self.gpu_partition = np.repeat(self.node_partition, G)

        self.offset = rng.normal(0, 1.6, N_GPU).astype(np.float32)
        self.util = np.zeros(N_GPU, np.float32)
        self.sm = np.zeros(N_GPU, np.float32)
        self.mem = np.full(N_GPU, 1.5, np.float32)
        self.membw = np.zeros(N_GPU, np.float32)
        self.power = np.full(N_GPU, T.GPU_IDLE_W, np.float32)
        self.temp = np.full(N_GPU, 36.0, np.float32)
        self.hbm = np.full(N_GPU, 40.0, np.float32)
        self.clock = np.full(N_GPU, 1965.0, np.float32)
        self.nvlink = np.zeros(N_GPU, np.float32)
        self.pcie = np.zeros(N_GPU, np.float32)
        self.throttle = np.zeros(N_GPU, np.int8)      # 0 none · 1 thermal · 2 power cap
        self.health = np.zeros(N_GPU, np.int8)        # 0 ok · 1 degraded · 2 failed
        self.ecc_sbe = rng.poisson(0.4, N_GPU).astype(np.int32)
        self.ecc_dbe = np.zeros(N_GPU, np.int32)
        self.xid_last = np.zeros(N_GPU, np.int16)
        self.xid_t = np.zeros(N_GPU, np.float64)
        self.gpu_job = np.full(N_GPU, -1, np.int32)
        self.coolant = np.full(N_GPU, 32.0, np.float32)

        self.node_cpu = np.zeros(N_NODE, np.float32)
        self.node_hostmem = np.full(N_NODE, 12.0, np.float32)
        self.node_power = np.zeros(N_NODE, np.float32)
        self.node_ib = np.zeros(N_NODE, np.float32)     # Gb/s
        self.node_eth = np.zeros(N_NODE, np.float32)    # Gb/s
        self.node_state = np.array(["idle"] * N_NODE, dtype=object)
        self.node_reason = [""] * N_NODE
        self.node_until = np.zeros(N_NODE, np.float64)
        self.node_events: dict[int, deque] = {}

        self.jobs: dict[int, Job] = {}
        self.finished: deque[dict] = deque(maxlen=400)
        self.next_job_id = 481200
        self.mig: dict[int, list[dict]] = {}
        self.gpu_seconds_today: dict[str, float] = {p["id"]: 0.0 for p in T.PROJECTS}
        self.idle_alloc_seconds: dict[str, float] = {p["id"]: 0.0 for p in T.PROJECTS}
        self.events: deque[dict] = deque(maxlen=600)
        self.completed_ts: deque[float] = deque(maxlen=2000)
        self.failed_ts: deque[float] = deque(maxlen=2000)
        self.xid_ts: deque[tuple] = deque(maxlen=2000)
        self.arrival_mult = 1.0
        self.inference_demand = 1.0
        self.diurnal = 0.8
        self.ckpt_write_gbs = 0.0
        self.train_read_gbs = 0.0
        self.io_by_project = {p["id"]: [0.0, 0.0] for p in T.PROJECTS}
        self.ckpt_jobs: list[int] = []

        self._setup_mig()
        self._seed_jobs(now)

    # ------------------------------------------------------------------ setup
    def _setup_mig(self) -> None:
        infer_nodes = [n for n in range(N_NODE) if self.node_partition[n] == "infer"]
        for k, n in enumerate(infer_nodes[-20:]):
            for g in range(G):
                gi = n * G + g
                layout = MIG_LAYOUTS[(k + g) % len(MIG_LAYOUTS)]
                svc = ["trtllm-ally-8b", "tts-stream", "embed-e5", "zoi-dialogue-svc"][(k + g) % 4]
                self.mig[gi] = [{"profile": p, "instance": i, "service": svc,
                                 "namespace": "inference-prod", "pod": f"{svc}-{(gi * 7 + i) % 9973:04x}"}
                                for i, p in enumerate(layout)]

    def _new_job(self, project: str, profile: str, size: int, now: float, service: bool = False,
                 orchestrator: str | None = None) -> Job:
        rng = self.rng
        part = _partition_of(profile, size)
        exclusive = profile in ("pretrain", "finetune", "rlhf", "inference") or (profile == "eval" and size >= 8)
        base = WORK_S[profile]
        name = str(rng.choice(JOB_NAMES[profile]))
        if orchestrator is None:
            orchestrator = "cubeflow" if profile in ("notebook", "eval") and rng.random() < 0.55 else "slurm"
        job = Job(
            id=self.next_job_id, name=name, project=project, user=str(rng.choice(USERS[project])),
            profile=profile, partition=part, size=size, exclusive=exclusive,
            work_s=float(rng.uniform(*base)), submit_t=now, orchestrator=orchestrator,
            ckpt_phase=float(rng.uniform(0, 1)), service=service,
        )
        self.next_job_id += 1
        self.jobs[job.id] = job
        return job

    def _seed_jobs(self, now: float) -> None:
        rng = self.rng
        # Production inference services pinned to the infer partition
        infer_nodes = [n for n in range(N_NODE) if self.node_partition[n] == "infer"]
        full_nodes = infer_nodes[:45]
        for i in range(0, len(full_nodes), 3):
            j = self._new_job("inference-prod", "inference", 3, now, service=True, orchestrator="cubeflow")
            j.name = ["vllm-kg-70b", "trtllm-ally-8b", "zoi-dialogue-svc", "tts-stream", "embed-e5"][(i // 3) % 5]
            self._start(j, now - rng.uniform(86400, 86400 * 9), nodes=full_nodes[i:i + 3])
        mig_nodes = infer_nodes[-20:]
        for i in range(0, len(mig_nodes), 5):
            j = self._new_job("inference-prod", "inference", 5, now, service=True, orchestrator="cubeflow")
            j.name = "mig-pool-" + "abcd"[i // 5]
            self._start(j, now - rng.uniform(86400, 86400 * 5), nodes=mig_nodes[i:i + 5])

        seeds = [
            ("llm-pretrain", "pretrain", 144), ("llm-pretrain", "pretrain", 72), ("llm-pretrain", "pretrain", 72),
            ("llm-pretrain", "finetune", 16),
            ("pubg-ally", "rlhf", 16), ("pubg-ally", "finetune", 16), ("inzoi-smartzoi", "finetune", 16),
            ("inzoi-smartzoi", "rlhf", 8), ("vision-gen", "finetune", 16), ("speech-voice", "finetune", 8),
            ("llm-pretrain", "finetune", 32), ("pubg-ally", "finetune", 24), ("vision-gen", "finetune", 8),
            ("llm-pretrain", "eval", 16), ("inzoi-smartzoi", "eval", 8),
        ]
        for proj, prof, size in seeds:
            j = self._new_job(proj, prof, size, now - rng.uniform(600, 5400))
            nodes = self._find_nodes(j)
            if nodes is not None:
                j.progress = float(rng.uniform(0.05, 0.85))
                self._start(j, now - j.progress * j.work_s, nodes=nodes)
        for _ in range(26):
            proj = str(rng.choice(["research-sandbox", "vision-gen", "inzoi-smartzoi", "speech-voice", "pubg-ally"]))
            j = self._new_job(proj, "notebook", int(rng.choice([1, 1, 2, 2, 4, 8])), now - rng.uniform(300, 7200))
            gpus = self._find_gpus(j)
            if gpus is not None:
                j.progress = float(rng.uniform(0.0, 0.7))
                self._start(j, now - j.progress * j.work_s, gpus=gpus)
        for _ in range(8):
            proj = str(rng.choice(["research-sandbox", "speech-voice", "vision-gen"]))
            prof = str(rng.choice(["data", "eval"]))
            j = self._new_job(proj, prof, int(rng.choice([2, 4, 4])), now - rng.uniform(60, 900))
            gpus = self._find_gpus(j)
            if gpus is not None:
                self._start(j, now - rng.uniform(30, 600), gpus=gpus)
        for proj, prof, size in [("llm-pretrain", "pretrain", 72), ("vision-gen", "finetune", 16), ("pubg-ally", "rlhf", 16)]:
            self._new_job(proj, prof, size, now - rng.uniform(120, 1800))
        # a couple of pre-existing drained nodes keep the health view honest
        for n in [int(rng.integers(0, 320)), int(rng.integers(320, 640))]:
            if self.node_state[n] == "idle":
                self._set_node(n, "drain", "Kill task failed · awaiting reboot", now, now + 600)

    # ------------------------------------------------------------- allocation
    def _node_free(self, n: int) -> bool:
        return self.node_state[n] == "idle" and (self.gpu_job[n * G:(n + 1) * G] < 0).all()

    def _find_nodes(self, job: Job) -> list[int] | None:
        cand = [n for n in range(N_NODE) if self.node_partition[n] == job.partition and self._node_free(n)]
        if len(cand) < job.size:
            return None
        # topology-aware: fewest SUs (each SU is one set of 8 rail leaves) first, then the tightest rack span
        best, best_score = None, None
        for start in range(0, max(1, len(cand) - job.size + 1), max(1, job.size // 4)):
            chunk = cand[start:start + job.size]
            if len(chunk) < job.size:
                break
            span = (int(self.node_su[chunk[-1]] - self.node_su[chunk[0]]), int(self.node_rack[chunk[-1]] - self.node_rack[chunk[0]]))
            if best_score is None or span < best_score:
                best, best_score = chunk, span
        return best

    def _find_gpus(self, job: Job) -> list[int] | None:
        part_nodes = [n for n in range(N_NODE) if self.node_partition[n] == job.partition
                      and self.node_state[n] in ("idle", "mix", "alloc")]
        # pack onto partially used nodes first
        part_nodes.sort(key=lambda n: -int((self.gpu_job[n * G:(n + 1) * G] >= 0).sum()))
        for n in part_nodes:
            free = [n * G + g for g in range(G) if self.gpu_job[n * G + g] < 0]
            if len(free) >= job.size:
                return free[:job.size]
        return None

    def _start(self, job: Job, t: float, nodes: list[int] | None = None, gpus: list[int] | None = None) -> None:
        if nodes is not None:
            job.nodes = list(nodes)
            job.gpus = [n * G + g for n in nodes for g in range(G)]
        else:
            job.gpus = list(gpus or [])
            job.nodes = sorted({gi // G for gi in job.gpus})
        self.gpu_job[job.gpus] = job.id
        job.state, job.start_t = "RUNNING", t
        for n in job.nodes:
            self._refresh_node_state(n)
        if t > 0:
            self._event("job_start", f"Job {job.id} {job.name} started on {len(job.nodes)} node(s)", job=job)

    def _finish(self, job: Job, now: float, state: str, reason: str = "") -> None:
        job.state, job.end_t, job.reason = state, now, reason
        if job.gpus:
            self.gpu_job[job.gpus] = -1
        for n in job.nodes:
            self._refresh_node_state(n)
        (self.completed_ts if state == "COMPLETED" else self.failed_ts).append(now)
        rec = job.public(now)
        rec["end_t"] = now
        self.finished.appendleft(rec)
        del self.jobs[job.id]
        self._event("job_end", f"Job {job.id} {job.name} {state.lower()}" + (f" — {reason}" if reason else ""),
                    job=job, level="error" if state == "FAILED" else "info")

    def _refresh_node_state(self, n: int) -> None:
        if self.node_state[n] in ("drain", "down", "maint"):
            return
        used = int((self.gpu_job[n * G:(n + 1) * G] >= 0).sum())
        self.node_state[n] = "idle" if used == 0 else ("alloc" if used == G else "mix")

    def _set_node(self, n: int, state: str, reason: str, now: float, until: float = 0.0) -> None:
        self.node_state[n] = state
        self.node_reason[n] = reason
        self.node_until[n] = until
        self.node_event(n, now, state, reason)

    def node_event(self, n: int, now: float, kind: str, text: str) -> None:
        dq = self.node_events.setdefault(n, deque(maxlen=40))
        dq.appendleft({"t": now, "kind": kind, "text": text})

    def _event(self, kind: str, text: str, job: Job | None = None, level: str = "info") -> None:
        self.events.appendleft({"kind": kind, "text": text, "level": level,
                                "job": job.id if job else None, "project": job.project if job else None})

    # -------------------------------------------------------------- scheduler
    def schedule(self, now: float, dt: float, cloud_burst_sink) -> None:
        rng = self.rng
        # arrivals — keep a realistic queue per partition instead of open-loop Poisson,
        # so the cluster sits at a busy steady state whatever the job durations are.
        for part, target in PENDING_TARGET.items():
            depth = sum(1 for j in self.jobs.values() if j.state == "PENDING" and j.partition == part)
            if depth < target * self.arrival_mult and rng.random() < 0.12 * dt:
                choices = [(proj, prof, sizes, w) for proj, mix in PROJECT_MIX.items()
                           for prof, w, sizes in mix if _partition_of(prof, max(sizes)) == part]
                if choices:
                    weights = np.array([c[3] for c in choices])
                    proj, prof, sizes, _ = choices[int(rng.choice(len(choices), p=weights / weights.sum()))]
                    self._new_job(proj, prof, int(rng.choice(sizes)), now)

        # completions / progress
        for job in list(self.jobs.values()):
            if job.state != "RUNNING":
                continue
            if not job.service:
                job.progress = min(1.0, job.progress + dt * job.speed / job.work_s)
                if job.progress >= 1.0:
                    self._finish(job, now, "COMPLETED")
                    continue
                if job.profile in ("notebook", "data", "eval") and rng.random() < 0.00008 * dt:
                    self._finish(job, now, "FAILED", str(rng.choice(["CUDA OOM", "exit code 1", "preempted by owner"])))

        # dispatch pending jobs by priority then age
        pending = sorted((j for j in self.jobs.values() if j.state == "PENDING"),
                         key=lambda j: (T.PROJECT_BY_ID[j.project]["priority"], j.submit_t))
        for job in pending:
            if job.exclusive:
                nodes = self._find_nodes(job)
                if nodes is not None:
                    self._start(job, now, nodes=nodes)
                else:
                    job.reason = "Resources" if job.size <= 32 else "Priority · waiting for large allocation"
            else:
                gpus = self._find_gpus(job)
                if gpus is not None:
                    self._start(job, now, gpus=gpus)
                else:
                    job.reason = "Resources"

        # queue too deep -> offer overflow to cloud
        patience = 40 if self.arrival_mult > 2 else 300
        waiting = [j for j in self.jobs.values() if j.state == "PENDING" and j.profile in ("finetune", "eval")
                   and now - j.submit_t > patience and j.gpu_count <= 128]
        for job in waiting[:2]:
            if cloud_burst_sink(job):
                job.state = "BURST"
                job.reason = "Burst to AWS Capacity Block"
                self._finish(job, now, "COMPLETED", "offloaded to AWS")

        # recover drained nodes (auto-reboot) and RMA'd ones after long repairs
        for n in np.where((self.node_until > 0) & (self.node_until <= now))[0]:
            if self.node_state[n] in ("drain", "down"):
                gi = slice(n * G, (n + 1) * G)
                self.health[gi] = 0
                self.xid_last[gi] = 0
                self.node_state[n] = "idle"
                self.node_reason[n] = ""
                self.node_until[n] = 0
                self.node_event(int(n), now, "resume", "Health checks passed · node resumed")
                self._refresh_node_state(int(n))

    def add_demand(self, profile_bias: float) -> None:
        self.arrival_mult = profile_bias

    # ---------------------------------------------------------------- physics
    def step(self, now: float, dt: float, row_supply_c: dict[str, float], ib_penalty: np.ndarray,
             xid_rate_rack: np.ndarray, power_cap_w: float) -> None:
        rng = self.rng
        target_u = np.full(N_GPU, 0.0, np.float32)
        target_sm = np.zeros(N_GPU, np.float32)
        target_mem = np.full(N_GPU, 1.5, np.float32)
        target_nvl = np.zeros(N_GPU, np.float32)
        node_ib_frac = np.zeros(N_NODE, np.float32)
        node_cpu_t = np.full(N_NODE, 3.0, np.float32)
        hour = ((now / 3600.0) + 9) % 24  # KST
        diurnal = 0.62 + 0.38 * math.sin((hour - 14.0) / 24 * 2 * math.pi)  # evening gaming peak
        self.diurnal = diurnal
        self.ckpt_write_gbs = 0.0
        self.train_read_gbs = 0.0
        self.io_by_project = {p["id"]: [0.0, 0.0] for p in T.PROJECTS}
        self.ckpt_jobs = []

        for job in self.jobs.values():
            if job.state != "RUNNING" or not job.gpus:
                continue
            p = PROFILES[job.profile]
            idx = np.array(job.gpus)
            lo, hi = p["util"]
            if job.profile == "inference":
                level = lo + (hi - lo) * min(1.0, diurnal * self.inference_demand)
                u = rng.normal(level, 5.0, len(idx))
            elif job.profile == "notebook":
                active = rng.random() < 0.12
                u = rng.uniform(15, hi, len(idx)) if active else rng.uniform(0, 4, len(idx))
            elif job.profile == "rlhf":
                phase = math.sin((now + job.id * 37) / 45.0)
                u = rng.normal(lo + (hi - lo) * (0.5 + 0.5 * phase), 4.0, len(idx))
            else:
                u = rng.uniform(lo, hi, len(idx))
            # synchronous checkpoints: the whole job dips together, storage absorbs the write burst
            in_ckpt = False
            if p["ckpt"]:
                cyc = ((now / p["ckpt"]) + job.ckpt_phase) % 1.0
                if cyc < p["ckpt_dur"] / p["ckpt"]:
                    u = u * 0.18
                    in_ckpt = True
                    w = len(idx) * CKPT_GB_PER_GPU / p["ckpt_dur"]
                    self.ckpt_write_gbs += w
                    self.io_by_project[job.project][1] += w
                    self.ckpt_jobs.append(job.id)
            if not in_ckpt and job.profile in ("pretrain", "finetune", "rlhf", "eval", "data"):
                r = len(idx) * READ_GBS_PER_GPU.get(job.profile, 0.03)
                self.train_read_gbs += r
                self.io_by_project[job.project][0] += r
            elif job.profile == "inference":
                self.io_by_project[job.project][0] += len(idx) * 0.004
            # fabric trouble stretches collective ops -> lower achieved util
            if p["ib"][1] > 0.1:
                pen = float(ib_penalty[self.node_rack[job.nodes]].max()) if job.nodes else 0.0
                u = u * (1.0 - pen)
            target_u[idx] = u
            target_sm[idx] = u * rng.uniform(p["sm"][0], p["sm"][1]) / max(1.0, hi)
            target_mem[idx] = rng.uniform(*p["mem"])
            target_nvl[idx] = rng.uniform(*p["nvl"]) * (u / max(1.0, hi))
            nodes = np.array(job.nodes)
            node_ib_frac[nodes] = np.maximum(node_ib_frac[nodes], rng.uniform(*p["ib"]) * (u.mean() / max(1.0, hi)))
            node_cpu_t[nodes] = rng.uniform(*p["cpu"])

        bad = self.health >= 2
        target_u[bad] = 0.0
        target_sm[bad] = 0.0

        self.util += (target_u - self.util) * 0.55 + rng.normal(0, 0.8, N_GPU).astype(np.float32)
        np.clip(self.util, 0, 100, out=self.util)
        self.sm += (np.minimum(target_sm, self.util) - self.sm) * 0.5
        np.clip(self.sm, 0, 100, out=self.sm)
        self.mem += (target_mem - self.mem) * 0.35
        np.clip(self.mem, 0.5, T.GPU_HBM_GB, out=self.mem)
        self.membw = np.clip(self.sm * rng.uniform(0.8, 1.05, N_GPU), 0, 100).astype(np.float32)
        self.nvlink += (target_nvl - self.nvlink) * 0.5
        self.pcie = np.clip(self.util * 0.42 + rng.normal(0, 1.5, N_GPU), 0, 63).astype(np.float32)

        # coolant supply per GPU from its row's CDU
        rack_supply = np.array([row_supply_c.get(r, 32.0) for r in self.rack_row], np.float32)
        self.coolant = rack_supply[self.gpu_rack]

        frac = (self.util / 100.0) ** 0.9
        p_target = T.GPU_IDLE_W + (T.GPU_TDP_W - T.GPU_IDLE_W) * frac * rng.uniform(0.93, 1.02, N_GPU)
        thermal = self.temp >= THROTTLE_C
        p_target = np.where(thermal, p_target * 0.78, p_target)
        capped = p_target > power_cap_w
        p_target = np.minimum(p_target, power_cap_w)
        p_target[bad] = 60.0
        self.power += (p_target.astype(np.float32) - self.power) * 0.6

        t_target = self.coolant + self.power * R_TH + self.offset
        self.temp += (t_target - self.temp) * 0.28 + rng.normal(0, 0.25, N_GPU).astype(np.float32)
        self.hbm = self.temp + 5.5 + self.offset * 0.4
        self.throttle = np.where(thermal, 1, np.where(capped & (self.util > 60), 2, 0)).astype(np.int8)
        self.clock = np.where(thermal, 1410.0, np.where(self.throttle == 2, 1830.0, 1965.0)).astype(np.float32)
        self.clock[self.util < 2] = 345.0

        # effective speed of each job reflects throttling on its GPUs
        for job in self.jobs.values():
            if job.state == "RUNNING" and job.gpus:
                idx = np.array(job.gpus)
                slow = float((self.throttle[idx] == 1).mean()) * 0.35 + float((self.throttle[idx] == 2).mean()) * 0.05
                pen = float(ib_penalty[self.node_rack[job.nodes]].max()) if job.nodes and PROFILES[job.profile]["ib"][1] > 0.1 else 0.0
                job.speed = max(0.05, 1.0 - slow - pen * 0.9)
                base_step = {"pretrain": 1850.0, "finetune": 620.0, "rlhf": 900.0}.get(job.profile, 0.0)
                job.step_ms = base_step / job.speed if base_step else 0.0

        # node aggregates
        pw = self.power.reshape(N_NODE, G).sum(axis=1)
        self.node_cpu += (node_cpu_t - self.node_cpu) * 0.4
        self.node_hostmem += (np.clip(node_cpu_t * 1.6 + 10, 5, 92) - self.node_hostmem) * 0.2
        self.node_power = pw + T.NODE_BASE_W * (0.55 + 0.45 * self.node_cpu / 100.0)
        down = np.isin(self.node_state, ["down"])
        self.node_power[down] = 0.0
        self.node_ib = node_ib_frac * 6400.0 * rng.uniform(0.9, 1.05, N_NODE).astype(np.float32)
        self.node_eth = (self.util.reshape(N_NODE, G).mean(axis=1) * 0.07 + rng.uniform(0.5, 3.0, N_NODE)).astype(np.float32)

        # health: ECC and XID events
        busy = self.util > 20
        sbe = rng.random(N_GPU) < (0.00004 * dt) * (1 + busy)
        self.ecc_sbe[sbe] += rng.integers(1, 4, int(sbe.sum()))
        rate = 1.1e-7 * dt + xid_rate_rack[self.gpu_rack]
        hit = np.where((rng.random(N_GPU) < rate) & (self.health < 2))[0]
        for gi in hit[:12]:
            self._xid(int(gi), now)
        degraded = (self.ecc_sbe > 60) | (self.throttle == 1)
        self.health = np.where(self.health >= 2, 2, np.where(degraded, 1, 0)).astype(np.int8)

        # accounting
        for job in self.jobs.values():
            if job.state == "RUNNING" and job.gpus:
                gs = len(job.gpus) * dt
                self.gpu_seconds_today[job.project] = self.gpu_seconds_today.get(job.project, 0.0) + gs
                idle = float((self.util[np.array(job.gpus)] < 5).mean())
                self.idle_alloc_seconds[job.project] = self.idle_alloc_seconds.get(job.project, 0.0) + gs * idle

    def _xid(self, gi: int, now: float, code: int | None = None) -> None:
        rng = self.rng
        if code is None:
            code = int(rng.choice([13, 31, 43, 48, 63, 74, 79, 94, 95, 119], p=[.18, .14, .1, .05, .12, .12, .06, .1, .03, .1]))
        desc, sev = XID_CODES[code]
        self.xid_last[gi] = code
        self.xid_t[gi] = now
        self.xid_ts.append((now, gi, code))
        n = gi // G
        self.node_event(n, now, "xid", f"GPU{gi % G} Xid {code}: {desc}")
        self._event("xid", f"{T.gpu_id(gi)} Xid {code} — {desc}", level="error" if sev >= 2 else "warn")
        if code == 48:
            self.ecc_dbe[gi] += 1
        if sev >= 2:
            self.health[gi] = 2
            jid = int(self.gpu_job[gi])
            if jid >= 0 and jid in self.jobs:
                job = self.jobs[jid]
                if not job.service:
                    self._finish(job, now, "FAILED", f"NODE_FAIL · Xid {code} on {T.NODE_IDS[n]}")
                else:
                    self.gpu_job[gi] = -1
            hard = code in (48, 95)
            self._set_node(n, "down" if hard else "drain",
                           f"Xid {code} · {'RMA ticket opened' if hard else 'auto-reboot scheduled'}",
                           now, now + (1800 if hard else 420))

    def inject_xid(self, gi: int, now: float, code: int) -> None:
        self._xid(gi, now, code)

    def drain(self, n: int, now: float, reason: str) -> None:
        for gi in range(n * G, (n + 1) * G):
            jid = int(self.gpu_job[gi])
            if jid >= 0 and jid in self.jobs and not self.jobs[jid].service:
                self._finish(self.jobs[jid], now, "FAILED", f"node drained · {reason}")
        self._set_node(n, "drain", reason, now, now + 600)

    def resume(self, n: int, now: float) -> None:
        self.node_until[n] = now

    # ---------------------------------------------------------------- summaries
    def summary(self, now: float) -> dict:
        alloc = self.gpu_job >= 0
        active = alloc & (self.util >= 5)
        effective = alloc & (self.sm >= 40)
        idle_alloc = alloc & (self.util < 5)
        unavailable = np.repeat(np.isin(self.node_state, ["drain", "down", "maint"]), G)
        running = [j for j in self.jobs.values() if j.state == "RUNNING"]
        pending = [j for j in self.jobs.values() if j.state == "PENDING"]
        hour_ago = now - 3600
        states = {s: int((self.node_state == s).sum()) for s in ("idle", "mix", "alloc", "drain", "down", "maint")}
        return {
            "total": N_GPU, "nodes": N_NODE, "racks": T.GPU_RACKS,
            "allocated": int(alloc.sum()), "active": int(active.sum()), "effective": int(effective.sum()),
            "idle_allocated": int(idle_alloc.sum()), "unallocated": int((~alloc & ~unavailable).sum()),
            "unavailable": int(unavailable.sum()),
            "allocation_pct": round(float(alloc.mean() * 100), 1),
            "avg_util": round(float(self.util.mean()), 1),
            "avg_util_alloc": round(float(self.util[alloc].mean()) if alloc.any() else 0.0, 1),
            "avg_sm": round(float(self.sm.mean()), 1),
            "avg_mem_gb": round(float(self.mem.mean()), 1),
            "avg_temp": round(float(self.temp.mean()), 1), "max_temp": round(float(self.temp.max()), 1),
            "p99_temp": round(float(np.percentile(self.temp, 99)), 1),
            "power_mw": round(float(self.node_power.sum() / 1e6), 3),
            "gpu_power_mw": round(float(self.power.sum() / 1e6), 3),
            "avg_power_w": round(float(self.power.mean()), 0),
            "thermal_throttle": int((self.throttle == 1).sum()), "power_throttle": int((self.throttle == 2).sum()),
            "healthy": int((self.health == 0).sum()), "degraded": int((self.health == 1).sum()),
            "failed": int((self.health == 2).sum()),
            "xid_1h": sum(1 for t, _, _ in self.xid_ts if t >= hour_ago),
            "ecc_sbe_total": int(self.ecc_sbe.sum()), "ecc_dbe_total": int(self.ecc_dbe.sum()),
            "nvlink_tbs": round(float(self.nvlink.sum() / 1000.0), 1),
            "node_states": states,
            "jobs_running": len(running), "jobs_pending": len(pending),
            "pending_gpus": sum(j.gpu_count for j in pending),
            "completed_1h": sum(1 for t in self.completed_ts if t >= hour_ago),
            "failed_1h": sum(1 for t in self.failed_ts if t >= hour_ago),
            "mig_gpus": len(self.mig), "mig_instances": sum(len(v) for v in self.mig.values()),
        }

    def partition_summary(self) -> list[dict]:
        out = []
        for p in T.PARTITIONS:
            mask = self.node_partition == p["id"]
            nodes = np.where(mask)[0]
            gmask = np.repeat(mask, G)
            alloc = (self.gpu_job >= 0) & gmask
            out.append({
                "id": p["id"], "desc": p["desc"], "nodes": int(len(nodes)), "gpus": int(gmask.sum()),
                "allocated_gpus": int(alloc.sum()),
                "util": round(float(self.util[gmask].mean()), 1),
                "states": {s: int((self.node_state[nodes] == s).sum()) for s in ("idle", "mix", "alloc", "drain", "down")},
                "pending": sum(1 for j in self.jobs.values() if j.state == "PENDING" and j.partition == p["id"]),
                "running": sum(1 for j in self.jobs.values() if j.state == "RUNNING" and j.partition == p["id"]),
            })
        return out

    def project_usage(self) -> list[dict]:
        out = []
        for proj in T.PROJECTS:
            pid = proj["id"]
            mask = np.isin(self.gpu_job, [j.id for j in self.jobs.values() if j.project == pid and j.state == "RUNNING"])
            used = int(mask.sum())
            out.append({
                **proj, "used_gpus": used, "quota_pct": round(used / proj["quota_gpus"] * 100, 1),
                "util": round(float(self.util[mask].mean()), 1) if used else 0.0,
                "running": sum(1 for j in self.jobs.values() if j.project == pid and j.state == "RUNNING"),
                "pending": sum(1 for j in self.jobs.values() if j.project == pid and j.state == "PENDING"),
                "gpu_hours_today": round(self.gpu_seconds_today.get(pid, 0.0) / 3600, 1),
                "idle_gpu_hours_today": round(self.idle_alloc_seconds.get(pid, 0.0) / 3600, 1),
            })
        return out

    def gpu_record(self, gi: int, now: float) -> dict:
        n = gi // G
        jid = int(self.gpu_job[gi])
        job = self.jobs.get(jid)
        return {
            "id": T.gpu_id(gi), "index": gi, "slot": gi % G, "node": T.NODE_IDS[n], "rack": T.NODE_RACK[n],
            "model": T.GPU_MODEL, "hbm_gb": T.GPU_HBM_GB,
            "util": round(float(self.util[gi]), 1), "sm": round(float(self.sm[gi]), 1),
            "mem_gb": round(float(self.mem[gi]), 1), "mem_pct": round(float(self.mem[gi]) / T.GPU_HBM_GB * 100, 1),
            "membw": round(float(self.membw[gi]), 1),
            "power_w": round(float(self.power[gi]), 0), "temp_c": round(float(self.temp[gi]), 1),
            "hbm_c": round(float(self.hbm[gi]), 1), "coolant_c": round(float(self.coolant[gi]), 1),
            "clock_mhz": round(float(self.clock[gi])), "nvlink_gbs": round(float(self.nvlink[gi]), 0),
            "pcie_gbs": round(float(self.pcie[gi]), 1),
            "throttle": ["none", "thermal", "power-cap"][int(self.throttle[gi])],
            "health": ["healthy", "degraded", "failed"][int(self.health[gi])],
            "ecc_sbe": int(self.ecc_sbe[gi]), "ecc_dbe": int(self.ecc_dbe[gi]),
            "xid": int(self.xid_last[gi]) or None,
            "xid_desc": XID_CODES.get(int(self.xid_last[gi]), ("", 0))[0] if self.xid_last[gi] else "",
            "xid_age_s": round(now - float(self.xid_t[gi])) if self.xid_last[gi] else None,
            "job": job.public(now) if job else None,
            "mig": self.mig.get(gi, []),
        }

    def node_record(self, n: int, now: float) -> dict:
        gi = slice(n * G, (n + 1) * G)
        jobs = {int(j) for j in self.gpu_job[gi] if j >= 0}
        return {
            "id": T.NODE_IDS[n], "index": n, "rack": T.NODE_RACK[n], "slot": T.NODE_SLOT[n], "su": T.NODE_SU[n],
            "row": self.rack_row[self.node_rack[n]], "hall": T.RACK_BY_ID[T.NODE_RACK[n]].hall,
            "partition": str(self.node_partition[n]), "model": T.NODE_MODEL,
            "state": str(self.node_state[n]), "reason": self.node_reason[n],
            "power_kw": round(float(self.node_power[n]) / 1000, 2),
            "cpu": round(float(self.node_cpu[n]), 1), "host_mem": round(float(self.node_hostmem[n]), 1),
            "ib_gbps": round(float(self.node_ib[n]), 0), "eth_gbps": round(float(self.node_eth[n]), 1),
            "util": round(float(self.util[gi].mean()), 1), "sm": round(float(self.sm[gi].mean()), 1),
            "temp_max": round(float(self.temp[gi].max()), 1), "temp_avg": round(float(self.temp[gi].mean()), 1),
            "mem_gb": round(float(self.mem[gi].sum()), 0),
            "gpus_alloc": int((self.gpu_job[gi] >= 0).sum()),
            "gpus_failed": int((self.health[gi] == 2).sum()),
            "throttling": int((self.throttle[gi] > 0).sum()),
            "coolant_c": round(float(self.coolant[n * G]), 1),
            "jobs": [self.jobs[j].public(now) for j in jobs if j in self.jobs],
            "orchestrator": ", ".join(sorted({self.jobs[j].orchestrator for j in jobs if j in self.jobs})) or "—",
            "user": ", ".join(sorted({self.jobs[j].user for j in jobs if j in self.jobs})) or "—",
            "ib_leaf": T.RACK_BY_ID[T.NODE_RACK[n]].ib_leaf, "eth_leaf": T.RACK_BY_ID[T.NODE_RACK[n]].eth_leaf,
            "events": list(self.node_events.get(n, [])),
        }

    def node_rows(self, now: float) -> list[dict]:
        """Compact per-node table for the Slurm + CubeFlow monitor (one row per node)."""
        util = self.util.reshape(N_NODE, G).mean(axis=1)
        mem = self.mem.reshape(N_NODE, G).sum(axis=1)
        temp = self.temp.reshape(N_NODE, G).max(axis=1)
        out = []
        for n in range(N_NODE):
            jids = {int(j) for j in self.gpu_job[n * G:(n + 1) * G] if j >= 0}
            js = [self.jobs[j] for j in jids if j in self.jobs]
            out.append({
                "id": T.NODE_IDS[n], "rack": T.NODE_RACK[n], "partition": str(self.node_partition[n]),
                "state": str(self.node_state[n]), "util": round(float(util[n]), 1),
                "mem_gb": round(float(mem[n])), "power_kw": round(float(self.node_power[n]) / 1000, 2),
                "temp": round(float(temp[n]), 1),
                "job": js[0].name if len(js) == 1 else (f"{len(js)} jobs" if js else "—"),
                "job_id": js[0].id if len(js) == 1 else None,
                "user": js[0].user if len(js) == 1 else ("multi" if js else "—"),
                "project": js[0].project if len(js) == 1 else ("multi" if js else "—"),
                "orch": js[0].orchestrator if len(js) == 1 else ("mixed" if js else "—"),
                "alloc": int((self.gpu_job[n * G:(n + 1) * G] >= 0).sum()),
            })
        return out
