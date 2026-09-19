"""[WORKFLOW-G 2026-09-13] Range-reversion entry profile acceptance.

The RANGE_REVERSION_V1 entry profile closes gap #1 from
``docs/2026-09-13-workflow-g-state-of-codebase-audit.md`` §6.

Pre-conditions at audit time:
  - ``proactive_intelligence.build_shadow_proposals`` already emits a
    ``range_reversion_v1`` proposal at line 172 with reason
    ``RANGE_STABILIZATION_RECLAIM``.
  - ``simulate_shadow_research_trial`` (line 382) raises
    ``ValueError("unsupported shadow research profile")`` for any
    ``entry_profile_id`` not in ``_SHADOW_ENTRY_PROFILES``.
  - Hence the proposal was constructible but never simulatable.

This file proves:
  1. The constant is shipped.
  2. The proposal flow is end-to-end (build emits, allocator accepts).
  3. The dispatcher's enum-check no longer trips on the new profile.

The original constant-only slice deliberately avoided numerical semantics.
G.3 later added a dedicated dispatcher and G.7 makes that dispatcher causal;
the detailed timing/invalidation contract is pinned in
``test_range_reversion_dispatcher.py``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from proactive_intelligence import (
    _SHADOW_ENTRY_PROFILES,
    ShadowProposal,
    allocate_shadow_proposals,
    build_shadow_proposals,
    simulate_shadow_research_trial,
)


def _range_stabilization_bars(end: datetime) -> list[dict]:
    """Build 21 15-minute bars whose last two trigger the range branch.

    Mirrors ``proactive_demo._range_bars``: 21 bars oscillating \u00b10.2 around
    100 with the second-to-last close at 98 (triggers the
    ``closes[-2] < mean * .985`` branch) and the last close at 99
    (``last > closes[-2]``). Range width is well under 6% of mean, so
    the ``max(window)-min(window) <= mean * .06`` branch also fires.
    """
    bars: list[dict] = []
    for index in range(21):
        close = 100 + (index % 3 - 1) * 0.2
        bars.append({
            "timestamp": (end - timedelta(minutes=(20 - index) * 15)).isoformat(),
            "open": close - 0.1,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": 100,
        })
    bars[-2].update({"open": 98.2, "high": 98.4, "low": 97.8, "close": 98})
    bars[-1].update({"open": 98.6, "high": 99.2, "low": 98.4, "close": 99})
    return bars


def test_range_reversion_is_in_shipped_entry_profiles() -> None:
    """The constant change is shipped."""
    assert "RANGE_REVERSION_V1" in _SHADOW_ENTRY_PROFILES, (
        "_SHADOW_ENTRY_PROFILES must contain 'RANGE_REVERSION_V1' "
        "after the G audit gap #1 closure; check "
        "python-engine/proactive_intelligence.py:28-31."
    )


def test_build_shadow_proposals_emits_range_reversion_proposal() -> None:
    """The proposal builder wires the new profile."""
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    bars = _range_stabilization_bars(now)
    proposals = build_shadow_proposals("NSE:RANGE", bars, now=now)
    range_proposals = [
        proposal for proposal in proposals
        if proposal.policy_id == "range_reversion_v1"
    ]
    assert len(range_proposals) >= 1, (
        "build_shadow_proposals must emit at least one range_reversion_v1 "
        "proposal from the deterministic range-shape fixture."
    )
    proposal: ShadowProposal = range_proposals[0]
    assert proposal.instrument == "NSE:RANGE"
    assert proposal.stop < proposal.entry < proposal.target
    assert proposal.reason == "RANGE_STABILIZATION_RECLAIM"


def test_allocator_accepts_range_reversion_proposal() -> None:
    """Capital allocator must not reject solely because policy_id is range_*."""
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    bars = _range_stabilization_bars(now)
    proposals = build_shadow_proposals("NSE:RANGE", bars, now=now)
    range_proposals = [
        proposal for proposal in proposals
        if proposal.policy_id == "range_reversion_v1"
    ]
    assert range_proposals, "fixture must emit a range proposal"
    selected, reasons = allocate_shadow_proposals(
        range_proposals, capital=8000.0
    )
    assert selected, (
        f"allocator rejected every range proposal; reasons={reasons}"
    )


def test_simulator_dispatcher_accepts_range_reversion_v1() -> None:
    """The dispatcher's enum check no longer fires on the new profile.

    This is the gap that the constant change closes. Before the change
    this test raised ``ValueError('unsupported shadow research profile')``.
    After the change it returns a bounded ShadowSimulation outcome. Detailed
    causal semantics are tested separately.
    """
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    bars = _range_stabilization_bars(now)
    proposals = build_shadow_proposals("NSE:RANGE", bars, now=now)
    range_proposals = [
        proposal for proposal in proposals
        if proposal.policy_id == "range_reversion_v1"
    ]
    assert range_proposals, "fixture must emit a range proposal"

    # Minimal future-bars fixture of 3 bars so the simulator has
    # something to walk; we are not asserting a fill, only that the
    # dispatcher's enum-check passes.
    future = [
        {"timestamp": (now + timedelta(minutes=15)).isoformat(),
         "open": 99.0, "high": 99.4, "low": 98.7, "close": 99.1, "volume": 100},
        {"timestamp": (now + timedelta(minutes=30)).isoformat(),
         "open": 99.1, "high": 99.5, "low": 98.8, "close": 99.3, "volume": 100},
        {"timestamp": (now + timedelta(minutes=45)).isoformat(),
         "open": 99.3, "high": 99.6, "low": 98.9, "close": 99.4, "volume": 100},
    ]
    simulation = simulate_shadow_research_trial(
        range_proposals[0], future, cash=8000.0,
        entry_profile_id="RANGE_REVERSION_V1",
        exit_profile_id="STOP_TARGET_TIME_V1",
    )
    assert simulation is not None
    assert hasattr(simulation, "status")
    # The set below is every ``status`` value ShadowSimulation can carry today,
    # observed across all entry profiles; ``OPEN`` is included because the
    # 3-bar future fixture is short enough that the simulator legitimately
    # reports ``DATA_END_OPEN_POSITION``.
    assert simulation.status in {
        "FILLED", "NO_FILL", "INVALID", "OPEN", "DEFERRED", "REJECTED",
    }, f"unexpected simulation status: {simulation.status!r}"


def test_unknown_profile_still_rejected_by_dispatcher() -> None:
    """Negative control: a profile id that is not registered still raises.

    Proves we did not accidentally widen the dispatcher. Pre- and
    post-change behaviour is identical for unknown ids; only
    ``RANGE_REVERSION_V1`` moved from 'rejected' to 'accepted'.
    """
    now = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    bars = _range_stabilization_bars(now)
    proposals = build_shadow_proposals("NSE:RANGE", bars, now=now)
    range_proposals = [
        proposal for proposal in proposals
        if proposal.policy_id == "range_reversion_v1"
    ]
    assert range_proposals, "fixture must emit a range proposal"
    future = [{
        "timestamp": (now + timedelta(minutes=15)).isoformat(),
        "open": 99.0, "high": 99.4, "low": 98.7, "close": 99.1, "volume": 100,
    }]
    with pytest.raises(ValueError, match="unsupported shadow research profile"):
        simulate_shadow_research_trial(
            range_proposals[0], future, cash=8000.0,
            entry_profile_id="NOT_A_REAL_PROFILE_V0",
            exit_profile_id="STOP_TARGET_TIME_V1",
        )
