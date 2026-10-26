"""[O26 2026-10-26] Do the check's warnings pick out the partner's losing trades? Scored on the trades the watch
stored, read-only.

    python -m partner_watch_score [FIRST_DAY [LAST_DAY]]     (default: FROZEN_FROM to the latest stored day)

Frozen on 2026-10-26 (O26), before any day it decides on. Owner's rules: freeze, then score; no tuning on a day
already seen; a result informs the owner and changes nothing by itself.

Trades: ``partner_watch_trips`` rows that are closed and were bought that day (not carried in). The result is
after charges (``realised``); a trade whose fills came partly from the orders (``exact`` 0) counts and is said.

Warnings, as the watch worked them out at the buy (the same ones a check gives):
  CHASED_SPIKE       the 15-minute run before the buy (the plan's) at least partner_insights.SPIKE_RUN_PCT (20%)
  AFTER_LOSS         bought within partner_coach.REENTRY_WINDOW_MIN (30 min) of a losing exit
  BIGGER_AFTER_LOSS  that, with more units than the losing trade
  UNUSUAL_SIZE       the opening buy's share of cash over partner_insights.USUAL_SIZE_MULT (1.5x) the usual share
  ANY                any of them
CHECKED (a check reply for the same option sent in the CHECK_LOOKBACK_MIN, 15, minutes before the buy) is not a
warning: checked and unchecked trades are reported apart.

Verdict per warning, on decision days only (FROZEN_FROM on; Oct 26 is the day these were designed on, so it is
shown and never counted):
  SUPPORTED      all four hold:
                   1. at least MIN_WARNED (20) warned trades;
                   2. the warned trades' mean result is below the unwarned trades' mean;
                   3. the warned trades' total is negative (not taking them would have kept money);
                   4. it is still negative without the warned trades' single worst loss;
  TOO_FEW        under MIN_WARNED warned trades;
  NOT_SUPPORTED  otherwise.
A skipped trade's cash is taken as idle (not traded elsewhere). Nothing here says what the partner would have done
instead, and nothing here is about the system's own trading.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Optional

FROZEN_FROM = "2026-10-27"
DESIGN_DAYS = ("2026-10-26",)
MIN_WARNED = 20
CHECK_LOOKBACK_MIN = 15
WARNINGS = ("CHASED_SPIKE", "AFTER_LOSS", "BIGGER_AFTER_LOSS", "UNUSUAL_SIZE", "ANY")


def _dt(value) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def warnings_of(trip: dict) -> set:
    """The warnings a check would have given at this trade's buy (module doc)."""
    from partner_insights import SPIKE_RUN_PCT, USUAL_SIZE_MULT
    out = set()
    if trip.get("run_pct") is not None and trip["run_pct"] >= SPIKE_RUN_PCT:
        out.add("CHASED_SPIKE")
    after = trip.get("after_loss")
    if after:
        out.add("AFTER_LOSS")
        if after.get("bigger"):
            out.add("BIGGER_AFTER_LOSS")
    usual, share = trip.get("usual"), trip.get("paid_share")
    if usual and share is not None and share > USUAL_SIZE_MULT * usual:
        out.add("UNUSUAL_SIZE")
    if out:
        out.add("ANY")
    return out


def load(db_path: str, first_day: Optional[str] = None, last_day: Optional[str] = None) -> tuple:
    """(first_day, last_day, trades): the closed trades bought that day, each with its warnings and whether it was
    checked; read-only."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='partner_watch_trips'").fetchone():
            return first_day, last_day, []
        first_day = first_day or FROZEN_FROM
        last_day = last_day or db.execute("SELECT MAX(session_date) FROM partner_watch_trips").fetchone()[0] or first_day
        cols = ("session_date", "position_key", "tradingsymbol", "first_at", "realised", "exact", "run_pct",
                "after_loss", "usual", "paid_share")
        rows = db.execute(f"SELECT {', '.join(cols)} FROM partner_watch_trips WHERE session_date>=? AND "
                          "session_date<=? AND carried=0 AND realised IS NOT NULL ORDER BY session_date, first_at",
                          (first_day, last_day)).fetchall()
        checks = db.execute("SELECT session_date, context, COALESCE(sent_at, created_at) FROM partner_watch_messages "
                            "WHERE kind='CHECK' AND sent=1 AND session_date>=? AND session_date<=?",
                            (first_day, last_day)).fetchall() if rows else []
    finally:
        db.close()
    asked: dict = {}
    for day, context, at in checks:
        try:
            symbol = ((json.loads(context or "{}") or {}).get("contract") or {}).get("tradingsymbol")
        except ValueError:
            symbol = None
        when = _dt(at)
        if symbol and when is not None:
            asked.setdefault((day, symbol), []).append(when)
    trades = []
    for row in rows:
        trip = dict(zip(cols, row))
        try:
            trip["after_loss"] = json.loads(trip["after_loss"]) if trip["after_loss"] else None
        except ValueError:
            trip["after_loss"] = None
        bought = _dt(trip["first_at"])
        trip["warnings"] = warnings_of(trip)
        trip["checked"] = bought is not None and any(
            bought - timedelta(minutes=CHECK_LOOKBACK_MIN) <= at <= bought
            for at in asked.get((trip["session_date"], trip["tradingsymbol"]), []))
        trades.append(trip)
    return first_day, last_day, trades


def _side(results: list) -> dict:
    return {"n": len(results), "won": sum(r > 0 for r in results), "total": round(sum(results), 2),
            "mean": round(sum(results) / len(results), 2) if results else None}


def score(trades: list) -> dict:
    """Per warning: warned and unwarned trades (decision days only) and the verdict (module doc); also checked
    against unchecked. Trades before FROZEN_FROM (the design day among them) are counted apart, never scored."""
    decided = [t for t in trades if t["session_date"] not in DESIGN_DAYS and t["session_date"] >= FROZEN_FROM]
    out = {"decision_trades": len(decided), "estimated": sum(not t["exact"] for t in decided),
           "days": sorted({t["session_date"] for t in decided}), "seen_trades": len(trades) - len(decided),
           "warnings": {}}
    for name in WARNINGS:
        warned = [t["realised"] for t in decided if name in t["warnings"]]
        unwarned = [t["realised"] for t in decided if name not in t["warnings"]]
        w, u = _side(warned), _side(unwarned)
        if w["n"] < MIN_WARNED:
            verdict = "TOO_FEW"
        else:
            checks = [u["mean"] is not None and w["mean"] < u["mean"], w["total"] < 0, w["total"] - min(warned) < 0]
            verdict = "SUPPORTED" if all(checks) else "NOT_SUPPORTED"
        out["warnings"][name] = {"warned": w, "unwarned": u, "verdict": verdict}
    out["checked"] = _side([t["realised"] for t in decided if t["checked"]])
    out["unchecked"] = _side([t["realised"] for t in decided if not t["checked"]])
    return out


def _rupees(value: Optional[float]) -> str:
    return "-" if value is None else f"{'−' if value < 0 else '+'}₹{abs(value):,.0f}"


def _line(label: str, side: dict) -> str:
    return (f"{label} {side['n']} trades, {side['won']} won, total {_rupees(side['total'])}, "
            f"mean {_rupees(side['mean'])}")


def render(first_day: str, last_day: str, data: dict) -> str:
    lines = [f"Check warnings scored, {first_day} to {last_day} (frozen O26; decision days from {FROZEN_FROM})"]
    if not data["decision_trades"]:
        lines.append("No closed trade stored on a decision day yet.")
    else:
        lines.append(f"{data['decision_trades']} closed trades on {len(data['days'])} day"
                     f"{'s' if len(data['days']) != 1 else ''}"
                     + (f" ({data['estimated']} with fills from the orders)" if data["estimated"] else "") + ".")
        for name in WARNINGS:
            entry = data["warnings"][name]
            lines.append(f"  {name}: {entry['verdict']}")
            lines.append("    " + _line("warned:  ", entry["warned"]))
            lines.append("    " + _line("unwarned:", entry["unwarned"]))
        lines.append("  " + _line("checked before the buy:  ", data["checked"]))
        lines.append("  " + _line("not checked before the buy:", data["unchecked"]))
    if data["seen_trades"]:
        lines.append(f"{data['seen_trades']} trades before {FROZEN_FROM} (seen while designing): never scored.")
    lines.append(f"A verdict needs at least {MIN_WARNED} warned trades and informs the owner; it changes nothing.")
    return "\n".join(lines)


def main(argv: list) -> int:
    from config import settings
    first_day, last_day, trades = load(settings.DB_PATH, argv[1] if len(argv) > 1 else None,
                                       argv[2] if len(argv) > 2 else None)
    print(render(first_day or FROZEN_FROM, last_day or first_day or FROZEN_FROM, score(trades)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
