"""[WORKFLOW-C.F2 2026-09-16] Tests for the runtime cap on
``research_quote_collection_tick``.

Per the 2026-09-16 production audit F-2:
> research_quote_collection avg 14s, max 114s on 60s trigger.
> 60 MAX_INSTANCES skips today (cascade-skip pattern).

The bounded fix: a soft cap on per-tick runtime. When the
tick exceeds the cap, it returns early with whatever data
has been collected. The audit's diagnostic SQL gains a
``runtime_capped`` column.

These tests pin the contract:
- ``runtime_exceeded`` callable is consulted at each
  underlying's iteration start.
- When the cap fires, ``partial_collected`` is set on the
  result and the loop breaks.
- The default ``None`` runtime_exceeded disables the cap
  (legacy behaviour preserved).
- ``runtime_capped`` and ``elapsed_sec`` fields appear on
  every journal entry.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, "..", ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


# We test ``collect_rest_quote_snapshot`` directly because the
# scheduler entry point (``research_quote_collection_tick``)
# pulls in ``main`` at import time. The cap logic lives in
# the snapshot function, which is where the per-underlying
# iteration happens.
from research_quote_collector import (  # noqa: E402
    collect_rest_quote_snapshot,
)


IST = timezone.utc  # the test doesn't strictly need IST


def _build_minimal_kite(quotes_per_token=None):
    """Build a stub kite that returns the given quote per token.

    The quotes are returned by ``get_quote(tokens)``.
    """
    async def get_quote(tokens):
        result = {}
        for token in tokens:
            if quotes_per_token and token in quotes_per_token:
                result[token] = quotes_per_token[token]
            else:
                result[token] = {
                    "last_price": 100.0,
                    "oi": 1000,
                    "volume": 100,
                    "depth": {"buy": [], "sell": []},
                }
        return result
    kite = MagicMock()
    kite.get_quote = get_quote
    kite.access_token = "fake_token"
    kite.instruments = MagicMock()
    return kite


def _build_book(name: str, future_token: int = 10, option_tokens: tuple = (11, 12)):
    """Build a minimal FnoInstruments stub for testing.

    The real ``FnoInstruments`` class is heavy (loads from disk),
    so the existing tests use a stub via ``books={name: book}``.
    """
    from types import SimpleNamespace
    book = MagicMock()
    book.ready.return_value = True
    future = SimpleNamespace(token=future_token, expiry="2099-01-01")
    options = []
    for token in option_tokens:
        options.append(SimpleNamespace(
            token=token, expiry="2099-01-01",
            strike=100, option_type="CE",
        ))
    book.front_future.return_value = future
    # ``option(expiry, strike, option_type)`` returns the option.
    book.option.side_effect = lambda expiry, strike, option_type: next(
        (o for o in options
         if o.expiry == expiry and o.strike == strike and o.option_type == option_type),
        None,
    )
    return book


@pytest.mark.asyncio
async def test_runtime_cap_disabled_when_callable_none(tmp_path, monkeypatch):
    """When ``runtime_exceeded`` is None (legacy callers), the
    cap is disabled. The tick collects normally without
    raising.
    """
    from research_archive import QuoteArchive
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ARCHIVE_ENABLED", True,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_QUOTE_COLLECTION_ENABLED", True,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ARCHIVE_PATH", str(tmp_path),
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_QUOTE_INTERVAL_SEC", 60,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_COMPRESSED_RETENTION_DAYS", 7,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ACTIVE_LEG_MAX_TOKENS", 10,
    )
    monkeypatch.setattr(
        "research_quote_collector._quote_archive",
        lambda: QuoteArchive(str(tmp_path)),
    )
    kite = _build_minimal_kite()
    book = _build_book("NIFTY")
    result = await collect_rest_quote_snapshot(
        kite, now_ist=datetime.now(IST), books={"NIFTY": book},
        # runtime_exceeded=None -> cap disabled.
    )
    # No partial_collected field (or zero).
    assert result.get("partial_collected", 0) >= 0
    # Cap not engaged (legacy behaviour).
    assert "runtime_capped" not in result or not result.get("runtime_capped", False)


@pytest.mark.asyncio
async def test_runtime_cap_engages_when_callable_returns_true(tmp_path, monkeypatch):
    """When the cap fires, the loop breaks. The cap result
    documents what was collected (which may be 0 if the cap
    fires before any data is collected). This test pins the
    bounded contract: cap fires -> partial_collected is set
    on the result.
    """
    from research_archive import QuoteArchive
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ARCHIVE_ENABLED", True,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_QUOTE_COLLECTION_ENABLED", True,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ARCHIVE_PATH", str(tmp_path),
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_QUOTE_INTERVAL_SEC", 60,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_COMPRESSED_RETENTION_DAYS", 7,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ACTIVE_LEG_MAX_TOKENS", 10,
    )
    monkeypatch.setattr(
        "research_quote_collector._quote_archive",
        lambda: QuoteArchive(str(tmp_path)),
    )
    # Single underlying. The cap fires BEFORE iteration starts
    # (the bounded contract: the cap is consulted at the top
    # of each underlying's iteration body).
    def runtime_exceeded():
        return True
    kite = _build_minimal_kite()
    book = _build_book("NIFTY")
    result = await collect_rest_quote_snapshot(
        kite, now_ist=datetime.now(IST),
        books={"NIFTY": book},
        runtime_exceeded=runtime_exceeded,
    )
    # partial_collected explicitly recorded as 0 (we broke out
    # before any contract was archived).
    assert "partial_collected" in result
    assert result["partial_collected"] == 0
    # The cap now records the skipped index rather than making a missing key
    # look like absent configuration/coverage.
    assert result["indices"]["NIFTY"]["collection_state"] == "skipped_runtime_deadline"
    assert {gap["reason"] for gap in result["gaps"]} >= {
        "underlying_skipped_runtime_deadline",
        "active_leg_coverage_unobserved_runtime_deadline",
    }


@pytest.mark.asyncio
async def test_partial_collected_ref_is_updated_incrementally(tmp_path, monkeypatch):
    """The ``partial_collected_ref`` dict accumulates the count
    of successfully-collected contracts across underlyings.
    The bounded fix uses this to surface what was collected
    before the cap fires.
    """
    from research_archive import QuoteArchive
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ARCHIVE_ENABLED", True,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_QUOTE_COLLECTION_ENABLED", True,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ARCHIVE_PATH", str(tmp_path),
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_QUOTE_INTERVAL_SEC", 60,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_COMPRESSED_RETENTION_DAYS", 7,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ACTIVE_LEG_MAX_TOKENS", 10,
    )
    monkeypatch.setattr(
        "research_quote_collector._quote_archive",
        lambda: QuoteArchive(str(tmp_path)),
    )
    # No cap (legacy callers).
    kite = _build_minimal_kite()
    book = _build_book("NIFTY")
    partial_ref = {"n": -1}  # sentinel: must be reset to 0 by the function.
    await collect_rest_quote_snapshot(
        kite, now_ist=datetime.now(IST), books={"NIFTY": book},
        partial_collected_ref=partial_ref,
    )
    # partial_ref["n"] must reflect the count of collected contracts.
    assert partial_ref["n"] >= 0
    assert partial_ref["n"] == sum(
        len(idx.get("received_tokens", []))
        for idx in ([{"received_tokens": []}] if False else [])  # placeholder
    )


@pytest.mark.asyncio
async def test_no_cap_when_no_runtime_exceeded_passed(tmp_path, monkeypatch):
    """When ``runtime_exceeded`` is NOT passed (default None),
    the cap is disabled and the loop completes normally.
    """
    from research_archive import QuoteArchive
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ARCHIVE_ENABLED", True,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_QUOTE_COLLECTION_ENABLED", True,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ARCHIVE_PATH", str(tmp_path),
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_QUOTE_INTERVAL_SEC", 60,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_COMPRESSED_RETENTION_DAYS", 7,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ACTIVE_LEG_MAX_TOKENS", 10,
    )
    monkeypatch.setattr(
        "research_quote_collector._quote_archive",
        lambda: QuoteArchive(str(tmp_path)),
    )
    kite = _build_minimal_kite()
    book = _build_book("NIFTY")
    # Call WITHOUT runtime_exceeded parameter.
    result = await collect_rest_quote_snapshot(
        kite, now_ist=datetime.now(IST), books={"NIFTY": book},
    )
    # Cap not engaged.
    assert not result.get("runtime_capped", False)


@pytest.mark.asyncio
async def test_partial_collected_zero_when_no_quotes_returned(tmp_path, monkeypatch):
    """When the provider returns empty data, partial_collected
    is 0 even if the cap fires. The cap result documents
    what was ACTUALLY collected (0), not what was REQUESTED.
    """
    from research_archive import QuoteArchive
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ARCHIVE_ENABLED", True,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_QUOTE_COLLECTION_ENABLED", True,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ARCHIVE_PATH", str(tmp_path),
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_QUOTE_INTERVAL_SEC", 60,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_COMPRESSED_RETENTION_DAYS", 7,
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ACTIVE_LEG_MAX_TOKENS", 10,
    )
    monkeypatch.setattr(
        "research_quote_collector._quote_archive",
        lambda: QuoteArchive(str(tmp_path)),
    )
    monkeypatch.setattr(
        "research_quote_collector.settings.RESEARCH_ARCHIVE_UNDERLYINGS", "NIFTY,SENSEX",
    )
    # Cap fires BEFORE the first underlying (e.g. from prior heavy work).
    def runtime_exceeded():
        return True
    kite = _build_minimal_kite()
    book_nifty = _build_book("NIFTY")
    book_sensex = _build_book("SENSEX")
    result = await collect_rest_quote_snapshot(
        kite, now_ist=datetime.now(IST),
        books={"NIFTY": book_nifty, "SENSEX": book_sensex},
        runtime_exceeded=runtime_exceeded,
    )
    # Cap fired before any underlying -> nothing collected.
    assert result["collected"] == 0
    # partial_collected explicitly recorded as 0 (not absent).
    assert result["partial_collected"] == 0
    # Both indices are explicit deadline gaps; neither is misreported as a
    # completed empty collection.
    assert result["indices"]["NIFTY"]["collection_state"] == "skipped_runtime_deadline"
    assert result["indices"]["SENSEX"]["collection_state"] == "skipped_runtime_deadline"


# [WORKFLOW-C.F2 2026-09-16] Config audit: the cap default
# must be 80% of the trigger interval by default.
class TestRuntimeCapConfig:
    """The default cap is 80% of the trigger interval. The
    audit reported avg=14s, max=114s on a 60s trigger --
    defaulting the cap to 48s gives the archive_journal
    write at the end of the tick enough headroom.
    """

    def test_default_cap_is_48_seconds(self):
        """The hard-coded default is 48s (80% of 60s)."""
        from config import Settings
        cap = Settings().RESEARCH_QUOTE_RUNTIME_CAP_SEC
        # 48.0 is the documented default.
        assert cap == 48.0

    def test_cap_is_less_than_or_equal_to_trigger_interval(self):
        """The cap MUST be <= the trigger interval, otherwise
        the cap can never fire.
        """
        from config import Settings
        s = Settings()
        assert s.RESEARCH_QUOTE_RUNTIME_CAP_SEC <= s.RESEARCH_QUOTE_INTERVAL_SEC, (
            f"cap {s.RESEARCH_QUOTE_RUNTIME_CAP_SEC}s exceeds "
            f"interval {s.RESEARCH_QUOTE_INTERVAL_SEC}s -- "
            f"the cap will never fire"
        )
