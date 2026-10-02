"""S7b timing hypotheses are frozen research, never admission authority."""
from datetime import datetime, timedelta

import pytest
from zoneinfo import ZoneInfo

from momentum_entry_timing_research import (
    CONTINUATION, PULLBACK, TimingCandidate, build_timing_report,
    evaluate_entry_timing, freeze_timing_manifest,
)
from momentum_exit_study import DEADLINE_EXACT, ExitStudyError, Quote


IST = ZoneInfo("Asia/Kolkata")
SOURCE = "sha256:" + "a" * 64


def _candidate(*, candidate_id="a", thesis="thesis-a", state="state-a", quotes=None, reentry_of=None):
    start = datetime(2026, 10, 2, 10, 0, tzinfo=IST)
    quotes = quotes if quotes is not None else tuple(
        Quote(start + timedelta(minutes=n), 100.0 if n < 2 else 104.0 if n == 2 else 103.0)
        for n in range(0, 316)
    )
    return TimingCandidate(candidate_id, "ACME", thesis, state, start, start + timedelta(minutes=1),
                           101.0, 99.0, 102.0, 98.0, 104.0, 10, SOURCE, quotes, reentry_of)


def test_completed_bar_continuation_enters_only_at_declared_completed_bar():
    result = evaluate_entry_timing([_candidate()], policy=CONTINUATION, max_gap_seconds=60,
                                   deadline_policy=DEADLINE_EXACT)[0]
    assert result["state"] == "COMPLETE"
    assert result["entry"]["at"].endswith("10:01:00+05:30")
    assert result["entry"]["price"] == 101.0


def test_pullback_waits_for_zone_and_never_chases():
    start = datetime(2026, 10, 2, 10, 0, tzinfo=IST)
    quotes = tuple(Quote(start + timedelta(minutes=n), 103.0 if n < 3 else 101.0)
                   for n in range(0, 316))
    result = evaluate_entry_timing([_candidate(quotes=quotes)], policy=PULLBACK, max_gap_seconds=60,
                                   deadline_policy=DEADLINE_EXACT)[0]
    assert result["state"] == "COMPLETE"
    assert result["entry"]["at"].endswith("10:03:00+05:30")
    no_chase = evaluate_entry_timing([_candidate(quotes=tuple(
        Quote(start + timedelta(minutes=n), 103.0) for n in range(316)))], policy=PULLBACK,
        max_gap_seconds=60, deadline_policy=DEADLINE_EXACT)[0]
    assert no_chase["state"] == "NO_CHASE_CAP_EXCEEDED"


def test_reentry_requires_new_state_and_duplicate_state_is_not_replayed():
    with pytest.raises(ExitStudyError, match="new thesis or state"):
        evaluate_entry_timing([_candidate(reentry_of=("thesis-a", "state-a"))], policy=CONTINUATION,
                              max_gap_seconds=60, deadline_policy=DEADLINE_EXACT)
    rows = evaluate_entry_timing([_candidate(), _candidate(candidate_id="b")], policy=CONTINUATION,
                                 max_gap_seconds=60, deadline_policy=DEADLINE_EXACT)
    assert [row["state"] for row in rows] == ["COMPLETE", "REENTRY_DUPLICATE_STATE"]
    allowed = evaluate_entry_timing([_candidate(), _candidate(candidate_id="c", state="state-b",
                                                               reentry_of=("thesis-a", "state-a"))],
                                     policy=CONTINUATION, max_gap_seconds=60, deadline_policy=DEADLINE_EXACT)
    assert [row["state"] for row in allowed] == ["COMPLETE", "COMPLETE"]


def test_manifest_freezes_terms_and_separates_holdout():
    frozen = datetime(2026, 10, 1, tzinfo=IST)
    manifest = freeze_timing_manifest(experiment_id="s7b", max_gap_seconds=60,
                                      deadline_policy=DEADLINE_EXACT, frozen_at=frozen)
    report = build_timing_report([_candidate()], manifest)
    assert len(report["holdout"][CONTINUATION]) == 1
    assert report["qualification"] == "NOT_ASSESSED"
    manifest["source_fingerprint"] = SOURCE
    with pytest.raises(ExitStudyError, match="FROZEN_POLICY_MISMATCH"):
        build_timing_report([_candidate()], manifest)
