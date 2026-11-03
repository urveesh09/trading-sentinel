"""Score the Oct 24 frozen arm B (profit protection) on the partner's recorded trips, Oct 27 - Nov 2.

Arm B (docs/NEXT_AGENT_PLAN.md, O24, frozen before these days): once the best bid reaches
P + max(W, P - S) the stop moves to the buy price P (break-even), then trails at best - W.
Scored as a MESSAGE overlay: the partner keeps their own exits, except that when B's stop is hit
before their first sale they sell everything REACTION seconds later at that look's bid.
Trips without a plan stop or swing, or with a sale before B's trigger, keep the actual result.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Users\Urveesh\Desktop\trading-sentinel\python-engine")
from partner_coach import round_trip_costs  # noqa: E402

EVIDENCE = r"C:\Users\Urveesh\Desktop\Production_Trading-sentinel\docs\audit-evidence\2026-11-02-partner\partner-evidence.json"
REACTION = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0

T = json.load(open(EVIDENCE, encoding="utf-8"))["tables"]
dt = datetime.fromisoformat
plans = {}
for v in T["partner_watch_plan_versions"]:
    if v["version"] == 1:
        plans[v["position_key"]] = json.loads(v["plan_json"]) if isinstance(v["plan_json"], str) else v["plan_json"]
looks = defaultdict(list)
for row in T["partner_watch_looks"]:
    if row["bid"] and row["bid"] > 0:
        looks[row["position_key"]].append((dt(row["at"]), float(row["bid"])))
for rows in looks.values():
    rows.sort()
sells = defaultdict(list)
for o in T["partner_orders"]:
    if o["transaction_type"] == "SELL" and o["status"] == "COMPLETE" and (o["filled_quantity"] or 0) > 0:
        sells[(o["session_date"], o["tradingsymbol"])].append(dt(o["updated_at"] or o["placed_at"]))

out = defaultdict(lambda: {"trips": 0, "fired": 0, "better": 0, "worse": 0, "delta": 0.0, "actual": 0.0, "b": 0.0})
detail = []
for t in T["partner_watch_trips"]:
    if not t["closed_at"] or t["realised"] is None or t["carried"]:
        continue
    day = t["session_date"]
    agg = out[day]
    agg["trips"] += 1
    agg["actual"] += t["realised"]
    plan = plans.get(t["position_key"])
    result = t["realised"]
    fired = None
    if plan and plan.get("stop") and plan.get("swing"):
        P, S, W = float(plan["entry"]), float(plan["stop"]), float(plan["swing"])
        arm = P + max(W, P - S)
        first_at, closed_at = dt(t["first_at"]), dt(t["closed_at"])
        first_sell = min((s for s in sells[(day, t["tradingsymbol"])] if first_at <= s <= closed_at), default=closed_at)
        best, stop = None, None
        path = [(at, bid) for at, bid in looks.get(t["position_key"], []) if first_at <= at < first_sell]
        for i, (at, bid) in enumerate(path):
            best = bid if best is None else max(best, bid)
            if stop is None and best >= arm:
                stop = P
            if stop is not None:
                stop = max(stop, best - W)
                if bid <= stop:
                    later = [(a, b) for a, b in path[i:] if a >= at + timedelta(seconds=REACTION)]
                    if later:
                        fired = later[0]
                    break
        if fired is not None:
            qty = int(t["bought"])
            orders = int(t["orders"] or 2)
            sell_px = fired[1]
            result = round((sell_px - float(t["entry"])) * qty - round_trip_costs(float(t["entry"]), sell_px, qty,
                                                                                 t["exchange"], orders=orders), 2)
            agg["fired"] += 1
            agg["better" if result > t["realised"] else "worse"] += 1
            detail.append((day, t["tradingsymbol"], t["first_at"][11:16], round(t["realised"]), round(result),
                           fired[0].strftime("%H:%M:%S"), round(sell_px, 2), round(arm, 2)))
    agg["b"] += result
    agg["delta"] += result - t["realised"]

tot = defaultdict(float)
print(f"reaction {REACTION:.0f} s")
print("day         trips fired better worse   actual        B      delta")
for day in sorted(out):
    a = out[day]
    print(f"{day}  {a['trips']:5d} {a['fired']:5d} {a['better']:6d} {a['worse']:5d} {a['actual']:9.0f} {a['b']:9.0f} "
          f"{a['delta']:9.0f}")
    for k in ("trips", "fired", "better", "worse", "actual", "b", "delta"):
        tot[k] += a[k]
print(f"all         {tot['trips']:5.0f} {tot['fired']:5.0f} {tot['better']:6.0f} {tot['worse']:5.0f} "
      f"{tot['actual']:9.0f} {tot['b']:9.0f} {tot['delta']:9.0f}")
if "--detail" in sys.argv:
    for d in detail:
        print(d)
