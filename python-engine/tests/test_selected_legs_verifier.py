"""[WORKFLOW-B.3 2026-09-17] Tests for the selected-legs
persistence verifier.

Per Workstream B in NEXT_AGENT_PLAN.md:
> Preserve all selected legs through the advice lifecycle
> and management horizon. Verify shared-token accounting,
> terminal registrations, restarts and expiry changes.

These tests pin the verifier:

  - Per-leg status (PASS / WARN / FAIL) based on
    chain snapshot + quote availability.
  - Shared-token accounting (no duplicate tokens
    across legs).
  - Aggregate ``overall_status`` is the worst case.
  - Decision at the boundary of the quote window is
    treated as "in window".
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from zoneinfo import ZoneInfo

PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))

from selected_legs_verifier import (  # noqa: E402  -- import path
    LegStatus,
    SelectedLegFinding,
    SelectedLegsReport,
    verify_selected_legs,
)


IST = ZoneInfo("Asia/Kolkata")


def _decision_at() -> datetime:
    return datetime(2026, 9, 14, 9, 45, tzinfo=IST)


def _qual(legs: list[dict], decision_at: datetime | None = None) -> dict:
    return {
        "decision_at": (decision_at or _decision_at()).isoformat(),
        "candidate": {
            "thesis_id": "t1",
            "selected_legs": legs,
        },
    }


# -- 1. Input validation --------------------------------------


def test_qualification_without_candidate_dict_raises():
    with pytest.raises(ValueError, match="candidate"):
        verify_selected_legs(
            qualification={},
            chain_snapshots_by_token={},
            quotes_by_token={},
        )


def test_qualification_without_selected_legs_raises():
    with pytest.raises(ValueError, match="selected_legs"):
        verify_selected_legs(
            qualification={"candidate": {},
                            "decision_at": _decision_at().isoformat()},
            chain_snapshots_by_token={},
            quotes_by_token={},
        )


def test_qualification_without_decision_at_raises():
    with pytest.raises(ValueError, match="decision_at"):
        verify_selected_legs(
            qualification={"candidate": {"selected_legs": []},
                            "decision_at": None},
            chain_snapshots_by_token={},
            quotes_by_token={},
            decision_at=None,
        )


def test_decision_at_kwarg_overrides_qualification():
    decision_at = _decision_at()
    qual = _qual([], decision_at=None)
    qual.pop("decision_at")  # remove to ensure kwarg is used.
    qual["decision_at"] = None  # explicit None to fall back.
    report = verify_selected_legs(
        qualification=qual,
        chain_snapshots_by_token={},
        quotes_by_token={},
        decision_at=decision_at,
    )
    assert report.decision_at == decision_at.isoformat()


# -- 2. Per-leg status ----------------------------------------


def test_leg_with_chain_and_quote_passes():
    decision_at = _decision_at()
    leg = {"token": 100, "symbol": "X", "expiry": "2026-09-26"}
    report = verify_selected_legs(
        qualification=_qual([leg]),
        chain_snapshots_by_token={100: [decision_at]},
        quotes_by_token={100: [decision_at]},
    )
    assert report.findings[0].status == LegStatus.PASS
    assert report.findings[0].has_chain_snapshot
    assert report.findings[0].has_quote_at_decision


def test_leg_with_chain_but_no_quote_warns():
    decision_at = _decision_at()
    leg = {"token": 100, "symbol": "X", "expiry": "2026-09-26"}
    report = verify_selected_legs(
        qualification=_qual([leg]),
        chain_snapshots_by_token={100: [decision_at]},
        quotes_by_token={},  # no quote for this token.
    )
    assert report.findings[0].status == LegStatus.WARN


def test_leg_without_chain_fails():
    leg = {"token": 100, "symbol": "X", "expiry": "2026-09-26"}
    report = verify_selected_legs(
        qualification=_qual([leg]),
        chain_snapshots_by_token={},  # no chain snapshot
        quotes_by_token={100: [_decision_at()]},
    )
    assert report.findings[0].status == LegStatus.FAIL
    assert "no chain snapshot" in report.findings[0].notes[0]


def test_leg_with_zero_token_fails():
    """[WORKFLOW-B.3 2026-09-17] A leg without a positive
    token is invalid -- FAIL."""
    leg = {"token": 0, "symbol": "X", "expiry": "2026-09-26"}
    report = verify_selected_legs(
        qualification=_qual([leg]),
        chain_snapshots_by_token={},
        quotes_by_token={},
    )
    assert report.findings[0].status == LegStatus.FAIL


def test_leg_outside_quote_window_warns():
    """[WORKFLOW-B.3 2026-09-17] When chain is present but
    no quote in the window, the leg is WARN (the plan:
    'preserve all selected legs'). FAIL would be too strict."""
    decision_at = _decision_at()
    leg = {"token": 100, "symbol": "X", "expiry": "2026-09-26"}
    report = verify_selected_legs(
        qualification=_qual([leg]),
        chain_snapshots_by_token={100: [decision_at]},
        # Quote is 1 hour before decision (outside 5-min window).
        quotes_by_token={100: [decision_at - timedelta(hours=1)]},
    )
    assert report.findings[0].status == LegStatus.WARN


def test_leg_at_quote_window_boundary_passes():
    """[WORKFLOW-B.3 2026-09-17] Quote exactly at the
    window boundary should count (inclusive)."""
    decision_at = _decision_at()
    leg = {"token": 100, "symbol": "X", "expiry": "2026-09-26"}
    report = verify_selected_legs(
        qualification=_qual([leg]),
        chain_snapshots_by_token={100: [decision_at]},
        quotes_by_token={100: [decision_at - timedelta(minutes=5)]},
        quote_window=timedelta(minutes=5),
    )
    assert report.findings[0].status == LegStatus.PASS


# -- 3. Shared-token accounting ------------------------------


def test_duplicate_token_across_legs_is_warn():
    """[WORKFLOW-B.3 2026-09-17] The same instrument_token
    on multiple legs is a hint of an upstream bug -- WARN."""
    decision_at = _decision_at()
    legs = [
        {"token": 100, "symbol": "X", "expiry": "2026-09-26"},
        {"token": 100, "symbol": "Y", "expiry": "2026-09-26"},
    ]
    report = verify_selected_legs(
        qualification=_qual(legs),
        chain_snapshots_by_token={100: [decision_at]},
        quotes_by_token={100: [decision_at]},
    )
    assert report.findings[0].shared_token_consistent is False
    assert report.findings[1].shared_token_consistent is False
    # Each leg is WARN (chain + quote OK, but token shared).
    assert report.findings[0].status == LegStatus.WARN
    assert report.findings[1].status == LegStatus.WARN


def test_unique_tokens_across_legs_are_consistent():
    decision_at = _decision_at()
    legs = [
        {"token": 100, "symbol": "A", "expiry": "2026-09-26"},
        {"token": 200, "symbol": "B", "expiry": "2026-09-26"},
    ]
    report = verify_selected_legs(
        qualification=_qual(legs),
        chain_snapshots_by_token={100: [decision_at], 200: [decision_at]},
        quotes_by_token={100: [decision_at], 200: [decision_at]},
    )
    assert report.findings[0].shared_token_consistent is True
    assert report.findings[1].shared_token_consistent is True
    assert all(f.status == LegStatus.PASS for f in report.findings)


# -- 4. Aggregate --------------------------------------------


def test_empty_legs_returns_warn_aggregate():
    report = verify_selected_legs(
        qualification=_qual([]),
        chain_snapshots_by_token={},
        quotes_by_token={},
    )
    assert report.findings == ()
    assert report.overall_status == LegStatus.WARN


def test_overall_status_is_worst_case():
    """[WORKFLOW-B.3 2026-09-17] overall_status = worst case
    across legs."""
    decision_at = _decision_at()
    legs = [
        {"token": 100, "symbol": "X", "expiry": "2026-09-26"},  # PASS
        {"token": 200, "symbol": "Y", "expiry": "2026-09-26"},  # WARN (no quote)
        {"token": 300, "symbol": "Z", "expiry": "2026-09-26"},  # FAIL (no chain)
    ]
    report = verify_selected_legs(
        qualification=_qual(legs),
        chain_snapshots_by_token={
            100: [decision_at],
            200: [decision_at],
            # 300: no chain
        },
        quotes_by_token={
            100: [decision_at],
            # 200: no quote
            # 300: no quote either
        },
    )
    assert report.pass_count == 1
    assert report.warn_count == 1
    assert report.fail_count == 1
    assert report.overall_status == LegStatus.FAIL  # worst case.


def test_count_methods_aggregate_correctly():
    decision_at = _decision_at()
    legs = [
        {"token": 100, "symbol": "A", "expiry": "2026-09-26"},
        {"token": 200, "symbol": "B", "expiry": "2026-09-26"},
        {"token": 300, "symbol": "C", "expiry": "2026-09-26"},
    ]
    report = verify_selected_legs(
        qualification=_qual(legs),
        chain_snapshots_by_token={t: [decision_at] for t in (100, 200, 300)},
        # Only 100 and 200 have quotes; 300 has chain only.
        quotes_by_token={100: [decision_at], 200: [decision_at]},
    )
    assert report.pass_count == 2
    assert report.warn_count == 1
    assert report.fail_count == 0


# -- 5. SelectedLegFinding dataclass --------------------------


def test_finding_to_dict_includes_required_fields():
    decision_at = _decision_at()
    leg = {"token": 100, "symbol": "X", "expiry": "2026-09-26"}
    report = verify_selected_legs(
        qualification=_qual([leg]),
        chain_snapshots_by_token={100: [decision_at]},
        quotes_by_token={100: [decision_at]},
    )
    f = report.findings[0]
    d = f.to_dict()
    expected = {
        "leg_index", "leg_token", "leg_symbol", "leg_expiry",
        "has_chain_snapshot", "has_quote_at_decision",
        "chain_snapshot_count", "shared_token_consistent",
        "status", "notes",
    }
    assert set(d.keys()) == expected


def test_finding_preserves_token_and_symbol():
    decision_at = _decision_at()
    leg = {"token": 12345, "symbol": "NIFTY24100CE", "expiry": "2026-09-26"}
    report = verify_selected_legs(
        qualification=_qual([leg]),
        chain_snapshots_by_token={12345: [decision_at]},
        quotes_by_token={12345: [decision_at]},
    )
    f = report.findings[0]
    assert f.leg_token == 12345
    assert f.leg_symbol == "NIFTY24100CE"
    assert f.leg_expiry == "2026-09-26"


# -- 6. SelectedLegsReport dataclass -------------------------


def test_report_to_dict_includes_all_fields():
    decision_at = _decision_at()
    leg = {"token": 100, "symbol": "X", "expiry": "2026-09-26"}
    report = verify_selected_legs(
        qualification=_qual([leg]),
        chain_snapshots_by_token={100: [decision_at]},
        quotes_by_token={100: [decision_at]},
        qualification_path="qual-1.json",
    )
    d = report.to_dict()
    expected = {
        "qualification_path", "decision_at", "overall_status",
        "pass_count", "warn_count", "fail_count", "findings",
    }
    assert set(d.keys()) == expected
    assert d["qualification_path"] == "qual-1.json"


def test_qualification_path_preserved():
    report = verify_selected_legs(
        qualification=_qual([{"token": 100, "symbol": "X",
                                "expiry": "2026-09-26"}]),
        chain_snapshots_by_token={},
        quotes_by_token={},
        qualification_path="/path/to/qual.json",
    )
    assert report.qualification_path == "/path/to/qual.json"
