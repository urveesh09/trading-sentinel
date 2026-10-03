"""B0: catalogue/registry agreement and the offline backtest CLI."""
import json
import sqlite3

import pytest

import backtest_cli
from backtest_catalogue import validate_catalogue
from tests.test_penny_lifecycle_replay import _breakout_day, _daily


def test_catalogue_matches_registry_and_scopes_are_declared():
    assert validate_catalogue() == []


def _source_db(path):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE intraday_cache(ticker TEXT,interval TEXT,datetime TEXT,open REAL,"
                   "high REAL,low REAL,close REAL,volume REAL)")
        db.execute("CREATE TABLE ohlcv_cache(ticker TEXT,date TEXT,open REAL,high REAL,low REAL,"
                   "close REAL,volume REAL)")
        db.executemany("INSERT INTO intraday_cache VALUES(?,?,?,?,?,?,?,?)", _breakout_day())
        db.executemany("INSERT INTO ohlcv_cache VALUES(?,?,?,?,?,?,?)", _daily())
    sqlite3.connect(path).close()


def test_snapshot_run_compare_and_tamper_refusal(tmp_path, capsys):
    src, snap = tmp_path / "src.db", tmp_path / "snap.sqlite"
    _source_db(src)
    before = src.read_bytes()
    assert backtest_cli.main(["snapshot", "--db", str(src), "--from", "2026-08-10", "--to", "2026-08-10",
                              "--tickers", "AAA", "--out", str(snap)]) == 0
    assert src.read_bytes() == before
    assert backtest_cli.main(["snapshot", "--db", str(src), "--from", "2026-08-10", "--to", "2026-08-10",
                              "--tickers", "AAA", "--out", str(snap)]) == 2          # no overwrite
    args = ["run", "--snapshot", str(snap), "--strategy", "penny_breakout_mis_lifecycle_1m",
            "--from", "2026-08-10", "--to", "2026-08-10", "--config", '{"tickers": ["AAA"]}']
    assert backtest_cli.main(args + ["--out", str(tmp_path / "a.json")]) == 0
    assert backtest_cli.main(args + ["--out", str(tmp_path / "b.json")]) == 0
    report = json.loads((tmp_path / "a.json").read_text())
    assert report["state"] == "SUCCEEDED" and report["scope"] == "LIFECYCLE"
    assert report["metrics"]["trade_count"] == 1 and report["policy"]["secret_keys_excluded"]
    assert not any(p in k.upper() for k in report["policy"]["family_settings"]
                   for p in backtest_cli.SECRET_PATTERNS)
    capsys.readouterr()
    assert backtest_cli.main(["compare", str(tmp_path / "a.json"), str(tmp_path / "b.json")]) == 0
    assert json.loads(capsys.readouterr().out)["metric_differences"]["net_pnl"]["b_minus_a"] == 0
    with sqlite3.connect(snap) as db:
        db.execute("UPDATE ohlcv_cache SET close=close+1 WHERE rowid=1")
    sqlite3.connect(snap).close()
    assert backtest_cli.main(args + ["--out", str(tmp_path / "c.json")]) == 2       # tampered
    with pytest.raises(backtest_cli.CliError, match="changed"):
        backtest_cli.verify_snapshot(str(snap))
