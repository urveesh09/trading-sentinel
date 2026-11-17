"""SN423 / SN424 / SN425 (own; PLAN.md section 2, frozen at e5cc95b7; details fixed here before any number). Learning only.

SN423 which experts and sides carry Gold: DEPLOYED with the stream filtered (every book's signals): without EFF, without
       OR20, without SHIPPED, TPB only, puts only, calls only; 2022 and 2023-26; Rs 205 / 400.
SN424 Gold's size ladder: wallets "1 lot" (one lot, no growth), "2 lots" (sized: two lots, halved on low-volatility
       days, no growth), growth caps 0 / 1 / 2 / 3 (deployed) / 4 / 5, and size "all" with cap 3; paths 2022, 2023-26,
       2022-26 (Rs 30k from Jan 2022); Rs 205 / 400; net, per session, worst month, months positive, refills, max lots.
SN425 Gold's stop slippage and tail risk: DEPLOYED 2022-26 at Rs 205 / 400 with Gold's full trade log: stop exits'
       realized loss against the room the walk was given (loss + realized at entry), the price overshoot beyond the
       stop price (gw's `overshoot`, rupees), days losing > 20% of the wallet, the no-bid bound per trade (entry debit:
       ask0 x 65 x lots0 + buy charges) against the worst actual trade loss, and the extension's contribution.
Runs cached in _local/sn423-425-runs.json (slices).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gold  # noqa: E402

OUT = {423: HERE / "results-sn423.json", 424: HERE / "results-sn424.json", 425: HERE / "results-sn425.json"}
CACHE = HERE / "_local" / "sn423-425-runs.json"
FILTERS = {"all (deployed)": None, "without EFF": lambda s: s["expert"] != "EFF", "without OR20": lambda s: s["expert"] != "OR20",
           "without SHIPPED": lambda s: s["expert"] != "SHIPPED", "TPB only": lambda s: s["expert"] == "TPB",
           "puts only": lambda s: s["opt"] == "PE", "calls only": lambda s: s["opt"] == "CE"}
WALLETS = {"1 lot": (("1 lot", 30000.0, "one", None), {}), "2 lots": (("2 lots", 30000.0, "sized", None), {}),
           **{f"growth cap {c}": ((f"30k grow stop {c}", 30000.0, "grow", c), {}) for c in (0, 1, 2, 3, 4, 5)},
           "size all, cap 3": (gold.GOLD_30K, {"size": "all"})}
P23 = {"2022": gold.Y22, "2023-2026": gold.Y2326}
P24 = {"2022": gold.Y22, "2023-2026": gold.Y2326, "2022-2026": gold.Y2226}


def main():
    if all(p.exists() for p in OUT.values()):
        raise SystemExit("SN423-SN425 are run once")
    CACHE.parent.mkdir(exist_ok=True)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    def go(k, **kw):
        if k not in cache:
            days, log, _ = gold.run(**kw)
            s = gold.summary(days, log)
            s["max_lots"] = max([x.get("lots0") or 0 for x in log], default=0)
            cache[k] = s
            CACHE.write_text(json.dumps(cache), encoding="utf-8")
            print(k, s["net"], flush=True)
        return cache[k]
    # SN423
    t423 = {}
    for name, f in FILTERS.items():
        for p, years in P23.items():
            for st in (205.0, 400.0):
                s = go(f"423 {name} | {p} @{int(st)}", years=years, books=gold.DEPLOYED, stress=st, stream_filter=f)
                t423[f"{name} | {p} @{int(st)}"] = {k: s[k] for k in ("net", "by_year", "months_positive", "worst_month", "trades")}
    assert t423["all (deployed) | 2023-2026 @205"]["net"] in (850882, 850883)
    # SN424
    t424 = {}
    for name, (w, vx) in WALLETS.items():
        for p, years in P24.items():
            for st in (205.0, 400.0):
                s = go(f"424 {name} | {p} @{int(st)}", years=years, books=gold.DEPLOYED, stress=st, wallet=w, **vx)
                t424[f"{name} | {p} @{int(st)}"] = {k: s[k] for k in ("net", "per_session", "worst_month", "months_positive", "months", "refilled", "max_lots", "final_wallet")}
    # SN425
    t425 = {}
    for st in (205.0, 400.0):
        days, log, _ = gold.run(gold.Y2226, gold.DEPLOYED, st)
        stops = [x for x in log if x.get("reason") == "stop"]
        exc = [(-x["net"] - x["room"]) for x in stops if x.get("room") is not None]
        over = [x.get("overshoot", 0.0) for x in stops]
        bound = []
        for x in log:
            q = (x.get("lots0") or 1) * 65
            debit = x["ask0"] * q + gold.T.Q.gw.buy_fees(x["ask0"], q)
            bound.append((debit, x["net"]))
        wal = {d: w for d, w, *_ in days}
        t425[f"@{int(st)}"] = {
            "trades": len(log), "stops": len(stops), "stop_share": round(len(stops) / max(1, len(log)), 3),
            "stops_beyond_room": sum(1 for e in exc if e > 0), "beyond_room_median": round(float(np.median([e for e in exc if e > 0])), 1) if any(e > 0 for e in exc) else 0.0,
            "beyond_room_worst": round(float(max(exc)), 1) if exc else 0.0, "price_overshoot_median": round(float(np.median(over)), 1) if over else 0.0,
            "price_overshoot_worst": round(float(max(over)), 1) if over else 0.0, "price_overshoot_total": round(float(sum(over))),
            "days_loss_over_20pct_wallet": sum(1 for d, w, n, *_ in days if n <= -0.2 * w), "worst_day": round(min(n for _d, _w, n, *_ in days)),
            "worst_day_share_of_wallet": round(min(n / w for _d, w, n, *_ in days if w), 3),
            "worst_trade": round(min(x["net"] for x in log)), "no_bid_bound_worst": round(-max(b for b, _n in bound)),
            "worst_trade_share_of_its_debit": round(min(n / b for b, n in bound if b), 3),
            "extension_trades": sum(1 for x in log if x.get("ext")), "extension_contribution": round(sum(x.get("ext_contrib", 0.0) for x in log if x.get("ext")))}
        print(int(st), json.dumps(t425[f"@{int(st)}"]), flush=True)
    OUT[423].write_text(json.dumps(t423, indent=1), encoding="utf-8")
    OUT[424].write_text(json.dumps(t424, indent=1), encoding="utf-8")
    OUT[425].write_text(json.dumps(t425, indent=1), encoding="utf-8")
    for k, v in t423.items():
        print("423", k, v["net"], v["trades"])
    for k, v in t424.items():
        print("424", k, v["net"], v["per_session"], v["worst_month"], v["max_lots"])


if __name__ == "__main__":
    main()
