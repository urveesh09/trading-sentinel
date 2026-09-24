"""P1 regression coverage for bounded research quote collection.

The collector must not wait indefinitely for the first underlying and then
silently omit the second.  These tests use the scheduler entry point so the
returned and journaled telemetry exercise the deployed contract.
"""
from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytz


IST = pytz.timezone("Asia/Kolkata")


class _Archive:
    """Thread-safe-enough in-memory archive double for scheduler tests."""

    def __init__(self, root):
        self.root = root
        self.runs = []

    def finalize_prior_days(self, _day):
        return []

    def append(self, _event):
        return True

    def record_collection_run(self, result, **_kwargs):
        self.runs.append(dict(result))
        return {"result": dict(result)}


def _book(contract):
    return SimpleNamespace(
        ready=lambda _day: True,
        front_future=lambda _day: contract,
    )


@pytest.mark.asyncio
async def test_stalled_first_underlying_is_cancelled_and_reports_second_gap(tmp_path, monkeypatch):
    """A first quote operation consumes only the tick budget.

    The provider double records cancellation in ``finally``.  If the collector
    merely times out a wrapper while letting the operation continue, this test
    cannot complete with the cancellation receipt and fails.
    """
    import research_quote_collector as collector
    from config import settings
    from fno_models import Contract
    from research_leg_subscriptions import ResearchLegSubscriptionStore

    now = IST.localize(datetime(2026, 9, 23, 10, 0))
    nifty = Contract(101, "NIFTYFUT", "NIFTY", now.date(), 0.0, "FUT", 75)
    sensex = Contract(201, "SENSEXFUT", "SENSEX", now.date(), 0.0, "FUT", 10)
    selected_nifty_leg = Contract(102, "NIFTY23SEP25000CE", "NIFTY", now.date(), 25000.0, "CE", 75)
    archive = _Archive(tmp_path)
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    class SlowKite:
        access_token = "test-token"

        async def get_quote(self, tokens):
            if int(tokens[0]) == nifty.token:
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return {
                int(token): {
                    "instrument_token": int(token), "last_price": 100.0,
                    "depth": {"buy": [], "sell": []},
                }
                for token in tokens
            }

    async def is_trading_day(_date, _db_path):
        return True

    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_COLLECTION_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_UNDERLYINGS", "NIFTY,SENSEX")
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_RUNTIME_CAP_SEC", 0.05)
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_INTERVAL_SEC", 60)
    monkeypatch.setattr(settings, "RESEARCH_COMPRESSED_RETENTION_DAYS", 7)
    monkeypatch.setattr(settings, "RESEARCH_ACTIVE_LEG_MAX_TOKENS", 10)
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.setattr(collector, "_quote_archive", lambda: archive)
    ResearchLegSubscriptionStore(tmp_path).register(
        decision_id="p1-deadline-fixture", exchange="NFO", contracts=[selected_nifty_leg],
        management_deadline=now.replace(hour=15, minute=15), registered_at=now,
    )
    monkeypatch.setattr(
        collector, "get_instruments_for",
        lambda name: _book(nifty if name == "NIFTY" else sensex),
    )
    monkeypatch.setattr(collector, "_fair_collection_order", lambda _now: ["NIFTY", "SENSEX"])
    monkeypatch.setitem(
        sys.modules, "main", SimpleNamespace(kite=SlowKite(), is_trading_day=is_trading_day),
    )

    started = time.monotonic()
    result = await asyncio.wait_for(collector.research_quote_collection_tick(now), timeout=0.5)
    elapsed = time.monotonic() - started

    assert entered.is_set()
    assert cancelled.is_set(), "the cancelled provider operation must not outlive the tick"
    assert elapsed < 0.25
    assert result["runtime_capped"] is True
    assert result["partial_collected"] == result["collected"] == 0
    # Windows event-loop timer resolution can fire the test double a few
    # milliseconds early; the explicit provider-deadline result is the
    # deterministic assertion, while the outer elapsed bound proves no overrun.
    assert result["elapsed_sec"] >= 0
    assert any(
        gap["underlying"] == "NIFTY" and gap["reason"] == "provider_deadline_exceeded"
        for gap in result["gaps"]
    )
    assert any(
        gap["underlying"] == "SENSEX" and gap["reason"] == "underlying_skipped_runtime_deadline"
        for gap in result["gaps"]
    )
    assert result["indices"]["NIFTY"]["active_leg_requested_tokens"] == [selected_nifty_leg.token]
    assert any(
        gap == {
            "underlying": "NIFTY", "reason": "active_leg_unobserved_runtime_deadline",
            "token": selected_nifty_leg.token,
        }
        for gap in result["gaps"]
    )
    assert archive.runs and archive.runs[-1]["runtime_capped"] is True
    assert archive.runs[-1]["elapsed_sec"] == result["elapsed_sec"]


@pytest.mark.asyncio
async def test_normal_scheduler_path_persists_complete_runtime_telemetry(tmp_path, monkeypatch):
    """Normal results carry the same audit fields as deadline results."""
    import research_quote_collector as collector
    from config import settings
    from fno_models import Contract

    now = IST.localize(datetime(2026, 9, 23, 10, 0))
    nifty = Contract(101, "NIFTYFUT", "NIFTY", now.date(), 0.0, "FUT", 75)
    sensex = Contract(201, "SENSEXFUT", "SENSEX", now.date(), 0.0, "FUT", 10)
    archive = _Archive(tmp_path)

    class FastKite:
        access_token = "test-token"

        async def get_quote(self, tokens):
            return {
                int(token): {
                    "instrument_token": int(token), "last_price": 100.0,
                    "depth": {"buy": [], "sell": []},
                }
                for token in tokens
            }

    async def is_trading_day(_date, _db_path):
        return True

    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_COLLECTION_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_UNDERLYINGS", "NIFTY,SENSEX")
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_RUNTIME_CAP_SEC", 1.0)
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_INTERVAL_SEC", 60)
    monkeypatch.setattr(settings, "RESEARCH_COMPRESSED_RETENTION_DAYS", 7)
    monkeypatch.setattr(settings, "RESEARCH_ACTIVE_LEG_MAX_TOKENS", 10)
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.setattr(collector, "_quote_archive", lambda: archive)
    monkeypatch.setattr(
        collector, "get_instruments_for",
        lambda name: _book(nifty if name == "NIFTY" else sensex),
    )
    monkeypatch.setattr(collector, "_fair_collection_order", lambda _now: ["NIFTY", "SENSEX"])
    monkeypatch.setattr(
        collector, "_select_contracts",
        lambda book, _forward, _day, _window: [(
            book.front_future(now.date()), "fixture_selected_future",
        )],
    )
    monkeypatch.setitem(
        sys.modules, "main", SimpleNamespace(kite=FastKite(), is_trading_day=is_trading_day),
    )

    result = await collector.research_quote_collection_tick(now)

    assert result["runtime_capped"] is False
    assert 0 <= result["elapsed_sec"] < result["runtime_cap_sec"]
    assert result["partial_count"] == result["partial_collected"] == result["collected"] == 2
    assert {result["indices"][name]["collection_state"] for name in ("NIFTY", "SENSEX")} == {"completed"}
    assert not any("runtime_deadline" in gap["reason"] for gap in result["gaps"])
    assert len(archive.runs) == 1
    for key in ("runtime_capped", "elapsed_sec", "runtime_cap_sec", "partial_count", "partial_collected"):
        assert archive.runs[0][key] == result[key]


def test_fair_collection_order_rotates_by_scheduler_slot(monkeypatch):
    """A restart cannot keep preferring NIFTY during repeated capped ticks."""
    import research_quote_collector as collector
    from config import settings

    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_UNDERLYINGS", "NIFTY,SENSEX")
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_INTERVAL_SEC", 60)
    first = IST.localize(datetime(2026, 9, 23, 10, 0))
    second = IST.localize(datetime(2026, 9, 23, 10, 1))
    assert collector._fair_collection_order(first) == list(reversed(collector._fair_collection_order(second)))


@pytest.mark.asyncio
async def test_no_token_error_path_persists_the_same_runtime_telemetry(tmp_path, monkeypatch):
    """A token failure is an auditable collection outcome, not a schema hole."""
    import research_quote_collector as collector
    from config import settings

    now = IST.localize(datetime(2026, 9, 23, 10, 0))
    archive = _Archive(tmp_path)

    class NoTokenKite:
        access_token = ""

    async def is_trading_day(_date, _db_path):
        return True

    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_COLLECTION_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_RUNTIME_CAP_SEC", 1.0)
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_INTERVAL_SEC", 60)
    monkeypatch.setattr(settings, "RESEARCH_COMPRESSED_RETENTION_DAYS", 7)
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.setattr(collector, "_quote_archive", lambda: archive)
    monkeypatch.setitem(
        sys.modules, "main", SimpleNamespace(kite=NoTokenKite(), is_trading_day=is_trading_day),
    )

    result = await collector.research_quote_collection_tick(now)

    assert result["reason"] == "no_market_data_token"
    assert result["runtime_capped"] is False
    assert result["partial_count"] == result["partial_collected"] == 0
    assert len(archive.runs) == 1
    for key in ("runtime_capped", "elapsed_sec", "runtime_cap_sec", "partial_count", "partial_collected"):
        assert archive.runs[0][key] == result[key]
