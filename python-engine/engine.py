import pandas as pd
import numpy as np
import math
import structlog
from typing import Dict, Any, Tuple, Optional

from config import settings
from models import Regime
from indicators_adaptive import AdaptiveIndicators

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
    """
    Compute RSI_14 (Wilder's smoothing method) for the most recent window.
    Returns a single float value (the current RSI).

    For historical RSI series (needed by RSI percentile filter), use
    `calc_rsi_series()` instead. This function is used for the current
    RSI reading only.
    """
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


def calc_rsi_series(close: pd.Series, length: int = 14) -> pd.Series:
    """
    Compute a full RSI_14 series using Wilder's smoothing method.

    Returns a Series of RSI values aligned with the input close prices.
    The first `length` values will be NaN (insufficient data).
    Requires at least `length + 1` prices to produce a valid series.

    Used by the RSI percentile filter in `evaluate_signal` to determine
    where the current RSI sits within its own 6-month historical range.

    OPEN QUESTION RESOLUTION (Task 9): RSI Percentile Persistence
    ──────────────────────────────────────────────────────────────
    Issue: RegimeEngine is instantiated fresh in each main.py scan run,
           so RSI history is lost between scans. The RSI percentile filter
           needs 126 days of history to work correctly.
    Options:
      1. Persist RSI history in SQLite — adds complexity, potential for stale data
      2. Rebuild from OHLC data each scan — recommended in plan; engine.py has
         access to 365 days of data; sufficient to compute 126-day RSI history
      3. In-memory cache across scans — not durable across process restarts

    Decision: Option 2 — `calc_rsi_series()` computes RSI history from the
    existing 365-day OHLC data fetched in main.py. No new persistence layer needed.
    The `evaluate_signal()` function accepts an optional `rsi_history` parameter;
    when provided with ≥20 readings, the RSI percentile filter is used instead
    of the fixed 45-72 range. When None or insufficient, the system falls back
    to the fixed range (graceful degradation — signals still generate).
    """
    prices = np.asarray(close, dtype=float)
    n = len(prices)

    if n < length + 1:
        return pd.Series(np.full(n, np.nan), index=close.index)

    deltas = np.diff(prices)
    gains = np.maximum(deltas, 0)
    losses = np.maximum(-deltas, 0)

    # Seed with SMA for first `length` periods
    avg_gain = gains[:length].mean()
    avg_loss = losses[:length].mean()

    # First valid RSI at index `length` (after seed period)
    rsi_values = np.full(n, np.nan, dtype=float)

    if avg_loss == 0:
        rsi_values[length:] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_values[length] = 100.0 - (100.0 / (1.0 + rs))

    # Wilder smoothing for remaining periods
    for i in range(length + 1, n):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length
        if avg_loss == 0:
            rsi_values[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_values[i] = 100.0 - (100.0 / (1.0 + rs))

    return pd.Series(rsi_values, index=close.index)


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
    regime: Regime = Regime.REGIME_1_NORMAL,
    market_regime: str = "BULL",
    nifty_50_current: Optional[float] = None,
    nifty_ema20: Optional[float] = None,
    nifty_return_1d: Optional[float] = None,
    rsi_history: Optional[pd.Series] = None,
    breadth_rank: Optional[float] = None,
    breadth_pct_above_sma50: Optional[float] = None,
) -> Tuple[bool, Dict[str, Any]]:

    if len(df) < 200:
        return False, {"reject_reason": "insufficient_data_200_days"}
    df = df.copy()

    # -----------------------------------------------------
    # BREADTH ENRICHMENT (Task 6, 2026-06-14)
    # R1 narrow-rally gate runs FIRST, before any signal-quality filter.
    # This is a *market-context* filter, not a signal filter: when breadth
    # is bad, we don't even bother evaluating individual signals. Skipped
    # entirely if breadth data is degraded (breadth_pct is None) or the
    # feature flag is off.
    # -----------------------------------------------------
    narrow_rally_filtered = (
        settings.BREADTH_ENRICHMENT_ENABLED
        and regime == Regime.REGIME_1_NORMAL
        and breadth_pct_above_sma50 is not None
        and breadth_pct_above_sma50 < settings.BREADTH_NARROW_RALLY_THRESHOLD
        and (breadth_rank is None or breadth_rank < settings.BREADTH_NARROW_GATE_EXEMPT_RANK)
    )
    if narrow_rally_filtered:
        return False, {
            "reject_reason": "narrow_rally_filtered",
            "breadth_pct_above_sma50": breadth_pct_above_sma50,
            "breadth_rank": breadth_rank,
            "threshold": settings.BREADTH_NARROW_RALLY_THRESHOLD,
            "exempt_rank": settings.BREADTH_NARROW_GATE_EXEMPT_RANK,
        }
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
    # REGIME-AWARE FILTER SETUP
    # -----------------------------------------------------
    adaptive_ind = AdaptiveIndicators()

    # Score accumulates regime-specific RSI percentile bonus throughout the
    # regime-filter blocks below; line 390's scoring loop then adds to it.
    score: int = 0

    # -----------------------------------------------------
    # FILTERS
    # -----------------------------------------------------

    # ----------------------------------------------------------------
    # REGIME-AWARE FILTER: RSI Percentile (Regime 1 and 2 only)
    # RS vs Nifty filter for Regime 3 applied separately below
    # ----------------------------------------------------------------
    rs_vs_nifty: Optional[float] = None
    rsi_pct: float = 0.0
    if regime == Regime.REGIME_1_NORMAL:
        rsi_pct_threshold = settings.RSI_PERCENTILE_REGIME1  # 20
        if not (0 <= rsi14 <= 100):
            return False, {"reject_reason": "rsi_out_of_range", "rsi": rsi14}
        rsi_pct = adaptive_ind.compute_rsi_percentile(rsi14, rsi_history) if rsi_history is not None else 0.0
        if rsi_history is not None and len(rsi_history) >= 20:
            # Accept: RSI above bottom X% of its 6-month range = not oversold
            # Reject: RSI in bottom X% = too weak / oversold territory
            if rsi_pct < rsi_pct_threshold:
                return False, {"reject_reason": "rsi_percentile_too_low", "rsi_pct": rsi_pct, "threshold": rsi_pct_threshold}
        else:
            if not (45 <= rsi14 <= 72):
                return False, {"reject_reason": "rsi_out_of_range", "rsi": rsi14}
        if rsi_history is not None and len(rsi_history) >= 20:
            # Sweet spot: mid-range percentile (40-60) scores highest; extremes score 0
            score += max(0, int(min(rsi_pct, 20) / 2))
    elif regime == Regime.REGIME_2_ELEVATED:
        rsi_pct_threshold = settings.RSI_PERCENTILE_REGIME2  # 15
        if nifty_50_current is not None and nifty_ema20 is not None:
            if nifty_50_current < nifty_ema20:
                return False, {"reject_reason": "nifty_below_ema20_regime2", "nifty": nifty_50_current, "ema20": nifty_ema20}
        rsi_pct = adaptive_ind.compute_rsi_percentile(rsi14, rsi_history) if rsi_history is not None else 0.0
        if rsi_history is not None and len(rsi_history) >= 20:
            # Accept: RSI above bottom X% of its 6-month range = not oversold
            # Reject: RSI in bottom X% = too weak / oversold territory
            if rsi_pct < rsi_pct_threshold:
                return False, {"reject_reason": "rsi_percentile_too_low", "rsi_pct": rsi_pct, "threshold": rsi_pct_threshold}
        else:
            if not (50 <= rsi14 <= 72):
                return False, {"reject_reason": "rsi_out_of_range", "rsi": rsi14}
        if rsi_history is not None and len(rsi_history) >= 20:
            score += max(0, int(min(rsi_pct, 15) / 2))
    elif regime == Regime.REGIME_3_CRISIS:
        # RS vs Nifty filter (primary — replaces RSI + vol percentile filters)
        stock_return_1d = (close.iloc[-1] / close.iloc[-2] - 1) if len(close) >= 2 else 0.0
        rs_vs_nifty = adaptive_ind.compute_rs_vs_nifty(
            stock_return_1d,
            nifty_return_1d if nifty_return_1d is not None else 0.0,
        )
        if rs_vs_nifty < settings.RS_VS_NIFTY_THRESHOLD:
            return False, {"reject_reason": "rs_vs_nifty_insufficient", "rs_vs_nifty": rs_vs_nifty, "threshold": settings.RS_VS_NIFTY_THRESHOLD}
        vol_zscore_r3 = adaptive_ind.compute_volume_zscore(df["volume"].iloc[-1], df["volume"])
        if vol_zscore_r3 < settings.VOL_ZSCORE_REGIME3:
            return False, {"reject_reason": "volume_zscore_low", "vol_zscore": vol_zscore_r3, "threshold": settings.VOL_ZSCORE_REGIME3}
    else:
        # UNKNOWN regime — apply Regime 1 defaults (no score bonus)
        pass

    # ----------------------------------------------------------------
    # REGIME-AWARE FILTER: Volume Z-Score (Regime 1 and 2 only)
    # ----------------------------------------------------------------
    vol_zscore = adaptive_ind.compute_volume_zscore(df["volume"].iloc[-1], df["volume"])
    vol_zscore_threshold = adaptive_ind.get_volume_zscore_threshold(regime)
    if regime in (Regime.REGIME_1_NORMAL, Regime.REGIME_2_ELEVATED):
        if vol_zscore < vol_zscore_threshold:
            return False, {"reject_reason": "volume_zscore_low", "vol_zscore": vol_zscore, "threshold": vol_zscore_threshold}

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
    # REGIME-AWARE RISK MANAGEMENT
    # -----------------------------------------------------
    atr_mult_map = {
        Regime.REGIME_1_NORMAL: settings.STOP_ATR_REGIME1,
        Regime.REGIME_2_ELEVATED: settings.STOP_ATR_REGIME2,
        Regime.REGIME_3_CRISIS: settings.STOP_ATR_REGIME3,
        Regime.UNKNOWN: settings.STOP_ATR_REGIME1,
    }
    pct_stop_map = {
        Regime.REGIME_1_NORMAL: settings.STOP_PCT_REGIME1,
        Regime.REGIME_2_ELEVATED: settings.STOP_PCT_REGIME2,
        Regime.REGIME_3_CRISIS: settings.STOP_PCT_REGIME3,
        Regime.UNKNOWN: settings.STOP_PCT_REGIME1,
    }
    atr_mult = atr_mult_map[regime]
    pct_stop_pct = pct_stop_map[regime]
    atr_stop = c - (atr_mult * a14)
    pct_stop = c * (1.0 - pct_stop_pct)
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
    # REGIME-AWARE TARGETS
    # -----------------------------------------------------
    r_distance = c - stop_loss

    t1_mult = settings.TARGET1_R
    t2_mult_map = {
        Regime.REGIME_1_NORMAL: settings.TARGET2_R_REGIME1,
        Regime.REGIME_2_ELEVATED: settings.TARGET2_R_REGIME2,
        Regime.REGIME_3_CRISIS: settings.TARGET2_R_REGIME3,
        Regime.UNKNOWN: settings.TARGET2_R_REGIME1,
    }
    t2_mult = t2_mult_map[regime]

    target_1 = c + (t1_mult * r_distance)
    target_2 = c + (t2_mult * r_distance) if t2_mult is not None else None

    # -----------------------------------------------------
    # EXPECTED VALUE
    # -----------------------------------------------------

    # Accurate cost model
    # Estimate exit at T2 for cost calculation
    # For Regime 3 (no T2), use T1 as the exit for cost model
    exit_for_costs = target_2 if target_2 is not None else target_1
    total_round_trip = calc_zerodha_costs(c, exit_for_costs, shares, is_intraday=False, for_gate=True)

    gross_profit_t1 = (target_1 - c) * shares * 0.5
    gross_profit_t2 = ((target_2 - c) * shares * 0.5) if target_2 is not None else 0.0

    gross_profit = gross_profit_t1 + gross_profit_t2

    net_ev = gross_profit - total_round_trip

    if net_ev <= 0:
        logger.warning("negative_net_ev", ticker=ticker)
        return False, {"reject_reason": "negative_net_ev", "net_ev": net_ev}


    # -----------------------------------------------------
    # SIGNAL SCORE
    # -----------------------------------------------------
    # score already carries the regime-specific RSI percentile bonus (from above).
    # The general scoring loop adds to it rather than replacing it.

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
    # BREADTH SCORING BONUS (Task 6, 2026-06-14)
    # Counter-trend enabler: top-breadth stocks get a bonus + 1.2x multiplier
    # even in R2/R3. Bottom-rank stocks get a penalty. Works only when the
    # feature flag is on AND breadth_rank is provided (not degraded).
    # -----------------------------------------------------
    if settings.BREADTH_ENRICHMENT_ENABLED and breadth_rank is not None:
        if breadth_rank >= 0.80:
            score += settings.BREADTH_RANK_BONUS_TOP       # default +15
        elif breadth_rank >= 0.60:
            score += settings.BREADTH_RANK_BONUS_MID       # default +7
        elif breadth_rank < 0.20:
            score += settings.BREADTH_RANK_PENALTY_BOTTOM  # default -10
        # Top quintile also gets a score multiplier to nudge borderline signals
        if breadth_rank >= 0.80:
            score = int(score * settings.BREADTH_RANK_MULTIPLIER)  # default ×1.2
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
        "trailing_stop": stop_loss,
        # Regime metadata
        "regime": regime,
        "narrow_rally_filtered": False,  # Default; True branch is handled by the early-return gate above
        "rsi_percentile": rsi_pct if regime in (Regime.REGIME_1_NORMAL, Regime.REGIME_2_ELEVATED) else None,
        "volume_zscore": vol_zscore,
        "rs_vs_nifty": rs_vs_nifty if regime == Regime.REGIME_3_CRISIS else None,
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


def resolve_momentum_regime_params(
    regime: Optional[Regime],
) -> Tuple[float, float, bool]:
    """
    [MOMENTUM-REGIME 2026-06-16] Pure helper. Resolves the 3-regime
    system into concrete momentum parameters: (r_target, risk_pct, should_block).

    Returns:
      r_target:    R-multiple for the position target
      risk_pct:    Fraction of momentum pool to risk
      should_block: True if the caller should reject the signal entirely
                    (skip MC1-MC6 gates) — applies in Regime 3 with BLOCK=True.

    The legacy market_regime string dispatch (BULL/BEAR_RS_ONLY) lives
    in evaluate_momentum_signal. This function is the NEW 3-regime path.
    When regime is None, falls back to R1 (safe default) — backward compat.

    Settings used:
      MOMENTUM_BLOCK_R3_ENTRIES  — gate to short-circuit in R3
      MOMENTUM_R_TARGET_R1/R2    — target R-multiples
      MOMENTUM_RISK_PCT_R1/R2/R3 — position sizing per regime
    """
    if regime is None or regime == Regime.REGIME_1_NORMAL or regime == Regime.UNKNOWN:
        # R1: 2.0R target, 7% risk. Default for unknown / backward compat.
        return (
            settings.MOMENTUM_R_TARGET_R1,
            settings.MOMENTUM_RISK_PCT_R1,
            False,
        )
    elif regime == Regime.REGIME_2_ELEVATED:
        # R2: tighter target (1.5R) + smaller size (5%). Not blocked —
        # still allow some participation but with discipline.
        return (
            settings.MOMENTUM_R_TARGET_R2,
            settings.MOMENTUM_RISK_PCT_R2,
            False,
        )
    elif regime == Regime.REGIME_3_CRISIS:
        # R3: block by default. If operator disables BLOCK_R3, still
        # give 0% risk so no positions open. Defense in depth.
        return (
            settings.MOMENTUM_R_TARGET_R2,  # conservative r_target (unused when blocked)
            settings.MOMENTUM_RISK_PCT_R3,  # 0% — no shares
            settings.MOMENTUM_BLOCK_R3_ENTRIES,
        )
    else:
        # Unknown enum value — be safe
        logger.warning("momentum_unknown_regime_enum", regime=str(regime))
        return (
            settings.MOMENTUM_R_TARGET_R1,
            settings.MOMENTUM_RISK_PCT_R1,
            False,
        )


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
    regime: "Regime | None" = None,
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

    # [MR-3REG] 3-regime dispatch (overrides legacy 4-state market_regime string)
    # If caller passed regime=None, this is a no-op and we fall through to the
    # legacy logic below. When regime is set, we use the configured R-target +
    # risk_pct for the regime, and gate the entire signal in R3 if BLOCK=True.
    regime_r_target, regime_risk_pct, should_block = resolve_momentum_regime_params(
        regime=regime,
    )
    if should_block:
        return False, {"reject_reason": "regime_r3_block", "regime": regime.name if regime else None}

    # Position sizing: regime-aware risk % of momentum pool
    if regime is not None:
        momentum_risk = momentum_pool * regime_risk_pct
    else:
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
    # Legacy 4-state string path. The 3-regime system (when `regime` is set)
    # overrides this with its configured r_target via the dispatcher above.
    if regime is not None:
        effective_r_target: float = regime_r_target
    else:
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

