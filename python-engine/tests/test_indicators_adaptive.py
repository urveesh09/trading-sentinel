import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np

from indicators_adaptive import AdaptiveIndicators
from models import Regime


class TestAdaptiveIndicators:
    """Tests for adaptive RSI percentile and volume z-score."""

    def test_rsi_percentile_single_reading(self):
        """RSI percentile should correctly rank current RSI within historical range."""
        ai = AdaptiveIndicators(window_rsi=126)
        # Create a series where RSI has been [30,40,50,60,70] repeatedly
        rsi_history = pd.Series([30.0, 40.0, 50.0, 60.0, 70.0] * 25)
        current_rsi = 35.0
        pct = ai.compute_rsi_percentile(current_rsi, rsi_history)
        # 35 is between 30 and 40, should be in 10-20% range
        assert 10 <= pct <= 20

    def test_rsi_percentile_lowest_ever(self):
        """RSI at the absolute lowest in history should return ~0."""
        ai = AdaptiveIndicators(window_rsi=126)
        rsi_history = pd.Series([50.0, 60.0, 70.0, 80.0] * 30)
        current_rsi = 50.0  # This is the minimum
        pct = ai.compute_rsi_percentile(current_rsi, rsi_history)
        assert pct <= 5.0

    def test_rsi_percentile_highest_ever(self):
        """RSI at the absolute highest in history should return ~100."""
        ai = AdaptiveIndicators(window_rsi=126)
        rsi_history = pd.Series([30.0, 40.0, 50.0, 60.0] * 30)
        # Use a current RSI slightly above max to ensure it's above all history
        current_rsi = 60.1
        pct = ai.compute_rsi_percentile(current_rsi, rsi_history)
        assert pct >= 95.0

    def test_rsi_percentile_insufficient_data(self):
        """Less than 20 days of history should return 0.0 (no signal)."""
        ai = AdaptiveIndicators(window_rsi=126)
        rsi_history = pd.Series([40.0, 50.0, 55.0])  # Only 3 days
        pct = ai.compute_rsi_percentile(45.0, rsi_history)
        assert pct == 0.0

    def test_volume_zscore_normal(self):
        """Volume at mean should give z-score of ~0."""
        ai = AdaptiveIndicators()
        # Constant series: mean = 1M, std = 0 -> z=0 by guard
        vol_history = pd.Series([1_000_000] * 20)
        current_vol = 1_000_000
        z = ai.compute_volume_zscore(current_vol, vol_history)
        assert z == 0.0

    def test_volume_zscore_high(self):
        """Volume 2 std devs above mean should give z-score of ~2."""
        ai = AdaptiveIndicators()
        # Std of ~222K, mean of 1M. For z=2: need 1M+2*222K=1.44M
        vol_history = pd.Series([800_000] * 19 + [800_000])  # mean=800K, std=0 -> bad
        vol_history = pd.Series([500_000, 800_000, 900_000, 1_000_000, 1_100_000,
                                  1_200_000, 1_300_000, 1_400_000, 1_500_000, 1_600_000,
                                  500_000, 800_000, 900_000, 1_000_000, 1_100_000,
                                  1_200_000, 1_300_000, 1_400_000, 1_500_000, 1_600_000])
        mean = vol_history.mean()
        std = vol_history.std(ddof=0)
        current_vol = mean + (2.1 * std)  # ~2 std devs above
        z = ai.compute_volume_zscore(current_vol, vol_history)
        assert z > 1.8

    def test_volume_zscore_insufficient_data(self):
        """Less than 20 days of history should return 0.0 (no signal)."""
        ai = AdaptiveIndicators()
        vol_history = pd.Series([1_000_000] * 5)  # Only 5 days
        current_vol = 2_000_000
        z = ai.compute_volume_zscore(current_vol, vol_history)
        assert z == 0.0

    def test_regime_thresholds_r1(self):
        """Regime 1 should use least strict thresholds."""
        ai = AdaptiveIndicators()
        assert ai.get_rsi_percentile_threshold(Regime.REGIME_1_NORMAL) == 20.0
        assert ai.get_volume_zscore_threshold(Regime.REGIME_1_NORMAL) == 1.5

    def test_regime_thresholds_r2(self):
        """Regime 2 should use tighter thresholds."""
        ai = AdaptiveIndicators()
        assert ai.get_rsi_percentile_threshold(Regime.REGIME_2_ELEVATED) == 15.0
        assert ai.get_volume_zscore_threshold(Regime.REGIME_2_ELEVATED) == 2.0

    def test_regime_thresholds_r3(self):
        """Regime 3 should use highest volume z-score threshold."""
        ai = AdaptiveIndicators()
        assert ai.get_volume_zscore_threshold(Regime.REGIME_3_CRISIS) == 2.5

    def test_rs_vs_nifty_computation(self):
        """RS vs Nifty correctly computes relative strength."""
        ai = AdaptiveIndicators()
        rs = ai.compute_rs_vs_nifty(stock_return_1d=0.03, nifty_return_1d=0.01)
        assert rs == 0.02  # 2 percentage points outperformance

    def test_rs_vs_nifty_negative(self):
        """RS vs Nifty can be negative (underperformance)."""
        ai = AdaptiveIndicators()
        rs = ai.compute_rs_vs_nifty(stock_return_1d=-0.02, nifty_return_1d=0.01)
        assert rs == -0.03

    def test_rs_vs_nifty_passes_non_crisis(self):
        """RS filter always passes in non-crisis regimes."""
        ai = AdaptiveIndicators()
        assert ai.rs_vs_nifty_passes(0.01, Regime.REGIME_1_NORMAL) is True
        assert ai.rs_vs_nifty_passes(0.01, Regime.REGIME_2_ELEVATED) is True

    def test_rs_vs_nifty_passes_crisis_above_threshold(self):
        """RS filter passes in crisis if outperformance >= 5%."""
        ai = AdaptiveIndicators()
        assert ai.rs_vs_nifty_passes(0.06, Regime.REGIME_3_CRISIS) is True

    def test_rs_vs_nifty_fails_crisis_below_threshold(self):
        """RS filter fails in crisis if outperformance < 5%."""
        ai = AdaptiveIndicators()
        assert ai.rs_vs_nifty_passes(0.03, Regime.REGIME_3_CRISIS) is False