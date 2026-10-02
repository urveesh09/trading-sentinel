"""S4 wiring: passive paper paths ride the research collector's existing request.

End to end with the real collector, capture, adapter and v1 study: a paper
admission subscribes its path; each minute the research tick attaches the
subscribed equity to its *existing* first quote request (no extra request);
verified envelopes are written by one bounded background writer; the adapter
builds a packet whose closing quote is the first observation at or after
15:15 IST (real provider time, never re-stamped); the v1 study completes.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import sys
from types import SimpleNamespace

import pytest
import pytz

IST = pytz.timezone("Asia/Kolkata")


def _db(tmp_path):
    from tests.test_momentum_paper import _db as make_db
    return make_db(tmp_path)


class _Archive:
    def __init__(self, root):
        self.root = root
        self.events = []

    def finalize_prior_days(self, _day):
        return []

    def append(self, event):
        self.events.append(event)
        return True

    def record_collection_run(self, result, **_kwargs):
        return {"result": dict(result)}


class _Kite:
    """Real-API-shaped double: one documented full-quote call per request."""

    access_token = "fixture"

    def __init__(self, clock, price_at):
        self.clock, self.price_at, self.requests = clock, price_at, []

    async def get_quote_by_instruments_with_timing(self, request):
        self.requests.append(dict(request))
        now = self.clock()
        data = {}
        for token, key in request.items():
            if key.startswith("NSE:"):
                data[token] = {"instrument_token": 7, "last_price": self.price_at(now),
                               "timestamp": now.strftime("%Y-%m-%d %H:%M:%S")}
            else:
                data[token] = {"instrument_token": token, "last_price": 25000.0,
                               "depth": {"buy": [], "sell": []}}
        return data, {"outcome": "COMPLETE", "limiter_wait_sec": 0.0}


def _book(future):
    return SimpleNamespace(ready=lambda _d: True, front_future=lambda _d: future, option_expiries=[],
                           strikes_window=lambda _f, _w: [], option=lambda *_a: None)


@pytest.fixture
def wired(tmp_path, monkeypatch):
    import research_quote_collector as collector
    from config import settings
    from fno_models import Contract
    db = _db(tmp_path)
    for name, value in {"RESEARCH_ARCHIVE_ENABLED": True, "RESEARCH_QUOTE_COLLECTION_ENABLED": True,
                        "RESEARCH_ARCHIVE_UNDERLYINGS": "NIFTY", "RESEARCH_ARCHIVE_PATH": str(tmp_path / "research"),
                        "RESEARCH_RESERVED_FREE_BYTES": 0, "DB_PATH": db,
                        "MOMENTUM_PAPER_PATH_CAPTURE_ENABLED": True, "MOMENTUM_PAPER_ENABLED": True}.items():
        monkeypatch.setattr(settings, name, value)
    archive = _Archive(tmp_path / "research")
    monkeypatch.setattr(collector, "_quote_archive", lambda: archive)
    monkeypatch.setattr(collector, "_path_write_task", None)
    future = Contract(101, "NIFTYFUT", "NIFTY", datetime(2026, 9, 30).date(), 0.0, "FUT", 75)
    return SimpleNamespace(collector=collector, db=db, books={"NIFTY": _book(future)}, settings=settings)


async def _tick(wired, kite, now):
    result = await wired.collector.collect_rest_quote_snapshot(kite, now_ist=now, books=wired.books)
    task = wired.collector._path_write_task
    if task is not None:
        await task
    return result


def test_subscribed_path_rides_existing_request_and_completes_the_study(tmp_path, wired):
    from momentum_paper import open_momentum_paper_positions
    from momentum_paper_path_adapter import build_momentum_paper_exit_study_packet
    import momentum_exit_study as study

    entry_at = IST.localize(datetime(2026, 9, 25, 14, 50, 10))
    clock = {"now": entry_at}
    kite = _Kite(lambda: clock["now"], lambda now: 100.0 + (now - entry_at).total_seconds() / 3600)

    async def scenario():
        opened = await open_momentum_paper_positions(
            wired.db, [{"ticker": "ACME", "close": 100.0, "stop_loss": 98.0, "target_1": 104.0,
                        "target_2": 104.0, "regime": "REGIME_1_NORMAL", "vwap": 99.5}],
            entry_at.astimezone(timezone.utc))
        assert opened == ["ACME"]
        results = []
        tick = IST.localize(datetime(2026, 9, 25, 14, 50, 25))
        while tick <= IST.localize(datetime(2026, 9, 25, 15, 16, 25)):
            clock["now"] = tick
            results.append(await _tick(wired, kite, tick))
            tick += timedelta(minutes=1)
        return results

    import research_quote_collector as collector_module

    class _ScenarioClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"].astimezone(tz) if tz else clock["now"]

    # Receipt time comes from the collector's wall clock; align it with the
    # simulated session so provider-to-receipt delay is realistic (0 s).
    original = collector_module.datetime
    collector_module.datetime = _ScenarioClock
    try:
        results = asyncio.run(scenario())
    finally:
        collector_module.datetime = original
    # The tick's existing two requests (reference, then ladder) are unchanged
    # in number; the equity rides only inside the first, with the future.
    assert len(kite.requests) == 2 * len(results)
    firsts, ladders = kite.requests[0::2], kite.requests[1::2]
    assert all("NSE:ACME" in request.values() and 101 in request for request in firsts[:-1])
    assert all("NSE:ACME" not in request.values() for request in ladders)
    assert all(result["momentum_paper_paths"]["write"] == "scheduled" for result in results[:-1])
    adapted = build_momentum_paper_exit_study_packet(wired.db)
    assert adapted["status"] == "COMPLETE", adapted
    packet = adapted["packet"]
    assert packet["deadline_quote_policy"] == study.DEADLINE_FIRST_WITHIN_GAP
    closing = packet["quotes"][-1]["observed_at"]
    assert closing == IST.localize(datetime(2026, 9, 25, 15, 15, 25)).astimezone(timezone.utc).isoformat()
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    report = study.build_momentum_exit_study(path)
    pair = report["pairs"][0]
    assert pair["status"] == "COMPLETE"
    assert pair["baseline"]["exit_at"] == IST.localize(datetime(2026, 9, 25, 15, 15, 25)).isoformat()
    assert report["evidence_contract"]["deadline_quote_policy"] == study.DEADLINE_FIRST_WITHIN_GAP


def test_no_subscription_or_disabled_capture_adds_nothing_to_the_request(tmp_path, wired, monkeypatch):
    now = IST.localize(datetime(2026, 9, 25, 11, 0, 25))
    kite = _Kite(lambda: now, lambda _now: 100.0)
    result = asyncio.run(_tick(wired, kite, now))
    assert "momentum_paper_paths" not in result
    assert all(not key.startswith("NSE:") for key in kite.requests[0].values())
    monkeypatch.setattr(wired.settings, "MOMENTUM_PAPER_PATH_CAPTURE_ENABLED", False)
    from momentum_paper import open_momentum_paper_positions
    asyncio.run(open_momentum_paper_positions(
        wired.db, [{"ticker": "ACME", "close": 100.0, "stop_loss": 98.0, "target_1": 104.0,
                    "target_2": 104.0, "regime": "REGIME_1_NORMAL", "vwap": 99.5}],
        now.astimezone(timezone.utc) - timedelta(minutes=5)))
    result = asyncio.run(_tick(wired, _Kite(lambda: now, lambda _now: 100.0), now))
    assert "momentum_paper_paths" not in result


def test_busy_writer_drops_the_batch_as_a_counted_gap_without_waiting(wired):
    collector = wired.collector

    class _Pending:
        def done(self):
            return False

    collector._path_write_task = _Pending()
    now = datetime(2026, 9, 25, 5, 0, tzinfo=timezone.utc)
    outcome = collector._schedule_paper_path_write(
        {-1: {"last_price": 100.0, "timestamp": "2026-09-25 10:30:00"}}, {-1: "NSE:ACME"}, now)
    assert outcome == {"instruments": 1, "observations": 1, "invalid_or_missing": 0,
                       "write": "skipped_writer_busy"}
    outcome = collector._schedule_paper_path_write({-1: {"last_price": 100.0}}, {-1: "NSE:ACME"}, now)
    assert outcome["invalid_or_missing"] == 1 and outcome["write"] == "none"


def test_one_incomplete_lifecycle_does_not_block_other_paths(tmp_path):
    from tests.test_momentum_paper import _envelope
    from momentum_paper import open_momentum_paper_positions, record_momentum_paper_path_observations
    from momentum_paper_path_adapter import build_momentum_paper_exit_study_packet
    db = _db(tmp_path)
    entry_at = datetime(2026, 9, 25, 9, 20, tzinfo=timezone.utc)
    sig = lambda ticker: {"ticker": ticker, "close": 100.0, "stop_loss": 80.0, "target_1": 140.0,
                          "target_2": 140.0, "regime": "REGIME_1_NORMAL", "vwap": 99.5}
    assert asyncio.run(open_momentum_paper_positions(db, [sig("GOOD"), sig("GAPPY")], entry_at)) == ["GOOD", "GAPPY"]
    observations = []
    current = entry_at + timedelta(seconds=30)
    while current <= datetime(2026, 9, 25, 9, 45, 30, tzinfo=timezone.utc):
        for ticker in ("GOOD", "GAPPY"):
            if ticker == "GAPPY" and current.minute in (30, 31, 32, 33, 34, 35):
                continue  # a six-minute hole in one path only
            observations.append({"ticker": ticker, "ltp": 100.0, "provider_observed_at": current.isoformat(),
                                 "receipt_at": current.isoformat(), "source_packet": _envelope(ticker, 100.0, current)})
        current += timedelta(minutes=1)
    assert asyncio.run(record_momentum_paper_path_observations(db, observations)) == len(observations)
    result = build_momentum_paper_exit_study_packet(db)
    assert result["status"] == "COMPLETE"
    assert [entry["ticker"] for entry in result["packet"]["entries"]] == ["GOOD"]
    assert [item["reason"].split(":")[0] for item in result["unavailable_entries"]] == ["quote_gap_or_order_invalid"]
