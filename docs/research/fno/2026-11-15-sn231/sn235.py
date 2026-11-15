"""SN235 - WK-H on expiry afternoon (DIAGNOSIS.md amendment). First, parity: wk4 with its defaults reproduces wk3's WK-H
trade by trade on all five WK samples. Then (a) checks through 15:15 on expiry day (no 14:30 freeze); (b) flatten the futures
at 14:30; (c) checks every 5 minutes from 14:30 to 15:15. Each: the five samples (per lot) and the Gold v6 account with the
variant in place of WK-H."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ev  # noqa: E402
import led  # noqa: E402
import wk4  # noqa: E402

VARIANTS = {"WK-H (as frozen)": {}, "(a) checks through 15:15": {"freeze_j": 361},
            "(b) flatten futures at 14:30": {"flatten_j": 315}, "(c) every 5 min 14:30-15:15": {"freeze_j": 361, "late_every": 5, "late_from": 315}}


def run(hp):
    return {n: wk4.book4(led.sample(n), "STRADDLE", "M", "settle", hp) for n in led.WK_SAMPLES}


if __name__ == "__main__":
    out_path = HERE / "results-sn235.json"
    if out_path.exists():
        raise SystemExit("SN235 is run once")
    par = {}
    for n in led.WK_SAMPLES:
        a = {t["expiry"]: t["net"] for t in led.wkh_trades(n)}
        b = {t["expiry"]: t["net"] for t in wk4.book4(led.sample(n), "STRADDLE", "M", "settle", {})}
        par[n] = {"same_weeks": set(a) == set(b), "max_abs_diff_rs": round(max((abs(a[e] - b[e]) for e in a if e in b), default=0.0), 6)}
    print("SN235 parity", json.dumps(par), flush=True)
    res = {"parity": par, "variants": {}}
    base = None
    for lab, hp in VARIANTS.items():
        tr = run(hp)
        st = ev.wk_stats(tr)
        ac = ev.account([ev.leg_days(tr["DEV"] + tr["TEST"])])
        if base is None:
            base = st
        res["variants"][lab] = {"hp": hp, "wk": st, "account": ac, "q4_vs_wkh": ev.q4(st, base),
                                "orders_dev": sum(t["orders"] for t in tr["DEV"]), "hedge_costs_dev_per_lot": round(sum(t["hedge_costs"] for t in tr["DEV"]) / 2)}
        print("SN235", ev.line(lab, st, ac), "Q4", res["variants"][lab]["q4_vs_wkh"], "orders DEV", res["variants"][lab]["orders_dev"], flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
