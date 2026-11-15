"""SN229 - wallets, lots and the account (PLAN.md). After SN228 (the exam is now seen; nothing here is re-selected).
1. Margin: the PICK (STRADDLE kM settle H15x2) needs 2 option lots, so one unit = Rs 5 lakh at the PLAN's Rs 2.5 lakh per
   option lot (an SN204 proxy, not verified on Zerodha). Wallets Rs 15k / 30k / 1 lakh / 2.5 lakh / 5 lakh / 10 lakh:
   units = floor(wallet / 5 lakh); growing = +1 unit after net profit equal to one unit's margin (cap 3). For Rs 2.5 lakh
   the 1-lot hedge (STRADDLE kM settle H15) is shown as information.
2. Gold v5 (Rs 30k growing, production) + the PICK at Rs 5 lakh (raw, 2 lots) in one account, DEV Jan 2 2023 - Aug 19 2026
   (SN207's window and summary); the PICK on Gold's empty days; correlation.
3. Per wallet on each sample, including the exam (raw rupees)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wk3  # noqa: E402

wk = wk3.wk
sys.path.insert(0, str(wk.HERE))
import sn207  # noqa: E402

PICK = ("STRADDLE", "M", "settle", "H15x2", "none")
ONE_LOT = ("STRADDLE", "M", "settle", "H15", "none")
UNIT = 500000.0
WALLETS = (15000, 30000, 100000, 250000, 500000, 1000000)
SAMPLES = wk3.SEEN + ("EXAM",)


def daily(t):
    out, prev = {}, 0.0
    for d in sorted(t["marks"]):
        if d > t["exit_day"]:
            break
        out[d] = t["marks"][d] - prev
        prev = t["marks"][d]
    return out


def growing(trades, units0):
    """Weekly chronological ledger with +1 unit after profit equal to one unit's margin (cap 3); per-unit trade nets."""
    units, bank, step_profit, steps = units0, 0.0, 0.0, 0
    for t in sorted(trades, key=lambda t: t["expiry"]):
        x = t["net"] * units
        bank += x
        step_profit += x
        if units < 3 and step_profit >= UNIT:
            units += 1
            steps += 1
            step_profit = 0.0
    return {"net": round(bank), "units_end": units, "steps": steps}


if __name__ == "__main__":
    out_path = HERE / "results-sn229.json"
    if out_path.exists():
        raise SystemExit("SN229 is run once")
    wk3.UNSEAL_EXAM = True
    res = {"unit_margin_rs": UNIT, "wallets": {}, "one_lot_H15_information": {}, "account": {}}
    books = {n: wk3.book3(wk3.sample(n), *PICK) for n in SAMPLES}
    for n in SAMPLES:
        s = wk3.sample(n)
        r1 = wk3.summary(wk3.book3(s, *ONE_LOT), s.W)
        res["one_lot_H15_information"][n] = {k: r1[k] for k in ("net", "trades", "worst", "worst_month", "by_year")}
        print("SN229 one-lot H15", n, json.dumps(res["one_lot_H15_information"][n]), flush=True)
    yrs = {"DEV": 229 / 52.0, "TEST": 9 / 52.0, "N2122": 17 / 52.0, "SENSEX": 83 / 52.0, "EXAM": 60 / 52.0}
    for w in WALLETS:
        u = int(w // UNIT)
        row = {"units": u}
        for n in SAMPLES:
            tr = books[n]
            net = sum(t["net"] for t in tr) * u
            row[n] = {"fixed_net": round(net), "per_year_pct": round(100 * net / yrs[n] / w, 1) if u else 0.0,
                      "per_week": round(net / wk3.sample(n).W), "growing": growing(tr, u) if u else None}
        res["wallets"][f"Rs {w:,}"] = row
        print("SN229 wallet", f"Rs {w:,}", json.dumps(row), flush=True)
    import p4
    D = wk.dev_data()
    days = sorted(d for d in D["idx"] if sn207.LO <= d < sn207.HI)
    gold = p4.gold("Rs 30k growing (production)")
    leg = {}
    for t in books["DEV"]:
        for d, x in daily(t).items():
            if sn207.LO <= d < sn207.HI:
                leg[d] = leg.get(d, 0.0) + x
    both = {d: gold.get(d, 0.0) + leg.get(d, 0.0) for d in days}
    res["account"]["Gold alone"] = sn207.summary(gold, days)
    res["account"]["PICK alone (Rs 5 lakh, 2 lots)"] = sn207.summary(leg, days)
    res["account"]["Gold + PICK"] = sn207.summary(both, days)
    half = {d: gold.get(d, 0.0) + leg.get(d, 0.0) / 2 for d in days}
    res["account"]["Gold + PICK per option lot (comparable with SN207's Gold + WK-S)"] = sn207.summary(half, days)
    empty = [d for d in days if not gold.get(d)]
    xe = np.array([leg.get(d, 0.0) for d in empty])
    res["account"]["PICK on Gold's empty days"] = {"days": len(empty), "mean_per_day": round(float(xe.mean()), 1),
                                                   "green_share_pct": round(float((xe > 0).mean() * 100), 1),
                                                   "days_with_position": int((xe != 0).sum())}
    g = np.array([gold.get(d, 0.0) for d in days])
    l_ = np.array([leg.get(d, 0.0) for d in days])
    tdays = g != 0
    res["account"]["correlation"] = {"all_days": round(float(np.corrcoef(g, l_)[0, 1]), 3),
                                     "gold_trade_days": round(float(np.corrcoef(g[tdays], l_[tdays])[0, 1]), 3)}
    for k, v in res["account"].items():
        print("SN229 account", k, json.dumps(v), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
