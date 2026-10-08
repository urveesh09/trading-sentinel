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


def _fresh(path):
    path.mkdir()
    return path


def _quote(o, h, l, c, v, day=TODAY):
    asks = [{"price": round(c * (1 + 0.0005 * (i + 1)), 2), "quantity": 20000, "orders": 3} for i in range(5)]
    bids = [{"price": round(c * (1 - 0.0005 * (i + 1)), 2), "quantity": 20000, "orders": 3} for i in range(5)]
    return {"ohlc": {"open": o, "high": h, "low": l, "close": 20.0}, "last_price": c, "volume": v,
            "last_trade_time": f"{day.isoformat()} 15:19:58", "depth": {"buy": bids, "sell": asks}}


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


@pytest.mark.asyncio
async def test_exit_splits_the_result_into_entry_and_overnight_parts(tmp_path, entry_quotes):
    cache = _cache(tmp_path)
    entry = await eop.run_overnight_entry(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 20))
    shares, entry_price = entry["opened"][0]["shares"], entry["opened"][0]["entry_price"]
    exit_quote = _quote(20.6, 20.8, 20.1, 20.3, 50000.0, NEXT)
    exit_quote["ohlc"]["close"] = 20.2                         # Oct 6 official close
    summary = await eop.run_overnight_exit(_Kite({"AAA": exit_quote}), cache, now=_at(NEXT, 9, 17))
    trade = summary["closed"][0]
    assert trade["entry_day_close"] == 20.2
    assert trade["entry_vs_close_rs"] == pytest.approx((20.2 - entry_price) * shares, abs=1e-3)
    assert trade["overnight_rs"] == pytest.approx((20.6 - 20.2) * shares, abs=1e-3)
    assert trade["open_is_prev_close"] is False
    assert "overnight close->open" in eop.format_exit_telegram(summary)
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        assert conn.execute("SELECT entry_day_close FROM edge_overnight_paper_trades").fetchone() == (20.2,)


@pytest.mark.asyncio
async def test_delayed_exit_does_not_claim_the_entry_day_close(tmp_path, entry_quotes):
    cache = _cache(tmp_path)
    await eop.run_overnight_entry(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 20))
    await eop.run_overnight_exit(_Kite({}), cache, now=_at(NEXT, 9, 17))          # no trade: waits
    later = date(2026, 10, 8)
    summary = await eop.run_overnight_exit(_Kite({"AAA": _quote(20.6, 20.8, 20.1, 20.3, 50000.0, later)}),
                                           cache, now=_at(later, 9, 17))
    assert summary["closed"][0]["reason"] == "OPEN_DELAYED"
    assert "overnight_rs" not in summary["closed"][0]


@pytest.mark.asyncio
async def test_waiting_leg_is_retried_the_same_session_oct7_praeng(tmp_path, entry_quotes):
    # Oct 7 audit T1: PRAENG had no trade at 09:17, the EXIT receipt was
    # written and nothing retried it although it traded later that day.
    cache = _cache(tmp_path)
    await eop.run_overnight_entry(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 20))
    stale = _quote(20.6, 20.8, 20.1, 20.3, 50000.0, TODAY)            # last trade yesterday
    first = await eop.run_overnight_exit(_Kite({"AAA": stale}), cache, now=_at(NEXT, 9, 17))
    assert first["waiting"] == [{"ticker": "AAA", "trade_date": TODAY.isoformat(), "reason": "no_trade_today",
                                 "last_trade_time": f"{TODAY.isoformat()} 15:19:58"}]
    assert await eop.catch_up(_Kite({"AAA": stale}), cache, now=_at(NEXT, 9, 20)) == []   # still no trade
    traded = _quote(20.4, 20.8, 20.1, 20.3, 50000.0, NEXT)
    assert await eop.catch_up(_Kite({"AAA": traded}), cache, now=_at(NEXT, 9, 25)) == ["EXIT_RETRY"]
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        row = conn.execute("SELECT status, exit_reason, exit_price, exit_date FROM edge_overnight_paper_trades").fetchone()
        notices = conn.execute("SELECT phase FROM edge_overnight_paper_notices ORDER BY phase").fetchall()
    assert row == ("CLOSED", "OPEN_RETRY", round(20.4 * 0.9995, 4), NEXT.isoformat())
    assert notices == [("ENTRY",), ("EXIT",), ("EXIT_RETRY_0925",)]
    assert await eop.catch_up(_Kite({"AAA": traded}), cache, now=_at(NEXT, 9, 30)) == []   # closed once


@pytest.mark.asyncio
async def test_retry_after_the_auction_grace_sells_at_ltp_and_stops_at_the_close(tmp_path, entry_quotes):
    cache = _cache(tmp_path)
    await eop.run_overnight_entry(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 20))
    await eop.run_overnight_exit(_Kite({}), cache, now=_at(NEXT, 9, 17))
    traded = _quote(20.4, 20.8, 20.1, 20.3, 50000.0, NEXT)
    assert await eop.retry_waiting_exits(_Kite({"AAA": traded}), cache, now=_at(NEXT, 15, 25)) \
        == {"closed": [], "waiting": []}                                  # past EXIT_LATEST: carried
    summary = await eop.retry_waiting_exits(_Kite({"AAA": traded}), cache, now=_at(NEXT, 11, 0))
    trade = summary["closed"][0]
    assert trade["reason"] == "CATCHUP_LTP" and trade["exit_price"] == round(20.3 * 0.9995, 4)
    assert trade["after_open_rs"] == pytest.approx((20.3 - 20.4) * eop_shares(cache))
    assert "[CATCHUP_LTP]" in eop.format_exit_telegram(summary)


def eop_shares(cache):
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        return conn.execute("SELECT shares FROM edge_overnight_paper_trades").fetchone()[0]


@pytest.mark.asyncio
async def test_missed_whole_session_does_not_claim_the_entry_day_close_t3(tmp_path, entry_quotes):
    # Oct 7 audit T3 probe: entered Oct 6, the service missed Oct 7 entirely
    # (no attempt), first exit Oct 8. Its quote's close is Oct 7's.
    cache = _cache(tmp_path)
    await eop.run_overnight_entry(_Kite(entry_quotes), cache, now=_at(TODAY, 15, 20))
    later = date(2026, 10, 8)
    quote = _quote(20.6, 20.8, 20.1, 20.3, 50000.0, later)
    quote["ohlc"]["close"] = 20.5
    summary = await eop.run_overnight_exit(_Kite({"AAA": quote}), cache, now=_at(later, 9, 17))
    trade = summary["closed"][0]
    assert trade["reason"] == "OPEN_DELAYED"
    assert "entry_day_close" not in trade and "overnight_rs" not in trade


def test_prior_session_skips_weekends_and_cached_holidays(tmp_path):
    db = str(tmp_path / "cal.db")
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE holidays (holiday_date TEXT PRIMARY KEY, fetched_at TIMESTAMP)")
        conn.execute("INSERT INTO holidays VALUES ('2026-10-02', NULL)")           # Friday holiday
    assert eop.prior_session("2026-10-05", db) == "2026-10-01"                      # Monday -> Thursday
    assert eop.prior_session("2026-10-07", db) == "2026-10-06"


# ---------------------------------------------------------------- realism guards (2026-10-07)

BAR = (20.0, 20.5, 19.5, 20.2, 100000.0)                # open, high, low, LTP, volume


def test_realism_refuses_unbuyable_duplicate_sme_and_weak_picks():
    ok = {"ohlc": {"close": 20.0}, "upper_circuit_limit": 24.0,
          "depth": {"sell": [{"price": 20.25, "quantity": 500}]}}
    assert eop.realism_refusal("AAA", "MR_strong", ok, BAR, set()) is None
    assert eop.realism_refusal("AAA-SM", "MR_strong", ok, BAR, set()) == "sme_series"
    assert eop.realism_refusal("CALSOFT-BE", "MO_strong", ok, BAR, {"CALSOFT"}) == "duplicate_series"
    assert eop.realism_refusal("AAA", "MR_mid", ok, BAR, set()) == "weak_kind_MR_mid"
    locked = {**ok, "upper_circuit_limit": 20.25}
    assert eop.realism_refusal("AAA", "MO_strong", locked, BAR, set()) == "at_upper_circuit"
    no_sellers = {**ok, "depth": {"sell": [{"price": 0, "quantity": 0}]}}
    assert eop.realism_refusal("AAA", "MO_strong", no_sellers, BAR, set()) == "no_sellers"
    at_high = (19.6, 20.5, 19.5, 20.5, 100000.0)        # +2.5% and closing on its high, band unknown
    assert eop.realism_refusal("AAA", "MO_strong", {"ohlc": {"close": 20.0}, "depth": ok["depth"]},
                               at_high, set()) == "at_day_high_after_rise"


def test_missing_or_empty_sell_depth_fails_closed_o8_o1():
    """Oct 8 audit O8-O1: missing or empty depth used to pass the no-sellers guard."""
    base = {"ohlc": {"close": 20.0}, "upper_circuit_limit": 24.0}
    assert eop.realism_refusal("AAA", "MR_strong", base, BAR, set()) == "no_depth"
    assert eop.realism_refusal("AAA", "MR_strong", {**base, "depth": {}}, BAR, set()) == "no_depth"
    assert eop.realism_refusal("AAA", "MR_strong", {**base, "depth": {"sell": []}}, BAR, set()) == "no_sellers"
    junk = {**base, "depth": {"sell": [None, {"price": "x", "quantity": 5}, {"price": 20.1, "quantity": 0}]}}
    assert eop.realism_refusal("AAA", "MR_strong", junk, BAR, set()) == "no_sellers"
    one = {**base, "depth": {"sell": [{"price": 20.1, "quantity": 1}]}}
    assert eop.realism_refusal("AAA", "MR_strong", one, BAR, set()) is None


def test_walk_asks_fills_only_the_visible_quantity_at_its_average_price():
    asks = eop.visible_asks({"depth": {"sell": [{"price": 20.2, "quantity": 100},
                                                {"price": 20.0, "quantity": 50}]}})
    assert asks == [(20.0, 50), (20.2, 100)]
    assert eop.walk_asks(asks, 100) == (100, pytest.approx(20.1))
    assert eop.walk_asks(asks, 500) == (150, pytest.approx((50 * 20.0 + 100 * 20.2) / 150))
    assert eop.walk_asks([], 10) == (0, None)


@pytest.mark.asyncio
async def test_entry_is_capped_by_visible_asks_and_priced_at_their_average(tmp_path, entry_quotes):
    cache = _cache(tmp_path)
    thin = dict(entry_quotes["AAA"])
    thin["depth"] = {"buy": [{"price": 19.9, "quantity": 400}],
                     "sell": [{"price": 20.10, "quantity": 120}, {"price": 20.30, "quantity": 80}]}
    summary = await eop.run_overnight_entry(_Kite({**entry_quotes, "AAA": thin}), cache, now=_at(TODAY, 15, 20))
    assert summary["fill_contract"] == "visible-asks-v1"
    (o,) = [o for o in summary["opened"] if o["ticker"] == "AAA"]
    assert o["planned"] > 200 and o["shares"] == 200 and o["visible_ask_qty"] == 200
    assert o["entry_price"] == pytest.approx((120 * 20.10 + 80 * 20.30) / 200)   # walked, above the 25 bps model
    assert o["best_ask"] == 20.10 and o["best_bid"] == 19.9
    # Fewer than a quarter of the planned shares on offer: refused, not shrunk to dust.
    dust = dict(thin, depth={"sell": [{"price": 20.10, "quantity": 30}]})
    summary = await eop.run_overnight_entry(_Kite({**entry_quotes, "AAA": dust}), _cache(_fresh(tmp_path / "b")),
                                            now=_at(TODAY, 15, 20))
    (skip,) = [s for s in summary["skipped"] if s["ticker"] == "AAA"]
    assert skip["reason"] == "thin_asks_below_quarter_of_plan" and skip["visible_ask_qty"] == 30


@pytest.mark.asyncio
async def test_a_refused_pick_is_replaced_by_the_next_ranked_one(tmp_path, entry_quotes, monkeypatch):
    from types import SimpleNamespace
    cache = _cache(tmp_path)

    def pick(ticker, kind):
        return SimpleNamespace(ticker=ticker, signal_subtype=kind, adjusted_strength=1.0, shares=100)

    ranked = [pick("AAA-SM", "MO_strong"), pick("AAA", "MR_mid"), pick("BBB", "MO_strong")]
    seen = {}

    def fake_scan(**kwargs):
        seen.update(kwargs)
        return {"positions": ranked, "candidates": ranked}

    monkeypatch.setattr("penny_edge_live.scan_today", fake_scan)
    monkeypatch.setattr(settings, "PENNY_EDGE_MAX_POSITIONS", 1)
    quotes = {**entry_quotes, "AAA-SM": entry_quotes["AAA"]}
    kite = _Kite(quotes)
    kite.instrument_cache["AAA-SM"] = 4
    monkeypatch.setattr(eop, "universe_from_cache", lambda _db: ["AAA", "AAA-SM", "BBB"])
    summary = await eop.run_overnight_entry(kite, cache, now=_at(TODAY, 15, 20))
    assert seen["max_positions"] == eop.RANK_DEPTH
    assert [o["ticker"] for o in summary["opened"]] == ["BBB"]
    assert [(s["ticker"], s["reason"]) for s in summary["skipped"]] == [
        ("AAA-SM", "sme_series"), ("AAA", "weak_kind_MR_mid")]
