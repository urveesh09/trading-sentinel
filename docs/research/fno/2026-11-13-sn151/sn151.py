"""SN151 - "is it hot right now?" every 30 minutes (PLAN.md). Checkpoints 10:00 ... 13:00; R_w = sigma of the last w
minutes' 1-minute index returns / the ATM straddle's implied per-minute sigma; the first checkpoint of the day whose R_w
is in the causal top 20% (earlier sessions' checkpoint values, same w) buys the straddle. Grid w {45, 90} x exit
{15:10, 120 minutes}; LOYO; random checkpoint-day control; robustness."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ph  # noqa: E402

C = ph.C
CHECKS = (45, 75, 105, 135, 165, 195, 225)
WS = (45, 90)
EXITS = {"15:10": None, "120m": 120}


def scan(day_ok):
    rows = []                       # (day, w, checkpoint, hot?) in time order
    qs = {w: ph.CausalQ() for w in WS}
    for S in ph.sessions():
        vals = {w: [(i, ph.r_window(S, i, w)) for i in CHECKS] for w in WS}
        for w in WS:
            thr = qs[w].thr(0.20)
            first = None
            if thr is not None and day_ok(S.day):
                for i, x in vals[w]:
                    if x is not None and x >= thr:
                        first = i
                        break
            rows.append((S, w, first))
        for w in WS:
            for _i, x in vals[w]:
                qs[w].add(x)
    return rows


def nets_for(rows, w, ex, **kw):
    out = {}
    for S, ww, i in rows:
        if ww == w and i is not None:
            t_exit = None if EXITS[ex] is None else i + EXITS[ex]
            v = ph.straddle(S, i, t_exit=t_exit, **kw)
            if v is not None:
                out[S.day] = v
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn151.json"
    if out_path.exists():
        raise SystemExit("SN151 is scored once")
    res = {}
    for dname, ok in (("gold-free", C.gold_free), ("all days", lambda d: C.adx(d) is not None)):
        rows = scan(ok)
        variants = {f"w{w} exit {ex}": (w, ex) for w, ex in itertools.product(WS, EXITS)}
        nets = {k: nets_for(rows, w, ex) for k, (w, ex) in variants.items()}
        tabs = {k: ph.table(v) for k, v in nets.items()}
        L = C.loyo(tabs, "profit")
        held = {d: v for y in ph.YEARS for d, v in nets[L[y]["pick"]].items() if d[:4] == y}
        s400 = sum(v for y in ph.YEARS for d, v in nets_for([r for r in rows if r[0].day[:4] == y], *variants[L[y]["pick"]], stress=400.0).items())
        late = sum(v for y in ph.YEARS for d, v in nets_for([r for r in rows if r[0].day[:4] == y], *variants[L[y]["pick"]], late=1).items())
        pool = {}
        for S in ph.sessions():
            if ok(S.day):
                i = CHECKS[(S.seed // 7) % len(CHECKS)]
                v = ph.straddle(S, i)
                if v is not None:
                    pool.setdefault(S.day[:4], []).append(v)
        rm, r95 = ph.random_control({y: L[y]["trades"] for y in ph.YEARS}, pool)
        v = ph.verdict(held, [L[y]["net"] for y in ph.YEARS], r95, round(s400), round(late))
        res[dname] = {"tables": tabs, "loyo": L, "random_mean": rm, "verdict": v, "heldout_day_nets": held}
        print(f"=== SN151 {dname}")
        for k, t in tabs.items():
            print(f"   {k:20s} {[t[y]['net'] for y in ph.YEARS]} total {ph.tot(t):>8} trades {sum(t[y]['trades'] for y in ph.YEARS)}")
        print("   LOYO", {y: (L[y]["pick"], L[y]["net"]) for y in ph.YEARS}, "| VERDICT", v | {"random_mean": rm}, flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
