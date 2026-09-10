from datetime import datetime, timezone
import hashlib
import json

import pytest

from intraday_spread_archive_adapter import SpreadContractIdentity, build_spread_observations
from intraday_spread_replay import ReplayInputError
from intraday_spread_signal_artifact import write_signal_artifact


MASTER = "c" * 64


def identity(token, symbol, strike):
    return SpreadContractIdentity(token, symbol, "NIFTY", "NFO", "CE", strike, "2026-09-24", 75)


def event(contract, received="2026-09-10T04:30:00+00:00"):
    return {"received_at_utc": received, "provider_timestamp_utc": received, "contract": contract,
            "buy_depth": [{"price": 100, "quantity": 75}], "sell_depth": [{"price": 102, "quantity": 75}]}


def contract(item):
    return {"instrument_token": str(item.token), "tradingsymbol": item.symbol, "underlying": item.underlying,
            "exchange": item.exchange, "instrument_type": item.option_type, "strike": item.strike,
            "expiry": item.expiry, "lot_size": item.lot_size}


def archive(tmp_path, *items):
    path = tmp_path / "contract-masters" / "KITE" / "NFO" / "2026-09-10" / MASTER
    path.mkdir(parents=True)
    (path / "manifest.json").write_text(json.dumps({"raw_sha256": MASTER}), encoding="utf-8")
    (path / "contracts.jsonl").write_text("\n".join(json.dumps(contract(item)) for item in items) + "\n", encoding="utf-8")
    return tmp_path


def artifact(tmp_path, *, receipt="2026-09-10T04:30:00+00:00", score=.9):
    path = tmp_path / "signals.json"
    source = tmp_path / "source-manifests" / "quotes-2026-09-10.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"archive":"fixture"}', encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    write_signal_artifact(path, {"format": "intraday_spread_signal_artifact_v1", "evaluator_id": "fixture-v1",
        "evaluator_sha256": "a" * 64, "policy_id": "policy-v1", "policy_sha256": "b" * 64,
        "config_sha256": "c" * 64, "underlying": "NIFTY", "session_date": "2026-09-10",
        "source_manifests": [{"reference": "source-manifests/quotes-2026-09-10.json", "sha256": digest}],
        "signals": [{"decision_id": "one", "received_at": receipt, "decision_cutoff": receipt, "score": score,
                     "source_receipt_bounds": {"start": receipt, "end": receipt}}]})
    return path


def test_archive_adapter_pairs_only_complete_same_receipt_batches_and_retains_partial(tmp_path):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    built = build_spread_observations(events=[event(contract(long)), event(contract(short)),
        event(contract(long), "2026-09-10T04:35:00+00:00")], long_contract=long, short_contract=short,
        master_sha256=MASTER, archive_root=archive(tmp_path, long, short),
        signal_artifact_path=artifact(tmp_path), policy_id="policy-v1", session_date="2026-09-10")
    assert len(built.observations) == 1
    assert built.observations[0].signal_score == .9
    assert built.partial_batches[0]["missing"] == ["short"]


def test_archive_adapter_rejects_tampered_signal_artifact(tmp_path):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    path = artifact(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace('"score":0.9', '"score":999'), encoding="utf-8")
    with pytest.raises(ReplayInputError, match="digest"):
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
