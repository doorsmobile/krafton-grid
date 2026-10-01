"""Static physical layout of the Krafton Grid campus.

Everything here is deterministic configuration; live state lives in the
domain models that index into these tables.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Campus / modules
# ---------------------------------------------------------------------------
MODULE_MW = 20.0
MODULES = [
    {"id": "M1", "phase": 1, "status": "live", "it_mw": 20.0, "rfs": "2026-03", "label": "Phase 1 · Active"},
    {"id": "M2", "phase": 2, "status": "construction", "it_mw": 20.0, "rfs": "2027-06", "label": "Phase 2 · Construction"},
    {"id": "M3", "phase": 3, "status": "design", "it_mw": 20.0, "rfs": "2028-03", "label": "Phase 3 · Design"},
    {"id": "M4", "phase": 4, "status": "planned", "it_mw": 20.0, "rfs": "2028-12", "label": "Phase 4 · Planned"},
    {"id": "M5", "phase": 5, "status": "planned", "it_mw": 20.0, "rfs": "2029-09", "label": "Phase 5 · Planned"},
]
CAMPUS_MW = MODULE_MW * len(MODULES)

# Build-out milestones per module (for the xrange timeline)
BUILDOUT = [
    ("M1", "Design", "2024-03", "2024-11"), ("M1", "Construction", "2024-11", "2025-11"),
    ("M1", "Commissioning", "2025-11", "2026-03"), ("M1", "Live", "2026-03", "2030-12"),
    ("M2", "Design", "2025-06", "2026-02"), ("M2", "Construction", "2026-02", "2027-03"),
    ("M2", "Commissioning", "2027-03", "2027-06"), ("M2", "Live", "2027-06", "2030-12"),
    ("M3", "Design", "2026-06", "2027-03"), ("M3", "Construction", "2027-03", "2028-01"),
    ("M3", "Commissioning", "2028-01", "2028-03"), ("M3", "Live", "2028-03", "2030-12"),
    ("M4", "Design", "2027-03", "2027-11"), ("M4", "Construction", "2027-11", "2028-10"),
    ("M4", "Commissioning", "2028-10", "2028-12"), ("M4", "Live", "2028-12", "2030-12"),
    ("M5", "Design", "2027-12", "2028-08"), ("M5", "Construction", "2028-08", "2029-07"),
    ("M5", "Commissioning", "2029-07", "2029-09"), ("M5", "Live", "2029-09", "2030-12"),
]

# ---------------------------------------------------------------------------
# M1 data halls & rows
# ---------------------------------------------------------------------------
HALLS = [
    {"id": "HA", "name": "Hall A", "purpose": "GPU · B300 liquid", "design_mw": 5.0, "cooling": "liquid"},
    {"id": "HB", "name": "Hall B", "purpose": "GPU · B300 liquid", "design_mw": 5.0, "cooling": "liquid"},
    {"id": "HC", "name": "Hall C", "purpose": "Storage · Network · K8s", "design_mw": 5.0, "cooling": "air"},
    {"id": "HD", "name": "Hall D", "purpose": "Reserved · expansion", "design_mw": 5.0, "cooling": "liquid"},
]
HALL_BY_ID = {h["id"]: h for h in HALLS}

GPU_MODEL = "NVIDIA B300"
GPU_HBM_GB = 288
GPU_TDP_W = 1100.0
GPU_IDLE_W = 145.0
GPUS_PER_NODE = 8
NODE_MODEL = "HGX B300 8-GPU · liquid-cooled"
NODE_BASE_W = 2350.0  # CPUs, DRAM, 8x CX-8, BlueField-3, pumps
NODE_COUNT = 625
GPU_COUNT = NODE_COUNT * GPUS_PER_NODE
GPU_RACKS = 40
RACK_U = 52


def _gpu_rack_sizes() -> list[int]:
    # 625 nodes over 40 racks: R01–R25 hold 16, R26–R40 hold 15.
    return [16] * 25 + [15] * 15


@dataclass
class Rack:
    id: str
    hall: str
    row: str
    pos: int
    kind: str  # gpu | storage | network | k8s | mgmt | reserved
    design_kw: float
    node_start: int = 0
    node_count: int = 0
    label: str = ""
    cdu: str = ""
    eth_leaf: str = ""
    ib_leaf: str = ""
    extra: dict = field(default_factory=dict)


RACKS: list[Rack] = []
ROWS: list[dict] = []

_node_cursor = 0
_sizes = _gpu_rack_sizes()
for hall_idx, hall in enumerate(["HA", "HB"]):
    letter = hall[1]
    for r in range(4):
        row_id = f"{letter}{r + 1}"
        ROWS.append({"id": row_id, "hall": hall, "kind": "gpu", "cdu": f"CDU-{row_id}"})
        for p in range(5):
            rack_no = hall_idx * 20 + r * 5 + p + 1
            n = _sizes[rack_no - 1]
            RACKS.append(Rack(
                id=f"R{rack_no:02d}", hall=hall, row=row_id, pos=p + 1, kind="gpu",
                design_kw=220.0, node_start=_node_cursor, node_count=n,
                label=f"B300 × {n * GPUS_PER_NODE}", cdu=f"CDU-{row_id}",
                eth_leaf=f"eth-leaf-{rack_no:02d}", ib_leaf=f"ib-leaf-{(rack_no - 1) // 4 + 1:02d}",
            ))
            _node_cursor += n
assert _node_cursor == NODE_COUNT

for r in range(3):
    row_id = f"C{r + 1}"
    ROWS.append({"id": row_id, "hall": "HC", "kind": "storage", "cdu": ""})
    for p in range(8):
        s_no = r * 8 + p + 1
        tier = "ss-hot" if s_no <= 8 else ("ss-capacity" if s_no <= 20 else "ss-archive")
        RACKS.append(Rack(id=f"S{s_no:02d}", hall="HC", row=row_id, pos=p + 1, kind="storage",
                          design_kw=38.0, label=f"IBM Storage · {tier}", extra={"cluster": tier},
                          eth_leaf=f"eth-leaf-{41 + (s_no - 1) // 6:02d}"))
ROWS.append({"id": "C4", "hall": "HC", "kind": "core", "cdu": ""})
for p in range(6):
    RACKS.append(Rack(id=f"N{p + 1:02d}", hall="HC", row="C4", pos=p + 1, kind="network", design_kw=24.0,
                      label="Arista spine · IB spine" if p < 4 else "Border · DCI"))
for p in range(3):
    RACKS.append(Rack(id=f"K{p + 1:02d}", hall="HC", row="C4", pos=7 + p, kind="k8s", design_kw=90.0,
                      label="Dell PowerEdge XE9680 × 10", eth_leaf=f"eth-leaf-{45 + (p // 2):02d}"))
RACKS.append(Rack(id="MG1", hall="HC", row="C4", pos=10, kind="mgmt", design_kw=12.0, label="OOB · BMS · Mgmt"))

for r in range(4):
    row_id = f"D{r + 1}"
    ROWS.append({"id": row_id, "hall": "HD", "kind": "reserved", "cdu": ""})
    for p in range(5):
        RACKS.append(Rack(id=f"D{r + 1}{p + 1}", hall="HD", row=row_id, pos=p + 1, kind="reserved",
                          design_kw=220.0, label="Reserved · Phase 1.5"))

RACK_BY_ID = {r.id: r for r in RACKS}
GPU_RACK_LIST = [r for r in RACKS if r.kind == "gpu"]

# node index -> (rack, slot)
NODE_RACK: list[str] = []
NODE_SLOT: list[int] = []
NODE_IDS: list[str] = []
for rk in GPU_RACK_LIST:
    for s in range(rk.node_count):
        NODE_RACK.append(rk.id)
        NODE_SLOT.append(s + 1)
        NODE_IDS.append(f"kg-{rk.id.lower()}-n{s + 1:02d}")
NODE_INDEX = {nid: i for i, nid in enumerate(NODE_IDS)}
RACK_INDEX = {rk.id: i for i, rk in enumerate(GPU_RACK_LIST)}
NODE_RACK_IDX = [RACK_INDEX[r] for r in NODE_RACK]


def gpu_id(i: int) -> str:
    return f"{NODE_IDS[i // GPUS_PER_NODE]}-g{i % GPUS_PER_NODE}"


def parse_gpu_id(gid: str) -> int | None:
    try:
        node_id, g = gid.rsplit("-g", 1)
        return NODE_INDEX[node_id] * GPUS_PER_NODE + int(g)
    except (ValueError, KeyError):
        return None


# ---------------------------------------------------------------------------
# Power chain — 2N
# ---------------------------------------------------------------------------
POWER_DEVICES = [
    {"id": "UTIL-1", "kind": "utility", "side": "A", "name": "KEPCO 154 kV Line 1", "rating_mw": 60.0, "parent": None, "vendor": "KEPCO"},
    {"id": "UTIL-2", "kind": "utility", "side": "B", "name": "KEPCO 154 kV Line 2", "rating_mw": 60.0, "parent": None, "vendor": "KEPCO"},
    {"id": "TX-A", "kind": "transformer", "side": "A", "name": "Main TR A 154/22.9 kV 40 MVA", "rating_mw": 36.0, "parent": "UTIL-1", "vendor": "HD Hyundai Electric"},
    {"id": "TX-B", "kind": "transformer", "side": "B", "name": "Main TR B 154/22.9 kV 40 MVA", "rating_mw": 36.0, "parent": "UTIL-2", "vendor": "HD Hyundai Electric"},
    {"id": "MV-A", "kind": "switchgear", "side": "A", "name": "22.9 kV MV Switchgear A", "rating_mw": 36.0, "parent": "TX-A", "vendor": "LS Electric"},
    {"id": "MV-B", "kind": "switchgear", "side": "B", "name": "22.9 kV MV Switchgear B", "rating_mw": 36.0, "parent": "TX-B", "vendor": "LS Electric"},
]
for hall in ["HA", "HB", "HC"]:
    for side in ["A", "B"]:
        POWER_DEVICES.append({
            "id": f"UPS-{side}-{hall}", "kind": "ups", "side": side, "hall": hall,
            "name": f"UPS {side}-side · {HALL_BY_ID[hall]['name']} (4 × 1.5 MW, Li-ion 5 min)",
            "rating_mw": 6.0, "parent": f"MV-{side}", "vendor": "Vertiv Liebert EXL S1",
        })
POWER_DEVICES.append({"id": "UPS-A-HD", "kind": "ups", "side": "A", "hall": "HD", "name": "UPS A · Hall D (planned)",
                      "rating_mw": 6.0, "parent": "MV-A", "vendor": "Vertiv", "planned": True})
POWER_DEVICES.append({"id": "UPS-B-HD", "kind": "ups", "side": "B", "hall": "HD", "name": "UPS B · Hall D (planned)",
                      "rating_mw": 6.0, "parent": "MV-B", "vendor": "Vertiv", "planned": True})
for row in ROWS:
    if row["kind"] == "reserved":
        continue
    for side in ["A", "B"]:
        POWER_DEVICES.append({
            "id": f"BW-{row['id']}-{side}", "kind": "busway", "side": side, "hall": row["hall"], "row": row["id"],
            "name": f"Busway {row['id']} · {side}-feed", "rating_mw": 1.6 if row["kind"] == "gpu" else 0.8,
            "parent": f"UPS-{side}-{row['hall']}", "vendor": "Schneider Electric I-Line",
        })
for g in range(1, 11):
    POWER_DEVICES.append({"id": f"GEN-{g:02d}", "kind": "generator", "side": "A" if g <= 5 else "B",
                          "name": f"Diesel Genset {g:02d} · 3.0 MW", "rating_mw": 3.0, "parent": None,
                          "vendor": "Cummins QSK95"})
POWER_BY_ID = {d["id"]: d for d in POWER_DEVICES}

# ---------------------------------------------------------------------------
# Cooling chain — liquid-first, N+1
# ---------------------------------------------------------------------------
COOLING_DEVICES = []
for c in range(1, 6):
    COOLING_DEVICES.append({"id": f"CH-{c}", "kind": "chiller", "name": f"Chiller {c} · 1,400 RT magnetic-bearing",
                            "capacity_mw": 4.9, "vendor": "Trane CVHS", "loop": "chw"})
for c in range(1, 7):
    COOLING_DEVICES.append({"id": f"CT-{c}", "kind": "tower", "name": f"Cooling Tower {c}", "capacity_mw": 4.2,
                            "vendor": "BAC Series 3000", "loop": "fws"})
for c in range(1, 5):
    COOLING_DEVICES.append({"id": f"HX-{c}", "kind": "hx", "name": f"Free-cooling Plate HX {c}", "capacity_mw": 3.5,
                            "vendor": "Alfa Laval", "loop": "fws"})
for row in ROWS:
    if row["kind"] == "gpu":
        COOLING_DEVICES.append({"id": f"CDU-{row['id']}", "kind": "cdu", "name": f"CDU {row['id']} · 1.35 MW L2L",
                                "capacity_mw": 1.35, "vendor": "Vertiv CoolChip CDU 1350", "loop": "tcs",
                                "hall": row["hall"], "row": row["id"]})
for hall in ["HA", "HB"]:
    COOLING_DEVICES.append({"id": f"CDU-{hall[1]}S", "kind": "cdu", "name": f"CDU {hall[1]}-Spare · N+1 manifold",
                            "capacity_mw": 1.35, "vendor": "Vertiv CoolChip CDU 1350", "loop": "tcs",
                            "hall": hall, "row": "", "spare": True})
for hall, n in [("HA", 4), ("HB", 4), ("HC", 8)]:
    for c in range(1, n + 1):
        COOLING_DEVICES.append({"id": f"CRAH-{hall[1]}{c}", "kind": "crah", "name": f"CRAH {hall[1]}{c} · fan wall",
                                "capacity_mw": 0.45 if hall != "HC" else 0.55, "vendor": "Stulz CyberAir", "loop": "chw",
                                "hall": hall})
COOLING_BY_ID = {d["id"]: d for d in COOLING_DEVICES}
ROW_CDU = {row["id"]: f"CDU-{row['id']}" for row in ROWS if row["kind"] == "gpu"}

# ---------------------------------------------------------------------------
# Network fabric
# ---------------------------------------------------------------------------
NET_DEVICES = []
for i in range(1, 9):
    NET_DEVICES.append({"id": f"eth-spine-{i:02d}", "fabric": "ethernet", "tier": "spine", "vendor": "Arista",
                        "model": "7800R3-36P", "ports": 144, "speed_g": 400, "rack": f"N0{1 + (i - 1) // 4}"})
for i in range(1, 49):
    if i <= 40:
        rack, role = f"R{i:02d}", "gpu-tor"
    elif i <= 44:
        rack, role = f"S{(i - 41) * 6 + 1:02d}", "storage"
    elif i <= 46:
        rack, role = f"K0{1 + (i - 45) * 2}", "k8s"
    else:
        rack, role = "N05", "border"
    NET_DEVICES.append({"id": f"eth-leaf-{i:02d}", "fabric": "ethernet", "tier": "leaf", "vendor": "Arista",
                        "model": "7060X6-64PE", "ports": 64, "speed_g": 800, "rack": rack, "role": role})
for i in range(1, 7):
    NET_DEVICES.append({"id": f"ib-spine-{i:02d}", "fabric": "infiniband", "tier": "spine", "vendor": "NVIDIA",
                        "model": "Quantum-2 QM9700", "ports": 64, "speed_g": 400, "rack": f"N0{3 + (i - 1) // 3}"})
for i in range(1, 11):
    NET_DEVICES.append({"id": f"ib-leaf-{i:02d}", "fabric": "infiniband", "tier": "leaf", "vendor": "NVIDIA",
                        "model": "Quantum-2 QM9700", "ports": 64, "speed_g": 400,
                        "rack": f"R{(i - 1) * 4 + 1:02d}", "serves": [f"R{(i - 1) * 4 + k:02d}" for k in range(1, 5)]})
NET_BY_ID = {d["id"]: d for d in NET_DEVICES}
ETH_LEAVES = [d for d in NET_DEVICES if d["fabric"] == "ethernet" and d["tier"] == "leaf"]
ETH_SPINES = [d for d in NET_DEVICES if d["fabric"] == "ethernet" and d["tier"] == "spine"]
IB_LEAVES = [d for d in NET_DEVICES if d["fabric"] == "infiniband" and d["tier"] == "leaf"]
IB_SPINES = [d for d in NET_DEVICES if d["fabric"] == "infiniband" and d["tier"] == "spine"]

# ---------------------------------------------------------------------------
# Storage — IBM Storage Scale, 100 PB
# ---------------------------------------------------------------------------
STORAGE_CLUSTERS = [
    {"id": "ss-hot", "name": "Scale Hot · NVMe", "product": "IBM Storage Scale System 6000 (all-NVMe)",
     "capacity_pb": 16.0, "peak_read_gbs": 1600.0, "peak_write_gbs": 1000.0, "racks": [f"S{i:02d}" for i in range(1, 9)]},
    {"id": "ss-capacity", "name": "Scale Capacity · QLC", "product": "IBM Storage Scale System 6000 (QLC hybrid)",
     "capacity_pb": 64.0, "peak_read_gbs": 420.0, "peak_write_gbs": 300.0, "racks": [f"S{i:02d}" for i in range(9, 21)]},
    {"id": "ss-archive", "name": "Archive · Tape/COS", "product": "IBM Storage Archive + Diamondback tape",
     "capacity_pb": 20.0, "peak_read_gbs": 45.0, "peak_write_gbs": 40.0, "racks": [f"S{i:02d}" for i in range(21, 25)]},
]
STORAGE_BY_ID = {c["id"]: c for c in STORAGE_CLUSTERS}
STORAGE_TOTAL_PB = sum(c["capacity_pb"] for c in STORAGE_CLUSTERS)

# ---------------------------------------------------------------------------
# Kubernetes — Dell PowerEdge XE9680 × 30
# ---------------------------------------------------------------------------
K8S_NODES = []
for i in range(1, 4):
    K8S_NODES.append({"id": f"k8s-cp-{i:02d}", "role": "control-plane", "rack": "K01", "model": "Dell PowerEdge XE9680",
                      "cpu_cores": 112, "mem_gb": 2048})
for i in range(1, 28):
    K8S_NODES.append({"id": f"k8s-w-{i:02d}", "role": "worker", "rack": f"K0{1 + (i + 2) // 10}",
                      "model": "Dell PowerEdge XE9680", "cpu_cores": 112, "mem_gb": 2048})
K8S_BY_ID = {n["id"]: n for n in K8S_NODES}

# ---------------------------------------------------------------------------
# Tenancy — GPU Platform projects map 1:1 to Slurm accounts
# ---------------------------------------------------------------------------
PROJECTS = [
    {"id": "llm-pretrain", "name": "Foundation LLM Pretrain", "team": "KRAFTON AI · LLM", "quota_gpus": 2560, "priority": 1},
    {"id": "pubg-ally", "name": "PUBG Ally (Co-Playable Character)", "team": "PUBG Studio AI", "quota_gpus": 640, "priority": 2},
    {"id": "inzoi-smartzoi", "name": "inZOI Smart Zoi", "team": "inZOI Studio AI", "quota_gpus": 512, "priority": 2},
    {"id": "speech-voice", "name": "Speech & Voice", "team": "KRAFTON AI · Audio", "quota_gpus": 256, "priority": 3},
    {"id": "vision-gen", "name": "Vision & 3D Gen", "team": "KRAFTON AI · Vision", "quota_gpus": 384, "priority": 3},
    {"id": "inference-prod", "name": "Inference Production", "team": "AI Platform", "quota_gpus": 480, "priority": 1},
    {"id": "research-sandbox", "name": "Research Sandbox", "team": "AI Research", "quota_gpus": 256, "priority": 4},
]
PROJECT_BY_ID = {p["id"]: p for p in PROJECTS}

# Slurm partitions by rack range
PARTITIONS = [
    {"id": "train", "racks": [f"R{i:02d}" for i in range(1, 31)], "desc": "Large-scale training (exclusive nodes)"},
    {"id": "infer", "racks": [f"R{i:02d}" for i in range(31, 36)], "desc": "Inference · MIG-enabled"},
    {"id": "dev", "racks": [f"R{i:02d}" for i in range(36, 39)], "desc": "Interactive · notebooks · RCS"},
    {"id": "batch", "racks": [f"R{i:02d}" for i in range(39, 41)], "desc": "Eval · data processing"},
]
RACK_PARTITION = {rk: p["id"] for p in PARTITIONS for rk in p["racks"]}
