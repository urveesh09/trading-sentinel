"""SN462: score calibration against cash (PLAN.md section 1, frozen at 83e1b444; details fixed here before any number).
Diagnostic; no threshold is chosen from it.

Scores: SN456's out-of-sample yA (with positioning) and yB (price only), each filed by the chronological scorer before its
outcome (_local/sn456_forecasts.json). Dates: SN456's out-of-sample dates that are ledger10 dates (2023 - Oct 2026, non-expiry).
The traded side is sign(score) and its ledger10 net (the chosen side must be ENTERED at that stress; otherwise the decision is
counted under its state and nets 0).
  BINS      quintiles of |score| from each block's in-sample |fitted| edges (q_a / q_b): per bin n, hit (sign agrees with y),
            the mean signed move (sign(score) x y, bp), net per decision at 205 / 400, priced share, unresolved share, the
            10th-percentile net (worst decile)
  COVER30   |score| >= the block's in-sample 70th percentile: per decision and per market session at both stresses
  DUMB30    the same count on the same dates and the same side choice, ranked by days to expiry ascending, then the chosen
            contract's modelled spread share of premium ascending
  CURVE     net per market session when trading the top c% of |score| (c = 10 .. 100), global ranks (diagnostic)
  CONFORMAL an 80% split-conformal interval for y from the previous blocks' out-of-sample residuals (causal); coverage by vol20
            tercile (the sample's terciles)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import feat456 as F  # noqa: E402
import ledger10  # noqa: E402

OUT = HERE / "results-sn462.json"


def side_net(L, d, s, st):
    r = L[d][s]
    ok = r["state"] == "ENTERED" if st == 205 else r["state400"] == "ENTERED"
    return (r[f"net{st}"] if ok else 0.0), r["state"] if st == 205 else r["state400"]


def main():
    if OUT.exists():
        raise SystemExit("SN462 is scored once")
    L = ledger10.build()
    cal, rows, _ = F.features()
    sessions = sum(1 for d in cal if ledger10.LO <= d <= ledger10.HI)
    fc = json.loads((HERE / "_local" / "sn456_forecasts.json").read_text(encoding="utf-8"))
    res = {"market_sessions": sessions}
    for name, key, qk, pk in (("AUG", "ya", "q_a", "p70_a"), ("BASE", "yb", "q_b", "p70_b")):
        recs = []
        for i, d in enumerate(fc["dates"]):
            if d not in L:
                continue
            sc, y, b = fc[key][i], fc["y"][i], str(fc["block"][i])
            s = "CE" if sc > 0 else "PE"
            n205, st205 = side_net(L, d, s, 205)
            n400, _st = side_net(L, d, s, 400)
            edges = fc[qk][b]
            recs.append({"day": d, "score": sc, "y": y, "bin": int(np.searchsorted(edges, abs(sc))), "cover": abs(sc) >= fc[pk][b],
                         "n205": n205, "n400": n400, "state": st205, "side": s,
                         "dte": (dt.date.fromisoformat(L[d]["expiry"]) - dt.date.fromisoformat(d)).days,
                         "spread": L[d][s].get("spread_share") if L[d][s].get("spread_share") is not None else 9.0,
                         "vol20": rows[d].get("vol20"), "block": int(b)})
        blk = {"dates": len(recs), "bins": {}}
        for q in range(5):
            xs = [r for r in recs if r["bin"] == q]
            if not xs:
                continue
            n205 = np.array([r["n205"] for r in xs])
            blk["bins"][str(q)] = {"n": len(xs), "hit": round(float(np.mean([np.sign(r["score"]) == np.sign(r["y"]) for r in xs if r["y"] != 0])), 4),
                                   "mean_signed_move_bp": round(float(np.mean([np.sign(r["score"]) * r["y"] for r in xs])), 2),
                                   "net205": round(float(n205.mean()), 1), "net400": round(float(np.mean([r["n400"] for r in xs])), 1),
                                   "priced_share": round(float(np.mean([r["state"] == "ENTERED" for r in xs])), 3),
                                   "unresolved_share": round(float(np.mean([r["state"] == "UNRESOLVED" for r in xs])), 3),
                                   "p10_net205": round(float(np.percentile(n205, 10)), 1)}
        cov = [r for r in recs if r["cover"]]
        blk["COVER30"] = {"trades": len(cov), "share": round(len(cov) / max(1, len(recs)), 3),
                          "per_decision_205": round(float(np.mean([r["n205"] for r in cov])), 1) if cov else None,
                          "per_decision_400": round(float(np.mean([r["n400"] for r in cov])), 1) if cov else None,
                          "per_market_session_205": round(sum(r["n205"] for r in cov) / sessions, 1),
                          "per_market_session_400": round(sum(r["n400"] for r in cov) / sessions, 1),
                          "hit": round(float(np.mean([np.sign(r["score"]) == np.sign(r["y"]) for r in cov if r["y"] != 0])), 4) if cov else None}
        dumb = sorted(recs, key=lambda r: (r["dte"], r["spread"]))[:len(cov)]
        blk["DUMB30"] = {"trades": len(dumb), "per_decision_205": round(float(np.mean([r["n205"] for r in dumb])), 1) if dumb else None,
                         "per_decision_400": round(float(np.mean([r["n400"] for r in dumb])), 1) if dumb else None,
                         "per_market_session_205": round(sum(r["n205"] for r in dumb) / sessions, 1)}
        order = sorted(recs, key=lambda r: -abs(r["score"]))
        blk["CURVE_per_market_session_205"] = {str(c): round(sum(r["n205"] for r in order[:int(len(order) * c / 100)]) / sessions, 1) for c in range(10, 101, 10)}
        # conformal: residuals of earlier blocks only
        cover_by = {0: [], 1: [], 2: []}
        v = np.array([r["vol20"] for r in recs if r["vol20"] is not None])
        t1, t2 = np.percentile(v, [33.3, 66.7])
        for r in recs:
            prev = [abs(x["y"] - x["score"]) for x in recs if x["block"] < r["block"]]
            if len(prev) < 100 or r["vol20"] is None:
                continue
            q80 = float(np.percentile(prev, 80))
            t = 0 if r["vol20"] <= t1 else (1 if r["vol20"] <= t2 else 2)
            cover_by[t].append(abs(r["y"] - r["score"]) <= q80)
        blk["CONFORMAL80_coverage_by_vol_tercile"] = {str(t): round(float(np.mean(c)), 3) if c else None for t, c in cover_by.items()}
        res[name] = blk
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
