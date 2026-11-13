"""SN109 - the real execution hurdle (PLAN.md): NIFTY option quotes (both archived expiries, usable depth only) against
the simulator's spread model; the cost of 1 / 2 / 3 / 6 lots walking the 5 levels; quote age; 1-minute mid moves; and
Gold v5's own research trades inside the archive (Sep 10 - Oct 28): real entry ask / exit bid vs the model's.
No cost gate changes follow from this."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pa  # noqa: E402
import qa  # noqa: E402

C, M = pa.C, pa.M
PB = (0, 50, 100, 150, 200, 300, 450, 1e9)
CLOCK = (("09:15-09:45", 0, 30), ("09:45-12:00", 30, 165), ("12:00-14:00", 165, 285), ("14:00-15:30", 285, 375))
LOTS = (1, 2, 3, 6)


def pbucket(m):
    for a, b in zip(PB, PB[1:]):
        if a <= m < b:
            return f"{int(a)}-{int(b) if b < 1e8 else 'up'}"


if __name__ == "__main__":
    out_path = HERE / "results-sn109.json"
    if out_path.exists():
        raise SystemExit("SN109 is scored once")
    acc = collections.defaultdict(lambda: {"real": [], "model": [], "n": 0})
    clock_acc = collections.defaultdict(list)
    impact = {n: {"buy": [], "sell": [], "thin": 0, "n": 0} for n in LOTS}
    ages, dmid = [], []
    lot_seen = set()
    expiries = sorted(qa.manifest()["option_expiries"]["NIFTY"])
    for day in qa.days():
        q = qa.load(day)
        lot = q["lot"]["NIFTY"]
        lot_seen.add(lot)
        later = [e for e in expiries if e >= day][:2]
        for (und, exp, strike, opt), r in q["opt"].items():
            if und != "NIFTY" or exp not in later:
                continue
            ok = r["usable"] & ~np.isnan(r["bid"]) & ~np.isnan(r["ask"])
            for i in np.flatnonzero(ok):
                if i > 374:
                    continue
                mid = (r["bid"][i] + r["ask"][i]) / 2
                if mid < 5:
                    continue
                spr = r["ask"][i] - r["bid"][i]
                b = pbucket(mid)
                acc[b]["real"].append(spr)
                acc[b]["model"].append(M.spread_for(mid))
                for cn, a0, a1 in CLOCK:
                    if a0 <= i < a1:
                        clock_acc[cn].append(spr / max(M.spread_for(mid), 0.05))
                if not np.isnan(r["age"][i]):
                    ages.append(r["age"][i])
                if i + 1 < qa.NM and ok[i + 1]:
                    dmid.append(abs((r["bid"][i + 1] + r["ask"][i + 1]) / 2 - mid) * lot)
                if 30 <= i <= 330 and 50 <= mid <= 300:
                    for n in LOTS:
                        impact[n]["n"] += 1
                        bp = qa.walk_cost(r["askp"][:, i], r["askq"][:, i], n * lot)
                        sp = qa.walk_cost(r["bidp"][:, i], r["bidq"][:, i], n * lot)
                        if bp is None or sp is None:
                            impact[n]["thin"] += 1
                            continue
                        impact[n]["buy"].append((bp - mid) * lot)        # rupees per lot above mid
                        impact[n]["sell"].append((mid - sp) * lot)
    spread_table = {b: {"quotes": len(v["real"]), "real_median": round(float(np.median(v["real"])), 2),
                        "real_p75": round(float(np.percentile(v["real"], 75)), 2), "model": round(float(np.median(v["model"])), 2),
                        "real_mean_over_model_mean": round(float(np.mean(v["real"]) / np.mean(v["model"])), 2)}
                    for b, v in sorted(acc.items(), key=lambda kv: float(kv[0].split("-")[0]))}
    clock_table = {k: round(float(np.median(v)), 2) for k, v in clock_acc.items()}
    impact_table = {n: {"minutes": d["n"], "too_thin_share": round(d["thin"] / max(1, d["n"]), 3),
                        "buy_above_mid_per_lot_median": round(float(np.median(d["buy"])), 1) if d["buy"] else None,
                        "sell_below_mid_per_lot_median": round(float(np.median(d["sell"])), 1) if d["sell"] else None,
                        "round_trip_vs_mid_per_lot_median": round(float(np.median(d["buy"]) + np.median(d["sell"])), 1) if d["buy"] else None,
                        "round_trip_p90": round(float(np.percentile(d["buy"], 90) + np.percentile(d["sell"], 90)), 1) if d["buy"] else None}
                    for n, d in impact.items()}
    print("lot sizes seen", lot_seen)
    print("SPREAD real vs model by premium", json.dumps(spread_table, indent=0), flush=True)
    print("real/model spread ratio by clock (median)", clock_table)
    print("IMPACT walking 5 levels (rupees per lot vs mid, premium 50-300, 09:45-14:45)", json.dumps(impact_table, indent=0), flush=True)
    lat = {"quote_age_median_s": round(float(np.median(ages)), 2), "quote_age_p95_s": round(float(np.percentile(ages, 95)), 2),
           "one_minute_abs_mid_move_per_lot_median": round(float(np.median(dmid)), 1),
           "one_minute_abs_mid_move_per_lot_mean": round(float(np.mean(dmid)), 1)}
    print("LATENCY", lat, flush=True)
    # Gold v5's own research trades inside the archive
    C.RECORD[0] = True
    C.TRADES.clear()
    C.run(C.V5, wallets=(C.STD_WALLETS[0],))
    C.RECORD[0] = False
    qdays = set(qa.days())
    gold = []
    Ys = C.years()
    for t in C.TRADES:
        if t["day"] not in qdays:
            continue
        q = qa.load(t["day"])
        S = Ys[t["day"][:4]].sessions[t["day"]]
        r = q["opt"].get(("NIFTY", S.s["expiry"], t["strike"], t["opt"]))
        if r is None:
            gold.append({"day": t["day"], "missing": True})
            continue
        ie = qa.first_at(r, t["i"])
        jx = qa.last_before(r, t["j"], t["i"] + 1)
        if ie is None or jx is None or ie > t["i"] + 1:
            gold.append({"day": t["day"], "missing": True})
            continue
        qty = t["lots"] * M.LOT
        model_bid_exit = t["px"]
        gold.append({"day": t["day"], "expert": t["expert"], "lots": t["lots"], "model_ask": t["ask"], "real_ask": float(r["ask"][ie]),
                     "model_exit": model_bid_exit, "real_exit_bid": float(r["bid"][jx]),
                     "entry_diff_per_lot": round((float(r["ask"][ie]) - t["ask"]) * M.LOT, 1),
                     "exit_diff_per_lot": round((model_bid_exit - float(r["bid"][jx])) * M.LOT, 1)})
    priced = [g for g in gold if not g.get("missing")]
    gsum = {"trades_in_archive": len(gold), "priced": len(priced),
            "mean_entry_real_minus_model_per_lot": round(float(np.mean([g["entry_diff_per_lot"] for g in priced])), 1) if priced else None,
            "mean_exit_model_minus_real_per_lot": round(float(np.mean([g["exit_diff_per_lot"] for g in priced])), 1) if priced else None}
    print("GOLD v5 TRADES vs REAL QUOTES", gsum, flush=True)
    for g in priced:
        print("   ", g)
    out_path.write_text(json.dumps({"lot_sizes": sorted(lot_seen), "spread": spread_table, "spread_ratio_by_clock": clock_table,
                                    "impact": impact_table, "latency": lat, "gold_trades": gold, "gold_summary": gsum},
                                   indent=1, default=float), encoding="utf-8")
