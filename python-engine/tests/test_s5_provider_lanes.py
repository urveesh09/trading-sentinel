"""S5b: bounded bulk provider lane and exact-leg-first research collection.

Production (September 28-October 1) showed the momentum screener's ~500
per-ticker fetches queueing ~50 waiters on the shared 3/s limiter for about
four minutes every quarter hour.  Research quote collection, F&O DR snapshots
and penny scans waited behind them.  These tests pin the ordering contract:
normal work is admitted ahead of bulk, bulk cannot starve, management keeps
its S2 priority, and research observes exact retained legs before the
optional ladder can consume the deadline.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime
from types import SimpleNamespace

import pytest
import pytz

from kite_client import RateLimiter, provider_lane

IST = pytz.timezone("Asia/Kolkata")


async def _queue(limiter, admitted, specs):
    """Queue ``(name, priority)`` waiters in order and return their tasks."""
    async def request(name, priority):
        await limiter.acquire(priority=priority)
        admitted.append(name)

    tasks = []
    for name, priority in specs:
        tasks.append(asyncio.create_task(request(name, priority)))
        await asyncio.sleep(0)
    return tasks


@pytest.mark.asyncio
async def test_normal_request_is_not_queued_behind_bulk_backlog():
    limiter = RateLimiter(rate=200.0, burst=1)
    await limiter.acquire()
    admitted = []
    bulk = await _queue(limiter, admitted, [(f"bulk-{i}", "bulk") for i in range(30)])
    normal = await _queue(limiter, admitted, [("research", "normal")])
    await asyncio.gather(*bulk, *normal)
    # Pre-S5b ordering would admit the research request after ~30 waiters.
    assert admitted.index("research") <= 1


@pytest.mark.asyncio
async def test_bulk_is_not_starved_by_sustained_normal_work():
    limiter = RateLimiter(rate=200.0, burst=1, normal_burst=3)
    await limiter.acquire()
    admitted = []
    tasks = await _queue(limiter, admitted, [("bulk-0", "bulk")])
    tasks += await _queue(limiter, admitted, [(f"normal-{i}", "normal") for i in range(10)])
    await asyncio.gather(*tasks)
    assert admitted.index("bulk-0") <= 3


@pytest.mark.asyncio
async def test_management_still_preempts_normal_and_bulk_with_bounded_fairness():
    limiter = RateLimiter(rate=200.0, burst=1, management_burst=2)
    await limiter.acquire()
    admitted = []
    tasks = await _queue(limiter, admitted, [("bulk-0", "bulk"), ("normal-0", "normal")])
    tasks += await _queue(limiter, admitted, [(f"management-{i}", "management") for i in range(4)])
    await asyncio.gather(*tasks)
    # Order *within* one lane is not FIFO-guaranteed; the lane contract is.
    assert all(name.startswith("management-") for name in admitted[:2])
    # After the management burst a lower lane is admitted, normal first.
    assert admitted[2] == "normal-0"


@pytest.mark.asyncio
async def test_management_yields_to_bulk_when_only_bulk_waits():
    """S2 fairness is preserved for the screener when no normal work waits."""
    limiter = RateLimiter(rate=200.0, burst=1, management_burst=2)
    await limiter.acquire()
    admitted = []
    tasks = await _queue(limiter, admitted, [("bulk-0", "bulk")])
    tasks += await _queue(limiter, admitted, [(f"management-{i}", "management") for i in range(5)])
    await asyncio.gather(*tasks)
    assert admitted.index("bulk-0") <= 2


@pytest.mark.asyncio
async def test_without_bulk_waiters_ordering_is_unchanged_from_s2():
    limiter = RateLimiter(rate=200.0, burst=1, management_burst=2)
    await limiter.acquire()
    admitted = []
    tasks = await _queue(limiter, admitted, [(f"normal-{i}", "normal") for i in range(3)])
    tasks += await _queue(limiter, admitted, [(f"management-{i}", "management") for i in range(2)])
    await asyncio.gather(*tasks)
    assert set(admitted[:2]) == {"management-0", "management-1"}
    assert admitted[2].startswith("normal-")


@pytest.mark.asyncio
async def test_cancelled_bulk_waiter_is_removed():
    limiter = RateLimiter(rate=200.0, burst=1)
    await limiter.acquire()
    cancelled = asyncio.create_task(limiter.acquire(priority="bulk"))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    await asyncio.wait_for(limiter.acquire(), timeout=0.2)
    assert limiter._waiting == {"management": 0, "normal": 0, "bulk": 0}


@pytest.mark.asyncio
async def test_provider_lane_labels_tasks_created_in_scope_and_resets():
    limiter = RateLimiter(rate=200.0, burst=1)
    await limiter.acquire()
    seen = []
    original = limiter._lane_turn

    def spy():
        seen.append(dict(limiter._waiting))
        return original()

    limiter._lane_turn = spy
    with provider_lane("bulk"):
        task = asyncio.create_task(limiter.acquire())
    await task
    assert any(snapshot["bulk"] == 1 for snapshot in seen)
    seen.clear()
    await limiter.acquire()  # outside the scope: default normal lane
    assert all(snapshot["bulk"] == 0 for snapshot in seen)
    assert any(snapshot["normal"] == 1 for snapshot in seen)
    with provider_lane("bulk"):
        seen.clear()
        await limiter.acquire(priority="management")  # explicit priority wins
    assert any(snapshot["management"] == 1 for snapshot in seen)


def test_unknown_provider_lane_is_rejected():
    with pytest.raises(ValueError):
        with provider_lane("urgent"):
            pass


@pytest.mark.asyncio
async def test_timed_documented_quote_reports_limiter_and_transport(tmp_path):
    from unittest.mock import MagicMock
    from kite_client import KiteClient

    client = KiteClient(str(tmp_path / "cache.db"))
    client.limiter = RateLimiter(rate=200.0, burst=10)

    async def get(_url, **_kwargs):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"data": {"NFO:NIFTYFUT": {"last_price": 100.0}}}
        return response

    client.client.get = get
    result, timing = await client.get_quote_by_instruments_with_timing({7: "NFO:NIFTYFUT", 8: "NFO:OTHER"})
    assert result == {7: {"last_price": 100.0}}
    assert timing["outcome"] == "PARTIAL" and timing["attempt_count"] == 1
    assert timing["limiter_wait_sec"] >= 0 and timing["transport_sec"] >= 0
    assert await client.get_quote_by_instruments({7: "NFO:NIFTYFUT"}) == {7: {"last_price": 100.0}}
    await client.client.aclose()


class _Archive:
    def __init__(self, root):
        self.root = root
        self.events = []
        self.runs = []

    def finalize_prior_days(self, _day):
        return []

    def append(self, event):
        self.events.append(event)
        return True

    def record_collection_run(self, result, **_kwargs):
        self.runs.append(dict(result))
        return {"result": dict(result)}


@pytest.mark.asyncio
async def test_exact_active_leg_survives_a_ladder_deadline(tmp_path, monkeypatch):
    import research_quote_collector as collector
    from config import settings
    from fno_models import Contract, OptionType
    from research_leg_subscriptions import ResearchLegSubscriptionStore

    now = IST.localize(datetime(2026, 9, 23, 10, 0))
    expiry = date(2026, 9, 30)
    future = Contract(101, "NIFTYFUT", "NIFTY", expiry, 0.0, "FUT", 75)
    active_leg = Contract(102, "NIFTY30SEP25100CE", "NIFTY", expiry, 25100.0, "CE", 75)
    ladder = {
        (25000.0, OptionType.CE): Contract(201, "NIFTY30SEP25000CE", "NIFTY", expiry, 25000.0, "CE", 75),
        (25000.0, OptionType.PE): Contract(202, "NIFTY30SEP25000PE", "NIFTY", expiry, 25000.0, "PE", 75),
    }
    book = SimpleNamespace(
        ready=lambda _day: True, front_future=lambda _day: future, option_expiries=[expiry],
        strikes_window=lambda _forward, _window: [25000.0],
        option=lambda _expiry, strike, option_type: ladder.get((strike, option_type)),
    )
    archive = _Archive(tmp_path)
    calls = []
    cancelled = asyncio.Event()

    class Kite:
        access_token = "test-token"

        async def get_quote(self, tokens):
            calls.append({int(token) for token in tokens})
            if len(calls) > 1:
                try:
                    await asyncio.Event().wait()  # the optional ladder stalls
                finally:
                    cancelled.set()
            return {int(token): {"instrument_token": int(token), "last_price": 25000.0,
                                 "depth": {"buy": [{"price": 99, "quantity": 75}],
                                           "sell": [{"price": 101, "quantity": 75}]}}
                    for token in tokens}

    async def is_trading_day(_date, _db_path):
        return True

    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_COLLECTION_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_UNDERLYINGS", "NIFTY")
    monkeypatch.setattr(settings, "RESEARCH_QUOTE_RUNTIME_CAP_SEC", 0.2)
    monkeypatch.setattr(settings, "RESEARCH_COMPRESSED_RETENTION_DAYS", 7)
    monkeypatch.setattr(settings, "RESEARCH_ACTIVE_LEG_MAX_TOKENS", 10)
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.setattr(collector, "_quote_archive", lambda: archive)
    monkeypatch.setattr(collector, "get_instruments_for", lambda _name: book)
    monkeypatch.setattr(collector, "_fair_collection_order", lambda _now: ["NIFTY"])
    store = ResearchLegSubscriptionStore(tmp_path)
    store.register(decision_id="s5b-exact-leg", exchange="NFO", contracts=[active_leg],
                   management_deadline=now.replace(hour=15, minute=15), registered_at=now)
    monkeypatch.setitem(sys.modules, "main", SimpleNamespace(kite=Kite(), is_trading_day=is_trading_day))

    result = await asyncio.wait_for(collector.research_quote_collection_tick(now), timeout=1.0)

    # The exact leg travelled with the reference; the ladder re-reads the
    # future but never re-requests the already observed exact leg.
    assert calls[0] == {101, 102}
    assert calls[1] == {101, 201, 202}
    assert cancelled.is_set()
    index = result["indices"]["NIFTY"]
    assert index["collection_state"] == "provider_deadline_exceeded"
    assert index["active_leg_received_tokens"] == [102]
    assert [event["contract"]["instrument_token"] for event in archive.events] == ["102"]
    assert "active_selected_leg decision=s5b-exact-leg" in archive.events[0]["selection_reason"]
    assert {"underlying": "NIFTY", "reason": "provider_deadline_exceeded",
            "stage": "quote_batch", "tokens": 3} in result["gaps"]
    assert not [gap for gap in result["gaps"] if gap.get("reason", "").startswith("active_leg_")]
    assert result["runtime_capped"] is True
    stages = [(row["stage"], row.get("timing_state"), row.get("outcome")) for row in result["provider_timing"]]
    assert stages == [("reference_and_active_legs", "UNAVAILABLE", None),
                      ("quote_batch", "PARTIAL_UNKNOWN", "DEADLINE_EXCEEDED")]
    readiness = store.readiness(now=now)["per_index"]["NIFTY"]
    assert readiness["missing_packets"] == 0
