"""
[FNO-MOM 2026-07-10] Opening-range momentum signal for NIFTY (spec §8).

THE rule this module exists to enforce: every signal is computed on
NIFTY FRONT-MONTH FUTURES 5-min bars, never on option premium. A
premium series is contaminated by theta decay and IV changes at once,
so an EMA or RSI on premium measures three things and reports on none
of them (spec §8.1). The option is purely the expression vehicle.

Entry (on a CLOSED 5-min bar):
  LONG  (buy CE): close > OR_high + 0.25*ATR(14), EMA(21) > EMA(50),
                  RVOL >= 1.2, regime != CRISIS
  SHORT (buy PE): symmetric below OR_low.

"Fresh break" rule: the signal fires only on the bar that CROSSES the
threshold (previous close inside the range, current close beyond it).
This is what makes re-entry after a stop-out legal only on a fresh
break (spec §8.2), and it also stops the engine from re-firing every
bar while price sits above the range.

RVOL is time-of-day adjusted: last bar volume vs the mean volume of the
SAME 5-min slot over the trailing sessions in the frame. Comparing a
09:50 bar against a whole-day average is the exact bug class the penny
module shipped (PENNY_BREAKOUT_RVOL_TIME_ADJUSTED); built correctly
from day one here.

Pure: pandas in, dataclass out. No I/O, no Kite, no DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import pytz
import structlog

from config import settings
from fno_models import FnoDirection

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

SESSION_OPEN_MIN = 9 * 60 + 15   # 09:15 IST


@dataclass
class MomSignal:
    """Outcome of one evaluation. direction=None means no entry; the
    reject_reason then says which condition failed (spec §9 taxonomy)."""
    bar_ts: str = ""
    direction: Optional[FnoDirection] = None
    reject_reason: str = ""
    close: float = 0.0
    or_high: float = 0.0
    or_low: float = 0.0
    atr: float = 0.0
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    rvol: float = 0.0
    stop_underlying: float = 0.0     # tightest of structural / volatility
    target_underlying: float = 0.0   # 1.5R from entry


def _minutes_ist(ts: pd.Timestamp) -> int:
    return ts.hour * 60 + ts.minute


def wilder_atr(df: pd.DataFrame, length: int) -> Optional[float]:
    """ATR over the frame's last rows, Wilder smoothing."""
    if len(df) < length + 1:
        return None
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1.0 / length, adjust=False).mean()
    val = float(atr.iloc[-1])
    return val if val > 0 else None


def _rvol_time_adjusted(df: pd.DataFrame, bar_ts: pd.Timestamp) -> Optional[float]:
    """Last-bar volume vs mean volume of the same HH:MM slot on prior days.

    [AUDIT-FIX-PHASE1 2026-07-11] Honour settings.FNO_RVOL_LOOKBACK_DAYS:
    the original implementation used ALL bars with date < bar_ts.date(),
    which silently grew with the multi-day frame length (21 calendar days
    by default -- ~14 trading days -> ~14 samples per slot, but the
    config knob was ignored). Operators expect lookback=10 to give 10,
    not "however many the frame happens to contain".
    """
    slot = (bar_ts.hour, bar_ts.minute)
    n_lookback = max(1, int(settings.FNO_RVOL_LOOKBACK_DAYS))
    # Walk back over the same slot on prior trading days; stop at n_lookback.
    samples: list = []
    for d in pd.date_range(end=bar_ts.date() - pd.Timedelta(days=1), periods=n_lookback, freq="D"):
        rows = df[(df.index.hour == slot[0]) & (df.index.minute == slot[1])
                  & (df.index.date == d.date())]
        if not rows.empty:
            samples.append(float(rows["volume"].iloc[0]))
    if len(samples) < 3:
        return None  # not enough history for an honest baseline
    baseline = float(pd.Series(samples).mean())
    if baseline <= 0:
        return None
    return float(df.loc[bar_ts, "volume"]) / baseline


def evaluate_fno_mom(
    bars: pd.DataFrame,
    regime: str,
    now_ist: datetime,
) -> MomSignal:
    """Evaluate the momentum entry on the last CLOSED 5-min bar.

    `bars`: 5-min futures bars indexed by naive-IST datetime, spanning
    several sessions (multi-day frame feeds the EMAs and the RVOL
    baseline; the opening range uses today only).
    """
    out = MomSignal()
    if bars is None or bars.empty:
        out.reject_reason = "no_bars"
        return out

    naive_now = now_ist.replace(tzinfo=None)
    # A bar is closed when its start + 5 min is in the past.
    closed = bars[bars.index + timedelta(minutes=5) <= naive_now]
    today = naive_now.date()
    today_bars = closed[[d == today for d in closed.index.date]]
    if today_bars.empty:
        out.reject_reason = "no_closed_bars_today"
        return out

    last_ts = today_bars.index[-1]
    out.bar_ts = last_ts.strftime("%Y-%m-%d %H:%M:%S")
    out.close = float(today_bars["close"].iloc[-1])

    # ---- opening range (09:15 + FNO_OR_MINUTES) ----------------------
    or_end_min = SESSION_OPEN_MIN + settings.FNO_OR_MINUTES
    or_bars = today_bars[[
        SESSION_OPEN_MIN <= _minutes_ist(t) < or_end_min for t in today_bars.index
    ]]
    expected_or_bars = settings.FNO_OR_MINUTES // 5
    if len(or_bars) < expected_or_bars:
        out.reject_reason = "opening_range_incomplete"
        return out
    out.or_high = float(or_bars["high"].max())
    out.or_low = float(or_bars["low"].min())
    if _minutes_ist(last_ts) < or_end_min:
        out.reject_reason = "inside_opening_range_window"
        return out

    # ---- indicators on the multi-day closed frame --------------------
    atr = wilder_atr(closed, settings.FNO_ATR_LEN)
    if atr is None:
        out.reject_reason = "atr_unavailable"
        return out
    out.atr = atr
    if len(closed) < settings.FNO_EMA_SLOW + 1:
        out.reject_reason = "ema_insufficient_bars"
        return out
    ema_fast = closed["close"].ewm(span=settings.FNO_EMA_FAST, adjust=False).mean()
    ema_slow = closed["close"].ewm(span=settings.FNO_EMA_SLOW, adjust=False).mean()
    out.ema_fast = float(ema_fast.iloc[-1])
    out.ema_slow = float(ema_slow.iloc[-1])

    rvol = _rvol_time_adjusted(closed, last_ts)
    out.rvol = rvol if rvol is not None else 0.0

    # ---- breakout levels ---------------------------------------------
    buf = settings.FNO_OR_BUFFER_ATR * atr
    long_level = out.or_high + buf
    short_level = out.or_low - buf
    prev_close = (
        float(today_bars["close"].iloc[-2]) if len(today_bars) >= 2 else out.close
    )

    long_break = out.close > long_level
    short_break = out.close < short_level
    if not long_break and not short_break:
        out.reject_reason = "no_or_break"
        return out

    # Fresh-break requirement (crossing bar, not resident-above bar).
    if long_break and prev_close > long_level:
        out.reject_reason = "not_fresh_break"
        return out
    if short_break and prev_close < short_level:
        out.reject_reason = "not_fresh_break"
        return out

    # ---- filters -----------------------------------------------------
    if regime == "REGIME_3_CRISIS":
        out.reject_reason = "regime_crisis"
        return out
    if long_break and not (out.ema_fast > out.ema_slow):
        out.reject_reason = "ema_trend_disagreement"
        return out
    if short_break and not (out.ema_fast < out.ema_slow):
        out.reject_reason = "ema_trend_disagreement"
        return out
    if rvol is None:
        out.reject_reason = "rvol_baseline_unavailable"
        return out
    if rvol < settings.FNO_MIN_RVOL:
        out.reject_reason = "rvol_below_min"
        return out

    # ---- stops / target in underlying points (spec §8.4/§8.5) --------
    # Tightest of structural (opposite OR edge) and volatility (1.5*ATR)
    # wins. The premium backstop (-25%) is applied downstream where the
    # premium is known.
    vol_dist = settings.FNO_STOP_ATR_MULT * atr
    if long_break:
        structural = out.or_low
        volatility = out.close - vol_dist
        out.stop_underlying = max(structural, volatility)
        r_points = out.close - out.stop_underlying
        out.target_underlying = out.close + settings.FNO_TARGET_R * r_points
        out.direction = FnoDirection.LONG
    else:
        structural = out.or_high
        volatility = out.close + vol_dist
        out.stop_underlying = min(structural, volatility)
        r_points = out.stop_underlying - out.close
        out.target_underlying = out.close - settings.FNO_TARGET_R * r_points
        out.direction = FnoDirection.SHORT

    if r_points <= 0:
        # Degenerate geometry (stop at/through entry) -- refuse.
        out.direction = None
        out.reject_reason = "degenerate_stop_distance"
        return out

    out.reject_reason = ""
    return out
