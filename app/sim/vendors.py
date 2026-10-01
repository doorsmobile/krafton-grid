"""Vendor / integration catalog with sample probes shaped like each real API."""
from __future__ import annotations

import time
import zlib

from . import topology as T

VENDORS = [
    # ------------------------------------------------------------ facility
    {"id": "kepco", "name": "KEPCO", "group": "Facility", "domain": "Utility", "product": "154 kV dual feed · 산업용(을) 고압C",
     "protocol": "KEPCO i-Smart open data API", "endpoint": "GET /openapi/v1/usage/interval?meterNo=…&unit=15m"},
    {"id": "hd-hyundai", "name": "HD Hyundai Electric", "group": "Facility", "domain": "Transformers", "product": "Main TR A/B · 40 MVA",
     "protocol": "IEC 61850 MMS via gateway", "endpoint": "MMS read TX_A/LLN0$MX"},
    {"id": "ls-electric", "name": "LS Electric", "group": "Facility", "domain": "MV switchgear", "product": "22.9 kV GIS A/B",
     "protocol": "Modbus TCP", "endpoint": "FC03 read holding registers 40001–40120"},
    {"id": "vertiv-ups", "name": "Vertiv", "group": "Facility", "domain": "UPS", "product": "Liebert EXL S1 · 4×1.5 MW per path",
     "protocol": "SNMP v3 · Vertiv Unify REST", "endpoint": "GET /api/v1/devices/{ups}/datapoints"},
    {"id": "vertiv-cdu", "name": "Vertiv", "group": "Facility", "domain": "CDU (liquid)", "product": "CoolChip CDU 1350 · L2L",
     "protocol": "Modbus TCP · Redfish (DMTF CDU schema)", "endpoint": "GET /redfish/v1/ThermalEquipment/CDUs/{id}"},
    {"id": "schneider", "name": "Schneider Electric", "group": "Facility", "domain": "Busway / PDU", "product": "I-Line busway · EcoStruxure IT",
     "protocol": "EcoStruxure IT Expert REST", "endpoint": "GET /api/v2/assets/{busway}/metrics"},
    {"id": "trane", "name": "Trane", "group": "Facility", "domain": "Chillers", "product": "CVHS magnetic-bearing · 1,400 RT ×5",
     "protocol": "BACnet/IP via Tracer SC+", "endpoint": "ReadPropertyMultiple analog-value:1..24"},
    {"id": "bac", "name": "BAC", "group": "Facility", "domain": "Cooling towers", "product": "Series 3000 ×6",
     "protocol": "BACnet/IP", "endpoint": "ReadProperty analog-input:fan-speed"},
    {"id": "stulz", "name": "STULZ", "group": "Facility", "domain": "CRAH", "product": "CyberAir fan walls ×16",
     "protocol": "Modbus RTU/TCP", "endpoint": "FC04 input registers 30001–30060"},
    {"id": "cummins", "name": "Cummins", "group": "Facility", "domain": "Gensets", "product": "QSK95 3.0 MW ×10",
     "protocol": "PowerCommand Cloud API", "endpoint": "GET /v1/gensets/{id}/status"},
    # ------------------------------------------------------------------ IT
    {"id": "nvidia-dcgm", "name": "NVIDIA", "group": "IT", "domain": "GPU", "product": "B300 × 5,000 · HGX 8-GPU × 625",
     "protocol": "DCGM exporter (Prometheus) · NVML", "endpoint": "GET :9400/metrics"},
    {"id": "nvidia-ufm", "name": "NVIDIA", "group": "IT", "domain": "InfiniBand", "product": "Quantum-2 QM9700 × 16",
     "protocol": "UFM Enterprise REST", "endpoint": "GET /ufmRest/resources/ports?system={guid}"},
    {"id": "arista", "name": "Arista", "group": "IT", "domain": "Ethernet", "product": "7800R3 × 8 spine · 7060X6 × 48 leaf",
     "protocol": "eAPI JSON-RPC · CloudVision gNMI", "endpoint": "POST /command-api runCmds['show interfaces counters rates']"},
    {"id": "ibm-scale", "name": "IBM", "group": "IT", "domain": "Storage", "product": "IBM Storage Scale System 6000 · 100 PB",
     "protocol": "Scale Management API v2", "endpoint": "GET /scalemgmt/v2/filesystems/{fs}/perfmon"},
    {"id": "dell-redfish", "name": "Dell", "group": "IT", "domain": "K8s hosts", "product": "PowerEdge XE9680 × 30",
     "protocol": "iDRAC9 Redfish", "endpoint": "GET /redfish/v1/Systems/System.Embedded.1"},
    {"id": "slurm", "name": "SchedMD Slurm", "group": "IT", "domain": "Scheduler", "product": "Slurm 25.05 · slurmrestd",
     "protocol": "slurmrestd OpenAPI", "endpoint": "GET /slurm/v0.0.42/jobs"},
    {"id": "kubernetes", "name": "Kubernetes", "group": "IT", "domain": "Orchestration", "product": "v1.34 · 3 CP + 27 workers",
     "protocol": "Kubernetes API", "endpoint": "GET /api/v1/nodes"},
    # ------------------------------------------------ cloud: AWS → GCP → NHN
    {"id": "aws", "name": "AWS", "group": "Cloud", "domain": "GPUaaS", "product": "EC2 p5en / p6-b200 · Capacity Blocks",
     "protocol": "EC2 Query API · CloudWatch", "endpoint": "POST ec2.ap-northeast-2 Action=DescribeInstances"},
    {"id": "gcp", "name": "Google Cloud", "group": "Cloud", "domain": "Storage", "product": "Cloud Storage + Persistent Disk",
     "protocol": "GCS JSON API v1 · Compute API", "endpoint": "GET storage/v1/b?project=krafton-grid"},
    {"id": "nhn", "name": "NHN Cloud", "group": "Cloud", "domain": "GPUaaS", "product": "GPU instances · KR1",
     "protocol": "NHN Cloud Compute API (OpenStack-compatible)", "endpoint": "GET /v2/{tenantId}/servers/detail"},
]
VENDOR_BY_ID = {v["id"]: v for v in VENDORS}


def health(vid: str, now: float, faults: set[str]) -> dict:
    h = zlib.crc32(vid.encode())
    lat = 8 + (h % 70) + (int(now) % 7)
    degraded = (vid == "nvidia-ufm" and any(f.startswith("ib-") for f in faults)) or \
               (vid == "vertiv-cdu" and any(f.startswith("CDU-") or f.startswith("LEAK") for f in faults)) or \
               (vid == "vertiv-ups" and any(f.startswith("UPS-") for f in faults))
    return {"status": "degraded" if degraded else "ok", "latency_ms": lat, "last_poll": now - (h % 9),
            "poll_s": 10 if VENDOR_BY_ID[vid]["group"] != "Cloud" else 60}


def sample(vid: str, eng) -> dict:
    now = time.time()
    f = eng.facility.snapshot
    fl = eng.fleet
    if vid == "kepco":
        return {"meterNo": "154-KG-0001", "interval": "15m", "data": [
            {"ts": time.strftime("%Y-%m-%dT%H:%M:00+09:00", time.gmtime(now + 9 * 3600 - k * 900)),
             "kw": round(f["facility_mw"] * 1000 * (1 - k * 0.002), 1), "pf": f["power"]["pq"]["pf"]} for k in range(4)]}
    if vid == "hd-hyundai":
        return {"logicalNode": "TX_A/LLN0", "MX": {"TotW": f["power"]["tx"]["TX-A"]["load_mw"] * 1e6,
                                                  "OilTmp": f["power"]["tx"]["TX-A"]["temp_c"], "TapPos": 9}}
    if vid == "ls-electric":
        return {"unit": 1, "registers": {"40001_kv_ab": f["power"]["pq"]["mv_kv"], "40003_freq": f["power"]["pq"]["freq_hz"],
                                         "40011_mw_total": round(f["power"]["side_mw"]["A"], 3), "40021_breaker": "CLOSED"}}
    if vid == "vertiv-ups":
        u = f["power"]["ups"]["UPS-A-HA"]
        return {"device": "UPS-A-HA", "datapoints": [
            {"name": "outputLoadPercent", "value": u["load_pct"]}, {"name": "efficiency", "value": u["eff"]},
            {"name": "batteryStateOfCharge", "value": round(u["soc"], 1)}, {"name": "operatingMode", "value": u["status"]},
            {"name": "estimatedRuntimeMin", "value": u["runtime_min"]}]}
    if vid == "vertiv-cdu":
        c = f["cooling"]["cdus"]["CDU-A1"]
        return {"@odata.id": "/redfish/v1/ThermalEquipment/CDUs/CDU-A1", "Status": {"Health": "OK", "State": "Enabled"},
                "PrimaryCoolantConnectors": {"SupplyTemperatureCelsius": f["cooling"]["fws_supply_c"]},
                "SecondaryCoolantConnectors": {"SupplyTemperatureCelsius": c["supply_c"], "ReturnTemperatureCelsius": c["return_c"],
                                               "FlowLitersPerMinute": c["flow_lpm"], "DeltaPressurekPa": c["dp_kpa"]},
                "Pumps": [{"Id": "1", "PumpSpeedPercent": c["pump_pct"]}], "LeakDetection": {"Detected": c["leak"]}}
    if vid == "schneider":
        b = f["power"]["busway"]["BW-A1-A"]
        return {"asset": "BW-A1-A", "metrics": {"activePowerKw": b["load_kw"], "loadPercent": b["load_pct"],
                                               "voltageLL": 415.0, "currentA": round(b["load_kw"] * 1000 / (1.732 * 415 * 0.99), 1)}}
    if vid == "trane":
        ch = f["cooling"]["chillers"]["CH-1"]
        return {"device": "CH-1", "objects": {"analog-value:1 ChwLvgTemp": ch["leaving_c"], "analog-value:3 PctRla": ch["load_pct"],
                                             "analog-value:7 kW": ch["kw"], "analog-value:9 COP": ch["cop"],
                                             "binary-value:1 Running": ch["status"] == "running", "multistate:2 Mode": ch["status"]}}
    if vid == "bac":
        return {"towers": {k: v for k, v in f["cooling"]["towers"].items()}, "wet_bulb_c": f["ambient"]["wet_c"]}
    if vid == "stulz":
        cr = f["cooling"]["crah"]["CRAH-C1"]
        return {"unit": "CRAH-C1", "30001_supply_air_c": cr["supply_c"], "30002_return_air_c": cr["return_c"], "30010_fan_pct": cr["fan_pct"]}
    if vid == "cummins":
        g = f["power"]["gens"]["GEN-01"]
        return {"id": "GEN-01", "state": g["status"], "loadMw": g["load_mw"], "fuelLevelPct": round(g["fuel_pct"], 1),
                "engineHours": 412.6, "batteryVolts": 26.8, "lastTest": "2026-09-14T10:00:00+09:00"}
    if vid == "nvidia-dcgm":
        lines = []
        for gi in range(0, 16, 1):
            node = T.NODE_IDS[gi // 8]
            lab = f'gpu="{gi % 8}",Hostname="{node}",modelName="NVIDIA B300"'
            lines += [f"DCGM_FI_DEV_GPU_UTIL{{{lab}}} {fl.util[gi]:.0f}", f"DCGM_FI_DEV_GPU_TEMP{{{lab}}} {fl.temp[gi]:.0f}",
                      f"DCGM_FI_DEV_POWER_USAGE{{{lab}}} {fl.power[gi]:.1f}", f"DCGM_FI_PROF_SM_ACTIVE{{{lab}}} {fl.sm[gi] / 100:.3f}"]
        return {"content_type": "text/plain; version=0.0.4", "body": "\n".join(lines)}
    if vid == "nvidia-ufm":
        d = eng.network.dev["ib-leaf-01"]
        return [{"name": f"ib-leaf-01/{p}", "logical_state": "Active" if p > d["links_down"] else "Down",
                 "active_speed": "NDR", "active_width": "4x", "symbol_errors": d["errors"] // 64,
                 "port_xmit_wait": int(d["util_pct"] * 1200), "tx_bytes_rate": d["out_gbps"] * 1e9 / 8 / 64} for p in range(1, 5)]
    if vid == "arista":
        d = eng.network.dev["eth-leaf-01"]
        return {"jsonrpc": "2.0", "id": "grid", "result": [{"interfaces": {
            f"Ethernet{p}/1": {"inBpsRate": d["in_gbps"] * 1e9 / 64, "outBpsRate": d["out_gbps"] * 1e9 / 64,
                               "inPktsRate": d["in_gbps"] * 1e9 / 64 / 8 / 4000, "interval": 300} for p in range(1, 4)}}]}
    if vid == "ibm-scale":
        c = eng.storage.clusters["ss-hot"]
        return {"filesystem": "hot", "perfmon": {"gpfs_fs_bytes_read": c["read_gbs"] * 1e9, "gpfs_fs_bytes_written": c["write_gbs"] * 1e9,
                                                "gpfs_fs_tot_disk_wait_rd": c["latency_ms"], "gpfs_fs_read_ops": c["iops_k"] * 700},
                "status": {"code": 200, "message": "The request finished successfully."}}
    if vid == "dell-redfish":
        n = eng.k8s.nodes["k8s-w-01"]
        return {"@odata.id": "/redfish/v1/Systems/System.Embedded.1", "Model": "PowerEdge XE9680", "PowerState": "On",
                "Status": {"Health": "OK" if n["status"] == "Ready" else "Warning"}, "ProcessorSummary": {"Count": 2, "LogicalProcessorCount": 224},
                "MemorySummary": {"TotalSystemMemoryGiB": 2048}, "Oem": {"Dell": {"CPUUtilPct": n["cpu_pct"]}}}
    if vid == "slurm":
        jobs = [j.public(now) for j in list(fl.jobs.values())[:3]]
        return {"meta": {"plugin": {"type": "openapi/slurmctld", "name": "Slurm OpenAPI slurmctld", "data_parser": "data_parser/v0.0.42"}},
                "jobs": [{"job_id": int(j["id"]), "name": j["name"], "account": j["project"], "partition": j["partition"],
                          "job_state": [j["state"]], "user_name": j["user"], "node_count": {"number": j["nodes"]},
                          "tres_req_str": f"gres/gpu={j['gpus']}"} for j in jobs]}
    if vid == "kubernetes":
        return {"kind": "NodeList", "apiVersion": "v1", "items": [
            {"metadata": {"name": k}, "status": {"conditions": [{"type": "Ready", "status": "True" if v["status"] == "Ready" else "Unknown"}],
                                                 "nodeInfo": {"kubeletVersion": v["kubelet"]}}} for k, v in list(eng.k8s.nodes.items())[:3]]}
    if vid == "aws":
        insts = eng.cloud.aws_instances[:3]
        return {"Reservations": [{"Instances": [{"InstanceId": i["id"], "InstanceType": i["type"], "State": {"Name": i["state"]},
                                                 "Placement": {"AvailabilityZone": i["az"]},
                                                 "CapacityReservationId": i["capacity_block"],
                                                 "InstanceLifecycle": "capacity-block" if i["capacity_block"] else "on-demand",
                                                 "Tags": [{"Key": "Name", "Value": i["name"]}, {"Key": "project", "Value": i["project"]}]}
                                                for i in insts]}]}
    if vid == "gcp":
        return {"kind": "storage#buckets", "items": [{"kind": "storage#bucket", "name": b["name"], "location": b["location"].upper(),
                                                      "storageClass": b["class"], "sizeBytes": int(b["size_tb"] * 1e12)}
                                                     for b in eng.cloud.buckets[:3]]}
    if vid == "nhn":
        return {"servers": [{"id": n["id"], "name": n["name"], "status": n["status"], "flavor": {"original_name": n["flavor"]},
                             "OS-EXT-AZ:availability_zone": n["zone"]} for n in eng.cloud.nhn[:3]]}
    return {}
