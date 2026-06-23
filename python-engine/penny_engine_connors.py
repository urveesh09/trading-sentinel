"""
[PENNY-CONNORS 2026-06-21] Larry Connors RSI(2) mean-reversion evaluator
for the penny subsystem (CNC, multi-day).

Spec section 4 + 4.5 covers the full signal + 3-way exit logic.

Hard architectural rule (enforced by tests/test_penny_isolation.py):
  this module MUST NOT import from engine, regime, risk_engine, portfolio,
  evaluate_signal, or evaluate_momentum_signal.

Public API:
  evaluate_connors_entry(ticker, daily, today_volume, avg20_volume,
                          regime_size_pct, risk_engine, as_of) -> dict
  evaluate_connors_exit(pos, current_price, now) -> dict
  atr_1min(bars) -> float
"""
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


# ---- helpers -----------------------------------------------------------

def _sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _rsi_2(closes: List[float]) -> float:
    """
    2-period RSI (Wilder-style). Requires >= 3 closes.
    Returns 50.0 for insufficient data.
    """
    if len(closes) < 3:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        if ch > 0:
            gains.append(ch)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-ch)
    if not gains:
        return 50.0
    avg_g = sum(gains[-2:]) / 2.0
    avg_l = sum(losses[-2:]) / 2.0
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1.0 + rs))


def atr_1min(bars: List[dict]) -> float:
    """
    Average true range of 1-min bars post-T1 (spec section 4.5).
    True range per bar = high - low (1-min bars don't gap).
    """
    if bars is None or (hasattr(bars, "empty") and bars.empty):
        return 0.0
    if hasattr(bars, "columns"):
        highs = bars["high"].tolist() if "high" in bars.columns else []
        lows = bars["low"].tolist() if "low" in bars.columns else []
        trs = [h - l for h, l in zip(highs, lows) if h is not None and l is not None]
    else:
        trs = [(b["high"] - b["low"]) for b in bars if b.get("high") is not None and b.get("low") is not None]
    if not trs:
        return 0.0
    return sum(trs) / len(trs)


# ---- entry evaluation --------------------------------------------------

def evaluate_connors_entry(
    ticker: str,
    daily: dict,
    today_volume: int,
    avg20_volume: int,
    regime_size_pct: float,
    risk_engine,  # PennyRiskEngine instance (avoiding import cycle name)
    as_of: datetime,
) -> dict:
    """
    Returns one of:
      {"accept": True, "entry": ..., "stop_loss": ..., "target_1": ...,
       "target_2": ..., "shares": ..., "entry_order_type": "LIMIT",
       "sl_order_type": "SL-M", "reason": "trigger fired"}
      {"accept": False, "reject_reason": "<why>"}
    """
    from config import settings
    closes = daily.get("closes", [])
    if len(closes) < 210:
        return {"accept": False, "reject_reason": "insufficient history (<210 bars)"}

    last = closes[-1]
    sma_200 = _sma(closes, 200)
    sma_50 = _sma(closes, 50)
    if sma_200 is None or sma_50 is None:
        return {"accept": False, "reject_reason": "SMA not available"}

    # 1. Trend filter (spec section 4.2)
    if last <= sma_200:
        return {"accept": False, "reject_reason": "below 200 SMA (trend fail)"}
    if last <= sma_50:
        return {"accept": False, "reject_reason": "below 50 SMA (trend fail)"}

    # 2. Trigger: RSI(2) < threshold (relaxed to 10 for penny, spec section 4.2)
    rsi = _rsi_2(closes)
    if rsi >= settings.PENNY_CONNORS_RSI2_BUY:
        return {"accept": False, "reject_reason": f"RSI(2)={rsi:.1f} not below threshold"}

    # 3. Confirmation: RSI(2) rising for 2 consecutive bars (spec section 4.2)
    rsi_prev1 = _rsi_2(closes[:-1])
    rsi_prev2 = _rsi_2(closes[:-2])
    if not (rsi > rsi_prev1 > rsi_prev2):
        return {"accept": False, "reject_reason": "RSI not rising for 2 bars (falling knife)"}

    # 4. Volume sanity (spec section 4.2)
    if avg20_volume <= 0 or today_volume < 0.5 * avg20_volume:
        return {"accept": False, "reject_reason": "volume too low (dead stock)"}

    # ---- signal fires ----
    # Entry at LTP + 0.5%, stop at -3%, T1 at +3%, T2 at +6%
    entry = round(last * 1.005, 2)
    stop_loss = round(entry * (1 - settings.PENNY_CONNORS_STOP_PCT), 2)
    target_1 = round(entry * (1 + settings.PENNY_CONNORS_T1_PCT), 2)
    target_2 = round(entry * (1 + settings.PENNY_CONNORS_T2_PCT), 2)

    shares = risk_engine.position_size(entry, stop_loss, _regime_from_pct(regime_size_pct))
    if shares <= 0:
        return {"accept": False, "reject_reason": "position size = 0 (regime/cap blocked)"}

    return {
        "accept": True,
        "ticker": ticker,
        "entry": entry,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "shares": shares,
        "entry_order_type": "LIMIT",
        "sl_order_type": "SL-M",
        "rsi_2": round(rsi, 2),
        "signal_time": as_of,
        "reason": "connors trigger fired",
    }


def _regime_from_pct(pct: float):
    """Reverse-map size_pct to PennyRegime for risk sizing."""
    from penny_models import PennyRegime
    from config import settings
    if pct >= settings.PENNY_RISK_PCT_PR1:
        return PennyRegime.PR1_CALM
    if pct >= settings.PENNY_RISK_PCT_PR2:
        return PennyRegime.PR2_ELEVATED
    return PennyRegime.PR3_HOT


# ---- exit evaluation ---------------------------------------------------

def evaluate_connors_exit(pos: dict, current_price: float, now: datetime) -> dict:
    """
    Spec section 4.2 + 4.5: 3-way exit (T2 OR trail OR time-stop, whichever first).
    pos keys: entry_price, entry_time, t1_fired, t1_exit_price,
              remaining_shares, highest_close_since_t1, atr_1min_post_t1

    Time-stop is 3 *trading days* (weekday-counted) from entry, not 3 calendar
    days -- a Friday entry is force-exited the following Wednesday, not Monday.
    NSE holiday calendar is out of scope for v1; if a known holiday falls
    inside the window the position holds one extra day (acceptable: the
    broker-level SL-M still protects downside, this only delays exit by 1d).

    Returns dict with:
      {"exit_reason": "T2"|"trail_stop"|"time_stop"|"hold", "exit_price": float}
    """
    from config import settings
    if not pos.get("t1_fired"):
        # Pre-T1: only stop-loss applies (broker SL-M). Engine doesn't compute it here.
        return {"exit_reason": "hold", "exit_price": current_price}

    # 1. Time-stop: count weekdays (Mon-Fri) elapsed from entry to now.
    if _trading_days_elapsed(pos["entry_time"], now) >= settings.PENNY_CONNORS_MAX_HOLD_DAYS:
        return {"exit_reason": "time_stop", "exit_price": current_price}

    # 2. T2 target
    target_2 = pos["entry_price"] * (1 + settings.PENNY_CONNORS_T2_PCT)
    if current_price >= target_2:
        return {"exit_reason": "T2", "exit_price": target_2}

    # 3. Trailing stop (post-T1, 2x ATR_1min, breakeven+0.5% floor)
    floor = round(pos["entry_price"] * 1.005, 2)  # breakeven + 0.5%
    atr = pos.get("atr_1min_post_t1", 0.0) or 0.0
    trail_raw = pos.get("highest_close_since_t1", current_price) - \
                 settings.PENNY_CONNORS_TRAIL_ATR_MULT * atr
    trail = max(floor, trail_raw)
    if current_price <= trail:
        return {"exit_reason": "trail_stop", "exit_price": trail}

    return {"exit_reason": "hold", "exit_price": current_price}


def _trading_days_elapsed(start: datetime, end: datetime) -> int:
    """
    Count weekdays (Mon=0..Sun=4) strictly between start (exclusive) and
    end (inclusive). A Friday 09:30 -> following Monday 09:30 = 1 trading
    day. Friday 09:30 -> Wednesday 09:30 = 3 trading days (force-exit fires).
    """
    if end <= start:
        return 0
    days = 0
    d = start.date() + timedelta(days=1)
    end_date = end.date()
    while d <= end_date:
        if d.weekday() < 5:  # Mon-Fri
            days += 1
        d += timedelta(days=1)
    return days
