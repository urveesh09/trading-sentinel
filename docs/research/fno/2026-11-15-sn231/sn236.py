"""SN236 - hedge cost and a second structure (PLAN.md, DIAGNOSIS.md amendment). On WK-H's 2 lots: band 0.8 / 1.0 x checks
every 15 / 30 minutes; the synthetic options hedge (band 0.6, every 15). A second hedged weekly unit beside WK-H: the best
hedged WK-S (STRANGLE 0.5 k3 settle stop1 H15x2) and the hedged strangle kM (STRANGLE 0.5 kM settle H15x2). Each: the five WK
samples (per lot) and the Gold v6 account (a cost variant replaces WK-H; a second unit is added to it)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ev  # noqa: E402
import led  # noqa: E402
import wk4  # noqa: E402

COST = {"WK-H (as frozen)": {}, "band 0.8 every 15": {"band": 0.8}, "band 1.0 every 15": {"band": 1.0},
        "band 0.6 every 30": {"every": 30}, "band 0.8 every 30": {"band": 0.8, "every": 30}, "band 1.0 every 30": {"band": 1.0, "every": 30},
        "synthetic hedge (options)": {"instrument": "synth"}}
SECOND = {"+ hedged WK-S (STRANGLE 0.5 k3 stop1 H15x2)": ("STRANGLE 0.5", 3, "settle stop1"),
          "+ hedged strangle kM (STRANGLE 0.5 kM H15x2)": ("STRANGLE 0.5", "M", "settle")}

if __name__ == "__main__":
    out_path = HERE / "results-sn236.json"
    if out_path.exists():
        raise SystemExit("SN236 is run once")
    res = {"cost": {}, "second_unit": {}}
    base = None
    for lab, hp in COST.items():
        tr = {n: wk4.book4(led.sample(n), "STRADDLE", "M", "settle", hp) for n in led.WK_SAMPLES}
        st = ev.wk_stats(tr)
        ac = ev.account([ev.leg_days(tr["DEV"] + tr["TEST"])])
        base = base or st
        res["cost"][lab] = {"hp": hp, "wk": st, "account": ac, "q4_vs_wkh": ev.q4(st, base),
                            "orders_dev": sum(t["orders"] for t in tr["DEV"]), "hedge_costs_dev_per_lot": round(sum(t["hedge_costs"] for t in tr["DEV"]) / 2)}
        print("SN236", ev.line(lab, st, ac), "Q4", res["cost"][lab]["q4_vs_wkh"], "orders", res["cost"][lab]["orders_dev"],
              "costs/lot", res["cost"][lab]["hedge_costs_dev_per_lot"], flush=True)
    for lab, (s, k, ex) in SECOND.items():
        tr = {n: wk4.book4(led.sample(n), s, k, ex, {}) for n in led.WK_SAMPLES}
        st = ev.wk_stats(tr)
        both = {n: tr[n] + led.wkh_trades(n) for n in led.WK_SAMPLES}
        st_both = ev.wk_stats(both, lots=4)
        ac = ev.account([ev.leg_days(tr["DEV"] + tr["TEST"])], replace_wkh=False)
        res["second_unit"][lab] = {"leg_alone": st, "with_wkh_per_lot": st_both, "account": ac}
        print("SN236", ev.line(lab + " (alone)", st, ac), flush=True)
        print("SN236", ev.line("   both units, per lot", st_both, ac), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
