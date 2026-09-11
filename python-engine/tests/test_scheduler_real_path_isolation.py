"""Fault-injection evidence against actual collection/lifecycle code paths."""
from datetime import datetime
from types import SimpleNamespace
import asyncio

import pytest
import pytz


IST = pytz.timezone("Asia/Kolkata")


@pytest.mark.asyncio
async def test_active_lifecycle_is_not_starved_by_real_slow_quote_provider(tmp_path, monkeypatch):
    import research_quote_collector as collector
    from config import settings
    from fno_models import Contract
    from partner_orchestrator import partner_manual_advisory_lifecycle_tick

    now = IST.localize(datetime(2026, 9, 10, 10, 0))
    contract = Contract(1, "NIFTYFUT", "NIFTY", now.date(), 0, "FUT", 75)
    book = SimpleNamespace(ready=lambda _day: True, front_future=lambda _day: contract)
    entered, release = asyncio.Event(), asyncio.Event()

    class Archive:
        def finalize_prior_days(self, _day): pass
        def append(self, _event): pass
        def record_collection_run(self, _result, **_kwargs): pass

    class Kite:
        access_token = "present"
        async def get_quote(self, tokens):
            entered.set()
            await release.wait()
            return {int(token): {"last_price": 25000, "instrument_token": int(token),
                "depth": {"buy": [{"price": 99, "quantity": 75}], "sell": [{"price": 101, "quantity": 75}]}}
                for token in tokens}

    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_COLLECTION_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_UNDERLYINGS", "NIFTY")
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_SHADOW_ENABLED", False)
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.setattr(collector, "_quote_archive", lambda: Archive())
    monkeypatch.setattr(collector, "_select_contracts", lambda *_args: [(contract, "fixture")])
    collection = asyncio.create_task(collector.collect_rest_quote_snapshot(Kite(), now_ist=now, books={"NIFTY": book}))
    await entered.wait()
    # This invokes the real advisory lifecycle/SQLite path while the real
    # provider-await boundary is saturated. No shared queue may hold it.
    await asyncio.wait_for(partner_manual_advisory_lifecycle_tick(now), timeout=.25)
    release.set()
    result = await collection
    assert result["collected"] == 1
    assert result["stage_durations_sec"]["provider_quote"] >= 0
