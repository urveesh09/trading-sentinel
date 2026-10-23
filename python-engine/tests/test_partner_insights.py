"""[O21-PX] The deeper partner review: what the option did around each trade
(1-minute candles), what the Zerodha book shows (order changes, rejections,
positions, the day's cash), the lessons and positives that follow, the
rules-kept score, the window statistics and the evening review link.

Every rupee figure is recomputed from prices with the coach's own charges, so
an arithmetic or wording slip fails a test."""
import asyncio
import json
from datetime import timedelta

import aiosqlite
import pytest

import partner_broker_sync as zerodha
import partner_coach as pc
import partner_fill_capture as pfc
import partner_insights as pi
import partner_lessons as pl
import partner_trade_paths as ptp
from config import settings
from tests.test_partner_broker_sync import _order, _resolve, _trade, kite, partner_app, partner_chat  # noqa: F401
from tests.test_partner_coach import DAY, OFF, RISING, T, _card, _item, _net, _view, _zr, rs
from tests.test_partner_fill_capture import _seed

SYM = OFF["tradingsymbol"]          # NIFTY26O2022950PE, lot 75, NFO
CANDLES = pi.BASIS_CANDLES


def candles(start, closes, day=19):
    """1-minute candles from ``start`` (h, m): open = the previous close."""
    h, m = start
    out, previous = [], closes[0]
    for i, close in enumerate(closes):
        at = T(h, m, day=day) + timedelta(minutes=i)
        out.append((at, float(previous), float(max(previous, close)), float(min(previous, close)), float(close)))
        previous = close
    return out


def ramp(a, b, n):
    """n closes from a (exclusive) to b (inclusive)."""
    return [round(a + (b - a) * (i + 1) / n, 2) for i in range(n)]


def ctx(bars=None, basis=CANDLES, symbol=SYM, exchange="NFO", **more):
    context = {"paths": {(DAY, exchange, symbol): {"basis": basis, "bars": bars}} if bars else {}}
    context.update(more)
    return context


def off(action, at, price, lots=1, order_id=None, **over):
    """An off-card Zerodha fill."""
    extra = {"dedup_key": f"kite:{order_id}"} if order_id else {}
    return _zr(action, at, price, lots=lots, **OFF, **extra, **over)


def off_item(view):
    return view["days"][0]["off_card"][0]


def codes(item):
    return [f["code"] for f in item["flags"]]


def flag(item, code):
    return next(f for f in item["flags"] if f["code"] == code)


def net(entry, exit_, qty, orders=2):
    return _net(entry, exit_, qty, "NFO", orders)


# ---------------------------------------------------------------------------
# what the option did: spike, giving back, cutting a loss, the numbers
# ---------------------------------------------------------------------------

SPIKE = candles((10, 0), [100.0] * 15 + ramp(100, 130, 15) + [131.0] + ramp(131, 110, 15) + [110.0] * 14)


def test_buying_straight_after_a_spike_is_named_with_the_run_and_the_dip():
    view = _view([], [off("BUY", T(10, 30, 20), 131.0), off("SELL", T(10, 46, 5), 110.0)], context=ctx(SPIKE))
    item = off_item(view)
    assert codes(item) == ["OFF_CARD", "CHASED_SPIKE"]
    spike = flag(item, "CHASED_SPIKE")
    assert spike["reason"] == ("You bought at ₹131 at 10:30, after the option rose 31% in 15 minutes (from ₹100), "
                               "at a new high for the day.")
    assert "In the 15 minutes after your buy it traded as low as ₹110 (−16%)." in spike["why"]
    # The rupees are told once, on OFF_CARD; the spike is the why.
    assert spike["impact_rs"] is None and spike["advice"] == pc.ADVICE["CHASED_SPIKE"]
    insight = item["insight"]
    assert insight["before"] == {"minutes": 15, "low": 100.0, "run_pct": 0.31}
    assert insight["best"]["price"] == 131.0 and insight["worst"] == {
        "at": "10:45", "price": 110.0, "move_rs": round((110 - 131) * 75, 2), "pct": round(110 / 131 - 1, 4)}
    assert insight["gross_pnl"] == (110 - 131) * 75 and insight["charges"] == round((110 - 131) * 75 - net(131, 110, 75), 2)


def test_a_slow_rise_a_buy_under_the_high_or_5_minute_prints_are_not_a_spike():
    slow = candles((10, 0), [100.0] * 15 + ramp(100, 110, 15) + [111.0] * 20)
    view = _view([], [off("BUY", T(10, 30, 20), 111.0), off("SELL", T(10, 46), 110.0)], context=ctx(slow))
    assert "CHASED_SPIKE" not in codes(off_item(view))
    # A 31% run, but bought 10% under the high made at 10:19.
    peaked = candles((10, 0), [100.0] * 15 + ramp(100, 145, 5) + ramp(145, 131, 10) + [131.0] * 20)
    view = _view([], [off("BUY", T(10, 30, 20), 131.0), off("SELL", T(10, 46), 120.0)], context=ctx(peaked))
    assert "CHASED_SPIKE" not in codes(off_item(view))
    view = _view([], [off("BUY", T(10, 30, 20), 131.0), off("SELL", T(10, 46, 5), 110.0)],
                 context=ctx(SPIKE, basis="5MIN_PRINTS"))
    assert "CHASED_SPIKE" not in codes(off_item(view))


GIVE_BACK = candles((10, 0), [100.0] + ramp(100, 125, 15) + ramp(125, 90, 20) + ramp(90, 70, 30) + [70.0] * 5)


def test_a_winner_that_turned_into_a_loss_is_priced_with_the_stop_at_the_entry():
    view = _view([], [off("BUY", T(10, 0, 30), 100.0), off("SELL", T(10, 36, 10), 90.0)], context=ctx(GIVE_BACK))
    item = off_item(view)
    gave = flag(item, "GAVE_BACK_PROFIT")
    actual, better = net(100, 90, 75), net(100, 97, 75)
    assert gave["reason"] == (f"At 10:15 the option was ₹125, 25% above your ₹100 buy (about {rs(25 * 75)} open "
                              f"on 75 qty). You sold at ₹90 at 10:36: {rs(actual)} after charges.")
    assert (gave["better_pnl"], gave["actual_pnl"], gave["impact_rs"]) == (better, actual, round(actual - better, 2))
    assert gave["better"] == (f"Moving the SL order to your buy price once it was up 20% would have sold near ₹100 "
                              f"(a fast fall fills a little lower): about {rs(better)} instead of {rs(actual)}.")
    # 30 minutes later the option was ₹70: cutting at ₹90 kept the loss ₹1,500 smaller. Hindsight praises the exit.
    [cut] = [p for p in item["positives"] if p["code"] == "CUT_LOSS_SAVED"]
    after = item["insight"]["after"]
    assert (after["minutes"], after["at"]) == (30, "11:06") and after["price"] <= 90 * 0.85
    assert cut["reason"] == (f"You sold at ₹90 for {rs(actual)}; 30 minutes later the option was {pc._px(after['price'])}. "
                             f"Getting out kept the loss about {pc._amt((90 - after['price']) * 75)} smaller than "
                             f"holding to then.")


def test_a_card_trade_follows_its_card_so_spike_and_give_back_are_not_flagged():
    sensex = "SENSEX26O2274200PE"
    bars = candles((11, 50), [500.0] * 15 + ramp(500, 640, 15) + ramp(640, 470, 40))
    view = _view([_card(series=RISING)], [_zr("BUY", T(12, 9), 518.0), _zr("SELL", T(12, 56), 470.0)],
                 context=ctx(bars, symbol=sensex, exchange="BFO"))
    item = _item(view)
    assert not {"CHASED_SPIKE", "GAVE_BACK_PROFIT"} & set(codes(item))
    assert item["insight"]["chart"]["levels"][:3] == [
        {"label": "Card buy-up-to", "price": 522.35, "kind": "limit"}, {"label": "Card SL", "price": 464.7, "kind": "stop"},
        {"label": "Card target", "price": 567.2, "kind": "target"}]


def test_the_chart_spans_the_trade_with_both_fills_marked():
    view = _view([], [off("BUY", T(10, 30, 20), 131.0), off("SELL", T(10, 46, 5), 110.0)], context=ctx(SPIKE))
    chart = off_item(view)["insight"]["chart"]
    assert (chart["start"], chart["end"], chart["start_t"], chart["end_t"]) == ("10:10", "10:59", 55, 104)
    assert chart["points"][0] == [55, 100.0] and chart["points"][-1] == [104, 110.0]
    assert chart["marks"] == [{"t": 75, "at": "10:30", "price": 131.0, "kind": "buy"},
                              {"t": 91, "at": "10:46", "price": 110.0, "kind": "sell"}]


# ---------------------------------------------------------------------------
# the order book: stops moved, buy prices raised, refusals
# ---------------------------------------------------------------------------

def _sl(order_id, placed, trigger, status="COMPLETE", **over):
    row = {"order_id": order_id, "session_date": DAY, "exchange": "NFO", "tradingsymbol": SYM,
           "transaction_type": "SELL", "order_type": "SL", "product": "NRML", "quantity": 75, "filled_quantity": 75,
           "price": trigger - 1, "trigger_price": trigger, "average_price": None, "status": status,
           "status_message": None, "placed_at": placed.isoformat(), "updated_at": None, "modified": 1}
    row.update(over)
    return row


def _change(order_id, at, field, old, new, seq=0):
    return {"order_id": order_id, "seq": seq, "session_date": DAY, "changed_at": at.isoformat(), "field": field,
            "old_value": old, "new_value": new}


STOP_PATH = candles((11, 0), [100.0] + ramp(100, 92, 19) + ramp(92, 78, 10) + [78.0] * 10)


def test_a_stop_moved_down_is_priced_where_it_was_placed():
    reports = [off("BUY", T(11, 0, 20), 100.0, order_id="1001"), off("SELL", T(11, 30, 2), 78.0, order_id="2001")]
    context = ctx(STOP_PATH, orders=[_sl("2001", T(11, 1), 80.0)],
                  changes={"2001": [_change("2001", T(11, 20, 5), "trigger_price", 90.0, 80.0)]})
    item = off_item(_view([], reports, context=context))
    lowered = flag(item, "STOP_LOWERED")
    actual, better = net(100, 78, 75), net(100, 90, 75)
    assert lowered["reason"] == "You moved your SL order down from ₹90 to ₹80 at 11:20."
    assert lowered["better"] == f"Keeping it at ₹90: the option traded there at 11:21, so about {rs(better)} instead of {rs(actual)}."
    assert (lowered["better_pnl"], lowered["impact_rs"]) == (better, round(actual - better, 2))
    assert lowered["advice"] == pc.ADVICE["STOP_CANCELLED"]
    assert ("11:20", "You lowered your stop from ₹90 to ₹80") in [(e["at"], e["text"]) for e in item["insight"]["events"]]


def test_a_stop_moved_up_is_praised_and_an_unpriced_lowering_still_named():
    reports = [off("BUY", T(11, 0, 20), 100.0, order_id="1001"), off("SELL", T(11, 30, 2), 104.0, order_id="2001")]
    up = ctx(None, orders=[_sl("2001", T(11, 1), 104.0)],
             changes={"2001": [_change("2001", T(11, 25), "trigger_price", 90.0, 104.0)]})
    item = off_item(_view([], reports, context=up))
    assert "STOP_LOWERED" not in codes(item)
    assert [p for p in item["positives"] if p["code"] == "STOP_TRAILED"][0]["reason"] == \
        "You raised your SL order to ₹104 at 11:25, so less of the trade was at risk."
    down = ctx(None, orders=[_sl("2001", T(11, 1), 85.0)],
               changes={"2001": [_change("2001", T(11, 10), "trigger_price", 90.0, 85.0)]})
    lowered = flag(off_item(_view([], reports, context=down)), "STOP_LOWERED")
    assert lowered["better_pnl"] is None and lowered["better"].startswith("Leave the stop where you placed it")


def test_raising_the_buy_price_to_get_filled_is_chasing_unless_inside_the_card():
    raises = {"1001": [_change("1001", T(10, 0, 10), "price", 100.0, 102.0),
                       _change("1001", T(10, 0, 40), "price", 102.0, 104.0, seq=1)]}
    view = _view([], [off("BUY", T(10, 0, 41), 104.0, order_id="1001"), off("SELL", T(10, 20), 110.0)],
                 context=ctx(None, changes=raises))
    raised = flag(off_item(view), "PRICE_RAISED_TO_FILL")
    assert raised["reason"] == "You raised your buy price 2 times, from ₹100 to ₹104 (+4.0%), between 10:00 and 10:00."
    assert raised["impact_rs"] is None
    inside = {"9001": [_change("9001", T(12, 8), "price", 515.0, 518.0),
                       _change("9001", T(12, 8, 30), "price", 518.0, 520.0, seq=1)]}
    card_view = _view([_card()], [_zr("BUY", T(12, 9), 520.0, dedup_key="kite:9001"), _zr("SELL", T(13, 3), 598.0)],
                      context={"changes": inside})
    assert "PRICE_RAISED_TO_FILL" not in codes(_item(card_view))
    past = {"9001": inside["9001"] + [_change("9001", T(12, 8, 50), "price", 520.0, 526.0, seq=2)]}
    card_view = _view([_card()], [_zr("BUY", T(12, 9), 526.0, dedup_key="kite:9001"), _zr("SELL", T(13, 3), 598.0)],
                      context={"changes": past})
    assert {"ENTRY_ABOVE_LIMIT", "PRICE_RAISED_TO_FILL"} <= set(codes(_item(card_view)))


def test_a_buy_refused_for_money_is_a_day_lesson_and_the_orders_are_counted():
    orders = [_sl("3001", T(10, 5), 0.0, transaction_type="BUY", order_type="LIMIT", status="REJECTED",
                  filled_quantity=0, quantity=450, status_message="Insufficient funds. Required margin is 45000.00 "
                                                                  "but available margin is 9000.00."),
              _sl("3002", T(10, 6), 0.0, transaction_type="BUY", order_type="MARKET", status="COMPLETE"),
              _sl("3003", T(10, 7), 0.0, transaction_type="BUY", order_type="LIMIT", status="CANCELLED",
                  filled_quantity=0)]
    view = _view([], [off("BUY", T(10, 6), 100.0), off("SELL", T(10, 30), 104.0)], context=ctx(None, orders=orders))
    row = view["days"][0]
    [funds] = row["day_flags"]
    assert funds["code"] == "INSUFFICIENT_FUNDS" and funds["reason"] == (
        "At 10:05 Zerodha refused your buy of 450 NIFTY26O2022950PE: “Insufficient funds. Required margin is "
        "45000.00 but available margin is 9000.00.”.")
    assert row["orders"] | {"rejected": len(row["orders"]["rejected"])} == {
        "placed": 3, "filled": 1, "rejected": 1, "cancelled_unfilled": 1, "modified": 0, "market": 1}
    review = pl.day_review(view, DAY)
    assert {r["key"]: (r["kept"], r["of"]) for r in review["score"]["rules"]}["cash"] == (0, 1)


# ---------------------------------------------------------------------------
# the account: risk against the day's cash, positions at the close
# ---------------------------------------------------------------------------

def _cash(opening, payin=0.0):
    return {DAY: {"session_date": DAY, "opening_balance": opening, "intraday_payin": payin, "live_balance": None,
                  "option_premium": None, "read_at": T(15, 45).isoformat()}}


def test_risk_is_measured_against_the_day_cash_and_too_much_is_sized_down():
    reports = [off("BUY", T(10, 0), 30.0, lots=3), off("SELL", T(10, 30), 20.0, lots=3)]
    item = off_item(_view([], reports, context=ctx(None, accounts=_cash(45000.0, 5000.0))))
    risk = flag(item, "BIG_RISK")
    actual, better = net(30, 20, 225), net(30, 20, 150)
    assert risk["reason"] == ("3 lots of NIFTY 22950 PE at ₹30: ₹6,750 at risk in premium paid, 14% of the ₹50,000 "
                              "cash in your account today.")
    assert risk["better"] == f"2 lots instead: about 9% at risk, and {rs(better)} instead of {rs(actual)}."
    assert (risk["better_pnl"], risk["impact_rs"]) == (better, round(actual - better, 2))
    assert item["insight"]["risk"] == {"rs": 6750.0, "pct_of_cash": 0.135, "basis": "PREMIUM", "cash": 50000.0,
                                       "trigger": None}


def test_a_stop_order_sets_the_risk_and_one_lot_too_big_says_so():
    stop = [{"source_id": "kite:2001", "session_date": DAY, "kind": "SL_ORDER", "exchange": "NFO", "tradingsymbol": SYM,
             "trigger_price": 80.0, "quantity": 150, "status": "TRIGGERED", "placed_at": T(10, 1).isoformat(),
             "updated_at": T(10, 20).isoformat()}]
    reports = [off("BUY", T(10, 0), 100.0, lots=2), off("SELL", T(10, 20), 80.0, lots=2)]
    item = off_item(_view([], reports, stops=stop, stops_known_days=frozenset({DAY}),
                          context=ctx(None, accounts=_cash(100000.0))))
    assert "BIG_RISK" not in codes(item)
    assert item["insight"]["risk"]["basis"] == "STOP" and item["insight"]["risk"]["rs"] == 3000.0
    item = off_item(_view([], reports, stops=[], stops_known_days=frozenset({DAY}),
                          context=ctx(None, accounts=_cash(50000.0))))
    risk = flag(item, "BIG_RISK")
    assert "₹15,000 at risk with no stop order, 30% of the ₹50,000 cash" in risk["reason"]
    assert risk["better"].startswith("Even 1 lot put more than a tenth of your cash at risk")
    assert risk["better_pnl"] is None and risk["impact_rs"] is None


def _held(quantity):
    return {DAY: [{"session_date": DAY, "exchange": "NFO", "tradingsymbol": SYM, "product": "NRML",
                   "quantity": quantity, "overnight_quantity": 0, "average_price": 100.0, "last_price": 95.0,
                   "close_price": None, "read_at": T(15, 45).isoformat()}]}


def test_an_off_card_option_still_held_at_the_close_is_named_when_zerodha_agrees():
    reports = [off("BUY", T(14, 0), 100.0)]
    known = frozenset({DAY})
    item = off_item(_view([], reports, complete_days=known, context=ctx(None, positions=_held(75))))
    held = flag(item, "HELD_OVERNIGHT")
    assert held["reason"] == "You still held 1 lot of NIFTY 22950 PE at the close."
    item = off_item(_view([], reports, complete_days=known, context=ctx(None, positions=_held(0))))
    assert "HELD_OVERNIGHT" not in codes(item)
    item = off_item(_view([], reports, complete_days=frozenset(), context=ctx(None)))
    assert "HELD_OVERNIGHT" not in codes(item)
    expiring = [off("BUY", T(14, 0), 100.0, expiry=DAY)]
    item = off_item(_view([], expiring, complete_days=known, context=ctx(None)))
    assert flag(item, "HELD_OVERNIGHT")["reason"].endswith("It expired today.")


# ---------------------------------------------------------------------------
# the review: rules kept, the option lines, day and window numbers, focus
# ---------------------------------------------------------------------------

def test_rules_kept_count_process_not_money_and_the_stop_rule_needs_known_stops():
    view = _view([], [off("BUY", T(10, 30, 20), 131.0), off("SELL", T(10, 46, 5), 110.0)], context=ctx(SPIKE))
    review = pl.day_review(view, DAY)
    [story] = review["trades"]
    assert [(c["key"], c["kept"]) for c in story["checks"]] == [
        ("card", False), ("entry", False), ("exit", True), ("calm", True), ("size", True)]
    means = pl.RULE_MEANINGS     # [O23-PM] each rule says what it means
    assert review["score"] == {"kept": 4, "of": 6, "pct": 67, "rules": [
        {"key": "card", "name": "Traded a card", "kept": 0, "of": 1, "means": means["card"]},
        {"key": "entry", "name": "Entered as planned", "kept": 0, "of": 1, "means": means["entry"]},
        {"key": "exit", "name": "Exited by the plan", "kept": 1, "of": 1, "means": means["exit"]},
        {"key": "calm", "name": "Calm after a loss", "kept": 1, "of": 1, "means": means["calm"]},
        {"key": "size", "name": "Size within the account", "kept": 1, "of": 1, "means": means["size"]},
        {"key": "cards_only", "name": "Traded only the cards", "kept": 1, "of": 1, "means": means["cards_only"]}]}
    assert story["option_lines"][:2] == [
        "Before you bought: up 31% in 15 minutes (from ₹100).",
        f"While you held (16 min): best ₹131 at 10:31 (₹0 open), worst ₹110 at 10:45 ({rs(-21 * 75)} open)."]
    assert story["option_lines"][-1] == f"Charges: {pc._amt(story['numbers']['charges'])} on a {rs(-21 * 75)} price move."
    assert story["chart"]["marks"][0]["kind"] == "buy"
    stats = review["stats"]
    assert (stats["trades"], stats["losses"], stats["time_in_market_min"]) == (1, 1, 16)
    assert stats["charges"] == story["numbers"]["charges"] and stats["gross_pnl"] == -21 * 75
    assert pl.render_note(review).split("\n")[1].endswith("rules kept 4/6")


def _round_trip(day, buy, sell, entry, exit_, lots=1):
    return [_zr("BUY", T(*buy, day=day), entry, lots=lots, **OFF), _zr("SELL", T(*sell, day=day), exit_, lots=lots, **OFF)]


def test_window_statistics_put_each_clear_pattern_into_one_line():
    reports = []
    # Three quick winners and three slow losers, two of them soon after a loss, mostly at the open.
    for day, buy, sell, entry, exit_ in ((13, (9, 20), (9, 25), 100, 110), (14, (9, 20), (9, 25), 100, 110),
                                         (15, (9, 20), (9, 25), 100, 110), (16, (9, 20), (9, 50), 100, 80),
                                         (16, (10, 0), (10, 40), 100, 80), (16, (10, 50), (11, 30), 100, 80)):
        reports += _round_trip(day, buy, sell, entry, exit_)
    view = _view([], reports, now=T(16, 0))
    stats = pl.progress(view, DAY)["stats"]
    win, loss = net(100, 110, 75), net(100, 80, 75)
    assert (stats["trades"], stats["wins"], stats["losses"], stats["win_rate"]) == (6, 3, 3, 0.5)
    assert (stats["avg_win"], stats["avg_loss"]) == (round(win, 2), round(loss, 2))
    assert stats["hold_min"] == {"wins": 5, "losses": 40}
    assert stats["after_loss"] == {"trades": 2, "pnl": round(2 * loss, 2)}
    assert stats["off_card"]["trades"] == 6 and stats["on_card"] == {"trades": 0, "pnl": None}
    assert stats["by_time"][0] == {"label": "09:15–09:45", "trades": 4, "pnl": round(3 * win + loss, 2)}
    lines = stats["insights"]
    assert lines[0] == ("You hold losing trades about 8.0× as long as winning ones (median 40 min against 5 min). "
                        "Losers get time to grow while winners get cut short: let the stop end a loser.")
    assert lines[1].startswith(f"Your average loss ({rs(loss)}) is bigger than your average win ({rs(win)})")
    assert f"Trades without a card: 6, {rs(3 * win + 3 * loss)}. Card trades: 0, n/a." in lines
    assert f"Trades taken within 30 minutes of a loss: 2, {rs(2 * loss)}." in lines
    assert lines[-1].startswith("Charges: ") and "over 6 trades" in lines[-1]


def test_the_focus_is_the_rule_broken_most_this_week():
    reports = (_round_trip(13, (10, 0), (10, 20), 100, 90) + _round_trip(14, (10, 0), (10, 20), 100, 90)
               + _round_trip(5, (10, 0), (10, 20), 100, 90))
    progress = pl.progress(_view([], reports, now=T(16, 0)), DAY)
    assert progress["focus"] == {"code": "OFF_CARD", "title": "Trade without a card", "rule": pc.ADVICE["OFF_CARD"],
                                 "count": 2, "text": "Trade without a card: 2 times in the last 7 days."}
    assert pl.progress(_view([], [], now=T(16, 0)), DAY)["focus"] is None


def test_a_view_without_context_is_unchanged_but_still_counts_hold_and_charges():
    view = _view([], [off("BUY", T(10, 0), 100.0), off("SELL", T(10, 30), 104.0)])
    item = off_item(view)
    assert set(item["insight"]) == {"hold_min", "held_to_close", "basis", "gross_pnl", "charges"}
    assert codes(item) == ["OFF_CARD"]


# ---------------------------------------------------------------------------
# the Zerodha read: order book details, best effort
# ---------------------------------------------------------------------------

def test_order_history_changes_count_only_confirmed_states():
    history = [{"status": "PUT ORDER REQ RECEIVED", "price": 100, "order_timestamp": "2026-10-19 10:00:00"},
               {"status": "OPEN", "price": 100, "order_timestamp": "2026-10-19 10:00:01"},
               {"status": "MODIFY VALIDATION PENDING", "price": 140, "order_timestamp": "2026-10-19 10:00:05"},
               {"status": "OPEN", "price": 100, "order_timestamp": "2026-10-19 10:00:06"},
               {"status": "OPEN", "price": 102, "exchange_update_timestamp": "2026-10-19 10:00:20"},
               {"status": "COMPLETE", "price": 102, "order_timestamp": "2026-10-19 10:00:30"}]
    assert zerodha.order_changes("1001", history) == [
        {"order_id": "1001", "seq": 0, "session_date": DAY, "changed_at": T(10, 0, 20).isoformat(), "field": "price",
         "old_value": 100.0, "new_value": 102.0}]


def test_option_orders_positions_and_cash_are_parsed():
    orders = [_order("251019000000001", "BUY", 75, T(10, 0), symbol=SYM, exchange="NFO", modified=True,
                     status="REJECTED", status_message="Insufficient funds"),
              _order("251019000000002", "SELL", 20, T(10, 5), order_type="SL", trigger_price=465.0),
              _order("251019000000003", "BUY", 1, T(10, 6), symbol="RELIANCE", exchange="NSE")]
    rows = zerodha.option_orders(orders, resolve=_resolve)
    assert [(r["order_id"], r["status"], r["modified"], r["status_message"]) for r in rows] == [
        ("251019000000001", "REJECTED", 1, "Insufficient funds"), ("251019000000002", "COMPLETE", 1, None)]
    positions = zerodha.option_positions({"net": [
        {"exchange": "NFO", "tradingsymbol": SYM, "product": "NRML", "quantity": 75, "overnight_quantity": 0,
         "average_price": 100, "last_price": 95, "close_price": 0},
        {"exchange": "NSE", "tradingsymbol": "RELIANCE", "product": "CNC", "quantity": 1}]}, resolve=_resolve)
    assert [(p["tradingsymbol"], p["quantity"], p["last_price"]) for p in positions] == [(SYM, 75, 95.0)]
    assert zerodha.option_positions([], resolve=_resolve) == []
    assert zerodha.account_row({"available": {"opening_balance": 50000, "intraday_payin": 2000}}) == {
        "opening_balance": 50000.0, "intraday_payin": 2000.0, "live_balance": None, "option_premium": None}
    assert zerodha.account_row({"available": {}}) is None and zerodha.account_row(None) is None


@pytest.mark.asyncio
async def test_a_read_stores_the_details_and_survives_a_failed_part(kite, monkeypatch):  # noqa: F811
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", T(15, 41))
    kite["orders"] = [_order("251019000000011", "BUY", 75, T(10, 0), symbol=SYM, exchange="NFO", modified=True),
                      _order("251019000000012", "SELL", 75, T(10, 1), symbol=SYM, exchange="NFO", order_type="SL",
                             trigger_price=80.0, modified=True, status="TRIGGER PENDING"),
                      _order("251019000000013", "SELL", 75, T(10, 30), symbol=SYM, exchange="NFO", modified=False)]
    kite["trades"] = [_trade("251019000000011", 75, 100.0, T(10, 0, 5)),
                      _trade("251019000000013", 75, 104.0, T(10, 30, 1))]
    kite["histories"] = {"251019000000011": [
        {"status": "OPEN", "price": 99, "order_timestamp": "2026-10-19 10:00:00"},
        {"status": "COMPLETE", "price": 100, "order_timestamp": "2026-10-19 10:00:05"}]}
    kite["positions"] = {"net": [{"exchange": "NFO", "tradingsymbol": SYM, "product": "NRML", "quantity": 0,
                                  "overnight_quantity": 0, "average_price": 0, "last_price": 101}]}
    kite["margins"] = {"available": {"opening_balance": 60000, "intraday_payin": 0}}
    fake = zerodha._kite_call

    async def history_fails_once(method, path, **kwargs):
        if path == "/orders/251019000000012":
            raise zerodha.BrokerError("NetworkException", "timeout")
        return await fake(method, path, **kwargs)

    monkeypatch.setattr(zerodha, "_kite_call", history_fails_once)
    result = await zerodha.sync_book(T(15, 45))
    assert result["details"] == {"orders": 3, "histories": 1, "history_failures": 1, "positions": 1, "account": True}
    # Only modified orders' histories are read.
    assert [c[1] for c in kite["calls"] if c[1].startswith("/orders/")] == ["/orders/251019000000011"]
    details = await zerodha.book_details(db, DAY, DAY)
    assert [o["order_id"] for o in details["orders"]] == ["251019000000011", "251019000000012", "251019000000013"]
    assert details["changes"]["251019000000011"][0]["new_value"] == 100.0
    assert details["positions"][DAY][0]["last_price"] == 101.0
    assert details["accounts"][DAY]["opening_balance"] == 60000.0


@pytest.mark.asyncio
async def test_positions_and_cash_are_not_read_before_the_open(kite):  # noqa: F811
    await _seed(settings.DB_PATH)
    await zerodha.create_session("reqtok12", T(8, 0))
    result = await zerodha.sync_book(T(8, 30))
    assert result["details"]["positions"] is None and result["details"]["account"] is None
    assert not [c for c in kite["calls"] if c[1] in ("/portfolio/positions", "/user/margins/equity")]


# ---------------------------------------------------------------------------
# price paths from the owner's market data
# ---------------------------------------------------------------------------

async def _traded(db, symbol=SYM):
    await pfc.init_partner_fill_db(db)
    for i, (action, at, price) in enumerate((("BUY", T(10, 0), 100.0), ("SELL", T(10, 30), 104.0))):
        await pfc.insert_report(db, {"dedup_key": f"kite:p{i}", "source": "ZERODHA", "received_at": T(15, 45).isoformat(),
                                     "trade_at": at.isoformat(), "trade_at_basis": "EXCHANGE_FILL", "action": action,
                                     "session_date": DAY, "underlying": "NIFTY", "tradingsymbol": symbol,
                                     "strike": 22950.0, "opt_type": "PE", "expiry": "2026-10-20", "exchange": "NFO",
                                     "lots": 1, "lot_size": 75, "price": price, "price_basis": "BROKER_FILL"})


@pytest.mark.asyncio
async def test_paths_are_read_once_after_the_close_and_fall_back_to_prints(monkeypatch):
    db = settings.DB_PATH
    await _traded(db)
    calls = []

    async def fetch(token, start, end):
        calls.append((token, start, end))
        return [("2026-10-19 10:00:00", 100, 101, 99, 100.5), ("2026-10-19 10:01:00", 100.5, 103, 100, 102)]

    assert (await ptp.ensure_paths(db, DAY, T(15, 0), fetch=fetch, token_of=lambda e, s: 7))["status"] == "day_not_over"
    out = await ptp.ensure_paths(db, DAY, T(15, 45), fetch=fetch, token_of=lambda e, s: 7)
    assert out[ptp.BASIS_CANDLES] == 1 and calls == [(7, f"{DAY} 09:15:00", f"{DAY} 15:30:00")]
    await ptp.ensure_paths(db, DAY, T(16, 0), fetch=fetch, token_of=lambda e, s: 7)
    assert len(calls) == 1          # candles stored: not read again
    paths = await ptp.load_paths(db, DAY, DAY)
    path = paths[(DAY, "NFO", SYM)]
    assert path["basis"] == ptp.BASIS_CANDLES and path["bars"][1] == (T(10, 1), 100.5, 103.0, 100.0, 102.0)


@pytest.mark.asyncio
async def test_a_contract_without_candles_keeps_prints_and_is_retried(monkeypatch):
    db = settings.DB_PATH
    await _traded(db)

    async def failing(token, start, end):
        raise RuntimeError("provider down")

    async def prints(db_path, day, contract):
        return [(f"{day} 10:00:00", 100.0, 100.0, 100.0, 100.0)]

    monkeypatch.setattr(ptp, "stored_prints", prints)
    out = await ptp.ensure_paths(db, DAY, T(15, 45), fetch=failing, token_of=lambda e, s: 7)
    assert out[ptp.BASIS_PRINTS] == 1
    assert (await ptp.load_paths(db, DAY, DAY))[(DAY, "NFO", SYM)]["basis"] == ptp.BASIS_PRINTS

    async def works(token, start, end):
        return [(f"{DAY} 10:00:00", 100, 101, 99, 100.5)]

    out = await ptp.ensure_paths(db, DAY, T(16, 0), fetch=works, token_of=lambda e, s: 7)
    assert out[ptp.BASIS_CANDLES] == 1
    out = await ptp.ensure_paths(db, DAY, T(16, 5), fetch=works, token_of=lambda e, s: None)
    assert out == {"status": "ok", "contracts": 1, ptp.BASIS_CANDLES: 0, ptp.BASIS_PRINTS: 0, "missing": 0}


@pytest.mark.asyncio
async def test_the_path_reads_stop_at_their_budget():
    db = settings.DB_PATH
    await _traded(db)

    async def slow(token, start, end):
        await asyncio.sleep(5)
        return []

    out = await ptp.ensure_paths(db, DAY, T(15, 45), fetch=slow, token_of=lambda e, s: 7, budget_sec=0.05)
    assert out["status"] == "budget_spent"


# ---------------------------------------------------------------------------
# the evening review link
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_every_trading_day_ends_with_one_review_link(kite, partner_chat):  # noqa: F811
    from partner_orchestrator import init_partner_db
    db = settings.DB_PATH
    await init_partner_db(db)
    # A login held since the morning and no trades: no coach note, so the prompt goes out.
    await zerodha.create_session("reqtok12", T(9, 0))
    assert (await zerodha.partner_broker_eod(T(15, 40)))["status"] == "synced"
    assert (await pc.partner_coach_eod(T(15, 40)))["note"] == "no_reported_trades"
    assert (await zerodha.ensure_review_message(T(15, 40)))["status"] == "prompted"
    [(kind, text, markup)] = partner_chat
    assert kind == "zerodha_prompt" and text.startswith("📒 Review your day (Mon 19 Oct)\n") and "read-only" in text
    assert markup["inline_keyboard"][0][0]["url"] == zerodha.login_url()
    assert (await zerodha.ensure_review_message(T(15, 41)))["status"] == "already_prompted"


@pytest.mark.asyncio
async def test_the_coach_note_is_the_review_link_when_it_went_out(kite, partner_chat):  # noqa: F811
    from partner_orchestrator import init_partner_db
    db = settings.DB_PATH
    await init_partner_db(db)
    await _seed(db)
    kite["orders"] = [_order("O1", "BUY", 20, T(12, 9, 5)), _order("O2", "SELL", 20, T(15, 11))]
    kite["trades"] = [_trade("O1", 20, 518.0, T(12, 9, 10)), _trade("O2", 20, 640.0, T(15, 11, 2))]
    await zerodha.create_session("reqtok12", T(9, 0))
    await zerodha.partner_broker_eod(T(15, 40))
    assert (await pc.partner_coach_eod(T(15, 40)))["note"] == "sent"
    assert (await zerodha.ensure_review_message(T(15, 40)))["status"] == "coach_note_sent"
    assert [kind for kind, _, _ in partner_chat] == ["coach"]


def test_the_wrap_sends_the_brief_then_the_review_link():
    import inspect
    import partner_orchestrator as po
    source = inspect.getsource(po.partner_eod_wrap)
    assert source.index("partner_broker_eod") < source.index("partner_coach_eod") < source.index("ensure_review_message")
    assert source.index('send_partner(msg, kind="eod")') < source.index("partner_broker_eod")


# ---------------------------------------------------------------------------
# end to end: a read with details and paths reaches the review
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_login_reads_details_and_paths_and_the_review_shows_them(kite, partner_chat, monkeypatch):  # noqa: F811
    from partner_orchestrator import init_partner_db
    db = settings.DB_PATH
    await init_partner_db(db)
    await _seed(db)
    kite["orders"] = [_order("251019000000021", "BUY", 20, T(12, 9, 5), modified=True),
                      _order("251019000000022", "SELL", 20, T(15, 11), modified=False)]
    kite["trades"] = [_trade("251019000000021", 20, 518.0, T(12, 9, 10)),
                      _trade("251019000000022", 20, 640.0, T(15, 11, 2))]
    kite["histories"] = {"251019000000021": [
        {"status": "OPEN", "price": 515, "order_timestamp": "2026-10-19 12:08:40"},
        {"status": "OPEN", "price": 518, "order_timestamp": "2026-10-19 12:09:00"},
        {"status": "COMPLETE", "price": 518, "order_timestamp": "2026-10-19 12:09:10"}]}
    kite["margins"] = {"available": {"opening_balance": 200000}}
    bars = candles((11, 50), [510.0] * 20 + ramp(510, 650, 200))
    monkeypatch.setattr(ptp, "contract_token", lambda exchange, symbol: 99)

    async def minutes(token, start, end):
        return [(b[0].strftime("%Y-%m-%d %H:%M:%S"), *b[1:]) for b in bars]

    monkeypatch.setattr(ptp, "kite_minutes", minutes)
    await zerodha.on_login("reqtok12", T(15, 52))
    result = await zerodha.wait_review_sync()
    assert result["note"] == "sent" and result["paths"][DAY][ptp.BASIS_CANDLES] == 1
    assert result["details"]["histories"] == 1 and result["details"]["account"] is True
    view = await pc.load_partner_coach(db, days=3, now=T(16, 0))
    item = view["days"][0]["cards"][0]
    assert item["insight"]["basis"] == ptp.BASIS_CANDLES and item["insight"]["risk"]["cash"] == 200000.0
    assert ("12:09", "You raised your buy price from ₹515 to ₹518") in [(e["at"], e["text"])
                                                                       for e in item["insight"]["events"]]
    review = pl.day_review(view, DAY)
    assert review["account"]["cash"] == 200000.0 and review["score"]["of"] >= 6
    assert review["trades"][0]["chart"]["points"]
    json.dumps(review)
    async with aiosqlite.connect(db) as conn:
        assert (await (await conn.execute("SELECT COUNT(*) FROM partner_trade_paths")).fetchone())[0] == 1


# ---------------------------------------------------------------------------
# round trips: a re-buy after a full exit is a new trade
# ---------------------------------------------------------------------------

def _row(action, minute, lots=1):
    return {"action": action, "lots": lots, "trade_at": T(10, minute).isoformat(), "report_id": minute}


def test_fills_split_where_the_position_is_flat_again():
    trips = pc.round_trips
    b1, s1, b2, s2 = _row("BUY", 1), _row("SELL", 2), _row("BUY", 3), _row("SELL", 4)
    assert trips([b1, s1, b2, s2]) == [[b1, s1], [b2, s2]]
    # Scaling in and out of one position stays one trade.
    scale = [_row("BUY", 1, 2), _row("SELL", 2, 1), _row("BUY", 3, 1), _row("SELL", 4, 2)]
    assert trips(scale) == [scale]
    # A sale with nothing bought before it (an earlier day's position) is kept apart, last.
    stray = _row("SELL", 0)
    assert trips([stray, b1, s1]) == [[b1, s1], [stray]]
    skip = _row("SKIP", 0, None)
    assert trips([skip]) == [[skip]] and trips([skip, b1, s1]) == [[skip, b1, s1]]
    assert trips([b1, _row("SELL", 2, None), b2]) == [[b1, _row("SELL", 2, None)], [b2]]


def test_a_rebuy_of_the_card_option_after_a_stop_out_is_a_reentry_not_averaging_down():
    from tests.test_partner_coach import FALLING
    reports = [_zr("BUY", T(12, 9), 518.0), _zr("SELL", T(12, 56), 430.0),
               _zr("BUY", T(13, 5), 420.0), _zr("SELL", T(13, 40), 400.0)]
    view = _view([_card(series=FALLING)], reports)
    first, again = view["days"][0]["cards"]
    assert "AVERAGED_DOWN" not in codes(first) and first["partner"]["avg_entry"] == 518.0
    assert again["reentry"] is True and again["time"] == "13:05" and again["advisory_id"] == "c1"
    assert {"QUICK_REENTRY_AFTER_LOSS", "LATE_ENTRY", "ENTRY_UNDER_STOP"} <= set(codes(again))
    assert again["partner"]["pnl"] == _net(420.0, 400.0, 20)
    # Bought at ₹420 under the card's ₹464.7 SL: the card's exits do not apply (no "sell at the SL" advice).
    under = flag(again, "ENTRY_UNDER_STOP")
    assert under["reason"] == "You bought at ₹420 at 13:05; the card's SL was ₹464.7, so the card's idea had already failed."
    assert under["better"] == f"No trade: ₹0 instead of {rs(_net(420.0, 400.0, 20))}."
    assert "HELD_PAST_STOP" not in codes(again) and again["plan"]["pnl"] == 0.0 and again["same_entry"] is None
    summary = view["summary"]
    assert (summary["cards_bought"], summary["card_reentries"], summary["trades_scored"]) == (1, 1, 2)
    review = pl.day_review(view, DAY)
    assert [(t["time"], t["reentry"]) for t in review["trades"]] == [("12:07", False), ("13:05", True)]
    # The re-entry's story starts with the card at its own time and never says the option "reached" the SL.
    timeline = review["trades"][1]["timeline"]
    assert timeline[0]["at"] == "12:07" and timeline[0]["who"] == "card"
    assert not any("reached the card's SL" in e["text"] for e in timeline)
    # "Only the card trades" means the card's own trade, not the re-buy.
    view = _view([_card(series=FALLING)], reports + [_zr("BUY", T(14, 0), 100.0, **OFF), _zr("SELL", T(14, 10), 90.0, **OFF)])
    [over] = view["days"][0]["day_flags"]
    assert over["code"] == "OVERTRADING" and over["better_pnl"] == _net(518.0, 430.0, 20)


def test_risk_on_a_card_trade_with_unknown_stops_is_to_the_card_sl():
    item = _item(_view([_card()], [_zr("BUY", T(12, 9), 518.0), _zr("SELL", T(13, 3), 598.0)],
                       context={"accounts": _cash(60000.0)}))
    assert item["insight"]["risk"] == {"rs": round((518.0 - 464.7) * 20, 2), "pct_of_cash": round(1066 / 60000, 4),
                                       "basis": "CARD_SL", "cash": 60000.0, "trigger": 464.7}
    assert "BIG_RISK" not in codes(item)
    story = pl.day_review(_view([_card()], [_zr("BUY", T(12, 9), 518.0), _zr("SELL", T(13, 3), 598.0)],
                                context={"accounts": _cash(60000.0)}), DAY)["trades"][0]
    assert "At risk: ₹1,066 to the card's stop, 2% of your cash today." in story["option_lines"]


def test_the_lesson_tells_at_most_three_other_mistakes_and_keeps_the_rest_as_lessons():
    reports = [off("BUY", T(10, 30, 20), 131.0, lots=2, order_id="2001"), off("SELL", T(10, 46, 5), 110.0, lots=2)]
    context = ctx(SPIKE, accounts=_cash(60000.0), orders=[_sl("2002", T(10, 31), 105.0, status="CANCELLED")],
                  changes={"2002": [_change("2002", T(10, 38), "trigger_price", 120.0, 105.0)],
                           "2001": [_change("2001", T(10, 30, 5), "price", 126.0, 129.0),
                                    _change("2001", T(10, 30, 15), "price", 129.0, 131.0, seq=1)]})
    review = pl.day_review(_view([], reports, context=context), DAY)
    lesson = review["lesson"]
    assert lesson["code"] == "OFF_CARD"
    assert [a["code"] for a in lesson["also"]] == ["STOP_LOWERED", "BIG_RISK", "CHASED_SPIKE"]
    assert [m["code"] for m in review["more_lessons"]] == ["PRICE_RAISED_TO_FILL"]
    # Same-minute events read in the order they happened: two raises, then the fill.
    timeline = [e["text"] for e in review["trades"][0]["timeline"]]
    assert timeline[:3] == ["You raised your buy price from ₹126 to ₹129", "You raised your buy price from ₹129 to ₹131",
                            "You bought 2 lots at ₹131"]
    assert all("sort_key" not in e for e in review["trades"][0]["timeline"])


def test_a_short_hold_gets_no_price_from_outside_the_holding():
    """[A22-P5] The audit's case: held 10:00:40-10:00:50. The 10:00 candle's
    high and low may have come before the buy or after the sale, so they are
    never "best" or "worst while you held"; they are shown apart, uncertain."""
    bars = [(T(10, 0), 100.0, 140.0, 90.0, 100.0)] + [
        (T(10, m), 100.0, 101.0, 99.0, 100.0) for m in range(1, 30)]
    view = _view([], [off("BUY", T(10, 0, 40), 100.0), off("SELL", T(10, 0, 50), 101.0)], context=ctx(bars))
    insight = off_item(view)["insight"]
    assert "best" not in insight and "worst" not in insight
    assert insight["edge"] == {"high": 140.0, "low": 90.0, "uncertain": True}
    assert ("In the minute you bought or sold it also traded at ₹90–₹140; that may have been before your buy or "
            "after your sale.") in pl.option_lines(insight)


def test_best_and_worst_while_held_come_from_whole_minutes_only():
    # Bought 10:00:40, sold 10:05:10. Whole minutes 10:01-10:04 ran 100-110; the 10:00 spike to 140
    # and the 10:05 drop to 80 sit in the buy and sale minutes.
    bars = ([(T(10, 0), 100.0, 140.0, 90.0, 100.0)]
            + [(T(10, m), 100.0 + m, 102.0 + 2 * m, 99.0 + m, 101.0 + m) for m in range(1, 5)]
            + [(T(10, 5), 105.0, 106.0, 80.0, 82.0)] + [(T(10, m), 82.0, 83.0, 81.0, 82.0) for m in range(6, 40)])
    view = _view([], [off("BUY", T(10, 0, 40), 100.0), off("SELL", T(10, 5, 10), 104.0)], context=ctx(bars))
    insight = off_item(view)["insight"]
    assert (insight["best"]["price"], insight["best"]["at"]) == (110.0, "10:04")
    assert (insight["worst"]["price"], insight["worst"]["at"]) == (100.0, "10:01")
    assert insight["edge"] == {"high": 140.0, "low": 80.0, "uncertain": True}
