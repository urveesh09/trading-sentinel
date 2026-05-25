"""
regime.py — Volatility-responsive market regime detection engine.

Computes a continuous regime score (0-100) from:
  1. India VIX level (primary driver)
  2. Nifty 50 vs its 20-day EMA (trend confirmation)
  3. Market breadth (% stocks above their SMA50)

The score smoothly transitions between three regimes:
  REGIME_1_NORMAL     (score >= 70): Full signal universe, 10% risk, standard targets
  REGIME_2_ELEVATED   (score 40-69): Selective, Nifty-confirmed, 7% risk
  REGIME_3_CRISIS     (score < 40):  Maximum caution, RS filter, 5% risk
"""

import structlog
from dataclasses import dataclass
from typing import Optional

from config import settings
from models import Regime

logger = structlog.get_logger()


@dataclass
class RegimeState:
    """Snapshot of the regime engine state at a point in time."""
    regime: Regime
    regime_score: float
    vix: float
    nifty_50: float
    nifty_ema20: float
    breadth: float
    consecutive_scans: int = 1


class RegimeEngine:
    """
    Detects market volatility regime using VIX + Nifty trend + breadth.

    Usage:
        engine = RegimeEngine()
        engine.update_regime(vix=17.0, nifty_50=25000, nifty_ema20=24900, breadth=0.55)
        print(engine.current_regime, engine.current_score)
    """

    def __init__(self):
        self.current_regime: Regime = Regime.UNKNOWN
        self.current_score: float = 100.0
        self._prior_regime: Regime = Regime.UNKNOWN
        # Start at 0 so first scan → 1 (need 2 to transition), second scan → 2 (fires)
        self._consecutive_in_range: int = 0

    def compute_score(
        self,
        vix: float,
        nifty_50: float,
        nifty_ema20: float,
        breadth: float,
    ) -> float:
        """
        Compute the continuous regime score (0-100).

        Score starts at 100 when VIX = 12 (calm) and decays as VIX rises.
        Penalties apply for Nifty below EMA20 (downtrend) and weak breadth.
        """
        # Primary driver: VIX (12 = calm, 32 = maximum stress)
        vix_factor = max(0.0, min(100.0, 100.0 - (vix - 12.0) * 5.0))

        # Trend penalty: Nifty below its 20-day EMA signals bearish environment
        if nifty_50 < nifty_ema20:
            vix_factor *= 0.7

        # Breadth penalty: less than 30% of stocks above SMA50 = weak market
        if breadth < 0.30:
            vix_factor *= 0.8

        return max(0.0, min(100.0, vix_factor))

    def get_regime(self, score: float, prior_regime: Optional[Regime] = None) -> Regime:
        """
        Map a continuous score to a Regime, applying hysteresis.

        Hysteresis: if previously in Regime 2, entering Regime 1 requires score >= 75
        (5 points above the 70 boundary). This prevents flip-flopping at boundaries.
        """
        if prior_regime == Regime.REGIME_2_ELEVATED:
            if score >= 75:
                return Regime.REGIME_1_NORMAL
            elif score >= 40:
                return Regime.REGIME_2_ELEVATED
            else:
                return Regime.REGIME_3_CRISIS
        elif prior_regime == Regime.REGIME_1_NORMAL:
            if score < 65:  # 5 points below 70
                return Regime.REGIME_2_ELEVATED
            elif score >= 70:
                return Regime.REGIME_1_NORMAL
            else:
                return Regime.REGIME_2_ELEVATED
        else:
            # No prior regime — use raw boundaries
            if score >= 70:
                return Regime.REGIME_1_NORMAL
            elif score >= 40:
                return Regime.REGIME_2_ELEVATED
            else:
                return Regime.REGIME_3_CRISIS

    def get_regime_for_scan(
        self,
        vix: float,
        nifty_50: float,
        nifty_ema20: float,
        breadth: float,
    ) -> Regime:
        """
        Compute regime for a scan cycle, with circuit breaker override.

        If VIX exceeds the circuit breaker threshold (40), forces Regime 3
        regardless of score to protect capital during extreme stress.
        """
        if vix > settings.VIX_CB_THRESHOLD:
            return Regime.REGIME_3_CRISIS

        score = self.compute_score(
            vix=vix,
            nifty_50=nifty_50,
            nifty_ema20=nifty_ema20,
            breadth=breadth,
        )
        return self.get_regime(score, prior_regime=self.current_regime)

    def update_regime(
        self,
        vix: float,
        nifty_50: float,
        nifty_ema20: float,
        breadth: float,
    ) -> RegimeState:
        """
        Update regime state for the current scan cycle.

        Requires score to remain in the new range for 2 consecutive scans
        before transitioning (anti-flash-signal protection).
        """
        candidate = self.get_regime_for_scan(
            vix=vix,
            nifty_50=nifty_50,
            nifty_ema20=nifty_ema20,
            breadth=breadth,
        )
        score = self.compute_score(vix, nifty_50, nifty_ema20, breadth)

        if candidate == self.current_regime:
            # Same regime: reset to 1 so next differing scan starts counting from 1
            self._consecutive_in_range = 1
        else:
            self._consecutive_in_range += 1

        # Transition only after 2 consecutive scans in new regime
        if self._consecutive_in_range >= settings.REGIME_TRANSITION_SCANS:
            if candidate != self.current_regime:
                logger.info(
                    "regime_transition",
                    from_regime=self.current_regime.value,
                    to_regime=candidate.value,
                    score=round(score, 2),
                    vix=vix,
                )
                self._prior_regime = self.current_regime
                self.current_regime = candidate
                self._consecutive_in_range = settings.REGIME_TRANSITION_SCANS

        self.current_score = score

        return RegimeState(
            regime=self.current_regime,
            regime_score=self.current_score,
            vix=vix,
            nifty_50=nifty_50,
            nifty_ema20=nifty_ema20,
            breadth=breadth,
            consecutive_scans=self._consecutive_in_range,
        )

    def get_risk_pct(self) -> float:
        """Return the risk percentage for the current regime."""
        mapping = {
            Regime.REGIME_1_NORMAL: settings.RISK_PCT_REGIME1,
            Regime.REGIME_2_ELEVATED: settings.RISK_PCT_REGIME2,
            Regime.REGIME_3_CRISIS: settings.RISK_PCT_REGIME3,
            Regime.UNKNOWN: settings.RISK_PCT_REGIME1,  # Safe default
        }
        return mapping[self.current_regime]

    def get_stop_atr_mult(self) -> float:
        """Return the ATR multiplier for stop loss in the current regime."""
        mapping = {
            Regime.REGIME_1_NORMAL: settings.STOP_ATR_REGIME1,
            Regime.REGIME_2_ELEVATED: settings.STOP_ATR_REGIME2,
            Regime.REGIME_3_CRISIS: settings.STOP_ATR_REGIME3,
            Regime.UNKNOWN: settings.STOP_ATR_REGIME1,
        }
        return mapping[self.current_regime]

    def get_target2_r(self) -> float:
        """Return the T2 R-multiple for the current regime."""
        if self.current_regime == Regime.REGIME_3_CRISIS:
            return settings.TARGET2_R_REGIME3
        elif self.current_regime == Regime.REGIME_2_ELEVATED:
            return settings.TARGET2_R_REGIME2
        else:
            return settings.TARGET2_R_REGIME1