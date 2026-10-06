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


# [EDGE-OVERNIGHT-CATCHUP 2026-10-05] Audit C5/C6.
@pytest.mark.asyncio
async def test_notice_outbox_retries_until_a_send_succeeds(tmp_path, entry_quotes):
    cache = _cache(tmp_path)
    await eop.run_overnight_entry(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 20))
    sent = []

    async def fail(message):
        raise RuntimeError("HTTP 500")

    async def ok(message):
        sent.append(message)

    assert await eop.flush_notices(fail, cache) == 0
    assert await eop.flush_notices(ok, cache) == 1
    assert await eop.flush_notices(ok, cache) == 0                   # sent once
    assert sent[0].startswith(f"EDGE overnight (paper) {TODAY.isoformat()}: bought 1")
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM edge_overnight_paper_trades").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_overlapping_flushes_send_a_notice_once(tmp_path, entry_quotes):
    """[EXPIRY-AUDIT 2026-10-06] Two flushers that read the same unsent row duplicated it."""
    import asyncio

    cache = _cache(tmp_path)
    await eop.run_overnight_entry(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 20))
    sent = []

    async def slow(message):
        await asyncio.sleep(0.01)
        sent.append(message)

    counts = await asyncio.gather(eop.flush_notices(slow, cache), eop.flush_notices(slow, cache))
    assert sorted(counts) == [0, 1] and len(sent) == 1


@pytest.mark.asyncio
async def test_catch_up_late_exit_sells_at_ltp_not_the_missed_auction(tmp_path, entry_quotes):
    cache = _cache(tmp_path)
    await eop.run_overnight_entry(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 20))
    quotes = {"AAA": _quote(20.6, 20.8, 20.1, 20.3, 50000.0, NEXT)}
    assert await eop.catch_up(_Kite(quotes), cache, now=_at(NEXT, 9, 10)) == []    # before the window
    assert await eop.catch_up(_Kite(quotes), cache, now=_at(NEXT, 11, 5)) == ["EXIT"]
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        row = conn.execute("SELECT exit_price, exit_reason, exit_open FROM edge_overnight_paper_trades").fetchone()
    assert row == (round(20.3 * 0.9995, 4), "CATCHUP_LTP", 20.6)
    assert await eop.catch_up(_Kite(quotes), cache, now=_at(NEXT, 11, 10)) == []    # once only


@pytest.mark.asyncio
async def test_catch_up_within_auction_grace_keeps_the_open_price(tmp_path, entry_quotes):
    cache = _cache(tmp_path)
    await eop.run_overnight_entry(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 20))
    quotes = {"AAA": _quote(20.6, 20.8, 20.1, 20.3, 50000.0, NEXT)}
    assert await eop.catch_up(_Kite(quotes), cache, now=_at(NEXT, 9, 40)) == ["EXIT"]
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        assert conn.execute("SELECT exit_reason FROM edge_overnight_paper_trades").fetchone()[0] == "NEXT_OPEN"


@pytest.mark.asyncio
async def test_catch_up_entry_only_before_the_close(tmp_path, entry_quotes):
    cache = _cache(tmp_path)
    assert await eop.catch_up(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 35)) == []
    assert await eop.catch_up(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 25)) == ["ENTRY"]


def test_open_positions_reserve_their_buy_charges_oct6_reproduction(tmp_path, monkeypatch):
    # Oct 6 audit: equity Rs 24,386.2186 after Oct 6 closes; three new picks
    # used Rs 24,364.8752 of premium and their buy charges were not reserved.
    monkeypatch.setattr(settings, "PENNY_BROKERAGE_BYPASS", False)
    store = eop.overnight_db_path(str(tmp_path / "cache.db"))
    picks = (("AAKASH", 8.2305, 990), ("PRAENG", 19.4986, 417), ("VIVOBIOT", 14.2355, 568))
    with eop._store(store) as conn:
        conn.execute("INSERT INTO edge_overnight_paper_trades (trade_date, ticker, kind, strength, entry_ltp, "
                     "entry_price, shares, entry_ts, status, net_pnl) VALUES ('2026-10-05','OLD','MR',1,1,1,1,'x',"
                     "'CLOSED',-613.7814)")
        conn.executemany("INSERT INTO edge_overnight_paper_trades (trade_date, ticker, kind, strength, entry_ltp, "
                         "entry_price, shares, entry_ts, status) VALUES ('2026-10-06',?,'MR',1,?,?,?,'x','OPEN')",
                         [(t, p, p, n) for t, p, n in picks])
        state = eop.book_state(conn, 25000.0)
    charges = sum(eop.buy_charges(p, n) for _, p, n in picks)
    assert state["equity"] == pytest.approx(24386.2186)
    assert charges == pytest.approx(28.931, abs=0.01)
    assert state["reserved_buy_charges"] == pytest.approx(charges)
    # Rebuilt after a restart, the over-admission is visible: -Rs 7.59.
    assert state["cash"] == pytest.approx(24386.2186 - 24364.8752 - charges, abs=1e-3)


def test_buy_charges_exclude_the_sell_side_dp_charge():
    whole = calc_penny_costs(10.0, 0.0, 100, False)
    assert eop.buy_charges(10.0, 100) == pytest.approx(whole - settings.PENNY_CNC_DP_CHARGE, abs=1e-4)
    assert eop.buy_charges(10.0, 0) == 0.0


@pytest.mark.asyncio
async def test_cash_bound_admission_fits_premium_plus_buy_charges(tmp_path, entry_quotes, monkeypatch):
    monkeypatch.setattr(settings, "PENNY_BROKERAGE_BYPASS", False)
    monkeypatch.setattr(settings, "EDGE_OVERNIGHT_PAPER_BANKROLL", 1000.0)
    cache = _cache(tmp_path)
    summary = await eop.run_overnight_entry(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 20))
    opened = summary["opened"][0]
    price, shares = opened["entry_price"], opened["shares"]
    assert opened["buy_charges"] == pytest.approx(eop.buy_charges(price, shares))
    assert price * shares + opened["buy_charges"] <= 1000.0
    assert summary["cash_after"] >= 0
    with eop._store(eop.overnight_db_path(cache)) as conn:
        assert eop.book_state(conn, 1000.0)["cash"] == pytest.approx(summary["cash_after"], abs=1e-3)
