"""SN252 - the gap-day census and the one-wallet player (PLAN.md). Gold v5 at Rs 30k growing (stop 3), Jan 2023 -
Oct 2026: per year, sessions, Gold trade days, gap days (non-expiry no-trade days) and expiry days (no SN session),
Gold's wallet on gap days, Gold's positive months; what a leg must add per gap day for a Rs 750 / Rs 1,500 / 10%-of-
wallet daily wage on every session. Parity: ow.play_day with no leg = SN110's player (= Gold v5) day by day."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402
import ow  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn252.json"
    if out_path.exists():
        raise SystemExit("SN252 is run once")
    row, days, _legs = ow.run_wallet(ow.C.V5, ow.GOLD_30K, None)
    base, bdays = ow.sn110.run_wallet(ow.C.V5, ow.GOLD_30K)
    mine = {d: n for d, _w, n, _t, _l in days}
    ref = dict(bdays)
    parity = {"days": len(ref), "same_days": set(mine) == set(ref),
              "max_abs_diff": round(max(abs(mine[d] - ref[d]) for d in ref), 6), "panel_net_mine": row["net"], "panel_net_sn110": base["net"]}
    print("SN252 parity", parity, flush=True)
    assert parity["same_days"] and parity["max_abs_diff"] < 1e-6 and row["net"] == base["net"], parity
    smp = ow._smp()
    sess = set(smp.days)
    cal = [d for d in smp.cal if "2023-01-01" <= d < gl.TEST_HI]
    census = {}
    for y in sorted({d[:4] for d in cal}):
        yd = [x for x in days if x[0][:4] == y]
        gold_days = [x for x in yd if x[3] > 0]
        gap = [x for x in yd if x[3] == 0]
        census[y] = {"calendar_sessions": sum(d[:4] == y for d in cal), "sn_sessions": len(yd),
                     "expiry_or_no_option_days": sum(d[:4] == y and d not in sess for d in cal),
                     "gold_trade_days": len(gold_days), "gap_days_non_expiry": len(gap),
                     "gold_net": round(sum(x[2] for x in yd)), "wallet_on_gap_days_median": round(float(np.median([x[1] for x in gap]))) if gap else None}
    tot_cal = len(cal)
    gold_net = sum(x[2] for x in days)
    n_gap = sum(x[3] == 0 for x in days) + sum(d not in sess for d in cal)
    months = {}
    for d, _w, n, _t, _l in days:
        months[d[:7]] = months.get(d[:7], 0.0) + n
    m = np.array(list(months.values()))
    wage = {}
    for name, per in (("Rs 750", lambda w: 750.0), ("Rs 1,500", lambda w: 1500.0), ("10% of wallet", lambda w: 0.10 * w)):
        need = sum(per(w) for _d, w, _n, _t, _l in days) + sum(per(30000.0) for d in cal if d not in sess)
        wage[name] = {"wage_total_all_sessions": round(need), "gold_net": round(gold_net),
                      "shortfall": round(need - gold_net), "per_gap_day_needed": round((need - gold_net) / n_gap)}
    res = {"parity": parity, "census": census, "totals": {"calendar_sessions": tot_cal, "gap_days_all": n_gap,
                                                          "gold_trade_days": sum(x[3] > 0 for x in days), "gold_net": round(gold_net),
                                                          "gold_months_positive": int((m > 0).sum()), "months": len(m)},
           "wage": wage}
    for y, r in census.items():
        print("SN252", y, json.dumps(r), flush=True)
    print("SN252 totals", json.dumps(res["totals"]), flush=True)
    for k, r in wage.items():
        print("SN252 wage", k, json.dumps(r), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
