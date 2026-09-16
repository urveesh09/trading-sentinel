"""[WORKFLOW-C.F3 2026-09-16] F-3 from the 2026-09-16
production audit: intraday_cache 0% hit rate was chronic
(4th consecutive audit). The bounded fix surfaces a
``cache_miss_reason`` field on every cache_miss log so
the audit can attribute zero-hit-rate days to one of the
5 known reasons:

  - no_rows: cache has no rows for this ticker/date.
  - insufficient_rows: len(rows) < _min_rows for the window.
  - date_window_miss: last_cached_date < to_date.
  - freshness_exceeded: (now - last_fetched) >= 86400.
  - timestamp_parse_failed: fetched_at couldn't be parsed.

The kite_client uses structlog (not stdlib logging), so
pytest's caplog does not capture its events. We patch
``kite_client.logger`` to a MagicMock with ``.info`` and
``.debug`` call records.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import aiosqlite
import pytest


HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, "..", ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from kite_client import KiteClient  # noqa: E402


def _mock_get(should_fail: bool = True):
    """Build a mock_get that fails if the API is reached."""
    async def mock_get(url, **kwargs):
        if should_fail:
            raise AssertionError("API should not have been called")
        return None
    return mock_get


def _patch_logger(monkeypatch):
    """Patch kite_client.logger to a MagicMock that records
    info / debug / error calls. The tests inspect this list
    for cache_miss entries.
    """
    mock = MagicMock()
    info_calls: list = []
    debug_calls: list = []
    error_calls: list = []
    mock.info.side_effect = lambda *a, **kw: info_calls.append((a, kw))
    mock.debug.side_effect = lambda *a, **kw: debug_calls.append((a, kw))
    mock.error.side_effect = lambda *a, **kw: error_calls.append((a, kw))
    monkeypatch.setattr("kite_client.logger", mock)
    return info_calls, debug_calls, error_calls


def _read_miss_entries(info_calls: list) -> list:
    """Read cache_miss log entries from the patched logger."""
    out = []
    for args, kwargs in info_calls:
        # structlog-style: ``logger.info("event_name", key1=val1, ...)``.
        # The first positional arg is the event name; kwargs carry fields.
        event = args[0] if args else kwargs.get("event")
        if event == "data_fetch" and kwargs.get("event_type") == "cache_miss":
            out.append(kwargs)
    return out


@pytest.mark.asyncio
async def test_no_rows_logs_no_rows_reason(patch_settings, monkeypatch):
    """Empty cache -> ``no_rows`` reason."""
    info_calls, _, _ = _patch_logger(monkeypatch)
    client = KiteClient(patch_settings.DB_PATH)
    client.access_token = "tok"
    client.instrument_cache = {"RELIANCE": "123"}
    await client._init_db()
    client.client.get = _mock_get(should_fail=True)
    try:
        await client.get_historical("RELIANCE", "2025-01-01", "2025-01-10")
    except AssertionError:
        pass
    miss_entries = _read_miss_entries(info_calls)
    assert len(miss_entries) == 1
    assert miss_entries[0]["cache_miss_reason"] == "no_rows"


@pytest.mark.asyncio
async def test_insufficient_rows_logs_reason(patch_settings, monkeypatch):
    """Fewer rows than the window requires -> ``insufficient_rows``."""
    info_calls, _, _ = _patch_logger(monkeypatch)
    client = KiteClient(patch_settings.DB_PATH)
    client.access_token = "tok"
    client.instrument_cache = {"RELIANCE": "123"}
    await client._init_db()
    async with aiosqlite.connect(patch_settings.DB_PATH) as db:
        base_date = datetime(2025, 1, 1)
        for i in range(2):
            d = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
            fetched = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            await db.execute(
                "INSERT INTO ohlcv_cache (ticker, date, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                ("RELIANCE", d, 1000+i, 1010+i, 990+i, 1005+i, 500000, fetched),
            )
        await db.commit()
    client.client.get = _mock_get(should_fail=True)
    try:
        await client.get_historical("RELIANCE", "2025-01-01", "2025-03-01")
    except AssertionError:
        pass
    miss_entries = _read_miss_entries(info_calls)
    assert len(miss_entries) == 1
    assert miss_entries[0]["cache_miss_reason"] == "insufficient_rows"


@pytest.mark.asyncio
async def test_date_window_miss_logs_reason(patch_settings, monkeypatch):
    """Cache rows exist but last_cached_date < to_date -> ``date_window_miss``."""
    info_calls, _, _ = _patch_logger(monkeypatch)
    client = KiteClient(patch_settings.DB_PATH)
    client.access_token = "tok"
    client.instrument_cache = {"RELIANCE": "123"}
    await client._init_db()
    async with aiosqlite.connect(patch_settings.DB_PATH) as db:
        base_date = datetime(2025, 1, 1)
        for i in range(30):
            d = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
            fetched = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            await db.execute(
                "INSERT INTO ohlcv_cache (ticker, date, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                ("RELIANCE", d, 1000+i, 1010+i, 990+i, 1005+i, 500000, fetched),
            )
        await db.commit()
    client.client.get = _mock_get(should_fail=True)
    try:
        await client.get_historical("RELIANCE", "2025-01-01", "2025-02-15")
    except AssertionError:
        pass
    miss_entries = _read_miss_entries(info_calls)
    assert len(miss_entries) == 1
    assert miss_entries[0]["cache_miss_reason"] == "date_window_miss"


@pytest.mark.asyncio
async def test_freshness_exceeded_logs_reason(patch_settings, monkeypatch):
    """Cache rows valid but last_fetched > 24h ago -> ``freshness_exceeded``."""
    info_calls, _, _ = _patch_logger(monkeypatch)
    client = KiteClient(patch_settings.DB_PATH)
    client.access_token = "tok"
    client.instrument_cache = {"RELIANCE": "123"}
    await client._init_db()
    async with aiosqlite.connect(patch_settings.DB_PATH) as db:
        base_date = datetime(2025, 1, 1)
        old_fetched = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        for i in range(30):
            d = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
            await db.execute(
                "INSERT INTO ohlcv_cache (ticker, date, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                ("RELIANCE", d, 1000+i, 1010+i, 990+i, 1005+i, 500000, old_fetched),
            )
        await db.commit()
    client.client.get = _mock_get(should_fail=True)
    try:
        await client.get_historical("RELIANCE", "2025-01-01", "2025-01-30")
    except AssertionError:
        pass
    miss_entries = _read_miss_entries(info_calls)
    assert len(miss_entries) == 1
    assert miss_entries[0]["cache_miss_reason"] == "freshness_exceeded"


@pytest.mark.asyncio
async def test_timestamp_parse_failed_logs_reason(patch_settings, monkeypatch):
    """Malformed fetched_at -> ``timestamp_parse_failed``."""
    info_calls, _, _ = _patch_logger(monkeypatch)
    client = KiteClient(patch_settings.DB_PATH)
    client.access_token = "tok"
    client.instrument_cache = {"RELIANCE": "123"}
    await client._init_db()
    async with aiosqlite.connect(patch_settings.DB_PATH) as db:
        base_date = datetime(2025, 1, 1)
        for i in range(30):
            d = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
            await db.execute(
                "INSERT INTO ohlcv_cache (ticker, date, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                ("RELIANCE", d, 1000+i, 1010+i, 990+i, 1005+i, 500000, "not-a-timestamp"),
            )
        await db.commit()
    client.client.get = _mock_get(should_fail=True)
    try:
        await client.get_historical("RELIANCE", "2025-01-01", "2025-01-30")
    except AssertionError:
        pass
    miss_entries = _read_miss_entries(info_calls)
    assert len(miss_entries) == 1
    assert miss_entries[0]["cache_miss_reason"] == "timestamp_parse_failed"


@pytest.mark.asyncio
async def test_cache_hit_does_not_emit_cache_miss(patch_settings, monkeypatch):
    """On cache hit, no cache_miss log is emitted."""
    info_calls, _, _ = _patch_logger(monkeypatch)
    client = KiteClient(patch_settings.DB_PATH)
    client.access_token = "tok"
    client.instrument_cache = {"RELIANCE": "123"}
    await client._init_db()
    async with aiosqlite.connect(patch_settings.DB_PATH) as db:
        base_date = datetime(2025, 1, 1)
        now_fetched = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        for i in range(65):
            d = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
            await db.execute(
                "INSERT INTO ohlcv_cache (ticker, date, open, high, low, close, volume, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                ("RELIANCE", d, 1000+i, 1010+i, 990+i, 1005+i, 500000, now_fetched),
            )
        await db.commit()
    client.client.get = _mock_get(should_fail=True)
    try:
        await client.get_historical("RELIANCE", "2025-01-01", "2025-03-06")
    except AssertionError:
        pass
    miss_entries = _read_miss_entries(info_calls)
    assert len(miss_entries) == 0
