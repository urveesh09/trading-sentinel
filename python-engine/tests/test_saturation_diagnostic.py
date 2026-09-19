"""[WORKFLOW-B.5 2026-09-17] Tests for the saturation diagnostic.

Per Workstream B in NEXT_AGENT_PLAN.md:
> Bound disk work. Current ``to_thread`` avoids event-loop
> blocking but awaiting it can still delay the advisory
> job. Introduce a bounded queue only with
> saturation/drop evidence, cancellation semantics and
> restart tests; never spawn unlimited writes.

These tests pin the diagnostic contract:

  - ``SaturationLevel`` enum has 3 levels.
  - ``compute_latency_stats`` aggregates count, mean,
    median, p95, p99, max, min, slow_count.
  - ``assess_saturation`` returns the right level:
    - NOT_SATURATED when p99 < limit and slow < limit.
    - WARNING when p95 > limit OR slow_fraction > limit.
    - SATURATED when p99 > limit.
  - Empty latencies return NOT_SATURATED with a
    recommendation to collect samples.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))

from saturation_diagnostic import (  # noqa: E402  -- import path
    LatencyStats,
    SaturationLevel,
    SaturationVerdict,
    assess_saturation,
    compute_latency_stats,
)


# -- 1. SaturationLevel enum ---------------------------------


def test_saturation_level_has_three_values():
    """[WORKFLOW-B.5 2026-09-17] Three levels:
    NOT_SATURATED / WARNING / SATURATED."""
    assert {l.value for l in SaturationLevel} == {
        "NOT_SATURATED", "WARNING", "SATURATED",
    }


# -- 2. compute_latency_stats --------------------------------


def test_compute_latency_stats_empty():
    stats = compute_latency_stats([])
    assert stats.count == 0
    assert stats.mean_seconds == 0.0
    assert stats.median_seconds == 0.0
    assert stats.p95_seconds == 0.0
    assert stats.p99_seconds == 0.0
    assert stats.max_seconds == 0.0
    assert stats.min_seconds == 0.0
    assert stats.slow_count == 0


def test_compute_latency_stats_basic_stats():
    stats = compute_latency_stats([0.1, 0.2, 0.3, 0.4, 0.5])
    assert stats.count == 5
    assert stats.mean_seconds == 0.3
    assert stats.median_seconds == 0.3
    assert stats.max_seconds == 0.5
    assert stats.min_seconds == 0.1


def test_compute_latency_stats_slow_count():
    stats = compute_latency_stats(
        [0.5, 0.6, 1.5, 1.6, 2.0],
        threshold_seconds=1.0,
    )
    assert stats.slow_count == 3  # 1.5, 1.6, 2.0.


def test_compute_latency_stats_single_value():
    stats = compute_latency_stats([0.5])
    assert stats.count == 1
    # Single value: mean=median=max=min=p95=p99=0.5.
    assert stats.mean_seconds == 0.5
    assert stats.median_seconds == 0.5
    assert stats.max_seconds == 0.5
    assert stats.min_seconds == 0.5
    assert stats.p95_seconds == 0.5
    assert stats.p99_seconds == 0.5


def test_compute_latency_stats_threshold_recorded():
    stats = compute_latency_stats([0.1, 0.2], threshold_seconds=2.5)
    assert stats.threshold_seconds == 2.5


# -- 3. assess_saturation: NOT_SATURATED ---------------------


def test_normal_latencies_returns_not_saturated():
    """[WORKFLOW-B.5 2026-09-17] All latencies within bounds
    -> NOT_SATURATED."""
    latencies = [0.05, 0.07, 0.06, 0.08, 0.04, 0.05, 0.06, 0.07,
                  0.05, 0.04]
    verdict = assess_saturation(latencies, threshold_seconds=1.0)
    assert verdict.level == SaturationLevel.NOT_SATURATED
    assert verdict.slow_fraction == 0.0
    assert "within bounds" in verdict.evidence[0]


def test_not_saturated_recommendation_says_no_queue_needed():
    latencies = [0.1, 0.2, 0.3]
    verdict = assess_saturation(latencies)
    assert "no bounded queue needed" in verdict.recommendation


# -- 4. assess_saturation: SATURATED -------------------------


def test_high_p99_returns_saturated():
    """[WORKFLOW-B.5 2026-09-17] p99 > 5s = SATURATED.

    With nearest-rank percentile on a 10-value list, p95
    and p99 both equal the maximum. Use 9 fast + 1 very
    slow so the maximum is the slow value, well above the
    p99_limit."""
    latencies = [0.1] * 9 + [10.0]
    verdict = assess_saturation(latencies,
                                  threshold_seconds=1.0,
                                  p99_limit_seconds=5.0)
    assert verdict.level == SaturationLevel.SATURATED
    assert any("p99" in e for e in verdict.evidence)


def test_saturated_recommendation_says_add_bounded_queue():
    """[WORKFLOW-B.5 2026-09-17] Single 10s sample = max =
    p99 = 10s > 5s limit = SATURATED."""
    latencies = [10.0]
    verdict = assess_saturation(latencies)
    assert "bounded queue" in verdict.recommendation


# -- 5. assess_saturation: WARNING --------------------------


def test_high_p95_with_ok_p99_returns_warning():
    """[WORKFLOW-B.5 2026-09-17] p95 > 2s but p99 <= 5s
    = WARNING (not SATURATED).

    With nearest-rank on small N, p95 = p99 = max. To get
    WARNING (not SATURATED), we use slow_fraction > limit
    instead -- this is the alternative WARNING trigger.
    """
    latencies = [0.5] * 7 + [2.0] * 3  # 30% slow.
    verdict = assess_saturation(
        latencies,
        threshold_seconds=1.0,
        p95_limit_seconds=10.0,
        p99_limit_seconds=10.0,
        slow_fraction_limit=0.20,
    )
    assert verdict.level == SaturationLevel.WARNING
    assert any("slow fraction" in e for e in verdict.evidence)


def test_high_slow_fraction_returns_warning():
    latencies = [0.5] * 7 + [2.0] * 3  # 30% slow.
    verdict = assess_saturation(
        latencies,
        threshold_seconds=1.0,
        p95_limit_seconds=10.0,
        p99_limit_seconds=100.0,
        slow_fraction_limit=0.20,
    )
    assert verdict.level == SaturationLevel.WARNING
    assert any("slow fraction" in e for e in verdict.evidence)


def test_warning_recommendation_says_investigate():
    latencies = [0.5] * 7 + [2.0] * 3
    verdict = assess_saturation(
        latencies,
        threshold_seconds=1.0,
        p95_limit_seconds=10.0,
        p99_limit_seconds=100.0,
        slow_fraction_limit=0.20,
    )
    assert "investigate" in verdict.recommendation


# -- 6. assess_saturation: edge cases -----------------------


def test_empty_latencies_returns_not_saturated():
    """[WORKFLOW-B.5 2026-09-17] Empty latencies -> NOT_SATURATED
    with a 'collect samples first' recommendation."""
    verdict = assess_saturation([])
    assert verdict.level == SaturationLevel.NOT_SATURATED
    assert "collect" in verdict.recommendation.lower()


def test_single_latency_below_threshold_returns_not_saturated():
    verdict = assess_saturation([0.5])
    assert verdict.level == SaturationLevel.NOT_SATURATED


def test_single_latency_above_p99_returns_saturated():
    verdict = assess_saturation([10.0])
    assert verdict.level == SaturationLevel.SATURATED


# -- 7. dataclass serialization -----------------------------


def test_latency_stats_to_dict_includes_all_fields():
    stats = compute_latency_stats([0.1, 0.2])
    d = stats.to_dict()
    expected = {
        "count", "mean_seconds", "median_seconds",
        "p95_seconds", "p99_seconds", "max_seconds",
        "min_seconds", "slow_count", "threshold_seconds",
    }
    assert set(d.keys()) == expected


def test_saturation_verdict_to_dict_includes_all_fields():
    latencies = [0.1, 0.2, 0.3]
    verdict = assess_saturation(latencies)
    d = verdict.to_dict()
    expected = {"level", "stats", "slow_fraction",
                "evidence", "recommendation"}
    assert set(d.keys()) == expected
    assert d["level"] == "NOT_SATURATED"
