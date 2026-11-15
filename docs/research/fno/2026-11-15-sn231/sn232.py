"""SN232 - bad-month anatomy (PLAN.md). Per month of the account window: each leg (Gold v5 trade days, green / red, worst
day; WK-H weeks, worst week, hedge orders and costs, implied / realised volatility of its weeks) and the market (realised
volatility, mean intraday range, gaps, trend efficiency, 1% days). Bad months vs good months: means and the rank
correlation of each measure with the account's month."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import led  # noqa: E402

wk = led.wk


def daily_bars():
    D = wk.dev_data()
    out = {}
    for d, a in D["idx"].items():
        v = a[~np.isnan(a)]
        if len(v) >= 200:
            out[d] = (float(v[0]), float(v.max()), float(v.min()), float(v[-1]))
    return out


def week_vol(t, data):
    """(implied sigma per session from the entry straddle, realised sd of its 15:15-to-15:15 log moves, incl. settlement)."""
    k = t["k"]
    t0 = (375 - 360) / 375.0 + (k - 1) + 360 / 375.0 + 0.15 * k
    s0 = t.get("S0") or wk.idx_px(data, t["entry"])     # post-run fix (disclosed): wk3 trade rows carry no S0
    sig = t["Q"] / (0.7979 * s0 * math.sqrt(t0)) if s0 else None
    pts = [wk.idx_px(data, d) for d in sorted(t["marks"]) if d < t["expiry"]]
    st = wk.settle_px(data, t["expiry"])
    pts = [p for p in pts if p] + ([st] if st else [])
    r = np.diff(np.log(pts)) if len(pts) > 1 else np.zeros(0)
    return sig, (float(np.sqrt(np.mean(r * r))) if len(r) else None)


def spearman(x, y):
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])


if __name__ == "__main__":
    out_path = HERE / "results-sn232.json"
    if out_path.exists():
        raise SystemExit("SN232 is run once")
    days = led.sessions()
    g, h = led.gold(), led.wkh_days()
    ma = led.months({d: g.get(d, 0.0) + h.get(d, 0.0) for d in days}, days)
    bars = daily_bars()
    alld = sorted(bars)
    D = wk.dev_data()
    trades = [t for t in led.wkh_trades("DEV") + led.wkh_trades("TEST") if led.LO <= t["exit_day"] < led.HI]
    rows = {}
    for m in sorted(ma):
        md = [d for d in days if d[:7] == m]
        prev = [d for d in alld if d < md[0]]
        p0 = bars[prev[-1]][3] if prev else bars[md[0]][0]
        closes = [p0] + [bars[d][3] for d in md if d in bars]
        lr = np.diff(np.log(closes))
        gaps = [abs(bars[d][0] / bars[alld[alld.index(d) - 1]][3] - 1) for d in md if d in bars and alld.index(d) > 0]
        rng = [(bars[d][1] - bars[d][2]) / bars[d][3] for d in md if d in bars]
        path = float(np.sum(np.abs(np.diff(closes))))
        gd = [g.get(d, 0.0) for d in md]
        mw = [t for t in trades if t["exit_day"][:7] == m]
        vols = [week_vol(t, D) for t in mw]
        ivrv = [a / b for a, b in vols if a and b]
        rows[m] = {
            "gold_v6": round(ma[m]), "gold": round(sum(gd)), "gold_trade_days": sum(x != 0 for x in gd), "gold_green": sum(x > 0 for x in gd),
            "gold_red": sum(x < 0 for x in gd), "gold_worst_day": round(min(gd)) if gd else 0,
            "wkh": round(sum(t["net"] for t in mw)), "wkh_weeks": len(mw), "wkh_losing_weeks": sum(t["net"] < 0 for t in mw),
            "wkh_worst_week": round(min((t["net"] for t in mw), default=0.0)), "wkh_orders": sum(t["orders"] for t in mw),
            "wkh_hedge_costs": round(sum(t["hedge_costs"] for t in mw)),
            "wkh_implied_over_realised": round(float(np.mean(ivrv)), 3) if ivrv else None,
            "wkh_premium_pct": round(float(np.mean([t["Q"] / wk.idx_px(D, t["entry"]) * 100 for t in mw if wk.idx_px(D, t["entry"])])), 3) if mw else None,
            "rv_ann_pct": round(float(np.std(lr, ddof=1) * math.sqrt(252) * 100), 2) if len(lr) > 2 else None,
            "range_pct": round(float(np.mean(rng)) * 100, 3), "gap_pct": round(float(np.mean(gaps)) * 100, 3) if gaps else None,
            "gaps_over_0.75pct": sum(x > 0.0075 for x in gaps), "days_over_1pct": int(np.sum(np.abs(lr) > 0.01)),
            "trend_efficiency": round(abs(closes[-1] - closes[0]) / path, 3) if path else None,
            "month_return_pct": round((closes[-1] / closes[0] - 1) * 100, 2)}
    bad = [m for m in rows if rows[m]["gold_v6"] < 0]
    good = [m for m in rows if rows[m]["gold_v6"] >= 0]
    feats = [k for k in rows[next(iter(rows))] if k not in ("gold_v6",)]
    comp = {}
    for f in feats:
        xb = [rows[m][f] for m in bad if rows[m][f] is not None]
        xg = [rows[m][f] for m in good if rows[m][f] is not None]
        xs = [(rows[m][f], rows[m]["gold_v6"]) for m in rows if rows[m][f] is not None]
        comp[f] = {"bad_mean": round(float(np.mean(xb)), 3) if xb else None, "good_mean": round(float(np.mean(xg)), 3) if xg else None,
                   "rank_corr_with_month": round(spearman([a for a, _ in xs], [b for _, b in xs]), 3) if len(xs) > 3 else None}
    res = {"months": rows, "bad": bad, "compare": comp}
    for m in bad:
        r = rows[m]
        print(f"SN232 BAD {m}: v6 {r['gold_v6']:>8} | Gold {r['gold']:>8} ({r['gold_trade_days']} trade days, {r['gold_green']}+/{r['gold_red']}-, worst {r['gold_worst_day']}) "
              f"| WK-H {r['wkh']:>8} ({r['wkh_weeks']} wk, {r['wkh_losing_weeks']} lost, worst {r['wkh_worst_week']}, orders {r['wkh_orders']}, costs {r['wkh_hedge_costs']}, "
              f"IV/RV {r['wkh_implied_over_realised']}, prem {r['wkh_premium_pct']}%) | mkt RV {r['rv_ann_pct']}% range {r['range_pct']}% "
              f"eff {r['trend_efficiency']} ret {r['month_return_pct']}% 1%days {r['days_over_1pct']}", flush=True)
    for f, c in comp.items():
        print(f"SN232 compare {f:28s} bad {c['bad_mean']} good {c['good_mean']} rank_corr {c['rank_corr_with_month']}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
