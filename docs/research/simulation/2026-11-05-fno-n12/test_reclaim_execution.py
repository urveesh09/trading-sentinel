from dataclasses import replace
from datetime import timedelta

import pytest

from test_shared_control import NOW, observation
from fno_models import Contract, ContractQuote
from prior_range_reclaim import Signal
from reclaim_execution import RangeSleeve


AT = NOW.replace(second=0)
NORMAL = "REGIME_1_NORMAL"


def entry(*, short=False, at=NOW, shift=0, depth=65):
    data = observation("NIFTY", at, short=short)
    forward = data.chain.forward + shift
    expiry = data.chain.expiry
    future = Contract(100, "NIFTYFUT", "NIFTY", expiry, 0., "FUT", 65)
    quotes = {key: replace(q, ask_quantity=depth) for key, q in data.chain.quotes.items()}
    snap = replace(data.chain, forward=forward, fut_quote=ContractQuote(future, ltp=forward), quotes=quotes)
    sign = -1 if short else 1
    return Signal(600, "SHORT" if short else "LONG", 25_000, 25_000 - sign * 40, 25_000 + sign * 100), snap


def test_actual_first_quote_risk_and_one_attempt():
    book = RangeSleeve()
    sig, snap = entry(shift=10)
    assert book.enter(sig, AT, snap, NORMAL, is_expiry_day=False) == "reclaim_geometry_at_quote"
    sig, next_snap = entry(at=NOW + timedelta(seconds=1))
    assert book.enter(sig, AT, next_snap, NORMAL, is_expiry_day=False) == "already_attempted"


def test_one_lot_at_native_contract_and_stressed_cash_target():
    for stress in (205., 410.):
        book = RangeSleeve(stress=stress)
        sig, snap = entry(short=True)
        assert book.enter(sig, AT, snap, NORMAL, is_expiry_day=False) == "accepted"
        p = book.position
        assert p.qty == 65 and p.symbol.endswith("PE")
        result, close = book.manage(NOW + timedelta(minutes=1), sig.target,
                                    token=p.token, bid=p.ask + 15, bid_quantity=65)
        assert result == "closed" and close.reason == "midpoint_target"
        assert close.net == pytest.approx(15 * 65 - close.fees - stress)
        assert book.equity == pytest.approx(250_000 + close.net)


def test_target_does_not_override_premium_stop_and_wrong_bid_keeps_position():
    book = RangeSleeve()
    sig, snap = entry()
    assert book.enter(sig, AT, snap, NORMAL, is_expiry_day=False) == "accepted"
    p = book.position
    result, close = book.manage(NOW + timedelta(seconds=10), sig.target,
                                token=p.token, bid=p.premium_stop, bid_quantity=64)
    assert (result, close) == ("held_bid_unavailable", None)
    assert book.position is p
    _, close = book.manage(NOW + timedelta(seconds=20), sig.target,
                           token=p.token, bid=p.premium_stop, bid_quantity=65)
    assert close.reason == 'premium_backstop'
    assert book.coverage_gaps == [(NOW + timedelta(seconds=10), 'held_bid_unavailable')]


def test_late_entry_shallow_ask_and_cross_session_refusal():
    late = RangeSleeve()
    sig, snap = entry(at=AT + timedelta(minutes=1))
    assert late.enter(sig, AT, snap, NORMAL, is_expiry_day=False) == "first_quote_outside_window"
    thin = RangeSleeve()
    sig, snap = entry(depth=64)
    assert thin.enter(sig, AT, snap, NORMAL, is_expiry_day=False) == "ask_depth_unavailable"
    book = RangeSleeve()
    sig, snap = entry()
    assert book.enter(sig, AT, snap, NORMAL, is_expiry_day=False) == "accepted"
    with pytest.raises(ValueError, match="earlier session"):
        book.manage(NOW + timedelta(days=1), None, token=book.position.token, bid=100, bid_quantity=65)


def test_structural_stop_and_hard_flat_priority():
    sig, snap = entry()
    for future, at, expected in (
        (sig.stop, NOW + timedelta(minutes=1), "underlying_stop"),
        (None, NOW.replace(hour=15, minute=10, second=0), "hard_flat"),
    ):
        book = RangeSleeve()
        assert book.enter(sig, AT, snap, NORMAL, is_expiry_day=False) == "accepted"
        p = book.position
        _, close = book.manage(at, future, token=p.token, bid=p.premium_stop, bid_quantity=p.qty)
        assert close.reason == expected


def test_native_expiry_gate_and_full_premium_plus_stress_reserve():
    sig, snap = entry()
    assert RangeSleeve().enter(sig, AT, snap, NORMAL, is_expiry_day=True) == "expiry_day_block"
    assert RangeSleeve(stress=250_000).enter(sig, AT, snap, NORMAL, is_expiry_day=False) == "full_cash_reserve"
