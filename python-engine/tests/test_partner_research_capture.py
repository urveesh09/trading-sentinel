from datetime import datetime, timedelta
import hashlib
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from partner_research_capture import persist_public_input


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
