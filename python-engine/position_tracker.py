import sqlite3

import aiosqlite
from datetime import datetime
import structlog
from typing import List
from models import OpenPosition
from engine import calc_zerodha_costs
from chandelier_stop import ChandelierStop
from config import settings

logger = structlog.get_logger()


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
                regime_at_entry TEXT
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
    open_pos = await get_open_positions(db_path)
    for pos in open_pos:
        ticker = pos['ticker']
        # [PENNY-TRACKER 2026-06-21] Existing logic accepts source != "MOMENTUM"
        # (i.e. SYSTEM-swing, PENNY-CNC, PENNY-MIS). No code change needed.
        if pos.get('source') == 'MOMENTUM':
            continue
        df = await kite_client.get_historical(ticker, current_date_str, current_date_str)
        if df.empty: continue
        # [TEST-COMPAT 2026-07-01] Some test mocks return only 'close'.
        # Use .get() to fall back to today_close when open/high/low
        # are missing. In production Kite always returns all four
        # columns; this fallback only triggers in test fixtures.
        today_open   = df['open'].iloc[-1]  if 'open'  in df.columns else df['close'].iloc[-1]
        today_high   = df['high'].iloc[-1]  if 'high'  in df.columns else df['close'].iloc[-1]
        today_low    = df['low'].iloc[-1]   if 'low'   in df.columns else df['close'].iloc[-1]
        today_close  = df['close'].iloc[-1]
        highest_close = max(pos['highest_close_since_entry'], today_close)
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
        status = current_status
        exit_price = None
        hit_t1_today = False
        entry_date = datetime.fromisoformat(pos['entry_date']).date()
        today = datetime.strptime(current_date_str, "%Y-%m-%d").date()
        days_held = (today - entry_date).days
        # [BUG-FIX 2026-07-01] Use intraday high/low, not just today_close.
        # The previous code only checked today_close, which misses:
        #   - TP hits where the bar touched target and closed below
        #   - SL hits where the bar wicked through stop and closed above
        # Today's penny stocks need both. Without this fix the strategy
        # leaves Rs 3,092 of paper P&L and Rs 12 of live P&L on the table
        # per typical day (verified on 2026-07-01 backout).
        # On ambiguity (both SL and TP touched same day), we assume
        # stop-hit-first since most execution priority is SL-first at most
        # brokers. A more conservative choice is target-first for momentum
        # trades; but losses are bounded by the stop_hit branch's use of
        # the trailing stop, not today's low, so slippage is small.
        stop_hit   = today_low  <= trailing_stop
        target2_hit = today_high >= effective_target_2 if effective_target_2 is not None else False
        target1_hit = today_high >= pos['target_1']
        # [GAP-THROUGH 2026-07-31] Fill at a price the market actually traded.
        # This branch used to book `exit_price = trailing_stop` unconditionally,
        # i.e. it assumed a stop order always fills exactly at its trigger. When
        # a stock gaps through the stop, that price never existed. 2026-07-30
        # SIGMA: stop 50.30, the bar OPENED at 48.00 and the day's low was
        # 47.20, yet both EDGE legs were booked out at exactly 50.304 -- a
        # 6.4% better exit than the close, on a fill that could not have
        # happened (Zerodha had in fact rejected the stop order outright).
        # penny_edge_engine.simulate_position has clamped to the open since
        # ROADMAP-3.3; position_tracker never got the same treatment.
        # Symmetric on the target side: a gap-up above the target fills at the
        # open, which is better than the limit, so max() there.
        if stop_hit and not (target2_hit or target1_hit):
            status = "STOPPED_OUT"
            exit_price = min(trailing_stop, today_open)
        elif target2_hit:
            status = "CLOSED_T2"
            exit_price = max(effective_target_2, today_open)
        elif target1_hit and current_status == "OPEN":
            status = "CLOSED_T1"
            exit_price = max(pos['target_1'], today_open)
            hit_t1_today = True
        elif days_held >= 15:
            status = "CLOSED_TIME"
            exit_price = today_close
        if status != current_status:
            if hit_t1_today:
                import math
                closed_shares = math.floor(pos['shares'] * 0.5)
                if closed_shares == 0: 
                    closed_shares = 1 # If only 1 share, sell it all
                remaining_shares = pos['shares'] - closed_shares
                gross = (exit_price - pos['entry_price']) * closed_shares
                costs = calc_zerodha_costs(pos['entry_price'], exit_price, closed_shares, is_intraday=False)
                realised_pnl = gross - costs
                await record_pnl_cb(ticker, realised_pnl, pos.get('source') or 'SYSTEM')
                if remaining_shares == 0:
                    # Full close (if you only had 1 share)
                    risk_initial = (pos['entry_price'] - pos['stop_loss_initial']) * pos['shares']
                    r_multiple = realised_pnl / risk_initial if risk_initial > 0 else 0
                    async with aiosqlite.connect(db_path) as db:
                        await db.execute("""
                            UPDATE positions SET highest_close_since_entry=?, trailing_stop_current=?,
                            status=?, exit_price=?, exit_date=?, realised_pnl=?, r_multiple=?
                            WHERE ticker=? AND entry_date=?
                        """, (highest_close, trailing_stop, "CLOSED_T1", exit_price, current_date_str, 
                            realised_pnl, r_multiple, ticker, pos['entry_date']))
                        await db.commit()
                else:
                    # Partial close (Let the remaining 50% ride)
                    trailing_stop = max(trailing_stop, pos['entry_price']) # Move to breakeven
                    async with aiosqlite.connect(db_path) as db:
                        await db.execute("""
                            UPDATE positions SET highest_close_since_entry=?, trailing_stop_current=?,
                            status=?, shares=?
                            WHERE ticker=? AND entry_date=?
                        """, (highest_close, trailing_stop, "CLOSED_T1", remaining_shares, ticker, pos['entry_date']))
                        await db.commit()
            else:
                # Normal Full Close (Stop Loss, Target 2, or Time Expiry)
                gross = (exit_price - pos['entry_price']) * pos['shares']
                costs = calc_zerodha_costs(pos['entry_price'], exit_price, pos['shares'], is_intraday=False)
                realised_pnl = gross - costs
                risk_initial = (pos['entry_price'] - pos['stop_loss_initial']) * pos['shares']
                r_multiple = realised_pnl / risk_initial if risk_initial > 0 else 0
                await record_pnl_cb(ticker, realised_pnl, pos.get('source') or 'SYSTEM')
                async with aiosqlite.connect(db_path) as db:
                    await db.execute("""
                        UPDATE positions SET highest_close_since_entry=?, trailing_stop_current=?,
                        status=?, exit_price=?, exit_date=?, realised_pnl=?, r_multiple=?
                        WHERE ticker=? AND entry_date=?
                    """, (highest_close, trailing_stop, status, exit_price, current_date_str, 
                        realised_pnl, r_multiple, ticker, pos['entry_date']))
                    await db.commit()
        else:
            # Just update the trailing stop and highest close for the day
            async with aiosqlite.connect(db_path) as db:
                await db.execute("""
                    UPDATE positions SET highest_close_since_entry=?, trailing_stop_current=?
                    WHERE ticker=? AND entry_date=?
                """, (highest_close, trailing_stop, ticker, pos['entry_date']))
                await db.commit()
