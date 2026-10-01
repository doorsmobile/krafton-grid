"""Cost views: Summary · DC · Cloud · Budget."""
from __future__ import annotations

from ..sim import cost as C


def _rows(eng) -> list[dict]:
    return eng.monthly()


def summary(eng) -> dict:
    rows = _rows(eng)
    s = eng.cost.summary(eng.now, rows, eng.gpu_hours_month())
    cur = rows[-1]
    last_full = rows[-2]
    return {"summary": s, "months": rows, "current": cur, "last_full": last_full,
            "mix": [{"name": "DC", "y": cur["dc_total"]}, {"name": "Cloud", "y": cur["cloud_total"]}],
            "mix_last": [{"name": "DC", "y": last_full["dc_total"]}, {"name": "Cloud", "y": last_full["cloud_total"]}],
            "live": {"today_power_krw": round(eng.cost.today_power_krw), "cloud_hr_krw": eng.live["cloud"]["total_cost_hr_krw"],
                     "today_cloud_krw": round(sum(eng.cloud.cost_today_krw.values()))}}


def dc(eng) -> dict:
    rows = _rows(eng)
    cur, last = rows[-1], rows[-2]
    fs = eng.facility.snapshot
    tou = [{"band": b, "ko": {"off": "경부하", "mid": "중간부하", "peak": "최대부하"}[b], "rates": {k: v[b] for k, v in C.TOU_RATES.items()}}
           for b in ("off", "mid", "peak")]
    return {"months": rows, "current": cur, "last_full": last, "lines": [{"id": i, "ko": ko, "en": en} for i, ko, en in C.DC_LINES],
            "live": {"facility_mw": fs["facility_mw"], "rate": eng.cost.current_rate(), "today_power_krw": round(eng.cost.today_power_krw),
                     "kwh_today": fs["energy"]["kwh_total_today"], "kwh_month": fs["energy"]["kwh_total_month"],
                     "peak_kw_month": fs["energy"]["peak_kw_month"], "burn_hr_krw": round(fs["facility_mw"] * 1000 * eng.cost.rate
                                                                                            * (1 + C.FUND_RATE) * (1 + C.VAT))},
            "tariff": {"tou": tou, "demand_krw_kw": C.DEMAND_KRW_PER_KW, "climate": C.CLIMATE_KRW_KWH, "fuel_adj": C.FUEL_ADJ_KRW_KWH,
                       "fund_rate": C.FUND_RATE, "vat": C.VAT}}


def cloud(eng) -> dict:
    rows = _rows(eng)
    cur, last = rows[-1], rows[-2]
    snap = eng.live["cloud"]
    return {"months": rows, "current": cur, "last_full": last,
            "providers": [{"id": i, "name": n, "role": r, "cost_hr_krw": snap[i]["cost_hr_krw"],
                           "today_krw": round(eng.cloud.cost_today_krw[i])} for i, n, r in C.CLOUD_LINES]}


def budget(eng) -> dict:
    rows = _rows(eng)
    return eng.cost.budget(eng.now, rows)
