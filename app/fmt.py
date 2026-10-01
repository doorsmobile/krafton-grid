"""Number / currency / time formatters shared by templates and view models."""
from __future__ import annotations

import time


def f_num(v, digits: int = 0) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):,.{digits}f}"
    except (TypeError, ValueError):
        return str(v)


def f_krw(v, short: bool = True) -> str:
    if v is None:
        return "—"
    v = float(v)
    sign, a = ("−" if v < 0 else ""), abs(v)
    if not short:
        return f"{sign}₩{a:,.0f}"
    if a >= 1e12:
        return f"{sign}₩{a / 1e12:,.2f}조"
    if a >= 1e8:
        return f"{sign}₩{a / 1e8:,.2f}억"
    if a >= 1e4:
        return f"{sign}₩{a / 1e4:,.0f}만"
    return f"{sign}₩{a:,.0f}"


def f_dur(s) -> str:
    if s is None:
        return "—"
    s = int(s)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    if s < 86400:
        return f"{s // 3600}h {(s % 3600) // 60:02d}m"
    return f"{s // 86400}d {(s % 86400) // 3600}h"


def f_ago(t) -> str:
    if not t:
        return "—"
    return f_dur(max(0, time.time() - float(t))) + " ago"


def f_kst(t, fmt: str = "%H:%M:%S") -> str:
    if not t:
        return "—"
    return time.strftime(fmt, time.gmtime(float(t) + 9 * 3600))
