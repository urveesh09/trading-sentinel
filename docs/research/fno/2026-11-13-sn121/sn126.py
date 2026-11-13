"""SN126 - trade actively only when movement is underpriced (PLAN.md): on SN95-L's hot days (Gold-free, R_today in the
causal top 20% at 10:00), from 10:00 to 15:00 buy the ATM option in the direction of a fresh 3-minute burst
>= k x ATR x sqrt 3; 2-ATR index stop, h-minute clock, 25% backstop; at most n trades a day. Grid k {1.5, 2.5} x
h {5, 15} x n {5, 15}; SN92's contest (LOYO, random side, robustness, wallets); the same picks on cold Gold-free days."""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pg  # noqa: E402

C, pa = pg.C, pg.pa
ADM = {}


def hot(day):
    return pa.sn95l(ADM, day)


def burst(k):
    def f(S):
        c, atr = S.F["c"], S.F["atr"]
        sig = np.zeros(len(c), np.int8)
        for i in range(pa.I10, 346):
            thr = k * atr[i] * math.sqrt(3)
            mv, prev = c[i] - c[i - 3], c[i - 1] - c[i - 4]
            if abs(mv) >= thr and abs(prev) < k * atr[i - 1] * math.sqrt(3):
                sig[i] = 1 if mv > 0 else -1
        return sig, {}
    f.__name__ = f"burst k{k}"
    return f


def null_side(f, seed):
    def g(S):
        s, x = f(S)
        rng = np.random.default_rng((S.seed * 31 + seed) & 0xFFFFFFFF)
        flip = np.where(rng.random(len(s)) < 0.5, 1, -1).astype(np.int8)
        return (s * flip).astype(np.int8), x
    return g


if __name__ == "__main__":
    out_path = HERE / "results-sn126.json"
    if out_path.exists():
        raise SystemExit("SN126 is scored once")
    ADM.update(pa.admission())
    real = {}
    grid = list(itertools.product((1.5, 2.5), (5, 15), (5, 15)))
    for k, h, n in grid:
        real[f"k{k} h{h} n{n}"] = (burst(k), {"stop_k": 2.0, "time": h, "backstop": 0.25})
    # contest() takes one max_trades; run it per n and merge the tables so LOYO chooses across the whole grid
    parts = {}
    for n in (5, 15):
        sub = {key: v for key, v in real.items() if key.endswith(f"n{n}")}
        parts[n] = C.contest(sub, {"NULL random side": {key: (null_side(f, 126), ex) for key, (f, ex) in sub.items()}},
                             day_ok=hot, max_trades=n, last_entry=345)
    table = {**parts[5]["real"], **parts[15]["real"]}
    nul = {**parts[5]["controls"]["NULL random side"], **parts[15]["controls"]["NULL random side"]}
    Lr, Ln = C.loyo(table, "profit"), C.loyo(nul, "profit")
    rob, cold, held_days = {"stress 400": 0, "1 minute late": 0}, 0, {}
    for y in C.YEARS:
        key = Lr[y]["pick"]
        f, ex = real[key]
        n = int(key.split("n")[-1])
        rob["stress 400"] += C.comp_table(f, ex, hot, stress=400.0, max_trades=n, last_entry=345)[y]["net"]
        rob["1 minute late"] += C.comp_table(f, ex, hot, max_trades=n, last_entry=345, delay=1)[y]["net"]
        cold += C.comp_table(f, ex, lambda d: C.gold_free(d) and not hot(d), max_trades=n, last_entry=345)[y]["net"]
        for S in C.years()[y].ordered():
            if not hot(S.day):
                continue
            sig, _x = f(S)
            realized, cnt, free = 0.0, 0, 0
            for i in np.flatnonzero(sig):
                if cnt >= n or i > 345 or i < free:
                    continue
                got = C.comp_one(S, int(i), int(sig[i]), ex, 15000.0, 1, 3000.0 + realized)
                if got is None:
                    continue
                realized += got[0]
                cnt += 1
                free = got[1] + 1
                if 3000.0 + realized < 150.0:
                    break
            held_days[S.day] = realized
    held = [Lr[y]["net"] for y in C.YEARS]
    ok = Lr["sum"]["net"] > 0 and sum(x > 0 for x in held) >= 3 and Lr["sum"]["net"] > Ln["sum"]["net"] and all(v > 0 for v in rob.values())
    for key, per in table.items():
        print(f"  {key:16s}", [per[y]["net"] for y in C.YEARS], C.tot(per), "trades", sum(per[y]["trades"] for y in C.YEARS))
    print("LOYO", {y: (Lr[y]["pick"], Lr[y]["net"]) for y in C.YEARS}, "sum", Lr["sum"]["net"], "| NULL", Ln["sum"]["net"],
          "| robust", rob, "| same picks on cold Gold-free days", cold, "| PASS" if ok else "| NOT PROVEN", flush=True)
    out_path.write_text(json.dumps(C.jsonable({"table": table, "null": nul, "loyo": Lr, "loyo_null": Ln, "robust": rob,
                                               "cold_days_same_picks": cold, "PASS": bool(ok), "heldout_day_nets": held_days}),
                                   indent=1), encoding="utf-8")
