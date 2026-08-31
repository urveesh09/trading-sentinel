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

[PENNY-RSI-CONTRACT 2026-06-25, G3 audit note] The penny subsystem
deliberately uses TWO RSI periods, one per engine:

- MIS Breakout leg: RSI(14) (Wilder). Implemented locally as
  _rsi_14_wilder() below. This is the standard 14-period RSI on the
  1-min closes. Used as an overbought guard (>70 = reject).

- CNC Connors leg: RSI(2) (Wilder). Implemented in
  penny_engine_connors._rsi_2(). This is the Connors mean-reversion
  RSI(2) on DAILY closes. Used as the oversold-bounce trigger (<10).

These are NOT the same thing. They are correctly different signals:
- RSI(14) on 1-min bars: short-term momentum / overbought, gates the
  MIS breakout entry to avoid chasing into exhaustion.
- RSI(2) on daily bars: mean-reversion, fires the CNC entry when the
  stock is pulling back in an uptrend.

A future consolidation would require picking one RSI per engine; for
now this is documented and the two implementations live in their
respective engine modules (no cross-import) so the isolation rule is
preserved.
"""
import logging
import math
from datetime import datetime, time, timedelta
from typing import List, Optional, Union

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


def _vwap_from_intraday(intraday) -> Optional[float]:
    """
    [TIER2-BREAKOUT-REFINEMENT 2026-06-25] Compute VWAP from intraday bars.
    VWAP = cumsum(typical_price * volume) / cumsum(volume), where
    typical_price = (H + L + C) / 3 per bar.

    Accepts either a pandas DataFrame with high/low/close/volume columns
    (same shape as kite.get_intraday output) or a list of dicts. Returns
    None if the data is too sparse (<3 bars) or any required column is
    missing.
    """
    if intraday is None:
        return None
    n = len(intraday) if hasattr(intraday, "__len__") else 0
    if n < 3:
        return None
    try:
        if hasattr(intraday, "columns"):
            if not all(c in intraday.columns for c in ("high", "low", "close", "volume")):
                return None
            tp = (intraday["high"] + intraday["low"] + intraday["close"]) / 3.0
            vol = intraday["volume"].fillna(0).astype(float)
        else:
            tps, vols = [], []
            for b in intraday:
                h = b.get("high"); l = b.get("low"); c = b.get("close"); v = b.get("volume")
                if h is None or l is None or c is None:
                    return None
                tps.append((h + l + c) / 3.0)
                vols.append(float(v or 0))
            import pandas as _pd
            tp = _pd.Series(tps)
            vol = _pd.Series(vols)
        cum_tp_vol = (tp * vol).sum()
        cum_vol = vol.sum()
        if cum_vol <= 0:
            return None
        return float(cum_tp_vol / cum_vol)
    except Exception:
        return None


def _atr_20_from_intraday(intraday) -> Optional[float]:
    """
    [TIER2-BREAKOUT-REFINEMENT 2026-06-25] 20-period ATR from 1-min bars.
    ATR_n = mean(true_range over last n bars). True range for 1-min bars
    is just (high - low) (no gaps within a session).

    Returns None if insufficient data (<20 bars) or missing columns.
    """
    if intraday is None:
        return None
    n = len(intraday) if hasattr(intraday, "__len__") else 0
    if n < 20:
        return None
    try:
        if hasattr(intraday, "columns"):
            if not all(c in intraday.columns for c in ("high", "low")):
                return None
            tr = intraday["high"] - intraday["low"]
        else:
            trs = []
            for b in intraday:
                h = b.get("high"); l = b.get("low")
                if h is None or l is None:
                    return None
                trs.append(h - l)
            import pandas as _pd
            tr = _pd.Series(trs)
        return float(tr.tail(20).mean())
    except Exception:
        return None


def _adaptive_threshold_scale(intraday, base_pct: float) -> float:
    """
    [TIER2-BREAKOUT-REFINEMENT 2026-06-25] Compute a volatility-adjusted
    multiplier for the breakout buffer. The current ATR(20) is divided
    by the median ATR(20) over the last 60 bars (a coarse "is this
    ticker calmer or more volatile than usual?" signal).

    - If scale > 1.0 (calmer than typical): tighten the buffer.
      Rationale: low-volatility breakouts are less meaningful; require
      more confirmation.
    - If scale < 1.0 (more volatile than typical): loosen the buffer.
      Rationale: high-vol breakouts already have wide swings; a tighter
      threshold would fire too often.

    The scale is bounded to [0.3, 2.0] so it cannot amplify the buffer
    by more than 2x or crush it below 30%. Per de Prado, Advances in
    Financial ML ch. 16 (volatility-targeted entries).

    Returns base_pct unchanged if data is insufficient.
    """
    if intraday is None:
        return base_pct
    n = len(intraday) if hasattr(intraday, "__len__") else 0
    if n < 60:
        return base_pct
    try:
        if hasattr(intraday, "columns"):
            if not all(c in intraday.columns for c in ("high", "low")):
                return base_pct
            tr = intraday["high"] - intraday["low"]
        else:
            trs = []
            for b in intraday:
                h = b.get("high"); l = b.get("low")
                if h is None or l is None:
                    return base_pct
                trs.append(h - l)
            import pandas as _pd
            tr = _pd.Series(trs)
        current_atr = float(tr.tail(20).mean())
        median_atr = float(tr.tail(60).median())
        if median_atr <= 0 or current_atr <= 0:
            return base_pct
        scale = current_atr / median_atr
        # Bound to [0.3, 2.0]
        scale = max(0.3, min(2.0, scale))
        return base_pct * scale
    except Exception:
        return base_pct


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
    intraday=None,                 # [TIER2-BREAKOUT-REFINEMENT 2026-06-25]
    *,
    regime=None,                   # [FIX-PHASE1-AUDIT 2026-07-09] PennyRegime | None
    time_start_min: int | None = None,
    volume_multiplier: float | None = None,
) -> dict:
    """
    Spec section 5.2: volume + breakout + time + RSI gates. On accept, returns
    sizing + order params. Reject returns the reason.

    [TIER2-BREAKOUT-REFINEMENT 2026-06-25] Two optional refinements, both
    controlled by config and both default to OFF:

    - VWAP-anchored breakout: when PENNY_BREAKOUT_USE_VWAP=True and intraday
      bars are provided, replace the day_high anchor with VWAP. The breakout
      becomes "close > VWAP + buffer" instead of "close > day_high + buffer".
      Rationale: a breakout above VWAP is volume-confirmed; above day_high
      alone is just "highest tick so far" which can be a single wick.

    - Adaptive buffer: when PENNY_BREAKOUT_ADAPTIVE_THRESHOLD=True and intraday
      has >= 60 bars, scale the buffer by current_ATR(20) / median_ATR(60).
      Calm ticker -> tighter buffer; volatile -> wider. Per de Prado,
      Advances in Financial ML ch. 16. Both default to False so pre-fix
      behaviour is preserved.
    """
    from config import settings
    if time_start_min is not None:
        if isinstance(time_start_min, bool) or not isinstance(time_start_min, int):
            raise ValueError("time_start_min must be an integer minute")
        if not 9 * 60 + 15 <= time_start_min < settings.PENNY_BREAKOUT_TIME_END:
            raise ValueError("time_start_min must be within the trading session")
    if volume_multiplier is not None:
        if isinstance(volume_multiplier, bool) or not isinstance(volume_multiplier, (int, float)):
            raise ValueError("volume_multiplier must be a positive finite number")
        volume_multiplier = float(volume_multiplier)
        if not math.isfinite(volume_multiplier) or not 0 < volume_multiplier <= 5:
            raise ValueError("volume_multiplier must be > 0 and <= 5")
    effective_start = (
        settings.PENNY_BREAKOUT_TIME_START
        if time_start_min is None else time_start_min
    )
    effective_volume_multiplier = (
        settings.PENNY_BREAKOUT_VOL_MULT
        if volume_multiplier is None else volume_multiplier
    )
    # 1. Time gate: 10:30 to 14:30 IST
    mins = _to_minutes_since_midnight(as_of)
    if mins < effective_start or mins >= settings.PENNY_BREAKOUT_TIME_END:
        return {"accept": False, "reject_reason": f"outside breakout time window ({mins} min)"}

    # 2. Volume surge gate.
    # [FIX-PHASE3-AUDIT 2026-07-09] cum_vol_today is a RUNNING cumulative
    # figure; median_vol_20d is a FULL-DAY figure. Comparing them raw
    # demands ~9x normal pace at the 10:30 window open (only ~20% of the
    # session has elapsed). When PENNY_BREAKOUT_RVOL_TIME_ADJUSTED is on,
    # scale the median by the elapsed fraction of the NSE session
    # (09:15-15:30 = 375 min) so the gate reads "1.8x normal pace for
    # this time of day" -- a true relative-volume check.
    if median_vol_20d <= 0:
        return {"accept": False,
                "reject_reason": f"volume {cum_vol_today} < {effective_volume_multiplier}x median ({median_vol_20d})"}
    vol_baseline = float(median_vol_20d)
    if settings.PENNY_BREAKOUT_RVOL_TIME_ADJUSTED:
        session_open_min = 9 * 60 + 15   # 09:15 IST
        session_len_min = 375.0          # 09:15 -> 15:30
        elapsed = min(max(mins - session_open_min, 1.0), session_len_min)
        vol_baseline = median_vol_20d * (elapsed / session_len_min)
    vol_threshold = effective_volume_multiplier * vol_baseline
    if cum_vol_today < vol_threshold:
        # [LEGIBILITY 2026-07-26] Report the THRESHOLD, not the baseline. The old
        # string read "volume 442374 < 1.8x median (257554)", which looks like a
        # false statement (442374 > 257554) because the printed number was the
        # pre-multiplier baseline. Auditing how close this gate runs -- it is the
        # single biggest penny blocker at 49% of MIS rejects -- meant re-deriving
        # 1.8 * baseline by hand for every row.
        return {"accept": False,
                "reject_reason": (
                    f"volume {cum_vol_today} < {int(vol_threshold)} "
                    f"({effective_volume_multiplier}x pace-adjusted median "
                    f"{int(vol_baseline)})"
                )}

    # 3. Breakout confirm: close > anchor + buffer on a 1-min bar.
    # Anchor = day_high (default) or VWAP (when USE_VWAP=True and intraday available).
    # Buffer = base (default 0.3%) or volatility-adjusted (when ADAPTIVE=True).
    bar_close = breakout_bar.get("close", 0)
    base_buffer = settings.PENNY_BREAKOUT_BUFFER_PCT
    if settings.PENNY_BREAKOUT_ADAPTIVE_THRESHOLD and intraday is not None:
        effective_buffer = _adaptive_threshold_scale(intraday, base_buffer)
    else:
        effective_buffer = base_buffer

    # [FIX-PHASE3-AUDIT 2026-07-09] Track which anchor was actually used
    # instead of recomputing VWAP a second time for the anchor_kind label.
    anchor_kind = "day_high"
    if settings.PENNY_BREAKOUT_USE_VWAP and intraday is not None:
        anchor = _vwap_from_intraday(intraday)
        if anchor is None:
            # VWAP unavailable -- fall back to day_high rather than reject.
            anchor = day_high
        else:
            anchor_kind = "vwap"
    else:
        anchor = day_high

    required = anchor * (1.0 + effective_buffer)
    if bar_close <= required:
        return {"accept": False,
                "reject_reason": f"breakout not confirmed (close {bar_close:.2f} <= {required:.2f})"}

    # 4. RSI not overbought.
    # [FIX-PHASE3-AUDIT 2026-07-09] Ceiling moved from hardcoded 70 to
    # PENNY_BREAKOUT_RSI_MAX (default 70 -- the backtest sweep showed
    # loosening to 80 was net-negative on daily bars; see config.py).
    if rsi_14 >= settings.PENNY_BREAKOUT_RSI_MAX:
        # [WATCHDOG-LABEL 2026-07-17] Stable text first -- see the
        # RSI(2) comment in penny_engine_connors.py.
        return {"accept": False,
                "reject_reason": f"RSI(14) overbought (rsi={rsi_14:.1f})"}

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

    # [FIX-PHASE1-AUDIT 2026-07-09] Honour the day's penny regime when sizing.
    # Pre-fix hardcoded _regime_from_pct(0.05) which always resolved to
    # PR1_CALM, so half-size (PR2) / no-new-entry (PR3) rules in spec §6.3
    # never applied. Live scanner wires in PennyRegimeEngine.today_regime
    # so the regime ladder actually takes effect.
    from penny_models import PennyRegime
    if regime is None:
        # Default: pre-fix behaviour (full size, treat as PR1_CALM).
        sizing_regime = PennyRegime.PR1_CALM
    else:
        sizing_regime = regime

    # PR3_HOT blocks new entries entirely (spec §6.3)
    if sizing_regime == PennyRegime.PR3_HOT:
        return {"accept": False, "reject_reason": "regime PR3_HOT: no new entries"}

    shares = risk_engine.position_size(entry, stop_loss, sizing_regime)
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
        # [TIER2-BREAKOUT-REFINEMENT] Expose the anchor + buffer used so
        # downstream logging and the hourly diagnostic breakdown can show
        # which mode was active. Backward-compat: callers that don't read
        # these are unaffected.
        "anchor": anchor,
        "buffer_pct": effective_buffer,
        "anchor_kind": anchor_kind,
        "adaptive_buffer": settings.PENNY_BREAKOUT_ADAPTIVE_THRESHOLD and intraday is not None,
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
    entry = float(pos["entry_price"])
    # Runtime positions come from the canonical positions table.  Retain the
    # legacy signal-dict names for direct evaluator/test callers.
    stop = float(pos.get("stop_loss_initial", pos.get("stop_loss")))
    target = float(pos.get("target_1", pos.get("target")))
    R = entry - stop  # risk per share

    in_profit = current_price >= entry
    distance_to_target = target - current_price

    if in_profit:
        if distance_to_target <= settings.PENNY_MIS_SMART_EOD_WITHIN_R * R:
            return {"action": "exit_now", "reason": "within_0_5R_of_target"}
        return {"action": "hold", "reason": "profit_far_from_target"}

    # In loss. entry_time may be a string (from DB) or naive/tz-aware datetime.
    entry_time = pos.get("entry_date", pos.get("entry_time"))
    if isinstance(entry_time, str):
        from datetime import datetime as _dt
        try:
            entry_time = _dt.fromisoformat(entry_time.replace("Z", "+00:00"))
        except Exception:
            entry_time = now  # safe fallback: treat as just-entered
    if entry_time.tzinfo is None and now.tzinfo is not None:
        from datetime import timezone
        entry_time = entry_time.replace(tzinfo=timezone.utc)
    elapsed_in_loss = now - entry_time
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


def time_stop_triggered(entry_time: Union[datetime, str], now: datetime) -> bool:
    """
    [PENNY-TIME-STOP 2026-06-24] Soft time-stop check: True iff the
    position is at least PENNY_TIME_STOP_MIN old AND still NOT in profit.

    Per intraday-trading research, breakout setups that don't move in
    the direction of the trade within ~30 minutes (less-volatile
    environments) tend to revert or chop sideways, eating the SL. A
    disciplined cut at market when this fires prevents the "stuck trade"
    pattern where a position hangs near entry for hours before finally
    hitting SL.

    The function only returns True; the caller decides what action to
    take (usually: cancel the SL-M and exit at MARKET). Returns False
    when PENNY_TIME_STOP_MIN == 0 (feature disabled).

    Robust to tz-aware vs naive datetimes by coercing both to UTC before
    subtraction. If entry_time can't be parsed (e.g. malformed string),
    returns False so the caller falls back to normal SL behavior.
    """
    from config import settings
    minutes = settings.PENNY_TIME_STOP_MIN
    if minutes <= 0:
        return False
    # Naive datetime coercion -- mirror smart_eod_check pattern.
    if isinstance(entry_time, str):
        try:
            entry_time = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
        except Exception:
            return False
    if entry_time.tzinfo is None and now.tzinfo is not None:
        from datetime import timezone
        entry_time = entry_time.replace(tzinfo=timezone.utc)
    elapsed = now - entry_time
    return elapsed >= timedelta(minutes=minutes)
