"""fw10: SN485's frozen forward verdict for Gold v5 alone (run once, at results-sn485.json's contest_market_sessions).

Input: a read-only Production receipt made by sn476_pull.py (sn_gold_positions, sn_gold_days) and NSE's market sessions from
2026-11-18 (the sessions the receipt's sn_gold_days covers plus sessions without a row, counted from fno_signals evaluation days).
Day net = the sum of CLOSED positions' net_stressed (Rs 205 a lot) on that session; Rs 400 = that minus Rs 195 x the day's lots.
UNRESOLVED positions: counted, and a bound prices each as the loss of its whole debit. Refuses to score before the frozen length.
    python fw10.py <receipt.json>            the verdict (once: writes results-fw10.json)
    python fw10.py --self-test               synthetic checks of the rule
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "results-fw10.json"
START = "2026-11-18"


def block_mean_ci(x, seed=485, block=20, draws=10000):
    x = np.asarray(x, float)
    n = len(x)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(draws, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(draws, -1)[:, :n] % n
    m = x[idx].mean(axis=1)
    return float(np.quantile(m, 0.05)), float(np.quantile(m, 0.95))


def verdict(d205, d400):
    lo2, hi2 = block_mean_ci(d205)
    lo4, hi4 = block_mean_ci(d400)
    if lo2 > 0 and lo4 > 0:
        v = "EDGE_CONFIRMED"
    elif hi2 < 0:
        v = "EDGE_REJECTED"
    else:
        v = "INCONCLUSIVE"
    return v, {"ci205": [round(lo2, 1), round(hi2, 1)], "ci400": [round(lo4, 1), round(hi4, 1)]}


def day_nets(P, sessions):
    by205 = {d: 0.0 for d in sessions}
    lots = {d: 0 for d in sessions}
    unresolved = []
    for p in P["sn_gold_positions"]:
        d = p["session_date"]
        if d not in by205:
            continue
        if p["status"] == "CLOSED":
            by205[d] += float(p["net_stressed"])
            lots[d] += sum(n for _e, n in json.loads(p["pieces"]))
        elif p["status"] == "UNRESOLVED":
            unresolved.append(p["id"])
    d205 = np.asarray([by205[d] for d in sessions])
    d400 = np.asarray([by205[d] - 195.0 * lots[d] for d in sessions])
    return d205, d400, unresolved


def main(argv):
    if argv[:1] == ["--self-test"]:
        rng = np.random.default_rng(1)
        assert verdict(rng.normal(500, 100, 300), rng.normal(400, 100, 300))[0] == "EDGE_CONFIRMED"
        assert verdict(rng.normal(-500, 100, 300), rng.normal(-600, 100, 300))[0] == "EDGE_REJECTED"
        assert verdict(rng.normal(0, 3000, 300), rng.normal(0, 3000, 300))[0] == "INCONCLUSIVE"
        print("self-test ok")
        return
    if OUT.exists():
        raise SystemExit("fw10 is scored once")
    need = json.loads((HERE / "results-sn485.json").read_text(encoding="utf-8"))["contest_market_sessions"]
    P = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    sessions = sorted({str(s["evaluated_at"])[:10] for s in P["fno_signals"]} | {d["session_date"] for d in P["sn_gold_days"]})
    sessions = [d for d in sessions if d >= START]
    if len(sessions) < need:
        raise SystemExit(f"not yet: {len(sessions)} of {need} market sessions (nothing scored)")
    sessions = sessions[:need]
    d205, d400, unresolved = day_nets(P, sessions)
    v, ci = verdict(d205, d400)
    res = {"sessions": len(sessions), "first": sessions[0], "last": sessions[-1], "verdict": v, **ci, "net205": round(float(d205.sum())),
           "net400": round(float(d400.sum())), "worst_day205": round(float(d205.min())), "unresolved": unresolved}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
