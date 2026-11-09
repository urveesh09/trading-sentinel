"""[N09 2026-11-09] The partner's coach: a morning plan with their own record and a rule they choose, short buy and day
messages, a losing run with a range to wait for and one message when it breaks, and the day's habits in the evening.

Nov 9: 31 buys from 09:15 to 12:04 and 59 messages by noon (six-to-eight-line PLANs after each buy, six identical
DAY updates). The record over 10 sessions: mornings ended down on 8; trades closed within 2 minutes won 14%, held
15-60 minutes 49%. Messages only: nothing here places or blocks an order.
"""
import json
from dataclasses import replace
from datetime import date, datetime, timedelta

import aiosqlite
import pandas as pd
import pytest

import partner_buyer
import partner_coach
import partner_habits as ph
import partner_watch as pw
from config import settings
from tests.test_partner_broker_sync import kite, partner_app  # noqa: F401
from tests.test_partner_watch import (D, FakeMarket, SYMBOL, _bars, _clocked, _holding, _login, _market,  # noqa: F401
                                      _messages, _o, watch)

DAY = "2026-10-23"


@pytest.fixture
def coach(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_WATCH_COACH_ENABLED", True)
    yield


# ---------------------------------------------------------------------------
# the record and the habits (partner_habits)
# ---------------------------------------------------------------------------

def _trip(day, first, minutes, realised, *, key=None, prior=None, entry=80.0, bought=65, symbol=SYMBOL,
          paid_share=0.2, usual=0.2, carried=0):
    start = datetime.fromisoformat(f"{day}T{first}:00+05:30")
    closed = start + timedelta(minutes=minutes) if minutes is not None else None
    exit_ = entry + realised / bought if realised is not None else None
    return {"session_date": day, "position_key": key or f"{day}-{first}", "exchange": "NFO", "tradingsymbol": symbol,
            "product": "NRML", "first_at": start.isoformat(), "closed_at": closed.isoformat() if closed else None,
            "bought": bought, "sold": bought if closed else 0, "entry": entry, "exit": exit_, "realised": realised,
            "orders": 2, "exact": 1, "carried": carried, "run_pct": None,
            "prior_exit": json.dumps(prior or {"state": "NONE"}), "usual": usual, "cash": 100000.0,
            "opening_order": None, "opening_qty": bought, "opening_value": entry * bought, "opening_final": 1,
            "opening_exact": 1, "paid_share": paid_share, "updated_at": start.isoformat()}


def _history(days=6, quick=15, long_=15):
    """``days`` sessions: a losing morning trade and a winning afternoon one each; then ``quick`` trades closed in
    a minute (2 of them won) and ``long_`` held 20 minutes (8 won)."""
    rows = []
    for i in range(days):
        day = f"2026-10-{12 + i:02d}"
        rows += [_trip(day, "09:30", 10, -500.0), _trip(day, "13:30", 10, 300.0)]
    for i in range(quick):
        rows.append(_trip("2026-10-12", f"14:{i:02d}", 1, 100.0 if i < 2 else -100.0))
    for i in range(long_):
        rows.append(_trip("2026-10-13", f"12:{i:02d}", 20, 200.0 if i < 8 else -100.0))
    return rows


def test_the_record_says_only_what_meets_its_frozen_sample():
    rec = ph.record(_history())
    assert rec["days"] == 6 and (rec["morning_red"], rec["morning_days"]) == (6, 6)
    assert rec["quick"] == (2, 15) and rec["long"] == (8, 15)
    assert ph.record_line(rec) == ("📊 Your last 6 days: mornings (to 12:00) ended down on 6 of 6 days · trades held "
                                   "15–60 min won 53%, under 2 min 13%.")
    assert ph.hold_line(rec) == "📊 Your trades held 15–60 min won 53%; under 2 min, 13%."
    thin = ph.record(_history(days=4, quick=14))
    assert ph.record_line(thin) == "" and ph.hold_line(thin) == ""      # 4 sessions; 14 quick trades
    assert ph.record_line(ph.record([])) == ""


def test_the_habits_of_a_day_and_the_one_thing_to_try_tomorrow():
    day = "2026-11-09"
    loss = {"state": "KNOWN", "result": -4040.0, "minutes": 0, "at": "09:27", "bought": 260}
    rows = [_trip(day, "09:15", 1.5, -6400.0, entry=676.0, bought=40),
            _trip(day, "09:17", 10, -4040.0, entry=50.0, bought=260),
            _trip(day, "09:27", 14, -20500.0, entry=248.0, bought=260, prior=loss),        # 5x the 09:17 trade
            _trip(day, "11:33", 5, 9086.0, entry=109.35, bought=130,
                  prior={"state": "KNOWN", "result": -1800.0, "minutes": 0}),
            _trip(day, "12:04", None, None, entry=26.0, bought=195)]                          # still open
    tags = ph.tags_of(rows[2], rows)
    assert tags == {"QUICK_REBUY", "BIG_AFTER_LOSS", "EARLY"}
    assert ph.tags_of(rows[0], rows) == {"QUICK_EXIT", "EARLY"}
    habits = ph.day_habits(rows, lowered=8)
    assert (habits["buys"], habits["early"], habits["quick_rebuys"], habits["big_after_loss"]) == (5, 3, 2, 1)
    assert habits["median_hold"] == 7.5 and habits["result_sign"] == -1
    assert ph.costliest(rows) == {"tag": "EARLY", "n": 3, "sum": -30940.0}
    lines = ph.evening_lines(rows, 8, pw._option)
    assert lines[0] == ("🧭 Habits today: 5 buys (3 before 10:00) · median hold 7.5 min · 2 bought within 2 min of a "
                        "loss · 8 stops moved down.")
    assert lines[1] == "✅ Best trade: 11:33 NIFTY 22300 PE, +64% in 5 min."
    assert lines[2] == ("🎯 Tomorrow, one thing: take at most 3 trades before 10:00. Today's 3 buys before 10:00: "
                        "−₹30,940 together.")
    assert ph.evening_lines([], 0, pw._option) == []


@pytest.mark.asyncio
async def test_the_scorecard_and_the_week_read_the_stored_trades_only(tmp_path):
    db = str(tmp_path / "habits.db")
    await pw.init_partner_watch_db(db)
    rows = [_trip("2026-10-26", "09:30", 1, -100.0), _trip("2026-10-26", "13:00", 30, 400.0),
            _trip("2026-10-30", "09:20", 3, -200.0), _trip("2026-11-02", "10:30", 20, 300.0),
            _trip("2026-11-06", "09:40", 1, -50.0, prior={"state": "KNOWN", "result": -10.0, "minutes": 1})]
    async with aiosqlite.connect(db) as conn:
        cols = list(rows[0])
        await conn.executemany(f"INSERT INTO partner_watch_trips({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                               [tuple(r[c] for c in cols) for r in rows])
        await conn.execute("INSERT INTO partner_watch_messages(message_key, session_date, kind, created_at, sent, text) "
                           "VALUES('l1','2026-11-06','LOWERED','x',1,'t')")
        await conn.commit()
    days = ph.scorecard(db, "2026-10-26", "2026-11-06")
    assert [d["day"] for d in days] == ["2026-10-26", "2026-10-30", "2026-11-02", "2026-11-06"]
    assert days[-1]["lowered"] == 1 and days[-1]["quick_rebuys"] == 1 and days[0]["result_sign"] == 1
    summary = ph.summarize(days)
    assert summary["sessions"] == 4 and summary["red_sessions"] == 2
    assert summary["quick_exit_share"] == 0.375                   # (0.5 + 0 + 0 + 1) / 4 sessions
    this, last = ph.weeks(db, "2026-11-06")
    assert [d["day"] for d in this] == ["2026-11-02", "2026-11-06"]
    assert [d["day"] for d in last] == ["2026-10-26", "2026-10-30"]
    assert ph.week_line(this, last).startswith("📈 This week against last: buys before 10:00 1 → 0.5 a day")
    assert ph.sessions_before(db, "2026-11-02") == ["2026-10-26", "2026-10-30"]
    assert ph.load_rows(str(tmp_path / "missing.db"), "2026-10-01", "2026-11-01") == []     # never created


# ---------------------------------------------------------------------------
# the texts
# ---------------------------------------------------------------------------

def _plan(**over):
    values = dict(entry=80.0, qty=130, stop=60.0, stop_basis="INDEX", stop_index=22450.0, loss=2700.0,
                  cash=100000.0, target=110.0, target_index=22600.0)
    values.update(over)
    return pw.Plan(**values)


def test_the_short_plan_is_four_lines_at_most_with_one_warning():
    holding = _holding(130, entry=80.0)
    after = {"loss": 4040.0, "at": "09:27", "minutes": 0, "last_value": 2600.0}
    text = pw.short_plan_text(holding, _plan(), lots=2, bought=(130, 80.0), after_loss=after, usual=0.2)
    lines = text.splitlines()
    assert lines[0] == "🟢 You bought NIFTY 22300 PE · 2 lots (130) at ₹80"
    assert lines[1] == "🛑 Plan stop ₹60: about −₹2,700 with charges, 3% of your cash if it sells there."
    assert lines[2] == "⚠️ 4× the size of the trade you just lost (−₹4,040), 0 min after it."
    assert len(lines) <= 4 and "Target zone" not in text and "Sentinel risks" not in text
    big = pw.short_plan_text(holding, _plan(), lots=2, bought=(130, 80.0), usual=0.04)
    assert "⚠️ 10% of your cash in this trade: much more than your usual 4%." in big
    soon = pw.short_plan_text(holding, _plan(), lots=2, bought=(130, 80.0),
                              after_loss={"loss": 500.0, "at": "10:00", "minutes": 3, "last_value": 9000.0})
    assert "⚠️ 3 min after a −₹500 loss." in soon
    calm = pw.short_plan_text(holding, _plan(), lots=2, bought=(130, 80.0))
    assert len(calm.splitlines()) <= 3 and "⚠️" not in calm
    fresh = _clocked({"bid": 79.0, "ask": 79.1, "ltp": 79.05}, at=D(10, 0, 5))
    common = pw.short_plan_text(holding, _plan(), lots=2, bought=(130, 80.0), quote=fresh, now=D(10, 0, 6),
                                after_loss={"loss": 500.0, "at": "09:58", "minutes": 2, "last_value": 9000.0})
    assert common.splitlines() == [
        "🟢 You bought NIFTY 22300 PE · 2 lots (130) at ₹80",
        "🛑 Place an SL sell now: trigger ₹60, limit a little under it. If it sells there: about −₹2,700 with "
        "charges, 3% of your cash.",
        "⚠️ 2 min after a −₹500 loss."]
    card = {"at": "11:20", "buy_limit": 78.0, "target": 120.0, "target_low": 100.0}
    carded = pw.short_plan_text(holding, _plan(stop_basis="CARD"), lots=2, bought=(130, 80.0), card=card)
    assert carded.splitlines()[0].endswith("on the 11:20 card") and "🎯 Card target ≈₹100–120." in carded
    assert "⚠️ You paid ₹80; the card said buy up to ₹78." in carded


def test_the_short_day_text_is_two_lines():
    day = {"net": -22443.0, "share": 0.2415, "closed": 5, "lost": 5, "won": 0, "charges": 391.0, "held": 0,
           "quick": 4, "quick_sum": -16036.0}
    assert pw.short_day_text(day, 92941.5).splitlines() == [
        "📉 Today so far: −₹22,443 after charges, 24% of your cash · 5 closed, 5 lost · charges ≈₹391.",
        "4 of them bought within 30 min of a losing exit: −₹16,036 together."]
    assert [pw.coach_step(s) for s in (0, 1, 2, 3, 4, 5, 6, 9)] == [0, 0, 2, 2, 4, 4, 6, 6]


def test_the_rule_the_partner_types():
    assert pw.parse_rule("rule 3") == {"trades": 3, "stop": None}
    assert pw.parse_rule("Rule 10%") == {"trades": None, "stop": 0.10}
    assert pw.parse_rule("rule 2 trades −8%") == {"trades": 2, "stop": 0.08}
    assert pw.parse_rule("rule none") == {"trades": None, "stop": None}
    for unclear in ("rule", "rule 99", "rule 80%", "rule soon"):
        assert pw.parse_rule(unclear) is None
    assert pw.rule_label({"trades": 3, "stop": 0.1}) == "3 trades before 10:00 · stop at −10% of cash"


def test_the_watch_on_message_says_what_the_coach_sends_in_two_short_lines():
    text = pw.WATCH_ON_COACH_TEXT.format(close="15:40")
    assert len(text.splitlines()) == 2 and len(text) <= 260
    assert "a losing run, the day's loss at 20/40/60% of cash" in text


def test_the_brief_no_longer_says_scalp_or_take_profits_quickly():
    assert partner_buyer._dte_note(0) == "expiry today: time value melts fast"
    assert partner_buyer._premium_read("RICH") == "premium rich (options cost more than usual)"


def test_a_losing_run_and_its_told_size():
    trips = [pw.Trip(k, "NFO", SYMBOL, "NRML", D(10, i), bought=65, sold=65, buy_value=65 * 80.0,
                     sell_value=65 * (70.0 if k != "w" else 90.0), buy_orders=1, sell_orders=1,
                     closed_at=D(10, i + 1)) for i, k in enumerate(["a", "w", "b", "c", "d"])]
    run = pw.losing_run(trips)
    assert [t.key for t in run] == ["b", "c", "d"] and pw.streak_size(run) == 2
    assert pw.losing_run(trips[:2]) == [] and pw.streak_size(trips[:1]) == 0
    fast = [replace(t, key=f"f{i}", closed_at=D(10, 30 + i)) for i, t in enumerate(trips[2:] + trips[:1])]
    assert pw.streak_size(fast) == 2                              # 4 losses in 4 minutes: the 2nd is the message
    slow = fast[:3] + [replace(fast[3], closed_at=D(10, 45))]
    assert pw.streak_size(slow) == 4                              # the 4th 14 min after the 2nd


# ---------------------------------------------------------------------------
# through the tick
# ---------------------------------------------------------------------------

def _flat_futures(until: datetime, *, low=22480.0, high=22520.0, close=22500.0, breaks=None) -> pd.DataFrame:
    """Five-minute future bars from 09:15 to ``until`` in a 22,480-22,520 band; ``breaks``: {bar start: close}."""
    index = list(pd.date_range(D(9, 15).replace(tzinfo=None), until.replace(tzinfo=None), freq="5min"))
    rows = [{"open": close, "high": high, "low": low, "close": close, "volume": 1.0} for _ in index]
    for at, value in (breaks or {}).items():
        rows[index.index(at.replace(tzinfo=None))].update(close=value, high=max(high, value), low=min(low, value))
    return pd.DataFrame(rows, index=index)


@pytest.mark.asyncio
async def test_the_morning_plan_comes_once_and_a_tap_sets_todays_rule(watch, kite, coach):
    """The 09:00 prompt job sends it (the watch's ticks start at 09:15), logged in or not; a later tick, a login
    or a restart sends no second one."""
    db = settings.DB_PATH
    await _login(D(8, 55))
    assert await pw.send_gameplan(D(8, 59)) is False              # before 09:00
    assert (await pw.watch_prompt(D(9, 0)))["reason"] == "connected"
    await pw.settle()
    await pw.on_login(D(9, 2))
    market = _market(D(9, 15))
    await pw.watch_tick(D(9, 15, 5), market=market)
    await pw.settle()
    plans = [m for m in watch if m["kind"] == "watch_gameplan"]
    assert len(plans) == 1
    assert plans[0]["text"].startswith("🧭 Plan for today · Fri 23 Oct")
    assert "send more for the full plan" in plans[0]["text"]
    buttons = [b["callback_data"] for row in plans[0]["keyboard"]["inline_keyboard"] for b in row]
    assert buttons == ["watch:rule:20261023:T3", "watch:rule:20261023:S10", "watch:rule:20261023:BOTH",
                       "watch:rule:20261023:NONE"]
    assert [m["kind"] for m in watch].index("watch_gameplan") < [m["kind"] for m in watch].index("watch_watch_on")
    assert await pw.handle_button(db, "watch:rule:20261022:BOTH", D(9, 15, 8)) == "That plan was for an earlier day."
    toast = await pw.handle_button(db, "watch:rule:20261023:BOTH", D(9, 15, 8))
    assert toast.startswith("✅ Today's rule: 3 trades before 10:00 · stop at −10% of cash.")
    assert watch[-1]["kind"] == "watch_rule" and watch[-1]["text"] == toast
    pw.reset()                                                    # a restart keeps the rule and sends no second plan
    await pw.watch_tick(D(9, 16), market=market)
    await pw.settle()
    assert pw._state.rule == {"trades": 3, "stop": 0.1}
    assert len([m for m in watch if m["kind"] == "watch_gameplan"]) == 1
    assert await pw.handle_button(db, "watch:quiet:20261023", D(9, 16, 5)) == pw.QUIET_GONE  # the old button


@pytest.mark.asyncio
async def test_the_coach_off_sends_no_morning_plan(watch, kite):
    await _login(D(8, 55))
    await pw.watch_prompt(D(9, 0))
    await pw.watch_tick(D(9, 15, 5), market=_market(D(9, 15)))
    await pw.settle()
    assert "watch_gameplan" not in [m["kind"] for m in watch]
    assert await pw.send_gameplan(D(9, 5)) is False


@pytest.mark.asyncio
async def test_a_typed_rule_is_reminded_once_and_the_plan_is_short_with_more_on_request(watch, kite, coach):
    db = settings.DB_PATH
    await _login()
    assert await pw.answer_check(db, "rule 2", D(9, 20), key="check:1", asked_at=D(9, 20)) == "rule"
    assert watch[-1]["kind"] == "watch_rule" and watch[-1]["text"].startswith("✅ Today's rule: 2 trades before 10:00.")
    assert await pw.answer_check(db, "more", D(9, 21), key="check:2", asked_at=D(9, 21)) == "more"
    assert watch[-1]["text"] == "📋 No buy today yet: the full plan comes with the first one."
    market = _market(D(9, 40, 5))
    await pw.watch_tick(D(9, 29, 55), market=market)
    await pw.settle()
    kite["orders"] = [_o("101", "BUY", D(9, 30), average_price=80.0), _o("102", "SELL", D(9, 35), average_price=82.0),
                      _o("103", "BUY", D(9, 40), average_price=75.05)]
    await pw.watch_tick(D(9, 40, 5), market=market)
    await pw.settle()
    kinds = [m["kind"] for m in watch]
    assert kinds.count("watch_rule") == 2 and kinds.count("watch_plan") == 1
    reminder = next(m for m in watch[2:] if m["kind"] == "watch_rule")
    assert reminder["text"] == "🧭 Trade 2 before 10:00: your rule this morning was 2. Your call from here."
    plan = next(m for m in watch if m["kind"] == "watch_plan")["text"]
    assert plan.startswith("🟢 You bought NIFTY 22300 PE · 1 lot (65) at ₹75.05") and len(plan.splitlines()) <= 4
    assert "Target zone" not in plan
    await pw.watch_tick(D(9, 40, 30), market=market)
    await pw.settle()
    assert [m["kind"] for m in watch].count("watch_rule") == 2               # once
    assert await pw.answer_check(db, "more", D(9, 41), key="check:3", asked_at=D(9, 41)) == "more"
    full = watch[-1]["text"]
    assert full.startswith("📋 The full plan for your NIFTY 22300 PE buy, as worked out at 09:40")
    assert "🎯 Target zone" in full and len(full.splitlines()) > len(plan.splitlines())


@pytest.mark.asyncio
async def test_a_losing_run_promises_a_break_and_tells_it_once(watch, kite, coach):
    """Two losses by 10:10: one losing-run message with the future's last 30 minutes in 5-minute bars; the 10:10
    bar closes above that range, told once at 10:15; the day's loss (36% of the cash) is told at its 20% step only,
    in two lines, and the partner's 20% rule once."""
    db = settings.DB_PATH
    await _login()
    futures = _flat_futures(D(10, 30), breaks={D(10, 10): 22561.0})
    option = _bars(D(9, 30), 60, 70.0, 76.0, 75.0)
    market = FakeMarket(option=option, futures=futures,
                        quotes={SYMBOL: {"bid": 75.0, "ask": 75.1, "ltp": 75.05}})
    assert await pw.answer_check(db, "rule 20%", D(9, 50), key="check:1", asked_at=D(9, 50)) == "rule"
    await pw.watch_tick(D(9, 59, 55), market=market)
    await pw.settle()
    kite["orders"] = [_o("101", "BUY", D(10, 0), average_price=80.0), _o("102", "SELL", D(10, 5), average_price=60.0),
                      _o("103", "BUY", D(10, 6), average_price=80.0), _o("104", "SELL", D(10, 9), average_price=60.0)]
    await pw.watch_tick(D(10, 10, 5), market=market)
    await pw.settle()
    kinds = [m["kind"] for m in watch]
    assert kinds.count("watch_streak") == 1 and kinds.count("watch_day") == 1
    streak = next(m for m in watch if m["kind"] == "watch_streak")["text"].splitlines()
    assert streak == ["⏸ 2 losses in a row (10:05, 10:09).",
                      "NIFTY fut 22,480–22,520 over the last 30 min (5-min bars): no break yet. I'll message you when "
                      "a 5-min bar closes outside it."]
    day = next(m for m in watch if m["kind"] == "watch_day")["text"].splitlines()
    assert len(day) == 2 and day[0].startswith("📉 Today so far: −₹2,") and "2 closed, 2 lost" in day[0]
    rows = {r[0]: r for r in await _messages(db)}
    assert f"day:{DAY}:2" in rows and f"rule:{DAY}:stop" in rows
    stop = next(m for m in watch if m["kind"] == "watch_rule" and m["text"].startswith("🧭"))["text"]
    assert stop.endswith("past the −20% you chose this morning. Your call from here.")
    for at in (D(10, 12), D(10, 14, 50)):                        # the 10:10 bar is not done yet
        await pw.watch_tick(at, market=market)
        await pw.settle()
    assert "watch_break" not in [m["kind"] for m in watch]
    await pw.watch_tick(D(10, 15, 5), market=market)
    await pw.settle()
    breaks = [m for m in watch if m["kind"] == "watch_break"]
    assert len(breaks) == 1
    assert breaks[0]["text"] == ("🔔 NIFTY fut: the 5-min bar to 10:15 closed at 22,561, above the 22,480–22,520 range "
                                 "I sent at 10:10. The range has broken upward.")
    for at in (D(10, 20, 5), D(10, 25, 5)):
        await pw.watch_tick(at, market=market)
        await pw.settle()
    assert len([m for m in watch if m["kind"] == "watch_break"]) == 1           # once
    assert len([m for m in watch if m["kind"] == "watch_streak"]) == 1


@pytest.mark.asyncio
async def test_the_first_patient_win_of_the_day_is_said_once(watch, kite, coach):
    """A win held 15 minutes or more, said as it happens, once a day; a quick win is not."""
    await _login()
    market = _market(D(10, 40))
    await pw.watch_tick(D(9, 59, 55), market=market)
    await pw.settle()
    kite["orders"] = [_o("101", "BUY", D(10, 0), average_price=80.0), _o("102", "SELL", D(10, 1), average_price=85.0),
                      _o("103", "BUY", D(10, 2), average_price=80.0), _o("104", "SELL", D(10, 20), average_price=90.0)]
    await pw.watch_tick(D(10, 20, 5), market=market)
    await pw.settle()
    good = [m for m in watch if m["kind"] == "watch_good"]
    assert len(good) == 1
    assert good[0]["text"].startswith("✅ NIFTY 22300 PE: held 18 min, +₹") and "(+12%)" in good[0]["text"]
    assert good[0]["text"].endswith("Giving it time worked here.")         # no record stored yet
    kite["orders"] += [_o("105", "BUY", D(10, 21), average_price=80.0), _o("106", "SELL", D(10, 40), average_price=95.0)]
    await pw.watch_tick(D(10, 40, 5), market=market)
    await pw.settle()
    assert len([m for m in watch if m["kind"] == "watch_good"]) == 1        # once a day
    record = {"quick": (5, 35), "long": (51, 104)}
    trip = pw.Trip("t", "NFO", SYMBOL, "NRML", D(11, 0), bought=65, sold=65, buy_value=65 * 80.0,
                   sell_value=65 * 100.0, buy_orders=1, sell_orders=1, closed_at=D(11, 25))
    assert pw.good_text(trip, record).endswith("That's your strongest pattern: trades you hold 15–60 min won 49%.")


@pytest.mark.asyncio
async def test_a_break_is_never_told_without_its_losing_run_message(watch, kite, coach):
    """The promise goes with the losing-run message: a range armed by a message that was never sent is dropped."""
    db = settings.DB_PATH
    await _login()
    await pw.init_partner_watch_db(db)
    arm = {"underlying": "NIFTY", "label": "NIFTY fut", "exchange": "NFO", "option": SYMBOL, "low": 22480.0,
           "high": 22520.0, "after": D(10, 10).replace(tzinfo=None).isoformat(), "streak": "streak:x:y:2",
           "armed_at": D(10, 10).isoformat(), "told_at": "10:10", "state": "ARMED"}
    await pw._set_state(db, f"break:{DAY}:NIFTY", json.dumps(arm), D(10, 10))
    async with aiosqlite.connect(db) as conn:
        await conn.execute("INSERT INTO partner_watch_messages(message_key, session_date, kind, created_at, sent, text, "
                           "outcome) VALUES('streak:x:y:2', ?, 'STREAK', 'x', 0, '', 'expired')", (DAY,))
        await conn.commit()
    market = FakeMarket(option=_bars(D(9, 30), 60, 70.0, 76.0, 75.0),
                        futures=_flat_futures(D(10, 30), breaks={D(10, 10): 22561.0}),
                        quotes={SYMBOL: {"bid": 75.0, "ask": 75.1, "ltp": 75.05}})
    await pw.watch_tick(D(10, 15, 5), market=market)
    await pw.settle()
    assert "watch_break" not in [m["kind"] for m in watch]
    assert json.loads(await pw._get_state(db, f"break:{DAY}:NIFTY"))["state"] == "UNSENT"


@pytest.fixture
def owner(monkeypatch):
    """[N09b] The owner's chat (operator_alert), faked: what was told, and whether the gateway takes it."""
    monkeypatch.setattr(settings, "PARTNER_WATCH_OWNER_HEADSUP_ENABLED", True)
    told, accept = [], [True]

    async def notify(message, *, event="operator_alert"):
        told.append((event, message))
        return accept[0]

    monkeypatch.setattr("operator_alert.notify_operator", notify)
    yield told, accept


@pytest.mark.asyncio
async def test_the_owner_gets_one_heads_up_a_day_after_four_losses_in_a_row(watch, kite, owner):
    told, _accept = owner
    await _login()
    market = _market(D(10, 20))
    await pw.watch_tick(D(9, 59, 55), market=market)
    for n, (buy, sell) in enumerate(((0, 2), (3, 5), (6, 8), (9, 11), (12, 14))):
        kite["orders"] += [_o(f"1{n}1", "BUY", D(10, buy), average_price=80.0),
                           _o(f"1{n}2", "SELL", D(10, sell), average_price=79.0)]
        await pw.watch_tick(D(10, sell, 5), market=market)
        await pw.settle()
        assert len(told) == (0 if n < 3 else 1)                  # the 4th loss in a row, once
    event, text = told[0]
    assert event == "partner_headsup"
    assert text.splitlines() == [
        "🤝 Partner heads-up · 10:11",
        "4 losses in a row since 10:02 · 4 buys today, 3 within 2 min of a loss.",
        "A call may help: on Nov 9 their buying slowed from about 11 an hour to 5 after yours."]
    assert "₹" not in text and "%" not in text                    # no money figures
    assert all(m["kind"] != "watch_headsup" for m in watch)      # nothing to the partner
    pw.reset()                                                    # a restart sends no second one
    await pw.watch_tick(D(10, 15), market=market)
    await pw.settle()
    assert len(told) == 1


@pytest.mark.asyncio
async def test_the_heads_up_on_a_deep_day_and_a_failed_send_is_tried_again(watch, kite, owner):
    told, accept = owner
    accept[0] = False
    await _login()
    market = _market(D(10, 20))
    await pw.watch_tick(D(9, 59, 55), market=market)
    kite["orders"] = [_o("101", "BUY", D(10, 0), average_price=80.0), _o("102", "SELL", D(10, 5), average_price=50.0)]
    await pw.watch_tick(D(10, 5, 5), market=market)
    await pw.settle()
    assert len(told) == 1                                         # tried, not taken
    await pw.watch_tick(D(10, 7), market=market)
    await pw.settle()
    assert len(told) == 1                                         # not before 5 minutes
    accept[0] = True
    await pw.watch_tick(D(10, 10, 10), market=market)
    await pw.settle()
    assert len(told) == 2 and told[1][1].splitlines()[1] == "The day is past −20% of their cash · 1 buy today."
    await pw.watch_tick(D(10, 16), market=market)
    await pw.settle()
    assert len(told) == 2


@pytest.mark.asyncio
async def test_the_evening_note_gets_the_days_habits(tmp_path, monkeypatch, coach):
    db = str(tmp_path / "evening.db")
    await pw.init_partner_watch_db(db)
    rows = [_trip("2026-11-06", "09:20", 1, -300.0), _trip("2026-11-06", "11:00", 25, 900.0)]
    async with aiosqlite.connect(db) as conn:
        cols = list(rows[0])
        await conn.executemany(f"INSERT INTO partner_watch_trips({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                               [tuple(r[c] for c in cols) for r in rows])
        await conn.commit()

    async def monday(current, db_path):
        return date(2026, 11, 9)

    monkeypatch.setattr("market_calendar.next_trading_day", monday)
    lines = await partner_coach.habit_lines(db, "2026-11-06")
    assert lines[0] == "🧭 Habits today: 2 buys (1 before 10:00) · median hold 13 min."
    assert lines[1] == "✅ Best trade: 11:00 NIFTY 22300 PE, +17% in 25 min."
    assert lines[2].startswith("🎯 Tomorrow, one thing: let the stop order sell a losing trade")
    assert len(lines) == 3                                         # no last week stored: no week line
    assert await partner_coach.habit_lines(str(tmp_path / "none.db"), "2026-11-06") == []
