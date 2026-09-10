"""Data-plan D1-D5 regression tests: preservation never fakes depth."""
from datetime import date, datetime
import hashlib
import json
import sqlite3

import pandas as pd
import pytest
import pytz

import research_archive as archive
from fno_instruments import FnoInstruments
from research_quote_collector import collect_rest_quote_snapshot, normalise_quote
from fno_models import Contract
from research_study import run_modelled_intraday_study
from market_data_sources import BreezeHistoricalRequest, Capability, KiteMarketDataSource

IST = pytz.timezone("Asia/Kolkata")
HEADER = "instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange"


def _source_db(path):
    db = sqlite3.connect(path)
    db.executescript("""
      CREATE TABLE fno_chain_oi(snap_ts TEXT, underlying TEXT, expiry TEXT, strike REAL, opt_type TEXT, oi INTEGER, volume INTEGER, ltp REAL, iv REAL);
      CREATE TABLE fno_fut_snap(snap_ts TEXT, underlying TEXT, fut_ltp REAL, fut_oi INTEGER, pcr REAL, max_pain REAL, atm_iv REAL);
    """)
    db.executemany("INSERT INTO fno_chain_oi VALUES(?,?,?,?,?,?,?,?,?)", [
        ("2026-09-08 09:25:00", "NIFTY", "2026-09-10", 25000, "CE", 100, 11, 100.5, None),
        ("2026-09-08 09:25:00", "SENSEX", "2026-09-10", 82000, "PE", 200, 12, 200.5, None),
        ("2026-09-08 09:25:00", "BANKNIFTY", "2026-09-10", 50000, "CE", 999, 1, 1, None),
    ])
    db.executemany("INSERT INTO fno_fut_snap VALUES(?,?,?,?,?,?,?)", [
        ("2026-09-08 09:25:00", "NIFTY", 25010, 1000, 1.0, 25000, .12),
        ("2026-09-08 09:25:00", "SENSEX", 82010, 2000, 1.1, 82000, .13),
    ])
    db.commit(); db.close()


def test_readonly_fno_export_is_checksumming_and_filters_underlyings(tmp_path):
    source = tmp_path / "operational.db"; _source_db(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    result = archive.export_operational_fno_evidence(
        str(source), str(tmp_path / "research"), ["NIFTY", "SENSEX"],
        exported_at=datetime(2026, 9, 8, 7, tzinfo=pytz.UTC), source_commit="abc",
    )
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    assert before == after  # source was never opened writable
    manifest = json.loads((tmp_path / "research" / "operational-fno" / "20260908T070000Z" / "manifest.json").read_text())
    assert result["evidence_level"] == archive.EVIDENCE_OPTION_LTP_OI
    assert manifest["coverage"]["fno_chain_oi"]["row_count"] == 2
    exported = (tmp_path / "research" / "operational-fno" / "20260908T070000Z" / "fno_chain_oi.jsonl").read_text()
    assert "BANKNIFTY" not in exported and "bid" not in exported.lower()
    assert len(manifest["files"]["fno_chain_oi.jsonl"]["sha256"]) == 64


def test_readonly_export_cli_writes_no_source_changes(tmp_path, capsys):
    from research_cli import main
    source = tmp_path / "operational.db"; _source_db(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    assert main(["export-fno", "--source-db", str(source), "--archive-root", str(tmp_path / "out")]) == 0
    assert before == hashlib.sha256(source.read_bytes()).hexdigest()
    assert json.loads(capsys.readouterr().out)["exported"] is True


def test_contract_master_keeps_token_reuse_and_changed_lot_as_distinct_immutable_records(tmp_path):
    base = HEADER + "\n101,1,NIFTYOPT,NIFTY,0,2026-09-10,25000,0.05,75,CE,NFO-OPT,NFO"
    later = HEADER + "\n101,1,NIFTYOPT2,NIFTY,0,2026-09-17,25100,0.05,65,CE,NFO-OPT,NFO"
    first = archive.archive_contract_master(str(tmp_path), provider="KITE", segment="NFO", raw_csv=base,
                                            observed_at=datetime(2026, 9, 8, tzinfo=pytz.UTC))
    second = archive.archive_contract_master(str(tmp_path), provider="KITE", segment="NFO", raw_csv=later,
                                             observed_at=datetime(2026, 9, 8, 1, tzinfo=pytz.UTC))
    assert first["raw_sha256"] != second["raw_sha256"]
    records = list((tmp_path / "contract-masters").glob("**/contracts.jsonl"))
    assert len(records) == 2
    assert any('"lot_size":65' in item.read_text() for item in records)


def test_quote_archive_preserves_missing_depth_and_recovers_partial_open_segment(tmp_path):
    writer = archive.QuoteArchive(str(tmp_path), reserved_free_bytes=0)
    writer.append({"received_at_utc": "2026-09-08T04:00:00Z", "ltp": 100, "buy_depth": []})
    raw = tmp_path / "quotes" / "2026-09-08" / "quotes.jsonl.open"
    with open(raw, "ab") as handle:
        handle.write(b'{"truncated"')
    manifest = writer.finalize_day("2026-09-08")
    assert manifest["event_count"] == 1
    assert not raw.exists()
    assert (tmp_path / "quotes" / "2026-09-08" / manifest["path"]).exists()


def test_restart_repairs_corrupt_tail_before_next_valid_quote(tmp_path):
    first = archive.QuoteArchive(str(tmp_path), reserved_free_bytes=0)
    first.append({"received_at_utc": "2026-09-08T04:00:00Z", "event": "before"})
    raw = tmp_path / "quotes" / "2026-09-08" / "quotes.jsonl.open"
    with open(raw, "ab") as handle:
        handle.write(b'{"truncated"')
    restarted = archive.QuoteArchive(str(tmp_path), reserved_free_bytes=0)
    restarted.append({"received_at_utc": "2026-09-08T04:01:00Z", "event": "after"})
    manifest = restarted.finalize_day("2026-09-08")
    assert manifest["event_count"] == 2
    assert list((tmp_path / "quotes" / "2026-09-08").glob("*.corrupt-*"))


def test_restart_repairs_complete_json_without_newline(tmp_path):
    raw = tmp_path / "quotes" / "2026-09-08" / "quotes.jsonl.open"; raw.parent.mkdir(parents=True)
    raw.write_bytes(b'{"id":1}')
    writer = archive.QuoteArchive(str(tmp_path), reserved_free_bytes=0)
    writer.append({"received_at_utc": "2026-09-08T04:01:00Z", "id": 2})
    assert writer.finalize_day("2026-09-08")["event_count"] == 2


def test_readiness_is_per_index_and_reports_durable_gap(tmp_path):
    raw = HEADER + "\n1,1,NIFTYOPT,NIFTY,0,2026-09-10,25000,0.05,75,CE,NFO-OPT,NFO"
    archive.archive_contract_master(str(tmp_path), provider="KITE", segment="NFO", raw_csv=raw,
                                    observed_at=datetime(2026, 9, 8, tzinfo=pytz.UTC))
    writer = archive.QuoteArchive(str(tmp_path), reserved_free_bytes=0)
    writer.record_collection_run({"collected": 0, "gaps": [{"underlying": "SENSEX", "reason": "quote_batch_empty"}]}, expected_interval_sec=60)
    view = archive.readiness_view(str(tmp_path), ["NIFTY", "SENSEX"])
    assert view["per_index"]["NIFTY"]["master"]["contract_count"] == 1
    assert view["per_index"]["SENSEX"]["recent_gap_count"] == 1
    assert view["per_index"]["NIFTY"]["qualification"] == "NOT_EVALUATED_HERE"


def test_normalise_quote_never_invents_missing_book_levels():
    contract = Contract(1, "NIFTYOPT", "NIFTY", date(2026, 9, 10), 25000, "CE", 75)
    event = normalise_quote(contract, {"last_price": 100, "depth": {"buy": [{"price": 99, "quantity": 10}]}},
                            source="KITE", mode="KITE_REST_FULL_LOWER_FREQUENCY", selection_reason="test", exchange="NFO")
    assert event["missing_depth"] is True
    assert len(event["buy_depth"]) == len(event["sell_depth"]) == 5
    assert event["sell_depth"][0]["price"] is None


def test_rest_timestamp_and_zero_book_are_preserved_but_not_usable():
    contract = Contract(1, "NIFTYOPT", "NIFTY", date(2026, 9, 10), 25000, "CE", 75)
    event = normalise_quote(contract, {"timestamp": "2026-09-08 10:00:00", "last_price": 100,
                                       "depth": {"buy": [{"price": 0, "quantity": 0}], "sell": [{"price": 0, "quantity": 0}]}},
                            source="KITE", mode="KITE_REST_FULL_LOWER_FREQUENCY", selection_reason="test", exchange="NFO")
    assert event["provider_timestamp_raw"] == "2026-09-08 10:00:00"
    assert event["provider_timestamp_utc"] == "2026-09-08T04:30:00Z"
    assert event["missing_depth"] is True and event["depth_state"] == "MISSING_OR_UNUSABLE"
    assert event["raw_packet"]["depth"]["buy"][0]["price"] == 0


def test_nonfinite_depth_is_isolated_as_unusable_not_an_exception():
    contract = Contract(1, "NIFTYOPT", "NIFTY", date(2026, 9, 10), 25000, "CE", 75)
    event = normalise_quote(contract, {"depth": {"buy": [{"price": float("inf"), "quantity": float("inf")}], "sell": [{"price": 101, "quantity": 1}]}},
                            source="KITE", mode="KITE_REST_FULL_LOWER_FREQUENCY", selection_reason="test", exchange="NFO")
    assert event["depth_state"] == "MISSING_OR_UNUSABLE"


@pytest.mark.asyncio
async def test_rest_collector_is_delivery_independent_and_records_both_legs(tmp_path, monkeypatch):
    import research_quote_collector as collector
    from config import settings
    now = IST.localize(datetime(2026, 9, 8, 10, 0))
    raw = "\n".join([HEADER,
        "10,1,NIFTYFUT,NIFTY,0,2026-09-24,0,0.05,75,FUT,NFO-FUT,NFO",
        "11,1,NIFTY25000CE,NIFTY,0,2026-09-10,25000,0.05,75,CE,NFO-OPT,NFO",
        "12,1,NIFTY25000PE,NIFTY,0,2026-09-10,25000,0.05,75,PE,NFO-OPT,NFO",
        "13,1,NIFTY25000CE2,NIFTY,0,2026-09-17,25000,0.05,75,CE,NFO-OPT,NFO",
        "14,1,NIFTY25000PE2,NIFTY,0,2026-09-17,25000,0.05,75,PE,NFO-OPT,NFO",
    ])
    book = FnoInstruments("NIFTY", json_path=str(tmp_path / "instruments.json")); assert book.load_from_raw(raw)
    book.refreshed_on = now.date()
    book._strike_step = 50.0  # minimal fixture has one strike; production derives this from its ladder
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_UNDERLYINGS", "NIFTY")
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_STRIKE_WINDOW", 0)
    collector._archive = None
    class Kite:
        access_token = "present"
        async def get_quote(self, tokens):
            return {int(token): {"last_price": 25000 if int(token) == 10 else 100,
                                 "oi": 1000, "volume": 100,
                                 "depth": {"buy": [{"price": 99, "quantity": 100, "orders": 2}],
                                           "sell": [{"price": 101, "quantity": 100, "orders": 2}]}}
                    for token in tokens}
    result = await collect_rest_quote_snapshot(Kite(), now_ist=now, books={"NIFTY": book})
    assert result["collected"] == 5 and result["mode"] == "KITE_REST_FULL_LOWER_FREQUENCY"
    # Journal partitioning follows actual provider receipt, not the scheduler
    # clock passed to the test (which may be historical during replay).
    assert list((tmp_path / "research" / "quotes").glob("*/quotes.jsonl.open"))


def test_modelled_report_never_auto_qualifies(tmp_path, monkeypatch):
    import research_study
    monkeypatch.setattr(research_study, "run_fno_backtest", lambda bars, **_: {"n_trades": len(bars), "total_pnl": 0})
    index = pd.date_range("2026-09-01 09:15", periods=6, freq="5min")
    bars = pd.DataFrame({"open": [1]*6, "high": [2]*6, "low": [1]*6, "close": [1.5]*6, "volume": [10]*6}, index=index)
    result = run_modelled_intraday_study(bars, underlying="NIFTY", archive_root=str(tmp_path), run_id="frozen-v1")
    assert result["report"]["qualification"]["automatically_qualified"] is False
    with pytest.raises(ValueError, match="BFO"):
        run_modelled_intraday_study(bars, underlying="SENSEX", archive_root=str(tmp_path), run_id="bad")


@pytest.mark.asyncio
async def test_kite_capabilities_and_breeze_alias_do_not_claim_historical_depth():
    class Kite:
        access_token = "available"
    report = await KiteMarketDataSource(Kite()).capability_report()
    assert Capability.HISTORICAL_CANDLES in report.capabilities
    assert Capability.HISTORICAL_DEPTH not in report.capabilities
    assert BreezeHistoricalRequest.sensex_option(
        expiry_date="2026-09-10", right="ce", strike_price=82000,
        from_date="2026-09-01", to_date="2026-09-02",
    ).as_payload()["stock_code"] == "BSESEN"
