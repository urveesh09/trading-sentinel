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
import statistics
from datetime import datetime, timezone
from typing import Dict, Optional, List

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
    """Singleton-style state holder + classifier for the penny subsystem.

    [FIX-PHASE2-AUDIT 2026-07-09] Made into a real singleton via __new__.
    Pre-fix each `PennyRegimeEngine()` constructor call returned a fresh
    instance with `_vol_rank = None`, so `penny_scanner._regime_to_size_pct`
    (which created a transient engine on every read) and the long-lived
    `_penny_regime_engine` in main.py were seeing different state. Vol
    ranks fed into the scanner's transient engine were silently dropped.
    With __new__ below, every reference now resolves to the same instance.
    """

    # Module-level singleton storage so the engine is shared across all
    # callers (scanner, main, tests). Resetting `__init__`-style requires
    # explicit `reset_state()`; that prevents surprise clobbering mid-day.
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Only run __init__ the very first time; subsequent constructor
            # calls are treated as access-only.
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        # Guard against re-initialisation when callers do "PennyRegimeEngine()"
        # repeatedly expecting a fresh state. Tests that need fresh state
        # should call PennyRegimeEngine.reset_state() first.
        if getattr(self, "_initialized", False):
            return
        self._today_regime: PennyRegime = PennyRegime.UNKNOWN
        self._as_of: Optional[str] = None
        # [TIER0-0.4 2026-07-14] Per-ticker ranks for today, keyed by ticker.
        # _vol_rank is the MEDIAN of these -- see update_vol_rank() for why the
        # old running-max made the whole penny book untradeable.
        self._vol_ranks: Dict[str, float] = {}
        self._vol_rank: Optional[float] = None
        self._vix_proxy: Optional[float] = None
        # [TIER3-REGIME-CONFIDENCE 2026-06-25] Persist the raw Nifty-50-vs-EMA50
        # distance and breadth for the confidence-reason generator. These
        # are the inputs the operator wants to see to UNDERSTAND the
        # classification, not just the final regime label.
        self._vix_distance: Optional[float] = None
        self._breadth: Optional[float] = None
        self._initialized = True

    @classmethod
    def reset_state(cls) -> None:
        """Drop the singleton. Test-only; production should never call this."""
        cls._instance = None

    # ---- public read API ------------------------------------------------

    @property
    def today_regime(self) -> PennyRegime:
        return self._today_regime

    @property
    def as_of(self) -> Optional[str]:
        return self._as_of

    @property
    def vix_proxy(self) -> Optional[float]:
        return self._vix_proxy

    @property
    def vix_distance(self) -> Optional[float]:
        """Raw Nifty-50 close vs EMA50 distance (e.g. -0.03 = 3% below EMA).
        Exposed for the regime-confidence reason generator."""
        return self._vix_distance

    @property
    def vol_rank(self) -> Optional[float]:
        """MEDIAN per-stock realized vol rank across the universe today -- i.e.
        what the typical penny stock is doing, not what the single hottest one is.
        Exposed for the regime-confidence reason generator.

        [TIER0-0.4 2026-07-14] Was the running max, which pinned the book to
        PR3_HOT permanently. See update_vol_rank()."""
        return self._vol_rank

    @property
    def breadth(self) -> Optional[float]:
        return self._breadth

    def confidence_reasons(self) -> List[str]:
        """
        [TIER3-REGIME-CONFIDENCE 2026-06-25] Return the 1-3 human-readable
        reasons that justify the current regime classification.

        Each reason shows the input value + the threshold it crossed (or
        didn't cross). Operator can read this in the Telegram /penny
        regime reply and immediately understand WHY the system is in
        PR1 vs PR2 vs PR3 today.

        Returns: a list of strings, one per input source. Empty list
        if regime hasn't been computed yet (UNKNOWN).
        """
        reasons: List[str] = []
        regime = self._today_regime

        # 1. Vol rank reason
        if self._vol_rank is not None:
            vr = self._vol_rank
            label = (
                f"vol_rank={vr:.2f}"
            )
            if vr >= _VOL_PR2_MAX:
                reasons.append(
                    f"{label} >= PR2 max {_VOL_PR2_MAX:.2f} (above PR3 threshold -- all entries blocked)"
                )
            elif vr >= _VOL_PR1_MAX:
                reasons.append(
                    f"{label} between PR1 max {_VOL_PR1_MAX:.2f} and PR2 max {_VOL_PR2_MAX:.2f}"
                )
            else:
                reasons.append(
                    f"{label} below PR1 max {_VOL_PR1_MAX:.2f} (calm)"
                )
        else:
            reasons.append("vol_rank: unknown (no scan fed per-stock vol yet)")

        # 2. VIX proxy reason (the headline indicator)
        if self._vix_proxy is not None:
            vp = self._vix_proxy
            label = f"vix_proxy={vp:.2f}"
            if vp >= _VIX_PR2_MAX:
                reasons.append(
                    f"{label} >= PR2 max {_VIX_PR2_MAX:.2f} (Nifty deeply below EMA -- panic territory)"
                )
            elif vp >= _VIX_PR1_MAX:
                reasons.append(
                    f"{label} between PR1 max {_VIX_PR1_MAX:.2f} and PR2 max {_VIX_PR2_MAX:.2f}"
                )
            else:
                reasons.append(
                    f"{label} below PR1 max {_VIX_PR1_MAX:.2f} (Nifty above EMA -- bullish/calm)"
                )
            # Add the raw distance for context (operator can spot drift)
            if self._vix_distance is not None:
                reasons.append(
                    f"  raw: Nifty 50 is {self._vix_distance*100:+.1f}% vs 50-day EMA"
                )
        else:
            reasons.append("vix_proxy: unknown (Nifty 50 fetch failed at 09:20)")

        # 3. Breadth (currently placeholder; surface transparently)
        reasons.append(
            f"breadth={self._breadth if self._breadth is not None else 'n/a'} "
            "(placeholder; weighted 20% in regime score)"
        )

        # 4. Final classification summary (1 line)
        reasons.append(
            f"=> classified {regime.value} "
            f"(sizing: {self.size_pct(regime)*100:.1f}% of bankroll per trade)"
        )

        return reasons

    # ---- public compute API --------------------------------------------

    def compute_vol_rank(
        self, closes: List[float], bars_per_day: Optional[int] = None,
    ) -> float:
        """
        Per-stock realized volatility proxy.
        Returns a normalized [0, 1] rank: 0 = quiet, 1 = most-volatile seen.
        Short / constant series return 0.5 (degenerate).

        [ROADMAP-3.6 2026-07-12] The 0.10 soft cap is calibrated for
        DAILY realized vol, but the scanner feeds ONE DAY of 1-min
        closes. Per-bar 1-min stdev is ~0.001-0.005 -- compared raw
        against the 0.10 cap it produced vol_rank ~= 0 for every ticker
        every day, so the 40%-weight input never influenced the regime
        (it rode on the VIX proxy alone). Pass `bars_per_day` (375 for
        NSE 1-min bars) to scale the per-bar stdev by sqrt(bars_per_day)
        to a daily equivalent before normalizing. Omitted = input is
        already daily-ish (back-compat with direct callers/tests).
        Intraday realized vol excludes overnight gaps, so this still
        slightly UNDER-states true daily vol -- acceptable: the cap is a
        soft ceiling and PR3 blocking has the VIX proxy as second input.
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
        if bars_per_day is not None and bars_per_day > 1:
            sd *= math.sqrt(bars_per_day)
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
        """
        Map the two inputs to a PennyRegime per spec §6.3.

        [FAIL-OPEN 2026-06-26] When either input is missing, do NOT
        return UNKNOWN. The earlier UNKNOWN behaviour sized at 0% per
        trade via the risk engine (UNKNOWN -> 0.0 in _DEFAULT_SIZE),
        which blocked every penny entry whenever the scanner had not
        yet fed vol_rank or the VIX proxy feed had no data. Rule 15
        (operator mandate): "don't kill proactiveness for lack of
        data." The scanner can still surface uncertainty via
        confidence_reasons() and the penny_regime_computed log line.

        [ROADMAP-3.6 2026-07-12] Fail-open reworked, two rules:
          1. A missing input FLOORS the regime at PR2_ELEVATED (2.5%
             sizing) -- half-blind is elevated uncertainty by
             definition, never PR1_CALM full 5% (the old fail-open
             traded full size through data outages).
          2. The input we DO have is still respected: vix_proxy=0.95
             with vol_rank missing is a PR3 print, and the old blanket
             fail-open made PR3_HOT unreachable every morning until
             the first scan fed vol_rank (the phase-2 audit finding).
        """
        if vol_rank is None or vix_proxy is None:
            vr = vol_rank if vol_rank is not None else 0.0
            vp = vix_proxy if vix_proxy is not None else 0.0
            if vr >= _VOL_PR2_MAX or vp >= _VIX_PR2_MAX:
                return PennyRegime.PR3_HOT
            return PennyRegime.PR2_ELEVATED
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
            # [TIER0-0.4] Clear yesterday's cross-section too, or today's median
            # would be computed over a mix of two days' ranks.
            self._vol_ranks = {}
            self._vol_rank = None  # will be set by scanner.update_vol_rank()
            self._breadth = breadth

            # VIX proxy from Nifty 50 daily closes.
            bars = await kite.get_historical(
                ticker="NIFTY 50",
                from_date="2026-01-01",  # overridden by Kite to last 60d usually
                to_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )
            if bars is not None and not (hasattr(bars, 'empty') and bars.empty):
                if hasattr(bars, 'columns'):
                    # pandas DataFrame
                    closes = bars["close"].tolist() if "close" in bars.columns else []
                else:
                    # list of dicts (legacy)
                    closes = [b["close"] for b in bars if b.get("close")]
                self._vix_proxy = self.compute_vix_proxy(closes)
                # [TIER3-REGIME-CONFIDENCE 2026-06-25] Persist the raw
                # Nifty-50-vs-EMA50 distance too, so the confidence
                # reason can show "Nifty is -3.2% vs EMA50" (the raw input
                # the operator wants to see, not just the normalised 0-1).
                if closes and len(closes) >= 50:
                    ema_period = 50
                    alpha = 2.0 / (ema_period + 1)
                    sma = sum(closes[:ema_period]) / ema_period
                    ema = sma
                    for c in closes[ema_period:]:
                        ema = alpha * c + (1 - alpha) * ema
                    if ema > 0:
                        self._vix_distance = (closes[-1] - ema) / ema
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

    def update_vol_rank(self, ticker_vol_rank: float, ticker: Optional[str] = None) -> None:
        """
        Scanner feeds in each stock's realized-vol rank. The engine aggregates
        them into ONE number describing the market.

        [TIER0-0.4 2026-07-14] That aggregate is now the MEDIAN across the
        universe. It used to be the running MAX, and it never fell back down:

            if self._vol_rank is None or ticker_vol_rank > self._vol_rank:
                self._vol_rank = ticker_vol_rank      # monotonic ratchet

        That made the penny book structurally untradeable, and the arithmetic is
        deterministic, not unlucky:

          * compute_vol_rank is NOT a cross-sectional rank -- it is sd/0.10,
            SATURATING at exactly 1.0 for any stock with >=10% daily vol.
          * Penny stocks routinely clear 10% daily vol, so several names in any
            100-name penny universe return exactly 1.0 every single day.
          * max(...) over the universe is therefore ~1.0 by lunchtime, always.
          * classify() calls PR3_HOT at vol_rank >= 0.90, and
            PENNY_RISK_PCT_PR3 = 0.0 means PR3 takes NO entries.

        Result: 0 accepts in 349,297 lifetime evaluations, with 93.4% of a
        typical day's rejects reading "regime PR3_HOT (no new entries)". One hot
        stock silenced the entire book, permanently. The comment called this "a
        conservative aggregate"; it was not conservative, it was unsatisfiable --
        the same dead-gate shape as the day_high anchor bug.

        The median describes the market rather than its single worst member, and
        it is recomputed from the current cross-section on every scan, so the
        regime can COOL DOWN as well as heat up. A genuinely hot tape still moves
        the median and still throttles size (see PENNY_RISK_PCT_PR3, now a reduced
        size rather than a shutdown).
        """
        key = ticker or f"_anon_{len(self._vol_ranks)}"
        self._vol_ranks[key] = ticker_vol_rank

        self._vol_rank = self._aggregate_vol_rank()
        self._today_regime = self.classify(self._vol_rank, self._vix_proxy)
        logger.info(
            "penny_regime_updated ticker=%s rank=%s aggregate=%s n=%d regime=%s",
            key, ticker_vol_rank, self._vol_rank, len(self._vol_ranks),
            self._today_regime.value,
        )

    def _aggregate_vol_rank(self) -> Optional[float]:
        """Median of the per-ticker vol ranks seen so far today."""
        if not self._vol_ranks:
            return None
        return statistics.median(self._vol_ranks.values())
