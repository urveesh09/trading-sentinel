"""[SV3 2026-11-04] Smart V3 paper book: opening-auction reversal. Paper only, no orders."""
import sqlite3
from datetime import date, datetime, timedelta

import pytest

import penny_smart_v3 as sv3
from config import settings
from penny_risk import calc_penny_costs

IST = sv3.IST
D1, D2 = "2026-11-02", "2026-11-03"          # Monday, Tuesday
NAMES = ("AAA", "BBB", "CCC", "DDD")


def _history(before: str, n: int = 25) -> list[str]:
    out, d = [], date.fromisoformat(before)
    while len(out) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            out.append(d.isoformat())
    return sorted(out)


def _cache(tmp_path) -> str:
    path = tmp_path / "cache.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE ohlcv_cache (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, "
                     "close REAL, volume REAL, PRIMARY KEY (ticker, date))")
        for t in NAMES:
            conn.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)",
                             [(t, d, 20.0, 20.2, 19.8, 20.0, 100000.0) for d in _history(D1)])
    return str(path)


def _q(last, *, open_=None, close=20.0, low=None, volume=50000.0, bid=None, lc=None):
    q = {"last_price": last, "ohlc": {"open": open_ or 0, "high": max(last, open_ or last), "low": low or min(last, open_ or last),
                                     "close": close}, "volume": volume, "buy_quantity": 1000, "sell_quantity": 5000}
    if bid is not None:
        q["depth"] = {"buy": [{"price": bid, "quantity": 500}], "sell": []}
    if lc is not None:
        q["lower_circuit_limit"] = lc
    return q


class _Kite:
    def __init__(self):
        self.instrument_cache = {t: i + 1 for i, t in enumerate(NAMES)}
        self.quotes = {}

    async def get_quote(self, tokens):
        names = {v: k for k, v in self.instrument_cache.items()}
        return {t: self.quotes[names[t]] for t in tokens if names[t] in self.quotes}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(sv3, "universe", lambda _kite: list(NAMES))
    monkeypatch.setattr(settings, "PENNY_SMART_V3_BANKROLL", 2000.0)
    return _cache(tmp_path), _Kite()


def _at(day: str, hh: int, mm: int) -> datetime:
    return datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:00").replace(tzinfo=IST)


def _rows(cache, variant):
    with sqlite3.connect(sv3.store_path(cache)) as conn:
        return conn.execute("SELECT trade_date, ticker, status, entry_price, shares, exit_price, exit_basis, net_pnl, "
                            "refusal, limit_price FROM sv3_trades WHERE variant=? ORDER BY trade_date, ticker",
                            (variant,)).fetchall()


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_select_deepest_gap_eq_band_value_and_thin():
    C = sv3.Candidate
    cands = [C("AAA-BE", 20, 18.0, 2e6, 1e5), C("BIG", 60, 50.0, 2e6, 1e5), C("SMALLGAP", 20, 19.8, 2e6, 1e5),
             C("THINV", 20, 18.0, 4e5, 1e5), C("GOLDBEES", 20, 18.0, 2e6, 1e5),
             C("DEEP", 20, 18.6, 2e6, 1e5), C("DEEPER", 20, 18.2, 2e6, 1e5), C("OK", 20, 19.5, 2e6, 1e5)]
    picks, refused = sv3.select(cands, capital=2000.0, thin={"DEEP": 1e5, "DEEPER": 1e5, "OK": 1e5})
    assert [p.ticker for p in picks] == ["DEEPER"]
    # DEEPER is too thin for the ticket: skipped without using the slot, the next deepest is taken
    picks, refused = sv3.select(cands, capital=2000.0, thin={"DEEP": 1e5, "DEEPER": 100.0, "OK": 1e5})
    assert [p.ticker for p in picks] == ["DEEP"] and refused == {"DEEPER": "thin_auction"}


def test_thin_estimate_history_then_daily_share():
    assert sv3.thin_estimate([10, 20, 30, 40, 50], 1e5) == (30.0, "first_minute_history")
    assert sv3.thin_estimate([10, 20], 1e5) == (800.0, "daily_share")
    assert sv3.fill_shares(100, 2000) == 100 and sv3.fill_shares(100, 200) == 0 and sv3.fill_shares(100, 400) == 40


def test_preopen_decides_and_open_fills_at_the_official_open(env):
    cache, kite = env
    kite.quotes = {"AAA": _q(19.0), "BBB": _q(19.6), "CCC": _q(20.0)}          # pre-open: AAA -5%, BBB -2%
    s = _run(sv3.run_preopen(kite, cache, _at(D1, 9, 7)))
    assert s["picks"] == ["AAA"] and s["indicative_moved"] == 2
    kite.quotes = {"AAA": _q(19.2, open_=19.1), "BBB": _q(19.1, open_=19.0), "CCC": _q(20.0, open_=20.0)}
    s = _run(sv3.run_open(kite, cache, _at(D1, 9, 16)))
    pre = _rows(cache, "SV3_PREOPEN")
    assert pre == [(D1, "AAA", "OPEN", 19.1, int(2000 // 19.1), None, None, None, None, 19.19)]
    ref = _rows(cache, "SV3_REF")          # the reference decides on the official opens: BBB -5% is deepest
    assert [(r[1], r[2], r[3]) for r in ref] == [("BBB", "OPEN", 19.0)]
    assert s["first_minutes"] == 3


def test_open_above_the_limit_or_without_capacity_is_refused(env):
    cache, kite = env
    kite.quotes = {"AAA": _q(19.0), "BBB": _q(19.0)}
    _run(sv3.run_preopen(kite, cache, _at(D1, 9, 7)))
    kite.quotes = {"AAA": _q(19.5, open_=19.5), "BBB": _q(19.5, open_=19.5)}
    _run(sv3.run_open(kite, cache, _at(D1, 9, 16)))
    assert _rows(cache, "SV3_PREOPEN")[0][2:3] + _rows(cache, "SV3_PREOPEN")[0][8:9] == ("REFUSED", "open_above_limit")
    # a reference pick whose auction traded too little for a quarter of the ticket is refused
    assert [(r[2], r[8]) for r in _rows(cache, "SV3_REF")] == [("OPEN", None)]
    cache2 = cache + ".b"          # same daily cache, a fresh paper store
    import shutil
    shutil.copy(cache, cache2)
    kite.quotes = {"AAA": _q(19.0, open_=19.0, volume=100.0)}
    _run(sv3.run_open(kite, cache2, _at(D1, 9, 16)))
    assert [(r[2], r[8]) for r in _rows(cache2, "SV3_REF")] == [("REFUSED", "auction_capacity")]


def test_settles_next_session_at_the_official_close_with_intraday_charges(env):
    cache, kite = env
    kite.quotes = {"AAA": _q(19.0)}
    _run(sv3.run_preopen(kite, cache, _at(D1, 9, 7)))
    kite.quotes = {"AAA": _q(19.2, open_=19.1)}
    _run(sv3.run_open(kite, cache, _at(D1, 9, 16)))
    kite.quotes = {"AAA": _q(19.9, open_=19.1, low=19.0, bid=19.85)}
    _run(sv3.run_bid(kite, cache, _at(D1, 15, 15)))
    kite.quotes = {"AAA": _q(20.1, close=20.0)}                    # D2 pre-open: ohlc.close is D1's close
    s = _run(sv3.run_preopen(kite, cache, _at(D2, 9, 7)))
    shares = int(2000 // 19.1)
    want = round((20.0 - 19.1) * shares - calc_penny_costs(19.1, 20.0, shares, is_intraday=True), 4)
    row = _rows(cache, "SV3_PREOPEN")[0]
    assert row[2] == "CLOSED" and row[5] == 20.0 and row[6] == "official_close" and row[7] == pytest.approx(want)
    assert s["settled"][0]["basis"] == "official_close" and s["cash_in_use"] is False
    with sqlite3.connect(sv3.store_path(cache)) as conn:
        bid_net = conn.execute("SELECT bid_net FROM sv3_trades WHERE variant='SV3_PREOPEN'").fetchone()[0]
    assert bid_net == pytest.approx((19.85 - 19.1) * shares - calc_penny_costs(19.1, 19.85, shares, is_intraday=True))
    c = sv3.comparison(cache)
    assert c["variants"]["SV3_PREOPEN"]["closed"] == 1 and c["variants"]["SV3_PREOPEN"]["net_pnl"] == round(want, 2)
    assert c["variants"]["SV3_PREOPEN"]["at_1515_bid"]["closes"] == 1


def test_a_lower_circuit_lock_sells_at_the_next_open_with_delivery_charges(env):
    cache, kite = env
    kite.quotes = {"AAA": _q(19.0)}
    _run(sv3.run_preopen(kite, cache, _at(D1, 9, 7)))
    kite.quotes = {"AAA": _q(19.1, open_=19.1)}
    _run(sv3.run_open(kite, cache, _at(D1, 9, 16)))
    kite.quotes = {"AAA": _q(18.15, open_=19.1, low=18.15, lc=18.15)}             # at the circuit, no bid
    _run(sv3.run_bid(kite, cache, _at(D1, 15, 15)))
    kite.quotes = {"AAA": _q(18.0, close=18.15), "BBB": _q(19.0)}
    s = _run(sv3.run_preopen(kite, cache, _at(D2, 9, 7)))
    assert s["settled"] == [] and s["cash_in_use"] is True and s["picks"] == []   # locked: waits for today's open
    kite.quotes = {"AAA": _q(17.4, open_=17.3, close=18.15), "BBB": _q(19.0, open_=19.0)}
    _run(sv3.run_open(kite, cache, _at(D2, 9, 16)))
    row = [r for r in _rows(cache, "SV3_PREOPEN") if r[0] == D1][0]
    shares = int(2000 // 19.1)
    want = (17.3 - 19.1) * shares - calc_penny_costs(19.1, 17.3, shares, is_intraday=False)
    assert row[2:3] + row[5:7] == ("CLOSED", 17.3, "next_open_locked") and row[7] == pytest.approx(want)


def test_losses_reduce_the_next_days_capital(env):
    cache, kite = env
    with sv3._store(sv3.store_path(cache)) as conn:
        conn.execute("INSERT INTO sv3_trades (variant, trade_date, ticker, status, prev_close, net_pnl) "
                     "VALUES ('SV3_REF', '2026-10-30', 'ZZZ', 'CLOSED', 20, -150), "
                     "('SV3_REF', '2026-10-29', 'YYY', 'CLOSED', 20, 400)")
        assert sv3.capital(conn, "SV3_REF") == 2000.0          # profits withheld
        conn.execute("UPDATE sv3_trades SET net_pnl=-500 WHERE ticker='YYY'")
        assert sv3.capital(conn, "SV3_REF") == pytest.approx(1350.0)


def test_each_phase_runs_once_and_outside_its_window_only_records(env):
    cache, kite = env
    s = _run(sv3.run_preopen(kite, cache, _at(D1, 9, 12)))
    assert s["status"] == "OUTSIDE_WINDOW"
    again = _run(sv3.run_preopen(kite, cache, _at(D1, 9, 7)))
    assert again["repeat"] is True and _rows(cache, "SV3_PREOPEN") == []


def test_first_minute_history_replaces_the_daily_share(env):
    cache, kite = env
    days = [d for d in _history(D1, 6)]
    with sv3._store(sv3.store_path(cache)) as conn:
        conn.executemany("INSERT INTO sv3_first_minute VALUES (?,?,?,?)", [(d, "AAA", 10.0, d) for d in days])
        est, src = sv3.thin_estimates(conn, ["AAA", "BBB"], D1, {"AAA": (2e6, 1e5), "BBB": (2e6, 1e5)})
    assert est == {"AAA": 10.0, "BBB": 800.0} and src == {"AAA": "first_minute_history", "BBB": "daily_share"}


def test_the_switch_and_book_settings():
    assert settings.PENNY_SMART_V3_ENABLED is True and settings.PENNY_SMART_V3_BANKROLL == 2000.0
    assert sv3.VARIANTS == ("SV3_PREOPEN", "SV3_REF") and sv3.SLOTS == 1 and sv3.GAP_MAX == -0.02
