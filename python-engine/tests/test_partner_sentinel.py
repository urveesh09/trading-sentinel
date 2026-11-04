"""[N06 2026-11-04] The Sentinel's own way of trading, told to the partner as advice (partner_sentinel, and the
partner watch's messages that carry it). Messages only: nothing here can place an order. [N06c] Every line short
and concrete; the audit's case of a closed paper trade announced as a buy; the option alone as a check; BROKEN."""
import json
import sqlite3
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import aiosqlite
import pytest
import pytz

import expiry_e02
import partner_sentinel as ps
import partner_watch as pw
from config import settings
from partner_coach import round_trip_costs
from tests.test_partner_watch_score import _store, _trip

IST = pytz.timezone("Asia/Kolkata")
DAY = "2026-11-05"
NOW = IST.localize(datetime(2026, 11, 5, 10, 6, 0))


@pytest.fixture
def advice(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_SENTINEL_ADVICE_ENABLED", True)
    ps._RECORDS.clear()
    pw.reset()
    yield
    ps._RECORDS.clear()
    pw.reset()


def _quote(at, ltp, bid=None, bids=None):
    """A quote as the watch holds one: read at ``at``, the exchange's time a second before (``level_state`` needs
    both clocks)."""
    out = {"ltp": ltp, "bid": bid if bid is not None else ltp - 0.5, "ask": ltp + 0.5, "looked_at": at,
           "received_at": at.isoformat(), "quote_at": (at - timedelta(seconds=1)).isoformat()}
    if bids is not None:
        out["bids"] = bids
    return out


# ---------------------------------------------------------------------------
# size: concrete choices in the partner's rupees
# ---------------------------------------------------------------------------

def test_the_size_choices_are_one_and_two_lots_each_with_its_own_charges():
    assert ps.risk_share() == settings.FNO_MAX_RISK_PCT == 0.02
    a = ps.size_advice(100.0, 90.0, 65, 100_000.0, "NFO")
    assert a["one"] == round(10.0 * 65 + round_trip_costs(100.0, 90.0, 65, "NFO"), 2)
    assert a["two"] == round(10.0 * 130 + round_trip_costs(100.0, 90.0, 130, "NFO"), 2)
    assert a["two"] < 2 * a["one"]                          # the flat order fees are paid once, not per lot
    assert a["budget"] == 2000.0 and a["lots"] == 2          # three lots lose more than 2% of 1 lakh
    assert ps.loss_at(100.0, 90.0, 195, "NFO") > 2000.0 >= a["two"]
    assert ps.size_advice(100.0, 90.0, 65, 100_000.0, "NFO", most=1)["lots"] == 1
    # Nov 4, 10:24: SENSEX 76700 CE at 598.75, plan stop 499.9, cash 80,456: one lot is already over 2%.
    nov4 = ps.size_advice(598.75, 499.9, 20, 80456.1, "BFO")
    assert nov4["lots"] == 0 and nov4["one"] > nov4["budget"] == round(0.02 * 80456.1, 2)
    for bad in ((None, 90.0, 65, 1e5), (100.0, None, 65, 1e5), (100.0, 100.0, 65, 1e5), (100.0, 90.0, 0, 1e5),
                (100.0, 90.0, 65, None), (100.0, 90.0, 65, 0.0)):
        assert ps.size_advice(*bad) is None


def test_the_size_line_is_one_short_line_of_choices_never_a_limit():
    """[N06c] Owner: concise and direct, and "we need them to have freedom"; the audit: show one lot and two lots in
    rupees. The partner's own size is in the stop line above it."""
    nov4 = ps.size_advice(598.75, 499.9, 20, 80456.1, "BFO")
    line = ps.size_line(nov4)
    assert line == (f"📏 At the plan stop: 1 lot −₹{nov4['one']:,.0f} (2.5%) · 2 lots −₹{nov4['two']:,.0f} (5.0%). "
                    f"The Sentinel risks at most 2% (₹1,609).")
    for word in ("none", "would pass", "at most.", "least at risk", "usual"):
        assert word not in line
    assert len(line) <= 120 and ps.size_line(None) == ""
    assert ps.size_line(nov4, stop_name="its stop").startswith("📏 At its stop: 1 lot")


# ---------------------------------------------------------------------------
# the partner's own record, only where the frozen score supports the warning
# ---------------------------------------------------------------------------

async def _three_kinds_of_buy():
    """22 oversized losers, 22 winners bought after a 25% run, 22 small even ones (frozen rule's days)."""
    trips = []
    for i in range(22):
        trips.append(_trip("2026-10-28", f"big{i}", -500.0, usual=0.2, value=3100.0, run=0.05))
        trips.append(_trip("2026-10-29", f"spike{i}", 300.0, usual=0.2, value=1000.0, run=0.25))
        trips.append(_trip("2026-10-30", f"even{i}", -10.0, usual=0.2, value=1000.0, run=0.05))
    return await _store(trips)


@pytest.mark.asyncio
async def test_records_follow_the_frozen_verdicts_and_only_supported_ones_are_said(advice):
    db = await _three_kinds_of_buy()
    recs = ps.records(db, DAY)
    assert recs["UNUSUAL_SIZE"]["verdict"] == "SUPPORTED" and ps.supported(recs, "UNUSUAL_SIZE")
    assert recs["CHASED_SPIKE"]["verdict"] == "NOT_SUPPORTED" and ps.refuted(recs, "CHASED_SPIKE")
    assert ps.record_line(recs, "UNUSUAL_SIZE") == "📊 Your oversized buys since 28 Oct: −₹11,000 (22); usual size +₹6,380 (44)."
    assert ps.record_line(recs, "CHASED_SPIKE") == ""                       # never a line for an unsupported one
    assert ps.record_line(recs, "AFTER_LOSS") == ""                         # TOO_FEW here
    early = ps.records(db, "2026-10-29")["UNUSUAL_SIZE"]          # only Oct 28 before it: no usual-size trade yet
    assert early["verdict"] == "TOO_FEW" and early["warned"]["n"] == 22 and early["unwarned"]["n"] == 0
    assert ps.record_line(ps.records(db, "2026-10-29"), "UNUSUAL_SIZE") == ""
    assert ps.records(db, "2026-10-28") == {}                                  # nothing stored before it
    assert ps.morning_lines(recs) == ["📊 Your buys since 28 Oct: usual size +₹6,380 (44) · oversized −₹11,000 (22).",
                                      "🤖 The Sentinel's own trades (paper) come here as it takes them."]
    assert ps.morning_lines({}) == ["🤖 The Sentinel's own trades (paper) come here as it takes them."]


@pytest.mark.asyncio
async def test_the_check_leaves_out_the_chased_spike_warning_while_its_score_refutes_it(advice):
    plan = pw.Plan(entry=75.5, qty=65, stop=60.0, stop_basis="SWING", swing=15.5, loss=1050.0, cash=20000.0,
                   run_pct=0.31, run_from=57.5)
    kwargs = dict(lots=1, qty=65, given=75.5, future="NIFTY future", opt_type="PE")
    warned = pw.check_text("NIFTY 22300 PE", None, plan, None, **kwargs)
    assert "chased spike" in warned and "up 31% in the last 15 min" in warned
    after = {"loss": 900.0, "at": "10:00", "minutes": 2}
    quiet = pw.check_text("NIFTY 22300 PE", None, plan, None, spike_warn=False, size_note="📏 size",
                          size_tail=" SIZE TAIL.", after_tail=" AFTER TAIL.", sentinel_line="🤖 holds nothing",
                          after_loss=after, usual=0.1, **kwargs)              # 25% of cash against 1.5 x 10%
    assert "chased spike" not in quiet and "up 31% in the last 15 min" in quiet      # the fact stays
    lines = quiet.splitlines()
    assert lines.index("📏 size") == 2 and lines[-2:] == ["🤖 holds nothing", pw.CHECK_NOTE]
    assert any(l.startswith("⚠️ Your last trade closed") and l.endswith(" AFTER TAIL.") for l in lines)
    assert any(l.startswith("⚠️ ₹4,908 is 25% of your cash") and l.endswith(" SIZE TAIL.") for l in lines)


# ---------------------------------------------------------------------------
# the PLAN, ADDED and DAY texts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_plan_is_short_each_warning_one_line_with_its_record_and_the_choices_after_the_stop(advice):
    """[N06c] Owner: "long long paragraph with market on reading is impossible". The record joins its warning line;
    the facts line is gone; the SWING stop line is one sentence shorter."""
    db = await _three_kinds_of_buy()
    plan = pw.Plan(entry=598.75, qty=100, stop=499.9, stop_basis="SWING", swing=98.82, loss=10051.0, cash=80456.1,
                   stop_index=77006.0, index_stop_option=501.05, run_pct=0.08, run_from=554.1, trend="WITH")
    after = {"loss": 2957.0, "at": "10:23", "minutes": 1}
    size, size_tail, after_tail = await pw._sentinel_notes(db, DAY, plan, lot=20, exchange="BFO", bought=100,
                                                           bought_px=598.75, lots=5, usual=0.31, after_loss=after)
    assert size == ps.size_line(ps.size_advice(598.75, 499.9, 20, 80456.1, "BFO"))
    assert size_tail == " Since 28 Oct such buys: −₹11,000 (22); usual size +₹6,380 (44)."
    assert after_tail == " The Sentinel takes 1 lot after a loss."              # no after-loss record: TOO_FEW
    trip = SimpleNamespace(tradingsymbol="SENSEX26N0576700CE", exchange="BFO", product="NRML", open_qty=100, qty=100,
                           entry=598.75, carried=False, first_at=NOW, basis="CONFIRMED")
    lines = pw.plan_text(trip, plan, lots=5, size_note=size, size_tail=size_tail, after_tail=after_tail, usual=0.31,
                         after_loss=after).splitlines()
    assert lines == [
        "🟢 You bought SENSEX 76700 CE · 5 lots (100) at ₹598.75",
        "🛑 Plan stop ₹499.9: one normal 5-minute swing (₹98.82) under your price. If it sells there: about −₹10,051 "
        "with charges, 12% of your cash.",
        "⚠️ ₹59,875 in this trade, 74% of your cash: much bigger than your usual 31%." + size_tail,
        size,
        "⚠️ Your last trade closed −₹2,957 at 10:23, 1 min before this buy." + after_tail,
        lines[-1]]
    assert lines[-1].startswith("Your stop") or "plan stop" in lines[-1].lower() or lines[-1].startswith("Check")
    # A supported after-loss record and the rule share the after-loss line.
    recs = {"AFTER_LOSS": {"verdict": "SUPPORTED", "since": "2026-10-27", "warned": {"n": 143, "total": -31721.0},
                           "unwarned": {"n": 89, "total": -8433.0}}}
    ps._RECORDS[(db, "2026-11-06")] = recs
    _s, no_size, joined = await pw._sentinel_notes(db, "2026-11-06", plan, lot=20, exchange="BFO", bought=20,
                                                   bought_px=598.75, lots=1, usual=0.31, after_loss=after)
    assert no_size == "" and joined == " Since 27 Oct such buys: −₹31,721 (143). The Sentinel takes 1 lot after a loss."
    # Without a stop to size from (no market data), no size line; switched off, nothing at all.
    assert (await pw._sentinel_notes(db, DAY, pw.Plan(entry=100.0, qty=65, loss=6500.0, cash=80000.0), lot=65,
                                     exchange="NFO", bought=65, bought_px=100.0, lots=1, usual=None,
                                     after_loss=None))[0] == ""
    settings.PARTNER_SENTINEL_ADVICE_ENABLED = False
    assert (await pw._sentinel_notes(db, DAY, plan, lot=20, exchange="BFO", bought=100, bought_px=598.75, lots=5,
                                     usual=0.31, after_loss=after)) == ("", "", "")


def test_averaging_down_and_the_day_message_carry_the_sentinels_own_rules(advice):
    holding = SimpleNamespace(tradingsymbol="SENSEX26N0576700CE", exchange="BFO", product="NRML", open_qty=80,
                              qty=80, entry=742.02, carried=False, basis="CONFIRMED", trip=None)
    plan = pw.Plan(entry=742.02, qty=80, stop=650.25, stop_basis="INDEX", stop_index=77320.0, loss=7535.0,
                   cash=80456.1)
    down = pw.added_text(holding, added=20, added_px=688.65, first_px=759.82, plan=plan, loss_before=6714.0,
                         rule=pw._sentinel_rule("ADD"))
    assert down.count(ps.ADD_RULE) == 1 and "Buying more of a falling option" in down
    up = pw.added_text(holding, added=20, added_px=770.0, first_px=759.82, plan=plan, loss_before=6714.0,
                       rule=pw._sentinel_rule("ADD"))
    assert ps.ADD_RULE not in up                                 # adding above the first buy: not averaging down
    day = {"net": -16713.0, "share": 0.2077, "closed": 12, "won": 7, "won_sum": 10813.0, "lost": 5,
           "lost_sum": -27526.0, "quick": 3, "quick_sum": 1177.0, "open": 0, "check": "check sensex 76700 ce"}
    lines = pw.day_text(day, 80456.1).splitlines()
    assert lines[lines.index(next(l for l in lines if "within 30 min of a losing exit" in l)) + 1] == ps.AFTER_LOSS_RULE
    settings.PARTNER_SENTINEL_ADVICE_ENABLED = False
    assert ps.AFTER_LOSS_RULE not in pw.day_text(day, 80456.1) and pw._sentinel_rule("ADD") == ""


# ---------------------------------------------------------------------------
# the Sentinel's own main trades, sent as they happen
# ---------------------------------------------------------------------------

async def _fno(db, **row):
    import fno_positions as fpos
    await fpos.init_fno_positions_db(db)
    base = {"source": "FNO_PAPER", "tradingsymbol": "NIFTY26N1024000PE", "underlying": "NIFTY", "expiry": "2026-11-10",
            "opt_type": "PE", "lots": 2, "lot_size": 65, "initial_lots": 2, "qty": 130,
            "entry_time": (NOW - timedelta(minutes=1)).isoformat(), "entry_date": DAY, "entry_premium": 120.5,
            "entry_underlying": 24050.0, "stop_underlying": 24110.0, "target_underlying": 23950.0,
            "premium_stop": 90.4, "delta_at_entry": -0.45, "status": "OPEN", "strategy": "N11_EFF"} | row
    async with aiosqlite.connect(db) as conn:
        cur = await conn.execute(f"INSERT INTO fno_positions({','.join(base)}) VALUES({','.join('?' * len(base))})",
                                 tuple(base.values()))
        await conn.commit()
        return cur.lastrowid


@pytest.mark.asyncio
async def test_the_sentinels_fno_buy_is_offered_once_fresh_in_four_short_lines(advice):
    db = settings.DB_PATH
    await _fno(db, entry_date="2026-11-03", entry_time="2026-11-03T10:00:00+05:30", status="CLOSED",
               exit_time="2026-11-03T10:30:00+05:30", exit_date="2026-11-03", exit_premium=110.0, pnl=-1500.0,
               exit_reason="underlying_stop")
    trade_id = await _fno(db)
    await _fno(db, strategy="N11_ADD", tradingsymbol="NIFTY26N1024000PE")                  # an earned lot: not a trade
    await _fno(db, entry_time=(NOW - timedelta(minutes=3)).isoformat(), tradingsymbol="NIFTY26N1023900PE")  # stale
    found = ps.events(db, DAY, NOW)
    assert [f[0] for f in found] == [f"sentinel:{DAY}:fno:{trade_id}:buy"] and found[0][1] == "SENTINEL"
    trade = ps.fno_trades(db, DAY)[0]
    assert ps.option_stop(trade) == round(max(120.5 - 0.45 * 60.0, 90.4), 2) == 93.5
    advice_ = ps.size_advice(120.5, 93.5, 65, 28600.0, "NFO")
    assert found[0][2](28600.0).splitlines() == [
        "🤖 Sentinel bought NIFTY 24000 PE (10 Nov) at ₹120.5, 10:05:00 (paper).",
        "🛑 Stop NIFTY fut 24,110 (option ≈₹93.5) · 🎯 target fut 23,950.",
        ps.size_line(advice_, stop_name="its stop"),
        "📊 Its last 1 paper trades: 0 won, −₹750 a lot. It loses often. Your call."]


@pytest.mark.asyncio
async def test_a_paper_trade_already_closed_is_never_announced_as_a_buy(advice):
    """[N06c] The audit's case, reproduced: a trade bought and sold inside the buy window was offered as a fresh buy.
    A buy is told only while the trade is still open; its sale then waits for a buy that was told, so neither goes."""
    db = settings.DB_PATH
    await pw.init_partner_watch_db(db)
    await _fno(db, status="CLOSED", exit_time=(NOW - timedelta(seconds=30)).isoformat(), exit_date=DAY,
               exit_premium=118.0, pnl=-400.0, exit_reason="time_stop")
    found = ps.events(db, DAY, NOW)
    assert [f[1] for f in found] == ["SENTINEL_EXIT"]                          # no buy for a closed trade
    assert await pw._sentinel_items(db, DAY, NOW, []) == []                     # and its sale has no told buy
    with sqlite3.connect(expiry_e02.path_for(db, expiry_e02.E032)) as c:
        c.execute("CREATE TABLE e02_positions(id INTEGER PRIMARY KEY, day TEXT, status TEXT, payload TEXT NOT NULL)")
        c.execute("INSERT INTO e02_positions VALUES(3, ?, 'CLOSED', ?)", (DAY, json.dumps(
            {"id": 3, "day": DAY, "underlying": "SENSEX", "symbol": "SENSEX26N0576500PE", "lot_size": 20, "lots": 1,
             "lots_open": 0, "entry_ts": (NOW - timedelta(minutes=1)).isoformat(), "entry_price": 40.0, "stop": 26.0,
             "status": "CLOSED", "net_pnl": -300.0, "_events": [{"ts": NOW.isoformat(), "action": "BUY", "lots": 1,
                                                                "price": 40.0}]})))
    settings.EXPIRY_MAIN_STRATEGY = "E032"
    assert not any(f[0].startswith(f"sentinel:{DAY}:exp:") and f[1] == "SENTINEL" for f in ps.events(db, DAY, NOW))


@pytest.mark.asyncio
async def test_a_sentinel_sale_is_told_only_after_its_buy_was_sent_with_what_the_partner_still_holds(advice):
    db = settings.DB_PATH
    await pw.init_partner_watch_db(db)
    pw._state.cash = 80000.0
    trade_id = await _fno(db)
    holdings = [SimpleNamespace(tradingsymbol="NIFTY26N1024000PE", open_qty=65)]
    first = await pw._sentinel_items(db, DAY, NOW, holdings)
    assert [i[0] for i in first] == [f"sentinel:{DAY}:fno:{trade_id}:buy"]
    await pw._enqueue_many(db, DAY, first, NOW)
    assert await pw._sentinel_items(db, DAY, NOW, holdings) == []                # not again
    async with aiosqlite.connect(db) as conn:
        await conn.execute("UPDATE fno_positions SET status='CLOSED', exit_time=?, exit_date=?, exit_premium=140.0, "
                           "pnl=2400.0, exit_reason='trail_stop' WHERE id=?",
                           ((NOW - timedelta(seconds=20)).isoformat(), DAY, trade_id))
        await conn.commit()
    assert await pw._sentinel_items(db, DAY, NOW, holdings) == []                # its buy was not sent yet
    async with aiosqlite.connect(db) as conn:
        await conn.execute("UPDATE partner_watch_messages SET sent=1 WHERE message_key=?", (first[0][0],))
        await conn.commit()
    sale = await pw._sentinel_items(db, DAY, NOW, holdings)
    assert [i[1] for i in sale] == ["SENTINEL_EXIT"]
    assert sale[0][3]["text"] == ("🤖 Sentinel sold NIFTY 24000 PE at ₹140, 10:05 (trailing stop): +₹1,200 a lot "
                                  "(paper). You still hold 65 of it.")
    # The outbox sends it as a fixed text: no Quiet any more, nothing mutes it.
    assert "SENTINEL" in pw.ALWAYS_SENT and "SENTINEL_EXIT" in pw.ALWAYS_SENT
    entry = pw._Entry(sale[0][0], "SENTINEL_EXIT", json.dumps(sale[0][3]), 0, "queued", None, NOW.isoformat(), None,
                      None, NOW.isoformat(), None)
    assert (await pw._build(db, entry, NOW, None))[0] == sale[0][3]["text"]


@pytest.mark.asyncio
async def test_the_expiry_main_ticket_is_offered_with_its_stop_its_2x_rule_and_the_choices(advice, monkeypatch):
    db = settings.DB_PATH
    monkeypatch.setattr(settings, "EXPIRY_MAIN_STRATEGY", "E032")
    p = {"id": 7, "day": DAY, "underlying": "SENSEX", "play": "E032", "exchange": "BFO", "symbol": "SENSEX26N0576500PE",
         "lot_size": 20, "lots": 2, "lots_open": 2, "entry_ts": (NOW - timedelta(minutes=1)).isoformat(),
         "entry_price": 40.0, "stop": 26.0, "underlying_stop": 76950.0, "direction": -1, "status": "OPEN",
         "net_pnl": -40.0, "e02_policy": {"flat": "15:14"},
         "_events": [{"ts": (NOW - timedelta(minutes=1)).isoformat(), "action": "BUY", "lots": 2, "price": 40.0}]}
    with sqlite3.connect(expiry_e02.path_for(db, expiry_e02.E032)) as c:
        c.execute("CREATE TABLE e02_positions(id INTEGER PRIMARY KEY, day TEXT, status TEXT, payload TEXT NOT NULL)")
        c.execute("INSERT INTO e02_positions VALUES(7, ?, 'OPEN', ?)", (DAY, json.dumps(p)))
    found = ps.events(db, DAY, NOW)
    assert [f[0] for f in found] == [f"sentinel:{DAY}:exp:7:buy"]
    lines = found[0][2](200_000.0).splitlines()
    assert lines[0] == "🤖 Sentinel's expiry ticket: bought SENSEX 76500 PE (expires today) at ₹40, 10:05:00 (paper)."
    assert lines[1] == "🛑 Stop ₹26 or SENSEX 76,950 · sells half at 2x (₹80) · all from 15:14."
    assert lines[2].startswith("📏 At its stop: 1 lot −₹") and lines[2].endswith(" A jump can take a lot's whole ₹800.")
    assert lines[3] == "📊 Its first SENSEX ticket: no record yet. Most lose a little; a few pay big. Your call."
    one = dict(p, lots=1)
    assert "· sells at 2x (₹80) ·" in ps.expiry_buy_text(one, 200_000.0, None)        # one lot: all of it at 2x
    sold = dict(p, status="CLOSED", net_pnl=1123.5, lots_open=0)
    assert ps.expiry_sell_text(sold, {"ts": NOW.isoformat(), "action": "TARGET_BASE", "lots": 1, "price": 80.0}) == (
        "🤖 Sentinel's expiry ticket: sold 1 lot of SENSEX 76500 PE at ₹80, 10:06 (2x sale, the rest runs); closed "
        "+₹1,124 (paper).")
    monkeypatch.setattr(settings, "EXPIRY_MAIN_STRATEGY", "ABC")                 # not the main ticket: nothing
    assert ps.events(db, DAY, NOW) == []


@pytest.mark.asyncio
async def test_a_check_says_what_the_sentinel_holds_and_off_means_the_watch_as_before(advice):
    db = settings.DB_PATH
    await _fno(db)
    assert ps.open_line(db, DAY, "NIFTY") == "🤖 Sentinel now: holds NIFTY 24000 PE (bought 10:05 at ₹120.5)."
    assert ps.open_line(db, DAY, "SENSEX") == "🤖 Sentinel now: nothing on SENSEX (0 trades today)."
    settings.PARTNER_SENTINEL_ADVICE_ENABLED = False
    assert await pw._sentinel_items(db, DAY, NOW, []) == [] and await pw._morning_lines(db, DAY, NOW) == []


def test_a_missing_store_tells_nothing_and_never_raises(tmp_path):
    missing = str(tmp_path / "none.db")
    assert ps.fno_trades(missing, DAY) == [] and ps.fno_record(missing, DAY) is None
    assert ps.events(missing, DAY, NOW) == []


# ---------------------------------------------------------------------------
# [N06c] the option alone is a check, and its index is worked out from the strike
# ---------------------------------------------------------------------------

class _Book:
    def __init__(self, strikes):
        self.strikes = strikes

    def nearest_option_expiry(self, today):
        return date(2026, 11, 5)

    def option(self, expiry, strike, kind):
        return object() if strike in self.strikes else None


def test_a_check_without_its_index_takes_the_one_that_lists_the_strike(monkeypatch):
    import fno_underlyings
    books = {"NIFTY": _Book({24000.0, 24050.0}), "SENSEX": _Book({76700.0, 76800.0})}
    monkeypatch.setattr(fno_underlyings, "get_instruments_for", lambda name: books.get(name, _Book(set())))
    today = date(2026, 11, 5)
    assert pw.infer_underlying(76700.0, "CE", today) == "SENSEX"
    assert pw.infer_underlying(24050.0, "PE", today) == "NIFTY"
    assert pw.infer_underlying(50000.0, "PE", today) is None                   # listed nowhere: as before (NIFTY)
    books["SENSEX"].strikes.add(24000.0)
    assert pw.infer_underlying(24000.0, "PE", today) is None                   # listed twice: not guessed


# ---------------------------------------------------------------------------
# [N06c] BROKEN: under the plan stop, with choices
# ---------------------------------------------------------------------------

def _held(qty=100, entry=598.75, first_at=None, carried=False):
    trip = SimpleNamespace(first_at=first_at or NOW - timedelta(minutes=5), carried=carried, buys={}, buy_orders=1,
                           key="t1")
    return SimpleNamespace(tradingsymbol="SENSEX26N0576700CE", exchange="BFO", product="NRML", open_qty=qty, qty=qty,
                           entry=entry, carried=carried, basis="CONFIRMED", trip=trip, position_key="t1", hkey="h1",
                           twin=False)


def test_broken_says_where_the_price_is_and_what_selling_all_or_half_gives_against_the_bids():
    held = _held()
    plan = pw.Plan(entry=598.75, qty=100, stop=499.9, stop_basis="SWING", loss=10051.0, cash=80456.1)
    quote = _quote(NOW, 470.0, bid=468.0, bids=[(468.0, 60), (467.0, 60)])
    lines = pw.broken_text(held, plan, quote, None, 20, 80456.1).splitlines()
    assert lines[0] == "⛔ SENSEX 76700 CE (100) is under its plan stop ₹499.9: ₹470 now."
    all_ = pw._result_for(held, (468.0 * 60 + 467.0 * 40) / 100, 100)
    half = pw._result_for(held, 468.0, 40)                    # 5 lots: half is 2 lots (40), all at the best bid
    assert lines[1] == (f"Sell all now −₹{-all_:,.0f}, {-all_ / 80456.1:.0%} of your cash · sell 2 lots (40) "
                        f"−₹{-half:,.0f} · or hold: your call.")
    thin = _quote(NOW, 470.0, bid=468.0, bids=[(468.0, 30)])
    assert " or worse" in pw.broken_text(held, plan, thin, None, 20, 80456.1)  # the bids shown take only 30
    one_lot = pw.broken_text(_held(qty=20), plan, quote, None, 20, 80456.1).splitlines()[1]
    assert " · sell " not in one_lot and one_lot.endswith("· or hold: your call.")   # one lot: no half
    lower = SimpleNamespace(state="FULL", stops=[{"trigger": 450.0, "units": 100}], covered=100, exiting=0)
    assert pw.broken_text(held, plan, quote, lower, 20).endswith(" Your SL at ₹450 is lower.")


def test_broken_is_told_once_on_the_first_read_under_the_stop_after_one_over_it(advice):
    held = _held()
    plan = pw.Plan(entry=598.75, qty=100, stop=499.9, stop_basis="SWING", loss=10051.0, cash=80456.1)
    pw._state.planned["t1"] = {"plan": plan}
    pw._state.quotes[held.tradingsymbol] = _quote(NOW, 470.0)
    assert pw._broken_item(DAY, held, None, NOW) is None                       # never seen over: its PLAN said it
    pw._state.quotes[held.tradingsymbol] = _quote(NOW, 520.0)
    assert pw._broken_item(DAY, held, None, NOW) is None                       # over: noted
    pw._state.quotes[held.tradingsymbol] = _quote(NOW, 470.0)
    item = pw._broken_item(DAY, held, None, NOW)
    assert item[:2] == (f"broken:{DAY}:t1", "BROKEN") and item[3] == {"episode": f"{DAY}:t1"}
    # Within NO_STOP_AFTER of the buy (NO_STOP and the PLAN say it), carried in, or an own stop at/over the plan's.
    early = _held(first_at=NOW - timedelta(seconds=60))
    pw._state.above.add(f"{DAY}:t1")
    assert pw._broken_item(DAY, early, None, NOW) is None
    assert pw._broken_item(DAY, _held(carried=True), None, NOW) is None
    own = SimpleNamespace(state="FULL", stops=[{"trigger": 500.0, "units": 100}], covered=100, exiting=0)
    assert pw._broken_item(DAY, held, own, NOW) is None
    lower = SimpleNamespace(state="FULL", stops=[{"trigger": 450.0, "units": 100}], covered=100, exiting=0)
    assert pw._broken_item(DAY, held, lower, NOW) is not None                  # a lower stop does not cover it
    stale = dict(_quote(NOW - timedelta(seconds=40), 470.0))                    # an old read checks nothing
    pw._state.quotes[held.tradingsymbol] = stale
    assert pw._broken_item(DAY, held, None, NOW) is None
    assert "BROKEN" in pw._BUILDERS and pw.PRIORITY["BROKEN"] == 1 and "BROKEN" not in pw.ALWAYS_SENT
    pw._state.quotes[held.tradingsymbol] = _quote(NOW, 470.0)
    assert pw._broken_item(DAY, held, None, NOW) is not None
    settings.PARTNER_WATCH_BROKEN_ENABLED = False                              # its own switch: off, never sent
    try:
        assert pw._broken_item(DAY, held, None, NOW) is None
    finally:
        settings.PARTNER_WATCH_BROKEN_ENABLED = True


@pytest.mark.asyncio
async def test_the_watch_on_extra_lines_are_the_records_the_feed_and_todays_expiry(advice, monkeypatch):
    """[N06c] After login: the partner's supported records (one line), the Sentinel's feed, and today's expiry."""
    import fno_underlyings

    class _Expiring:
        def __init__(self, day):
            self.day = day

        def is_expiry_day(self, day):
            return day == self.day

    monkeypatch.setattr(fno_underlyings, "get_instruments_for",
                        lambda name: _Expiring(NOW.date() if name == "SENSEX" else None))
    ps._RECORDS[(settings.DB_PATH, DAY)] = {}
    assert await pw._morning_lines(settings.DB_PATH, DAY, NOW) == [
        "🤖 The Sentinel's own trades (paper) come here as it takes them.",
        "⏳ SENSEX expires today: its options lose time value fastest and settle at the close."]
