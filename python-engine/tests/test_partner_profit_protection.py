from dataclasses import replace
from datetime import timedelta

import pandas as pd
import pytest

from config import settings
from partner_coach import round_trip_costs
import partner_profit_protection as profit
import partner_watch as pw
from tests.test_partner_broker_sync import kite, partner_app  # noqa: F401
from tests.test_partner_watch import D, _clocked, _fill, _login, _market, _messages, _o, watch  # noqa: F401


@pytest.fixture
def protection(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_SENTINEL_ADVICE_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_WATCH_PROFIT_PROTECTION_ENABLED", True)


def test_market_uses_completed_bars_and_a_current_futures_trade():
    now = D(14, 10, 4)
    bar_starts = [D(13, 55), D(14, 0), D(14, 5), D(14, 10)]
    bars = pd.DataFrame({"high": [101, 102, 104, 200], "low": [98, 99, 102, 70],
                         "close": [100, 101, 103, 80]},
                        index=[x.replace(tzinfo=None) for x in bar_starts])
    quote = _clocked({"ltp": 103.5, "trade_at": now.isoformat()}, now)
    assert pw._profit_direction(bars, quote, now) == "UP"  # ignores the incomplete plunge
    assert pw._profit_direction(bars, quote | {"ltp": 99}, now) == "MIXED"
    assert pw._profit_direction(bars.drop(bars.index[1]), quote, now) == "UNKNOWN"
    assert pw._profit_direction(bars, quote | {"trade_at": (now - timedelta(minutes=1)).isoformat()},
                                now) == "UNKNOWN"
    falling = bars.assign(high=[104, 103, 102, 200], low=[101, 100, 98, 70], close=[103, 102, 99, 180])
    assert pw._profit_direction(falling, quote | {"ltp": 98.5}, now) == "DOWN"
    assert "Protect profit" in profit.trend_note("DOWN", "SENSEX", "CE")
    assert "supporting puts" in profit.trend_note("DOWN", "SENSEX", "PE")
    assert "Continue" not in profit.trend_note("UP", "SENSEX", "CE", advise=False)


def _holding(key, strike, price, qty):
    symbol = f"SENSEX26N05{strike}CE"
    trip = pw.Trip(key, "BFO", symbol, "NRML", D(13, 54), bought=qty, buy_value=qty * price, buy_orders=1)
    return pw.Holding("BFO", symbol, "NRML", qty, qty, qty, "CONFIRMED", trip=trip, average=price)


@pytest.mark.asyncio
async def test_november_five_combined_risk_threatens_the_profit_floor(monkeypatch, protection):
    now = D(13, 54, 45)
    state = pw._State(cash=53587.20, profit_choice_day=now.date().isoformat())
    monkeypatch.setattr(pw, "_state", state)
    first = _holding("1", 80000, 24.90, 200)
    second = _holding("2", 79900, 37.15, 200)
    state.planned = {"1": {"plan": pw.Plan(24.90, 200, stop=15.35)},
                     "2": {"plan": pw.Plan(37.15, 200, stop=22.45)}}
    day = {"net": 45487.86, "best": 45487.86, "at": D(13, 54, 1)}
    monkeypatch.setattr(pw, "day_so_far", lambda trips, cash: day)
    view = pw.View(now.date().isoformat(), now, [], [first.trip, second.trip], [first, second])
    assert pw._profit_floor(day, view.trips) == 40939.07
    assert pw._profit_plan_loss(view.holdings) == pytest.approx(4964.0, abs=1)
    note = await pw._profit_risk_note(view, now, second, direction="DOWN")
    assert "₹40,939" in note and "Reduce size or pause new buys" in note
    assert "SENSEX futures are falling, against calls" in note
    # The check prices the proposed second call in addition to the first holding.
    view.holdings = [first]
    candidate = pw.revised(state.planned["2"]["plan"], entry=37.15, qty=200, exchange="BFO")
    preview = await pw._profit_risk_note(view, now, second, candidate=candidate, direction="UP")
    assert "Reduce size or pause new buys" in preview and "supporting calls" in preview
    assert "Continue" not in preview  # trend support cannot override the chosen profit floor
    assert await pw._profit_risk_note(view, now, first, direction="UP") == ""
    assert "Protect profit" in await pw._profit_risk_note(view, now, first, direction="DOWN")


def test_open_mark_counts_partial_sales_and_requires_full_fresh_depth(monkeypatch):
    now = D(14, 5)
    state = pw._State()
    monkeypatch.setattr(pw, "_state", state)
    h = _holding("1", 79900, 200, 60)
    h.trip.sold, h.trip.sell_value, h.trip.sell_orders = 20, 5000, 1
    h.qty = h.orders_qty = h.broker_qty = 40
    state.quotes[h.tradingsymbol] = _clocked({"bids": [[210, 20], [200, 20]]}, now)
    fees = round_trip_costs(200, 220, 60, "BFO", orders=3)
    assert pw._profit_mark([h], now, 45487.86) == round(45487.86 + 1200 - fees, 2)
    assert pw._profit_mark([h, replace(h, product="MIS")], now, 45487.86) is None
    assert pw._profit_mark([h], now + timedelta(seconds=16), 45487.86) is None
    state.quotes[h.tradingsymbol]["bids"] = [[210, 20]]
    assert pw._profit_mark([h], now, 45487.86) is None


@pytest.mark.asyncio
async def test_floor_preference_is_saved_for_one_session_and_can_return_to_auto(partner_app, watch, kite, protection):
    db = settings.DB_PATH
    at = D(13, 50)
    assert await pw.answer_check(db, "protect 40,000", at, key="check:1") == "profit_protection"
    assert await pw._get_state(db, f"profit_floor:{at.date()}") == "40000"
    assert pw._state.profit_choice == 40000
    pw.reset()
    await pw._load_profit_choice(db, at.date().isoformat())
    assert pw._state.profit_choice == 40000
    assert profit.floor_for(39999, 53587.20, 40000) is None
    await pw._load_profit_choice(db, (at.date() + timedelta(days=1)).isoformat())
    assert pw._state.profit_choice is None
    assert await pw.answer_check(db, "protect auto", at, key="check:2") == "profit_protection"
    assert await pw._get_state(db, f"profit_floor:{at.date()}") == "auto"


@pytest.mark.asyncio
async def test_watch_sends_one_milestone_and_one_early_floor_breach(partner_app, watch, kite, protection):
    await _login()
    market = _market(D(10, 0))
    await pw.watch_tick(D(9, 59, 55), market=market)
    kite["orders"] = [_o("101", "BUY", D(10, 0), average_price=80),
                      _o("102", "SELL", D(10, 5), average_price=180)]
    kite["trades"] = [_fill("101", 65, 80, D(10, 0)), _fill("102", 65, 180, D(10, 5))]
    await pw.watch_tick(D(10, 5, 5), market=market)
    assert any("Booked profit buffer" in m["text"] for m in watch)
    kite["orders"] += [_o("103", "BUY", D(10, 10), average_price=80),
                       _o("104", "SELL", D(10, 15), average_price=70)]
    kite["trades"] += [_fill("103", 65, 80, D(10, 10)), _fill("104", 65, 70, D(10, 15))]
    await pw.watch_tick(D(10, 15, 5), market=market)
    await pw.watch_tick(D(10, 15, 10), market=market)
    assert sum("Profit floor breached" in m["text"] for m in watch) == 1
    rows = [row for row in await _messages(settings.DB_PATH) if row[1] == "DAY"]
    assert sorted(row[0] for row in rows) == ["profit:2026-10-23:floor:0", "profit:2026-10-23:milestone"]


def test_profit_floor_advances_only_at_meaningful_steps():
    assert pw._profit_phase(45487.86, 40524, 40939.07, 53587.20) == "floor:0"
    assert pw._profit_phase(45487.86, 35000, 40939.07, 53587.20) == "floor:1"
    assert pw._profit_phase(45487.86, None, 40939.07, 53587.20) == "milestone"
