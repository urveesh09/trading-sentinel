"""SN233 - WK-H's losing weeks on the five WK samples (PLAN.md), per option lot. For every week: options vs futures-hedge
result, hedge charges, the largest overnight gap held, the move after the 14:30 expiry-day freeze (index 14:30 ->
settlement, in units of the entry straddle Q) and what it cost, realised / implied. Each losing week gets one cause, in this
order: "hedge charges" (the week was positive before the futures charges), "after the freeze" (the 14:30 -> settlement
part lost more than the whole week), "gap" (a held overnight gap >= 0.75%), "moves above implied" (realised / implied >= 1.2),
else "other". Totals per cause and sample."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import led  # noqa: E402

wk, wk3 = led.wk, led.wk3
FREEZE_J = 315


def fut_at(s, e, d, j):
    F = s.fut.series(e, d)
    a = s.data["idx"].get(d)
    if F is not None and F[j] == F[j]:
        return float(F[j])
    if a is not None and a[j] == a[j] and F is not None:
        ok = ~np.isnan(F) & ~np.isnan(a)
        if ok.any():
            return float(a[j] + (F[ok] - a[ok]).mean())
    return None


def week_row(s, t):
    e, d0, L, lot = t["expiry"], t["entry"], 2, s.mk["lot"]
    base = wk3.base_trade(s, e, dict(s.weeks)[e], "STRADDLE", "M")
    H = s.hpaths[(e, "STRADDLE", "M", "H15x2")]
    opt, hedge = L * base["marks"][e], H["settle"]
    K, Q = base["K0"], base["Q"]
    days = [d for d in dict(s.weeks)[e] if d >= d0] + [e]
    gaps = []
    for a_, b_ in zip(days, days[1:]):
        pa, pb = s.data["idx"].get(a_), s.data["idx"].get(b_)
        if pa is not None and pb is not None:
            c = pa[~np.isnan(pa)]
            o = pb[~np.isnan(pb)]
            if len(c) and len(o):
                gaps.append(abs(o[0] / c[-1] - 1))
    S1430 = wk.idx_px(s.data, e, FREEZE_J)
    ST = wk.settle_px(s.data, e)
    f1430 = fut_at(s, e, e, FREEZE_J)
    ftw = [fut_at(s, e, e, j) for j in range(345, 375)]
    ftw = [x for x in ftw if x is not None]
    after = None
    if S1430 and ST and f1430 and ftw:
        opt_after = -L * lot * (abs(ST - K) - abs(S1430 - K))           # intrinsic change; time value at 14:30 is small
        hedge_after = H["end_lots"] * lot * (float(np.mean(ftw)) - f1430)
        after = opt_after + hedge_after
    pts = [wk.idx_px(s.data, d) for d in days[:-1]] + [ST]
    pts = [p for p in pts if p]
    r = np.diff(np.log(pts)) if len(pts) > 1 else np.zeros(0)
    k = base["k"]
    t0 = (375 - 360) / 375.0 + (k - 1) + 360 / 375.0 + 0.15 * k
    S0 = base.get("S0") or wk.idx_px(s.data, d0) or K
    sig = Q / (0.7979 * S0 * math.sqrt(t0))
    rv_iv = float(np.sqrt(np.mean(r * r))) / sig if len(r) else None
    return {"expiry": e, "net_per_lot": t["net"] / L, "options_per_lot": opt / L, "hedge_per_lot": hedge / L,
            "hedge_charges_per_lot": t["hedge_costs"] / L, "orders": t["orders"], "max_gap_pct": round(max(gaps) * 100, 2) if gaps else 0.0,
            "after_freeze_per_lot": None if after is None else after / L,
            "after_freeze_move_q": None if not (S1430 and ST) else round((ST - S1430) / Q, 2), "end_lots": H["end_lots"],
            "rv_over_iv": None if rv_iv is None else round(rv_iv, 2), "Q_pct": round(Q / S0 * 100, 3)}


def cause(w):
    if w["net_per_lot"] + w["hedge_charges_per_lot"] > 0:
        return "hedge charges"
    if w["after_freeze_per_lot"] is not None and w["after_freeze_per_lot"] < w["net_per_lot"]:
        return "after the freeze"
    if w["max_gap_pct"] >= 0.75:
        return "gap"
    if w["rv_over_iv"] is not None and w["rv_over_iv"] >= 1.2:
        return "moves above implied"
    return "other"


if __name__ == "__main__":
    out_path = HERE / "results-sn233.json"
    if out_path.exists():
        raise SystemExit("SN233 is run once")
    res = {}
    for n in led.WK_SAMPLES:
        s = led.sample(n)
        trades = led.wkh_trades(n)
        rows = [week_row(s, t) for t in trades]
        lost = [w for w in rows if w["net_per_lot"] < 0]
        for w in lost:
            w["cause"] = cause(w)
        by = {}
        for w in lost:
            c = by.setdefault(w["cause"], {"weeks": 0, "loss": 0.0})
            c["weeks"] += 1
            c["loss"] += w["net_per_lot"]
        allr = {"weeks": len(rows), "net": round(sum(w["net_per_lot"] for w in rows)),
                "options": round(sum(w["options_per_lot"] for w in rows)), "hedge": round(sum(w["hedge_per_lot"] for w in rows)),
                "hedge_charges": round(sum(w["hedge_charges_per_lot"] for w in rows)),
                "after_freeze_total": round(sum(w["after_freeze_per_lot"] or 0.0 for w in rows)),
                "losing_weeks": len(lost), "loss_in_losing_weeks": round(sum(w["net_per_lot"] for w in lost)),
                "by_cause": {k: {"weeks": v["weeks"], "loss": round(v["loss"])} for k, v in by.items()}}
        res[n] = {"summary": allr, "losing_weeks": sorted(lost, key=lambda w: w["net_per_lot"])}
        print("SN233", n, json.dumps(allr), flush=True)
        for w in res[n]["losing_weeks"][:5]:
            print(f"SN233   {n} {w['expiry']} net {w['net_per_lot']:>8.0f} options {w['options_per_lot']:>8.0f} hedge {w['hedge_per_lot']:>8.0f} "
                  f"charges {w['hedge_charges_per_lot']:>6.0f} gap {w['max_gap_pct']}% after-freeze {w['after_freeze_per_lot'] if w['after_freeze_per_lot'] is None else round(w['after_freeze_per_lot'])} "
                  f"({w['after_freeze_move_q']} Q, end lots {w['end_lots']}) rv/iv {w['rv_over_iv']} -> {w['cause']}", flush=True)
    tot = {}
    for n in res:
        for k, v in res[n]["summary"]["by_cause"].items():
            c = tot.setdefault(k, {"weeks": 0, "loss": 0})
            c["weeks"] += v["weeks"]
            c["loss"] += v["loss"]
    res["all samples by cause"] = tot
    print("SN233 all samples by cause", json.dumps(tot), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
