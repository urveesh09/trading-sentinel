import aiosqlite
from datetime import datetime, timezone
import pytz
import structlog
from config import settings

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

async def init_ledger(db_path: str):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bankroll_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, event_type TEXT,
                ticker TEXT, pnl REAL, bankroll_before REAL, bankroll_after REAL,
                source TEXT NOT NULL DEFAULT 'SYSTEM', notes TEXT
            )
        """)
        # Migration: existing DBs (pre-2026-06-24) were created without the
        # `source` column. Add it idempotently -- SQLite raises OperationalError
        # "duplicate column name" if it already exists, so we swallow that.
        try:
            await db.execute(
                "ALTER TABLE bankroll_ledger "
                "ADD COLUMN source TEXT NOT NULL DEFAULT 'SYSTEM'"
            )
        except Exception:
            pass  # column already exists -- safe to ignore
        await db.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                timestamp TEXT, strategy_version TEXT,
                gate TEXT, metrics_json TEXT
            )
        """)
        # [BK1]
        cursor = await db.execute("SELECT COUNT(*) FROM bankroll_ledger")
        count = (await cursor.fetchone())[0]
        if count == 0:
            await db.execute(
                "INSERT INTO bankroll_ledger "
                "(timestamp, event_type, pnl, bankroll_before, bankroll_after, source) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), "INITIAL", 0.0,
                 settings.INITIAL_BANKROLL, settings.INITIAL_BANKROLL, "SYSTEM")
            )
        await db.commit()

async def current_bankroll(db_path: str) -> float:
    """
    [AUDIT-FIX-1.1 2026-06-25] DEPRECATED for risk math.

    Returns whatever `bankroll_after` was written to the LAST row of the
    ledger. This was convenient for a single-pool system but is now
    **incorrect when ledger rows of different sources interleave**:
    after a penny close, the "last row" reflects `nifty_bankroll +
    penny_pnl`, not `nifty_bankroll`. After a swing close, it reflects
    `nifty + swing_pnl`. Different sequences give different answers
    for the same actual bankroll state.

    **DO NOT use in risk decisions.** Use `bankroll_for_source(db,
    source)` instead. This function is kept only for back-compat in
    non-risk call sites (legacy audit displays).

    Migration: search-replace `current_bankroll()` with
    `bankroll_for_source(db_path, source)` where the caller knows the
    source. For endpoints that need the OVERALL bankroll, use the
    proper sum: `INITIAL_BANKROLL + SUM(pnl)` (filter not applied).
    """
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT bankroll_after FROM bankroll_ledger ORDER BY id DESC LIMIT 1")
        row = await cursor.fetchone()
        return row[0] if row else settings.INITIAL_BANKROLL


async def bankroll_for_source(db_path: str, source: str) -> float:
    """
    [AUDIT-FIX-1.1 2026-06-25] Per-source running bankroll.

    Returns: INITIAL_BANKROLL + sum(pnl WHERE source == {source}).

    Use this everywhere you used to call `current_bankroll()` with a
    known source. Unlike `current_bankroll()`, this is robust to row
    ordering and never mixes sources.

    Examples:
        nifty_bal = await bankroll_for_source(db, "SYSTEM")   # swing
        mom_bal   = await bankroll_for_source(db, "MOMENTUM")  # momentum
        penny_bal = await bankroll_for_source(db, "PENNY")     # penny
        overall   = INITIAL_BANKROLL + sum over all sources
                    (computed by caller; not exposed here because
                    callers should think in terms of per-pool)

    Penny users: penny pool is allocated separately (PENNY_LIVE_BANKROLL
    or PENNY_PAPER_BANKROLL), not from the INITIAL_BANKROLL pool. For
    penny, prefer `penny_bankroll()` (returns allocated + realised
    pnl for penny only).

    Fails open: any DB error returns INITIAL_BANKROLL.
    """
    import aiosqlite
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT COALESCE(SUM(pnl), 0.0) FROM bankroll_ledger WHERE source = ?",
                (source,),
            ) as cur:
                row = await cur.fetchone()
                if row and row[0] is not None:
                    return settings.INITIAL_BANKROLL + float(row[0])
    except Exception as e:
        logger.warning("bankroll_for_source_query_failed source=%s error=%s", source, str(e))
    return settings.INITIAL_BANKROLL


async def nifty_bankroll(db_path: str) -> float:
    """
    [NIFTY-BANKROLL 2026-06-24] Strict-separation Nifty-subsystem balance.

    Returns the Nifty-subsystem bankroll = swing balance + momentum balance,
    computed as INITIAL_BANKROLL plus the sum of every ledger row whose
    source is 'SYSTEM' or 'MOMENTUM'. PENNY rows are EXCLUDED.

    Why this exists: the legacy current_bankroll() reads the LAST row of
    the ledger, which can be a PENNY row after the first penny close. That
    meant a swing RiskEngine constructed with the result was sizing off a
    penny-contaminated number. Strict separation per Uru 2026-06-24
    ("keep them separate, separate module systems from the start").

    Used by:
      - swing RiskEngine construction in main.py (swing screener)
      - swing RiskEngine.update_bankroll() sync after swing trade close
      - momentum screener (swing sub-pool sizing)
      - /signals, /momentum-signals, /performance endpoints (swing display)
      - /bankroll endpoint (Nifty-subsystem balance)
      - check_circuit_breakers() -- swing CBs now measured against the
        Nifty-subsystem balance, NOT the last ledger row. This is a
        stricter, more honest swing risk gate: a penny loss cannot
        artificially trip or inflate the swing CB trigger.

    Penny has its own balance path: pool_breakdown().penny.balance.

    Returns: float, never None. Falls back to INITIAL_BANKROLL if no
    SYSTEM/MOMENTUM rows exist.
    """
    import aiosqlite
    total = 0.0
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT COALESCE(SUM(pnl), 0.0) FROM bankroll_ledger "
                "WHERE source IN ('SYSTEM', 'MOMENTUM')"
            ) as cur:
                row = await cur.fetchone()
                if row and row[0] is not None:
                    total = float(row[0])
    except Exception as e:
        logger.warning("nifty_bankroll_query_failed error=%s", str(e))
    return settings.INITIAL_BANKROLL + total

async def record_trade_close(db_path: str, ticker: str, pnl: float,
                             r_multiple: float | None = None,
                             notes: str | None = None,
                             source: str = "SYSTEM"):
    # [BK2]
    # `source` distinguishes which subsystem wrote the row. Allowed values:
    #   "SYSTEM"  -- default for swing / manual closes (back-compat)
    #   "MOMENTUM" -- Nifty options subsystem
    #   "PENNY"  -- penny subsystem
    # Used by performance.penny_pool_pnl() and analytics.outcome_correlator()
    # to compute per-pool P&L without double-counting across pools.
    before = await bankroll_for_source(db_path, source)
    after = before + pnl
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO bankroll_ledger "
            "(timestamp, event_type, ticker, pnl, bankroll_before, bankroll_after, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), "TRADE_CLOSED", ticker,
             pnl, before, after, source)
        )
        await db.commit()
    # [ANALYTICS 2026-06-16] Side-effect: record the trade outcome + join with
    # the signal-log row that birthed it. Best-effort; never raises.
    try:
        from analytics import record_trade_outcome
        await record_trade_outcome(db_path, ticker, pnl, r_multiple=r_multiple, notes=notes)
    except Exception:
        # Don't propagate -- analytics failure must not break ledger writes.
        pass

async def check_circuit_breakers(db_path: str) -> tuple[bool, list[str]]:
    halted = False
    reasons = []

    # 2026-06-24 strict separation: swing CBs are measured against the
    # Nifty-subsystem balance (swing + momentum), not the last ledger row.
    # A penny P&L close no longer affects swing CB thresholds -- the penny
    # subsystem has its own kill-switch in PennyRiskEngine.
    bankroll = await nifty_bankroll(db_path)

    # [CB3] & [BK5]
    # Peak is the highest Nifty-subsystem bankroll_after seen. Filter out
    # PENNY rows so a large penny allocation or penny win doesn't bump peak.
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT MAX(bankroll_after) FROM bankroll_ledger "
            "WHERE source IN ('SYSTEM', 'MOMENTUM')"
        )
        peak = (await cursor.fetchone())[0]
        
    if bankroll < settings.INITIAL_BANKROLL * settings.CB_FLOOR_PCT:
        halted = True
        reasons.append("CB_FLOOR_BREACHED")
        logger.error("bankroll_floor_breached", current=bankroll)
        
    if peak > 0 and ((peak - bankroll) / peak) >= settings.CB_MAX_DRAWDOWN_PCT:
        halted = True
        reasons.append("CB_MAX_DRAWDOWN")

    # [CB1] Daily loss - uses IST date since trading day is defined in IST.
    # Timestamps are stored as UTC ISO-8601 with timezone suffix (e.g. "2026-05-11T04:30:00+00:00").
    # SQLite's date() does NOT parse timezone suffixes and returns NULL for such strings,
    # so we shift the UTC timestamp by +5.5h inside SQL before extracting the date.
    # 2026-06-24 strict separation: source IN ('SYSTEM', 'MOMENTUM') -- penny
    # losses do not contribute to the swing daily-loss CB threshold. The penny
    # subsystem has its own kill-switch in PennyRiskEngine.
    today = datetime.now(IST).date().isoformat()
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """SELECT SUM(pnl) FROM bankroll_ledger
               WHERE event_type='TRADE_CLOSED'
               AND source IN ('SYSTEM', 'MOMENTUM')
               AND date(datetime(
                   REPLACE(REPLACE(timestamp, '+00:00', ''), 'Z', ''),
                   '+5 hours', '+30 minutes'
               )) = ?""",
            (today,)
        )
        daily_pnl = (await cursor.fetchone())[0] or 0.0
        if daily_pnl <= -(bankroll * settings.CB_DAILY_LOSS_PCT):
            halted = True
            reasons.append("CB_DAILY_LOSS")

    # [CB2] Consecutive losses
    # 2026-06-24 strict separation: streak counts Nifty-subsystem trades only.
    # Penny losses do not contribute to the swing consecutive-losses counter.
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT pnl FROM bankroll_ledger "
            "WHERE event_type='TRADE_CLOSED' "
            "AND source IN ('SYSTEM', 'MOMENTUM') "
            "ORDER BY id DESC LIMIT 10"
        )
        rows = await cursor.fetchall()
        streak = 0
        for r in rows:
            if r[0] < 0: streak += 1
            else: break
        if streak >= settings.CB_MAX_CONSECUTIVE_LOSSES:
            halted = True
            reasons.append("CB_CONSECUTIVE_LOSSES")
    """
    # [CB4] Backtest Gate
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT gate FROM backtest_results ORDER BY rowid DESC LIMIT 1")
        gate_row = await cursor.fetchone()
        if not gate_row or gate_row[0] == "FAIL":
            halted = True
            reasons.append("BACKTEST_GATE_FAILED")
    """
    return halted, reasons

async def penny_pool_pnl(db_path: str, days: int = 14) -> dict:
    """
    [PENNY-PERF 2026-06-21] Sum realized P&L for source='PENNY' rows
    in the bankroll_ledger for the last `days` days. Independent of
    the Nifty pool -- pool split per spec §3.4.

    Reads from bankroll_ledger.source = 'PENNY'. This column was added
    on 2026-06-24 (the bankroll fix): the source field was already
    designed into performance.py + analytics.py + main.py:1686, but
    not wired into the schema. Now that PennyRiskEngine.record_close
    writes through a ledger_writer callable, this function returns
    real data instead of always-zero.
    """
    import aiosqlite
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    total_pnl = 0.0
    trade_count = 0
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT pnl FROM bankroll_ledger "
                "WHERE source='PENNY' AND timestamp >= ?",
                (cutoff,),
            ) as cur:
                async for row in cur:
                    total_pnl += row[0] or 0.0
                    trade_count += 1
    except Exception:
        # No penny rows yet, or bankroll_ledger lacks 'source' column.
        # Read-only is OK -- this function is best-effort.
        pass
    return {"total_pnl": total_pnl, "trade_count": trade_count, "days": days}


async def pool_breakdown(db_path: str) -> dict:
    """
    [POOL-BREAKDOWN 2026-06-24] Per-pool bankroll display.

    Returns the swing balance and penny balance as INDEPENDENT numbers.
    No risk math is changed -- current_bankroll() and check_circuit_breakers()
    are untouched. This is a display-only helper used by /bankroll/breakdown.

    Math:
      swing_balance = (swing-only ledger balance)
                    = current_bankroll() MINUS any penny P&L that has
                      accumulated. Because the ledger is append-only and
                      ordered by id, and penny closes arrive after the
                      INITIAL seed, the most-recent-row may not be pure
                      swing. We compute swing as:
                        SELECT SUM(pnl) FROM bankroll_ledger WHERE source='SYSTEM'
                      + INITIAL_BANKROLL.
                      This is robust regardless of which row is "last".

      penny_balance = PENNY_LIVE_BANKROLL (or PENNY_PAPER_BANKROLL in paper)
                      + SUM(pnl WHERE source='PENNY').
                      The constant is the *allocated* pool capacity, not a
                      ledger seed -- it represents the testing budget the
                      operator opted into. No ledger row is inserted for it.

      combined = swing_balance + penny_balance
                 (informational only; never used in CB math)

    Returns:
      {
        "swing":   {"balance": float, "trades": int},
        "penny":   {"balance": float, "allocated": float, "pnl": float,
                    "trades": int, "mode": "live"|"paper"},
        "combined": float,    # informational only
        "as_of":   "<UTC ISO8601>",
      }
    """
    import aiosqlite
    from datetime import datetime, timezone

    # Swing balance: SUM of all SYSTEM-source P&L rows + the INITIAL seed.
    swing_pnl = 0.0
    swing_trades = 0
    # Penny P&L: SUM of all PENNY-source rows. Allocated = the constant.
    penny_pnl = 0.0
    penny_trades = 0

    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT pnl FROM bankroll_ledger WHERE source='SYSTEM'"
            ) as cur:
                async for row in cur:
                    swing_pnl += row[0] or 0.0
                    if (row[0] or 0.0) != 0.0:
                        swing_trades += 1
            async with db.execute(
                "SELECT pnl FROM bankroll_ledger WHERE source='PENNY'"
            ) as cur:
                async for row in cur:
                    penny_pnl += row[0] or 0.0
                    if (row[0] or 0.0) != 0.0:
                        penny_trades += 1
    except Exception as e:
        # No rows yet, or schema missing source column (pre-migration DB).
        # Best-effort: return zeros. Callers should treat empty as "no data".
        logger.warning("pool_breakdown_query_failed error=%s", str(e))

    swing_balance = settings.INITIAL_BANKROLL + swing_pnl

    # Penny mode + allocation: live unless PENNY_LIVE_TRADING is False.
    penny_live = bool(getattr(settings, "PENNY_LIVE_TRADING", False))
    penny_allocated = (
        float(getattr(settings, "PENNY_LIVE_BANKROLL", 0.0))
        if penny_live
        else float(getattr(settings, "PENNY_PAPER_BANKROLL", 0.0))
    )
    penny_balance = penny_allocated + penny_pnl

    return {
        "swing": {
            "balance": round(swing_balance, 2),
            "trades":  swing_trades,
        },
        "penny": {
            "balance":   round(penny_balance, 2),
            "allocated": round(penny_allocated, 2),
            "pnl":       round(penny_pnl, 2),
            "trades":    penny_trades,
            "mode":      "live" if penny_live else "paper",
        },
        "combined": round(swing_balance + penny_balance, 2),
        "as_of":    datetime.now(timezone.utc).isoformat(),
    }
