import pandas as pd
import numpy as np
import math
import structlog
from typing import Dict, Any, Tuple

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
    risk_pct: float
) -> Tuple[bool, Dict[str, Any]]:

    if len(df) < 200:
        return False, {}
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

    if not (c > e200 and e50 > e200):
        return False, {}

    if not (e21 * 0.97 <= c <= e21 * 1.01):
        return False, {}

    if vol_ratio < 1.5:
        return False, {}

    if not (45 <= rsi14 <= 72):
        return False, {}

    if c < 50:
        return False, {}

    if avg_20d_vol < 100_000:
        return False, {}

    if slope5 <= 0:
        return False, {}

    if a14 <= 0:
        return False, {}

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
        return False, {}

    raw_shares = risk_per_trade / risk_per_share
    shares = math.floor(raw_shares)

    if shares <= 0:
        logger.info("shares_zero", ticker=ticker)
        return False, {}

    capital_required = shares * c

    if capital_required > bankroll:
        return False, {}

    # -----------------------------------------------------
    # TARGETS
    # -----------------------------------------------------

    r_distance = c - stop_loss

    target_1 = c + (1.5 * r_distance)
    target_2 = c + (3.0 * r_distance)

    # -----------------------------------------------------
    # EXPECTED VALUE
    # -----------------------------------------------------

    cost_per_side = c * shares * 0.001
    total_round_trip = cost_per_side * 2

    gross_profit_t1 = (target_1 - c) * shares * 0.5
    gross_profit_t2 = (target_2 - c) * shares * 0.5

    gross_profit = gross_profit_t1 + gross_profit_t2

    net_ev = gross_profit - total_round_trip

    if net_ev <= 0:
        logger.warning("negative_net_ev", ticker=ticker)
        return False, {}

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
