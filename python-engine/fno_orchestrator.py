"""
[FNO-ORCHESTRATOR 2026-07-10] Dual-leg tick runner for the F&O subsystem
(spec §10.4).

Reuses the EDGE_PAPER / EDGE_LIVE shape from penny_edge_orchestrator:
one candidate scan, two legs, bankroll scales the sizing, separate
source tags (FNO_PAPER / FNO_LIVE) so the legs cannot see each other's
rows. In P1 the live leg is structurally disarmed three ways:
FNO_DISABLE_LIVE=True, FNO_LIVE_TRADING=False, FNO_LIVE_BANKROLL=0 --
and even with all three flipped it still refuses unless
fno_go_live_check() returns [].

run_fno_tick() fires every FNO_SCAN_INTERVAL_SEC during market hours:
  1. manage open positions (stops / target+trail / time stop / 15:10
     hard flat) -- exits are checked BEFORE entries so a stop and a
     same-tick new signal can't double the book
  2. evaluate the FNO-MOM entry on the newest closed 5-min futures bar
     (once per bar per leg -- restart-safe via the bar_ts column)
  3. write EVERY evaluation to the signal log, §9.2

Breadcrumb layers (ops rules 55/56): the main.py wrapper logs
fno_tick_invoked; this module logs fno_orchestrator_tick first-line;
every engine call is wrapped with a distinct log tag.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional
from uuid import uuid4

import pytz
import structlog

import fno_positions as fpos
from config import settings
from fno_chain import ChainSnapshot, select_strike_by_delta, take_chain_snapshot
from fno_costs import calc_fno_costs
from fno_engine_mom import MomSignal, evaluate_fno_mom
from fno_executor import FnoExecutor
from fno_gates import GateContext, evaluate_entry_gates
from fno_instruments import get_fno_instruments
from fno_models import FnoDirection, FnoSource, Leg, OptionType
from fno_risk import (
    kill_switch_status, lots_for_pool, min_viable_pool, validate_position,
)
from fno_signal_log import log_fno_signal

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

RVOL_FETCH_CALENDAR_DAYS = 21   # ~14 sessions of 5-min bars for EMA/RVOL


def _now_min(now_ist: datetime) -> int:
    return now_ist.hour * 60 + now_ist.minute


def _fno_pool_paper() -> float:
    return float(settings.FNO_PAPER_BANKROLL)


def _fno_pool_live() -> float:
    return float(settings.FNO_LIVE_BANKROLL)


async def _fetch_futures_bars(kite, fut_token: int, now_ist: datetime):
    frm = (now_ist - timedelta(days=RVOL_FETCH_CALENDAR_DAYS)).strftime(
        "%Y-%m-%d 09:15:00"
    )
    to = now_ist.strftime("%Y-%m-%d %H:%M:%S")
    return await kite.get_intraday_by_token(fut_token, frm, to, interval="5minute")


# ---------------------------------------------------------------------------
# position management (exits)
# ---------------------------------------------------------------------------

async def _manage_open_positions(
    kite, db_path: str, source: str, executor: FnoExecutor,
    now_ist: datetime, fut_price: Optional[float],
) -> List[dict]:
    """Check every OPEN position for this leg against the §8.4/§8.5 exit
    ladder. Returns records of closed positions."""
    positions = await fpos.open_positions(db_path, source)
    if not positions:
        return []

    # One batched quote for every held contract.
    tokens = [p.token for p in positions if p.token]
    quotes = await kite.get_quote(tokens) if tokens else {}

    hard_flat = _now_min(now_ist) >= settings.FNO_HARD_FLAT_MIN
    closed: List[dict] = []
    for p in positions:
        q = quotes.get(p.token) or {}
        depth = q.get("depth") or {}
        buys = depth.get("buy") or []
        bid = float(buys[0]["price"]) if buys and buys[0].get("price") else 0.0
        ltp = float(q.get("last_price") or 0.0)
        exit_px_basis = bid if bid > 0 else ltp

        exit_reason = ""
        long_view = p.direction == FnoDirection.LONG.value

        if hard_flat:
            exit_reason = "hard_flat_1510"
        elif fut_price is not None and fut_price > 0:
            # progress/trail bookkeeping first
            best = p.best_underlying or p.entry_underlying
            best = max(best, fut_price) if long_view else min(best, fut_price)
            trail_active = bool(p.trail_active)
            trail_stop = p.trail_stop_underlying

            target_hit = (
                fut_price >= p.target_underlying if long_view
                else fut_price <= p.target_underlying
            )
            if target_hit and not trail_active:
                trail_active = True
                logger.info(
                    "fno_trail_armed id=%d symbol=%s fut=%.1f target=%.1f",
                    p.id, p.tradingsymbol, fut_price, p.target_underlying,
                )
            if trail_active:
                dist = settings.FNO_TRAIL_ATR_MULT * (p.atr_at_entry or 0.0)
                new_trail = best - dist if long_view else best + dist
                if trail_stop is None:
                    trail_stop = new_trail
                else:
                    trail_stop = max(trail_stop, new_trail) if long_view else min(trail_stop, new_trail)

            # 1) underlying stop (structural/volatility, tightest at entry)
            stopped = (
                fut_price <= p.stop_underlying if long_view
                else fut_price >= p.stop_underlying
            )
            # 2) trailing stop after target
            trailed = (
                trail_active and trail_stop is not None
                and (fut_price <= trail_stop if long_view else fut_price >= trail_stop)
            )
            # 3) premium backstop -- the one that bounds risk_per_lot (§8.4)
            premium_stopped = exit_px_basis > 0 and exit_px_basis <= p.premium_stop
            # 4) time stop: not +0.5R (underlying points) within 45 min
            timed_out = False
            if not trail_active:
                try:
                    entry_dt = datetime.fromisoformat(p.entry_time)
                    if entry_dt.tzinfo is None:
                        entry_dt = IST.localize(entry_dt)
                    age_min = (now_ist - entry_dt).total_seconds() / 60.0
                except (ValueError, TypeError):
                    # [AUDIT-FIX-PHASE1 2026-07-11] Loud-but-non-blocking.
                    # Silently fall-through to age=0 means the time
                    # stop never fires for the malformed row -- a
                    # position can live forever. Log loudly so the
                    # operator sees the malformed entry_time and can
                    # patch the row directly.
                    logger.warning(
                        "fno_time_stop_age_parse_failed id=%d entry_time=%r "
                        "-- age_min defaulted to 0; time stop DEFEATED for "
                        "this position (operator must patch entry_time "
                        "to force the exit)",
                        p.id, p.entry_time,
                    )
                    age_min = 0.0
                if age_min >= settings.FNO_TIME_STOP_MIN:
                    r_points = abs(p.entry_underlying - p.stop_underlying)
                    progress = (
                        fut_price - p.entry_underlying if long_view
                        else p.entry_underlying - fut_price
                    )
                    if progress < settings.FNO_TIME_STOP_MIN_R * r_points:
                        timed_out = True

            if stopped:
                exit_reason = "underlying_stop"
            elif trailed:
                exit_reason = "trail_stop"
            elif premium_stopped:
                exit_reason = "premium_backstop"
            elif timed_out:
                exit_reason = "time_stop"

            # persist trail state even when not exiting
            if not exit_reason:
                await fpos.update_trail(
                    db_path, p.id, 1 if trail_active else 0, trail_stop, best,
                )
        else:
            # No futures quote this tick: only the premium backstop can
            # still protect us. Chain staleness blocks entries elsewhere.
            if exit_px_basis > 0 and exit_px_basis <= p.premium_stop:
                exit_reason = "premium_backstop"

        if not exit_reason:
            continue

        if exit_px_basis <= 0:
            # [AUDIT-FIX-PHASE1 2026-07-11] Loud-but-non-blocking: a hard
            # flat with no quote would otherwise silently `continue` and
            # leave the position open through the weekend (MIS auto-sq-off
            # at 15:30 is the broker safety net, not a guarantee). On a
            # non-trading-day next-tick the carry is real -> page the
            # operator so they can flatten manually or patch the
            # fno_positions row directly.
            msg = (
                f"⚠️ *F&O hard flat blocked by no quote*\n"
                f"id={p.id} symbol={p.tradingsymbol} reason={exit_reason}\n"
                f"The 15:10 hard flat could not price -- position may "
                f"carry into the next session. Action required: manual "
                f"flatten or UPDATE fno_positions SET status='CLOSED' for "
                f"id={p.id} once broker quotes return."
            )
            try:
                from operator_alert import notify_operator
                await notify_operator(msg, event="fno_hard_flat_no_quote")
            except Exception as notify_exc:
                logger.error(
                    "fno_operator_page_failed id=%d err=%s",
                    p.id, notify_exc,
                )
            logger.critical(
                "fno_exit_no_quote id=%d symbol=%s reason=%s -- cannot price "
                "the exit; position will carry into next session (operator paged)",
                p.id, p.tradingsymbol, exit_reason,
            )
            continue

        result = await executor.execute_exit(
            p.tradingsymbol, p.qty, exit_px_basis,
            tick_size=settings.FNO_TICK_SIZE,
            hard_flat=exit_reason.startswith("hard_flat"),
        )
        if result["status"] not in ("paper", "filled"):
            logger.warning(
                "fno_exit_not_filled id=%d symbol=%s status=%s -- retry next tick",
                p.id, p.tradingsymbol, result["status"],
            )
            continue

        fill = float(result["fill_price"])
        gross = (fill - p.entry_premium) * p.qty
        costs = calc_fno_costs(p.entry_premium, fill, p.qty)
        pnl = gross - costs
        risk_rupees = p.entry_premium * settings.FNO_STOP_PREMIUM_PCT * p.qty
        r_mult = pnl / risk_rupees if risk_rupees > 0 else 0.0
        await fpos.close_position(
            db_path, p.id,
            exit_time_ist=now_ist, exit_premium=fill,
            exit_underlying=fut_price or 0.0, exit_reason=exit_reason,
            gross_pnl=gross, costs=costs, pnl=pnl, r_multiple=r_mult,
            exit_order_id=result.get("order_id"),
        )
        # Pool accounting: additive source tag in the shared ledger (§10.3).
        try:
            from performance import record_trade_close
            await record_trade_close(
                db_path, ticker=p.tradingsymbol, pnl=pnl,
                r_multiple=r_mult, notes=f"fno_exit {exit_reason}",
                source=source,
            )
        except Exception as exc:
            logger.error("fno_ledger_write_failed id=%d err=%s", p.id, str(exc))
        logger.info(
            "fno_position_closed source=%s symbol=%s reason=%s entry=%.2f "
            "exit=%.2f pnl=%.0f r=%.2f",
            source, p.tradingsymbol, exit_reason, p.entry_premium, fill, pnl, r_mult,
        )
        closed.append({
            "symbol": p.tradingsymbol, "reason": exit_reason,
            "entry": p.entry_premium, "exit": fill,
            "pnl": pnl, "r": r_mult, "source": source,
        })
    return closed


# ---------------------------------------------------------------------------
# entry (one leg)
# ---------------------------------------------------------------------------

async def _try_entry_for_leg(
    kite, db_path: str, source: str, pool: float, executor: FnoExecutor,
    sig: MomSignal, snap: ChainSnapshot, regime: str,
    now_ist: datetime, scan_id: str, is_trading_day: bool,
) -> Optional[dict]:
    """Run the §7 gate ladder + §4 constitution + sizing for ONE leg and,
    if everything passes, place the entry. Logs the evaluation either way."""
    instruments = get_fno_instruments()
    today_iso = now_ist.date().isoformat()

    async def _log(accepted: bool, reason: str, **extra):
        await log_fno_signal(
            db_path, scan_id=scan_id, leg=source, accepted=accepted,
            reject_reason=reason, bar_ts=sig.bar_ts,
            underlying=settings.FNO_UNDERLYING,
            direction=sig.direction.value if sig.direction else None,
            regime=regime, fut_price=snap.forward,
            or_high=sig.or_high, or_low=sig.or_low, atr=sig.atr,
            rvol=sig.rvol, ema_fast=sig.ema_fast, ema_slow=sig.ema_slow,
            **extra,
        )

    # Strike selection (§8.3): |delta| closest to 0.55, ATM-or-ITM only.
    opt_type = OptionType.CE if sig.direction == FnoDirection.LONG else OptionType.PE
    picked = select_strike_by_delta(snap, opt_type, now_ist)
    if picked is None:
        await _log(False, "no_strike_solves_delta")
        return None
    quote, iv, delta_val = picked
    contract = quote.contract
    ask = quote.ask
    lot_size = snap.lot_size or contract.lot_size

    quote_age = (
        (now_ist - quote.last_trade_time).total_seconds()
        if quote.last_trade_time else float("inf")
    )
    open_prem = await fpos.open_premium_committed(db_path, source)
    n_open = len(await fpos.open_positions(db_path, source))
    n_today = await fpos.trades_today(db_path, source, today_iso)
    switches = await kill_switch_status(db_path, source, pool, now_ist.date())
    if switches:
        # Rule 72: a halted leg is a WARNING, never an INFO.
        logger.warning("fno_kill_switch_active source=%s switches=%s", source, switches)

    ctx = GateContext(
        now_min=_now_min(now_ist),
        is_trading_day=is_trading_day,
        is_expiry_day=instruments.is_expiry_day(now_ist.date()),
        regime=regime,
        oi=quote.oi, volume=quote.volume,
        bid=quote.bid, ask=quote.ask, ltp=quote.ltp,
        quote_age_sec=quote_age,
        forward=snap.forward, strike=contract.strike,
        is_call=(opt_type == OptionType.CE), iv=iv,
        pool=pool, premium=ask, lot_size=lot_size,
        open_premium=open_prem, open_positions=n_open, trades_today=n_today,
        active_kill_switches=switches,
        chain_age_sec=snap.age_sec(now_ist),
    )
    contract_fields = dict(
        tradingsymbol=contract.tradingsymbol, strike=contract.strike,
        opt_type=opt_type.value, expiry=contract.expiry.isoformat(),
        premium=ask, iv=iv, delta=delta_val, spread_pct=quote.spread_pct,
        oi=quote.oi, volume=quote.volume,
        min_pool_required=min_viable_pool(
            ask, lot_size, settings.FNO_STOP_PREMIUM_PCT, settings.FNO_MAX_RISK_PCT,
        ),
    )

    ok, reject = evaluate_entry_gates(ctx)
    if not ok:
        await _log(False, reject, **contract_fields)
        return None

    # Sizing (§3): decline rather than oversize.
    lots = lots_for_pool(
        pool, ask, lot_size,
        settings.FNO_STOP_PREMIUM_PCT, settings.FNO_MAX_RISK_PCT,
        settings.FNO_MAX_LOTS,
    )
    # Respect the open-premium cap on the marginal lot too.
    while lots > 0 and open_prem + lots * ask * lot_size > settings.FNO_MAX_OPEN_PREMIUM_PCT * pool:
        lots -= 1
    if lots < 1:
        await _log(False, "pool_below_min_viable", **contract_fields, lots=0)
        return None

    # §4 constitution -- the order path runs through validate_position.
    legs = [Leg(opt_type=opt_type, strike=contract.strike, quantity=lots, premium=ask)]
    ok_ml, reject_ml, ml = validate_position(legs, lot_size)
    if not ok_ml:
        await _log(False, reject_ml, **contract_fields, lots=lots, max_loss_rupees=ml)
        return None

    qty = lots * lot_size
    result = await executor.execute_entry(contract.tradingsymbol, qty, ask)
    if result["status"] not in ("paper", "filled"):
        await _log(False, f"entry_{result['status']}", **contract_fields, lots=lots)
        return None
    fill = float(result["fill_price"])

    premium_stop = round((1.0 - settings.FNO_STOP_PREMIUM_PCT) * fill, 2)
    await fpos.insert_position(
        db_path,
        source=source,
        tradingsymbol=contract.tradingsymbol,
        token=contract.token,
        underlying=settings.FNO_UNDERLYING,
        expiry=contract.expiry.isoformat(),
        strike=contract.strike,
        opt_type=opt_type.value,
        direction=sig.direction.value,
        lots=lots, lot_size=lot_size, qty=qty,
        entry_time=now_ist.isoformat(),
        entry_date=today_iso,
        entry_premium=fill,
        entry_underlying=snap.forward,
        delta_at_entry=delta_val, iv_at_entry=iv, atr_at_entry=sig.atr,
        stop_underlying=sig.stop_underlying,
        target_underlying=sig.target_underlying,
        premium_stop=premium_stop,
        trail_active=0, trail_stop_underlying=None,
        best_underlying=snap.forward,
        max_loss_rupees=ml,
        status="OPEN",
        entry_order_id=result.get("order_id"),
        bar_ts=sig.bar_ts,
    )
    await _log(True, "", **contract_fields, lots=lots, max_loss_rupees=ml)
    logger.info(
        "fno_entry_submitted source=%s symbol=%s dir=%s lots=%d fill=%.2f "
        "delta=%.2f iv=%.2f stop_u=%.1f target_u=%.1f prem_stop=%.2f max_loss=%.0f",
        source, contract.tradingsymbol, sig.direction.value, lots, fill,
        delta_val, iv, sig.stop_underlying, sig.target_underlying,
        premium_stop, ml,
    )
    return {
        "symbol": contract.tradingsymbol, "direction": sig.direction.value,
        "lots": lots, "fill": fill, "delta": round(delta_val, 2),
        "iv": round(iv, 3), "source": source,
    }


# ---------------------------------------------------------------------------
# the tick
# ---------------------------------------------------------------------------

async def run_fno_tick(
    kite, db_path: Optional[str] = None,
    regime: str = "UNKNOWN",
    is_trading_day: bool = True,
    now_ist: Optional[datetime] = None,
) -> dict:
    """One scan tick. Called by the main.py cron wrapper (which owns the
    calendar gate + no-token guard + Telegram delivery)."""
    db_path = db_path or settings.DB_PATH
    now_ist = now_ist or datetime.now(IST)
    scan_id = f"FNO-{now_ist.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
    summary: dict = {"scan_id": scan_id, "entries": [], "exits": [], "note": ""}

    # Rule 56: first-line orchestrator breadcrumb.
    logger.info(
        "fno_orchestrator_tick scan_id=%s now_ist=%s regime=%s",
        scan_id, now_ist.strftime("%H:%M:%S"), regime,
    )

    instruments = get_fno_instruments()
    if not instruments.ready(now_ist.date()):
        # Try disk rehydrate once per tick; the 08:00 cron owns refresh.
        if not instruments.load_from_disk():
            logger.warning(
                "fno_tick_skip reason=instruments_not_ready "
                "FIX=wait for 08:00 refresh or check kite auth"
            )
            summary["note"] = "instruments_not_ready"
            return summary

    fut = instruments.front_future(now_ist.date())
    if fut is None:
        logger.warning("fno_tick_skip reason=no_front_future")
        summary["note"] = "no_front_future"
        return summary

    paper_exec = FnoExecutor(kite, paper_mode=True, source_tag=FnoSource.FNO_PAPER.value)
    # Live leg is paper-forced unless every arming condition holds; in P1
    # FNO_DISABLE_LIVE=True short-circuits it entirely below.
    live_master = bool(settings.FNO_LIVE_TRADING)
    live_exec = FnoExecutor(
        kite, paper_mode=not live_master, source_tag=FnoSource.FNO_LIVE.value,
    )

    # ---- futures price for exit management ---------------------------
    fut_quote = await kite.get_quote([fut.token])
    fut_price = None
    fq = fut_quote.get(fut.token)
    if fq and fq.get("last_price"):
        fut_price = float(fq["last_price"])

    # ---- 1) exits first ----------------------------------------------
    try:
        if not settings.FNO_DISABLE_PAPER:
            summary["exits"] += await _manage_open_positions(
                kite, db_path, FnoSource.FNO_PAPER.value, paper_exec, now_ist, fut_price,
            )
        if not settings.FNO_DISABLE_LIVE:
            summary["exits"] += await _manage_open_positions(
                kite, db_path, FnoSource.FNO_LIVE.value, live_exec, now_ist, fut_price,
            )
    except Exception as exc:
        logger.error("fno_exit_management_failed err=%s", str(exc), exc_info=True)

    # ---- 1b) defined-risk paper book (Phase 2) -----------------------
    # Rides this same tick: manage any open structure to current mids, then
    # (if flat + in-window) open one -- a debit spread on a directional signal,
    # an iron condor on a rich-IV range day (which the single-leg engine's
    # no-signal early-return below would never reach). Fully self-contained and
    # guarded: nothing here can disturb the single-leg engine above or below.
    if not settings.FNO_DISABLE_PAPER:
        try:
            import fno_dr_book as _dr
            await _dr.init_dr_db(db_path)
            open_dr = await _dr.open_structures(db_path)
            nm_dr = _now_min(now_ist)
            in_dr_window = _dr._entry_lo_min() <= nm_dr <= _dr._entry_hi_min()
            if open_dr or in_dr_window:
                dr_snap = await take_chain_snapshot(kite, instruments, now_ist)
                if open_dr:
                    summary["exits"] += await _dr.manage_dr_structures(db_path, dr_snap, now_ist)
                if in_dr_window and not await _dr.open_structures(db_path):
                    try:
                        dr_bars = await _fetch_futures_bars(kite, fut.token, now_ist)
                        dr_sig = evaluate_fno_mom(dr_bars, regime, now_ist)
                        opened = await _dr.maybe_open_dr_structure(
                            db_path, dr_snap, dr_sig.direction is not None,
                            dr_sig.direction, now_ist,
                        )
                        if opened:
                            summary.setdefault("dr_opened", []).append(opened)
                    except Exception as exc:
                        logger.error("fno_dr_entry_failed err=%s", str(exc))
        except Exception as exc:
            logger.error("fno_dr_block_failed err=%s", str(exc), exc_info=True)

    # ---- 2) entries ----------------------------------------------------
    nm = _now_min(now_ist)
    if not (settings.FNO_ENTRY_START_MIN <= nm < settings.FNO_ENTRY_END_MIN):
        summary["note"] = "outside_entry_window"
        return summary

    try:
        bars = await _fetch_futures_bars(kite, fut.token, now_ist)
    except Exception as exc:
        logger.error("fno_futures_bars_failed err=%s", str(exc))
        summary["note"] = "futures_bars_failed"
        return summary

    sig = evaluate_fno_mom(bars, regime, now_ist)
    if not sig.bar_ts:
        summary["note"] = f"engine:{sig.reject_reason}"
        return summary

    # One evaluation per closed bar per leg (restart-safe): if this leg
    # already recorded an entry for the bar, or the engine says no signal,
    # log at most one no-signal row per bar.
    if sig.direction is None:
        # Only log the no-signal outcome once per bar (the tick fires
        # every 60s; a 5-min bar would otherwise produce 5 duplicates).
        if not await _bar_already_logged(db_path, sig.bar_ts):
            await log_fno_signal(
                db_path, scan_id=scan_id, leg="ENGINE", accepted=False,
                reject_reason=sig.reject_reason, bar_ts=sig.bar_ts,
                underlying=settings.FNO_UNDERLYING, regime=regime,
                fut_price=sig.close, or_high=sig.or_high, or_low=sig.or_low,
                atr=sig.atr, rvol=sig.rvol,
                ema_fast=sig.ema_fast, ema_slow=sig.ema_slow,
            )
        summary["note"] = f"no_signal:{sig.reject_reason}"
        return summary

    # Signal fired: snapshot the chain once, then run both legs off it.
    snap = await take_chain_snapshot(kite, instruments, now_ist)
    if snap is None:
        await log_fno_signal(
            db_path, scan_id=scan_id, leg="ENGINE", accepted=False,
            reject_reason="chain_unavailable", bar_ts=sig.bar_ts,
            underlying=settings.FNO_UNDERLYING,
            direction=sig.direction.value, regime=regime,
        )
        summary["note"] = "chain_unavailable"
        return summary

    if not settings.FNO_DISABLE_PAPER:
        if await fpos.already_entered_bar(db_path, FnoSource.FNO_PAPER.value, sig.bar_ts):
            logger.info("fno_entry_skip source=FNO_PAPER reason=bar_already_entered")
        else:
            try:
                entry = await _try_entry_for_leg(
                    kite, db_path, FnoSource.FNO_PAPER.value, _fno_pool_paper(),
                    paper_exec, sig, snap, regime, now_ist, scan_id, is_trading_day,
                )
                if entry:
                    summary["entries"].append(entry)
            except Exception as exc:
                logger.error("fno_paper_entry_failed err=%s", str(exc), exc_info=True)

    if not settings.FNO_DISABLE_LIVE:
        # The live leg refuses to arm unless the go-live function returns
        # clean (spec §11) -- and it runs paper-forced unless the master
        # switch is on.
        from fno_risk import fno_go_live_check
        unmet = await fno_go_live_check(db_path)
        if unmet:
            logger.warning("fno_live_leg_refused_to_arm unmet=%s", unmet)
        elif await fpos.already_entered_bar(db_path, FnoSource.FNO_LIVE.value, sig.bar_ts):
            logger.info("fno_entry_skip source=FNO_LIVE reason=bar_already_entered")
        else:
            try:
                entry = await _try_entry_for_leg(
                    kite, db_path, FnoSource.FNO_LIVE.value, _fno_pool_live(),
                    live_exec, sig, snap, regime, now_ist, scan_id, is_trading_day,
                )
                if entry:
                    summary["entries"].append(entry)
            except Exception as exc:
                logger.error("fno_live_entry_failed err=%s", str(exc), exc_info=True)

    return summary


async def _bar_already_logged(db_path: str, bar_ts: str) -> bool:
    import aiosqlite
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fno_signals'"
            ) as cur:
                if await cur.fetchone() is None:
                    return False
            async with db.execute(
                "SELECT 1 FROM fno_signals WHERE bar_ts=? LIMIT 1", (bar_ts,),
            ) as cur:
                return (await cur.fetchone()) is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Telegram formatting (delivery owned by main.py, like penny edge)
# ---------------------------------------------------------------------------

def format_fno_telegram(summary: dict) -> str:
    out = [f"*F&O tick* `{summary.get('scan_id', '?')}`"]
    for e in summary.get("entries", []):
        out.append(
            f"ENTRY [{e['source']}] `{e['symbol']}` {e['direction']} "
            f"lots={e['lots']} @ {e['fill']:.2f} delta={e['delta']} iv={e['iv']}"
        )
    for x in summary.get("exits", []):
        out.append(
            f"EXIT [{x['source']}] `{x['symbol']}` {x['reason']} "
            f"{x['entry']:.2f} -> {x['exit']:.2f} pnl=Rs {x['pnl']:,.0f} ({x['r']:+.2f}R)"
        )
    if len(out) == 1:
        out.append("No activity.")
    return "\n".join(out)
