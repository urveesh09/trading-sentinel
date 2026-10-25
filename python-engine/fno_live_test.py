"""[O25 2026-10-25] The owner's real-money F&O test: own cash, one lot, the paper book's trades.

The owner's decision (Oct 25): after a five-session paper proving week
(fno_proving_week.py), put FNO_LIVE_TEST_CAPITAL (₹12,500) of real money on the
pure intraday single-leg F&O book for about a week, with the investment and
risk guardrails relaxed, to see how the system trades with real fills. It is
one switch, FNO_LIVE_TEST_ENABLED; it is off unless the owner sets it.

What the test does
  - It never decides a trade. When the paper book buys an option, the test
    buys ONE lot of the same contract on the same signal bar (``mirror_entry``),
    so the signal, strike, gates, reward/risk, the paper book's own size tiers,
    loss brakes and drawdown halt all decide for both. Its exits are the same
    ladder on its own fill (fno_orchestrator: underlying stop and target from the
    same signal, the 25% premium stop, trail, profit lock, time stop, 15:10 hard
    flat), plus a resting broker stop-loss (fno_broker_backstop).
  - The buy is a LIMIT at the fresh ask plus FNO_LIVE_TEST_ENTRY_BUFFER_TICKS
    (it trades at the ask or better). It is skipped when that ask is more than
    FNO_LIVE_TEST_MAX_CHASE_PCT above the paper book's price, when the quote is
    stale or one-sided, or when its spread is over FNO_MAX_SPREAD_PCT; an
    unfilled order is cancelled after FNO_FILL_TIMEOUT_SEC (never chased).

What is relaxed, and only here
  - The 2%-of-pool risk per trade, the minimum-viable-pool and open-premium
    gates, and the live go-live bar (fno_risk.fno_go_live_check). One lot at
    the 25% stop risks about ₹1.5k-3.7k: 12-30% of ₹12,500 per losing trade.

What is kept
  - Own cash only: kite_client refuses a BUY that its own free cash in the
    account cannot pay (no margin, no leverage), and the shared F&O ledger
    reserves the trade's whole premium against the test's own equity.
  - NIFTY (NFO) only, never on its expiry day, one open position, at most
    FNO_MAX_TRADES_PER_DAY entries, MIS, LIMIT orders only.
  - The floor: no new entry while test equity (capital plus realised real P&L)
    is under FNO_LIVE_TEST_FLOOR; the owner is told once a day.

Switching it off stops new entries only: an open real position is still
managed to its exit (fno_orchestrator._live_leg_managed).
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

import aiosqlite
import structlog

from config import settings
from fno_models import FnoSource

logger = structlog.get_logger()
SOURCE = FnoSource.FNO_LIVE.value
PAPER = FnoSource.FNO_PAPER.value
_FLOOR_TOLD: set = set()


def armed() -> bool:
    return bool(getattr(settings, "FNO_LIVE_TEST_ENABLED", False))


def live_pool() -> float:
    """The live leg's allocation: the test capital while the test is on."""
    return float(settings.FNO_LIVE_TEST_CAPITAL) if armed() else float(settings.FNO_LIVE_BANKROLL)


def entry_limit(ask: float, tick: float, buffer_ticks: int, cap: float) -> Optional[float]:
    """The buy LIMIT: the ask on the tick grid plus the buffer, never over ``cap``
    (the chase limit) and never under the ask; None when the ask is over the cap."""
    if ask <= 0 or tick <= 0:
        return None
    on_grid = math.ceil(round(ask / tick, 6)) * tick
    if on_grid > cap + 1e-9:
        return None
    capped = math.floor(round(cap / tick, 6)) * tick
    return round(max(on_grid, min(on_grid + buffer_ticks * tick, capped)), 2)


async def live_equity(db_path: str) -> Optional[float]:
    """Capital plus realised real P&L; None when the ledger cannot be read (fail closed)."""
    try:
        async with aiosqlite.connect(db_path) as db:
            exists = await (await db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bankroll_ledger'")).fetchone()
            if exists is None:
                return live_pool()
            row = await (await db.execute(
                "SELECT COALESCE(SUM(pnl), 0.0) FROM bankroll_ledger WHERE source=?", (SOURCE,))).fetchone()
        return live_pool() + float(row[0] or 0.0)
    except Exception as exc:
        logger.error("fno_live_test_equity_unreadable err=%s", str(exc))
        return None


async def _paper_row(db_path: str, bar_ts: str, symbol: str, underlying: str) -> Optional[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM fno_positions WHERE source=? AND bar_ts=? AND tradingsymbol=? AND underlying=? "
            "ORDER BY id DESC LIMIT 1", (PAPER, bar_ts, symbol, underlying))).fetchone()
    return dict(row) if row else None


async def _fresh_quote(kite, contract):
    """The contract's quote right now (management lane); None when unreadable."""
    from fno_chain import _parse_quote_entry
    from kite_client import provider_lane
    try:
        with provider_lane("management"):
            observed = getattr(type(kite), "get_quote_with_timing", None)
            if callable(observed):
                raw, _timing = await observed(kite, [contract.token], priority="management")
            else:
                raw = await kite.get_quote([contract.token])
    except Exception as exc:
        logger.error("fno_live_test_quote_failed symbol=%s err=%s", contract.tradingsymbol, str(exc))
        return None
    q = (raw or {}).get(contract.token)
    return _parse_quote_entry(contract, q) if q else None


def _contract_for(row: dict, instruments):
    from datetime import date
    from fno_models import Contract, OptionType
    expiry = date.fromisoformat(row["expiry"])
    found = None
    try:
        found = instruments.option(expiry, float(row["strike"]), OptionType(row["opt_type"]))
    except Exception:
        found = None
    if found is not None and found.tradingsymbol == row["tradingsymbol"]:
        return found
    return Contract(token=int(row["token"]), tradingsymbol=row["tradingsymbol"], name=row["underlying"],
                    expiry=expiry, strike=float(row["strike"]), instrument_type=row["opt_type"],
                    lot_size=int(row["lot_size"]), tick_size=float(settings.FNO_TICK_SIZE))


async def _tell_floor_once(now_ist: datetime, equity: float) -> None:
    day = now_ist.date().isoformat()
    if day in _FLOOR_TOLD:
        return
    try:
        from operator_alert import notify_operator
        told = await notify_operator(
            f"🛑 REAL-money F&O test: equity ₹{equity:,.0f} is under its floor "
            f"₹{settings.FNO_LIVE_TEST_FLOOR:,.0f} (it started with ₹{live_pool():,.0f}). No new real trades; the "
            "paper book carries on. Lowering the floor, adding capital or ending the test is your decision.",
            event="fno_live_test_floor")
        if told:                       # an undelivered notice is tried again on the next refusal
            _FLOOR_TOLD.add(day)
    except Exception as exc:
        logger.error("fno_live_test_floor_notice_failed err=%s", str(exc))


async def mirror_entry(kite, db_path: str, executor, *, sig, paper_entry: dict, underlying: str, instruments,
                       regime: str, now_ist: datetime, scan_id: str, action_clock=None) -> Optional[dict]:
    """Buy one real lot of the contract the paper book just bought; the entry
    record, or None (every refusal is logged as a FNO_LIVE signal row)."""
    from fno_costs import calc_fno_costs
    from fno_models import Leg, OptionType
    from fno_risk import validate_position
    from fno_signal_log import log_fno_signal
    import fno_positions as fpos

    if not armed():
        return None
    symbol = paper_entry.get("symbol") or ""

    async def _log(accepted: bool, reason: str, **extra):
        try:
            await log_fno_signal(db_path, scan_id=scan_id, leg=SOURCE, accepted=accepted, reject_reason=reason,
                                 bar_ts=sig.bar_ts, underlying=underlying,
                                 direction=sig.direction.value if sig.direction else None, regime=regime,
                                 tradingsymbol=symbol, **extra)
        except Exception as exc:
            logger.error("fno_live_test_signal_log_failed err=%s", str(exc))
        if not accepted:
            logger.warning("fno_live_test_skip symbol=%s reason=%s", symbol, reason)

    if getattr(executor, "paper_mode", True):
        await _log(False, "live_test_executor_not_live")
        return None
    today = now_ist.date()
    if instruments.is_expiry_day(today):
        # The owner excluded expiry trading from this test; held even if
        # FNO_EXPIRY_DAY_ENTRIES is ever switched on for paper.
        await _log(False, "live_test_expiry_day")
        return None
    row = await _paper_row(db_path, sig.bar_ts, symbol, underlying)
    if row is None:
        await _log(False, "live_test_paper_row_missing")
        return None
    if await fpos.already_entered_bar(db_path, SOURCE, sig.bar_ts, underlying=underlying):
        return None
    if await fpos.open_positions(db_path, SOURCE):
        await _log(False, "live_test_position_open")
        return None
    if await fpos.trades_today(db_path, SOURCE, today.isoformat()) >= int(settings.FNO_MAX_TRADES_PER_DAY):
        await _log(False, "live_test_trades_per_day")
        return None
    equity = await live_equity(db_path)
    if equity is None:
        await _log(False, "live_test_equity_unreadable")
        return None
    if equity < float(settings.FNO_LIVE_TEST_FLOOR):
        await _log(False, "live_test_floor")
        await _tell_floor_once(now_ist, equity)
        return None

    contract = _contract_for(row, instruments)
    quote = await _fresh_quote(kite, contract)
    clock = action_clock() if action_clock is not None else now_ist
    paper_price = float(row["entry_premium"])
    if quote is None or quote.bid <= 0 or quote.ask <= 0:
        await _log(False, "live_test_no_two_sided_quote")
        return None
    age = (clock - quote.last_trade_time).total_seconds() if quote.last_trade_time else float("inf")
    if age > settings.FNO_MAX_QUOTE_AGE_SEC:
        await _log(False, "live_test_quote_stale", premium=quote.ask)
        return None
    if quote.spread_pct > settings.FNO_MAX_SPREAD_PCT:
        await _log(False, "live_test_spread", premium=quote.ask, spread_pct=quote.spread_pct)
        return None
    tick = float(contract.tick_size or settings.FNO_TICK_SIZE)
    limit = entry_limit(quote.ask, tick, int(settings.FNO_LIVE_TEST_ENTRY_BUFFER_TICKS),
                        paper_price * (1.0 + float(settings.FNO_LIVE_TEST_MAX_CHASE_PCT)))
    if limit is None:
        await _log(False, "live_test_price_ran", premium=quote.ask)
        return None
    lot_size = int(row["lot_size"])
    qty = lot_size                                   # one lot, always
    opt_type = OptionType(row["opt_type"])
    ok, reason, max_loss = validate_position(
        [Leg(opt_type=opt_type, strike=float(row["strike"]), quantity=1, premium=limit)], lot_size)
    if not ok:
        await _log(False, reason, premium=limit, lots=1, max_loss_rupees=max_loss)
        return None
    fields = dict(strike=float(row["strike"]), opt_type=opt_type.value, expiry=row["expiry"], premium=limit,
                  iv=row.get("iv_at_entry"), delta=row.get("delta_at_entry"), spread_pct=quote.spread_pct, lots=1,
                  max_loss_rupees=max_loss, pool_at_eval=round(equity, 2))

    # The same reservation, single dispatch claim and outcome protocol as the
    # paper/live legs (fno_orchestrator._try_entry_for_leg): the whole premium
    # plus exit costs is reserved against the test's own equity first.
    from performance import init_ledger
    import fno_dr_book as _dr
    from fno_shared_risk import (DISPATCH_RELEASE_OUTCOMES, DISPATCH_RETAIN_OUTCOMES, EntryOccupancy,
                                 claim_shared_fno_entry_dispatch, init_shared_fno_risk_db,
                                 reserve_shared_fno_risk, resolve_shared_fno_entry_dispatch)
    await init_ledger(db_path)
    await fpos.init_fno_positions_db(db_path)
    await _dr.init_dr_db(db_path)
    await init_shared_fno_risk_db(db_path)
    exchange = instruments.segment
    key = f"single:{SOURCE}:{contract.token}:{sig.bar_ts}"
    admission = await reserve_shared_fno_risk(
        db_path, source=SOURCE, pool_rs=live_pool(), reservation_key=key, book="SINGLE_LEG",
        worst_case_cash_rs=max_loss + calc_fno_costs(limit, 0.0, qty, exchange=exchange),
        entry_day_ist=None, policy=None,
    )
    if not admission.allowed:
        await _log(False, f"live_test_{admission.reason}", **fields)
        return None
    claim = await claim_shared_fno_entry_dispatch(
        db_path, reservation_key=key, source=SOURCE, book="SINGLE_LEG", pool_rs=live_pool(), entry_day_ist=None,
        policy=None, occupancy=EntryOccupancy(
            entry_day=today, max_open=1, tradingsymbol=symbol, planned_premium_rs=limit * qty,
            max_trades_per_day=int(settings.FNO_MAX_TRADES_PER_DAY), max_open_premium_rs=live_pool(),
            no_pyramid=True),
    )
    if not claim.granted:
        await _log(False, f"dispatch_claim_denied:{claim.reason}", **fields)
        return None
    if action_clock is not None:
        late = action_clock()
        minute = late.hour * 60 + late.minute
        stale = (late - quote.last_trade_time).total_seconds() if quote.last_trade_time else float("inf")
        reason = ("entry_window" if not settings.FNO_ENTRY_START_MIN <= minute < settings.FNO_ENTRY_END_MIN
                  else "quote_freshness" if stale > settings.FNO_MAX_QUOTE_AGE_SEC else None)
        if reason:
            await resolve_shared_fno_entry_dispatch(
                db_path, reservation_key=key, owner=claim.owner, outcome="no_dispatch",
                evidence={"dispatch_certainty": "NOT_SENT", "order_id": None, "reason": f"post_admission_{reason}"})
            await _log(False, f"post_admission_{reason}", **fields)
            return None

    result = await executor.execute_entry(symbol, qty, limit,
                                          **({} if exchange == "NFO" else {"exchange": exchange}))
    status = result["status"]
    if status != "filled":
        outcome = status if status in DISPATCH_RELEASE_OUTCOMES | DISPATCH_RETAIN_OUTCOMES else "unknown"
        applied = await resolve_shared_fno_entry_dispatch(
            db_path, reservation_key=key, owner=claim.owner, outcome=outcome,
            evidence=result.get("evidence") or {"status": status})
        await _log(False, f"entry_{status}", **fields)
        if applied not in DISPATCH_RELEASE_OUTCOMES:
            logger.critical("fno_live_test_entry_unresolved symbol=%s status=%s applied=%s reservation=%s",
                            symbol, status, applied, key)
            await _page(f"⚠️ REAL F&O buy unclear: {symbol} order status {status}. Check Kite: if you hold it, "
                        "sell it there; the system will not trade it.", "fno_live_test_entry_unclear")
        return None

    fill = float(result["fill_price"])
    _ok, _reason, filled_loss = validate_position(
        [Leg(opt_type=opt_type, strike=float(row["strike"]), quantity=1, premium=fill)], lot_size)
    try:
        position_id = await fpos.insert_position_with_risk_reservation(
            db_path, reservation_key=key,
            source=SOURCE, tradingsymbol=symbol, token=contract.token, underlying=underlying,
            expiry=row["expiry"], strike=float(row["strike"]), opt_type=opt_type.value,
            direction=row["direction"], lots=1, lot_size=lot_size, qty=qty,
            entry_time=clock.isoformat(), entry_date=clock.date().isoformat(), entry_premium=fill,
            entry_underlying=row["entry_underlying"], delta_at_entry=row.get("delta_at_entry"),
            iv_at_entry=row.get("iv_at_entry"), atr_at_entry=row.get("atr_at_entry"),
            stop_underlying=row["stop_underlying"], target_underlying=row["target_underlying"],
            premium_stop=round((1.0 - settings.FNO_STOP_PREMIUM_PCT) * fill, 2),
            trail_active=0, trail_stop_underlying=None, best_underlying=row["entry_underlying"],
            max_loss_rupees=filled_loss, status="OPEN", entry_order_id=result.get("order_id"),
            bar_ts=sig.bar_ts,
        )
    except Exception as exc:
        await resolve_shared_fno_entry_dispatch(
            db_path, reservation_key=key, owner=claim.owner, outcome="filled_unrecorded",
            evidence={**(result.get("evidence") or {}), "dispatch_certainty": "ACCEPTED",
                      "order_id": result.get("order_id"), "receipt": "position_insert_failed"})
        logger.critical("fno_live_test_fill_unrecorded symbol=%s order_id=%s err=%s", symbol,
                        result.get("order_id"), str(exc))
        await _page(f"🔴 REAL F&O buy filled but NOT recorded: {symbol} x{qty} at ₹{fill:.2f} (order "
                    f"{result.get('order_id')}). The system cannot manage it: sell it in Kite.",
                    "fno_live_test_fill_unrecorded")
        return None
    import fno_broker_backstop
    await fno_broker_backstop.arm(db_path, executor, position_id=position_id, source=SOURCE, tradingsymbol=symbol,
                                  exchange=exchange, qty=qty, fill=fill, tick=settings.FNO_TICK_SIZE)
    await _log(True, "", **{**fields, "premium": fill, "max_loss_rupees": filled_loss})
    logger.info("fno_live_test_entry symbol=%s qty=%d fill=%.2f paper=%.2f limit=%.2f order_id=%s", symbol, qty,
                fill, paper_price, limit, result.get("order_id"))
    return {"symbol": symbol, "direction": row["direction"], "lots": 1, "fill": fill,
            "delta": round(float(row.get("delta_at_entry") or 0.0), 2),
            "iv": round(float(row.get("iv_at_entry") or 0.0), 3), "source": SOURCE, "paper_fill": paper_price}


async def _page(text: str, event: str) -> None:
    try:
        from operator_alert import notify_operator
        await notify_operator(text, event=event)
    except Exception as exc:
        logger.error("fno_live_test_page_failed event=%s err=%s", event, str(exc))


def _rs(value: float) -> str:
    return f"{'+' if value >= 0 else '-'}₹{abs(value):,.0f}"


async def day_report(db_path: str, day_iso: str) -> Optional[str]:
    """The day's real trades beside the paper trade each mirrored; None without real trades."""
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            exists = await (await db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fno_positions'")).fetchone()
            if exists is None:
                return None
            rows = [dict(r) for r in await (await db.execute(
                "SELECT l.tradingsymbol, l.status, l.entry_premium, l.exit_premium, l.exit_reason, l.pnl, l.qty, "
                "p.entry_premium AS paper_entry, p.exit_premium AS paper_exit, p.pnl AS paper_pnl, "
                "COALESCE(p.initial_lots, p.lots) AS paper_lots, p.exit_reason AS paper_reason "
                "FROM fno_positions l LEFT JOIN fno_positions p ON p.source=? AND p.bar_ts=l.bar_ts "
                "AND p.tradingsymbol=l.tradingsymbol WHERE l.source=? AND l.entry_date=? ORDER BY l.id",
                (PAPER, SOURCE, day_iso))).fetchall()]
    except Exception as exc:
        logger.error("fno_live_test_day_report_failed err=%s", str(exc))
        return None
    if not rows:
        return None
    equity = await live_equity(db_path)
    lines = [f"💰 REAL-money F&O test, {day_iso}: {len(rows)} trade(s)"]
    real_total = paper_total = 0.0
    for r in rows:
        if r["status"] != "CLOSED":
            lines.append(f"- {r['tradingsymbol']}: bought ₹{r['entry_premium']:.2f} (paper ₹"
                         f"{(r['paper_entry'] or 0):.2f}); still {r['status'].lower()}")
            continue
        paper_one_lot = (r["paper_pnl"] or 0.0) / max(1, int(r["paper_lots"] or 1))
        real_total += float(r["pnl"] or 0.0)
        paper_total += paper_one_lot
        lines.append(f"- {r['tradingsymbol']}: real ₹{r['entry_premium']:.2f} → ₹{r['exit_premium']:.2f} "
                     f"({r['exit_reason']}) = {_rs(r['pnl'] or 0.0)}; paper ₹{(r['paper_entry'] or 0):.2f} → "
                     f"₹{(r['paper_exit'] or 0):.2f} = {_rs(paper_one_lot)} a lot")
    lines.append(f"Real {_rs(real_total)} against paper {_rs(paper_total)} (one lot, after charges); the gap "
                 "is real fills and timing.")
    if equity is not None:
        lines.append(f"Test equity ₹{equity:,.0f} of ₹{live_pool():,.0f} (floor ₹{settings.FNO_LIVE_TEST_FLOOR:,.0f}).")
    return "\n".join(lines)
