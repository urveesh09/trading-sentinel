"""M01 sealed exam: score the frozen arms and hypotheses once on Jan-Jul 2026 (Kite snapshot of Oct 5).

Run only after freeze.json is committed and the owner has said to open the exam:
    python signals.py EXAM && python exam.py
Writes results.json. verify_freeze() refuses to run if any frozen source changed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import lab
import lab_data
from explore_exits import entries

HERE = Path(__file__).resolve().parent
FROZEN = ("lab.py", "lab_data.py", "signals.py", "explore_exits.py", "exam.py", "PLAN.md")


def digest(name):
    return hashlib.sha256((HERE / name).read_bytes().replace(b"
", b"
")).hexdigest()   # line-ending neutral


def verify_freeze():
    freeze = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    changed = [n for n in FROZEN if freeze["sha256"][n] != digest(n)]
    if changed:
        raise SystemExit(f"frozen sources changed: {changed}")
    return freeze


def shipped_arm(data, shipped, selective, rule):
    trades = []
    for ticker, day, bars, j, fill, r, qty in entries(data, shipped, selective):
        t = lab.run_trade(bars, j, fill, r.stop, qty, rule, target_price=r.target, atr=r.atr, vwap_entry=r.vwap)
        if t:
            trades.append({"day": day, "ticker": ticker, **t})
    return trades


def decile_tests(data):
    """H1/H2: rest-of-day (10:15 open to 14:30 open) of first-hour deciles against the day's mean, liquid names."""
    rows = []
    for (t, day), b in data["bars"].items():
        if t == lab.INDEX or len(b) < 22 or b.index[4].strftime("%H:%M") != "10:15":
            continue
        prior = lab.prior_daily(data, t, day)
        if prior is None or float((prior["close"] * prior["volume"]).tail(20).median()) < 5e7 or b["open"].iloc[0] < 50:
            continue
        rest_end = b[b.index.strftime("%H:%M") == lab.DEADLINE]
        if rest_end.empty:
            continue
        rows.append((day, b["close"].iloc[3] / b["open"].iloc[0] - 1, float(rest_end["open"].iloc[0]) / b["open"].iloc[4] - 1))
    f = pd.DataFrame(rows, columns=["day", "fh", "rest"])
    f["dm"] = f.groupby("day")["rest"].transform("mean")
    f["dec"] = f.groupby("day")["fh"].transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
    top, bottom = f[f.dec == 9], f[f.dec == 0]
    by_day_top = (top["rest"] - top["dm"]).groupby(top["day"]).mean()
    by_day_bottom = (bottom["rest"] - bottom["dm"]).groupby(bottom["day"]).mean()
    return {"stock_days": len(f), "days": int(f["day"].nunique()),
            "mean_rest_pct": round(f["rest"].mean() * 100, 4),
            "H1_top_vs_mean_pct": round(by_day_top.mean() * 100, 4),
            "H1_top_positive_days": int((by_day_top > 0).sum()),
            "H2_bottom_vs_mean_pct": round(by_day_bottom.mean() * 100, 4),
            "H2_bottom_positive_days": int((by_day_bottom > 0).sum())}


def verdict(arm, reference, floor=2500.0):
    checks = {"trades_ge_30": arm["trades"] >= 30, "net_positive": arm["net"] > 0,
              "net_ex_best_day_positive": arm.get("net_ex_best_day", 0) > 0,
              "beats_live_rule": arm["net"] > reference["net"],
              "drawdown_ok": arm.get("max_dd", 0) <= max(1.5 * reference.get("max_dd", 0), floor)}
    return {"checks": checks, "promising": all(checks.values())}


if __name__ == "__main__":
    freeze = verify_freeze()
    data = lab_data.load_exam()
    shipped = pd.read_pickle(lab_data.LOCAL / "exam_shipped.pkl")
    live, vwap = lab.Exit("LIVE", live=True), lab.Exit("VWAP", vwap_exit=True)
    days = sorted({d for (_, d) in data["bars"]})
    arms = {
        "A0_BASE_LIVE": shipped_arm(data, shipped, False, live),
        "A1_SELECTIVE_LIVE": shipped_arm(data, shipped, True, live),
        "A2_SELECTIVE_VWAP": shipped_arm(data, shipped, True, vwap),
        "A3_ORB_TOP5_VWAP": [x for d in days for x in lab.orb_day(data, d, lab.Orb("top5_vwap", exit=vwap), 600.0, lab.POOL / 5)],
    }
    rng = np.random.default_rng(1)
    arms["NULL_ORB_RANDOM5_VWAP"] = [x for d in days for x in lab.orb_day(data, d, lab.Orb("null", exit=vwap), 600.0,
                                                                            lab.POOL / 5, rng=rng)]
    results = {name: lab.summary(trades) for name, trades in arms.items()}
    reference = results["A1_SELECTIVE_LIVE"]
    verdicts = {name: verdict(results[name], reference) for name in ("A2_SELECTIVE_VWAP", "A3_ORB_TOP5_VWAP")}
    out = {"freeze_commit": freeze.get("commit"), "window": [days[0], days[-1]], "sessions": len(days),
           "arms": results, "verdicts": verdicts, "hypotheses": decile_tests(data),
           "absolute_checks": {name: verdict(results[name], {"net": -1e18, "max_dd": 1e18}) for name in ("A0_BASE_LIVE", "A1_SELECTIVE_LIVE")}}
    (HERE / "results.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
