"""[OV3 2026-11-04] ON_V3 overnight shadow: ON_V2 plus 20-day-high picks first and plain
overnight (F3) fillers for slots the EDGE picks leave empty. Paper only."""
import sqlite3
from types import SimpleNamespace

import pytest

import edge_overnight_paper as eop
from config import settings
from penny_risk import calc_penny_costs
from tests.test_edge_overnight_paper import HISTORY, NEXT, TODAY, _at, _quote

NAMES = ("AAA", "BBB", "CCC", "DDD", "EEE")


def _night_cache(tmp_path, opens: dict) -> str:
    """Flat closes at 20.0 and 100k volume; each ticker opens at ``opens[ticker]`` every cached session."""
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
        self.instrument_cache = {**{t: i + 1 for i, t in enumerate(NAMES)}, "NIFTYBEES": 9}
        self.quotes = quotes
        self.calls = []

    async def get_quote(self, tokens):
        self.calls.append(sorted(tokens))
        names = {v: k for k, v in self.instrument_cache.items()}
        return {t: self.quotes[names[t]] for t in tokens if names[t] in self.quotes}


def _setup(tmp_path, monkeypatch, opens: dict, quotes: dict, picks=("AAA", "BBB", "CCC")):
    ranked = [SimpleNamespace(ticker=t, signal_subtype="MO_strong", adjusted_strength=1.0, shares=150) for t in picks]
    monkeypatch.setattr("penny_edge_live.scan_today", lambda **_k: {"positions": ranked, "candidates": ranked})
    monkeypatch.setattr(eop, "universe_from_cache", lambda _db: sorted(opens))
    monkeypatch.setattr(settings, "PENNY_EDGE_MAX_POSITIONS", 3)
    cache = _night_cache(tmp_path, opens)
    return cache, _Kite({**quotes, "NIFTYBEES": _quote(20.0, 20.2, 19.8, 20.0, 900000.0)})


def _rows(cache, variant):
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        return conn.execute("SELECT ticker, kind, shares, entry_price, status, net_pnl, pnl_entry_price, "
                            "entry_basis, night_mean, exit_price FROM edge_overnight_shadow_trades "
                            "WHERE variant=? ORDER BY ticker", (variant,)).fetchall()


FLAT = _quote(20.0, 20.2, 19.8, 20.0, 900000.0)            # not at a 20-day high, not a filler
FILLER = _quote(20.0, 21.6, 20.0, 21.2, 300000.0)          # +6%, upper range, 3x volume, below the day high
WEAK = _quote(20.0, 20.4, 19.9, 20.2, 300000.0)            # +1%: not a filler


def test_features_are_causal_and_match_the_night_screen(tmp_path):
    cache = _night_cache(tmp_path, {"AAA": 20.2, "DDD": 20.2})
    bars = {"AAA": (20.0, 20.2, 19.8, 20.0, 900000.0), "DDD": (20.0, 21.6, 20.0, 21.2, 300000.0)}
    got = eop.overnight_features(cache, bars, TODAY.isoformat())
    d = got["DDD"]
    assert d["ret"] == pytest.approx(0.06) and d["clv"] == pytest.approx(0.75) and d["rvol"] == pytest.approx(3.0)
    assert d["near_hi20"] == pytest.approx(21.2 / 21.6 - 1)          # today's high is the 20-day high
    assert got["AAA"]["near_hi20"] == pytest.approx(20.0 / (20.2 * 1.01) - 1)
    assert d["night_mean"] == pytest.approx(eop.night_means(cache, ["DDD"], TODAY.isoformat(), {"DDD": 20.0})["DDD"])
    assert d["nights"] == 40
    # A bar dated today (an intraday cache write) is never read.
    with sqlite3.connect(cache) as conn:
        conn.execute("INSERT INTO ohlcv_cache VALUES ('DDD', ?, 40.0, 40.0, 40.0, 40.0, 1.0)", (TODAY.isoformat(),))
    assert eop.overnight_features(cache, bars, TODAY.isoformat())["DDD"] == d


def test_filler_rule_and_order(tmp_path):
    cache = _night_cache(tmp_path, {"DDD": 20.2, "EEE": 20.4, "FFF-SM": 20.4, "GGG": 20.2})
    bars = {"DDD": (20.0, 21.6, 20.0, 21.2, 300000.0), "EEE": (20.0, 21.6, 20.0, 21.2, 300000.0),
            "FFF-SM": (20.0, 21.6, 20.0, 21.2, 300000.0), "GGG": (20.0, 20.4, 19.9, 20.2, 300000.0)}
    features = eop.overnight_features(cache, bars, TODAY.isoformat())
    picks = eop.filler_picks(features, exclude=set())
    assert [p.ticker for p in picks] == ["EEE", "DDD"]           # best night first; SME and +1% refused
    assert eop.filler_picks(features, exclude={"EEE"})[0].ticker == "DDD"
    low_volume = {**features["DDD"], "rvol": 1.9}
    assert not eop.filler_rule(low_volume)
    twins = {**features, "EEE-BE": {**features["EEE"], "night_mean": features["EEE"]["night_mean"] / 2}}
    assert [p.ticker for p in eop.filler_picks(twins, exclude=set())] == ["EEE", "DDD"]   # one name per company


@pytest.mark.asyncio
async def test_on_v3_fills_an_empty_slot_with_a_filler(tmp_path, monkeypatch):
    opens = {"AAA": 20.2, "BBB": 19.8, "CCC": 19.8, "DDD": 20.2, "EEE": 20.2}
    cache, kite = _setup(tmp_path, monkeypatch, opens,
                         {"AAA": FLAT, "BBB": FLAT, "CCC": FLAT, "DDD": FILLER, "EEE": WEAK})
    summary = await eop.run_overnight_entry(kite, cache, now=_at(TODAY, 15, 20))
    assert [o["ticker"] for o in summary["opened"]] == ["AAA", "BBB", "CCC"]     # the book is unchanged
    assert [r[0] for r in _rows(cache, "ON_V2")] == ["AAA"]                        # BBB, CCC screened out
    v3 = _rows(cache, "ON_V3")
    assert [(r[0], r[1]) for r in v3] == [("AAA", "MO_strong"), ("DDD", "FILL_F3")]
    for _t, _k, shares, price, status, *_rest, night, _x in v3:
        assert status == "OPEN" and night > 0.001
        assert settings.EDGE_OVERNIGHT_PAPER_BANKROLL / 2 - 100 < shares * price <= settings.EDGE_OVERNIGHT_PAPER_BANKROLL / 2
    assert summary["v3_inputs"]["fillers"] == ["DDD"] and summary["v3_inputs"]["fillers_quoted"] == 1
    assert kite.calls[-1] == [4]                                    # one re-quote of the filler shortlist

    exit_quote = _quote(20.6, 20.8, 20.1, 20.3, 50000.0, NEXT)
    exit_quote["ohlc"]["close"] = 19.9                              # the entry day's official close
    await eop.run_overnight_exit(_Kite({t: exit_quote for t in NAMES}), cache, now=_at(NEXT, 9, 17))
    for _t, _k, shares, _p, status, net, basis_price, basis, _n, exit_price in _rows(cache, "ON_V3"):
        assert status == "CLOSED" and (basis_price, basis) == (19.9, "official_close")
        assert net == pytest.approx((exit_price - 19.9) * shares - calc_penny_costs(19.9, exit_price, shares, False),
                                    abs=1e-3)
    row = next(s for s in eop.overnight_shadow_comparison(cache)["shadows"] if s["variant"] == "ON_V3")
    assert row["config"]["filler"] == "F3" and row["config"]["hi_first"] is True and row["closed"] == 2


@pytest.mark.asyncio
async def test_on_v3_takes_picks_at_a_20_day_high_first(tmp_path, monkeypatch):
    opens = {"AAA": 20.2, "BBB": 20.2, "CCC": 20.2}
    at_high = _quote(20.0, 21.0, 19.9, 20.9, 900000.0)             # +4.5%, within 1% of the 20-day high
    cache, kite = _setup(tmp_path, monkeypatch, opens, {"AAA": FLAT, "BBB": FLAT, "CCC": at_high})
    await eop.run_overnight_entry(kite, cache, now=_at(TODAY, 15, 20))
    assert [r[0] for r in _rows(cache, "ON_V2")] == ["AAA", "BBB"]
    assert [r[0] for r in _rows(cache, "ON_V3")] == ["AAA", "CCC"]


@pytest.mark.asyncio
async def test_v3_input_failure_never_blocks_the_book_or_v2(tmp_path, monkeypatch):
    opens = {"AAA": 20.2, "BBB": 19.8, "CCC": 19.8, "DDD": 20.2}
    cache, kite = _setup(tmp_path, monkeypatch, opens, {"AAA": FLAT, "BBB": FLAT, "CCC": FLAT, "DDD": FILLER})

    def boom(*_a, **_k):
        raise RuntimeError("cache unreadable")
    monkeypatch.setattr(eop, "overnight_features", boom)
    summary = await eop.run_overnight_entry(kite, cache, now=_at(TODAY, 15, 20))
    assert len(summary["opened"]) == 3 and [r[0] for r in _rows(cache, "ON_V2")] == ["AAA"]
    assert [r[0] for r in _rows(cache, "ON_V3")] == ["AAA"]          # no filler without inputs
    assert summary["v3_inputs"] == {"features": 0, "fillers": [], "fillers_quoted": 0}


@pytest.mark.asyncio
async def test_no_filler_quote_when_shadows_are_off(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "EDGE_OVERNIGHT_SHADOWS_ENABLED", False)
    opens = {"AAA": 20.2, "BBB": 19.8, "CCC": 19.8, "DDD": 20.2}
    cache, kite = _setup(tmp_path, monkeypatch, opens, {"AAA": FLAT, "BBB": FLAT, "CCC": FLAT, "DDD": FILLER})
    summary = await eop.run_overnight_entry(kite, cache, now=_at(TODAY, 15, 20))
    assert "v3_inputs" not in summary and len(kite.calls) == 2      # universe + shortlist re-quote only


@pytest.mark.asyncio
async def test_v3_switch_stops_only_v3_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "EDGE_OVERNIGHT_V3_SHADOW_ENABLED", False)
    opens = {"AAA": 20.2, "BBB": 19.8, "CCC": 19.8, "DDD": 20.2}
    cache, kite = _setup(tmp_path, monkeypatch, opens, {"AAA": FLAT, "BBB": FLAT, "CCC": FLAT, "DDD": FILLER})
    summary = await eop.run_overnight_entry(kite, cache, now=_at(TODAY, 15, 20))
    assert "ON_V3" not in summary["shadows"] and "v3_inputs" not in summary
    assert [r[0] for r in _rows(cache, "ON_V2")] == ["AAA"] and _rows(cache, "ON_V3") == []


@pytest.mark.asyncio
async def test_failed_filler_requote_keeps_the_high_first_order(tmp_path, monkeypatch):
    opens = {"AAA": 20.2, "BBB": 20.2, "CCC": 20.2, "DDD": 20.2}
    at_high = _quote(20.0, 21.0, 19.9, 20.9, 900000.0)
    cache, kite = _setup(tmp_path, monkeypatch, opens, {"AAA": FLAT, "BBB": FLAT, "CCC": at_high, "DDD": FILLER})
    real = kite.get_quote

    async def flaky(tokens):
        if sorted(tokens) == [4]:                                     # the filler re-quote
            raise TimeoutError("quote timeout")
        return await real(tokens)
    kite.get_quote = flaky
    summary = await eop.run_overnight_entry(kite, cache, now=_at(TODAY, 15, 20))
    assert summary["v3_inputs"]["fillers"] == ["DDD"] and summary["v3_inputs"]["fillers_quoted"] == 0
    assert [r[0] for r in _rows(cache, "ON_V3")] == ["AAA", "CCC"]   # 20-day high first still applied
