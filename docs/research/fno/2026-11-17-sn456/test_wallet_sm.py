"""SN468 fixtures for wallet_sm (synthetic cases, labelled as such)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wallet_sm as W  # noqa: E402


def open_lot(cash=30000.0, px=200.0, qty=65):
    L = W.Ledger(cash)
    L.companion_buy(0.0, qty, px + 1)
    L.packet(1, 1.0, 0.5, px - 1, 500, px, 500)
    assert L.comp.state == "OPEN"
    return L


def test_gold_affordable_spends_only_free_cash():
    L = open_lot()
    free = L.cash
    g = L.gold_intent(5.0, free - 10)
    assert g.state == "FILLED" and L.comp.state == "OPEN" and L.cash == 10


def test_gold_during_pending_exit_is_delayed_to_the_real_exit():
    L = open_lot()
    g = L.gold_intent(5.0, 25000.0)
    assert g.state == "WAITING" and L.comp.state == "PENDING_EXIT"
    L.packet(2, 6.0, 5.0, 210, 500, 211, 500)          # stale: no exit, no gold
    assert g.state == "WAITING" and L.comp.state == "PENDING_EXIT"
    L.packet(3, 7.0, 0.4, 210, 500, 211, 500)
    assert L.comp.state == "CLOSED" and g.state == "DELAYED" and g.t_done == 7.0
    assert L.cash >= 0


def test_partial_entry_and_partial_exit():
    L = W.Ledger(30000.0)
    L.companion_buy(0.0, 65, 201)
    L.packet(1, 1.0, 0.2, 199, 10, 200, 30)
    assert L.comp.state == "PARTIAL" and L.comp.held == 30
    L.packet(2, 2.0, 0.2, 199, 10, 200, 50)
    assert L.comp.state == "OPEN" and L.comp.held == 65
    L.companion_exit(3.0)
    L.packet(3, 4.0, 0.2, 205, 40, 206, 5)
    assert L.comp.state == "PARTIAL_EXIT" and L.comp.held == 25
    L.packet(4, 5.0, 0.2, 204, 100, 206, 5)
    assert L.comp.state == "CLOSED" and L.fees_booked == 4


def test_absent_bid_leaves_unresolved_and_gold_missed():
    L = open_lot()
    g = L.gold_intent(5.0, 25000.0)
    L.packet(2, 30.0, 0.3, None, 0, 211, 500)          # no bid
    L.packet(3, 70.0, 0.3, 0.0, 0, 211, 500)           # zero bid, and past the 60 s wait
    assert g.state == "MISSED"
    L.session_end(100.0)
    assert L.comp.state == "UNRESOLVED" and L.comp.held == 65 and L.comp.received == 0.0


def test_duplicate_packet_processed_once():
    L = W.Ledger(30000.0)
    L.companion_buy(0.0, 65, 201)
    L.packet(7, 1.0, 0.2, 199, 10, 200, 30)
    L.packet(7, 1.0, 0.2, 199, 10, 200, 30)
    assert L.comp.held == 30 and L.fees_booked == 1


def test_simultaneous_gold_intent_before_packet():
    L = open_lot()
    g = L.gold_intent(9.0, 25000.0)                     # same timestamp as the packet below: the intent comes first
    L.packet(2, 9.0, 0.1, 210, 500, 211, 500)
    assert g.state == "DELAYED" or g.state == "FILLED"
    assert g.t_done == 9.0 and L.comp.state == "CLOSED"


def test_session_boundary_cancels_unfilled_entry_and_never_invents_a_price():
    L = W.Ledger(30000.0)
    L.companion_buy(0.0, 65, 150)
    L.packet(1, 1.0, 0.2, 199, 10, 200, 30)            # above the limit
    L.session_end(22500.0)
    assert L.comp.state == "CANCELLED" and L.cash == 30000.0


def test_gold_too_large_even_after_exit_is_missed():
    L = open_lot()
    g = L.gold_intent(5.0, 60000.0)
    L.packet(2, 6.0, 0.2, 210, 500, 211, 500)
    assert L.comp.state == "CLOSED" and g.state == "WAITING"
    L.packet(3, 70.0, 0.2, 210, 500, 211, 500)
    assert g.state == "MISSED" and L.cash > 0
