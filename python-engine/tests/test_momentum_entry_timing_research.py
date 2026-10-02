"""S7b timing hypotheses are frozen research, never admission authority."""
from datetime import datetime, timedelta, timezone

import pytest
from zoneinfo import ZoneInfo

from momentum_entry_timing_research import (
    CONTINUATION, PULLBACK, TimingCandidate, build_timing_report,
    evaluate_entry_timing, freeze_timing_manifest,
)
from momentum_exit_study import DEADLINE_EXACT, ExitStudyError, Quote
from config import settings


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


@pytest.mark.parametrize("field", ["MOMENTUM_TIME_STOP_MIN", "ZERODHA_BROKERAGE_MAX"])
def test_frozen_timing_rejects_runtime_settings_or_fee_drift(monkeypatch, field):
    manifest = freeze_timing_manifest(experiment_id="drift", max_gap_seconds=60,
                                      deadline_policy=DEADLINE_EXACT,
                                      frozen_at=datetime(2026, 10, 1, tzinfo=IST))
    monkeypatch.setattr(settings, field, getattr(settings, field) + 1)
    with pytest.raises(ExitStudyError, match="FROZEN_POLICY_MISMATCH"):
        build_timing_report([_candidate()], manifest)


def test_timing_freeze_rejects_unknown_deadline_policy():
    with pytest.raises(ExitStudyError, match="deadline"):
        freeze_timing_manifest(experiment_id="invalid", max_gap_seconds=60,
                               deadline_policy="invented",
                               frozen_at=datetime(2026, 10, 1, tzinfo=IST))


# [S7b R5 2026-10-02] Candidates built only from immutable admission evidence.
def _evidence_db(tmp_path, price_at):
    import asyncio as _asyncio
    from datetime import timedelta as _td, timezone as _tz
    from momentum_paper import open_momentum_paper_positions, record_momentum_paper_path_observations
    from tests.test_momentum_paper import _db, _envelope
    db = _db(tmp_path)
    entry_at = datetime(2026, 9, 25, 9, 0, tzinfo=_tz.utc)   # 14:30 IST
    signal = {"ticker": "ACME", "close": 100.0, "stop_loss": 98.0, "target_1": 106.0, "target_2": 106.0,
              "regime": "REGIME_1_NORMAL", "vwap": 99.0}
    assert _asyncio.run(open_momentum_paper_positions(db, [signal], entry_at)) == ["ACME"]
    observations, current = [], entry_at + _td(seconds=30)
    while current <= datetime(2026, 9, 25, 9, 45, 30, tzinfo=_tz.utc):
        minute = (current - entry_at).total_seconds() / 60
        price = round(price_at(minute), 4)
        observations.append({"ticker": "ACME", "ltp": price, "provider_observed_at": current.isoformat(),
                             "receipt_at": current.isoformat(), "source_packet": _envelope("ACME", price, current)})
        current += _td(seconds=60)
    _asyncio.run(record_momentum_paper_path_observations(db, observations))
    return db


def test_adapter_builds_candidates_with_the_frozen_zone_rule(tmp_path):
    from momentum_entry_timing_research import ZONE_RULE, timing_candidates_from_db
    built = timing_candidates_from_db(_evidence_db(tmp_path, lambda m: 100.2))
    assert built["unavailable"] == [] and len(built["candidates"]) == 1
    candidate = built["candidates"][0]
    # VWAP 99 is above stop + 0.25R (98.5), so it is the floor; cap = close + 0.25R.
    assert (candidate.pullback_floor, candidate.no_chase_cap) == (99.0, 100.5)
    assert candidate.thesis_id and candidate.state_id.startswith("sha256:")
    assert (candidate.pullback_deadline - candidate.continuation_at).total_seconds() == ZONE_RULE["pullback_max_wait_seconds"]


def test_pullback_after_the_window_expires_instead_of_entering(tmp_path):
    from momentum_entry_timing_research import PULLBACK, evaluate_entry_timing, timing_candidates_from_db
    from momentum_exit_study import DEADLINE_FIRST_WITHIN_GAP
    built = timing_candidates_from_db(_evidence_db(tmp_path, lambda m: 101.0 if m < 40 else 99.5))
    rows = evaluate_entry_timing(built["candidates"], policy=PULLBACK, max_gap_seconds=300,
                                 deadline_policy=DEADLINE_FIRST_WITHIN_GAP)
    assert rows[0]["state"] == "PULLBACK_WINDOW_EXPIRED"


def test_missing_evidence_is_unavailable_and_zone_rule_drift_is_refused(tmp_path, monkeypatch):
    import momentum_entry_timing_research as timing
    from momentum_exit_study import DEADLINE_FIRST_WITHIN_GAP, ExitStudyError
    from tests.test_momentum_paper import _db
    db = _db(tmp_path)
    assert timing.timing_candidates_from_db(db)["candidates"] == []
    manifest = timing.freeze_timing_manifest(experiment_id="r5", max_gap_seconds=300,
                                             deadline_policy=DEADLINE_FIRST_WITHIN_GAP,
                                             frozen_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert manifest["zone_rule"] == timing.ZONE_RULE
    monkeypatch.setattr(timing, "ZONE_RULE", {**timing.ZONE_RULE, "no_chase_cap_r": 1.0})
    with pytest.raises(ExitStudyError, match="zone_rule"):
        timing.build_timing_report([], manifest)
