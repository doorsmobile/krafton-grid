"""Cost: DC (전기요금 · 세금 · 관리비 · 인건비), Cloud (AWS · GCP · NHN), budget & requests.

Electricity is computed, not invented: facility kW from the physics model is
billed tick-by-tick at a KEPCO-style industrial time-of-use rate. History is
anchored to the real build-out (M1 commissioning from 2025-11, live 2026-03).
"""
from __future__ import annotations

import calendar
import json
import time
import zlib
from datetime import datetime, timedelta, timezone

from .. import config

KST = timezone(timedelta(hours=9))

# Illustrative 산업용(을) 고압C TOU energy rates (₩/kWh) — editable assumptions
TOU_RATES = {
    "summer": {"off": 110.0, "mid": 170.2, "peak": 255.8},
    "spring_fall": {"off": 110.0, "mid": 137.1, "peak": 175.6},
    "winter": {"off": 117.1, "mid": 169.6, "peak": 229.5},
}
DEMAND_KRW_PER_KW = 8320.0
CLIMATE_KRW_KWH = 9.0
FUEL_ADJ_KRW_KWH = 5.0
FUND_RATE = 0.027
VAT = 0.10
CAPEX_KRW_PER_MONTH = 8.0e9  # assumed 5-yr straight-line on 6,912 × B300 + 480 PB storage + fit-out, for unit economics only

DC_LINES = [("power", "전기요금", "Power"), ("tax", "세금", "Tax"), ("management", "관리비", "Management"),
            ("labor", "인건비", "Labor")]
CLOUD_LINES = [("aws", "AWS", "GPUaaS · EC2 / Capacity Blocks"), ("gcp", "GCP", "Storage · GCS + PD"),
               ("nhn", "NHN Cloud", "GPUaaS")]


def season(month: int) -> str:
    if month in (6, 7, 8):
        return "summer"
    if month in (11, 12, 1, 2):
        return "winter"
    return "spring_fall"


def tou_band(dt: datetime) -> str:
    h = dt.hour
    if dt.weekday() >= 5:
        return "off" if (h >= 22 or h < 8) else "mid"
    if h >= 22 or h < 8:
        return "off"
    if season(dt.month) == "winter":
        return "peak" if (9 <= h < 12 or 16 <= h < 19) else "mid"
    return "peak" if (h == 11 or 13 <= h < 18) else "mid"


def energy_rate(dt: datetime) -> tuple[float, str]:
    band = tou_band(dt)
    return TOU_RATES[season(dt.month)][band] + CLIMATE_KRW_KWH + FUEL_ADJ_KRW_KWH, band


def _ramp_frac(y: int, m: int) -> float:
    """Monthly average facility load as a fraction of today's live load, following M1's build-out."""
    idx = (y - 2026) * 12 + (m - 3)  # 0 == 2026-03 go-live
    if idx < -4:
        return 0.06
    if idx < 0:
        return [0.14, 0.26, 0.37, 0.52][idx + 4]  # commissioning + load-bank testing
    if idx <= 6:
        return [0.61, 0.72, 0.83, 0.9, 0.98, 1.03, 1.0][idx]  # go-live ramp, summer PUE bump
    return 1.0


CURRENT_MW = {"value": 6.8}


def _noise(key: str, spread: float) -> float:
    return 1 + ((zlib.crc32(key.encode()) % 1000) / 1000 - 0.5) * 2 * spread


def month_dc(y: int, m: int, mw: float | None = None, hours: float | None = None) -> dict:
    mw = _ramp_frac(y, m) * CURRENT_MW["value"] if mw is None else mw
    hours = calendar.monthrange(y, m)[1] * 24 if hours is None else hours
    kwh = mw * 1000 * hours
    s = TOU_RATES[season(m)]
    avg_rate = 0.46 * s["off"] + 0.33 * s["mid"] + 0.21 * s["peak"] + CLIMATE_KRW_KWH + FUEL_ADJ_KRW_KWH
    peak_kw = mw * 1000 * 1.08
    frac = hours / (calendar.monthrange(y, m)[1] * 24)
    base = kwh * avg_rate + peak_kw * DEMAND_KRW_PER_KW * frac
    power = base * (1 + FUND_RATE) * (1 + VAT) * _noise(f"p{y}{m}", 0.02)
    live = (y, m) >= (2026, 3)
    key = f"{y}{m}"
    tax = (192e6 if live else 64e6) * _noise("t" + key, 0.03) * frac
    ramp = max(0.0, min(1.0, ((y - 2025) * 12 + m - 10) / 11))
    mgmt = (240e6 + 212e6 * ramp) * _noise("m" + key, 0.04) * frac
    labor = (395e6 + 153e6 * ramp) * _noise("l" + key, 0.015) * frac
    return {"power": round(power), "tax": round(tax), "management": round(mgmt), "labor": round(labor),
            "kwh": round(kwh), "avg_mw": round(mw, 2)}


def month_cloud(y: int, m: int, frac: float = 1.0) -> dict:
    idx = (y - 2025) * 12 + (m - 10)
    g = max(0.0, min(1.4, idx / 11))
    key = f"{y}{m}"
    aws = (420e6 + 610e6 * g) * _noise("a" + key, 0.12) * frac
    gcp = (90e6 + 60e6 * g) * _noise("g" + key, 0.05) * frac
    nhn = (310e6 + 262e6 * g) * _noise("n" + key, 0.08) * frac
    return {"aws": round(aws), "gcp": round(gcp), "nhn": round(nhn)}


def _months_back(now_kst: datetime, n: int) -> list[tuple[int, int]]:
    y, m = now_kst.year, now_kst.month
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append((y, m))
    return list(reversed(out))


MIN_FRAC = 0.0005   # ~22 min of a month: floor for straight-line forecasts right after rollover

BUDGET_ITEMS = [
    {"code": "OPX-110", "name": "전기요금 · Electricity", "category": "DC", "line": "power", "annual": 9.0e9},
    {"code": "OPX-120", "name": "시설관리 · Facility O&M", "category": "DC", "line": "management", "annual": 5.3e9},
    {"code": "OPX-130", "name": "인건비 · Labor", "category": "DC", "line": "labor", "annual": 6.9e9},
    {"code": "OPX-140", "name": "세금·공과 · Tax & dues", "category": "DC", "line": "tax", "annual": 2.2e9},
    {"code": "OPX-210", "name": "클라우드 · AWS", "category": "Cloud", "line": "aws", "annual": 9.6e9},
    {"code": "OPX-220", "name": "클라우드 · GCP", "category": "Cloud", "line": "gcp", "annual": 1.9e9},
    {"code": "OPX-230", "name": "클라우드 · NHN", "category": "Cloud", "line": "nhn", "annual": 6.7e9},
    {"code": "OPX-310", "name": "네트워크 회선 · DCI", "category": "Shared", "line": None, "annual": 1.2e9},
    {"code": "OPX-320", "name": "SW 라이선스 · Scale/NVAIE/CloudVision", "category": "Shared", "line": None, "annual": 3.8e9},
    {"code": "OPX-900", "name": "예비비 · Contingency", "category": "Shared", "line": None, "annual": 1.5e9},
]
REQUEST_KINDS = {
    "transfer": {"ko": "예산 이관", "en": "Transfer budget"},
    "increase": {"ko": "예산 증액", "en": "Increase budget"},
    "refund": {"ko": "예산 환입", "en": "Refund budget"},
    "new_item": {"ko": "예산항목 생성", "en": "Budget item request"},
}
APPROVAL_STEPS = ["draft", "submitted", "team_lead", "finance", "approved"]
STEP_LABEL = {"draft": "작성중", "submitted": "상신", "team_lead": "팀장 승인", "finance": "재무 검토",
              "approved": "최종 승인", "rejected": "반려"}


class Cost:
    def __init__(self, now: float):
        self.today_power_krw = 0.0
        self.month_power_live = 0.0
        self.band = "mid"
        self.rate = 0.0
        self.boot = now
        self.items = [dict(it, adjust=0.0) for it in BUDGET_ITEMS]
        self.requests: list[dict] = []
        self._seq = 1040
        self._store = config.DATA_DIR / "budget.json"
        if not self._load():
            self._seed_requests(now)
            self._save()

    # ------------------------------------------------------------- persistence
    def _load(self) -> bool:
        try:
            data = json.loads(self._store.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        adjust = data.get("adjust", {})
        for it in self.items:
            it["adjust"] = float(adjust.get(it["code"], 0.0))
        self.items += [dict(x) for x in data.get("extra_items", [])]
        self.requests = data.get("requests", [])
        self._seq = int(data.get("seq", self._seq))
        return True

    def _save(self) -> None:
        base = {it["code"] for it in BUDGET_ITEMS}
        data = {"seq": self._seq, "requests": self.requests,
                "adjust": {it["code"]: it["adjust"] for it in self.items if it["code"] in base},
                "extra_items": [it for it in self.items if it["code"] not in base]}
        try:
            self._store.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._store.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self._store)
        except OSError:
            pass  # best-effort: the workflow keeps working in memory

    # ------------------------------------------------------------- live billing
    def tick(self, now: float, dt: float, facility_kw: float) -> None:
        d = datetime.fromtimestamp(now, KST)
        rate, band = energy_rate(d)
        self.rate, self.band = rate, band
        krw = facility_kw * dt / 3600 * rate * (1 + FUND_RATE) * (1 + VAT)
        self.today_power_krw += krw
        self.month_power_live += krw

    def current_rate(self) -> dict:
        return {"band": self.band, "band_ko": {"off": "경부하", "mid": "중간부하", "peak": "최대부하"}[self.band],
                "krw_kwh": round(self.rate, 1), "season": season(datetime.now(KST).month)}

    # --------------------------------------------------------------- history
    def monthly(self, now: float, live_mw: float, cloud_month_live: dict) -> list[dict]:
        d = datetime.fromtimestamp(now, KST)
        rows = []
        for y, m in _months_back(d, 12):
            dc = month_dc(y, m)
            cl = month_cloud(y, m)
            rows.append(self._row(y, m, dc, cl, partial=False))
        start = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_h = calendar.monthrange(d.year, d.month)[1] * 24
        elapsed_h = max((d - start).total_seconds() / 3600, 0.01)
        # before this process booted we bill at the live average; after boot, tick-by-tick
        prior_h = max(0.01, elapsed_h - (now - self.boot) / 3600)
        dc_prior = month_dc(d.year, d.month, mw=live_mw, hours=prior_h)
        dc_elapsed = month_dc(d.year, d.month, mw=live_mw, hours=elapsed_h)
        dc = {**dc_elapsed, "power": round(dc_prior["power"] + self.month_power_live)}
        cl = month_cloud(d.year, d.month, frac=prior_h / month_h)
        for k in cl:
            cl[k] = round(cl[k] + cloud_month_live.get(k, 0.0))
        rows.append(self._row(d.year, d.month, dc, cl, partial=True, frac=elapsed_h / month_h))
        return rows

    @staticmethod
    def _row(y: int, m: int, dc: dict, cl: dict, partial: bool, frac: float = 1.0) -> dict:
        dc_total = dc["power"] + dc["tax"] + dc["management"] + dc["labor"]
        cl_total = cl["aws"] + cl["gcp"] + cl["nhn"]
        return {"month": f"{y}-{m:02d}", "partial": partial, "month_frac": round(frac, 6),
                "dc": {k: dc[k] for k in ("power", "tax", "management", "labor")}, "dc_total": dc_total,
                "cloud": {k: cl[k] for k in ("aws", "gcp", "nhn")}, "cloud_total": cl_total,
                "total": dc_total + cl_total, "kwh": dc.get("kwh"), "avg_mw": dc.get("avg_mw")}

    def summary(self, now: float, rows: list[dict], gpu_hours_month: float) -> dict:
        cur, prev = rows[-1], rows[-2]
        frac = max(cur["month_frac"], MIN_FRAC)
        forecast = {"dc": cur["dc_total"] / frac, "cloud": cur["cloud_total"] / frac}
        mom = {k: ((forecast[k] - prev[f"{k}_total"]) / prev[f"{k}_total"] * 100) if prev[f"{k}_total"] else 0.0
               for k in ("dc", "cloud")}
        y = datetime.fromtimestamp(now, KST).year
        ytd = [r for r in rows if r["month"].startswith(str(y))]
        ytd_dc = sum(r["dc_total"] for r in ytd)
        ytd_cloud = sum(r["cloud_total"] for r in ytd)
        last12 = rows[-12:]
        opex = forecast["dc"]
        gpu_hours_full = max(gpu_hours_month / frac, 1.0)   # project MTD GPU-hours to the whole month, like the costs
        per_gpu_hr = (opex + CAPEX_KRW_PER_MONTH) / gpu_hours_full
        return {
            "month": cur["month"], "month_frac": cur["month_frac"],
            "mtd": {"dc": cur["dc_total"], "cloud": cur["cloud_total"], "total": cur["total"]},
            "forecast": {k: round(v) for k, v in forecast.items()} | {"total": round(sum(forecast.values()))},
            "mom_pct": {k: round(v, 1) for k, v in mom.items()},
            "ytd": {"dc": ytd_dc, "cloud": ytd_cloud, "total": ytd_dc + ytd_cloud, "year": y},
            "trailing12": {"dc": sum(r["dc_total"] for r in last12), "cloud": sum(r["cloud_total"] for r in last12)},
            "today_power_krw": round(self.today_power_krw),
            "rate": self.current_rate(),
            "unit": {
                "gpu_hours_month": round(gpu_hours_month), "gpu_hours_forecast": round(gpu_hours_full),
                "opex_per_gpu_hr": round(opex / gpu_hours_full),
                "tco_per_gpu_hr": round(per_gpu_hr), "aws_b200_per_gpu_hr": round(77.40 / 8 * 1392),
                "aws_h200_per_gpu_hr": round(63.30 / 8 * 1392), "nhn_h100_per_gpu_hr": 9800,
                "capex_month_assumed": CAPEX_KRW_PER_MONTH,
            },
        }

    # ---------------------------------------------------------------- budget
    def budget(self, now: float, rows: list[dict]) -> dict:
        d = datetime.fromtimestamp(now, KST)
        ytd_rows = [r for r in rows if r["month"].startswith(str(d.year))]
        frac = rows[-1]["month_frac"]
        months_left = 12 - d.month + (1 - frac)
        w = min(1.0, frac / 0.25)   # first week of a month: lean on last full month for the run-rate
        out = []
        for it in self.items:
            line = it["line"]
            if line in ("power", "tax", "management", "labor"):
                actual = sum(r["dc"][line] for r in ytd_rows)
                run = w * rows[-1]["dc"][line] / max(frac, MIN_FRAC) + (1 - w) * rows[-2]["dc"][line]
            elif line in ("aws", "gcp", "nhn"):
                actual = sum(r["cloud"][line] for r in ytd_rows)
                run = w * rows[-1]["cloud"][line] / max(frac, MIN_FRAC) + (1 - w) * rows[-2]["cloud"][line]
            else:
                elapsed = (d.month - 1 + rows[-1]["month_frac"]) / 12
                pace = 0.22 if it["code"] == "OPX-900" else 0.84 + (zlib.crc32(it["code"].encode()) % 90) / 1000
                actual = it["annual"] * elapsed * pace          # contingency is drawn down slowly
                run = it["annual"] / 12 * pace
            budget = it["annual"] + it["adjust"]
            forecast = actual + run * months_left
            out.append({"code": it["code"], "name": it["name"], "category": it["category"],
                        "annual": round(it["annual"]), "adjust": round(it["adjust"]), "budget": round(budget),
                        "actual_ytd": round(actual), "forecast_fy": round(forecast),
                        "used_pct": round(actual / budget * 100, 1) if budget else 0.0,
                        "variance": round(budget - forecast), "status": "over" if forecast > budget * 1.0 else
                        ("watch" if forecast > budget * 0.95 else "ok")})
        tot_b = sum(o["budget"] for o in out)
        tot_a = sum(o["actual_ytd"] for o in out)
        tot_f = sum(o["forecast_fy"] for o in out)
        return {"fy": d.year, "items": out, "total_budget": tot_b, "total_actual": tot_a, "total_forecast": tot_f,
                "requests": self.requests, "kinds": REQUEST_KINDS, "steps": APPROVAL_STEPS, "step_label": STEP_LABEL}

    def _seed_requests(self, now: float) -> None:
        seeds = [
            ("increase", "OPX-210", None, 1.8e9, "AI Platform", "AWS Capacity Block 추가 확보 (Q4 LLM 70B stage-3 학습 대기열 해소)", "finance"),
            ("transfer", "OPX-900", "OPX-110", 0.6e9, "Infra Ops", "하계 PUE 상승분 전기요금 보전 (예비비 → 전력비)", "approved"),
            ("refund", "OPX-230", None, 0.35e9, "Inference Platform", "NHN L40S 인스턴스 온프렘 infer 파티션 이전에 따른 잔여 예산 환입", "team_lead"),
            ("new_item", None, None, 0.9e9, "AI Research", "신규 항목: 합성 데이터 생성용 외부 API 사용료 (Synthetic data APIs)", "submitted"),
            ("increase", "OPX-320", None, 0.4e9, "Storage", "IBM Storage Scale 용량 라이선스 +12 PB (M1 Hall D 확장 대비)", "draft"),
        ]
        for i, (kind, src, dst, amt, team, reason, step) in enumerate(seeds):
            r = self._make_request(kind, src, dst, amt, team, reason, now - (5 - i) * 86400 * 1.7,
                                   new_name="Synthetic data APIs" if kind == "new_item" else None,
                                   category="Shared" if kind == "new_item" else None)
            for s in APPROVAL_STEPS[1:APPROVAL_STEPS.index(step) + 1]:
                self._advance(r, s, now - (5 - i) * 86400 * 1.5, apply=(s == "approved"))

    def _make_request(self, kind: str, src: str | None, dst: str | None, amount: float, team: str, reason: str,
                      t: float, new_name: str | None = None, category: str | None = None) -> dict:
        self._seq += 1
        r = {"id": f"BR-2026-{self._seq}", "kind": kind, "kind_ko": REQUEST_KINDS[kind]["ko"],
             "kind_en": REQUEST_KINDS[kind]["en"], "source": src, "target": dst, "amount": round(amount),
             "team": team, "reason": reason, "status": "draft", "created_t": t, "updated_t": t,
             "new_name": new_name, "category": category,
             "history": [{"t": t, "step": "draft", "label": STEP_LABEL["draft"], "by": team}]}
        self.requests.insert(0, r)
        return r

    def _advance(self, r: dict, step: str, t: float, apply: bool = False) -> None:
        r["status"] = step
        r["updated_t"] = t
        by = {"submitted": r["team"], "team_lead": f"{r['team']} Lead", "finance": "Finance BP",
              "approved": "CFO Office", "rejected": "Finance BP"}.get(step, r["team"])
        r["history"].append({"t": t, "step": step, "label": STEP_LABEL[step], "by": by})
        if apply:
            self._apply(r)

    def _apply(self, r: dict) -> None:
        by_code = {it["code"]: it for it in self.items}
        amt = r["amount"]
        if r["kind"] == "transfer" and r["source"] in by_code and r["target"] in by_code:
            by_code[r["source"]]["adjust"] -= amt
            by_code[r["target"]]["adjust"] += amt
        elif r["kind"] == "increase" and r["source"] in by_code:
            by_code[r["source"]]["adjust"] += amt
        elif r["kind"] == "refund" and r["source"] in by_code:
            by_code[r["source"]]["adjust"] -= amt
        elif r["kind"] == "new_item":
            code = f"OPX-{400 + len([i for i in self.items if i['code'].startswith('OPX-4')]) + 1}"
            self.items.append({"code": code, "name": r.get("new_name") or r["reason"][:40],
                               "category": r.get("category") or "Shared", "line": None, "annual": 0.0, "adjust": float(amt)})
            r["created_code"] = code

    def create_request(self, payload: dict, now: float) -> dict:
        kind = payload.get("kind")
        if kind not in REQUEST_KINDS:
            raise ValueError("kind must be one of transfer|increase|refund|new_item")
        amount = float(payload.get("amount") or 0)
        if amount <= 0:
            raise ValueError("amount must be positive")
        codes = {it["code"] for it in self.items}
        src, dst = payload.get("source"), payload.get("target")
        if kind in ("transfer", "increase", "refund") and src not in codes:
            raise ValueError("source budget item not found")
        if kind == "transfer" and (dst not in codes or dst == src):
            raise ValueError("target budget item must differ from source")
        if kind == "new_item" and not (payload.get("new_name") or "").strip():
            raise ValueError("new_name required for a budget item request")
        r = self._make_request(kind, src, dst if kind == "transfer" else None, amount,
                               (payload.get("team") or "Infra Ops")[:40], (payload.get("reason") or "")[:300], now,
                               new_name=(payload.get("new_name") or "").strip()[:60] or None,
                               category=payload.get("category") or None)
        if payload.get("submit"):
            self._advance(r, "submitted", now)
        self._save()
        return r

    def act(self, rid: str, action: str, now: float) -> dict:
        r = next((x for x in self.requests if x["id"] == rid), None)
        if r is None:
            raise KeyError(rid)
        if r["status"] in ("approved", "rejected"):
            raise ValueError("request already closed")
        if action == "reject":
            self._advance(r, "rejected", now)
        elif action == "approve":
            nxt = APPROVAL_STEPS[APPROVAL_STEPS.index(r["status"]) + 1]
            self._advance(r, nxt, now, apply=(nxt == "approved"))
        else:
            raise ValueError("action must be approve|reject")
        self._save()
        return r
