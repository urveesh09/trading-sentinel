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
        """UNKNOWN -> any regime: requires 2 consecutive scans to transition.
        Scan 1: UNKNOWN stays UNKNOWN (counter=1, not yet 2).
        Scan 2: UNKNOWN -> R2 (counter=2, fires transition).
        Scan 3: stay in R2 (counter reset to 1, then incremented to 2).
        """
        engine = RegimeEngine()
        # Scan 1: UNKNOWN candidate, counter 0->1, still UNKNOWN (not yet 2)
        engine.update_regime(vix=21.0, nifty_50=25000, nifty_ema20=24900, breadth=0.50)
        assert engine.current_regime == Regime.UNKNOWN

        # Scan 2: still R2 candidate, counter 1->2, hits threshold -> transition fires
        engine.update_regime(vix=21.0, nifty_50=25000, nifty_ema20=24900, breadth=0.50)
        assert engine.current_regime == Regime.REGIME_2_ELEVATED

    def test_hysteresis_prevents_flip_flopping(self):
        """Once in R2, score 70-74 should stay R2 (need 75+ to re-enter R1)."""
        engine = RegimeEngine()
        # Establish R1
        engine.update_regime(vix=12.0, nifty_50=25000, nifty_ema20=24900, breadth=0.55)
        engine.update_regime(vix=12.0, nifty_50=25000, nifty_ema20=24900, breadth=0.55)
        assert engine.current_regime == Regime.REGIME_1_NORMAL

        # Transition R1 -> R2 (score=65 < 70 boundary)
        engine.update_regime(vix=19.0, nifty_50=25000, nifty_ema20=24900, breadth=0.55)
        assert engine.current_regime == Regime.REGIME_2_ELEVATED

        # Score=72.5 (70 <= score < 75): hysteresis says stay in R2
        engine.update_regime(vix=17.6, nifty_50=25000, nifty_ema20=24900, breadth=0.55)
        assert engine.current_regime == Regime.REGIME_2_ELEVATED

        # Score=75+ (hysteresis cleared): R2 -> R1
        engine.update_regime(vix=14.0, nifty_50=25000, nifty_ema20=24900, breadth=0.55)
        assert engine.current_regime == Regime.REGIME_1_NORMAL

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
        """update_regime returns a RegimeState with correct regime, score, and consecutive_scans.
        
        UNKNOWN -> any regime requires 2 consecutive scans.
        Scan 1: UNKNOWN (consecutive_scans=1).
        Scan 2: R2 (consecutive_scans=2, transition fires).
        """
        engine = RegimeEngine()
        # Scan 1: UNKNOWN (counter=1, below threshold)
        state = engine.update_regime(vix=21.0, nifty_50=25000, nifty_ema20=24900, breadth=0.50)
        assert state.regime == Regime.UNKNOWN
        assert state.regime_score == 55.0
        assert state.vix == 21.0
        assert state.consecutive_scans == 1

        # Scan 2: R2 (counter=2, transition fires)
        state = engine.update_regime(vix=21.0, nifty_50=25000, nifty_ema20=24900, breadth=0.50)
        assert state.regime == Regime.REGIME_2_ELEVATED
        assert 0 <= state.regime_score <= 100