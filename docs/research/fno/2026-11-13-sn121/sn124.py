"""SN124 - overnight short volatility (Muravyev & Ni; PLAN.md). Every night whose next session shares the nearest
weekly expiry: sell at 15:15 the ATM iron fly (+-200 wings) or iron condor (short +-50, long +-250), buy back next
morning at 09:16 / 09:20 / 09:45 / 10:15. Control: the same structure sold 09:20 and bought 15:15 the same day.
Descriptions: the long straddle overnight; implied sigma 15:15 -> 09:20. Margin = defined maximum loss (proxy)."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pg  # noqa: E402

C, M = pg.C, pg.M
I1515 = 360
EXITS = {"09:16": 1, "09:20": 5, "09:45": 30, "10:15": 60}
STRUCTS = {"fly": pg.fly, "condor": pg.condor}
WALLETS = {"A 15k": 15000.0, "B 20k": 20000.0, "C 30k": 30000.0}


def atm(S, i):
    return int(round(S.F["c"][i] / M.STEP) * M.STEP)


def nights():
    by_day = {S.day: S for S in pg.all_sessions()}
    out = []
    for d, S in by_day.items():
        d2 = pg.next_trading_day(d)
        S2 = by_day.get(d2)
        if S2 is not None and S2.s["expiry"] == S.s["expiry"]:
            out.append((S, S2))
    return sorted(out, key=lambda p: p[0].day)


def short_trade(S_in, i, S_out, j, kind, stress):
    legs = STRUCTS[kind](atm(S_in, i))
    op = pg.structure_open(S_in, i, legs)
    if op is None:
        return None
    ml = pg.max_loss(op, kind)
    if ml <= 0:
        return None
    net = pg.structure_close(S_out, j, op, stress)
    return None if net is None else (net, ml)


def table(results, wallet):
    """results: {day: (net, max_loss) or None} -> loyo-ready per-year table (a trade only when max loss fits)."""
    per = {}
    for y in C.YEARS:
        xs = [r[0] for d, r in results.items() if d[:4] == y and r is not None and r[1] <= wallet]
        per[y] = {"net": round(sum(xs)), "green": sum(x > 0 for x in xs), "red": sum(x < 0 for x in xs), "trades": len(xs)}
    return per


def summarize(results, wallet=15000.0):
    xs = sorted((r[0] for r in results.values() if r is not None and r[1] <= wallet), reverse=True)
    return {"trades": len(xs), "total": round(sum(xs)), "without_best_5": round(sum(xs[5:])), "worst": round(min(xs)) if xs else 0,
            "mean": round(float(np.mean(xs))) if xs else 0}


if __name__ == "__main__":
    out_path = HERE / "results-sn124.json"
    if out_path.exists():
        raise SystemExit("SN124 is scored once")
    C.years()
    N = nights()
    print("eligible nights", len(N), flush=True)
    res = {"nights": len(N), "variants": {}, "day_leg": {}, "descriptions": {}}
    raw = {}
    for (kind, (en, j)), (sname, st) in itertools.product(itertools.product(STRUCTS, EXITS.items()), (("strict", 205.0), ("house", 100.0))):
        raw[(kind, en, sname)] = {S.day: short_trade(S, I1515, S2, j, kind, st) for S, S2 in N}
    day_leg = {(kind, sname): {S.day: short_trade(S, 5, S, I1515, kind, st) for S, _S2 in N}
               for kind in STRUCTS for sname, st in (("strict", 205.0), ("house", 100.0))}
    for sname in ("strict", "house"):
        tab = {f"{k} -> {en}": table(raw[(k, en, sname)], 15000.0) for k in STRUCTS for en in EXITS}
        Lr = C.loyo(tab, "profit")
        res["variants"][sname] = {"tables": tab, "loyo": Lr,
                                  "summaries": {f"{k} -> {en}": summarize(raw[(k, en, sname)]) for k in STRUCTS for en in EXITS}}
        res["day_leg"][sname] = {k: summarize(day_leg[(k, sname)]) for k in STRUCTS}
        print(f"=== SN124 overnight short [{sname}]")
        for k, s in res["variants"][sname]["summaries"].items():
            print(f"   {k:16s}", [tab[k][y]["net"] for y in C.YEARS], s, flush=True)
        print("   day leg (sold 09:20, bought 15:15):", res["day_leg"][sname])
        print("   LOYO", {y: (Lr[y]["pick"], Lr[y]["net"]) for y in C.YEARS}, "sum", Lr["sum"]["net"], flush=True)
    st_l = res["variants"]["strict"]["loyo"]
    picks = {y: st_l[y]["pick"] for y in C.YEARS}
    held_days = {}
    for y, p in picks.items():
        k, en = p.split(" -> ")
        for d, r in raw[(k, en, "strict")].items():
            if d[:4] == y and r is not None and r[1] <= 15000.0:
                held_days[d] = r[0]
    xs = sorted(held_days.values(), reverse=True)
    house_sum = res["variants"]["house"]["loyo"]["sum"]["net"]
    day_best = max(res["day_leg"]["strict"][k]["total"] for k in STRUCTS)
    held = [st_l[y]["net"] for y in C.YEARS]
    res["verdict"] = {"held_out_strict": st_l["sum"]["net"], "held_out_house": house_sum, "years": held,
                      "without_best_5": round(sum(xs[5:])), "worst_night": round(min(xs)) if xs else 0, "day_leg_best_total": day_best,
                      "PASS": bool(st_l["sum"]["net"] > 0 and house_sum > 0 and sum(x > 0 for x in held) >= 3 and sum(xs[5:]) > 0
                                   and st_l["sum"]["net"] > day_best)}
    res["wallets_heldout_strict"] = {w: sum(table({d: r for d, r in raw[(p.split(' -> ')[0], p.split(' -> ')[1], 'strict')].items() if d[:4] == y}, W)[y]["net"]
                                            for y, p in picks.items()) for w, W in WALLETS.items()}
    # descriptions: the long straddle overnight, and implied sigma overnight
    longs, ivs = [], []
    for S, S2 in N:
        K = atm(S, I1515)
        op = pg.structure_open(S, I1515, [(K, "CE", +1), (K, "PE", +1)])
        if op is not None:
            v = pg.structure_close(S2, 5, op, 205.0)
            if v is not None:
                longs.append(v)
        a, b = C.sigma_imp(S, I1515), C.sigma_imp(S2, 5)
        if a and b:
            ivs.append(b / a - 1)
    res["descriptions"] = {"long_straddle_overnight_strict": {"n": len(longs), "total": round(sum(longs)), "mean": round(float(np.mean(longs)))},
                           "implied_sigma_1515_to_0920_mean_change": round(float(np.mean(ivs)), 4), "n_iv": len(ivs)}
    res["heldout_day_nets"] = held_days
    print("VERDICT", res["verdict"], "| wallets", res["wallets_heldout_strict"], "| descriptions", res["descriptions"], flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
