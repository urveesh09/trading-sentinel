import pandas as pd
import numpy as np
import math
import structlog
from typing import Dict, Any, Tuple

from config import settings

logger = structlog.get_logger()


# ---------------------------------------------------------
# INDICATORS
# ---------------------------------------------------------

def calc_ema(n: int, prices: pd.Series) -> pd.Series:
    return prices.ewm(span=n, adjust=False, min_periods=n).mean()


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder ATR
    return true_range.ewm(alpha=1/14, adjust=False, min_periods=14).mean()


def calc_volume_ratio(volume: pd.Series, n: int = 20) -> float:
    if len(volume) < n + 1:
        return 0.0

    avg_vol = volume.iloc[-(n+1):-1].mean()
    if avg_vol == 0:
        return 0.0

    return float(volume.iloc[-1]) / avg_vol


def calc_rsi(close: pd.Series, length: int = 14) -> float:
    prices = np.asarray(close, dtype=float)

    if len(prices) < length + 1:
        return 0.0

    deltas = np.diff(prices)

    gains = np.maximum(deltas, 0)
    losses = np.maximum(-deltas, 0)

    avg_gain = gains[:length].mean()
    avg_loss = losses[:length].mean()

    for i in range(length, len(deltas)):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length

    if avg_gain == 0 and avg_loss == 0:
        return 50.0

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return round(rsi, 4)


def calc_slope(series: pd.Series, n: int = 5) -> float:
    if len(series) < n:
        return 0.0

    y = series.iloc[-n:].values
    x = np.arange(n)

    slope = np.polyfit(x, y, 1)[0]

    last_price = series.iloc[-1]

    if last_price == 0:
        return 0.0

    return float(slope / last_price)


# ---------------------------------------------------------
# SIGNAL ENGINE
# ---------------------------------------------------------

def evaluate_signal(
    ticker: str,
    df: pd.DataFrame,
    bankroll: float,
    risk_pct: float,
    market_regime: str = "BULL"
) -> Tuple[bool, Dict[str, Any]]:

    if len(df) < 200:
        return False, {"reject_reason": "insufficient_data_200_days"}
    df = df.copy()
    close = df["close"]

    ema21 = calc_ema(21, close)
    ema50 = calc_ema(50, close)
    ema200 = calc_ema(200, close)

    atr14 = calc_atr(df["high"], df["low"], close)

    c = close.iloc[-1]
    e21 = ema21.iloc[-1]
    e50 = ema50.iloc[-1]
    e200 = ema200.iloc[-1]
    a14 = atr14.iloc[-1]

    vol_ratio = calc_volume_ratio(df["volume"])
    rsi14 = calc_rsi(close)
    slope5 = calc_slope(close)

    avg_20d_vol = df["volume"].iloc[-21:-1].mean()

    # -----------------------------------------------------
    # FILTERS
    # -----------------------------------------------------

    # [RS-FILTER] In BEAR_RS_ONLY mode, we bypass the absolute trend check (C1)
    if market_regime != "BEAR_RS_ONLY":
        if not (c > e200 and e50 > e200):
            return False, {"reject_reason": "trend_filter_failed", "close": c, "ema50": e50, "ema200": e200}
    
    # All other filters (C2-C8) still apply
    if not (e21 * 0.93 <= c <= e21 * 1.20):  # widened from 97–110% to 93–120%
        return False, {"reject_reason": "ema21_proximity_failed", "close": c, "ema21": e21}

    if vol_ratio < 1.2:  # lowered from 1.5x to 1.2x
        return False, {"reject_reason": "volume_ratio_low", "vol_ratio": vol_ratio}

    if not (45 <= rsi14 <= 72):
        return False, {"reject_reason": "rsi_out_of_range", "rsi": rsi14}

    if c < 50:
        return False, {"reject_reason": "price_too_low", "close": c}

    if avg_20d_vol < 100_000:
        return False, {"reject_reason": "avg_volume_low", "avg_20d_vol": avg_20d_vol}

    if slope5 <= 0:
        return False, {"reject_reason": "negative_slope", "slope": slope5}

    if a14 <= 0:
        return False, {"reject_reason": "invalid_atr", "atr": a14}

    # -----------------------------------------------------
    # RISK MANAGEMENT
    # -----------------------------------------------------

    atr_stop = c - (1.5 * a14)
    pct_stop = c * 0.95

    stop_loss = max(atr_stop, pct_stop)

    risk_per_trade = bankroll * risk_pct
    risk_per_share = c - stop_loss

    if risk_per_share <= 0:
        logger.warning("negative_risk_per_share", ticker=ticker)
        return False, {"reject_reason": "negative_risk_per_share"}

    raw_shares = risk_per_trade / risk_per_share
    shares = math.floor(raw_shares)

    if shares <= 0:
        logger.info("shares_zero", ticker=ticker)
        return False, {"reject_reason": "zero_shares_calculated", "risk_per_trade": risk_per_trade, "risk_per_share": risk_per_share}

    capital_required = shares * c

    if capital_required > bankroll:
        return False, {"reject_reason": "insufficient_bankroll", "required": capital_required, "available": bankroll}


    # -----------------------------------------------------
    # TARGETS
    # -----------------------------------------------------

    r_distance = c - stop_loss

    target_1 = c + (1.5 * r_distance)
    target_2 = c + (3.0 * r_distance)

    # -----------------------------------------------------
    # EXPECTED VALUE
    # -----------------------------------------------------

    # Accurate cost model
    # Estimate exit at T2 for cost calculation
    total_round_trip = calc_zerodha_costs(c, target_2, shares, is_intraday=False, for_gate=True)

    gross_profit_t1 = (target_1 - c) * shares * 0.5
    gross_profit_t2 = (target_2 - c) * shares * 0.5

    gross_profit = gross_profit_t1 + gross_profit_t2

    net_ev = gross_profit - total_round_trip

    if net_ev <= 0:
        logger.warning("negative_net_ev", ticker=ticker)
        return False, {"reject_reason": "negative_net_ev", "net_ev": net_ev}


    # -----------------------------------------------------
    # SIGNAL SCORE
    # -----------------------------------------------------

    score = 0

    if vol_ratio >= 2.5:
        score += 30
    elif vol_ratio >= 2.0:
        score += 25
    elif vol_ratio >= 1.5:
        score += 15

    if 50 <= rsi14 <= 65:
        score += 20
    elif 65 < rsi14 <= 72:
        score += 10

    if c > e50:
        score += 15

    stop_pct = (c - stop_loss) / c

    if stop_pct < 0.03:
        score += 20
    elif stop_pct < 0.05:
        score += 10

    if avg_20d_vol >= 1_000_000:
        score += 15
    elif avg_20d_vol >= 500_000:
        score += 10
    elif avg_20d_vol >= 100_000:
        score += 5

    if slope5 > 0.002:
        score += 10
    elif slope5 > 0:
        score += 5

    if net_ev >= risk_per_trade * 2:
        score += 10

    score = min(score, 100)

    # -----------------------------------------------------
    # RESULT
    # -----------------------------------------------------

    res = {
        "close": c,
        "ema_21": e21,
        "ema_50": e50,
        "ema_200": e200,
        "atr_14": a14,
        "volume_ratio": vol_ratio,
        "rsi_14": rsi14,
        "slope_5": slope5,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "shares": shares,
        "capital_deployed": capital_required,
        "capital_at_risk": shares * (c - stop_loss),
        "net_ev": net_ev,
        "score": score,
        "trailing_stop": stop_loss
    }

    return True, res


def calc_zerodha_costs(
    entry_price: float,
    exit_price: float,
    shares: int,
    is_intraday: bool,
    for_gate: bool = False
) -> float:
    """
    Accurate Zerodha cost model for NSE equity trades.
    
    Delivery (CNC): STT on sell side only (0.1%)
    Intraday (MIS): STT on sell side only (0.025%)
    
    When for_gate=True, brokerage (₹20 cap), STT, and GST are zeroed
    for signal viability checks only. Actual P&L tracking always uses
    the full cost model (for_gate=False).
    
    Returns total round-trip cost in rupees.
    """
    buy_value  = entry_price * shares
    sell_value = exit_price  * shares

    # Exchange transaction charges (NSE): 0.00345% both sides
    exchange_txn = (buy_value + sell_value) * settings.ZERODHA_EXCHANGE_PCT

    # Stamp duty: 0.015% on buy side only
    stamp_duty = buy_value * settings.ZERODHA_STAMP_DUTY_PCT

    # SEBI turnover fee: ₹10 per crore = 0.0001% both sides
    sebi = (buy_value + sell_value) * settings.ZERODHA_SEBI_PCT

    # ── TEMPORARY: Brokerage + STT + GST zeroed for gate calculations ──
    # At ₹5,000 bankroll the ₹20 flat brokerage + STT + GST kill most
    # viable signals.  These are skipped ONLY for signal viability gates;
    # actual P&L tracking (position_tracker, close_position) still uses
    # the full cost model.
    # TODO(urveesh): Remove for_gate bypass when bankroll reaches ₹50,000+
    if for_gate:
        brokerage_buy  = 0.0
        brokerage_sell = 0.0
        stt            = 0.0
        gst            = 0.0
    else:
        # Brokerage: min(0.03% of turnover, ₹20) per executed order
        brokerage_buy  = min(buy_value  * settings.ZERODHA_BROKERAGE_PCT, settings.ZERODHA_BROKERAGE_MAX)
        brokerage_sell = min(sell_value * settings.ZERODHA_BROKERAGE_PCT, settings.ZERODHA_BROKERAGE_MAX)

        # STT (Securities Transaction Tax) - sell side only
        stt_rate = settings.ZERODHA_STT_MIS if is_intraday else settings.ZERODHA_STT_CNC
        stt = sell_value * stt_rate

        # GST: 18% on (brokerage + exchange charges)
        gst = (brokerage_buy + brokerage_sell + exchange_txn) * settings.ZERODHA_GST_PCT


    total = (brokerage_buy + brokerage_sell + stt +
             exchange_txn + stamp_duty + sebi + gst)

    return round(total, 4)


def is_cost_viable(
    entry_price: float,
    shares: int,
    risk_per_trade: float,
    r_target: float = 2.0,
    max_cost_ratio: float = 0.25,
    is_intraday: bool = True
) -> tuple[bool, float]:
    """
    Rejects momentum trades where costs eat >25% of expected profit.
    Uses estimated exit at r_target x R above entry.
    Returns (is_viable, cost_ratio).
    """
    r_distance     = risk_per_trade / shares   # stop distance per share
    estimated_exit = entry_price + (r_target * r_distance)
    total_cost     = calc_zerodha_costs(
        entry_price, estimated_exit, shares, is_intraday, for_gate=True
    )
    expected_gross = risk_per_trade * r_target
    cost_ratio     = total_cost / expected_gross if expected_gross > 0 else 1.0
    return cost_ratio <= max_cost_ratio, round(cost_ratio, 4)


def calc_relative_strength(
    stock_close: pd.Series,
    nifty_close: pd.Series,
    periods: int = 20
) -> float:
    """
    [RS1] Relative Strength vs Nifty 50 over N periods.
    RS = stock_return_pct - nifty_return_pct over last `periods` bars.
    Positive RS = stock outperforming Nifty.
    """
    if len(stock_close) < periods + 1 or len(nifty_close) < periods + 1:
        return -999.0   # sentinel: insufficient data

    stock_return = (stock_close.iloc[-1] - stock_close.iloc[-periods]) \
                   / stock_close.iloc[-periods] * 100
    nifty_return = (nifty_close.iloc[-1] - nifty_close.iloc[-periods]) \
                   / nifty_close.iloc[-periods] * 100

    return round(stock_return - nifty_return, 4)



def calc_vwap(df: pd.DataFrame) -> pd.Series:
    """
    [MOM1] VWAP calculation for intraday candles.
    VWAP = cumsum(typical_price × volume) / cumsum(volume)
    Typical price = (high + low + close) / 3
    Resets at start of each day - caller must pass only today's candles.
    df must have columns: high, low, close, volume
    Returns pd.Series indexed same as df.
    """
    typical_price  = (df['high'] + df['low'] + df['close']) / 3
    cumulative_tpv = (typical_price * df['volume']).cumsum()
    cumulative_vol = df['volume'].cumsum()
    vwap = cumulative_tpv / cumulative_vol
    return vwap

def calc_volume_consistency(volume: pd.Series, n_days: int = 5,
                            lookback: int = 20) -> bool:
    if len(volume) < lookback + n_days + 1:
        return False
    avg_vol = volume.iloc[-(lookback + n_days + 1):-(n_days + 1)].mean()
    recent_vols = volume.iloc[-n_days-1:-1]   # last 5 completed sessions
 
    days_above = sum(1 for v in recent_vols if v > avg_vol)
    return days_above >= 3

def evaluate_momentum_signal(
    ticker: str,
    df: pd.DataFrame,
    prev_day_high: float,
    bankroll: float,
    momentum_pool: float,
    min_candles: int = 4,
    df_daily: "pd.DataFrame | None" = None,
    vol_surge_threshold: float = 1.5,
    market_regime: str = "BULL",
) -> tuple[bool, dict]:
    """
    [MOM2] Intraday momentum signal evaluation.
    df must contain ONLY today's 15-minute candles (VWAP resets daily).
    df_daily must contain at least 14 daily OHLCV rows for ATR calculation (MC5).

    Entry conditions (ALL must be true):
      [MC1] Minimum candles: len(df) >= min_candles
      [MC2] Price crossed ABOVE VWAP in the LAST 3 candles + holding check
      [MC3] Last candle volume >= vol_surge_threshold (time-aware, set by caller)
            [MC3-T] Caller raises threshold to 1.75x during 11:30-13:15 IST
      [MC4] Current close in top 20% of today's intraday session range
      [MC5] Daily ATR exhaustion: target_distance <= remaining_fuel * ATR_FUEL_BUFFER
      [MC6] Morphology: close_position_score >= MOMENTUM_MORPHOLOGY_MIN_SCORE

    Risk:
      [MR1] Stop loss = low of the breakout candle (last candle)
      [MR2] Target = r_target x R  where r_target is regime-adjusted:
            BULL: settings.MOMENTUM_R_TARGET (2.0)
            BEAR_RS_ONLY: settings.MOMENTUM_R_TARGET_BEAR (1.5)
      [MR3] Product type decision: MIS if position_value < 5000, else CNC
    """
    if len(df) < min_candles:
        return False, {"reject_reason": "min_candles_not_met", "count": len(df)}

    df = df.copy()
    vwap = calc_vwap(df)

    current_close = df['close'].iloc[-1]
    prev_close    = df['close'].iloc[-2]
    current_vwap  = vwap.iloc[-1]
    prev_vwap     = vwap.iloc[-2]

        # [MC2] VWAP crossover: was below, now above (Lookback 3 candles to avoid "sniper blindness")
    # This checks if the crossover happened in any of the last 3 candles.
    crossed = False
    for i in range(1, 4): # Check index -1, -2, -3
        if len(df) < i + 1:
            break
        c_close = df['close'].iloc[-i]
        p_close = df['close'].iloc[-(i+1)]
        c_vwap  = vwap.iloc[-i]
        p_vwap  = vwap.iloc[-(i+1)]
        
        if p_close <= p_vwap and c_close > c_vwap:
            crossed = True
            break
            
    if not crossed:
        return False, {
            "reject_reason": "no_recent_vwap_crossover", 
            "current_close": current_close, 
            "current_vwap": current_vwap
        }


    # [MC2.1] Holding Check: Ensure we haven't crashed back below VWAP right now
    if current_close <= current_vwap:
        return False, {
            "reject_reason": "crossed_but_failed_holding_vwap",
            "current_close": current_close,
            "current_vwap": current_vwap
        }

    # [MC3] Volume surge: Use setting from config

    if len(df) < 2:

        return False, {"reject_reason": "insufficient_candles_for_vol"}

    # Use whatever candles we have (up to 10) for the average
    lookback = min(len(df) - 1, 10)
    avg_vol_lookback = df['volume'].iloc[-lookback-1:-1].mean()

    if avg_vol_lookback == 0:
        return False, {"reject_reason": "zero_avg_volume"}

    current_vol = df['volume'].iloc[-1]
    vol_ratio_intraday = current_vol / avg_vol_lookback
    if vol_ratio_intraday < vol_surge_threshold:   # [MC3-T] threshold is time-aware; elevated during lunchtime by caller
        return False, {
            "reject_reason":      "MC3_volume_surge_insufficient",
            "vol_ratio":          round(vol_ratio_intraday, 3),
            "vol_threshold_used": round(vol_surge_threshold, 3),
        }


    # [MC4] REPLACED: Close must be in top 20% of today's intraday session range (intraday strength).
    # Old [MC4] gate (price > prev_day_high) is preserved below - uncomment to re-enable [Q13].
    intraday_high = df['high'].max()
    intraday_low  = df['low'].min()
    intraday_range = intraday_high - intraday_low
    if intraday_range > 0 and current_close < (intraday_low + 0.80 * intraday_range):
        return False, {
            "reject_reason": "not_in_top_20pct_intraday_range",
            "close": current_close,
            "intraday_low": round(intraday_low, 2),
            "intraday_high": round(intraday_high, 2),
            "threshold": round(intraday_low + 0.80 * intraday_range, 2),
        }
    # [MC4-LEGACY - commented out] Structural breakout: above previous day's high.
    # Uncomment to restore strict prev-day-high gate for confirmed breakout strategy.
    # if current_close <= prev_day_high:
    #     return False, {"reject_reason": "below_prev_day_high", "close": current_close, "prev_high": prev_day_high}

    # [MC6] Morphology gate — reject shooting-star and doji candles
    # A close near the bottom of the candle's range signals seller control.
    last_high    = float(df["high"].iloc[-1])
    last_low     = float(df["low"].iloc[-1])
    candle_range = last_high - last_low
    if candle_range <= 0.0:
        return False, {
            "reject_reason": "MC6_doji_candle",
            "close_position_score": 0.0,
        }
    close_position_score = round((current_close - last_low) / candle_range, 4)
    if close_position_score < settings.MOMENTUM_MORPHOLOGY_MIN_SCORE:
        return False, {
            "reject_reason": "MC6_shooting_star",
            "close_position_score": close_position_score,
            "morphology_threshold": settings.MOMENTUM_MORPHOLOGY_MIN_SCORE,
        }

    # [MR1] Stop loss = low of breakout candle
    breakout_candle_low = df['low'].iloc[-1]
    stop_loss = breakout_candle_low

    risk_per_share = current_close - stop_loss
    if risk_per_share <= 0:
        return False, {"reject_reason": "negative_risk_per_share"}

    # Position sizing: User-defined 7% risk of momentum pool
    momentum_risk = momentum_pool * settings.MOMENTUM_RISK_PCT
    shares = math.floor(momentum_risk / risk_per_share)
    if shares == 0:

        return False, {"reject_reason": "zero_shares_momentum", "risk": momentum_risk, "risk_per_share": risk_per_share}

    position_value = shares * current_close
    
    # [SEBI-COMPLIANCE] Ensure position doesn't exceed pool
    if position_value > momentum_pool:
        # Resize to fit pool if risk allows
        shares = math.floor(momentum_pool / current_close)
        if shares == 0:
            return False, {"reject_reason": "insufficient_pool_for_one_share"}
        position_value = shares * current_close

    # [MR2] Regime-adjusted R target
    effective_r_target: float = (
        settings.MOMENTUM_R_TARGET_BEAR
        if market_regime == "BEAR_RS_ONLY"
        else settings.MOMENTUM_R_TARGET
    )
    r_distance = current_close - stop_loss
    target     = current_close + effective_r_target * r_distance

    # [MR3] Product type decision
    product_type = "MIS" if position_value < 5000 else "CNC"

    # [MC5] Daily ATR exhaustion gate
    # Prevents entry when the day's typical range is already consumed and there is
    # insufficient "fuel" left for price to reach the R-target.
    # calc_atr() requires >= 14 rows; gate skipped if df_daily not provided.
    if df_daily is not None and len(df_daily) >= 14:
        daily_atr_val: float = float(calc_atr(df_daily["high"], df_daily["low"], df_daily["close"]).iloc[-1])
        intraday_consumed: float = float(intraday_high - intraday_low)
        remaining_fuel: float = max(0.0, daily_atr_val - intraday_consumed)
        r_distance_atr: float = float(current_close - stop_loss)
        target_distance: float = r_distance_atr * effective_r_target  # [AUDIT-003] use regime-adjusted target, not hardcoded 2.0R
        if target_distance > remaining_fuel * settings.MOMENTUM_ATR_FUEL_BUFFER:
            return False, {
                "reject_reason":     "MC5_atr_fuel_exhausted",
                "daily_atr":         round(daily_atr_val, 2),
                "intraday_consumed": round(intraday_consumed, 2),
                "remaining_fuel":    round(remaining_fuel, 2),
                "target_distance":   round(target_distance, 2),
                "fuel_buffer":       settings.MOMENTUM_ATR_FUEL_BUFFER,
            }

    # Cost viability check — use effective_r_target so bear-mode trades are assessed
    # against their actual 1.5R projected profit, not the default 2.0R.
    viable, cost_ratio = is_cost_viable(
        entry_price=current_close, shares=shares,
        risk_per_trade=momentum_risk, r_target=effective_r_target,  # [AUDIT-004]
        max_cost_ratio=settings.MOMENTUM_MAX_COST_RATIO, is_intraday=True
    )
    if not viable:
        return False, {"reject_reason": "cost_not_viable", "cost_ratio": cost_ratio}

    # Accurate cost for net_ev — must use effective_r_target to avoid inflated EV in bear mode
    estimated_exit = current_close + (effective_r_target * r_distance)  # [AUDIT-004]
    total_cost = calc_zerodha_costs(
        current_close, estimated_exit, shares, is_intraday=True, for_gate=True
    )
    net_ev = (momentum_risk * effective_r_target) - total_cost  # [AUDIT-004]

    if net_ev <= 0:
        return False, {"reject_reason": "negative_net_ev_final", "net_ev": net_ev}


    result = {
        "close":               round(current_close, 2),
        "vwap":                round(current_vwap, 2),
        "prev_day_high":       round(prev_day_high, 2),
        "stop_loss":           round(stop_loss, 2),
        "target_1":            round(target, 2),
        "target_2":            round(target, 2),   # single target for momentum
        "trailing_stop":       round(stop_loss, 2),
        "shares":              shares,
        "capital_deployed":    round(position_value, 2),
        "capital_at_risk":     round(shares * risk_per_share, 2),
        "net_ev":              round(net_ev, 2),
        "cost_ratio":          cost_ratio,
        "volume_ratio":        round(vol_ratio_intraday, 2),
        "product_type":        product_type,
        "strategy_type":       "MOMENTUM",
        "effective_r_target":  effective_r_target,
        "entry_price":         round(current_close, 2),
        "target":              round(target, 2),
    }
    return True, result

