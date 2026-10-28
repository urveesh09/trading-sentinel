"""[O24g 2026-10-24] How the partner's trade watch did on live days, read from the database (read-only).

    python -m partner_watch_report [FIRST_DAY [LAST_DAY]]      (default: the latest day with messages)

Messages (``partner_watch_messages``), per kind:
  - how many, how many reached Telegram, and how each ended (acknowledged,
    superseded, expired, muted, attempting, a Telegram failure...);
  - seen: event_at → detected_at, from what happened at Zerodha (the
    order's exchange update time) to the tick that found it. For NO_STOP and
    PARTIAL the event is the moment the message became due (120 s after the
    buy), and for EXCESS, ORPHAN and PRODUCT the first look at the orders,
    so for them it measures the watch's own scheduling;
  - sent: detected_at → sent_at, from that tick to Telegram's
    acknowledgement (building, retries and the send);
  - by: found by the 5 s tick (poll) or a tick the order stream woke.
Ticks (``partner_watch_state`` ``ticks:<day>:<process start>``): how they
ended, their length and the order-book read's, and the order stream's
numbers. Seconds and milliseconds are p50 / p95 / max.

[O26] Trades (``partner_watch_trips``), per day: closed, won and lost, the
result after charges (exact during the day, from Zerodha's trade book; "from
the orders" when a fill was not in it yet), what is open, and each trade with
what a check would have warned about at its buy (the run before it, a losing
exit just before, the size against the usual).

Facts about the watch's timing and delivery, and the partner's own results;
nothing about whether its advice made or saved money (partner_watch_score
scores the warnings).
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from datetime import datetime
from typing import Optional


def _dt(value) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def spread(values: list) -> Optional[dict]:
    """p50, p95 and max of some numbers (nearest rank), with how many; None without any."""
    if not values:
        return None
    ordered = sorted(values)

    def rank(q: float):
        return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]

    return {"n": len(ordered), "p50": rank(0.5), "p95": rank(0.95), "max": ordered[-1]}


def _seconds(start, end) -> Optional[float]:
    a, b = _dt(start), _dt(end)
    return round((b - a).total_seconds(), 2) if a is not None and b is not None else None


def report(db_path: str, first_day: Optional[str] = None, last_day: Optional[str] = None) -> dict:
    """The numbers for FIRST_DAY..LAST_DAY (both ISO dates), opened read-only."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cols = {row[1] for row in db.execute("PRAGMA table_info(partner_watch_messages)")}
        if not cols:
            return {"first_day": first_day, "last_day": last_day, "messages": {}, "ticks": {}, "trades": {}}
        if first_day is None:
            first_day = db.execute("SELECT MAX(session_date) FROM partner_watch_messages").fetchone()[0]
        last_day = last_day or first_day
        by = "detected_by" if "detected_by" in cols else "NULL"
        rows = db.execute(
            f"SELECT kind, sent, outcome, event_at, detected_at, sent_at, attempts, {by} FROM partner_watch_messages "
            "WHERE session_date>=? AND session_date<=? ORDER BY created_at", (first_day, last_day)).fetchall()
        ticks = db.execute("SELECT key, value FROM partner_watch_state WHERE key>=? AND key<?",
                           (f"ticks:{first_day}", f"ticks:{last_day}~")).fetchall()
        trips = _trips(db, first_day, last_day)
    finally:
        db.close()
    kinds: dict = {}
    for kind, sent, outcome, event_at, detected_at, sent_at, attempts, found_by in rows:
        entry = kinds.setdefault(kind, {"n": 0, "sent": 0, "outcomes": {}, "seen_s": [], "sent_s": [], "by": {},
                                        "retried": 0})
        entry["n"] += 1
        entry["sent"] += int(bool(sent))
        entry["outcomes"][outcome or "-"] = entry["outcomes"].get(outcome or "-", 0) + 1
        entry["by"][found_by or "-"] = entry["by"].get(found_by or "-", 0) + 1
        entry["retried"] += int((attempts or 0) > 1)
        seen = _seconds(event_at, detected_at)
        if seen is not None:
            entry["seen_s"].append(seen)
        if sent:
            delivered = _seconds(detected_at, sent_at)
            if delivered is not None:
                entry["sent_s"].append(delivered)
    for entry in kinds.values():
        entry["seen_s"], entry["sent_s"] = spread(entry["seen_s"]), spread(entry["sent_s"])
    days: dict = {}
    for key, value in ticks:
        try:
            part = json.loads(value)
        except ValueError:
            continue
        day = key.split(":")[1]
        merged = days.setdefault(day, {"parts": 0, "counts": {}, "tick_ms": [], "read_ms": [], "stream": []})
        merged["parts"] += 1
        for name, count in (part.get("counts") or {}).items():
            merged["counts"][name] = merged["counts"].get(name, 0) + int(count)
        merged["tick_ms"] += list(part.get("tick_ms") or [])
        merged["read_ms"] += list(part.get("read_ms") or [])
        if part.get("stream"):
            merged["stream"].append(part["stream"])
    for merged in days.values():
        merged["tick_ms"], merged["read_ms"] = spread(merged["tick_ms"]), spread(merged["read_ms"])
        lags = [lag for stream in merged["stream"] for lag in stream.get("lag_ms") or []]
        merged["stream"] = {
            "states": sorted({stream.get("state") for stream in merged["stream"] if stream.get("state")}),
            "connects": sum(int(stream.get("connects") or 0) for stream in merged["stream"]),
            "updates": sum(int(stream.get("updates") or 0) for stream in merged["stream"]),
            "errors": _summed(stream.get("errors") or {} for stream in merged["stream"]),
            "lag_ms": spread(lags)} if merged["stream"] else None
    return {"first_day": first_day, "last_day": last_day, "messages": kinds, "ticks": days, "trades": trips}


TRIP_COLS = ("session_date", "first_at", "closed_at", "tradingsymbol", "product", "bought", "sold", "entry", "exit",
             "realised", "exact", "carried", "run_pct", "prior_exit", "usual", "cash", "opening_qty", "opening_value",
             "opening_final", "paid_share")


def _trips(db, first_day: str, last_day: str) -> dict:
    """[O26] The trades the watch stored (``partner_watch_trips``), by day, in buy order; {} before O26."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='partner_watch_trips'").fetchone():
        return {}
    out: dict = {}
    have = {row[1] for row in db.execute("PRAGMA table_info(partner_watch_trips)")}
    cols = [c if c in have else f"NULL AS {c}" for c in TRIP_COLS]
    for row in db.execute(f"SELECT {', '.join(cols)} FROM partner_watch_trips WHERE session_date>=? AND "
                          "session_date<=? ORDER BY session_date, first_at", (first_day, last_day)):
        trip = dict(zip(TRIP_COLS, row))
        try:
            trip["prior_exit"] = json.loads(trip["prior_exit"]) if trip["prior_exit"] else None
        except ValueError:
            trip["prior_exit"] = None
        out.setdefault(trip["session_date"], []).append(trip)
    return out


def day_totals(trips: list) -> dict:
    """[O26] A day's trades bought that day (carried ones apart): closed, won, lost, the result after charges,
    whether every closed one is from Zerodha's trade book, and how many are still open. [O29] And what the carried
    ones sold that day made against what was paid for them (Oct 28: −₹12,444 on two calls from Oct 27's close)."""
    today = [t for t in trips if not t["carried"]]
    closed = [t for t in today if t["realised"] is not None]
    carried_closed = [t for t in trips if t["carried"] and t["realised"] is not None]
    return {"closed": len(closed), "won": sum(t["realised"] > 0 for t in closed),
            "lost": sum(t["realised"] < 0 for t in closed), "net": round(sum(t["realised"] for t in closed), 2),
            "exact": all(t["exact"] for t in closed), "open": sum(t["realised"] is None for t in today),
            "carried": len(trips) - len(today), "carried_closed": len(carried_closed),
            "carried_net": round(sum(t["realised"] for t in carried_closed), 2)}


def _rupees(value: float) -> str:
    return f"{'−' if value < 0 else '+'}₹{abs(value):,.0f}"


def _trip_line(trip: dict) -> str:
    at = (_dt(trip["first_at"]) or datetime.min).strftime("%H:%M")
    held = f"{trip['bought']} @ {trip['entry']:g}" if trip["entry"] is not None else f"{trip['bought']}"
    if trip["realised"] is not None:
        out = f" → {trip['exit']:g} {_rupees(trip['realised'])}" + ("" if trip["exact"] else " (from orders)")
    else:
        out = f", open ({trip['sold']} sold)" if trip["sold"] else ", open"
    from partner_watch_score import POSITIVE, evidence_of
    marks = []
    if trip["run_pct"] is not None:
        marks.append(f"run {math.floor(trip['run_pct'] * 100 + 1e-9)}%")
    if evidence_of(trip)["AFTER_LOSS"] == POSITIVE:    # [O26d] the scorer's frozen rule, on the stored evidence
        marks.append(f"{trip['prior_exit']['minutes']} min after a {_rupees(trip['prior_exit']['result'])} exit")
    if trip["usual"] and trip["paid_share"] is not None:
        marks.append(f"size {trip['paid_share']:.0%} (usual {trip['usual']:.0%})")
    carried = " carried" if trip["carried"] else ""
    return f"    {at} {trip['tradingsymbol']} {trip['product']}{carried} {held}{out}" + (
        f"  [{'; '.join(marks)}]" if marks else "")


def _summed(dicts) -> dict:
    out: dict = {}
    for item in dicts:
        for name, count in item.items():
            out[name] = out.get(name, 0) + int(count)
    return out


def _span(values: Optional[dict], unit: str) -> str:
    return "-" if not values else f"{values['p50']:g} / {values['p95']:g} / {values['max']:g} {unit}"


def render(data: dict) -> str:
    """The report as plain text."""
    lines = [f"Trade watch, {data['first_day']} to {data['last_day']}"]
    if not data["messages"] and not data["ticks"] and not data.get("trades"):
        return "\n".join(lines + ["Nothing recorded."])
    lines.append("Messages: sent/all, how they ended; seen and sent in seconds (p50 / p95 / max); found by")
    for kind in sorted(data["messages"]):
        entry = data["messages"][kind]
        ends = ", ".join(f"{name} {count}" for name, count in sorted(entry["outcomes"].items()))
        found = ", ".join(f"{name} {count}" for name, count in sorted(entry["by"].items()))
        lines.append(f"  {kind:<9} {entry['sent']}/{entry['n']} ({ends}); seen {_span(entry['seen_s'], 's')}; "
                     f"sent {_span(entry['sent_s'], 's')}; by {found}"
                     + (f"; sent again {entry['retried']}" if entry["retried"] else ""))
    for day in sorted(data["ticks"]):
        merged = data["ticks"][day]
        counts = ", ".join(f"{name} {count}" for name, count in sorted(merged["counts"].items()))
        lines.append(f"Ticks {day} ({merged['parts']} part{'s' if merged['parts'] != 1 else ''}): {counts}; "
                     f"tick {_span(merged['tick_ms'], 'ms')}; order-book read {_span(merged['read_ms'], 'ms')}")
        stream = merged["stream"]
        if stream:
            errors = ", ".join(f"{name} {count}" for name, count in sorted(stream["errors"].items())) or "none"
            lines.append(f"  Stream: {'/'.join(stream['states']) or '-'}; connections {stream['connects']}; order "
                         f"updates {stream['updates']}; errors {errors}; exchange to receipt "
                         f"{_span(stream['lag_ms'], 'ms')}")
    for day in sorted(data.get("trades") or {}):
        trips, totals = data["trades"][day], day_totals(data["trades"][day])
        lines.append(f"Trades {day}: {totals['closed']} closed ({totals['won']} won, {totals['lost']} lost), "
                     f"{_rupees(totals['net'])} after charges"
                     + ("" if totals["exact"] else " (some fills from the orders, not the trade book)")
                     + f"; {totals['open']} open" + (f"; {totals['carried']} carried in" if totals["carried"] else "")
                     + (f" ({totals['carried_closed']} sold {_rupees(totals['carried_net'])}; the day "
                        f"{_rupees(totals['net'] + totals['carried_net'])})" if totals["carried_closed"] else ""))
        lines.extend(_trip_line(trip) for trip in trips)
    return "\n".join(lines)


def main(argv: list) -> int:
    from config import settings
    first = argv[1] if len(argv) > 1 else None
    last = argv[2] if len(argv) > 2 else None
    print(render(report(settings.DB_PATH, first, last)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
