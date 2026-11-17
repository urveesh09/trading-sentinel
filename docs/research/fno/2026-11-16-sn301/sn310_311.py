"""SN310 (Gold v5's loss waterfall) and SN311 (the scale-in cash test), PLAN.md frozen at 94c772cd.

Gold v5 at Rs 30,000 growing (stop 3), Jan 2023 - Oct 28 2026, through ow.run_wallet (SN252's parity player):
  1. parity: the instrumented walk (gw.py, cash "mtm") reproduces the lab's day nets to Rs 0.01 and the panel net;
  2. SN310: every trade attributed (first piece, added piece, extension, stop overshoot, marked exits, by expert / side);
  3. SN311: G0 (mtm, Gold v5), G1 (both), G2 (debit) at Rs 205 and Rs 400 stress, whole period and both halves, and the
     frozen decision rule."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gw  # noqa: E402

ow, C, L = gw.ow, gw.C, gw.L
HALVES = (("2023-24", "2023-01-01", "2025-01-01"), ("2025-26", "2025-01-01", "2027-01-01"))


def run(cash=None, stress=205.0):
    v = dict(C.V5)
    if cash:
        v["cash"] = cash
    old = L.STRESS
    L.STRESS = stress
    gw.LOG.clear()
    try:
        row, days, _ = ow.run_wallet(v, ow.GOLD_30K, None)
    finally:
        L.STRESS = old
    return row, days, list(gw.LOG)


def metrics(row, days, log, lo="0000", hi="9999"):
    dd = [(d, n) for d, _w, n, _t, _l in days if lo <= d < hi]
    months = collections.defaultdict(float)
    for d, n in dd:
        months[d[:7]] += n
    cum = np.cumsum([n for _d, n in dd]) if dd else np.array([0.0])
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))
    trades = [x for x in log if lo <= x["day"] < hi]
    nets = sorted((x["net"] for x in trades), reverse=True)
    return {"net_days": round(sum(n for _d, n in dd)), "trades": len(trades), "months": len(months),
            "positive_months": sum(v > 0 for v in months.values()), "worst_month": round(min(months.values())) if months else 0,
            "worst_day": round(min((n for _d, n in dd), default=0.0)), "max_drawdown": round(float((peak[1:] - cum).max())) if dd else 0,
            "refill_days": sum(1 for _d, n in dd if n < 0), "refilled": round(-sum(n for _d, n in dd if n < 0)),
            "adds": sum(1 for x in trades for a in x["adds"] if a["added"]),
            "top10": round(sum(nets[:10]))}


def waterfall(log):
    t = log
    rows = []
    for x in t:
        first = x["pieces"][0][2] if x["pieces"] else 0.0
        add = sum(p[2] for p in x["pieces"][1:])
        rows.append({"day": x["day"], "net": x["net"], "first": first, "add": add, "ext": x.get("ext_contrib", 0.0) if x["ext"] else 0.0,
                     "overshoot": x.get("overshoot", 0.0), "fees": x["fees"], "reason": x["reason"], "marked": not x["traded_exit"],
                     "expert": x.get("expert"), "opt": x.get("opt"), "added": any(a["added"] for a in x["adds"]),
                     "lots": sum(p[1] for p in x["pieces"])})
    los = [r for r in rows if r["net"] < 0]
    win = [r for r in rows if r["net"] > 0]

    def agg(rs):
        return {"n": len(rs), "net": round(sum(r["net"] for r in rs)), "first_piece": round(sum(r["first"] for r in rs)),
                "added_piece": round(sum(r["add"] for r in rs)), "extension": round(sum(r["ext"] for r in rs)),
                "stop_overshoot": round(sum(r["overshoot"] for r in rs)), "fees_and_stress": round(sum(r["fees"] for r in rs)),
                "with_add": sum(r["added"] for r in rs), "marked_exits": sum(r["marked"] for r in rs),
                "by_reason": dict(collections.Counter(r["reason"] for r in rs))}
    out = {"all": agg(rows), "losers": agg(los), "winners": agg(win)}
    for key in ("expert", "opt", "reason"):
        out["by_" + key] = {str(k): {"n": len(g), "net": round(sum(r["net"] for r in g)), "losers_net": round(sum(r["net"] for r in g if r["net"] < 0)),
                                     "winners_net": round(sum(r["net"] for r in g if r["net"] > 0))}
                            for k, g in _group(rows, key).items()}
    srt = sorted(rows, key=lambda r: r["net"])
    out["worst10"] = [{k: (round(v) if isinstance(v, float) else v) for k, v in r.items()} for r in srt[:10]]
    out["best10_share_of_net"] = round(sum(r["net"] for r in srt[-10:]) / sum(r["net"] for r in rows), 3) if rows else None
    out["losers_without_worst10"] = round(sum(r["net"] for r in srt[10:] if r["net"] < 0))
    # loss of the added piece on trades whose add lost money; and the add's share of winners
    out["adds_on_losers"] = {"n": sum(r["added"] for r in los), "added_piece_net": round(sum(r["add"] for r in los if r["added"]))}
    out["adds_on_winners"] = {"n": sum(r["added"] for r in win), "added_piece_net": round(sum(r["add"] for r in win if r["added"]))}
    return out


def _group(rows, key):
    g = collections.defaultdict(list)
    for r in rows:
        g[r[key]].append(r)
    return g


def cash_census(log):
    adds = [a for x in log for a in x["adds"]]
    over = [a for a in adds if a["over_wallet_if_mtm"] and a["added"]]
    return {"triggers": len(adds), "added": sum(1 for a in adds if a["added"]), "rejected_by_mtm": sum(1 for a in adds if not a["fits_mtm"]),
            "mtm_rejects_that_cash_allows": sum(1 for a in adds if not a["fits_mtm"] and a["n_cash"] >= 1),
            "adds_over_wallet": len(over), "largest_excess": round(max((a["excess_if_mtm"] for a in over), default=0.0)),
            "stop_blocked": sum(1 for a in adds if a.get("stop_blocked"))}


if __name__ == "__main__":
    out_path = HERE / "results-sn310-311.json"
    if out_path.exists():
        raise SystemExit("SN310-SN311 are run once")
    # 1. parity
    gw.uninstall()
    base_row, base_days, _ = ow.run_wallet(C.V5, ow.GOLD_30K, None)
    gw.install()
    row0, days0, log0 = run()
    ref = {d: n for d, _w, n, _t, _l in base_days}
    mine = {d: n for d, _w, n, _t, _l in days0}
    parity = {"days": len(ref), "same_days": set(ref) == set(mine), "max_abs_diff": max(abs(ref[d] - mine[d]) for d in ref),
              "panel_net_lab": base_row["net"], "panel_net_mine": row0["net"], "trades_logged": len(log0),
              "trade_sum_equals_day_sum": abs(sum(x["net"] for x in log0) - sum(mine.values())) < 0.01}
    print("SN310 parity", parity, flush=True)
    assert parity["same_days"] and parity["max_abs_diff"] < 0.01 and base_row["net"] == row0["net"] and parity["trade_sum_equals_day_sum"], parity
    res = {"parity": parity, "SN310": waterfall(log0), "SN311": {}}
    print("SN310", json.dumps(res["SN310"]["all"]), flush=True)
    # 2. SN311 arms
    runs = {}
    for stress in (205.0, 400.0):
        for arm, cash in (("G0", "mtm"), ("G1", "both"), ("G2", "debit")):
            row, days, log = run(cash, stress)
            runs[(arm, stress)] = (row, days, log)
            m = {"panel_net": row["net"], "panel_refilled": row["refilled"], "whole": metrics(row, days, log),
                 "halves": {h: metrics(row, days, log, lo, hi) for h, lo, hi in HALVES}, "cash": cash_census(log)}
            res["SN311"][f"{arm} @{int(stress)}"] = m
            print("SN311", arm, int(stress), json.dumps({k: m[k] for k in ("panel_net", "panel_refilled", "cash")}), json.dumps(m["whole"]), flush=True)
    # 3. the frozen decision
    g0 = res["SN311"]["G0 @205"]["cash"]
    dec = {"G0_commits_over_wallet": g0["adds_over_wallet"] > 0,
           "reference_for_real_money": "G1" if g0["adds_over_wallet"] > 0 else "G0"}
    ok = True
    for stress in (205, 400):
        a, b = res["SN311"][f"G2 @{stress}"], res["SN311"][f"G1 @{stress}"]
        for part in [("whole", a["whole"], b["whole"])] + [(h, a["halves"][h], b["halves"][h]) for h, _lo, _hi in HALVES]:
            name, x, y = part
            cond = {"net": x["net_days"] >= y["net_days"], "positive_months": x["positive_months"] >= y["positive_months"],
                    "worst_month": x["worst_month"] >= y["worst_month"], "refills": x["refilled"] <= 1.10 * y["refilled"],
                    "worst_day": x["worst_day"] >= 1.10 * y["worst_day"]}
            dec[f"G2 vs G1 @{stress} {name}"] = cond
            ok = ok and all(cond.values())
    dec["G2_dev_candidate"] = ok
    res["decision"] = dec
    print("SN311 decision", json.dumps(dec), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
