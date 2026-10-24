"""[O21-PC / O21-PL] Partner coach: the card's plan, each mistake explained
(what happened, why it matters, the better action and what it would have
paid, the rule), the stop-discipline checks and the loader.

Every rupee figure is recomputed here from prices with the same charges
schedule, so a wording or arithmetic slip fails a test."""
import json
from datetime import datetime, timedelta

import aiosqlite
import pytest
import pytz

import partner_coach as pc
import partner_fill_capture as pfc
from config import settings

IST = pytz.timezone("Asia/Kolkata")
DAY = "2026-10-19"
SYMBOL = "SENSEX26O2274200PE"
rs = pc._rs


def T(h, m, s=0, day=19):
    return IST.localize(datetime(2026, 10, day, h, m, s))


def _series(points: dict, day=19) -> list:
    """{(h, m): ltp} -> sorted 5-minute prints."""
    return sorted((T(h, m, day=day), float(p)) for (h, m), p in points.items())


RISING = _series({(12, 10): 516, (12, 15): 520, (12, 20): 520, (12, 30): 540, (12, 45): 560, (13, 0): 590,
                  (13, 5): 600, (13, 30): 610, (14, 0): 560, (15, 10): 550, (15, 15): 548})
FALLING = _series({(12, 10): 540, (12, 15): 530, (12, 25): 500, (12, 40): 460, (12, 55): 430, (13, 10): 420,
                   (15, 15): 400})


def _card(advisory_id="c1", series=RISING, updates=(), **over):
    card = dict(advisory_id=advisory_id, underlying="SENSEX", day=DAY, delivered_at=T(12, 7), direction="SHORT",
                option="SENSEX 74200 PE", strike=74200.0, opt_type="PE", expiry="2026-10-22", lot_size=20,
                exchange="BFO", tick_size=0.05, ask=514.8, buy_limit=522.35, sl_premium=464.7,
                target_premium=667.3, target_low=567.2, fill_by=T(12, 16, 50), exit_by=T(15, 15),
                updates=[{"event_type": e, "delivered_at": at} for e, at in updates], series=list(series))
    card.update(over)
    return card


_ids = iter(range(1, 10_000))


def _rep(action, at, price, lots=1, advisory="c1", **over):
    row = {"report_id": next(_ids), "status": "ACTIVE", "action": action, "trade_at": at.isoformat(),
           "price": price, "lots": lots, "lot_size": 20, "advisory_id": advisory, "session_date": at.date().isoformat(),
           "underlying": "SENSEX", "strike": 74200.0, "opt_type": "PE", "tradingsymbol": SYMBOL,
           "exchange": "BFO", "price_basis": "PARTNER_STATED", "source": "TELEGRAM_TEXT", "trade_at_basis": "STATED"}
    row.update(over)
    return row


def _zr(action, at, price, **over):
    """A Zerodha fill."""
    return _rep(action, at, price, **({"source": "ZERODHA", "price_basis": "BROKER_FILL",
                                       "trade_at_basis": "EXCHANGE_FILL"} | over))


def _stop(trigger, status, placed, updated=None, kind="SL_ORDER", symbol=SYMBOL):
    return {"source_id": f"s{next(_ids)}", "session_date": placed.date().isoformat(), "kind": kind,
            "exchange": "BFO", "tradingsymbol": symbol, "trigger_price": trigger, "quantity": 20,
            "status": status, "placed_at": placed.isoformat(), "updated_at": (updated or placed).isoformat()}


def _net(entry, exit_, qty, exchange="BFO", orders=2):
    return round((exit_ - entry) * qty - pc.round_trip_costs(entry, exit_, qty, exchange, orders=orders), 2)


def amt(value):
    return f"₹{abs(value):,.0f}"


def _view(cards, reports, now=T(16, 0), **kw):
    return pc.analyse(cards, reports, reaction_sec=120, now=now, **kw)


def _item(view, advisory_id="c1"):
    return next(i for row in view["days"] for i in row["cards"] if i["advisory_id"] == advisory_id)


def _codes(item):
    return [f["code"] for f in item["flags"]]


def _flags(item):
    return {f["code"]: f for f in item["flags"]}


# ---------------------------------------------------------------------------
# the plan and the good habits
# ---------------------------------------------------------------------------

def test_a_followed_card_scores_both_sides_and_earns_positives():
    card = _card(updates=[("TARGET_ZONE", T(13, 0))])
    view = _view([card], [_rep("BUY", T(12, 9), 518.0), _rep("SELL", T(13, 3), 598.0)])
    item = _item(view)
    assert _codes(item) == []
    assert {p["code"] for p in item["positives"]} == {"BOUGHT_IN_LIMIT", "EXITED_WITH_CARD"}
    # The card's exit is the first 5-minute print 2 minutes after the target message: 13:05 = 600.
    assert item["plan"]["exit"] == 600.0 and item["plan"]["exit_reason"] == "TARGET_MESSAGE"
    assert item["plan"]["pnl"] == _net(518.0, 600.0, 20)
    assert item["partner"]["pnl"] == _net(518.0, 598.0, 20)
    summary = view["summary"]
    assert summary["followed_cards"] == 1 and summary["gap_vs_plan"] == round(_net(518, 598, 20) - _net(518, 600, 20), 2)


def test_rupees_read_plainly():
    assert (rs(1240.4), rs(-1094), rs(0.0), rs(0.4), rs(None)) == ("+₹1,240", "−₹1,094", "₹0", "₹0", "n/a")


# ---------------------------------------------------------------------------
# entries
# ---------------------------------------------------------------------------

def test_a_chased_entry_shows_the_extra_risk_and_the_better_action():
    view = _view([_card(series=FALLING)], [_rep("BUY", T(12, 10), 540.0), _rep("SELL", T(12, 56), 430.0)])
    item = _item(view)
    assert _codes(item) == ["ENTRY_ABOVE_LIMIT", "HELD_PAST_STOP"]
    actual = _net(540.0, 430.0, 20)
    chase = _flags(item)["ENTRY_ABOVE_LIMIT"]
    assert chase["title"] == "Chased the entry (FOMO)"
    assert chase["reason"] == "The card said buy up to ₹522.35. You paid ₹540 at 12:10, ₹17.65 (3.4%) more."
    # Risk to the stop: (540 - 464.7) x 20 = 1,506 against (522.35 - 464.7) x 20 = 1,153 -> 31% more.
    assert chase["why"] == ("The stop stays at ₹464.7, so a stop-out loses ₹1,506 instead of ₹1,153 on 20 qty "
                            "(31% more), while the first target ₹567.2 is ₹27.2 away instead of ₹44.85.")
    assert chase["better"] == f"Skip it, as the card says above the limit: ₹0 instead of {rs(actual)}."
    assert (chase["better_pnl"], chase["actual_pnl"], chase["impact_rs"]) == (0.0, actual, actual)
    assert chase["advice"].startswith("Above the buy-up-to price, skip.")
    # Chasing above the limit was a skip on the card: plan ₹0.
    assert item["plan"]["pnl"] == 0.0 and "price above the limit" in item["plan"]["note"]


def test_waiting_is_offered_when_the_price_came_back_and_a_lucky_chase_is_still_named():
    back = _series({(12, 10): 540, (12, 15): 518, (12, 20): 530, (12, 30): 560, (12, 45): 580, (15, 15): 560})
    view = _view([_card(series=back)], [_rep("BUY", T(12, 10, 30), 540.0), _rep("SELL", T(12, 30), 560.0)])
    item = _item(view)
    assert _codes(item) == ["ENTRY_ABOVE_LIMIT"]
    actual = _net(540.0, 560.0, 20)
    assert actual > 0
    chase = item["flags"][0]
    assert chase["better"] == (f"Skip it, as the card says above the limit: ₹0 instead of {rs(actual)}. Or wait with "
                               f"a limit order at ₹522.35: the option traded at ₹518 at 12:15, before the "
                               f"skip-after time.")
    assert chase["why"].endswith(f"It made {rs(actual)} this time; the rule is about the risk taken, not about "
                                 f"this result.")


def test_a_late_entry_that_made_money_is_still_a_lesson():
    card = _card(updates=[("TARGET_ZONE", T(13, 0))])
    item = _item(_view([card], [_rep("BUY", T(12, 25), 520.0), _rep("SELL", T(13, 3), 598.0)]))
    assert _codes(item) == ["LATE_ENTRY"]
    actual = _net(520.0, 598.0, 20)
    late = item["flags"][0]
    assert late["reason"] == "The card's skip-after time was 12:16. You bought at 12:25, 8 min later."
    assert late["why"] == ("The card's price, stop and target were set for an entry by 12:16. At 12:25 the option "
                           "was ₹520 against the card's ₹514.8, so the plan no longer fitted the price. "
                           f"It made {rs(actual)} this time; the rule is about the risk taken, not about this result.")
    assert late["better"] == f"Let it go: ₹0 instead of {rs(actual)}."
    assert late["impact_rs"] == actual > 0
    assert [p["code"] for p in item["positives"]] == ["EXITED_WITH_CARD"]


def test_buying_after_the_card_closed_says_which_message_ended_it():
    failed = _item(_view([_card(series=FALLING, updates=[("INVALIDATION", T(12, 30))])],
                         [_rep("BUY", T(12, 40), 460.0)]))
    flag = _flags(failed)["AFTER_CARD_CLOSED"]
    assert flag["reason"] == "You bought at 12:40; the card's exit message came at 12:30."
    assert flag["why"].startswith("An exit message means the card's idea failed")
    done = _item(_view([_card(updates=[("TARGET_ZONE", T(13, 0))])], [_rep("BUY", T(13, 10), 600.0)]))
    flag = _flags(done)["AFTER_CARD_CLOSED"]
    assert flag["reason"] == "You bought at 13:10; the card's target message came at 13:00."
    assert flag["why"].startswith("A target message means the planned move is mostly done")


def test_a_card_whose_stop_was_already_hit_is_a_skip_on_the_card():
    late_card = _card("c2", series=FALLING, delivered_at=T(13, 0), fill_by=T(13, 10))
    item = _item(_view([late_card], [], ), "c2")
    assert item["plan"]["pnl"] == 0.0
    assert item["plan"]["note"] == "card said skip: print ₹420 at 13:10 was already at or under the SL ₹464.7"


# ---------------------------------------------------------------------------
# after a loss
# ---------------------------------------------------------------------------

OFF = dict(advisory=None, underlying="NIFTY", strike=22950.0, opt_type="PE", lot_size=75, exchange="NFO",
           tradingsymbol="NIFTY26O2022950PE")


def test_revenge_reentry_and_size_up_explain_what_they_cost():
    reports = [_rep("BUY", T(12, 10), 540.0), _rep("SELL", T(12, 56), 430.0),
               _rep("BUY", T(13, 5), 100.0, lots=2, **OFF), _rep("SELL", T(13, 40), 80.0, lots=2, **OFF)]
    view = _view([_card(series=FALLING)], reports)
    [off_item] = view["days"][0]["off_card"]
    assert _codes(off_item) == ["OFF_CARD", "QUICK_REENTRY_AFTER_LOSS", "SIZE_UP_AFTER_LOSS"]
    prev, off = _net(540.0, 430.0, 20), _net(100.0, 80.0, 150, "NFO")
    flags = _flags(off_item)
    revenge = flags["QUICK_REENTRY_AFTER_LOSS"]
    assert revenge["reason"] == (f"You closed SENSEX 74200 PE at 12:56 for {rs(prev)} and bought NIFTY 22950 PE "
                                 f"9 min later (without a card, with 2 lots after 1).")
    assert revenge["why"] == ("A buy straight after a loss is the revenge pattern: the aim is to win the money back "
                              f"quickly, not to follow a setup. This trade lost {amt(off)}, so the two trades "
                              f"together came to {rs(prev + off)}.")
    assert revenge["better"] == f"Pause 30 minutes and wait for the next card. Without this trade: ₹0 instead of {rs(off)}."
    assert revenge["impact_rs"] == off
    size = flags["SIZE_UP_AFTER_LOSS"]
    same = _net(100.0, 80.0, 75, "NFO")
    assert size["reason"] == f"2 lots right after a {rs(prev)} trade with 1."
    assert size["why"] == ("Each ₹1 move in the option was ₹150 instead of ₹75. A bigger size after a loss makes the "
                           "next loss bigger too.")
    assert size["better"] == f"The same 1 lot: {rs(same)} instead of {rs(off)}."
    assert size["impact_rs"] == round(off - same, 2)
    no_card = flags["OFF_CARD"]
    assert no_card["reason"] == "You bought NIFTY 22950 PE at 13:05 without a card."
    assert no_card["better"] == f"No trade: ₹0 instead of {rs(off)}."
    assert off_item["partner"]["pnl"] == off
    assert view["leaks"][0]["code"] in ("OFF_CARD", "QUICK_REENTRY_AFTER_LOSS")


def test_a_pause_after_a_loss_before_the_next_card_is_praised():
    later = _series({(13, 35): 500, (13, 40): 505, (14, 0): 520, (15, 15): 530})
    c2 = _card("c2", series=later, delivered_at=T(13, 30), fill_by=T(13, 40))
    reports = [_rep("BUY", T(12, 10), 540.0), _rep("SELL", T(12, 56), 430.0),
               _rep("BUY", T(13, 35), 500.0, advisory="c2"), _rep("SELL", T(14, 0), 520.0, advisory="c2")]
    item = _item(_view([_card(series=FALLING), c2], reports), "c2")
    assert _codes(item) == []
    pause = next(p for p in item["positives"] if p["code"] == "PAUSED_AFTER_LOSS")
    assert pause["reason"] == f"After the {rs(_net(540.0, 430.0, 20))} exit at 12:56 you waited 39 min and took a card."


# ---------------------------------------------------------------------------
# exits
# ---------------------------------------------------------------------------

def test_early_exit_and_giving_back_after_target_are_priced_against_the_card():
    card = _card(updates=[("TARGET_ZONE", T(13, 0))])
    early = _item(_view([card], [_rep("BUY", T(12, 9), 518.0), _rep("SELL", T(12, 20), 520.0)]))
    [flag] = early["flags"]
    actual, held = _net(518.0, 520.0, 20), _net(518.0, 600.0, 20)
    assert flag["code"] == "EARLY_EXIT"
    assert flag["reason"] == "You sold at 12:20 for ₹520. The card's target message came at 13:00 with the option at ₹600."
    assert flag["better"] == (f"Holding with the SL order in place until the card's target message: {rs(held)} "
                              f"instead of {rs(actual)}.")
    assert flag["impact_rs"] == round(actual - held, 2)
    late = _item(_view([card], [_rep("BUY", T(12, 9), 518.0), _rep("SELL", T(14, 0), 540.0)]))
    [flag] = late["flags"]
    actual, booked = _net(518.0, 540.0, 20), _net(518.0, 600.0, 20)
    assert flag["code"] == "GAVE_BACK_AFTER_TARGET"
    assert flag["reason"] == "The target message came at 13:00 with the option at ₹600. You sold at 14:00 for ₹540."
    assert flag["better"].startswith(f"Booking at the message: {rs(booked)} instead of {rs(actual)}.")
    assert flag["impact_rs"] == round(actual - booked, 2)


def test_late_entry_averaging_down_holding_past_stop_and_square_off():
    card = _card(series=FALLING)
    item = _item(_view([card], [_rep("BUY", T(12, 25), 500.0), _rep("BUY", T(12, 40), 460.0),
                                _rep("SELL", T(15, 25), 400.0, lots=2)]))
    assert _codes(item) == ["LATE_ENTRY", "AVERAGED_DOWN", "HELD_PAST_STOP", "HELD_PAST_SQUARE_OFF"]
    assert item["plan"]["pnl"] == 0.0
    # Three orders: the extra one pays its flat ₹20 + GST.
    actual = _net(480.0, 400.0, 40, orders=3)
    assert item["partner"]["pnl"] == actual
    flags = _flags(item)
    added = flags["AVERAGED_DOWN"]
    only_first = _net(500.0, 400.0, 20)
    assert added["reason"] == "First buy ₹500 at 12:25; you added at ₹460 at 12:40, 8.0% lower."
    assert added["why"] == ("Adding to a falling option raises the size exactly when the trade is going wrong: 40 qty "
                            "were exposed instead of 20. The card's stop at ₹464.7 was the plan for a fall.")
    assert added["better"] == f"Only the first buy: {rs(only_first)} instead of {rs(actual)}."
    assert added["impact_rs"] == round(actual - only_first, 2)
    held = flags["HELD_PAST_STOP"]
    at_sl = _net(480.0, 464.7, 40, orders=3)        # the same three orders, sold at the SL
    assert held["reason"] == ("The card's SL was ₹464.7. You sold at ₹400 at 15:25; the option was under the SL by "
                              "12:40 (5-minute print ₹460).")
    assert held["impact_rs"] == round(actual - at_sl, 2)
    late_out = flags["HELD_PAST_SQUARE_OFF"]
    # The 15:15 print was also ₹400: no rupee effect this time, so no "instead of".
    assert late_out["reason"] == "Exit-by was 15:15; you sold at 15:25."
    assert late_out["better"] == "Be out by 15:15." and late_out["impact_rs"] == 0.0


def test_overtrading_counts_charges_and_the_cards_only_day():
    reports = []
    for n, (h, m) in enumerate(((12, 10), (12, 30), (13, 0), (13, 30))):
        off = OFF | {"strike": 22900.0 + 50 * n, "tradingsymbol": f"NIFTY26O20{22900 + 50 * n}CE", "opt_type": "CE"}
        reports += [_rep("BUY", T(h, m), 100.0, **off), _rep("SELL", T(h, m + 10), 104.0, **off)]
    view = _view([_card()], reports)
    [flag] = view["days"][0]["day_flags"]
    each = _net(100.0, 104.0, 75, "NFO")
    charges = 4 * (4 * 75 - each)
    assert flag["code"] == "OVERTRADING" and flag["reason"] == "4 buys against 1 card."
    assert flag["why"].startswith(f"Extra trades come from watching the screen rather than from a setup; today's "
                                  f"trades paid {amt(charges)} in charges.")
    assert flag["better"] == f"Only the card trades: ₹0 instead of {rs(round(4 * each, 2))}."
    assert flag["impact_rs"] == round(4 * each, 2)


def test_unreported_card_and_exit_without_buy_are_data_gaps_not_flags():
    card = _card(updates=[("TARGET_ZONE", T(13, 0))])
    item = _item(_view([card], []))
    assert item["partner"]["status"] == "NOT_REPORTED" and item["flags"] == []
    assert item["plan"]["entry"] == 516.0 and item["plan"]["pnl"] == _net(516.0, 600.0, 20)
    view = _view([card], [_rep("SELL", T(13, 3), 598.0, lots=None)])
    item = _item(view)
    assert item["partner"]["status"] == "EXIT_ONLY" and "buy price not reported" in item["plan"]["note"]
    assert view["data_quality"]["exits_without_buy"] == 1


def test_a_skipped_card_that_stopped_out_shows_the_saving():
    view = _view([_card(series=FALLING)], [_rep("SKIP", T(12, 8), None, lots=None)])
    item = _item(view)
    assert item["partner"]["status"] == "SKIPPED"
    # Following it: the print at 12:09 + 2 min is 12:10 = 540, above the 522.35 limit -> the card said skip.
    assert item["plan"]["pnl"] == 0.0 and "above the buy-up-to" in item["plan"]["note"]
    lower = _card(series=_series({(12, 10): 518, (12, 25): 500, (12, 40): 460, (15, 15): 400}))
    item = _item(_view([lower], [_rep("SKIP", T(12, 8), None, lots=None)]))
    assert item["plan"]["pnl"] == _net(518.0, 464.7, 20) < 0
    assert [p["code"] for p in item["positives"]] == ["SKIP_SAVED"]


# ---------------------------------------------------------------------------
# stop discipline (Zerodha days only)
# ---------------------------------------------------------------------------

KNOWN = frozenset({DAY})
STOPPED_OUT = [_zr("BUY", T(12, 9), 518.0), _zr("SELL", T(12, 56), 430.0)]


def test_no_stop_order_is_flagged_only_when_the_day_is_known():
    item = _item(_view([_card(series=FALLING)], STOPPED_OUT, stops=[], stops_known_days=KNOWN))
    flag = _flags(item)["NO_STOP_ORDER"]
    assert flag["reason"] == ("You bought at 12:09 and held 47 min with no stop-loss order in Zerodha (no SL order or "
                              "GTT on this option).")
    assert flag["better"] == "Place an SL order at the card's ₹464.7 right after the buy fills."
    assert flag["impact_rs"] is None and item["stops"] == []
    # Taps (no Zerodha) or a day whose GTTs could not be read: nothing is said about stops.
    assert "NO_STOP_ORDER" not in _codes(_item(_view([_card(series=FALLING)], STOPPED_OUT, stops=[])))
    # A trade held under five minutes is not flagged.
    quick = [_zr("BUY", T(12, 9), 518.0), _zr("SELL", T(12, 12), 520.0)]
    assert "NO_STOP_ORDER" not in _codes(_item(_view([_card()], quick, stops=[], stops_known_days=KNOWN)))


def test_stops_on_another_option_or_before_the_buy_do_not_count():
    stops = [_stop(465.0, "PENDING", T(12, 15), symbol="NIFTY26O2022950PE"), _stop(465.0, "CANCELLED", T(11, 0))]
    item = _item(_view([_card(series=FALLING)], STOPPED_OUT, stops=stops, stops_known_days=KNOWN))
    assert "NO_STOP_ORDER" in _codes(item)


def test_a_gtt_stop_counts_and_is_praised():
    card = _card(updates=[("TARGET_ZONE", T(13, 0))])
    trades = [_zr("BUY", T(12, 9), 518.0), _zr("SELL", T(13, 3), 598.0)]
    item = _item(_view([card], trades, stops=[_stop(465.0, "CANCELLED", T(12, 11), T(13, 3), kind="GTT")],
                       stops_known_days=KNOWN))
    assert item["flags"] == []
    placed = next(p for p in item["positives"] if p["code"] == "STOP_PLACED")
    assert placed["reason"] == "GTT at ₹465 placed 2 min after buying."
    assert item["stops"] == [{"kind": "GTT", "trigger": 465.0, "status": "CANCELLED", "placed": "12:11",
                              "updated": "13:03", "exact": True}]


def test_a_wider_stop_that_fired_is_priced_against_the_card_stop():
    trades = [_zr("BUY", T(12, 9), 518.0), _zr("SELL", T(12, 50), 430.0)]
    item = _item(_view([_card(series=FALLING)], trades, stops=[_stop(430.0, "TRIGGERED", T(12, 10), T(12, 50))],
                       stops_known_days=KNOWN))
    assert _codes(item) == ["HELD_PAST_STOP", "STOP_WIDER_THAN_CARD"]
    wide = _flags(item)["STOP_WIDER_THAN_CARD"]
    actual, at_card = _net(518.0, 430.0, 20), _net(518.0, 464.7, 20)
    assert wide["reason"] == "Your SL order was at ₹430; the card's SL was ₹464.7."
    # (518 - 430) x 20 = 1,760 against (518 - 464.7) x 20 = 1,066.
    assert wide["why"] == "Your stop risked ₹1,760 instead of ₹1,066 on 20 qty. A wider stop is a bigger loss, not a safer trade."
    assert wide["better"] == f"The stop at the card's ₹464.7: {rs(at_card)} instead of {rs(actual)}."
    assert wide["impact_rs"] == round(actual - at_card, 2)
    assert "STOP_PLACED" not in [p["code"] for p in item["positives"]]


def test_a_cancelled_stop_followed_by_a_worse_exit():
    stops = [_stop(465.0, "CANCELLED", T(12, 10), T(12, 38))]
    item = _item(_view([_card(series=FALLING)], STOPPED_OUT, stops=stops, stops_known_days=KNOWN))
    flag = _flags(item)["STOP_CANCELLED"]
    actual, kept = _net(518.0, 430.0, 20), _net(518.0, 465.0, 20)
    assert flag["reason"] == "You cancelled your stop at ₹465 at 12:38 and sold at ₹430 at 12:56."
    assert flag["better"] == f"Leaving it in place: about {rs(kept)} instead of {rs(actual)}."
    assert flag["impact_rs"] == round(actual - kept, 2)
    # Placing it is not praised when it was then cancelled.
    assert "STOP_PLACED" not in [p["code"] for p in item["positives"]]
    # Re-placed after the cancel: protected again, nothing to flag.
    again = stops + [_stop(465.0, "TRIGGERED", T(12, 39), T(12, 56))]
    assert "STOP_CANCELLED" not in _codes(_item(_view([_card(series=FALLING)], STOPPED_OUT, stops=again,
                                                      stops_known_days=KNOWN)))
    # A cancel at 15:16 can be the broker's own square-off: not the partner's choice.
    late = [_zr("BUY", T(12, 9), 518.0), _zr("SELL", T(15, 20), 400.0)]
    stops = [_stop(465.0, "CANCELLED", T(12, 10), T(15, 16))]
    assert "STOP_CANCELLED" not in _codes(_item(_view([_card(series=FALLING)], late, stops=stops,
                                                      stops_known_days=KNOWN)))


def test_off_card_trades_get_the_stop_check_too():
    reports = [_zr("BUY", T(13, 5), 100.0, **OFF), _zr("SELL", T(13, 40), 80.0, **OFF)]
    view = _view([], reports, stops=[], stops_known_days=KNOWN)
    [item] = view["days"][0]["off_card"]
    assert _codes(item) == ["OFF_CARD", "NO_STOP_ORDER"]
    assert _flags(item)["NO_STOP_ORDER"]["better"] == ("Decide the stop before buying and place the SL order right "
                                                        "after the buy fills.")


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loader_uses_delivery_times_and_frozen_paths(monkeypatch):
    import fno_oi_store
    from tests.test_partner_fill_capture import CARD_ID, _seed
    db = settings.DB_PATH
    await _seed(db)
    await fno_oi_store.init_oi_db(db)
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            "INSERT INTO partner_advisory_updates(update_id,advisory_id,event_type,observed_at,observed_underlying,"
            "rendered_update,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            ("upd1", CARD_ID, "TARGET_ZONE", "2026-10-19T15:10:00+05:30", 73901.0, "t", "DELIVERED_ACKNOWLEDGED",
             "x", "x"))
        for hhmm, ltp in (("12:10:00", 516.0), ("15:10:00", 640.0), ("15:15:00", 650.0)):
            await conn.execute(
                "INSERT INTO fno_chain_oi(snap_ts,underlying,expiry,strike,opt_type,oi,volume,ltp,iv) "
                "VALUES(?,?,?,?,?,?,?,?,?)", (f"{DAY} {hhmm}", "SENSEX", "2026-10-22", 74200.0, "PE", 1, 1, ltp, 0.15))
        await conn.commit()
    await pfc.insert_report(db, {"dedup_key": "d1", "source": "DASHBOARD", "received_at": T(12, 9).isoformat(),
                                 "trade_at": T(12, 9).isoformat(), "trade_at_basis": "STATED", "action": "BUY",
                                 "advisory_id": CARD_ID, "session_date": DAY, "underlying": "SENSEX", "lots": 1,
                                 "lot_size": 20, "exchange": "BFO", "price": 518.0, "price_basis": "PARTNER_STATED"})
    view = await pc.load_partner_coach(db, days=3, now=T(16, 0))
    [item] = view["days"][0]["cards"]
    assert item["time"] == "12:06" and item["card_messages"] == [{"type": "TARGET_ZONE", "at": "15:10", "delivered": True}]
    assert item["same_entry"]["exit"] == 650.0      # first print >= 15:10:05 + 120 s
    assert view["data_quality"]["open_without_exit"] == 1
    assert await pc.freeze_card_paths(db, DAY, T(16, 0)) == 1
    async with aiosqlite.connect(db) as conn:
        await conn.execute("DELETE FROM fno_chain_oi")
        await conn.commit()
    again = await pc.load_partner_coach(db, days=3, now=T(16, 0))
    assert again["days"][0]["cards"][0]["same_entry"]["exit"] == 650.0
    assert "tok" not in json.dumps(again["zerodha"])
