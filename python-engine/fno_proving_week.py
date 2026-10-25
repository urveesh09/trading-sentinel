"""[O25 2026-10-25] The owner's five-session proving week for the paper F&O single-leg book.

The owner (Oct 25): "I will give the system 5 more days to prove itself, if it's
able to then you tell me", before ₹12,500 of real money goes on the book
(fno_live_test.py). These rules were fixed on Sunday Oct 25, before the first
session, and are scored once; they are not tuned afterwards.

Window: the first FNO_PROVING_SESSIONS NSE trading days from FNO_PROVING_START
(Mon Oct 26 to Fri Oct 30, 2026). Scored: FNO_PAPER single-leg positions
entered in the window, each at ONE lot, because the real test trades one lot:
its two fills times one lot, less one lot's own full charges. [O25b, before
the first session] Not its P&L divided by its lots: brokerage is a fixed
charge per order, so a halved two-lot result understated one lot's costs.

Verdict, once the last session has closed:
  PROVED       at least one trade, one-lot net >= ₹0, clean operation, and the
               15% drawdown halt not active at the end;
  NOT_PROVED   one-lot net < ₹0, operation not clean, or the drawdown halt active;
  NO_EVIDENCE  no trade in the window (and nothing else wrong);
  UNAVAILABLE  [O25b] the drawdown-halt state could not be read: a required
               condition that is unknown is never a pass.
Clean operation: every window position closed on its entry day, and none of
them needed exit recovery (a row in fno_exit_intents or fno_exit_recoveries).

Shown beside it (not scored): wins, exit reasons, the actual-size paper P&L,
and what ₹12,500 would have done at one lot, one position at a time, taking
only the trades whose lot it could pay for.

Five sessions cannot prove an edge: the book trades two or three times a week.
The verdict says whether anything broke and whether the week lost money.
Starting the real-money test is the owner's decision.

CLI (read-only): python -m fno_proving_week [--db PATH]
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta
from typing import Optional

import aiosqlite
import pytz
import structlog

from config import settings

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")
SOURCE = "FNO_PAPER"
DAY_DONE = (15, 40)        # the derivatives close: a window day is scored after it


def window_days(db_path: str) -> list[date]:
    """The window's trading days (holiday cache, else the static list; never the network)."""
    from market_calendar import is_trading_day_sync
    day = date.fromisoformat(str(settings.FNO_PROVING_START))
    days: list[date] = []
    while len(days) < int(settings.FNO_PROVING_SESSIONS):
        if is_trading_day_sync(day, db_path):
            days.append(day)
        day += timedelta(days=1)
    return days


def _day_closed(day: date, now: datetime) -> bool:
    return now.date() > day or (now.date() == day and (now.hour, now.minute) >= DAY_DONE)


def replay_small_account(trades: list[dict], cash: float) -> dict:
    """One lot each, one open position at a time, only when the lot fits the cash."""
    taken = skipped = 0
    busy_until = None
    for t in sorted(trades, key=lambda r: r["entry_time"]):
        if t["pnl"] is None:
            continue
        cost = float(t["entry_premium"]) * int(t["lot_size"])
        if cost > cash or (busy_until is not None and t["entry_time"] < busy_until):
            skipped += 1
            continue
        taken += 1
        cash += t["one_lot"]
        busy_until = t["exit_time"] or t["entry_time"]
    return {"taken": taken, "skipped": skipped, "end_cash": round(cash, 2)}


async def score(db_path: str, now: Optional[datetime] = None) -> dict:
    """The week as it stands at ``now``; read-only."""
    now = now or datetime.now(IST)
    days = window_days(db_path)
    first, last = days[0].isoformat(), days[-1].isoformat()
    trades: list[dict] = []
    recovery_ids: set = set()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        tables = {r[0] for r in await (await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}
        if "fno_positions" in tables:
            trades = [dict(r) for r in await (await db.execute(
                "SELECT id, tradingsymbol, underlying, entry_date, entry_time, exit_date, exit_time, status, "
                "entry_premium, exit_premium, lot_size, COALESCE(initial_lots, lots) AS lots, pnl, exit_reason "
                "FROM fno_positions WHERE source=? AND entry_date BETWEEN ? AND ? ORDER BY entry_time",
                (SOURCE, first, last))).fetchall()]
        for table in ("fno_exit_intents", "fno_exit_recoveries"):
            if table in tables and trades:
                marks = ",".join("?" for _ in trades)
                recovery_ids |= {r[0] for r in await (await db.execute(
                    f"SELECT position_id FROM {table} WHERE source=? AND position_id IN ({marks})",
                    (SOURCE, *[t["id"] for t in trades]))).fetchall()}
    from fno_live_test import one_lot_pnl
    for t in trades:
        t["one_lot"] = (round(one_lot_pnl(t["entry_premium"], t["exit_premium"], t["lot_size"],
                                          t["underlying"] or "NIFTY"), 2)
                        if t["pnl"] is not None and t["entry_premium"] and t["exit_premium"] else None)
    problems = []
    for t in trades:
        entered = date.fromisoformat(t["entry_date"])
        if t["status"] == "CLOSED" and t["exit_date"] != t["entry_date"]:
            problems.append(f"{t['tradingsymbol']} closed on {t['exit_date']}, not its entry day")
        elif t["status"] != "CLOSED" and _day_closed(entered, now):
            problems.append(f"{t['tradingsymbol']} still {t['status'].lower()} after its day")
        if t["id"] in recovery_ids:
            problems.append(f"{t['tradingsymbol']} needed exit recovery")
    closed = [t for t in trades if t["one_lot"] is not None]
    halted = None
    try:
        from fno_shared_risk import policy_from_settings, shared_fno_entry_policy
        decision = await shared_fno_entry_policy(db_path, source=SOURCE, pool_rs=float(settings.FNO_PAPER_BANKROLL),
                                                 today_ist=now.date(), policy=policy_from_settings())
        if getattr(decision.view, "available", False):
            halted = any(str(h).startswith("drawdown_halt") for h in decision.active_halts)
    except Exception as exc:
        logger.warning("fno_proving_week_halt_unreadable err=%s", type(exc).__name__)
    done = sum(1 for d in days if _day_closed(d, now))
    net = round(sum(t["one_lot"] for t in closed), 2)
    result = {
        "days": [d.isoformat() for d in days], "sessions_done": done, "sessions": len(days),
        "trades": len(trades), "closed": len(closed), "wins": sum(1 for t in closed if t["one_lot"] > 0),
        "one_lot_net": net, "actual_net": round(sum(float(t["pnl"]) for t in closed), 2),
        "problems": problems, "drawdown_halt": halted,
        "small_account": replay_small_account(closed, float(settings.FNO_LIVE_TEST_CAPITAL)),
        "by_day": {d.isoformat(): [t for t in closed if t["entry_date"] == d.isoformat()] for d in days},
    }
    if done < len(days):
        result["verdict"] = "IN_PROGRESS"
    elif halted is None:
        result["verdict"] = "UNAVAILABLE"
    elif problems or halted:
        result["verdict"] = "NOT_PROVED"
    elif not closed:
        result["verdict"] = "NO_EVIDENCE"
    else:
        result["verdict"] = "PROVED" if net >= 0 else "NOT_PROVED"
    return result


def _rs(value: float) -> str:
    return f"{'+' if value >= 0 else '-'}₹{abs(value):,.0f}"


def render(result: dict, today: Optional[date] = None) -> str:
    """The owner's message for the week as scored."""
    days = [date.fromisoformat(d) for d in result["days"]]
    today = today or datetime.now(IST).date()
    lines = []
    if today in days:
        lines.append(f"📋 F&O proving week, day {days.index(today) + 1} of {len(days)} ({today:%a %d %b})")
        todays = result["by_day"].get(today.isoformat(), [])
        if todays:
            for t in todays:
                lines.append(f"Today: {t['tradingsymbol']} {_rs(t['one_lot'])} a lot ({t['exit_reason']}).")
        else:
            lines.append("Today: no paper trade.")
    else:
        lines.append(f"📋 F&O proving week ({days[0]:%d %b} to {days[-1]:%d %b})")
    if result["closed"]:
        lines.append(f"Week so far: {result['closed']} trade(s), {result['wins']} won, {_rs(result['one_lot_net'])} "
                     f"at one lot after one lot's own charges (paper size {_rs(result['actual_net'])}).")
    else:
        lines.append("Week so far: no paper trade.")
    lines.append("Operation: clean (every trade closed the same day by its rules)." if not result["problems"]
                 else "Operation: NOT clean: " + "; ".join(result["problems"]) + ".")
    small = result["small_account"]
    if result["closed"]:
        lines.append(f"₹{settings.FNO_LIVE_TEST_CAPITAL:,.0f} at one lot would have taken {small['taken']} of them "
                     f"(skipped {small['skipped']}): ₹{small['end_cash']:,.0f}.")
    verdict = result["verdict"]
    if verdict == "IN_PROGRESS":
        lines.append(f"Verdict after the close on {days[-1]:%a %d %b}.")
        return "\n".join(lines)
    head = {"PROVED": "✅ PROVED", "NOT_PROVED": "❌ NOT PROVED", "NO_EVIDENCE": "➖ NO EVIDENCE",
            "UNAVAILABLE": "⚠️ UNAVAILABLE"}[verdict]
    why = {"PROVED": "it traded, did not lose at one lot, and nothing broke.",
           "UNAVAILABLE": "the drawdown-halt state could not be read, and the verdict needs it. Run "
                          "`python -m fno_proving_week` again; it is scored from the same week.",
           "NOT_PROVED": ("the drawdown halt is on." if result["drawdown_halt"] else
                          "operation was not clean." if result["problems"] else
                          "the week lost money at one lot."),
           "NO_EVIDENCE": "no signal traded, so nothing was tested."}[verdict]
    lines.append(f"{head}: {why}")
    lines.append("Five sessions cannot prove an edge (the book trades two or three times a week); this says whether "
                 "anything broke and whether the week lost money. Starting the ₹12,500 real-money test is your "
                 "decision: FNO_LIVE_TEST_ENABLED=true (docs/runbooks/fno-live-test.md).")
    return "\n".join(lines)


async def _told(db_path: str, day: str) -> bool:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS fno_evening_report_told (day TEXT PRIMARY KEY, told_at TEXT)")
        await db.commit()
        return (await (await db.execute("SELECT 1 FROM fno_evening_report_told WHERE day=?",
                                        (day,))).fetchone()) is not None


async def _mark_told(db_path: str, day: str, now: datetime) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT OR IGNORE INTO fno_evening_report_told(day, told_at) VALUES(?,?)",
                         (day, now.isoformat()))
        await db.commit()


async def evening_report(db_path: str, now: Optional[datetime] = None, notify=None) -> Optional[str]:
    """[O25] One owner message after the close: the proving week on its days, and the
    real-money test's trades beside their paper twins. Once a day; never raises."""
    now = now or datetime.now(IST)
    try:
        day = now.date().isoformat()
        if not _day_closed(now.date(), now) or await _told(db_path, day):
            return None
        parts = []
        days = window_days(db_path)
        if days[0] <= now.date() <= days[-1]:
            parts.append(render(await score(db_path, now), now.date()))
        import fno_live_test
        live = await fno_live_test.day_report(db_path, day)
        if live:
            parts.append(live)
        if not parts:
            return None
        text = "\n\n".join(parts)
        if notify is None:
            from operator_alert import notify_operator as notify
        if await notify(text, event="fno_evening_report"):
            await _mark_told(db_path, day, now)
            return text
        return None
    except Exception as exc:
        logger.warning("fno_evening_report_failed err=%s", type(exc).__name__)
        return None


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="The F&O proving week, as it stands (read-only).")
    parser.add_argument("--db", default=settings.DB_PATH)
    args = parser.parse_args(argv)
    print(render(asyncio.run(score(args.db))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
