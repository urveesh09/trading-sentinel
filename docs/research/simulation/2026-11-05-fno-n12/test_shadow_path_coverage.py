from datetime import datetime, timedelta
from types import SimpleNamespace

from shadow_path_coverage import path
from fno_exit_rules import IST


AT = IST.localize(datetime(2026, 9, 14, 10))


def leg(at=AT):
    return SimpleNamespace(direction="LONG", entry_underlying=1000, stop_underlying=960,
                           target_underlying=1080, atr_at_entry=20, entry_premium=100,
                           premium_stop=75, entry_time=at.isoformat(), best_underlying=1000,
                           best_premium=None, trail_active=0, trail_stop_underlying=None)


def packets(at, *, bid=95, depth=65, future=1000):
    return {at: SimpleNamespace(bid=bid, bid_quantity=depth)}, {at: SimpleNamespace(ltp=future)}


def test_early_native_stop_can_resolve_before_any_later_quote_gap():
    when = AT + timedelta(seconds=65)
    bids, futures = packets(when, future=959)
    out = path(AT, leg(), "N11_EFF", 65, bids, futures)
    assert out == {"status": "resolved_at_sampled_clock", "exit_reason": "underlying_stop",
                   "exit_at": when.isoformat(), "max_gap_sec": 65.0, "looks": 1}


def test_insufficient_depth_cannot_hide_gap_before_later_stop_quote():
    early = AT + timedelta(seconds=60)
    late = AT + timedelta(seconds=125)
    bids, futures = packets(early, future=959, depth=64)
    second_bid, second_future = packets(late, future=959)
    out = path(AT, leg(), "N11_EFF", 65, bids | second_bid, futures | second_future)
    assert out["status"] == "held_gap" and out["gap_sec"] == 125.0
    assert out["last_verified"] == AT.isoformat() and out["looks"] == 0


def test_eff_clock_requires_the_contiguous_one_lot_path():
    bids, futures = {}, {}
    for minute in range(1, 31):
        at = AT + timedelta(minutes=minute)
        bid, future = packets(at, bid=99)
        bids.update(bid)
        futures.update(future)
    out = path(AT, leg(), "N11_EFF", 65, bids, futures)
    assert out["exit_reason"] == "time_stop" and out["looks"] == 30
    assert out["exit_at"] == (AT + timedelta(minutes=30)).isoformat()


def test_hard_flat_uses_only_same_packet_and_can_override_minimum_spacing():
    entry = AT.replace(hour=15, minute=9, second=30)
    at = entry + timedelta(seconds=35)
    bids, futures = packets(at)
    result = path(entry, leg(entry), "N11_EFF", 65, bids, futures)
    assert result["exit_reason"] == "hard_flat_1510"
    missing = path(entry, leg(entry), "N11_EFF", 65, bids, {})
    assert missing["status"] == "no_qualified_exit_or_flat_bid" and missing["looks"] == 0
