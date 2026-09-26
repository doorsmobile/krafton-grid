"""Simulation models — modular 20 MW centers toward 100 MW campus."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModularCenter:
    id: str
    name: str
    design_mw: float
    phase: str
    status: str  # online | commissioning | planned
    halls: int
    note: str


# 5 × 20 MW modular centers = 100 MW total site / investment envelope
MODULAR_CENTERS: list[ModularCenter] = [
    ModularCenter(
        "M1",
        "Modular Center 1 — First Online",
        20.0,
        "Phase 1",
        "online",
        3,
        "First modular AIDC block in operation (liquid-first)",
    ),
    ModularCenter(
        "M2",
        "Modular Center 2",
        20.0,
        "Phase 2",
        "commissioning",
        3,
        "Fit-out / CDU & busway energization",
    ),
    ModularCenter(
        "M3",
        "Modular Center 3",
        20.0,
        "Phase 3",
        "planned",
        3,
        "Master-plan slot — power reserved",
    ),
    ModularCenter(
        "M4",
        "Modular Center 4",
        20.0,
        "Phase 4",
        "planned",
        3,
        "Master-plan slot — cooling plant shared",
    ),
    ModularCenter(
        "M5",
        "Modular Center 5",
        20.0,
        "Phase 5",
        "planned",
        3,
        "Master-plan slot — final 20 MW block",
    ),
]


@dataclass
class Hall:
    id: str
    name: str
    module_id: str
    design_mw: float
    rack_count: int
    avg_rack_kw: float
    cooling: str
    liquid_pct: float


# Halls inside first modular center (sum = 20 MW)
HALLS: list[Hall] = [
    Hall("H1", "Hall Alpha — Training", "M1", 8.0, 100, 72.0, "DLC Cold Plate", 0.94),
    Hall("H2", "Hall Beta — Inference", "M1", 7.0, 110, 58.0, "DLC + Rear Door", 0.80),
    Hall("H3", "Hall Gamma — Staging", "M1", 5.0, 80, 52.0, "Rear Door HX", 0.60),
]

ZONES = [
    {"id": "Z-PWR", "name": "Central Power Block", "type": "electrical"},
    {"id": "Z-CLU", "name": "Central Cooling Plant", "type": "mechanical"},
    {"id": "Z-NET", "name": "Spine Network Rooms", "type": "network"},
    {"id": "Z-BESS", "name": "BESS / Ride-through Yard", "type": "storage"},
]


@dataclass
class SimState:
    tick: int = 0
    mode: str = "normal"  # normal | stress | maintenance | failover
    it_load_mw: float = 14.8
    facility_mw: float = 2.6
    pue: float = 1.176
    ups_load_pct: float = 74.0
    cooling_load_pct: float = 68.0
    liquid_loop_temp_c: float = 28.4
    return_temp_c: float = 36.2
    outdoor_temp_c: float = 22.0
    humidity_pct: float = 42.0
    active_alerts: int = 3
    renewable_pct: float = 34.0
    bess_soc_pct: float = 86.0
    hall_loads: dict[str, float] = field(default_factory=dict)
    module_loads: dict[str, float] = field(default_factory=dict)
    vendor_health: dict[str, str] = field(default_factory=dict)
