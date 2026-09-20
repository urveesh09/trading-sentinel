"""[WORKFLOW-B.2 2026-09-17] Quote + public-event gap detector.

Per Workstream B in NEXT_AGENT_PLAN.md:
> Track quote and public-event gaps independently. Avoid
> pretending a stop between unobserved samples has a known
> fill.

This module is a pure analyzer. Given an ordered list of
observation timestamps, it computes:

  - ``detect_gaps(timestamps, ...)`` -- returns a list of
    ``Gap`` records (one per gap > the threshold).
  - ``gap_summary(gaps)`` -- aggregate stats (count,
    total_seconds, max_seconds, mean_seconds).
  - ``gap_crosses_entry_cutoff(gap, entry_cutoff)`` --
    whether the gap spans the configured entry cutoff.
  - ``gap_could_hide_fill(gap, max_acceptable_gap)`` --
    whether the gap is wide enough to potentially hide
    a fill (the plan's rule). The caller decides what
    threshold means "could hide a fill" -- it depends on
    the strategy's holding_horizon.

The "could hide a fill" rule is the key plan item:
> Avoid pretending a stop between unobserved samples has
> a known fill.

If the gap is wider than the operator-set
``max_acceptable_gap``, we surface it as
``GAP_COULD_HIDE_FILL`` so the audit pipeline can flag
that the strategy's between-sample state is uncertain.

Pure function. No I/O. No DB. No clock injection (the
caller passes the timestamps).
"""
from __future__ import annotations

import dataclasses
import enum
import statistics
from datetime import datetime, timedelta
from typing import Iterable, Optional


class GapSeverity(str, enum.Enum):
    """Severity of a single gap."""
    NORMAL = "NORMAL"  # gap < threshold
    SUSPICIOUS = "SUSPICIOUS"  # gap >= threshold
    GAP_COULD_HIDE_FILL = "GAP_COULD_HIDE_FILL"  # gap >= max_acceptable


@dataclasses.dataclass(frozen=True)
class Gap:
    """A single gap between two consecutive observations.

    Attributes:
        start_at: timestamp of the LAST observation before
            the gap.
        end_at: timestamp of the FIRST observation after
            the gap.
        duration: timedelta between the two observations.
        severity: GapSeverity classification.
    """
    start_at: datetime
    end_at: datetime
    duration: timedelta
    severity: GapSeverity = GapSeverity.NORMAL

    def to_dict(self) -> dict:
        return {
            "start_at": self.start_at.isoformat(),
            "end_at": self.end_at.isoformat(),
            "duration_seconds": self.duration.total_seconds(),
            "severity": self.severity.value,
        }


@dataclasses.dataclass(frozen=True)
class GapSummary:
    """Aggregate stats for a list of gaps.

    Attributes:
        count: number of gaps.
        total_seconds: sum of gap durations.
        max_seconds: longest gap.
        mean_seconds: average gap (0.0 when count == 0).
        median_seconds: median gap.
        by_severity: dict mapping severity -> count.
    """
    count: int
    total_seconds: float
    max_seconds: float
    mean_seconds: float
    median_seconds: float
    by_severity: dict

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "total_seconds": self.total_seconds,
            "max_seconds": self.max_seconds,
            "mean_seconds": self.mean_seconds,
            "median_seconds": self.median_seconds,
            "by_severity": dict(self.by_severity),
        }


def _gap_severity(duration: timedelta, *,
                    max_acceptable_gap: timedelta) -> GapSeverity:
    """Classify a gap by duration.

    Per the plan: 'Avoid pretending a stop between
    unobserved samples has a known fill.' A gap wider than
    ``max_acceptable_gap`` is flagged as
    GAP_COULD_HIDE_FILL.
    """
    if duration >= max_acceptable_gap:
        return GapSeverity.GAP_COULD_HIDE_FILL
    return GapSeverity.NORMAL


def detect_gaps(
    timestamps: Iterable[datetime],
    *,
    max_acceptable_gap: timedelta,
) -> list[Gap]:
    """Detect gaps in an ordered sequence of timestamps.

    The input must be sorted ascending. Out-of-order inputs
    are auto-sorted (so callers don't need to worry about
    ordering).

    A gap is the timedelta between two consecutive
    observations. Two consecutive observations 0 seconds
    apart produce no gap. Two observations 30 minutes apart
    produce a 30-minute gap.

    Args:
        timestamps: ordered (or sortable) timestamps of
            observations.
        max_acceptable_gap: gaps >= this threshold are
            flagged as ``GAP_COULD_HIDE_FILL``. Smaller
            gaps are NORMAL.

    Returns:
        A list of ``Gap`` records, one per gap, in
        chronological order.
    """
    sorted_ts = sorted(timestamps)
    if len(sorted_ts) < 2:
        return []
    gaps: list[Gap] = []
    for prev, curr in zip(sorted_ts[:-1], sorted_ts[1:]):
        if curr <= prev:
            continue  # zero or negative gap (defensive)
        duration = curr - prev
        severity = _gap_severity(
            duration, max_acceptable_gap=max_acceptable_gap,
        )
        gaps.append(Gap(
            start_at=prev, end_at=curr,
            duration=duration, severity=severity,
        ))
    return gaps


def gap_summary(gaps: list[Gap]) -> GapSummary:
    """Aggregate stats for a list of gaps."""
    if not gaps:
        return GapSummary(
            count=0, total_seconds=0.0, max_seconds=0.0,
            mean_seconds=0.0, median_seconds=0.0,
            by_severity={},
        )
    durations = [g.duration.total_seconds() for g in gaps]
    by_severity: dict[str, int] = {}
    for g in gaps:
        by_severity[g.severity.value] = (
            by_severity.get(g.severity.value, 0) + 1
        )
    return GapSummary(
        count=len(gaps),
        total_seconds=float(sum(durations)),
        max_seconds=float(max(durations)),
        mean_seconds=float(statistics.mean(durations)),
        median_seconds=float(statistics.median(durations)),
        by_severity=by_severity,
    )


def gap_crosses_entry_cutoff(
    gap: Gap,
    *,
    entry_cutoff_minute: int,
    session_open_minute: int = 9 * 60 + 15,
) -> bool:
    """True iff the gap spans the entry-cutoff minute.

    The cutoff is computed against the gap's start_at date
    (assumed IST or UTC -- caller passes the gap's date
    in the relevant tz). The function checks whether
    ``entry_cutoff_minute`` falls within the gap interval.
    """
    if gap.end_at <= gap.start_at:
        return False
    start_min = gap.start_at.hour * 60 + gap.start_at.minute
    end_min = gap.end_at.hour * 60 + gap.end_at.minute
    if start_min <= end_min:
        return start_min < entry_cutoff_minute < end_min
    # Wrap around midnight.
    return entry_cutoff_minute > start_min or entry_cutoff_minute < end_min


def gap_could_hide_fill(gap: Gap, *,
                          max_acceptable_gap: timedelta) -> bool:
    """Per the plan: 'Avoid pretending a stop between
    unobserved samples has a known fill.'

    Returns True iff the gap is wider than
    ``max_acceptable_gap``. Callers should treat any
    such gap as uncertain: between-sample state is
    unknown.
    """
    return gap.duration >= max_acceptable_gap


def audit_gaps(
    timestamps: Iterable[datetime],
    *,
    max_acceptable_gap: timedelta,
    entry_cutoff_minute: Optional[int] = None,
) -> dict:
    """End-to-end gap audit. Returns a structured report.

    The report includes:
      - ``summary``: aggregate stats.
      - ``gaps``: list of all gap records.
      - ``fill_uncertain_gaps``: subset of gaps that
        could hide a fill (duration >= max_acceptable_gap).
      - ``crosses_entry_cutoff``: list of gaps that
        span the entry cutoff (when entry_cutoff_minute is
        set).
    """
    gaps = detect_gaps(timestamps,
                         max_acceptable_gap=max_acceptable_gap)
    summary = gap_summary(gaps)
    fill_uncertain = [g for g in gaps if gap_could_hide_fill(
        g, max_acceptable_gap=max_acceptable_gap,
    )]
    crosses_cutoff: list[Gap] = []
    if entry_cutoff_minute is not None:
        for g in gaps:
            if gap_crosses_entry_cutoff(
                g, entry_cutoff_minute=entry_cutoff_minute,
            ):
                crosses_cutoff.append(g)
    return {
        "summary": summary.to_dict(),
        "max_acceptable_gap_seconds": (
            max_acceptable_gap.total_seconds()
        ),
        "gaps": [g.to_dict() for g in gaps],
        "fill_uncertain_gaps": [g.to_dict() for g in fill_uncertain],
        "crosses_entry_cutoff": [g.to_dict() for g in crosses_cutoff],
        "entry_cutoff_minute": entry_cutoff_minute,
    }


__all__ = [
    "Gap",
    "GapSeverity",
    "GapSummary",
    "audit_gaps",
    "detect_gaps",
    "gap_could_hide_fill",
    "gap_crosses_entry_cutoff",
    "gap_summary",
]
