"""SN237 - the daily hedged straddle (PLAN.md): one 1-session ATM straddle (2 lots) from every 15:15 followed by the next
calendar day's session (no weekend or holiday held), hedged as WK-H (band 0.6 / 0.8, every 15), closed at the next 15:15 or
settled when that session is the expiry. On the five WK samples (per lot) and in the Gold v6 account in place of WK-H."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ev  # noqa: E402
import led  # noqa: E402
import wk4  # noqa: E402

VARIANTS = {"daily hedged straddle, band 0.6": {}, "daily hedged straddle, band 0.8": {"band": 0.8}}

if __name__ == "__main__":
    out_path = HERE / "results-sn237.json"
    if out_path.exists():
        raise SystemExit("SN237 is run once")
    res = {}
    base = ev.wk_stats({n: led.wkh_trades(n) for n in led.WK_SAMPLES})
    for lab, hp in VARIANTS.items():
        tr = {n: wk4.daily4(led.sample(n), hp) for n in led.WK_SAMPLES}
        st = ev.wk_stats(tr)
        ac = ev.account([ev.leg_days(tr["DEV"] + tr["TEST"])])
        res[lab] = {"hp": hp, "wk": st, "account": ac, "q4_vs_wkh": ev.q4(st, base), "positions_dev": len(tr["DEV"]),
                    "win_pct_dev": round(100 * sum(t["net"] > 0 for t in tr["DEV"]) / max(1, len(tr["DEV"])), 1),
                    "mean_per_position_per_lot_dev": round(sum(t["net"] for t in tr["DEV"]) / max(1, len(tr["DEV"])) / 2)}
        print("SN237", ev.line(lab, st, ac), "Q4", res[lab]["q4_vs_wkh"], "positions DEV", res[lab]["positions_dev"],
              "win%", res[lab]["win_pct_dev"], "mean/lot", res[lab]["mean_per_position_per_lot_dev"], flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
