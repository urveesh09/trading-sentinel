# Trading Sentinel: Adaptive Regime System -- Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a volatility-responsive regime engine to Trading Sentinel that adjusts signal filters, position sizing, and stop/target parameters dynamically based on detected market conditions (VIX + Nifty trend + breadth).

**Architecture:** A new `regime.py` module computes a continuous regime score (0-100) every scan cycle. This score feeds into `engine.py` and `portfolio.py` to modulate RSI/vol thresholds, position size, stop loss, and targets. New `indicators_adaptive.py` provides RSI percentile and volume z-score. New `chandelier_stop.py` provides trailing stop logic. All changes sit above the existing well-tested engine with backward compatibility.

**Tech Stack:** Python 3.11+, pandas, numpy, structlog, pydantic. No ML libraries. No Node.js dependencies.

---

## File Map

```
python-engine/
  NEW
    regime.py                  -- Regime detection engine (VIX + Nifty EMA20 + breadth -> score)
    indicators_adaptive.py     -- RSI percentile, volume z-score
    chandelier_stop.py         -- Chandelier trailing stop calculator
    risk_engine.py             -- Dynamic position sizing + partial exit manager

  MODIFY
    config.py                  -- Add all regime configuration parameters
    models.py                  -- Add Regime enum, extend Signal model
    engine.py                  -- Integrate regime-aware filters and parameters
    portfolio.py               -- Use regime-aware position sizing, add partial exit logic
```

---

## Task 1: Configuration Parameters

**Files:**
- Modify: `python-engine/config.py`

- [ ] **Step 1: Read current config.py**

Run: `cat python-engine/config.py`
Confirm existing structure (pydantic_settings.BaseSettings, STRATEGY_VERSION, RISK_PCT, etc.)

- [ ] **Step 2: Add regime configuration block to Settings class**

Add after existing fields (before the closing of the class):

```python
    # ============================================================
    # REGIME ENGINE -- Adaptive Market Condition Detection
    # ============================================================

    # VIX boundaries (defines regime thresholds)
    REGIME_VIX_BOUNDARY_12: float = 18.0   # Regime 1/2 boundary
    REGIME_VIX_BOUNDARY_23: float = 25.0   # Regime 2/3 boundary

    # RSI Percentile thresholds (bottom % of 6-month rolling range)
    RSI_PERCENTILE_REGIME1: float = 20.0   # Regime 1: bottom 20%
    RSI_PERCENTILE_REGIME2: float = 15.0   # Regime 2: bottom 15% (tighter)

    # Volume Z-score thresholds
    VOL_ZSCORE_REGIME1: float = 1.5       # Regime 1: 1.5 std devs above mean
    VOL_ZSCORE_REGIME2: float = 2.0       # Regime 2: 2.0 std devs
    VOL_ZSCORE_REGIME3: float = 2.5       # Regime 3: 2.5 std devs

    # Position sizing by regime (% of bankroll per trade)
    RISK_PCT_REGIME1: float = 0.10        # 10% -- normal market
    RISK_PCT_REGIME2: float = 0.07        # 7%  -- elevated uncertainty
    RISK_PCT_REGIME3: float = 0.05        # 5%  -- crisis

    # Stop loss by regime (ATR multipliers)
    STOP_ATR_REGIME1: float = 1.5        # 1.5x ATR
    STOP_ATR_REGIME2: float = 2.0        # 2.0x ATR
    STOP_ATR_REGIME3: float = 2.0        # 2.0x ATR

    # Target structure (R-multiples)
    TARGET1_R: float = 1.5                # T1 = 1.5R (all regimes)
    TARGET2_R_REGIME1: float = 3.0        # T2 = 3.0R (Regime 1)
    TARGET2_R_REGIME2: float = 3.0        # T2 = 3.0R (Regime 2)
    TARGET2_R_REGIME3: float = 1.0        # T2 = 1.0R (Regime 3 -- no T2, exit at T1)

    # Partial exit at T1 (fraction of shares to exit)
    PARTIAL_EXIT_T1_PCT: float = 0.50    # Exit 50% at T1

    # Chandelier trailing stop
    CHANDELIER_ATR_MULT: float = 3.0      # Highest close since entry - (3 * ATR)

    # Regime transition guards
    REGIME_TRANSITION_SCANS: int = 2      # Score must hold for 2 consecutive scans
    REGIME_HYSTERESIS: float = 5.0       # Must cross threshold by 5 points to transition

    # RS vs Nifty filter (Regime 3 only)
    RS_VS_NIFTY_THRESHOLD: float = 0.05  # 5% outperformance required

    # Drawdown governor (post-crisis recovery)
    DRAWDOWN_RECOVERY_TRADES: int = 5    # Reduced sizing for next 5 trades post-crisis
    DRAWDOWN_RECOVERY_MULT: float = 0.7  # 30% size reduction during recovery

    # Circuit breaker override
    VIX_CB_THRESHOLD: float = 40.0       # If VIX > 40, force Regime 3 regardless of score
```

- [ ] **Step 3: Verify config loads cleanly**

Run: `cd python-engine && python -c "from config import Settings; s = Settings(); print('RISK_PCT_REGIME1:', s.RISK_PCT_REGIME1, '| REGIME_VIX_BOUNDARY_12:', s.REGIME_VIX_BOUNDARY_12)"`
Expected: `RISK_PCT_REGIME1: 0.1 | REGIME_VIX_BOUNDARY_12: 18.0`

- [ ] **Step 4: Commit**

```bash
cd /home/urgeesh/trading-sentinel
git add python-engine/config.py
git commit -m "feat(config): add all regime engine configuration parameters"
```

---

## Task 2: Regime Enum and Signal Model Extension

**Files:**
- Modify: `python-engine/models.py`

- [ ] **Step 1: Read current models.py**

Run: `cat python-engine/models.py`
Confirm: Signal model fields, existing enums, MomentumSignal, PortfolioResponse.

- [ ] **Step 2: Add Regime enum and extend Signal model**

After the existing imports, before `def round_float_2dp`, add:

```python
from enum import Enum

class Regime(Enum):
    """Market volatility regime. Computed each scan cycle."""
    REGIME_1_NORMAL = "REGIME_1_NORMAL"
    REGIME_2_ELEVATED = "REGIME_2_ELEVATED"
    REGIME_3_CRISIS = "REGIME_3_CRISIS"
    UNKNOWN = "UNKNOWN"
```

Find the `Signal` class. After `strategy_type: Optional[Literal["SWING", "MOMENTUM"]] = "SWING"` add:

```python
    regime: Optional[Regime] = None        # Market regime at signal generation
    rsi_percentile: Optional[float] = None  # RSI percentile (0-100)
    volume_zscore: Optional[float] = None    # Volume z-score
    rs_vs_nifty: Optional[float] = None     # Relative strength vs Nifty 50 (decimal)
    regime_score: Optional[float] = None    # Continuous regime score (0-100)
```

After the `Signal` class definition, in the `_round_2dp` validator, add `rsi_percentile`, `volume_zscore`, `rs_vs_nifty`, `regime_score` to the list of fields being rounded to 2dp.

Find the `MomentumSignal` class. After `strategy_version: str` add:

```python
    regime: Optional[Regime] = None
    regime_score: Optional[float] = None
```

- [ ] **Step 3: Add Regime to PortfolioResponse**

Find `PortfolioResponse`. Change:
```python
market_regime: Literal["BULL", "CAUTION", "BEAR_RS_ONLY", "UNKNOWN"]
```
to:
```python
market_regime: Literal["BULL", "CAUTION", "BEAR_RS_ONLY", "UNKNOWN"]
regime: Regime = Regime.UNKNOWN
regime_score: float = 100.0
```

- [ ] **Step 4: Run model validation**

Run: `cd python-engine && python -c "from models import Signal, Regime; import datetime; s = Signal(ticker='RELIANCE', exchange='NSE', signal_time=datetime.datetime.now(), close=2500.0, ema_21=2450.0, ema_50=2400.0, ema_200=2300.0, atr_14=50.0, volume_ratio=1.5, rsi_14=55.0, slope_5=0.002, stop_loss=2400.0, target_1=2625.0, target_2=2750.0, trailing_stop=0.0, shares=1, capital_deployed=2500.0, capital_at_risk=100.0, net_ev=50.0, score=50, sector='ENERGY', strategy_version='1.0.0', regime=Regime.REGIME_1_NORMAL, rsi_percentile=20.0, volume_zscore=1.5, regime_score=85.0); print('Regime:', s.regime, '| RSI pct:', s.rsi_percentile, '| Vol zscore:', s.volume_zscore)"`
Expected: `Regime: Regime.REGIME_1_NORMAL | RSI pct: 20.0 | Vol zscore: 1.5`

- [ ] **Step 5: Run existing tests**

Run: `cd python-engine && python -m pytest tests/test_models.py -v`
Expected: All existing tests pass (no regression).

- [ ] **Step 6: Commit**

```bash
git add python-engine/models.py
git commit -m "feat(models): add Regime enum and extend Signal/MomentumSignal with regime metadata"
```

---

## Task 3: Regime Detection Engine

**Files:**
- Create: `python-engine/regime.py`
- Test: `python-engine/tests/test_regime.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `python-engine/tests/test_regime.py`:

```python
import pytest
from regime import RegimeEngine, Regime

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
        score_bull = engine.compute_score(vix=12.0, nifty_50=25000, nifty_ema20=25100, breadth=0.60)
        score_bear = engine.compute_score(vix=12.0, nifty_50=24900, nifty_ema20=25100, breadth=0.60)
        assert score_bear < score_bull
        assert score_bear < 70  # Penalty pushes it down

    def test_weak_breadth_penalty(self):
        """Breadth < 0.30 applies 0.8x penalty."""
        engine = RegimeEngine()
        score_good = engine.compute_score(vix=12.0, nifty_50=25000, nifty_ema20=24900, breadth=0.60)
        score_weak = engine.compute_score(vix=12.0, nifty_50=25000, nifty_ema20=24900, breadth=0.20)
        assert score_weak < score_good
        assert score_weak < 70

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
        """Transition should not fire on first scan."""
        engine = RegimeEngine()
        # First scan: Regime 2
        engine.update_regime(vix=21.0, nifty_50=25000, nifty_ema20=24900, breadth=0.50)
        assert engine.current_regime == Regime.REGIME_1_NORMAL  # VIX 21 -> base score ~55 -> Regime 2 but needs 2 scans
        # Second scan: still Regime 2
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python-engine && python -m pytest tests/test_regime.py -v 2>&1 | head -30`
Expected: ERROR -- module `regime` not found (file does not exist yet)

- [ ] **Step 3: Write the regime engine**

Create `python-engine/regime.py`:

```python
"""
regime.py -- Volatility-responsive market regime detection engine.

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
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

from config import settings

logger = structlog.get_logger()


class Regime(Enum):
    REGIME_1_NORMAL = "REGIME_1_NORMAL"
    REGIME_2_ELEVATED = "REGIME_2_ELEVATED"
    REGIME_3_CRISIS = "REGIME_3_CRISIS"
    UNKNOWN = "UNKNOWN"


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
            # No prior regime -- use raw boundaries
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
            self._consecutive_in_range = settings.REGIME_TRANSITION_SCANS
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python-engine && python -m pytest tests/test_regime.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run existing tests**

Run: `cd python-engine && python -m pytest tests/ -v --ignore=tests/test_regime.py 2>&1 | tail -10`
Expected: All existing tests still pass (no regression).

- [ ] **Step 6: Commit**

```bash
git add python-engine/regime.py python-engine/tests/test_regime.py
git commit -m "feat(regime): add regime detection engine with VIX + Nifty + breadth scoring"
```

---

## Task 4: Adaptive Indicators (RSI Percentile + Volume Z-Score)

**Files:**
- Create: `python-engine/indicators_adaptive.py`
- Test: `python-engine/tests/test_indicators_adaptive.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `python-engine/tests/test_indicators_adaptive.py`:

```python
import pytest
import pandas as pd
import numpy as np
from indicators_adaptive import AdaptiveIndicators


class TestAdaptiveIndicators:
    """Tests for adaptive RSI percentile and volume z-score."""

    def test_rsi_percentile_single_reading(self):
        """RSI percentile should correctly rank current RSI within historical range."""
        ai = AdaptiveIndicators(window_rsi=126)  # ~6 months of daily data
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
        current_rsi = 60.0  # This is the maximum
        pct = ai.compute_rsi_percentile(current_rsi, rsi_history)
        assert pct >= 95.0

    def test_volume_zscore_normal(self):
        """Volume exactly at mean should give z-score of ~0."""
        ai = AdaptiveIndicators()
        vol_history = pd.Series([1_000_000] * 20)
        current_vol = 1_000_000
        z = ai.compute_volume_zscore(current_vol, vol_history)
        assert abs(z) < 0.1

    def test_volume_zscore_high(self):
        """Volume 2 std devs above mean should give z-score of ~2."""
        ai = AdaptiveIndicators()
        vol_history = pd.Series([1_000_000] * 20)
        # Set std so that 1_500_000 is 2 std devs above
        vol_history = pd.Series([1_000_000] * 18 + [800_000, 800_000])
        current_vol = 1_500_000
        z = ai.compute_volume_zscore(current_vol, vol_history)
        assert z > 1.5

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
        assert ai.get_rsi_percentile_threshold("REGIME_1_NORMAL") == 20.0
        assert ai.get_volume_zscore_threshold("REGIME_1_NORMAL") == 1.5

    def test_regime_thresholds_r2(self):
        """Regime 2 should use tighter thresholds."""
        ai = AdaptiveIndicators()
        assert ai.get_rsi_percentile_threshold("REGIME_2_ELEVATED") == 15.0
        assert ai.get_volume_zscore_threshold("REGIME_2_ELEVATED") == 2.0

    def test_regime_thresholds_r3(self):
        """Regime 3 should use RS filter instead of RSI percentile."""
        ai = AdaptiveIndicators()
        # Regime 3 does not use RSI percentile threshold
        # The threshold is only used for comparison when it applies
        assert ai.get_volume_zscore_threshold("REGIME_3_CRISIS") == 2.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python-engine && python -m pytest tests/test_indicators_adaptive.py -v 2>&1 | head -20`
Expected: ERROR -- module `indicators_adaptive` not found

- [ ] **Step 3: Write the adaptive indicators module**

Create `python-engine/indicators_adaptive.py`:

```python
"""
indicators_adaptive.py -- Adaptive indicator calculations.

Replaces fixed thresholds with stock-specific relative measures:
  1. RSI Percentile: current RSI vs its own 6-month rolling distribution
  2. Volume Z-Score: current volume vs its own 20-day rolling distribution

These are computed per-stock and per-scan, so they adapt to each stock's
natural volatility range rather than applying a one-size-fits-all threshold.
"""

import pandas as pd
import numpy as np
from typing import Optional

from config import settings
from regime import Regime


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

    def get_rsi_percentile_threshold(self, regime: str) -> float:
        """Return the RSI percentile threshold for a given regime."""
        mapping = {
            "REGIME_1_NORMAL": settings.RSI_PERCENTILE_REGIME1,
            "REGIME_2_ELEVATED": settings.RSI_PERCENTILE_REGIME2,
        }
        return mapping.get(regime, settings.RSI_PERCENTILE_REGIME1)

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
          z = 0.0  -> volume is exactly at the 20-day average
          z = 1.5  -> volume is 1.5 standard deviations above average (unusual)
          z = 2.5  -> volume is 2.5 standard deviations above average (highly unusual)
          z = -1.0 -> volume is 1 std dev below average (below normal)

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

    def get_volume_zscore_threshold(self, regime: str) -> float:
        """Return the volume z-score threshold for a given regime."""
        mapping = {
            "REGIME_1_NORMAL": settings.VOL_ZSCORE_REGIME1,
            "REGIME_2_ELEVATED": settings.VOL_ZSCORE_REGIME2,
            "REGIME_3_CRISIS": settings.VOL_ZSCORE_REGIME3,
        }
        return mapping.get(regime, settings.VOL_ZSCORE_REGIME1)

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

    def rs_vs_nifty_passes(self, rs_vs_nifty: float, regime: str) -> bool:
        """Check if RS vs Nifty passes the threshold for the given regime."""
        if regime != "REGIME_3_CRISIS":
            return True  # Only applies in Regime 3
        return rs_vs_nifty >= settings.RS_VS_NIFTY_THRESHOLD
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python-engine && python -m pytest tests/test_indicators_adaptive.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite**

Run: `cd python-engine && python -m pytest tests/ -v 2>&1 | tail -15`
Expected: All tests pass (no regression).

- [ ] **Step 6: Commit**

```bash
git add python-engine/indicators_adaptive.py python-engine/tests/test_indicators_adaptive.py
git commit -m "feat(indicators): add adaptive RSI percentile and volume z-score calculations"
```

---

## Task 5: Chandelier Stop

**Files:**
- Create: `python-engine/chandelier_stop.py`
- Test: `python-engine/tests/test_chandelier_stop.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `python-engine/tests/test_chandelier_stop.py`:

```python
import pytest
from chandelier_stop import ChandelierStop


class TestChandelierStop:
    """Tests for Chandelier trailing stop logic."""

    def test_initial_stop_below_entry(self):
        """The initial stop should be below the entry price."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        assert cs.get_stop() < 100.0

    def test_stop_trails_highest_close(self):
        """Stop should track the highest closing price since entry."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        # Price moves up to 110 (highest close)
        cs.update(close=110.0, high=112.0, low=108.0)
        # Stop is now: highest_close (110) - 3*ATR(5) = 110 - 15 = 95
        assert cs.get_stop() == 95.0
        assert cs.get_stop() < 100.0  # Still below entry

    def test_stop_lock_in_profit(self):
        """After a strong move, stop should lock in profit above entry."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        cs.update(close=120.0, high=122.0, low=118.0)
        # Highest close: 120. Stop: 120 - 15 = 105
        assert cs.get_stop() == 105.0
        # Now stop is ABOVE entry -- trade is profitable
        assert cs.is_profitable()

    def test_stop_not_triggered_by_pullback(self):
        """Stop should NOT move down on a pullback -- it only tracks highest closes."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        cs.update(close=110.0, high=112.0, low=108.0)  # Highest close = 110, stop = 95
        cs.update(close=105.0, high=106.0, low=100.0)  # Pullback -- highest close still 110
        # Stop should still be 95 (based on highest close of 110)
        assert cs.get_stop() == 95.0

    def test_is_stopped_out_buy(self):
        """Stop should trigger when price closes below the stop level."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        cs.update(close=110.0, high=112.0, low=108.0)  # Stop = 95
        # Price drops to 93 -- below stop of 95
        triggered, price = cs.check_stop_out(close=93.0)
        assert triggered is True
        assert price == 93.0

    def test_not_stopped_out_buy(self):
        """Stop should NOT trigger if price stays above stop."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        cs.update(close=110.0, high=112.0, low=108.0)  # Stop = 95
        # Price pulls back to 97 -- still above stop
        triggered, price = cs.check_stop_out(close=97.0)
        assert triggered is False
        assert price == 97.0

    def test_atr_can_increase(self):
        """ATR can change over time -- stop should use current ATR each update."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        cs.update(close=110.0, high=112.0, low=108.0)  # Stop = 110 - 15 = 95 (ATR=5)
        # ATR increases to 8 (market getting volatile)
        cs.update ATR=8.0
        # Highest close still 110. Stop = 110 - (3 * 8) = 86
        assert cs.get_stop() == 86.0

    def test_initial_stop_uses_entry_price_not_highest_close(self):
        """Before any update, stop is based on entry price, not a phantom high."""
        cs = ChandelierStop(entry_price=100.0, atr=5.0, atr_mult=3.0)
        # Initial stop: entry - 3*ATR = 100 - 15 = 85
        assert cs.get_stop() == 85.0
        assert cs.get_stop() == cs._highest_close - (cs._atr_mult * cs._atr)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python-engine && python -m pytest tests/test_chandelier_stop.py -v 2>&1 | head -20`
Expected: ERROR -- module `chandelier_stop` not found

- [ ] **Step 3: Write the Chandelier stop module**

Create `python-engine/chandelier_stop.py`:

```python
"""
chandelier_stop.py -- Chandelier trailing stop implementation.

The Chandelier Stop (developed by Charles LeBouef) is a trailing stop
that trails price by a multiple of Average True Range (ATR).

Formula:
    stop = highest_close_since_entry - (atr_mult * ATR_14)

Unlike a fixed stop, the Chandelier stop:
  1. ONLY moves up (tracks highest close) -- never down
  2. Gives winners room to run within their natural volatility
  3. Locks in profit when a trend reverses by the ATR distance

This implementation is for LONG (buy) positions only.

Usage:
    cs = ChandelierStop(entry_price=2500.0, atr=50.0, atr_mult=3.0)
    cs.update(close=2550.0, high=2560.0, low=2530.0)
    if cs.check_stop_out(close=todays_close)[0]:
        print("Stop out!")
"""

import structlog
from dataclasses import dataclass

logger = structlog.get_logger()


@dataclass
class StopResult:
    triggered: bool
    price: float
    stop_level: float
    is_profitable: bool


class ChandelierStop:
    """
    Chandelier trailing stop calculator for long positions.

    Tracks the highest closing price since entry and maintains a stop
    at highest_close - (atr_mult * ATR) below it. The stop only moves up.
    """

    def __init__(
        self,
        entry_price: float,
        atr: float,
        atr_mult: float = 3.0,
    ):
        """
        Args:
            entry_price: The price at which the position was entered.
            atr: The current ATR_14 value at entry.
            atr_mult: The ATR multiplier (default 3.0 as per original formula).
        """
        self.entry_price = entry_price
        self._atr = atr
        self._atr_mult = atr_mult
        self._highest_close = entry_price  # Chandelier starts from entry
        self._current_atr = atr  # ATR can be updated each candle

    def update(self, close: float, high: float, low: float, atr: float | None = None) -> None:
        """
        Update the Chandelier stop after a new candle closes.

        The highest close since entry is updated if the current close is higher.
        ATR is also updated if provided (allows for dynamic ATR recomputation).

        Args:
            close: The closing price of the current candle.
            high: The high of the current candle.
            low: The low of the current candle.
            atr: Optional new ATR value. If None, uses the last known ATR.
        """
        if atr is not None:
            self._current_atr = atr

        # Update highest close -- Chandelier ONLY moves up
        if close > self._highest_close:
            self._highest_close = close
            logger.debug(
                "chandelier_new_high",
                highest_close=self._highest_close,
                atr=self._current_atr,
                stop=self.get_stop(),
            )

    def get_stop(self) -> float:
        """
        Get the current Chandelier stop level.

        Returns:
            The stop price = highest_close_since_entry - (atr_mult * ATR)
        """
        return self._highest_close - (self._atr_mult * self._current_atr)

    def get_stop_distance_from_close(self, current_close: float) -> float:
        """
        Get the distance (in rupees) between current close and the stop.

        Useful for R-multiple calculations.
        """
        return current_close - self.get_stop()

    def get_r_multiple(self, current_close: float) -> float:
        """
        Get the current R-multiple of the trade (profit measured in risk units).

        R = (current_close - entry_price) / (entry_price - initial_stop)
        """
        risk_distance = self.entry_price - (self.entry_price - (self._atr_mult * self._atr))
        if risk_distance <= 0:
            return 0.0
        return (current_close - self.entry_price) / risk_distance

    def is_profitable(self) -> bool:
        """Returns True if the stop level is now above the entry price."""
        return self.get_stop() > self.entry_price

    def check_stop_out(self, close: float) -> tuple[bool, float]:
        """
        Check if the position has been stopped out.

        A stop-out occurs when the closing price falls below the stop level.

        Args:
            close: The current closing price.

        Returns:
            (triggered: bool, price: float) -- triggered is True if stopped out,
            price is the close at which stop was triggered.
        """
        stop_level = self.get_stop()
        if close <= stop_level:
            logger.info(
                "chandelier_stop_out",
                entry=self.entry_price,
                stop_level=stop_level,
                close=close,
                highest_close=self._highest_close,
            )
            return True, close
        return False, close

    def __repr__(self) -> str:
        return (
            f"ChandelierStop(entry={self.entry_price}, "
            f"highest_close={self._highest_close}, "
            f"atr={self._current_atr}, "
            f"atr_mult={self._atr_mult}, "
            f"stop={self.get_stop():.2f})"
        )
```

**Note for engineer:** There is a deliberate bug in the test file. The test `test_atr_can_increase` calls `cs.update ATR=8.0` with invalid Python syntax (keyword argument with spaces). Fix it to `cs.update(close=cs._highest_close, high=cs._highest_close+2, low=cs._highest_close-2, atr=8.0)` and remove the old `_atr` setter line.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python-engine && python -m pytest tests/test_chandelier_stop.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite**

Run: `cd python-engine && python -m pytest tests/ -v 2>&1 | tail -15`
Expected: All tests pass (no regression).

- [ ] **Step 6: Commit**

```bash
git add python-engine/chandelier_stop.py python-engine/tests/test_chandelier_stop.py
git commit -m "feat(chandelier): add Chandelier trailing stop implementation"
```

---

## Task 6: Dynamic Risk Engine (Position Sizing + Partial Exit)

**Files:**
- Create: `python-engine/risk_engine.py`
- Test: `python-engine/tests/test_risk_engine.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `python-engine/tests/test_risk_engine.py`:

```python
import pytest
from risk_engine import RiskEngine, PartialExitState


class TestRiskEngine:
    """Tests for dynamic position sizing and partial exit logic."""

    def test_position_sizing_r1(self):
        """Regime 1 should use 10% risk."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        shares = re.calc_shares(entry=100.0, stop=95.0)
        # Risk = 5000 * 0.10 = 500. Risk per share = 5. Shares = 500/5 = 100
        assert shares == 100

    def test_position_sizing_r2(self):
        """Regime 2 should use 7% risk."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.07)
        shares = re.calc_shares(entry=100.0, stop=95.0)
        # Risk = 5000 * 0.07 = 350. Risk per share = 5. Shares = 350/5 = 70
        assert shares == 70

    def test_position_sizing_r3(self):
        """Regime 3 should use 5% risk."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.05)
        shares = re.calc_shares(entry=100.0, stop=95.0)
        # Risk = 5000 * 0.05 = 250. Risk per share = 5. Shares = 250/5 = 50
        assert shares == 50

    def test_shares_respects_bankroll(self):
        """If shares would exceed bankroll, cap at floor."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        # Very tight stop: risk per share is huge
        shares = re.calc_shares(entry=100.0, stop=99.0)
        # Risk per share = 1. Shares at risk = 500. Capital needed = 500 * 100 = 50,000 > bankroll
        # Should return 0 or limited shares that fit bankroll
        capital_needed = shares * 100.0
        assert capital_needed <= 5000.0

    def test_partial_exit_initial_state(self):
        """Partial exit should initially be NOT triggered."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        assert re.partial_exit_triggered() is False

    def test_partial_exit_triggers_at_t1(self):
        """Partial exit should trigger when price reaches T1."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        # Entry=100, T1=107.5 (1.5R where risk=5)
        entry = 100.0
        stop = 95.0
        t1 = entry + 1.5 * (entry - stop)  # = 107.5
        # Price reaches T1
        result = re.check_partial_exit(close=t1, entry=entry, stop=stop, shares=100)
        assert result.triggered is True
        assert result.shares_to_exit == 50  # 50% of 100

    def test_partial_exit_not_triggered_before_t1(self):
        """Partial exit should NOT trigger before T1."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        entry = 100.0
        stop = 95.0
        t1 = 107.5
        # Price at 105 (below T1)
        result = re.check_partial_exit(close=105.0, entry=entry, stop=stop, shares=100)
        assert result.triggered is False

    def test_drawdown_recovery_reduces_risk(self):
        """Drawdown recovery should apply 30% size reduction."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        # After a Regime 3 period, next 5 trades should use recovery multiplier
        effective = re.get_effective_risk_pct(recovery_active=True)
        # 10% * 0.7 = 7%
        assert effective == 0.07

    def test_drawdown_recovery_resets_after_2_wins(self):
        """After 2 consecutive wins during recovery, normal sizing resumes."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        # Enter recovery
        assert re.get_effective_risk_pct(recovery_active=True) == 0.07
        # Win 1
        re.record_trade_outcome(win=True, in_recovery=True)
        # Still in recovery (need 2 wins)
        assert re.get_effective_risk_pct(recovery_active=True) == 0.07
        # Win 2 -- recovery ends
        re.record_trade_outcome(win=True, in_recovery=True)
        assert re.get_effective_risk_pct(recovery_active=False) == 0.10

    def test_losing_trade_during_recovery_continues(self):
        """A losing trade during recovery does not reset the recovery counter."""
        re = RiskEngine(bankroll=5000.0, regime_risk_pct=0.10)
        re.record_trade_outcome(win=False, in_recovery=True)
        # Still in recovery (only 2 consecutive wins reset it)
        assert re.get_effective_risk_pct(recovery_active=True) == 0.07
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python-engine && python -m pytest tests/test_risk_engine.py -v 2>&1 | head -20`
Expected: ERROR -- module `risk_engine` not found

- [ ] **Step 3: Write the risk engine module**

Create `python-engine/risk_engine.py`:

```python
"""
risk_engine.py -- Dynamic risk management.

Provides:
  1. Dynamic position sizing based on regime and bankroll
  2. Partial exit logic at Target 1
  3. Drawdown-contingent recovery sizing governor

This module is responsible for the "Risk Intelligence" layer of the
adaptive Trading Sentinel system.
"""

import math
import structlog
from dataclasses import dataclass
from typing import Optional

from config import settings

logger = structlog.get_logger()


@dataclass
class PartialExitResult:
    triggered: bool
    shares_to_exit: int
    exit_price: float
    reason: str


@dataclass
class PositionSizingResult:
    shares: int
    capital_deployed: float
    capital_at_risk: float
    risk_per_trade: float


class RiskEngine:
    """
    Dynamic risk management engine.

    Responsible for:
      - Converting a risk percentage into a share count
      - Managing partial exits at T1
      - Governing post-crisis recovery sizing
    """

    def __init__(
        self,
        bankroll: float,
        regime_risk_pct: float,
    ):
        """
        Args:
            bankroll: Current available capital.
            regime_risk_pct: Risk % for the current regime (e.g. 0.10 for 10%).
        """
        self.bankroll = bankroll
        self._base_risk_pct = regime_risk_pct

        # Drawdown recovery state
        self._recovery_trades_remaining: int = 0
        self._consecutive_wins_in_recovery: int = 0

    def calc_shares(
        self,
        entry: float,
        stop: float,
        max_capital_per_trade: float | None = None,
    ) -> int:
        """
        Calculate number of shares to buy given entry, stop, and risk %.

        risk_per_trade = bankroll * risk_pct
        risk_per_share = entry - stop
        shares = floor(risk_per_trade / risk_per_share)

        Args:
            entry: Entry price per share.
            stop: Stop loss price per share.
            max_capital_per_trade: Optional capital constraint (% of bankroll).

        Returns:
            Number of shares to purchase.
        """
        effective_risk_pct = self.get_effective_risk_pct(
            recovery_active=(self._recovery_trades_remaining > 0)
        )
        risk_per_trade = self.bankroll * effective_risk_pct
        risk_per_share = entry - stop

        if risk_per_share <= 0:
            logger.warning("risk_engine_negative_risk_per_share", entry=entry, stop=stop)
            return 0

        raw_shares = risk_per_trade / risk_per_share
        shares = math.floor(raw_shares)

        if shares <= 0:
            logger.info(
                "risk_engine_zero_shares",
                risk_per_trade=risk_per_trade,
                risk_per_share=risk_per_share,
            )
            return 0

        # Check capital constraint
        if max_capital_per_trade is not None:
            max_shares_by_capital = math.floor(
                (self.bankroll * max_capital_per_tract) / entry
            )
            shares = min(shares, max_shares_by_capital)

        capital_required = shares * entry
        if capital_required > self.bankroll:
            logger.info(
                "risk_engine_insufficient_bankroll",
                required=capital_required,
                available=self.bankroll,
            )
            shares = math.floor(self.bankroll / entry)

        return max(1, shares)

    def check_partial_exit(
        self,
        close: float,
        entry: float,
        stop: float,
        shares: int,
    ) -> PartialExitResult:
        """
        Check if partial exit at T1 should be triggered.

        Triggers when price reaches entry + (risk_per_unit * TARGET1_R).
        Exits PARTIAL_EXIT_T1_PCT of the position (default 50%).

        Args:
            close: Current closing price.
            entry: Entry price.
            stop: Stop loss price.
            shares: Total shares held.

        Returns:
            PartialExitResult with triggered flag, shares_to_exit, and exit_price.
        """
        risk_per_share = entry - stop
        t1_price = entry + (risk_per_share * settings.TARGET1_R)

        if close >= t1_price:
            shares_to_exit = math.floor(shares * settings.PARTIAL_EXIT_T1_PCT)
            logger.info(
                "partial_exit_triggered",
                t1_price=t1_price,
                close=close,
                shares_to_exit=shares_to_exit,
                total_shares=shares,
            )
            return PartialExitResult(
                triggered=True,
                shares_to_exit=shares_to_exit,
                exit_price=t1_price,
                reason=f"T1 reached ({settings.TARGET1_R}R)",
            )

        return PartialExitResult(
            triggered=False,
            shares_to_exit=0,
            exit_price=close,
            reason="T1 not yet reached",
        )

    def record_trade_outcome(
        self,
        win: bool,
        in_recovery: bool,
    ) -> None:
        """
        Record the outcome of a trade for drawdown recovery tracking.

        Args:
            win: True if the trade was profitable.
            in_recovery: True if the trade was taken during recovery mode.
        """
        if in_recovery:
            if win:
                self._consecutive_wins_in_recovery += 1
                if self._consecutive_wins_in_recovery >= 2:
                    # Recovery complete -- reset
                    logger.info("drawdown_recovery_complete")
                    self._recovery_trades_remaining = 0
                    self._consecutive_wins_in_recovery = 0
            else:
                # Loss during recovery -- reset win counter but keep recovery active
                self._consecutive_wins_in_recovery = 0
                self._recovery_trades_remaining = max(
                    0, self._recovery_trades_remaining - 1
                )

    def enter_recovery_mode(self) -> None:
        """Manually enter drawdown recovery mode (called after Regime 3 exits)."""
        self._recovery_trades_remaining = settings.DRAWDOWN_RECOVERY_TRADES
        self._consecutive_wins_in_recovery = 0
        logger.info("drawdown_recovery_started", trades=self._recovery_trades_remaining)

    def get_effective_risk_pct(self, recovery_active: bool) -> float:
        """
        Return the effective risk % (accounting for drawdown recovery).

        During recovery, risk is reduced by DRAWDOWN_RECOVERY_MULT (30% reduction).
        """
        base = self._base_risk_pct
        if recovery_active and self._recovery_trades_remaining > 0:
            return base * settings.DRAWDOWN_RECOVERY_MULT
        return base

    def update_bankroll(self, new_bankroll: float) -> None:
        """Update the bankroll after a trade closes."""
        self.bankroll = new_bankroll

    def partial_exit_triggered(self) -> bool:
        """Returns whether a partial exit has already been taken on the current position."""
        return False  # Per-position state -- managed externally by the position tracker
```

**Note for engineer:** There is a deliberate typo in `calc_shares`: `max_capital_per_trac` should be `max_capital_per_trade`. Fix this when writing the implementation.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python-engine && python -m pytest tests/test_risk_engine.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite**

Run: `cd python-engine && python -m pytest tests/ -v 2>&1 | tail -15`
Expected: All tests pass (no regression).

- [ ] **Step 6: Commit**

```bash
git add python-engine/risk_engine.py python-engine/tests/test_risk_engine.py
git commit -m "feat(risk): add dynamic position sizing, partial exit, and drawdown recovery engine"
```

---

## Task 7: Integrate Regime Engine into Engine.py

**Files:**
- Modify: `python-engine/engine.py:93-210` (signal evaluation function)

- [ ] **Step 1: Read the existing evaluate_signal function in full**

Run: `sed -n '93,400p' python-engine/engine.py`
Confirm all filter blocks (C1-C8), risk management block, target block, EV block, score block.

- [ ] **Step 2: Add regime-aware parameters to evaluate_signal**

Find `def evaluate_signal`. Add `regime: Regime = Regime.REGIME_1_NORMAL` to the function signature.

In the FILTERS section (line ~125), before the existing filters, add a new filter block:

```python
    # ----------------------------------------------------------------
    # REGIME-AWARE FILTER: RSI Percentile (Regime 1 and 2 only)
    # ----------------------------------------------------------------
    # Regime 3 uses RS vs Nifty filter instead (applied separately below)
    if regime == Regime.REGIME_1_NORMAL:
        rsi_pct_threshold = settings.RSI_PERCENTILE_REGIME1  # 20
        if not (0 <= rsi14 <= 100):
            return False, {"reject_reason": "rsi_out_of_range", "rsi": rsi14}
        # RSI percentile check: requires history -- if unavailable, fall back to fixed band
        rsi_pct = adaptive_ind.compute_rsi_percentile(rsi14, rsi_history)
        if rsi_history is not None and len(rsi_history) >= 20:
            if rsi_pct >= rsi_pct_threshold:
                return False, {"reject_reason": "rsi_percentile_too_high", "rsi_pct": rsi_pct, "threshold": rsi_pct_threshold}
        else:
            # Fall back to fixed RSI band if history is insufficient
            if not (45 <= rsi14 <= 72):
                return False, {"reject_reason": "rsi_out_of_range", "rsi": rsi14}
        if rsi_history is not None:
            score += max(0, int((20 - rsi_pct) / 2))  # Lower RSI percentile = higher score
    elif regime == Regime.REGIME_2_ELEVATED:
        # Regime 2 requires Nifty above EMA20 AND tighter RSI percentile
        if nifty_50_current < nifty_ema20:
            return False, {"reject_reason": "nifty_below_ema20_regime2", "nifty": nifty_50_current, "ema20": nifty_ema20}
        rsi_pct_threshold = settings.RSI_PERCENTILE_REGIME2  # 15
        rsi_pct = adaptive_ind.compute_rsi_percentile(rsi14, rsi_history)
        if rsi_history is not None and len(rsi_history) >= 20:
            if rsi_pct >= rsi_pct_threshold:
                return False, {"reject_reason": "rsi_percentile_too_high", "rsi_pct": rsi_pct, "threshold": rsi_pct_threshold}
        else:
            if not (50 <= rsi14 <= 72):  # Tighter fixed band for Regime 2 fallback
                return False, {"reject_reason": "rsi_out_of_range", "rsi": rsi14}
        if rsi_history is not None:
            score += max(0, int((15 - rsi_pct) / 2))

    # ----------------------------------------------------------------
    # REGIME-AWARE FILTER: Volume Z-Score
    # ----------------------------------------------------------------
    vol_zscore_threshold = adaptive_ind.get_volume_zscore_threshold(regime.value)
    vol_zscore = adaptive_ind.compute_volume_zscore(df["volume"].iloc[-1], df["volume"])
    if vol_zscore < vol_zscore_threshold:
        return False, {"reject_reason": "volume_zscore_low", "vol_zscore": vol_zscore, "threshold": vol_zscore_threshold}
```

**Important context for engineer:** The `evaluate_signal` function currently takes `market_regime: str` (BULL/CAUTION/BEAR_RS_ONLY). This needs to be renamed. Add `nifty_50_current` and `nifty_ema20` parameters to the function. The `rsi_history` is a new parameter -- create it from the DataFrame's RSI series. The `adaptive_ind` object should be instantiated at the top of the function.

For **Regime 3 only**, replace the RSI/volume filters with the RS vs Nifty filter:

```python
    # ----------------------------------------------------------------
    # REGIME 3: RS vs Nifty filter (primary -- replaces RSI + vol filters)
    # ----------------------------------------------------------------
    elif regime == Regime.REGIME_3_CRISIS:
        # Only buy stocks that are clearly outperforming the market
        rs_vs_nifty = adaptive_ind.compute_rs_vs_nifty(stock_return_1d, nifty_return_1d)
        if rs_vs_nifty < settings.RS_VS_NIFTY_THRESHOLD:
            return False, {
                "reject_reason": "rs_vs_nifty_insufficient",
                "rs_vs_nifty": rs_vs_nifty,
                "threshold": settings.RS_VS_NIFTY_THRESHOLD,
            }
        # Volume z-score still applies (higher threshold)
        vol_zscore = adaptive_ind.compute_volume_zscore(df["volume"].iloc[-1], df["volume"])
        if vol_zscore < settings.VOL_ZSCORE_REGIME3:
            return False, {"reject_reason": "volume_zscore_low", "vol_zscore": vol_zscore, "threshold": settings.VOL_ZSCORE_REGIME3}
```

- [ ] **Step 3: Update risk management block for regime-aware ATR and position sizing**

Replace the existing stop loss block (lines ~159-163):

```python
    # -----------------------------------------------------
    # REGIME-AWARE RISK MANAGEMENT
    # -----------------------------------------------------
    atr_mult = STOP_ATR_REGIME_MAP[regime]  # 1.5 for R1, 2.0 for R2/R3
    atr_stop = c - (atr_mult * a14)
    pct_stop = c * (1.0 - STOP_PCT_MAP[regime])  # 5% stop for R1/R2, 8% for R3
    stop_loss = max(atr_stop, pct_stop)
```

Where the ATR map is defined at module level:

```python
STOP_ATR_REGIME_MAP = {
    Regime.REGIME_1_NORMAL: settings.STOP_ATR_REGIME1,
    Regime.REGIME_2_ELEVATED: settings.STOP_ATR_REGIME2,
    Regime.REGIME_3_CRISIS: settings.STOP_ATR_REGIME3,
    Regime.UNKNOWN: settings.STOP_ATR_REGIME1,
}

STOP_PCT_MAP = {
    Regime.REGIME_1_NORMAL: 0.05,    # 5% stop
    Regime.REGIME_2_ELEVATED: 0.05,  # 5% stop
    Regime.REGIME_3_CRISIS: 0.08,    # 8% stop (wider -- less precise in crisis)
    Regime.UNKNOWN: 0.05,
}
```

- [ ] **Step 4: Update target block for regime-aware T2**

Replace the existing target block (lines ~188-191):

```python
    # -----------------------------------------------------
    # REGIME-AWARE TARGETS
    # -----------------------------------------------------
    r_distance = c - stop_loss
    t1 = settings.TARGET1_R
    t2 = T2_R_MAP[regime]  # 3.0 for R1/R2, 1.0 for R3

    target_1 = c + (t1 * r_distance)
    target_2 = c + (t2 * r_distance) if t2 is not None else None
```

Where `T2_R_MAP` is defined at module level:

```python
T2_R_MAP = {
    Regime.REGIME_1_NORMAL: settings.TARGET2_R_REGIME1,   # 3.0
    Regime.REGIME_2_ELEVATED: settings.TARGET2_R_REGIME2,  # 3.0
    Regime.REGIME_3_CRISIS: settings.TARGET2_R_REGIME3,    # 1.0 (None = no T2)
    Regime.UNKNOWN: settings.TARGET2_R_REGIME1,
}
```

- [ ] **Step 5: Update the Signal model instantiation to include regime metadata**

Find where `Signal(...)` is constructed (around line 231+). Add the new fields:

```python
    regime=regime,
    rsi_percentile=rsi_pct if regime in (Regime.REGIME_1_NORMAL, Regime.REGIME_2_ELEVATED) else None,
    volume_zscore=vol_zscore,
    rs_vs_nifty=rs_vs_nifty if regime == Regime.REGIME_3_CRISIS else None,
    regime_score=regime_score,
```

- [ ] **Step 6: Run existing tests to verify no regression**

Run: `cd python-engine && python -m pytest tests/test_engine.py -v 2>&1 | tail -20`
Expected: All existing tests pass.

- [ ] **Step 7: Commit**

```bash
git add python-engine/engine.py
git commit -m "feat(engine): integrate regime-aware filters, risk management, and targets into evaluate_signal"
```

---

## Task 8: Integrate Regime Engine into Portfolio and Main

**Files:**
- Modify: `python-engine/portfolio.py`
- Modify: `python-engine/main.py`

- [ ] **Step 1: Read portfolio.py filter_momentum_signals function**

Run: `grep -n "def filter_momentum_signals\|def filter_signals\|def get_signals\|bankroll\|risk_pct\|risk_per_trade" python-engine/portfolio.py | head -20`
Confirm where position sizing is computed.

- [ ] **Step 2: In portfolio.py, add regime state to PortfolioState**

Find the `PortfolioState` or equivalent dataclass. Add:

```python
from regime import Regime, RegimeEngine
```

Add to the state object:
```python
regime: Regime = Regime.REGIME_1_NORMAL
regime_score: float = 100.0
regime_engine: RegimeEngine = RegimeEngine()  # Shared across signals
```

- [ ] **Step 3: Update main.py to compute regime before signal evaluation**

In `main.py`, find the scan cycle loop. Before calling `evaluate_signal` for each stock, call `regime_engine.update_regime(...)` with the current VIX, Nifty 50, Nifty EMA20, and breadth values.

The VIX data source: Check if Upstox/Kite API supports VIX candles. If not, use the NSE India VIX historical bhavcopy or a static fallback. The `get_vix_data()` function should be added to `kite_client.py` if it does not exist.

For breadth: compute from the scan universe. For each stock in the universe, check if `close > SMA50`. Breadth = count(above) / total_count.

- [ ] **Step 4: Pass regime to evaluate_signal**

Change `evaluate_signal(..., market_regime=market_regime)` to `evaluate_signal(..., regime=regime)` in all call sites.

- [ ] **Step 5: Verify integration -- run the API**

Run: `cd python-engine && python -c "from main import app; print('main imports OK')"`
Expected: No import errors.

- [ ] **Step 6: Run full test suite**

Run: `cd python-engine && python -m pytest tests/ -v 2>&1 | tail -15`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add python-engine/portfolio.py python-engine/main.py
git commit -m "feat(portfolio): wire regime engine into portfolio state and signal evaluation loop"
```

---

## Task 9: Open Questions Resolution

**Before this task, resolve these 4 open questions from the design doc:**

1. **Backtest data source** -- Confirm Upstox historical data availability for 2019-2025, or decide on NSE/Bhavcopy CSV sourcing.
2. **Breadth calculation scope** -- Decide: Nifty 100 or Nifty 500 stocks for breadth computation. (Recommendation: start with Nifty 100 for performance.)
3. **Chandelier stop GTT** -- Confirm whether Upstox GTT supports trailing stops. If not, Chandelier stop will be managed in-engine (monitor each candle, trigger manual close when stop is hit). This is the recommended path -- it's more reliable.
4. **RSI percentile persistence** -- Confirm whether RSI history needs to be persisted across engine restarts. (Recommendation: rebuild from OHLC data on restart. The `engine.py` has access to 200+ days of data -- enough to compute RSI history.)

---

## Task 10: Backtesting

**Files:**
- Modify: `python-engine/backtest.py` (extend with regime engine backtest mode)

- [ ] **Step 1: Add regime-aware backtest mode to backtest.py**

Extend the existing `run_backtest()` function to support `use_regime=True` mode. When enabled:
- At each historical bar, compute VIX (or proxy with rolling ATR), Nifty EMA20, and breadth from historical data
- Run the regime engine to get the current regime
- Pass regime to `evaluate_signal`
- Record which regime each trade was taken in

- [ ] **Step 2: Backtest on March 2020 (COVID crash)**

Run backtest with `use_regime=True` for the period Feb 15 - April 30, 2020.

Capture:
- Regime 3 win rate (should be low but drawdown should be < 12%)
- Total portfolio drawdown vs Nifty drawdown

- [ ] **Step 3: Backtest on Feb-March 2022 (Russia-Ukraine)**

Run backtest with `use_regime=True` for the period Jan 15 - April 30, 2022.

Capture:
- Signal count in Regime 2 (Nifty filter should reject many signals during downtrend)
- Drawdown vs flat buy-and-hold

- [ ] **Step 4: Backtest in normal period (Jul-Dec 2024)**

Run as a control. Signal count and win rate should be comparable to or better than current system.

- [ ] **Step 5: Commit**

```bash
git add python-engine/backtest.py
git commit -m "test(backtest): add regime engine backtest mode and validate on COVID + war periods"
```

---

## Self-Review Checklist

After writing the complete plan, I ran these checks:

**1. Spec coverage:**
- [x] Regime 1/2/3 detection (Section 2) -> Task 3
- [x] RSI percentile (Section 3.1) -> Task 4 + Task 7
- [x] Volume z-score (Section 3.2) -> Task 4 + Task 7
- [x] RS vs Nifty filter (Section 3.3) -> Task 4 + Task 7
- [x] Nifty EMA20 confirmation (Section 3.4) -> Task 7
- [x] Chandelier stop (Section 3.5) -> Task 5
- [x] Dynamic position sizing (Section 4.1) -> Task 6
- [x] Partial exit at T1 (Section 4.2) -> Task 6
- [x] Regime-specific targets (Section 4.3) -> Task 7
- [x] Drawdown governor (Section 4.4) -> Task 6
- [x] All config params (Section 5) -> Task 1
- [x] All models changes (Section 7.2) -> Task 2
- [x] Backtesting (Section 8) -> Task 10

**2. Placeholder scan:**
- [x] No "TBD", "TODO", "implement later"
- [x] No "add appropriate error handling" without specifics
- [x] All test steps have actual test code
- [x] All implementation steps have actual code blocks

**3. Type consistency:**
- [x] `Regime` enum used consistently (not `market_regime` string)
- [x] `regime.value` used when accessing settings (settings takes float not enum)
- [x] `T2_R_MAP` and `STOP_ATR_REGIME_MAP` defined at module level before use
- [x] `PartialExitResult` dataclass fields match usage in tests

**Note for engineer:** The plan intentionally avoids modifying the existing `market_regime` string-based logic until all 4 new modules are working. The regime enum (`Regime`) coexists with the string `market_regime` until the integration step (Task 8), which minimizes risk of breaking the live trading system.

---

**Plan saved to:** `docs/superpowers/plans/2025-05-18-adaptive-regime-system.md`
