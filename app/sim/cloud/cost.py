"""DC + Cloud cost baselines and monthly trends."""

from __future__ import annotations

from typing import Any

def build_dc_cost_baseline() -> dict[str, Any]:
    """Monthly KRW baseline for on-prem DC opex (demo)."""
    power = 185_000_000  # 전기요금
    tax = 42_000_000  # 세금
    management = 68_000_000  # 관리비
    labor = 120_000_000  # 인건비
    return {
        "currency": "KRW",
        "period": "month",
        "lines": [
            {"id": "power", "label": "전기요금 (Power)", "amount": power, "note": "M1 IT+facility · 한전 산업용"},
            {"id": "tax", "label": "세금 (Tax)", "amount": tax, "note": "재산세 / 부가세 추정"},
            {"id": "management", "label": "관리비 (Management)", "amount": management, "note": "FM · 보안 · 유지보수"},
            {"id": "labor", "label": "인건비 (Labor)", "amount": labor, "note": "DC ops · NOC · facility"},
        ],
        "total": power + tax + management + labor,
    }

def build_cloud_cost_baseline() -> dict[str, Any]:
    nhn = 78_500_000
    aws = 92_000_000
    gcp = 41_200_000
    return {
        "currency": "KRW",
        "period": "month",
        "lines": [
            {"id": "aws", "label": "AWS GPUaaS", "amount": aws, "note": "EC2 P/G + data transfer"},
            {"id": "gcp", "label": "GCP Storage", "amount": gcp, "note": "GCS + PD + egress"},
            {"id": "nhn", "label": "NHN Cloud GPUaaS", "amount": nhn, "note": "GPU instance + network"},
        ],
        "total": aws + gcp + nhn,
    }

def build_cost_monthly_trends(months: int = 12) -> dict[str, Any]:
    """Trailing monthly cost history for Summary / DC / Cloud trend charts."""
    dc = build_dc_cost_baseline()
    cloud = build_cloud_cost_baseline()
    # Fixed seasonal factors (demo, deterministic)
    factors = [0.88, 0.90, 0.93, 0.95, 0.97, 1.02, 1.08, 1.10, 1.06, 1.01, 0.98, 1.00]
    labels: list[str] = []
    dc_series: dict[str, list[int]] = {ln["id"]: [] for ln in dc["lines"]}
    cloud_series: dict[str, list[int]] = {ln["id"]: [] for ln in cloud["lines"]}
    dc_totals: list[int] = []
    cloud_totals: list[int] = []
    grand_totals: list[int] = []

    # Label months ending at 2026-09
    year, month = 2025, 10
    for i in range(months):
        labels.append(f"{year}-{month:02d}")
        f = factors[i % len(factors)]
        # slight growth over the year
        growth = 1.0 + (i * 0.012)
        dc_month = 0
        for ln in dc["lines"]:
            # power more seasonal than labor
            season = f if ln["id"] == "power" else (0.97 + 0.03 * f)
            val = int(ln["amount"] * season * growth)
            dc_series[ln["id"]].append(val)
            dc_month += val
        cloud_month = 0
        for ln in cloud["lines"]:
            # cloud follows util seasonality
            season = 0.92 + 0.1 * f
            val = int(ln["amount"] * season * growth * (1.02 if ln["id"] == "aws" else 1.0))
            cloud_series[ln["id"]].append(val)
            cloud_month += val
        dc_totals.append(dc_month)
        cloud_totals.append(cloud_month)
        grand_totals.append(dc_month + cloud_month)
        month += 1
        if month > 12:
            month = 1
            year += 1

    return {
        "currency": "KRW",
        "months": labels,
        "dc": {
            "by_line": dc_series,
            "labels": {ln["id"]: ln["label"] for ln in dc["lines"]},
            "total": dc_totals,
        },
        "cloud": {
            "by_line": cloud_series,
            "labels": {ln["id"]: ln["label"] for ln in cloud["lines"]},
            "total": cloud_totals,
        },
        "grand_total": grand_totals,
        "summary": {
            "latest_month": labels[-1],
            "latest_dc": dc_totals[-1],
            "latest_cloud": cloud_totals[-1],
            "latest_grand": grand_totals[-1],
            "prev_grand": grand_totals[-2] if len(grand_totals) > 1 else grand_totals[-1],
            "ytd_dc": sum(dc_totals),
            "ytd_cloud": sum(cloud_totals),
            "ytd_grand": sum(grand_totals),
            "mom_pct": round(
                ((grand_totals[-1] - grand_totals[-2]) / grand_totals[-2]) * 100,
                1,
            )
            if len(grand_totals) > 1 and grand_totals[-2]
            else 0.0,
        },
    }

