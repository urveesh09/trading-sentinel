"""[O24-PW] The partner's trade watch: messages only, loss first.

Pure parts (round trips, the plan, the texts) and the tick against a fake
Kite book, a fake market and a fake Telegram.
"""
from datetime import date, datetime, timedelta

import aiosqlite
import pandas as pd
import pytest

import options_math as om
import partner_broker_sync as zerodha
import partner_watch as pw
from config import settings
from fno_chain import RISK_FREE_RATE, years_to_expiry
from partner_coach import round_trip_costs
from tests.test_partner_broker_sync import T, _order, _ts, kite, partner_app  # noqa: F401
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
    def __init__(self, option=None, futures=None, quotes=None):
        super().__init__()
        self.option, self.futures, self.quotes, self.calls = option, futures, quotes or {}, []

    async def quote(self, contracts):
        self.calls.append(("quote", [c.tradingsymbol for c in contracts]))
        return {k: v for k, v in self.quotes.items() if k in {c.tradingsymbol for c in contracts}}

    async def candles(self, contract, interval, start, end):
        self.calls.append((interval, contract.tradingsymbol))
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


def test_round_trips_open_and_close_in_fill_order():
    rows = [_row("1", "BUY", 65, 75.05, D(11, 29, 17)), _row("2", "SELL", 65, 62.6, D(13, 38, 17)),
            _row("3", "BUY", 65, 80.0, D(13, 40)), _row("4", "BUY", 65, 82.0, D(13, 41)),
            _row("5", "SELL", 65, 90.0, D(13, 50)), _row("6", "BUY", 65, 70.0, D(13, 55), status="REJECTED")]
    first, second = pw.trips_from_orders(rows)
    assert (first.key, first.open_qty, first.closed_at) == ("1", 0, D(13, 38, 17))
    assert first.realised() == round((62.6 - 75.05) * 65 - round_trip_costs(75.05, 62.6, 65, "NFO"), 2)
    assert (second.key, second.bought, second.sold, second.open_qty, round(second.entry, 2)) == ("3", 130, 65, 65, 81.0)
    assert second.realised() is None                      # still open


def test_a_position_carried_from_yesterday_is_a_trip_from_the_open():
    carried = [{"exchange": "NFO", "tradingsymbol": SYMBOL, "product": "NRML", "quantity": 65, "overnight_quantity": 65,
                "average_price": 90.0}]
    trips = pw.trips_from_orders([_row("9", "SELL", 65, 80.0, D(10, 0))], carried, DAY)
    assert len(trips) == 1 and trips[0].carried and trips[0].first_at == D(9, 15) and trips[0].open_qty == 0


def test_the_plan_is_the_systems_index_stop_priced_into_the_option():
    now = D(11, 29, 30)
    futures = _futures(now, rising=False)
    plan = pw.build_plan(entry=75.05, qty=65, exchange="NFO", opt_type="PE", strike=22300.0, expiry=date(2026, 10, 27),
                         now=now, bought_at=D(11, 29, 17), cash=7536.7, option_bars=None, fut_bars=futures,
                         fut_price=22534.7, option_mid=75.05)
    years = years_to_expiry(date(2026, 10, 27), now)
    iv = om.implied_vol(75.05, 22534.7, 22300.0, years, RISK_FREE_RATE, False)
    # ATR 40 on these bars; a PE is wrong when the index rises: 22534.7 + 1.5 x 40. The opening-range high
    # (22520 + 20) is under the index, on the winning side, so it is not the stop.
    assert round(plan.atr, 6) == 40.0 and plan.range_edge is None and plan.stop_index == 22594.7
    assert plan.stop == pw._floor_tick(om.black76_price(22594.7, 22300.0, years, iv, RISK_FREE_RATE, False))
    assert plan.stop_basis == "INDEX" and plan.target_index == round(22534.7 - 1.8 * 60.0, 1)
    assert plan.loss == round((75.05 - plan.stop) * 65 + round_trip_costs(75.05, plan.stop, 65, "NFO"), 2)
    assert plan.loss_pct == round(plan.loss / 7536.7, 4) and plan.trend == "WITH"    # falling index, a PE


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


def test_without_market_data_the_plan_names_only_the_premium_at_risk():
    plan = pw.build_plan(entry=100.0, qty=65, exchange="NFO", opt_type="CE", strike=22700.0, expiry=date(2026, 10, 27),
                         now=D(14, 2, 40), bought_at=D(14, 2, 36), cash=7536.7, option_bars=None, fut_bars=None,
                         fut_price=None, option_mid=None)
    assert (plan.stop, plan.stop_basis, plan.loss) == (None, "PREMIUM", 6500.0)
    text = pw.plan_text(pw.Trip("1", "NFO", "NIFTY26OCT22700CE", "NRML", D(14, 2, 36), bought=65, buy_value=6500.0),
                        plan, lots=1)
    assert "At risk: the whole ₹6,500 you paid, 86% of your cash. Decide your stop and place it now." in text
    assert "usual" not in text                       # no usual size known: no size warning
    assert "Place the SL order now" not in text


def test_the_plan_message_reads_plainly():
    plan = pw.Plan(entry=75.05, qty=65, stop=57.85, stop_basis="INDEX", stop_index=22601.3, swing=11.4, loss=1180.0,
                   cash=7536.7, loss_pct=0.1566, target=115.2, target_index=22414.8, run_pct=0.24, run_from=60.5,
                   trend="WITH")
    trip = pw.Trip("1", "NFO", SYMBOL, "NRML", D(11, 29, 17), bought=65, buy_value=65 * 75.05)
    text = pw.plan_text(trip, plan, lots=1, after_loss={"loss": 925.0, "at": "13:53", "minutes": 0, "bigger": "130 after 65"},
                        day_line="Trade 5 today · ₹290 in charges so far.", usual=0.30)
    assert text.splitlines() == [
        "🟢 You bought NIFTY 22300 PE · 1 lot (65) at ₹75.05",
        "🛑 Plan stop ₹57.85 (index 22,601). If it is hit: about −₹1,180 with charges, 16% of your cash.",
        "⚠️ ₹4,878 in this trade, 65% of your cash: much bigger than your usual 30%.",
        "🎯 Target zone ₹115.2 (index 22,415).",
        "• normal 5-min swing ₹11.4; up 24% in the 15 min before you bought (from ₹60.5); the 5-min trend is with you.",
        "⚠️ Your last trade closed −₹925 at 13:53, 0 min before this buy. This is 130 after 65.",
        "Trade 5 today · ₹290 in charges so far.",
        "Place the SL order now: trigger ₹57.85. A fast fall can fill a little lower.",
    ]


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
    assert pw.removed_text(trip, 75.0, None).endswith("Nothing limits this trade's loss now.")


def test_close_texts_name_what_the_close_does():
    trip = pw.Trip("1", "NFO", SYMBOL, "NRML", D(14, 2), bought=65, buy_value=65 * 90.0)
    assert pw.close_text(trip, expiry_today=False, theta_day=-17.08).endswith(
        "As NRML it stays open overnight: time decay is about ₹1,110 a day on it.")
    assert "settled in cash at its in-the-money value" in pw.close_text(trip, expiry_today=True, theta_day=None)
    trip.product = "MIS"
    assert "squares it off near the close" in pw.close_text(trip, expiry_today=False, theta_day=None)


@pytest.mark.asyncio
async def test_the_quiet_button_is_for_today_only(partner_app):
    db = settings.DB_PATH
    assert await pw.handle_button(db, "c:BOUGHT:x", D(10, 0)) is None
    assert await pw.handle_button(db, "watch:quiet:20261022", D(10, 0)) == "That was for an earlier day."
    assert await pw.handle_button(db, "watch:quiet:20261023", D(10, 0)) == pw.QUIET_TOAST
    assert await pw.quiet(db, "2026-10-23") and not await pw.quiet(db, "2026-10-24")


# ---------------------------------------------------------------------------
# the tick
# ---------------------------------------------------------------------------

@pytest.fixture
def watch(kite, monkeypatch):
    """Fake Telegram, an open trading day and the fake option book."""
    sent = []

    class Result:
        def __init__(self):
            self.delivered = True

    async def send(text, *, kind="partner_msg", reply_markup=None):
        sent.append({"kind": kind, "text": text, "keyboard": reply_markup})
        return Result()

    async def trading_day(now):
        return True

    import partner_bot
    monkeypatch.setattr(settings, "PARTNER_WATCH_ENABLED", True)
    monkeypatch.setattr(partner_bot, "partner_enabled", lambda: True)
    monkeypatch.setattr(partner_bot, "send_partner_result", send)
    monkeypatch.setattr(pw, "_is_trading_day", trading_day)
    monkeypatch.setattr(pw, "contract_of", lambda exchange, symbol: FakeContract(symbol))
    pw.reset()
    kite["margins"] = {"available": {"opening_balance": 7536.7, "intraday_payin": 0.0, "live_balance": 7536.7},
                       "utilised": {"option_premium": 0.0}}
    yield sent
    pw.reset()


def _o(order_id, side, at, **over):
    over = {"order_type": "MARKET", "product": "NRML"} | over
    return _order(order_id, side, 65, at, symbol=SYMBOL, exchange="NFO", **over)


def _market(now):
    option = _bars(now - timedelta(minutes=40), 40, 70.0, 76.0, 75.0)
    return FakeMarket(option=option, futures=_futures(now, rising=False),
                      quotes={SYMBOL: {"bid": 75.0, "ask": 75.1, "ltp": 75.05}, FUT: {"bid": None, "ask": None,
                                                                                     "ltp": 22534.7}})


@pytest.mark.asyncio
async def test_a_buy_gets_its_plan_then_no_stop_then_a_lowered_and_a_removed_stop(watch, kite):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", D(9, 0))
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
    assert watch[-1]["kind"] == "watch_no_stop" and watch[-1]["text"].startswith("⏰ NIFTY 22300 PE: no stop order yet")
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
        looks = (await (await conn.execute("SELECT COUNT(*) FROM partner_watch_looks")).fetchone())[0]
    assert looks >= 3                                                                # shadow looks recorded


@pytest.mark.asyncio
async def test_a_cancel_and_lower_replacement_is_one_lowered_message(watch, kite):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", D(9, 0))
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
async def test_a_refusal_is_explained_and_quiet_keeps_only_the_loss_alarms(watch, kite):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", D(9, 0))
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
    await _seed(db)
    await zerodha.create_session("reqtok12", D(9, 0))
    kite["orders"] = [_o("101", "BUY", D(10, 0), average_price=98.75),
                      _o("201", "SELL", D(10, 1), order_type="SL", status="TRIGGER PENDING", trigger_price=85.0),
                      _o("301", "BUY", D(10, 30), status="REJECTED", status_message="Margin required: 8118.50. "
                         "Margin available: 7536.70.")]
    await pw.watch_tick(D(11, 0), market=_market(D(11, 0)))
    assert watch == []                                     # a 60-minute-old buy and an old refusal: nothing told
    async with aiosqlite.connect(db) as conn:
        plans = (await (await conn.execute("SELECT position_key FROM partner_watch_plans")).fetchall())
    assert plans == [("101",)]                              # the plan is kept for later messages


@pytest.mark.asyncio
async def test_login_says_the_watch_is_on_and_a_lost_login_asks_to_reconnect(watch, kite):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", D(9, 5))
    await pw.on_login(D(9, 5))
    assert watch[-1]["kind"] == "watch_watch_on" and watch[-1]["text"].startswith("✅ Trade watch on until 15:40.")
    zerodha.disconnect()                                   # a restart loses the login
    await pw.watch_tick(D(10, 0), market=_market(D(10, 0)))
    await pw.watch_tick(D(10, 0, 5), market=_market(D(10, 0)))
    reconnects = [m for m in watch if m["kind"] == "watch_reconnect"]
    assert len(reconnects) == 1 and reconnects[0]["keyboard"]["inline_keyboard"][0][0]["text"] == "🔐 Reconnect the watch"


@pytest.mark.asyncio
async def test_the_morning_prompt_goes_once_and_not_when_a_login_is_held(watch, kite):
    db = settings.DB_PATH
    await _seed(db)
    assert (await pw.watch_prompt(D(9, 0)))["sent"] is True
    assert watch[-1]["text"] == pw.PROMPT_TEXT and watch[-1]["keyboard"]["inline_keyboard"][0][0]["text"] == \
        "🔐 Start today's watch"
    assert (await pw.watch_prompt(D(9, 0, 30)))["sent"] is False
    await zerodha.create_session("reqtok12", D(9, 1))
    assert (await pw.watch_prompt(D(9, 2)))["reason"] == "connected"


@pytest.mark.asyncio
async def test_a_gtt_stop_counts_and_no_stop_is_not_claimed(watch, kite):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", D(9, 0))
    market = _market(D(11, 0))
    kite["orders"] = [_o("101", "BUY", D(11, 0), average_price=75.05)]
    kite["gtts"] = [{"id": 5, "type": "single", "status": "active", "created_at": _ts(D(11, 0, 30)),
                     "updated_at": _ts(D(11, 0, 30)),
                     "condition": {"exchange": "NFO", "tradingsymbol": SYMBOL, "trigger_values": [60.0], "last_price": 75.0},
                     "orders": [{"transaction_type": "SELL", "quantity": 65, "order_type": "LIMIT", "price": 60.0}]}]
    await pw.watch_tick(D(11, 0, 10), market=market)
    await pw.watch_tick(D(11, 3), market=market)
    assert [m["kind"] for m in watch] == ["watch_plan"]


@pytest.mark.asyncio
async def test_the_review_shows_what_the_assistant_said(watch, kite):
    import partner_coach as pc
    import partner_lessons as lessons
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", D(9, 0))
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
    """[O24-SZ] No fixed share of cash: earlier days' Zerodha buys set the usual (1.5 x their median share)."""
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.init_partner_broker_db(db)
    async with aiosqlite.connect(db) as conn:
        for i, day in enumerate(("2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-22")):
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
