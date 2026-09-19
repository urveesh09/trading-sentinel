"""[WORKFLOW-B.2 2026-09-17] Tests for the gap detector.

Per Workstream B in NEXT_AGENT_PLAN.md:
> Track quote and public-event gaps independently. Avoid
> pretending a stop between unobserved samples has a known
> fill.

These tests pin:

  - ``detect_gaps`` returns one Gap per pair of consecutive
    observations.
  - ``gap_summary`` aggregates count, total, max, mean,
    median, by_severity.
  - ``gap_crosses_entry_cutoff`` returns True iff the gap
    spans the cutoff minute.
  - ``gap_could_hide_fill`` returns True iff the gap is
    wider than the threshold (the plan's rule).
  - ``audit_gaps`` end-to-end returns a structured report
    with fill_uncertain_gaps and crosses_entry_cutoff.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from zoneinfo import ZoneInfo

PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))

from gap_detector import (  # noqa: E402  -- import path
    Gap,
    GapSeverity,
    GapSummary,
    audit_gaps,
    detect_gaps,
    gap_could_hide_fill,
    gap_crosses_entry_cutoff,
    gap_summary,
)


IST = ZoneInfo("Asia/Kolkata")


def _ts(hour: int, minute: int, *, day: int = 14) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=IST)


# -- 1. detect_gaps basic behavior ---------------------------


def test_detect_gaps_returns_empty_for_one_timestamp():
    assert detect_gaps([_ts(9, 30)], max_acceptable_gap=timedelta(minutes=10)) == []


def test_detect_gaps_returns_empty_for_zero_timestamps():
    assert detect_gaps([], max_acceptable_gap=timedelta(minutes=10)) == []


def test_detect_gaps_with_two_consecutive_timestamps():
    ts = [_ts(9, 30), _ts(9, 31)]
    gaps = detect_gaps(ts, max_acceptable_gap=timedelta(minutes=10))
    assert len(gaps) == 1
    assert gaps[0].duration == timedelta(minutes=1)


def test_detect_gaps_with_multiple_timestamps():
    ts = [_ts(9, 30), _ts(9, 31), _ts(10, 0)]
    gaps = detect_gaps(ts, max_acceptable_gap=timedelta(minutes=10))
    assert len(gaps) == 2
    assert gaps[0].duration == timedelta(minutes=1)
    assert gaps[1].duration == timedelta(minutes=29)


def test_detect_gaps_sorts_unsorted_input():
    ts = [_ts(10, 0), _ts(9, 30), _ts(9, 31)]
    gaps = detect_gaps(ts, max_acceptable_gap=timedelta(minutes=10))
    assert len(gaps) == 2
    assert gaps[0].start_at < gaps[1].start_at


def test_detect_gaps_skips_zero_or_negative_durations():
    """[WORKFLOW-B.2 2026-09-17] Defensive: same-timestamp
    rows produce no gap (would cause divide-by-zero in
    downstream rate calculations)."""
    ts = [_ts(9, 30), _ts(9, 30), _ts(9, 31)]
    gaps = detect_gaps(ts, max_acceptable_gap=timedelta(minutes=10))
    assert len(gaps) == 1
    assert gaps[0].duration == timedelta(minutes=1)


# -- 2. Gap severity ---------------------------------------


def test_short_gap_classified_normal():
    ts = [_ts(9, 30), _ts(9, 31)]
    gaps = detect_gaps(ts, max_acceptable_gap=timedelta(minutes=10))
    assert gaps[0].severity == GapSeverity.NORMAL


def test_gap_at_threshold_classified_as_could_hide_fill():
    """[WORKFLOW-B.2 2026-09-17] Gap exactly at threshold =
    GAP_COULD_HIDE_FILL."""
    ts = [_ts(9, 30), _ts(9, 40)]  # 10 minutes.
    gaps = detect_gaps(ts, max_acceptable_gap=timedelta(minutes=10))
    assert gaps[0].severity == GapSeverity.GAP_COULD_HIDE_FILL


def test_gap_above_threshold_classified_as_could_hide_fill():
    ts = [_ts(9, 30), _ts(10, 30)]  # 1 hour.
    gaps = detect_gaps(ts, max_acceptable_gap=timedelta(minutes=10))
    assert gaps[0].severity == GapSeverity.GAP_COULD_HIDE_FILL


# -- 3. gap_summary ----------------------------------------


def test_gap_summary_empty():
    summary = gap_summary([])
    assert summary.count == 0
    assert summary.total_seconds == 0.0
    assert summary.max_seconds == 0.0
    assert summary.mean_seconds == 0.0
    assert summary.median_seconds == 0.0
    assert summary.by_severity == {}


def test_gap_summary_basic_stats():
    ts = [_ts(9, 30), _ts(9, 35), _ts(10, 30), _ts(14, 50)]
    gaps = detect_gaps(ts, max_acceptable_gap=timedelta(minutes=10))
    summary = gap_summary(gaps)
    assert summary.count == 3
    # First gap: 5min=300s, second: 55min=3300s, third: 4h20m=15600s.
    assert summary.max_seconds == 15600.0
    assert summary.total_seconds == 300.0 + 3300.0 + 15600.0


def test_gap_summary_by_severity():
    ts = [_ts(9, 30), _ts(9, 31), _ts(10, 0)]
    gaps = detect_gaps(ts, max_acceptable_gap=timedelta(minutes=10))
    summary = gap_summary(gaps)
    # First gap NORMAL, second GAP_COULD_HIDE_FILL.
    assert summary.by_severity["NORMAL"] == 1
    assert summary.by_severity["GAP_COULD_HIDE_FILL"] == 1


# -- 4. gap_crosses_entry_cutoff ---------------------------


def test_gap_crossing_entry_cutoff_returns_true():
    """[WORKFLOW-B.2 2026-09-17] A gap that spans the entry
    cutoff must be flagged for the audit pipeline."""
    gap = Gap(
        start_at=_ts(10, 0),
        end_at=_ts(15, 0),
        duration=timedelta(hours=5),
    )
    assert gap_crosses_entry_cutoff(
        gap, entry_cutoff_minute=14 * 60 + 45,
    ) is True


def test_gap_not_crossing_entry_cutoff_returns_false():
    gap = Gap(
        start_at=_ts(9, 30),
        end_at=_ts(10, 30),
        duration=timedelta(hours=1),
    )
    assert gap_crosses_entry_cutoff(
        gap, entry_cutoff_minute=14 * 60 + 45,
    ) is False


def test_gap_ending_exactly_at_cutoff_returns_false():
    """[WORKFLOW-B.2 2026-09-17] Strict inequality: a gap
    that ends EXACTLY at the cutoff doesn't span it."""
    gap = Gap(
        start_at=_ts(9, 30),
        end_at=_ts(14, 45),
        duration=timedelta(hours=5, minutes=15),
    )
    assert gap_crosses_entry_cutoff(
        gap, entry_cutoff_minute=14 * 60 + 45,
    ) is False


# -- 5. gap_could_hide_fill --------------------------------


def test_gap_below_threshold_does_not_hide_fill():
    gap = Gap(
        start_at=_ts(9, 30),
        end_at=_ts(9, 35),
        duration=timedelta(minutes=5),
    )
    assert gap_could_hide_fill(
        gap, max_acceptable_gap=timedelta(minutes=10),
    ) is False


def test_gap_at_threshold_could_hide_fill():
    gap = Gap(
        start_at=_ts(9, 30),
        end_at=_ts(9, 40),
        duration=timedelta(minutes=10),
    )
    assert gap_could_hide_fill(
        gap, max_acceptable_gap=timedelta(minutes=10),
    ) is True


# -- 6. audit_gaps end-to-end ------------------------------


def test_audit_gaps_returns_structured_report():
    ts = [_ts(9, 30), _ts(9, 31), _ts(10, 0), _ts(14, 50)]
    report = audit_gaps(
        ts, max_acceptable_gap=timedelta(minutes=10),
        entry_cutoff_minute=14 * 60 + 45,
    )
    assert "summary" in report
    assert "gaps" in report
    assert "fill_uncertain_gaps" in report
    assert "crosses_entry_cutoff" in report


def test_audit_gaps_fill_uncertain_subset():
    ts = [_ts(9, 30), _ts(9, 31), _ts(10, 0)]
    report = audit_gaps(ts, max_acceptable_gap=timedelta(minutes=10))
    # First gap (1min) is below threshold.
    # Second gap (29min) is above.
    assert len(report["fill_uncertain_gaps"]) == 1
    assert report["fill_uncertain_gaps"][0]["duration_seconds"] == 29 * 60


def test_audit_gaps_crosses_entry_cutoff_subset():
    """[WORKFLOW-B.2 2026-09-17] End-to-end: a gap that
    spans 14:45 must appear in crosses_entry_cutoff."""
    ts = [_ts(10, 0), _ts(14, 50)]
    report = audit_gaps(
        ts, max_acceptable_gap=timedelta(minutes=10),
        entry_cutoff_minute=14 * 60 + 45,
    )
    assert len(report["crosses_entry_cutoff"]) == 1


def test_audit_gaps_without_entry_cutoff_skips_cutoff_check():
    """[WORKFLOW-B.2 2026-09-17] When entry_cutoff_minute is
    None, the crosses_entry_cutoff list is empty (not a
    crash)."""
    ts = [_ts(10, 0), _ts(15, 0)]
    report = audit_gaps(
        ts, max_acceptable_gap=timedelta(minutes=10),
        entry_cutoff_minute=None,
    )
    assert report["crosses_entry_cutoff"] == []
    assert report["entry_cutoff_minute"] is None


def test_audit_gaps_max_acceptable_gap_in_report():
    ts = [_ts(10, 0), _ts(10, 5)]
    report = audit_gaps(
        ts, max_acceptable_gap=timedelta(minutes=3),
    )
    assert report["max_acceptable_gap_seconds"] == 180.0


# -- 7. Gap dataclass serialization ------------------------


def test_gap_to_dict_includes_required_fields():
    gap = Gap(
        start_at=_ts(9, 30),
        end_at=_ts(9, 35),
        duration=timedelta(minutes=5),
        severity=GapSeverity.NORMAL,
    )
    d = gap.to_dict()
    assert d["start_at"] == "2026-09-14T09:30:00+05:30"
    assert d["end_at"] == "2026-09-14T09:35:00+05:30"
    assert d["duration_seconds"] == 300.0
    assert d["severity"] == "NORMAL"
