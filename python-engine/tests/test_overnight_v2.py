"""[OV2 2026-11-04] ON_V2 overnight shadow (two halves, night screen, official-close entry)
and the read-only post-close liquidity probe."""
import sqlite3
from datetime import timedelta
from types import SimpleNamespace

import pytest

import edge_overnight_paper as eop
from config import settings
from penny_risk import calc_penny_costs
from tests.test_edge_overnight_paper import HISTORY, NEXT, TODAY, _at, _quote


def _night_cache(tmp_path, opens: dict) -> str:
    """Flat closes at 20.0; each ticker opens at ``opens[ticker]`` every cached session."""
    path = tmp_path / "cache.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE ohlcv_cache (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, "
                     "close REAL, volume REAL, PRIMARY KEY (ticker, date))")
        for ticker, o in {**opens, "NIFTYBEES": 20.0}.items():
            conn.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)",
                             [(ticker, d, o, max(o, 20.0) * 1.01, min(o, 20.0) * 0.99, 20.0, 100000.0)
                              for d in HISTORY])
    return str(path)


class _Kite:
    def __init__(self, quotes):
        self.instrument_cache = {"AAA": 1, "BBB": 2, "CCC": 3, "NIFTYBEES": 9}
        self.quotes = quotes
        self.calls = []

    async def get_quote(self, tokens):
        self.calls.append(sorted(tokens))
        names = {v: k for k, v in self.instrument_cache.items()}
        return {t: self.quotes[names[t]] for t in tokens if names[t] in self.quotes}


@pytest.fixture
def v2(tmp_path, monkeypatch):
    picks = [SimpleNamespace(ticker=t, signal_subtype="MO_strong", adjusted_strength=1.0, shares=150)
             for t in ("AAA", "BBB", "CCC")]
    monkeypatch.setattr("penny_edge_live.scan_today", lambda **_k: {"positions": picks, "candidates": picks})
    monkeypatch.setattr(eop, "universe_from_cache", lambda _db: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(settings, "PENNY_EDGE_MAX_POSITIONS", 3)
    cache = _night_cache(tmp_path, {"AAA": 20.2, "BBB": 19.8, "CCC": 20.2})
    quotes = {t: _quote(20.0, 20.2, 19.8, 20.0, 900000.0) for t in ("AAA", "BBB", "CCC", "NIFTYBEES")}
    return SimpleNamespace(cache=cache, kite=_Kite(quotes))


def _rows(cache, variant):
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        return conn.execute("SELECT ticker, shares, entry_price, status, net_pnl, pnl_entry_price, entry_basis, "
                            "night_mean, exit_price FROM edge_overnight_shadow_trades WHERE variant=? "
                            "ORDER BY ticker", (variant,)).fetchall()


def test_night_means_are_causal_shrunk_and_end_at_todays_open(tmp_path):
    cache = _night_cache(tmp_path, {"AAA": 20.2, "BBB": 19.8})
    got = eop.night_means(cache, ["AAA", "BBB", "ZZZ"], TODAY.isoformat(), {"AAA": 20.0, "BBB": None})
    # AAA: 39 cached nights of +1% and today's open at the last close (0%); 40 nights.
    assert got["AAA"] == pytest.approx((39 * 0.01 / 40) * 40 / 60)
    # BBB: no usable open today, so only the 39 cached nights of -1% count.
    assert got["BBB"] == pytest.approx(-0.01 * 39 / 59)
    assert got["ZZZ"] is None
    # A bar dated today (an intraday cache write) is never read.
    with sqlite3.connect(cache) as conn:
        conn.execute("INSERT INTO ohlcv_cache VALUES ('AAA', ?, 40.0, 40.0, 40.0, 40.0, 1.0)", (TODAY.isoformat(),))
    assert eop.night_means(cache, ["AAA"], TODAY.isoformat(), {"AAA": 20.0})["AAA"] == pytest.approx(got["AAA"])


@pytest.mark.asyncio
async def test_on_v2_takes_two_equal_halves_of_the_screened_picks(v2):
    summary = await eop.run_overnight_entry(v2.kite, v2.cache, now=_at(TODAY, 15, 20))
    assert [o["ticker"] for o in summary["opened"]] == ["AAA", "BBB", "CCC"]      # the book is unchanged
    rows = _rows(v2.cache, "ON_V2")
    assert [r[0] for r in rows] == ["AAA", "CCC"]                                 # BBB's nights are negative
    for _t, shares, price, status, *_rest, night, _x in rows:
        assert status == "OPEN" and night > 0.001
        assert settings.EDGE_OVERNIGHT_PAPER_BANKROLL / 2 - 100 < shares * price <= settings.EDGE_OVERNIGHT_PAPER_BANKROLL / 2
    assert summary["shadows"]["ON_V2"]["skipped"] == 1


@pytest.mark.asyncio
async def test_on_v2_books_its_pnl_from_the_official_close(v2):
    await eop.run_overnight_entry(v2.kite, v2.cache, now=_at(TODAY, 15, 20))
    exit_quote = _quote(20.6, 20.8, 20.1, 20.3, 50000.0, NEXT)
    exit_quote["ohlc"]["close"] = 19.9                    # the entry day's official close
    await eop.run_overnight_exit(_Kite({t: exit_quote for t in ("AAA", "BBB", "CCC")}), v2.cache,
                                 now=_at(NEXT, 9, 17))
    rows = _rows(v2.cache, "ON_V2")
    assert rows and all(r[3] == "CLOSED" for r in rows)
    for _t, shares, fill, _s, net, basis_price, basis, _n, exit_price in rows:
        assert (basis_price, basis) == (19.9, "official_close") and fill > 19.9
        assert exit_price == round(20.6 * 0.9995, 4)
        assert net == pytest.approx((exit_price - 19.9) * shares - calc_penny_costs(19.9, exit_price, shares, False),
                                    abs=1e-3)
    # The older shadows keep their fill price.
    two = _rows(v2.cache, "ON_TWO_LARGER")
    assert two and all(r[6] == "fill" and r[5] == r[2] for r in two)
    comparison = eop.overnight_shadow_comparison(v2.cache)
    v2_row = next(s for s in comparison["shadows"] if s["variant"] == "ON_V2")
    assert v2_row["since"] == TODAY.isoformat() and v2_row["entry_basis_counts"] == {"official_close": 2}
    assert v2_row["config"] == {"slots": 2, "fill_cash_share": True, "max_entry_cost_pct": None,
                                "night_min": 0.001, "entry_basis": "official_close", "hi_first": False,
                                "filler": None}
    assert v2_row["book_same_nights"]["closed"] == 3


@pytest.mark.asyncio
async def test_on_v2_keeps_the_fill_when_the_close_is_not_the_entry_days(v2):
    await eop.run_overnight_entry(v2.kite, v2.cache, now=_at(TODAY, 15, 20))
    later = NEXT + timedelta(days=1)                      # a whole session was missed
    late_quote = _quote(20.6, 20.8, 20.1, 20.3, 50000.0, later)
    late_quote["ohlc"]["close"] = 19.0                    # NEXT's close, not the entry day's
    await eop.run_overnight_exit(_Kite({t: late_quote for t in ("AAA", "BBB", "CCC")}), v2.cache,
                                 now=_at(later, 9, 17))
    for _t, shares, fill, status, net, basis_price, basis, _n, exit_price in _rows(v2.cache, "ON_V2"):
        assert status == "CLOSED" and (basis_price, basis) == (fill, "fill_fallback")
        assert net == pytest.approx((exit_price - fill) * shares - calc_penny_costs(fill, exit_price, shares, False),
                                    abs=1e-3)


@pytest.mark.asyncio
async def test_postclose_probe_measures_the_session_and_never_repeats(v2):
    await eop.run_overnight_entry(v2.kite, v2.cache, now=_at(TODAY, 15, 20))
    assert (await eop.run_postclose_probe(v2.kite, "CLOSE", v2.cache, now=_at(TODAY, 15, 25)))["status"] == "outside_window"
    first = await eop.run_postclose_probe(v2.kite, "CLOSE", v2.cache, now=_at(TODAY, 15, 32))
    assert first["tickers"] == 3 and first["quoted"] == 3
    assert (await eop.run_postclose_probe(v2.kite, "CLOSE", v2.cache, now=_at(TODAY, 15, 33)))["repeat"] is True
    after = {t: dict(q) for t, q in v2.kite.quotes.items()}
    after["AAA"]["volume"] = 900000.0 + 1000.0            # 1,000 shares traded in the post-close session
    calls = len(v2.kite.calls)
    await eop.run_postclose_probe(_Kite(after), "POST", v2.cache, now=_at(TODAY, 16, 3))
    assert len(v2.kite.calls) == calls                    # the probe used only its own quote batch
    with sqlite3.connect(eop.overnight_db_path(v2.cache)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM edge_overnight_postclose_probe").fetchone()[0] == 6
        summary = eop.postclose_probe_summary(conn, 12500.0)
    assert summary["pairs"] == 3 and summary["traded_share"] == pytest.approx(1 / 3, abs=1e-3)
    assert summary["median_value"] == 0.0 and summary["covers_ticket_share"] == pytest.approx(1 / 3, abs=1e-3)
    probe = eop.overnight_shadow_comparison(v2.cache)["postclose_probe"]
    assert probe["pairs"] == 3 and probe["ticket"] == settings.EDGE_OVERNIGHT_PAPER_BANKROLL / 2


@pytest.mark.asyncio
async def test_postclose_probe_without_an_entry_receipt_quotes_nothing(v2):
    out = await eop.run_postclose_probe(v2.kite, "CLOSE", v2.cache, now=_at(TODAY, 15, 32))
    assert out["tickers"] == 0 and v2.kite.calls == []

