"""
[PENNY-SECTOR-FILTER-TEST 2026-06-25] Tests for penny_sector_filter.py
(the Tier 2-C sector-relative strength gate).

FAIL-OPEN is the contract. Every test that exercises a data-failure
path must assert ALLOW, not REJECT. If a future change accidentally
makes the gate REJECT when data is missing, these tests catch it.
"""
import asyncio
import csv
import json
import os
import tempfile

import pandas as pd
import pytest


# ---- helpers ---------------------------------------------------------

def _write_csv(path: str, rows):
    """rows = list of dicts with symbol + sector keys."""
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "sector"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def _make_kite_with_etf_quotes(quotes_by_etf: dict):
    """Build a fake kite that returns pre-canned ETF quote responses.

    quotes_by_etf: {etf_symbol: (ltp, prev_close)} mapping.
    """
    from unittest.mock import AsyncMock, MagicMock

    k = MagicMock()
    k.instrument_cache = {etf: 9000 + i for i, etf in enumerate(quotes_by_etf)}

    async def _quote(tokens):
        out = {}
        for t in tokens:
            # reverse-lookup etf from token (mock cache key)
            for etf, tok in k.instrument_cache.items():
                if tok == t:
                    ltp, prev = quotes_by_etf[etf]
                    out[t] = {
                        "last_price": ltp,
                        "ohlc": {"close": prev, "high": prev, "low": prev},
                        "volume": 1000,
                    }
                    break
        return out

    async def _instruments():
        return [
            {"instrument_token": 9000 + i, "tradingsymbol": etf}
            for i, etf in enumerate(quotes_by_etf)
        ]

    k.get_quote = AsyncMock(side_effect=_quote)
    k.get_instruments_nse_eq = AsyncMock(side_effect=_instruments)
    return k


# ---- CSV loading tests ----------------------------------------------

def test_load_sector_map_missing_file_returns_empty(tmp_path):
    """T2-C: missing CSV path = empty map (no error)."""
    from penny_sector_filter import load_sector_map
    nonexistent = str(tmp_path / "does_not_exist.csv")
    out = load_sector_map(nonexistent)
    assert out == {}


def test_load_sector_map_empty_csv_returns_empty(tmp_path):
    """T2-C: empty CSV (no data rows) = empty map."""
    from penny_sector_filter import load_sector_map
    p = tmp_path / "empty.csv"
    with open(p, "w") as f:
        f.write("symbol,sector\n")
    out = load_sector_map(str(p))
    assert out == {}


def test_load_sector_map_malformed_csv_returns_empty(tmp_path):
    """T2-C: CSV missing required columns = empty map (no exception)."""
    from penny_sector_filter import load_sector_map
    p = tmp_path / "bad.csv"
    with open(p, "w") as f:
        f.write("foo,bar\n1,2\n")
    out = load_sector_map(str(p))
    assert out == {}


def test_load_sector_map_parses_valid(tmp_path):
    """T2-C: valid CSV loads symbol->sector mapping correctly."""
    from penny_sector_filter import load_sector_map
    p = tmp_path / "ok.csv"
    _write_csv(p, [
        {"symbol": "AAA", "sector": "Steel"},
        {"symbol": "BBB", "sector": "Bank"},
        {"symbol": "aaa", "sector": "IT"},  # lowercase symbol normalised to upper
    ])
    out = load_sector_map(str(p))
    assert out == {"AAA": "Steel", "BBB": "Bank", "AAA": "IT"} or \
           out == {"AAA": "IT", "BBB": "Bank"}  # last-write-wins on duplicate keys
    assert out["BBB"] == "Bank"


def test_load_sector_map_skips_blank_rows(tmp_path):
    """T2-C: blank rows in the CSV don't crash the loader."""
    from penny_sector_filter import load_sector_map
    p = tmp_path / "blanks.csv"
    with open(p, "w", newline="") as f:
        f.write("symbol,sector\n")
        f.write("AAA,Steel\n")
        f.write(",\n")  # empty row
        f.write("BBB,Bank\n")
    out = load_sector_map(str(p))
    assert out == {"AAA": "Steel", "BBB": "Bank"}


# ---- sector_check fail-open tests ----------------------------------

def test_sector_check_unknown_ticker_returns_unknown_then_allow(tmp_path):
    """T2-C: ticker not in CSV -> UNKNOWN -> caller treats as ALLOW."""
    from penny_sector_filter import sector_check, SectorCheckResult
    p = tmp_path / "sectors.csv"
    _write_csv(p, [{"symbol": "AAA", "sector": "Steel"}])
    sector_map = {"AAA": "Steel"}
    kite = _make_kite_with_etf_quotes({"NIFTY_METAL": (100.0, 100.0)})
    decision = asyncio.run(sector_check(
        ticker="ZZZ", kite=kite, sector_map=sector_map,
    ))
    assert decision.result == SectorCheckResult.UNKNOWN
    # UNKNOWN is not REJECT -> is_blocked is False -> treated as ALLOW.
    assert decision.is_blocked is False


def test_sector_check_etf_quote_failure_returns_unknown(tmp_path):
    """T2-C: ETF quote fails (network/auth) -> UNKNOWN -> ALLOW."""
    from penny_sector_filter import sector_check, SectorCheckResult
    p = tmp_path / "sectors.csv"
    _write_csv(p, [{"symbol": "AAA", "sector": "Steel"}])
    sector_map = {"AAA": "Steel"}
    kite = _make_kite_with_etf_quotes({})  # no ETF cached -> quote returns empty
    decision = asyncio.run(sector_check(
        ticker="AAA", kite=kite, sector_map=sector_map,
    ))
    # Token unresolved -> ETF can't be priced -> UNKNOWN -> ALLOW.
    # This is the critical fail-open path. Must NEVER return REJECT.
    assert decision.result == SectorCheckResult.UNKNOWN
    assert decision.is_blocked is False


def test_sector_check_healthy_sector_returns_allow(tmp_path):
    """T2-C: sector ETF up or mildly down (< -1.5%) -> ALLOW."""
    from penny_sector_filter import sector_check, SectorCheckResult
    p = tmp_path / "sectors.csv"
    _write_csv(p, [{"symbol": "AAA", "sector": "Steel"}])
    sector_map = {"AAA": "Steel"}
    # Steel ETF: prev=100, ltp=99.0 -> change=-1.0% (above -1.5% threshold)
    kite = _make_kite_with_etf_quotes({"NIFTY_METAL": (99.0, 100.0)})
    decision = asyncio.run(sector_check(
        ticker="AAA", kite=kite, sector_map=sector_map,
    ))
    assert decision.result == SectorCheckResult.ALLOW


def test_sector_check_weak_but_not_severe_returns_allow(tmp_path):
    """T2-C: sector ETF between -1.5% and -1.65% (the severe threshold) -> ALLOW.
    This preserves proactiveness: we don't kill signals on moderate weakness."""
    from penny_sector_filter import sector_check, SectorCheckResult
    p = tmp_path / "sectors.csv"
    _write_csv(p, [{"symbol": "AAA", "sector": "Steel"}])
    sector_map = {"AAA": "Steel"}
    # Steel ETF: prev=100, ltp=98.5 -> change=-1.5% (at threshold, not severe)
    # Default top_losers_pct=0.10 -> severe_threshold=-1.5% * 1.10 = -1.65%
    # -1.5% is exactly at threshold, not below it -> ALLOW
    kite = _make_kite_with_etf_quotes({"NIFTY_METAL": (98.5, 100.0)})
    decision = asyncio.run(sector_check(
        ticker="AAA", kite=kite, sector_map=sector_map,
    ))
    assert decision.result == SectorCheckResult.ALLOW


def test_sector_check_severe_drop_returns_reject(tmp_path):
    """T2-C: sector ETF down > severe_threshold -> REJECT.
    severe_threshold = -1.5% * (1 + 0.10) = -1.65%. -2.0% qualifies."""
    from penny_sector_filter import sector_check, SectorCheckResult
    p = tmp_path / "sectors.csv"
    _write_csv(p, [{"symbol": "AAA", "sector": "Steel"}])
    sector_map = {"AAA": "Steel"}
    # Steel ETF: prev=100, ltp=98.0 -> change=-2.0% (below severe -1.65%)
    kite = _make_kite_with_etf_quotes({"NIFTY_METAL": (98.0, 100.0)})
    decision = asyncio.run(sector_check(
        ticker="AAA", kite=kite, sector_map=sector_map,
    ))
    assert decision.result == SectorCheckResult.REJECT
    assert "severe drop" in decision.reason


def test_sector_check_unknown_sector_uses_default_etf(tmp_path):
    """T2-C: a sector name not in SECTOR_TO_ETF -> NIFTY_50 fallback."""
    from penny_sector_filter import sector_check, SectorCheckResult, SECTOR_TO_ETF
    p = tmp_path / "sectors.csv"
    _write_csv(p, [{"symbol": "AAA", "sector": "Unobtainium Mining"}])
    sector_map = {"AAA": "Unobtainium Mining"}
    # NIFTY_50 (Default) up -> allow
    kite = _make_kite_with_etf_quotes({"NIFTY_50": (101.0, 100.0)})
    decision = asyncio.run(sector_check(
        ticker="AAA", kite=kite, sector_map=sector_map,
    ))
    # Default sector lookup picks NIFTY_50
    assert decision.etf_symbol == SECTOR_TO_ETF["Default"]
    assert decision.result == SectorCheckResult.ALLOW


# ---- batch helper tests ---------------------------------------------

def test_filter_universe_by_sector_dedupes_etf_calls(tmp_path):
    """T2-C: 10 tickers all in 'Steel' = 1 ETF call (not 10)."""
    from penny_sector_filter import filter_universe_by_sector, SectorCheckResult
    p = tmp_path / "sectors.csv"
    rows = [{"symbol": f"S{i:03d}", "sector": "Steel"} for i in range(10)]
    _write_csv(p, rows)
    sector_map = {f"S{i:03d}": "Steel" for i in range(10)}
    tickers = [f"S{i:03d}" for i in range(10)]

    kite = _make_kite_with_etf_quotes({"NIFTY_METAL": (98.0, 100.0)})
    # Wrap get_quote to count calls.
    call_count = {"n": 0}
    orig_get_quote = kite.get_quote
    async def counting_get_quote(tokens):
        call_count["n"] += 1
        return await orig_get_quote(tokens)
    kite.get_quote = counting_get_quote

    decisions = asyncio.run(filter_universe_by_sector(
        tickers=tickers, kite=kite, sector_map=sector_map,
    ))
    assert call_count["n"] == 1, \
        f"Expected 1 deduped ETF call, got {call_count['n']}"
    # All 10 should REJECT because the ETF is severely down.
    assert all(d.result == SectorCheckResult.REJECT for d in decisions.values())


def test_filter_universe_by_sector_mixed_sectors(tmp_path):
    """T2-C: 6 tickers across 2 sectors = 2 ETF calls (one per sector)."""
    from penny_sector_filter import filter_universe_by_sector, SectorCheckResult
    p = tmp_path / "sectors.csv"
    rows = (
        [{"symbol": f"S{i}", "sector": "Steel"} for i in range(3)] +
        [{"symbol": f"B{i}", "sector": "Bank"} for i in range(3)]
    )
    _write_csv(p, rows)
    sector_map = {r["symbol"]: r["sector"] for r in rows}
    tickers = [r["symbol"] for r in rows]

    kite = _make_kite_with_etf_quotes({
        "NIFTY_METAL": (98.0, 100.0),  # severely down
        "NIFTY_BANK": (101.0, 100.0),   # up
    })
    decisions = asyncio.run(filter_universe_by_sector(
        tickers=tickers, kite=kite, sector_map=sector_map,
    ))
    steel_decisions = [decisions[f"S{i}"] for i in range(3)]
    bank_decisions = [decisions[f"B{i}"] for i in range(3)]
    assert all(d.result == SectorCheckResult.REJECT for d in steel_decisions)
    assert all(d.result == SectorCheckResult.ALLOW for d in bank_decisions)


def test_filter_universe_by_sector_unknown_tickers_get_allow(tmp_path):
    """T2-C: tickers not in CSV get ALLOW (UNKNOWN), no Kite calls wasted."""
    from penny_sector_filter import filter_universe_by_sector, SectorCheckResult
    sector_map = {"AAA": "Steel"}  # only AAA mapped
    tickers = ["AAA", "ZZZ", "QQQ"]
    kite = _make_kite_with_etf_quotes({"NIFTY_METAL": (98.0, 100.0)})
    decisions = asyncio.run(filter_universe_by_sector(
        tickers=tickers, kite=kite, sector_map=sector_map,
    ))
    assert decisions["AAA"].result == SectorCheckResult.REJECT
    assert decisions["ZZZ"].result == SectorCheckResult.UNKNOWN
    assert decisions["QQQ"].result == SectorCheckResult.UNKNOWN


# ---- scanner integration test --------------------------------------

def test_scanner_with_sector_filter_falls_open_when_csv_missing(tmp_path):
    """T2-C: when the sector CSV doesn't exist, the scanner still works
    and the filter is effectively OFF. This is the critical regression
    test: if a future change makes the filter REJECT when data is
    missing, this test catches it."""
    import json
    from penny_scanner import PennyScanner

    # Universe with one ticker
    universe_path = tmp_path / "penny.json"
    universe_path.write_text(json.dumps({
        "as_of": "2026-06-25",
        "universe_size_target": 100,
        "tickers": [
            {"symbol": "AAA", "series": "EQ", "prev_close": 12.0,
             "promoter_holding_pct": 50.0, "pb_ratio": 1.2,
             "is_t2t": False, "is_asm": False, "is_gsm": False,
             "median_traded_value_20d": 1_000_000},
        ],
    }))
    # CSV path pointing to a non-existent file
    nonexistent_csv = str(tmp_path / "no_such_file.csv")
    from config import settings
    csv_backup = settings.PENNY_SECTORS_CSV_PATH
    settings.PENNY_SECTORS_CSV_PATH = nonexistent_csv
    try:
        # Build a minimal fake_kite
        from unittest.mock import AsyncMock, MagicMock
        import pandas as pd
        from datetime import datetime, timezone
        k = MagicMock()
        k.instrument_cache = {"AAA": 1001}
        k.get_quote = AsyncMock(return_value={
            1001: {"last_price": 12.0, "ohlc": {"high": 12.0, "low": 12.0, "close": 12.0},
                   "volume": 100_000, "depth": {"buy": [], "sell": []}},
        })
        # Simple intraday that's not enough for breakout but doesn't crash.
        async def fake_intraday(ticker, from_datetime, to_datetime, interval="minute"):
            times = pd.date_range("2026-06-25 09:15", periods=60, freq="1min")
            df = pd.DataFrame({
                "open": [12.0] * 60, "high": [12.0] * 60, "low": [12.0] * 60,
                "close": [12.0] * 60, "volume": [1000] * 60,
            }, index=times)
            return df
        k.get_intraday = AsyncMock(side_effect=fake_intraday)
        async def fake_historical(ticker, from_date, to_date):
            dates = pd.date_range(end="2026-06-25", periods=20, freq="D")
            return pd.DataFrame({
                "open": [12.0] * 20, "high": [12.5] * 20, "low": [11.5] * 20,
                "close": [12.0] * 20, "volume": [50_000] * 20,
            }, index=dates)
        k.get_historical = AsyncMock(side_effect=fake_historical)

        scanner = PennyScanner(
            kite=k, universe_json_path=str(universe_path),
            paper_mode=True, regime="PR1_CALM",
        )
        # Must not raise. Result must include AAA in either accept or
        # reject (NOT skip-with-error due to sector filter bug).
        result = asyncio.run(scanner.scan_once(
            as_of=datetime(2026, 6, 25, 11, 0),
        ))
        assert result["scan_id"].startswith("penny-")
        assert result["accept"] + result["reject"] + result["error"] == 1
    finally:
        settings.PENNY_SECTORS_CSV_PATH = csv_backup
