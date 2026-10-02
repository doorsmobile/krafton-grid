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
    {"id": "HA", "name": "Hall A", "purpose": "GPU · B300 liquid · SU01–SU06", "design_mw": 6.0, "cooling": "liquid"},
    {"id": "HB", "name": "Hall B", "purpose": "GPU · B300 liquid · SU07–SU12", "design_mw": 6.0, "cooling": "liquid"},
    {"id": "HC", "name": "Hall C", "purpose": "Storage · Network · K8s", "design_mw": 3.0, "cooling": "air"},
    {"id": "HD", "name": "Hall D", "purpose": "Reserved · SU13–SU16 expansion", "design_mw": 5.0, "cooling": "liquid"},
]
HALL_BY_ID = {h["id"]: h for h in HALLS}

GPU_MODEL = "NVIDIA B300"
GPU_HBM_GB = 288
GPU_TDP_W = 1100.0
GPU_IDLE_W = 145.0
GPUS_PER_NODE = 8
NODE_MODEL = "HGX B300 8-GPU · liquid-cooled"
NODE_BASE_W = 2350.0  # CPUs, DRAM, 8x CX-8, BlueField-3, pumps

# Scalable units (NVIDIA DGX SuperPOD B300 reference architecture: 72 nodes / 576 GPUs per SU).
# One SU = one row of 4 racks × 18 nodes, its own 8 rail-optimized IB leaves and its own storage building blocks.
SU_COUNT = 12
NODES_PER_SU = 72
RACKS_PER_SU = 4
NODES_PER_RACK = NODES_PER_SU // RACKS_PER_SU          # 18
GPUS_PER_SU = NODES_PER_SU * GPUS_PER_NODE             # 576
SU_PER_HALL = 6                                        # Hall A: SU01–SU06 · Hall B: SU07–SU12
NODE_COUNT = SU_COUNT * NODES_PER_SU                   # 864
GPU_COUNT = NODE_COUNT * GPUS_PER_NODE                 # 6,912
GPU_RACKS = SU_COUNT * RACKS_PER_SU                    # 48
IB_RAILS = GPUS_PER_NODE                               # one ConnectX-8 (800G XDR) per GPU, one leaf per rail
RACK_U = 52


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
SUS: list[dict] = []

# Ethernet leaf numbering: one ToR per GPU rack, then storage, K8s and border leaves
STORAGE_RACKS_PER_LEAF = 6
HOT_RACKS_PER_SU, COLD_RACKS_PER_SU = 1, 2
STORAGE_RACKS = SU_COUNT * (HOT_RACKS_PER_SU + COLD_RACKS_PER_SU)          # 36
ETH_STORAGE_LEAF0 = GPU_RACKS + 1                                          # eth-leaf-49 …
ETH_K8S_LEAF0 = ETH_STORAGE_LEAF0 + STORAGE_RACKS // STORAGE_RACKS_PER_LEAF  # eth-leaf-55, 56
ETH_BORDER_LEAF0 = ETH_K8S_LEAF0 + 2                                       # eth-leaf-57, 58


def ib_leaf_id(su: int, rail: int) -> str:
    """Rail-optimized fabric: SU n (1-based) owns leaves (n-1)·8+1 … n·8; leaf for rail r carries GPU r of every node."""
    return f"ib-leaf-{(su - 1) * IB_RAILS + rail:02d}"


_node_cursor = 0
for su in range(1, SU_COUNT + 1):
    hall = "HA" if su <= SU_PER_HALL else "HB"
    row_id = f"{hall[1]}{(su - 1) % SU_PER_HALL + 1}"
    su_id = f"SU{su:02d}"
    leaves = [ib_leaf_id(su, r) for r in range(1, IB_RAILS + 1)]
    ROWS.append({"id": row_id, "hall": hall, "kind": "gpu", "cdu": f"CDU-{row_id}", "su": su_id})
    racks = []
    for p in range(RACKS_PER_SU):
        rack_no = (su - 1) * RACKS_PER_SU + p + 1
        RACKS.append(Rack(
            id=f"R{rack_no:02d}", hall=hall, row=row_id, pos=p + 1, kind="gpu",
            design_kw=220.0, node_start=_node_cursor, node_count=NODES_PER_RACK,
            label=f"{su_id} · B300 × {NODES_PER_RACK * GPUS_PER_NODE}", cdu=f"CDU-{row_id}",
            eth_leaf=f"eth-leaf-{rack_no:02d}", ib_leaf=leaves[0], extra={"su": su_id, "ib_leaves": leaves},
        ))
        racks.append(f"R{rack_no:02d}")
        _node_cursor += NODES_PER_RACK
    SUS.append({"id": su_id, "index": su - 1, "hall": hall, "row": row_id, "racks": racks, "ib_leaves": leaves,
                "node_start": _node_cursor - NODES_PER_SU, "node_count": NODES_PER_SU, "gpus": GPUS_PER_SU,
                "hot_racks": [f"S{su:02d}"],
                "cold_racks": [f"S{SU_COUNT + (su - 1) * COLD_RACKS_PER_SU + k + 1:02d}" for k in range(COLD_RACKS_PER_SU)]})
assert _node_cursor == NODE_COUNT
SU_BY_ID = {u["id"]: u for u in SUS}

# Hall C: row C1 = hot tier (one rack per SU), C2–C3 = cold tier (two racks per SU), C4 = core
for r in range(3):
    row_id = f"C{r + 1}"
    ROWS.append({"id": row_id, "hall": "HC", "kind": "storage", "cdu": ""})
    for p in range(SU_COUNT):
        s_no = r * SU_COUNT + p + 1
        hot = s_no <= SU_COUNT
        su = s_no if hot else (s_no - SU_COUNT - 1) // COLD_RACKS_PER_SU + 1
        tier = "ss-hot" if hot else "ss-cold"
        RACKS.append(Rack(id=f"S{s_no:02d}", hall="HC", row=row_id, pos=p + 1, kind="storage",
                          design_kw=30.0 if hot else 22.0, label=f"IBM Storage Scale · {tier} · SU{su:02d}",
                          extra={"cluster": tier, "su": f"SU{su:02d}"},
                          eth_leaf=f"eth-leaf-{ETH_STORAGE_LEAF0 + (s_no - 1) // STORAGE_RACKS_PER_LEAF:02d}"))
ROWS.append({"id": "C4", "hall": "HC", "kind": "core", "cdu": ""})
for p in range(6):
    RACKS.append(Rack(id=f"N{p + 1:02d}", hall="HC", row="C4", pos=p + 1, kind="network", design_kw=24.0,
                      label="Arista spine · IB spine (Quantum-X800)" if p < 4 else "Border · DCI"))
for p in range(3):
    RACKS.append(Rack(id=f"K{p + 1:02d}", hall="HC", row="C4", pos=7 + p, kind="k8s", design_kw=90.0,
                      label="Dell PowerEdge XE9680 × 10", eth_leaf=f"eth-leaf-{ETH_K8S_LEAF0 + (p // 2):02d}"))
RACKS.append(Rack(id="MG1", hall="HC", row="C4", pos=10, kind="mgmt", design_kw=12.0, label="OOB · BMS · Mgmt"))

for r in range(4):
    row_id = f"D{r + 1}"
    ROWS.append({"id": row_id, "hall": "HD", "kind": "reserved", "cdu": ""})
    for p in range(RACKS_PER_SU):
        RACKS.append(Rack(id=f"D{r + 1}{p + 1}", hall="HD", row=row_id, pos=p + 1, kind="reserved",
                          design_kw=220.0, label=f"Reserved · SU{SU_COUNT + r + 1:02d} (Phase 1.5)"))

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
# InfiniBand: NVIDIA Quantum-X800 XDR (Q3400-RA, 144 × 800G), rail-optimized two-tier fat tree.
#   per SU: 8 leaves (one per rail) · each leaf 72 down (one port per node) + 72 up
#   spines: 8 planes (one per rail) × 6 · a plane's 6 spines take the 12 same-rail leaves, 12 links per leaf
IB_PORTS = 144
IB_SPINES_PER_PLANE = (SU_COUNT * NODES_PER_SU) // IB_PORTS               # 6
IB_LINKS_PER_SPINE = NODES_PER_SU // IB_SPINES_PER_PLANE                  # 12
NET_DEVICES = []
for i in range(1, 9):
    NET_DEVICES.append({"id": f"eth-spine-{i:02d}", "fabric": "ethernet", "tier": "spine", "vendor": "Arista",
                        "model": "7800R3-36P", "ports": 144, "speed_g": 400, "rack": f"N0{1 + (i - 1) // 4}"})
for i in range(1, ETH_BORDER_LEAF0 + 2):
    if i <= GPU_RACKS:
        rack, role = f"R{i:02d}", "gpu-tor"
    elif i < ETH_K8S_LEAF0:
        rack, role = f"S{(i - ETH_STORAGE_LEAF0) * STORAGE_RACKS_PER_LEAF + 1:02d}", "storage"
    elif i < ETH_BORDER_LEAF0:
        rack, role = f"K0{1 + (i - ETH_K8S_LEAF0) * 2}", "k8s"
    else:
        rack, role = "N05", "border"
    NET_DEVICES.append({"id": f"eth-leaf-{i:02d}", "fabric": "ethernet", "tier": "leaf", "vendor": "Arista",
                        "model": "7060X6-64PE", "ports": 64, "speed_g": 800, "rack": rack, "role": role})
for i in range(1, IB_RAILS * IB_SPINES_PER_PLANE + 1):
    plane = (i - 1) // IB_SPINES_PER_PLANE + 1
    NET_DEVICES.append({"id": f"ib-spine-{i:02d}", "fabric": "infiniband", "tier": "spine", "vendor": "NVIDIA",
                        "model": "Quantum-X800 Q3400-RA", "ports": IB_PORTS, "speed_g": 800, "plane": plane,
                        "rack": f"N0{1 + (i - 1) * 4 // (IB_RAILS * IB_SPINES_PER_PLANE)}"})
for u in SUS:
    for rail, lid in enumerate(u["ib_leaves"], start=1):
        NET_DEVICES.append({"id": lid, "fabric": "infiniband", "tier": "leaf", "vendor": "NVIDIA",
                            "model": "Quantum-X800 Q3400-RA", "ports": IB_PORTS, "speed_g": 800,
                            "rack": u["racks"][0], "su": u["id"], "rail": rail, "plane": rail, "serves": list(u["racks"])})
NET_BY_ID = {d["id"]: d for d in NET_DEVICES}
ETH_LEAVES = [d for d in NET_DEVICES if d["fabric"] == "ethernet" and d["tier"] == "leaf"]
ETH_SPINES = [d for d in NET_DEVICES if d["fabric"] == "ethernet" and d["tier"] == "spine"]
IB_LEAVES = [d for d in NET_DEVICES if d["fabric"] == "infiniband" and d["tier"] == "leaf"]
IB_SPINES = [d for d in NET_DEVICES if d["fabric"] == "infiniband" and d["tier"] == "spine"]
IB_PLANE_SPINES = {p: [d["id"] for d in IB_SPINES if d["plane"] == p] for p in range(1, IB_RAILS + 1)}
IB_PLANE_LEAVES = {p: [d["id"] for d in IB_LEAVES if d["plane"] == p] for p in range(1, IB_RAILS + 1)}

# ---------------------------------------------------------------------------
# Storage — IBM Storage Scale, one hot + one cold building block per SU
# ---------------------------------------------------------------------------
HOT_PB_PER_SU, COLD_PB_PER_SU = 10.0, 30.0
NSD_PER_BLOCK = 2  # NSD server pair (canisters) per building block
STORAGE_CLUSTERS = [
    {"id": "ss-hot", "name": "Scale Hot · NVMe", "tier": "hot", "per_su_pb": HOT_PB_PER_SU,
     "product": "IBM Storage Scale System 6000 · all-NVMe (122.88 TB QLC)",
     "block": "SSS 6000 + NVMe expansion · 10 PB usable · 300 GB/s read · 180 GB/s write",
     "capacity_pb": HOT_PB_PER_SU * SU_COUNT, "peak_read_gbs": 300.0 * SU_COUNT, "peak_write_gbs": 180.0 * SU_COUNT,
     "racks": [r for u in SUS for r in u["hot_racks"]]},
    {"id": "ss-cold", "name": "Scale Cold · HDD", "tier": "cold", "per_su_pb": COLD_PB_PER_SU,
     "product": "IBM Storage Scale System 6000 · HDD expansion (4U102, 30 TB NL-SAS)",
     "block": "SSS 6000 + HDD enclosures · 30 PB usable · 120 GB/s read · 90 GB/s write",
     "capacity_pb": COLD_PB_PER_SU * SU_COUNT, "peak_read_gbs": 120.0 * SU_COUNT, "peak_write_gbs": 90.0 * SU_COUNT,
     "racks": [r for u in SUS for r in u["cold_racks"]]},
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
    {"id": "llm-pretrain", "name": "Foundation LLM Pretrain", "team": "KRAFTON AI · LLM", "quota_gpus": 3456, "priority": 1},
    {"id": "pubg-ally", "name": "PUBG Ally (Co-Playable Character)", "team": "PUBG Studio AI", "quota_gpus": 864, "priority": 2},
    {"id": "inzoi-smartzoi", "name": "inZOI Smart Zoi", "team": "inZOI Studio AI", "quota_gpus": 704, "priority": 2},
    {"id": "speech-voice", "name": "Speech & Voice", "team": "KRAFTON AI · Audio", "quota_gpus": 352, "priority": 3},
    {"id": "vision-gen", "name": "Vision & 3D Gen", "team": "KRAFTON AI · Vision", "quota_gpus": 512, "priority": 3},
    {"id": "inference-prod", "name": "Inference Production", "team": "AI Platform", "quota_gpus": 640, "priority": 1},
    {"id": "research-sandbox", "name": "Research Sandbox", "team": "AI Research", "quota_gpus": 384, "priority": 4},
]
PROJECT_BY_ID = {p["id"]: p for p in PROJECTS}

# Slurm partitions by SU (whole SUs keep training traffic inside one rail group)
def _su_racks(first: int, last: int) -> list[str]:
    return [r for u in SUS[first - 1:last] for r in u["racks"]]


PARTITIONS = [
    {"id": "train", "sus": "SU01–SU09", "racks": _su_racks(1, 9), "desc": "Large-scale training (exclusive nodes)"},
    {"id": "infer", "sus": "SU10", "racks": _su_racks(10, 10), "desc": "Inference · MIG-enabled"},
    {"id": "dev", "sus": "SU11", "racks": _su_racks(11, 11), "desc": "Interactive · notebooks · RCS"},
    {"id": "batch", "sus": "SU12", "racks": _su_racks(12, 12), "desc": "Eval · data processing"},
]
for _p in PARTITIONS:
    _p["range"] = f"{_p['racks'][0]}–{_p['racks'][-1]}"
PARTITION_BY_ID = {p["id"]: p for p in PARTITIONS}
RACK_PARTITION = {rk: p["id"] for p in PARTITIONS for rk in p["racks"]}
RACK_SU = {rk.id: rk.extra["su"] for rk in RACKS if rk.kind == "gpu"}
NODE_SU = [RACK_SU[r] for r in NODE_RACK]
