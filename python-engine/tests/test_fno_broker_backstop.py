"""[O21-BS] Resting broker SL under live F&O options: levels, arming and never selling twice."""
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

import fno_broker_backstop as bs
from config import settings
from fno_executor import FnoExecutor
from tests.test_atomic_settlement import _insert_open_position, fno_db  # noqa: F401 (fixture)


@pytest.fixture(autouse=True)
def _pages(monkeypatch):
    pages = []

    async def notify(message, **kwargs):
        pages.append((kwargs.get("event"), message))
        return True

    alert = MagicMock()
    alert.notify_operator = notify
    monkeypatch.setitem(sys.modules, "operator_alert", alert)
    monkeypatch.setattr(bs, "_paged", set())
    monkeypatch.setattr(bs, "_last_check", {})
    monkeypatch.setattr(settings, "FNO_BROKER_BACKSTOP_ENABLED", True)
    return pages


@pytest.mark.parametrize("fill, expected", [
    (100.0, (65.0, 58.5)),       # 35% under; 10% gap inside the 20% range
    (40.0, (26.0, 23.4)),        # small trigger: gap well inside the ₹10 range
    (1000.0, (650.0, 585.0)),
    (101.37, (65.85, 59.25)),    # rounded down to the 0.05 tick
])
def test_backstop_levels(fill, expected):
    assert bs.backstop_levels(fill, 0.05, stop_pct=0.25, extra_pct=0.10, gap_pct=0.10) == expected


def test_no_level_for_a_worthless_option_or_a_bad_config():
    assert bs.backstop_levels(0.10, 0.05, stop_pct=0.25, extra_pct=0.10, gap_pct=0.10) is None
    assert bs.backstop_levels(100.0, 0.05, stop_pct=0.6, extra_pct=0.5, gap_pct=0.10) is None
    # A 30% gap on a ₹200 trigger exceeds NSE's 20% range: clamped to 20%.
    trigger, limit = bs.backstop_levels(400.0, 0.05, stop_pct=0.25, extra_pct=0.25, gap_pct=0.30)
    assert (trigger, limit) == (200.0, 160.0)


def _live(kite=None) -> FnoExecutor:
    executor = FnoExecutor(kite or AsyncMock(), paper_mode=False, source_tag="FNO_LIVE")
    executor.poll_interval_sec = 0
    return executor


@pytest.mark.asyncio
async def test_arm_places_a_protective_sell_sl_and_records_it(fno_db):
    kite = AsyncMock()
    kite.place_order.return_value = {"order_id": "SL-1", "dispatch_certainty": "ACCEPTED"}
    out = await bs.arm(fno_db, _live(kite), position_id=7, source="FNO_LIVE", tradingsymbol="NIFTY26O2322950PE",
                       exchange="NFO", qty=75, fill=100.0, tick=0.05)
    assert out["state"] == "PLACED"
    kwargs = kite.place_order.await_args.kwargs
    assert (kwargs["transaction_type"], kwargs["order_type"], kwargs["trigger_price"], kwargs["price"]) == \
        ("SELL", "SL", 65.0, 58.5)
    assert kwargs["intent"] == "exit" and kwargs["product"] == "MIS" and kwargs["quantity"] == 75
    row = await bs.load_backstop(fno_db, 7)
    assert (row["state"], row["order_id"], row["trigger_price"]) == ("PLACED", "SL-1", 65.0)


@pytest.mark.asyncio
async def test_arm_is_inert_on_paper_and_pages_when_rejected(fno_db, _pages):
    paper = FnoExecutor(AsyncMock(), paper_mode=True, source_tag="FNO_PAPER")
    assert (await bs.arm(fno_db, paper, position_id=1, source="FNO_PAPER", tradingsymbol="X", exchange="NFO",
                         qty=75, fill=100.0, tick=0.05))["state"] == "NOT_ARMED"
    paper.kite.place_order.assert_not_awaited()
    kite = AsyncMock()
    kite.place_order.return_value = {"order_id": None, "dispatch_certainty": "BROKER_REJECTED", "message": "range"}
    out = await bs.arm(fno_db, _live(kite), position_id=2, source="FNO_LIVE", tradingsymbol="X", exchange="NFO",
                       qty=75, fill=100.0, tick=0.05)
    assert out["state"] == "PLACE_REJECTED" and _pages[0][0] == "fno_backstop_not_placed"


async def _armed(db, position_id=5, state="PLACED", order_id="SL-1"):
    await bs._write(db, position_id, source="FNO_LIVE", tradingsymbol="NIFTY26O2322950PE", exchange="NFO", qty=75,
                    trigger_price=65.0, limit_price=58.5, order_id=order_id, state=state)


@pytest.mark.asyncio
@pytest.mark.parametrize("final, expected", [
    ({"status": "CANCELLED", "filled_quantity": 0}, {"action": "proceed"}),
    ({"status": "COMPLETE", "filled_quantity": 75, "average_price": 63.2},
     {"action": "filled", "fill_price": 63.2, "order_id": "SL-1"}),
    ({"status": "CANCELLED", "filled_quantity": 25, "average_price": 64.0},
     {"action": "partial", "filled_qty": 25, "fill_price": 64.0, "remaining": 50, "order_id": "SL-1"}),
])
async def test_before_exit_cancels_and_reports_what_is_left(fno_db, final, expected):
    await _armed(fno_db)
    executor = _live()
    executor.kite.order_history.return_value = [final]
    assert await bs.before_exit(fno_db, executor, 5, 75) == expected
    executor.kite.cancel_order.assert_awaited_once_with("SL-1")


@pytest.mark.asyncio
async def test_before_exit_holds_when_the_state_cannot_be_proven(fno_db, _pages):
    await _armed(fno_db)
    executor = _live()
    executor.kite.order_history.return_value = [{"status": "OPEN", "filled_quantity": 0}]
    assert (await bs.before_exit(fno_db, executor, 5, 75))["action"] == "hold"
    assert (await bs.before_exit(fno_db, executor, 5, 75))["action"] == "hold"
    assert [event for event, _ in _pages] == ["fno_backstop_unknown"]        # paged once


@pytest.mark.asyncio
async def test_unknown_dispatch_is_resolved_from_the_order_book(fno_db):
    await _armed(fno_db, state="PLACE_UNKNOWN", order_id=None)
    executor = _live()
    executor.kite.orders_snapshot.return_value = []
    assert await bs.before_exit(fno_db, executor, 5, 75) == {"action": "proceed"}
    await _armed(fno_db, position_id=6, state="PLACE_UNKNOWN", order_id=None)
    executor.kite.orders_snapshot.return_value = _book(order_id="SL-9")
    executor.kite.order_history.return_value = [{"status": "CANCELLED", "filled_quantity": 0}]
    assert await bs.before_exit(fno_db, executor, 6, 75) == {"action": "proceed"}
    executor.kite.cancel_order.assert_awaited_once_with("SL-9")
    await _armed(fno_db, position_id=8, state="PLACE_UNKNOWN", order_id=None)
    executor.kite.orders_snapshot.return_value = None      # unreadable book
    assert (await bs.before_exit(fno_db, executor, 8, 75))["action"] == "hold"


@pytest.mark.asyncio
async def test_passive_check_books_an_executed_backstop_and_notices_a_drop(fno_db, _pages):
    await _armed(fno_db)
    executor = _live()
    now = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)
    executor.kite.order_history.return_value = [{"status": "TRIGGER PENDING", "filled_quantity": 0}]
    assert await bs.check_filled(fno_db, executor, 5, price=90.0, now=now) is None
    # Far from the trigger and checked a moment ago: no broker read.
    assert await bs.check_filled(fno_db, executor, 5, price=90.0, now=now) is None
    assert executor.kite.order_history.await_count == 1
    executor.kite.order_history.return_value = [{"status": "COMPLETE", "filled_quantity": 75, "average_price": 62.0}]
    assert await bs.check_filled(fno_db, executor, 5, price=66.0, now=now) == {"fill_price": 62.0, "order_id": "SL-1"}
    await _armed(fno_db, position_id=9)
    executor.kite.order_history.return_value = [{"status": "CANCELLED", "filled_quantity": 30}]
    assert await bs.check_filled(fno_db, executor, 9, price=0.0, now=now) is None
    assert (await bs.load_backstop(fno_db, 9))["state"] == "BROKER_CANCELLED"
    assert _pages[-1][0] == "fno_backstop_dropped"
    # The part-fill is not "safe": the exit re-reads it and sells only the rest.
    executor.kite.order_history.return_value = [{"status": "CANCELLED", "filled_quantity": 30, "average_price": 64.0}]
    assert (await bs.before_exit(fno_db, executor, 9, 75))["remaining"] == 45


def _exit_executor():
    kite = AsyncMock()
    kite.get_quote.return_value = {1: {"last_price": 110, "depth": {"buy": [{"price": 110}]}}}
    executor = AsyncMock()
    executor.paper_mode = False
    executor.execute_exit.return_value = {"status": "filled", "order_id": "broker-1", "fill_price": 110}
    return kite, executor


NOW = datetime(2026, 9, 13, 15, 20, tzinfo=timezone.utc)      # past the 15:10 hard flat


@pytest.mark.asyncio
async def test_a_filled_backstop_is_the_exit_and_no_sell_is_sent(fno_db):
    from fno_orchestrator import _manage_open_positions
    position_id = await _insert_open_position(fno_db, source="FNO_LIVE")
    await _armed(fno_db, position_id=position_id)
    kite, executor = _exit_executor()
    executor.cancel_and_read.return_value = ({"status": "COMPLETE", "filled_quantity": 75, "average_price": 62.0}, None)
    closed = await _manage_open_positions(kite, fno_db, "FNO_LIVE", executor, NOW, 19500)
    assert len(closed) == 1
    executor.execute_exit.assert_not_awaited()
    with closing(sqlite3.connect(fno_db)) as db:
        exit_premium, reason, order_id = db.execute(
            "SELECT exit_premium, exit_reason, exit_order_id FROM fno_positions WHERE id=?", (position_id,)).fetchone()
    assert (exit_premium, reason, order_id) == (62.0, "broker_backstop", "SL-1")


@pytest.mark.asyncio
async def test_engine_exit_cancels_the_backstop_first_and_partial_sells_only_the_rest(fno_db):
    from fno_orchestrator import _manage_open_positions
    position_id = await _insert_open_position(fno_db, source="FNO_LIVE")
    await _armed(fno_db, position_id=position_id)
    kite, executor = _exit_executor()
    executor.cancel_and_read.return_value = ({"status": "CANCELLED", "filled_quantity": 25, "average_price": 64.0}, None)
    closed = await _manage_open_positions(kite, fno_db, "FNO_LIVE", executor, NOW, 19500)
    assert len(closed) == 1
    assert executor.execute_exit.await_args.args[:2] == ("NIFTY26SEP19500CE", 50)
    with closing(sqlite3.connect(fno_db)) as db:
        exit_premium = db.execute("SELECT exit_premium FROM fno_positions WHERE id=?", (position_id,)).fetchone()[0]
    assert exit_premium == pytest.approx((25 * 64.0 + 50 * 110.0) / 75)


@pytest.mark.asyncio
async def test_an_unproven_backstop_holds_the_exit_without_claiming_it(fno_db):
    from fno_orchestrator import _manage_open_positions
    position_id = await _insert_open_position(fno_db, source="FNO_LIVE")
    await _armed(fno_db, position_id=position_id)
    kite, executor = _exit_executor()
    executor.cancel_and_read.return_value = ({}, "TimeoutError")
    assert await _manage_open_positions(kite, fno_db, "FNO_LIVE", executor, NOW, 19500) == []
    executor.execute_exit.assert_not_awaited()
    with closing(sqlite3.connect(fno_db)) as db:
        assert db.execute("SELECT COUNT(*) FROM fno_exit_intents").fetchone()[0] == 0
        assert db.execute("SELECT status FROM fno_positions WHERE id=?", (position_id,)).fetchone()[0] == "OPEN"


@pytest.mark.asyncio
async def test_paper_positions_never_touch_the_backstop(fno_db):
    from fno_orchestrator import _manage_open_positions
    await _insert_open_position(fno_db)
    kite, executor = _exit_executor()
    executor.paper_mode = True
    assert len(await _manage_open_positions(kite, fno_db, "FNO_PAPER", executor, NOW, 19500)) == 1
    executor.cancel_and_read.assert_not_awaited()
    executor.execute_exit.assert_awaited_once()


# ---------------------------------------------------------------- [A22-BS] uncertain records


def _order(order_id="SL-7", *, tag="FNO_LIVE", at=None, status="TRIGGER PENDING", trigger=65.0, qty=75,
           exchange="NFO"):
    """One order as Kite's /orders lists it; ``at`` defaults to now (IST)."""
    at = at or datetime.now(bs.IST).strftime("%Y-%m-%d %H:%M:%S")
    return {"order_id": order_id, "tradingsymbol": "NIFTY26O2322950PE", "exchange": exchange,
            "transaction_type": "SELL", "order_type": "SL", "trigger_price": trigger, "quantity": qty,
            "status": status, "order_timestamp": at, "tag": tag}


def _book(trigger=65.0, order_id="SL-7", tag="FNO_LIVE"):
    return [_order(order_id, tag=tag, trigger=trigger)]


def _age(db, position_id, seconds):
    """Back-date a row so it is past the in-flight grace."""
    from datetime import timedelta
    old = (datetime.now(bs.IST) - timedelta(seconds=seconds)).isoformat()
    with closing(sqlite3.connect(db)) as con:
        con.execute("UPDATE fno_broker_backstops SET placed_at=?, updated_at=? WHERE position_id=?",
                    (old, old, position_id))
        con.commit()


@pytest.mark.asyncio
async def test_a_receipt_lost_after_the_send_never_lets_an_exit_sell_blind(fno_db, monkeypatch, _pages):
    # The audit's reproducer: the broker accepts the SL, then the receipt write fails.
    kite = AsyncMock()
    kite.place_order.return_value = {"order_id": "SL-7", "dispatch_certainty": "ACCEPTED"}
    real_write = bs._write

    async def failing_write(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(bs, "_write", failing_write)
    out = await bs.arm(fno_db, _live(kite), position_id=7, source="FNO_LIVE", tradingsymbol="NIFTY26O2322950PE",
                       exchange="NFO", qty=75, fill=100.0, tick=0.05)
    monkeypatch.setattr(bs, "_write", real_write)
    assert out["state"] == "PLACING" and _pages[-1][0] == "fno_backstop_unrecorded"
    row = await bs.load_backstop(fno_db, 7)
    assert (row["state"], row["order_id"], row["trigger_price"]) == ("PLACING", None, 65.0)
    executor = _live(kite)
    # Seconds later the send may still be in flight: hold, never guess.
    assert await bs.before_exit(fno_db, executor, 7, 75) == {"action": "hold",
                                                             "reason": "backstop_dispatch_in_flight"}
    _age(fno_db, 7, 60)
    kite.orders_snapshot.return_value = None                 # the book cannot be read: still hold
    assert (await bs.before_exit(fno_db, executor, 7, 75))["action"] == "hold"
    assert row["broker_tag"] == kite.place_order.await_args.kwargs["tag"]
    kite.orders_snapshot.return_value = _book(tag=row["broker_tag"])   # found: cancel it, read what it did
    kite.order_history.return_value = [{"status": "CANCELLED", "filled_quantity": 0}]
    assert await bs.before_exit(fno_db, executor, 7, 75) == {"action": "proceed"}
    kite.cancel_order.assert_awaited_once_with("SL-7")


@pytest.mark.asyncio
async def test_no_order_is_sent_without_a_durable_intent_and_never_twice(fno_db, monkeypatch, _pages):
    kite = AsyncMock()
    kite.place_order.return_value = {"order_id": "SL-1", "dispatch_certainty": "ACCEPTED"}

    async def unwritable(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(bs, "_claim_intent", unwritable)
    out = await bs.arm(fno_db, _live(kite), position_id=3, source="FNO_LIVE", tradingsymbol="X", exchange="NFO",
                       qty=75, fill=100.0, tick=0.05)
    assert out == {"state": "ARM_FAILED"} and _pages[-1][0] == "fno_backstop_not_placed"
    kite.place_order.assert_not_awaited()
    monkeypatch.undo()
    monkeypatch.setattr(settings, "FNO_BROKER_BACKSTOP_ENABLED", True)
    first = await bs.arm(fno_db, _live(kite), position_id=3, source="FNO_LIVE", tradingsymbol="X", exchange="NFO",
                         qty=75, fill=100.0, tick=0.05)
    again = await bs.arm(fno_db, _live(kite), position_id=3, source="FNO_LIVE", tradingsymbol="X", exchange="NFO",
                         qty=75, fill=100.0, tick=0.05)
    assert (first["state"], again["state"], kite.place_order.await_count) == ("PLACED", "ALREADY_RECORDED", 1)


@pytest.mark.asyncio
async def test_an_unreadable_ledger_is_not_an_absent_backstop(fno_db, tmp_path, _pages):
    # A fresh database has no table yet: nothing was ever recorded.
    empty = str(tmp_path / "empty.db")
    assert await bs.load_backstop(empty, 1) is None
    # A database that cannot be opened proves nothing: the exit holds, the passive check waits.
    unreadable = str(tmp_path)                               # a directory, not a database
    with pytest.raises(bs.BackstopUnreadable):
        await bs.load_backstop(unreadable, 1)
    executor = _live()
    assert await bs.before_exit(unreadable, executor, 1, 75) == {"action": "hold",
                                                                 "reason": "backstop_ledger_unreadable"}
    assert await bs.check_filled(unreadable, executor, 1, price=50.0) is None
    executor.kite.cancel_order.assert_not_awaited()
    assert [event for event, _ in _pages] == ["fno_backstop_unreadable"]


@pytest.mark.asyncio
async def test_the_passive_check_adopts_a_lost_receipt_from_the_order_book(fno_db):
    await _armed(fno_db, position_id=4, state="PLACING", order_id=None)
    _age(fno_db, 4, 60)
    executor = _live()
    executor.kite.orders_snapshot.return_value = _book(order_id="SL-4")
    executor.kite.order_history.return_value = [{"status": "TRIGGER PENDING", "filled_quantity": 0}]
    assert await bs.check_filled(fno_db, executor, 4, price=90.0) is None
    row = await bs.load_backstop(fno_db, 4)
    assert (row["state"], row["order_id"]) == ("PLACED", "SL-4")
    executor.kite.order_history.assert_awaited_once_with(order_id="SL-4")


# ---------------------------------------------------------------- [S23-BS1] order identity, not shape


async def _intent(db, position_id, *, tag, at="2026-10-23T11:01:00+05:30", state="PLACE_UNKNOWN"):
    """An uncertain dispatch recorded at ``at`` (IST)."""
    await bs._write(db, position_id, source="FNO_LIVE", tradingsymbol="NIFTY26O2322950PE", exchange="NFO", qty=75,
                    trigger_price=65.0, limit_price=58.5, order_id=None, state=state, broker_tag=tag)
    with closing(sqlite3.connect(db)) as con:
        con.execute("UPDATE fno_broker_backstops SET placed_at=?, updated_at=? WHERE position_id=?",
                    (at, at, position_id))
        con.commit()


EARLIER_STOP = _order("OLD-POSITION-SL", at="2026-10-23 10:01:12", status="COMPLETE")


@pytest.mark.asyncio
@pytest.mark.parametrize("tag", ["BSL0123456789abcdef", None])
async def test_an_earlier_positions_completed_stop_is_never_adopted(fno_db, tag):
    # The Oct 23 audit's reproducer: the current 11:01 send is not in the book;
    # an earlier position's 10:01 COMPLETE stop has the same symbol, trigger,
    # quantity and exchange. Adopting it booked the still-held long as flat.
    await _intent(fno_db, 11, tag=tag)
    executor = _live()
    executor.kite.orders_snapshot.return_value = [{**EARLIER_STOP, "average_price": 58.5}]
    assert await bs.before_exit(fno_db, executor, 11, 75) == {"action": "proceed"}
    executor.kite.cancel_order.assert_not_awaited()
    assert (await bs.load_backstop(fno_db, 11))["state"] == "CANCELLED"
    # The passive check does not adopt it either.
    await _intent(fno_db, 12, tag=tag)
    now = datetime(2026, 10, 23, 5, 35, tzinfo=timezone.utc)          # 11:05 IST
    assert await bs.check_filled(fno_db, executor, 12, price=66.0, now=now) is None
    row = await bs.load_backstop(fno_db, 12)
    assert (row["state"], row["order_id"]) == ("PLACE_UNKNOWN", None)
    executor.kite.order_history.assert_not_awaited()


@pytest.mark.asyncio
async def test_our_tag_identifies_the_order_even_when_it_already_executed(fno_db):
    tag = "BSL00000000000000aa"
    await _intent(fno_db, 13, tag=tag)
    executor = _live()
    executor.kite.orders_snapshot.return_value = [
        EARLIER_STOP,
        _order("OTHER-BACKSTOP", tag="BSL00000000000000bb", at="2026-10-23 11:01:20"),   # another position's
        _order("OURS", tag=tag, at="2026-10-23 11:01:01", status="COMPLETE")]
    executor.kite.order_history.return_value = [{"status": "COMPLETE", "filled_quantity": 75, "average_price": 63.0}]
    assert await bs.before_exit(fno_db, executor, 13, 75) == {"action": "filled", "fill_price": 63.0,
                                                              "order_id": "OURS"}
    executor.kite.cancel_order.assert_awaited_once_with("OURS")


@pytest.mark.asyncio
async def test_a_fired_backstop_listed_as_limit_is_still_ours(fno_db, _pages):
    # [O24-BS] Kite lists a triggered SL as LIMIT with its trigger kept. With our tag (or, for a legacy intent,
    # placed after it with our trigger) it is this backstop, and its fill is read from the order itself.
    tag = "BSL00000000000000cc"
    await _intent(fno_db, 17, tag=tag)
    executor = _live()
    executor.kite.orders_snapshot.return_value = [{**_order("FIRED", tag=tag, at="2026-10-23 11:01:01",
                                                            status="COMPLETE"), "order_type": "LIMIT"}]
    executor.kite.order_history.return_value = [{"status": "COMPLETE", "filled_quantity": 75, "average_price": 61.5}]
    assert await bs.before_exit(fno_db, executor, 17, 75) == {"action": "filled", "fill_price": 61.5,
                                                              "order_id": "FIRED"}
    await _intent(fno_db, 18, tag=None)
    executor = _live()
    executor.kite.orders_snapshot.return_value = [{**_order("LEGACY", at="2026-10-23 11:01:02", status="OPEN"),
                                                   "order_type": "LIMIT"}]
    executor.kite.order_history.return_value = [{"status": "CANCELLED", "filled_quantity": 0}]
    assert await bs.before_exit(fno_db, executor, 18, 75) == {"action": "proceed"}
    executor.kite.cancel_order.assert_awaited_once_with("LEGACY")
    assert _pages == []


@pytest.mark.asyncio
async def test_a_limit_order_without_a_trigger_is_not_a_backstop(fno_db, _pages):
    # A plain LIMIT sale under our tag is not the SL we sent: the exit holds and pages, as before.
    tag = "BSL00000000000000dd"
    await _intent(fno_db, 19, tag=tag)
    executor = _live()
    executor.kite.orders_snapshot.return_value = [{**_order("PLAIN", tag=tag, at="2026-10-23 11:01:01", trigger=0.0),
                                                   "order_type": "LIMIT"}]
    assert await bs.before_exit(fno_db, executor, 19, 75) == {"action": "hold", "reason": "backstop_dispatch_unknown"}
    executor.kite.cancel_order.assert_not_awaited()
    assert bs._sl_shape({"order_type": "SL"}) and bs._sl_shape({"order_type": "LIMIT", "trigger_price": 65.0})
    assert not bs._sl_shape({"order_type": "LIMIT", "trigger_price": "x"}) and not bs._sl_shape({"order_type": "MARKET",
                                                                                                "trigger_price": 65.0})


@pytest.mark.asyncio
async def test_a_legacy_intent_adopts_only_an_order_placed_after_it(fno_db):
    await _intent(fno_db, 14, tag=None)
    executor = _live()
    executor.kite.orders_snapshot.return_value = [EARLIER_STOP, _order("AFTER", at="2026-10-23 11:01:02")]
    executor.kite.order_history.return_value = [{"status": "CANCELLED", "filled_quantity": 0}]
    assert await bs.before_exit(fno_db, executor, 14, 75) == {"action": "proceed"}
    executor.kite.cancel_order.assert_awaited_once_with("AFTER")


@pytest.mark.asyncio
@pytest.mark.parametrize("tag, book", [
    # Two untagged orders since a legacy intent: never pick one.
    (None, [_order("A", at="2026-10-23 11:01:02"), _order("B", at="2026-10-23 11:01:03")]),
    # An earlier same-shape stop still working: whose it is cannot be proven.
    (None, [_order("WORKING", at="2026-10-23 10:01:12", status="TRIGGER PENDING")]),
    ("BSL0123456789abcdef", [_order("WORKING", at="2026-10-23 10:01:12", status="TRIGGER PENDING")]),
    # Our tag is absent but an untagged same-shape order appeared since the intent.
    ("BSL0123456789abcdef", [_order("MANUAL", at="2026-10-23 11:02:00")]),
    # Our tag on an order that no longer has our quantity.
    ("BSL0123456789abcdef", [_order("OURS", tag="BSL0123456789abcdef", qty=50)]),
    # A same-shape order with no timestamp.
    (None, [{**_order("NO-TIME"), "order_timestamp": None}]),
])
async def test_an_unprovable_order_holds_the_exit_and_pages(fno_db, _pages, tag, book):
    await _intent(fno_db, 15, tag=tag)
    executor = _live()
    executor.kite.orders_snapshot.return_value = book
    assert await bs.before_exit(fno_db, executor, 15, 75) == {"action": "hold",
                                                              "reason": "backstop_dispatch_unknown"}
    executor.kite.cancel_order.assert_not_awaited()
    assert [event for event, _ in _pages] == ["fno_backstop_unknown"]


@pytest.mark.asyncio
async def test_another_exchange_or_quantity_is_not_this_backstop(fno_db):
    # The audit's second probe: changed exchange and quantity were still adopted.
    await _intent(fno_db, 16, tag=None)
    executor = _live()
    executor.kite.orders_snapshot.return_value = [_order("BFO", exchange="BFO", at="2026-10-23 11:01:05"),
                                                  _order("QTY", qty=150, at="2026-10-23 11:01:05")]
    assert await bs.before_exit(fno_db, executor, 16, 75) == {"action": "proceed"}
    executor.kite.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_ledger_from_before_tags_gains_the_column(tmp_path):
    db = str(tmp_path / "old.db")
    with closing(sqlite3.connect(db)) as con:
        con.execute(bs._DDL.replace(",\n  broker_tag TEXT", ""))
        con.execute("INSERT INTO fno_broker_backstops VALUES (1,'FNO_LIVE','X','NFO',75,65.0,58.5,'SL-1','PLACED',"
                    "'2026-10-22T10:00:00+05:30','2026-10-22T10:00:00+05:30',NULL)")
        con.commit()
    assert await bs._claim_intent(db, 2, source="FNO_LIVE", tradingsymbol="X", exchange="NFO", qty=75,
                                  trigger_price=65.0, limit_price=58.5, state="PLACING", broker_tag="BSLx")
    assert (await bs.load_backstop(db, 1))["broker_tag"] is None
    assert (await bs.load_backstop(db, 2))["broker_tag"] == "BSLx"


def test_backstop_tags_fit_kite_and_are_unique():
    tags = {bs.new_tag() for _ in range(1000)}
    assert len(tags) == 1000
    assert all(len(t) == 20 and t.startswith(bs.TAG_PREFIX) and t.isalnum() for t in tags)
