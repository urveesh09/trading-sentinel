"""
[PENNY-EXECUTOR 2026-06-21] Tests for the order-execution flow.

Spec §7.2 mandatory flow:
  1. Place entry LIMIT
  2. Wait for fill (with timeout)
  3. Place SL-M at broker
  4. If SL-M rejected -> market-exit immediately

We test with a fake Kite client; no real orders.
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock
import pytest


@pytest.fixture
def fake_kite():
    k = MagicMock()
    k.place_order = AsyncMock(return_value={"order_id": "ENT-001"})
    k.cancel_order = AsyncMock(return_value={"status": "cancelled"})
    k.order_history = AsyncMock(return_value=[
        {"order_id": "ENT-001", "status": "COMPLETE",
         "average_price": 10.05, "filled_quantity": 50,
         "tradingsymbol": "AAA", "transaction_type": "BUY",
         "order_timestamp": "2026-06-21T09:30:00+05:30"},
    ])
    # [ORDER-RECONCILE 2026-07-17] Post-timeout reconciliation reads the
    # positions book. Default: flat (no position held).
    k.get_broker_positions = AsyncMock(return_value={"net": [], "day": []})
    return k


def test_executor_places_limit_then_sl_m(fake_kite):
    """Happy path: entry fills, SL-M accepted, no unwind."""
    from penny_executor import PennyExecutor
    from penny_models import PennyLeg
    ex = PennyExecutor(kite=fake_kite, paper_mode=False)
    result = asyncio.run(ex.execute_entry(
        ticker="AAA", leg=PennyLeg.MIS,
        entry_price=10.05, stop_loss=9.75,
        shares=50,
    ))
    assert result["entry_order_id"] == "ENT-001"
    assert result["sl_order_id"] is not None
    assert result["unwound"] is False
    assert fake_kite.place_order.call_count == 2
    first_call = fake_kite.place_order.call_args_list[0]
    second_call = fake_kite.place_order.call_args_list[1]
    assert first_call.kwargs["order_type"] == "LIMIT"
    assert second_call.kwargs["order_type"] == "SL-M"
    assert second_call.kwargs["transaction_type"] == "SELL"
    assert second_call.kwargs["trigger_price"] == 9.75


def test_executor_market_unwinds_when_sl_m_rejected(fake_kite):
    """Spec §7.2: if SL-M is REJECTED by broker, executor MUST market-exit."""
    fake_kite.place_order = AsyncMock(side_effect=[
        {"order_id": "ENT-001"},
        {"status": "REJECTED", "message": "SL-M not supported"},
        {"order_id": "UNW-001"},
    ])
    from penny_executor import PennyExecutor
    from penny_models import PennyLeg
    ex = PennyExecutor(kite=fake_kite, paper_mode=False)
    result = asyncio.run(ex.execute_entry(
        ticker="AAA", leg=PennyLeg.MIS,
        entry_price=10.05, stop_loss=9.75,
        shares=50,
    ))
    assert result["unwound"] is True
    assert result["sl_order_id"] is None
    assert result["unwind_order_id"] == "UNW-001"
    assert fake_kite.place_order.call_count == 3
    third_call = fake_kite.place_order.call_args_list[2]
    assert third_call.kwargs["order_type"] == "MARKET"
    assert third_call.kwargs["transaction_type"] == "SELL"
    assert third_call.kwargs["quantity"] == 50


def test_executor_cancels_unfilled_entry(fake_kite):
    """If entry LIMIT doesn't fill and the positions book confirms no stock,
    cancel + log timeout (no SL placed, no spurious buy)."""
    fake_kite.order_history = AsyncMock(return_value=[
        {"order_id": "ENT-001", "status": "OPEN",
         "filled_quantity": 0, "tradingsymbol": "AAA",
         "order_timestamp": "2026-06-21T09:30:00+05:30"},
    ])
    from penny_executor import PennyExecutor
    from penny_models import PennyLeg
    ex = PennyExecutor(kite=fake_kite, paper_mode=False,
                        fill_timeout_sec=0.1, poll_interval_sec=0.05)
    result = asyncio.run(ex.execute_entry(
        ticker="AAA", leg=PennyLeg.MIS,
        entry_price=10.05, stop_loss=9.75,
        shares=50,
    ))
    assert result["entry_status"] == "timeout"
    assert result["sl_order_id"] is None
    fake_kite.cancel_order.assert_called_once_with("ENT-001")
    # entry LIMIT only -- no SL-M, no unwind for an unfilled order.
    assert fake_kite.place_order.call_count == 1


def test_executor_proceeds_when_fill_lands_late_in_history(fake_kite):
    """[ORDER-HISTORY-2026-07-17] Kite returns history chronologically, so
    a filled order shows COMPLETE at the LAST row, not history[0]. The old
    `history[0].get("status") == "COMPLETE"` never saw it -- every live
    edge entry since 2026-07-15 "timed out". Here the COMPLETE row sits
    after the initial OPEN row: the executor must treat it as filled and
    place the SL-M, not cancel."""
    fake_kite.order_history = AsyncMock(return_value=[
        {"order_id": "ENT-001", "status": "OPEN", "filled_quantity": 0,
         "order_timestamp": "2026-06-21T09:30:00+05:30"},
        {"order_id": "ENT-001", "status": "COMPLETE",
         "average_price": 10.05, "filled_quantity": 50,
         "order_timestamp": "2026-06-21T09:30:03+05:30"},
    ])
    from penny_executor import PennyExecutor
    from penny_models import PennyLeg
    ex = PennyExecutor(kite=fake_kite, paper_mode=False,
                       fill_timeout_sec=0.2, poll_interval_sec=0.05)
    result = asyncio.run(ex.execute_entry(
        ticker="AAA", leg=PennyLeg.MIS,
        entry_price=10.05, stop_loss=9.75, shares=50,
    ))
    assert result["entry_status"] == "filled"
    assert result["sl_order_id"] is not None
    fake_kite.cancel_order.assert_not_called()
    # entry LIMIT + SL-M.
    assert fake_kite.place_order.call_count == 2


def test_executor_reconciles_fill_after_poll_timeout(fake_kite):
    """The dangerous case: the fill poll times out (history slow to update),
    the code cancels, but the order ACTUALLY FILLED. Reconciliation via the
    positions book must catch it and place the SL rather than walking away
    from a naked long. This is the 2026-07-17 JINDWORLD near-miss."""
    # Poll always sees OPEN (history lags); positions book shows the fill.
    fake_kite.order_history = AsyncMock(return_value=[
        {"order_id": "ENT-001", "status": "OPEN", "filled_quantity": 0,
         "order_timestamp": "2026-06-21T09:30:00+05:30"},
    ])
    fake_kite.get_broker_positions = AsyncMock(return_value={
        "net": [{"tradingsymbol": "AAA", "quantity": 50}], "day": [],
    })
    from penny_executor import PennyExecutor
    from penny_models import PennyLeg
    ex = PennyExecutor(kite=fake_kite, paper_mode=False,
                       fill_timeout_sec=0.1, poll_interval_sec=0.05)
    result = asyncio.run(ex.execute_entry(
        ticker="AAA", leg=PennyLeg.MIS,
        entry_price=10.05, stop_loss=9.75, shares=50,
    ))
    assert result["entry_status"] == "filled"
    assert result["sl_order_id"] is not None
    # LIMIT entry + SL-M -- the position is protected, not abandoned.
    assert fake_kite.place_order.call_count == 2


def test_executor_no_cancel_when_broker_already_killed_order(fake_kite):
    """A REJECTED entry has nothing to cancel: pre-2026-07-17 the code
    cancelled anyway and got a confusing 'order does not exist' back. Now
    it exits early on the terminal state without a cancel call."""
    fake_kite.order_history = AsyncMock(return_value=[
        {"order_id": "ENT-001", "status": "OPEN",
         "order_timestamp": "2026-06-21T09:30:00+05:30"},
        {"order_id": "ENT-001", "status": "REJECTED",
         "status_message": "insufficient margin",
         "order_timestamp": "2026-06-21T09:30:01+05:30"},
    ])
    from penny_executor import PennyExecutor
    from penny_models import PennyLeg
    ex = PennyExecutor(kite=fake_kite, paper_mode=False,
                       fill_timeout_sec=0.5, poll_interval_sec=0.05)
    result = asyncio.run(ex.execute_entry(
        ticker="AAA", leg=PennyLeg.MIS,
        entry_price=10.05, stop_loss=9.75, shares=50,
    ))
    assert result["entry_status"] == "rejected"
    assert result["sl_order_id"] is None
    fake_kite.cancel_order.assert_not_called()
    assert fake_kite.place_order.call_count == 1


def test_executor_paper_mode_returns_paper_ids_without_calling_kite():
    """Paper mode: emit fake order_ids, don't call kite.place_order."""
    from penny_executor import PennyExecutor
    from penny_models import PennyLeg
    fake_kite = MagicMock()
    fake_kite.place_order = AsyncMock()
    ex = PennyExecutor(kite=fake_kite, paper_mode=True)
    result = asyncio.run(ex.execute_entry(
        ticker="AAA", leg=PennyLeg.MIS,
        entry_price=10.05, stop_loss=9.75,
        shares=50,
    ))
    assert result["paper"] is True
    assert result["entry_order_id"].startswith("PAPER-")
    assert result["sl_order_id"].startswith("PAPER-")
    assert result["unwound"] is False
    fake_kite.place_order.assert_not_called()


def test_executor_handles_entry_rejection(fake_kite):
    """If entry LIMIT is rejected by broker, no SL-M attempted."""
    fake_kite.place_order = AsyncMock(side_effect=Exception("broker rejected"))
    from penny_executor import PennyExecutor
    from penny_models import PennyLeg
    ex = PennyExecutor(kite=fake_kite, paper_mode=False)
    result = asyncio.run(ex.execute_entry(
        ticker="AAA", leg=PennyLeg.MIS,
        entry_price=10.05, stop_loss=9.75,
        shares=50,
    ))
    assert result["entry_status"] == "rejected"
    assert result["sl_order_id"] is None
    assert result["unwound"] is False


def test_executor_retries_sl_m_then_unwinds_on_second_failure(fake_kite):
    """SL-M raises (transient network error): retry once; on 2nd failure, unwind."""
    fake_kite.place_order = AsyncMock(side_effect=[
        {"order_id": "ENT-001"},
        Exception("network blip"),
        Exception("network down"),
        {"order_id": "UNW-001"},
    ])
    from penny_executor import PennyExecutor
    from penny_models import PennyLeg
    ex = PennyExecutor(kite=fake_kite, paper_mode=False)
    result = asyncio.run(ex.execute_entry(
        ticker="AAA", leg=PennyLeg.MIS,
        entry_price=10.05, stop_loss=9.75,
        shares=50,
    ))
    assert result["unwound"] is True
    assert result["sl_order_id"] is None
    assert fake_kite.place_order.call_count == 4
