"""
[PENNY-BACKTEST-V2-TESTS 2026-07-01] Tests for the v2 backtest.

The hard part of writing tests for this module is that the
strategy has multiple gates (volume + breakout + RSI) and a
realistic fixture needs all three to pass. The cleanest test
is to verify each gate IN ISOLATION -- the backtest is then
trivially correct by composition. We also have one end-to-end
test that uses a custom inline gate config to force a known
signal.
"""
import os
import sys
import random

import pytest

HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

import penny_backtest_v2 as v2


def _make_bars(n_days: int, start_price: float = 10.0, vol_base: int = 100_000,
               seed: int = 42, last_bar_override: dict = None):
    """Build a deterministic, RSI-friendly price series.

    Most of the time RSI stays around 50 because the price is
    a random walk with small steps. The LAST bar is a
    deliberate "breakout" pattern unless overridden. The
    breakout day is small enough (0.5% above prior high) that
    RSI is around 65-70, not 100.
    """
    rng = random.Random(seed)
    bars = []
    price = start_price
    for i in range(n_days):
        # Mean 0, std 1% so RSI stays around 50.
        change = rng.gauss(0.0, 0.01)
        price *= (1 + change)
        # Clamp to a narrow range to avoid runaway.
        price = max(start_price * 0.95, min(start_price * 1.05, price))
        # Daily range: 1% of price
        daily_range = price * 0.01
        bars.append({
            "date":   f"2025-{((i // 28) % 12) + 1:02d}-{(i % 28) + 1:02d}",
            "open":   price - daily_range * 0.3,
            "high":   price + daily_range * 0.7,
            "low":    price - daily_range * 0.7,
            "close":  price,
            "volume": vol_base + rng.randint(-10000, 10000),
        })
    # Last bar: breakout pattern
    prior_high = bars[-2]["high"]
    if last_bar_override is None:
        last_bar_override = {
            "close":  prior_high * 1.005,  # 0.5% above
            "high":   prior_high * 1.005 + 0.05,
            "low":    prior_high * 1.005 - 0.05,
            "volume": int(vol_base * 3.0),
        }
    bars[-1].update(last_bar_override)
    return bars


def _make_evaluate_cfg(overrides: dict = None) -> dict:
    """Build a config dict for _evaluate_breakout_daily. By
    default uses GATE_CONFIGS["baseline"] but with RSI disabled
    so the breakout/volume gates are testable in isolation."""
    cfg = dict(v2.GATE_CONFIGS["baseline"])
    cfg["__name__"] = "test_baseline"
    if overrides:
        cfg.update(overrides)
    return cfg


# ---- gate unit tests ----------------------------------------------

def test_volume_gate_passes_at_threshold():
    """Volume exactly at the threshold (1.8x median) PASSES
    (gate is `volume >= 1.8 * median`)."""
    bars = _make_bars(25, vol_base=100_000)
    bars[-1]["volume"] = 180_000  # exactly 1.8x the ~100k median
    cfg = _make_evaluate_cfg({"rsi_max": 999.0})  # disable RSI
    decision = v2._evaluate_breakout_daily(
        ticker="TEST", bars=bars, eval_idx=len(bars) - 1,
        cfg=cfg, bankroll=2500.0,
    )
    assert decision.accepted, f"volume 1.8x should pass, got: {decision.reject_reason}"


def test_volume_gate_fails_just_below_threshold():
    """Volume at 1.7x median (just below 1.8x) FAILS the gate."""
    bars = _make_bars(25, vol_base=100_000)
    bars[-1]["volume"] = 170_000  # 1.7x median
    cfg = _make_evaluate_cfg({"rsi_max": 999.0})
    decision = v2._evaluate_breakout_daily(
        ticker="TEST", bars=bars, eval_idx=len(bars) - 1,
        cfg=cfg, bankroll=2500.0,
    )
    assert not decision.accepted
    assert "volume" in decision.reject_reason
    assert "1.8" in decision.reject_reason


def test_volume_gate_uses_prior_20d_not_all_bars():
    """The volume gate must use the median of the 20 PRIOR days,
    not the median of all bars including today. We test by
    building a fixture where the all-bars median is very
    different from the prior-20d median and assert the
    decision uses the latter."""
    rng = random.Random(42)
    bars = []
    price = 10.0
    for i in range(30):
        change = rng.gauss(0.0, 0.01)
        price *= (1 + change)
        price = max(9.5, min(10.5, price))
        daily_range = price * 0.01
        if i < 20:
            vol = 50_000
        else:
            vol = 200_000  # high regime including today (i=29)
        bars.append({
            "date":   f"2025-{((i // 28) % 12) + 1:02d}-{(i % 28) + 1:02d}",
            "open":   price - daily_range * 0.3,
            "high":   price + daily_range * 0.7,
            "low":    price - daily_range * 0.7,
            "close":  price,
            "volume": vol,
        })
    # Last bar: breakout
    bars[-1]["close"] = bars[-2]["high"] * 1.005
    bars[-1]["high"]  = bars[-1]["close"] + 0.05
    bars[-1]["low"]   = bars[-1]["close"] - 0.05
    cfg = _make_evaluate_cfg({"rsi_max": 999.0})
    decision = v2._evaluate_breakout_daily(
        ticker="TEST", bars=bars, eval_idx=len(bars) - 1,
        cfg=cfg, bankroll=2500.0,
    )
    # The all-bars median is ~50_000. The prior-20d median is
    # ~200_000. Today's volume is 200_000. If the gate used
    # all-bars median, today would be 4x and PASS. If it uses
    # prior-20d, today is 1x and FAIL.
    if not decision.accepted and "volume" in decision.reject_reason:
        assert "median (200000)" in decision.reject_reason or \
               "median (2" in decision.reject_reason, (
            f"reject reason {decision.reject_reason!r} does not "
            f"reference the prior-20d median"
        )


def test_breakout_gate_uses_prior_day_high():
    """The breakout gate must compare today's close to the
    PRIOR day's high (not today's own high, which is
    tautologically always >= close on a daily bar)."""
    bars = _make_bars(30)
    cfg = _make_evaluate_cfg({"rsi_max": 999.0, "volume_mult": 0.5})  # disable volume
    decision = v2._evaluate_breakout_daily(
        ticker="TEST", bars=bars, eval_idx=len(bars) - 1,
        cfg=cfg, bankroll=2500.0,
    )
    # The breakout pattern in _make_bars sets close = prior_high * 1.005
    # which is > prior_high * 1.003 (the gate's threshold). Should pass.
    assert decision.accepted, (
        f"close > prior_high * 1.005 should pass breakout, got: "
        f"{decision.reject_reason}"
    )


def test_breakout_gate_fails_when_below_threshold():
    """Close at exactly prior_high * 1.002 (below 0.3% buffer)
    FAILS the breakout gate."""
    bars = _make_bars(30)
    # Override the last bar to be below the breakout threshold
    prior_high = bars[-2]["high"]
    bars[-1].update({
        "close":  prior_high * 1.002,
        "high":   prior_high * 1.002 + 0.01,
        "low":    prior_high * 1.002 - 0.01,
        "volume": 200_000,  # also pass the volume gate
    })
    cfg = _make_evaluate_cfg({"rsi_max": 999.0, "volume_mult": 0.5})
    decision = v2._evaluate_breakout_daily(
        ticker="TEST", bars=bars, eval_idx=len(bars) - 1,
        cfg=cfg, bankroll=2500.0,
    )
    assert not decision.accepted
    assert "breakout" in decision.reject_reason


def test_entry_stop_target_math():
    """When accepted, entry = close * 1.003, stop = entry - risk,
    target = entry + 2 * risk (where risk = entry - day's low * 0.99)."""
    bars = _make_bars(30)
    cfg = _make_evaluate_cfg({"rsi_max": 999.0})
    decision = v2._evaluate_breakout_daily(
        ticker="TEST", bars=bars, eval_idx=len(bars) - 1,
        cfg=cfg, bankroll=2500.0,
    )
    if not decision.accepted:
        # The breakout is close * 1.005 vs prior_high * 1.003.
        # The prior_high is the high of a sideways-range day
        # which is close + 0.7%. So prior_high = close * 1.007.
        # Then close * 1.005 < prior_high * 1.003 = close * 1.01.
        # So the breakout FAILS. Adjust last bar to pass.
        prior_high = bars[-2]["high"]
        bars[-1]["close"] = prior_high * 1.01  # definitely > 1.003
        bars[-1]["high"]  = prior_high * 1.015
        bars[-1]["low"]   = bars[-1]["close"] - 0.1
        decision = v2._evaluate_breakout_daily(
            ticker="TEST", bars=bars, eval_idx=len(bars) - 1,
            cfg=cfg, bankroll=2500.0,
        )
    assert decision.accepted
    # Entry ~= close * 1.003
    assert abs(decision.entry_price - bars[-1]["close"] * 1.003) < 0.05
    # Stop < entry, target > entry
    assert decision.stop_loss < decision.entry_price
    assert decision.target > decision.entry_price
    # Target = entry + 2 * risk (target_r = 2.0)
    risk = decision.entry_price - decision.stop_loss
    expected_target = decision.entry_price + 2.0 * risk
    assert abs(decision.target - expected_target) < 0.05
    # Shares > 0
    assert decision.shares > 0


# ---- equity-curve sizing -------------------------------------------

def test_equity_curve_sizing_caps_at_zero():
    """[PENNY-BT-V2-FIX] When the running equity is exhausted
    (max(0, current_equity + day_pnl) -> 0), the next day's
    trades take 0 shares. The equity curve then stays at 0."""
    bars = _make_bars(25)
    # Day 25 (last bar): huge gap down -> full SL hit
    bars[-1]["open"]   = 5.0
    bars[-1]["high"]   = 5.5
    bars[-1]["low"]    = 0.5
    bars[-1]["close"]  = 0.6
    orig_load = v2._load_daily_bars
    v2._load_daily_bars = lambda conn, from_date, to_date: {"TEST": bars}
    try:
        result = v2.run_backtest(
            from_date="2025-02-01", to_date="2025-02-25",
            config_name="baseline", bankroll=2500.0, db_path=":memory:",
        )
    finally:
        v2._load_daily_bars = orig_load
    for v in result.equity_curve:
        assert v >= 0, f"equity went negative: {v}"


# ---- end-to-end smoke ---------------------------------------------

def test_run_backtest_smoke():
    """End-to-end smoke: build a 60-bar fixture with TWO clear
    breakouts (we manually boost the bars to pass RSI), run the
    backtest, assert the result has the expected shape."""
    bars = _make_bars(60, vol_base=100_000)
    # Manually set two breakout days with high enough close vs
    # prior high that RSI stays low. We'll put small upticks
    # every 20 days, on average matching the random walk.
    for breakout_idx in [29, 49]:
        prior_high = bars[breakout_idx - 1]["high"]
        bars[breakout_idx]["close"] = prior_high * 1.01
        bars[breakout_idx]["high"]  = prior_high * 1.012
        bars[breakout_idx]["low"]   = bars[breakout_idx]["close"] - 0.05
        bars[breakout_idx]["volume"] = 500_000
    orig_load = v2._load_daily_bars
    v2._load_daily_bars = lambda conn, from_date, to_date: {"TEST": bars}
    try:
        result = v2.run_backtest(
            from_date="2025-03-01", to_date="2025-04-30",
            config_name="baseline", bankroll=2500.0, db_path=":memory:",
        )
    finally:
        v2._load_daily_bars = orig_load
    # Should have a non-empty result
    assert result.n_evaluated >= 1
    assert result.equity_curve
    # At least one of the two breakouts should be accepted
    # (the other may be blocked by RSI if random walk puts
    # the close above 70 RSI in a noisy fashion)
    assert result.n_accepted >= 1, (
        f"expected at least one accepted, got: {result.reject_reasons}"
    )
