"""[O24] The partner's stops as Zerodha's book really shows them, refusals in
plain words, and the 15:40 close.

The shapes are the partner's Oct 23 orders (Production, read-only):
  - a fired stop stays a LIMIT order with its trigger (SELL 22950 CE, trigger
    33, never modified, filled 13:53);
  - a stop turned into a market sale keeps its trigger only in its history
    (SELL 22300 PE: 68 -> 65 -> 60 -> 68 -> ... -> 75 -> 70 -> 65 -> 60,
    then MARKET at 62.6);
  - a second stop for a lot that already had one was refused for margin
    ("Margin required: 159586.95. Margin available: 7536.70").
"""
import aiosqlite
import pytest

import partner_broker_sync as zerodha
import partner_coach as pc
import partner_insights as insights
import partner_lessons as lessons
from config import settings
from tests.test_partner_broker_sync import (OFF_SYMBOL, T, _order, _trade, _ts, kite, partner_app)  # noqa: F401
from tests.test_partner_fill_capture import _seed

DAY = "2026-10-19"


def _history(*states):
    """Kite order history states: (status, order_type, trigger, at)."""
    return [{"status": status, "order_type": kind, "trigger_price": trigger, "price": trigger,
             "order_timestamp": _ts(at), "exchange_update_timestamp": _ts(at)} for status, kind, trigger, at in states]


def _row(order_id, side, status, order_type, *, trigger=0.0, placed, updated=None, modified=0, qty=75,
         filled=None, product="NRML", message=None, history=None):
    """A stored partner_orders row (``history``: the O24 history facts)."""
    row = {"order_id": order_id, "session_date": DAY, "exchange": "NFO", "tradingsymbol": OFF_SYMBOL,
           "transaction_type": side, "order_type": order_type, "product": product, "quantity": qty,
           "filled_quantity": qty if filled is None and status == "COMPLETE" else (filled or 0), "price": 0.0,
           "trigger_price": trigger, "average_price": 0.0, "status": status, "status_message": message,
           "placed_at": placed.isoformat(), "updated_at": (updated or placed).isoformat(), "modified": modified,
           "history_read": 0, "stop_trigger": None, "stop_since": None}
    row.update(history or {})
    return row


def _moves(order_id, *values_at):
    """Stored trigger changes: (old, new, at)."""
    return [{"order_id": order_id, "seq": i, "session_date": DAY, "changed_at": at.isoformat(),
             "field": "trigger_price", "old_value": old, "new_value": new} for i, (old, new, at) in enumerate(values_at)]


# ---------------------------------------------------------------------------
# pure parts
# ---------------------------------------------------------------------------

def test_a_fired_stop_stays_a_stop_whatever_its_type_now():
    orders = [
        _order("F1", "SELL", 75, T(13, 53, 11), symbol=OFF_SYMBOL, exchange="NFO", order_type="LIMIT",
               trigger_price=33.0, price=33.0),                        # an SL that fired (Kite: LIMIT)
        _order("F2", "SELL", 75, T(13, 55), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET",
               trigger_price=31.0),                                    # an SL-M that fired (Kite: MARKET)
        _order("T1", "SELL", 75, T(13, 56), symbol=OFF_SYMBOL, exchange="NFO", order_type="LIMIT", status="OPEN",
               price=60.0),                                            # a target: no trigger
    ]
    stops = zerodha.stops_from_orders(orders, resolve=lambda s, e: {"underlying": "NIFTY"})
    assert [(s["source_id"], s["status"], s["trigger_price"]) for s in stops] == [
        ("kite:F1", "TRIGGERED", 33.0), ("kite:F2", "TRIGGERED", 31.0)]


def test_the_history_gives_the_first_trigger_and_when_it_was_placed():
    converted = _history(("PUT ORDER REQ RECEIVED", "SL", 95.0, T(13, 54, 5)), ("TRIGGER PENDING", "SL", 95.0, T(13, 54, 5)),
                         ("TRIGGER PENDING", "SL", 90.0, T(13, 55, 54)), ("COMPLETE", "MARKET", 0.0, T(14, 2, 29)))
    assert zerodha.history_facts(converted) == {"history_read": 1, "stop_trigger": 95.0,
                                                "stop_since": T(13, 54, 5).isoformat()}
    # A target later turned into a stop: the stop starts when its trigger appears.
    target_then_stop = _history(("OPEN", "LIMIT", 0.0, T(11, 0)), ("TRIGGER PENDING", "SL", 70.0, T(11, 20)))
    assert zerodha.history_facts(target_then_stop)["stop_since"] == T(11, 20).isoformat()
    assert zerodha.history_facts(_history(("OPEN", "LIMIT", 0.0, T(11, 0)), ("COMPLETE", "MARKET", 0.0, T(11, 5)))) \
        == {"history_read": 1, "stop_trigger": None, "stop_since": None}
    assert zerodha.history_facts([])["history_read"] == 0          # an empty history says nothing


def test_order_stop_reads_the_history_and_rebuilds_older_days():
    facts = {"history_read": 1, "stop_trigger": 95.0, "stop_since": T(13, 54, 5).isoformat()}
    converted = zerodha.order_stop(_row("C1", "SELL", "COMPLETE", "MARKET", placed=T(14, 2, 29), modified=1,
                                        history=facts))
    assert (converted["trigger_price"], converted["status"], converted["placed_at"], converted["placed_exact"]) == (
        95.0, "CONVERTED", T(13, 54, 5).isoformat(), True)
    # Stored before O24 (no history facts): the first trigger is the first change's old value, and the
    # earliest stamp seen is when it was in place by.
    legacy = zerodha.order_stop(
        _row("L1", "SELL", "COMPLETE", "MARKET", placed=T(13, 38, 17), modified=1),
        _moves("L1", (68.0, 65.0, T(11, 44, 16)), (65.0, 60.0, T(11, 44, 33)), (60.0, 75.0, T(12, 54))))
    assert (legacy["trigger_price"], legacy["status"], legacy["placed_at"], legacy["placed_exact"]) == (
        68.0, "CONVERTED", T(11, 44, 16).isoformat(), False)
    fired = zerodha.order_stop(_row("L2", "SELL", "COMPLETE", "LIMIT", trigger=33.0, placed=T(13, 53, 11)))
    assert (fired["status"], fired["trigger_price"], fired["placed_exact"]) == ("TRIGGERED", 33.0, False)
    # A modified sale with no trigger in sight may have been a stop or a target.
    assert zerodha.order_stop(_row("L3", "SELL", "COMPLETE", "MARKET", placed=T(11, 18), modified=1)) == zerodha.UNKNOWN
    assert zerodha.order_stop(_row("L4", "SELL", "COMPLETE", "MARKET", placed=T(11, 18))) is None
    assert zerodha.order_stop(_row("B1", "BUY", "COMPLETE", "SL", trigger=40.0, placed=T(11, 0))) is None
    plain = {"history_read": 1, "stop_trigger": None, "stop_since": None}
    assert zerodha.order_stop(_row("P1", "SELL", "COMPLETE", "MARKET", placed=T(11, 18), modified=1,
                                   history=plain)) is None
    # A history that missed the trigger never hides one the book still shows.
    assert zerodha.order_stop(_row("P2", "SELL", "TRIGGER PENDING", "SL", trigger=50.0, placed=T(11, 18),
                                   history=plain))["trigger_price"] == 50.0


def test_merge_takes_sl_stops_from_the_stored_book_and_gtts_from_the_read():
    orders = [_row("O1", "SELL", "COMPLETE", "LIMIT", trigger=33.0, placed=T(13, 53))]
    kept = [{"source_id": "kite:O1", "session_date": DAY, "kind": "SL_ORDER", "exchange": "NFO",
             "tradingsymbol": OFF_SYMBOL, "trigger_price": 33.0, "quantity": 75, "status": "TRIGGERED",
             "placed_at": T(13, 53).isoformat(), "updated_at": T(13, 53).isoformat()},
            {"source_id": "gtt:9", "session_date": DAY, "kind": "GTT", "exchange": "NFO", "tradingsymbol": OFF_SYMBOL,
             "trigger_price": 30.0, "quantity": 75, "status": "PENDING", "placed_at": T(13, 50).isoformat(),
             "updated_at": T(13, 50).isoformat()},
            {"source_id": "kite:X", "session_date": "2026-10-16", "kind": "SL_ORDER", "exchange": "NFO",
             "tradingsymbol": OFF_SYMBOL, "trigger_price": 20.0, "quantity": 75, "status": "CANCELLED",
             "placed_at": T(10, 0, day=16).isoformat(), "updated_at": T(10, 5, day=16).isoformat()}]
    stops, unknown = zerodha.merge_stops(kept, orders, {})
    assert [(s["source_id"], s["placed_exact"]) for s in stops] == [("kite:X", False), ("gtt:9", True),
                                                                    ("kite:O1", False)]
    assert unknown == []


@pytest.mark.parametrize("refused, others, expected", [
    (_row("R1", "BUY", "REJECTED", "LIMIT", placed=T(11, 12, 9), qty=65,
          message="Insufficient funds. Margin required: 8118.50. Margin available: 7536.70. Check orderbook for open orders."),
     [], "the buy needed ₹8,118 and your account had ₹7,537."),
    (_row("R2", "SELL", "REJECTED", "SL", trigger=95.0, placed=T(13, 54, 39), qty=65,
          message="Insufficient funds. Margin required: 159586.95. Margin available: 7536.70. Check orderbook for open orders."),
     [_row("B2", "BUY", "COMPLETE", "MARKET", placed=T(13, 53, 41), qty=65),
      _row("S2", "SELL", "COMPLETE", "MARKET", placed=T(14, 2, 29), qty=65, modified=1)],
     "another sell order for this option was already waiting, so this one would have sold more than the 65 you held: "
     "Zerodha counted it as a new short sale, which needs ₹159,587 of margin; your account had ₹7,537."),
    (_row("R3", "SELL", "REJECTED", "MARKET", placed=T(13, 54), qty=65, product="MIS",
          message="Margin required: 159586.95. Margin available: 7536.70."),
     [_row("B3", "BUY", "COMPLETE", "MARKET", placed=T(13, 53), qty=65)],
     "you bought it as NRML and sold it as MIS, so Zerodha counted the sale as a new short sale, which needs "
     "₹159,587 of margin; your account had ₹7,537."),
    (_row("R4", "SELL", "REJECTED", "MARKET", placed=T(13, 54), qty=130,
          message="Margin required: 159586.95. Margin available: 7536.70."),
     [_row("B4", "BUY", "COMPLETE", "MARKET", placed=T(13, 53), qty=65)],
     "the sale was for 130 and you held 65, so Zerodha counted the extra 65 as a new short sale, which needs "
     "₹159,587 of margin; your account had ₹7,537."),
    (_row("R5", "SELL", "REJECTED", "MARKET", placed=T(13, 54), qty=65,
          message="Margin required: 159586.95. Margin available: 7536.70."),
     [], "you did not hold this option at that moment, so Zerodha counted the sale as a new short sale, which needs "
         "₹159,587 of margin; your account had ₹7,537."),
    (_row("R6", "SELL", "REJECTED", "SL", trigger=120.0, placed=T(13, 54), qty=65,
          message="Trigger price for stoploss sell orders should be lower than the last traded price."), [], None),
])
def test_refusals_read_in_plain_words(refused, others, expected):
    assert insights.refusal_plain(refused, [refused, *others]) == expected


def test_the_day_closes_at_1540():
    assert zerodha.CLOSE_MIN == 15 * 60 + 40 and settings.PARTNER_EOD_MIN == 50
    assert not zerodha._complete(DAY, T(15, 35)) and zerodha._complete(DAY, T(15, 40))
    assert pc._day_close(DAY) == T(15, 40)
    assert lessons.TIME_BUCKETS[-1] == ("13:30–15:40", 810, 940)


# ---------------------------------------------------------------------------
# through the read and the review
# ---------------------------------------------------------------------------

async def _review(db, now=T(16, 0)):
    view = await pc.load_partner_coach(db, days=3, now=now)
    review = lessons.day_review(view, DAY)
    return view, review


def _off_card(view):
    return view["days"][0]["off_card"]


@pytest.mark.asyncio
async def test_a_stop_turned_into_a_sale_and_a_fired_stop_are_read_from_their_histories(kite):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", T(15, 41))
    kite["orders"] = [
        _order("101", "BUY", 75, T(13, 53, 41), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET"),
        # The stop placed at 13:54:05, lowered at 13:55:54, then turned into a market sale (Kite stamps 14:02:29).
        _order("201", "SELL", 75, T(14, 2, 29), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET", modified=True),
        _order("102", "BUY", 75, T(14, 10), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET"),
        # A stop placed at 14:11, never modified, fired at 14:40 (Kite: LIMIT, trigger kept, stamped 14:40).
        _order("202", "SELL", 75, T(14, 40), symbol=OFF_SYMBOL, exchange="NFO", order_type="LIMIT",
               trigger_price=88.0, price=88.0, modified=False),
    ]
    kite["trades"] = [_trade("101", 75, 105.8, T(13, 53, 41)), _trade("201", 75, 94.4, T(14, 2, 29)),
                      _trade("102", 75, 95.0, T(14, 10)), _trade("202", 75, 88.0, T(14, 40))]
    kite["histories"] = {
        "201": _history(("PUT ORDER REQ RECEIVED", "SL", 95.0, T(13, 54, 5)), ("TRIGGER PENDING", "SL", 95.0, T(13, 54, 5)),
                       ("TRIGGER PENDING", "SL", 90.0, T(13, 55, 54)), ("COMPLETE", "MARKET", 0.0, T(14, 2, 29))),
        "202": _history(("TRIGGER PENDING", "SL", 88.0, T(14, 11)), ("COMPLETE", "LIMIT", 88.0, T(14, 40))),
    }
    result = await zerodha.sync_book(T(15, 45))
    assert result["details"]["histories"] == 2         # the converted stop and the unmodified fired one
    view, review = await _review(db)
    first, second = _off_card(view)
    assert "NO_STOP_ORDER" not in [f["code"] for f in first["flags"]]
    assert "STOP_LOWERED" in [f["code"] for f in first["flags"]]
    assert first["stops"] == [{"kind": "SL_ORDER", "trigger": 95.0, "status": "CONVERTED", "placed": "13:54",
                               "updated": "14:02", "exact": True}]
    assert second["stops"][0] | {} == {"kind": "SL_ORDER", "trigger": 88.0, "status": "TRIGGERED", "placed": "14:11",
                                       "updated": "14:40", "exact": True}
    timeline = [(e["at"], e["text"]) for e in review["trades"][0]["timeline"]]
    assert ("13:54", "You placed an SL order at ₹95") in timeline
    assert ("13:55", "You lowered your stop from ₹95 to ₹90") in timeline
    stop_rule = next(c for c in review["trades"][1]["checks"] if c["key"] == "stop")
    assert stop_rule["kept"] is True


@pytest.mark.asyncio
async def test_a_day_stored_before_o24_is_rebuilt_and_a_sale_that_cannot_be_told_claims_nothing(kite):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", T(15, 41))
    kite["orders"] = [
        _order("B1", "BUY", 75, T(11, 29, 17), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET"),
        _order("S1", "SELL", 75, T(13, 38, 17), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET", modified=True),
        _order("B2", "BUY", 75, T(13, 40), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET"),
        _order("S2", "SELL", 75, T(13, 50), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET", modified=True),
        _order("B3", "BUY", 75, T(14, 0), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET"),
        _order("S3", "SELL", 75, T(14, 20), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET"),
    ]
    kite["trades"] = [_trade("B1", 75, 75.05, T(11, 29, 17)), _trade("S1", 75, 62.6, T(13, 38, 17)),
                      _trade("B2", 75, 70.0, T(13, 40)), _trade("S2", 75, 64.0, T(13, 50)),
                      _trade("B3", 75, 66.0, T(14, 0)), _trade("S3", 75, 60.0, T(14, 20))]
    await zerodha.sync_book(T(15, 45))
    # As Production stored Oct 23: no history facts, only the trigger changes.
    async with aiosqlite.connect(db) as conn:
        await conn.execute("UPDATE partner_orders SET history_read=0, stop_trigger=NULL, stop_since=NULL")
        for change in _moves("S1", (68.0, 65.0, T(11, 44, 16)), (65.0, 60.0, T(11, 44, 33)),
                             (60.0, 75.0, T(12, 54)), (75.0, 70.0, T(12, 56, 32))):
            await conn.execute("INSERT INTO partner_order_changes(order_id,seq,session_date,changed_at,field,old_value,"
                               "new_value) VALUES(:order_id,:seq,:session_date,:changed_at,:field,:old_value,:new_value)",
                               change)
        await conn.commit()
    view, review = await _review(db)
    rebuilt, unknown, plain = _off_card(view)
    assert rebuilt["stops"][0] == {"kind": "SL_ORDER", "trigger": 68.0, "status": "CONVERTED", "placed": "11:44",
                                   "updated": "13:38", "exact": False}
    assert "NO_STOP_ORDER" not in [f["code"] for f in rebuilt["flags"]]
    assert "STOP_LOWERED" in [f["code"] for f in rebuilt["flags"]]
    timeline = [(e["at"], e["text"]) for e in review["trades"][0]["timeline"]]
    assert ("11:44", "By this time you had an SL order at ₹68") in timeline
    # A modified sale with no trigger seen: unknown, so nothing is said about this trade's stop.
    assert "stops" not in unknown and "NO_STOP_ORDER" not in [f["code"] for f in unknown["flags"]]
    # An unmodified market sale is no stop: the day's stops are known, so "no stop" holds.
    assert "NO_STOP_ORDER" in [f["code"] for f in plain["flags"]]


@pytest.mark.asyncio
async def test_a_refused_second_stop_reads_in_plain_words_on_the_timeline(kite):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", T(15, 41))
    margin = "Insufficient funds. Margin required: 159586.95. Margin available: 7536.70. Check orderbook for open orders."
    kite["orders"] = [
        _order("101", "BUY", 75, T(13, 53, 41), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET", product="NRML"),
        _order("201", "SELL", 75, T(14, 2, 29), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET", modified=True,
               product="NRML"),
        _order("203", "SELL", 75, T(13, 54, 39), symbol=OFF_SYMBOL, exchange="NFO", order_type="SL", status="REJECTED",
               trigger_price=95.0, status_message=margin, product="NRML"),
    ]
    kite["trades"] = [_trade("101", 75, 105.8, T(13, 53, 41)), _trade("201", 75, 94.4, T(14, 2, 29))]
    kite["histories"] = {"201": _history(("TRIGGER PENDING", "SL", 95.0, T(13, 54, 5)),
                                        ("COMPLETE", "MARKET", 0.0, T(14, 2, 29)))}
    await zerodha.sync_book(T(15, 45))
    view, review = await _review(db)
    texts = [e["text"] for e in review["trades"][0]["timeline"]]
    assert ("Zerodha refused your sell order: another sell order for this option was already waiting, so this one "
            "would have sold more than the 75 you held: Zerodha counted it as a new short sale, which needs ₹159,587 "
            "of margin; your account had ₹7,537.") in texts
    refused = review["orders"]["rejected"][0]
    assert refused["reason"] == margin and refused["plain"].startswith("another sell order for this option")


@pytest.mark.asyncio
async def test_a_trailed_stop_is_praised_after_a_small_trim_but_not_when_it_ended_lower(kite):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", T(15, 41))
    kite["orders"] = [
        _order("B1", "BUY", 75, T(9, 22, 36), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET"),
        _order("S1", "SELL", 75, T(10, 22, 31), symbol=OFF_SYMBOL, exchange="NFO", order_type="LIMIT",
               trigger_price=90.0, price=90.0, modified=True),
        _order("B2", "BUY", 75, T(10, 31), symbol=OFF_SYMBOL, exchange="NFO", order_type="MARKET"),
        _order("S2", "SELL", 75, T(10, 40), symbol=OFF_SYMBOL, exchange="NFO", order_type="LIMIT",
               trigger_price=300.0, price=300.0, modified=True),
    ]
    kite["trades"] = [_trade("B1", 75, 42.25, T(9, 22, 36)), _trade("S1", 75, 90.0, T(10, 22, 31)),
                      _trade("B2", 75, 360.0, T(10, 31)), _trade("S2", 75, 300.0, T(10, 40))]
    await zerodha.sync_book(T(15, 45))
    async with aiosqlite.connect(db) as conn:
        for change in (_moves("S1", (33.0, 50.0, T(9, 54)), (50.0, 68.0, T(10, 4)), (68.0, 66.0, T(10, 5)),
                              (66.0, 90.0, T(10, 17)))
                       + _moves("S2", (320.0, 300.0, T(10, 33)), (300.0, 280.0, T(10, 35)), (280.0, 300.0, T(10, 39)))):
            await conn.execute("INSERT INTO partner_order_changes(order_id,seq,session_date,changed_at,field,old_value,"
                               "new_value) VALUES(:order_id,:seq,:session_date,:changed_at,:field,:old_value,:new_value)",
                               change)
        await conn.commit()
    view, _review_ = await _review(db)
    trailed, lowered = _off_card(view)
    assert {"STOP_LOWERED"} <= {f["code"] for f in trailed["flags"]}
    assert "STOP_TRAILED" in [p["code"] for p in trailed["positives"]]
    assert "STOP_LOWERED" in [f["code"] for f in lowered["flags"]]
    assert "STOP_TRAILED" not in [p["code"] for p in lowered["positives"]]      # 320 -> 280 -> 300 ended lower
