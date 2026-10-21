"""MOM_RS_PULLBACK: a leader's VWAP pullback, for days the crossover misses.

Shadow-only Momentum variant [O19-M2], declared 2026-10-19 before any scoring.
Oct 19 ran 19 Momentum scans with 0 accepts: 7,382 of 9,443 evaluations were
``no_recent_vwap_crossover`` and MOM_SELECTIVE requires the market to be up.
On a red or flat day a trader still finds the stock that leads the market,
holds above VWAP, dips to it and is bought back. The shipped evaluator cannot
see that setup (it needs a fresh cross from below), so this variant records
it on the same scan frames as forward paper evidence; it gates nothing live.

Every input is a completed 15-minute bar known at the decision. Stop, target
and size use the shipped Momentum rules (percent and ATR stop floors, regime
R target and risk budget, pool cap); a missing index bar fails closed.
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from config import settings

RS_MIN_EXCESS = 0.0075        # stock session return - NIFTY session return
VWAP_SHARE_MIN = 0.60         # share of earlier session bars closed above VWAP
TOUCH_TOLERANCE = 0.003       # a low within 0.3% above VWAP counts as a touch
CLOSE_LOCATION_MIN = 0.5      # reclaim bar closes in the upper half of its range
VOLUME_MULT = 1.2             # reclaim bar volume vs the prior 8 bars' mean
MIN_SESSION_BARS = 6
WINDOW_START_MIN = 10 * 60 + 15
WINDOW_END_MIN = 14 * 60 + 15
RULES_VERSION = "rs_pullback_v1"


def rs_pullback_rules() -> dict:
    """[S21-R2] Every constant and setting the decision reads, with a version,
    so a shadow record says exactly which rule produced it."""
    return {
        "version": RULES_VERSION, "rs_min_excess": RS_MIN_EXCESS, "vwap_share_min": VWAP_SHARE_MIN,
        "touch_tolerance": TOUCH_TOLERANCE, "close_location_min": CLOSE_LOCATION_MIN,
        "volume_mult": VOLUME_MULT, "min_session_bars": MIN_SESSION_BARS,
        "window_start_min": WINDOW_START_MIN, "window_end_min": WINDOW_END_MIN,
        "min_stop_pct": float(settings.MOMENTUM_MIN_STOP_PCT),
        "min_stop_atr_mult": float(settings.MOMENTUM_MIN_STOP_ATR_MULT),
        "risk_pct": float(settings.MOMENTUM_RISK_PCT), "r_target": float(settings.MOMENTUM_R_TARGET),
        "r_target_bear": float(settings.MOMENTUM_R_TARGET_BEAR),
    }


def rs_index_known(index_today: Optional[pd.DataFrame], signal_ts) -> Optional[pd.DataFrame]:
    """The index bars the rule can see at ``signal_ts`` (same session, not later)."""
    if index_today is None or index_today.empty or not isinstance(index_today.index, pd.DatetimeIndex):
        return None
    return index_today[(index_today.index.date == signal_ts.date()) & (index_today.index <= signal_ts)]


def _vwap(frame: pd.DataFrame) -> pd.Series:
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    volume = frame["volume"].astype(float)
    return (typical * volume).cumsum() / volume.cumsum().where(volume.cumsum() > 0)


def rs_pullback_signal(df: pd.DataFrame, index_today: Optional[pd.DataFrame], *, momentum_pool: float,
                       df_daily: Optional[pd.DataFrame] = None, regime=None,
                       market_regime: str = "BULL") -> tuple[bool, dict]:
    """Decide on the last bar of ``df``; returns the shipped decision shape."""
    from engine import calc_atr, resolve_momentum_regime_params

    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return False, {"reject_reason": "intraday_data_empty"}
    session = df.index[-1].date()
    today = df[df.index.date == session]
    if len(today) < MIN_SESSION_BARS:
        return False, {"reject_reason": "insufficient_session_bars", "count": len(today)}
    signal_ts = today.index[-1]
    minute = signal_ts.hour * 60 + signal_ts.minute
    if not WINDOW_START_MIN <= minute <= WINDOW_END_MIN:
        return False, {"reject_reason": "outside_pullback_window", "minute": minute}
    index_known = rs_index_known(index_today, signal_ts)
    if index_known is None or index_known.empty or index_known.index[-1] != signal_ts:
        return False, {"reject_reason": "index_bar_unavailable"}

    first_open, close = float(today["open"].iloc[0]), float(today["close"].iloc[-1])
    index_open, index_close = float(index_known["open"].iloc[0]), float(index_known["close"].iloc[-1])
    if not all(math.isfinite(v) and v > 0 for v in (first_open, close, index_open, index_close)):
        return False, {"reject_reason": "session_return_unavailable"}
    stock_ret, index_ret = close / first_open - 1.0, index_close / index_open - 1.0
    evidence = {"stock_session_return": round(stock_ret, 6), "index_session_return": round(index_ret, 6),
                "relative_strength": round(stock_ret - index_ret, 6)}
    if stock_ret <= 0:
        return False, {"reject_reason": "stock_not_up", **evidence}
    if stock_ret - index_ret < RS_MIN_EXCESS:
        return False, {"reject_reason": "relative_strength_too_low", **evidence}

    vwap = _vwap(today)
    if vwap.isna().any():
        return False, {"reject_reason": "zero_session_volume", **evidence}
    earlier = today.iloc[:-1]
    share_above = float((earlier["close"] > vwap.iloc[:-1]).mean())
    current_vwap = float(vwap.iloc[-1])
    evidence.update(vwap=round(current_vwap, 4), share_above_vwap=round(share_above, 4))
    if share_above < VWAP_SHARE_MIN:
        return False, {"reject_reason": "not_holding_above_vwap", **evidence}

    bar, prev = today.iloc[-1], today.iloc[-2]
    touched = (float(prev["low"]) <= float(vwap.iloc[-2]) * (1 + TOUCH_TOLERANCE)
               or float(bar["low"]) <= current_vwap * (1 + TOUCH_TOLERANCE))
    if not touched:
        return False, {"reject_reason": "no_vwap_pullback", **evidence}
    bar_range = float(bar["high"]) - float(bar["low"])
    location = (close - float(bar["low"])) / bar_range if bar_range > 0 else 0.0
    if not (close > current_vwap and close > float(prev["close"]) and location >= CLOSE_LOCATION_MIN):
        return False, {"reject_reason": "pullback_not_reclaimed", "close_location": round(location, 4), **evidence}
    prior_volume = today["volume"].iloc[-9:-1].astype(float)
    volume_ratio = float(bar["volume"]) / float(prior_volume.mean()) if prior_volume.mean() > 0 else 0.0
    evidence["volume_ratio"] = round(volume_ratio, 4)
    if volume_ratio < VOLUME_MULT:
        return False, {"reject_reason": "reclaim_volume_insufficient", **evidence}

    # Shipped Momentum stop: the widest of the pullback low, the percent floor
    # and the daily-ATR floor.
    daily_atr = None
    if df_daily is not None and len(df_daily) >= 14:
        value = float(calc_atr(df_daily["high"], df_daily["low"], df_daily["close"]).iloc[-1])
        daily_atr = value if value > 0 else None
    stop_candidates = [min(float(prev["low"]), float(bar["low"])),
                       close * (1.0 - settings.MOMENTUM_MIN_STOP_PCT)]
    if daily_atr:
        stop_candidates.append(close - settings.MOMENTUM_MIN_STOP_ATR_MULT * daily_atr)
    stop = min(stop_candidates)
    risk_per_share = close - stop
    r_target, risk_pct, blocked = resolve_momentum_regime_params(regime=regime)
    if blocked:
        return False, {"reject_reason": "regime_r3_block", **evidence}
    if regime is None:
        risk_pct = settings.MOMENTUM_RISK_PCT
        r_target = (settings.MOMENTUM_R_TARGET_BEAR if market_regime == "BEAR_RS_ONLY"
                    else settings.MOMENTUM_R_TARGET)
    shares = math.floor(momentum_pool * risk_pct / risk_per_share) if risk_per_share > 0 else 0
    shares = min(shares, math.floor(momentum_pool / close))
    if shares <= 0:
        return False, {"reject_reason": "zero_shares_momentum", **evidence}
    return True, {
        **evidence, "close": close, "entry_price": close, "stop_loss": round(stop, 4),
        "target_1": round(close + r_target * risk_per_share, 4), "shares": shares,
        "daily_atr": daily_atr, "intraday_high": float(today["high"].max()),
        "intraday_low": float(today["low"].min()),
    }
