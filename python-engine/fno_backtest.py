"""
[ROADMAP-3.11 2026-07-12] F&O momentum backtest -- the module's first
historical validation.

REUSED VERBATIM from the live stack (the penny-edge pattern: shared
code between live and backtest is what makes a backtest trustworthy):
  - fno_engine_mom.evaluate_fno_mom  -- the entry signal, bar by bar
  - fno_gates.evaluate_entry_gates   -- the §7 ladder (see caveats)
  - fno_risk.lots_for_pool / validate_position -- sizing + constitution
  - fno_costs.calc_fno_costs         -- the real cost model, no bypass
  - options_math.black76_price/delta -- the module's own pricer
  - the orchestrator's exit ladder ORDER: hard-flat -> underlying stop
    -> trail stop -> premium backstop -> time stop

MODEL SUBSTITUTIONS (read before believing any number):
  1. THE OPTION LEG IS SYNTHETIC. Kite does not serve historical option
     chains, so premiums are Black-76 at a CONSTANT IV (FNO_BT_IV) with
     a symmetric spread (FNO_BT_SPREAD_PCT): buy at mid*(1+s/2), sell
     at mid*(1-s/2). Theta decay and delta/gamma are therefore modelled
     honestly, but IV CHANGES ARE NOT -- a real crisis entry rides IV
     up, a real quiet drift bleeds IV down. Sweep FNO_BT_IV to bound
     the sensitivity.
  2. Microstructure gates (min_oi / min_volume / quote & chain
     freshness) cannot be replayed against model quotes -- they are
     fed structurally-passing values. The max_spread / intrinsic_floor
     / quote_envelope / iv_sanity gates DO run on the model numbers.
     Session-window, expiry-day, regime, pool arithmetic, open-premium
     cap, concurrency, trades/day and kill switches replay for real.
  3. 5-MIN BAR GRANULARITY. The live loop manages exits on 60s ticks;
     here exits are evaluated per closed 5-min bar with the 3.3
     discipline: a gap through the underlying stop fills from the bar
     OPEN, stop-before-target when both are touched inside one bar,
     trail progress tracked on bar CLOSES (conservative), and the
     premium backstop is checked at the bar's WORST underlying print.
  4. Expiry is synthetic: next FNO_BT_EXPIRY_WEEKDAY on/after the bar
     date (matches NIFTY weeklies; VERIFY-3 -- the weekday has changed
     historically, confirm for long runs).

Usage:
    # from a CSV of 5-min futures bars (datetime,open,high,low,close,volume)
    python fno_backtest.py --csv bars.csv [--iv 0.12] [--pool 250000]

    # or programmatically
    from fno_backtest import run_fno_backtest
    result = run_fno_backtest(bars_df)

Pure pandas in, dict out. No Kite, no DB, no I/O beyond the CLI.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from typing import List, Optional

import pandas as pd
import structlog

import options_math
import pytz
from config import settings
from fno_chain import RISK_FREE_RATE, years_to_expiry
from fno_costs import calc_fno_costs
from fno_engine_mom import MomSignal, evaluate_fno_mom
from fno_gates import GateContext, evaluate_entry_gates
from fno_models import FnoDirection, Leg, OptionType
from fno_risk import lots_for_pool, validate_position

logger = structlog.get_logger()

IST = pytz.timezone("Asia/Kolkata")


def _years_to_expiry(expiry: date, now: datetime) -> float:
    """fno_chain.years_to_expiry with naive-IST bar timestamps admitted
    (the frame is naive IST by the evaluate_fno_mom contract)."""
    if now.tzinfo is None:
        now = IST.localize(now)
    return years_to_expiry(expiry, now)


# ---------------------------------------------------------------------------
# synthetic option leg
# ---------------------------------------------------------------------------

def _next_expiry(d: date) -> date:
    """Next weekly expiry ON or AFTER d (synthetic, FNO_BT_EXPIRY_WEEKDAY)."""
    ahead = (settings.FNO_BT_EXPIRY_WEEKDAY - d.weekday()) % 7
    return d + timedelta(days=ahead)


def _model_mid(F: float, K: float, expiry: date, now: datetime,
               is_call: bool, iv: float) -> float:
    T = _years_to_expiry(expiry, now)
    return options_math.black76_price(F, K, T, iv, RISK_FREE_RATE, is_call)


def _select_strike(F: float, expiry: date, now: datetime,
                   is_call: bool, iv: float) -> Optional[float]:
    """Mirror fno_chain.select_strike_by_delta on the synthetic ladder:
    |delta| closest to FNO_TARGET_DELTA, ATM-or-ITM only."""
    step = settings.FNO_BT_STRIKE_STEP
    atm = round(F / step) * step
    T = _years_to_expiry(expiry, now)
    best, best_dist = None, float("inf")
    for i in range(0, 12):
        K = atm - i * step if is_call else atm + i * step
        if K <= 0:
            continue
        # Same ATM-or-ITM tolerance as the live selector.
        if is_call and K > F * 1.001:
            continue
        if not is_call and K < F * 0.999:
            continue
        d = options_math.delta(F, K, T, iv, RISK_FREE_RATE, is_call)
        dist = abs(abs(d) - settings.FNO_TARGET_DELTA)
        if dist < best_dist:
            best, best_dist = K, dist
    return best


# ---------------------------------------------------------------------------
# simulated position
# ---------------------------------------------------------------------------

@dataclass
class _SimPosition:
    direction: str
    strike: float
    expiry: date
    is_call: bool
    entry_time: datetime
    entry_date: date
    entry_underlying: float
    entry_premium: float          # ask fill
    lots: int
    qty: int
    stop_underlying: float
    target_underlying: float
    premium_stop: float
    atr_at_entry: float
    iv: float
    trail_active: bool = False
    trail_stop: Optional[float] = None
    best_underlying: float = 0.0


def _bid(mid: float) -> float:
    return mid * (1.0 - settings.FNO_BT_SPREAD_PCT / 2.0)


def _ask(mid: float) -> float:
    return mid * (1.0 + settings.FNO_BT_SPREAD_PCT / 2.0)


def _close_trade(pos: _SimPosition, exit_time: datetime, exit_underlying: float,
                 reason: str) -> dict:
    """Price the exit at the model bid and settle with real costs --
    the same P&L arithmetic as fno_orchestrator._manage_open_positions."""
    mid = _model_mid(exit_underlying, pos.strike, pos.expiry, exit_time,
                     pos.is_call, pos.iv)
    fill = max(0.0, _bid(mid))
    gross = (fill - pos.entry_premium) * pos.qty
    costs = calc_fno_costs(pos.entry_premium, fill, pos.qty)
    pnl = gross - costs
    risk_rupees = pos.entry_premium * settings.FNO_STOP_PREMIUM_PCT * pos.qty
    return {
        "entry_date": pos.entry_date.isoformat(),
        "entry_time": pos.entry_time.strftime("%Y-%m-%d %H:%M"),
        "exit_time": exit_time.strftime("%Y-%m-%d %H:%M"),
        "direction": pos.direction,
        "strike": pos.strike,
        "expiry": pos.expiry.isoformat(),
        "lots": pos.lots,
        "entry_premium": round(pos.entry_premium, 2),
        "exit_premium": round(fill, 2),
        "entry_underlying": pos.entry_underlying,
        "exit_underlying": exit_underlying,
        "exit_reason": reason,
        "gross_pnl": round(gross, 2),
        "costs": round(costs, 2),
        "pnl": round(pnl, 2),
        "r_multiple": round(pnl / risk_rupees, 3) if risk_rupees > 0 else 0.0,
    }


def _manage_position_on_bar(pos: _SimPosition, bar_start: datetime,
                            bar) -> Optional[dict]:
    """One closed 5-min bar against the live exit ladder, in the
    orchestrator's order. Returns a trade record when an exit fires."""
    bar_end = bar_start + timedelta(minutes=5)
    o, h, l, c = (float(bar["open"]), float(bar["high"]),
                  float(bar["low"]), float(bar["close"]))
    long_view = pos.direction == FnoDirection.LONG.value

    # 0) 15:10 hard flat -- unconditional, checked first (live order).
    if bar_start.hour * 60 + bar_start.minute >= settings.FNO_HARD_FLAT_MIN:
        return _close_trade(pos, bar_start, o, "hard_flat_1510")

    # 1) underlying stop. Gap discipline (ROADMAP-3.3): if the bar OPENED
    # through the stop, the exit basis is the open, not the stop.
    if long_view and l <= pos.stop_underlying:
        return _close_trade(pos, bar_end, min(pos.stop_underlying, o),
                            "underlying_stop")
    if not long_view and h >= pos.stop_underlying:
        return _close_trade(pos, bar_end, max(pos.stop_underlying, o),
                            "underlying_stop")

    # 2) trail stop. Chronology at bar granularity: the trail level a
    # bar can hit is the one set by PRIOR bars -- arming/ratcheting
    # happens on the CLOSE (the bar's last print), so checking this
    # bar's low against a trail derived from its own close would let
    # information travel backwards in time. Order: check hit against
    # the existing trail, THEN arm/ratchet from this bar's close.
    dist = settings.FNO_TRAIL_ATR_MULT * pos.atr_at_entry
    if pos.trail_active and pos.trail_stop is not None:
        trailed = l <= pos.trail_stop if long_view else h >= pos.trail_stop
        if trailed:
            basis = (
                min(pos.trail_stop, o) if long_view else max(pos.trail_stop, o)
            )
            return _close_trade(pos, bar_end, basis, "trail_stop")
    target_hit = c >= pos.target_underlying if long_view else c <= pos.target_underlying
    if target_hit and not pos.trail_active:
        pos.trail_active = True
        pos.best_underlying = c
    if pos.trail_active:
        pos.best_underlying = (
            max(pos.best_underlying, c) if long_view else min(pos.best_underlying, c)
        )
        new_trail = (
            pos.best_underlying - dist if long_view else pos.best_underlying + dist
        )
        pos.trail_stop = (
            new_trail if pos.trail_stop is None
            else (max(pos.trail_stop, new_trail) if long_view
                  else min(pos.trail_stop, new_trail))
        )

    # 3) premium backstop at the bar's WORST underlying print.
    worst_u = l if long_view else h
    worst_mid = _model_mid(worst_u, pos.strike, pos.expiry, bar_end,
                           pos.is_call, pos.iv)
    if _bid(worst_mid) <= pos.premium_stop:
        return _close_trade(pos, bar_end, worst_u, "premium_backstop")

    # 4) time stop: not +FNO_TIME_STOP_MIN_R progress within the window.
    if not pos.trail_active:
        age_min = (bar_end - pos.entry_time).total_seconds() / 60.0
        if age_min >= settings.FNO_TIME_STOP_MIN:
            r_points = abs(pos.entry_underlying - pos.stop_underlying)
            progress = (
                c - pos.entry_underlying if long_view
                else pos.entry_underlying - c
            )
            if progress < settings.FNO_TIME_STOP_MIN_R * r_points:
                return _close_trade(pos, bar_end, c, "time_stop")
    return None


# ---------------------------------------------------------------------------
# kill switches (pure replay of fno_risk.kill_switch_status semantics)
# ---------------------------------------------------------------------------

def _sim_kill_switches(closed: List[dict], pool: float, today: date) -> List[str]:
    active: List[str] = []
    iso_year, iso_week, _ = today.isocalendar()
    week_start = date.fromisocalendar(iso_year, iso_week, 1)
    month_start = today.replace(day=1)

    def _pnl_since(day: date) -> float:
        return sum(
            t["pnl"] for t in closed
            if date.fromisoformat(t["entry_date"]) >= day
        )

    if _pnl_since(today) <= -settings.FNO_DAILY_KILL_PCT * pool:
        active.append("daily_loss_halt")
    if _pnl_since(week_start) <= -settings.FNO_WEEKLY_KILL_PCT * pool:
        active.append("weekly_loss_halt")
    if _pnl_since(month_start) <= -settings.FNO_MONTHLY_KILL_PCT * pool:
        active.append("monthly_loss_halt")

    n = settings.FNO_MAX_CONSECUTIVE_LOSSES
    if len(closed) >= n and all(t["pnl"] < 0 for t in closed[-n:]):
        last_loss = date.fromisoformat(closed[-1]["entry_date"])
        if today <= last_loss + timedelta(days=1):
            active.append("consecutive_loss_pause")
    return active


# ---------------------------------------------------------------------------
# the walk
# ---------------------------------------------------------------------------

def run_fno_backtest(
    bars: pd.DataFrame,
    pool: Optional[float] = None,
    iv: Optional[float] = None,
    regime: str = "REGIME_1_NORMAL",
) -> dict:
    """Replay the FNO-MOM strategy over a 5-min futures frame.

    `bars`: naive-IST datetime index, columns open/high/low/close/volume,
    spanning several sessions (the first ~3 sessions only feed the
    EMA/RVOL baselines, exactly like live).
    """
    pool = float(pool if pool is not None else settings.FNO_PAPER_BANKROLL)
    iv = float(iv if iv is not None else settings.FNO_BT_IV)
    lot_size = 75  # NIFTY

    trades: List[dict] = []
    rejects: dict = {}
    open_positions: List[_SimPosition] = []

    if bars is None or bars.empty:
        return _stats(trades, rejects, pool, iv)
    bars = bars.sort_index()

    sessions = sorted(set(bars.index.date))
    for day in sessions:
        day_bars = bars[[d == day for d in bars.index.date]]
        expiry = _next_expiry(day)
        for bar_start in day_bars.index:
            bar_end = bar_start.to_pydatetime() + timedelta(minutes=5)

            # ---- exits first (live tick order: manage, then enter) ----
            still_open: List[_SimPosition] = []
            for pos in open_positions:
                rec = _manage_position_on_bar(
                    pos, bar_start.to_pydatetime(), day_bars.loc[bar_start]
                )
                if rec is None:
                    still_open.append(pos)
                else:
                    trades.append(rec)
            open_positions = still_open

            # ---- entry evaluation on this closed bar -------------------
            nm = bar_end.hour * 60 + bar_end.minute
            if not (settings.FNO_ENTRY_START_MIN <= nm < settings.FNO_ENTRY_END_MIN):
                continue
            sig: MomSignal = evaluate_fno_mom(bars, regime, bar_end)
            if sig.direction is None:
                if sig.reject_reason not in (
                    "no_or_break", "inside_opening_range_window",
                    "no_closed_bars_today",
                ):
                    rejects[sig.reject_reason] = rejects.get(sig.reject_reason, 0) + 1
                continue
            # One evaluation per bar: skip if this bar already entered
            # (restart-safe bar_ts dedupe in live; here the loop itself
            # guarantees it).

            F = sig.close  # futures close = model forward
            is_call = sig.direction == FnoDirection.LONG
            K = _select_strike(F, expiry, bar_end, is_call, iv)
            if K is None:
                rejects["no_strike_solves_delta"] = rejects.get(
                    "no_strike_solves_delta", 0) + 1
                continue
            mid = _model_mid(F, K, expiry, bar_end, is_call, iv)
            if mid <= 0:
                rejects["degenerate_model_premium"] = rejects.get(
                    "degenerate_model_premium", 0) + 1
                continue
            ask, bid = _ask(mid), _bid(mid)

            trades_today = sum(1 for t in trades if t["entry_date"] == day.isoformat())
            open_prem = sum(p.entry_premium * p.qty for p in open_positions)
            switches = _sim_kill_switches(trades, pool, day)

            ctx = GateContext(
                now_min=nm,
                is_trading_day=True,          # bars exist => market traded
                is_expiry_day=(expiry == day),
                regime=regime,
                # Microstructure fields are MODELLED (see module banner):
                # oi/volume structurally pass; spread/envelope/intrinsic/
                # iv-sanity run on the model quote.
                oi=settings.FNO_MIN_OI, volume=settings.FNO_MIN_VOL,
                bid=bid, ask=ask, ltp=mid,
                quote_age_sec=0.0,
                forward=F, strike=K, is_call=is_call, iv=iv,
                pool=pool, premium=ask, lot_size=lot_size,
                open_premium=open_prem,
                open_positions=len(open_positions),
                trades_today=trades_today,
                active_kill_switches=switches,
                chain_age_sec=0.0,
            )
            ok, reject = evaluate_entry_gates(ctx)
            if not ok:
                rejects[reject] = rejects.get(reject, 0) + 1
                continue

            lots = lots_for_pool(
                pool, ask, lot_size,
                settings.FNO_STOP_PREMIUM_PCT, settings.FNO_MAX_RISK_PCT,
                settings.FNO_MAX_LOTS,
            )
            while lots > 0 and open_prem + lots * ask * lot_size > (
                settings.FNO_MAX_OPEN_PREMIUM_PCT * pool
            ):
                lots -= 1
            if lots < 1:
                rejects["pool_below_min_viable"] = rejects.get(
                    "pool_below_min_viable", 0) + 1
                continue

            legs = [Leg(
                opt_type=OptionType.CE if is_call else OptionType.PE,
                strike=K, quantity=lots, premium=ask,
            )]
            ok_ml, reject_ml, _ml = validate_position(legs, lot_size)
            if not ok_ml:
                rejects[reject_ml] = rejects.get(reject_ml, 0) + 1
                continue

            open_positions.append(_SimPosition(
                direction=sig.direction.value,
                strike=K, expiry=expiry, is_call=is_call,
                entry_time=bar_end, entry_date=day,
                entry_underlying=F,
                entry_premium=ask,
                lots=lots, qty=lots * lot_size,
                stop_underlying=sig.stop_underlying,
                target_underlying=sig.target_underlying,
                premium_stop=round((1.0 - settings.FNO_STOP_PREMIUM_PCT) * ask, 2),
                atr_at_entry=sig.atr,
                iv=iv,
                best_underlying=F,
            ))

        # ---- session end: anything still open exits at the last close
        # (defence in depth; the 15:10 hard flat should have fired).
        if open_positions and not day_bars.empty:
            last_start = day_bars.index[-1].to_pydatetime()
            last_close = float(day_bars["close"].iloc[-1])
            for pos in open_positions:
                trades.append(_close_trade(
                    pos, last_start + timedelta(minutes=5), last_close,
                    "session_end_flat",
                ))
            open_positions = []

    return _stats(trades, rejects, pool, iv)


def _stats(trades: List[dict], rejects: dict, pool: float, iv: float) -> dict:
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    by_reason: dict = {}
    for t in trades:
        by_reason[t["exit_reason"]] = by_reason.get(t["exit_reason"], 0) + 1
    days_traded = len({t["entry_date"] for t in trades})
    return {
        "model": {
            "iv": iv, "spread_pct": settings.FNO_BT_SPREAD_PCT,
            "pool": pool,
            "note": (
                "synthetic option leg (Black-76, constant IV); see the "
                "fno_backtest.py banner before citing these numbers"
            ),
        },
        "n_trades": len(trades),
        "days_traded": days_traded,
        "win_rate": round(len(wins) / len(trades), 4) if trades else 0.0,
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else 0.0,
        "avg_r": round(
            sum(t["r_multiple"] for t in trades) / len(trades), 3
        ) if trades else 0.0,
        "total_pnl": round(sum(t["pnl"] for t in trades), 2),
        "total_costs": round(sum(t["costs"] for t in trades), 2),
        "exit_reasons": by_reason,
        "entry_rejects": rejects,
        "trades": trades,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["datetime"], index_col="datetime")
    return df[["open", "high", "low", "close", "volume"]]


if __name__ == "__main__":
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(description="FNO-MOM backtest (model option leg)")
    ap.add_argument("--csv", required=True,
                    help="5-min futures bars: datetime,open,high,low,close,volume")
    ap.add_argument("--iv", type=float, default=None)
    ap.add_argument("--pool", type=float, default=None)
    ap.add_argument("--regime", default="REGIME_1_NORMAL")
    args = ap.parse_args()

    result = run_fno_backtest(
        _load_csv(args.csv), pool=args.pool, iv=args.iv, regime=args.regime,
    )
    trades = result.pop("trades")
    print(_json.dumps(result, indent=2))
    print(f"\n{len(trades)} trades:")
    for t in trades:
        print(
            f"  {t['entry_time']} {t['direction']:5s} K={t['strike']:.0f} "
            f"x{t['lots']} in={t['entry_premium']:.2f} out={t['exit_premium']:.2f} "
            f"pnl={t['pnl']:>8.0f} r={t['r_multiple']:>6.2f} {t['exit_reason']}"
        )
