"""SN231 - Gold v6's ledger (PLAN.md): SN Gold v5 (Rs 30k growing) + WK-H (2 lots) per day, Jan 2023 - Oct 2026; per month
the net of each leg and of the account; the bad months; the owner's refill cash flow (banked by green days, refilled for
red days) per month."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import led  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn231.json"
    if out_path.exists():
        raise SystemExit("SN231 is run once")
    days = led.sessions()
    g, h = led.gold(), led.wkh_days()
    acct = {d: g.get(d, 0.0) + h.get(d, 0.0) for d in days}
    res = {"window": [days[0], days[-1]], "sessions": len(days),
           "Gold v5": led.account_stats(g, days), "WK-H": led.account_stats(h, days), "Gold v6": led.account_stats(acct, days)}
    mg, mh, ma = led.months(g, days), led.months(h, days), led.months(acct, days)
    rf = led.refill_months(acct, days)
    res["months"] = {m: {"gold": round(mg[m]), "wkh": round(mh[m]), "gold_v6": round(ma[m]), "banked": round(rf[m]["banked"]),
                         "refilled": round(rf[m]["refilled"]), "green_days": rf[m]["green_days"], "red_days": rf[m]["red_days"]} for m in sorted(ma)}
    bad = [m for m in sorted(ma) if ma[m] < 0]
    res["bad_months"] = bad
    res["bad_month_split"] = {
        "both legs negative": sum(mg[m] < 0 and mh[m] < 0 for m in bad),
        "Gold negative, WK-H positive": sum(mg[m] < 0 <= mh[m] for m in bad),
        "WK-H negative, Gold positive": sum(mh[m] < 0 <= mg[m] for m in bad),
        "loss from Gold": round(sum(min(0.0, mg[m]) for m in bad)), "loss from WK-H": round(sum(min(0.0, mh[m]) for m in bad))}
    res["legs_negative_months"] = {"Gold v5": sum(v < 0 for v in mg.values()), "WK-H": sum(v < 0 for v in mh.values()),
                                   "Gold v5 flat (no trade)": sum(v == 0 for v in mg.values())}
    for k in ("Gold v5", "WK-H", "Gold v6"):
        print("SN231", k, json.dumps(res[k]), flush=True)
    for m, r in res["months"].items():
        print(f"SN231 {m} gold {r['gold']:>9} wkh {r['wkh']:>9} v6 {r['gold_v6']:>9} banked {r['banked']:>9} refilled {r['refilled']:>9} "
              f"green/red {r['green_days']}/{r['red_days']}{'  <-- BAD' if r['gold_v6'] < 0 else ''}", flush=True)
    print("SN231 bad months", len(bad), json.dumps(res["bad_month_split"]), json.dumps(res["legs_negative_months"]), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
