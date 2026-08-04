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
    """Static allocation. Prefer `_fno_equity()` -- it adds realised P&L."""
    return float(settings.FNO_PAPER_BANKROLL)


def _fno_pool_live() -> float:
    """Static allocation. Prefer `_fno_equity()` -- it adds realised P&L."""
    return float(settings.FNO_LIVE_BANKROLL)


# A book that has surrendered this share of its pool stops trading. The
# directional F&O leg ran 2W/10L to -15,474 without anything noticing,
# because sizing read a constant and the ledger was posting the damage
# against an unrelated pool.
FNO_MAX_DRAWDOWN_PCT = 0.25


async def _fno_equity(db_path: str, source: str) -> float:
    """[POOL-TRUTH 2026-07-31] Live F&O equity: allocation + realised P&L."""
    from performance import division_equity
    return await division_equity(db_path, source)


def _fno_halted(equity: float, allocation: float, source: str) -> bool:
    """True when a leg has drawn down past its limit or gone non-positive."""
    if allocation <= 0:
        return False
    if equity <= 0:
        logger.critical(
            "fno_leg_halted source=%s equity=%.2f -- NON-POSITIVE equity",
            source, equity,
        )
        return True
    if equity < allocation * (1.0 - FNO_MAX_DRAWDOWN_PCT):
        logger.critical(
            "fno_leg_halted source=%s equity=%.2f allocation=%.2f "
            "drawdown=%.1f%% limit=%.0f%%",
            source, equity, allocation,
            (1 - equity / allocation) * 100, FNO_MAX_DRAWDOWN_PCT * 100,
        )
        return True
    return False


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

                    # [TIME-STOP-PREMIUM 2026-08-04] Do not cut a position that
                    # is making money.
                    #
                    # The clause above measures progress in UNDERLYING points
                    # while the P&L is in PREMIUM, and on a near-ATM long the
                    # two are separated by delta. Requiring 0.5R of underlying
                    # movement on a 31-point R means ~16 index points, which on
                    # a 0.49-delta contract is ~8 premium points -- a quarter of
                    # a 30-rupee option. So a contract could be up 15% and still
                    # read as "gone nowhere".
                    #
                    # That is not hypothetical. The time stop is the single
                    # biggest loser in this book (8 exits, -7,010) and two of
                    # those eight were CUT WHILE PROFITABLE: 2026-07-23 at
                    # +286 and 2026-08-03 at +530. Meanwhile trail_stop is the
                    # only exit reason with positive expectancy in the book's
                    # entire history (2 exits, +2,869, avg +0.62R) -- and a
                    # trade can only reach the trail by surviving long enough
                    # to get there.
                    #
                    # So the clock now only cuts trades that are BOTH going
                    # nowhere on the underlying AND not in profit on premium.
                    # A losing position is still cut on schedule; the whole
                    # point of the time stop is preserved.
                    if timed_out and settings.FNO_TIME_STOP_RESPECTS_PREMIUM:
                        premium_pnl_per_lot = (exit_px_basis - p.entry_premium)
                        if p.direction == "SHORT":
                            premium_pnl_per_lot = -premium_pnl_per_lot
                        if exit_px_basis > 0 and premium_pnl_per_lot > 0:
                            timed_out = False
                            logger.info(
                                "fno_time_stop_deferred_in_profit id=%d age=%.0f "
                                "underlying_progress=%.1f needed=%.1f "
                                "premium_pnl_per_unit=%.2f",
                                p.id, age_min, progress,
                                settings.FNO_TIME_STOP_MIN_R * r_points,
                                premium_pnl_per_lot,
                            )

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
        # [POOL-AUDIT 2026-08-04] Log the pool the gate was actually evaluated
        # against, not just the threshold it had to clear.
        #
        # Without this the row is unfalsifiable. The 2026-08-03 audit read
        # min_pool_required=24,821 next to a bankroll_ledger showing FNO_PAPER
        # at -10,329 and concluded the gate had been bypassed. It had not: the
        # ledger column omitted the division's allocation, while sizing used
        # the full 250,000 pool. The two numbers were describing different
        # things and nothing in the signal row said which one the gate saw.
        pool_at_eval=round(float(pool), 2),
    )

    ok, reject = evaluate_entry_gates(ctx)
    if not ok:
        await _log(False, reject, **contract_fields)
        return None

    # [NO-PYRAMID 2026-07-26] Refuse a second position on a contract this leg is
    # already holding. The existing caps are count-based (FNO_MAX_CONCURRENT) and
    # premium-based (FNO_MAX_OPEN_PREMIUM_PCT), and already_entered_bar() only
    # blocks a repeat within the SAME 5-min bar -- so nothing stopped the book
    # from re-entering the identical strike on a later bar.
    #
    # 2026-07-24 is what that looks like: FNO_PAPER opened NIFTY26JUL23700PE at
    # 10:05 (1 lot, -Rs 1,280), again at 10:35 (1 lot, -Rs 1,926), then again at
    # 11:00 with 2 lots while the 10:35 leg was still open and already losing
    # (-Rs 2,512). ~Rs 30k of premium concentrated on one strike, and the third
    # entry was averaging into a loser the ORB signal had already been wrong
    # about twice. Same-day re-entry on a DIFFERENT strike stays allowed.
    held = [p for p in await fpos.open_positions(db_path, source)
            if p.tradingsymbol == contract.tradingsymbol]
    if held:
        await _log(False, "already_holding_this_contract", **contract_fields)
        logger.info(
            "fno_entry_skip source=%s reason=already_holding_this_contract symbol=%s open_lots=%d",
            source, contract.tradingsymbol, sum(p.lots for p in held),
        )
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

    # [NAKED-LEG-EXPECTANCY 2026-07-31] A long option is only a trade if its
    # payoff at target beats its loss at stop AFTER the spread. Measured on the
    # premium, this book's geometry was upside down and its record says so:
    # 12 naked legs, 2 winners, -Rs 15,474 since 2026-07-16. The defined-risk
    # spreads over the same period ran ~flat on a 1.7:1 structure.
    #
    # Two things invert it. First the premium backstop: risk is
    # min(delta-implied loss at the underlying stop, FNO_STOP_PREMIUM_PCT of
    # premium), so a -25% backstop can cap the loss BELOW the stop distance --
    # which sounds protective but means the position is stopped by decay rather
    # than by the thesis being wrong. Second the spread, paid twice, on an
    # instrument whose whole edge is a fraction of one underlying point.
    #
    # 2026-07-30 is the worked example: risk ~Rs 3,503 against a reward of
    # ~Rs 2,717 -- 0.78:1 before costs, i.e. negative expectancy at ANY win
    # rate below 56%, on a book running 17%. This gate refuses that trade.
    # It does not touch the defined-risk book, which trades earlier in the tick.
    entry_u = float(snap.forward)
    stop_pts = abs(entry_u - float(sig.stop_underlying))
    target_pts = abs(float(sig.target_underlying) - entry_u)
    abs_delta = abs(float(delta_val)) or 0.0
    # Premium moves ~delta per underlying point over a short intraday hold.
    reward_rs = abs_delta * target_pts * (lots * lot_size)
    risk_prem_pts = min(abs_delta * stop_pts, ask * settings.FNO_STOP_PREMIUM_PCT)
    risk_rs = risk_prem_pts * (lots * lot_size)
    # Round-trip spread, paid on entry and exit.
    spread_rs = (quote.spread_pct or 0.0) * ask * (lots * lot_size)
    net_reward = reward_rs - spread_rs
    net_risk = risk_rs + spread_rs
    rr = (net_reward / net_risk) if net_risk > 0 else 0.0
    if rr < settings.FNO_MIN_REWARD_RISK:
        await _log(
            False, "reward_risk_below_min", **contract_fields,
            lots=lots, max_loss_rupees=ml,
        )
        logger.info(
            "fno_entry_skip source=%s reason=reward_risk_below_min symbol=%s "
            "rr=%.2f min=%.2f reward=%.0f risk=%.0f spread=%.0f "
            "stop_pts=%.1f target_pts=%.1f delta=%.2f",
            source, contract.tradingsymbol, rr, settings.FNO_MIN_REWARD_RISK,
            net_reward, net_risk, spread_rs, stop_pts, target_pts, abs_delta,
        )
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
    if not settings.FNO_DISABLE_PAPER and not settings.FNO_DR_DISABLE_PAPER:
        try:
            import fno_dr_book as _dr
            await _dr.init_dr_db(db_path)
            open_dr = await _dr.open_structures(db_path)
            nm_dr = _now_min(now_ist)
            in_dr_window = _dr._entry_lo_min() <= nm_dr <= _dr._entry_hi_min()
            if open_dr or in_dr_window:
                dr_snap = await take_chain_snapshot(kite, instruments, now_ist)
                if open_dr:
                    # manage_dr_structures returns a COUNT (int), while
                    # summary["exits"] is a list of single-leg exit *records*
                    # consumed key-by-key in format_fno_telegram. Keep the DR
                    # tally in its own key (mirrors "dr_opened" below) so the
                    # two shapes never collide -- the DR closes are detailed in
                    # their own fno_dr_closed log lines.
                    summary["dr_exits"] = summary.get("dr_exits", 0) + \
                        await _dr.manage_dr_structures(db_path, dr_snap, now_ist)
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
        paper_equity = await _fno_equity(db_path, FnoSource.FNO_PAPER.value)
        if _fno_halted(paper_equity, _fno_pool_paper(), FnoSource.FNO_PAPER.value):
            logger.info("fno_entry_skip source=FNO_PAPER reason=drawdown_halt")
        elif await fpos.already_entered_bar(db_path, FnoSource.FNO_PAPER.value, sig.bar_ts):
            logger.info("fno_entry_skip source=FNO_PAPER reason=bar_already_entered")
        else:
            try:
                entry = await _try_entry_for_leg(
                    kite, db_path, FnoSource.FNO_PAPER.value, paper_equity,
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
        live_equity = await _fno_equity(db_path, FnoSource.FNO_LIVE.value)
        if unmet:
            logger.warning("fno_live_leg_refused_to_arm unmet=%s", unmet)
        elif _fno_halted(live_equity, _fno_pool_live(), FnoSource.FNO_LIVE.value):
            logger.info("fno_entry_skip source=FNO_LIVE reason=drawdown_halt")
        elif await fpos.already_entered_bar(db_path, FnoSource.FNO_LIVE.value, sig.bar_ts):
            logger.info("fno_entry_skip source=FNO_LIVE reason=bar_already_entered")
        else:
            try:
                entry = await _try_entry_for_leg(
                    kite, db_path, FnoSource.FNO_LIVE.value, live_equity,
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
    """[PAPER-MARKING 2026-08-04] Every rupee figure here is tagged paper or
    live via performance.fmt_money.

    This book has never held real capital, yet its exits rendered exactly like
    the live momentum book's: on 2026-08-03 it reported `pnl=Rs -730` beside a
    genuine live loss of Rs 8.41 the same day. Two numbers 87x apart,
    identically formatted, distinguished only by a bracketed source tag in the
    middle of the line.
    """
    from performance import fmt_money, is_paper_source

    out = [f"*F&O tick* `{summary.get('scan_id', '?')}`"]
    for e in summary.get("entries", []):
        tag = " (paper)" if is_paper_source(e["source"]) else ""
        out.append(
            f"ENTRY [{e['source']}]{tag} `{e['symbol']}` {e['direction']} "
            f"lots={e['lots']} @ {e['fill']:.2f} delta={e['delta']} iv={e['iv']}"
        )
    for x in summary.get("exits", []):
        out.append(
            f"EXIT [{x['source']}] `{x['symbol']}` {x['reason']} "
            f"{x['entry']:.2f} -> {x['exit']:.2f} "
            f"pnl={fmt_money(x['pnl'], x['source'])} ({x['r']:+.2f}R)"
        )
    if len(out) == 1:
        out.append("No activity.")
    return "\n".join(out)
