"""Independent regressions for the proposed Penny clock correction."""
import pytest

import penny_auction_forward as f
from config import settings
from tests.test_penny_auction_forward import at, quote, phase, read, smart, DAY, NEXT


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PENNY_AUCTION_FORWARD_ENABLED", True)
    monkeypatch.setattr(settings, "PENNY_SMART_V3_ENABLED", True)
    monkeypatch.setattr(settings, "PENNY_SMART_V3_BANKROLL", 2000.)
    if hasattr(settings, "PENNY_SMART_AUCTION_ENTRIES_ENABLED"):
        monkeypatch.setattr(settings, "PENNY_SMART_AUCTION_ENTRIES_ENABLED", True)
    return str(tmp_path / "cache.db")


def test_missing_decision_cannot_become_complete_profit_after_later_closed_trade(cache):
    smart(cache)
    phase(cache, "MATCH", {}, "09:12:00")
    f.capture_smart(cache, {"AAA": quote(day=NEXT)}, {"AAA": (2e6, 1e5)}, {"AAA": 10000}, at("09:07:00", NEXT))
    for name, clock, packet in (
        ("MATCH", "09:12:00", quote("09:12:00", trade="09:11:00", day=NEXT)),
        ("MORNING", "09:30:00", quote("09:30:00", day=NEXT)),
        ("POST_BASE", "15:51:00", quote("15:51:00", price=20.5, volume=20000, day=NEXT)),
        ("POST_END", "16:03:00", quote("16:03:00", trade="15:59:00", price=20.5, volume=40000, day=NEXT)),
    ):
        phase(cache, name, {"AAA": packet}, clock, NEXT)
    result = f.comparison(cache)
    for variant in f.SMART:
        row = result["variants"][variant]
        assert row["closed"] == 1 and row["no_evidence"] == 1
        assert row["closed_modeled_net_subtotal"] > 0
        assert row["complete_modeled_net"] is None
        assert row["capital_path_complete"] is False


def test_positive_volume_with_no_later_trade_is_inconsistent_not_zero_capacity():
    q = quote("15:59:00", trade="15:50:00", price=20., volume=30000)
    amount, reason = f.later_volume(q, at("16:03:00"), {"at": at("15:51:00").isoformat(), "price": 20., "volume": 20000})
    assert amount is None and reason == "volume_trade_clock_inconsistent"


def test_later_trade_without_increasing_volume_is_not_valid_zero_capacity():
    q = quote("15:59:00", trade="15:58:00", price=20., volume=20000)
    amount, reason = f.later_volume(q, at("16:03:00"), {"at": at("15:51:00").isoformat(), "price": 20., "volume": 20000})
    assert amount is None and reason == "volume_trade_clock_inconsistent"


def test_pre_matching_trade_stamp_cannot_be_treated_as_verified_auction_fill(cache):
    smart(cache)
    phase(cache, "MATCH", {"AAA": quote("09:08:05", trade="09:08:00")}, "09:12:00")
    assert all(r["status"] == f.NO_EVIDENCE for r in read(cache))


def test_valid_matching_packet_may_be_older_than_live_quote_ttl(cache):
    smart(cache)
    phase(cache, "MATCH", {"AAA": quote("09:10:10", trade="09:10:05")}, "09:12:00")
    assert all(r["status"] == "OPEN" for r in read(cache))


def test_unverified_smart_source_keeps_observer_but_does_not_create_orders(cache, monkeypatch):
    monkeypatch.setattr(f, "smart_entries_enabled", lambda: False, raising=False)
    smart(cache)
    assert read(cache) == []
    view = f.comparison(cache)["smart_preopen_price"]
    assert view["quotes"] == 1 and view["moved_from_previous_close"] == 1
    assert view["entry_enabled"] is False and view["indicative_price_verified"] is False


@pytest.mark.asyncio
async def test_idle_morning_job_expires_missed_match_without_requesting_quotes(cache):
    smart(cache)
    result = await f.collect(object(), "MORNING", cache, now=at("09:30:00"))
    assert result["status"] == "idle"
    assert all(r["status"] == f.NO_EVIDENCE for r in read(cache))


def test_expiring_missing_intents_does_not_release_an_open_position(cache):
    smart(cache)
    phase(cache, "MATCH", {"AAA": quote("09:12:00", trade="09:11:00")}, "09:12:00")
    with f.store(cache) as c:
        before = f.free_cash(c, f.SMART[0])
        f.expire(c, at("09:03:00", NEXT))
        assert f.free_cash(c, f.SMART[0]) == before and before < 20
        assert all(r["status"] == "OPEN" for r in f.rows(c))
