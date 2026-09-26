"""Major facility / power vendor catalog for AIDC DCIM integration."""

from __future__ import annotations

VENDORS = [
    {
        "id": "schneider",
        "name": "Schneider Electric",
        "category": "Power & DCIM",
        "products": ["EcoStruxure IT", "Galaxy VL UPS", "APC Rack PDU", "Premset MV"],
        "api": {
            "protocol": "REST / MQTT",
            "base_url": "https://api.ecostruxure-it.local/v1",
            "auth": "OAuth2 Client Credentials",
            "endpoints": ["/sites", "/devices", "/metrics", "/alarms"],
            "sample_metric": "ups.output.power_kw",
        },
        "coverage": ["UPS", "PDU", "MV Switchgear", "DCIM Platform"],
        "status": "connected",
        "latency_ms": 42,
    },
    {
        "id": "vertiv",
        "name": "Vertiv",
        "category": "Cooling & Power",
        "products": ["Liebert EXL S1", "CoolChip CDU", "Liebert DSE", "VR Rack"],
        "api": {
            "protocol": "REST / Modbus TCP Gateway",
            "base_url": "https://api.vertiv-intelligence.local/v2",
            "auth": "API Key + mTLS",
            "endpoints": ["/cdus", "/cracs", "/ups", "/telemetry"],
            "sample_metric": "cdu.loop.supply_temp_c",
        },
        "coverage": ["CDU", "CRAC", "UPS", "Rack"],
        "status": "connected",
        "latency_ms": 58,
    },
    {
        "id": "eaton",
        "name": "Eaton",
        "category": "Power Quality",
        "products": ["Power Xpert", "93PM UPS", "EnergyAware UPS", "Busway"],
        "api": {
            "protocol": "REST / BACnet/IP",
            "base_url": "https://api.powerxpert.local/v1",
            "auth": "Bearer Token",
            "endpoints": ["/ups", "/meters", "/busway", "/events"],
            "sample_metric": "busway.section.load_kw",
        },
        "coverage": ["UPS", "Busway", "Metering"],
        "status": "connected",
        "latency_ms": 51,
    },
    {
        "id": "abb",
        "name": "ABB",
        "category": "MV / Switchgear",
        "products": ["Ability EDCS", "UniGear ZS1", "TXpert Transformer", "Ability Energy Manager"],
        "api": {
            "protocol": "OPC UA / REST",
            "base_url": "https://api.abb-ability.local/v1",
            "auth": "Certificate + Token",
            "endpoints": ["/switchgear", "/transformers", "/feeders", "/pq"],
            "sample_metric": "mv.feeder.active_power_mw",
        },
        "coverage": ["MV Switchgear", "Transformer", "PQ"],
        "status": "connected",
        "latency_ms": 67,
    },
    {
        "id": "siemens",
        "name": "Siemens",
        "category": "BMS / Building",
        "products": ["Desigo CC", "SENTRON PAC", "SICAM", "Simatic"],
        "api": {
            "protocol": "REST / OPC UA",
            "base_url": "https://api.desigo.local/v3",
            "auth": "OAuth2",
            "endpoints": ["/buildings", "/points", "/alarms", "/trends"],
            "sample_metric": "bms.ahu.fan_speed_pct",
        },
        "coverage": ["BMS", "Metering", "Life Safety Integration"],
        "status": "degraded",
        "latency_ms": 188,
    },
    {
        "id": "stulz",
        "name": "STULZ",
        "category": "Precision Cooling",
        "products": ["CyberAir 3", "Explorer WPA", "CyberCool Indoor"],
        "api": {
            "protocol": "Modbus TCP / REST Bridge",
            "base_url": "https://api.stulz-cpc.local/v1",
            "auth": "Basic + IP allowlist",
            "endpoints": ["/units", "/circuits", "/setpoints", "/alarms"],
            "sample_metric": "crac.return_air_c",
        },
        "coverage": ["CRAH/CRAC", "Chiller Interface"],
        "status": "connected",
        "latency_ms": 73,
    },
    {
        "id": "coolit",
        "name": "CoolIT Systems",
        "category": "Liquid Cooling",
        "products": ["CHx80 CDU", "AHx Rack Manifold", "Direct Liquid Cooling"],
        "api": {
            "protocol": "REST / Redfish-style",
            "base_url": "https://api.coolit.local/v1",
            "auth": "API Key",
            "endpoints": ["/cdus", "/manifolds", "/racks", "/leaks"],
            "sample_metric": "dlc.rack.flow_lpm",
        },
        "coverage": ["CDU", "Manifold", "Cold Plate Loop"],
        "status": "connected",
        "latency_ms": 39,
    },
    {
        "id": "motivair",
        "name": "Motivair",
        "category": "Liquid Cooling",
        "products": ["ChilledDoor", "Cooling Distribution Unit", "DynamicCDU"],
        "api": {
            "protocol": "REST / SNMP",
            "base_url": "https://api.motivair.local/v1",
            "auth": "API Key",
            "endpoints": ["/doors", "/cdus", "/telemetry", "/alarms"],
            "sample_metric": "rear_door.delta_t_c",
        },
        "coverage": ["Rear Door HX", "CDU"],
        "status": "connected",
        "latency_ms": 61,
    },
    {
        "id": "nlyte",
        "name": "Nlyte Software",
        "category": "DCIM Platform",
        "products": ["Nlyte DCIM", "Asset Lifecycle", "Capacity Planning"],
        "api": {
            "protocol": "REST",
            "base_url": "https://api.nlyte.local/api/v2",
            "auth": "OAuth2",
            "endpoints": ["/assets", "/capacity", "/power", "/change"],
            "sample_metric": "capacity.rack.available_kw",
        },
        "coverage": ["Asset", "Capacity", "Change Mgmt"],
        "status": "connected",
        "latency_ms": 84,
    },
    {
        "id": "sunbird",
        "name": "Sunbird DCIM",
        "category": "DCIM Platform",
        "products": ["dcTrack", "Power IQ", "Environmental Monitor"],
        "api": {
            "protocol": "REST",
            "base_url": "https://api.sunbirddcim.local/v1",
            "auth": "API Token",
            "endpoints": ["/cabinets", "/sensors", "/circuits", "/reports"],
            "sample_metric": "env.cabinet.temp_c",
        },
        "coverage": ["Cabinet", "Environment", "Power IQ"],
        "status": "idle",
        "latency_ms": 0,
    },
]

POWER_CHAIN = [
    {"stage": "Utility Feed", "vendor": "ABB / Local Utility", "rating": "2N × 120 MVA", "load_pct": 71},
    {"stage": "Substation / Transformer", "vendor": "ABB TXpert", "rating": "2N × 110 MVA", "load_pct": 69},
    {"stage": "MV Switchgear", "vendor": "ABB UniGear / Schneider Premset", "rating": "2N", "load_pct": 68},
    {"stage": "UPS", "vendor": "Schneider Galaxy VL / Eaton 93PM / Vertiv EXL", "rating": "N+1 blocks", "load_pct": 74},
    {"stage": "Busway", "vendor": "Eaton Busway", "rating": "400–800A", "load_pct": 72},
    {"stage": "Rack PDU", "vendor": "APC / Eaton", "rating": "3-phase 63A", "load_pct": 70},
    {"stage": "AI Rack", "vendor": "Vertiv / OEM GPU", "rating": "40–120 kW/rack", "load_pct": 68},
]

COOLING_CHAIN = [
    {"stage": "Plant Chillers", "vendor": "STULZ / Carrier interface", "mode": "Free-cool preferential"},
    {"stage": "CDU Primary Loop", "vendor": "CoolIT CHx / Motivair DynamicCDU", "mode": "Liquid primary"},
    {"stage": "Secondary Manifold", "vendor": "CoolIT AHx", "mode": "Row-level DLC"},
    {"stage": "Cold Plate / Rear Door", "vendor": "CoolIT / Motivair", "mode": "GPU direct contact"},
    {"stage": "Hall CRAH Assist", "vendor": "Vertiv / STULZ", "mode": "Air assist / humidity"},
]

# Append IT fabric vendors at import time from it_fabric
from app.sim.it.vendors_extra import IT_VENDORS_EXTRA  # noqa: E402
from app.sim.cloud.vendors_extra import CLOUD_VENDORS_EXTRA  # noqa: E402

VENDORS = VENDORS + IT_VENDORS_EXTRA + CLOUD_VENDORS_EXTRA
