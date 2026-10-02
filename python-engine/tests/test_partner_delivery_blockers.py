"""S5c: read-only per-candidate partner delivery-blocker diagnostic."""
from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest

import research_cli
from partner_collection_attempts import PartnerCollectionAttemptStore
from partner_delivery_blockers import build_delivery_blocker_report, candidate_blockers
from partner_manual_advisory import PartnerAdvisoryProfile, persist_candidate, save_partner_profile
from tests.test_partner_manual_advisory import NOW, _candidate


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _attempt(store, attempt_id, *, underlying, terminal_state, terminal_reason):
    with store._connect() as db:
        db.execute(
            "INSERT INTO partner_collection_attempts(attempt_id, run_id, account_id, underlying, clock_policy, "
            "tick_started_at_utc, evaluation_cutoff_at_utc, expected_at_utc, terminal_state, terminal_reason, "
            "updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (attempt_id, attempt_id, "manual-profile:default", underlying, "fixture",
             "2026-09-07T04:30:00+00:00", "2026-09-07T04:30:00+00:00", "2026-09-07T04:30:00+00:00",
             terminal_state, terminal_reason, "2026-09-07T04:30:05+00:00"),
        )


async def _fixture_db(tmp_path):
    db_path = tmp_path / "engine.db"
    profile = PartnerAdvisoryProfile(holding_period="INTRADAY")
    await save_partner_profile(str(db_path), profile, now=NOW)
    # A research-only, otherwise valid card queued for delivery: shadow only.
    shadow = await persist_candidate(str(db_path), _candidate("NIFTY"), profile, now=NOW, queue_for_delivery=True)
    # The same economics judged far too late: a validation rejection.
    rejected = await persist_candidate(str(db_path), _candidate("SENSEX"), profile,
                                       now=NOW.replace(hour=10, minute=5), queue_for_delivery=True)
    assert shadow["status"] == "VALIDATED_SHADOW" and rejected["status"] == "REJECTED"
    return db_path


@pytest.mark.asyncio
async def test_every_candidate_has_an_ordered_explained_blocker(tmp_path):
    db_path = await _fixture_db(tmp_path)
    before = _digest(db_path)
    report = build_delivery_blocker_report(db_path=db_path, session_from=date(2026, 9, 7),
                                           session_to=date(2026, 9, 7))
    assert _digest(db_path) == before, "diagnostic must not modify the database"
    assert report["authority_effect"] == "NONE"
    by_index = {row["underlying"]: row for row in report["candidates"]}
    nifty, sensex = by_index["NIFTY"], by_index["SENSEX"]
    assert nifty["delivered"] is False
    assert nifty["blockers"] == ["EVIDENCE:RESEARCH_ONLY", "NO_CURRENT_QUALIFICATION_AT_DECISION",
                                 "DELIVERY:strategy_not_qualified_for_delivery"]
    assert nifty["primary_blocker"] == "EVIDENCE:RESEARCH_ONLY"
    assert sensex["primary_blocker"].startswith("VALIDATION:")
    assert report["totals"]["candidates"] == 2 and report["totals"]["delivered"] == 0
    assert report["qualification_registry"]["rows"] == []
    assert report["attempts_state"] == "UNAVAILABLE:not_supplied"


@pytest.mark.asyncio
async def test_attempt_journal_disagreement_is_reported_as_aggregate(tmp_path):
    db_path = await _fixture_db(tmp_path)
    store = PartnerCollectionAttemptStore(tmp_path / "research")
    _attempt(store, "a1", underlying="SENSEX", terminal_state="CANDIDATE_RECORDED",
             terminal_reason="candidate_validated")
    _attempt(store, "a2", underlying="NIFTY", terminal_state="CANDIDATE_RECORDED",
             terminal_reason="candidate_validated")
    report = build_delivery_blocker_report(db_path=db_path, attempts_path=store.path)
    sensex = report["sessions"]["2026-09-07:SENSEX"]
    assert sensex["ideas_by_status"] == {"REJECTED": 1}
    assert sensex["attempts"]["terminal"] == {"CANDIDATE_RECORDED": 1}
    assert sensex["attempt_idea_disagreement"] is True
    assert report["sessions"]["2026-09-07:NIFTY"]["attempt_idea_disagreement"] is False
    assert report["totals"]["sessions_with_attempt_idea_disagreement"] == 1


def test_missing_databases_are_reported_and_never_created(tmp_path):
    missing = tmp_path / "absent.db"
    report = build_delivery_blocker_report(db_path=missing, attempts_path=tmp_path / "absent-attempts.db")
    assert report["ideas_state"] == "UNAVAILABLE:database_missing"
    assert report["attempts_state"] == "UNAVAILABLE:database_missing"
    assert report["candidates"] == [] and not missing.exists()


@pytest.mark.parametrize("row, primary", [
    ({"status": "DELIVERED_ACKNOWLEDGED", "evidence": "QUALIFIED_FOR_ADVISORY",
      "payload": json.dumps({"validation_reasons": [], "qualification_registry_match": True})}, None),
    ({"status": "SUPERSEDED_MARKET", "evidence": "QUALIFIED_FOR_ADVISORY",
      "payload": json.dumps({"validation_reasons": [], "qualification_registry_match": True})},
     "SUPERSEDED_BY_NEWER_MARKET_VERSION"),
    ({"status": "QUEUED", "evidence": "QUALIFIED_FOR_ADVISORY",
      "payload": json.dumps({"validation_reasons": [], "qualification_registry_match": True})},
     "QUEUED_NOT_DISPATCHED"),
    ({"status": "SOMETHING_NEW", "evidence": "QUALIFIED_FOR_ADVISORY",
      "payload": json.dumps({"qualification_registry_match": True})}, "STATUS:SOMETHING_NEW"),
    ({"status": "VALIDATED_SHADOW", "evidence": "QUALIFIED_FOR_ADVISORY",
      "payload": json.dumps({"qualification_registry_match": True})}, "UNEXPLAINED_NOT_DELIVERED"),
    ({"status": "VALIDATED_SHADOW", "evidence": "RESEARCH_ONLY", "payload": "not-json"}, "MALFORMED_PAYLOAD"),
])
def test_candidate_blocker_classification(row, primary):
    assert candidate_blockers(row)["primary_blocker"] == primary


@pytest.mark.asyncio
async def test_cli_writes_immutable_report_and_refuses_different_overwrite(tmp_path, capsys):
    db_path = await _fixture_db(tmp_path)
    output = tmp_path / "out" / "blockers.json"
    argv = ["partner-delivery-blockers", "--db", str(db_path), "--output", str(output)]
    assert research_cli.main(argv) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["can_send"] is False and summary["authorization_effect"] == "NONE"
    assert summary["candidates"] == 2
    first = output.read_bytes()
    assert research_cli.main(argv) == 0  # byte-identical retry is accepted
    assert output.read_bytes() == first
    narrowed = argv[:-2] + ["--session-from", "2026-09-08", "--output", str(output)]
    assert research_cli.main(narrowed) == 2  # different evidence cannot overwrite
    assert output.read_bytes() == first
