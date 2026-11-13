"""SN157 - partner-speed momentum on hot days (PLAN.md; development evidence). 1-second archives A (Apr 6 - Jul 27)
and B (Jul 28 - Nov 12). Hot day: R_today at 10:00 from the 1-second index sampled each minute 09:20-10:00 and the
opening-ATM straddle (implied sigma with the index as the forward and weekdays to expiry as the session count);
causal top 20% over earlier archive days (>= 15). On hot days, 10:00-15:00, every 10 s: a fresh 60-second index move
>= k x the sigma of 60-second moves over the previous 30 minutes buys the opening-ATM leg in its direction (strike
within 100 points); sell h seconds later at the bid; one position at a time; Rs 3k room; strict. Grid k {2, 3} x
h {60, 180}: choose on A's hot days, score B's hot days once; controls: the same rule on B's cold days, random side."""
from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn131"))
import ph  # noqa: E402
import sn135  # noqa: E402

M = ph.M
S10, S15 = 2700, 20700


def weekdays_until(day, expiry):
    a, b = dt.date.fromisoformat(day), dt.date.fromisoformat(expiry)
    n, d = 0, a
    while d < b:
        d += dt.timedelta(days=1)
        n += d.weekday() < 5
    return n


def prep(day, rec):
    ser = rec["series"]
    if not all(k in ser for k in ("INDEX", "CE", "PE")):
        return None
    K, expiry = rec["meta"]["CE"][0], rec["meta"]["CE"][1][:10]
    ic = sn135.ffill(ser["INDEX"][3].astype(np.float64))
    oc = {o: ser[o][3].astype(np.float64) for o in ("CE", "PE")}
    om = {o: sn135.ffill(oc[o]) for o in oc}
    if np.isnan(ic[S10]) or np.isnan(om["CE"][S10]) or np.isnan(om["PE"][S10]):
        return None
    mins = ic[300: S10 + 1: 60]
    r = np.diff(np.log(mins))
    n = weekdays_until(day, expiry)
    tau = (375 - 46) + 375.0 * n + 125.0 * n
    s_imp = (om["CE"][S10] + om["PE"][S10]) / (0.7979 * ic[S10] * math.sqrt(tau))
    return {"K": K, "ic": ic, "oc": oc, "lp": {o: sn135.lastprint(oc[o]) for o in oc}, "R": float(np.std(r)) / s_imp}


def play(p, k, h, stress=205.0, side_flip=None, room=3000.0):
    ic, K = p["ic"], p["K"]
    realized, free, prev_hit, trades = 0.0, 0, False, 0
    for s in range(S10, S15 + 1, 10):
        m60 = ic[s] - ic[s - 60]
        hist = ic[s - 1800: s: 10] - ic[s - 1860: s - 60: 10]
        sd = float(np.nanstd(hist)) if len(hist) > 20 else np.nan
        hit = sd > 0 and abs(m60) >= k * sd
        fresh = hit and not prev_hit
        prev_hit = hit
        if not fresh or s < free or realized <= -room or abs(ic[s] - K) > 100:
            continue
        d = 1 if m60 > 0 else -1
        if side_flip is not None:
            d = d * side_flip(s)
        o = "CE" if d > 0 else "PE"
        if np.isnan(p["oc"][o][s]):
            continue
        ask = M.ask_of(float(p["oc"][o][s]))
        j = min(s + h, 22499)
        if j - p["lp"][o][j] > 10:
            continue
        b = M.bid_of(float(p["oc"][o][p["lp"][o][j]]))
        realized += (b - ask) * M.LOT - M.charges(ask, b, M.LOT) - stress
        trades += 1
        free = j + 10
    return realized, trades


if __name__ == "__main__":
    out_path = HERE / "results-sn157.json"
    if out_path.exists():
        raise SystemExit("SN157 is scored once")
    A = sn135.SD.load()["days"]
    sn135.SD.CACHE = HERE.parent / "2026-11-13-sn78" / "_local" / "seconds-1112.pkl"
    B = {d: v for d, v in sn135.SD.load()["days"].items() if d > "2026-07-27"}
    allp, hist, hot = {}, [], {}
    for d in sorted(set(A) | set(B)):
        p = prep(d, A.get(d) or B.get(d))
        if p is None:
            continue
        allp[d] = p
        hot[d] = len(hist) >= 15 and p["R"] >= float(np.quantile(hist, 0.8))
        hist.append(p["R"])
    a_hot = [d for d in allp if d in A and hot[d]]
    b_hot = [d for d in allp if d in B and hot[d]]
    b_cold = [d for d in allp if d in B and not hot[d]]
    grid = list(itertools.product((2.0, 3.0), (60, 180)))
    choose = {f"k{k} h{h}": sum(play(allp[d], k, h)[0] for d in a_hot) for k, h in grid}
    pick = max(choose, key=choose.get)
    k, h = next((k, h) for k, h in grid if f"k{k} h{h}" == pick)
    score = [play(allp[d], k, h) for d in b_hot]
    cold = [play(allp[d], k, h) for d in b_cold]
    rng = np.random.default_rng(157)
    rnd = [sum(play(allp[d], k, h, side_flip=lambda s, r=rng: 1 if r.random() < 0.5 else -1)[0] for d in b_hot) for _ in range(200)]
    s400 = sum(play(allp[d], k, h, stress=400.0)[0] for d in b_hot)
    nets = [x for x, _t in score]
    res = {"a_hot_days": len(a_hot), "b_hot_days": len(b_hot), "b_cold_days": len(b_cold), "choose": {k_: round(v) for k_, v in choose.items()},
           "pick": pick, "b_hot": {"net": round(sum(nets)), "trades": sum(t for _x, t in score), "won_days": sum(x > 0 for x in nets),
                                  "without_best_5_days": round(sum(sorted(nets, reverse=True)[5:]))},
           "b_cold_same_rule": {"net": round(sum(x for x, _t in cold)), "trades": sum(t for _x, t in cold)},
           "random_side_mean": round(float(np.mean(rnd))), "random_side_95th": round(float(np.percentile(rnd, 95))), "stress_400": round(s400)}
    res["PASS_development"] = bool(res["b_hot"]["net"] > 0 and res["b_hot"]["net"] > res["random_side_95th"] and s400 > 0
                                   and res["b_hot"]["without_best_5_days"] > 0)
    print("SN157", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
