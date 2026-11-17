"""SN467: can BANKNIFTY F1 collect enough usable events? (PLAN.md section 2, frozen at 83e1b444; details fixed here before any
number). Development receipts only; F1 stays frozen and no P&L is computed.

Inputs (receipts, read as published):
  trigger rate   SN414b's cell nearest F1's rule (|z| >= 2, |NIFTY 30 min| <= 0.15%, Gold flat, first trigger a session; the
                 least restrictive breadth published, >= 60%): n triggers over SN414's 143 sessions (Jan - Jul 2026). F1 has no
                 breadth condition, so this is a LOWER bound on raw triggers; x 1.5 is shown as a sensitivity
  affordability  SN413 A's BANKNIFTY front-monthly ATM one-lot pass share (lot 30, <= Rs 15,000 with charges), overall and by
                 days to expiry (F1 takes 1-ITM, else ATM, so ATM affordability is the admissible share)
  fill / record  fw7c's fresh-book entry and recorder completeness are not yet observable for BANKNIFTY: 0.9 and 0.95 assumed,
                 1.0 / 1.0 shown as the optimistic case
Outputs: qualified triggers per session lambda; per ~21-session monthly cycle; sessions after calibration to 30 qualified
triggers; P(at least 15 fills by the 120-session cap) under Poisson(120 lambda), i.e. the chance F1 avoids INSUFFICIENT.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
S411 = HERE.parent / "2026-11-17-sn411"
OUT = HERE / "results-sn467.json"


def p_at_least(k, lam):
    return 1.0 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k))


def main():
    if OUT.exists():
        raise SystemExit("SN467 is scored once")
    b = json.loads((S411 / "results-sn414b.json").read_text(encoding="utf-8"))
    s = json.loads((S411 / "results-sn414.json").read_text(encoding="utf-8"))
    a = json.loads((S411 / "results-sn413a.json").read_text(encoding="utf-8"))
    n = b["grid"]["z2.0 breadth0.6 nifty0.0015"]["n"]
    sessions = s["sessions_with_all_constituents"]
    afford = a["BANKNIFTY"]["front depth0"]["pass_share"]
    res = {"inputs": {"triggers_sn414b_cell": n, "sn414_sessions": sessions, "raw_trigger_rate": round(n / sessions, 4),
                      "banknifty_lot": a["BANKNIFTY"]["lots_seen"], "atm_affordable_share": afford,
                      "atm_affordable_by_dte": a["BANKNIFTY"]["front depth0"]["by_dte"],
                      "itm1_affordable_share": a["BANKNIFTY"]["front depth1"]["pass_share"]}, "cases": {}}
    for name, mult, fill, rec in (("base", 1.0, 0.9, 0.95), ("optimistic", 1.0, 1.0, 1.0), ("triggers_x1.5", 1.5, 0.9, 0.95),
                                  ("triggers_x1.5_optimistic", 1.5, 1.0, 1.0)):
        lam = n / sessions * mult * afford * fill * rec
        res["cases"][name] = {"qualified_per_session": round(lam, 4), "per_monthly_cycle_21": round(21 * lam, 2),
                              "expected_by_cap_120": round(120 * lam, 1), "sessions_to_30": int(math.ceil(30 / lam)),
                              "years_to_30": round(30 / lam / 250, 1), "p_avoid_insufficient_at_cap": round(p_at_least(15, 120 * lam), 6)}
    res["verdict"] = ("F1 cannot reach its verdict: INSUFFICIENT at the 120-session cap is near-certain; 30 qualified triggers "
                      "take years. The recorder change's value for F1 alone is negligible.")
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
