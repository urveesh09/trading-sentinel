from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from partner_research_capture import persist_public_input


def scoped_future(master="a" * 64):
    return {"format": "partner_public_future_scope_v1", "provider": "KITE", "channel": "HISTORICAL",
            "interval": "5minute", "underlying": "NIFTY", "exchange": "NFO",
            "contract_master_raw_sha256": master, "selection_as_of": "2026-07-10",
            "selected_future": {"token": 123, "tradingsymbol": "NIFTY26JULFUT", "expiry": "2026-07-30",
                                "instrument_type": "FUT", "lot_size": 75, "tick_size": .05},
            "eligible_future_expiries": ["2026-07-30", "2026-08-27"],
            "next_future": {"token": 124, "tradingsymbol": "NIFTY26AUGFUT", "expiry": "2026-08-27",
                            "instrument_type": "FUT", "lot_size": 75, "tick_size": .05},
            "nearest_strictly_future_option_expiry": "2026-07-14"}


def test_candidate_capture_roundtrip_preserves_actual_receipt(tmp_path):
    from tests.test_partner_qualification import candidate_bundle
    from partner_qualification import load_candidate_evidence
    from partner_research_capture import persist_candidate_input
    from pathlib import Path
    now = datetime(2026, 9, 11, 10, tzinfo=ZoneInfo('Asia/Kolkata'))
    book, snapshot, profile = load_candidate_evidence(candidate_bundle(), underlying='NIFTY', decision_at=now)
    received = now + timedelta(seconds=2)
    result = persist_candidate_input(tmp_path, book=book, snapshot=snapshot, profile=profile,
                                     evaluation_at=now, received_at=received)
    payload = json.loads(Path(result['path']).read_text())
    assert payload['received_at'] == received.isoformat()
    assert payload['evaluation_at'] == now.isoformat()
    assert len(payload['snapshot']['quotes']) == 2
    assert not payload['can_qualify']
    # Late receipt stays late; the original tick clock cannot authorize its use.
    with pytest.raises(ValueError, match='unavailable at decision time'):
        load_candidate_evidence(payload, underlying='NIFTY', decision_at=now)
    restored_book, restored, restored_profile = load_candidate_evidence(payload, underlying='NIFTY', decision_at=received)
    assert restored.quotes == snapshot.quotes
    assert restored_profile == profile
    assert len(restored_book.by_symbol) == len(book.by_symbol)
    assert persist_candidate_input(tmp_path, book=book, snapshot=snapshot, profile=profile,
        evaluation_at=now, received_at=received) == result
    from research_cli import _candidate_file
    assert _candidate_file(result['path']) == payload
    payload['profile']['risk_limit_rs'] = 999999
    Path(result['path']).write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError, match='fingerprint'):
        _candidate_file(result['path'])


def test_v2_captures_bind_same_run_with_frozen_cutoff_and_later_decision(tmp_path):
    from tests.test_partner_qualification import candidate_bundle
    from partner_decision_clock import start_clock
    from partner_qualification import load_candidate_evidence
    from partner_research_capture import load_public_input, persist_candidate_input

    cutoff = datetime(2026, 9, 11, 10, tzinfo=ZoneInfo("Asia/Kolkata"))
    public_received = cutoff + timedelta(seconds=2)
    chain_received = cutoff + timedelta(seconds=5)
    decision_at = cutoff + timedelta(seconds=6)
    partial_clock = start_clock(
        underlying="NIFTY", account_id="manual-profile:p1", tick_started_at=cutoff,
    ).with_stage(
        public_requested_at=cutoff, public_received_at=public_received,
        public_source_id="KITE_HISTORICAL_5MINUTE:NIFTY:123",
    )
    from tests.test_partner_qualification import bars as make_bars
    bars = make_bars()
    scan = SimpleNamespace(name="NIFTY", research_bars=bars, research_received_at=public_received,
                           research_future_token=123, sig=None, error="")
    public = persist_public_input(tmp_path, scan, regime="REGIME_1_NORMAL",
                                  evaluation_at=cutoff, decision_clock=partial_clock)
    _, _, restored_cutoff, provenance = load_public_input(public["path"], underlying="NIFTY")
    assert restored_cutoff == cutoff
    assert provenance["state"] == "ACQUIRED_AFTER_FROZEN_CUTOFF"
    assert provenance["decision_clock"]["run_id"] == partial_clock.run_id

    value = candidate_bundle()
    value["received_at"] = value["snapshot"]["taken_at"] = chain_received.isoformat()
    book, snapshot, profile = load_candidate_evidence(value, underlying="NIFTY", decision_at=decision_at)
    full_clock = partial_clock.with_stage(
        chain_requested_at=cutoff + timedelta(seconds=3), chain_received_at=chain_received,
        chain_source_id="KITE_OPTION_CHAIN:NIFTY", candidate_constructed_at=decision_at,
    )
    candidate = persist_candidate_input(
        tmp_path, book=book, snapshot=snapshot, profile=profile,
        evaluation_at=cutoff, received_at=chain_received, decision_clock=full_clock,
    )
    payload = json.loads(Path(candidate["path"]).read_text())
    assert payload["format"] == "partner_observed_candidate_input_v2"
    assert payload["decision_clock"]["run_id"] == provenance["decision_clock"]["run_id"]
    assert payload["decision_clock"]["candidate_constructed_at"] == decision_at.isoformat()


def test_lifecycle_loader_recomputes_price_and_preserves_late_receipt(tmp_path):
    from tests.test_fno_signal_scan import _frame, LONG_ROWS, NOW
    from partner_research_capture import load_public_lifecycle
    from pathlib import Path
    frame = _frame(LONG_ROWS)
    receipt = NOW + timedelta(seconds=2)
    scan = SimpleNamespace(name='NIFTY', research_bars=frame, research_received_at=receipt,
                           research_future_token=123, sig=None, error='')
    capture = persist_public_input(tmp_path, scan, regime='REGIME_1_NORMAL', evaluation_at=NOW)
    result = load_public_lifecycle([capture['path']], underlying='NIFTY', max_age_seconds=600)
    assert result['observations'][0]['received_at'] == receipt
    assert result['observations'][0]['observed_at'] <= NOW
    assert result['sources'][0]['provenance_state'] == 'RETROSPECTIVE'
    assert result['sources'][0]['public_scope_state'] == 'LEGACY_UNSCOPED'
    assert result['coverage'] == 'SUPPLIED_CAPTURES_ONLY'
    assert not result['can_qualify']
    with pytest.raises(ValueError, match='duplicate'):
        load_public_lifecycle([capture['path']] * 2, underlying='NIFTY', max_age_seconds=600)
    with pytest.raises(ValueError, match='scope'):
        load_public_lifecycle([capture['path']], underlying='SENSEX', max_age_seconds=600)
    Path(capture['path']).write_text('{}')
    with pytest.raises(ValueError, match='fingerprint'):
        load_public_lifecycle([capture['path']], underlying='NIFTY', max_age_seconds=600)


def test_lifecycle_loader_rejects_stale_receipt(tmp_path):
    from tests.test_fno_signal_scan import _frame, LONG_ROWS, NOW
    from partner_research_capture import load_public_lifecycle
    scan = SimpleNamespace(name='NIFTY', research_bars=_frame(LONG_ROWS),
        research_received_at=NOW + timedelta(minutes=20), research_future_token=123, sig=None, error='')
    capture = persist_public_input(tmp_path, scan, regime='REGIME_1_NORMAL', evaluation_at=NOW)
    with pytest.raises(ValueError, match='stale'):
        load_public_lifecycle([capture['path']], underlying='NIFTY', max_age_seconds=600)


def test_capture_retains_frame_and_actual_late_receipt(tmp_path):
    now = datetime(2026, 9, 11, 10, tzinfo=ZoneInfo("Asia/Kolkata"))
    bars = pd.DataFrame({"open": [100.], "high": [102.], "low": [99.], "close": [101.], "volume": [50.]},
                        index=pd.to_datetime(["2026-09-11 09:55"]))
    scan = SimpleNamespace(name="NIFTY", research_bars=bars, research_received_at=now + timedelta(seconds=3),
                           research_future_token=123, sig=None, error="")
    result = persist_public_input(tmp_path, scan, regime="NORMAL", evaluation_at=now)
    repeated = persist_public_input(tmp_path, scan, regime="NORMAL", evaluation_at=now)
    assert result == repeated
    from pathlib import Path
    raw = Path(result["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == result["sha256"]
    payload = json.loads(raw)
    assert payload["received_at"] != payload["evaluation_at"]
    assert payload["bars"][0]["close"] == 101
    assert payload["can_qualify"] is False
    from partner_research_capture import load_public_input
    frame, regime, at, provenance = load_public_input(result["path"], underlying="NIFTY")
    assert frame.iloc[0]["close"] == 101
    assert at == now and regime == "NORMAL"
    assert provenance["state"] == "RETROSPECTIVE"
    from research_cli import main
    output = tmp_path / "diagnostic.json"
    assert main(["captured-policy-diagnostic", "--public-input", result["path"],
                 "--underlying", "NIFTY", "--output", str(output)]) == 0
    assert json.loads(output.read_text())["can_qualify"] is False
    Path(result["path"]).write_text("corrupted")
    with pytest.raises(ValueError, match="hash mismatch"):
        persist_public_input(tmp_path, scan, regime="NORMAL", evaluation_at=now)


def test_v3_capture_binds_verified_future_master_and_roll_scope(tmp_path):
    from tests.test_fno_signal_scan import _frame, LONG_ROWS, NOW
    from partner_research_capture import load_public_input, load_public_lifecycle
    scan = SimpleNamespace(name="NIFTY", research_bars=_frame(LONG_ROWS), research_received_at=NOW,
        research_future_token=123, research_public_scope=scoped_future(), sig=None, error="")
    capture = persist_public_input(tmp_path, scan, regime="REGIME_1_NORMAL", evaluation_at=NOW)
    payload = json.loads(Path(capture["path"]).read_text())
    assert payload["format"] == "partner_observed_public_input_v3"
    assert payload["public_scope"]["selected_future"]["expiry"] == "2026-07-30"
    _, _, _, provenance = load_public_input(capture["path"], underlying="NIFTY")
    assert provenance["public_scope_state"] == "VERIFIED_CONTRACT_SCOPE"
    assert provenance["public_scope_sha256"] == payload["public_scope_sha256"]
    lifecycle = load_public_lifecycle([capture["path"]], underlying="NIFTY", max_age_seconds=600)
    assert lifecycle["sources"][0]["public_scope"]["next_future"]["token"] == 124
    invalid = SimpleNamespace(**{**scan.__dict__, "research_public_scope": {
        **scoped_future(), "eligible_future_expiries": ["2026-08-27", "2026-07-30"]}})
    with pytest.raises(ValueError, match="front-future selection"):
        persist_public_input(tmp_path, invalid, regime="REGIME_1_NORMAL", evaluation_at=NOW)


def test_missing_capture_is_explicit(tmp_path):
    result = persist_public_input(tmp_path, SimpleNamespace(), regime="NORMAL", evaluation_at=None)
    assert result == {"state": "UNAVAILABLE", "reason": "observed_bars_missing"}


def test_captured_frame_to_real_candidate_cli(tmp_path):
    from tests.test_fno_signal_scan import _frame, LONG_ROWS, NOW, EXPIRY
    from tests.test_partner_qualification import candidate_bundle
    from fno_engine_mom import evaluate_fno_mom
    from research_cli import main
    frame = _frame(LONG_ROWS)
    scan = SimpleNamespace(name="NIFTY", research_bars=frame, research_received_at=NOW,
        research_future_token=123, sig=evaluate_fno_mom(frame, "REGIME_1_NORMAL", NOW), error="")
    capture = persist_public_input(tmp_path, scan, regime="REGIME_1_NORMAL", evaluation_at=NOW)
    bundle = candidate_bundle()
    bundle["received_at"] = bundle["snapshot"]["taken_at"] = NOW.isoformat()
    bundle["snapshot"]["expiry"] = EXPIRY.isoformat()
    for item in bundle["contracts"]:
        item["expiry"] = EXPIRY.isoformat()
    for item in bundle["snapshot"]["quotes"]:
        item["last_trade_time"] = NOW.isoformat()
    chain = tmp_path / "chain.json"
    chain.write_text(json.dumps(bundle))
    output = tmp_path / "decision.json"
    assert main(["captured-policy-diagnostic", "--public-input", capture["path"], "--underlying", "NIFTY",
                 "--candidate-evidence", str(chain), "--output", str(output)]) == 0
    result = json.loads(output.read_text())
    assert result["state"] == "ACCEPTED", result["validation_reasons"]
    assert len(result["candidate"]["selected_legs"]) == 2
    assert result["can_qualify"] is False
