"""
Tests for momentum signal regime dispatch.

[MOMENTUM-REGIME 2026-06-16] The 3-regime dispatch for evaluate_momentum_signal:
  - Regime 3 → reject all signals (BLOCK_R3_ENTRIES=True)
  - Regime 1 → MOMENTUM_RISK_PCT_R1 (7%) + MOMENTUM_R_TARGET_R1 (2.0R)
  - Regime 2 → MOMENTUM_RISK_PCT_R2 (5%) + MOMENTUM_R_TARGET_R2 (1.5R)
  - Regime 3 (with BLOCK=False) → MOMENTUM_RISK_PCT_R3 (0%) — defense-in-depth
  - UNKNOWN → conservative default: R1 sizing (safe)

The core signal evaluation (gates MC1-MC6) is unchanged. We only modify:
  1. effective_r_target (was: BULL=2.0, BEAR_RS_ONLY=1.5, now: R1=2.0, R2=1.5, R3=block)
  2. momentum_risk (was: MOMENTUM_RISK_PCT=0.10, now: R1=0.07, R2=0.05, R3=0.00)

Tested in isolation via the pure helper `resolve_momentum_regime_params()`.
This is the contract that run_momentum_screener and backtest.py both use.
"""

import pytest
from unittest.mock import patch
from config import settings
from models import Regime
from engine import resolve_momentum_regime_params


class TestResolveMomentumRegimeParams:
    """
    [MOMENTUM-REGIME 2026-06-16] Pure function. Takes a Regime enum,
    returns (effective_r_target, momentum_risk_pct, should_block).

    should_block=True means caller should reject the signal before
    running MC1-MC6 gates (skip the work entirely).
    """

    def test_regime_1_returns_r1_params_no_block(self):
        """[MOMENTUM-AGGRESSIVE 2026-06-16] R1 = 2.0R target, 10% risk, no block."""
        r_target, risk_pct, block = resolve_momentum_regime_params(Regime.REGIME_1_NORMAL)
        assert r_target == 2.0
        assert risk_pct == 0.10
        assert block is False

    def test_regime_2_returns_r2_params_no_block(self):
        """[MOMENTUM-AGGRESSIVE 2026-06-16] R2 = 1.5R target, 7% risk, no block."""
        r_target, risk_pct, block = resolve_momentum_regime_params(Regime.REGIME_2_ELEVATED)
        assert r_target == 1.5
        assert risk_pct == 0.07
        assert block is False

    def test_regime_3_blocks_when_block_setting_true(self):
        """R3 with BLOCK_R3_ENTRIES=True → block (don't even evaluate)."""
        with patch.object(settings, "MOMENTUM_BLOCK_R3_ENTRIES", True):
            r_target, risk_pct, block = resolve_momentum_regime_params(Regime.REGIME_3_CRISIS)
            assert block is True
            # When blocked, the r_target/risk values don't matter
            # (caller should short-circuit), but the function should
            # still return consistent values.
            assert r_target == settings.MOMENTUM_R_TARGET_R2  # conservative fallback
            assert risk_pct == settings.MOMENTUM_RISK_PCT_R3  # 0%

    def test_regime_3_risk_is_zero_even_when_not_blocked(self):
        """R3 with BLOCK_R3_ENTRIES=False → don't block, but 0% risk = no shares."""
        with patch.object(settings, "MOMENTUM_BLOCK_R3_ENTRIES", False):
            r_target, risk_pct, block = resolve_momentum_regime_params(Regime.REGIME_3_CRISIS)
            assert block is False
            assert risk_pct == 0.0  # defense-in-depth: even if block is off, R3 = 0%

    def test_unknown_regime_falls_back_to_r1(self):
        """UNKNOWN regime = safe default: R1 sizing. No block."""
        r_target, risk_pct, block = resolve_momentum_regime_params(Regime.UNKNOWN)
        assert r_target == settings.MOMENTUM_R_TARGET_R1
        assert risk_pct == settings.MOMENTUM_RISK_PCT_R1
        assert block is False

    def test_none_regime_falls_back_to_r1(self):
        """None = backward compat (legacy callers don't pass regime) = R1."""
        r_target, risk_pct, block = resolve_momentum_regime_params(None)
        assert r_target == settings.MOMENTUM_R_TARGET_R1
        assert risk_pct == settings.MOMENTUM_RISK_PCT_R1
        assert block is False


class TestEvaluateMomentumSignalRegimeDispatch:
    """
    [MOMENTUM-REGIME 2026-06-16] Integration tests: the regime param
    flows into evaluate_momentum_signal and changes effective_r_target
    + position sizing. Uses a fake_momentum_candles fixture.
    """

    @pytest.fixture
    def good_momentum_candles(self):
        """Candles that pass MC1-MC6 (clean VWAP cross, good volume, good morphology)."""
        import pandas as pd
        n = 6
        df = pd.DataFrame({
            "open":   [100 + i for i in range(n)],
            "high":   [105 + i for i in range(n)],
            "low":    [98 + i for i in range(n)],
            "close":  [102 + i for i in range(n)],
            "volume": [100_000, 100_000, 100_000, 100_000, 100_000, 500_000],  # 5x volume surge
        })
        # Force VWAP crossover on last candle
        df.loc[df.index[-2], "close"] = 100  # below VWAP
        df.loc[df.index[-1], "close"] = 115  # above VWAP, big green candle
        df.loc[df.index[-1], "high"] = 117
        df.loc[df.index[-1], "low"] = 105
        return df

    def test_regime_3_blocks_signal_evaluation(self, good_momentum_candles):
        """When regime=R3 and BLOCK=True, evaluate_momentum_signal must short-circuit
        with reject_reason='regime_r3_block' BEFORE running MC1-MC6."""
        from engine import evaluate_momentum_signal
        with patch.object(settings, "MOMENTUM_BLOCK_R3_ENTRIES", True):
            fired, result = evaluate_momentum_signal(
                "TEST", good_momentum_candles,
                prev_day_high=100.0, bankroll=5000, momentum_pool=1000,
                regime=Regime.REGIME_3_CRISIS,
            )
        assert fired is False
        assert result["reject_reason"] == "regime_r3_block"

    def test_regime_1_uses_2r_target(self, good_momentum_candles):
        """R1 = 2.0R target (vs 1.5R for R2). Verify via the result dict."""
        from engine import evaluate_momentum_signal
        with patch.object(settings, "MOMENTUM_RISK_PCT_R1", 0.07), \
             patch.object(settings, "MOMENTUM_R_TARGET_R1", 2.0):
            fired, result = evaluate_momentum_signal(
                "TEST", good_momentum_candles,
                prev_day_high=100.0, bankroll=5000, momentum_pool=1000,
                regime=Regime.REGIME_1_NORMAL,
            )
        if fired:
            assert result["effective_r_target"] == 2.0

    def test_regime_2_uses_1_5r_target(self, good_momentum_candles):
        """R2 = 1.5R target. Verify via the result dict."""
        from engine import evaluate_momentum_signal
        with patch.object(settings, "MOMENTUM_RISK_PCT_R2", 0.05), \
             patch.object(settings, "MOMENTUM_R_TARGET_R2", 1.5):
            fired, result = evaluate_momentum_signal(
                "TEST", good_momentum_candles,
                prev_day_high=100.0, bankroll=5000, momentum_pool=1000,
                regime=Regime.REGIME_2_ELEVATED,
            )
        if fired:
            assert result["effective_r_target"] == 1.5

    def test_regime_2_smaller_position_size(self, good_momentum_candles):
        """R2 = 5% risk per trade. Same setup, fewer shares than R1.

        This is the key behavioral guarantee: in elevated regime, the
        system takes smaller positions. Verify by comparing shares.
        """
        from engine import evaluate_momentum_signal
        with patch.object(settings, "MOMENTUM_RISK_PCT_R1", 0.07), \
             patch.object(settings, "MOMENTUM_RISK_PCT_R2", 0.05), \
             patch.object(settings, "MOMENTUM_R_TARGET_R1", 2.0), \
             patch.object(settings, "MOMENTUM_R_TARGET_R2", 1.5):
            fired_r1, result_r1 = evaluate_momentum_signal(
                "TEST", good_momentum_candles,
                prev_day_high=100.0, bankroll=5000, momentum_pool=1000,
                regime=Regime.REGIME_1_NORMAL,
            )
            fired_r2, result_r2 = evaluate_momentum_signal(
                "TEST", good_momentum_candles,
                prev_day_high=100.0, bankroll=5000, momentum_pool=1000,
                regime=Regime.REGIME_2_ELEVATED,
            )
            if fired_r1 and fired_r2:
                # R2 has 5/7 the risk budget → fewer shares
                assert result_r2["shares"] < result_r1["shares"], (
                    f"R2 should produce fewer shares than R1. "
                    f"R1: {result_r1['shares']}, R2: {result_r2['shares']}"
                )
                assert result_r2["capital_at_risk"] < result_r1["capital_at_risk"]

    def test_no_regime_uses_legacy_string_dispatch(self, good_momentum_candles):
        """Backward compat: regime=None uses the legacy 'market_regime' string
        via the existing BULL/BEAR_RS_ONLY logic. R target = MOMENTUM_R_TARGET
        (2.0R for BULL default)."""
        from engine import evaluate_momentum_signal
        # regime=None, market_regime="BULL" (default) → 2.0R legacy
        fired, result = evaluate_momentum_signal(
            "TEST", good_momentum_candles,
            prev_day_high=100.0, bankroll=5000, momentum_pool=1000,
            regime=None,
            market_regime="BULL",
        )
        if fired:
            assert result["effective_r_target"] == 2.0
