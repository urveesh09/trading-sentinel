from datetime import datetime, timezone
import json

import pytest

from intraday_spread_archive_adapter import SpreadContractIdentity, build_spread_observations
from intraday_spread_replay import ReplayInputError


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


def test_archive_adapter_pairs_only_complete_same_receipt_batches_and_retains_partial(tmp_path):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    built = build_spread_observations(events=[event(contract(long)), event(contract(short)),
        event(contract(long), "2026-09-10T04:35:00+00:00")], long_contract=long, short_contract=short,
        master_sha256=MASTER, archive_root=archive(tmp_path, long, short),
        signal_scores={"2026-09-10T04:30:00+00:00": .9}, signal_provenance_sha256="d" * 64)
    assert len(built.observations) == 1
    assert built.observations[0].signal_score == .9
    assert built.partial_batches[0]["missing"] == ["short"]


def test_archive_adapter_requires_signal_provenance(tmp_path):
    long, short = identity(1, "NIFTY25000CE", 25000), identity(2, "NIFTY25200CE", 25200)
    with pytest.raises(ReplayInputError, match="provenance"):
        build_spread_observations(events=[], long_contract=long, short_contract=short, master_sha256=MASTER, archive_root=archive(tmp_path, long, short),
                                  signal_scores={})
