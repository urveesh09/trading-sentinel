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

async def fno_bankroll(db_path: str, source: str = "FNO_PAPER") -> float:
    """
    [FNO 2026-07-10] Per-leg F&O pool balance (spec §10.3).

    Returns allocated pool (FNO_PAPER_BANKROLL / FNO_LIVE_BANKROLL) plus
    the sum of ledger pnl rows tagged with that leg's source. Purely
    additive next to the existing strict-separation queries: SYSTEM/
    MOMENTUM ('nifty_bankroll') and PENNY filters can never see these
    rows, so an F&O drawdown cannot trip a Nifty circuit breaker and
    cannot touch the penny pool (operator mandate 2026-06-24).

    Fails open to the allocated pool on DB errors.
    """
    allocated = (
        settings.FNO_PAPER_BANKROLL if source == "FNO_PAPER"
        else settings.FNO_LIVE_BANKROLL
    )
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT COALESCE(SUM(pnl), 0.0) FROM bankroll_ledger WHERE source = ?",
                (source,),
            ) as cur:
                row = await cur.fetchone()
                if row and row[0] is not None:
                    return allocated + float(row[0])
    except Exception as e:
        logger.warning("fno_bankroll_query_failed source=%s error=%s", source, str(e))
    return allocated


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
    except Exception as e:
        # Don't propagate -- analytics failure must not break ledger writes.
        # But DO log it: [ROADMAP-4.3 2026-07-13] a bare `pass` here meant
        # analytics could stop recording outcomes indefinitely and the only
        # symptom would be a suspiciously thin sample size weeks later, in
        # the very table the strategy tuning reads.
        logger.warning("analytics_record_outcome_failed",
                       ticker=ticker, error=str(e))

async def record_cb_reset(db_path: str) -> None:
    """[MED-006 / ROADMAP-4.6 2026-07-12] Operator circuit-breaker reset.

    The CBs are DERIVED from the ledger, so there is no state to
    "clear" -- and deleting ledger rows would destroy money history.
    Instead a CB_RESET marker row re-baselines the derived quantities:
    the drawdown PEAK and the consecutive-loss STREAK are computed only
    from rows AFTER the latest marker. Deliberately NOT re-baselined:
    CB_FLOOR (absolute capital protection vs INITIAL_BANKROLL) and
    CB_DAILY_LOSS (auto-clears at the next IST day) -- an operator
    reset must not be able to disable the floor."""
    bankroll = await nifty_bankroll(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO bankroll_ledger "
            "(timestamp, event_type, pnl, bankroll_before, bankroll_after, source, notes) "
            "VALUES (?, 'CB_RESET', 0.0, ?, ?, 'SYSTEM', 'operator reset: peak+streak re-baselined')",
            (datetime.now(timezone.utc).isoformat(), bankroll, bankroll),
        )
        await db.commit()
    logger.warning("circuit_breaker_reset_recorded", bankroll=bankroll)


async def _last_cb_reset_id(db) -> int:
    cursor = await db.execute(
        "SELECT COALESCE(MAX(id), 0) FROM bankroll_ledger WHERE event_type='CB_RESET'"
    )
    return int((await cursor.fetchone())[0])


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
    # [MED-006 2026-07-12] ... since the last operator CB_RESET marker,
    # so a reviewed-and-accepted drawdown stops re-halting forever.
    async with aiosqlite.connect(db_path) as db:
        reset_id = await _last_cb_reset_id(db)
        # >= so the marker row itself (bankroll_after = balance at reset
        # time) seeds the new peak baseline immediately.
        cursor = await db.execute(
            "SELECT MAX(bankroll_after) FROM bankroll_ledger "
            "WHERE source IN ('SYSTEM', 'MOMENTUM') AND id >= ?",
            (reset_id,),
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
    # [MED-006 2026-07-12] Streak is also bounded by the last CB_RESET.
    async with aiosqlite.connect(db_path) as db:
        reset_id = await _last_cb_reset_id(db)
        cursor = await db.execute(
            "SELECT pnl FROM bankroll_ledger "
            "WHERE event_type='TRADE_CLOSED' "
            "AND source IN ('SYSTEM', 'MOMENTUM') AND id > ? "
            "ORDER BY id DESC LIMIT 10",
            (reset_id,),
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
    except Exception as e:
        # No penny rows yet, or bankroll_ledger lacks 'source' column.
        # Read-only is OK -- this function is best-effort and must not
        # break a report. [ROADMAP-4.3 2026-07-13] But it now says so out
        # loud, and flags the result as partial: silently returning
        # total_pnl=0.0 made a broken query look exactly like a flat P&L
        # day, in the number the operator uses to judge the strategy.
        logger.warning("penny_pnl_summary_failed error=%s", str(e))
        return {"total_pnl": 0.0, "trade_count": 0, "days": days,
                "error": str(e), "partial": True}
    return {"total_pnl": total_pnl, "trade_count": trade_count, "days": days,
            "partial": False}


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


# ─────────────────────────────────────────────────────────────────────────
# [DIVISION-BREAKDOWN 2026-07-15] Per-division P&L attribution.
#
# Every strategy already tags its ledger rows with a `source`, and every
# strategy has an allocated pool constant in config. This surfaces both in one
# view so the operator can see, per division: capital allocated, realised P&L,
# balance, trades and return — and decide where to deploy more capital.
#
# Two levels:
#   - DIVISIONS: one row per source tag (swing, momentum, penny breakout, penny
#     edge paper/live, F&O paper/live). This is the P&L attribution the operator
#     asked for — "what gave what profit".
#   - POOLS: capital rollup. The ₹5,000 Nifty pool is split 50/50 (by
#     MOMENTUM_POOL_PCT) into a swing pool and a momentum pool — ₹2,500 each,
#     non-overlapping. Every division is its own pool. Live and paper are
#     totalled SEPARATELY — paper money must never be summed with real capital.
#
# Report-only: no sizing or risk math is touched (operator decision 2026-07-15).
# ─────────────────────────────────────────────────────────────────────────

def _division_registry() -> list:
    """The canonical division → (source, pool, allocation, mode) mapping.

    Reads allocation constants live from `settings` so a config change is
    reflected without editing this list. Each division is its own capital pool;
    swing and momentum are the two halves of the ₹5,000 Nifty pool.
    """
    penny_live = bool(getattr(settings, "PENNY_LIVE_TRADING", False))
    fno_live   = bool(getattr(settings, "FNO_LIVE_TRADING", False))
    # The ₹5,000 Nifty pool is split between swing and momentum by
    # MOMENTUM_POOL_PCT (0.50 default) — momentum gets its half, swing the rest.
    # They are separate, non-overlapping allocations (₹2,500 each at defaults).
    mom_pct = float(getattr(settings, "MOMENTUM_POOL_PCT", 0.5))
    momentum_alloc = round(mom_pct * settings.INITIAL_BANKROLL, 2)
    swing_alloc    = round((1.0 - mom_pct) * settings.INITIAL_BANKROLL, 2)
    return [
        # key, label, source tag, pool id, allocated (notional), mode
        ("swing",            "Swing (CNC)",              "SYSTEM",     "swing",          swing_alloc,                                             "live"),
        ("momentum",         "Intraday Momentum (MIS)",  "MOMENTUM",   "momentum",       momentum_alloc,                                          "live"),
        # [MOMENTUM-PAPER 2026-07-26] Paper twin. Live momentum entry is manual
        # (Telegram EXEC), so the live row records operator behaviour, not
        # strategy behaviour -- 8 trades in months. The paper book takes every
        # accepted signal automatically, which is what the promotion ladder needs.
        ("momentum_paper",   "Intraday Momentum (paper)","MOMENTUM_PAPER", "momentum_paper", float(getattr(settings, "MOMENTUM_PAPER_BANKROLL", 0.0)), "paper"),
        ("penny_breakout",   "Penny Breakout",           "PENNY",      "penny_breakout", float(getattr(settings, "PENNY_LIVE_BANKROLL", 0.0)) if penny_live else float(getattr(settings, "PENNY_PAPER_BANKROLL", 0.0)), "live" if penny_live else "paper"),
        ("penny_edge_paper", "Penny Edge (paper)",       "EDGE_PAPER", "edge_paper",     float(getattr(settings, "PENNY_EDGE_PAPER_BANKROLL", 0.0)), "paper"),
        ("penny_edge_live",  "Penny Edge (live)",        "EDGE_LIVE",  "edge_live",      float(getattr(settings, "PENNY_EDGE_LIVE_BANKROLL", 0.0)),  "live"),
        ("fno_paper",        "F&O Options (paper)",      "FNO_PAPER",  "fno_paper",      float(getattr(settings, "FNO_PAPER_BANKROLL", 0.0)),        "paper"),
        ("fno_live",         "F&O Options (live)",       "FNO_LIVE",   "fno_live",       float(getattr(settings, "FNO_LIVE_BANKROLL", 0.0)),         "live"),
    ]


async def division_breakdown(db_path: str) -> dict:
    """Per-division P&L attribution + per-pool capital rollup.

    Returns realised P&L / balance / trades / return per division (by ledger
    `source`), and live-vs-paper capital totals rolled up by pool (Nifty holds
    swing+momentum so its capacity is counted once). Purely informational —
    never used in risk or circuit-breaker math.
    """
    import aiosqlite
    from datetime import datetime, timezone

    # One pass over the ledger: realised P&L and closed-trade count per source.
    pnl_by_source: dict = {}
    trades_by_source: dict = {}
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT source, COALESCE(SUM(pnl), 0.0), "
                "SUM(CASE WHEN event_type != 'INITIAL' THEN 1 ELSE 0 END) "
                "FROM bankroll_ledger GROUP BY source"
            ) as cur:
                async for row in cur:
                    pnl_by_source[row[0]] = float(row[1] or 0.0)
                    trades_by_source[row[0]] = int(row[2] or 0)
    except Exception as e:
        logger.warning("division_breakdown_query_failed error=%s", str(e))

    divisions = []
    # pool_id -> {capacity, mode, pnl}: capacity taken once (the swing/Nifty seed
    # for the shared Nifty pool; the division allocation otherwise).
    pools: dict = {}
    for key, label, source, pool_id, allocated, mode in _division_registry():
        pnl = round(pnl_by_source.get(source, 0.0), 2)
        trades = trades_by_source.get(source, 0)
        return_pct = round(pnl / allocated, 4) if allocated else 0.0
        divisions.append({
            "key": key, "label": label, "source": source, "pool": pool_id,
            "mode": mode, "allocated": round(allocated, 2), "realised_pnl": pnl,
            "balance": round(allocated + pnl, 2), "trades": trades,
            "return_pct": return_pct,
        })
        # Roll P&L into the pool; set the pool capacity ONCE (first division that
        # names it), so the shared Nifty pool's ₹5,000 is not double-counted.
        p = pools.setdefault(pool_id, {"capacity": None, "mode": mode, "realised_pnl": 0.0})
        if p["capacity"] is None:
            p["capacity"] = round(allocated, 2)
        p["realised_pnl"] = round(p["realised_pnl"] + pnl, 2)

    pool_rows = []
    totals = {"live": {"capacity": 0.0, "realised_pnl": 0.0, "balance": 0.0},
              "paper": {"capacity": 0.0, "realised_pnl": 0.0, "balance": 0.0}}
    for pool_id, p in pools.items():
        cap = p["capacity"] or 0.0
        bal = round(cap + p["realised_pnl"], 2)
        pool_rows.append({"pool": pool_id, "mode": p["mode"], "capacity": cap,
                          "realised_pnl": p["realised_pnl"], "balance": bal})
        bucket = totals["live"] if p["mode"] == "live" else totals["paper"]
        bucket["capacity"] = round(bucket["capacity"] + cap, 2)
        bucket["realised_pnl"] = round(bucket["realised_pnl"] + p["realised_pnl"], 2)
        bucket["balance"] = round(bucket["balance"] + bal, 2)

    return {
        "divisions": divisions,
        "pools": pool_rows,
        "totals": totals,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def format_division_breakdown(data: dict) -> str:
    """Render division_breakdown() as a Telegram message (plain text).

    Groups divisions by live vs paper, shows allocated → balance, P&L and
    return% per division, and a per-mode capital total (Nifty counted once).
    """
    def rupee(x: float) -> str:
        sign = "-" if x < 0 else ""
        return f"{sign}₹{abs(x):,.2f}"

    divisions = data.get("divisions", [])
    totals = data.get("totals", {})
    lines = ["\U0001F4CA *Bankroll by Division*"]

    for mode, header in (("live", "LIVE (real capital)"), ("paper", "PAPER (simulated)")):
        rows = [d for d in divisions if d["mode"] == mode]
        if not rows:
            continue
        lines.append("")
        lines.append(f"*{header}*")
        for d in rows:
            pnl = d["realised_pnl"]
            pct = d["return_pct"] * 100
            tail = "not armed" if d["allocated"] == 0 and d["trades"] == 0 else \
                   f"P&L {rupee(pnl)} ({pct:+.1f}%) · {d['trades']} trades"
            lines.append(
                f"• {d['label']}: {rupee(d['allocated'])} → {rupee(d['balance'])}  {tail}"
            )
        t = totals.get(mode)
        if t:
            lines.append(
                f"  — {mode.capitalize()} total: {rupee(t['capacity'])} → "
                f"{rupee(t['balance'])}  (P&L {rupee(t['realised_pnl'])})"
            )

    lines.append("")
    lines.append("_Swing + momentum split the ₹5,000 Nifty pool 50/50 (₹2,500 each)._")
    return "\n".join(lines)
