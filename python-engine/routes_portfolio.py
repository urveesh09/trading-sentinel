"""[ROADMAP-4.1 stage 3, 2026-07-13] Signal, position, bankroll and performance endpoints.

Extracted verbatim from main.py. Registered on the app via
`app.include_router(router)`, so the route table -- paths, methods, endpoint
names, response models -- is byte-identical; the 24-route characterization
golden proves it.

EVERY business name is reached through `_main` at CALL time, not imported.
That is not stylistic. Two independent reasons, both load-bearing:

  1. Eight of main's globals are REBOUND at runtime via `global` statements
     (current_signals, market_regime, momentum_signals_today, last_run,
     rejected_signals, current_momentum_signals, last_momentum_date,
     _last_regime_state). `from main import current_signals` would capture the
     list that existed at import and serve it forever, while run_screener
     quietly rebinds main's name to a NEW list on every scan. The endpoint
     would go permanently stale and nothing would raise.

  2. The suite patches ~25 of these names BY NAME on main (kite,
     get_open_positions, record_trade_close, post_login_initialization,
     run_momentum_screener, ...). Import-time binding silently detaches every
     one of those patches.

The module-level `import main as _main` is safe despite main importing this
module: Python registers main in sys.modules BEFORE executing it, so we bind
the module object, and only ever touch its attributes at request time -- by
which point main is fully initialised.
"""
from fastapi import APIRouter, HTTPException, Request

import main as _main

from datetime import datetime, timezone
import aiosqlite

from config import settings
from models import Regime
from models import (ManualPositionRequest, OpenPosition,
                    PerformanceReport, PortfolioResponse)

router = APIRouter()



@router.get("/signals", response_model=PortfolioResponse)
async def get_signals():
    async with _main.state_lock:
        halted, reasons = await _main.check_circuit_breakers(settings.DB_PATH)
        open_pos = await _main.get_open_positions(settings.DB_PATH)
        # Strict separation: report Nifty-subsystem balance on /signals.
        bankroll = await _main.nifty_bankroll(settings.DB_PATH)

        risk = sum((p['entry_price'] - p['stop_loss_initial']) * p['shares'] for p in open_pos)
        deployed = sum(p['entry_price'] * p['shares'] for p in open_pos)
        
        # Mark stale
        for s in _main.current_signals:
            s.stale_data = (datetime.now(timezone.utc) - s.signal_time).total_seconds() > 3600

        return PortfolioResponse(
            run_time=_main.last_run or datetime.now(timezone.utc),
            market_regime=_main.market_regime,
            bankroll=bankroll,
            backtest_gate="PASS" if "BACKTEST_GATE_FAILED" not in reasons else "FAIL",
            trading_halted=halted,
            halt_reasons=reasons,
            stale_data=bool(_main.last_run and (datetime.now(timezone.utc) - _main.last_run).total_seconds() > 3600),
            total_capital_at_risk=risk,
            total_capital_deployed=deployed,
            bankroll_utilization_pct=deployed / bankroll if bankroll else 0,
            open_positions_count=len(open_pos),
            remaining_slots=settings.MAX_OPEN_POSITIONS - len(open_pos),
            signals=_main.current_signals,
            regime=_main._last_regime_state.regime if _main._last_regime_state else Regime.UNKNOWN,
            regime_score=_main._last_regime_state.regime_score if _main._last_regime_state else 100.0,
        )




@router.get("/momentum-signals")
async def get_momentum_signals():
    async with _main.state_lock:
        # Strict separation: momentum display uses Nifty-subsystem balance.
        bankroll      = await _main.nifty_bankroll(settings.DB_PATH)
        momentum_pool = bankroll * settings.MOMENTUM_POOL_PCT  # 50% of bankroll = Rs2,500 at Rs5k
        halted, reasons = await _main.check_circuit_breakers(settings.DB_PATH)

        # [MOM-FUNNEL 2026-07-11] Serve the cumulative day list, not the
        # latest 15-min snapshot. The snapshot made this endpoint lossy for
        # its two consumers: the agent's poll (saw 3 of 17 signals on
        # 2026-07-10 -- no EXEC-button alert for the other 14) and the
        # gateway's EXEC callback (couldn't execute any signal wiped by a
        # newer scan). Both consumers dedupe/lock per ticker, so the wider
        # list is safe. Day guard: before the first scan of a new day,
        # _main.momentum_signals_today still holds yesterday's list -- serve [].
        signals_today = (
            _main.momentum_signals_today
            if _main.last_momentum_date == datetime.now(_main.IST).date()
            else []
        )
        for s in signals_today:
            s.stale_data = (
                datetime.now(timezone.utc) - s.signal_time
            ).total_seconds() > 1800   # 30 min stale for intraday

        return {
            "run_time":         _main.last_run,
            "_main.market_regime":    _main.market_regime,
            "momentum_pool":    round(momentum_pool, 2),
            "trading_halted":   halted,
            "halt_reasons":     reasons,
            "signals":          signals_today,
            # Latest scan's snapshot, kept for observability/debugging.
            "latest_scan_signals": _main.current_momentum_signals,
        }



@router.get("/rejected")
async def get_rejected_signals():
    # [MED-007 / ROADMAP-4.6 2026-07-12] Was a hardcoded `[]` -- the
    # dashboard's rejected panel could never show anything. Serve the
    # state-locked global the same way /signals serves _main.current_signals.
    async with _main.state_lock:
        return {"data": list(_main.rejected_signals)}




@router.get("/positions", response_model=list[OpenPosition])
async def get_positions_route():
    open_pos = await _main.get_open_positions(settings.DB_PATH)
    return open_pos




@router.post("/positions/manual")
async def add_manual_position(request: Request, payload: ManualPositionRequest):
    """
    Called by Container A after a successful execution.
    Creates a new position in the database.

    [AUDIT-FIX-1.4 2026-06-25] Body is now validated by Pydantic
    (ManualPositionRequest). Missing required fields -> HTTP 422
    with field-level error messages. Previously: KeyError -> HTTP 500.

    [AUDIT-FIX-2.2 2026-06-25] Uses the centralised auth gate.
    """
    _main._check_internal_secret(request, "add_manual_position")

    # Derive stop / targets from entry_price if not supplied. Same
    # defaults as the pre-fix manual dict path (95% / 105% / 110%).
    stop_loss = payload.stop_loss if payload.stop_loss is not None else payload.entry_price * 0.95
    target_1  = payload.target_1  if payload.target_1  is not None else payload.entry_price * 1.05
    target_2  = payload.target_2  if payload.target_2  is not None else payload.entry_price * 1.10

    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.execute("""
            INSERT INTO positions (
                ticker, exchange, entry_date, entry_price, shares,
                stop_loss_initial, trailing_stop_current, target_1, target_2,
                atr_14_at_entry, highest_close_since_entry, status, source, product_type,
                regime_at_entry, sl_order_id, vwap_at_entry
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (payload.ticker, payload.exchange, datetime.now(timezone.utc).isoformat(),
              payload.entry_price, payload.shares, stop_loss, stop_loss,
              target_1, target_2,
              # NULL, never 0.0. A 0.0 ATR makes the Chandelier stop resolve to
              # `highest_close - 3*0` == highest_close, which sits at or above
              # entry and force-closes the position at its own entry price. That
              # bug shipped twice already (atr_1min_post_t1, and the EDGE book).
              payload.atr_14_at_entry,
              payload.entry_price, "OPEN",
              payload.source, payload.product_type, payload.regime_at_entry,
              payload.sl_order_id, payload.vwap_at_entry))
        await db.commit()

    _main.logger.info("position_added_manually", ticker=payload.ticker,
                source=payload.source, regime=payload.regime_at_entry,
                sl_order_id=payload.sl_order_id, atr=payload.atr_14_at_entry)
    return {"status": "ok"}



@router.post("/positions/close")
async def close_position(request: Request):
    """
    Called by Container A after a square-off order is confirmed.
    Updates position status to CLOSED_MANUAL and records P&L.

    [AUDIT-FIX-2.2 2026-06-25] Uses the centralised auth gate.
    """
    _main._check_internal_secret(request, "close_position")
    data = await request.json()

    ticker     = data["ticker"]
    exit_price = float(data["exit_price"])
    order_id   = data.get("order_id", "")

    open_pos = await _main.get_open_positions(settings.DB_PATH)
    pos = next((p for p in open_pos if p['ticker'] == ticker
                and p.get('source') == 'MOMENTUM'), None)
    if not pos:
        raise HTTPException(status_code=404,
                            detail=f"No open MOMENTUM position for {ticker}")

    gross = (exit_price - pos['entry_price']) * pos['shares']
    # [AUDIT-FIX-1.2] Derive is_intraday from product_type (was hardcoded True).
    costs = _main.calc_zerodha_costs(
        pos['entry_price'], exit_price, pos['shares'],
        is_intraday=_main._is_intraday_from_product_type(pos.get('product_type')),
    )
    realised_pnl = gross - costs
    risk_initial = (pos['entry_price'] - pos['stop_loss_initial']) * pos['shares']
    r_multiple   = realised_pnl / risk_initial if risk_initial > 0 else 0

    # [LEDGER-INTEGRITY 2026-07-26] Accept CLOSED_T1 as closable and gate the
    # ledger write on rowcount, matching auto_square_momentum. A WHERE clause that
    # matches nothing must never book P&L -- that is exactly how four sessions of
    # fabricated losses reached the live ledger in July.
    async with aiosqlite.connect(settings.DB_PATH) as db:
        cur = await db.execute("""
            UPDATE positions
            SET status='CLOSED_MANUAL', exit_price=?, exit_date=?,
                realised_pnl=?, r_multiple=?
            WHERE ticker=? AND source='MOMENTUM'
              AND status IN ('OPEN', 'CLOSED_T1') AND exit_date IS NULL
        """, (exit_price, datetime.now(timezone.utc).isoformat(),
              realised_pnl, r_multiple, ticker))
        await db.commit()
        rows_closed = cur.rowcount

    if rows_closed != 1:
        _main.logger.error("close_position_not_persisted", ticker=ticker,
                           rows_affected=rows_closed, order_id=order_id)
        raise HTTPException(
            status_code=409,
            detail=f"{ticker}: {rows_closed} position rows closed -- no P&L booked. "
                   "Reconcile against the broker before retrying.",
        )

    # [SOURCE-REQUIRED 2026-07-26] Was omitting `source`, so this endpoint booked
    # momentum closes into the SWING pool via the old "SYSTEM" default.
    await _main.record_trade_close(settings.DB_PATH, ticker, realised_pnl,
                                   r_multiple=r_multiple, notes="manual",
                                   source=pos.get('source') or 'MOMENTUM')
    _main.logger.info("momentum_position_closed", ticker=ticker,
                exit_price=exit_price, pnl=realised_pnl, r=r_multiple)

    return {"status": "closed", "ticker": ticker,
            "realised_pnl": round(realised_pnl, 2),
            "r_multiple":   round(r_multiple, 4)}



@router.get("/bankroll")
async def get_bankroll_route():
    # 2026-06-24 strict separation: /bankroll reports the Nifty-subsystem
    # balance (swing + momentum), excluding penny. For per-pool breakdown
    # including the penny pool, see GET /bankroll/breakdown.
    val = await _main.nifty_bankroll(settings.DB_PATH)
    return {"status": "ok", "bankroll": val}




# 2026-06-24 (B-tight): per-pool breakdown endpoint. Returns swing and
# penny balances independently. No risk math is touched -- current_bankroll()
# and _main.check_circuit_breakers() are unchanged. The combined number is
# informational only. See docs/deviations/2026-06-24-penny-bankroll-pool-breakdown-deviation.md
@router.get("/bankroll/breakdown")
async def get_bankroll_breakdown():
    from performance import pool_breakdown
    return await pool_breakdown(settings.DB_PATH)


# [DIVISION-BREAKDOWN 2026-07-15] Full per-division P&L attribution: swing,
# intraday momentum, penny breakout, penny edge (paper/live), F&O (paper/live),
# with capital rolled up per pool and totalled live-vs-paper. Informational only.
@router.get("/bankroll/divisions")
async def get_bankroll_divisions():
    from performance import division_breakdown
    return await division_breakdown(settings.DB_PATH)




@router.get("/performance", response_model=PerformanceReport)
async def get_performance():
    """[AUDIT-FIX-2.6] HTTP wrapper around the shared async helper."""
    return await _main.compute_performance_report(settings.DB_PATH)
