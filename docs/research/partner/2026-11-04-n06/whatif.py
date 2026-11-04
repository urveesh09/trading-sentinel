"""Read-only what-if on the partner's stored trades (Oct 26 - Nov 4).

A   what happened (partner_watch_trips.realised, after the watch's modelled charges)
S   same trades, sized by the Sentinel's own rule: lots so the loss at the plan stop is at most RISK of the day's cash
    (at least 1 lot); result scaled per unit
SS  S, and the plan stop honoured: the first stored look (15 s) whose bid is at or under the plan stop sells there,
    at that bid
O   1 lot always, plan stop honoured (no size rule)
F   the Sentinel's own main F&O paper trades that day, at 1 lot each
Rule constants are the Sentinel's own (Rs 5,000 per trade on Rs 2,50,000 = 2%), not fitted to these days.
"""
import json
import sqlite3
from collections import defaultdict

RISK = 0.02
db = sqlite3.connect("file:/data/cache.db?mode=ro", uri=True)


def lot_of(sym):
    return 20 if sym.startswith("SENSEX") else 65 if sym.startswith("NIFTY") else 1


plans = {}
for key, plan in db.execute("SELECT position_key, plan_json FROM partner_watch_plan_versions WHERE version=1"):
    plans[key] = json.loads(plan)

looks = defaultdict(list)
for key, at, bid in db.execute("SELECT position_key, at, bid FROM partner_watch_looks WHERE bid IS NOT NULL ORDER BY at"):
    looks[key].append((at, bid))

days = defaultdict(lambda: defaultdict(float))
counts = defaultdict(lambda: defaultdict(int))
rows = db.execute("SELECT session_date, position_key, tradingsymbol, first_at, closed_at, bought, entry, exit, realised, "
                  "cash FROM partner_watch_trips WHERE closed_at IS NOT NULL AND carried=0 ORDER BY first_at").fetchall()
for day, key, sym, first, closed, bought, entry, exit_, realised, cash in rows:
    if not bought or entry is None or exit_ is None or realised is None:
        continue
    lot = lot_of(sym)
    gross = (exit_ - entry) * bought
    fee_u = max(0.0, gross - realised) / bought          # charges per unit
    unit = realised / bought                            # result per unit, as traded
    plan = plans.get(key) or {}
    stop, p_entry = plan.get("stop"), plan.get("entry") or entry
    cash = cash or plan.get("cash")
    days[day]["A"] += realised
    counts[day]["n"] += 1
    # stop honoured: per unit from the plan entry
    unit_stop = unit
    hit = False
    if stop is not None:
        for at, bid in looks.get(key, []):
            if at < first or at > closed:
                continue
            if bid <= stop:
                unit_stop = (bid - p_entry) - fee_u
                hit = True
                break
        # sold below the plan stop between looks: it was crossed, so it would have sold near the stop
        if not hit and exit_ < stop:
            unit_stop = (stop - p_entry) - fee_u
            hit = True
    counts[day]["hit"] += hit
    if stop is not None and cash:
        per_lot = (p_entry - stop) * lot + fee_u * lot
        lots = max(1, int((RISK * cash) // per_lot)) if per_lot > 0 else 1
    else:
        lots = 1
    q = lots * lot
    days[day]["S"] += unit * q
    days[day]["SS"] += unit_stop * q
    days[day]["O"] += unit_stop * lot
    counts[day]["lots_s"] += lots
    counts[day]["lots_a"] += bought / lot

for day, pnl, lots in db.execute("SELECT exit_date, pnl, lots FROM fno_positions WHERE status='CLOSED' AND "
                                 "source='FNO_PAPER' AND exit_date>='2026-10-26'"):
    days[day]["F"] += (pnl or 0) / max(1, lots or 1)
    counts[day]["f"] += 1

tot = defaultdict(float)
print("day        trades  A(actual)  S(size)  SS(size+stop)  O(1 lot+stop)  F(Sentinel 1 lot)  stops-hit  lots actual/sized")
for day in sorted(days):
    d, c = days[day], counts[day]
    for k in ("A", "S", "SS", "O", "F"):
        tot[k] += d[k]
    print(f"{day} {c['n']:>5} {d['A']:>10,.0f} {d['S']:>8,.0f} {d['SS']:>13,.0f} {d['O']:>13,.0f} {d['F']:>12,.0f} ({c['f']})"
          f" {c['hit']:>6}  {c['lots_a']:.0f}/{c['lots_s']}")
print("TOTAL           " + "  ".join(f"{k} {tot[k]:,.0f}" for k in ("A", "S", "SS", "O", "F")))
win = {k: sum(1 for day in days if days[day][k] > 0) for k in ("A", "S", "SS", "O")}
print("days won", win, "of", len(days))
worst = {k: min(days[day][k] for day in days) for k in ("A", "S", "SS", "O")}
print("worst day", {k: round(v) for k, v in worst.items()})
