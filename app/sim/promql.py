"""PromQL-lite: a small, real evaluator over the in-memory TSDB.

Supported:
  selectors            gpu_temp_c{rack="R07", hall=~"HA|HB"}   (=  !=  =~  !~)
  range functions      rate / increase / delta / avg_over_time / max_over_time / min_over_time / sum_over_time (m[5m])
  aggregations         sum / avg / max / min / count  [by (label, ...)]   ·  topk(k, …) / bottomk(k, …)
  arithmetic           + - * /  between vectors (label-matched) and scalars, parentheses
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .tsdb import TSDB, parse_duration

TOKEN = re.compile(r"""
    (?P<ws>\s+)|
    (?P<num>\d+(?:\.\d+)?(?:e[+-]?\d+)?)|
    (?P<dur>\[\d+[smhd]\])|
    (?P<str>"(?:[^"\\]|\\.)*")|
    (?P<op>=~|!~|!=|==|[-+*/(){},=])|
    (?P<ident>[a-zA-Z_:][a-zA-Z0-9_:]*)
""", re.X)

AGGS = {"sum", "avg", "max", "min", "count", "topk", "bottomk"}
RANGE_FUNCS = {"rate", "irate", "increase", "delta", "avg_over_time", "max_over_time", "min_over_time", "sum_over_time"}


class PromQLError(ValueError):
    pass


@dataclass
class Matrix:
    ts: np.ndarray            # (T,)
    vals: np.ndarray          # (T, S)
    labels: list[dict]        # len S

    @property
    def scalar(self) -> bool:
        return False


@dataclass
class Scalar:
    value: float


def tokenize(q: str) -> list[tuple[str, str]]:
    out, pos = [], 0
    while pos < len(q):
        m = TOKEN.match(q, pos)
        if not m:
            raise PromQLError(f"unexpected character at {pos}: {q[pos:pos + 12]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        out.append((kind, m.group(kind)))
    return out


class Parser:
    def __init__(self, q: str):
        self.toks = tokenize(q)
        self.i = 0

    def peek(self, k: int = 0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else (None, None)

    def take(self, kind=None, val=None):
        t = self.peek()
        if t[0] is None or (kind and t[0] != kind) or (val and t[1] != val):
            raise PromQLError(f"expected {val or kind}, got {t[1]!r}")
        self.i += 1
        return t

    def parse(self):
        node = self.expr()
        if self.peek()[0] is not None:
            raise PromQLError(f"unexpected trailing token {self.peek()[1]!r}")
        return node

    def expr(self):
        node = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            node = ("bin", op, node, self.term())
        return node

    def term(self):
        node = self.factor()
        while self.peek() in (("op", "*"), ("op", "/")):
            op = self.take()[1]
            node = ("bin", op, node, self.factor())
        return node

    def factor(self):
        kind, val = self.peek()
        if kind == "num":
            self.take()
            return ("num", float(val))
        if (kind, val) == ("op", "("):
            self.take()
            node = self.expr()
            self.take("op", ")")
            return node
        if (kind, val) == ("op", "-"):
            self.take()
            return ("bin", "*", ("num", -1.0), self.factor())
        if kind == "ident":
            if val in AGGS:
                return self.aggregation()
            if val in RANGE_FUNCS:
                self.take()
                self.take("op", "(")
                inner = self.selector(require_range=True)
                self.take("op", ")")
                return ("func", val, inner)
            return self.selector()
        raise PromQLError(f"unexpected token {val!r}")

    def labels_list(self):
        self.take("op", "(")
        labs = []
        while self.peek() != ("op", ")"):
            labs.append(self.take("ident")[1])
            if self.peek() == ("op", ","):
                self.take()
        self.take("op", ")")
        return labs

    def aggregation(self):
        name = self.take()[1]
        by = None
        if self.peek() == ("ident", "by"):
            self.take()
            by = self.labels_list()
        self.take("op", "(")
        k = None
        if name in ("topk", "bottomk"):
            k = int(float(self.take("num")[1]))
            self.take("op", ",")
        inner = self.expr()
        self.take("op", ")")
        if self.peek() == ("ident", "by"):
            self.take()
            by = self.labels_list()
        return ("agg", name, by, k, inner)

    def selector(self, require_range: bool = False):
        name = self.take("ident")[1]
        matchers = []
        if self.peek() == ("op", "{"):
            self.take()
            while self.peek() != ("op", "}"):
                lab = self.take("ident")[1]
                op = self.take("op")[1]
                if op not in ("=", "!=", "=~", "!~"):
                    raise PromQLError(f"bad matcher op {op}")
                raw = self.take("str")[1][1:-1]
                matchers.append((lab, op, raw))
                if self.peek() == ("op", ","):
                    self.take()
            self.take("op", "}")
        rng = None
        if self.peek()[0] == "dur":
            rng = parse_duration(self.take()[1][1:-1])
        if require_range and rng is None:
            raise PromQLError("range function needs a range selector like metric[5m]")
        return ("sel", name, matchers, rng)


def _match(labels: dict, matchers) -> bool:
    for lab, op, raw in matchers:
        v = str(labels.get(lab, ""))
        if op == "=" and v != raw:
            return False
        if op == "!=" and v == raw:
            return False
        if op == "=~" and not re.fullmatch(raw, v):
            return False
        if op == "!~" and re.fullmatch(raw, v):
            return False
    return True


class Evaluator:
    def __init__(self, db: TSDB, window_s: float, max_series: int = 64):
        self.db = db
        self.window = window_s
        self.max_series = max_series

    def run(self, node):
        kind = node[0]
        if kind == "num":
            return Scalar(node[1])
        if kind == "sel":
            return self.select(node, extra=0.0)
        if kind == "func":
            return self.func(node[1], node[2])
        if kind == "agg":
            return self.aggregate(node)
        if kind == "bin":
            return self.binary(node[1], self.run(node[2]), self.run(node[3]))
        raise PromQLError(f"unknown node {kind}")

    def select(self, node, extra: float) -> Matrix:
        _, name, matchers, _ = node
        m = self.db.metrics.get(name)
        if m is None:
            raise PromQLError(f"unknown metric {name!r} — see the metric catalog")
        cols = [i for i, lab in enumerate(m.labels) if _match({**lab, "__name__": name}, matchers)]
        with self.db.lock:
            ts, vals = m.window(self.window + extra, cols=cols)
            vals = vals.astype(np.float64) if cols else np.zeros((len(ts), 0))
        return Matrix(ts.copy(), vals, [dict(m.labels[c]) for c in cols])

    def func(self, fname: str, sel) -> Matrix:
        rng = sel[3]
        mat = self.select(sel, extra=rng)
        if not len(mat.ts):
            return mat
        dt = float(np.median(np.diff(mat.ts))) if len(mat.ts) > 1 else 2.0
        w = max(1, int(round(rng / dt)))
        v = mat.vals
        out = np.full_like(v, np.nan)
        for t in range(len(mat.ts)):
            lo = max(0, t - w + 1)
            win = v[lo:t + 1]
            if not len(win):
                continue
            if fname == "avg_over_time":
                out[t] = np.nanmean(win, axis=0)
            elif fname == "max_over_time":
                out[t] = np.nanmax(win, axis=0)
            elif fname == "min_over_time":
                out[t] = np.nanmin(win, axis=0)
            elif fname == "sum_over_time":
                out[t] = np.nansum(win, axis=0)
            elif fname in ("rate", "irate", "increase", "delta"):
                if len(win) < 2:
                    continue
                if fname == "irate":
                    d, span = win[-1] - win[-2], dt
                else:
                    d, span = win[-1] - win[0], dt * (len(win) - 1)
                if fname in ("rate", "irate", "increase"):
                    d = np.where(d < 0, win[-1], d)  # counter reset
                out[t] = d if fname in ("increase", "delta") else d / span
        keep = mat.ts >= mat.ts[-1] - self.window
        return Matrix(mat.ts[keep], out[keep], [{k: v for k, v in lab.items()} for lab in mat.labels])

    def aggregate(self, node) -> Matrix:
        _, name, by, k, inner = node
        mat = self.run(inner)
        if isinstance(mat, Scalar):
            raise PromQLError(f"{name} needs a vector")
        if name in ("topk", "bottomk"):
            if not mat.vals.shape[1]:
                return mat
            last = np.nan_to_num(mat.vals[-1], nan=-np.inf if name == "topk" else np.inf)
            order = np.argsort(-last if name == "topk" else last)[:k]
            return Matrix(mat.ts, mat.vals[:, order], [mat.labels[i] for i in order])
        groups: dict[tuple, list[int]] = {}
        for i, lab in enumerate(mat.labels):
            key = tuple((b, lab.get(b, "")) for b in by) if by else ()
            groups.setdefault(key, []).append(i)
        cols, labs = [], []
        fn = {"sum": np.nansum, "avg": np.nanmean, "max": np.nanmax, "min": np.nanmin}.get(name)
        for key, idx in groups.items():
            sub = mat.vals[:, idx]
            if name == "count":
                cols.append(np.sum(~np.isnan(sub), axis=1).astype(np.float64))
            else:
                with np.errstate(all="ignore"):
                    cols.append(fn(sub, axis=1) if sub.size else np.full(len(mat.ts), np.nan))
            labs.append(dict(key))
        vals = np.stack(cols, axis=1) if cols else np.zeros((len(mat.ts), 0))
        return Matrix(mat.ts, vals, labs)

    def binary(self, op: str, a, b):
        f = {"+": np.add, "-": np.subtract, "*": np.multiply, "/": np.divide}[op]
        if isinstance(a, Scalar) and isinstance(b, Scalar):
            return Scalar(float(f(a.value, b.value)))
        with np.errstate(all="ignore"):
            if isinstance(a, Scalar):
                return Matrix(b.ts, f(a.value, b.vals), b.labels)
            if isinstance(b, Scalar):
                return Matrix(a.ts, f(a.vals, b.value), a.labels)
            bi = {tuple(sorted(lab.items())): i for i, lab in enumerate(b.labels)}
            cols, labs = [], []
            for i, lab in enumerate(a.labels):
                j = bi.get(tuple(sorted(lab.items())))
                if j is None and len(b.labels) == 1:
                    j = 0
                if j is None:
                    continue
                bcol = np.interp(a.ts, b.ts, b.vals[:, j]) if len(b.ts) else np.full(len(a.ts), np.nan)
                cols.append(f(a.vals[:, i], bcol))
                labs.append(lab)
            vals = np.stack(cols, axis=1) if cols else np.zeros((len(a.ts), 0))
            return Matrix(a.ts, vals, labs)


def query(db: TSDB, q: str, window_s: float = 900, max_series: int = 60, max_points: int = 240) -> dict:
    node = Parser(q).parse()
    res = Evaluator(db, window_s, max_series).run(node)
    if isinstance(res, Scalar):
        return {"resultType": "scalar", "result": res.value, "series": 0}
    total = res.vals.shape[1]
    order = list(range(total))
    if total > max_series:
        last = np.nan_to_num(res.vals[-1], nan=-np.inf) if len(res.ts) else np.zeros(total)
        order = list(np.argsort(-last)[:max_series])
    step = max(1, len(res.ts) // max_points)
    out = []
    for i in order:
        col = res.vals[::step, i]
        pts = [[int(t * 1000), None if v != v or np.isinf(v) else round(float(v), 4)]
               for t, v in zip(res.ts[::step].tolist(), col.tolist())]
        last = next((p[1] for p in reversed(pts) if p[1] is not None), None)
        out.append({"metric": res.labels[i], "values": pts, "last": last})
    return {"resultType": "matrix", "result": out, "series": total, "truncated": total > max_series,
            "points": len(res.ts[::step])}
