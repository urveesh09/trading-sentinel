"""
[PENNY-REGIME 2026-06-21] Per-stock regime classifier for penny subsystem.

Spec §6. Three regimes (PR1_CALM, PR2_ELEVATED, PR3_HOT) computed each
day at 09:20 IST (and refreshed at 13:00 IST). Inputs:
  1. Per-stock realized volatility rank (40% weight) -- over a 60-day
     rolling distribution
  2. India VIX proxy: Nifty 50 close vs Nifty 50 EMA50 ratio (40% weight)
  3. Breadth fallback: 0.5 (placeholder, matches Nifty engine) (20% weight)

Hard architectural rule (enforced by tests/test_penny_isolation.py):
  this module MUST NOT import from engine, regime, risk_engine, portfolio,
  evaluate_signal, or evaluate_momentum_signal.

The state (_today_regime, _as_of) lives on the singleton instance so the
scanner can read it without recomputing.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List

from penny_models import PennyRegime

logger = logging.getLogger(__name__)

# Spec §6.3 regime boundaries
_VOL_PR1_MAX = 0.7
_VOL_PR2_MAX = 0.9
_VIX_PR1_MAX = 0.7
_VIX_PR2_MAX = 0.9

# Spec §7.1 size multipliers (read once at instance construction)
_DEFAULT_SIZE = {
    PennyRegime.PR1_CALM: 0.05,
    PennyRegime.PR2_ELEVATED: 0.025,
    PennyRegime.PR3_HOT: 0.0,
    PennyRegime.UNKNOWN: 0.0,  # fail-safe
}


class PennyRegimeEngine:
    """Singleton-style state holder + classifier for the penny subsystem."""

    def __init__(self):
        self._today_regime: PennyRegime = PennyRegime.UNKNOWN
        self._as_of: Optional[str] = None
        self._vol_rank: Optional[float] = None
        self._vix_proxy: Optional[float] = None

    # ---- public read API ------------------------------------------------

    @property
    def today_regime(self) -> PennyRegime:
        return self._today_regime

    @property
    def as_of(self) -> Optional[str]:
        return self._as_of

    # ---- public compute API --------------------------------------------

    def compute_vol_rank(self, closes: List[float]) -> float:
        """
        Per-stock realized volatility proxy (5-min returns, 60d lookback).
        Returns a normalized [0, 1] rank: 0 = quiet, 1 = most-volatile seen.
        Short / constant series return 0.5 (degenerate).
        """
        if not closes or len(closes) < 30:
            return 0.5
        # constant series: zero realized vol -> degenerate -> 0.5
        # (per docstring; spec considers zero-vol as "unknown / neutral")
        if len(set(closes)) <= 1:
            return 0.5
        # simple stdev of log returns
        import math
        log_rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
        if len(log_rets) < 5:
            return 0.5
        mean = sum(log_rets) / len(log_rets)
        var = sum((r - mean) ** 2 for r in log_rets) / len(log_rets)
        sd = math.sqrt(var)
        # Normalize to [0,1] with a soft cap at sd=0.10 (10% daily vol).
        # Anything above that is treated as PR3 territory regardless.
        if sd >= 0.10:
            return 1.0
        return sd / 0.10

    def compute_vix_proxy(self, closes: List[float], ema_period: int = 50) -> float:
        """
        India VIX proxy (spec §6.2): close-vs-EMA50 distance, normalized.

        Returns a value in [0, 1]:
          - 0 = close well above EMA (calm / bullish)
          - 1 = close well below EMA (panic / crash)
          - 0.5 = close at EMA (neutral)
        """
        if not closes or len(closes) < ema_period:
            return 0.5
        # Wilder-style EMA seeded with SMA of first ema_period values
        alpha = 2.0 / (ema_period + 1)
        sma = sum(closes[:ema_period]) / ema_period
        ema = sma
        for c in closes[ema_period:]:
            ema = alpha * c + (1 - alpha) * ema
        last = closes[-1]
        if ema <= 0:
            return 0.5
        # Distance as a fraction of EMA. Map [-10%, +5%] -> [1, 0].
        # Below -10% -> clipped to 1.0 (full crisis).
        # Above +5% -> clipped to 0.0 (full calm).
        dist = (last - ema) / ema
        if dist <= -0.10:
            return 1.0
        if dist >= 0.05:
            return 0.0
        # Linear map: dist=-0.10 -> 1.0, dist=0.05 -> 0.0
        # slope = (0 - 1) / (0.05 - (-0.10)) = -1/0.15
        return 1.0 - (dist + 0.10) / 0.15

    def classify(self, vol_rank: Optional[float], vix_proxy: Optional[float]) -> PennyRegime:
        """Map the two inputs to a PennyRegime per spec §6.3."""
        if vol_rank is None or vix_proxy is None:
            return PennyRegime.UNKNOWN
        if vol_rank >= _VOL_PR2_MAX or vix_proxy >= _VIX_PR2_MAX:
            return PennyRegime.PR3_HOT
        if vol_rank >= _VOL_PR1_MAX or vix_proxy >= _VIX_PR1_MAX:
            return PennyRegime.PR2_ELEVATED
        return PennyRegime.PR1_CALM

    def size_pct(self, regime: PennyRegime) -> float:
        """Spec §7.1: per-regime position-sizing multiplier."""
        return _DEFAULT_SIZE.get(regime, 0.0)

    async def compute_today(self, kite, breadth: float = 0.5) -> PennyRegime:
        """
        Compute the day's penny regime (spec §6 + §9.1).

        Reads Nifty 50 daily closes from Kite, computes VIX proxy. Per-stock
        realized vol rank needs per-ticker 5-min bars which the scanner feeds
        in via `update_vol_rank()` after the first scan completes; until
        then the engine defaults to UNKNOWN (fail-safe).

        Failures (Kite down, etc.) -> UNKNOWN, no crash.
        """
        try:
            # Per-stock vol rank: defaults to None until scanner feeds it.
            # Use breadth as the third input weight (placeholder 0.5).
            self._vol_rank = None  # will be set by scanner.update_vol_rank()
            self._breadth = breadth

            # VIX proxy from Nifty 50 daily closes.
            bars = await kite.get_historical(
                ticker="NIFTY 50",
                from_date="2026-01-01",  # overridden by Kite to last 60d usually
                to_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )
            if bars:
                closes = [b["close"] for b in bars if b.get("close")]
                self._vix_proxy = self.compute_vix_proxy(closes)
            else:
                self._vix_proxy = None

            self._today_regime = self.classify(self._vol_rank, self._vix_proxy)
            self._as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            logger.info(
                "penny_regime_computed regime=%s vix_proxy=%s vol_rank=%s",
                self._today_regime.value,
                self._vix_proxy,
                self._vol_rank,
            )
            return self._today_regime
        except Exception as e:
            logger.error("penny_regime_compute_failed error=%s", str(e))
            self._today_regime = PennyRegime.UNKNOWN
            return self._today_regime

    def update_vol_rank(self, ticker_vol_rank: float) -> None:
        """
        Scanner feeds in the per-stock realized-vol rank (computed from the
        5-min bars it has for each ticker). The engine picks the WORST
        (highest) rank across the universe as a conservative aggregate --
        if any penny stock is in PR3 territory, block all new entries.
        """
        if self._vol_rank is None or ticker_vol_rank > self._vol_rank:
            self._vol_rank = ticker_vol_rank
            self._today_regime = self.classify(self._vol_rank, self._vix_proxy)
            logger.info(
                "penny_regime_updated vol_rank=%s regime=%s",
                self._vol_rank,
                self._today_regime.value,
            )
