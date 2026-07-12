"""
[ROADMAP-3.2 2026-07-12] R3 (crisis) RSI-band contradiction.

The R3 branch of evaluate_signal says the RS-vs-Nifty filter "replaces
RSI + vol percentile filters", but an unconditional 45 <= RSI(14) <= 72
band further down applied to every regime -- silently rejecting exactly
the high-RSI relative-strength leaders R3 exists to buy. No R3
evaluation exists in the signal log yet (no crisis since logging began
2026-06-23), so this is the statically-caught sibling of the penny
dead-gate class: these tests are the witness that the band is now
regime-conditional.

The fixture df is engineered to pass every gate BEFORE the RSI band
(trend, EMA21 proximity, volume ratio) with RSI(14) far above 72, so
under the old code R3 deterministically died at "rsi_out_of_range" --
making the first test genuinely falsifiable.
"""
import numpy as np
import pandas as pd
import pytest

from engine import evaluate_signal
from models import Regime


@pytest.fixture
def crisis_rs_leader_df():
    """250 daily bars: steady uptrend, then 15 straight up-days (~1.2%/d)
    -> RSI(14) ~100, close above EMA200, within EMA21 proximity, with a
    final-volume spike (vol z-score >> 2.5, vol_ratio >> 1.2)."""
    n = 250
    closes = [400.0]
    for i in range(1, n):
        step = 0.012 if i >= n - 15 else 0.0015
        closes.append(closes[-1] * (1 + step))
    closes = np.array(closes)
    volumes = np.array([200_000 + (i % 2) * 40_000 for i in range(n)], dtype=float)
    volumes[-1] = 900_000.0
    return pd.DataFrame({
        "open": np.roll(closes, 1),
        "high": closes * 1.01,
        "low": closes * 0.99,
        "close": closes,
        "volume": volumes,
    })


def test_r3_no_longer_rejects_high_rsi_rs_leader(crisis_rs_leader_df):
    """Stock +1.2% on a Nifty -5% day = RS +6.2% >= 5% threshold: the R3
    candidate must NOT die at the RSI band (RSI(14) here is ~100)."""
    ok, res = evaluate_signal(
        "RSLEADER", crisis_rs_leader_df, bankroll=100_000, risk_pct=0.02,
        regime=Regime.REGIME_3_CRISIS,
        nifty_return_1d=-0.05,
    )
    assert res.get("reject_reason") != "rsi_out_of_range", (
        f"R3 still applies the RSI band the RS filter replaces: {res}"
    )


def test_r3_rs_filter_still_guards(crisis_rs_leader_df):
    """The band removal must not weaken R3's own primary gate: the same
    stock on a flat Nifty day (RS ~1.2% < 5%) is rejected for RS."""
    ok, res = evaluate_signal(
        "RSLEADER", crisis_rs_leader_df, bankroll=100_000, risk_pct=0.02,
        regime=Regime.REGIME_3_CRISIS,
        nifty_return_1d=0.0,
    )
    assert ok is False
    assert res["reject_reason"] == "rs_vs_nifty_insufficient"


def test_r1_still_rejects_out_of_band_rsi(crisis_rs_leader_df):
    """The band stays in force outside R3: the identical df in R1 dies
    at rsi_out_of_range (also proves the fixture's RSI really is > 72,
    which is what makes the R3 test falsifiable)."""
    ok, res = evaluate_signal(
        "RSLEADER", crisis_rs_leader_df, bankroll=100_000, risk_pct=0.02,
        regime=Regime.REGIME_1_NORMAL,
    )
    assert ok is False
    assert res["reject_reason"] == "rsi_out_of_range"
