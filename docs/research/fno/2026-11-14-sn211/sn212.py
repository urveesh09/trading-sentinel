"""SN212 - where the losses come from (PLAN.md; development only, description). WK-S on both bases (settle, pre),
replayed minute by minute with a rule that cannot fire. Per week: entry evening (15:16-15:29 of the entry day after the
15:15 entry), overnight gaps (last value of a session -> its first fresh minute next session), intraday sessions,
and the residual to the exit (the expiry day for settle). Losing weeks' totals by component; the worst 10 weeks
broken down; MAE (worst minute value) of winners and losers; the first breach of a short strike: how often holding
from there ended worse, and the mean of (final - value at the breach)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wk2  # noqa: E402

wk = wk2.wk


def parts(t):
    r = t["record"]
    d0 = t["entry"]
    v0 = t["marks"][d0] if d0 in t["marks"] else 0.0
    days = sorted(r["close"])
    comp = {"entry evening": r["close"].get(d0, v0) - v0, "overnight": 0.0, "intraday": 0.0}
    prev = r["close"].get(d0, v0)
    for d in days:
        if d == d0:
            continue
        o = r["open"].get(d, prev)
        comp["overnight"] += o - prev
        comp["intraday"] += r["close"][d] - o
        prev = r["close"][d]
    comp["to exit (expiry day for settle)"] = t["net"] - prev
    comp["entry cost"] = v0
    return comp


if __name__ == "__main__":
    out_path = HERE / "results-sn212.json"
    if out_path.exists():
        raise SystemExit("SN212 is run once")
    D = wk.dev_data()
    weeks = wk.split(wk.expiries(D), "dev")
    mins = wk2.Minutes("dev")
    res = {}
    for tag, base in wk2.BASES.items():
        tr = wk2.book2(wk.NIFTY, D, mins, weeks, base, {"breach": 99.0}, record=True)
        P = [parts(t) for t in tr]
        lose = [(t, p) for t, p in zip(tr, P) if t["net"] < 0]
        keys = list(P[0])
        row = {"weeks": len(tr), "net": round(sum(t["net"] for t in tr)), "losing_weeks": len(lose),
               "all weeks by component": {k: round(sum(p[k] for p in P)) for k in keys},
               "losing weeks by component": {k: round(sum(p[k] for _t, p in lose)) for k in keys}}
        worst = sorted(zip(tr, P), key=lambda x: x[0]["net"])[:10]
        row["worst 10"] = [{"entry": t["entry"], "expiry": t["expiry"], "net": round(t["net"]), "reason": t["reason"],
                            **{k: round(v) for k, v in p.items()}} for t, p in worst]
        cr = np.array([t["credit_pts"] * wk.NIFTY["lot"] for t in tr])
        mae = np.array([t["record"]["mae"] for t in tr])
        net = np.array([t["net"] for t in tr])
        row["MAE"] = {"winners": int((net > 0).sum()), "winners_down_1x_credit_at_some_minute": int(((net > 0) & (mae <= -cr)).sum()),
                      "winners_down_0.5x": int(((net > 0) & (mae <= -0.5 * cr)).sum()),
                      "losers_mae_median": round(float(np.median(mae[net < 0]))), "credit_median": round(float(np.median(cr)))}
        br = [(t, t["record"]["first_breach"]) for t in tr if t["record"]["first_breach"]]
        if br:
            diff = np.array([t["net"] - b["value"] for t, b in br])
            row["first breach of a short strike"] = {"weeks": len(br), "share_of_weeks_pct": round(100 * len(br) / len(tr), 1),
                                                     "holding_ended_worse_pct": round(100 * float((diff < 0).mean()), 1),
                                                     "mean_final_minus_value_at_breach": round(float(diff.mean())),
                                                     "sum_final_minus_value_at_breach": round(float(diff.sum())),
                                                     "breached_weeks_net": round(sum(t["net"] for t, _b in br))}
        res[tag] = row
        print(f"SN212 {tag}:", json.dumps({k: v for k, v in row.items() if k != "worst 10"}), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
