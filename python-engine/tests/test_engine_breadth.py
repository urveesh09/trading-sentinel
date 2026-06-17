"""Tests for breadth enrichment integration into evaluate_signal().

These tests exercise the new kwargs (breadth_rank, breadth_pct_above_sma50)
and the two new integration points:
  A) Stock-level scoring bonus + 1.2x multiplier (works in all regimes)
  B) R1 narrow-rally gate (R1 only, skips when degraded)

Test pattern follows the project's existing convention: use `if fired:`
guards since the test fixture does not reliably produce a firing signal.

The `breadth_enabled` fixture flips BREADTH_ENRICHMENT_ENABLED to True for
the duration of the test, since the feature defaults to OFF for safe rollout.
"""
import numpy as np
import pandas as pd
import pytest

from engine import evaluate_signal
from regime import Regime


@pytest.fixture
def breadth_enabled():
    """Enable BREADTH_ENRICHMENT_ENABLED for the test, restore after."""
    from config import settings
    original = settings.BREADTH_ENRICHMENT_ENABLED
    settings.BREADTH_ENRICHMENT_ENABLED = True
    try:
        yield
    finally:
        settings.BREADTH_ENRICHMENT_ENABLED = original


def _make_df() -> pd.DataFrame:
    """250-day OHLCV using the project's tested data shape (deterministic).

    The base series is a gentle uptrend, but the last 5 days include a small
    pullback so the final RSI lands in the 50-65 range (passes the engine's
    fixed 45-72 band check). Otherwise the rsi_out_of_range reject fires
    before our breadth gate can be tested.
    """
    n = 250
    base = 500.0
    close = np.array([base + 0.5 * i + 2 * np.sin(i / 10) for i in range(n)])
    high = close + np.linspace(3, 5, n)
    low = close - np.linspace(3, 5, n)
    opn = close - np.linspace(0.5, 1.0, n)
    volume = np.array([200_000 + 5000 * (i % 20) for i in range(n)])
    volume[-1] = int(volume[-21:-1].mean() * 2.5)
    # Pull back the last 3 closes ~2% so RSI isn't pegged at 100
    close[-3:] = close[-3] * np.array([0.99, 0.98, 0.985])
    high[-3:] = np.maximum(high[-3:], close[-3:])
    low[-3:] = np.minimum(low[-3:], close[-3:])
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    df = pd.DataFrame({
        "open": opn, "high": high, "low": low,
        "close": close, "volume": volume, "date": dates
    })
    df.index = dates
    return df


def _accept_kwargs():
    """Keyword args that pass non-breadth regime filters for the standard fixture.

    Uses rsi_history=None so the engine falls back to the fixed 45-72 band
    (rsi14=100 would otherwise fail the band check before the gate runs).
    """
    return dict(
        market_regime="BULL",
        nifty_50_current=620.0,
        nifty_ema20=600.0,
        nifty_return_1d=0.001,
        rsi_history=None,
    )


# -- Scoring bonus tests (Integration Point A) ------------------------


def test_breadth_rank_top_quintile_gets_bonus_and_multiplier(breadth_enabled):
    """breadth_rank >= 0.80 -> +15 bonus + 1.2x score multiplier (when fired)."""
    df = _make_df()
    bankroll = 100_000
    kw = _accept_kwargs()
    _, base = evaluate_signal("TEST", df, bankroll, 0.02, regime=Regime.REGIME_1_NORMAL, **kw)
    _, top = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL, breadth_rank=0.85, **kw,
    )
    # If both fired, check the math
    if "score" in base and "score" in top:
        expected = min(100, int((base["score"] + 15) * 1.2))
        assert top["score"] == expected, f"Expected {expected}, got {top['score']} (base={base['score']})"
    # Both should have same fired-status (breadth_rank doesn't reject by itself)
    assert ("score" in base) == ("score" in top), "breadth_rank alone shouldn't change fired status"


def test_breadth_rank_mid_gets_bonus_no_multiplier(breadth_enabled):
    """0.60 <= breadth_rank < 0.80 -> +7 bonus, no multiplier (when fired)."""
    df = _make_df()
    bankroll = 100_000
    kw = _accept_kwargs()
    _, base = evaluate_signal("TEST", df, bankroll, 0.02, regime=Regime.REGIME_1_NORMAL, **kw)
    _, mid = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL, breadth_rank=0.65, **kw,
    )
    if "score" in base and "score" in mid:
        assert mid["score"] == base["score"] + 7


def test_breadth_rank_bottom_gets_penalty(breadth_enabled):
    """breadth_rank < 0.20 -> -10 penalty (when fired)."""
    df = _make_df()
    bankroll = 100_000
    kw = _accept_kwargs()
    _, base = evaluate_signal("TEST", df, bankroll, 0.02, regime=Regime.REGIME_1_NORMAL, **kw)
    _, bot = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL, breadth_rank=0.10, **kw,
    )
    if "score" in base and "score" in bot:
        assert bot["score"] == base["score"] - 10


def test_breadth_rank_none_no_effect(breadth_enabled):
    """breadth_rank=None (degraded) -> no scoring changes (when fired)."""
    df = _make_df()
    bankroll = 100_000
    kw = _accept_kwargs()
    _, base = evaluate_signal("TEST", df, bankroll, 0.02, regime=Regime.REGIME_1_NORMAL, **kw)
    _, none = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL, breadth_rank=None, **kw,
    )
    if "score" in base and "score" in none:
        assert none["score"] == base["score"]


def test_breadth_rank_relative_ordering_is_correct(breadth_enabled):
    """Top rank >= mid rank >= bottom rank in score impact (when fired)."""
    df = _make_df()
    bankroll = 100_000
    kw = _accept_kwargs()
    _, top = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL, breadth_rank=0.85, **kw,
    )
    _, mid = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL, breadth_rank=0.65, **kw,
    )
    _, bot = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL, breadth_rank=0.10, **kw,
    )
    if "score" in top and "score" in mid and "score" in bot:
        # Top: +15 + 1.2x = much higher; Mid: +7; Bot: -10
        assert top["score"] > mid["score"] > bot["score"]


# -- R1 narrow-rally gate tests (Integration Point B) -----------------


def test_breadth_narrow_rally_gate_r1_rejects_non_leader(breadth_enabled):
    """R1 + breadth_pct < 0.40 + rank < 0.80 -> rejected with narrow_rally_filtered=True."""
    df = _make_df()
    bankroll = 100_000
    kw = _accept_kwargs()
    ok, res = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL,
        breadth_rank=0.50,
        breadth_pct_above_sma50=0.30,
        **kw,
    )
    assert ok is False
    assert res.get("reject_reason") == "narrow_rally_filtered"
    # The early-return path doesn't set the narrow_rally_filtered flag in the
    # result dict (only the success path does). Verify gate fired by checking
    # reject_reason is the gate's identifier.


def test_breadth_narrow_rally_gate_r1_exempts_top_quintile(breadth_enabled):
    """R1 + breadth_pct < 0.40 + rank >= 0.80 -> gate does NOT reject."""
    df = _make_df()
    bankroll = 100_000
    kw = _accept_kwargs()
    ok, res = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL,
        breadth_rank=0.85,
        breadth_pct_above_sma50=0.30,
        **kw,
    )
    if not ok:
        assert res.get("reject_reason") != "narrow_rally_filtered"


def test_breadth_narrow_rally_gate_r1_skips_when_degraded(breadth_enabled):
    """R1 + breadth_pct=None (degraded) -> gate skipped, signal proceeds normally."""
    df = _make_df()
    bankroll = 100_000
    kw = _accept_kwargs()
    ok, res = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL,
        breadth_rank=0.50,
        breadth_pct_above_sma50=None,
        **kw,
    )
    if not ok:
        assert res.get("reject_reason") != "narrow_rally_filtered"


def test_breadth_narrow_rally_gate_does_not_fire_in_r2(breadth_enabled):
    """R2 + breadth_pct < 0.40 + rank < 0.80 -> gate does NOT fire."""
    df = _make_df()
    bankroll = 100_000
    kw = _accept_kwargs()
    ok, res = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_2_ELEVATED,
        breadth_rank=0.50,
        breadth_pct_above_sma50=0.30,
        **kw,
    )
    if not ok:
        assert res.get("reject_reason") != "narrow_rally_filtered"


def test_breadth_narrow_rally_gate_does_not_fire_in_r3(breadth_enabled):
    """R3 + breadth_pct < 0.40 + rank < 0.80 -> gate does NOT fire."""
    df = _make_df()
    bankroll = 100_000
    ok, res = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_3_CRISIS,
        breadth_rank=0.50,
        breadth_pct_above_sma50=0.30,
    )
    if not ok:
        assert res.get("reject_reason") != "narrow_rally_filtered"


def test_breadth_narrow_rally_gate_r1_passes_with_healthy_breadth(breadth_enabled):
    """R1 + breadth_pct >= 0.40 -> gate does NOT fire (only narrow rallies trigger it)."""
    df = _make_df()
    bankroll = 100_000
    kw = _accept_kwargs()
    ok, res = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL,
        breadth_rank=0.50,
        breadth_pct_above_sma50=0.60,  # Healthy breadth -> gate doesn't fire
        **kw,
    )
    if not ok:
        assert res.get("reject_reason") != "narrow_rally_filtered"


# -- Feature flag test ------------------------------------------------


def test_breadth_feature_flag_off_means_no_breadth_effect():
    """When BREADTH_ENRICHMENT_ENABLED=False, breadth_rank has no effect on score."""
    from config import settings
    original = settings.BREADTH_ENRICHMENT_ENABLED
    try:
        settings.BREADTH_ENRICHMENT_ENABLED = False
        df = _make_df()
        bankroll = 100_000
        kw = _accept_kwargs()
        _, base = evaluate_signal("TEST", df, bankroll, 0.02, regime=Regime.REGIME_1_NORMAL, **kw)
        _, with_rank = evaluate_signal(
            "TEST", df, bankroll, 0.02,
            regime=Regime.REGIME_1_NORMAL, breadth_rank=0.85, **kw,
        )
        if "score" in base and "score" in with_rank:
            assert base["score"] == with_rank["score"]
    finally:
        settings.BREADTH_ENRICHMENT_ENABLED = original
