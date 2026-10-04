"""EDGE overnight paper book: 15:20 paper entry on provisional bars, next-open paper exit."""
from datetime import date, datetime, timedelta
import sqlite3

import pytest

import edge_overnight_paper as eop
from config import settings
from penny_risk import calc_penny_costs


def _sessions(end: date, n: int) -> list[str]:
    out, day = [], end
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day -= timedelta(days=1)
    return sorted(out)


TODAY = date(2026, 10, 6)                       # Tuesday
NEXT = date(2026, 10, 7)
HISTORY = _sessions(TODAY - timedelta(days=1), 40)


def _cache(tmp_path, tickers=("AAA", "BBB", "BIG")):
    path = tmp_path / "cache.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE ohlcv_cache (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, "
                     "close REAL, volume REAL, PRIMARY KEY (ticker, date))")
        for ticker in (*tickers, "NIFTYBEES"):
            price = 500.0 if ticker == "BIG" else 20.0
            conn.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)",
                             [(ticker, d, price, price * 1.01, price * 0.99, price, 100000.0) for d in HISTORY])
    return str(path)


def _quote(o, h, l, c, v, day=TODAY):
    return {"ohlc": {"open": o, "high": h, "low": l, "close": 20.0}, "last_price": c, "volume": v,
            "last_trade_time": f"{day.isoformat()} 15:19:58"}


class _Kite:
    def __init__(self, quotes):
        self.instrument_cache = {"AAA": 1, "BBB": 2, "BIG": 3, "NIFTYBEES": 9}
        self.quotes = quotes
        self.calls = []

    async def get_quote(self, tokens):
        self.calls.append(sorted(tokens))
        names = {v: k for k, v in self.instrument_cache.items()}
        return {t: self.quotes[names[t]] for t in tokens if names[t] in self.quotes}


def _at(day, hh, mm):
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=eop.IST)


@pytest.fixture
def entry_quotes():
    # AAA rebounds hard off a deep intraday low on 3x volume (EDGE MR candidate);
    # BBB is quiet. BIG is outside the EDGE price band and is never quoted.
    return {"AAA": _quote(20.0, 20.2, 18.0, 20.0, 300000.0), "BBB": _quote(20.0, 20.1, 19.9, 20.0, 90000.0),
            "NIFTYBEES": _quote(20.0, 20.1, 19.9, 20.0, 100000.0)}


@pytest.mark.asyncio
async def test_entry_scans_provisional_bars_and_opens_once_per_day(tmp_path, entry_quotes):
    cache = _cache(tmp_path)
    kite = _Kite(entry_quotes)
    summary = await eop.run_overnight_entry(kite, cache, now=_at(TODAY, 15, 20))
    assert [o["ticker"] for o in summary["opened"]] == ["AAA"]
    opened = summary["opened"][0]
    assert opened["entry_price"] == pytest.approx(20.0 * 1.0025)
    assert opened["shares"] * opened["entry_price"] <= settings.EDGE_OVERNIGHT_PAPER_BANKROLL
    assert opened["shares"] <= int(0.01 * 20.0 * 300000.0 // opened["entry_price"])
    assert kite.calls == [[1, 2, 9]]                                   # one batch, BIG excluded
    repeat = await eop.run_overnight_entry(kite, cache, now=_at(TODAY, 15, 24))
    assert repeat["repeat"] is True and len(kite.calls) == 1
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM edge_overnight_paper_trades WHERE status='OPEN'").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_exit_sells_at_the_next_opening_auction_with_delivery_costs(tmp_path, entry_quotes):
    cache = _cache(tmp_path)
    entry = await eop.run_overnight_entry(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 20))
    shares, entry_price = entry["opened"][0]["shares"], entry["opened"][0]["entry_price"]
    summary = await eop.run_overnight_exit(_Kite({"AAA": _quote(20.6, 20.8, 20.1, 20.3, 50000.0, NEXT)}),
                                           cache, now=_at(NEXT, 9, 17))
    trade = summary["closed"][0]
    exit_price = round(20.6 * 0.9995, 4)
    assert (trade["exit_price"], trade["reason"]) == (exit_price, "NEXT_OPEN")
    expected = (exit_price - entry_price) * shares - calc_penny_costs(entry_price, exit_price, shares, False)
    assert trade["net_pnl"] == pytest.approx(expected, abs=1e-3)
    assert summary["book"]["equity"] == pytest.approx(settings.EDGE_OVERNIGHT_PAPER_BANKROLL + expected, abs=1e-3)


@pytest.mark.asyncio
async def test_a_ticker_without_a_trade_today_waits_and_is_sold_later(tmp_path, entry_quotes):
    cache = _cache(tmp_path)
    await eop.run_overnight_entry(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 20))
    stale = _quote(20.6, 20.8, 20.1, 20.3, 50000.0, TODAY)            # last trade from yesterday
    first = await eop.run_overnight_exit(_Kite({"AAA": stale}), cache, now=_at(NEXT, 9, 17))
    assert first["closed"] == [] and first["waiting"][0]["ticker"] == "AAA"
    later = NEXT + timedelta(days=1)
    second = await eop.run_overnight_exit(_Kite({"AAA": _quote(21.0, 21.0, 20.5, 20.7, 1.0, later)}),
                                          cache, now=_at(later, 9, 17))
    assert second["closed"][0]["reason"] == "OPEN_DELAYED"


def test_provisional_bar_rejects_stale_inconsistent_or_empty_quotes():
    day = TODAY.isoformat()
    assert eop.provisional_bar(_quote(20.0, 20.2, 18.0, 20.0, 1.0), day) == (20.0, 20.2, 18.0, 20.0, 1.0)
    assert eop.provisional_bar(_quote(20.0, 20.2, 18.0, 20.0, 1.0, NEXT), day) is None
    assert eop.provisional_bar(_quote(20.0, 19.0, 18.0, 20.0, 1.0), day) is None       # close above high
    assert eop.provisional_bar(_quote(20.0, 20.2, 18.0, 20.0, 0.0), day) is None


def test_module_has_no_order_capability():
    import ast
    from pathlib import Path
    tree = ast.parse(Path(eop.__file__).read_text(encoding="utf-8"))
    names = {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
             for alias in node.names}
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not any("executor" in n or "order" in n for n in names | {m or "" for m in modules})
    assert "place_order" not in Path(eop.__file__).read_text(encoding="utf-8")
