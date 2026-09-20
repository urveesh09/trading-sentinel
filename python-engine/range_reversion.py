"""[WORKFLOW-G.3 2026-09-17] Range mean-reversion entry profile.

Per Workstream G in NEXT_AGENT_PLAN.md:
> Range mean reversion with strict invalidation. Stable
> range/no expansion. Comparison: No-trade baseline and
> existing range logic. Main risk: Regime shift produces
> tail losses.

G.3 introduces a DEDICATED entry semantics for
``RANGE_REVERSION_V1`` proposals. Previously the
proactive-intelligence dispatcher routed these proposals
through the ``COMPLETED_BAR_CONFIRMATION_V1`` fallback,
which is the plan note:
> RANGE_REVERSION_V1 dispatcher still routes through
> completed-bar-confirmation fallback.

This module implements the range-specific entry:

  1. **Range detection**: a window of N bars has a range
     (max - min) <= ``max_range_pct * mean``.
  2. **Lower-band touch**: the entry bar's low is at or
     below the recent range low (within ``touch_tolerance``).
  3. **No expansion**: the range must NOT be expanding
     (the most-recent half-window's range <= the older
     half-window's range, otherwise we're in a breakout,
     not a range).
  4. **Mean target**: ``target = mean(window)``.
  5. **Strict invalidation**: ``stop = recent_low - epsilon``.

The new entry timing is *narrower* than the
COMPLETED_BAR_CONFIRMATION fallback: range_reversion
enters ONLY when the lower band is touched AND the range
is intact. This produces fewer trades but with higher
hit rate on the mean-reversion hypothesis.

The module exposes a pure function:
``range_reversion_entry(bars, *, ...) -> RangeReversionVerdict``.

The verdict includes:
  - Whether the entry condition is satisfied.
  - The mean target (if entry is satisfied).
  - The strict invalidation stop (if entry is satisfied).
  - The observed range width (for the audit log).

Per the plan: 'Main risk: Regime shift produces tail
losses.' The strict invalidation (a fixed stop below
the range low) bounds the per-trade loss in regime
shifts; the operator can tighten the stop further.

Read-only. No I/O. No DB. No clock injection.
"""
from __future__ import annotations

import dataclasses
import enum
import math
from datetime import datetime
from typing import Iterable, Optional


class EntrySignal(str, enum.Enum):
    """The entry signal produced by the verifier."""
    ENTER = "ENTER"  # entry conditions satisfied.
    WAIT_RANGE_NOT_INTACT = "WAIT_RANGE_NOT_INTACT"
    WAIT_RANGE_EXPANDING = "WAIT_RANGE_EXPANDING"
    WAIT_NO_LOWER_TOUCH = "WAIT_NO_LOWER_TOUCH"
    WAIT_INSUFFICIENT_BARS = "WAIT_INSUFFICIENT_BARS"


@dataclasses.dataclass(frozen=True)
class RangeReversionVerdict:
    """Verdict from the range-reversion entry check.

    Attributes:
        signal: ENTER if all conditions satisfied;
            otherwise the reason to wait.
        mean_target: the mean of the analysis window
            (set when ENTER, else None).
        strict_stop: the strict invalidation stop
            (just below the recent low; set when ENTER,
            else None).
        recent_low: the recent range low used as the
            anchor for the strict stop (set when ENTER,
            else None).
        range_pct: the observed range width as a fraction
            of the mean (set when ENTER or
            WAIT_RANGE_NOT_INTACT, else None).
        expansion_ratio: recent-half range / older-half
            range (set when ENTER or WAIT_RANGE_EXPANDING,
            else None).
        window_size: number of bars in the analysis
            window.
        notes: human-readable notes for the audit log.
    """
    signal: EntrySignal
    mean_target: Optional[float]
    strict_stop: Optional[float]
    recent_low: Optional[float]
    range_pct: Optional[float]
    expansion_ratio: Optional[float]
    window_size: int
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "signal": self.signal.value,
            "mean_target": (
                round(self.mean_target, 4)
                if self.mean_target is not None else None
            ),
            "strict_stop": (
                round(self.strict_stop, 4)
                if self.strict_stop is not None else None
            ),
            "recent_low": (
                round(self.recent_low, 4)
                if self.recent_low is not None else None
            ),
            "range_pct": (
                round(self.range_pct, 4)
                if self.range_pct is not None else None
            ),
            "expansion_ratio": (
                round(self.expansion_ratio, 4)
                if self.expansion_ratio is not None else None
            ),
            "window_size": self.window_size,
            "notes": list(self.notes),
        }


def _safe_mean(values: list[float]) -> Optional[float]:
    """Mean that returns ``None`` for empty input."""
    if not values:
        return None
    total = sum(values)
    if not math.isfinite(total):
        return None
    return total / len(values)


def range_reversion_entry(
    bars: Iterable[dict],
    *,
    window_size: int = 14,
    max_range_pct: float = 0.06,
    expansion_limit: float = 1.5,
    touch_tolerance_pct: float = 0.005,
    strict_stop_epsilon: float = 0.001,
) -> RangeReversionVerdict:
    """Check whether ``bars`` satisfies the range-reversion
    entry conditions.

    Args:
        bars: iterable of bar dicts, each with at least
            ``close``, ``high``, ``low``, and
            optionally ``volume``.
        window_size: number of bars to use for range
            detection (default 14, matching the
            ``build_shadow_proposals`` inline logic).
        max_range_pct: maximum allowed (max-min)/mean for
            the window. Default 6%, matching the inline
            threshold.
        expansion_limit: if the recent half-window's
            range is more than ``expansion_limit`` times
            the older half's range, the range is
            expanding -- WAIT. Default 1.5.
        touch_tolerance_pct: how close to the recent low
            the entry bar's low must be, as a fraction of
            the mean. Default 0.5%.
        strict_stop_epsilon: how far below the recent low
            to set the strict stop, as a fraction of the
            mean. Default 0.1%.

    Returns:
        A ``RangeReversionVerdict`` with the entry signal
        and the relevant price levels (when ENTER).
    """
    notes: list[str] = []
    bars_list = list(bars)
    if len(bars_list) < window_size + 1:
        return RangeReversionVerdict(
            signal=EntrySignal.WAIT_INSUFFICIENT_BARS,
            mean_target=None,
            strict_stop=None,
            recent_low=None,
            range_pct=None,
            expansion_ratio=None,
            window_size=len(bars_list),
            notes=(
                f"need {window_size + 1} bars, got {len(bars_list)}",
            ),
        )

    # The analysis window excludes the entry bar (the last
    # bar in the input). This matches the inline logic at
    # proactive_intelligence.py:182 which uses closes[-15:-1].
    window = bars_list[-(window_size + 1):-1]
    closes = [bar.get("close") for bar in window]
    highs = [bar.get("high") for bar in window]
    lows = [bar.get("low") for bar in window]
    if any(v is None for v in closes + highs + lows):
        return RangeReversionVerdict(
            signal=EntrySignal.WAIT_INSUFFICIENT_BARS,
            mean_target=None,
            strict_stop=None,
            recent_low=None,
            range_pct=None,
            expansion_ratio=None,
            window_size=window_size,
            notes=("missing OHLC values in window",),
        )

    mean = _safe_mean(closes)
    if mean is None or mean <= 0:
        return RangeReversionVerdict(
            signal=EntrySignal.WAIT_INSUFFICIENT_BARS,
            mean_target=None,
            strict_stop=None,
            recent_low=None,
            range_pct=None,
            expansion_ratio=None,
            window_size=window_size,
            notes=("mean is non-positive",),
        )

    window_max = max(highs)
    window_min = min(lows)
    range_pct = (window_max - window_min) / mean

    # 1. Range intact check.
    if range_pct > max_range_pct:
        return RangeReversionVerdict(
            signal=EntrySignal.WAIT_RANGE_NOT_INTACT,
            mean_target=mean,
            strict_stop=None,
            recent_low=None,
            range_pct=range_pct,
            expansion_ratio=None,
            window_size=window_size,
            notes=(
                f"range {range_pct:.4f} > max_range_pct {max_range_pct}",
            ),
        )
    notes.append(f"range {range_pct:.4f} within {max_range_pct}")

    # 2. Expansion check.
    half = window_size // 2
    older_half_highs = highs[:half]
    older_half_lows = lows[:half]
    recent_half_highs = highs[half:]
    recent_half_lows = lows[half:]
    older_range = max(older_half_highs) - min(older_half_lows)
    recent_range = max(recent_half_highs) - min(recent_half_lows)
    if older_range > 0:
        expansion_ratio = recent_range / older_range
    else:
        # Older half has no range -- treat as non-expanding.
        expansion_ratio = 0.0
    if expansion_ratio > expansion_limit:
        return RangeReversionVerdict(
            signal=EntrySignal.WAIT_RANGE_EXPANDING,
            mean_target=mean,
            strict_stop=None,
            recent_low=None,
            range_pct=range_pct,
            expansion_ratio=expansion_ratio,
            window_size=window_size,
            notes=(
                f"recent range {recent_range:.4f} / older range "
                f"{older_range:.4f} = {expansion_ratio:.4f} "
                f"> expansion_limit {expansion_limit}"
            ),
        )
    notes.append(f"expansion_ratio {expansion_ratio:.4f} within {expansion_limit}")

    # 3. Lower-band touch check.
    entry_bar = bars_list[-1]
    entry_low = entry_bar.get("low")
    entry_close = entry_bar.get("close")
    if entry_low is None or entry_close is None:
        return RangeReversionVerdict(
            signal=EntrySignal.WAIT_NO_LOWER_TOUCH,
            mean_target=mean,
            strict_stop=None,
            recent_low=window_min,
            range_pct=range_pct,
            expansion_ratio=expansion_ratio,
            window_size=window_size,
            notes=("entry bar has no low/close",),
        )
    touch_threshold = window_min + mean * touch_tolerance_pct
    if entry_low > touch_threshold:
        return RangeReversionVerdict(
            signal=EntrySignal.WAIT_NO_LOWER_TOUCH,
            mean_target=mean,
            strict_stop=None,
            recent_low=window_min,
            range_pct=range_pct,
            expansion_ratio=expansion_ratio,
            window_size=window_size,
            notes=(
                f"entry low {entry_low:.4f} > touch threshold "
                f"{touch_threshold:.4f} (window_min {window_min:.4f} + "
                f"mean {mean:.4f} * tolerance {touch_tolerance_pct})"
            ),
        )
    notes.append(f"entry low {entry_low:.4f} touched band {touch_threshold:.4f}")

    # 4. Strict invalidation: stop just below the recent low.
    strict_stop = window_min - mean * strict_stop_epsilon

    notes.append(f"mean_target {mean:.4f}, strict_stop {strict_stop:.4f}")

    return RangeReversionVerdict(
        signal=EntrySignal.ENTER,
        mean_target=mean,
        strict_stop=strict_stop,
        recent_low=window_min,
        range_pct=range_pct,
        expansion_ratio=expansion_ratio,
        window_size=window_size,
        notes=tuple(notes),
    )


__all__ = [
    "EntrySignal",
    "RangeReversionVerdict",
    "range_reversion_entry",
]
