"""
Tests for the main.py breadth wiring helpers (Task 7 step 2).

The actual run_screener() body is too tangled to test directly (touches kite,
NIFTY_100_TICKERS, sqlite, regime fetcher, nifty CSV, …). So we extract two
small, pure helpers into main.py and test those in isolation:

    build_breadth_engine(kite, settings) -> Optional[BreadthEngine]
        - Returns None when BREADTH_ENRICHMENT_ENABLED is False.
        - Returns a BreadthEngine when the flag is on + Universe loads.
        - Returns None + logs error when Universe fails to load (fail-soft).

    build_breadth_kwargs(token, breadth_result) -> dict
        - Pulls breadth_pct_above_sma50 + rank for a single token.
        - Returns empty dict (no kwargs) when breadth_result is None / token missing.

These are the smallest pieces needed to wire breadth into the scan loop.
"""

import os
import sys
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


# ─────────────────────────────────────────────────────────────────
# build_breadth_engine
# ─────────────────────────────────────────────────────────────────


def test_build_breadth_engine_returns_none_when_flag_off(monkeypatch, tmp_path):
    """If BREADTH_ENRICHMENT_ENABLED is False, helper must return None — no I/O."""
    from main import build_breadth_engine
    from config import settings

    monkeypatch.setattr(settings, "BREADTH_ENRICHMENT_ENABLED", False)

    # We pass a kite and settings that would otherwise cause the helper to try
    # to load nifty100.json. Because the flag is off, none of that should run.
    fake_kite = MagicMock()
    fake_kite.instrument_cache = {"RELIANCE": 2880257}

    result = build_breadth_engine(fake_kite, settings)
    assert result is None


def test_build_breadth_engine_returns_engine_when_flag_on(monkeypatch, tmp_path):
    """If flag is on + nifty100.json exists, helper returns a BreadthEngine."""
    from main import build_breadth_engine
    from config import settings

    # Write a tiny nifty100.json the helper can load
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "nifty100.json").write_text(json.dumps({
        "as_of_date": "2026-06-14",
        "tickers": [
            {"symbol": "RELIANCE", "instrument_token": None},
            {"symbol": "TCS",      "instrument_token": None},
        ],
    }))
    monkeypatch.setattr(settings, "BREADTH_ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(settings, "BREADTH_DATA_DIR", str(data_dir))

    fake_kite = MagicMock()
    fake_kite.instrument_cache = {"RELIANCE": 2880257, "TCS": 2953217}
    fake_kite.get_historical = AsyncMock(return_value=None)  # shouldn't be called at init

    with patch("main.BreadthEngine") as mock_cls:
        mock_engine = MagicMock()
        mock_cls.return_value = mock_engine
        result = build_breadth_engine(fake_kite, settings)

    assert result is mock_engine, "Helper should return the BreadthEngine instance"
    # The constructor should have been called with the universe and a kite_historical_fn
    assert mock_cls.call_count == 1
    kwargs = mock_cls.call_args.kwargs
    assert "universe" in kwargs
    assert "kite_historical_fn" in kwargs


def test_build_breadth_engine_returns_none_on_universe_load_failure(monkeypatch, tmp_path):
    """If Universe() raises (missing/malformed file), helper returns None and logs."""
    from main import build_breadth_engine
    from config import settings

    # Point the helper at a directory with NO nifty100.json
    data_dir = tmp_path / "empty_data"
    data_dir.mkdir()
    monkeypatch.setattr(settings, "BREADTH_ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(settings, "BREADTH_DATA_DIR", str(data_dir))

    fake_kite = MagicMock()
    fake_kite.instrument_cache = {}

    # Should not raise — should return None
    result = build_breadth_engine(fake_kite, settings)
    assert result is None


# ─────────────────────────────────────────────────────────────────
# build_breadth_kwargs
# ─────────────────────────────────────────────────────────────────


def test_build_breadth_kwargs_returns_empty_dict_when_breadth_unavailable():
    """When breadth_result is None (engine not initialized or Tier 1 cold-start),
    build_breadth_kwargs should return {} so the call site can do **kwargs safely."""
    from main import build_breadth_kwargs

    # No engine
    assert build_breadth_kwargs(12345, None) == {}


def test_build_breadth_kwargs_returns_empty_dict_when_token_missing():
    """When the scan loop sees a token not in the breadth rank_map (e.g. small-cap
    not in Nifty 100), it should pass empty kwargs (treat as neutral)."""
    from main import build_breadth_kwargs

    fake_result = MagicMock()
    fake_result.breadth_pct_above_sma50 = 0.65
    fake_result.rank_map = {111: 0.9, 222: 0.3}  # 12345 is NOT in here

    assert build_breadth_kwargs(12345, fake_result) == {}


def test_build_breadth_kwargs_returns_pct_and_rank_for_known_token():
    """For a known token, return both breadth_pct_above_sma50 and breadth_rank."""
    from main import build_breadth_kwargs

    fake_result = MagicMock()
    fake_result.breadth_pct_above_sma50 = 0.55
    fake_result.rank_map = {12345: 0.82, 67890: 0.30}

    out = build_breadth_kwargs(12345, fake_result)
    assert out == {
        "breadth_pct_above_sma50": 0.55,
        "breadth_rank": 0.82,
    }


def test_build_breadth_kwargs_handles_none_pct():
    """If breadth_pct_above_sma50 is None (degraded path), still return rank only."""
    from main import build_breadth_kwargs

    fake_result = MagicMock()
    fake_result.breadth_pct_above_sma50 = None
    fake_result.rank_map = {12345: 0.75}

    out = build_breadth_kwargs(12345, fake_result)
    assert out == {"breadth_pct_above_sma50": None, "breadth_rank": 0.75}


def test_build_breadth_kwargs_returns_empty_when_token_is_none():
    """When token is None (ticker not in kite.instrument_cache), return {}."""
    from main import build_breadth_kwargs

    fake_result = MagicMock()
    fake_result.breadth_pct_above_sma50 = 0.55
    fake_result.rank_map = {12345: 0.82}

    # This is the common case for tickers Kite doesn't know about
    # (delisted, F&O-only, etc.) — the scan loop passes token=None.
    assert build_breadth_kwargs(None, fake_result) == {}
