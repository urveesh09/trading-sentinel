"""SN94 - confirmed failed breakout of the 09:15-09:45 range, traded toward the interior (both sides, causal Gold-free
days; PLAN.md). 16 rules; controls: the unconditional fade at the break minute, and a random side."""
from __future__ import annotations

import functools
import itertools
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

EX = {"time": 90, "backstop": 0.35}
LAST = 285
MIN_DIST = 20.0


@functools.lru_cache(maxsize=None)
def _fb(day, buf, W, retest, target, unconditional):
    S = C.years()[day[:4]].sessions[day]
    F = S.F
    c, h, l, atr = F["c"], F["h"], F["l"], F["atr"]
    n = len(c)
    sig = np.zeros(n, np.int8)
    ext = {}
    orh, orl = float(h[:30].max()), float(l[:30].min())
    t1 = side = None
    for t in range(30, LAST + 1):
        if c[t] > orh + buf * atr[t]:
            t1, side = t, 1
            break
        if c[t] < orl - buf * atr[t]:
            t1, side = t, -1
            break
    if t1 is None:
        return sig, ext
    X = float(h[t1] if side > 0 else l[t1])
    entry = None
    if unconditional:
        entry = t1
    else:
        t2 = None
        for t in range(t1 + 1, min(t1 + W, LAST) + 1):
            X = max(X, float(h[t])) if side > 0 else min(X, float(l[t]))
            if (side > 0 and c[t] < orh) or (side < 0 and c[t] > orl):
                t2 = t
                break
        if t2 is None:
            return sig, ext
        if not retest:
            entry = t2
        else:
            near = False
            edge = orh if side > 0 else orl
            for t in range(t2 + 1, min(t2 + 30, LAST) + 1):
                if (side > 0 and c[t] > X) or (side < 0 and c[t] < X):
                    break
                if (side > 0 and h[t] >= edge - 0.5 * atr[t] and c[t] < edge) or (side < 0 and l[t] <= edge + 0.5 * atr[t] and c[t] > edge):
                    near = True
                if near and ((side > 0 and c[t] < l[t - 1]) or (side < 0 and c[t] > h[t - 1])):
                    entry = t
                    break
    if entry is None:
        return sig, ext
    d = -side
    tgt = (orh + orl) / 2 if target == "mid" else (orl if side > 0 else orh)
    if (tgt - c[entry]) * d < MIN_DIST:
        return sig, ext
    sig[entry] = d
    ext[entry] = {"stop": X + side * 0.5 * float(atr[entry]), "target": tgt}
    return sig, ext


def rule(buf, W, retest, target, unconditional=False):
    def f(S):
        return _fb(S.day, buf, W, retest, target, unconditional)
    return f


def null_side(f, seed):
    def g(S):
        s, x = f(S)
        idx = np.flatnonzero(s)
        if not len(idx):
            return s, x
        rng = random.Random(f"{seed}|{S.day}")
        if rng.random() < 0.5:
            return s, x
        i = int(idx[0])
        u = float(S.F["c"][i])
        return (-s).astype(np.int8), {i: {"stop": 2 * u - x[i]["stop"], "target": 2 * u - x[i]["target"]}}
    return g


if __name__ == "__main__":
    out_path = HERE / "results-sn94.json"
    if out_path.exists():
        raise SystemExit("SN94 is scored once")
    C.years()
    real, fade = {}, {}
    for buf, W, retest, target in itertools.product((0.0, 0.5), (15, 30), (True, False), ("mid", "far")):
        k = f"buf{buf} W{W} {'retest' if retest else 'direct'} {target}"
        real[k] = (rule(buf, W, retest, target), EX)
        fade[k] = (rule(buf, W, retest, target, unconditional=True), EX)
    controls = {"unconditional fade at the break": fade,
                "NULL random side": {k: (null_side(f, 94), ex) for k, (f, ex) in real.items()}}
    res = C.contest(real, controls, max_trades=1, last_entry=LAST)
    C.show_contest("SN94 confirmed failed breakout (Gold-free days)", res)
    out_path.write_text(json.dumps(C.jsonable({k: v for k, v in res.items() if k != "by_year_cfg"}), indent=1), encoding="utf-8")
