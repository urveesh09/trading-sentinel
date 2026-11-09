"""[N09 2026-11-09] The partner's own trading habits, from the trade watch's stored trades (read-only).

The owner, Nov 9, after a morning of 31 buys: "not just a caution machine, but something that can help them grow
almost every day". The trade watch stores every trade (``partner_watch_trips``) with what was known at its buy;
this module turns those rows into the partner's own record and habits, for the morning plan, the losing-run
message, the evening note and the frozen before/after scorecard (docs/research/partner/2026-11-09-n09-coach).

Only facts the partner's record shows are said, each with its sample, and only once the sample meets the frozen
minimums below. Nothing here reads the market, places, blocks or recommends an order.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
from datetime import date, datetime
from pathlib import Path
from typing import Optional

SPEC_ID = "n09-habits-v1"
LOOKBACK_SESSIONS = 10
MIN_DAYS = 5                 # sessions (with morning trades) before the morning fact is said
MIN_BUCKET = 15              # closed trades in each hold bucket before the hold fact is said
QUICK_HOLD_MIN = 2.0         # a trade closed sooner than this is a quick exit
LONG_HOLD_MIN = (15.0, 60.0)
MORNING_END = "12:00"
EARLY_END = "10:00"
QUICK_REBUY_MIN = 2          # a buy this soon after a losing exit (whole minutes, so 0 or 1)
AFTER_LOSS_MIN = 30          # partner_coach.REENTRY_WINDOW_MIN
BIG_MULT = 2.0               # a buy worth this many times the losing trade just before it

TAGS = ("QUICK_REBUY", "BIG_AFTER_LOSS", "QUICK_EXIT", "EARLY")
TAG_TEXT = {
    "QUICK_REBUY": "buys within 2 min of a losing exit",
    "BIG_AFTER_LOSS": "buys at least twice the size of the trade just lost",
    "QUICK_EXIT": "trades sold within 2 min of buying",
    "EARLY": "buys before 10:00",
}
TRY_TOMORROW = {
    "QUICK_REBUY": "after a loss, wait for one 5-minute close before the next buy.",
    "BIG_AFTER_LOSS": "after a loss, make the next buy no bigger than the one you lost on.",
    "QUICK_EXIT": "let the stop order sell a losing trade, and give every trade at least 5 minutes.",
    "EARLY": "take at most 3 trades before 10:00.",
}


# ---------------------------------------------------------------------------
# one stored trade
# ---------------------------------------------------------------------------

def _at(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _hm(row: dict) -> str:
    return str(row.get("first_at") or "")[11:16]


def hold_minutes(row: dict) -> Optional[float]:
    first, closed = _at(row.get("first_at")), _at(row.get("closed_at"))
    if first is None or closed is None:
        return None
    return max((closed - first).total_seconds() / 60.0, 0.0)


def _prior(row: dict) -> dict:
    try:
        value = json.loads(row.get("prior_exit") or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _closed(rows: list) -> list:
    return [r for r in rows if r.get("realised") is not None and not r.get("carried")]


def _value(row: dict) -> Optional[float]:
    if row.get("entry") and row.get("bought"):
        return float(row["entry"]) * float(row["bought"])
    return None


def _last_before(row: dict, rows: list) -> Optional[dict]:
    first = _at(row.get("first_at"))
    if first is None:
        return None
    before = [r for r in rows if r is not row and r.get("session_date") == row.get("session_date")
              and _at(r.get("closed_at")) is not None and _at(r["closed_at"]) <= first]
    return max(before, key=lambda r: _at(r["closed_at"]), default=None)


def tags_of(row: dict, rows: list) -> set:
    """The habits one trade shows (``TAGS``), from what was known at its buy and how long it was held."""
    tags = set()
    prior = _prior(row)
    after_loss = prior.get("state") == "KNOWN" and (prior.get("result") or 0) < 0
    minutes = prior.get("minutes")
    if after_loss and isinstance(minutes, int) and minutes < QUICK_REBUY_MIN:
        tags.add("QUICK_REBUY")
    if after_loss and isinstance(minutes, int) and minutes < AFTER_LOSS_MIN:
        last = _last_before(row, rows)
        mine, theirs = _value(row), _value(last) if last else None
        if mine and theirs and mine >= BIG_MULT * theirs:
            tags.add("BIG_AFTER_LOSS")
    held = hold_minutes(row)
    if held is not None and held < QUICK_HOLD_MIN:
        tags.add("QUICK_EXIT")
    if _hm(row) and _hm(row) < EARLY_END:
        tags.add("EARLY")
    return tags


# ---------------------------------------------------------------------------
# the record before today (morning plan, losing-run message)
# ---------------------------------------------------------------------------

def _wins(rows: list) -> tuple:
    return sum(1 for r in rows if r["realised"] > 0), len(rows)


def record(rows: list) -> dict:
    """The partner's record over ``rows`` (earlier sessions): sessions, mornings that ended down, and the win
    rates of quick exits and of trades held 15–60 minutes, as (wins, n)."""
    closed = _closed(rows)
    days = sorted({r["session_date"] for r in closed})
    mornings: dict = {}
    for r in closed:
        if _hm(r) < MORNING_END:
            mornings[r["session_date"]] = mornings.get(r["session_date"], 0.0) + float(r["realised"])
    holds = [(r, hold_minutes(r)) for r in closed]
    quick = [r for r, h in holds if h is not None and h < QUICK_HOLD_MIN]
    long_ = [r for r, h in holds if h is not None and LONG_HOLD_MIN[0] <= h < LONG_HOLD_MIN[1]]
    return {"spec": SPEC_ID, "days": len(days), "first": days[0] if days else None, "last": days[-1] if days else None,
            "morning_days": len(mornings), "morning_red": sum(1 for v in mornings.values() if v < 0),
            "quick": _wins(quick), "long": _wins(long_)}


def _rate(pair: tuple) -> str:
    wins, n = pair
    return f"{round(100 * wins / n)}%"


def morning_part(rec: dict) -> str:
    if rec.get("days", 0) < MIN_DAYS or rec.get("morning_days", 0) < MIN_DAYS:
        return ""
    return f"mornings (to 12:00) ended down on {rec['morning_red']} of {rec['morning_days']} days"


def hold_part(rec: dict) -> str:
    if min(rec.get("quick", (0, 0))[1], rec.get("long", (0, 0))[1]) < MIN_BUCKET:
        return ""
    return f"trades held 15–60 min won {_rate(rec['long'])}, under 2 min {_rate(rec['quick'])}"


def record_line(rec: dict) -> str:
    """For the morning plan: "📊 Your last 10 days: mornings (to 12:00) ended down on 8 of 10 days · trades held
    15–60 min won 49%, under 2 min 14%." "" while neither part meets its sample."""
    parts = [p for p in (morning_part(rec), hold_part(rec)) if p]
    if not parts:
        return ""
    return f"📊 Your last {rec['days']} days: " + " · ".join(parts) + "."


def hold_line(rec: dict) -> str:
    """For the losing-run message: "📊 Your trades held 15–60 min won 49%; under 2 min, 14%." or ""."""
    if not hold_part(rec):
        return ""
    return f"📊 Your trades held 15–60 min won {_rate(rec['long'])}; under 2 min, {_rate(rec['quick'])}."


# ---------------------------------------------------------------------------
# one day's habits (evening note, scorecard)
# ---------------------------------------------------------------------------

def day_habits(rows: list, lowered: int = 0) -> Optional[dict]:
    """One session's habits from its trades (opened that day) and its stops moved down."""
    today = [r for r in rows if not r.get("carried")]
    if not today:
        return None
    closed = _closed(today)
    holds = [h for h in (hold_minutes(r) for r in closed) if h is not None]
    tagged = [tags_of(r, today) for r in today]
    return {"buys": len(today), "early": sum(1 for t in tagged if "EARLY" in t),
            "median_hold": round(statistics.median(holds), 1) if holds else None,
            "quick_exit_share": round(sum(1 for h in holds if h < QUICK_HOLD_MIN) / len(holds), 3) if holds else None,
            "quick_rebuys": sum(1 for t in tagged if "QUICK_REBUY" in t),
            "big_after_loss": sum(1 for t in tagged if "BIG_AFTER_LOSS" in t),
            "lowered": int(lowered),
            "closed": len(closed), "won": sum(1 for r in closed if r["realised"] > 0),
            "result_sign": (0 if not closed else (1 if sum(r["realised"] for r in closed) > 0 else -1))}


def costliest(rows: list) -> Optional[dict]:
    """The habit whose trades lost the most today, by the fixed order of ``TAGS`` on a tie; None when no tagged
    group lost."""
    today = [r for r in rows if not r.get("carried")]
    sums: dict = {}
    for r in _closed(today):
        for tag in tags_of(r, today):
            n, total = sums.get(tag, (0, 0.0))
            sums[tag] = (n + 1, total + float(r["realised"]))
    worst = None
    for tag in TAGS:
        if tag in sums and sums[tag][1] < 0 and (worst is None or sums[tag][1] < worst["sum"] - 1e-9):
            worst = {"tag": tag, "n": sums[tag][0], "sum": round(sums[tag][1], 2)}
    return worst


def best_trade(rows: list) -> Optional[dict]:
    closed = [r for r in _closed(rows) if r["realised"] > 0 and r.get("entry") and r.get("exit")]
    if not closed:
        return None
    best = max(closed, key=lambda r: r["realised"])
    return {"at": _hm(best), "symbol": best.get("tradingsymbol"), "move": float(best["exit"]) / float(best["entry"]) - 1,
            "minutes": hold_minutes(best), "realised": float(best["realised"])}


def _amt(value: float) -> str:
    return f"₹{abs(value):,.0f}"


def _signed(value: float) -> str:
    return f"{'+' if value >= 0 else '−'}{_amt(value)}"


def _num(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def evening_lines(rows: list, lowered: int, option_name) -> list:
    """The habits part of the evening note: today's habits, the best trade, and one thing to try tomorrow (the
    costliest habit's). ``option_name``: tradingsymbol -> "NIFTY 24900 CE"."""
    habits = day_habits(rows, lowered)
    if habits is None:
        return []
    parts = [f"{habits['buys']} buys ({habits['early']} before 10:00)"]
    if habits["median_hold"] is not None:
        parts.append(f"median hold {_num(habits['median_hold'])} min")
    if habits["quick_rebuys"]:
        parts.append(f"{habits['quick_rebuys']} bought within 2 min of a loss")
    if habits["lowered"]:
        parts.append(f"{habits['lowered']} stop{'s' if habits['lowered'] != 1 else ''} moved down")
    lines = ["🧭 Habits today: " + " · ".join(parts) + "."]
    best = best_trade(rows)
    if best is not None:
        held = f" in {_num(best['minutes'])} min" if best["minutes"] is not None else ""
        lines.append(f"✅ Best trade: {best['at']} {option_name(best['symbol'])}, {best['move']:+.0%}{held}.")
    worst = costliest(rows)
    if worst is not None:
        lines.append(f"🎯 Tomorrow, one thing: {TRY_TOMORROW[worst['tag']]} Today's {worst['n']} "
                     f"{TAG_TEXT[worst['tag']]}: {_signed(worst['sum'])} together.")
    return lines


def _mean(values: list, digits: int = 1) -> Optional[float]:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), digits) if values else None


def week_line(this_week: list, last_week: list) -> str:
    """This week's habits against last week's, as daily means: [] of ``day_habits`` per session each."""
    if not this_week or not last_week:
        return ""
    parts = []
    for key, label, unit in (("early", "buys before 10:00", " a day"), ("median_hold", "median hold", " min"),
                             ("quick_rebuys", "quick re-buys after a loss", " a day"),
                             ("lowered", "stops moved down", " a day")):
        old, new = _mean([d[key] for d in last_week]), _mean([d[key] for d in this_week])
        if old is not None and new is not None:
            parts.append(f"{label} {_num(old)} → {_num(new)}{unit}")
    return "📈 This week against last: " + " · ".join(parts) + "." if parts else ""


# ---------------------------------------------------------------------------
# read-only loaders
# ---------------------------------------------------------------------------

def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{Path(db_path).absolute().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_rows(db_path: str, first_day: str, last_day: str) -> list:
    """The stored trades of the sessions from ``first_day`` to ``last_day``; [] without the table."""
    try:
        with _connect(db_path) as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM partner_watch_trips WHERE session_date BETWEEN ? AND ? ORDER BY first_at",
                (first_day, last_day))]
    except sqlite3.Error:
        return []


def load_lowered(db_path: str, first_day: str, last_day: str) -> dict:
    """Stops moved down that the watch told, per session."""
    try:
        with _connect(db_path) as conn:
            return {d: n for d, n in conn.execute(
                "SELECT session_date, COUNT(*) FROM partner_watch_messages WHERE kind='LOWERED' AND sent=1 "
                "AND session_date BETWEEN ? AND ? GROUP BY session_date", (first_day, last_day))}
    except sqlite3.Error:
        return {}


def sessions_before(db_path: str, day: str, sessions: int = LOOKBACK_SESSIONS) -> list:
    """The last ``sessions`` stored sessions before ``day`` (oldest first)."""
    try:
        with _connect(db_path) as conn:
            found = [r[0] for r in conn.execute(
                "SELECT DISTINCT session_date FROM partner_watch_trips WHERE session_date < ? "
                "ORDER BY session_date DESC LIMIT ?", (day, sessions))]
    except sqlite3.Error:
        return []
    return sorted(found)


def weeks(db_path: str, day: str) -> tuple:
    """(this ISO week's sessions to ``day``, last week's) as lists of ``day_habits``."""
    today = date.fromisoformat(day)
    monday = today.toordinal() - today.weekday()
    first = date.fromordinal(monday - 7).isoformat()
    days = scorecard(db_path, first, day)
    this = [d for d in days if date.fromisoformat(d["day"]).toordinal() >= monday]
    last = [d for d in days if date.fromisoformat(d["day"]).toordinal() < monday]
    return this, last


def record_before(db_path: str, day: str) -> dict:
    """``record`` over the last LOOKBACK_SESSIONS sessions before ``day``."""
    days = sessions_before(db_path, day)
    return record(load_rows(db_path, days[0], days[-1])) if days else record([])


def scorecard(db_path: str, first_day: str, last_day: str) -> list:
    """[N09] The frozen scorecard: ``day_habits`` for each stored session in the window (SCORECARD.md)."""
    rows = load_rows(db_path, first_day, last_day)
    lowered = load_lowered(db_path, first_day, last_day)
    out = []
    for day in sorted({r["session_date"] for r in rows}):
        habits = day_habits([r for r in rows if r["session_date"] == day], lowered.get(day, 0))
        if habits is not None:
            out.append({"day": day, **habits})
    return out


def summarize(days: list) -> dict:
    """Means of the scorecard's daily habits, and the red sessions."""
    keys = ("buys", "early", "median_hold", "quick_exit_share", "quick_rebuys", "big_after_loss", "lowered")
    out = {key: _mean([d[key] for d in days], 3 if key == "quick_exit_share" else 1) for key in keys}
    out["sessions"] = len(days)
    out["red_sessions"] = sum(1 for d in days if d["result_sign"] < 0)
    return out


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="The partner's frozen habit scorecard (read-only).")
    parser.add_argument("--db", required=True)
    parser.add_argument("--from", dest="first", required=True)
    parser.add_argument("--to", dest="last", default=date.today().isoformat())
    args = parser.parse_args(argv)
    days = scorecard(args.db, args.first, args.last)
    print(json.dumps({"spec": SPEC_ID, "from": args.first, "to": args.last, "days": days,
                      "summary": summarize(days)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
