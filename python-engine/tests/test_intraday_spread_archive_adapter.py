from datetime import datetime, timezone
import hashlib
import json

import pytest

from intraday_spread_archive_adapter import SpreadContractIdentity, build_spread_observations
from intraday_spread_replay import ReplayInputError
from intraday_spread_signal_artifact import write_signal_artifact


RAW_MASTER = (b"instrument_token,tradingsymbol,name,exchange,instrument_type,expiry,strike,lot_size\n"
              b"1,NIFTY25000CE,NIFTY,NFO,CE,2026-09-24,25000,75\n"
              b"2,NIFTY25200CE,NIFTY,NFO,CE,2026-09-24,25200,75\n")
MASTER = hashlib.sha256(RAW_MASTER).hexdigest()


def identity(token, symbol, strike):
    return SpreadContractIdentity(token, symbol, "NIFTY", "NFO", "CE", strike, "2026-09-24", 75)


def event(contract, received="2026-09-10T04:30:00+00:00"):
    raw = {"instrument_token": int(contract["instrument_token"]), "timestamp": received,
           "depth": {"buy": [{"price": 100, "quantity": 75}], "sell": [{"price": 102, "quantity": 75}]}}
    return {"received_at_utc": received, "provider_timestamp_utc": received, "contract": contract,
            "buy_depth": [{"price": 100, "quantity": 75}], "sell_depth": [{"price": 102, "quantity": 75}],
            "raw_packet": raw, "raw_sha256": hashlib.sha256(json.dumps(raw, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()}


def contract(item):
    return {"instrument_token": str(item.token), "tradingsymbol": item.symbol, "underlying": item.underlying,
            "exchange": item.exchange, "instrument_type": item.option_type, "strike": item.strike,
            "expiry": item.expiry, "lot_size": item.lot_size}


def archive(tmp_path, *items):
    path = tmp_path / "contract-masters" / "KITE" / "NFO" / "2026-09-10" / MASTER
    path.mkdir(parents=True)
    canonical = ("\n".join(json.dumps(contract(item)) for item in items) + "\n").encode()
    (path / "raw.csv").write_bytes(RAW_MASTER)
    (path / "manifest.json").write_text(json.dumps({"raw_sha256": MASTER, "canonical_sha256": hashlib.sha256(canonical).hexdigest()}), encoding="utf-8")
    (path / "contracts.jsonl").write_bytes(canonical)
    return tmp_path


def artifact(tmp_path, *, receipt="2026-09-10T04:30:00+00:00", score=1.0):
    path = tmp_path / "signals.json"
    source = tmp_path / "source-manifests" / "quotes-2026-09-10.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"archive":"fixture"}', encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    write_signal_artifact(path, {"format": "intraday_spread_signal_artifact_v1", "evaluator_id": "orb_threshold_v1",
        "evaluator_sha256": "a" * 64, "policy_id": "policy-v1", "policy_sha256": "b" * 64,
        "config_sha256": "c" * 64, "underlying": "NIFTY", "session_date": "2026-09-10",
        "source_manifests": [{"reference": "source-manifests/quotes-2026-09-10.json", "sha256": digest}],
        "signals": [{"decision_id": "one", "received_at": receipt, "decision_cutoff": receipt, "score": score,
                     "evaluator_input": {"direction": "LONG", "close": 101, "trigger": 100,
                     "source_packets": [{"packet_id": "bar-one", "received_at": receipt}]}}]})
    return path


@pytest.mark.parametrize("filename", ["raw.csv", "contracts.jsonl"])
def test_master_file_tampering_rejected(tmp_path, filename):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    archive(tmp_path, long, short)
    path = next((tmp_path / "contract-masters").rglob(filename))
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ReplayInputError, match="master does not prove"):
        build_spread_observations(events=[], long_contract=long, short_contract=short,
                                  master_sha256=MASTER, archive_root=tmp_path)


def test_rehashed_normalized_terms_must_still_match_raw_master(tmp_path):
    from dataclasses import replace
    from intraday_spread_archive_adapter import _master_proves_contract
    wrong = replace(identity(1, "NIFTY25000CE", 25000), lot_size=100)
    archive(tmp_path, wrong)
    assert not _master_proves_contract(tmp_path, wrong, MASTER)


@pytest.mark.parametrize("fault", ["hash", "price", "clock", "changed_clock"])
def test_unproven_quote_is_partial_not_executable(tmp_path, fault):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    bad = event(contract(long))
    if fault == "hash":
        bad["raw_sha256"] = "0" * 64
    elif fault == "price":
        bad["buy_depth"][0]["price"] = 999
    elif fault == "clock":
        bad["provider_timestamp_utc"] = None
    else:
        bad["provider_timestamp_utc"] = "2026-09-10T04:29:59+00:00"
    built = build_spread_observations(events=[bad, event(contract(short))], long_contract=long,
        short_contract=short, master_sha256=MASTER, archive_root=archive(tmp_path, long, short))
    assert not built.observations
    assert built.partial_batches[0]["missing"] == ["long"]


def test_archive_adapter_pairs_only_complete_same_receipt_batches_and_retains_partial(tmp_path):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    built = build_spread_observations(events=[event(contract(long)), event(contract(short)),
        event(contract(long), "2026-09-10T04:35:00+00:00")], long_contract=long, short_contract=short,
        master_sha256=MASTER, archive_root=archive(tmp_path, long, short),
        signal_artifact_path=artifact(tmp_path), policy_id="policy-v1", session_date="2026-09-10")
    assert len(built.observations) == 1
    assert built.observations[0].signal_score == 1.0
    assert built.partial_batches[0]["missing"] == ["short"]


def test_archive_adapter_rejects_tampered_signal_artifact(tmp_path):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    path = artifact(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace('"score":1.0', '"score":999'), encoding="utf-8")
    with pytest.raises(ReplayInputError, match="score does not reproduce"):
        build_spread_observations(events=[], long_contract=long, short_contract=short, master_sha256=MASTER, archive_root=archive(tmp_path, long, short),
                                  signal_artifact_path=path, policy_id="policy-v1", session_date="2026-09-10")


def test_archive_adapter_rejects_signal_artifact_with_missing_source_manifest(tmp_path):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    root = archive(tmp_path, long, short)
    path = artifact(tmp_path)
    (tmp_path / "source-manifests" / "quotes-2026-09-10.json").unlink()
    with pytest.raises(ReplayInputError, match="source manifest is missing"):
        build_spread_observations(events=[], long_contract=long, short_contract=short, master_sha256=MASTER,
            archive_root=root, signal_artifact_path=path, policy_id="policy-v1", session_date="2026-09-10")
