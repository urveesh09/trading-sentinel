"""[WORKFLOW-G.3 2026-09-17] Tests for the range mean-reversion
entry verifier.

Per Workstream G in NEXT_AGENT_PLAN.md:
> Range mean reversion with strict invalidation. Stable
> range/no expansion. Comparison: No-trade baseline and
> existing range logic. Main risk: Regime shift produces
> tail losses.

These tests pin the verifier:

  - EntrySignal enum: ENTER / WAIT_*.
  - range_reversion_entry produces ENTER when the range
    is intact, not expanding, AND the entry bar touches
    the lower band.
  - WAIT_RANGE_NOT_INTACT: range too wide.
  - WAIT_RANGE_EXPANDING: recent half has wider range.
  - WAIT_NO_LOWER_TOUCH: entry bar doesn't reach the band.
  - WAIT_INSUFFICIENT_BARS: not enough bars.
  - Strict invalidation: stop just below the recent low.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))

from range_reversion import (  # noqa: E402  -- import path
    EntrySignal,
    RangeReversionVerdict,
    range_reversion_entry,
)


def _stable_bars(n: int = 14, *, base: float = 100.0,
                   amplitude: float = 0.3) -> list[dict]:
    """Build n stable bars around ``base``.

    Each bar has high = base + amplitude, low = base - amplitude,
    close = base (the amplitude is just the high-low band; the
    close is pinned at the mean for simplicity).
    """
    return [
        {"close": base, "high": base + amplitude,
         "low": base - amplitude}
        for _ in range(n)
    ]


# -- 1. EntrySignal enum -----------------------------------


def test_entry_signal_has_five_values():
    assert {s.value for s in EntrySignal} == {
        "ENTER",
        "WAIT_RANGE_NOT_INTACT",
        "WAIT_RANGE_EXPANDING",
        "WAIT_NO_LOWER_TOUCH",
        "WAIT_INSUFFICIENT_BARS",
    }


# -- 2. ENTER ---------------------------------------------


def test_enter_when_range_intact_and_lower_touched():
    """[WORKFLOW-G.3 2026-09-17] Stable range + lower-band
    touch = ENTER. The strict stop is just below the
    recent low."""
    bars = _stable_bars(14, base=100.0, amplitude=0.3)
    # Entry bar: low at the band (close to window_min).
    bars.append({"close": 99.8, "high": 100.2, "low": 99.5})
    v = range_reversion_entry(bars)
    assert v.signal == EntrySignal.ENTER
    assert v.mean_target is not None
    assert v.strict_stop is not None
    assert v.recent_low is not None
    # The strict stop must be BELOW the recent low.
    assert v.strict_stop < v.recent_low


def test_enter_uses_window_mean_as_target():
    """[WORKFLOW-G.3 2026-09-17] The mean target equals
    the mean of the analysis window's closes."""
    bars = _stable_bars(14, base=100.0, amplitude=0.3)
    bars.append({"close": 99.8, "high": 100.2, "low": 99.5})
    v = range_reversion_entry(bars)
    # Mean of 14 closes all = 100.0 -> 100.0.
    assert v.mean_target == pytest.approx(100.0)


def test_enter_strict_stop_epsilon_is_configurable():
    """[WORKFLOW-G.3 2026-09-17] Tighter epsilon = tighter
    stop. Operators can configure the per-trade loss
    tolerance via strict_stop_epsilon."""
    bars = _stable_bars(14, base=100.0, amplitude=0.3)
    bars.append({"close": 99.8, "high": 100.2, "low": 99.5})
    v1 = range_reversion_entry(bars, strict_stop_epsilon=0.001)
    v2 = range_reversion_entry(bars, strict_stop_epsilon=0.01)
    # v2's stop is further below the recent low.
    assert v2.strict_stop < v1.strict_stop


# -- 3. WAIT_RANGE_NOT_INTACT ---------------------------------


def test_wait_range_not_intact_when_range_too_wide():
    """[WORKFLOW-G.3 2026-09-17] When (max-min)/mean > max_range_pct,
    the range is NOT intact -- WAIT."""
    # Amplitude 5 (so range = 10) on mean 100 = range_pct = 0.1 > 0.06.
    bars = _stable_bars(14, base=100.0, amplitude=5.0)
    bars.append({"close": 99.8, "high": 100.2, "low": 99.5})
    v = range_reversion_entry(bars)
    assert v.signal == EntrySignal.WAIT_RANGE_NOT_INTACT
    assert v.range_pct is not None
    assert v.range_pct > 0.06
    assert v.mean_target is not None  # still surfaces mean.


def test_wait_range_not_intact_notes_record_threshold():
    bars = _stable_bars(14, base=100.0, amplitude=5.0)
    bars.append({"close": 99.8, "high": 100.2, "low": 99.5})
    v = range_reversion_entry(bars)
    assert any("max_range_pct" in n for n in v.notes)


def test_wait_range_not_intact_does_not_set_stop():
    """[WORKFLOW-G.3 2026-09-17] WAIT signals never set the
    strict_stop -- it's only meaningful on ENTER."""
    bars = _stable_bars(14, base=100.0, amplitude=5.0)
    bars.append({"close": 99.8, "high": 100.2, "low": 99.5})
    v = range_reversion_entry(bars)
    assert v.strict_stop is None
    assert v.recent_low is None


# -- 4. WAIT_RANGE_EXPANDING -------------------------------


def test_wait_range_expanding_when_recent_half_wider():
    """[WORKFLOW-G.3 2026-09-17] Recent half-window's range
    >> older half's range = the range is expanding (we're
    in a breakout, not a stable range) -- WAIT."""
    # Build older half: tight (amplitude 0.3).
    # Build recent half: wide (amplitude 3).
    bars = _stable_bars(7, base=100.0, amplitude=0.3)
    bars.extend(_stable_bars(7, base=100.0, amplitude=3.0))
    bars.append({"close": 99.8, "high": 100.2, "low": 99.5})
    v = range_reversion_entry(bars)
    assert v.signal == EntrySignal.WAIT_RANGE_EXPANDING
    assert v.expansion_ratio is not None
    assert v.expansion_ratio > 1.5


def test_wait_range_expanding_does_not_set_stop():
    bars = _stable_bars(7, base=100.0, amplitude=0.3)
    bars.extend(_stable_bars(7, base=100.0, amplitude=3.0))
    bars.append({"close": 99.8, "high": 100.2, "low": 99.5})
    v = range_reversion_entry(bars)
    assert v.strict_stop is None


def test_expansion_limit_is_configurable():
    """[WORKFLOW-G.3 2026-09-17] Operators can tighten
    expansion_limit for stricter audit."""
    bars = _stable_bars(7, base=100.0, amplitude=0.3)
    bars.extend(_stable_bars(7, base=100.0, amplitude=2.0))
    # Entry bar with low at the recent low (98.0).
    bars.append({"close": 98.0, "high": 99.0, "low": 98.0})
    # Default expansion_limit=1.5 -> WAIT.
    v = range_reversion_entry(bars)
    assert v.signal == EntrySignal.WAIT_RANGE_EXPANDING
    # expansion_limit=10.0 -> ENTER (if other checks pass).
    # expansion = 4.0 / 0.6 = 6.67 < 10.0 -> expansion OK.
    # range = (100+2.0) - (100-2.0) = 4.0; range_pct = 4/100 = 0.04 < 0.06.
    # entry_low = 98.0 == window_min -> touch OK (inclusive).
    v = range_reversion_entry(bars, expansion_limit=10.0)
    assert v.signal == EntrySignal.ENTER


# -- 5. WAIT_NO_LOWER_TOUCH --------------------------------


def test_wait_no_lower_touch_when_entry_above_band():
    """[WORKFLOW-G.3 2026-09-17] When the entry bar's low
    is above the touch threshold, the lower band is NOT
    touched -- WAIT."""
    bars = _stable_bars(14, base=100.0, amplitude=0.3)
    # Entry bar with low well above the touch threshold.
    # touch_threshold = window_min + mean * 0.005
    #             = 99.7 + 100.0 * 0.005 = 100.2.
    # Set entry_low = 100.5 > 100.2.
    bars.append({"close": 101.0, "high": 101.5, "low": 100.5})
    v = range_reversion_entry(bars)
    assert v.signal == EntrySignal.WAIT_NO_LOWER_TOUCH
    assert v.recent_low is not None  # still surfaces recent low.


def test_wait_no_lower_touch_does_not_set_stop():
    bars = _stable_bars(14, base=100.0, amplitude=0.3)
    bars.append({"close": 101.0, "high": 101.5, "low": 100.5})
    v = range_reversion_entry(bars)
    assert v.strict_stop is None


def test_touch_at_boundary_is_inclusive():
    """[WORKFLOW-G.3 2026-09-17] Touch at the exact
    boundary (= threshold) counts as a touch (inclusive)."""
    bars = _stable_bars(14, base=100.0, amplitude=0.3)
    # touch_threshold = 100.2 exactly.
    bars.append({"close": 99.8, "high": 100.2, "low": 100.2})
    v = range_reversion_entry(bars)
    assert v.signal == EntrySignal.ENTER


# -- 6. WAIT_INSUFFICIENT_BARS ------------------------------


def test_wait_insufficient_bars_when_too_few():
    """[WORKFLOW-G.3 2026-09-17] With fewer than window_size + 1
    bars, the verifier waits for more data."""
    bars = _stable_bars(10, base=100.0, amplitude=0.3)  # < 15.
    bars.append({"close": 99.8, "high": 100.2, "low": 99.5})
    v = range_reversion_entry(bars, window_size=14)
    assert v.signal == EntrySignal.WAIT_INSUFFICIENT_BARS


def test_wait_insufficient_bars_when_no_bars():
    v = range_reversion_entry([])
    assert v.signal == EntrySignal.WAIT_INSUFFICIENT_BARS


def test_wait_insufficient_bars_with_missing_ohlc():
    """[WORKFLOW-G.3 2026-09-17] Bars missing OHLC values
    produce WAIT_INSUFFICIENT_BARS (defensive)."""
    bars = [{"close": 100.0}] * 15  # missing high/low.
    v = range_reversion_entry(bars)
    assert v.signal == EntrySignal.WAIT_INSUFFICIENT_BARS


def test_wait_insufficient_bars_with_zero_mean():
    """[WORKFLOW-G.3 2026-09-17] All-zero bars (mean=0) are
    rejected defensively -- can't compute range_pct."""
    bars = [{"close": 0.0, "high": 0.0, "low": 0.0} for _ in range(15)]
    v = range_reversion_entry(bars)
    assert v.signal == EntrySignal.WAIT_INSUFFICIENT_BARS


# -- 7. RangeReversionVerdict dataclass --------------------


def test_to_dict_includes_required_fields():
    bars = _stable_bars(14, base=100.0, amplitude=0.3)
    bars.append({"close": 99.8, "high": 100.2, "low": 99.5})
    v = range_reversion_entry(bars)
    d = v.to_dict()
    expected = {"signal", "mean_target", "strict_stop",
                "recent_low", "range_pct", "expansion_ratio",
                "window_size", "notes"}
    assert set(d.keys()) == expected


def test_to_dict_rounds_float_values():
    bars = _stable_bars(14, base=100.0, amplitude=0.3)
    bars.append({"close": 99.8, "high": 100.2, "low": 99.5})
    v = range_reversion_entry(bars)
    d = v.to_dict()
    # All floats should be rounded to 4 decimals (or None).
    for k in ("mean_target", "strict_stop", "recent_low",
              "range_pct", "expansion_ratio"):
        val = d[k]
        if val is None:
            continue
        # Should not have more than 4 decimal places.
        s = str(val)
        if "." in s:
            decimals = len(s.split(".")[1])
            assert decimals <= 4, f"{k} has {decimals} decimals"


def test_verdict_is_immutable():
    """[WORKFLOW-G.3 2026-09-17] Verdict is a frozen
    dataclass -- can't be mutated post-construction."""
    import dataclasses
    # Check the dataclass is frozen.
    fields = dataclasses.fields(RangeReversionVerdict)
    # The class itself uses frozen=True via the decorator.
    # We can verify by attempting mutation.
    v = range_reversion_entry(_stable_bars(14) + [
        {"close": 99.8, "high": 100.2, "low": 99.5},
    ])
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.signal = EntrySignal.WAIT_NO_LOWER_TOUCH


# -- 8. Default window_size matches the inline logic ---------


def test_default_window_size_is_14():
    """[WORKFLOW-G.3 2026-09-17] The default window_size=14
    matches the inline logic in build_shadow_proposals."""
    # Build exactly 15 bars (window 14 + 1 entry bar).
    bars = _stable_bars(14, base=100.0, amplitude=0.3)
    bars.append({"close": 99.8, "high": 100.2, "low": 99.5})
    v = range_reversion_entry(bars)  # default window_size=14.
    assert v.window_size == 14
    assert v.signal == EntrySignal.ENTER
