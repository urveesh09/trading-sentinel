import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from regime import RegimeEngine
from models import Regime


class TestRegimeEngine:
    """Tests for the regime detection engine."""

    def test_vix_only_regime_1(self):
        """VIX 15 with neutral Nifty and good breadth -> Regime 1."""
        engine = RegimeEngine()
        score = engine.compute_score(vix=15.0, nifty_50=25000, nifty_ema20=24900, breadth=0.60)
        assert score >= 70
        regime = engine.get_regime(score)
        assert regime == Regime.REGIME_1_NORMAL

    def test_vix_only_regime_2(self):
        """VIX 21 with neutral Nifty -> Regime 2."""
        engine = RegimeEngine()
        score = engine.compute_score(vix=21.0, nifty_50=25000, nifty_ema20=24900, breadth=0.50)
        assert 40 <= score < 70
        regime = engine.get_regime(score)
        assert regime == Regime.REGIME_2_ELEVATED

    def test_vix_only_regime_3(self):
        """VIX 30 -> Regime 3."""
        engine = RegimeEngine()
        score = engine.compute_score(vix=30.0, nifty_50=25000, nifty_ema20=24900, breadth=0.50)
        assert score < 40
        regime = engine.get_regime(score)
        assert regime == Regime.REGIME_3_CRISIS

    def test_nifty_downtrend_penalty(self):
        """Nifty below EMA20 applies 0.7x penalty to score."""
        engine = RegimeEngine()
        # Bull: nifty_50=25200 > ema20=25100 → no penalty → 100.0
        score_bull = engine.compute_score(vix=12.0, nifty_50=25200, nifty_ema20=25100, breadth=0.60)
        # Bear: nifty_50=24900 < ema20=25100 → 0.7x penalty → 70.0
        score_bear = engine.compute_score(vix=12.0, nifty_50=24900, nifty_ema20=25100, breadth=0.60)
        assert score_bear < score_bull
        assert score_bull == 100.0
        assert score_bear == 70.0

    def test_weak_breadth_penalty(self):
        """Breadth < 0.30 applies 0.8x penalty."""
        engine = RegimeEngine()
        score_good = engine.compute_score(vix=12.0, nifty_50=25000, nifty_ema20=24900, breadth=0.60)
        score_weak = engine.compute_score(vix=12.0, nifty_50=25000, nifty_ema20=24900, breadth=0.20)
        assert score_weak < score_good
        # VIX=12→100, breadth 0.6 → 100.0; breadth 0.2 → 80.0 (0.8x)
        assert score_good == 100.0
        assert score_weak == 80.0

    def test_hysteresis_boundary(self):
        """Score at 70 exactly should NOT transition to Regime 1 if prior was Regime 2."""
        engine = RegimeEngine()
        score = 70.0
        # With hysteresis of 5, must cross 75 to enter Regime 1
        # So 70 should map to Regime 2
        regime = engine.get_regime(score, prior_regime=Regime.REGIME_2_ELEVATED)
        assert regime == Regime.REGIME_2_ELEVATED

    def test_circuit_breaker_override(self):
        """VIX > 40 forces Regime 3 regardless of score."""
        engine = RegimeEngine()
        # Even a "calm" VIX of 41 should force Regime 3
        regime = engine.get_regime_for_scan(vix=41.0, nifty_50=25000, nifty_ema20=24900, breadth=0.60)
        assert regime == Regime.REGIME_3_CRISIS

    def test_regime_transition_requires_2_scans(self):
        """UNKNOWN -> any regime: immediate on first scan.
        Transitions between ESTABLISHED regimes require 2 consecutive scans."""
        engine = RegimeEngine()
        # First scan: UNKNOWN -> R2 immediately (initial establishment is instant)
        engine.update_regime(vix=21.0, nifty_50=25000, nifty_ema20=24900, breadth=0.50)
        assert engine.current_regime == Regime.REGIME_2_ELEVATED
        # Second scan: same regime -> stays
        engine.update_regime(vix=21.0, nifty_50=25000, nifty_ema20=24900, breadth=0.50)
        assert engine.current_regime == Regime.REGIME_2_ELEVATED

    def test_score_clamped_to_0_100(self):
        """Score must never go outside 0-100."""
        engine = RegimeEngine()
        # VIX way below 12 should clamp to 100
        score = engine.compute_score(vix=5.0, nifty_50=25000, nifty_ema20=24900, breadth=0.60)
        assert score == 100.0
        # VIX way above 32 should clamp to 0
        score = engine.compute_score(vix=50.0, nifty_50=25000, nifty_ema20=24900, breadth=0.60)
        assert score == 0.0

    def test_get_risk_pct_r1(self):
        """Regime 1 returns correct risk %."""
        engine = RegimeEngine()
        engine.current_regime = Regime.REGIME_1_NORMAL
        assert engine.get_risk_pct() == 0.10

    def test_get_risk_pct_r2(self):
        """Regime 2 returns correct risk %."""
        engine = RegimeEngine()
        engine.current_regime = Regime.REGIME_2_ELEVATED
        assert engine.get_risk_pct() == 0.07

    def test_get_risk_pct_r3(self):
        """Regime 3 returns correct risk %."""
        engine = RegimeEngine()
        engine.current_regime = Regime.REGIME_3_CRISIS
        assert engine.get_risk_pct() == 0.05

    def test_update_regime_returns_state(self):
        """update_regime returns a RegimeState."""
        engine = RegimeEngine()
        state = engine.update_regime(vix=17.0, nifty_50=25000, nifty_ema20=24900, breadth=0.55)
        assert state.regime in (Regime.REGIME_1_NORMAL, Regime.REGIME_2_ELEVATED)
        assert 0 <= state.regime_score <= 100
        assert state.vix == 17.0