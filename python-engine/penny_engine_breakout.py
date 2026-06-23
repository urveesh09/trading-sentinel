"""
[PENNY-BREAKOUT 2026-06-21] Volume Breakout MIS signal evaluator + 14:30
smart-EOD rule for the penny subsystem.

Spec section 5 covers the full signal flow and the smart-EOD exit logic.

Hard architectural rule (enforced by tests/test_penny_isolation.py):
  this module MUST NOT import from engine, regime, risk_engine, portfolio,
  evaluate_signal, or evaluate_momentum_signal.

Public API:
  evaluate_breakout_entry(ticker, cum_vol_today, median_vol_20d,
                          breakout_bar, day_high, rsi_14, as_of,
                          risk_engine) -> dict
  smart_eod_check(pos, current_price, now) -> dict
  mis_time_stop_active(now) -> bool
"""
import logging
from datetime import datetime, time, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---- helpers ----------------------------------------------------------

def _rsi_14_wilder(closes: List[float]) -> float:
    """
    Wilder-style 14-period RSI on a list of closes.
    Local helper to keep penny_engine_breakout isolated from engine.py
    (the isolation test forbids importing from engine).
    Returns 50.0 if there are fewer than 15 closes (insufficient data).
    """
    if len(closes) < 15:
        return 50.0
    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    # First average: simple mean of first 14 changes
    avg_g = sum(gains[:14]) / 14.0
    avg_l = sum(losses[:14]) / 14.0
    # Wilder smoothing for the rest
    for i in range(14, len(gains)):
        avg_g = (avg_g * 13 + gains[i]) / 14.0
        avg_l = (avg_l * 13 + losses[i]) / 14.0
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1.0 + rs))


def _to_minutes_since_midnight(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def _regime_from_pct(pct: float):
    from penny_models import PennyRegime
    from config import settings
    if pct >= settings.PENNY_RISK_PCT_PR1:
        return PennyRegime.PR1_CALM
    if pct >= settings.PENNY_RISK_PCT_PR2:
        return PennyRegime.PR2_ELEVATED
    return PennyRegime.PR3_HOT


# ---- entry evaluation --------------------------------------------------

def evaluate_breakout_entry(
    ticker: str,
    cum_vol_today: int,
    median_vol_20d: int,
    breakout_bar: dict,
    day_high: float,
    rsi_14: float,
    as_of: datetime,
    risk_engine,
) -> dict:
    """
    Spec section 5.2: volume + breakout + time + RSI gates. On accept, returns
    sizing + order params. Reject returns the reason.
    """
    from config import settings
    # 1. Time gate: 10:30 to 14:30 IST
    mins = _to_minutes_since_midnight(as_of)
    if mins < settings.PENNY_BREAKOUT_TIME_START or mins >= settings.PENNY_BREAKOUT_TIME_END:
        return {"accept": False, "reject_reason": f"outside breakout time window ({mins} min)"}

    # 2. Volume surge: today cumulative > 3x 20-day median
    if median_vol_20d <= 0 or cum_vol_today < settings.PENNY_BREAKOUT_VOL_MULT * median_vol_20d:
        return {"accept": False,
                "reject_reason": f"volume {cum_vol_today} < {settings.PENNY_BREAKOUT_VOL_MULT}x median ({median_vol_20d})"}

    # 3. Breakout confirm: close > day_high + 0.3% on a 1-min bar
    bar_close = breakout_bar.get("close", 0)
    required = day_high * 1.003
    if bar_close <= required:
        return {"accept": False,
                "reject_reason": f"breakout not confirmed (close {bar_close:.2f} <= {required:.2f})"}

    # 4. RSI not overbought
    if rsi_14 >= 70:
        return {"accept": False, "reject_reason": f"RSI(14)={rsi_14:.1f} overbought"}

    # ---- signal fires ----
    # Entry: limit at LTP (bar_close) + 0.3%
    entry = round(bar_close * 1.003, 2)
    # Stop: breakout candle low (1-min)
    stop_loss = breakout_bar.get("low", entry * 0.98)
    risk_per_share = entry - stop_loss
    if risk_per_share <= 0:
        return {"accept": False, "reject_reason": "non-positive risk (bar low >= entry)"}
    # Target: +2R
    target = round(entry + settings.PENNY_BREAKOUT_TARGET_R * risk_per_share, 2)

    shares = risk_engine.position_size(entry, stop_loss, _regime_from_pct(0.05))
    if shares <= 0:
        return {"accept": False, "reject_reason": "position size = 0 (regime/cap blocked)"}

    return {
        "accept": True,
        "ticker": ticker,
        "entry": entry,
        "stop_loss": stop_loss,
        "target": target,
        "breakout_level": day_high,  # the day's high that price broke above (spec section 10.1)
        "shares": shares,
        "entry_order_type": "LIMIT",
        "sl_order_type": "SL-M",
        "rsi_14": round(rsi_14, 2),
        "signal_time": as_of,
        "reason": "breakout signal fired",
    }


# ---- smart-EOD 14:30 rule --------------------------------------------

def smart_eod_check(pos: dict, current_price: float, now: datetime) -> dict:
    """
    Spec section 5.3: 3-way decision rule at PENNY_MIS_SMART_EOD_TIME (default 14:30).

      In profit + within 0.5R of target -> exit_now
      In profit + > 0.5R from target     -> hold
      In loss + > 30 min in loss          -> exit_now (cut_bleed)
      In loss + fresh entry (< 30 min)    -> hold

    Returns dict with:
      {"action": "exit_now"|"hold",
       "reason": "<which branch>"}
    """
    from config import settings
    entry = pos["entry_price"]
    stop = pos["stop_loss"]
    target = pos["target"]
    R = entry - stop  # risk per share

    in_profit = current_price >= entry
    distance_to_target = target - current_price

    if in_profit:
        if distance_to_target <= settings.PENNY_MIS_SMART_EOD_WITHIN_R * R:
            return {"action": "exit_now", "reason": "within_0_5R_of_target"}
        return {"action": "hold", "reason": "profit_far_from_target"}

    # In loss
    elapsed_in_loss = now - pos["entry_time"]
    if elapsed_in_loss > timedelta(minutes=settings.PENNY_MIS_SMART_EOD_LOSS_MIN):
        return {"action": "exit_now", "reason": "loss_over_30_min"}
    return {"action": "hold", "reason": "fresh_loss"}


# ---- 15:00 time-stop -------------------------------------------------

def mis_time_stop_active(now: datetime) -> bool:
    """
    Spec section 5.2: at 15:00 IST (PENNY_BREAKOUT_TIME_EXIT), force-exit all open
    MIS positions. Returns True if now >= 15:00 IST.
    """
    from config import settings
    mins = _to_minutes_since_midnight(now)
    return mins >= settings.PENNY_BREAKOUT_TIME_EXIT
