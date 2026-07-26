"""
[MOMENTUM-PAPER 2026-07-26] A paper twin of the live momentum book.

WHY THIS EXISTS
---------------
Live momentum entry is manual: the screener sends a Telegram EXEC button and a
human decides. The ledger therefore records what the *operator* did, never what
the *strategy* proposed -- 8 recorded momentum trades in months of running, which
is why nothing can be concluded about the strategy from them. A signal that fired
at 11:04 while nobody was looking left no trace at all.

This book takes EVERY accepted momentum signal automatically, sizes it off its
own pool, manages it with the same pure exit logic the live book uses, and books
cost-adjusted P&L to source='MOMENTUM_PAPER'. The result is a record of the
strategy's own decisions, which is the thing the promotion ladder actually needs.

It matters now in particular because MOMENTUM_MIN_STOP_PCT just changed the stop,
the position size and the R distribution simultaneously, and that cannot be
evaluated on roughly two manual trades a month.

SAFETY
------
This module contains NO order-placing code. Not a disabled branch, not a flag
that must stay False -- there is no call to place_order, no square-off endpoint,
no executor import anywhere in the file. The only outbound call is a read-only
LTP fetch, injected as `ltp_fn` so tests never touch the network.

That is deliberate. The 2026-07-21..24 incident was a book placing real orders it
was never meant to place, and the cheapest way to guarantee that cannot happen
here is to leave the capability out of the module entirely.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import aiosqlite
import structlog

from config import settings
from engine import calc_zerodha_costs
from momentum_exits import ACTION_EXIT, ACTION_TRAIL, evaluate_momentum_exit, momentum_exit_status

logger = structlog.get_logger()

SOURCE = "MOMENTUM_PAPER"

# Fills are modelled at the quoted price with real Zerodha costs applied on top.
# No slippage model: intraday MIS on liquid NSE names fills close to the quote,
# and inventing a slippage number would make the paper book look precise about
# something it is guessing at. Costs are NOT optional -- a cost-free paper book
# would report the exact optimism this system has already been burned by.
LtpFn = Callable[[str], Awaitable[Optional[float]]]


def paper_position_size(close: float, stop_loss: float, pool: float,
                        risk_pct: float) -> int:
    """Shares for the paper book, using the live sizing rule at paper scale.

    Mirrors engine.evaluate_momentum_signal: risk a fixed fraction of the pool,
    divided by per-share risk, then cap so one position cannot exceed the pool.
    Sized from the PAPER pool rather than copying the live share count, because
    copying would just reproduce the Rs 2,500 pool's 0-1 share positions, where
    tick size and costs swamp whatever edge the signal has.
    """
    if close <= 0 or stop_loss <= 0 or pool <= 0:
        return 0
    risk_per_share = close - stop_loss
    if risk_per_share <= 0:
        return 0
    shares = math.floor((pool * risk_pct) / risk_per_share)
    if shares * close > pool:                      # never exceed the pool
        shares = math.floor(pool / close)
    return max(0, shares)


def _sig_get(sig, key, default=None):
    """Accepted signals arrive as dicts or pydantic models depending on caller."""
    if sig is None:
        return default
    if isinstance(sig, dict):
        return sig.get(key, default)
    return getattr(sig, key, default)


async def open_momentum_paper_positions(db_path: str, accepted: list,
                                        now_utc: Optional[datetime] = None) -> list:
    """Open a paper position for each accepted signal not already held today.

    Returns the list of opened tickers. Never raises into the screener: a paper
    bookkeeping failure must not take down the live scan that produced the signal.
    """
    if not settings.MOMENTUM_PAPER_ENABLED or not accepted:
        return []

    now_utc = now_utc or datetime.now(timezone.utc)
    pool = float(settings.MOMENTUM_PAPER_BANKROLL)
    risk_pct = float(settings.MOMENTUM_RISK_PCT)
    opened = []

    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT ticker FROM positions WHERE source=? AND exit_date IS NULL",
                (SOURCE,),
            ) as cur:
                held = {r[0] for r in await cur.fetchall()}

            for sig in accepted:
                ticker = _sig_get(sig, "ticker")
                close = float(_sig_get(sig, "close", 0) or 0)
                stop = float(_sig_get(sig, "stop_loss", 0) or 0)
                if not ticker or ticker in held:
                    continue
                shares = paper_position_size(close, stop, pool, risk_pct)
                if shares < 1:
                    logger.info("momentum_paper_skip ticker=%s reason=zero_shares "
                                "close=%s stop=%s", ticker, close, stop)
                    continue

                await db.execute(
                    "INSERT INTO positions "
                    "(ticker, exchange, entry_date, entry_price, shares, "
                    " stop_loss_initial, trailing_stop_current, target_1, target_2, "
                    " atr_14_at_entry, highest_close_since_entry, status, source, "
                    " product_type, regime_at_entry, t1_fired) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ticker, "NSE", now_utc.isoformat(), close, shares,
                     stop, stop,
                     _sig_get(sig, "target_1"), _sig_get(sig, "target_2"),
                     _sig_get(sig, "atr_at_entry"), close, "OPEN", SOURCE,
                     "MIS", _sig_get(sig, "regime"), 0),
                )
                held.add(ticker)
                opened.append(ticker)
                logger.info(
                    "momentum_paper_opened ticker=%s shares=%d entry=%.2f stop=%.2f "
                    "notional=%.0f pool=%.0f", ticker, shares, close, stop,
                    shares * close, pool,
                )
            await db.commit()
    except Exception as exc:
        logger.error("momentum_paper_open_failed err=%s", str(exc), exc_info=True)
        return opened

    return opened


async def _close_paper_position(db, db_path: str, pos: dict, exit_price: float,
                                status: str, reason: str) -> Optional[float]:
    """Persist the close, then book cost-adjusted P&L. Returns realised P&L.

    Same rowcount discipline as the live path (see auto_square_momentum): the
    ledger is only written when a position row actually closed. A close that
    matched nothing must never book P&L -- that is precisely how four sessions of
    fabricated losses got into the real ledger.
    """
    from performance import record_trade_close

    entry = float(pos["entry_price"])
    shares = int(pos["shares"])
    gross = (exit_price - entry) * shares
    costs = calc_zerodha_costs(entry, exit_price, shares, is_intraday=True)
    realised = gross - costs
    risk_initial = (entry - float(pos["stop_loss_initial"])) * shares
    r_multiple = realised / risk_initial if risk_initial > 0 else 0.0

    cur = await db.execute(
        "UPDATE positions SET status=?, exit_price=?, exit_date=?, "
        "       realised_pnl=?, r_multiple=? "
        "WHERE ticker=? AND source=? AND exit_date IS NULL",
        (status, exit_price, datetime.now(timezone.utc).isoformat(),
         realised, r_multiple, pos["ticker"], SOURCE),
    )
    await db.commit()
    if cur.rowcount != 1:
        logger.error("momentum_paper_close_not_persisted ticker=%s rows=%d",
                     pos["ticker"], cur.rowcount)
        return None

    await record_trade_close(db_path, pos["ticker"], realised,
                            r_multiple=r_multiple, notes=f"paper:{reason}",
                            source=SOURCE)
    logger.info("momentum_paper_closed ticker=%s exit=%.2f pnl=%.2f r=%.2f reason=%s",
                pos["ticker"], exit_price, realised, r_multiple, reason)
    return realised


async def momentum_paper_monitor(db_path: str, ltp_fn: LtpFn,
                                 now_ist: datetime) -> dict:
    """Evaluate stops/targets/trails on open paper positions.

    Reuses evaluate_momentum_exit -- the same pure decision function the live book
    uses -- so the paper record reflects the live exit policy rather than a
    parallel one that could quietly drift.
    """
    if not settings.MOMENTUM_PAPER_ENABLED:
        return {"checked": 0, "exited": [], "trailed": []}

    exited, trailed = [], []
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM positions WHERE source=? AND exit_date IS NULL",
                (SOURCE,),
            ) as cur:
                positions = [dict(r) for r in await cur.fetchall()]

            for pos in positions:
                ltp = await ltp_fn(pos["ticker"])
                if not ltp or ltp <= 0:
                    continue
                decision = evaluate_momentum_exit(pos, float(ltp), now_ist)
                action = decision.get("action")
                if action == ACTION_EXIT:
                    status = momentum_exit_status(decision.get("reason", ""))
                    pnl = await _close_paper_position(
                        db, db_path, pos, float(ltp), status,
                        decision.get("reason", "exit"),
                    )
                    if pnl is not None:
                        exited.append((pos["ticker"], round(pnl, 2)))
                elif action == ACTION_TRAIL and decision.get("new_stop"):
                    await db.execute(
                        "UPDATE positions SET trailing_stop_current=? "
                        "WHERE ticker=? AND source=? AND exit_date IS NULL",
                        (float(decision["new_stop"]), pos["ticker"], SOURCE),
                    )
                    await db.commit()
                    trailed.append(pos["ticker"])
    except Exception as exc:
        logger.error("momentum_paper_monitor_failed err=%s", str(exc), exc_info=True)

    return {"checked": len(exited) + len(trailed), "exited": exited, "trailed": trailed}


async def momentum_paper_square_off(db_path: str, ltp_fn: LtpFn,
                                    now_ist: datetime) -> list:
    """15:15 IST: flatten every open paper position, mirroring the live MIS book.

    Momentum is intraday, so nothing may be carried overnight -- otherwise the
    paper record would show a strategy the live book cannot run.
    """
    if not settings.MOMENTUM_PAPER_ENABLED:
        return []

    closed = []
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM positions WHERE source=? AND exit_date IS NULL",
                (SOURCE,),
            ) as cur:
                positions = [dict(r) for r in await cur.fetchall()]

            for pos in positions:
                ltp = await ltp_fn(pos["ticker"])
                if not ltp or ltp <= 0:
                    # No quote: fall back to the entry price so the position is
                    # still flattened. Carrying it would misreport an intraday
                    # strategy as holding overnight.
                    ltp = float(pos["entry_price"])
                    logger.warning("momentum_paper_squareoff_no_quote ticker=%s "
                                   "using_entry_price", pos["ticker"])
                pnl = await _close_paper_position(
                    db, db_path, pos, float(ltp), "CLOSED_TIME", "eod_square_off",
                )
                if pnl is not None:
                    closed.append((pos["ticker"], round(pnl, 2)))
    except Exception as exc:
        logger.error("momentum_paper_squareoff_failed err=%s", str(exc), exc_info=True)

    if closed:
        logger.info("momentum_paper_squared_off n=%d total_pnl=%.2f",
                    len(closed), sum(p for _, p in closed))
    return closed
