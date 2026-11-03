"""[N05-PP 2026-11-03] Would a profit-protection message have helped the partner's own trades? Scored on what the
trade watch stored, read-only.

    python -m partner_protect_score [FIRST_DAY [LAST_DAY]]      (default: the SPEC's frozen_from to the latest day)

Frozen on 2026-11-03, before any day it decides on (the owner's rules: freeze, then score; no tuning on a day
already seen; a result informs the owner and changes nothing by itself). Changing a rule is a new version, frozen
again before the days it decides on; every result carries ``SPEC_ID``.

The rules, each a message the watch would send. P is the plan's buy price, S the plan stop and W the option's normal
5-minute swing (version 1 of the trade's plan).

  B (frozen Oct 24, O24; scored once on Oct 27 - Nov 2: 8 of 166 trips, +₹5,463, mixed, not enabled):
      once the best bid reaches P + max(W, P - S), the stop moves to P; then it trails at best - W.
  B2 (frozen here): once the best bid reaches P + W, the stop moves to P; then it trails at best - W.

How a message is scored: the partner keeps their own exits, except that when a rule's stop is hit before their first
sale they sell everything ``reaction_sec`` (20 s) later, at that look's bid. A trip without a plan stop and swing, or
with a sale before the rule fired, keeps its actual result. Charges use the trip's own order count.

Verdict, per rule, on days from ``frozen_from``:
  SUPPORTED      all four hold:
                   1. it fired on at least ``min_fired`` (20) trips;
                   2. the total change is positive;
                   3. still positive without the single best change (not one lucky trade);
                   4. it helped on at least as many trips as it hurt;
  TOO_FEW        under ``min_fired``;
  NOT_SUPPORTED  otherwise.
A quote is not a fill and a reaction is assumed, so the numbers describe the rule, not money the partner would
certainly have kept. Nothing here sends a message.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

SPEC = {
    "name": "partner_protect_score",
    "version": 1,
    "frozen_on": "2026-11-03",
    "frozen_from": "2026-11-04",
    "reaction_sec": 20,
    "min_fired": 20,
    "rules": {
        "B": {"arm": "P + max(W, P - S)", "stop": "P", "trail": "best - W", "frozen_on": "2026-10-24"},
        "B2": {"arm": "P + W", "stop": "P", "trail": "best - W", "frozen_on": "2026-11-03"},
    },
}
SPEC_ID = "v1-" + hashlib.sha256(json.dumps(SPEC, sort_keys=True).encode()).hexdigest()[:12]


def arm_level(rule: str, entry: float, stop: float, swing: float) -> float:
    if rule == "B":
        return entry + max(swing, entry - stop)
    if rule == "B2":
        return entry + swing
    raise ValueError(f"unknown rule {rule}")


def fired_at(rule: str, entry: float, stop: float, swing: float, path: list) -> Optional[int]:
    """Index in ``path`` [(at, bid)] of the look where the rule's stop is hit, or None."""
    arm = arm_level(rule, entry, stop, swing)
    best, level = None, None
    for i, (_at, bid) in enumerate(path):
        best = bid if best is None else max(best, bid)
        if level is None and best >= arm:
            level = entry
        if level is not None:
            level = max(level, best - swing)
            if bid <= level:
                return i
    return None


def _load(db_path: str, first_day: str, last_day: str) -> dict:
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        trips = db.execute(
            "SELECT session_date, position_key, tradingsymbol, exchange, first_at, closed_at, bought, entry, "
            "realised, orders, carried FROM partner_watch_trips WHERE session_date>=? AND session_date<=?",
            (first_day, last_day)).fetchall()
        plans = dict(db.execute(
            "SELECT position_key, plan_json FROM partner_watch_plan_versions WHERE version=1 AND session_date>=? "
            "AND session_date<=?", (first_day, last_day)).fetchall())
        looks = db.execute(
            "SELECT position_key, at, bid FROM partner_watch_looks WHERE session_date>=? AND session_date<=? "
            "AND bid>0 ORDER BY position_key, at", (first_day, last_day)).fetchall()
        sells = db.execute(
            "SELECT session_date, tradingsymbol, COALESCE(updated_at, placed_at) FROM partner_orders "
            "WHERE transaction_type='SELL' AND status='COMPLETE' AND filled_quantity>0 AND session_date>=? "
            "AND session_date<=?", (first_day, last_day)).fetchall()
    by_key = defaultdict(list)
    for key, at, bid in looks:
        by_key[key].append((datetime.fromisoformat(at), float(bid)))
    sold = defaultdict(list)
    for day, symbol, at in sells:
        sold[(day, symbol)].append(datetime.fromisoformat(at))
    return {"trips": trips, "plans": plans, "looks": by_key, "sells": sold}


def score(db_path: str, first_day: Optional[str] = None, last_day: str = "9999-12-31",
          rules: Optional[tuple] = None) -> dict:
    """``rules``: score only these (default every rule). A rule must never be scored on days before its freeze
    and then frozen: B2's days start at ``frozen_from``."""
    from partner_coach import round_trip_costs
    first_day = first_day or SPEC["frozen_from"]
    data = _load(db_path, first_day, last_day)
    reaction = timedelta(seconds=SPEC["reaction_sec"])
    out = {"spec_id": SPEC_ID, "first_day": first_day, "rules": {}}
    for rule in (rules or tuple(SPEC["rules"])):
        changes, days = [], defaultdict(float)
        trips = 0
        for day, key, symbol, exchange, first_at, closed_at, bought, entry, realised, orders, carried in data["trips"]:
            if not closed_at or realised is None or carried:
                continue
            trips += 1
            plan = json.loads(data["plans"].get(key) or "null") or {}
            if not plan.get("stop") or not plan.get("swing") or not entry:
                continue
            start, end = datetime.fromisoformat(first_at), datetime.fromisoformat(closed_at)
            first_sell = min((s for s in data["sells"][(day, symbol)] if start <= s <= end), default=end)
            path = [(at, bid) for at, bid in data["looks"].get(key, []) if start <= at < first_sell]
            i = fired_at(rule, float(plan["entry"]), float(plan["stop"]), float(plan["swing"]), path)
            if i is None:
                continue
            later = [(at, bid) for at, bid in path[i:] if at >= path[i][0] + reaction]
            if not later:
                continue
            price, qty = later[0][1], int(bought)
            result = round((price - float(entry)) * qty
                           - round_trip_costs(float(entry), price, qty, exchange, orders=int(orders or 2)), 2)
            changes.append(round(result - float(realised), 2))
            days[day] += result - float(realised)
        total = round(sum(changes), 2)
        without_best = round(total - max(changes), 2) if changes else 0.0
        better, worse = sum(c > 0 for c in changes), sum(c < 0 for c in changes)
        if len(changes) < SPEC["min_fired"]:
            verdict = "TOO_FEW"
        elif total > 0 and without_best > 0 and better >= worse:
            verdict = "SUPPORTED"
        else:
            verdict = "NOT_SUPPORTED"
        out["rules"][rule] = {"trips": trips, "fired": len(changes), "better": better, "worse": worse,
                              "change": total, "change_without_best": without_best,
                              "days": {d: round(v, 2) for d, v in sorted(days.items())}, "verdict": verdict}
    return out


def main(argv: list) -> int:
    from config import settings
    first = argv[1] if len(argv) > 1 else None
    last = argv[2] if len(argv) > 2 else "9999-12-31"
    print(json.dumps(score(settings.DB_PATH, first, last), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
