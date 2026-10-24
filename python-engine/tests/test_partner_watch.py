"""[O24-PW] The partner's trade watch: messages only, loss first.

Pure parts (fills, holdings, cover, the plan, the texts) and the tick against
a fake Kite book, a fake market and a fake Telegram. [O24c] The Oct 24
audit's counterexamples are reproduced here: the held count after a partly
filled buy and after a partial sale of a carried position, cover by product
and quantity, an unreadable GTT list, a send that never left, a plan stop the
price is already under, a plan replaced after a restart, and a slow plan.
"""
import asyncio
import time
from dataclasses import replace
from datetime import date, datetime, timedelta

import aiosqlite
import pandas as pd
import pytest

import options_math as om
import partner_bot
import partner_broker_sync as zerodha
import partner_watch as pw
from config import settings
from fno_chain import RISK_FREE_RATE, years_to_expiry
from partner_coach import round_trip_costs
from tests.test_partner_broker_sync import T, _order, _trade, _ts, kite, partner_app  # noqa: F401
from tests.test_partner_fill_capture import _seed

DAY = date(2026, 10, 23)
SYMBOL = "NIFTY26OCT22300PE"
FUT = "NIFTY26OCTFUT"


def D(h, m, s=0):
    return T(h, m, s, day=23)


class FakeContract:
    def __init__(self, symbol=SYMBOL, kind="PE", strike=22300.0, token=11, lot=65):
        self.tradingsymbol, self.instrument_type, self.strike, self.token = symbol, kind, strike, token
        self.segment, self.expiry, self.lot_size, self.name = "NFO", date(2026, 10, 27), lot, "NIFTY"

    def front_future(self, today):
        return FakeContract(FUT, "FUT", 0.0, token=22)


def _bars(start: datetime, minutes: int, low: float, high: float, close: float) -> pd.DataFrame:
    index = [start.replace(tzinfo=None) + timedelta(minutes=i) for i in range(minutes)]
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": 1.0}, index=index)


def _futures(now: datetime, *, rising: bool, low_edge: float = 22450.0) -> pd.DataFrame:
    """Five-minute futures bars: every bar 40 points high to low (ATR 40), the
    close drifting up (or down) 1 point a bar; today's 09:15-09:45 low is
    ``low_edge``."""
    rows, index = [], []
    for day_offset in (2, 1, 0):
        start = (now - timedelta(days=day_offset)).replace(hour=9, minute=15, second=0, microsecond=0, tzinfo=None)
        for i in range(75):
            at = start + timedelta(minutes=5 * i)
            if day_offset == 0 and at + timedelta(minutes=5) > now.replace(tzinfo=None):
                break
            n = len(rows)
            close = 22500.0 + (n if rising else -n) * 1.0
            low = low_edge if day_offset == 0 and i < 6 else close - 20
            rows.append({"open": close, "high": close + 20, "low": min(low, close - 20), "close": close, "volume": 1.0})
            index.append(at)
    return pd.DataFrame(rows, index=index)


class FakeMarket(pw.Market):
    def __init__(self, option=None, futures=None, quotes=None, delay=0.0):
        super().__init__()
        self.option, self.futures, self.quotes, self.calls, self.delay = option, futures, quotes or {}, [], delay

    async def quote(self, contracts):
        self.calls.append(("quote", [c.tradingsymbol for c in contracts]))
        return {k: v for k, v in self.quotes.items() if k in {c.tradingsymbol for c in contracts}}

    async def candles(self, contract, interval, start, end):
        self.calls.append((interval, contract.tradingsymbol))
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.option if interval == "minute" else self.futures


# ---------------------------------------------------------------------------
# pure parts
# ---------------------------------------------------------------------------

def _row(order_id, side, qty, price, at, status="COMPLETE", **over):
    row = {"order_id": order_id, "exchange": "NFO", "tradingsymbol": SYMBOL, "transaction_type": side,
           "order_type": "MARKET", "product": "NRML", "quantity": qty, "filled_quantity": qty if status == "COMPLETE" else 0,
           "average_price": price, "trigger_price": 0.0, "status": status, "placed_at": at.isoformat(),
           "updated_at": at.isoformat()}
    row.update(over)
    return row


def _stop_row(order_id, qty, trigger, at, status="TRIGGER PENDING", product="NRML", **over):
    row = _row(order_id, "SELL", qty, 0.0, at, status=status, order_type="SL", trigger_price=trigger, product=product)
    row["price"] = round(trigger - 1, 2)          # the limit (``_row``'s own price is the fill's average)
    row.update(over)
    return row


def _fill(order_id, qty, price, at):
    return _trade(order_id, qty, price, at) | {"trade_id": f"t{order_id}-{at.isoformat()}"}


def _holding(qty, product="NRML", entry=80.0):
    trip = pw.Trip("101", "NFO", SYMBOL, product, D(10, 0), bought=qty, buy_value=qty * entry)
    return pw.Holding("NFO", SYMBOL, product, qty=qty, orders_qty=qty, broker_qty=qty, basis="CONFIRMED", trip=trip,
                      average=entry)


def test_round_trips_open_and_close_in_fill_order():
    rows = [_row("1", "BUY", 65, 75.05, D(11, 29, 17)), _row("2", "SELL", 65, 62.6, D(13, 38, 17)),
            _row("3", "BUY", 65, 80.0, D(13, 40)), _row("4", "BUY", 65, 82.0, D(13, 41)),
            _row("5", "SELL", 65, 90.0, D(13, 50)), _row("6", "BUY", 65, 70.0, D(13, 55), status="REJECTED")]
    first, second = pw.trips_from_orders(rows)
    assert (first.key, first.open_qty, first.closed_at) == ("1", 0, D(13, 38, 17))
    assert first.realised() == round((62.6 - 75.05) * 65 - round_trip_costs(75.05, 62.6, 65, "NFO"), 2)
    assert (second.key, second.bought, second.sold, second.open_qty, round(second.entry, 2)) == ("3", 130, 65, 65, 81.0)
    assert list(second.buys) == ["3", "4"] and second.buy_orders == 2
    assert second.realised() is None                      # still open


def test_a_partly_filled_buy_with_a_sale_between_its_fills_holds_65_not_130():
    """[O24c] Audit A1: buy 130 fills 65 at 10:00, a sale of 65 at 10:05, the other 65 at 10:10. The order book
    stamps the whole 130 at 10:10, after the sale; the trade book has each fill."""
    rows = [_row("101", "BUY", 130, 80.0, D(10, 10)), _row("201", "SELL", 65, 85.0, D(10, 5))]
    trades = [_fill("101", 65, 79.0, D(10, 0)), _fill("201", 65, 85.0, D(10, 5)), _fill("101", 65, 81.0, D(10, 10))]
    assert [t.open_qty for t in pw.trips_from_orders(rows)] == [130]          # the order book alone: wrong
    first, second = pw.trips_from_orders(rows, trades=trades)
    assert (first.key, first.bought, first.sold, first.closed_at) == ("101", 65, 65, D(10, 5))
    assert (second.key, second.open_qty, second.entry, second.exact) == ("101#2", 65, 81.0, True)
    # Zerodha's positions agree with the fills.
    [held] = pw.holdings_of([first, second], [{"exchange": "NFO", "tradingsymbol": SYMBOL, "product": "NRML",
                                               "quantity": 65, "overnight_quantity": 0, "average_price": 81.0}],
                            D(10, 15))
    assert (held.qty, held.basis) == (65, "CONFIRMED")


def test_a_carried_position_sold_in_part_before_the_login_still_holds_the_rest():
    """[O24c] Audit A2: 130 carried in, 65 sold at 09:30, a login at 10:00. The trip starts at the overnight
    130 (not the 65 left), so the sale is not taken off twice."""
    carried = [{"exchange": "NFO", "tradingsymbol": SYMBOL, "product": "NRML", "quantity": 65, "overnight_quantity": 130,
                "average_price": 90.0}]
    [trip] = pw.trips_from_orders([_row("9", "SELL", 65, 80.0, D(9, 30))], carried, DAY)
    assert (trip.carried, trip.first_at, trip.bought, trip.sold, trip.open_qty) == (True, D(9, 15), 130, 65, 65)
    [held] = pw.holdings_of([trip], carried, D(10, 0))
    assert (held.qty, held.basis, held.carried) == (65, "CONFIRMED", True)


def test_a_count_zerodha_does_not_confirm_uses_zerodhas_and_says_so():
    trip = pw.trips_from_orders([_row("101", "BUY", 130, 80.0, D(10, 10))])[0]
    positions = [{"exchange": "NFO", "tradingsymbol": SYMBOL, "product": "NRML", "quantity": 65,
                  "overnight_quantity": 0, "average_price": 80.0}]
    # A fill newer than the positions read keeps the orders' count for now...
    [fresh] = pw.holdings_of([trip], positions, D(10, 10, 5))
    assert (fresh.qty, fresh.basis) == (130, "ORDERS")
    # ...a difference older than a fill can lag uses Zerodha's and says so.
    [stale] = pw.holdings_of([trip], positions, D(10, 11))
    assert (stale.qty, stale.basis, stale.orders_qty) == (65, "ZERODHA", 130)
    assert pw.no_stop_text(stale, None) == (
        "⏰ NIFTY 22300 PE (65): no stop order yet (bought 10:10). Zerodha's positions show 65 held; your orders today "
        "give 130, so the count is Zerodha's.")
    # Without positions the count is the orders', said as such.
    [unread] = pw.holdings_of([trip], None)
    assert pw._count_note(unread) == " The count is from your orders: Zerodha's positions could not be read."
    # Zerodha shows nothing held long after: nothing to watch.
    assert pw.holdings_of([trip], [], D(10, 30)) == []


def test_cover_counts_only_stops_of_the_same_product_and_their_units():
    """[O24c] Audit B: a 65-unit MIS stop does not protect a 130-unit NRML holding."""
    held = _holding(130)
    mis = [_stop_row("201", 65, 70.0, D(10, 1), product="MIS")]
    cover = pw.cover_of(held, mis, [])
    assert (cover.state, cover.covered, [s["units"] for s in cover.other_product]) == ("ABSENT", 0, [65])
    assert pw.cover_of(held, mis, None).state == "UNKNOWN"          # the GTTs could still cover it
    both = mis + [_stop_row("202", 65, 70.0, D(10, 2))]
    cover = pw.cover_of(held, both, [])
    assert (cover.state, cover.covered, cover.held) == ("PARTIAL", 65, 130)
    assert pw.partial_text(held, cover, None) == (
        "⚠️ NIFTY 22300 PE: protection incomplete. A stop covers 65 of your 130; the other 65 have none. Your stop "
        "for 65 is MIS and these are NRML: it would not sell them.")
    # A stop partly filled covers only what it still has to sell; a modify in flight still waits.
    partly = [_stop_row("203", 130, 70.0, D(10, 3), status="MODIFY PENDING", filled_quantity=65)]
    assert pw.cover_of(_holding(65), partly, None).state == "FULL"
    assert pw.cover_of(held, [_stop_row("204", 130, 70.0, D(10, 4))], None).state == "FULL"


def test_a_fired_stop_that_has_not_sold_is_exiting_not_missing():
    held = _holding(65)
    fired = [_stop_row("201", 65, 70.0, D(10, 1), status="OPEN", order_type="LIMIT", price=69.0)]
    cover = pw.cover_of(held, fired, None)
    assert (cover.state, cover.covered, cover.exiting) == ("FULL", 0, 65)
    assert cover.fired == [{"order_id": "201", "trigger": 70.0, "limit": 69.0, "pending": 65, "kind": "SL"}]
    text = pw.unfilled_text(held, cover.fired[0], {"bid": 66.0, "ltp": 66.5})
    at_bid = (66.0 - 80.0) * 65 - round_trip_costs(80.0, 66.0, 65, "NFO")
    assert text == ("🚨 NIFTY 22300 PE: your stop triggered at ₹70, but its sell order (limit ₹69) has not filled: "
                    "65 of 65 still to sell. The bid is ₹66, under your limit: it sells only at ₹69 or better. Selling "
                    f"at the bid ₹66 now: about −{pw._amt(-at_bid)} with charges. To sell now, the limit has to come "
                    "down to the bid.")


def test_gtt_stop_legs_count_with_their_product_and_a_fired_gtt_is_exiting():
    held = _holding(65)
    oco = {"id": 7, "type": "two-leg", "status": "active",
           "condition": {"exchange": "NFO", "tradingsymbol": SYMBOL, "trigger_values": [60.0, 120.0], "last_price": 80.0},
           "orders": [{"transaction_type": "SELL", "quantity": 65, "product": "NRML", "price": 59.0},
                      {"transaction_type": "SELL", "quantity": 65, "product": "NRML", "price": 119.0}]}
    target_only = {"id": 8, "type": "single", "status": "active",
                   "condition": {"exchange": "NFO", "tradingsymbol": SYMBOL, "trigger_values": [120.0], "last_price": 80.0},
                   "orders": [{"transaction_type": "SELL", "quantity": 65, "product": "NRML"}]}
    assert pw.cover_of(held, [], [target_only]).state == "ABSENT"         # a target is not a stop
    cover = pw.cover_of(held, [], [oco])
    assert (cover.state, cover.stops) == ("FULL", [{"id": "gtt:7", "trigger": 60.0, "units": 65, "product": "NRML",
                                                    "kind": "GTT"}])
    fired = oco | {"status": "triggered", "orders": [oco["orders"][0] | {"result": {"order_result": {"order_id": "901"}}},
                                                     oco["orders"][1]]}
    placed = _row("901", "SELL", 65, 0.0, D(10, 30), status="OPEN", order_type="LIMIT") | {"price": 59.0}
    cover = pw.cover_of(held, [placed], [fired])
    assert (cover.state, cover.fired[0]["kind"], cover.fired[0]["trigger"]) == ("FULL", "GTT", 60.0)


def test_the_plan_is_the_systems_futures_stop_priced_into_the_option():
    now = D(11, 29, 30)
    futures = _futures(now, rising=False)
    plan = pw.build_plan(entry=75.05, qty=65, exchange="NFO", opt_type="PE", strike=22300.0, expiry=date(2026, 10, 27),
                         now=now, bought_at=D(11, 29, 17), cash=7536.7, option_bars=None, fut_bars=futures,
                         fut_price=22534.7, option_mid=75.05)
    years = years_to_expiry(date(2026, 10, 27), now)
    iv = om.implied_vol(75.05, 22534.7, 22300.0, years, RISK_FREE_RATE, False)
    # ATR 40 on these bars; a PE is wrong when the future rises: 22534.7 + 1.5 x 40. The opening-range high
    # (22520 + 20) is under the future, on the winning side, so it is not the stop.
    assert round(plan.atr, 6) == 40.0 and plan.range_edge is None and plan.stop_index == 22594.7
    assert plan.stop == pw._floor_tick(om.black76_price(22594.7, 22300.0, years, iv, RISK_FREE_RATE, False))
    assert plan.stop_basis == "INDEX" and plan.target_index == round(22534.7 - 1.8 * 60.0, 1)
    assert plan.loss == round((75.05 - plan.stop) * 65 + round_trip_costs(75.05, plan.stop, 65, "NFO"), 2)
    assert plan.loss_pct == round(plan.loss / 7536.7, 4) and plan.trend == "WITH"    # falling future, a PE


def test_a_stop_inside_the_options_normal_swing_moves_one_swing_under_the_price():
    now = D(9, 22, 50)
    bought = D(9, 22, 36)
    # 30 one-minute bars swinging 15 a bar: every 5-minute window is 15 high to low.
    option = _bars(bought - timedelta(minutes=30), 30, 35.0, 50.0, 42.0)
    futures = _futures(now, rising=False)
    plan = pw.build_plan(entry=42.25, qty=130, exchange="NFO", opt_type="PE", strike=22400.0, expiry=date(2026, 10, 27),
                         now=now, bought_at=bought, cash=7536.7,
                         option_bars=[(ts.to_pydatetime(), *row) for ts, row in
                                      zip(option.index, option[["open", "high", "low", "close"]].values.tolist())],
                         fut_bars=futures, fut_price=22771.0, option_mid=42.25)
    assert plan.swing == 15.0 and plan.stop_basis == "SWING" and plan.stop == 27.25
    assert plan.index_stop_option is not None and 42.25 - plan.index_stop_option < 15.0
    assert plan.run_from == 35.0 and plan.run_pct == round((42.25 - 35.0) / 35.0, 4)
    assert plan.loss_pct > 0.10


def test_a_plan_stop_the_price_is_already_under_is_never_offered_as_a_stop():
    """[O24c] Audit D: bought at ₹100, the option at ₹20 now, no futures read: the swing stop (₹90) is already
    crossed, so the message says so and what selling at the bid gives, and asks for no SL at ₹90."""
    bought = D(10, 0)
    option = _bars(bought - timedelta(minutes=30), 30, 95.0, 105.0, 100.0)
    plan = pw.build_plan(entry=100.0, qty=65, exchange="NFO", opt_type="CE", strike=22700.0, expiry=date(2026, 10, 27),
                         now=D(10, 0, 30), bought_at=bought, cash=20000.0,
                         option_bars=[(ts.to_pydatetime(), *row) for ts, row in
                                      zip(option.index, option[["open", "high", "low", "close"]].values.tolist())],
                         fut_bars=None, fut_price=None, option_mid=20.0)
    assert (plan.stop, plan.stop_basis) == (90.0, "SWING")
    quote = {"bid": 19.9, "ask": 20.1, "ltp": 20.0}
    assert pw.level_state(plan.stop, quote) == "CROSSED" and pw.level_state(plan.stop, None) == "UNCHECKED"
    trip = pw.Trip("1", "NFO", "NIFTY26OCT22700CE", "NRML", bought, bought=65, buy_value=6500.0)
    text = pw.plan_text(trip, plan, lots=1, quote=quote)
    at_bid = (19.9 - 100.0) * 65 - round_trip_costs(100.0, 19.9, 65, "NFO")
    assert text.splitlines()[1] == (f"🛑 The price (₹20) is already under the plan stop ₹90, the level where this trade "
                                    f"is wrong. Selling at the bid ₹19.9 now: about −{pw._amt(-at_bid)} with charges, "
                                    f"{-at_bid / 20000.0:.0%} of your cash.")
    assert "Place an SL sell" not in text
    assert pw.plan_summary(plan, quote) == "the price was already under the plan stop ₹90"
    held = pw.Holding("NFO", "NIFTY26OCT22700CE", "NRML", qty=65, orders_qty=65, broker_qty=65, basis="CONFIRMED",
                      trip=trip, average=100.0)
    assert "is already under the plan stop ₹90" in pw.no_stop_text(held, plan, quote)
    assert "the price could not be read now" in pw.no_stop_text(held, plan, None, set_at=bought)


def test_without_market_data_the_plan_names_only_the_premium_at_risk():
    plan = pw.build_plan(entry=100.0, qty=65, exchange="NFO", opt_type="CE", strike=22700.0, expiry=date(2026, 10, 27),
                         now=D(14, 2, 40), bought_at=D(14, 2, 36), cash=7536.7, option_bars=None, fut_bars=None,
                         fut_price=None, option_mid=None)
    assert (plan.stop, plan.stop_basis, plan.loss) == (None, "PREMIUM", 6500.0)
    text = pw.plan_text(pw.Trip("1", "NFO", "NIFTY26OCT22700CE", "NRML", D(14, 2, 36), bought=65, buy_value=6500.0),
                        plan, lots=1)
    assert "At risk: the whole ₹6,500 you paid, 86% of your cash. Decide your stop and place it now." in text
    assert "usual" not in text                       # no usual size known: no size warning
    assert "Place an SL sell" not in text


def test_the_plan_message_reads_plainly():
    plan = pw.Plan(entry=75.05, qty=65, stop=57.85, stop_basis="INDEX", stop_index=22601.3, swing=11.4, loss=1180.0,
                   cash=7536.7, loss_pct=0.1566, target=115.2, target_index=22414.8, run_pct=0.24, run_from=60.5,
                   trend="WITH")
    trip = pw.Trip("1", "NFO", SYMBOL, "NRML", D(11, 29, 17), bought=65, buy_value=65 * 75.05)
    text = pw.plan_text(trip, plan, lots=1, after_loss={"loss": 925.0, "at": "13:53", "minutes": 0, "bigger": "130 after 65"},
                        day_line="Trade 5 today · ₹290 in charges so far.", usual=0.30,
                        quote={"bid": 75.0, "ask": 75.1, "ltp": 75.05})
    assert text.splitlines() == [
        "🟢 You bought NIFTY 22300 PE · 1 lot (65) at ₹75.05",
        "🛑 Plan stop ₹57.85 (NIFTY future 22,601). If it sells there: about −₹1,180 with charges, 16% of your cash.",
        "⚠️ ₹4,878 in this trade, 65% of your cash: much bigger than your usual 30%.",
        "🎯 Target zone ₹115.2 (NIFTY future 22,415).",
        "• normal 5-min swing ₹11.4; up 24% in the 15 min before you bought (from ₹60.5); the NIFTY future's 5-min "
        "trend is with you.",
        "⚠️ Your last trade closed −₹925 at 13:53, 0 min before this buy. This is 130 after 65.",
        "Trade 5 today · ₹290 in charges so far.",
        "Place an SL sell now: trigger ₹57.85, limit a little under it. In a fast fall an SL order can trigger and "
        "still not fill.",
    ]
    above = pw.plan_text(trip, plan, lots=1, quote={"bid": 116.0, "ask": 116.2, "ltp": 116.1})
    assert "🎯 Already above the target zone ₹115.2 (price ₹116.1)." in above


def test_a_stop_moved_down_is_told_first_then_only_under_the_plan_or_off_the_buy_price():
    trip = pw.Trip("1", "NFO", SYMBOL, "NRML", D(11, 29, 17), bought=65, buy_value=65 * 75.05)
    plan = pw.Plan(entry=75.05, qty=65, stop=57.85, stop_basis="INDEX")
    # Oct 23, NIFTY 22300 PE: 68 -> 65 (first), 65 -> 60 (within the plan), 75 -> 70 (off the buy price),
    # 60 -> 55 (under the plan stop).
    assert pw.lowered_reason(trip, 68.0, 65.0, plan, first=True) == "FIRST"
    assert pw.lowered_reason(trip, 65.0, 60.0, plan, first=False) is None
    assert pw.lowered_reason(trip, 75.0, 70.0, plan, first=False) == "GUARD"      # 75 is within 0.5% of 75.05
    assert pw.lowered_reason(trip, 60.0, 55.0, plan, first=False) == "BELOW_PLAN"
    assert pw.lowered_reason(trip, 65.0, 60.0, None, first=False) is None
    assert pw.lowered_text(trip, 75.0, 70.0, "GUARD", plan).endswith(
        "It was guarding your buy price; now this trade can end in a loss.")
    assert pw.lowered_text(trip, 60.0, 55.0, "BELOW_PLAN", plan).endswith(
        "That is under your plan stop ₹57.85: the loss can now be bigger than planned.")


def test_lowered_and_removed_texts_give_the_result_if_hit():
    trip = pw.Trip("1", "NFO", SYMBOL, "NRML", D(11, 29, 17), bought=65, buy_value=65 * 75.05)
    text = pw.lowered_text(trip, 75.0, 70.0)
    at_75 = (75.0 - 75.05) * 65 - round_trip_costs(75.05, 75.0, 65, "NFO")
    at_70 = (70.0 - 75.05) * 65 - round_trip_costs(75.05, 70.0, 65, "NFO")
    assert text == (f"⚠️ NIFTY 22300 PE: you moved your stop down ₹75 → ₹70. If it is hit: −{pw._amt(at_70)} instead "
                    f"of −{pw._amt(at_75)}. A stop moved down adds to the loss you chose when you placed it.")
    held = _holding(65, entry=75.05)
    assert pw.removed_text(held, {"kind": "CANCELLED", "trigger": 75.0}, None).endswith(
        "Nothing limits this trade's loss now.")
    assert pw.removed_text(held, {"kind": "SOLD", "trigger": 70.0, "sold": 65}, None) == (
        "⚠️ NIFTY 22300 PE: your stop at ₹70 sold 65; the 65 still held have no stop.")


def test_an_add_names_the_new_size_and_the_bigger_loss_at_the_plan_stop():
    held = _holding(130, entry=77.5)
    plan = pw.Plan(entry=77.5, qty=130, stop=60.0, stop_basis="INDEX")
    text = pw.added_text(held, added=65, added_px=75.0, first_px=80.0, plan=plan, loss_before=1300.0,
                         quote={"bid": 74.9, "ask": 75.1, "ltp": 75.0})
    at_stop = (60.0 - 77.5) * 130 - round_trip_costs(77.5, 60.0, 130, "NFO")
    assert text == (f"➕ You added 65 to NIFTY 22300 PE at ₹75, under your first buy at ₹80: now 130 at ₹77.5. If the "
                    f"plan stop ₹60 sells: about −{pw._amt(-at_stop)} with charges (it was −₹1,300). Buying more of a "
                    "falling option makes the loss at the stop bigger.")


def test_close_texts_name_what_the_close_does():
    trip = pw.Trip("1", "NFO", SYMBOL, "NRML", D(14, 2), bought=65, buy_value=65 * 90.0)
    assert pw.close_text(trip, expiry_today=False, theta_day=-17.08).endswith(
        "As NRML it stays open overnight: time decay is about ₹1,110 a day on it.")
    assert "settled in cash at its in-the-money value" in pw.close_text(trip, expiry_today=True, theta_day=None)
    trip.product = "MIS"
    assert "squares it off near the close" in pw.close_text(trip, expiry_today=False, theta_day=None)


def test_a_quote_keeps_its_sizes_and_clocks():
    """[O24c] Audit G: the shadow looks keep the bid/ask quantities and the exchange's and our clocks."""
    raw = {"last_price": 75.05, "timestamp": "2026-10-23 11:30:01", "last_trade_time": "2026-10-23 11:29:58",
           "depth": {"buy": [{"price": 75.0, "quantity": 650, "orders": 3}, {"price": 74.9, "quantity": 65, "orders": 1},
                             {"price": 0, "quantity": 0, "orders": 0}],
                     "sell": [{"price": 75.1, "quantity": 325, "orders": 2}]}}
    top = pw._top(raw, D(11, 30, 2))
    assert top == {"bid": 75.0, "ask": 75.1, "ltp": 75.05, "bid_qty": 650, "ask_qty": 325,
                   "bids": [[75.0, 650], [74.9, 65]], "quote_at": D(11, 30, 1).isoformat(),
                   "trade_at": D(11, 29, 58).isoformat(), "received_at": D(11, 30, 2).isoformat()}
    assert pw._top({"last_price": 0, "depth": {}}, D(11, 30))["bid"] is None


def test_the_plan_never_asks_for_a_second_sl_and_never_widens_a_tighter_one():
    """[O24d] Audit 1: a trade fully covered by an SL at ₹95 was told "Place an SL sell now: trigger ₹80" (a
    second sell order, or a reason to loosen the tighter stop)."""
    held = _holding(65, entry=100.0)
    plan = pw.Plan(entry=100.0, qty=65, stop=80.0, stop_basis="INDEX", stop_index=22601.0, loss=1400.0, cash=20000.0)
    quote = {"bid": 99.9, "ask": 100.1, "ltp": 100.0, "looked_at": D(10, 0, 5)}
    tight = pw.cover_of(held, [_stop_row("201", 65, 95.0, D(10, 0, 1))], [])
    text = pw.plan_text(held, plan, lots=1, cover=tight, quote=quote, now=D(10, 0, 6))
    assert "Place an SL" not in text
    assert text.splitlines()[-1] == ("Your SL at ₹95 already covers all 65. The plan stop ₹80 is lower than yours: no "
                                     "second SL is needed.")
    assert pw.plan_summary(plan, quote, tight, D(10, 0, 6)) == "plan stop ₹80; your SL at ₹95 already covered it"
    # A looser stop: compared with the plan stop. No second SL, and [O24e] no call to tighten it either: a tighter
    # stop is not a better one until it is scored.
    loose = pw.cover_of(held, [_stop_row("202", 65, 70.0, D(10, 0, 1))], [])
    at_70, at_80 = pw._result_at(held, 70.0), pw._result_at(held, 80.0)
    assert pw.stop_advice(held, plan, loose, quote, now=D(10, 0, 6)) == (
        f"Your SL at ₹70 covers all 65, under the plan stop ₹80: if it sells there, about {pw._signed(at_70)} with "
        f"charges, against {pw._signed(at_80)} at the plan stop.")
    # Part covered: an SL for the rest only.
    big = _holding(130, entry=100.0)
    part = pw.cover_of(big, [_stop_row("203", 65, 95.0, D(10, 0, 1))], [])
    assert pw.stop_advice(big, plan, part, quote, now=D(10, 0, 6)) == (
        "Your SL at ₹95 covers 65 of your 130. For the other 65: an SL sell, trigger ₹80, limit a little under it; the "
        "price was ₹100 at 10:00:05.")
    # The GTTs could not be read: a GTT may be there.
    assert pw.stop_advice(held, plan, pw.cover_of(held, [], None), quote, now=D(10, 0, 6)).startswith(
        "Your GTTs could not be read. If you have no stop yet: an SL sell, trigger ₹80")
    # Nothing in place: the instruction, against a fresh price.
    assert pw.stop_advice(held, plan, pw.cover_of(held, [], []), quote, now=D(10, 0, 6)) == (
        "Place an SL sell now: trigger ₹80, limit a little under it; the price was ₹100 at 10:00:05. In a fast fall "
        "an SL order can trigger and still not fill.")


def test_a_level_is_an_instruction_only_against_a_fresh_price():
    """[O24d] Audit 5: with no price read, or an exchange quote an hour old, the plan stop was still "Place an SL
    sell now" (an old quote checked as VALID). Now it is an earlier reference to check first."""
    held = _holding(65, entry=100.0)
    plan = pw.Plan(entry=100.0, qty=65, stop=80.0, stop_basis="INDEX", stop_index=22601.0, loss=1400.0, cash=20000.0)
    absent = pw.cover_of(held, [], [])
    old = {"bid": 99.9, "ltp": 100.0, "quote_at": D(9, 0, 5).isoformat(), "received_at": D(10, 0, 5).isoformat(),
           "looked_at": D(10, 0, 5)}
    current = old | {"quote_at": D(10, 0, 4).isoformat()}
    assert pw.level_state(80.0, None) == "UNCHECKED"
    assert pw.level_state(80.0, old, D(10, 0, 6)) == "STALE"
    assert pw.level_state(80.0, current, D(10, 0, 6)) == "VALID"
    assert pw.level_state(80.0, current, D(10, 0, 21)) == "STALE"         # our own read 16 s old
    blind = pw.plan_text(held, plan, lots=1, cover=absent, quote=None, set_at=D(10, 0, 2))
    assert "Place an SL sell now" not in blind
    assert blind.splitlines()[-1] == (
        "The plan stop ₹80 is from 10:00:02, and the price could not be read now: check the option is still above ₹80 "
        "before placing an SL there (Zerodha refuses an SL sell at or above the price).")
    stale = pw.plan_text(held, plan, lots=1, cover=absent, quote=old, now=D(10, 0, 6), set_at=D(10, 0, 2))
    assert stale.splitlines()[-1].startswith(
        "The plan stop ₹80 is from 10:00:02, and the last price update I have is from 09:00:05: check")
    assert "(set at 10:00; the last price update was 09:00:05)" in pw.no_stop_text(held, plan, old, absent,
                                                                                   D(10, 0, 2), now=D(10, 0, 6))


def test_selling_now_is_priced_against_the_bids_sizes():
    """[O24d] Audit 5: a best bid for 65 is not the price of 130."""
    held = _holding(130, entry=100.0)
    assert pw._sell_now(held, {"bid": 19.9, "ltp": 20.0, "bids": [[19.9, 200]]}) == (
        f" Selling at the bid ₹19.9 now: about {pw._signed(pw._result_at(held, 19.9))} with charges.")
    deep = {"bid": 19.9, "ltp": 20.0, "bids": [[19.9, 65], [19.5, 100]]}
    assert pw._sell_now(held, deep) == (
        f" Selling all 130 now into the bids (₹19.9 down to ₹19.5): about "
        f"{pw._signed(pw._result_at(held, (19.9 * 65 + 19.5 * 65) / 130))} with charges.")
    thin = {"bid": 19.9, "ltp": 20.0, "bids": [[19.9, 65], [19.5, 30]]}
    bound = (19.9 * 65 + 19.5 * 30 + 19.5 * 35) / 130          # the 35 not shown at the lowest bid shown, or under
    assert pw._sell_now(held, thin) == (
        f" The bids shown take only 95 of your 130 (₹19.9 down to ₹19.5); selling all now: about "
        f"{pw._signed(pw._result_at(held, bound))} or worse with charges.")
    # Without sizes (a quote without depth): the bid, as before.
    assert pw._sell_now(held, {"bid": 19.9, "ltp": 20.0}).startswith(" Selling at the bid ₹19.9 now")


def test_a_trades_messages_are_its_own_each_day():
    """[O24d] Audit 3: a warning's key names the trade (its opening buy's order id, or the carried position) and
    the day, not the option and an in-memory counter."""
    first, again = _holding(65), _holding(65)
    again.trip.key = "301"
    assert pw._episode("2026-10-23", first) != pw._episode("2026-10-23", again)
    carried = _holding(65)
    carried.trip.key, carried.trip.carried = "carry:NFO:NIFTY26OCT22300PE:NRML", True
    assert pw._episode("2026-10-23", carried) != pw._episode("2026-10-24", carried)


@pytest.mark.parametrize("state, error, retry", [
    ("unsent_connect", "ConnectError", True), ("rate_limited", "telegram_429", True),
    ("rejected", "telegram_http_502", True), ("rejected", "telegram_http_400", False),
    ("ambiguous_timeout", "ReadTimeout", False), ("ambiguous_transport", "RemoteProtocolError", False),
    ("disabled", "partner_transport_disabled", False), ("attempting", None, False),
])
def test_only_a_send_that_provably_did_not_leave_is_sent_again(state, error, retry):
    assert pw._retryable(state, error) is retry


@pytest.mark.asyncio
async def test_the_quiet_button_is_for_today_only(partner_app):
    db = settings.DB_PATH
    assert await pw.handle_button(db, "c:BOUGHT:x", D(10, 0)) is None
    assert await pw.handle_button(db, "watch:quiet:20261022", D(10, 0)) == "That was for an earlier day."
    assert await pw.handle_button(db, "watch:quiet:20261023", D(10, 0)) == pw.QUIET_TOAST
    assert await pw.quiet(db, "2026-10-23") and not await pw.quiet(db, "2026-10-24")


@pytest.mark.asyncio
async def test_tables_written_by_o24_gain_the_new_columns(tmp_path):
    db = str(tmp_path / "o24.db")
    async with aiosqlite.connect(db) as conn:
        await conn.executescript(
            "CREATE TABLE partner_watch_messages (message_key TEXT PRIMARY KEY, session_date TEXT NOT NULL, kind TEXT "
            "NOT NULL, exchange TEXT, tradingsymbol TEXT, position_key TEXT, created_at TEXT NOT NULL, sent INTEGER NOT "
            "NULL DEFAULT 0, text TEXT NOT NULL, summary TEXT);"
            "CREATE TABLE partner_watch_looks (position_key TEXT NOT NULL, at TEXT NOT NULL, session_date TEXT NOT "
            "NULL, bid REAL, ask REAL, ltp REAL, fut REAL, PRIMARY KEY (position_key, at));")
    await pw.init_partner_watch_db(db)
    async with aiosqlite.connect(db) as conn:
        cols = {r[1] for r in await (await conn.execute("PRAGMA table_info(partner_watch_messages)")).fetchall()}
        looks = {r[1] for r in await (await conn.execute("PRAGMA table_info(partner_watch_looks)")).fetchall()}
    assert {"attempts", "outcome", "error", "event_at", "detected_at", "sent_at", "message_id", "context", "episode",
            "priority"} <= cols
    assert {"bid_qty", "ask_qty", "quote_at", "trade_at", "received_at"} <= looks


# ---------------------------------------------------------------------------
# the tick
# ---------------------------------------------------------------------------

def _net_positions(orders, carried):
    """Zerodha's net positions as the fake book implies them: the overnight
    quantity plus today's fills, per exchange, option and product."""
    net: dict = {}
    for item in carried:
        key = (item["exchange"], item["tradingsymbol"], item["product"])
        net[key] = dict(item)
    for order in orders:
        filled = int(order.get("filled_quantity") or 0)
        if not filled:
            continue
        key = (order["exchange"], order["tradingsymbol"], order["product"])
        row = net.setdefault(key, {"exchange": key[0], "tradingsymbol": key[1], "product": key[2], "quantity": 0,
                                   "overnight_quantity": 0, "average_price": 0.0})
        sign = 1 if order["transaction_type"] == "BUY" else -1
        if sign > 0 and order.get("average_price"):
            held = max(row["quantity"], 0)
            row["average_price"] = (row["average_price"] * held + float(order["average_price"]) * filled) / (held + filled)
        row["quantity"] += sign * filled
    return {"net": list(net.values()), "day": []}


@pytest.fixture
def watch(kite, monkeypatch):
    """Fake Telegram (``outcomes``: the next sends' states), an open trading
    day, the fake option book, and positions that follow the fake orders."""
    sent, outcomes = [], []

    async def send(text, *, kind="partner_msg", reply_markup=None):
        state = outcomes.pop(0) if outcomes else "acknowledged"
        delivered = state == "acknowledged"
        sent.append({"kind": kind, "text": text, "keyboard": reply_markup, "state": state})
        return partner_bot.PartnerSendResult(delivered, message_id=len(sent) if delivered else None, state=state,
                                             error=None if delivered else "ConnectError")

    async def trading_day(now):
        return True

    fake = zerodha._kite_call

    async def book(method, path, **kw):
        if path == "/portfolio/positions" and kite.get("auto_positions", True):
            return _net_positions(kite["orders"], kite.get("carried", []))
        if path == "/gtt/triggers" and kite.get("gtt_fail"):
            raise zerodha.BrokerError("network", "ConnectError")
        return await fake(method, path, **kw)

    monkeypatch.setattr(zerodha, "_kite_call", book)
    monkeypatch.setattr(settings, "PARTNER_WATCH_ENABLED", True)
    monkeypatch.setattr(partner_bot, "partner_enabled", lambda: True)
    monkeypatch.setattr(partner_bot, "send_partner_result", send)
    monkeypatch.setattr(pw, "_is_trading_day", trading_day)
    monkeypatch.setattr(pw, "contract_of", lambda exchange, symbol: FakeContract(symbol))
    pw.reset()
    kite["margins"] = {"available": {"opening_balance": 7536.7, "intraday_payin": 0.0, "live_balance": 7536.7},
                       "utilised": {"option_premium": 0.0}}
    kite["outcomes"] = outcomes
    yield sent
    pw.reset()


def _o(order_id, side, at, **over):
    over = {"order_type": "MARKET", "product": "NRML"} | over
    return _order(order_id, side, over.pop("qty", 65), at, symbol=SYMBOL, exchange="NFO", **over)


def _market(now, **quote):
    option = _bars(now - timedelta(minutes=40), 40, 70.0, 76.0, 75.0)
    return FakeMarket(option=option, futures=_futures(now, rising=False),
                      quotes={SYMBOL: {"bid": 75.0, "ask": 75.1, "ltp": 75.05} | quote,
                              FUT: {"bid": None, "ask": None, "ltp": 22534.7}})


async def _login(at=D(9, 0)):
    await _seed(settings.DB_PATH)
    await zerodha.create_session("reqtok12", at)


async def _messages(db):
    async with aiosqlite.connect(db) as conn:
        rows = await (await conn.execute(
            "SELECT message_key, kind, sent, attempts, outcome, event_at, detected_at, sent_at FROM partner_watch_messages "
            "ORDER BY created_at")).fetchall()
    return rows


@pytest.mark.asyncio
async def test_a_buy_gets_its_plan_then_no_stop_then_a_lowered_and_a_removed_stop(watch, kite):
    db = settings.DB_PATH
    await _login()
    market = _market(D(11, 29, 30))
    assert (await pw.watch_tick(D(11, 29, 0), market=market))["sent"] == 0          # the first read seeds
    kite["orders"] = [_o("101", "BUY", D(11, 29, 17), average_price=75.05)]
    await pw.watch_tick(D(11, 29, 25), market=market)
    plan_msg = watch[-1]
    assert plan_msg["kind"] == "watch_plan" and plan_msg["text"].startswith("🟢 You bought NIFTY 22300 PE · 1 lot (65) at ₹75.05")
    assert "Plan stop ₹" in plan_msg["text"] and plan_msg["keyboard"] == pw.quiet_keyboard("2026-10-23")
    await pw.watch_tick(D(11, 31, 0), market=market)
    assert watch[-1]["kind"] == "watch_plan"                                         # 103 s: not yet
    await pw.watch_tick(D(11, 31, 20), market=market)
    assert watch[-1]["kind"] == "watch_no_stop"
    assert watch[-1]["text"].startswith("⏰ NIFTY 22300 PE (65): no stop order yet (bought 11:29). Plan stop ₹")
    # A stop placed, then lowered: told at once with the result if it is hit.
    kite["orders"].append(_o("201", "SELL", D(11, 32), order_type="SL", status="TRIGGER PENDING", trigger_price=68.0))
    await pw.watch_tick(D(11, 32, 5), market=market)
    count = len(watch)
    kite["orders"][-1] = _o("201", "SELL", D(11, 44, 16), order_type="SL", status="TRIGGER PENDING", trigger_price=65.0)
    await pw.watch_tick(D(11, 44, 20), market=market)
    assert len(watch) == count + 1 and watch[-1]["kind"] == "watch_lowered"
    assert "you moved your stop down ₹68 → ₹65" in watch[-1]["text"]
    await pw.watch_tick(D(11, 44, 25), market=market)
    assert len(watch) == count + 1                                                   # told once
    kite["orders"][-1] = _o("201", "SELL", D(11, 44, 33), order_type="SL", status="TRIGGER PENDING", trigger_price=60.0)
    await pw.watch_tick(D(11, 44, 40), market=market)
    assert len(watch) == count + 1                       # 65 -> 60 stays above the plan stop: the review keeps it
    # Cancelled with nothing in its place: told after the 20 s grace.
    kite["orders"][-1] = _o("201", "SELL", D(12, 0), order_type="SL", status="CANCELLED", trigger_price=60.0)
    await pw.watch_tick(D(12, 0, 5), market=market)
    assert len(watch) == count + 1
    await pw.watch_tick(D(12, 0, 30), market=market)
    assert watch[-1]["kind"] == "watch_removed" and "your stop at ₹60 is cancelled" in watch[-1]["text"]
    # 15:20 with the option still held.
    await pw.watch_tick(D(15, 20, 0), market=market)
    assert watch[-1]["kind"] == "watch_close" and "20 minutes to the 15:40 close" in watch[-1]["text"]
    async with aiosqlite.connect(db) as conn:
        looks = await (await conn.execute("SELECT bid, ask, ltp, fut FROM partner_watch_looks")).fetchall()
    assert len(looks) >= 3 and looks[0] == (75.0, 75.1, 75.05, 22534.7)                # shadow looks recorded
    # Each message keeps when the broker event happened, when it was seen and when Telegram acknowledged it.
    plan_row = next(r for r in await _messages(db) if r[1] == "PLAN")
    assert plan_row[2:5] == (1, 1, "acknowledged") and plan_row[5] == D(11, 29, 17).isoformat()
    # The plan is ready (and queued) a moment after the tick that started it.
    assert pw._dt(plan_row[6]) - D(11, 29, 25) < timedelta(seconds=2) and plan_row[7] is not None


@pytest.mark.asyncio
async def test_a_cancel_and_lower_replacement_is_one_lowered_message(watch, kite):
    await _login()
    market = _market(D(14, 3))
    kite["orders"] = [_o("101", "BUY", D(14, 2, 36), average_price=112.25),
                      _o("201", "SELL", D(14, 3), order_type="SL", status="TRIGGER PENDING", trigger_price=100.0)]
    await pw.watch_tick(D(14, 3, 5), market=market)
    count = len(watch)
    kite["orders"][1] = _o("201", "SELL", D(14, 22), order_type="SL", status="CANCELLED", trigger_price=100.0)
    kite["orders"].append(_o("202", "SELL", D(14, 22, 10), order_type="SL", status="TRIGGER PENDING", trigger_price=90.0))
    await pw.watch_tick(D(14, 22, 5), market=market)
    await pw.watch_tick(D(14, 22, 30), market=market)
    kinds = [m["kind"] for m in watch[count:]]
    assert kinds == ["watch_lowered"] and "₹100 → ₹90" in watch[-1]["text"]


@pytest.mark.asyncio
async def test_a_higher_stop_that_fires_is_not_a_stop_moved_down(watch, kite):
    # Two stops on 130: 65 at ₹80 and 65 at ₹70. The ₹80 one fires and sells; the ₹70 one still waits. Nothing
    # was moved down, so no LOWERED (and the 65 left are covered).
    await _login()
    market = _market(D(10, 0), bid=79.0, ltp=79.5, ask=79.6)
    kite["orders"] = [_o("101", "BUY", D(10, 0), qty=130, average_price=90.0),
                      _o("201", "SELL", D(10, 1), order_type="SL", status="TRIGGER PENDING", trigger_price=80.0),
                      _o("202", "SELL", D(10, 1), order_type="SL", status="TRIGGER PENDING", trigger_price=70.0)]
    await pw.watch_tick(D(10, 2), market=market)
    count = len(watch)
    kite["orders"][1] = _o("201", "SELL", D(10, 5), order_type="LIMIT", status="COMPLETE", trigger_price=80.0,
                           average_price=79.5)
    for at in (D(10, 5, 5), D(10, 5, 30), D(10, 6)):
        await pw.watch_tick(at, market=market)
    assert [m["kind"] for m in watch[count:]] == []


@pytest.mark.asyncio
async def test_a_refusal_is_explained_and_quiet_keeps_only_the_loss_alarms(watch, kite):
    db = settings.DB_PATH
    await _login()
    market = _market(D(13, 54))
    margin = "Insufficient funds. Margin required: 159586.95. Margin available: 7536.70. Check orderbook for open orders."
    kite["orders"] = [_o("101", "BUY", D(13, 53, 41), average_price=105.8),
                      _o("201", "SELL", D(13, 54, 5), order_type="SL", status="TRIGGER PENDING", trigger_price=95.0)]
    await pw.watch_tick(D(13, 54, 10), market=market)
    assert await pw.handle_button(db, "watch:quiet:20261023", D(13, 54, 20)) == pw.QUIET_TOAST
    kite["orders"].append(_o("202", "SELL", D(13, 54, 39), order_type="SL", status="REJECTED", trigger_price=95.0,
                             status_message=margin))
    await pw.watch_tick(D(13, 54, 45), market=market)
    assert watch[-1]["kind"] == "watch_refused"
    assert watch[-1]["text"] == (
        "❗ Zerodha refused your sell order on NIFTY 22300 PE: another sell order for this option was already waiting, "
        "so this one would have sold more than the 65 you held: Zerodha counted it as a new short sale, which needs "
        "₹159,587 of margin; your account had ₹7,537. The trade (65) is still open.")
    # Quiet: a new buy's plan and the 15:20 note are muted; a lowered stop still goes.
    kite["orders"][1] = _o("201", "SELL", D(13, 55, 54), order_type="SL", status="TRIGGER PENDING", trigger_price=90.0)
    await pw.watch_tick(D(13, 56), market=market)
    assert watch[-1]["kind"] == "watch_lowered"
    count = len(watch)
    await pw.watch_tick(D(15, 20, 0), market=market)
    assert len(watch) == count


@pytest.mark.asyncio
async def test_after_a_restart_old_events_are_not_told_again_and_old_buys_get_no_plan_message(watch, kite):
    db = settings.DB_PATH
    await _login()
    kite["orders"] = [_o("101", "BUY", D(10, 0), average_price=98.75),
                      _o("201", "SELL", D(10, 1), order_type="SL", status="TRIGGER PENDING", trigger_price=85.0),
                      _o("301", "BUY", D(10, 30), status="REJECTED", status_message="Margin required: 8118.50. "
                         "Margin available: 7536.70.")]
    await pw.watch_tick(D(11, 0), market=_market(D(11, 0)))
    assert watch == []                                     # a 60-minute-old buy and an old refusal: nothing told
    assert [(v["version"], v["reason"]) for v in await pw.plan_versions(db, "101")] == [(1, "BUY")]


@pytest.mark.asyncio
async def test_a_restart_keeps_the_plan_that_was_sent_and_an_add_is_a_new_version(watch, kite):
    """[O24c] Audit E: after a restart the stored plan stays (a recomputation without market data used to
    replace an ₹80-ish stop with "no stop"); a new buy order adds version 2 and an ADDED message."""
    db = settings.DB_PATH
    await _login()
    await pw.watch_tick(D(11, 29, 0), market=_market(D(11, 29, 30)))
    kite["orders"] = [_o("101", "BUY", D(11, 29, 17), average_price=75.05)]
    await pw.watch_tick(D(11, 29, 25), market=_market(D(11, 29, 30)))
    [first] = await pw.plan_versions(db, "101")
    assert first["plan"].stop is not None
    pw.reset()                                             # the restart: memory gone, the login kept
    blind = FakeMarket()                                   # and no market data now
    await pw.watch_tick(D(11, 30, 0), market=blind)
    assert [v["plan"] for v in await pw.plan_versions(db, "101")] == [first["plan"]]
    assert ("minute", SYMBOL) not in blind.calls           # nothing recomputed
    kite["orders"].append(_o("102", "BUY", D(11, 31, 0), average_price=70.0))
    await pw.watch_tick(D(11, 31, 5), market=_market(D(11, 31, 5), ltp=70.1, bid=70.0, ask=70.2))
    versions = await pw.plan_versions(db, "101")
    assert [(v["version"], v["reason"], v["qty"]) for v in versions] == [(1, "BUY", 65), (2, "ADDED", 130)]
    assert versions[0]["plan"] == first["plan"] and versions[1]["plan"].stop == first["plan"].stop
    assert watch[-1]["kind"] == "watch_added"
    assert watch[-1]["text"].startswith(f"➕ You added 65 to NIFTY 22300 PE at ₹70, under your first buy at ₹75.05: now "
                                        f"130 at {pw._px((75.05 + 70.0) / 2)}. If the plan stop ")


@pytest.mark.asyncio
async def test_a_stop_of_another_product_or_for_part_is_named(watch, kite):
    """[O24c] Audit B: an MIS stop for 65 on 130 NRML is not protection."""
    await _login()
    market = _market(D(10, 0))
    kite["orders"] = [_o("101", "BUY", D(10, 0), qty=130, average_price=75.05),
                      _o("201", "SELL", D(10, 0, 30), order_type="SL", status="TRIGGER PENDING", trigger_price=65.0,
                         product="MIS")]
    for at in (D(10, 0, 5), D(10, 1, 0), D(10, 2, 5)):
        await pw.watch_tick(at, market=market)
    assert watch[-1]["kind"] == "watch_no_stop"
    assert "Your stop for 65 is MIS and these are NRML: it would not sell them." in watch[-1]["text"]
    kite["orders"].append(_o("202", "SELL", D(10, 3), order_type="SL", status="TRIGGER PENDING", trigger_price=65.0))
    for at in (D(10, 3, 5), D(10, 3, 30)):
        await pw.watch_tick(at, market=market)
    assert watch[-1]["kind"] == "watch_partial"
    assert watch[-1]["text"].startswith("⚠️ NIFTY 22300 PE: protection incomplete. A stop covers 65 of your 130; the "
                                        "other 65 have none.")


@pytest.mark.asyncio
async def test_an_unreadable_gtt_list_claims_nothing_and_is_read_again(watch, kite):
    """[O24c] Audit B: a failed GTT read used to end the no-stop check for the trade."""
    await _login()
    market = _market(D(11, 0))
    kite["orders"] = [_o("101", "BUY", D(11, 0), average_price=75.05)]
    kite["gtt_fail"] = True
    for at in (D(11, 0, 5), D(11, 2, 5), D(11, 2, 30)):
        await pw.watch_tick(at, market=market)
    assert [m["kind"] for m in watch] == ["watch_plan"]                 # unknown: nothing said
    kite["gtt_fail"] = False
    await pw.watch_tick(D(11, 2, 35), market=market)
    await pw.watch_tick(D(11, 3, 0), market=market)
    assert watch[-1]["kind"] == "watch_no_stop"


@pytest.mark.asyncio
async def test_a_gtt_stop_counts_and_a_gtt_that_goes_away_is_told(watch, kite):
    await _login()
    market = _market(D(11, 0))
    kite["orders"] = [_o("101", "BUY", D(11, 0), average_price=75.05)]
    kite["gtts"] = [{"id": 5, "type": "single", "status": "active", "created_at": _ts(D(11, 0, 30)),
                     "updated_at": _ts(D(11, 0, 30)),
                     "condition": {"exchange": "NFO", "tradingsymbol": SYMBOL, "trigger_values": [60.0], "last_price": 75.0},
                     "orders": [{"transaction_type": "SELL", "quantity": 65, "order_type": "LIMIT", "price": 60.0}]}]
    await pw.watch_tick(D(11, 0, 10), market=market)
    await pw.watch_tick(D(11, 3), market=market)
    assert [m["kind"] for m in watch] == ["watch_plan"]
    kite["gtts"] = []                                      # deleted at Zerodha
    for at in (D(11, 4), D(11, 4, 25)):
        await pw.watch_tick(at, market=market)
    assert watch[-1]["kind"] == "watch_removed"
    assert watch[-1]["text"].startswith("⚠️ NIFTY 22300 PE: your GTT at ₹60 is no longer active")


@pytest.mark.asyncio
async def test_a_stop_that_fired_and_did_not_sell_is_an_alarm_even_when_quiet(watch, kite):
    db = settings.DB_PATH
    await _login()
    market = _market(D(12, 0), bid=66.0, ltp=66.5, ask=66.6)
    kite["orders"] = [_o("101", "BUY", D(11, 50), average_price=80.0),
                      _o("201", "SELL", D(11, 51), order_type="SL", status="TRIGGER PENDING", trigger_price=70.0,
                         price=69.0)]
    await pw.watch_tick(D(11, 59, 55), market=market)
    await pw.handle_button(db, "watch:quiet:20261023", D(11, 59, 56))
    kite["orders"][1] = _o("201", "SELL", D(12, 0), order_type="LIMIT", status="OPEN", trigger_price=70.0, price=69.0)
    await pw.watch_tick(D(12, 0, 2), market=market)
    count = len(watch)
    await pw.watch_tick(D(12, 0, 7), market=market)
    assert len(watch) == count                             # 5 s: it may still fill
    await pw.watch_tick(D(12, 0, 15), market=market)
    assert watch[-1]["kind"] == "watch_unfilled"
    assert watch[-1]["text"].startswith("🚨 NIFTY 22300 PE: your stop triggered at ₹70, but its sell order (limit ₹69) "
                                        "has not filled: 65 of 65 still to sell. The bid is ₹66, under your limit")
    assert not any(m["kind"] in ("watch_no_stop", "watch_removed") for m in watch)


@pytest.mark.asyncio
async def test_a_send_that_never_left_is_sent_again_and_a_timeout_is_not(watch, kite):
    """[O24c] Audit C: the message key was claimed before the send, so a confirmed connection failure was never
    sent again."""
    db = settings.DB_PATH
    await _login()
    market = _market(D(11, 0))
    kite["orders"] = [_o("101", "BUY", D(11, 0), average_price=75.05)]
    await pw.watch_tick(D(11, 0, 5), market=market)                          # the plan
    kite["outcomes"].append("unsent_connect")
    await pw.watch_tick(D(11, 2, 5), market=market)
    assert watch[-1] == watch[-1] | {"kind": "watch_no_stop", "state": "unsent_connect"}
    count = len(watch)
    await pw.watch_tick(D(11, 2, 10), market=market)
    assert len(watch) == count                                               # 10 s apart at least
    await pw.watch_tick(D(11, 2, 16), market=market)
    assert watch[-1] == watch[-1] | {"kind": "watch_no_stop", "state": "acknowledged"}
    row = next(r for r in await _messages(db) if r[1] == "NO_STOP")
    assert row[2:5] == (1, 2, "acknowledged")
    # A refusal whose send timed out may have arrived: it is not sent again.
    kite["outcomes"].append("ambiguous_timeout")
    kite["orders"].append(_o("301", "BUY", D(11, 3), status="REJECTED", status_message="Margin required: 8118.50. "
                             "Margin available: 7536.70."))
    await pw.watch_tick(D(11, 3, 5), market=market)
    count = len(watch)
    for at in (D(11, 3, 20), D(11, 3, 40)):
        await pw.watch_tick(at, market=market)
    assert len(watch) == count and watch[-1]["state"] == "ambiguous_timeout"
    # A refusal that provably did not leave is sent again from the tick.
    kite["outcomes"].append("unsent_connect")
    kite["orders"].append(_o("302", "BUY", D(11, 4), status="REJECTED", status_message="Margin required: 8118.50. "
                             "Margin available: 7536.70."))
    await pw.watch_tick(D(11, 4, 5), market=market)
    await pw.watch_tick(D(11, 4, 20), market=market)
    assert [m["state"] for m in watch if m["kind"] == "watch_refused"][-2:] == ["unsent_connect", "acknowledged"]


@pytest.mark.asyncio
async def test_a_slow_plan_does_not_hold_up_the_tick(watch, kite, monkeypatch):
    """[O24c] Audit G: the plan's candles ran inside the tick. Now the tick goes on after PLAN_INLINE_SEC, the
    refusal in the same tick is told at once, and the plan follows."""
    monkeypatch.setattr(pw, "PLAN_INLINE_SEC", 0.05)
    await _login()
    slow = _market(D(11, 0))
    slow.delay = 1.0
    await pw.watch_tick(D(11, 0, 0), market=slow)
    kite["orders"] = [_o("101", "BUY", D(11, 0, 2), average_price=75.05),
                      _o("301", "BUY", D(11, 0, 3), status="REJECTED", status_message="Margin required: 8118.50. "
                         "Margin available: 7536.70.")]
    started = time.monotonic()
    await pw.watch_tick(D(11, 0, 5), market=slow)
    assert time.monotonic() - started < 0.8
    assert [m["kind"] for m in watch] == ["watch_refused"]
    await pw.settle()
    assert [m["kind"] for m in watch] == ["watch_refused", "watch_plan"]
    # A plan that cannot be read in time says only the premium at risk.
    monkeypatch.setattr(pw, "PLAN_DEADLINE_SEC", 0.05)
    kite["orders"].append(_o("102", "BUY", D(11, 1), average_price=70.0, tradingsymbol="NIFTY26OCT22400PE"))
    await pw.watch_tick(D(11, 1, 5), market=slow)
    await pw.settle()
    assert watch[-1]["kind"] == "watch_plan" and "At risk: the whole ₹4,550 you paid" in watch[-1]["text"]


@pytest.mark.asyncio
async def test_a_plan_that_failed_is_started_again(watch, kite, monkeypatch):
    await _login()
    calls = []
    real = pw._store_plan

    async def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise aiosqlite.OperationalError("database is locked")
        return await real(*args, **kwargs)

    monkeypatch.setattr(pw, "_store_plan", flaky)
    market = _market(D(11, 0))
    await pw.watch_tick(D(11, 0, 0), market=market)
    kite["orders"] = [_o("101", "BUY", D(11, 0, 2), average_price=75.05)]
    await pw.watch_tick(D(11, 0, 5), market=market)
    assert watch == []                                     # the first plan failed
    await pw.watch_tick(D(11, 0, 10), market=market)
    assert [m["kind"] for m in watch] == ["watch_plan"] and len(calls) == 2


@pytest.mark.asyncio
async def test_login_says_the_watch_is_on_and_a_lost_login_asks_to_reconnect(watch, kite):
    await _login(D(9, 5))
    await pw.on_login(D(9, 5))
    assert watch[-1]["kind"] == "watch_watch_on" and watch[-1]["text"].startswith("✅ Trade watch on until 15:40.")
    zerodha.disconnect()                                   # a restart loses the login
    await pw.watch_tick(D(10, 0), market=_market(D(10, 0)))
    await pw.watch_tick(D(10, 0, 5), market=_market(D(10, 0)))
    reconnects = [m for m in watch if m["kind"] == "watch_reconnect"]
    assert len(reconnects) == 1 and reconnects[0]["keyboard"]["inline_keyboard"][0][0]["text"] == "🔐 Reconnect the watch"


@pytest.mark.asyncio
async def test_the_morning_prompt_goes_once_and_not_when_a_login_is_held(watch, kite, monkeypatch):
    await _seed(settings.DB_PATH)
    monkeypatch.setattr(pw, "RETRY_GAP", timedelta(0))
    kite["outcomes"].append("unsent_connect")              # the first try never left: tried again
    assert (await pw.watch_prompt(D(9, 0)))["sent"] is True
    assert [m["state"] for m in watch] == ["unsent_connect", "acknowledged"]
    assert watch[-1]["text"] == pw.PROMPT_TEXT and watch[-1]["keyboard"]["inline_keyboard"][0][0]["text"] == \
        "🔐 Start today's watch"
    assert (await pw.watch_prompt(D(9, 0, 30)))["sent"] is False
    await zerodha.create_session("reqtok12", D(9, 1))
    assert (await pw.watch_prompt(D(9, 2)))["reason"] == "connected"


@pytest.mark.asyncio
async def test_the_review_shows_what_the_assistant_said(watch, kite):
    import partner_coach as pc
    import partner_lessons as lessons
    db = settings.DB_PATH
    await _login()
    market = _market(D(11, 29, 30))
    kite["orders"] = []
    await pw.watch_tick(D(11, 29, 0), market=market)
    kite["orders"] = [_o("101", "BUY", D(11, 29, 17), average_price=75.05)]
    await pw.watch_tick(D(11, 29, 25), market=_market(D(11, 29, 25)))
    kite["orders"].append(_o("102", "SELL", D(11, 50), average_price=70.0))
    kite["trades"] = []
    await zerodha.sync_book(D(15, 45))
    view = await pc.load_partner_coach(db, days=3, now=D(16, 0))
    review = lessons.day_review(view, "2026-10-23")
    assistant = [e for e in review["trades"][0]["timeline"] if e["who"] == "assistant"]
    assert assistant and assistant[0]["at"] == "11:29" and assistant[0]["text"].startswith("Assistant: plan stop ₹")


@pytest.mark.asyncio
async def test_the_inbox_sends_the_quiet_button_to_the_watch(watch, monkeypatch):
    import partner_fill_capture as pfc
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_CHAT_ID", "777")
    answered = []

    async def answer(callback_id, text):
        answered.append((callback_id, text))

    monkeypatch.setattr(pfc, "_answer", answer)
    await pfc.init_partner_fill_db(settings.DB_PATH)
    update = {"update_id": 5, "callback_query": {"id": "q1", "data": "watch:quiet:20261023",
                                                 "message": {"chat": {"id": 777}}}}
    assert await pfc.handle_update(settings.DB_PATH, update, D(10, 0)) == "watch_button"
    assert answered == [("q1", pw.QUIET_TOAST)] and await pw.quiet(settings.DB_PATH, "2026-10-23")
    other = {"update_id": 6, "callback_query": {"id": "q2", "data": "watch:quiet:20261023",
                                                "message": {"chat": {"id": 999}}}}
    assert await pfc.handle_update(settings.DB_PATH, other, D(10, 0)) == "foreign_chat"


@pytest.mark.asyncio
async def test_the_plan_warns_only_when_a_buy_is_much_bigger_than_the_partners_usual(watch, kite):
    """[O24-SZ] No fixed share of cash: the partner's earlier trades, as the review counts them
    (partner_coach.size_history), set the usual (1.5 x their median share)."""
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.init_partner_broker_db(db)
    async with aiosqlite.connect(db) as conn:
        for i, day in enumerate(("2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22")):
            await conn.execute(
                "INSERT INTO partner_trade_reports(dedup_key,source,received_at,trade_at,trade_at_basis,action,"
                "session_date,tradingsymbol,exchange,lots,lot_size,price,price_basis) "
                "VALUES(?, 'ZERODHA', ?, ?, 'EXCHANGE_FILL', 'BUY', ?, ?, 'NFO', 1, 65, 30.0, 'BROKER_FILL')",
                (f"kite:9{i}", f"{day}T16:00:00+05:30", f"{day}T10:0{i}:00+05:30", day, SYMBOL))
            await conn.execute("INSERT OR REPLACE INTO partner_account_days(session_date,opening_balance,intraday_payin,"
                               "read_at) VALUES(?,?,0,?)", (day, 7536.7, f"{day}T16:00:00+05:30"))
        await conn.commit()
    await zerodha.create_session("reqtok12", D(9, 0))
    await pw.watch_tick(D(11, 29, 0), market=_market(D(11, 29, 30)))
    kite["orders"] = [_o("101", "BUY", D(11, 29, 17), average_price=75.05)]
    await pw.watch_tick(D(11, 29, 25), market=_market(D(11, 29, 30)))
    # Usual: 30 x 65 = ₹1,950 of ₹7,537 = 26%; this buy ₹4,878 = 65% > 1.5 x 26%.
    assert "⚠️ ₹4,878 in this trade, 65% of your cash: much bigger than your usual 26%." in watch[-1]["text"]


# ---------------------------------------------------------------------------
# [O24d] the Oct 24 follow-up audit: advice that stays with the partner's position
# ---------------------------------------------------------------------------

MARGIN = "Insufficient funds. Margin required: 159586.95. Margin available: 7536.70. Check orderbook for open orders."


@pytest.mark.asyncio
async def test_a_trade_already_protected_is_not_asked_for_another_sl(watch, kite):
    """[O24d] Audit 1 in the tick: the stop placed with the buy is read before the plan goes out."""
    await _login()
    market = _market(D(11, 29, 30))
    await pw.watch_tick(D(11, 29, 0), market=market)
    kite["orders"] = [_o("101", "BUY", D(11, 29, 17), average_price=75.05),
                      _o("201", "SELL", D(11, 29, 20), order_type="SL", status="TRIGGER PENDING", trigger_price=74.0,
                         price=73.0)]
    await pw.watch_tick(D(11, 29, 25), market=market)
    [plan] = [m for m in watch if m["kind"] == "watch_plan"]
    assert "Place an SL" not in plan["text"]
    assert plan["text"].splitlines()[-1].startswith("Your SL at ₹74 already covers all 65. The plan stop ₹")


@pytest.mark.asyncio
async def test_a_plan_ready_after_the_trade_closed_is_not_sent(watch, kite, monkeypatch):
    """[O24d] Audit 2: the plan was computed beside the tick and then sent although the partner had sold
    meanwhile. It is built when it can go, from the book read then."""
    db = settings.DB_PATH
    monkeypatch.setattr(pw, "PLAN_INLINE_SEC", 0.05)
    await _login()
    slow = _market(D(11, 0))
    slow.delay = 0.5
    await pw.watch_tick(D(11, 0, 0), market=slow)
    kite["orders"] = [_o("101", "BUY", D(11, 0, 2), average_price=75.05)]
    await pw.watch_tick(D(11, 0, 5), market=slow)              # the plan starts, slowly
    kite["orders"].append(_o("102", "SELL", D(11, 0, 6), average_price=76.0))
    await pw.watch_tick(D(11, 0, 8), market=slow)              # sold before it was ready
    await pw.settle()
    assert watch == []
    assert [(r[1], r[4]) for r in await _messages(db)] == [("PLAN", "superseded")]
    assert [v["reason"] for v in await pw.plan_versions(db, "101")] == ["BUY"]      # kept for the review


@pytest.mark.asyncio
async def test_a_plan_ready_after_a_partial_sale_is_for_what_is_still_held(watch, kite, monkeypatch):
    """[O24d] The partner sold half before the plan was ready: it says so, and its risk is the half held."""
    db = settings.DB_PATH
    monkeypatch.setattr(pw, "PLAN_INLINE_SEC", 0.05)
    await _login()
    slow = _market(D(11, 0))
    slow.delay = 0.5
    await pw.watch_tick(D(11, 0, 0), market=slow)
    kite["orders"] = [_o("101", "BUY", D(11, 0, 2), qty=130, average_price=75.05)]
    await pw.watch_tick(D(11, 0, 5), market=slow)
    kite["orders"].append(_o("102", "SELL", D(11, 0, 6), average_price=80.0))
    await pw.watch_tick(D(11, 0, 8), market=slow)
    await pw.settle()
    [plan] = [m["text"].splitlines() for m in watch if m["kind"] == "watch_plan"]
    sold = round((80.0 - 75.05) * 65 - round_trip_costs(75.05, 80.0, 65, "NFO"), 2)
    assert plan[0] == "🟢 You bought NIFTY 22300 PE · 2 lots (130) at ₹75.05"
    assert plan[1] == (f"• 65 still held: you sold 65 at ₹80, {pw._signed(sold)} with charges. The lines below are "
                       "for the 65 held.")
    stop = (await pw.plan_versions(db, "101"))[0]["plan"].stop
    loss = round((75.05 - stop) * 65 + round_trip_costs(75.05, stop, 65, "NFO"), 2)
    assert f"about −{pw._amt(loss)} with charges" in plan[2]


@pytest.mark.asyncio
async def test_a_second_trade_in_the_same_option_is_warned_too(watch, kite):
    """[O24d] Audit 3: the removal warning's key was the option and an in-memory counter, so a later trade in
    the same option, once the first had closed, lost its warning."""
    await _login()
    market = _market(D(10, 0))
    await pw.watch_tick(D(10, 0, 0), market=market)
    kite["orders"] = [_o("101", "BUY", D(10, 0, 2), average_price=75.05),
                      _o("201", "SELL", D(10, 0, 30), order_type="SL", status="TRIGGER PENDING", trigger_price=65.0)]
    await pw.watch_tick(D(10, 0, 35), market=market)
    kite["orders"][1] = _o("201", "SELL", D(10, 5), order_type="SL", status="CANCELLED", trigger_price=65.0)
    for at in (D(10, 5, 5), D(10, 5, 30)):
        await pw.watch_tick(at, market=market)
    kite["orders"].append(_o("102", "SELL", D(10, 6), average_price=74.0))          # the first trade closed
    await pw.watch_tick(D(10, 6, 5), market=market)
    kite["orders"] += [_o("103", "BUY", D(10, 10), average_price=72.0),
                       _o("202", "SELL", D(10, 10, 30), order_type="SL", status="TRIGGER PENDING", trigger_price=62.0)]
    await pw.watch_tick(D(10, 10, 35), market=market)
    kite["orders"][-1] = _o("202", "SELL", D(10, 15), order_type="SL", status="CANCELLED", trigger_price=62.0)
    for at in (D(10, 15, 5), D(10, 15, 30)):
        await pw.watch_tick(at, market=market)
    removed = [m["text"] for m in watch if m["kind"] == "watch_removed"]
    assert len(removed) == 2 and "your stop at ₹65 is cancelled" in removed[0]
    assert "your stop at ₹62 is cancelled" in removed[1]


@pytest.mark.asyncio
async def test_a_position_carried_over_two_days_is_warned_each_day(watch, kite):
    """[O24d] Audit 3 across days: a carried position's warning key was the same on each day."""
    kite["carried"] = [{"exchange": "NFO", "tradingsymbol": SYMBOL, "product": "NRML", "quantity": 65,
                        "overnight_quantity": 65, "average_price": 80.0}]

    def next_day(h, m, s=0):
        return T(h, m, s, day=24)

    for when, stop_id, trigger in ((D, "201", 65.0), (next_day, "301", 60.0)):
        if when is D:
            await _login()
        else:
            await zerodha.create_session("reqtok12", next_day(9, 0))
        market = _market(when(10, 0))
        kite["orders"] = [_o(stop_id, "SELL", when(9, 50), order_type="SL", status="TRIGGER PENDING",
                             trigger_price=trigger)]
        await pw.watch_tick(when(10, 0, 0), market=market)
        kite["orders"][0] = _o(stop_id, "SELL", when(10, 1), order_type="SL", status="CANCELLED", trigger_price=trigger)
        for at in (when(10, 1, 5), when(10, 1, 30)):
            await pw.watch_tick(at, market=market)
    removed = [m["text"] for m in watch if m["kind"] == "watch_removed"]
    assert len(removed) == 2 and "₹65 is cancelled" in removed[0] and "₹60 is cancelled" in removed[1]


@pytest.mark.asyncio
async def test_zerodhas_count_is_the_plans_count(watch, kite):
    """[O24d] Audit 4: Zerodha's positions showed 65 and the orders 130. The protection messages used 65, but the
    plan and its loss used 130. One reconciled count for every message; what was bought is said apart."""
    db = settings.DB_PATH
    await _login()
    kite["auto_positions"] = False
    market = _market(D(11, 30))
    await pw.watch_tick(D(11, 29, 0), market=market)
    kite["positions"] = {"net": [{"exchange": "NFO", "tradingsymbol": SYMBOL, "product": "NRML", "quantity": 65,
                                  "overnight_quantity": 0, "average_price": 75.05}], "day": []}
    kite["orders"] = [_o("101", "BUY", D(11, 29, 2), qty=130, average_price=75.05)]
    await pw.watch_tick(D(11, 29, 25), market=market)
    [plan] = [m["text"].splitlines() for m in watch if m["kind"] == "watch_plan"]
    assert plan[0] == "🟢 You bought NIFTY 22300 PE · 2 lots (130) at ₹75.05"
    assert plan[1] == ("• Zerodha's positions show 65 held; your orders today give 130, so the count is Zerodha's. "
                       "The lines below are for the 65 held.")
    [first] = await pw.plan_versions(db, "101")
    assert (first["qty"], first["bought"]) == (65, 130)
    stop = first["plan"].stop
    loss = round((75.05 - stop) * 65 + round_trip_costs(75.05, stop, 65, "NFO"), 2)
    assert f"about −{pw._amt(loss)} with charges" in plan[2]


@pytest.mark.asyncio
async def test_a_plan_without_a_price_is_a_reference_not_an_instruction(watch, kite):
    """[O24d] Audit 5 in the tick: no quote for the option when the plan goes out."""
    await _login()
    market = _market(D(11, 29, 30))
    market.quotes.pop(SYMBOL)
    await pw.watch_tick(D(11, 29, 0), market=market)
    kite["orders"] = [_o("101", "BUY", D(11, 29, 17), average_price=75.05)]
    await pw.watch_tick(D(11, 29, 25), market=market)
    [plan] = [m["text"] for m in watch if m["kind"] == "watch_plan"]
    assert "Place an SL sell now" not in plan
    assert "and the price could not be read now: check the option is still above ₹" in plan.splitlines()[-1]


@pytest.mark.asyncio
async def test_a_message_that_never_left_is_sent_after_a_restart_rebuilt(watch, kite):
    """[O24d] Audit 6: a refusal's send failed to connect; its retry lived only in memory and a restart lost it.
    The outbox is in the database: the next tick sends it, rebuilt from the book read then."""
    await _login()
    market = _market(D(13, 54))
    kite["orders"] = [_o("101", "BUY", D(13, 53, 41), qty=130, average_price=105.8),
                      _o("201", "SELL", D(13, 54, 5), order_type="SL", status="TRIGGER PENDING", trigger_price=95.0,
                         qty=130)]
    await pw.watch_tick(D(13, 54, 10), market=market)
    kite["outcomes"].append("unsent_connect")
    kite["orders"].append(_o("202", "SELL", D(13, 54, 39), order_type="SL", status="REJECTED", trigger_price=95.0,
                             status_message=MARGIN))
    await pw.watch_tick(D(13, 54, 45), market=market)
    assert watch[-1] == watch[-1] | {"kind": "watch_refused", "state": "unsent_connect"}
    assert watch[-1]["text"].endswith("The trade (130) is still open.")
    pw.reset()                                             # the restart: memory gone, the login kept
    kite["orders"].append(_o("102", "SELL", D(13, 54, 50), qty=65, average_price=100.0))     # meanwhile: half sold
    await pw.watch_tick(D(13, 55, 0), market=market)
    refused = [m for m in watch if m["kind"] == "watch_refused"]
    assert [m["state"] for m in refused] == ["unsent_connect", "acknowledged"]
    assert refused[-1]["text"].endswith("The trade (65) is still open.")


@pytest.mark.asyncio
async def test_a_warning_no_longer_true_when_it_can_go_is_dropped(watch, kite):
    """[O24d] A no-stop warning that never left, then a stop placed before its retry: it is not sent."""
    db = settings.DB_PATH
    await _login()
    market = _market(D(11, 0))
    kite["orders"] = [_o("101", "BUY", D(11, 0), average_price=75.05)]
    await pw.watch_tick(D(11, 0, 5), market=market)                         # the plan
    kite["outcomes"].append("unsent_connect")
    await pw.watch_tick(D(11, 2, 5), market=market)                         # NO_STOP: it never left
    kite["orders"].append(_o("201", "SELL", D(11, 2, 8), order_type="SL", status="TRIGGER PENDING", trigger_price=65.0))
    await pw.watch_tick(D(11, 2, 20), market=market)                        # the retry finds a stop in place
    assert [m["state"] for m in watch if m["kind"] == "watch_no_stop"] == ["unsent_connect"]
    assert next(r[4] for r in await _messages(db) if r[1] == "NO_STOP") == "superseded"


@pytest.mark.asyncio
async def test_a_stop_cancelled_while_the_watch_was_down_is_still_told(watch, kite):
    """[O24d] What covered a trade is kept in partner_watch_state. Before, a restart forgot the stop, and the
    no-stop warning already sent for the trade then hid its cancellation."""
    await _login()
    market = _market(D(10, 0))
    await pw.watch_tick(D(10, 0, 0), market=market)
    kite["orders"] = [_o("101", "BUY", D(10, 0, 2), average_price=75.05)]
    for at in (D(10, 0, 5), D(10, 2, 5)):
        await pw.watch_tick(at, market=market)
    assert watch[-1]["kind"] == "watch_no_stop"
    kite["orders"].append(_o("201", "SELL", D(10, 3), order_type="SL", status="TRIGGER PENDING", trigger_price=65.0))
    await pw.watch_tick(D(10, 3, 5), market=market)
    pw.reset()                                             # the restart
    kite["orders"][-1] = _o("201", "SELL", D(10, 4), order_type="SL", status="CANCELLED", trigger_price=65.0)
    for at in (D(10, 4, 5), D(10, 4, 30)):
        await pw.watch_tick(at, market=market)
    assert watch[-1]["kind"] == "watch_removed" and "your stop at ₹65 is cancelled" in watch[-1]["text"]


@pytest.mark.asyncio
async def test_a_slow_send_does_not_hold_up_the_check(watch, kite, monkeypatch):
    """[O24d] Audit 7: the tick awaited each Telegram send, so a slow send delayed checking the next holding.
    Now the tick finds every message first and the sender goes beside it."""
    db = settings.DB_PATH
    monkeypatch.setattr(pw, "TICK_BUDGET_SEC", 0.6)
    monkeypatch.setattr(pw, "DELIVERY_INLINE_SEC", 0.05, raising=False)
    other = "NIFTY26OCT22400PE"
    await _login()
    market = _market(D(11, 0))
    await pw.watch_tick(D(11, 0, 0), market=market)
    kite["orders"] = [_o("101", "BUY", D(11, 0, 2), average_price=75.05),
                      _o("102", "BUY", D(11, 0, 3), average_price=70.0, tradingsymbol=other)]
    await pw.watch_tick(D(11, 0, 5), market=market)
    await pw.settle()
    fast = partner_bot.send_partner_result

    async def slow(text, **kw):
        await asyncio.sleep(0.5)
        return await fast(text, **kw)

    monkeypatch.setattr(partner_bot, "send_partner_result", slow)
    started = time.monotonic()
    await pw.watch_tick(D(11, 2, 10), market=market)              # both trades 120 s without a stop
    assert time.monotonic() - started < 0.6 + 0.3
    assert len([r for r in await _messages(db) if r[1] == "NO_STOP"]) == 2      # both found in that tick
    await pw.settle()
    assert [m["kind"] for m in watch].count("watch_no_stop") == 2


@pytest.mark.asyncio
async def test_the_ticks_reads_share_one_budget(watch, kite, monkeypatch):
    """[O24d] Audit 7: each read had its own 4 s, so several could pass the 5 s cadence. A read left with too
    little of the budget waits for the next tick, keeping the last one."""
    monkeypatch.setattr(pw, "TICK_BUDGET_SEC", 0.6)
    monkeypatch.setattr(pw, "MIN_READ_SEC", 0.2, raising=False)
    await _login()
    market = _market(D(11, 0))
    await pw.watch_tick(D(11, 0, 0), market=market)
    book = zerodha._kite_call

    async def slow(method, path, **kw):
        if path == "/trades":
            await asyncio.sleep(0.5)
        return await book(method, path, **kw)

    monkeypatch.setattr(zerodha, "_kite_call", slow)
    kite["orders"] = [_o("101", "BUY", D(11, 0, 2), average_price=75.05)]
    started = time.monotonic()
    result = await pw.watch_tick(D(11, 0, 5), market=market)
    assert result["status"] == "COMPLETED" and time.monotonic() - started < 0.6 + 0.3
    assert pw._state.positions_at == D(11, 0, 0)               # the positions read waits for the next tick
    with pytest.raises(zerodha.BrokerError, match="budget"):
        await pw._book("/orders", time.monotonic())
    await pw.settle()                                          # the plan the tick left running


@pytest.mark.asyncio
async def test_one_option_through_a_day_open_trim_add_close_reopen_restart(watch, kite):
    """[O24d] The audit's lifecycle: open, partial exit, add, close, reopen, restart. Each message is for what is
    held when it goes, each trade has its own warnings, and the restart repeats nothing."""
    db = settings.DB_PATH
    await _login()
    market = _market(D(10, 0))
    await pw.watch_tick(D(10, 0, 0), market=market)
    # Open: 130 at ₹80, then a stop for all of it.
    kite["orders"] = [_o("101", "BUY", D(10, 0, 2), qty=130, average_price=80.0)]
    await pw.watch_tick(D(10, 0, 5), market=market)
    kite["orders"].append(_o("201", "SELL", D(10, 0, 30), order_type="SL", status="TRIGGER PENDING", trigger_price=70.0,
                             qty=130))
    await pw.watch_tick(D(10, 0, 35), market=market)
    # Partial exit: 65 sold at ₹85, the stop cut to 65.
    kite["orders"].append(_o("102", "SELL", D(10, 5), qty=65, average_price=85.0))
    kite["orders"][1] = _o("201", "SELL", D(10, 5, 1), order_type="SL", status="TRIGGER PENDING", trigger_price=70.0,
                           qty=65)
    await pw.watch_tick(D(10, 5, 5), market=market)
    # Add 65 at ₹75: the stop now covers 65 of 130.
    kite["orders"].append(_o("103", "BUY", D(10, 10), qty=65, average_price=75.0))
    for at in (D(10, 10, 5), D(10, 12, 5), D(10, 12, 30)):
        await pw.watch_tick(at, market=market)
    # Close: the stop cancelled and everything sold.
    kite["orders"][1] = _o("201", "SELL", D(10, 15), order_type="SL", status="CANCELLED", trigger_price=70.0, qty=65)
    kite["orders"].append(_o("104", "SELL", D(10, 15, 1), qty=130, average_price=78.0))
    for at in (D(10, 15, 5), D(10, 15, 30)):
        await pw.watch_tick(at, market=market)
    # Reopen, then a restart.
    kite["orders"].append(_o("105", "BUY", D(10, 20), average_price=70.0))
    await pw.watch_tick(D(10, 20, 5), market=market)
    told = len(watch)
    pw.reset()
    await pw.watch_tick(D(10, 20, 30), market=market)
    assert len(watch) == told                                   # nothing told twice
    await pw.watch_tick(D(10, 22, 5), market=market)            # the new trade: 120 s without a stop
    assert [m["kind"] for m in watch] == ["watch_plan", "watch_added", "watch_partial", "watch_plan", "watch_no_stop"]
    added = next(m["text"] for m in watch if m["kind"] == "watch_added")
    average = (130 * 80.0 + 65 * 75.0) / 195
    assert added.startswith(f"➕ You added 65 to NIFTY 22300 PE at ₹75, under your first buy at ₹80: now 130 at "
                            f"{pw._px(average)}.")
    assert added.endswith("A stop covers 65 of the 130 now held.")
    partial = next(m["text"] for m in watch if m["kind"] == "watch_partial")
    assert partial.startswith("⚠️ NIFTY 22300 PE: protection incomplete. A stop covers 65 of your 130; the other 65 "
                              "have none.")
    assert [(v["reason"], v["qty"]) for v in await pw.plan_versions(db, "101")] == [
        ("BUY", 130), ("TRIMMED", 65), ("ADDED", 130)]
    assert [(v["reason"], v["qty"]) for v in await pw.plan_versions(db, "105")] == [("BUY", 65)]
    assert watch[-1]["text"].startswith("⏰ NIFTY 22300 PE (65): no stop order yet (bought 10:20).")


# ---------------------------------------------------------------------------
# [O24e] the third review: races at the send, atomic plans, the units a stop sells, protection without a level
# ---------------------------------------------------------------------------

def test_a_stop_moved_for_part_of_a_holding_counts_only_its_units():
    """[O24e] Audit 3: 130 held, two stops of 65; one moved ₹95 → ₹70 adds 25 x 65 = ₹1,625 of gross loss if
    hit, not 25 x 130. The message was for the whole holding."""
    held = _holding(130, entry=100.0)
    cover = pw.cover_of(held, [_stop_row("201", 65, 70.0, D(10, 0)), _stop_row("202", 65, 90.0, D(10, 0))], [])
    before, after = pw._result_for(held, 95.0, 65), pw._result_for(held, 70.0, 65)
    assert round((95.0 - 70.0) * 65, 2) == 1625.0
    assert pw.lowered_text(held, 95.0, 70.0, "FIRST", None, units=65, cover=cover, stop_id="kite:201") == (
        f"⚠️ NIFTY 22300 PE: you moved your stop for 65 of your 130 down ₹95 → ₹70. If it is hit, on those 65: "
        f"{pw._signed(after)} instead of {pw._signed(before)}. The other 65 keep their stop at ₹90. A stop moved down "
        "adds to the loss you chose when you placed it.")
    alone = pw.cover_of(held, [_stop_row("201", 65, 70.0, D(10, 0))], [])
    assert "The other 65 have no stop." in pw.lowered_text(held, 95.0, 70.0, units=65, cover=alone, stop_id="kite:201")
    # A stop for all of it reads as before.
    assert pw.lowered_text(held, 95.0, 70.0, units=130).startswith("⚠️ NIFTY 22300 PE: you moved your stop down ₹95")


def test_without_a_level_the_stop_already_in_place_is_still_named():
    """[O24e] Audit 4: with all 65 covered by an SL at ₹95, the plan without market data still said "At risk:
    the whole ₹6,500 you paid. Decide your stop and place it now." A stop is not a floor under the loss either."""
    held = _holding(65, entry=100.0)
    plan = pw.build_plan(entry=100.0, qty=65, exchange="NFO", opt_type="PE", strike=22300.0, expiry=date(2026, 10, 27),
                         now=D(10, 0, 5), bought_at=D(10, 0), cash=20000.0, option_bars=None, fut_bars=None,
                         fut_price=None, option_mid=None)
    assert (plan.stop, plan.stop_basis) == (None, "PREMIUM")
    full = pw.cover_of(held, [_stop_row("201", 65, 95.0, D(10, 0, 2))], [])
    text = pw.plan_text(held, plan, lots=1, cover=full)
    assert "place it now" not in text
    assert text.splitlines()[1] == (
        f"🛑 Your SL at ₹95 covers all 65. I could not work out a fresh reference level (no market data). If it sells "
        f"there: about {pw._signed(pw._result_at(held, 95.0))} with charges; in a fast fall an SL order can trigger "
        "and still not fill.")
    assert pw.plan_summary(plan, None, full) == "no plan stop; your SL at ₹95 covered all 65"
    big = _holding(130, entry=100.0)
    part = pw.cover_of(big, [_stop_row("202", 65, 95.0, D(10, 0, 2))], [])
    both = pw.revised(plan, entry=100.0, qty=130, exchange="NFO")
    assert pw.plan_text(big, both, lots=2, cover=part).splitlines()[1] \
        == ("🛑 Your SL at ₹95 covers 65 of your 130; the other 65 have none: ₹6,500 of what you paid is at risk on "
            "them. I could not work out a fresh reference level (no market data).")
    unread = pw.plan_text(held, plan, lots=1, cover=pw.cover_of(held, [], None)).splitlines()[1]
    assert "unless a GTT covers it (your GTTs could not be read)" in unread
    assert pw.plan_text(held, plan, lots=1, cover=pw.cover_of(held, [], [])).splitlines()[1].endswith(
        "Decide your stop and place it now.")
    added = pw.added_text(held, added=65, added_px=100.0, first_px=100.0, plan=plan, loss_before=6500.0, cover=full)
    assert added.endswith(f"Your SL at ₹95 covers all 65: if it sells there, about "
                          f"{pw._signed(pw._result_at(held, 95.0))} with charges.")


def test_an_exchange_quote_is_fresh_for_15_seconds():
    """[O24e] The exchange's last quote update counts as fresh for 15 s before we received it (was 60 s), the same
    as our own read: the partner's index options are quoted many times a second."""
    quote = {"bid": 99.9, "ltp": 100.0, "received_at": D(10, 0, 20).isoformat(), "looked_at": D(10, 0, 20)}
    assert pw.level_state(80.0, quote | {"quote_at": D(10, 0, 6).isoformat()}, D(10, 0, 21)) == "VALID"
    assert pw.level_state(80.0, quote | {"quote_at": D(10, 0, 4).isoformat()}, D(10, 0, 21)) == "STALE"


def test_sell_orders_are_counted_against_what_is_held():
    """[O24e] Exits that together sell more than is held: an OCO GTT counts once (only one leg can fire)."""
    rows = [_stop_row("201", 65, 70.0, D(10, 0)),
            _row("202", "SELL", 65, 0.0, D(10, 1), status="OPEN", order_type="LIMIT") | {"price": 110.0},
            _row("203", "SELL", 65, 0.0, D(10, 1), status="CANCELLED", order_type="LIMIT"),
            _stop_row("204", 65, 70.0, D(10, 0), product="MIS")]
    oco = {"id": 7, "type": "two-leg", "status": "active",
           "condition": {"exchange": "NFO", "tradingsymbol": SYMBOL, "trigger_values": [60.0, 120.0]},
           "orders": [{"transaction_type": "SELL", "quantity": 65, "product": "NRML"},
                      {"transaction_type": "SELL", "quantity": 65, "product": "NRML"}]}
    exits = pw.exits_of(rows, [oco], "NFO", SYMBOL, "NRML")
    assert [(e["kind"], e["units"]) for e in exits] == [("SL", 65), ("SELL", 65), ("OCO", 65)]
    assert len(pw.exits_of(rows, [oco], "NFO", SYMBOL, None)) == 4          # any product: the MIS stop too
    assert pw.excess_text(_holding(65), exits) == (
        "⚠️ NIFTY 22300 PE: your sell orders add up to 195 but you hold 65 (SL ₹70 for 65, sell ₹110 for 65, OCO GTT "
        "₹60/₹120 for 65). If more than 65 fill, the extra 130 is a new short sale: Zerodha needs margin for it, and a "
        "short option can lose far more than its premium. An OCO GTT links a stop and a target so that only one of "
        "them can fill.")
    assert pw.orphan_text(SYMBOL, exits[:1]) == (
        "⚠️ NIFTY 22300 PE: you hold none now, but this sell order is still waiting: SL ₹70 for 65. If it triggers it "
        "sells 65 you do not have: a short sale. Cancel it if the trade is over.")


@pytest.mark.asyncio
async def test_a_message_whose_trade_closed_while_it_was_built_is_not_sent(watch, kite, monkeypatch):
    """[O24e] Audit 1: the sender checked the book before building, then awaited the database and prices; a newer
    read showing the trade closed arrived meanwhile, and the old text was still sent. Now it is built again
    from the newer read (and dropped)."""
    db = settings.DB_PATH
    monkeypatch.setattr(pw, "DELIVERY_INLINE_SEC", 0.05, raising=False)
    await _login()
    market = _market(D(11, 0))
    kite["orders"] = [_o("101", "BUY", D(11, 0), average_price=75.05)]
    await pw.watch_tick(D(11, 0, 5), market=market)                         # the plan
    gate, entered = asyncio.Event(), asyncio.Event()
    real = pw._plan_for

    async def held_up(*args, **kwargs):
        entered.set()
        await gate.wait()
        return await real(*args, **kwargs)

    monkeypatch.setattr(pw, "_plan_for", held_up)
    await pw.watch_tick(D(11, 2, 5), market=market)                         # NO_STOP: its build is held up
    await asyncio.wait_for(entered.wait(), 2)
    kite["orders"].append(_o("102", "SELL", D(11, 2, 6), average_price=74.0))
    await pw.watch_tick(D(11, 2, 8), market=market)                         # the newer read: sold
    gate.set()
    await pw.settle()
    assert not any(m["kind"] == "watch_no_stop" for m in watch)
    assert next(r[4] for r in await _messages(db) if r[1] == "NO_STOP") == "superseded"


@pytest.mark.asyncio
async def test_a_newer_read_while_the_row_is_marked_builds_the_message_again(watch, kite, monkeypatch):
    """[O24e] The second check, after the row is marked "attempting": a newer read there puts the row back and
    builds again."""
    db = settings.DB_PATH
    await _login()
    market = _market(D(11, 0))
    kite["orders"] = [_o("101", "BUY", D(11, 0), average_price=75.05)]
    await pw.watch_tick(D(11, 0, 5), market=market)
    real = pw._mark

    async def mark_then_read(db_path, entry, *args):
        await real(db_path, entry, *args)
        if entry.kind == "NO_STOP":                                         # a tick lands: the trade is closed
            pw._state.view = replace(pw._state.view, holdings=[], covers={})

    monkeypatch.setattr(pw, "_mark", mark_then_read)
    await pw.watch_tick(D(11, 2, 5), market=market)
    await pw.settle()
    assert not any(m["kind"] == "watch_no_stop" for m in watch)
    row = next(r for r in await _messages(db) if r[1] == "NO_STOP")
    assert (row[3], row[4]) == (0, "superseded")                            # put back, then dropped


@pytest.mark.asyncio
async def test_a_plan_is_never_stored_without_its_message(watch, kite, monkeypatch):
    """[O24e] Audit 2: the plan was stored, then its PLAN message written separately; one failed write left a
    plan that never got its message (nothing repaired it). The same for an add. Now both go in one transaction:
    a failed write leaves neither, and the next tick tries again."""
    db = settings.DB_PATH
    failed: list = []
    real_enqueue, real_insert = pw._enqueue, getattr(pw, "_insert_outbox", None)

    async def enqueue_once(db_path, key, day, kind, *args, **kwargs):           # the write as 2effb5d made it
        if kind in ("PLAN", "ADDED") and kind not in failed:
            failed.append(kind)
            raise aiosqlite.OperationalError("database is locked")
        return await real_enqueue(db_path, key, day, kind, *args, **kwargs)

    async def insert_once(conn, day, items, now):
        kinds = [item[1] for item in items if item[1] in ("PLAN", "ADDED") and item[1] not in failed]
        if kinds:
            failed.append(kinds[0])
            raise aiosqlite.OperationalError("database is locked")
        return await real_insert(conn, day, items, now)

    monkeypatch.setattr(pw, "_enqueue", enqueue_once)
    if real_insert is not None:
        monkeypatch.setattr(pw, "_insert_outbox", insert_once)
    await _login()
    market = _market(D(11, 0))
    await pw.watch_tick(D(11, 0, 0), market=market)
    kite["orders"] = [_o("101", "BUY", D(11, 0, 2), average_price=75.05)]
    await pw.watch_tick(D(11, 0, 5), market=market)                         # the write fails
    assert watch == [] and await pw.plan_versions(db, "101") == []
    await pw.watch_tick(D(11, 0, 10), market=market)                        # tried again
    assert [m["kind"] for m in watch] == ["watch_plan"]
    kite["orders"].append(_o("102", "BUY", D(11, 1), average_price=70.0))
    await pw.watch_tick(D(11, 1, 5), market=market)                         # the add's write fails
    await pw.watch_tick(D(11, 1, 10), market=market)
    assert [m["kind"] for m in watch] == ["watch_plan", "watch_added"]
    assert [v["reason"] for v in await pw.plan_versions(db, "101")] == ["BUY", "ADDED"]


@pytest.mark.asyncio
async def test_a_stop_moved_for_part_of_a_holding_is_told_for_that_stop(watch, kite):
    """[O24e] Audit 3 in the tick, and the identity: the warning is bound to the stop that moved, not to any
    stop at the new level."""
    db = settings.DB_PATH
    await _login()
    market = _market(D(10, 0))
    await pw.watch_tick(D(10, 0, 0), market=market)
    kite["orders"] = [_o("101", "BUY", D(10, 0, 2), qty=130, average_price=100.0),
                      _o("201", "SELL", D(10, 0, 30), order_type="SL", status="TRIGGER PENDING", trigger_price=95.0),
                      _o("202", "SELL", D(10, 0, 30), order_type="SL", status="TRIGGER PENDING", trigger_price=90.0)]
    await pw.watch_tick(D(10, 0, 35), market=market)
    kite["outcomes"].append("unsent_connect")
    kite["orders"][1] = _o("201", "SELL", D(10, 1), order_type="SL", status="TRIGGER PENDING", trigger_price=70.0)
    await pw.watch_tick(D(10, 1, 5), market=market)
    lowered = [m for m in watch if m["kind"] == "watch_lowered"]
    assert lowered[0]["text"].startswith("⚠️ NIFTY 22300 PE: you moved your stop for 65 of your 130 down ₹95 → ₹70. "
                                         "If it is hit, on those 65: ")
    assert "The other 65 keep their stop at ₹90." in lowered[0]["text"]
    # Before the retry, that stop is cancelled and another put at ₹70: the warning was about the first one.
    kite["orders"][1] = _o("201", "SELL", D(10, 1, 8), order_type="SL", status="CANCELLED", trigger_price=70.0)
    kite["orders"].append(_o("203", "SELL", D(10, 1, 9), order_type="SL", status="TRIGGER PENDING", trigger_price=70.0))
    await pw.watch_tick(D(10, 1, 20), market=market)
    assert [m["state"] for m in watch if m["kind"] == "watch_lowered"] == ["unsent_connect"]
    assert next(r[4] for r in await _messages(db) if r[1] == "LOWERED") == "superseded"


@pytest.mark.asyncio
async def test_a_plan_without_market_data_names_the_stop_already_there(watch, kite):
    """[O24e] Audit 4 in the tick: no market data, the stop placed with the buy."""
    await _login()
    blind = FakeMarket()
    await pw.watch_tick(D(11, 29, 0), market=blind)
    kite["orders"] = [_o("101", "BUY", D(11, 29, 17), average_price=75.05),
                      _o("201", "SELL", D(11, 29, 20), order_type="SL", status="TRIGGER PENDING", trigger_price=70.0)]
    await pw.watch_tick(D(11, 29, 25), market=blind)
    [plan] = [m["text"].splitlines() for m in watch if m["kind"] == "watch_plan"]
    assert plan[1].startswith("🛑 Your SL at ₹70 covers all 65. I could not work out a fresh reference level")
    assert not any("place it now" in line for line in plan)


@pytest.mark.asyncio
async def test_sell_orders_for_more_than_is_held_are_told(watch, kite):
    """[O24e] An SL for 65 and a target limit for 65 on 65 held: if both fill, 65 are sold short."""
    await _login()
    market = _market(D(10, 0))
    await pw.watch_tick(D(10, 0, 0), market=market)
    kite["orders"] = [_o("101", "BUY", D(10, 0, 2), average_price=75.05),
                      _o("201", "SELL", D(10, 0, 30), order_type="SL", status="TRIGGER PENDING", trigger_price=70.0),
                      _o("202", "SELL", D(10, 0, 40), order_type="LIMIT", status="OPEN", price=110.0)]
    await pw.watch_tick(D(10, 0, 45), market=market)
    assert not any(m["kind"] == "watch_excess" for m in watch)              # 20 s to put it right
    await pw.watch_tick(D(10, 1, 10), market=market)
    assert watch[-1]["kind"] == "watch_excess"
    assert watch[-1]["text"].startswith("⚠️ NIFTY 22300 PE: your sell orders add up to 130 but you hold 65 (SL ₹70 "
                                        "for 65, sell ₹110 for 65).")
    count = len(watch)
    await pw.watch_tick(D(10, 1, 40), market=market)
    assert len(watch) == count                                              # told once


@pytest.mark.asyncio
async def test_a_sell_order_left_waiting_after_the_trade_is_told(watch, kite):
    """[O24e] Sold at market with the SL still waiting, and an old GTT on an option no longer held: if either
    triggers it sells what is not held. A stop replaced quickly (the new one placed first) is not told."""
    other = "NIFTY26OCT22400PE"
    kite["gtts"] = [{"id": 9, "type": "single", "status": "active",
                     "condition": {"exchange": "NFO", "tradingsymbol": other, "trigger_values": [40.0],
                                   "last_price": 50.0},
                     "orders": [{"transaction_type": "SELL", "quantity": 65, "product": "NRML", "price": 39.0}]}]
    await _login()
    market = _market(D(10, 0))
    kite["orders"] = [_o("101", "BUY", D(9, 59), average_price=75.05),
                      _o("201", "SELL", D(9, 59, 30), order_type="SL", status="TRIGGER PENDING", trigger_price=70.0)]
    await pw.watch_tick(D(10, 0, 0), market=market)
    await pw.watch_tick(D(10, 0, 25), market=market)
    assert [m["text"] for m in watch if m["kind"] == "watch_orphan"] == [
        "⚠️ NIFTY 22400 PE: you hold none now, but this sell order is still waiting: GTT ₹40 for 65. If it triggers it "
        "sells 65 you do not have: a short sale. Cancel it if the trade is over."]
    # A replacement placed before the old stop is cancelled: briefly 130 for 65, not told.
    kite["orders"].append(_o("202", "SELL", D(10, 1), order_type="SL", status="TRIGGER PENDING", trigger_price=72.0))
    await pw.watch_tick(D(10, 1, 5), market=market)
    kite["orders"][1] = _o("201", "SELL", D(10, 1, 10), order_type="SL", status="CANCELLED", trigger_price=70.0)
    await pw.watch_tick(D(10, 1, 15), market=market)
    await pw.watch_tick(D(10, 1, 40), market=market)
    assert not any(m["kind"] == "watch_excess" for m in watch)
    # Sold at market; the SL still waits.
    kite["orders"].append(_o("102", "SELL", D(10, 5), average_price=76.0))
    for at in (D(10, 5, 5), D(10, 5, 30)):
        await pw.watch_tick(at, market=market)
    assert watch[-1]["kind"] == "watch_orphan" and "this sell order is still waiting: SL ₹72 for 65" in watch[-1]["text"]


@pytest.mark.asyncio
async def test_a_send_cut_off_part_way_is_not_sent_twice(watch, kite, monkeypatch):
    """[O24e] Interrupted after the send began (a shutdown): it may have reached Telegram, so the row stays
    "attempting" and the restart does not send it again."""
    import background_tasks
    db = settings.DB_PATH
    monkeypatch.setattr(pw, "DELIVERY_INLINE_SEC", 0.05, raising=False)
    await _login()
    market = _market(D(11, 0))
    kite["orders"] = [_o("101", "BUY", D(11, 0), average_price=75.05)]
    await pw.watch_tick(D(11, 0, 5), market=market)
    started, fast = asyncio.Event(), partner_bot.send_partner_result

    async def hang(text, **kw):
        started.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(partner_bot, "send_partner_result", hang)
    await pw.watch_tick(D(11, 2, 5), market=market)                         # NO_STOP: its send hangs
    await asyncio.wait_for(started.wait(), 2)
    await background_tasks.drain(grace=0, timeout=2)                        # the shutdown
    monkeypatch.setattr(partner_bot, "send_partner_result", fast)
    pw.reset()
    for at in (D(11, 2, 30), D(11, 2, 50)):
        await pw.watch_tick(at, market=market)
    assert not any(m["kind"] == "watch_no_stop" for m in watch)
    assert next(r[4] for r in await _messages(db) if r[1] == "NO_STOP") == "attempting"
