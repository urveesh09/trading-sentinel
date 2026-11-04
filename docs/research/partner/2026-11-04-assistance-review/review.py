"""Read-only, seen-day arithmetic and source audit; never sends or trades."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "python-engine"))
from partner_coach import round_trip_costs
import partner_sentinel as ps


def dt(value):
    return datetime.fromisoformat(value)


def main():
    manifest = json.loads((HERE / "input-manifest.json").read_text())
    raw = (HERE / "_local/production-selected.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["sha256"]
    for name, expected in manifest["source_sha"].items():
        assert hashlib.sha256((ROOT / "python-engine" / name).read_bytes()).hexdigest() == expected
    tables = json.loads(raw)["tables"]
    day = "2026-11-04"
    trips = sorted((t for t in tables["partner_watch_trips"] if t["session_date"] == day),
                   key=lambda t: t["first_at"])
    messages = sorted((m for m in tables["partner_watch_messages"]
                       if m["session_date"] == day and m["sent"]), key=lambda m: m["sent_at"])
    actual = round(sum(t["realised"] for t in trips), 2)
    assert len(trips) == 29 and actual == -51869.02
    assert all(t["exact"] == 1 and t["bought"] == t["sold"] and not t["carried"] for t in trips)
    assert len(messages) == 74
    cuts = []
    for message in (m for m in messages if m["kind"] == "DAY"):
        at = message["sent_at"]
        past = [t for t in trips if t["closed_at"] <= at]
        opened = [t for t in trips if t["first_at"] <= at < t["closed_at"]]
        future = [t for t in trips if t["first_at"] > at]
        # Every actual DAY checkpoint happens to be flat. Never invent an exit.
        assert not opened and len(past) + len(future) == len(trips)
        before = sum(t["realised"] for t in past)
        alternatives = {}
        for retain_orders in (False, True):
            value = before
            for t in future:
                qty = 20 if t["exchange"] == "BFO" else 65
                orders = max(2, t["orders"]) if retain_orders else 2
                value += (t["exit"] - t["entry"]) * qty - round_trip_costs(
                    t["entry"], t["exit"], qty, t["exchange"], orders=orders)
            alternatives["retain_original_order_charges" if retain_orders else "two_orders"] = round(value, 2)
        cuts.append({"at": at, "already_realised": round(before, 2), "open_trips": 0,
                     "future_trips": len(future), "one_lot_later_round_trips": alternatives,
                     "flat_then_cash": round(before, 2),
                     "next_buy_seconds": round((dt(future[0]["first_at"]) - dt(at)).total_seconds(), 2)
                     if future else None})
    peaks = {}
    for seconds in (60, 300):
        count, at = max((sum(dt(m["sent_at"]) <= dt(n["sent_at"]) <
                            dt(m["sent_at"]) + timedelta(seconds=seconds) for n in messages), m["sent_at"])
                        for m in messages)
        peaks[str(seconds)] = {"sent": count, "start": at}
    delays = [(dt(m["sent_at"]) - dt(m["event_at"])).total_seconds()
              for m in messages if m["kind"] == "PLAN" and m["event_at"]]
    # Native selector reproduction on an already CLOSED synthetic record. All
    # readers replaced with pure in-memory functions: no broker, DB or messages.
    saved = ps.fno_trades, ps.fno_record, ps.expiry_trades
    try:
        now = dt(day + "T10:03:00+05:30")
        trade = {"id": "SYNTHETIC", "entry_time": day + "T10:00:00+05:30",
                 "entry_premium": 120.5, "tradingsymbol": "NIFTY26N1024000PE",
                 "status": "CLOSED", "exit_time": day + "T10:02:00+05:30", "exit_premium": 110}
        ps.fno_trades = lambda *args: [trade]
        ps.fno_record = lambda *args: None
        ps.expiry_trades = lambda *args: []
        events = ps.events("UNUSED", day, now)
        closed_buy = {"synthetic": True, "event_kinds": [e[1] for e in events],
                      "buy_still_offered": any(e[1] == "SENTINEL" for e in events)}
        assert closed_buy["buy_still_offered"]
    finally:
        ps.fno_trades, ps.fno_record, ps.expiry_trades = saved
    result = {"day": day, "actual_watch_net": actual, "actual_trip_count": len(trips),
              "exact_trip_flags": dict(Counter(t["exact"] for t in trips)),
              "messages_sent": len(messages), "kind_counts": dict(Counter(m["kind"] for m in messages)),
              "characters_sent": sum(len(m["text"]) for m in messages), "peak_windows_seconds": peaks,
              "plan_event_to_ack_seconds": {"min": round(min(delays), 2), "max": round(max(delays), 2)},
              "intraday_checkpoints": cuts, "closed_entry_source_reproduction": closed_buy,
              "limits": ["SEEN-DATA exposure arithmetic, not a strategy test or proof of compliance",
                         "Keeps each later trip's actual average entry/exit despite reducing quantity; path includes averaging/partial sales",
                         "Recomputes charges at hypothetical size; two-order vs original-order sensitivities",
                         "Does not assume perfect stops, invented bids, altered choices, fills or sequence",
                         "No cash/margin/order-book lifecycle replay; no price impact or execution guarantee",
                         "Earlier losses stay realised; late resizing can sacrifice later recovery",
                         "Broker balance differs from watch modeled P&L; no invented account-equity reconciliation"],
              "input_sha256": manifest["sha256"]}
    target = HERE / "results.json"
    assert not target.exists(), "Preserve previous results; use a new revision for a correction"
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"actual": actual, "sent": len(messages), "checkpoints": cuts,
                      "closed_buy_reproduction": closed_buy}, indent=2))


if __name__ == "__main__":
    main()
