import sqlite3

import aiosqlite
import math
from datetime import datetime, time, timedelta, timezone
import structlog
from typing import List
from models import OpenPosition
from equity_charges import charged_as_intraday
from penny_risk import calc_penny_costs
from chandelier_stop import ChandelierStop
from config import settings

logger = structlog.get_logger()


def settlement_costs(pos: dict, exit_price: float, shares: int, exit_date) -> float:
    """[S23-COST1] Round-trip charges for a tracker settlement.

    The tracker settles only the Penny/EDGE paper books, so it uses their cost
    function (the confirmed EDGE exit's) and the same rule: CNC sold in the
    session it was bought pays intraday charges, held overnight delivery."""
    intraday = charged_as_intraday(pos.get('product_type'), pos['entry_date'], exit_date, default_product="CNC")
    return calc_penny_costs(pos['entry_price'], exit_price, shares, is_intraday=intraday)


# [O26d] The order of one day's exits. Shared with research_penny_cnc_lifecycle.tracker_step,
# so the tracker and its research mirror cannot drift apart.
_IST = timezone(timedelta(hours=5, minutes=30))
MINUTE_PATH_TOLERANCE = 0.001      # minute bars must reach the day's own high and low within 0.1%
MINUTE_PATH_FIRST = time(9, 16)    # and cover the session: from its first minute
MINUTE_PATH_LAST = time(15, 14)    # to the end of continuous trading (15:15 for closing-auction stocks)


def bar_exits(status: str, stop: float, entry_price: float, target_1: float, target_2, bar: dict,
              *, open_known: bool = True) -> dict:
    """[O26d] What one bar does to a paper position, in the only order its prices allow.

    Known first, at the open: through the stop, all out at the open; at T2, all out at the open;
    at T1, the T1 half at the open and the stop to breakeven. ``open_known=False`` (the bar the
    position was bought in) takes the entry as the open: that bar's own open came before it.
    After the open a bar cannot say whether its high or its low came first, so a stop in reach is
    taken before a target, including the breakeven stop a T1 half made active earlier in the same
    bar. Rising from under T1 the price passes T1 before T2, so T2 takes the T1 half first (unless
    T2 is at or under T1).

    Returns ``{"t1": price|None, "close": (status, price)|None, "stop": stop after the bar,
    "ambiguous": bool}``. ``ambiguous`` marks a result the stop-first rule chose.
    """
    o = float(bar["open"]) if open_known else float(entry_price)
    h, l = float(bar["high"]), float(bar["low"])
    t2 = float(target_2) if target_2 is not None else None
    t1_due = status == "OPEN"
    t1, t1_inside = None, False
    if open_known:
        if o <= stop:
            return {"t1": None, "close": ("STOPPED_OUT", o), "stop": stop, "ambiguous": False}
        if t2 is not None and o >= t2:
            return {"t1": None, "close": ("CLOSED_T2", o), "stop": stop, "ambiguous": False}
        if t1_due and o >= target_1:
            t1, t1_due, stop = o, False, max(stop, entry_price)
    if t1_due:
        reach = target_1 if t2 is None else min(target_1, t2)
        if l <= stop:
            return {"t1": None, "close": ("STOPPED_OUT", stop), "stop": stop, "ambiguous": h >= reach}
        if t2 is not None and t2 <= target_1 and h >= t2:
            return {"t1": None, "close": ("CLOSED_T2", t2), "stop": stop, "ambiguous": False}
        if h < target_1:
            return {"t1": None, "close": None, "stop": stop, "ambiguous": False}
        t1, t1_inside, stop = target_1, True, max(stop, entry_price)
    t2_hit = t2 is not None and h >= t2
    if l <= stop:
        return {"t1": t1, "close": ("STOPPED_OUT", stop), "stop": stop, "ambiguous": t1_inside or t2_hit}
    if t2_hit:
        return {"t1": t1, "close": ("CLOSED_T2", t2), "stop": stop, "ambiguous": False}
    return {"t1": t1, "close": None, "stop": stop, "ambiguous": False}


def _ist_naive(value) -> datetime:
    when = datetime.fromisoformat(value) if isinstance(value, str) else value
    return when.astimezone(_IST).replace(tzinfo=None) if when.tzinfo else when


def usable_minutes(minutes, day_bar: dict, *, entered_at=None):
    """[O26d] The day's minute bars in time order, from the entry minute on the entry day, or None
    when they cannot stand for the day: empty, not to the end of continuous trading, not from the
    open (a later day), or not reaching the daily bar's own high and low."""
    if not minutes:
        return None
    path = sorted(({**m, "start": _ist_naive(m["start"])} for m in minutes), key=lambda m: m["start"])
    if entered_at is not None:
        since = _ist_naive(entered_at).replace(second=0, microsecond=0)
        path = [m for m in path if m["start"] >= since]
    if not path or path[-1]["start"].time() < MINUTE_PATH_LAST:
        return None
    high, low = max(m["high"] for m in path), min(m["low"] for m in path)
    day_high, day_low = float(day_bar["high"]), float(day_bar["low"])
    if high > day_high * (1 + MINUTE_PATH_TOLERANCE) or low < day_low * (1 - MINUTE_PATH_TOLERANCE):
        return None
    if entered_at is None and (path[0]["start"].time() > MINUTE_PATH_FIRST
                               or high < day_high * (1 - MINUTE_PATH_TOLERANCE)
                               or low > day_low * (1 + MINUTE_PATH_TOLERANCE)):
        return None
    return path


def day_exits(status: str, stop: float, entry_price: float, target_1: float, target_2, day_bar: dict,
              *, entered_at=None, minutes=None) -> dict:
    """[O26d] One day's exits for a paper position, and what they rest on (``basis``).

    ``entered_at`` is the entry instant on the entry day (None on later days): the daily bar then
    also holds prices from before the entry, so its open is not used and its touches are not
    trusted alone. A day the daily bar cannot order (``ambiguous``, or any touch on the entry day)
    is walked minute by minute when usable minute bars are given (``MINUTES``); without them the
    daily bar decides (``DAILY_STOP_FIRST`` or ``DAILY_ENTRY_DAY``). A caller fetches minutes only
    when the basis says the daily bar was not enough."""
    entry_day = entered_at is not None
    daily = bar_exits(status, stop, entry_price, target_1, target_2, day_bar, open_known=not entry_day)
    if entry_day and (daily["t1"] is not None or daily["close"] is not None):
        basis = "DAILY_ENTRY_DAY"
    elif daily["ambiguous"]:
        basis = "DAILY_STOP_FIRST"
    else:
        return {**daily, "basis": "DAILY"}
    path = usable_minutes(minutes, day_bar, entered_at=entered_at)
    if path is None:
        return {**daily, "basis": basis}
    t1 = None
    for n, bar in enumerate(path):
        step = bar_exits(status, stop, entry_price, target_1, target_2, bar, open_known=not (entry_day and n == 0))
        stop = step["stop"]
        if step["t1"] is not None:
            t1, status = step["t1"], "CLOSED_T1"
        if step["close"] is not None:
            return {"t1": t1, "close": step["close"], "stop": stop, "ambiguous": step["ambiguous"],
                    "basis": "MINUTES"}
    return {"t1": t1, "close": None, "stop": stop, "ambiguous": False, "basis": "MINUTES"}


async def _session_minutes(kite_client, ticker: str, day: str):
    """[O26d] The day's minute bars for ``day_exits``; None when the client has none or they fail
    (the daily bar then decides)."""
    fetch = getattr(kite_client, "get_intraday", None)
    if fetch is None:
        return None
    try:
        frame = await fetch(ticker, f"{day} 09:15:00", f"{day} 15:30:00", "minute")
        return [{"start": ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                 "open": float(row["open"]), "high": float(row["high"]), "low": float(row["low"]),
                 "close": float(row["close"])}
                for ts, row in frame.iterrows() if str(ts)[:10] == day]
    except Exception as exc:
        logger.warning("daily_position_minutes_unavailable ticker=%s day=%s error=%s", ticker, day, str(exc))
        return None


async def _init_pnl_outbox(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS position_pnl_outbox (
                event_key TEXT PRIMARY KEY, ticker TEXT NOT NULL,
                pnl REAL NOT NULL, source TEXT NOT NULL,
                delivered INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        await db.commit()


async def _deliver_pnl_outbox(db_path: str, record_pnl_cb) -> None:
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT event_key,ticker,pnl,source FROM position_pnl_outbox "
            "WHERE delivered=0 ORDER BY created_at,event_key"
        )).fetchall()
    for event_key, ticker, pnl, source in rows:
        try:
            await record_pnl_cb(ticker, float(pnl), source)
        except Exception as exc:
            logger.error(
                "daily_position_pnl_delivery_failed event_key=%s error=%s",
                event_key, str(exc),
            )
            continue
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE position_pnl_outbox SET delivered=1 "
                "WHERE event_key=? AND delivered=0",
                (event_key,),
            )
            await db.commit()


async def _add_column_if_missing(db, column: str, ddl: str) -> None:
    """[ROADMAP-4.3 2026-07-13] Idempotent ALTER TABLE.

    Each of these migrations used to be `except Exception: pass`, on the
    reasoning that re-adding an existing column is the only way it can
    fail. That reasoning is wrong, and 2026-07-13 proved it: when the
    disk filled, every SQLite call in the process raised
    `sqlite3.OperationalError: disk I/O error` -- including these. A bare
    `pass` would have swallowed that and let the engine continue with a
    positions table MISSING atr_1min_post_t1 and t1_fired.

    That is not a cosmetic loss. evaluate_connors_exit() reads
    atr_1min_post_t1; when it is absent it reads 0.0, which degenerates
    the CNC post-T1 trailing stop into a hard floor at breakeven+0.5%
    (see the PENNY-G5 note below) -- i.e. real money exits at the wrong
    price, silently, with no error anywhere.

    So: swallow ONLY "duplicate column name", which is the one benign
    outcome. Anything else is a broken database and must be loud.
    """
    try:
        await db.execute(f"ALTER TABLE positions ADD COLUMN {column} {ddl}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            return  # already migrated -- the expected steady state
        logger.error(
            "positions_migration_failed", column=column, error=str(e),
            hint="positions table may be missing columns the exit logic reads",
        )
        raise


async def init_positions_db(db_path: str):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT, exchange TEXT, entry_date TEXT, entry_price REAL, shares INTEGER,
                stop_loss_initial REAL, trailing_stop_current REAL, target_1 REAL, target_2 REAL,
                atr_14_at_entry REAL, highest_close_since_entry REAL, status TEXT, source TEXT,
                exit_price REAL, exit_date TEXT, realised_pnl REAL, r_multiple REAL,
                product_type TEXT DEFAULT 'CNC',
                regime_at_entry TEXT,
                initial_capital_at_risk REAL,
                broker_entry_order_id TEXT
            )
        """)
        # [MED-008] Migration: add product_type column to pre-existing tables on
        # the persistent volume.
        await _add_column_if_missing(db, "product_type", "TEXT DEFAULT 'CNC'")
        # [TRAILING-EXITS 2026-06-16] regime_at_entry for the regime-aware
        # Chandelier trailing stop. NULL = legacy 3.0x ATR behavior (backward
        # compat for pre-existing positions).
        await _add_column_if_missing(db, "regime_at_entry", "TEXT")
        # [PENNY-G5 2026-06-25] atr_1min_post_t1 and t1_fired for the CNC
        # Connors post-T1 trailing stop (evaluate_connors_exit). Pre-fix these
        # were never written; evaluate_connors_exit read 0.0 for
        # atr_1min_post_t1 which made the trail-stop degenerate to a hard floor
        # at breakeven+0.5%. Now CNC positions carry the data.
        await _add_column_if_missing(db, "atr_1min_post_t1", "REAL")
        await _add_column_if_missing(db, "t1_fired", "INTEGER DEFAULT 0")
        # [TIER0-0.1 2026-07-14] Broker-side SL-M protecting an MIS position.
        # Zerodha GTT is CNC-only, so MIS positions had no broker-side stop at
        # all; the intraday monitor must cancel this order before it takes a
        # target or trail exit, or the SL-M would still be resting and sell a
        # second time.
        await _add_column_if_missing(db, "sl_order_id", "TEXT")
        # Stable classic-Penny execution identity. NULL preserves every legacy
        # and non-Penny row; non-NULL attempts can create at most one position.
        await _add_column_if_missing(db, "penny_attempt_id", "TEXT")
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_penny_attempt
            ON positions(penny_attempt_id) WHERE penny_attempt_id IS NOT NULL
        """)
        # [THESIS-EXIT 2026-08-04] VWAP at entry -- the level the momentum
        # thesis was built on. The exit ladder uses it to ask "is this setup
        # still true?" instead of "has enough time passed?". NULL on positions
        # opened before this column existed, and the exit logic falls back to
        # the old clock-and-R test in that case.
        await _add_column_if_missing(db, "vwap_at_entry", "REAL")
        # Full-position risk at the actual fill.  ``shares`` is mutable after a
        # momentum scale-out, so it cannot remain the denominator for the
        # trade's final aggregate R multiple.
        await _add_column_if_missing(db, "initial_capital_at_risk", "REAL")
        await _add_column_if_missing(db, "broker_entry_order_id", "TEXT")
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_broker_entry_order
            ON positions(broker_entry_order_id)
            WHERE broker_entry_order_id IS NOT NULL
        """)
        # Paper-only immutable lifecycle identity.  It intentionally remains
        # NULL for every historical/live/non-momentum row; new momentum-paper
        # opens retain the admission key that actually admitted the position so
        # later research can join evidence without ticker/date guesswork.
        await _add_column_if_missing(db, "paper_admission_key", "TEXT")
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_paper_admission_key
            ON positions(paper_admission_key)
            WHERE paper_admission_key IS NOT NULL
        """)
        await db.commit()

async def get_open_positions(db_path: str) -> List[dict]:
    """Positions the engine should still be managing.

    CLOSED_T1 is included because the swing/penny runner keeps managing the
    remaining 50% after a partial T1 exit -- that row is genuinely still open.

    [PHANTOM-OPEN-INVARIANT 2026-07-26] But `status` alone is not a safe
    open/closed test, because two paths write CLOSED_T1 on a position that is
    entirely gone:

      1. A momentum exit mislabelled CLOSED_T1. Fixed at the writer by
         64ce0e5 (momentum_exit_status), but the two rows already in prod
         (THELEELA, LATENTVIEW, both fully exited 2026-07-20) stayed
         "open" forever, and a code fix could not reach them.
      2. update_daily_positions' full-close-at-T1 branch (the 1-share edge
         case, ~line 240): remaining_shares == 0 so nothing is left to ride,
         yet it still persists status='CLOSED_T1'. Latent, same shape.

    Cost of that in prod, 2026-07-21..24: the 15:15 auto-square re-squared
    both phantoms every day -- placing REAL Zerodha sell orders for stock the
    account did not hold -- booked a fresh fabricated loss each time
    (-Rs 178.31 of pure fiction), tripped CB_CONSECUTIVE_LOSSES off those
    fake losses, and pinned 94% of the momentum capital pool so 25 (07-23)
    and 16 (07-24) candidates that passed every strategy gate were rejected
    for lack of cash.

    exit_date is the durable invariant: the partial-T1 runner branch updates
    only status + shares and leaves exit_date NULL, while every full-close
    path sets it. So "still open" == not-yet-exited, whatever the label says.
    Verified against prod cache.db: this excludes exactly the two phantoms
    and no legitimately-open row.
    """
    await init_positions_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM positions "
            "WHERE status IN ('OPEN', 'CLOSED_T1') AND exit_date IS NULL"
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def update_daily_positions(db_path: str, kite_client, current_date_str: str, record_pnl_cb):
    """
    [TIER0-0.2 2026-07-14] record_pnl_cb is now called as
    `record_pnl_cb(ticker, pnl, source)`.

    It used to be `record_pnl_cb(ticker, pnl)`, and main.py bound it to
    `record_trade_close(db, t, p)` -- which defaults `source="SYSTEM"`. But this
    function iterates EVERY open position, including EDGE_PAPER ones sized off a
    ₹100,000 imaginary bankroll. So the paper leg's P&L was booked straight into
    the real ₹5,000 SYSTEM pool:

        EDGE_PAPER net  = +3,826.27      <- paper money
        EDGE_LIVE  net  =    +39.16
        MOMENTUM   net  =    -23.33
                          ----------
        ledger says       ₹8,842.11      real book is ₹5,015.83

    76% of the reported account was fiction. Passing the position's own source
    keeps each pool separate, which is what bankroll_for_source() already assumes.
    """
    await _init_pnl_outbox(db_path)
    await _deliver_pnl_outbox(db_path, record_pnl_cb)
    open_pos = await get_open_positions(db_path)
    for pos in open_pos:
        ticker = pos['ticker']
        # This function is an OHLC simulator, not an execution reconciler.  It
        # must never manufacture an exit for a source backed by real broker
        # positions. Only explicitly paper-labelled sources are eligible.
        source = pos.get('source') or 'SYSTEM'
        if source not in {'PENNY_PAPER', 'EDGE_PAPER'}:
            logger.info(
                "daily_position_ohlc_skip_live ticker=%s source=%s",
                ticker, source,
            )
            continue
        df = await kite_client.get_historical(ticker, current_date_str, current_date_str)
        if df.empty: continue
        # [TEST-COMPAT 2026-07-01] Some test mocks return only 'close'.
        # Use .get() to fall back to today_close when open/high/low
        # are missing. In production Kite always returns all four
        # columns; this fallback only triggers in test fixtures.
        try:
            today_open = float(df['open'].iloc[-1] if 'open' in df.columns else df['close'].iloc[-1])
            today_high = float(df['high'].iloc[-1] if 'high' in df.columns else df['close'].iloc[-1])
            today_low = float(df['low'].iloc[-1] if 'low' in df.columns else df['close'].iloc[-1])
            today_close = float(df['close'].iloc[-1])
            if not all(math.isfinite(v) for v in (today_open, today_high, today_low, today_close)):
                raise ValueError("non-finite OHLC")
        except (TypeError, ValueError, OverflowError) as exc:
            logger.error(
                "daily_position_invalid_ohlc ticker=%s source=%s error=%s",
                ticker, source, str(exc),
            )
            continue
        highest_close = float(max(float(pos['highest_close_since_entry']), today_close))
        # [TRAILING-EXITS 2026-06-16] Regime-aware Chandelier multiplier.
        # Wider trail in calm markets (Regime 1 = 3.5x ATR) gives mid-cap
        # trends room to breathe. Tighter in crisis (Regime 3 = 2.5x ATR)
        # cuts losses fast. Backward compat: NULL regime -> legacy 3.0x.
        regime_at_entry = pos.get('regime_at_entry')
        if regime_at_entry == 'REGIME_1_NORMAL':
            chandelier_mult = settings.CHANDELIER_ATR_REGIME1_MULT
        elif regime_at_entry == 'REGIME_2_ELEVATED':
            chandelier_mult = settings.CHANDELIER_ATR_REGIME2_MULT
        elif regime_at_entry == 'REGIME_3_CRISIS':
            chandelier_mult = settings.CHANDELIER_ATR_REGIME3_MULT
        else:
            # Legacy / NULL regime -- use original single setting
            chandelier_mult = settings.CHANDELIER_ATR_MULT
        # [TIER0-0.3 2026-07-14] A missing ATR must DISABLE the trail, not
        # degenerate it. ChandelierStop returns `highest_close - mult*atr`, so
        # atr=0 collapses it to `highest_close`, which is >= entry_price -- and
        # position_tracker then force-closes the position at its own entry price
        # the first time the day's low ticks a paise below entry. That is exactly
        # what happened to the live EDGE book: RPOWER/IRISDOREME/MIRZAINT/
        # PCJEWELLER all exited at entry, their real -4/-5% stops never consulted,
        # every "loss" pure brokerage. Same shape as the atr_1min_post_t1 bug above.
        # No ATR -> hold the stop we entered with.
        atr_at_entry = pos.get('atr_14_at_entry')
        if atr_at_entry and atr_at_entry > 0:
            # Chandelier stop: highest_close_since_entry - (atr_mult * ATR)
            cs = ChandelierStop(
                entry_price=pos['entry_price'],
                atr=atr_at_entry,
                atr_mult=chandelier_mult,
            )
            # Seed highest_close with yesterday's value so stop trails from there, not entry
            cs._highest_close = highest_close
            cs.update(close=today_close, high=today_close, low=today_close)
            # Chandelier stop can only move up (one-way ratchet), never down
            trailing_stop = max(pos['trailing_stop_current'], cs.get_stop())
        else:
            trailing_stop = pos['trailing_stop_current']
            logger.warning(
                "trail_disabled_no_atr ticker=%s source=%s stop=%s -- position "
                "keeps its entry stop; trail cannot be computed without an ATR",
                pos.get('ticker'), pos.get('source'), trailing_stop,
            )

        # [TRAILING-EXITS 2026-06-16] Apply HARD_CAP_R_REGIME1 ceiling.
        # The hard cap is min(target_2, entry + HARD_CAP_R * risk_per_share).
        # This is a safety valve: even if target_2 is configured higher, the
        # position is force-closed at the 5R ceiling in Regime 1.
        effective_target_2 = pos['target_2']
        if regime_at_entry == 'REGIME_1_NORMAL':
            risk_per_share = pos['entry_price'] - pos['stop_loss_initial']
            if risk_per_share > 0:
                hard_cap_price = pos['entry_price'] + (settings.HARD_CAP_R_REGIME1 * risk_per_share)
                # The effective T2 is the lesser of (configured target_2, hard cap)
                if effective_target_2 is None or effective_target_2 > hard_cap_price:
                    effective_target_2 = hard_cap_price

        current_status = pos['status']
        entry_date = datetime.fromisoformat(pos['entry_date']).date()
        today = datetime.strptime(current_date_str, "%Y-%m-%d").date()
        days_held = (today - entry_date).days
        # [BUG-FIX 2026-07-01] Use intraday high/low, not just today_close: a
        # bar can touch a target or wick through the stop and close inside.
        # [O26c 2026-10-26] A bar touching both took the target (Oct 26 audit
        # O26-P1); the stop is taken first.
        # [O26d 2026-10-26] day_exits orders the day (independent review R1):
        # what the open settles first; T1 before T2 on the way up; a stop in
        # reach before a target after the open, including the breakeven stop a
        # T1 half made active that bar. On the entry day the bar's open and part
        # of its range came before the entry, so the open is not used. A day the
        # daily bar cannot order is walked through its minute bars when they
        # cover it; otherwise the stop-first result stands.
        entered_at = pos['entry_date'] if _ist_naive(pos['entry_date']).date() == today else None
        bar = {"open": today_open, "high": today_high, "low": today_low}
        args = (current_status, trailing_stop, pos['entry_price'], pos['target_1'], effective_target_2, bar)
        exits = day_exits(*args, entered_at=entered_at)
        if exits["basis"] != "DAILY":
            minutes = await _session_minutes(kite_client, ticker, current_date_str)
            if minutes:
                exits = day_exits(*args, entered_at=entered_at, minutes=minutes)
            logger.info("daily_bar_exit_order ticker=%s source=%s basis=%s t1=%s close=%s", ticker, source,
                        exits["basis"], exits["t1"], exits["close"])
        trailing_stop = exits["stop"]
        t1_price, close = exits["t1"], exits["close"]
        if t1_price is None and close is None and days_held >= 15:
            close = ("CLOSED_TIME", today_close)
        shares = pos['shares']
        prior_realised = float(pos.get('realised_pnl') or 0)
        if t1_price is not None:
            closed_shares = math.floor(shares * 0.5)
            if closed_shares == 0:
                closed_shares = 1 # If only 1 share, sell it all
            remaining_shares = shares - closed_shares
            gross = (t1_price - pos['entry_price']) * closed_shares
            costs = settlement_costs(pos, t1_price, closed_shares, current_date_str)
            realised_pnl = gross - costs
            if remaining_shares == 0:
                # Full close (if you only had 1 share)
                close = None
                risk_initial = (pos['entry_price'] - pos['stop_loss_initial']) * shares
                r_multiple = realised_pnl / risk_initial if risk_initial > 0 else 0
                async with aiosqlite.connect(db_path) as db:
                    cur = await db.execute("""
                        UPDATE positions SET highest_close_since_entry=?, trailing_stop_current=?,
                        status=?, exit_price=?, exit_date=?, realised_pnl=?, r_multiple=?
                        WHERE ticker=? AND entry_date=? AND source=? AND shares=?
                          AND exit_date IS NULL
                    """, (highest_close, trailing_stop, "CLOSED_T1", t1_price, current_date_str,
                        realised_pnl, r_multiple, ticker, pos['entry_date'], source,
                        shares))
                    if cur.rowcount == 1:
                        await db.execute(
                            "INSERT OR IGNORE INTO position_pnl_outbox "
                            "(event_key,ticker,pnl,source,created_at) VALUES (?,?,?,?,?)",
                            (f"{source}|{ticker}|{pos['entry_date']}|{shares}|T1FULL",
                             ticker, realised_pnl, source, datetime.utcnow().isoformat()),
                        )
                    await db.commit()
            else:
                # Partial close (Let the remaining 50% ride; the stop is at breakeven)
                async with aiosqlite.connect(db_path) as db:
                    cur = await db.execute("""
                        UPDATE positions SET highest_close_since_entry=?, trailing_stop_current=?,
                        status=?, shares=?, realised_pnl=COALESCE(realised_pnl, 0)+?
                        WHERE ticker=? AND entry_date=? AND source=? AND shares=?
                          AND exit_date IS NULL
                    """, (highest_close, trailing_stop, "CLOSED_T1", remaining_shares,
                          realised_pnl, ticker, pos['entry_date'], source, shares))
                    if cur.rowcount == 1:
                        await db.execute(
                            "INSERT OR IGNORE INTO position_pnl_outbox "
                            "(event_key,ticker,pnl,source,created_at) VALUES (?,?,?,?,?)",
                            (f"{source}|{ticker}|{pos['entry_date']}|{shares}|T1PART",
                             ticker, realised_pnl, source, datetime.utcnow().isoformat()),
                        )
                    await db.commit()
                # [O26d] The rest closes in this same pass when the day also took
                # it, with the keys and figures the next day's pass would use.
                shares, prior_realised = remaining_shares, prior_realised + realised_pnl
            if cur.rowcount != 1:
                logger.warning(
                    "daily_position_settlement_stale ticker=%s source=%s expected_shares=%s",
                    ticker, source, pos['shares'],
                )
                continue
        if close is not None:
            # Normal Full Close (Stop Loss, Target 2, or Time Expiry)
            status, exit_price = close
            gross = (exit_price - pos['entry_price']) * shares
            costs = settlement_costs(pos, exit_price, shares, current_date_str)
            realised_pnl = gross - costs
            total_realised_pnl = prior_realised + realised_pnl
            risk_initial = float(pos.get('initial_capital_at_risk') or 0)
            if risk_initial <= 0:
                risk_initial = (pos['entry_price'] - pos['stop_loss_initial']) * shares
            r_multiple = total_realised_pnl / risk_initial if risk_initial > 0 else 0
            async with aiosqlite.connect(db_path) as db:
                cur = await db.execute("""
                    UPDATE positions SET highest_close_since_entry=?, trailing_stop_current=?,
                    status=?, exit_price=?, exit_date=?, realised_pnl=?, r_multiple=?
                    WHERE ticker=? AND entry_date=? AND source=? AND shares=?
                      AND exit_date IS NULL
                """, (highest_close, trailing_stop, status, exit_price, current_date_str,
                    total_realised_pnl, r_multiple, ticker, pos['entry_date'], source,
                    shares))
                if cur.rowcount == 1:
                    await db.execute(
                        "INSERT OR IGNORE INTO position_pnl_outbox "
                        "(event_key,ticker,pnl,source,created_at) VALUES (?,?,?,?,?)",
                        (f"{source}|{ticker}|{pos['entry_date']}|{shares}|{status}",
                         ticker, realised_pnl, source, datetime.utcnow().isoformat()),
                    )
                await db.commit()
            if cur.rowcount != 1:
                logger.warning(
                    "daily_position_settlement_stale ticker=%s source=%s expected_shares=%s",
                    ticker, source, shares,
                )
        elif t1_price is None:
            # Just update the trailing stop and highest close for the day
            async with aiosqlite.connect(db_path) as db:
                await db.execute("""
                    UPDATE positions SET highest_close_since_entry=?, trailing_stop_current=?
                    WHERE ticker=? AND entry_date=? AND source=? AND shares=?
                      AND exit_date IS NULL
                """, (highest_close, trailing_stop, ticker, pos['entry_date'], source,
                      pos['shares']))
                await db.commit()
    await _deliver_pnl_outbox(db_path, record_pnl_cb)
