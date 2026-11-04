"""[N06 2026-11-04] The Sentinel's own way of trading, told to the partner as advice (partner_sentinel, and the
partner watch's messages that carry it). Messages only: nothing here can place an order."""
import json
import sqlite3
from datetime import datetime, timedelta
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


# ---------------------------------------------------------------------------
# size: the Sentinel's 2% rule in the partner's rupees
# ---------------------------------------------------------------------------

def test_the_size_rule_is_the_sentinels_own_two_percent_at_the_stop_with_charges():
    assert ps.risk_share() == settings.FNO_MAX_RISK_PCT == 0.02
    a = ps.size_advice(100.0, 90.0, 65, 100_000.0, "NFO")
    per_lot = round(10.0 * 65 + round_trip_costs(100.0, 90.0, 65, "NFO"), 2)
    assert a["per_lot"] == per_lot and a["budget"] == 2000.0
    assert a["lots"] == int(2000.0 // per_lot) == 2
    assert ps.size_advice(100.0, 90.0, 65, 100_000.0, "NFO", most=1)["lots"] == 1
    # Nov 4, 10:24: SENSEX 76700 CE at 598.75, plan stop 499.9, cash 80,456: even one lot is over the rule.
    nov4 = ps.size_advice(598.75, 499.9, 20, 80456.1, "BFO")
    assert nov4["lots"] == 0 and nov4["per_lot"] > nov4["budget"] == round(0.02 * 80456.1, 2)
    for bad in ((None, 90.0, 65, 1e5), (100.0, None, 65, 1e5), (100.0, 100.0, 65, 1e5), (100.0, 90.0, 0, 1e5),
                (100.0, 90.0, 65, None), (100.0, 90.0, 65, 0.0)):
        assert ps.size_advice(*bad) is None


def test_the_size_line_says_what_the_rule_gives_and_never_reads_over_the_rule_as_two_percent():
    a = ps.size_advice(100.0, 90.0, 65, 100_000.0, "NFO")
    line = ps.size_line(a, bought_lots=5)
    assert line.startswith("📏 The Sentinel's size for this: 2 lots (130), about −₹")
    assert "of your cash: it never risks more than 2% of its cash on one trade." in line
    assert line.endswith(" You bought 5 lots.")
    assert ps.size_line(a, bought_lots=2).endswith("on one trade.")            # at the rule: nothing added
    none = ps.size_line(ps.size_advice(598.75, 499.9, 20, 80456.1, "BFO"), bought_lots=5, verb="asked about")
    assert "size for this: none. One lot (20) loses about ₹" in none
    assert "2.5% of your cash" in none                          # one decimal: 2.5%, never "2%" or "3%"
    assert "(₹1,609 for you): it would pass, or take a cheaper option" in none
    assert none.endswith("one lot is the least at risk. You asked about 5 lots.")
    assert ps.size_line(None) == ""


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
    assert ps.record_line(recs, "UNUSUAL_SIZE") == (
        "📊 Your record since 28 Oct: buys much bigger than your usual, 22 trades, −₹11,000; your usual size, "
        "44 trades, +₹6,380.")
    assert ps.record_line(recs, "CHASED_SPIKE") == ""                       # never a line for an unsupported one
    assert ps.record_line(recs, "AFTER_LOSS") == ""                         # TOO_FEW here
    # A day's records are worked out once and only from the days before it.
    early = ps.records(db, "2026-10-29")["UNUSUAL_SIZE"]          # only Oct 28 before it: no usual-size trade yet
    assert early["verdict"] == "TOO_FEW" and early["warned"]["n"] == 22 and early["unwarned"]["n"] == 0
    assert ps.record_line(ps.records(db, "2026-10-29"), "UNUSUAL_SIZE") == ""
    assert ps.records(db, "2026-10-28") == {}                                  # nothing stored before it
    morning = ps.morning_lines(recs)
    assert morning[0] == ps.record_line(recs, "UNUSUAL_SIZE")
    assert morning[-1].startswith("🤖 The Sentinel's own trades come here as it takes them (paper")


@pytest.mark.asyncio
async def test_the_check_leaves_out_the_chased_spike_warning_while_its_score_refutes_it(advice):
    plan = pw.Plan(entry=75.5, qty=65, stop=60.0, stop_basis="SWING", swing=15.5, loss=1050.0, cash=20000.0,
                   run_pct=0.31, run_from=57.5)
    kwargs = dict(lots=1, qty=65, given=75.5, future="NIFTY future", opt_type="PE")
    warned = pw.check_text("NIFTY 22300 PE", None, plan, None, **kwargs)
    assert "chased spike" in warned and "up 31% in the last 15 min" in warned
    quiet = pw.check_text("NIFTY 22300 PE", None, plan, None, spike_warn=False, size_note="📏 size",
                          notes=["📊 record"], sentinel_line="🤖 holds nothing", **kwargs)
    assert "chased spike" not in quiet and "up 31% in the last 15 min" in quiet      # the fact stays
    lines = quiet.splitlines()
    assert lines.index("📏 size") == 2 and lines[-3:] == ["📊 record", "🤖 holds nothing", pw.CHECK_NOTE]


# ---------------------------------------------------------------------------
# the PLAN, ADDED and DAY texts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_plan_carries_the_sentinels_size_and_on_a_supported_warning_the_partners_record(advice):
    db = await _three_kinds_of_buy()
    plan = pw.Plan(entry=598.75, qty=100, stop=499.9, stop_basis="SWING", swing=98.82, loss=10051.0, cash=80456.1)
    size, notes = await pw._sentinel_notes(db, DAY, plan, lot=20, exchange="BFO", bought=100, bought_px=598.75,
                                           lots=5, usual=0.31, after_loss={"loss": 2957.0, "at": "10:23", "minutes": 1})
    assert size.startswith("📏 The Sentinel's size for this: none.") and size.endswith("You bought 5 lots.")
    # 74% of the cash against a usual 31%: the size record; after a loss: the Sentinel's own rule (no record: TOO_FEW).
    assert notes == [ps.record_line(ps.records(db, DAY), "UNUSUAL_SIZE"), ps.AFTER_LOSS_RULE]
    trip = SimpleNamespace(tradingsymbol="SENSEX26N0576700CE", exchange="BFO", product="NRML", open_qty=100, qty=100,
                           entry=598.75, carried=False, first_at=NOW, basis="CONFIRMED")
    text = pw.plan_text(trip, plan, lots=5, size_note=size, notes=notes, usual=0.31)
    lines = text.splitlines()
    assert lines[1].startswith("🛑 Plan stop ₹499.9") and lines[2].startswith("⚠️ ₹59,875 in this trade, 74%")
    assert lines[3] == size and ps.AFTER_LOSS_RULE in lines
    # Without a stop to size from (no market data), no size line; switched off, nothing at all.
    assert (await pw._sentinel_notes(db, DAY, pw.Plan(entry=100.0, qty=65, loss=6500.0, cash=80000.0), lot=65,
                                     exchange="NFO", bought=65, bought_px=100.0, lots=1, usual=None,
                                     after_loss=None)) == ("", [])
    settings.PARTNER_SENTINEL_ADVICE_ENABLED = False
    assert (await pw._sentinel_notes(db, DAY, plan, lot=20, exchange="BFO", bought=100, bought_px=598.75, lots=5,
                                     usual=0.31, after_loss={"loss": 1.0, "at": "x", "minutes": 1})) == ("", [])


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
async def test_the_sentinels_fno_buy_is_offered_once_fresh_with_its_stop_size_and_record(advice):
    db = settings.DB_PATH
    await _fno(db, entry_date="2026-11-03", entry_time="2026-11-03T10:00:00+05:30", status="CLOSED",
               exit_time="2026-11-03T10:30:00+05:30", exit_date="2026-11-03", exit_premium=110.0, pnl=-1500.0,
               exit_reason="underlying_stop")
    trade_id = await _fno(db)
    await _fno(db, strategy="N11_ADD", tradingsymbol="NIFTY26N1024000PE")                  # an earned lot: not a trade
    await _fno(db, entry_time=(NOW - timedelta(minutes=9)).isoformat(), tradingsymbol="NIFTY26N1023900PE")  # stale
    found = ps.events(db, DAY, NOW)
    assert [f[0] for f in found] == [f"sentinel:{DAY}:fno:{trade_id}:buy"] and found[0][1] == "SENTINEL"
    text = found[0][2](28600.0)
    trade = ps.fno_trades(db, DAY)[0]
    stop = ps.option_stop(trade)
    assert stop == round(max(120.5 - 0.45 * 60.0, 90.4), 2) == 93.5
    assert text.splitlines()[0] == "🤖 The Sentinel's own trade (paper, not a tip): bought NIFTY 24000 PE (10 Nov) at ₹120.5 at 10:05."
    assert "🛑 Its stop: NIFTY future 24,110, about ₹93.5 on the option. 🎯 Its target: NIFTY future 23,950." in text
    assert "📏 For your ₹28,600 cash: one lot (65) loses about ₹" in text
    assert "more than the 2% it risks itself (₹572 for you). If you follow, one lot at most." in text
    assert "📊 Its last 1 paper trades: 0 won, −₹750 a lot after charges." in text
    assert text.splitlines()[-1] == "I'll tell you when it sells. Whether to follow is your call."


@pytest.mark.asyncio
async def test_a_sentinel_sale_is_told_only_after_its_buy_was_sent_with_what_the_partner_still_holds(advice):
    db = settings.DB_PATH
    await pw.init_partner_watch_db(db)
    pw._state.cash = 80000.0
    trade_id = await _fno(db, status="CLOSED", exit_time=(NOW - timedelta(seconds=20)).isoformat(), exit_date=DAY,
                          exit_premium=140.0, pnl=2400.0, exit_reason="trail_stop")
    holdings = [SimpleNamespace(tradingsymbol="NIFTY26N1024000PE", open_qty=65)]
    first = await pw._sentinel_items(db, DAY, NOW, holdings)
    assert [i[0] for i in first] == [f"sentinel:{DAY}:fno:{trade_id}:buy"]        # the sale waits for its buy
    await pw._enqueue_many(db, DAY, first, NOW)
    assert await pw._sentinel_items(db, DAY, NOW, holdings) == []                # not again
    async with aiosqlite.connect(db) as conn:
        await conn.execute("UPDATE partner_watch_messages SET sent=1 WHERE message_key=?", (first[0][0],))
        await conn.commit()
    sale = await pw._sentinel_items(db, DAY, NOW, holdings)
    assert [i[1] for i in sale] == ["SENTINEL_EXIT"]
    assert sale[0][3]["text"] == ("🤖 The Sentinel sold its NIFTY 24000 PE at ₹140 at 10:05 (its trailing stop): "
                                  "+₹1,200 a lot after charges (paper). You still hold 65 of it.")
    # The outbox sends it as a fixed text, never muted on a quiet day.
    assert "SENTINEL" in pw.ALWAYS_SENT and "SENTINEL_EXIT" in pw.ALWAYS_SENT
    entry = pw._Entry(sale[0][0], "SENTINEL_EXIT", json.dumps(sale[0][3]), 0, "queued", None, NOW.isoformat(), None,
                      None, NOW.isoformat(), None)
    built = await pw._build(db, entry, NOW, None)
    assert built[0] == sale[0][3]["text"]


@pytest.mark.asyncio
async def test_the_expiry_main_ticket_is_offered_with_its_size_capped_at_its_own_lots(advice, monkeypatch):
    db = settings.DB_PATH
    monkeypatch.setattr(settings, "EXPIRY_MAIN_STRATEGY", "E032")
    p = {"id": 7, "day": DAY, "underlying": "SENSEX", "play": "E032", "exchange": "BFO", "symbol": "SENSEX26N0576500PE",
         "lot_size": 20, "lots": 2, "lots_open": 2, "entry_ts": (NOW - timedelta(minutes=2)).isoformat(),
         "entry_price": 40.0, "stop": 26.0, "underlying_stop": 76950.0, "direction": -1, "status": "OPEN",
         "net_pnl": -40.0, "e02_policy": {"flat": "15:14"},
         "_events": [{"ts": (NOW - timedelta(minutes=2)).isoformat(), "action": "BUY", "lots": 2, "price": 40.0}]}
    with sqlite3.connect(expiry_e02.path_for(db, expiry_e02.E032)) as c:
        c.execute("CREATE TABLE e02_positions(id INTEGER PRIMARY KEY, day TEXT, status TEXT, payload TEXT NOT NULL)")
        c.execute("INSERT INTO e02_positions VALUES(7, ?, 'OPEN', ?)", (DAY, json.dumps(p)))
    found = ps.events(db, DAY, NOW)
    assert [f[0] for f in found] == [f"sentinel:{DAY}:exp:7:buy"]
    text = found[0][2](200_000.0)
    assert text.splitlines()[0] == ("🤖 The Sentinel's expiry ticket (paper, not a tip): bought SENSEX 76500 PE "
                                    "(expires today) at ₹40 at 10:04.")
    assert "🛑 Its stop ₹26 or SENSEX 76,950. At 2x (₹80) it sells part and lets the rest run; it sells everything from 15:14." in text
    assert "📏 For your ₹200,000 cash its size rule gives 2 lots (40)" in text   # 2% of 2 lakh allows more: its own 2
    assert "a lot can lose all of its ₹800" in text and "Its first SENSEX expiry ticket on paper" in text
    # Not the main ticket: nothing from the expiry book.
    monkeypatch.setattr(settings, "EXPIRY_MAIN_STRATEGY", "ABC")
    assert ps.events(db, DAY, NOW) == []


@pytest.mark.asyncio
async def test_a_check_says_what_the_sentinel_holds_and_off_means_the_watch_as_before(advice):
    db = settings.DB_PATH
    await _fno(db)
    assert ps.open_line(db, DAY, "NIFTY") == "🤖 The Sentinel now holds NIFTY 24000 PE (paper, bought 10:05 at ₹120.5)."
    assert ps.open_line(db, DAY, "SENSEX") == "🤖 The Sentinel holds nothing on SENSEX now (0 trades today)."
    settings.PARTNER_SENTINEL_ADVICE_ENABLED = False
    assert await pw._sentinel_items(db, DAY, NOW, []) == [] and await pw._morning_lines(db, DAY, NOW) == []


def test_a_missing_store_tells_nothing_and_never_raises(tmp_path):
    missing = str(tmp_path / "none.db")
    assert ps.fno_trades(missing, DAY) == [] and ps.fno_record(missing, DAY) is None
    assert ps.events(missing, DAY, NOW) == []
