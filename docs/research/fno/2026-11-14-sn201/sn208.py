"""SN208 - robustness of WK-S (PLAN.md SN207 rule, applied to WK-S by the amendment). Development weeks. Entry at
15:05 / 15:16 / 15:25; stress Rs 300 / 400 per leg-lot (about double / triple the friction); strangle width 0.25 / 0.75;
stop 1.5 / 2.0 / none; entry k neighbours; the weeks with estimated marks vs the rest; the share of profit in the best
10 weeks."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wk  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn208.json"
    if out_path.exists():
        raise SystemExit("SN208 is run once")
    D = wk.dev_data()
    weeks = wk.split(wk.expiries(D), "dev")
    A = pickle.loads((wk.LOCAL / "sn204-picks.pkl").read_bytes())["WK-S"]
    s, k, ex, st = A
    base = wk.book(wk.NIFTY, D, weeks, A)

    def row(tr):
        x = wk.stats(tr)
        return {n: x[n] for n in ("weeks", "net", "win_pct", "worst", "by_year", "years_positive", "without_best_10")}

    res = {"variant": wk.vname(A), "base": row(base)}
    res["entry_time"] = {lab: row(wk.book(wk.NIFTY, D, weeks, A, i_entry=i)) for lab, i in (("15:05", 350), ("15:16", 361), ("15:25", 370))}
    res["stress"] = {str(x): row(wk.book(wk.NIFTY, D, weeks, A, stress=x)) for x in (300.0, 400.0)}
    if s.startswith("STRANGLE"):
        res["width"] = {w: row(wk.book(wk.NIFTY, D, weeks, (f"STRANGLE {w}", k, ex, st))) for w in ("0.25", "0.75")}
    res["stop"] = {str(x): row(wk.book(wk.NIFTY, D, weeks, (s, k, ex, x))) for x in (None, 0.5, 1.0, 1.5, 2.0)}
    res["k"] = {str(x): row(wk.book(wk.NIFTY, D, weeks, (s, x, ex, st))) for x in (2, 3, "F")}
    est = [t for t in base if t["estimated_marks"]]
    res["estimated_marks"] = {"weeks_with": len(est), "net_with": round(sum(t["net"] for t in est)),
                              "net_without": round(sum(t["net"] for t in base if not t["estimated_marks"]))}
    tot = sum(t["net"] for t in base)
    best10 = sum(sorted((t["net"] for t in base), reverse=True)[:10])
    res["best_10_weeks_share_pct"] = round(100 * best10 / tot, 1) if tot else None
    print("SN208", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
