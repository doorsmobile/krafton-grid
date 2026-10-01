"""Facility physics: 2N power chain and liquid-first N+1 cooling for module M1.

Heat balance drives everything: rack power -> liquid (CDU/TCS) and air (CRAH/CHW)
fractions -> chiller / tower / pump energy -> PUE. Faults injected by scenarios
(CDU pump, chiller trip, UPS fault, utility loss) propagate through that chain.
"""
from __future__ import annotations

import math
import time

import numpy as np

from . import topology as T

LIQUID_CAPTURE = 0.88
FWS_SETPOINT_MAX = 30.0
FWS_SETPOINT_MIN = 26.0
CHW_SETPOINT = 18.0
CDU_APPROACH = 3.0
CP_WATER = 4.18  # kJ/kg·K
UPS_BATTERY_KWH = 500.0
GENSET_START_S = 12.0


def ups_efficiency(load_frac: float) -> float:
    lf = min(max(load_frac, 0.02), 1.0)
    return 0.978 - 0.035 * (1 - lf) ** 4


class Facility:
    def __init__(self, rng: np.random.Generator, now: float):
        self.rng = rng
        self.weather = 0.0
        self.dry_c = 21.0
        self.wet_c = 16.0
        self.rh = 58.0
        self.cdu = {}
        for d in T.COOLING_DEVICES:
            if d["kind"] == "cdu":
                self.cdu[d["id"]] = {
                    "status": "standby" if d.get("spare") else "running", "supply_c": 32.0, "return_c": 40.0,
                    "flow_lpm": 1500.0, "load_mw": 0.0, "load_pct": 0.0, "pump_pct": 62.0, "dp_kpa": 180.0,
                    "leak": False, "covering": None, "failover_at": None,
                }
        self.row_supply = {row: 32.0 for row in T.ROW_CDU}
        self.row_return = {row: 42.0 for row in T.ROW_CDU}
        self.chillers = {f"CH-{i}": {"status": "running" if i <= 2 else "standby", "load_pct": 0.0, "kw": 0.0,
                                     "cop": 8.0, "leaving_c": CHW_SETPOINT, "restart_at": None, "run_h": 4100.0 + i * 713}
                         for i in range(1, 6)}
        self.towers = {f"CT-{i}": {"status": "running" if i <= 4 else "standby", "fan_pct": 40.0} for i in range(1, 7)}
        self.chw_supply = CHW_SETPOINT
        self.chw_return = 25.0
        self.fws_supply = 28.0
        self.fws_return = 37.0
        self.free_cooling_pct = 100.0
        self.ups = {}
        for d in T.POWER_DEVICES:
            if d["kind"] == "ups":
                self.ups[d["id"]] = {"status": "planned" if d.get("planned") else "online", "load_mw": 0.0,
                                     "load_pct": 0.0, "eff": 0.97, "soc": 100.0, "runtime_min": 5.0,
                                     "temp_c": 24.0, "hall": d["hall"], "side": d["side"]}
        self.busway = {d["id"]: {"load_kw": 0.0, "load_pct": 0.0} for d in T.POWER_DEVICES if d["kind"] == "busway"}
        self.gens = {d["id"]: {"status": "standby", "load_mw": 0.0, "fuel_pct": 96.0 - (int(d["id"][-2:]) % 4),
                               "start_at": None, "side": d["side"]} for d in T.POWER_DEVICES if d["kind"] == "generator"}
        self.utility = {"UTIL-1": {"status": "energized", "mw": 0.0, "kv": 154.0},
                        "UTIL-2": {"status": "energized", "mw": 0.0, "kv": 154.0}}
        self.tx = {"TX-A": {"load_mw": 0.0, "load_pct": 0.0, "temp_c": 62.0, "loss_mw": 0.0},
                   "TX-B": {"load_mw": 0.0, "load_pct": 0.0, "temp_c": 62.0, "loss_mw": 0.0}}
        self.crah = {d["id"]: {"supply_c": 24.0, "return_c": 34.0, "fan_pct": 55.0, "hall": d["hall"]}
                     for d in T.COOLING_DEVICES if d["kind"] == "crah"}
        self.hall_inlet = {"HA": 25.0, "HB": 25.0, "HC": 23.5, "HD": 22.0}
        self.snapshot: dict = {}
        self.energy = {"kwh_total_today": 0.0, "kwh_it_today": 0.0, "kwh_total_month": 0.0,
                       "kwh_it_month": 0.0, "water_l_today": 0.0, "co2_t_today": 0.0, "peak_kw_month": 0.0}
        self.day_key = None
        self.month_key = None

    # ---------------------------------------------------------------- ambient
    def _ambient(self, now: float, heat_delta: float) -> None:
        hour = ((now / 3600.0) + 9) % 24
        self.weather += (-self.weather * 0.002) + self.rng.normal(0, 0.02)
        self.dry_c = 21.3 + 4.6 * math.sin((hour - 9.0) / 24 * 2 * math.pi) + self.weather + heat_delta
        dep = 4.2 + 1.6 * math.sin((hour - 9.0) / 24 * 2 * math.pi)
        self.wet_c = self.dry_c - dep + heat_delta * -0.3
        if heat_delta > 0:  # tropical night: wet bulb stays high even after dark
            self.dry_c = max(self.dry_c, 33.5)
            self.wet_c = max(self.wet_c, 27.0)
        self.rh = max(25.0, min(95.0, 100 - 5.2 * dep - 8))

    # ------------------------------------------------------------------ step
    def step(self, now: float, dt: float, rack_kw: dict[str, float], hallc_kw: float, faults: set[str],
             maint: set[str], heat_delta: float, rate_krw_kwh: float) -> dict:
        rng = self.rng
        self._ambient(now, heat_delta)

        # ---- heat by row / hall
        row_kw = {row: 0.0 for row in T.ROW_CDU}
        hall_it = {"HA": 0.0, "HB": 0.0, "HC": hallc_kw, "HD": 0.0}
        for rk in T.GPU_RACK_LIST:
            kw = rack_kw.get(rk.id, 0.0)
            row_kw[rk.row] += kw
            hall_it[rk.hall] += kw
        it_kw = sum(hall_it.values())
        liquid_kw = sum(row_kw.values()) * LIQUID_CAPTURE
        air_kw = sum(row_kw.values()) * (1 - LIQUID_CAPTURE) + hallc_kw * 0.97

        # ---- FWS (warm water) loop: free cooling unless the wet bulb is too high
        achievable = self.wet_c + 4.0 + 1.5
        self.fws_supply += (min(FWS_SETPOINT_MAX, max(FWS_SETPOINT_MIN, achievable)) - self.fws_supply) * 0.1
        trim_frac = min(1.0, max(0.0, (achievable - FWS_SETPOINT_MAX) / 6.0))
        self.free_cooling_pct = round(100 * (1 - trim_frac), 1)

        # ---- CDUs, spare failover
        for hall in ("HA", "HB"):
            spare_id = f"CDU-{hall[1]}S"
            spare = self.cdu[spare_id]
            rows = [r for r in T.ROW_CDU if r.startswith(hall[1])]
            failed_rows = [r for r in rows if T.ROW_CDU[r] in faults]
            for r in rows:
                c = self.cdu[T.ROW_CDU[r]]
                if T.ROW_CDU[r] in faults and c["status"] != "failed":
                    c["status"] = "failed"
                    c["failover_at"] = now + 24.0
                elif T.ROW_CDU[r] not in faults and c["status"] == "failed":
                    c["status"] = "running"
                    c["failover_at"] = None
            covering = spare["covering"]
            if covering and covering not in failed_rows:
                spare["covering"], spare["status"] = None, "standby"
            if not spare["covering"] and spare_id not in faults:
                for r in failed_rows:
                    c = self.cdu[T.ROW_CDU[r]]
                    if c["failover_at"] and now >= c["failover_at"]:
                        spare["covering"], spare["status"] = r, "running"
                        break
            if spare_id in faults:
                spare["status"], spare["covering"] = "failed", None
            elif spare["status"] == "failed":
                spare["status"] = "standby"

        for r in T.ROW_CDU:
            cid = T.ROW_CDU[r]
            c = self.cdu[cid]
            heat = row_kw[r] * LIQUID_CAPTURE
            spare = self.cdu[f"CDU-{r[0]}S"]
            if c["status"] == "failed":
                if spare["covering"] == r:
                    target = self.fws_supply + CDU_APPROACH + 7.5 + 4.0 * max(0.0, heat / 1350 - 0.7)
                    flow = 1350.0
                    spare.update(load_mw=round(heat / 1000, 3), load_pct=round(heat / 1350 * 100, 1),
                                 supply_c=round(target, 1), flow_lpm=flow, pump_pct=96.0, dp_kpa=265.0)
                else:
                    target, flow = 63.0 + 8.0 * heat / 1350, 220.0
                c.update(load_mw=0.0, load_pct=0.0, flow_lpm=flow if spare["covering"] != r else 0.0, pump_pct=0.0, dp_kpa=12.0)
            else:
                target = self.fws_supply + CDU_APPROACH * (0.6 + 0.4 * heat / 1350)
                flow = 900 + 1000 * min(1.0, heat / 1350)
                c.update(load_mw=round(heat / 1000, 3), load_pct=round(heat / 1350 * 100, 1),
                         flow_lpm=round(flow + rng.normal(0, 6), 0), pump_pct=round(45 + 50 * heat / 1350, 1),
                         dp_kpa=round(150 + 110 * heat / 1350 + rng.normal(0, 2), 0))
            self.row_supply[r] += (target - self.row_supply[r]) * (0.12 if c["status"] == "failed" else 0.3)
            kg_s = max(flow, 150.0) / 60.0
            self.row_return[r] = self.row_supply[r] + heat / (kg_s * CP_WATER)
            if c["status"] != "failed":
                c["supply_c"] = round(self.row_supply[r], 1)
                c["return_c"] = round(self.row_return[r], 1)
            else:
                c["supply_c"] = round(self.row_supply[r], 1)
                c["return_c"] = round(self.row_return[r], 1)
            c["leak"] = f"LEAK-{cid}" in faults
        for hall in ("HA", "HB"):
            spare = self.cdu[f"CDU-{hall[1]}S"]
            if not spare["covering"]:
                spare.update(load_mw=0.0, load_pct=0.0, flow_lpm=0.0, pump_pct=0.0, dp_kpa=0.0,
                             supply_c=round(self.fws_supply + CDU_APPROACH, 1), return_c=round(self.fws_supply + CDU_APPROACH, 1))
        fws_heat = liquid_kw
        self.fws_return = self.fws_supply + 9.0 * min(1.2, fws_heat / 9000.0) + 1.0

        # ---- chiller plant (air side + trim)
        chw_load = air_kw + trim_frac * fws_heat + 0.0
        for cid, ch in self.chillers.items():
            if cid in faults and ch["status"] == "running":
                ch["status"] = "tripped"
            elif cid in maint:
                ch["status"] = "maintenance"
            elif cid not in faults and ch["status"] in ("tripped", "maintenance"):
                ch["status"] = "standby"
        running = [c for c, ch in self.chillers.items() if ch["status"] in ("running", "starting")]
        needed = max(2, math.ceil(chw_load / (4900 * 0.8)))
        if len(running) < needed:
            for cid, ch in self.chillers.items():
                if ch["status"] == "standby":
                    ch["status"] = "starting"
                    ch["restart_at"] = now + 90.0
                    running.append(cid)
                    if len(running) >= needed:
                        break
        for cid, ch in self.chillers.items():
            if ch["status"] == "starting" and ch["restart_at"] and now >= ch["restart_at"]:
                ch["status"], ch["restart_at"] = "running", None
        online = [c for c, ch in self.chillers.items() if ch["status"] == "running"]
        cap = len(online) * 4900.0
        deficit = max(0.0, chw_load - cap * 0.98)
        starting = any(ch["status"] == "starting" for ch in self.chillers.values())
        excursion = (deficit / 900.0) + (1.6 if starting and len(online) < needed else 0.0)
        self.chw_supply += (CHW_SETPOINT + excursion - self.chw_supply) * 0.15
        pl = chw_load / cap if cap else 1.0
        self.chw_return = self.chw_supply + 5.5 + 3.0 * min(1.0, pl)
        chiller_kw = 0.0
        for cid, ch in self.chillers.items():
            if ch["status"] == "running" and online:
                share = chw_load / len(online)
                cop = max(3.5, min(10.0, 8.4 - 0.17 * (self.wet_c - 14) - 1.4 * abs(share / 4900 - 0.55)))
                ch.update(load_pct=round(share / 4900 * 100, 1), cop=round(cop, 2), kw=round(share / cop, 1),
                          leaving_c=round(self.chw_supply, 1))
                ch["run_h"] += dt / 3600
                chiller_kw += share / cop
            else:
                ch.update(load_pct=0.0, kw=0.0, leaving_c=round(self.chw_return, 1))

        rejected = fws_heat * (1 - trim_frac) + chw_load + chiller_kw
        tower_kw = 0.0092 * rejected * (1 + 0.045 * max(0.0, self.wet_c - 16))
        n_towers = max(2, min(6, math.ceil(rejected / 3200)))
        for i, (tid, tw) in enumerate(self.towers.items()):
            tw["status"] = "running" if i < n_towers else "standby"
            tw["fan_pct"] = round(min(100.0, 25 + 60 * rejected / (n_towers * 4200)), 1) if i < n_towers else 0.0
        pump_kw = 0.012 * liquid_kw + 0.008 * fws_heat + 0.015 * chw_load + 0.010 * rejected
        crah_kw = 0.035 * air_kw
        for cid, cr in self.crah.items():
            hall_air = (sum(row_kw[r] for r in T.ROW_CDU if r.startswith(cid[5])) * (1 - LIQUID_CAPTURE)
                        if cid[5] in "AB" else hallc_kw * 0.97)
            n = 4 if cid[5] in "AB" else 8
            cr["supply_c"] = round(self.chw_supply + 5.5 + rng.normal(0, 0.1), 1)
            cr["return_c"] = round(cr["supply_c"] + 9.0 + 3.0 * min(1.0, hall_air / n / 450), 1)
            cr["fan_pct"] = round(min(100, 35 + 55 * hall_air / n / 500), 1)
        for hall in ("HA", "HB", "HC"):
            supply = np.mean([cr["supply_c"] for cr in self.crah.values() if cr["hall"] == hall])
            self.hall_inlet[hall] = round(float(supply) + 0.8 + rng.normal(0, 0.08), 1)
        mech_kw = chiller_kw + tower_kw + pump_kw + crah_kw
        cdu_pump_kw = 0.012 * liquid_kw

        # ---- power chain
        util_live = {u: (u not in faults) for u in self.utility}
        side_live = {"A": util_live["UTIL-1"], "B": util_live["UTIL-2"]}
        for side, live in side_live.items():
            for gid, g in self.gens.items():
                if g["side"] != side:
                    continue
                if not live and g["status"] == "standby":
                    g["status"], g["start_at"] = "starting", now + GENSET_START_S
                elif not live and g["status"] == "cooldown":
                    g["status"], g["start_at"] = "running", None
                if g["status"] == "starting" and g["start_at"] and now >= g["start_at"]:
                    g["status"] = "running"
                if live and g["status"] in ("running", "starting"):
                    g["status"], g["start_at"] = "cooldown", now + 300
                if g["status"] == "cooldown" and g["start_at"] and now >= g["start_at"]:
                    g["status"], g["start_at"] = "standby", None
        gen_on = {s: any(g["status"] == "running" and g["side"] == s for g in self.gens.values()) for s in "AB"}
        source_ok = {s: side_live[s] or gen_on[s] for s in "AB"}

        ups_loss = 0.0
        side_load = {"A": 0.0, "B": 0.0}
        for hall in ("HA", "HB", "HC"):
            a, b = self.ups[f"UPS-A-{hall}"], self.ups[f"UPS-B-{hall}"]
            a_ok = f"UPS-A-{hall}" not in faults
            b_ok = f"UPS-B-{hall}" not in faults
            crit = hall_it[hall] + (cdu_pump_kw * hall_it[hall] / max(1.0, hall_it["HA"] + hall_it["HB"]) if hall != "HC" else 0.0)
            share_a = 0.5 if (a_ok and b_ok) else (1.0 if a_ok else 0.0)
            for u, ok, share, side in ((a, a_ok, share_a, "A"), (b, b_ok, 1 - share_a, "B")):
                load = crit * share
                lf = load / 6000.0
                if not ok:
                    u.update(status="fault", load_mw=0.0, load_pct=0.0, eff=0.0)
                    continue
                eff = ups_efficiency(lf)
                on_batt = not source_ok[side] or (not side_live[side] and not gen_on[side])
                if on_batt:
                    u["soc"] = max(0.0, u["soc"] - (load * dt / 3600.0) / UPS_BATTERY_KWH * 100)
                    u["status"] = "on-battery"
                else:
                    u["soc"] = min(100.0, u["soc"] + 0.25 * dt)
                    u["status"] = "online" if side_live[side] else "online · genset"
                u.update(load_mw=round(load / 1000, 3), load_pct=round(lf * 100, 1), eff=round(eff * 100, 2),
                         runtime_min=round((UPS_BATTERY_KWH * u["soc"] / 100) / max(load, 1) * 60, 1),
                         temp_c=round(24 + 3 * lf + rng.normal(0, 0.1), 1))
                loss = load / eff - load
                ups_loss += loss
                side_load[side] += load + loss
        for d in T.POWER_DEVICES:
            if d["kind"] != "busway":
                continue
            row = d["row"]
            if row in T.ROW_CDU:
                row_it = row_kw[row]
            else:
                row_it = hallc_kw / 4
            a_ok = f"UPS-A-{d['hall']}" not in faults
            b_ok = f"UPS-B-{d['hall']}" not in faults
            share = 0.5 if (a_ok and b_ok) else (1.0 if (d["side"] == "A") == a_ok else 0.0)
            kw = row_it * share
            self.busway[d["id"]] = {"load_kw": round(kw, 1), "load_pct": round(kw / (d["rating_mw"] * 1000) * 100, 1)}

        misc_kw = 180.0 + 0.008 * it_kw
        non_ups = mech_kw - cdu_pump_kw + misc_kw
        side_load["A"] += non_ups / 2
        side_load["B"] += non_ups / 2
        tx_loss = 0.0
        for side, txid in (("A", "TX-A"), ("B", "TX-B")):
            load = side_load[side]
            loss = 20.0 + 0.004 * load
            tx_loss += loss
            self.tx[txid].update(load_mw=round((load + loss) / 1000, 3), load_pct=round((load + loss) / 36000 * 100, 1),
                                 temp_c=round(55 + 25 * (load / 36000) + self.dry_c * 0.3, 1), loss_mw=round(loss / 1000, 3))
        for side, uid in (("A", "UTIL-1"), ("B", "UTIL-2")):
            u = self.utility[uid]
            if side_live[side]:
                u.update(status="energized", mw=round((side_load[side] + 20 + 0.004 * side_load[side]) / 1000, 3),
                         kv=round(154.0 + rng.normal(0, 0.25), 2))
            else:
                u.update(status="lost", mw=0.0, kv=0.0)
                running = [g for g in self.gens.values() if g["side"] == side and g["status"] == "running"]
                for g in running:
                    g["load_mw"] = round(side_load[side] / 1000 / len(running), 3)
                    g["fuel_pct"] = max(0.0, g["fuel_pct"] - dt * 0.0009 * g["load_mw"])
        for g in self.gens.values():
            if g["status"] != "running":
                g["load_mw"] = 0.0

        facility_kw = it_kw + ups_loss + tx_loss + mech_kw + misc_kw
        pue = facility_kw / it_kw if it_kw else 0.0
        evap_frac = min(1.0, max(0.15, (self.dry_c - 18) / 12))
        water_lph = rejected * 2.0 * evap_frac
        wue = water_lph / it_kw if it_kw else 0.0
        grid_factor = 0.4594  # tCO2 / MWh, Korea national grid
        co2_tph = facility_kw / 1000 * grid_factor
        cue = co2_tph * 1000 / it_kw if it_kw else 0.0

        # ---- energy counters (reset on KST day/month change)
        kst = time.gmtime(now + 9 * 3600)
        day, month = (kst.tm_year, kst.tm_yday), (kst.tm_year, kst.tm_mon)
        if self.day_key is None:
            self.day_key, self.month_key = day, month
        if day != self.day_key:
            self.energy.update(kwh_total_today=0.0, kwh_it_today=0.0, water_l_today=0.0, co2_t_today=0.0)
            self.day_key = day
        if month != self.month_key:
            self.energy.update(kwh_total_month=0.0, kwh_it_month=0.0, peak_kw_month=0.0)
            self.month_key = month
        h = dt / 3600.0
        self.energy["kwh_total_today"] += facility_kw * h
        self.energy["kwh_it_today"] += it_kw * h
        self.energy["kwh_total_month"] += facility_kw * h
        self.energy["kwh_it_month"] += it_kw * h
        self.energy["water_l_today"] += water_lph * h
        self.energy["co2_t_today"] += co2_tph * h
        self.energy["peak_kw_month"] = max(self.energy["peak_kw_month"], facility_kw)

        redundancy = "2N"
        for hall in ("HA", "HB", "HC"):
            if self.ups[f"UPS-A-{hall}"]["status"] == "fault" or self.ups[f"UPS-B-{hall}"]["status"] == "fault":
                redundancy = "N (degraded)"
        if not all(side_live.values()):
            redundancy = "N (utility loss)"
        cooling_red = "N+1"
        standby_ok = sum(1 for ch in self.chillers.values() if ch["status"] == "standby")
        if standby_ok == 0 or any(c["status"] == "failed" for c in self.cdu.values()):
            cooling_red = "N (degraded)"

        halls = {}
        for h_ in T.HALLS:
            hid = h_["id"]
            halls[hid] = {"id": hid, "name": h_["name"], "purpose": h_["purpose"], "design_mw": h_["design_mw"],
                          "it_mw": round(hall_it[hid] / 1000, 3),
                          "util_pct": round(hall_it[hid] / (h_["design_mw"] * 1000) * 100, 1),
                          "inlet_c": self.hall_inlet[hid], "rh_pct": round(45 + rng.normal(0, 0.4), 1)}

        self.snapshot = {
            "ambient": {"dry_c": round(self.dry_c, 1), "wet_c": round(self.wet_c, 1), "rh_pct": round(self.rh, 0),
                        "heatwave": heat_delta > 0},
            "it_mw": round(it_kw / 1000, 3), "facility_mw": round(facility_kw / 1000, 3),
            "capacity_mw": T.MODULE_MW, "util_pct": round(it_kw / (T.MODULE_MW * 1000) * 100, 1),
            "pue": round(pue, 3), "wue": round(wue, 3), "cue": round(cue, 3),
            "breakdown_mw": {"it": round(it_kw / 1000, 3), "ups_loss": round(ups_loss / 1000, 3),
                             "tx_loss": round(tx_loss / 1000, 3), "chillers": round(chiller_kw / 1000, 3),
                             "towers": round(tower_kw / 1000, 3), "pumps": round(pump_kw / 1000, 3),
                             "crah": round(crah_kw / 1000, 3), "misc": round(misc_kw / 1000, 3)},
            "heat_mw": {"liquid": round(liquid_kw / 1000, 3), "air": round(air_kw / 1000, 3),
                        "rejected": round(rejected / 1000, 3)},
            "power": {
                "redundancy": redundancy,
                "utility": self.utility, "tx": self.tx, "ups": self.ups, "gens": self.gens,
                "side_mw": {"A": round(side_load["A"] / 1000, 3), "B": round(side_load["B"] / 1000, 3)},
                "busway": self.busway,
                "pq": {"freq_hz": round(60 + rng.normal(0, 0.01), 3), "pf": round(0.985 + rng.normal(0, 0.002), 3),
                       "thd_pct": round(2.3 + rng.normal(0, 0.1), 2), "mv_kv": round(22.9 + rng.normal(0, 0.05), 2)},
            },
            "cooling": {
                "redundancy": cooling_red, "chw_supply_c": round(self.chw_supply, 2),
                "chw_return_c": round(self.chw_return, 2), "fws_supply_c": round(self.fws_supply, 2),
                "fws_return_c": round(self.fws_return, 2), "free_cooling_pct": self.free_cooling_pct,
                "tcs_supply_avg_c": round(float(np.mean(list(self.row_supply.values()))), 2),
                "tcs_supply_max_c": round(float(max(self.row_supply.values())), 2),
                "chillers_running": sum(1 for ch in self.chillers.values() if ch["status"] == "running"),
                "chiller_load_mw": round(chw_load / 1000, 3), "cooling_kw": round(mech_kw, 1),
                "water_lph": round(water_lph, 0), "chillers": self.chillers, "towers": self.towers,
                "cdus": self.cdu, "crah": self.crah,
                "row_supply_c": {r: round(v, 2) for r, v in self.row_supply.items()},
                "row_return_c": {r: round(v, 2) for r, v in self.row_return.items()},
            },
            "halls": halls,
            "energy": {k: round(v, 1) for k, v in self.energy.items()},
            "rate_krw_kwh": rate_krw_kwh,
        }
        return self.snapshot
