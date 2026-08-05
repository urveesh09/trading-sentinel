"""
[ROADMAP-2.8 2026-07-12] Persistent ops metrics time-series.

Docker's log ring buffer forgets; these two tables don't. They exist so
that "did the engine run clean for 30 days?" and "how many accepts did
each subsystem produce last week?" are SQL queries instead of manual
log greps:

  ops_liveness_daily -- one row per IST day: scheduler-tick count and
      the worst gap between consecutive ticks (total and market-hours).
      Fed by main._scheduler_tick_job (the ROADMAP-2.4 loop-progress
      tick, 60s, 24/7). This is the attestation source for the F&O
      go-live liveness gate (fno_risk.fno_go_live_check condition 4,
      FNO_LIVENESS_30D_CLEAN) -- previously an operator log grep over
      logs that rotate away.

  ops_funnel_daily -- one row per IST day per subsystem (momentum /
      penny / fno): evaluated, accepted, rejected + top reject reasons.
      The accept-watchdogs alarm on TODAY's pathology; this keeps the
      history they alarm from.

Isolation rule (same as the accept-watchdogs): read-only over the
signal tables, writes only its own ops_* tables, imports nothing from
engine/regime/risk/portfolio. Every public function catches and logs --
metrics must never break the trading loop.
"""
from __future__ import annotations

import json
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Optional

import aiosqlite
import pytz
import structlog

logger = structlog.get_logger()

IST = pytz.timezone("Asia/Kolkata")

# Gate 4 of fno_go_live_check: "no liveness gap > 5 min in 30 days".
LIVENESS_MAX_GAP_SEC = 300.0

_TOP_REJECTS = 5


async def init_ops_metrics_db(db_path: str) -> None:
    """Create both ops tables if absent. Idempotent, never raises."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ops_liveness_daily (
                    date_ist               TEXT PRIMARY KEY,
                    ticks                  INTEGER NOT NULL,
                    max_gap_seconds        REAL NOT NULL,
                    max_gap_market_seconds REAL NOT NULL,
                    as_of                  TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ops_funnel_daily (
                    date_ist    TEXT NOT NULL,
                    subsystem   TEXT NOT NULL,
                    evaluated   INTEGER NOT NULL,
                    accepted    INTEGER NOT NULL,
                    rejected    INTEGER NOT NULL,
                    top_rejects TEXT,
                    as_of       TEXT NOT NULL,
                    PRIMARY KEY (date_ist, subsystem)
                )
            """)
            await db.commit()
    except Exception as e:
        logger.error("ops_metrics_init_failed db=%s error=%s", db_path, str(e))


# -------------------------------------------------------------------
# Liveness (scheduler-tick gaps)
# -------------------------------------------------------------------

def _gap_overlaps_market(end_ist: datetime, gap_seconds: float) -> bool:
    """Did the interval [end - gap, end] touch a weekday 09:15-15:30 IST
    session? Weekday-only (no holiday lookup: this runs every minute and
    must stay DB-free; a frozen scheduler on a holiday is still worth
    seeing in the report -- it would stay frozen into the next session)."""
    start_ist = end_ist - timedelta(seconds=gap_seconds)
    day = start_ist.date()
    while day <= end_ist.date():
        if day.weekday() < 5:
            open_dt = datetime.combine(day, dtime(9, 15), tzinfo=end_ist.tzinfo)
            close_dt = datetime.combine(day, dtime(15, 30), tzinfo=end_ist.tzinfo)
            if start_ist <= close_dt and end_ist >= open_dt:
                return True
        day += timedelta(days=1)
    return False


async def record_scheduler_tick(
    db_path: str, now_ist: datetime, gap_seconds: Optional[float]
) -> None:
    """Fold one scheduler tick into today's liveness row. `gap_seconds`
    is the time since the previous tick (None on the first tick after
    boot -- restarts don't fabricate a gap). Never raises."""
    try:
        gap = float(gap_seconds) if gap_seconds is not None else 0.0
        market_gap = gap if (gap > 0 and _gap_overlaps_market(now_ist, gap)) else 0.0
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """INSERT INTO ops_liveness_daily
                       (date_ist, ticks, max_gap_seconds,
                        max_gap_market_seconds, as_of)
                   VALUES (?, 1, ?, ?, ?)
                   ON CONFLICT(date_ist) DO UPDATE SET
                       ticks = ticks + 1,
                       max_gap_seconds =
                           MAX(max_gap_seconds, excluded.max_gap_seconds),
                       max_gap_market_seconds =
                           MAX(max_gap_market_seconds,
                               excluded.max_gap_market_seconds),
                       as_of = excluded.as_of""",
                (
                    now_ist.strftime("%Y-%m-%d"), gap, market_gap,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()
    except Exception as e:
        logger.warning("ops_liveness_record_failed error=%s", str(e))


async def liveness_report(
    db_path: str, days: int = 30, now_ist: Optional[datetime] = None
) -> dict:
    """Per-day liveness rows over the last `days` IST calendar days plus
    the summary the F&O go-live gate needs: is every market-hours gap
    <= 5 min, and over how many covered days?

    `now_ist` anchors the window and defaults to the wall clock. It is
    injectable ONLY so tests can be deterministic: the first version of
    this function read datetime.now(IST) directly, and the tests around
    it pinned literal dates against that moving anchor. They passed on
    the day they were written (2026-07-12) and started failing the very
    next morning, when the same literal date fell one day outside the
    window. Production always passes None; a test that must not rot
    passes its own anchor.

    The window is (since, today] -- strictly-greater on purpose, so a
    `days`-day window yields at most exactly `days` rows, which is what
    market_gap_clean's `len(rows) >= days` check is calibrated against.
    """
    anchor = now_ist or datetime.now(IST)
    since = (anchor - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                """SELECT date_ist, ticks, max_gap_seconds,
                          max_gap_market_seconds
                   FROM ops_liveness_daily
                   WHERE date_ist > ? ORDER BY date_ist""",
                (since,),
            ) as cur:
                rows = await cur.fetchall()
    except Exception as e:
        logger.error("ops_liveness_report_failed error=%s", str(e))
        return {"days": days, "error": str(e), "rows": []}
    worst_market_gap = max((r[3] for r in rows), default=0.0)
    return {
        "days": days,
        "days_covered": len(rows),
        "worst_market_gap_seconds": worst_market_gap,
        "gap_threshold_seconds": LIVENESS_MAX_GAP_SEC,
        # True only when the window has data for the full period AND no
        # market-hours gap ever exceeded the threshold. This is the
        # queryable form of fno_go_live_check condition 4.
        "market_gap_clean": (
            len(rows) >= days and worst_market_gap <= LIVENESS_MAX_GAP_SEC
        ),
        "rows": [
            {
                "date_ist": r[0], "ticks": r[1],
                "max_gap_seconds": r[2], "max_gap_market_seconds": r[3],
            }
            for r in rows
        ],
    }


# -------------------------------------------------------------------
# Daily gate funnels (momentum / penny / fno)
# -------------------------------------------------------------------

def _ist_day_utc_bounds(date_ist: str) -> tuple[str, str]:
    """UTC ISO bounds [start, end) of an IST calendar day, matching the
    `datetime.now(timezone.utc).isoformat()` format the signal loggers
    write, so string comparison in SQL is correct."""
    day = datetime.strptime(date_ist, "%Y-%m-%d")
    start = IST.localize(day).astimezone(timezone.utc)
    return start.isoformat(), (start + timedelta(days=1)).isoformat()


async def _funnel_counts(
    db, table: str, where_day: str, params: tuple,
    ticker_col: str = "ticker",
) -> Optional[tuple]:
    """(evaluated, accepted, rejected, {reason: n} top rejects) for one
    subsystem-day, or None when the table doesn't exist yet.

    [FUNNEL-DISTINCT 2026-07-31] `accepted` counts DISTINCT TICKERS, not rows.
    Every scanner re-evaluates its whole universe on a fixed interval and logs
    a row each time, so a single standing signal accumulates one accept row per
    scan. 2026-07-29 reported "penny accepted=25"; it was one ticker
    (KCPSUGIND) re-accepted by the 30-second loop for 14 minutes, whose 25
    order attempts were all rejected by the broker and which never became a
    position. Counting rows made a dead strategy look like its busiest day of
    the month. `evaluated` stays a row count -- it is a measure of scanner
    work, and its size (54 tickers x ~700 scans/day) is meaningful as such."""
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ) as cur:
        if await cur.fetchone() is None:
            return None
    # Degrade, never disappear: if the identity column is absent (schema drift,
    # a partially-migrated DB), fall back to counting accept ROWS and say so.
    # Dropping the subsystem's row entirely would make "the scanner never ran"
    # and "we could not count it" look identical in the time-series, which is
    # the exact ambiguity ops_funnel_daily exists to remove.
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        cols = {row[1] for row in await cur.fetchall()}
    if ticker_col not in cols:
        logger.warning(
            "funnel_distinct_column_missing table=%s column=%s "
            "-- falling back to accept-row count",
            table, ticker_col,
        )
        distinct_expr = "COALESCE(SUM(CASE WHEN accepted = 1 THEN 1 ELSE 0 END), 0)"
    else:
        distinct_expr = f"COUNT(DISTINCT CASE WHEN accepted = 1 THEN {ticker_col} END)"
    async with db.execute(
        f"""SELECT COUNT(*),
                   {distinct_expr},
                   COALESCE(SUM(CASE WHEN accepted = 1 THEN 1 ELSE 0 END), 0)
            FROM {table} WHERE {where_day}""",
        params,
    ) as cur:
        total, accepted, accepted_rows = await cur.fetchone()
    async with db.execute(
        f"""SELECT reject_reason, COUNT(*) AS n FROM {table}
            WHERE {where_day} AND accepted = 0
                  AND reject_reason IS NOT NULL AND reject_reason != ''
            GROUP BY reject_reason""",
        params,
    ) as cur:
        reason_rows = await cur.fetchall()
    return int(total), int(accepted), int(accepted_rows), reason_rows


def _top_rejects(reason_rows, normalise=None) -> str:
    counts: dict[str, int] = {}
    for reason, n in reason_rows:
        key = normalise(reason) if normalise else (reason or "(empty)")
        counts[key] = counts.get(key, 0) + int(n)
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:_TOP_REJECTS]
    return json.dumps(dict(top))


async def snapshot_funnels_for_day(db_path: str, date_ist: str) -> dict:
    """Upsert one ops_funnel_daily row per subsystem for `date_ist`.
    Zero-evaluation days are written too: "the scanner never ran" must
    be visible in the time-series, not a missing row. Never raises;
    returns {subsystem: evaluated} for what was written."""
    # Penny reject strings carry per-ticker numbers; reuse the accept-
    # watchdog's normaliser so the histogram groups by gate, not ticker.
    # Momentum and F&O reasons are already stable slugs.
    from penny_accept_watchdog import _normalise_reason as _penny_norm

    utc_start, utc_end = _ist_day_utc_bounds(date_ist)
    subsystems = [
        # (name, table, day-predicate, params, reason-normaliser, ticker-col)
        # [FUNNEL-DISTINCT 2026-07-31] The last field names the column that
        # identifies a distinct signal, so `accepted` counts signals rather
        # than re-emissions of the same one by the scan loop.
        ("momentum", "momentum_signals",
         "scanned_at >= ? AND scanned_at < ?", (utc_start, utc_end), None,
         "ticker"),
        ("penny", "penny_signals",
         "scanned_at >= ? AND scanned_at < ?", (utc_start, utc_end),
         _penny_norm, "ticker"),
        # fno logs bar_ts as the IST bar timestamp; its own watchdog
        # buckets days the same way. Its "ticker" is the option contract.
        ("fno", "fno_signals",
         "substr(bar_ts, 1, 10) = ?", (date_ist,), None, "tradingsymbol"),
    ]
    written: dict[str, int] = {}
    as_of = datetime.now(timezone.utc).isoformat()
    for name, table, where_day, params, normalise, ticker_col in subsystems:
        try:
            async with aiosqlite.connect(db_path) as db:
                counts = await _funnel_counts(
                    db, table, where_day, params, ticker_col=ticker_col,
                )
                if counts is None:
                    continue  # subsystem not initialised yet
                total, accepted, accepted_rows, reason_rows = counts
                await db.execute(
                    """INSERT INTO ops_funnel_daily
                           (date_ist, subsystem, evaluated, accepted,
                            rejected, top_rejects, as_of)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(date_ist, subsystem) DO UPDATE SET
                           evaluated = excluded.evaluated,
                           accepted = excluded.accepted,
                           rejected = excluded.rejected,
                           top_rejects = excluded.top_rejects,
                           as_of = excluded.as_of""",
                    (
                        # rejected is a ROW count (it pairs with `evaluated`);
                        # accepted is a DISTINCT-SIGNAL count. They deliberately
                        # do not sum to `evaluated` -- see _funnel_counts.
                        date_ist, name, total, accepted, total - accepted_rows,
                        _top_rejects(reason_rows, normalise), as_of,
                    ),
                )
                await db.commit()
            written[name] = total
        except Exception as e:
            logger.error(
                "ops_funnel_snapshot_failed subsystem=%s error=%s",
                name, str(e),
            )
    return written


async def funnel_window(db_path: str, days: int = 30) -> list[dict]:
    """ops_funnel_daily rows over the last `days` IST calendar days."""
    since = (datetime.now(IST) - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                """SELECT date_ist, subsystem, evaluated, accepted,
                          rejected, top_rejects
                   FROM ops_funnel_daily
                   WHERE date_ist > ? ORDER BY date_ist, subsystem""",
                (since,),
            ) as cur:
                rows = await cur.fetchall()
    except Exception as e:
        logger.error("ops_funnel_window_failed error=%s", str(e))
        return []
    return [
        {
            "date_ist": r[0], "subsystem": r[1], "evaluated": r[2],
            "accepted": r[3], "rejected": r[4],
            "top_rejects": json.loads(r[5]) if r[5] else {},
        }
        for r in rows
    ]
