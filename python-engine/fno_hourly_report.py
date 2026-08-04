"""
[FNO-HOURLY 2026-07-10] Per-hour Telegram brief for the F&O subsystem
(spec §1: "reports hourly to Telegram").

Built read-only from fno_positions + fno_signals. The report must make a
ZERO-TRADE day self-explanatory (§9.2): it distinguishes
  - "declined expensive premium" (pool_below_min_viable dominating --
    healthy self-regulation, reported as such)
  - "no breakout today" (engine reject reasons)
  - "engine evaluated nothing" (0 evaluations -- suspicious, watchdog
    territory)
Delivery is owned by the main.py wrapper (same notify endpoint pattern
as penny edge).
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Optional

import aiosqlite
import pytz
import structlog

import fno_positions as fpos
from config import settings

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

REPORT_START_HOUR = 10   # first brief at 10:00 IST
REPORT_END_HOUR = 15     # last at 15:00 IST (after that the EOD story is closed)


def is_in_report_window(now_ist: datetime) -> bool:
    return REPORT_START_HOUR <= now_ist.hour <= REPORT_END_HOUR


async def _day_signal_stats(db_path: str, today_iso: str) -> dict:
    """Evaluations / accepts / reject histogram for today (UTC-stored
    evaluated_at is fine to filter by bar_ts date, which is IST)."""
    out = {"evaluations": 0, "accepts": 0, "rejects": Counter()}
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fno_signals'"
            ) as cur:
                if await cur.fetchone() is None:
                    return out
            async with db.execute(
                "SELECT accepted, reject_reason FROM fno_signals WHERE bar_ts LIKE ?",
                (today_iso + "%",),
            ) as cur:
                rows = await cur.fetchall()
        for accepted, reason in rows:
            out["evaluations"] += 1
            if accepted:
                out["accepts"] += 1
            elif reason:
                out["rejects"][reason] += 1
    except Exception as exc:
        logger.error("fno_hourly_signal_stats_failed err=%s", str(exc))
    return out


async def build_hourly_report(
    db_path: Optional[str] = None, now_ist: Optional[datetime] = None,
    regime: str = "UNKNOWN",
) -> str:
    db_path = db_path or settings.DB_PATH
    now_ist = now_ist or datetime.now(IST)
    today_iso = now_ist.date().isoformat()

    lines = [f"*F&O hourly* `{now_ist.strftime('%Y-%m-%d %H:%M')} IST` regime=`{regime}`"]

    for source in ("FNO_PAPER", "FNO_LIVE"):
        if source == "FNO_PAPER" and settings.FNO_DISABLE_PAPER:
            continue
        if source == "FNO_LIVE" and settings.FNO_DISABLE_LIVE:
            continue
        open_pos = await fpos.open_positions(db_path, source)
        closed = await fpos.closed_today(db_path, source, today_iso)
        day_pnl = sum(c["pnl"] or 0.0 for c in closed)
        pool = (
            settings.FNO_PAPER_BANKROLL if source == "FNO_PAPER"
            else settings.FNO_LIVE_BANKROLL
        )
        # [PAPER-MARKING 2026-08-04] Mark the leg and every rupee in it. This
        # report's numbers are an order of magnitude larger than the live
        # book's and used to render identically -- see performance.fmt_money.
        from performance import fmt_money, is_paper_source
        paper = is_paper_source(source)
        lines.append(
            f"--- *{source}*{' (PAPER MONEY)' if paper else ''} "
            f"pool={fmt_money(pool, source)} | open={len(open_pos)} "
            f"closed_today={len(closed)} day_pnl={fmt_money(day_pnl, source)} ---"
        )
        for p in open_pos:
            lines.append(
                f"OPEN `{p.tradingsymbol}` {p.direction} lots={p.lots} "
                f"entry={p.entry_premium:.2f} stop_u={p.stop_underlying:.0f} "
                f"tgt_u={p.target_underlying:.0f} trail={'Y' if p.trail_active else 'N'}"
            )
        for c in closed:
            lines.append(
                f"CLOSED `{c['tradingsymbol']}` {c['exit_reason']} "
                f"{c['entry_premium']:.2f}->{c['exit_premium']:.2f} "
                f"pnl={fmt_money(c['pnl'] or 0.0, source)} "
                f"({(c['r_multiple'] or 0):+.2f}R)"
            )

    stats = await _day_signal_stats(db_path, today_iso)
    lines.append(
        f"Signals today: evaluations={stats['evaluations']} accepts={stats['accepts']}"
    )
    if stats["rejects"]:
        top = stats["rejects"].most_common(3)
        lines.append("Top rejects: " + ", ".join(f"`{r}`x{n}" for r, n in top))
        # §9.2: self-regulation is reported, not alarmed.
        mv = stats["rejects"].get("pool_below_min_viable", 0)
        if mv and mv >= max(n for _, n in top):
            lines.append(
                "Note: premium too rich for the pool today -- the module is "
                "correctly declining (volatility filter via sizing identity, §3)."
            )
    elif stats["evaluations"] == 0 and now_ist.hour >= 11:
        lines.append(
            "WARNING: zero evaluations so far -- check fno_orchestrator_tick "
            "breadcrumbs (dead engine != quiet market)."
        )
    return "\n".join(lines)
