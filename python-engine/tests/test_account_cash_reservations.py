"""P1 cross-runtime-compatible durable own-cash reservation protocol."""
import pytest

from account_cash_reservations import (
    AccountCashReservations, ReservationRefused, required_reservation,
)


def _ledger(tmp_path):
    return AccountCashReservations(str(tmp_path / "cache.db"))


def test_second_independent_caller_cannot_spend_the_first_callers_snapshot(tmp_path):
    first = _ledger(tmp_path)
    second = _ledger(tmp_path)  # models the separately-started Node process
    first.reserve(reservation_id="PY:first", account_id="kite-primary", book="penny",
                  broker_tag="AC_FIRST", notional=700, own_uncommitted_cash=1_400, broker_orders=[])
    with pytest.raises(ReservationRefused, match="ACCOUNT_OWN_CASH_INSUFFICIENT"):
        second.reserve(reservation_id="GW:second", account_id="kite-primary", book="momentum",
                       broker_tag="QS_SECOND", notional=700, own_uncommitted_cash=1_400, broker_orders=[])


def test_broker_visible_open_order_is_not_double_subtracted(tmp_path):
    ledger = _ledger(tmp_path)
    reservation = ledger.reserve(reservation_id="PY:first", account_id="kite-primary", book="penny",
                                 broker_tag="AC_FIRST", notional=700, own_uncommitted_cash=1_500, broker_orders=[])
    ledger.mark_dispatch(reservation.reservation_id, broker_order_id="KITE-1", ambiguous=False)
    # F1-A's own-cash snapshot already subtracts the OPEN broker order. The
    # reservation is still durable but must not consume the same ₹ twice.
    next_reservation = ledger.reserve(
        reservation_id="GW:second", account_id="kite-primary", book="momentum", broker_tag="QS_SECOND",
        notional=700, own_uncommitted_cash=800,
        broker_orders=[{"order_id": "KITE-1", "tag": "AC_FIRST", "status": "OPEN",
                        "transaction_type": "BUY"}],
    )
    assert next_reservation.available_after >= 0


def test_unknown_or_partial_evidence_retains_the_commitment_and_only_zero_fill_releases(tmp_path):
    ledger = _ledger(tmp_path)
    reservation = ledger.reserve(reservation_id="PY:first", account_id="kite-primary", book="penny",
                                 broker_tag="AC_FIRST", notional=700, own_uncommitted_cash=2_000, broker_orders=[])
    ledger.mark_dispatch(reservation.reservation_id, broker_order_id="KITE-1", ambiguous=True)
    assert not ledger.release_zero_fill(reservation.reservation_id, broker_order_id="OTHER",
                                        terminal_status="CANCELLED", filled_quantity=0)
    assert not ledger.release_zero_fill(reservation.reservation_id, broker_order_id="KITE-1",
                                        terminal_status="CANCELLED", filled_quantity=1)
    assert ledger.release_zero_fill(reservation.reservation_id, broker_order_id="KITE-1",
                                    terminal_status="CANCELLED", filled_quantity=0)


def test_reserve_includes_calculated_charges_and_one_percent_fill_buffer():
    total, charges, buffer = required_reservation(1_000)
    assert charges > 0
    assert buffer == 10
    assert total == pytest.approx(1_000 + charges + buffer)
