"""SN112 - is the straddle a hidden direction trade? (PLAN.md) On SN95-L days and all signal days: the ATM leg in the
direction of 09:15->10:00 only, the other leg only, and the straddle; Rs 3k room, hold to 15:10, strict; a random leg
each day (2,000 draws) as control; the preference rule."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pb  # noqa: E402

C, pa = pb.C, pb.pa


def prefer(alt, base):
    yrs = sum(alt[y]["net"] > base[y]["net"] for y in C.YEARS)
    return alt["total"] > base["total"] and yrs >= 3 and alt["without_best_5"] > base["without_best_5"], yrs


if __name__ == "__main__":
    out_path = HERE / "results-sn112.json"
    if out_path.exists():
        raise SystemExit("SN112 is scored once")
    adm = pa.admission()
    res = {}
    rng = np.random.default_rng(112)
    for name, gf in (("SN95-L days", True), ("all signal days", False)):
        days = pb.signal_days(adm, gf)
        rows = {}
        for S in days:
            i, K = pb.I10, pb.atm(S, pb.I10)
            c, o = S.F["c"], S.F["o"]
            d = 1 if c[i] >= o[0] else -1
            ce = pb.net(pb.struct_path(S, i, [(K, "CE")]), n_legs=1)
            pe = pb.net(pb.struct_path(S, i, [(K, "PE")]), n_legs=1)
            st = pb.net(pa.path(S, i))
            rows[S.day] = {"with": ce if d > 0 else pe, "against": pe if d > 0 else ce, "straddle": st, "ce": ce, "pe": pe}
        tabs = {k: pa.year_table({d: r[k] for d, r in rows.items()}) for k in ("with", "against", "straddle")}
        draws = []
        keys = list(rows)
        for _ in range(2000):
            pick = rng.random(len(keys)) < 0.5
            draws.append(sum(rows[k]["ce"] if p else rows[k]["pe"] for k, p in zip(keys, pick)))
        ok, yrs = prefer(tabs["with"], tabs["straddle"])
        p95 = float(np.percentile(draws, 95))
        res[name] = {"days": len(rows), "tables": tabs, "random_leg_mean": round(float(np.mean(draws))), "random_leg_95th": round(p95),
                     "with_trend_preferred": bool(ok and tabs["with"]["total"] > p95), "with_years_beating_straddle": yrs, "rows": rows}
        print(f"=== SN112 {name} ({len(rows)} days)")
        for k, t in tabs.items():
            print(f"   {k:9s} {[t[y]['net'] for y in C.YEARS]} total {t['total']:>8} w/o best5 {t['without_best_5']:>8} trades {sum(t[y]['trades'] for y in C.YEARS)}")
        print("   random leg mean", res[name]["random_leg_mean"], "95th", res[name]["random_leg_95th"], "| with-trend preferred:", res[name]["with_trend_preferred"], flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
