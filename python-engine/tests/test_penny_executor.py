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
    # [EDGE-DRIFT 2026-07-31] The executor now verifies the signal price
    # against a live quote before it will place anything. Default quote sits
    # exactly at the signal price (10.05) so existing cases stay on the happy
    # path; drift cases override it.
    k.instrument_cache = {"AAA": 12345}
    k.get_quote = AsyncMock(return_value={12345: {"last_price": 10.05}})
    return k


def test_executor_places_limit_then_stop_limit(fake_kite):
    """Happy path: entry fills, protective stop accepted, no unwind.

    [SL-M 2026-07-31] The stop is an SL (stop-loss LIMIT), never SL-M.
    Zerodha refuses SL-M over the API ("Market orders without market
    protection are not allowed"), which is why every stop was rejected in
    production. Trigger snaps DOWN to a valid tick; the limit sits 1% below
    the trigger so it is marketable the instant it fires."""
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
    # Buy is a marketable LIMIT priced off the LIVE quote (10.05 * 1.005
    # snapped up), not off the signal's possibly-stale close.
    assert first_call.kwargs["order_type"] == "LIMIT"
    assert first_call.kwargs["price"] == pytest.approx(10.1)
    assert second_call.kwargs["order_type"] == "SL"
    assert second_call.kwargs["transaction_type"] == "SELL"
    assert second_call.kwargs["trigger_price"] == pytest.approx(9.7)
    assert second_call.kwargs["price"] == pytest.approx(9.6)
    # A SELL SL is only valid when limit <= trigger.
    assert second_call.kwargs["price"] <= second_call.kwargs["trigger_price"]
    # Never a raw MARKET order anywhere in the flow.
    assert all(c.kwargs.get("order_type") != "MARKET"
               for c in fake_kite.place_order.call_args_list)


def test_executor_unwinds_with_marketable_limit_when_stop_rejected(fake_kite):
    """Spec §7.2: if the stop is REJECTED, the executor MUST flatten.

    [UNWIND 2026-07-31] The unwind is a marketable SELL LIMIT, not a raw
    MARKET order -- Zerodha rejects the latter over the API, which on
    2026-07-30 left 14 SIGMA shares naked one second after the stop was
    also refused."""
    fake_kite.place_order = AsyncMock(side_effect=[
        {"order_id": "ENT-001"},
        {"status": "REJECTED", "message": "SL-M not supported"},
        {"order_id": "UNW-001"},
    ])
    fake_kite.order_history = AsyncMock(return_value=[
        {"order_id": "ANY", "status": "COMPLETE", "average_price": 10.05,
         "filled_quantity": 50, "order_timestamp": "2026-06-21T09:30:00+05:30"},
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
    assert result["entry_status"] == "unwound"
    assert result["sl_order_id"] is None
    assert result["unwind_order_id"] == "UNW-001"
    assert fake_kite.place_order.call_count == 3
    third_call = fake_kite.place_order.call_args_list[2]
    assert third_call.kwargs["order_type"] == "LIMIT"
    assert third_call.kwargs["transaction_type"] == "SELL"
    assert third_call.kwargs["quantity"] == 50
    # Marketable: 1% below the live quote, snapped down.
    assert third_call.kwargs["price"] == pytest.approx(9.9)


def test_executor_reports_unprotected_when_stop_and_unwind_both_fail(fake_kite):
    """[NAKED-POSITION 2026-07-31] The 2026-07-30 SIGMA state.

    Buy fills, stop is rejected, unwind is ALSO rejected. The old code set
    unwound=True unconditionally and returned entry_status="filled", so the
    orchestrator recorded a tidy position while real shares sat at the broker
    with no stop. It must now refuse to claim either."""
    fake_kite.place_order = AsyncMock(side_effect=[
        {"order_id": "ENT-001"},
        {"status": "ERROR", "message":
         "HTTP 400: Trigger price for stoploss sell orders should be lower "
         "than the last traded price"},
        {"status": "ERROR", "message":
         "HTTP 400: Market orders without market protection are not allowed"},
    ])
    from penny_executor import PennyExecutor
    from penny_models import PennyLeg
    ex = PennyExecutor(kite=fake_kite, paper_mode=False)
    result = asyncio.run(ex.execute_entry(
        ticker="AAA", leg=PennyLeg.MIS,
        entry_price=10.05, stop_loss=9.75,
        shares=50,
    ))
    assert result["entry_status"] == "unprotected"
    assert result["unwound"] is False
    assert result["sl_order_id"] is None
    assert result["unwind_order_id"] is None


def test_executor_refuses_entry_when_signal_price_is_stale(fake_kite):
    """[EDGE-DRIFT 2026-07-31] The 2026-07-30 SIGMA entry.

    Signal says 52.40 (a partially-formed daily candle cached at 09:17);
    the market is at 48.86 by the time the 09:30 cron fires. A 7.3% gap
    means the signal is describing a stock that no longer exists at that
    price -- refuse rather than book a phantom edge."""
    fake_kite.instrument_cache = {"SIGMA": 999}
    fake_kite.get_quote = AsyncMock(return_value={999: {"last_price": 48.86}})
    from penny_executor import PennyExecutor
    from penny_models import PennyLeg
    ex = PennyExecutor(kite=fake_kite, paper_mode=False)
    result = asyncio.run(ex.execute_entry(
        ticker="SIGMA", leg=PennyLeg.CNC,
        entry_price=52.40, stop_loss=50.304,
        shares=14,
    ))
    assert result["entry_status"] == "drift_rejected"
    fake_kite.place_order.assert_not_called()


def test_executor_refuses_entry_born_past_its_stop(fake_kite):
    """A long whose stop already sits at/above the market is not a trade.

    This is the condition Zerodha itself reported on 2026-07-30 ("trigger
    price should be lower than the last traded price") -- but by then we
    already owned the stock. Catch it before the buy."""
    fake_kite.instrument_cache = {"AAA": 12345}
    # Inside the 2% drift window, but the stop is above the market.
    fake_kite.get_quote = AsyncMock(return_value={12345: {"last_price": 9.95}})
    from penny_executor import PennyExecutor
    from penny_models import PennyLeg
    ex = PennyExecutor(kite=fake_kite, paper_mode=False)
    result = asyncio.run(ex.execute_entry(
        ticker="AAA", leg=PennyLeg.MIS,
        entry_price=10.05, stop_loss=9.98,
        shares=50,
    ))
    assert result["entry_status"] == "stop_already_breached"
    fake_kite.place_order.assert_not_called()


def test_paper_leg_fills_at_the_live_quote_not_the_stale_signal(fake_kite):
    """Paper must answer to the same market as live.

    On 2026-07-30 the paper book entered SIGMA at 52.40 while the stock
    traded 48.86, handing itself a 7.3% edge it could never have had."""
    fake_kite.instrument_cache = {"AAA": 12345}
    fake_kite.get_quote = AsyncMock(return_value={12345: {"last_price": 10.03}})
    from penny_executor import PennyExecutor
    from penny_models import PennyLeg
    ex = PennyExecutor(kite=fake_kite, paper_mode=True)
    result = asyncio.run(ex.execute_entry(
        ticker="AAA", leg=PennyLeg.MIS,
        entry_price=10.05, stop_loss=9.75,
        shares=50,
    ))
    assert result["entry_status"] == "paper"
    assert result["fill_price"] == pytest.approx(10.03)
    fake_kite.place_order.assert_not_called()


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
    # [EDGE-DRIFT 2026-07-31] Even paper needs a live quote to price against.
    fake_kite.instrument_cache = {"AAA": 12345}
    fake_kite.get_quote = AsyncMock(return_value={12345: {"last_price": 10.05}})
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


# ---------------------------------------------------------------------------
# [RETRY-STORM 2026-07-31] Per-ticker entry circuit breaker
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_entry_blocks():
    from penny_executor import reset_entry_blocks
    reset_entry_blocks()
    yield
    reset_entry_blocks()


def test_a_non_retryable_broker_rejection_blocks_the_ticker(fake_kite):
    """The 2026-07-29 KCPSUGIND storm.

    "MIS orders are currently blocked for KCPSUGIND" is a property of the
    instrument for the whole session -- it cannot succeed on a retry. The old
    code re-placed the identical order every 30 seconds for 14 minutes: 25
    rejected orders, no backoff, no alert, and a funnel that reported
    "accepted=25" for one signal that never traded."""
    from penny_executor import PennyExecutor, entry_blocked
    from penny_models import PennyLeg
    fake_kite.place_order = AsyncMock(return_value={
        "order_id": None, "status": "ERROR",
        "message": "HTTP 400: MIS orders are currently blocked for KCPSUGIND. "
                   "Place a CNC order instead.",
    })
    fake_kite.instrument_cache = {"KCPSUGIND": 555}
    fake_kite.get_quote = AsyncMock(return_value={555: {"last_price": 32.79}})
    ex = PennyExecutor(kite=fake_kite, paper_mode=False)

    first = asyncio.run(ex.execute_entry(
        ticker="KCPSUGIND", leg=PennyLeg.MIS,
        entry_price=32.79, stop_loss=32.40, shares=15,
    ))
    assert first["entry_status"] == "rejected"
    assert entry_blocked("KCPSUGIND")

    # Every subsequent attempt is refused WITHOUT touching the broker.
    calls_after_first = fake_kite.place_order.call_count
    for _ in range(24):
        again = asyncio.run(ex.execute_entry(
            ticker="KCPSUGIND", leg=PennyLeg.MIS,
            entry_price=32.79, stop_loss=32.40, shares=15,
        ))
        assert again["entry_status"] == "ticker_blocked"
    assert fake_kite.place_order.call_count == calls_after_first, (
        "blocked ticker still reached the broker -- the storm is not contained"
    )


def test_repeated_transient_failures_also_trip_the_breaker(fake_kite):
    """A retryable error still gets a bounded number of attempts."""
    from penny_executor import (
        MAX_ENTRY_ATTEMPTS_PER_TICKER, PennyExecutor, entry_blocked,
    )
    from penny_models import PennyLeg
    fake_kite.place_order = AsyncMock(return_value={
        "order_id": None, "status": "ERROR", "message": "HTTP 502: bad gateway",
    })
    ex = PennyExecutor(kite=fake_kite, paper_mode=False)
    for _ in range(MAX_ENTRY_ATTEMPTS_PER_TICKER):
        asyncio.run(ex.execute_entry(
            ticker="AAA", leg=PennyLeg.MIS,
            entry_price=10.05, stop_loss=9.75, shares=50,
        ))
    assert entry_blocked("AAA")


def test_a_fill_clears_the_failure_streak(fake_kite):
    """Transient failures must not accumulate across a successful trade."""
    from penny_executor import PennyExecutor, entry_blocked, note_entry_failure
    from penny_models import PennyLeg
    note_entry_failure("AAA", "HTTP 502: bad gateway")
    ex = PennyExecutor(kite=fake_kite, paper_mode=False)
    res = asyncio.run(ex.execute_entry(
        ticker="AAA", leg=PennyLeg.MIS,
        entry_price=10.05, stop_loss=9.75, shares=50,
    ))
    assert res["entry_status"] == "filled"
    assert entry_blocked("AAA") is None
