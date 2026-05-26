"""
indicators_adaptive.py — Adaptive indicator calculations.

Replaces fixed thresholds with stock-specific relative measures:
  1. RSI Percentile: current RSI vs its own 6-month rolling distribution
  2. Volume Z-Score: current volume vs its own 20-day rolling distribution

These are computed per-stock and per-scan, so they adapt to each stock's
natural volatility range rather than applying a one-size-fits-all threshold.
"""

import pandas as pd
from typing import Optional

from config import settings
from models import Regime


class AdaptiveIndicators:
    """
    Provides adaptive (stock-specific) indicator calculations.

    RSI percentile and volume z-score are computed relative to each stock's
    own recent history, not absolute fixed thresholds.
    """

    def __init__(self, window_rsi: int = 126, window_vol: int = 20):
        """
        Args:
            window_rsi: Number of trading days for RSI history (~126 = 6 months)
            window_vol: Number of trading days for volume history (~20 = 1 month)
        """
        self.window_rsi = window_rsi
        self.window_vol = window_vol

    # ------------------------------------------------------------------
    # RSI Percentile
    # ------------------------------------------------------------------

    def compute_rsi_percentile(
        self,
        current_rsi: float,
        rsi_history: pd.Series,
    ) -> float:
        """
        Compute the percentile rank of current_rsi within rsi_history.

        Returns a value 0-100:
          0  = RSI is at the lowest point in the history window
          50 = RSI is at the median of the history window
          100 = RSI is at the highest point in the history window

        Requires at least 20 historical readings. Returns 0.0 if insufficient data.

        Args:
            current_rsi: The current RSI_14 reading
            rsi_history: A pandas Series of historical RSI_14 values
        """
        if len(rsi_history) < 20:
            return 0.0

        # Use only the most recent `window_rsi` readings
        hist = rsi_history.tail(self.window_rsi).dropna()
        if len(hist) < 20:
            return 0.0

        # Percentile rank: what % of historical readings were below current
        count_below = (hist < current_rsi).sum()
        percentile = (count_below / len(hist)) * 100.0
        return float(round(percentile, 2))

    def get_rsi_percentile_threshold(self, regime: Regime) -> Optional[float]:
        """Return the RSI percentile threshold for a given regime.
        
        R1 (Normal)    → 20.0 (bottom 20% of RSI history)
        R2 (Elevated)  → 15.0 (bottom 15% — tighter)
        R3 (Crisis)    → None (RSI percentile not used; RS vs Nifty filter applies instead)
        UNKNOWN        → 20.0 (same as R1, safe default)
        """
        if regime == Regime.REGIME_2_ELEVATED:
            return settings.RSI_PERCENTILE_REGIME2
        elif regime == Regime.REGIME_3_CRISIS:
            return None  # Not used in R3 — RS vs Nifty filter is the primary gate
        return settings.RSI_PERCENTILE_REGIME1  # R1 and UNKNOWN

    # ------------------------------------------------------------------
    # Volume Z-Score
    # ------------------------------------------------------------------

    def compute_volume_zscore(
        self,
        current_volume: float,
        volume_history: pd.Series,
    ) -> float:
        """
        Compute the z-score of current_volume relative to its 20-day history.

        z-score = (current - mean) / std_dev

        Returns 0.0 if there is insufficient volume history (less than 20 days).

        Interpretation:
          z = 0.0  → volume is exactly at the 20-day average
          z = 1.5  → volume is 1.5 standard deviations above average (unusual)
          z = 2.5  → volume is 2.5 standard deviations above average (highly unusual)
          z = -1.0 → volume is 1 std dev below average (below normal)

        A positive z-score is required for a breakout signal.
        """
        if len(volume_history) < self.window_vol:
            return 0.0

        hist = volume_history.tail(self.window_vol).dropna()
        if len(hist) < self.window_vol:
            return 0.0

        mean_vol = hist.mean()
        std_vol = hist.std(ddof=0)  # Population std (not sample)

        if std_vol == 0:
            return 0.0

        zscore = (current_volume - mean_vol) / std_vol
        return float(round(zscore, 4))

    def get_volume_zscore_threshold(self, regime: Regime) -> float:
        """Return volume z-score threshold for the given regime.
        
        R1 (Normal)    → 1.5  — loose, allow quieter setups
        R2 (Elevated)  → 2.0  — stricter, require confirmation
        R3 (Crisis)    → 2.5  — strictest
        UNKNOWN        → 1.5  — safe default (same as R1)
        """
        if regime == Regime.REGIME_2_ELEVATED:
            return settings.VOL_ZSCORE_REGIME2
        elif regime == Regime.REGIME_3_CRISIS:
            return settings.VOL_ZSCORE_REGIME3
        else:
            # R1_NORMAL and UNKNOWN both use R1 threshold
            return settings.VOL_ZSCORE_REGIME1

    # ------------------------------------------------------------------
    # Relative Strength vs Nifty
    # ------------------------------------------------------------------

    def compute_rs_vs_nifty(
        self,
        stock_return_1d: float,
        nifty_return_1d: float,
    ) -> float:
        """
        Compute relative strength of stock vs Nifty 50 over 1 day.

        Returns the decimal difference:
          0.05  = stock outperformed Nifty by 5 percentage points today
          -0.03 = stock underperformed Nifty by 3 percentage points today

        Used in Regime 3 as the primary signal filter (must be > 0.05).
        """
        return round(stock_return_1d - nifty_return_1d, 6)

    def rs_vs_nifty_passes(self, rs_vs_nifty: float, regime: Regime) -> bool:
        """Check if RS vs Nifty passes the threshold for the given regime."""
        if regime != Regime.REGIME_3_CRISIS:
            return True  # Only applies in Regime 3
        return rs_vs_nifty >= settings.RS_VS_NIFTY_THRESHOLD