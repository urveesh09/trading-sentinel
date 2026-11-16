"""[SN338] Gold V8's order lifecycle when the broker or the market misbehaves: the units sold never exceed the units held."""
import pytest

from sn_gold_v8_orders import Book


def held_book(units=130, stop=True):
    b = Book(lot_size=65)
    e = b.buy("ENTRY", units, 200.0)
    b.on_fill(e.oid, units)
    if stop:
        b.protect(180.0, 171.0)
    return b


def test_partial_entry_fill_sizes_the_stop_to_what_is_held():
    b = Book(lot_size=65)
    e = b.buy("ENTRY", 130, 200.0)
    b.on_fill(e.oid, 65)
    s = b.protect(180.0, 171.0)
    assert b.held == 65 and s.qty == 65 and s.status == "TRIGGER_PENDING"


def test_exit_waits_for_the_stop_and_a_stop_that_fills_during_the_cancel_leaves_nothing_to_sell():
    b = held_book()
    s = b.stop()
    assert b.exit() is None and s.status == "CANCEL_REQUESTED", "no SELL until the stop's cancel or fill is known"
    b.on_fill(s.oid, 130)                      # the stop filled while we were cancelling it
    assert b.held == 0 and not b.live(kind="EXIT") and "OVERSOLD" not in b.flags


def test_a_partly_filled_stop_shrinks_the_exit():
    b = held_book()
    s = b.stop()
    b.exit()
    b.on_fill(s.oid, 65)
    b.on_cancelled(s.oid)
    (x,) = b.live(kind="EXIT")
    assert x.qty == 65
    b.on_fill(x.oid, 65)
    assert b.held == 0 and "OVERSOLD" not in b.flags


def test_a_stop_that_triggers_without_filling_becomes_a_market_exit():
    b = held_book()
    s = b.stop()
    b.on_triggered_unfilled(s.oid)
    assert s.status == "CANCEL_REQUESTED" and not b.live(kind="EXIT")
    b.on_cancelled(s.oid)
    (x,) = b.live(kind="EXIT")
    assert x.order_type == "MARKET" and x.qty == 130


def test_an_add_cancels_the_old_stop_and_the_new_stop_covers_the_whole_holding():
    b = held_book(65)
    old = b.stop()
    a = b.buy("ADD", 65, 210.0)
    assert old.status == "CANCEL_REQUESTED"
    b.on_cancelled(old.oid)
    b.on_fill(a.oid, 65)
    new = b.protect(195.0, 185.0)
    assert b.held == 130 and new.qty == 130 and old.status == "CANCELLED"


def test_a_sell_can_never_exceed_the_holding():
    b = held_book(65, stop=False)
    with pytest.raises(ValueError):
        b._place("EXIT", "SELL", 130, "LIMIT")


def test_a_late_fill_after_a_confirmed_cancel_is_booked_and_flagged():
    b = held_book()
    s = b.stop()
    b.exit()
    b.on_cancelled(s.oid)
    (x,) = b.live(kind="EXIT")
    b.on_fill(x.oid, 130)
    b.on_fill(s.oid, 65)                       # an exchange race: a fill reported after the cancel was confirmed
    assert s.late_fill and "OVERSOLD" in b.flags and b.held == -65


def test_a_rejected_order_is_flagged_and_holds_nothing():
    b = Book(lot_size=65)
    e = b.buy("ENTRY", 65, 200.0)
    b.on_rejected(e.oid)
    assert b.held == 0 and any("rejected" in f for f in b.flags) and b.protect(180.0, 171.0) is None
