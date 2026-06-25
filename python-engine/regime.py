"""
regime.py -- VIX-Free Volatility-Responsive Market Regime Detection Engine.

Replaces India VIX (unavailable via Kite) with a dual-component volatility signal:
  1. ATR Compression Ratio  (primary, 60% weight): Nifty ATR_14 / ATR_14_SMA_200
  2. Realized Volatility    (secondary, 40% weight): 20-day annualized std-dev of log returns

Combined with:
  - Nifty vs EMA20 trend penalty (x0.7 when below)
  - Nifty/BankNifty ratio breadth penalty (x0.8 when NB ratio below 30th percentile)

The score smoothly transitions between three regimes:
  REGIME_1_NORMAL   (score >= 70): Full signal universe, 10% risk, standard targets
  REGIME_2_ELEVATED (score 40-69): Selective, Nifty-confirmed, 7% risk
  REGIME_3_CRISIS   (score < 40):  Maximum caution, RS filter, 5% risk
"""

import structlog
from dataclasses import dataclass
from typing import Optional

from config import settings
from models import Regime

logger = structlog.get_logger()

# Default VIX when live data is unavailable (used in VIX-backward-compat mode only).
# Calibrated to produce Regime 1 (score=100, no penalty) with the standard
# 100.0 - (vix - 12.0) * 5.0 formula: 18.0 -> 100.0 - 30.0 = 70.0.
VIX_DEFAULT = 18.0


@dataclass
class RegimeState:
    """Snapshot of the regime engine state at a point in time."""
    regime: Regime
    regime_score: float
    rv_ratio: float                     # ATR compression ratio (ATR_14 / ATR_SMA_200)
    realized_vol: float                 # 20-day annualized realized volatility
    nb_ratio: float                     # Nifty/BankNifty close ratio
    nifty_50: float
    nifty_ema20: float
    breadth: float                     # Legacy-proxy breadth (close/ema50 ratio)
    consecutive_scans: int = 1


class RegimeEngine:
    """
    Detects market volatility regime using ATR Compression + Realized Volatility.

    Replaces India VIX which is unavailable via Kite Connect historical data.
    Uses dual-component volatility scoring (ATR compression 60% + RV 40%) with
    trend penalty (Nifty vs EMA20) and breadth penalty (Nifty/BankNifty ratio).

    Usage:
        engine = RegimeEngine()
        # Full VIX-free call:
        state = engine.update_regime(
            nifty_atr_current=120.0,
            nifty_atr_baseline=140.0,
            nifty_close=25000,
            nifty_ema20=24900,
            banknifty_close=52000,
            nb_ratio_history=[...],   # 60-day rolling history
            breadth=0.55,
        )
        print(engine.current_regime, engine.current_score)
    """

    def __init__(self):
        self.current_regime: Regime = Regime.UNKNOWN
        self.current_score: float = 100.0
        self._prior_regime: Regime = Regime.UNKNOWN
        # Start at 0 so first scan -> 1 (need 2 to transition), second scan -> 2 (fires)
        self._consecutive_in_range: int = 0

    # ------------------------------------------------------------------
    # Internal scoring helpers
    # ------------------------------------------------------------------

    def _calc_rv_ratio(self, nifty_atr_current: float, nifty_atr_baseline: float) -> float:
        """
        ATR Compression Ratio.
        rv_ratio <= 0.70 = compressed (calm)
        rv_ratio  1.00  = normal
        rv_ratio >= 1.20 = expansion (stress)
        rv_ratio >  1.50 = circuit breaker territory
        """
        if nifty_atr_baseline <= 0:
            return 1.0
        return nifty_atr_current / nifty_atr_baseline

    def _calc_atr_score(self, rv_ratio: float) -> float:
        """
        Convert ATR compression ratio to a 0-100 score.

        Score map (with slope = 100 / 0.50 = 200):
          rv_ratio 0.70 -> score 100 (compressed baseline)
          rv_ratio 0.95 -> score  75.0 (mild compression above baseline)
          rv_ratio 1.20 -> score  50.0 (normal expansion)
          rv_ratio 1.45 -> score  25.0 (elevated stress)
          rv_ratio 1.70 -> score   0.0 (extreme expansion, clamped)
        """
        if rv_ratio <= settings.RV_ATR_COMPRESS_THRESHOLD:
            return 100.0
        score = 100.0 - (rv_ratio - settings.RV_ATR_COMPRESS_THRESHOLD) * settings.RV_ATR_SCORE_SCALE
        return max(0.0, min(100.0, score))

    def _calc_realized_vol(self, close_series) -> float:
        """
        Compute 20-day annualized realized volatility from a close price series.
        Uses log returns: ln(close_t / close_t-1) x sqrt(252).
        Returns annualized volatility as a float (e.g., 0.18 = 18% annualized vol).
        """
        import pandas as pd
        import numpy as np
        if len(close_series) < 21:          # need 21 closes for 20 log returns
            return settings.RV_NORMAL_ANNUAL  # safe fallback
        log_returns = np.diff(np.log(np.asarray(close_series, dtype=float)))
        if len(log_returns) < 20:
            return settings.RV_NORMAL_ANNUAL
        rv = float(np.std(log_returns[-20:], ddof=0) * (252 ** 0.5))
        return max(0.0, rv)

    def _calc_rv_score(self, realized_vol: float) -> float:
        """
        Convert 20-day annualized realized volatility to a 0-100 score.

        Score map:
          rv = 12% -> score 100 (historically low vol = calm)
          rv = 18% -> score  62.5 (normal vol baseline)
          rv = 28% -> score  37.5 (elevated stress)
          rv = 34% -> score  ~0 (clamped, extreme)
        """
        if realized_vol <= settings.RV_NORMAL_ANNUAL:
            return 100.0
        score = 100.0 - (realized_vol - settings.RV_NORMAL_ANNUAL) * settings.RV_SCORE_SCALE
        return max(0.0, min(100.0, score))

    def _calc_nb_pctile(self, nb_ratio: float, nb_ratio_history: list) -> float:
        """
        Compute the percentile rank of today's Nifty/BankNifty ratio
        within its own trailing 60-day history.
        Returns a float in [0.0, 1.0].
        """
        import numpy as np
        if not nb_ratio_history or len(nb_ratio_history) < 5:
            return 0.50  # insufficient history -> neutral
        arr = np.array(nb_ratio_history, dtype=float)
        # percentile rank: fraction of history below today's ratio
        pctile = float(np.sum(arr < nb_ratio) / len(arr))
        return pctile

    # ------------------------------------------------------------------
    # Full update with all signals
    # ------------------------------------------------------------------

    def compute_score_full(
        self,
        nifty_atr_current: float,
        nifty_atr_baseline: float,
        realized_vol: float,
        nifty_close: float,
        nifty_ema20: float,
        banknifty_close: float,
        nb_ratio_history: list,
        breadth: float,
    ) -> float:
        """
        Full VIX-free score computation with all signals explicitly provided.
        Use this for the live update_regime() call.
        """
        import numpy as np

        # 1. ATR compression ratio -> ATR score
        rv_ratio = self._calc_rv_ratio(nifty_atr_current, nifty_atr_baseline)
        atr_score = self._calc_atr_score(rv_ratio)

        # 2. Realized volatility -> RV score
        rv_score = self._calc_rv_score(realized_vol)

        # 3. Combine into vol_score
        vol_score = atr_score * settings.RV_ATR_WEIGHT + rv_score * settings.RV_RV_WEIGHT

        # 4. Trend penalty
        if nifty_close < nifty_ema20:
            vol_score *= 0.7

        # 5. Breadth penalty (Nifty/BankNifty ratio percentile)
        nb_ratio = nifty_close / banknifty_close if banknifty_close > 0 else 1.0
        nb_pctile = self._calc_nb_pctile(nb_ratio, nb_ratio_history)
        if nb_pctile < settings.NB_RATIO_LO_PCT:
            vol_score *= 0.8

        return max(0.0, min(100.0, vol_score))

    def compute_score(  # kept for backward compat + tests using VIX param
        self,
        vix: Optional[float],
        nifty_50: float,
        nifty_ema20: float,
        breadth: float,
        # New VIX-free parameters (ignored when vix is provided)
        nifty_atr_current: float = 0.0,
        nifty_atr_baseline: float = 0.0,
        banknifty_close: float = 0.0,
        nb_ratio_history: list = None,
        realized_vol: float = 0.0,
    ) -> float:
        """
        Compute regime score.

        BACKWARD COMPAT: When vix is NOT None, falls back to the old VIX formula
        so existing tests pass without modification. Logs a deprecation warning.

        VIX-FREE mode: Pass vix=None and provide the new signals:
          - nifty_atr_current, nifty_atr_baseline: ATR compression inputs
          - realized_vol: 20-day annualized realized vol
          - banknifty_close + nb_ratio_history: breadth proxy inputs
        """
        # [AUDIT-FIX-2.1 2026-06-25] Same fix as _compute_bk_score: the
        # DeprecationWarning is documented in this function's docstring
        # (above) and no longer fires per call. Set REGIME_VIX_DEBUG=1
        # to log each call at debug level if needed.
        import os
        if os.environ.get("REGIME_VIX_DEBUG"):
            logger.debug(
                "regime_compute_score_vix_used vix=%s", vix,
            )
        if vix is not None:
            # OLD formula (VIX-based) -- kept for backward compat with existing tests
            effective_vix = vix
            vix_factor = max(0.0, min(100.0, 100.0 - (effective_vix - 12.0) * 5.0))
            if nifty_50 < nifty_ema20:
                vix_factor *= 0.7
            if breadth < 0.30:
                vix_factor *= 0.8
            return max(0.0, min(100.0, vix_factor))
        # VIX-free path
        return self.compute_score_full(
            nifty_atr_current=nifty_atr_current,
            nifty_atr_baseline=nifty_atr_baseline,
            realized_vol=realized_vol if realized_vol > 0 else settings.RV_NORMAL_ANNUAL,
            nifty_close=nifty_50,
            nifty_ema20=nifty_ema20,
            banknifty_close=banknifty_close,
            nb_ratio_history=nb_ratio_history or [],
            breadth=breadth,
        )

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
            # No prior regime -- use raw boundaries
            if score >= 70:
                return Regime.REGIME_1_NORMAL
            elif score >= 40:
                return Regime.REGIME_2_ELEVATED
            else:
                return Regime.REGIME_3_CRISIS

    # Sentinel for detecting backward-compat VIX API calls (avoiding default ambiguity).
    # Typed as float | None so type checkers understand it satisfies Optional[float].
    _BKC: float | None = object()  # type: ignore[assignment]

    def _compute_bk_score(
        self, vix: float, nifty_50: float, nifty_ema20: float, breadth: float
    ) -> float:
        """Old VIX formula for backward-compat tests.

        [AUDIT-FIX-2.1 2026-06-25] The previous implementation emitted a
        `DeprecationWarning` per call. With 30s scans × multiple
        subsystems, this flooded production logs and pytest's
        warning summary. The deprecation is still documented in this
        docstring (and in `get_regime_for_scan`'s comment block); we
        just don't spam the warning. If you need to verify the VIX path
        is being hit, set the env var `REGIME_VIX_DEBUG=1` and a
        single debug-level log line fires per call.
        """
        import os
        if os.environ.get("REGIME_VIX_DEBUG"):
            logger.debug(
                "regime_vix_path_used vix=%s nifty=%s ema=%s breadth=%s",
                vix, nifty_50, nifty_ema20, breadth,
            )
        effective_vix = vix
        vix_factor = max(0.0, min(100.0, 100.0 - (effective_vix - 12.0) * 5.0))
        if nifty_50 < nifty_ema20:
            vix_factor *= 0.7
        if breadth < 0.30:
            vix_factor *= 0.8
        return max(0.0, min(100.0, vix_factor))

    def get_regime_for_scan(
        self,
        # VIX-free primary signals
        nifty_atr_current: float = 0.0,
        nifty_atr_baseline: float = 0.0,
        realized_vol: float = 0.0,
        nifty_close: float = 0.0,
        nifty_ema20: float = 0.0,
        banknifty_close: float = 0.0,
        nb_ratio_history: Optional[list] = None,
        breadth: float = 0.50,
        # VIX backward-compat
        vix: Optional[float] = _BKC,
        nifty_50: float = 0.0,
    ) -> Regime:
        """
        Compute regime for a scan cycle, with ATR circuit breaker override.

        VIX-BACKWARD-COMPAT path (deprecated, tests only):
            Pass vix keyword argument (any value) -> uses old VIX formula.

        VIX-FREE path (primary):
            Pass nifty_atr_current > 0 -> uses ATR compression circuit breaker.
        """
        if vix is not self._BKC:
            # -- VIX BACKWARD-COMPAT PATH ----------------------------------
            # Used by existing tests: get_regime_for_scan(vix=41.0, ...)
            score = self._compute_bk_score(vix, nifty_50, nifty_ema20, breadth)
            return self.get_regime(score, prior_regime=self.current_regime)

        # -- VIX-FREE PRIMARY PATH -----------------------------------------
        if nb_ratio_history is None:
            nb_ratio_history = []
        rv_ratio = self._calc_rv_ratio(nifty_atr_current, nifty_atr_baseline)
        if rv_ratio > settings.ATR_CB_THRESHOLD:
            return Regime.REGIME_3_CRISIS

        score = self.compute_score_full(
            nifty_atr_current=nifty_atr_current,
            nifty_atr_baseline=nifty_atr_baseline,
            realized_vol=realized_vol,
            nifty_close=nifty_close,
            nifty_ema20=nifty_ema20,
            banknifty_close=banknifty_close,
            nb_ratio_history=nb_ratio_history,
            breadth=breadth,
        )
        return self.get_regime(score, prior_regime=self.current_regime)

    def update_regime(
        self,
        # VIX-free primary signals
        nifty_atr_current: float = 0.0,
        nifty_atr_baseline: float = 0.0,
        realized_vol: float = 0.0,
        nifty_close: float = 0.0,
        nifty_ema20: float = 0.0,
        banknifty_close: float = 0.0,
        nb_ratio_history: Optional[list] = None,
        breadth: float = 0.50,
        # VIX backward-compat  (deprecated -- tests only)
        vix: Optional[float] = None,
        nifty_50: float = 0.0,
    ) -> RegimeState:
        """
        Update regime state for the current scan cycle VIX-free.

        Requires score to remain in the new range for 2 consecutive scans
        before transitioning (anti-flash-signal protection).
        """
        if nb_ratio_history is None:
            nb_ratio_history = []
        candidate = self.get_regime_for_scan(
            nifty_atr_current=nifty_atr_current,
            nifty_atr_baseline=nifty_atr_baseline,
            realized_vol=realized_vol,
            nifty_close=nifty_close,
            nifty_ema20=nifty_ema20,
            banknifty_close=banknifty_close,
            nb_ratio_history=nb_ratio_history,
            breadth=breadth,
            # VIX backward-compat (pass through from update_regime's vix kwarg)
            vix=vix if vix is not None else self._BKC,
            nifty_50=nifty_50,  # use the nifty_50 param, NOT nifty_close (which may be 0 in BKC mode)
        )
        # vix backward-compat active?
        bkc_mode = vix is not None  # tests pass vix=21.0 etc.

        rv_ratio = self._calc_rv_ratio(nifty_atr_current, nifty_atr_baseline)
        bkc_mode = vix is not None  # tests pass vix=21.0 etc.

        # -- ATR CIRCUIT BREAKER -- immediate R3, no 2-scan guard needed -----
        # When volatility explodes beyond 1.50x the 200-day ATR baseline,
        # the market is in flash-crash territory. Skip the 2-scan confirmation
        # and force REGIME_3_CRISIS immediately.
        if (
            not bkc_mode
            and rv_ratio > settings.ATR_CB_THRESHOLD
        ):
            if self.current_regime != Regime.REGIME_3_CRISIS:
                logger.warning(
                    "regime_cb_override",
                    from_regime=self.current_regime.value,
                    to_regime="REGIME_3_CRISIS",
                    rv_ratio=round(rv_ratio, 4),
                    threshold=settings.ATR_CB_THRESHOLD,
                    reason="ATR circuit breaker -- immediate transition, no scan delay",
                )
                self._prior_regime = self.current_regime
                self.current_regime = Regime.REGIME_3_CRISIS
                self._consecutive_in_range = settings.REGIME_TRANSITION_SCANS
            nb_ratio = nifty_close / banknifty_close if banknifty_close > 0 else 1.0
            self.current_score = max(
                0.0,
                min(100.0, self._calc_atr_score(rv_ratio) * settings.RV_ATR_WEIGHT),
            )
            return RegimeState(
                regime=self.current_regime,
                regime_score=self.current_score,
                rv_ratio=rv_ratio,
                realized_vol=realized_vol,
                nb_ratio=nb_ratio,
                nifty_50=nifty_close,
                nifty_ema20=nifty_ema20,
                breadth=breadth,
                consecutive_scans=self._consecutive_in_range,
            )

        if candidate == self.current_regime:
            pass  # stay stable -- counter just keeps accumulating naturally
        else:
            self._consecutive_in_range += 1

        if self._consecutive_in_range >= settings.REGIME_TRANSITION_SCANS:
            if candidate != self.current_regime:
                logger.info(
                    "regime_transition",
                    from_regime=self.current_regime.value,
                    to_regime=candidate.value,
                    score=round(self.current_score, 2),
                    rv_ratio=round(rv_ratio, 4),
                    realized_vol=round(realized_vol, 4),
                )
                self._prior_regime = self.current_regime
                self.current_regime = candidate
                self._consecutive_in_range = settings.REGIME_TRANSITION_SCANS

        nb_ratio = nifty_close / banknifty_close if banknifty_close > 0 else 1.0

        # Compute score using the formula matching the active path:
        #   backward-compat VIX path -> old VIX formula (matches get_regime_for_scan)
        #   VIX-free path          -> ATR+RV formula
        if bkc_mode:
            self.current_score = self._compute_bk_score(
                vix, nifty_50, nifty_ema20, breadth
            )
        else:
            self.current_score = self.compute_score_full(
                nifty_atr_current=nifty_atr_current,
                nifty_atr_baseline=nifty_atr_baseline,
                realized_vol=realized_vol,
                nifty_close=nifty_close,
                nifty_ema20=nifty_ema20,
                banknifty_close=banknifty_close,
                nb_ratio_history=nb_ratio_history,
                breadth=breadth,
            )

        return RegimeState(
            regime=self.current_regime,
            regime_score=self.current_score,
            rv_ratio=rv_ratio,
            realized_vol=realized_vol,
            nb_ratio=nb_ratio,
            nifty_50=nifty_close,
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
            Regime.UNKNOWN: settings.RISK_PCT_REGIME1,
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
