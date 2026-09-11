from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytz

from fno_models import Contract
from research_leg_subscriptions import ResearchLegSubscriptionStore


IST = pytz.timezone("Asia/Kolkata")


def leg(token=101, symbol="NIFTY26SEP25000CE"):
    return Contract(token, symbol, "NIFTY", date(2026, 9, 24), 25000, "CE", 75)


def test_selected_legs_survive_restart_and_record_missing_coverage(tmp_path):
    now = IST.localize(datetime(2026, 9, 11, 10, 0))
    first = ResearchLegSubscriptionStore(tmp_path)
    assert first.register(decision_id="decision-a", exchange="NFO", contracts=[leg()],
                          management_deadline=now + timedelta(hours=5), master_sha256="a" * 64,
                          registered_at=now) == 1
    # A new process sees the same exact dated contract, not a fresh ATM choice.
    second = ResearchLegSubscriptionStore(tmp_path)
    active, shortfall = second.active(underlying="NIFTY", now=now, capacity=4)
    assert not shortfall and active[0].contract == leg() and active[0].master_sha256 == "a" * 64
    second.record_collection(requested_tokens=[101], received_tokens=[], now=now)
    assert second.readiness(now=now)["per_index"]["NIFTY"]["missing_packets"] == 1


def test_capacity_shortfall_is_explicit_and_expired_legs_are_bounded(tmp_path):
    now = IST.localize(datetime(2026, 9, 11, 10, 0))
    store = ResearchLegSubscriptionStore(tmp_path)
    store.register(decision_id="a", exchange="NFO", contracts=[leg(101)], management_deadline=now + timedelta(minutes=1), registered_at=now)
    store.register(decision_id="b", exchange="NFO", contracts=[leg(102, "NIFTY26SEP25050CE")], management_deadline=now + timedelta(minutes=2), registered_at=now)
    active, shortfall = store.active(underlying="NIFTY", now=now, capacity=1)
    assert [item.contract.token for item in active] == [101]
    assert [item.contract.token for item in shortfall] == [102]
    store.record_collection(requested_tokens=[101], received_tokens=[101], now=now, capacity_shortfall=shortfall)
    assert store.readiness(now=now)["recent_gap_count"] == 1
    result = store.finalize(now=now + timedelta(days=91), evidence_retention_days=90)
    assert result["deleted"] == 2 and result["active"] == 0


@pytest.mark.asyncio
async def test_active_leg_is_collected_when_rolling_contract_master_is_unavailable(tmp_path, monkeypatch):
    import research_quote_collector as collector
    from config import settings

    now = IST.localize(datetime(2026, 9, 11, 10, 0))
    store = ResearchLegSubscriptionStore(tmp_path)
    store.register(decision_id="pinned", exchange="NFO", contracts=[leg()], management_deadline=now + timedelta(hours=5), registered_at=now)
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_COLLECTION_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_UNDERLYINGS", "NIFTY")
    monkeypatch.setattr(settings, "RESEARCH_RESERVED_FREE_BYTES", 0)
    collector._archive = None

    class Kite:
        access_token = "fixture"
        async def get_quote(self, tokens):
            return {int(token): {"instrument_token": int(token), "last_price": 100, "oi": 1000, "volume": 100,
                                 "depth": {"buy": [{"price": 99, "quantity": 75}], "sell": [{"price": 101, "quantity": 75}]}}
                    for token in tokens}

    unavailable_book = SimpleNamespace(ready=lambda _day: False)
    result = await collector.collect_rest_quote_snapshot(Kite(), now_ist=now, books={"NIFTY": unavailable_book})
    assert result["indices"]["NIFTY"]["active_leg_requested_tokens"] == [101]
    assert result["indices"]["NIFTY"]["active_leg_received_tokens"] == [101]
    assert any(gap["reason"] == "fresh_contract_master_unavailable" for gap in result["gaps"])
