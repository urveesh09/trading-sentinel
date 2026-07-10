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


# ---- 2026-06-25 observability + reject-counting tests ----------------

def test_scanner_logs_loop_summary_with_universe_size(tmp_paths, fake_kite, fake_universe, caplog):
    """2026-06-25: scan_once logs penny_scan_loop_summary with eligible
    count at the start so silent-empty-eligible scenarios surface."""
    import logging
    from penny_scanner import PennyScanner
    scanner = PennyScanner(
        kite=fake_kite, universe_json_path=fake_universe,
        paper_mode=True, regime="PR1_CALM",
    )
    caplog.set_level(logging.INFO, logger="penny_scanner")
    asyncio.run(scanner.scan_once(as_of=datetime(2026, 6, 21, 11, 0)))
    summary_lines = [r.message for r in caplog.records
                     if "penny_scan_loop_summary" in r.message]
    assert len(summary_lines) >= 1
    # Must mention eligible count
    assert "eligible=3" in summary_lines[0]


def test_scanner_logs_warning_when_no_eligible_universe(tmp_paths, fake_kite, tmp_path, caplog):
    """2026-06-25: when the universe JSON produces zero eligible tickers
    (e.g. all tickers fail a hard gate like out-of-band price or BE series),
    the scanner now logs penny_scan_no_eligible_universe at WARN level.

    Note: post-2026-06-25 null-tolerance, an all-null corp-data universe
    IS eligible (passes with quality flag). To force zero eligible we
    use out-of-band price (0.5) which the price-band gate hard-rejects."""
    import json
    import logging
    # All tickers below PENNY_PRICE_MIN (1.0) -> hard reject, not null-tolerance
    payload = {
        "as_of": "2026-06-25",
        "universe_size_target": 100,
        "tickers": [
            {"symbol": "X1", "series": "EQ", "prev_close": 0.5,
             "promoter_holding_pct": 50.0, "pb_ratio": 1.2,
             "is_t2t": False, "is_asm": False, "is_gsm": False,
             "median_traded_value_20d": 1_000_000},
            {"symbol": "X2", "series": "EQ", "prev_close": 0.8,
             "promoter_holding_pct": 60.0, "pb_ratio": 1.5,
             "is_t2t": False, "is_asm": False, "is_gsm": False,
             "median_traded_value_20d": 2_000_000},
        ],
    }
    p = tmp_path / "all_oob_penny.json"
    p.write_text(json.dumps(payload))
    fake_kite.instrument_cache = {"X1": 9999, "X2": 9998}

    from penny_scanner import PennyScanner
    scanner = PennyScanner(
        kite=fake_kite, universe_json_path=str(p),
        paper_mode=True, regime="PR1_CALM",
    )
    # [PENNY-STARTUP-GATE 2026-07-02] This test seeds only 2
    # instrument_cache entries to make a small universe. The new
    # startup-gate waits for >=100 by default; lower the threshold
    # so the test exercises the empty-eligible-universe path, not
    # the startup-gate timeout path.
    scanner.instrument_cache_min_count = 1
    caplog.set_level(logging.WARNING, logger="penny_scanner")
    asyncio.run(scanner.scan_once(as_of=datetime(2026, 6, 21, 11, 0)))
    warn_lines = [r.message for r in caplog.records
                  if "penny_scan_no_eligible_universe" in r.message]
    assert len(warn_lines) >= 1, \
        "Scanner did not WARN about empty eligible universe -- silent-empty regression!"


def test_scanner_none_decision_counts_as_reject_not_error(tmp_paths, fake_kite, fake_universe):
    """2026-06-25: when _evaluate_ticker_breakout returns None (e.g.
    silent data-fetch failure), it now counts as reject + logs a
    penny_eval_skipped warn -- not as a silent error."""
    from unittest.mock import AsyncMock
    fake_kite.get_quote = AsyncMock(return_value={})  # empty quote -> _get_quote_safe returns None -> None decision
    from penny_scanner import PennyScanner
    scanner = PennyScanner(
        kite=fake_kite, universe_json_path=fake_universe,
        paper_mode=True, regime="PR1_CALM",
    )
    result = asyncio.run(scanner.scan_once(as_of=datetime(2026, 6, 21, 11, 0)))
    # Each of 3 tickers should be a reject (None decision now -> reject)
    assert result["reject"] == 3, \
        f"Expected reject=3 for None-decision tickers, got {result}"
    assert result["accept"] == 0
    assert result["error"] == 0, \
        f"Expected error=0 (None decisions are not errors anymore), got {result}"


def test_scanner_logs_eval_skipped_when_quote_unavailable(tmp_paths, fake_kite, fake_universe, caplog):
    """2026-06-25: silent None-return in _evaluate_ticker_breakout now
    emits penny_eval_skipped with the specific reason."""
    import logging
    from unittest.mock import AsyncMock
    fake_kite.get_quote = AsyncMock(return_value={})  # empty
    from penny_scanner import PennyScanner
    scanner = PennyScanner(
        kite=fake_kite, universe_json_path=fake_universe,
        paper_mode=True, regime="PR1_CALM",
    )
    caplog.set_level(logging.INFO, logger="penny_scanner")
    asyncio.run(scanner.scan_once(as_of=datetime(2026, 6, 21, 11, 0)))
    skipped = [r.message for r in caplog.records if "penny_eval_skipped" in r.message]
    assert len(skipped) >= 1, \
        f"Expected penny_eval_skipped lines, got: {[r.message for r in caplog.records]}"
    # At least one should have reason=quote_unavailable
    assert any("reason=quote_unavailable" in m for m in skipped)


def test_scanner_handles_string_valued_instrument_cache(tmp_paths, fake_kite, fake_universe, caplog):
    """[INSTRUMENT-CACHE-INT 2026-07-03] Today's prod bug:
    `kite.instrument_cache[symbol] = parts[0]` stored the raw CSV
    cell (a str). `KiteClient.get_quote` returns a dict keyed by int
    (`{int(k): v for k, v in data.items()}`). `_get_quote_safe`
    looked up `quotes.get(token)` where `token` was a str -- silently
    returning None for every ticker.

    Pre-fix: 100% of penny tickers logged `quote_unavailable` even
    though the cache was full and `get_quote` was returning real
    data. Scanner's `accept` and `reject` counts never reflected
    reality.

    Post-fix `_get_quote_safe` coerces `token` to int before the
    lookup, so this test (with a STR-valued cache mirroring the prod
    bug) must still get quotes through and evaluate tickers
    normally -- producing a non-zero total (accept + reject + error
    = universe size).
    """
    import logging
    from unittest.mock import AsyncMock
    import pandas as pd

    # Mirror the prod bug: cache values are str (e.g. "1001").
    fake_kite.instrument_cache = {
        "AAA": "1001", "BBB": "1002", "CCC": "1003",
    }
    # /quote response is keyed by int -- the int/str mismatch is the
    # entire point of this test.
    fake_kite.get_quote = AsyncMock(return_value={
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

    from penny_scanner import PennyScanner
    scanner = PennyScanner(
        kite=fake_kite, universe_json_path=fake_universe,
        paper_mode=True, regime="PR1_CALM",
    )
    caplog.set_level(logging.INFO, logger="penny_scanner")
    result = asyncio.run(scanner.scan_once(as_of=datetime(2026, 6, 21, 11, 0)))

    # Every universe ticker should have produced an outcome.
    # Pre-fix this would be `total=0` because every `_get_quote_safe`
    # returned None for the str->int lookup miss, and the scanner
    # counted each as "the universe returned None -> reject=0
    # error=0 total=0" via the early scan_no_eligible_universe
    # short-circuit (only when universe was truly empty; here it
    # wasn't, so each eval hit the `if not q: skip` branch silently).
    total = result["accept"] + result["reject"] + result["error"]
    assert total == 3, (
        f"Expected total=3 outcomes (universe size), got {result}. "
        f"If total=0 with full universe, `_get_quote_safe` is still "
        f"missing the int-coercion and penny scans are silently "
        f"empty. [INSTRUMENT-CACHE-INT 2026-07-03]"
    )
    # None of the reasons should be `quote_unavailable` for ALL
    # tickers -- at most a couple if a specific intraday fixture is
    # missing, but never 3/3 (would re-confirm the bug).
    skipped_msgs = [r.message for r in caplog.records if "penny_eval_skipped" in r.message]
    quote_unavail = [m for m in skipped_msgs if "reason=quote_unavailable" in m]
    assert len(quote_unavail) < 3, (
        f"`quote_unavailable` fired {len(quote_unavail)}/3 times with a "
        f"populated cache and returning get_quote -- the str/int "
        f"mismatch is still present. [INSTRUMENT-CACHE-INT 2026-07-03]"
    )
    # The scanner must have actually called get_quote covering each token.
    # Pre-fix the call would have been made (cache resolved) but the
    # dict-lookup at the consumer would have failed. Post-fix the
    # call still happens and the response is used.
    # [FIX-PHASE3-AUDIT 2026-07-09] scan_once now batch-prefetches all
    # quotes in ONE get_quote call (Kite allows 500 instruments per
    # request) instead of one call per ticker, so we assert on the union
    # of tokens requested across all calls -- and that every requested
    # token was coerced to int (the original str/int regression).
    assert fake_kite.get_quote.await_count >= 1, (
        f"Expected at least one get_quote call, got "
        f"{fake_kite.get_quote.await_count}. If 0, the cache lookup "
        f"`token is None` branch fired instead, meaning the cache is "
        f"still str-keyed. [INSTRUMENT-CACHE-INT 2026-07-03]"
    )
    requested_tokens = set()
    for call in fake_kite.get_quote.await_args_list:
        arg = call.args[0] if call.args else call.kwargs.get("tokens")
        if isinstance(arg, (list, tuple, set)):
            requested_tokens.update(arg)
        else:
            requested_tokens.add(arg)
    assert {1001, 1002, 1003} <= {int(t) for t in requested_tokens}, (
        f"Expected all three universe tokens requested via get_quote, got "
        f"{requested_tokens}. The str-keyed cache regression may be back. "
        f"[INSTRUMENT-CACHE-INT 2026-07-03]"
    )
    assert all(isinstance(t, int) for t in requested_tokens), (
        f"get_quote must be called with int tokens (str tokens miss the "
        f"int-keyed /quote response dict): {requested_tokens}"
    )


# ---- 2026-06-25 Phase 3 tests (G9) ---------------------------------

def test_scanner_evaluates_in_parallel_via_gather(tmp_paths, fake_kite, fake_universe):
    """G9: scan_once now uses asyncio.gather internally. We can't directly
    assert parallelism (it depends on the event loop), but we CAN verify
    that the scanner still produces the same accept/reject counts as
    before the refactor -- ensuring correctness was preserved while
    gaining the speedup."""
    from penny_scanner import PennyScanner
    scanner = PennyScanner(
        kite=fake_kite, universe_json_path=fake_universe,
        paper_mode=True, regime="PR1_CALM",
    )
    result = asyncio.run(scanner.scan_once(as_of=datetime(2026, 6, 21, 11, 0)))
    # With the fake_kite fixture (3 tickers, all with neutral price data),
    # the breakout engine produces a reject for each (price < required
    # breakout level). The exact count doesn't matter; what matters is
    # the loop processed all 3 tickers without crashing and the sum
    # matches the universe size.
    total = result["accept"] + result["reject"] + result["error"]
    assert total == 3, f"expected 3 ticker outcomes, got {result}"


def test_scanner_gather_handles_per_ticker_exceptions(tmp_paths, fake_kite, fake_universe):
    """G9: with return_exceptions=True, a single ticker raising an
    exception does NOT abort the whole scan -- other tickers still
    complete and the failing one is counted as error."""
    import penny_scanner as ps_module
    from penny_scanner import PennyScanner

    # Patch _evaluate_ticker_breakout so BBB raises but others succeed.
    real_eval = PennyScanner._evaluate_ticker_breakout

    async def selective_eval(self, ticker, as_of, **kwargs):
        if ticker == "BBB":
            raise RuntimeError("simulated Kite 500")
        return await real_eval(self, ticker, as_of, **kwargs)

    ps_module.PennyScanner._evaluate_ticker_breakout = selective_eval
    try:
        scanner = PennyScanner(
            kite=fake_kite, universe_json_path=fake_universe,
            paper_mode=True, regime="PR1_CALM",
        )
        result = asyncio.run(scanner.scan_once(as_of=datetime(2026, 6, 21, 11, 0)))
        # BBB counted as error; AAA and CCC should be either accept or reject.
        assert result["error"] == 1, f"BBB should be error=1, got {result}"
        total = result["accept"] + result["reject"] + result["error"]
        assert total == 3
    finally:
        ps_module.PennyScanner._evaluate_ticker_breakout = real_eval
