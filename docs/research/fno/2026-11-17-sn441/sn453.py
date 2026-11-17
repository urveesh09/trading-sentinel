"""SN453 (own): SN443's discount rule on Gold's own stream inside the Rs 30k wallet (Breeze minutes) (PLAN.md section 2,
frozen at f56f5807; details fixed here before any number). Pass = better than DEPLOYED in 2022 and 2023-26 at Rs 205 and 400.

Gold v5 as deployed; only the entry changes. common.gold_one picks the strike, lots and decision ask a0 at minute i as usual
(the replay's model ask of that minute's close), then:
  DEPLOYED                as shipped
  DELAY-k (k = 1, 3, 5)   gold_one's own `late` option: the entry k minutes later at that minute's model ask (SN409's wiring)
  PLAIN-5                 the first minute t in i+1 .. i+5 with a quote whose model ask <= a0 - D, while the premise holds
  DISCOUNT-5              the same with model ask <= a0 + delta x (F_t - F_i) - D
  DISCOUNT-OR-MARKET-5    DISCOUNT-5; if no fill by i+5 and the premise holds, buy at i+5's model ask (no fill -> missed)
  premise   fails on a 0.10% adverse move of the future's close from minute i (checked first at each minute; cancels)
  delta     (V_K - K (V_{K+50} - V_{K-50}) / 100) / F from the neighbours' closes at i, kept if 0.05 <= |delta| <= 0.98 with
            the right sign; otherwise NO_DELTA and DISCOUNT arms enter at i as deployed (counted)
  D         1.5 x the model spread at a0's close (M.spread_for), so a bid-ask bounce alone cannot trigger it
Lots are re-fitted to the wallet at the fill price; Gold's exit minute is unchanged (at least one minute after the fill).
A missed signal frees the wallet for Gold's later signals that day, as in the wallet runner.
Reported: net, trades, fill states, the mean improvement per lot on fills, worst month, months positive.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn411"))
import gold  # noqa: E402

OUT = HERE / "results-sn453.json"
gw = gold.T.Q.gw
Lb = gold.L
M = Lb.M
STATE = {"arm": None, "states": collections.Counter(), "impr": []}


def disc_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss):
    i = sg["i"]
    lots = Lb.size(S, sg, v, full_lots, ctx, vol_day)
    strike = sg["strike"]
    step = M.STEP if sg["opt"] == "CE" else -M.STEP
    per_lot = wallet / max(1, lots)
    casc = 1 if per_lot < v["itm_auto"][0] else (2 if per_lot < v["itm_auto"][1] else 3)
    for dep in range(casc, 0, -1):
        k_itm = sg["strike"] - dep * step
        r_itm = Lb.quote(S, k_itm, sg["opt"], i)
        if r_itm is not None and M.ask_of(float(r_itm[0][3][i])) * M.LOT * lots <= wallet * v.get("itm_share", 1.0):
            strike = k_itm
            break
    got = Lb.affordable(S, i, strike, sg["opt"], wallet)
    if got is None:
        return None
    rec, a0, strike = got
    lots = min(lots, max(1, int(wallet // (a0 * M.LOT))))
    d = 1 if sg["opt"] == "CE" else -1
    arm = STATE["arm"]
    fut = np.asarray(S.s["future"][3], dtype=np.float64)
    F0 = fut[i]
    c0 = float(rec[0][3][i])
    D = 1.5 * M.spread_for(c0)
    delta = None
    lo, hi = Lb.quote(S, strike - M.STEP, sg["opt"], i), Lb.quote(S, strike + M.STEP, sg["opt"], i)
    if lo is not None and hi is not None and np.isfinite(F0):
        dd = (c0 - strike * (float(hi[0][3][i]) - float(lo[0][3][i])) / (2 * M.STEP)) / F0
        if 0.05 <= abs(dd) <= 0.98 and np.sign(dd) == d:
            delta = float(dd)
    i_f, a_f = None, None
    if arm.startswith("DISCOUNT") and delta is None:
        STATE["states"]["NO_DELTA"] += 1
        i_f, a_f = i, a0
    else:
        why = "WINDOW_END"
        for t in range(i + 1, min(i + 6, M.EXIT_MIN)):
            F = fut[t]
            if np.isfinite(F) and np.isfinite(F0) and d * (F - F0) / F0 <= -0.0010:
                why = "PREMISE_FAILED"
                break
            r_t = Lb.quote(S, strike, sg["opt"], t)
            if r_t is None:
                continue
            a_t = M.ask_of(float(r_t[0][3][t]))
            lim = a0 - D if arm == "PLAIN-5" else (a0 + delta * (F - F0) - D if np.isfinite(F) else -1.0)
            if a_t <= lim + 1e-9:
                i_f, a_f, why = t, a_t, "FILLED"
                break
            if arm == "DISCOUNT-OR-MARKET-5" and t == i + 5:
                i_f, a_f, why = t, a_t, "MARKET_AT_5"
        STATE["states"][why] += 1
    if i_f is None:
        return None
    if a_f * M.LOT > wallet:
        STATE["states"]["UNAFFORDABLE_AT_FILL"] += 1
        return None
    STATE["impr"].append((a0 - a_f) * M.LOT)
    lots = min(lots, max(1, int(wallet // (a_f * M.LOT))))
    net, j, px = Lb.walk(S, rec, a_f, lots, i_f, min(max(sg["j"], i_f + 1), M.EXIT_MIN), d, v, loss + realized, wallet)
    net += Lb.side_legs(S, i_f, j, d, strike, v)
    return net, j, lots, a_f, px, strike


def main():
    if OUT.exists():
        raise SystemExit("SN453 is run once")
    gold.install()
    orig_one = gw._ORIG["gold_one"]
    res = {}
    for p, years in (("2022", gold.Y22), ("2023-2026", gold.Y2326)):
        for st in (205.0, 400.0):
            for arm in ("DEPLOYED", "DELAY-1", "DELAY-3", "DELAY-5", "PLAIN-5", "DISCOUNT-5", "DISCOUNT-OR-MARKET-5"):
                STATE.update(arm=arm, states=collections.Counter(), impr=[])
                vx = {"late": int(arm[-1])} if arm.startswith("DELAY") else {}
                if arm in ("PLAIN-5", "DISCOUNT-5", "DISCOUNT-OR-MARKET-5"):
                    gw._ORIG["gold_one"] = disc_one
                try:
                    days, log, _ = gold.run(years, gold.DEPLOYED, st, **vx)
                finally:
                    gw._ORIG["gold_one"] = orig_one
                s = gold.summary(days, log)
                s["states"] = dict(STATE["states"])
                s["mean_improvement_per_lot_on_fills"] = round(float(np.mean(STATE["impr"])), 1) if STATE["impr"] else None
                res[f"{arm} | {p} @{int(st)}"] = s
                print(arm, p, int(st), s["net"], s["trades"], s["worst_month"], s["months_positive"], s["states"], s["mean_improvement_per_lot_on_fills"], flush=True)
    assert res["DEPLOYED | 2023-2026 @205"]["net"] in (850882, 850883)
    res["pass"] = {a: all(res[f"{a} | {p} @{s}"]["net"] > res[f"DEPLOYED | {p} @{s}"]["net"] for p in ("2022", "2023-2026") for s in (205, 400))
                   for a in ("DELAY-1", "DELAY-3", "DELAY-5", "PLAIN-5", "DISCOUNT-5", "DISCOUNT-OR-MARKET-5")}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(res["pass"])


if __name__ == "__main__":
    main()
