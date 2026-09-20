"""[WORKFLOW-A.4 2026-09-17] Tests for the cross-boundary
safety net.

Per Workstream A in NEXT_AGENT_PLAN.md:
> Crossing a five-minute boundary, entry cutoff or session
> boundary during a fetch cannot create a backdated idea.

The base ``partner_decision_clock.crossed_entry_boundary``
covers entry cutoff and session boundary but only one at
a time. These tests pin ``crossed_boundaries`` which:

  - Returns ALL boundary crossings (not just one).
  - Covers 5-minute bar boundary in addition to entry
    cutoff and session boundary.
  - Lets operators configure thresholds.
"""
from __future__ import annotations

import sys
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest
from zoneinfo import ZoneInfo

PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))

from boundary_safety import (  # noqa: E402  -- import path
    BoundaryCrossing,
    BoundaryKind,
    FIVE_MINUTE_BOUNDARY_MS,
    crossed_boundaries,
    has_crossed_boundary,
)
from decision_clocks_extensions import (  # noqa: E402  -- import path
    build_clock_for_test,
)


IST = ZoneInfo("Asia/Kolkata")


def _tick_at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 9, 14, hour, minute, second, tzinfo=IST)


# -- 1. Five-minute bar boundary -------------------------------


def test_bar_boundary_crossed_when_fetch_exceeds_five_minutes():
    tick = _tick_at(9, 30)
    clock = build_clock_for_test(
        tick_started_at=tick,
        public_received_after_ms=200,
        chain_received_after_ms=300,
        candidate_constructed_after_ms=600_000,  # 10 minutes
    )
    crossings = crossed_boundaries(clock)
    bar = [c for c in crossings if c.kind == BoundaryKind.BAR_5MIN]
    assert len(bar) == 1
    assert "5-minute bar boundary crossed" in bar[0].message


def test_bar_boundary_not_crossed_when_fetch_under_five_minutes():
    tick = _tick_at(9, 30)
    clock = build_clock_for_test(tick_started_at=tick)  # 1 second fetch
    crossings = crossed_boundaries(clock)
    bar = [c for c in crossings if c.kind == BoundaryKind.BAR_5MIN]
    assert bar == []


def test_bar_boundary_threshold_is_configurable():
    """[WORKFLOW-A.4 2026-09-17] Operators can tune the bar
    boundary threshold for non-5-minute setups."""
    tick = _tick_at(9, 30)
    clock = build_clock_for_test(
        tick_started_at=tick,
        public_received_after_ms=200,
        chain_received_after_ms=300,
        candidate_constructed_after_ms=60_000,  # 1 minute fetch
    )
    # With a 30-second threshold, 1-minute fetch crosses.
    crossings = crossed_boundaries(clock, bar_boundary_ms=30_000)
    assert any(c.kind == BoundaryKind.BAR_5MIN for c in crossings)
    # With the default 5-minute threshold, 1-minute fetch doesn't.
    crossings = crossed_boundaries(clock, bar_boundary_ms=300_000)
    assert not any(c.kind == BoundaryKind.BAR_5MIN for c in crossings)


def test_bar_boundary_constant_is_5_minutes():
    """[WORKFLOW-A.4 2026-09-17] The plan says 'five-minute
    boundary' -- constant should be exactly 5 minutes."""
    assert FIVE_MINUTE_BOUNDARY_MS == 5 * 60 * 1000


# -- 2. Entry cutoff crossing ---------------------------------


def test_entry_cutoff_crossed_after_minutes_into_day():
    tick = _tick_at(14, 50)
    clock = build_clock_for_test(tick_started_at=tick)
    crossings = crossed_boundaries(clock, entry_cutoff_minute=14*60 + 45)
    entry = [c for c in crossings if c.kind == BoundaryKind.ENTRY_CUTOFF]
    assert len(entry) == 1
    assert "entry cutoff crossed" in entry[0].message


def test_entry_cutoff_not_crossed_before_minutes_into_day():
    tick = _tick_at(14, 30)
    clock = build_clock_for_test(tick_started_at=tick)
    crossings = crossed_boundaries(clock, entry_cutoff_minute=14*60 + 45)
    entry = [c for c in crossings if c.kind == BoundaryKind.ENTRY_CUTOFF]
    assert entry == []


def test_entry_cutoff_skipped_when_minute_is_none():
    tick = _tick_at(14, 50)
    clock = build_clock_for_test(tick_started_at=tick)
    crossings = crossed_boundaries(clock, entry_cutoff_minute=None)
    entry = [c for c in crossings if c.kind == BoundaryKind.ENTRY_CUTOFF]
    assert entry == []


# -- 3. Session boundary -------------------------------------


def test_session_boundary_crossed_when_fetch_spans_midnight():
    """[WORKFLOW-A.4 2026-09-17] The fetch started on one
    calendar day and the candidate was constructed on the
    next."""
    tick = datetime(2026, 9, 13, 23, 59, 30, tzinfo=IST)
    clock = build_clock_for_test(
        tick_started_at=tick,
        public_received_after_ms=200,
        chain_received_after_ms=300,
        candidate_constructed_after_ms=60_000,
    )
    crossings = crossed_boundaries(clock, session_open=time(9, 15))
    sess = [c for c in crossings if c.kind == BoundaryKind.SESSION]
    assert len(sess) == 1
    assert "session boundary crossed" in sess[0].message


def test_session_boundary_not_crossed_when_same_day():
    tick = _tick_at(14, 30)
    clock = build_clock_for_test(tick_started_at=tick)
    crossings = crossed_boundaries(clock, session_open=time(9, 15))
    sess = [c for c in crossings if c.kind == BoundaryKind.SESSION]
    assert sess == []


def test_session_boundary_skipped_when_session_open_is_none():
    tick = datetime(2026, 9, 13, 23, 59, 30, tzinfo=IST)
    clock = build_clock_for_test(
        tick_started_at=tick,
        public_received_after_ms=200,
        candidate_constructed_after_ms=60_000,
    )
    crossings = crossed_boundaries(clock, session_open=None)
    sess = [c for c in crossings if c.kind == BoundaryKind.SESSION]
    assert sess == []


# -- 4. Aggregate behavior -----------------------------------


def test_no_crossings_for_clean_clock():
    tick = _tick_at(10, 0)
    clock = build_clock_for_test(tick_started_at=tick)
    crossings = crossed_boundaries(
        clock,
        entry_cutoff_minute=14*60 + 45,
        session_open=time(9, 15),
    )
    assert crossings == []


def test_returns_all_three_crossings_at_once():
    """[WORKFLOW-A.4 2026-09-17] Unlike the base
    ``crossed_entry_boundary`` which returns a single
    string, ``crossed_boundaries`` returns ALL violations."""
    tick = _tick_at(14, 30)
    clock = build_clock_for_test(
        tick_started_at=tick,
        public_received_after_ms=200,
        chain_received_after_ms=300,
        candidate_constructed_after_ms=600_000,
    )
    # The fetch spans 10 minutes (crosses 5-min bar) and
    # ends at 14:40 (past 14:30 entry cutoff at 14:35).
    # We don't cross session boundary (same day).
    crossings = crossed_boundaries(
        clock,
        entry_cutoff_minute=14*60 + 35,
    )
    kinds = {c.kind for c in crossings}
    assert BoundaryKind.BAR_5MIN in kinds
    assert BoundaryKind.ENTRY_CUTOFF in kinds


def test_returns_all_three_crossings_when_session_also_crossed():
    """[WORKFLOW-A.4 2026-09-17] Cross all three boundaries
    in one fetch: 5-min bar, entry cutoff, AND session."""
    tick = datetime(2026, 9, 13, 23, 55, tzinfo=IST)
    clock = build_clock_for_test(
        tick_started_at=tick,
        public_received_after_ms=200,
        chain_received_after_ms=300,
        candidate_constructed_after_ms=10 * 60_000,  # 10 minutes later = next day
    )
    # entry_cutoff at 0 minutes (00:00) -- candidate at
    # 00:05 next day is past it.
    crossings = crossed_boundaries(
        clock,
        entry_cutoff_minute=0,
        session_open=time(9, 15),
    )
    kinds = {c.kind for c in crossings}
    assert BoundaryKind.BAR_5MIN in kinds
    assert BoundaryKind.ENTRY_CUTOFF in kinds
    assert BoundaryKind.SESSION in kinds


def test_has_crossed_boundary_true_when_any_crossing():
    tick = _tick_at(14, 50)
    clock = build_clock_for_test(tick_started_at=tick)
    assert has_crossed_boundary(
        clock, entry_cutoff_minute=14*60 + 45,
    ) is True


def test_has_crossed_boundary_false_for_clean_clock():
    tick = _tick_at(10, 0)
    clock = build_clock_for_test(tick_started_at=tick)
    assert has_crossed_boundary(
        clock, entry_cutoff_minute=14*60 + 45,
    ) is False


# -- 5. BoundaryCrossing dataclass ----------------------------


def test_boundary_crossing_required_fields():
    """[WORKFLOW-A.4 2026-09-17] Each crossing record must
    carry the boundary kind, a human-readable message, and
    (when available) the timestamp at which the crossing
    occurred."""
    c = BoundaryCrossing(
        kind=BoundaryKind.BAR_5MIN,
        message="boundary crossed",
        crossed_at=datetime(2026, 9, 14, 10, 0, tzinfo=IST),
    )
    assert c.kind == BoundaryKind.BAR_5MIN
    assert "boundary crossed" in c.message
    assert c.crossed_at is not None


def test_boundary_crossing_crossed_at_is_optional():
    c = BoundaryCrossing(
        kind=BoundaryKind.SESSION,
        message="boundary crossed",
    )
    assert c.crossed_at is None


# -- 6. BoundaryKind enum exit codes --------------------------


def test_boundary_kind_exit_code_is_two():
    """[WORKFLOW-A.4 2026-09-17] Any boundary crossing is a
    hard rejection for the candidate-construction path.
    Use exit 2 (BLOCKER) so the dispatch pipeline can
    short-circuit cleanly."""
    for kind in BoundaryKind:
        assert kind.exit_code() == 2
