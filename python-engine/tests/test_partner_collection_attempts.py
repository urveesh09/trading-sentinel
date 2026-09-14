from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from partner_collection_attempts import PartnerCollectionAttemptStore
from partner_decision_clock import start_clock


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 9, 14, 9, 46, 50, tzinfo=IST)


def _started(tmp_path, underlying="NIFTY", tick=NOW):
    store = PartnerCollectionAttemptStore(tmp_path)
    clock = start_clock(underlying=underlying, account_id="manual-profile:p1", tick_started_at=tick).with_stage(
        public_requested_at=tick, public_received_at=tick + timedelta(seconds=1),
        public_source_id=f"PUBLIC:{underlying}", chain_requested_at=tick + timedelta(seconds=1),
        chain_received_at=tick + timedelta(seconds=2), chain_source_id=f"CHAIN:{underlying}",
        candidate_constructed_at=tick + timedelta(seconds=2),
    )
    store.start(clock)
    return store, clock


def test_never_attempted_and_restart_complete_are_distinct(tmp_path):
    store = PartnerCollectionAttemptStore(tmp_path)
    empty = store.session_readiness(session_date=NOW.date(), now=NOW,
                                    underlyings=["NIFTY", "SENSEX"],
                                    entry_start_minute=9 * 60 + 45, entry_end_minute=14 * 60 + 45)
    assert empty["per_index"]["NIFTY"]["state"] == "NEVER_ATTEMPTED"

    store, clock = _started(tmp_path)
    store.record_public(clock.run_id, state="OBSERVED", requested_at=clock.public_requested_at,
                        received_at=clock.public_received_at, source_id=clock.public_source_id,
                        artifact_ref="public.json", updated_at=NOW + timedelta(seconds=2))
    store.record_candidate(clock.run_id, state="OBSERVED", requested_at=clock.chain_requested_at,
                           received_at=clock.chain_received_at, source_id=clock.chain_source_id,
                           requested_contracts=[11, 12], received_contracts=[11, 12],
                           artifact_ref="candidate.json", updated_at=NOW + timedelta(seconds=2))
    store.finish(clock.run_id, state="CANDIDATE_RECORDED", reason="candidate_validated",
                 updated_at=NOW + timedelta(seconds=2))
    reopened = PartnerCollectionAttemptStore(tmp_path).session_readiness(
        session_date=NOW.date(), now=NOW + timedelta(seconds=2), underlyings=["NIFTY", "SENSEX"],
        entry_start_minute=9 * 60 + 45, entry_end_minute=14 * 60 + 45,
    )
    assert reopened["per_index"]["NIFTY"]["state"] == "COMPLETE"
    assert reopened["per_index"]["SENSEX"]["state"] == "NEVER_ATTEMPTED"
    assert reopened["can_qualify"] is False

    interrupted = PartnerCollectionAttemptStore(tmp_path).session_readiness(
        session_date=NOW.date(), now=NOW + timedelta(minutes=2), underlyings=["NIFTY"],
        entry_start_minute=9 * 60 + 45, entry_end_minute=14 * 60 + 45,
    )
    assert interrupted["per_index"]["NIFTY"]["state"] == "PARTIAL"
    assert interrupted["per_index"]["NIFTY"]["missing_schedule_count"] == 1


def test_unavailable_and_partial_contract_coverage_survive_reopen(tmp_path):
    store, clock = _started(tmp_path, "NIFTY")
    store.record_public(clock.run_id, state="UNAVAILABLE", requested_at=clock.public_requested_at,
                        received_at=None, source_id=clock.public_source_id, reason="timeout", updated_at=NOW)
    store.record_candidate(clock.run_id, state="NOT_REQUIRED", requested_at=None, received_at=None,
                           source_id=None, reason="public unavailable", updated_at=NOW)
    store.finish(clock.run_id, state="UNAVAILABLE", reason="timeout", updated_at=NOW)
    report = PartnerCollectionAttemptStore(tmp_path).session_readiness(
        session_date=NOW.date(), now=NOW, underlyings=["NIFTY"],
        entry_start_minute=9 * 60 + 45, entry_end_minute=14 * 60 + 45)
    assert report["per_index"]["NIFTY"]["state"] == "ATTEMPTED_UNAVAILABLE"

    other_store, other = _started(tmp_path, "SENSEX")
    other_store.record_public(other.run_id, state="OBSERVED", requested_at=other.public_requested_at,
                              received_at=other.public_received_at, source_id=other.public_source_id,
                              updated_at=NOW)
    other_store.record_candidate(other.run_id, state="PARTIAL", requested_at=other.chain_requested_at,
                                 received_at=other.chain_received_at, source_id=other.chain_source_id,
                                 requested_contracts=[21, 22], received_contracts=[21], reason="missing_leg",
                                 updated_at=NOW)
    other_store.finish(other.run_id, state="ERROR", reason="missing_leg", updated_at=NOW)
    report = PartnerCollectionAttemptStore(tmp_path).session_readiness(
        session_date=NOW.date(), now=NOW, underlyings=["SENSEX"],
        entry_start_minute=9 * 60 + 45, entry_end_minute=14 * 60 + 45)
    assert report["per_index"]["SENSEX"]["state"] == "PARTIAL"
    assert report["per_index"]["SENSEX"]["incomplete_count"] == 1


def test_attempt_module_has_no_operational_authority_imports():
    source = Path(__import__("partner_collection_attempts").__file__).read_text(encoding="utf-8")
    for forbidden in ("order_executor", "performance", "position_tracker", "hedge_advisory", "telegram"):
        assert f"import {forbidden}" not in source


def test_received_contract_outside_request_is_rejected(tmp_path):
    store, clock = _started(tmp_path)
    with pytest.raises(ValueError, match="subset"):
        store.record_candidate(clock.run_id, state="PARTIAL", requested_at=clock.chain_requested_at,
                               received_at=clock.chain_received_at, source_id=clock.chain_source_id,
                               requested_contracts=[1], received_contracts=[2], updated_at=NOW)


def test_stale_public_observation_is_not_reported_complete(tmp_path):
    store, clock = _started(tmp_path)
    store.record_public(
        clock.run_id, state="OBSERVED", requested_at=clock.public_requested_at,
        received_at=clock.public_received_at, observed_at=clock.public_received_at - timedelta(minutes=7),
        source_id=clock.public_source_id, updated_at=NOW,
    )
    store.record_candidate(
        clock.run_id, state="NOT_REQUIRED", requested_at=None, received_at=None,
        source_id=None, reason="no_setup", updated_at=NOW,
    )
    store.finish(clock.run_id, state="NO_SETUP", reason="no_setup", updated_at=NOW)
    report = store.session_readiness(
        session_date=NOW.date(), now=NOW, underlyings=["NIFTY"],
        entry_start_minute=9 * 60 + 45, entry_end_minute=14 * 60 + 45,
    )
    assert report["per_index"]["NIFTY"]["state"] == "STALE"
    assert report["per_index"]["NIFTY"]["stale_input_count"] == 1
