"""SN93 - slow up-drift specialist on causal Gold-free days (calls only; PLAN.md). 16 rules + 3 control groups."""
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

E1 = {"stop_k": 4.0, "trail_k": 4.0, "backstop": 0.25}
E2 = {"stop_k": 6.0, "trail_k": 6.0, "vwap_exit": True, "backstop": 0.25}
EXITS = {"E1": E1, "E2": E2}
LAST = 285      # 14:00


def drift_on(S, N, need, prog):
    F = S.F
    c, h, o, vwap = F["c"], F["h"], F["o"], F["vwap"]
    on = {}
    for k in range(4, 19):
        m = 15 * k + 14
        if k < N - 1:
            on[m] = False
            continue
        rets = []
        for b in range(k - N + 1, k + 1):
            start = o[0] if b == 0 else c[15 * b - 1]
            rets.append(c[15 * b + 14] - start)
        hi = float(h[: m + 1].max())
        on[m] = (sum(r > 0 for r in rets) >= need and (c[m] - o[0]) / o[0] >= prog
                 and vwap[m] > vwap[m - 15] and c[m] > vwap[m] and hi > o[0] and (hi - c[m]) <= 0.4 * (hi - o[0]))
    return on


@functools.lru_cache(maxsize=None)
def _sig(day, N, need, prog, entry):
    S = C.years()[day[:4]].sessions[day]
    F = S.F
    on = drift_on(S, N, need, prog)
    sig = np.zeros(len(F["c"]), np.int8)
    if entry == "simple":
        for m in sorted(on):
            if on[m] and m <= LAST:
                sig[m] = 1
                break
        return sig
    c, h, l, e9, e21, atr = F["c"], F["h"], F["l"], F["ema9"], F["ema21"], F["atr"]
    active = touched = False
    for t in range(74, LAST + 1):
        if t in on:
            active = on[t]
            touched = False if not on[t] else touched
            continue
        if not active:
            continue
        if l[t] <= e21[t] + 0.25 * atr[t]:
            touched = True
        if touched and c[t] > h[t - 1] and c[t] > e9[t]:
            sig[t] = 1
            break
    return sig


def rule(N, need, prog, entry):
    def f(S):
        return _sig(S.day, N, need, prog, entry), {}
    f.__name__ = f"drift N{N}/{need} p{prog} {entry}"
    return f


def null_side(f, seed):
    def g(S):
        s, x = f(S)
        rng = random.Random(f"{seed}|{S.day}")
        return (s * (1 if rng.random() < 0.5 else -1)).astype(np.int8), x
    return g


def matched_days(f, seed):
    """The rule's entry minutes moved to a random other Gold-free day of the same year (a call at the same clock)."""
    Ys = C.years()
    plan = {}
    for y in C.YEARS:
        days = [S.day for S in Ys[y].ordered() if C.gold_free(S.day)]
        rng = random.Random(f"{seed}|{y}")
        for d in days:
            s, _ = f(Ys[y].sessions[d])
            idx = np.flatnonzero(s)
            if len(idx):
                other = rng.choice([x for x in days if x != d])
                plan.setdefault(other, int(idx[0]))

    def g(S):
        i = plan.get(S.day)
        if i is None:
            return None
        s = np.zeros(len(S.F["c"]), np.int8)
        s[i] = 1
        return s, {}
    return g


def plain_call(i):
    def g(S):
        s = np.zeros(len(S.F["c"]), np.int8)
        s[i] = 1
        return s, {}
    return g


def grid():
    real = {}
    for (N, need), prog, entry, (en, ex) in itertools.product(((4, 3), (6, 4)), (0.0015, 0.0030), ("simple", "pullback"),
                                                              EXITS.items()):
        real[f"N{N}/{need} p{prog} {entry} {en}"] = (rule(N, need, prog, entry), ex)
    return real


if __name__ == "__main__":
    out_path = HERE / "results-sn93.json"
    if out_path.exists():
        raise SystemExit("SN93 is scored once")
    C.years()
    real = grid()
    controls = {
        "NULL random side": {k: (null_side(f, 93), ex) for k, (f, ex) in real.items()},
        "matched random days": {k: (matched_days(f, 930), ex) for k, (f, ex) in real.items()},
        "plain calls 10:30/12:00": {f"call {t} {en}": (plain_call(i), ex) for (t, i), (en, ex)
                                    in itertools.product((("10:30", 75), ("12:00", 165)), EXITS.items())},
    }
    res = C.contest(real, controls, max_trades=1, last_entry=LAST)
    C.show_contest("SN93 slow up-drift calls (Gold-free days)", res)
    out_path.write_text(json.dumps(C.jsonable({k: v for k, v in res.items() if k != "by_year_cfg"}), indent=1), encoding="utf-8")
