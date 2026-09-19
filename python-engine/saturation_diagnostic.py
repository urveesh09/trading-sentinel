"""[WORKFLOW-B.5 2026-09-17] Saturation evidence diagnostic.

Per Workstream B in NEXT_AGENT_PLAN.md:
> Bound disk work. Current ``to_thread`` avoids event-loop
> blocking but awaiting it can still delay the advisory
> job. Introduce a bounded queue only with
> saturation/drop evidence, cancellation semantics and
> restart tests; never spawn unlimited writes.

This module is a read-only diagnostic. It does NOT
introduce a bounded queue (the plan reserves that for
after evidence is collected). Instead, it analyzes
advisory-job timing data and reports whether the system
is exhibiting saturation symptoms.

A system is "saturated" when:
  - tail latency (p95 / p99) exceeds a configured
    threshold, OR
  - the count of "slow" runs (latency > threshold)
    exceeds a fraction of the total runs.

The diagnostic takes a list of latency measurements
(seconds per advisory-job tick) and produces:

  - ``LatencyStats`` -- aggregate stats (count, mean,
    median, p95, p99, max).
  - ``SaturationVerdict`` -- the verdict (NOT_SATURATED /
    WARNING / SATURATED) + the evidence that drove it.
  - ``assess_saturation(latencies, ...)`` -- end-to-end
    diagnostic that returns the verdict.

Pure function. No I/O. No clock injection.
"""
from __future__ import annotations

import dataclasses
import enum
import statistics
from typing import Iterable, Optional


class SaturationLevel(str, enum.Enum):
    """The system's saturation level."""
    NOT_SATURATED = "NOT_SATURATED"
    WARNING = "WARNING"  # tail latency elevated.
    SATURATED = "SATURATED"  # sustained high latency / many slow runs.


@dataclasses.dataclass(frozen=True)
class LatencyStats:
    """Aggregate stats for a list of latencies (seconds)."""
    count: int
    mean_seconds: float
    median_seconds: float
    p95_seconds: float
    p99_seconds: float
    max_seconds: float
    min_seconds: float
    slow_count: int  # count of latencies > threshold_seconds
    threshold_seconds: float

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "mean_seconds": self.mean_seconds,
            "median_seconds": self.median_seconds,
            "p95_seconds": self.p95_seconds,
            "p99_seconds": self.p99_seconds,
            "max_seconds": self.max_seconds,
            "min_seconds": self.min_seconds,
            "slow_count": self.slow_count,
            "threshold_seconds": self.threshold_seconds,
        }


@dataclasses.dataclass(frozen=True)
class SaturationVerdict:
    """Verdict + evidence for a single diagnostic run."""
    level: SaturationLevel
    stats: LatencyStats
    slow_fraction: float  # slow_count / count.
    evidence: tuple[str, ...]
    recommendation: str

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "stats": self.stats.to_dict(),
            "slow_fraction": self.slow_fraction,
            "evidence": list(self.evidence),
            "recommendation": self.recommendation,
        }


def _percentile(values: list[float], pct: float) -> float:
    """Compute the ``pct`` percentile (0-100) using a simple
    sorted-index method. For small lists (n < 100) we use
    nearest-rank; for larger lists we interpolate."""
    if not values:
        return 0.0
    if pct < 0 or pct > 100:
        raise ValueError(f"pct must be 0-100; got {pct}")
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    # Nearest-rank percentile.
    rank = max(0, min(len(sorted_values) - 1,
                       int(round((pct / 100.0) * (len(sorted_values) - 1)))))
    return sorted_values[rank]


def compute_latency_stats(
    latencies: Iterable[float],
    *,
    threshold_seconds: float = 1.0,
) -> LatencyStats:
    """Compute aggregate stats for a list of latencies.

    Args:
        latencies: advisory-job tick latencies in seconds
            (one per run).
        threshold_seconds: a run is "slow" if its latency
            exceeds this. Default 1.0s.
    """
    values = list(latencies)
    if not values:
        return LatencyStats(
            count=0, mean_seconds=0.0, median_seconds=0.0,
            p95_seconds=0.0, p99_seconds=0.0,
            max_seconds=0.0, min_seconds=0.0,
            slow_count=0, threshold_seconds=threshold_seconds,
        )
    slow_count = sum(1 for v in values if v > threshold_seconds)
    return LatencyStats(
        count=len(values),
        mean_seconds=float(statistics.mean(values)),
        median_seconds=float(statistics.median(values)),
        p95_seconds=_percentile(values, 95.0),
        p99_seconds=_percentile(values, 99.0),
        max_seconds=float(max(values)),
        min_seconds=float(min(values)),
        slow_count=slow_count,
        threshold_seconds=threshold_seconds,
    )


def assess_saturation(
    latencies: Iterable[float],
    *,
    threshold_seconds: float = 1.0,
    p95_limit_seconds: float = 2.0,
    p99_limit_seconds: float = 5.0,
    slow_fraction_limit: float = 0.10,
) -> SaturationVerdict:
    """Run the saturation diagnostic end-to-end.

    Args:
        latencies: per-run advisory-job latencies.
        threshold_seconds: a run is "slow" if its latency
            exceeds this.
        p95_limit_seconds: when p95 exceeds this, the
            verdict is at least WARNING.
        p99_limit_seconds: when p99 exceeds this, the
            verdict is at least SATURATED.
        slow_fraction_limit: when slow_count / total_count
            exceeds this, the verdict is at least WARNING.
    """
    stats = compute_latency_stats(latencies,
                                    threshold_seconds=threshold_seconds)
    if stats.count == 0:
        return SaturationVerdict(
            level=SaturationLevel.NOT_SATURATED,
            stats=stats,
            slow_fraction=0.0,
            evidence=("no latency measurements; cannot assess",),
            recommendation=(
                "collect per-run latency samples before drawing "
                "a saturation conclusion"
            ),
        )

    slow_fraction = stats.slow_count / stats.count
    evidence: list[str] = []
    level = SaturationLevel.NOT_SATURATED

    if stats.p99_seconds > p99_limit_seconds:
        evidence.append(
            f"p99 latency {stats.p99_seconds:.2f}s "
            f"exceeds limit {p99_limit_seconds:.2f}s"
        )
        level = SaturationLevel.SATURATED
    if stats.p95_seconds > p95_limit_seconds:
        evidence.append(
            f"p95 latency {stats.p95_seconds:.2f}s "
            f"exceeds limit {p95_limit_seconds:.2f}s"
        )
        if level == SaturationLevel.NOT_SATURATED:
            level = SaturationLevel.WARNING
    if slow_fraction > slow_fraction_limit:
        evidence.append(
            f"slow fraction {slow_fraction:.1%} "
            f"exceeds limit {slow_fraction_limit:.1%}"
        )
        if level == SaturationLevel.NOT_SATURATED:
            level = SaturationLevel.WARNING

    if not evidence:
        evidence.append(
            f"all latency measurements within bounds "
            f"(p95={stats.p95_seconds:.2f}s, "
            f"p99={stats.p99_seconds:.2f}s, "
            f"slow={slow_fraction:.1%})"
        )
        recommendation = (
            "system is NOT_SATURATED; no bounded queue needed yet"
        )
    elif level == SaturationLevel.WARNING:
        recommendation = (
            "WARNING: tail latency is elevated; investigate "
            "before adding a bounded queue"
        )
    else:
        recommendation = (
            "SATURATED: evidence supports adding a bounded queue "
            "with saturation/drop semantics; review cancellation "
            "semantics and run the bounded-queue test plan"
        )

    return SaturationVerdict(
        level=level,
        stats=stats,
        slow_fraction=slow_fraction,
        evidence=tuple(evidence),
        recommendation=recommendation,
    )


__all__ = [
    "LatencyStats",
    "SaturationLevel",
    "SaturationVerdict",
    "assess_saturation",
    "compute_latency_stats",
]
