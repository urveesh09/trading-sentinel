"""SN114 - a cheaper structure for the same signal (PLAN.md): on SN95-L days, the ATM straddle vs the 1-step and
2-step strangles and the 1-step in-the-money pair; 10:00 to 15:10, Rs 3k room, Rs 15k ceiling, strict; preference rule."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pb  # noqa: E402
import sn112  # noqa: E402

C, pa = pb.C, pb.pa
STRUCTS = {"ATM straddle": (0, 0), "strangle 1 step": (50, -50), "strangle 2 steps": (100, -100), "ITM pair 1 step": (-50, 50)}


if __name__ == "__main__":
    out_path = HERE / "results-sn114.json"
    if out_path.exists():
        raise SystemExit("SN114 is scored once")
    adm = pa.admission()
    days = pb.signal_days(adm, True)
    rows, prem = {k: {} for k in STRUCTS}, {k: [] for k in STRUCTS}
    for S in days:
        K = pb.atm(S, pb.I10)
        for name, (dc, dp) in STRUCTS.items():
            got = pb.struct_path(S, pb.I10, [(K + dc, "CE"), (K + dp, "PE")])
            rows[name][S.day] = pb.net(got)
            if got is not None:
                prem[name].append(got[1])
    tabs = {k: pa.year_table(v) for k, v in rows.items()}
    res = {"days": len(days), "tables": tabs, "mean_premium": {k: round(sum(v) / max(1, len(v))) for k, v in prem.items()},
           "priced": {k: len(v) for k, v in prem.items()}, "preferred": {}}
    for k in STRUCTS:
        if k != "ATM straddle":
            ok, yrs = sn112.prefer(tabs[k], tabs["ATM straddle"])
            res["preferred"][k] = {"preferred": bool(ok), "years_beating_atm": yrs}
    for k, t in tabs.items():
        print(f"{k:18s} {[t[y]['net'] for y in C.YEARS]} total {t['total']:>8} w/o best5 {t['without_best_5']:>8} trades "
              f"{sum(t[y]['trades'] for y in C.YEARS)} mean premium {res['mean_premium'][k]}", flush=True)
    print("preferred", res["preferred"])
    res["rows"] = rows
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
