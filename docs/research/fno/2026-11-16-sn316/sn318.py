"""SN318: does a one-minute break-and-hold transfer to 2019? (PLAN.md, frozen before any 2019 price is read; refuses until
SN316's seal is written.)

Rule: the level = the high / low of the 3 completed one-minute index bars; an event = a completed minute closing outside
the level (the previous minute did not), and the next completed minute also closing outside it (held); buy the
at-the-money call (up) or put (down) at the following minute's modelled ask (house spread table, gl.Pos); hold 15 minutes
with a Rs 3,000 stop on the minute marks (gl.walk); decisions 09:30-14:30; non-expiry sessions; one position at a time,
at most one event per 15 minutes. Zerodha charges + Rs 205 (Rs 400) per lot; one lot of today's 65 units (75 as a
sensitivity on 2019). Control: 200 random-clock books with the same trades per session and sides.
Reported: DEV (NIFTY Apr 2022 - Aug 2026) and TEST (Aug 20 - Oct 28 2026), both seen; 2019 Q3 and Q4 separately
(unseen), all sessions and the quiet-day proxy (yesterday's ADX < 30 from the sealed minutes).
Pass in 2019: net > 0 at Rs 205 and Rs 400 in both quarters, and above the random median at Rs 205."""
from __future__ import annotations

import json
import pickle
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn251"))
import gl  # noqa: E402

M2019 = HERE / "_local" / "mirror-nifty-2019.sqlite"
HOLD, ROOM = 15, 3000.0
gl.SRC["N2019"] = {"und": "NIFTY", "lo": "2019-07-01", "hi": "2019-12-31", "option": [M2019], "index": [M2019], "future": [M2019]}


def n2019():
    p = HERE / "_local" / "gl-n2019.pkl"
    if not p.exists():
        p.write_bytes(pickle.dumps(gl.build_exam("N2019"), protocol=pickle.HIGHEST_PROTOCOL))
    return gl.Sample("N2019", pickle.loads(p.read_bytes()))


def events(s):
    c, h, l = s["index"][3], s["index"][1], s["index"][2]
    out, prev = [], 0
    for m in range(3, 320):
        hi, lo = float(np.max(h[m - 3:m])), float(np.min(l[m - 3:m]))
        sg = 1 if c[m] > hi else (-1 if c[m] < lo else 0)
        fresh = sg != 0 and sg != prev
        prev = sg
        if not fresh or m < 15 or m + 2 > 317:
            continue
        lvl = hi if sg > 0 else lo
        if sg * (c[m + 1] - lvl) > 0:
            out.append((m + 2, sg))
    return out


def trade(smp, s, i, sg, stress):
    K = gl.atm(smp, s, i)
    pos = gl.Pos(smp, s, [(K, "CE" if sg > 0 else "PE", +1)], i, lots=1, stress=stress)
    if not pos.ok:
        return None
    net, j, _why = gl.walk(pos, s, i, min(i + HOLD, gl.FLAT), room=ROOM)
    return None if net is None else (net, j)


def run_day(smp, s, stress, picks=None):
    rows, free, last = [], -1, -99
    for i, sg in (picks if picks is not None else events(s)):
        if i <= free or i - last < 15:
            continue
        t = trade(smp, s, i, sg, stress)
        if t is None:
            continue
        rows.append((i, sg, t[0]))
        free, last = t[1], i
    return rows


def book(smp, stress, days=None, quiet=False):
    per, sides = {}, {}
    for d in (days or smp.days):
        if quiet:
            a = smp.adx(d)
            if a is None or a >= 30:
                continue
        rows = run_day(smp, smp.s[d], stress)
        per[d] = sum(x for _i, _s, x in rows)
        sides[d] = [sg for _i, sg, _x in rows]
    return per, sides


def null(smp, sides, stress, draws=200, seed=318):
    rng = random.Random(seed)
    tots = []
    for _ in range(draws):
        tot = 0.0
        for d, sg in sides.items():
            if not sg:
                continue
            mins = sorted(rng.sample(range(17, 318), min(len(sg), 20)))
            tot += sum(x for _i, _s, x in run_day(smp, smp.s[d], stress, picks=list(zip(mins, sg))))
        tots.append(tot)
    return float(np.median(tots)), tots


def report(smp, days, stress, with_null=False):
    per, sides = book(smp, stress, days)
    q_per, _qs = book(smp, stress, days, quiet=True)
    out = {"sessions": len(per), "trades": sum(len(v) for v in sides.values()), "net": round(sum(per.values())),
           "per_session": round(sum(per.values()) / max(1, len(per)), 1), "worst_day": round(min(per.values(), default=0.0)),
           "quiet_sessions": len(q_per), "quiet_net": round(sum(q_per.values()))}
    if with_null:
        med, tots = null(smp, sides, stress)
        out["random_median"] = round(med)
        out["rule_percentile_vs_random"] = round(float(np.mean([out["net"] > t for t in tots])), 3)
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn318.json"
    if out_path.exists():
        raise SystemExit("SN318 is run once")
    if not (HERE / "seal-sn316.json").exists():
        raise SystemExit("SN318 waits for SN316's seal")
    res = {}
    for name in ("DEV", "TEST"):
        smp = gl.sample(name)
        for st in (205.0, 400.0):
            res[f"{name} @{int(st)}"] = report(smp, smp.days, st, with_null=(st == 205.0))
            print("SN318", name, int(st), json.dumps(res[f"{name} @{int(st)}"]), flush=True)
    smp = n2019()
    quarters = {"2019Q3": [d for d in smp.days if d < "2019-10-01"], "2019Q4": [d for d in smp.days if d >= "2019-10-01"]}
    for q, days in quarters.items():
        for st in (205.0, 400.0):
            res[f"{q} @{int(st)}"] = report(smp, days, st, with_null=(st == 205.0))
            print("SN318", q, int(st), json.dumps(res[f"{q} @{int(st)}"]), flush=True)
    smp.mk = {**smp.mk, "lot": 75}
    for q, days in quarters.items():
        res[f"{q} @205 lot 75 (sensitivity)"] = report(smp, days, 205.0)
    ok = all(res[f"{q} @205"]["net"] > 0 and res[f"{q} @400"]["net"] > 0 and res[f"{q} @205"]["net"] > res[f"{q} @205"]["random_median"]
             for q in quarters)
    res["verdict_2019"] = "PASS" if ok else "FAIL"
    print("SN318 verdict", res["verdict_2019"], flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
