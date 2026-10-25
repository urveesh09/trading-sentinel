"""[O24h 2026-10-24] How far the F&O paper exits ran past their own levels, read from the database (read-only).

    python -m fno_exit_report [FIRST_DAY [LAST_DAY]]        (default: every closed single-leg paper trade)

For each closed single-leg paper trade (``fno_positions``, source FNO_PAPER)
whose exit had a level:
  - underlying_stop: the stop on the index (``stop_underlying``);
  - trail_stop: the trail on the index (``trail_stop_underlying``);
  - premium_stop: the stop on the option (``premium_stop``).
"Past" is how far beyond that level the exit filled, in index points (in
premium for the premium stop); a negative number is an exit before the level.
The rupee figure is an estimate at the entry delta (points x |delta| x
quantity: linear, IV and gamma ignored). Exits on a time stop, the profit
lock, a target or the forced close have no fixed level and are only counted.

The exit checks ran every FNO_SCAN_INTERVAL_SEC (90 s) until the fast exit
pass (FNO_FAST_EXIT_INTERVAL_SEC, 10 s) was switched on (Dev Oct 9); each row
shows its date. These are facts about execution timing; an exit exactly at a
level was never certain (the price can gap through it).
"""
from __future__ import annotations

import sqlite3
import sys
from typing import Optional

LEVELS = {"underlying_stop": "stop_underlying", "trail_stop": "trail_stop_underlying", "premium_stop": "premium_stop"}


def _past(reason: str, direction: str, level: float, row: dict) -> float:
    """Points beyond the level, positive when the exit was worse than the level."""
    if reason == "premium_stop":                       # a bought option: its stop is under the entry premium
        return round(level - float(row["exit_premium"]), 2)
    exit_at = float(row["exit_underlying"])
    return round((level - exit_at) if direction == "LONG" else (exit_at - level), 2)


def exit_slippage(db_path: str, first_day: Optional[str] = None, last_day: Optional[str] = None) -> dict:
    """Each closed paper exit with a level, and a summary per exit reason."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in db.execute(
            "SELECT id, entry_date, exit_time, tradingsymbol, direction, qty, delta_at_entry, exit_reason, "
            "exit_underlying, exit_premium, stop_underlying, trail_stop_underlying, premium_stop, pnl "
            "FROM fno_positions WHERE source='FNO_PAPER' AND status='CLOSED' AND entry_date>=? AND entry_date<=? "
            "ORDER BY exit_time", (first_day or "0000-00-00", last_day or "9999-12-31"))]
    finally:
        db.close()
    exits, others = [], {}
    for row in rows:
        reason = str(row["exit_reason"] or "")
        level = row.get(LEVELS.get(reason, ""), None)
        if level is None or (reason != "premium_stop" and row["exit_underlying"] is None):
            others[reason or "-"] = others.get(reason or "-", 0) + 1
            continue
        past = _past(reason, str(row["direction"]), float(level), row)
        rupees = (round(max(past, 0.0) * abs(float(row["delta_at_entry"] or 0.0)) * int(row["qty"] or 0))
                  if reason != "premium_stop" else round(max(past, 0.0) * int(row["qty"] or 0)))
        exits.append({"date": row["entry_date"], "exit_time": row["exit_time"], "symbol": row["tradingsymbol"],
                      "direction": row["direction"], "reason": reason, "level": round(float(level), 2),
                      "past": past, "unit": "premium" if reason == "premium_stop" else "points",
                      "rupees_estimate": rupees, "pnl": round(float(row["pnl"] or 0.0))})
    summary = {}
    for item in exits:
        entry = summary.setdefault(item["reason"], {"n": 0, "past": [], "rupees_estimate": 0, "worse": 0})
        entry["n"] += 1
        entry["past"].append(item["past"])
        entry["rupees_estimate"] += item["rupees_estimate"]
        entry["worse"] += int(item["past"] > 0)
    for entry in summary.values():
        values = sorted(entry.pop("past"))
        entry["past_median"] = values[len(values) // 2]
        entry["past_max"] = values[-1]
    return {"first_day": first_day, "last_day": last_day, "exits": exits, "by_reason": summary,
            "without_level": dict(sorted(others.items()))}


def render(data: dict) -> str:
    lines = ["F&O paper exits past their own level (positive: worse than the level)"]
    if not data["exits"] and not data["without_level"]:
        return "\n".join(lines + ["No closed paper exits."])
    for item in data["exits"]:
        lines.append(f"  {item['date']}  {item['symbol']:<22} {item['direction']:<5} {item['reason']:<15} "
                     f"level {item['level']:g}  past {item['past']:+g} {item['unit']}  "
                     f"about Rs{item['rupees_estimate']:,}  (trade {item['pnl']:+,})")
    for reason, entry in sorted(data["by_reason"].items()):
        lines.append(f"{reason}: {entry['n']} exits, {entry['worse']} worse than the level, median "
                     f"{entry['past_median']:+g}, max {entry['past_max']:+g}, about Rs{entry['rupees_estimate']:,} "
                     f"in all")
    if data["without_level"]:
        lines.append("Without a level: " + ", ".join(f"{k} {v}" for k, v in data["without_level"].items()))
    return "\n".join(lines)


def main(argv: list) -> int:
    from config import settings
    print(render(exit_slippage(settings.DB_PATH, argv[1] if len(argv) > 1 else None,
                               argv[2] if len(argv) > 2 else None)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
