"""Yahoo transport/fidelity tests use deterministic quotes, never network/brokers."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import backtest_all_yahoo as yahoo


def fixture_chart(days, values=None, *, symbol="AAA.NS", interval="1d"):
    stamps = [int(datetime.fromisoformat(day).replace(tzinfo=yahoo.IST).timestamp()) for day in days]
    rows = values or [[10, 11, 9, 10.5, 100] for _ in stamps]
    fields = ("open", "high", "low", "close", "volume")
    return {"chart": {"error": None, "result": [{
        "meta": {"symbol": symbol, "currency": "INR", "exchangeTimezoneName": "Asia/Kolkata", "instrumentType": "EQUITY"},
        "timestamp": stamps,
        "indicators": {"quote": [{field: [row[i] for row in rows] for i, field in enumerate(fields)}]},
    }]}}


def test_inclusive_end_and_extra_latest_provider_mark():
    payload = fixture_chart(["2026-09-24T09:15:00", "2026-09-30T09:15:00", "2026-10-01T15:30:00"])
    rows, receipt = yahoo.parse_chart(payload, "AAA", "AAA.NS", "1d", "2026-09-24", "2026-09-30")
    assert [row[1] for row in rows] == ["2026-09-24", "2026-09-30"]
    assert receipt["out_of_window_rows"] == 1


def test_native_interval_aware_clock_and_zero_volume_preserved():
    payload = fixture_chart(["2026-09-30T09:15:00"], [[10, 11, 9, 10.5, 0]])
    rows, _ = yahoo.parse_chart(payload, "AAA", "AAA.NS", "1m", "2026-09-30", "2026-09-30")
    assert rows == [["AAA", "minute", "2026-09-30T09:15:00+05:30", 10, 11, 9, 10.5, 0]]


def test_latest_close_quote_is_not_mislabelled_as_a_session_bar():
    payload = fixture_chart(["2026-09-30T15:29:00", "2026-09-30T15:30:00"], [[10, 11, 9, 10.5, 100], [10.5]*4+[0]])
    result = payload["chart"]["result"][0]
    result["meta"]["regularMarketTime"] = result["timestamp"][-1]
    rows, receipt = yahoo.parse_chart(payload, "AAA", "AAA.NS", "1m", "2026-09-30", "2026-09-30")
    assert len(rows) == 1 and len(receipt["latest_quote_marks"]) == 1


def test_absence_slots_and_closed_session_marks_are_not_candles():
    payload = fixture_chart(["2026-09-14T09:15:00", "2026-09-15T09:15:00", "2026-09-16T09:15:00", "2026-09-17T09:15:00"],
                            [[10, 10, 10, 10, 0], [None]*5, [10, 11, 9, 10.5, 100], [None, 11, 9, 10.5, 100]])
    rows, receipt = yahoo.parse_chart(payload, "AAA", "AAA.NS", "1d", "2026-09-14", "2026-09-17")
    assert len(rows) == 2 and rows[-1][2] is None
    assert len(receipt["empty_provider_slots"]) == len(receipt["non_session_marks"]) == 1
    assert receipt["invalid_cells_rows"] == 1


@pytest.mark.parametrize("field,value", [("symbol", "WRONG.NS"), ("currency", "USD"),
                                         ("exchangeTimezoneName", "America/New_York"), ("instrumentType", "OPTION")])
def test_wrong_instrument_provenance_fails(field, value):
    payload = fixture_chart(["2026-09-30T09:15:00"])
    payload["chart"]["result"][0]["meta"][field] = value
    with pytest.raises(yahoo.YahooDataError):
        yahoo.parse_chart(payload, "AAA", "AAA.NS", "1d", "2026-09-30", "2026-09-30")


def test_retention_error_is_not_empty_profitable_sample():
    with pytest.raises(yahoo.YahooDataError, match="last 60 days"):
        yahoo.parse_chart({"chart": {"error": {"code": "Unprocessable Entity", "description": "last 60 days"}}},
                          "AAA", "AAA.NS", "15m", "2026-07-01", "2026-09-30")
    assert yahoo.chunks("2026-09-01", "2026-09-15", "1m") == [
        ("2026-09-01", "2026-09-07"), ("2026-09-08", "2026-09-14"), ("2026-09-15", "2026-09-15")]


def test_utc_clocks_do_not_misorder_shared_cash_and_leave_source_untouched():
    from portfolio_parity import reconcile_shared_cash
    trades = [{"ticker": "A", "entry_time_utc": "2026-09-30T04:00:00+00:00", "exit_fill_ts": "2026-09-30T10:00:00+05:30",
               "entry_price": 10, "shares": 1, "net_pnl": 1},
              {"ticker": "B", "entry_time_utc": "2026-09-30T05:00:00+00:00", "entry_price": 10, "shares": 1}]
    result = reconcile_shared_cash((("mis", yahoo.normalize_trade_clocks(trades)),), initial_cash=10)
    assert result.admitted == 2 and result.cash_rejected == 0 and result.locked_cash == 10
    assert trades[0]["exit_fill_ts"].endswith("+05:30")


def fake_request(tmp_path, modules="range"):
    return yahoo.parser().parse_args(["--start", "2026-09-30", "--end", "2026-09-30", "--tickers", "AAA",
                                     "--modules", modules, "--out", str(tmp_path / "run")])


def fixture_fetch(local, symbol, mapped, interval, start, end, **kwargs):
    payload = fixture_chart(["2026-09-29T09:15:00", "2026-09-30T09:15:00"], symbol=mapped)
    rows, receipt = yahoo.parse_chart(payload, symbol, mapped, interval, start, end)
    target = local / "raw" / f"{mapped}_{interval}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload))
    return rows, {**receipt, "interval": interval, "symbol": symbol, "state": "AVAILABLE",
                  "raw_file": str(target.relative_to(local.parent)), "raw_sha256": yahoo.sha(target)}


def test_yahoo_only_snapshot_offline_replay_and_no_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(yahoo, "fetch_chart", fixture_fetch)
    original = yahoo.run(fake_request(tmp_path))
    summary = json.loads((original / "summary.json").read_text())
    assert summary["source"] == yahoo.SOURCE and summary["full_system_profit_available"] is False
    assert summary["modules"][0]["scope"] == "EVALUATOR"
    with pytest.raises(FileExistsError):
        yahoo.run(fake_request(tmp_path))
    def no_network(*args, **kwargs):
        raise AssertionError("offline rerun contacted provider")
    monkeypatch.setattr(yahoo, "fetch_chart", no_network)
    offline = fake_request(tmp_path)
    offline.offline = original
    offline.out = tmp_path / "offline"
    repeated = yahoo.run(offline)
    second = json.loads((repeated / "summary.json").read_text())
    assert second["modules"][0]["metrics"] == summary["modules"][0]["metrics"]
    raw = next((original / "_local/raw").glob("*.json"))
    raw.write_text("tampered")
    offline = fake_request(tmp_path)
    offline.offline = original
    offline.out = tmp_path / "tampered"
    with pytest.raises(ValueError, match="raw response changed"):
        yahoo.run(offline)


def test_module_failure_does_not_suppress_other_results(tmp_path, monkeypatch):
    monkeypatch.setattr(yahoo, "fetch_chart", fixture_fetch)
    def fail(*args):
        raise RuntimeError("fixture evaluator failed")
    monkeypatch.setattr(yahoo.STRATEGY_REGISTRY["range_reversion_daily_evaluator"], "execute", fail)
    out = yahoo.run(fake_request(tmp_path, "range,partner"))
    records = json.loads((out / "summary.json").read_text())["modules"]
    assert [record["state"] for record in records] == ["FAILED", "NOT_ADAPTED"]
    assert records[0]["metrics"] is None


def test_invalid_row_excludes_entire_ticker_day_not_only_bad_bar(tmp_path):
    out = tmp_path / "run"
    (out / "_local").mkdir(parents=True)
    snap = yahoo.write_snapshot({"daily": [["AAA", "2026-09-29", 10, 11, 9, 10.5, 100]],
        "intraday": [["AAA", "15minute", "2026-09-30T09:15:00+05:30", 10, 11, 9, 10.5, 100],
                     ["AAA", "15minute", "2026-09-30T09:30:00+05:30", None, 11, 9, 10.5, 100]],
        "request": {"start": "2026-09-30", "end": "2026-09-30"}}, str(out / "_local/yahoo.sqlite"), source=yahoo.SOURCE)
    manifest = {"requested": ["2026-09-30", "2026-09-30"], "snapshot": snap,
                "availability": {"primary:15m": {"start": "2026-09-30", "end": "2026-09-30", "state": "AVAILABLE"}}}
    _, quality = yahoo.data_quality(out, {"stock": ["AAA"], "penny": ["AAA"]}, manifest)
    assert quality["validated_snapshot"]["row_counts"]["intraday"] == 0
    assert quality["intraday"]["primary:15m"]["manifest"]["status_counts"] == {"INVALID": 1}


def test_fno_selection_and_production_output_forbidden(tmp_path):
    args = fake_request(tmp_path, "fno")
    with pytest.raises(ValueError, match="unknown/non-cash"):
        yahoo.run(args)
    args = fake_request(tmp_path)
    args.out = ROOT.parent / "Production_Trading-sentinel" / "forbidden-yahoo-test"
    with pytest.raises(ValueError, match="Production output"):
        yahoo.run(args)


def test_unfinished_current_session_and_midrun_policy_drift_rejected(tmp_path, monkeypatch):
    class CurrentSession(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 30, 12, 0, tzinfo=yahoo.IST)
    monkeypatch.setattr(yahoo, "datetime", CurrentSession)
    with pytest.raises(ValueError, match="session is unfinished"):
        yahoo.run(fake_request(tmp_path))
    with pytest.raises(yahoo.BacktestUnavailable, match="source/settings changed"):
        yahoo.check_policy({"engine_sha256": "changed", "settings_sha256": "same"},
                           {"engine_sha256": "before", "settings_sha256": "same"}, None)
