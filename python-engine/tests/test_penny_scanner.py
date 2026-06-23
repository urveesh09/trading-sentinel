"""
[PENNY-SCANNER 2026-06-21] Tests for the orchestrator that ties the penny
subsystem together.

Spec §9 + §8:
  - run_penny_scanner_once() called every 30s in MIS mode
  - run_penny_connors_scan() called once at 09:30 IST
  - Paper mode (PENNY_LIVE_TRADING=false): all signals fire but no
    real Kite orders placed; log_penny_signal called regardless
  - Live mode: real orders via kite.place_order() (not exercised here;
    covered in Task 11 main.py wiring tests)
  - PR3 regime blocks new entries (size_pct == 0)
  - Kill-switch blocks new entries
  - Manual disable list blocks specific tickers
  - Open-positions cap enforced
"""
import asyncio
import os
import csv
import sqlite3
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
import pytest


# ---- fixtures ---------------------------------------------------------

@pytest.fixture
def tmp_paths(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "PENNY_LOG_CSV_PATH", str(tmp_path / "penny_signals.csv"))
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "PENNY_LIVE_TRADING", False)  # paper mode
    monkeypatch.setattr(settings, "PENNY_DISABLE_TICKERS", "")
    return tmp_path


@pytest.fixture
def fake_kite():
    """Fake Kite client. Per the 2026-06-22 deviation, the scanner now
    fetches real 1-min intraday bars + 20-day daily volume via
    kite.get_intraday and kite.get_historical. The fake returns
    realistic-shape data so the evaluator gets to run.
    """
    import pandas as pd
    from datetime import datetime, timedelta

    k = MagicMock()
    k.instrument_cache = {"AAA": 1001, "BBB": 1002, "CCC": 1003}
    k.get_quote = AsyncMock(return_value={
        1001: {"last_price": 12.0, "ohlc": {"high": 12.0, "low": 12.0, "close": 12.0},
               "volume": 100_000, "depth": {"buy": [{"price": 12.0, "quantity": 1000}],
                                            "sell": [{"price": 12.1, "quantity": 1000}]}},
        1002: {"last_price": 30.0, "ohlc": {"high": 30.5, "low": 29.5, "close": 30.0},
               "volume": 80_000, "depth": {"buy": [{"price": 30.0, "quantity": 500}],
                                            "sell": [{"price": 30.05, "quantity": 500}]}},
        1003: {"last_price": 22.0, "ohlc": {"high": 22.0, "low": 22.0, "close": 22.0},
               "volume": 50_000, "depth": {"buy": [{"price": 22.0, "quantity": 200}],
                                            "sell": [{"price": 22.05, "quantity": 200}]}},
    })

    # Realistic 1-min intraday DataFrame (last bar at minute=as_of.minute
    # is in-progress; the scanner drops it). For test reproducibility
    # we use a 60-bar series ending at 14:29 IST.
    def _fake_intraday(ticker, from_datetime, to_datetime, interval="minute"):
        times = pd.date_range("2026-06-21 09:15", periods=60, freq="1min")
        # small random walk
        import math
        base = 12.0 if ticker == "AAA" else (30.0 if ticker == "BBB" else 22.0)
        prices = [base + 0.05 * math.sin(i / 5) for i in range(60)]
        df = pd.DataFrame({
            "open":   [p - 0.05 for p in prices],
            "high":   [p + 0.10 for p in prices],
            "low":    [p - 0.10 for p in prices],
            "close":  prices,
            "volume": [1000] * 60,
        }, index=pd.DatetimeIndex(times, name="datetime"))
        return df

    k.get_intraday = AsyncMock(side_effect=_fake_intraday)

    # Daily historical: 20 days of realistic volume data
    def _fake_historical(ticker, from_date, to_date):
        dates = pd.date_range(end="2026-06-21", periods=20, freq="D")
        return pd.DataFrame({
            "open":   [12.0] * 20,
            "high":   [12.5] * 20,
            "low":    [11.5] * 20,
            "close":  [12.0] * 20,
            "volume": [50_000] * 20,
        }, index=pd.DatetimeIndex(dates, name="date"))

    k.get_historical = AsyncMock(side_effect=_fake_historical)
    k.place_order = AsyncMock(return_value={"order_id": "PAPER-001"})
    return k


@pytest.fixture
def fake_universe(tmp_path):
    """Pre-populate penny_static.json with 3 eligible tickers."""
    import json
    payload = {
        "as_of": "2026-06-21",
        "universe_size_target": 100,
        "tickers": [
            {"symbol": "AAA", "series": "EQ", "prev_close": 12.0, "promoter_holding_pct": 50.0, "pb_ratio": 1.2, "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 1_000_000},
            {"symbol": "BBB", "series": "EQ", "prev_close": 30.0, "promoter_holding_pct": 55.0, "pb_ratio": 1.4, "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 1_500_000},
            {"symbol": "CCC", "series": "EQ", "prev_close": 22.0, "promoter_holding_pct": 60.0, "pb_ratio": 1.5, "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 800_000},
        ],
    }
    p = tmp_path / "penny_static.json"
    p.write_text(json.dumps(payload))
    return str(p)


# ---- helpers ----------------------------------------------------------

def _read_csv_rows(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


# ---- tests ------------------------------------------------------------

def test_scanner_initializes_signal_db(tmp_paths, fake_kite, fake_universe):
    """First run creates the penny_signals table."""
    asyncio.run(_run_scanner_with(tmp_paths, fake_kite, fake_universe))
    con = sqlite3.connect(tmp_paths / "test.db")
    cur = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='penny_signals'"
    )
    assert cur.fetchone() is not None
    con.close()


def test_scanner_appends_csv_rows(tmp_paths, fake_kite, fake_universe):
    """Each scan outcome (accept or reject) appears in the CSV."""
    asyncio.run(_run_scanner_with(tmp_paths, fake_kite, fake_universe))
    rows = _read_csv_rows(str(tmp_paths / "penny_signals.csv"))
    assert len(rows) >= 1   # at least one ticker logged
    tickers = {r["ticker"] for r in rows}
    # All 3 universe tickers should have at least one log entry
    assert tickers.issuperset({"AAA", "BBB", "CCC"})


def test_scanner_paper_mode_does_not_call_kite_place_order(tmp_paths, fake_kite, fake_universe):
    """In paper mode, signals fire but no real orders are placed."""
    asyncio.run(_run_scanner_with(tmp_paths, fake_kite, fake_universe))
    # fake_kite.place_order is mocked; in paper mode it should NOT have been called
    fake_kite.place_order.assert_not_called()


def test_scanner_blocks_when_pr3_regime(tmp_paths, fake_kite, fake_universe):
    """When regime is PR3_HOT, no new entries accepted."""
    from penny_scanner import PennyScanner
    scanner = PennyScanner(
        kite=fake_kite, universe_json_path=fake_universe,
        paper_mode=True, regime="PR3_HOT",
    )
    # Even if signal fires, PR3 returns size 0 -> reject
    asyncio.run(scanner.scan_once(as_of=datetime(2026, 6, 21, 11, 0)))
    rows = _read_csv_rows(str(tmp_paths / "penny_signals.csv"))
    # All entries should be rejected (accepted=0)
    assert all(r["accepted"] == "0" for r in rows)


def test_scanner_blocks_when_kill_switch_active(tmp_paths, fake_kite, fake_universe):
    from penny_scanner import PennyScanner
    scanner = PennyScanner(
        kite=fake_kite, universe_json_path=fake_universe,
        paper_mode=True, regime="PR1_CALM",
        daily_pnl_override=-500.0,   # triggers kill-switch
    )
    asyncio.run(scanner.scan_once(as_of=datetime(2026, 6, 21, 11, 0)))
    rows = _read_csv_rows(str(tmp_paths / "penny_signals.csv"))
    # All entries rejected with kill_switch reason
    assert all(r["accepted"] == "0" for r in rows)
    assert any("kill" in (r.get("reject_reason") or "").lower() for r in rows)


def test_scanner_respects_disable_list(tmp_paths, fake_kite, fake_universe):
    """Tickers in PENNY_DISABLE_TICKERS are skipped with disabled reason."""
    from config import settings
    settings.PENNY_DISABLE_TICKERS = "BBB"
    from penny_scanner import PennyScanner
    scanner = PennyScanner(
        kite=fake_kite, universe_json_path=fake_universe,
        paper_mode=True, regime="PR1_CALM",
    )
    asyncio.run(scanner.scan_once(as_of=datetime(2026, 6, 21, 11, 0)))
    rows = _read_csv_rows(str(tmp_paths / "penny_signals.csv"))
    bbb_rows = [r for r in rows if r["ticker"] == "BBB"]
    assert len(bbb_rows) >= 1
    assert all("disabl" in (r.get("reject_reason") or "").lower() for r in bbb_rows)


def test_scanner_handles_kite_failure_gracefully(tmp_paths, fake_kite, fake_universe):
    """If Kite raises during quote fetch, scanner logs and continues."""
    fake_kite.get_quote = AsyncMock(side_effect=Exception("network"))
    from penny_scanner import PennyScanner
    scanner = PennyScanner(
        kite=fake_kite, universe_json_path=fake_universe,
        paper_mode=True, regime="PR1_CALM",
    )
    # Should not raise
    asyncio.run(scanner.scan_once(as_of=datetime(2026, 6, 21, 11, 0)))
    # CSV may or may not exist depending on whether any ticker got evaluated;
    # what matters is no crash.
    assert True


# ---- helpers for the tests above -------------------------------------

async def _run_scanner_with(tmp_path, kite, universe_path):
    from penny_scanner import PennyScanner
    from penny_signal_log import init_penny_signal_db
    from config import settings
    await init_penny_signal_db(str(settings.DB_PATH))
    scanner = PennyScanner(
        kite=kite, universe_json_path=universe_path,
        paper_mode=True, regime="PR1_CALM",
    )
    await scanner.scan_once(as_of=datetime(2026, 6, 21, 11, 0))

def test_breakout_uses_real_intraday_not_synthetic_bar(tmp_paths, fake_kite, fake_universe, monkeypatch):
    """Per the 2026-06-22 deviation: the scanner must use real 1-min bars
    from kite.get_intraday, NOT a synthetic bar built from the LTP.

    This test patches evaluate_breakout_entry to capture the breakout_bar
    dict that the scanner passes in, then asserts it has the real
    open/high/low/close/volume keys (not a fabricated {high: ltp*1.01, ...}).
    """
    from unittest.mock import MagicMock
    import penny_engine_breakout
    from penny_scanner import PennyScanner

    captured = {}
    real_eval = penny_engine_breakout.evaluate_breakout_entry

    def capturing_eval(ticker, **kwargs):
        captured[ticker] = kwargs
        return {"accept": False, "reject_reason": "captured-only"}

    monkeypatch.setattr(penny_engine_breakout, "evaluate_breakout_entry", capturing_eval)

    s = PennyScanner(
        kite=fake_kite,
        universe_json_path=fake_universe,
        paper_mode=True,
        regime="PR1_CALM",
    )
    # Drive one ticker through the breakout evaluator
    from datetime import datetime
    asyncio.run(s._evaluate_ticker_breakout("AAA", as_of=datetime(2026, 6, 21, 14, 30)))

    assert "AAA" in captured, "evaluate_breakout_entry was not called for AAA"
    bar = captured["AAA"]["breakout_bar"]
    # Real bar has 5 fields: open, high, low, close, volume
    assert "open" in bar, f"breakout_bar missing 'open' (synthetic-bar fallback?): {bar}"
    assert "high" in bar and "low" in bar and "close" in bar, f"missing fields: {bar}"
    assert "volume" in bar, f"breakout_bar missing 'volume' (synthetic-bar fallback?): {bar}"
    # median_vol_20d must be a real number, not 10_000
    mv = captured["AAA"]["median_vol_20d"]
    assert mv > 0 and mv != 10_000, f"median_vol_20d is fabricated: {mv}"
    # rsi_14 must be 0-100, not 50.0
    rsi = captured["AAA"]["rsi_14"]
    assert 0.0 <= rsi <= 100.0, f"rsi_14 out of range: {rsi}"
    assert rsi != 50.0, f"rsi_14 is the hardcoded 50.0 fallback: {rsi}"
