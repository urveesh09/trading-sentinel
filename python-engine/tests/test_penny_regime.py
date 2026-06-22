"""
[PENNY-REGIME 2026-06-21] Tests for PennyRegimeEngine.

The engine produces a per-day (and per-refresh) PennyRegime from:
  - per-stock realized volatility (5-min, last 60 days)
  - India VIX proxy (Nifty 50 close vs EMA50 ratio)
  - breadth fallback (placeholder 0.5, matches Nifty engine)

Per spec §6.3:
  PR1_CALM     if vol_rank < 0.7 AND vix_proxy < 0.7
  PR2_ELEVATED if either is in [0.7, 0.9)
  PR3_HOT      if either is >= 0.9

Independent of Nifty regime (separate module, separate state).
"""
import math
import pytest
from unittest.mock import MagicMock, AsyncMock


# ---- helpers -----------------------------------------------------------

def _returns(n, base=100.0, vol=0.01, seed=42):
    """Deterministic synthetic return series (no numpy)."""
    import random
    random.seed(seed)
    out = [base]
    for _ in range(n - 1):
        out.append(out[-1] * (1 + random.gauss(0, vol)))
    return out


# ---- tests -------------------------------------------------------------

def test_volatility_rank_constant_series_is_half():
    """All-constant returns -> realized vol ~0 -> rank = 0.5 (degenerate)."""
    from penny_regime import PennyRegimeEngine
    eng = PennyRegimeEngine()
    rank = eng.compute_vol_rank([100.0] * 200)
    assert 0.0 <= rank <= 1.0
    assert abs(rank - 0.5) < 1e-6


def test_volatility_rank_increases_with_vol():
    from penny_regime import PennyRegimeEngine
    eng = PennyRegimeEngine()
    low = eng.compute_vol_rank(_returns(200, vol=0.005))
    high = eng.compute_vol_rank(_returns(200, vol=0.05))
    assert high > low


def test_volatility_rank_short_series_returns_half():
    """Need >= 30 bars for a meaningful estimate; below that, return 0.5."""
    from penny_regime import PennyRegimeEngine
    eng = PennyRegimeEngine()
    assert eng.compute_vol_rank([100.0] * 10) == 0.5


def test_vix_proxy_low_when_close_above_ema():
    from penny_regime import PennyRegimeEngine
    eng = PennyRegimeEngine()
    # Close well above EMA -> ratio < 1 -> proxy < 0.5
    closes = [100.0] * 50 + [110.0] * 50   # EMA converges near 105
    proxy = eng.compute_vix_proxy(closes, ema_period=50)
    assert 0.0 <= proxy <= 1.0
    assert proxy < 0.5


def test_vix_proxy_high_when_close_below_ema():
    from penny_regime import PennyRegimeEngine
    eng = PennyRegimeEngine()
    # NOTE: plan used [110]*50 + [100]*50, but Wilder EMA(50) seeded with
    # SMA(110) decays to ~101.35 after 50 values of 100 -> dist=-1.3% ->
    # proxy=0.42, which is < 0.5. The plan's intended invariant is "close
    # below EMA -> proxy elevated above neutral". We bump the seed to 120
    # so the EMA after 50 decay steps lands at ~102.70, giving dist=-2.6%
    # and proxy=0.51 (just above 0.5). This matches the spec's "[-10%,+5%]
    # -> [1,0]" mapping and the plan's body code (unchanged).
    # See docs/deviations/2026-06-21-penny-regime-vix-fixture-deviation.md
    closes = [120.0] * 50 + [100.0] * 50
    proxy = eng.compute_vix_proxy(closes, ema_period=50)
    assert 0.0 <= proxy <= 1.0
    assert proxy > 0.5


def test_vix_proxy_short_series_returns_half():
    from penny_regime import PennyRegimeEngine
    eng = PennyRegimeEngine()
    assert eng.compute_vix_proxy([100.0] * 20, ema_period=50) == 0.5


def test_classify_pr1_calm():
    from penny_regime import PennyRegimeEngine, PennyRegime
    eng = PennyRegimeEngine()
    assert eng.classify(vol_rank=0.3, vix_proxy=0.4) == PennyRegime.PR1_CALM


def test_classify_pr2_elevated_by_vol():
    from penny_regime import PennyRegimeEngine, PennyRegime
    eng = PennyRegimeEngine()
    assert eng.classify(vol_rank=0.8, vix_proxy=0.3) == PennyRegime.PR2_ELEVATED


def test_classify_pr2_elevated_by_vix():
    from penny_regime import PennyRegimeEngine, PennyRegime
    eng = PennyRegimeEngine()
    assert eng.classify(vol_rank=0.3, vix_proxy=0.75) == PennyRegime.PR2_ELEVATED


def test_classify_pr3_hot_by_vol():
    from penny_regime import PennyRegimeEngine, PennyRegime
    eng = PennyRegimeEngine()
    assert eng.classify(vol_rank=0.95, vix_proxy=0.3) == PennyRegime.PR3_HOT


def test_classify_pr3_hot_by_vix():
    from penny_regime import PennyRegimeEngine, PennyRegime
    eng = PennyRegimeEngine()
    assert eng.classify(vol_rank=0.3, vix_proxy=0.92) == PennyRegime.PR3_HOT


def test_classify_unknown_when_inputs_missing():
    from penny_regime import PennyRegimeEngine, PennyRegime
    eng = PennyRegimeEngine()
    assert eng.classify(vol_rank=None, vix_proxy=None) == PennyRegime.UNKNOWN
    assert eng.classify(vol_rank=None, vix_proxy=0.5) == PennyRegime.UNKNOWN
    assert eng.classify(vol_rank=0.5, vix_proxy=None) == PennyRegime.UNKNOWN


def test_size_for_pr1_uses_full_pct():
    from penny_regime import PennyRegimeEngine
    from penny_models import PennyRegime
    eng = PennyRegimeEngine()
    assert eng.size_pct(PennyRegime.PR1_CALM) == 0.05


def test_size_for_pr2_uses_half_pct():
    from penny_regime import PennyRegimeEngine
    from penny_models import PennyRegime
    eng = PennyRegimeEngine()
    assert eng.size_pct(PennyRegime.PR2_ELEVATED) == 0.025


def test_size_for_pr3_is_zero():
    from penny_regime import PennyRegimeEngine
    from penny_models import PennyRegime
    eng = PennyRegimeEngine()
    assert eng.size_pct(PennyRegime.PR3_HOT) == 0.0


def test_compute_today_async_uses_injected_kite():
    from penny_regime import PennyRegimeEngine, PennyRegime
    import asyncio

    eng = PennyRegimeEngine()

    fake_kite = MagicMock()
    # 60-day Nifty 50 daily closes, slowly rising
    closes = [100 + i * 0.1 for i in range(60)]
    fake_kite.get_historical = AsyncMock(return_value=[
        {"date": "2026-04-01", "close": c} for c in closes
    ])

    regime = asyncio.run(eng.compute_today(kite=fake_kite))
    assert regime in (PennyRegime.PR1_CALM, PennyRegime.PR2_ELEVATED, PennyRegime.PR3_HOT, PennyRegime.UNKNOWN)


def test_compute_today_handles_kite_failure():
    from penny_regime import PennyRegimeEngine, PennyRegime
    import asyncio

    eng = PennyRegimeEngine()
    fake_kite = MagicMock()
    fake_kite.get_historical = AsyncMock(side_effect=Exception("network"))

    regime = asyncio.run(eng.compute_today(kite=fake_kite))
    assert regime == PennyRegime.UNKNOWN
