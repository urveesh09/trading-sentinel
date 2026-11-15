"""SN247 - Gold v7 (Gold v5 + WK-H band 0.8, SN245) in money (PLAN.md): every month of the account window for Gold v6 and
Gold v7 side by side (each leg, the owner's refills, banked); the bad months that remain and what lost in them; the wallet
table (1 / 2 / 3 WK-H units = Rs 5.3 / 10.3 / 15.3 lakh with Gold's Rs 30k); the idle-capital credit shown apart."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ev  # noqa: E402
import led  # noqa: E402
import wk4  # noqa: E402

dumps = lambda x: json.dumps(x, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))   # noqa: E731

if __name__ == "__main__":
    out_path = HERE / "results-sn247.json"
    if out_path.exists():
        raise SystemExit("SN247 is run once")
    days = led.sessions()
    g = led.gold()
    l6 = led.wkh_days()
    tr8 = wk4.book4(led.sample("DEV"), "STRADDLE", "M", "settle", {"band": 0.8}) + wk4.book4(led.sample("TEST"), "STRADDLE", "M", "settle", {"band": 0.8})
    l8 = ev.leg_days(tr8)
    v6 = {d: g.get(d, 0.0) + l6.get(d, 0.0) for d in days}
    v7 = {d: g.get(d, 0.0) + l8.get(d, 0.0) for d in days}
    mg, m6, m7, mw8 = led.months(g, days), led.months(v6, days), led.months(v7, days), led.months(l8, days)
    r6, r7 = led.refill_months(v6, days), led.refill_months(v7, days)
    res = {"Gold v6": led.account_stats(v6, days), "Gold v7": led.account_stats(v7, days), "months": {}}
    for m in sorted(m7):
        res["months"][m] = {"gold": round(mg[m]), "wkh08": round(mw8[m]), "gold_v7": round(m7[m]), "gold_v6": round(m6[m]),
                            "v7_banked": round(r7[m]["banked"]), "v7_refilled": round(r7[m]["refilled"]), "v6_refilled": round(r6[m]["refilled"])}
    bad7 = [m for m in sorted(m7) if m7[m] < 0]
    res["bad_months_v7"] = {m: {"gold": round(mg[m]), "wkh08": round(mw8[m]), "total": round(m7[m]),
                                "driver": "Gold" if mg[m] < mw8[m] else "WK-H"} for m in bad7}
    res["bad_v7_by_driver"] = {k: sum(1 for v in res["bad_months_v7"].values() if v["driver"] == k) for k in ("Gold", "WK-H")}
    res["refills"] = {"Gold v6 total refilled": round(sum(r["refilled"] for r in r6.values())), "Gold v7 total refilled": round(sum(r["refilled"] for r in r7.values())),
                      "Gold v6 worst month refilled": round(max(r["refilled"] for r in r6.values())), "Gold v7 worst month refilled": round(max(r["refilled"] for r in r7.values()))}
    res["wallets"] = {}
    for u in (1, 2, 3):
        st = led.account_stats({d: g.get(d, 0.0) + u * l8.get(d, 0.0) for d in days}, days)
        cap = 30000 + 500000 * u
        res["wallets"][f"Rs {cap / 1e5:.1f} lakh ({u} WK-H unit{'s' if u > 1 else ''})"] = {
            "net": st["net"], "per_year_pct": round(100 * st["net"] / (46 / 12) / cap, 1), "months_positive": st["months_positive"],
            "worst_month": st["worst_month"], "mean_month": st["mean_month"], "idle_capital_credit_per_month": round(cap * 0.05 / 12)}
    print("SN247 Gold v6", json.dumps({x: res["Gold v6"][x] for x in ("net", "months_positive", "worst_month", "mean_month", "sd_month", "by_year")}), flush=True)
    print("SN247 Gold v7", json.dumps({x: res["Gold v7"][x] for x in ("net", "months_positive", "worst_month", "mean_month", "sd_month", "by_year")}), flush=True)
    for m, v in res["bad_months_v7"].items():
        print("SN247 v7 bad", m, json.dumps(v), flush=True)
    print("SN247 by driver", json.dumps(res["bad_v7_by_driver"]), "refills", json.dumps(res["refills"]), flush=True)
    for k, v in res["wallets"].items():
        print("SN247 wallet", k, json.dumps(v), flush=True)
    out_path.write_text(dumps(res), encoding="utf-8")
