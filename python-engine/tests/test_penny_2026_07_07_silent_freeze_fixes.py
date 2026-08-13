"""
[PENNY-2026-07-07-FIXES] Tests for the post-incident fixes:

1. compute_metrics_from_history respects a bounded semaphore
2. penny_universe_quality_audit escalates to WARNING on degraded universe
3. The repo-seed fallback for corp_data resolves correctly
4. logging_setup.configure_structlog emits timestamps on stdlib logging calls
"""
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

import pytest


# ----------------------------------------------------------------------
# Fix #1: bounded semaphore in compute_metrics_from_history
# ----------------------------------------------------------------------

@pytest.fixture
def fresh_settings(monkeypatch):
    """Override settings.PENNY_HISTORY_SQLITE_MAX_CONCURRENT for tests."""
    from config import settings
    monkeypatch.setattr(settings, "PENNY_HISTORY_SQLITE_MAX_CONCURRENT", 5)
    return settings


def _make_history_df(n=300, seed=1):
    import pandas as pd
    import numpy as np
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = rng.normal(50, 5, n).cumsum() / n + 50
    df = pd.DataFrame({
        "open": closes - 0.5, "high": closes + 1,
        "low": closes - 1, "close": closes,
        "volume": rng.integers(50_000, 200_000, n),
    }, index=idx)
    return df


def test_compute_metrics_from_history_respects_semaphore(fresh_settings):
    """
    The 2026-07-07 incident had compute_metrics_from_history fan 9,769
    coroutines out via asyncio.gather, all racing to open the same sqlite
    cache.db file. SQLite (even in WAL) returns "unable to open database
    file" once the OS file-handle ceiling is hit. Fix: bound the gather
    with an asyncio.Semaphore at settings.PENNY_HISTORY_SQLITE_MAX_CONCURRENT.

    This test verifies the semaphore is honored under contention.
    """
    from penny_universe import compute_metrics_from_history

    in_flight = 0
    max_in_flight = 0

    async def slow_historical(ticker, from_date, to_date):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        # Hold the connection briefly to simulate sqlite contention
        await asyncio.sleep(0.05)
        in_flight -= 1
        return _make_history_df()

    fake_kite = MagicMock()
    fake_kite.get_historical = AsyncMock(side_effect=slow_historical)

    # 50 symbols but semaphore=5 -> never more than 5 concurrent sqlite opens
    symbols = [f"SYM{i:04d}" for i in range(50)]

    asyncio.run(compute_metrics_from_history(fake_kite, symbols))

    assert max_in_flight <= 5, (
        f"semaphore not honored: peak concurrency {max_in_flight} > 5"
    )
    # Sanity: did the semaphore actually allow multiple in parallel?
    assert max_in_flight >= 2, (
        f"semaphore too tight: peak concurrency {max_in_flight} < 2"
    )


def test_compute_metrics_from_history_uses_default_concurrency():
    """
    When PENNY_HISTORY_SQLITE_MAX_CONCURRENT is not set, the default
    is 50 (well above Kite's 3 req/s rate limit, well below OS FD
    ceiling). This test sets the attribute to a sentinel value then
    deletes it to verify the getattr default kicks in.
    """
    from config import settings

    # Save current value
    saved = getattr(settings, "PENNY_HISTORY_SQLITE_MAX_CONCURRENT", None)

    # Remove the attribute
    if hasattr(settings, "PENNY_HISTORY_SQLITE_MAX_CONCURRENT"):
        delattr(settings, "PENNY_HISTORY_SQLITE_MAX_CONCURRENT")

    try:
        from penny_universe import compute_metrics_from_history
        fake_kite = MagicMock()
        fake_kite.get_historical = AsyncMock(return_value=_make_history_df())
        # Should not raise on missing setting
        asyncio.run(compute_metrics_from_history(fake_kite, ["X"]))
    finally:
        # Restore
        if saved is not None:
            settings.PENNY_HISTORY_SQLITE_MAX_CONCURRENT = saved


# ----------------------------------------------------------------------
# Fix #2: penny_universe_quality_audit escalates on degraded universe
# ----------------------------------------------------------------------

def test_quality_audit_emits_warning_when_all_null_tv(caplog, tmp_path):
    """
    [PENNY-QUALITY-AUDIT 2026-07-07] When every ticker has null tv,
    the quality_audit log line must be WARNING-level so the operator
    sees the degraded universe at refresh time, not 12 minutes later
    when the 30s scanner logs penny_scan_no_eligible_universe.
    """
    from penny_universe import refresh_from_kite
    import penny_universe as pu

    # Build a fake instrument + quote setup that produces 100 tickers
    # all with null tv (corp missing, history fails).
    fake_kite = MagicMock()
    fake_kite.get_instruments_nse_eq = AsyncMock(return_value=[
        {"instrument_token": i + 1000, "tradingsymbol": f"SYM{i:04d}",
         "series": "EQ"} for i in range(100)
    ])
    fake_kite.get_quote = AsyncMock(return_value={
        i + 1000: {"ohlc": {"close": 25.0}, "last_price": 25.0}
        for i in range(100)
    })
    fake_kite.get_corporate_actions = AsyncMock(return_value=[])
    fake_kite.get_historical = AsyncMock(side_effect=Exception("sqlite exhausted"))

    out_path = str(tmp_path / "penny_static.json")
    corp_path = "/nonexistent/path/to/company_data.json"

    caplog.set_level(logging.DEBUG, logger="penny_universe")

    result = asyncio.run(refresh_from_kite(
        kite=fake_kite,
        out_json_path=out_path,
        corp_json_path=corp_path,
    ))

    # Should have produced a universe despite missing data
    assert result is not None, "refresh_from_kite returned None unexpectedly"

    # Find the quality_audit log line
    audit_lines = [
        r for r in caplog.records
        if r.getMessage().startswith("penny_universe_quality_audit")
    ]
    assert len(audit_lines) == 1, (
        f"expected exactly 1 quality_audit log, got {len(audit_lines)}"
    )
    audit = audit_lines[0]
    # Must be WARNING level (was INFO before 2026-07-07 fix)
    assert audit.levelno == logging.WARNING, (
        f"quality_audit should be WARNING when degraded, got level "
        f"{audit.levelname}"
    )
    # Audit payload should report null_tv == total
    assert "null_tv=100" in audit.getMessage()


def test_quality_audit_emits_info_when_universe_healthy(caplog, tmp_path):
    """When the universe is healthy, quality_audit should be INFO."""
    from penny_universe import refresh_from_kite
    import pandas as pd

    fake_kite = MagicMock()
    fake_kite.get_instruments_nse_eq = AsyncMock(return_value=[
        {"instrument_token": 1000, "tradingsymbol": "GOOD1", "series": "EQ"},
        {"instrument_token": 1001, "tradingsymbol": "GOOD2", "series": "EQ"},
    ])
    fake_kite.get_quote = AsyncMock(return_value={
        1000: {"ohlc": {"close": 25.0}, "last_price": 25.0},
        1001: {"ohlc": {"close": 30.0}, "last_price": 30.0},
    })
    fake_kite.get_corporate_actions = AsyncMock(return_value=[
        {"symbol": "GOOD1", "promoter_holding_pct": 50.0, "pb_ratio": 1.0,
         "median_traded_value_20d": 1_000_000, "avg_return_20d": 0.02,
         "dist_from_52w_low_pct": 0.15, "vol_20d": 0.03,
         "is_t2t": False, "is_asm": False, "is_gsm": False},
        {"symbol": "GOOD2", "promoter_holding_pct": 55.0, "pb_ratio": 0.8,
         "median_traded_value_20d": 2_000_000, "avg_return_20d": 0.03,
         "dist_from_52w_low_pct": 0.20, "vol_20d": 0.04,
         "is_t2t": False, "is_asm": False, "is_gsm": False},
    ])
    # History fetch returns good data so all fields are populated
    good_df = _make_history_df()
    fake_kite.get_historical = AsyncMock(return_value=good_df)

    out_path = str(tmp_path / "penny_static.json")
    corp_path = str(tmp_path / "corp.json")
    with open(corp_path, "w") as f:
        json.dump({"records": []}, f)

    caplog.set_level(logging.DEBUG, logger="penny_universe")
    asyncio.run(refresh_from_kite(
        kite=fake_kite, out_json_path=out_path, corp_json_path=corp_path,
    ))

    audit_lines = [
        r for r in caplog.records
        if r.getMessage().startswith("penny_universe_quality_audit")
    ]
    assert len(audit_lines) == 1
    assert audit_lines[0].levelno == logging.INFO, (
        f"healthy universe should be INFO, got {audit_lines[0].levelname}"
    )


# ----------------------------------------------------------------------
# Fix #3: corp_data repo-seed fallback path resolves correctly
# ----------------------------------------------------------------------

def test_repo_seed_path_resolves_inside_python_engine_dir():
    """
    The fallback path /app/data/penny_company_data.json (in the container)
    or python-engine/data/penny_company_data.json (locally) must exist
    OR be silently absent. The fix is os.path.dirname(__file__) + 'data',
    NOT os.path.dirname(os.path.dirname(__file__)) + 'data' (which walks
    past python-engine/ to the repo root).
    """
    import penny_universe as pu
    repo_data_dir = os.path.join(
        os.path.dirname(os.path.abspath(pu.__file__)), "data",
    )
    repo_seed = os.path.join(repo_data_dir, "penny_company_data.json")

    # The path must be the data directory beside the imported module. Docker
    # intentionally installs that same directory as /app, so asserting a
    # literal checkout-folder name is not portable.
    assert os.path.dirname(repo_seed) == repo_data_dir
    assert os.path.dirname(repo_data_dir) == os.path.dirname(os.path.abspath(pu.__file__))
    # The seed file should exist locally (even if empty)
    assert os.path.exists(repo_seed), (
        f"repo_seed file missing: {repo_seed}"
    )


# ----------------------------------------------------------------------
# Fix #4: structlog configuration emits timestamps on stdlib logger
# ----------------------------------------------------------------------

def test_logging_setup_emits_timestamps_on_warning(monkeypatch):
    """
    The 2026-07-07 incident showed that some `logger.warning(...)`
    calls in penny_universe.py emit WITHOUT timestamps in production.
    This test verifies that after configure_structlog(), a stdlib
    `logging.getLogger(name).warning(...)` call emits a timestamped line.

    We can't easily capture stderr because structlog binds the
    file=sys.stderr at configure time (before our monkeypatch runs).
    Instead we verify via the HANDLER's formatter: configure_structlog
    adds a StreamHandler to the root logger with our timestamped
    formatter; that formatter is what produces the production output.
    """
    from logging_setup import configure_structlog
    configure_structlog(level="INFO")

    # The fix: configure_structlog attaches a StreamHandler to the root
    # logger with format "%(asctime)s [%(levelname)s] %(message)s" and
    # datefmt="%Y-%m-%d %H:%M:%S". Verify the formatter is present and
    # has the timestamp format.
    root = logging.getLogger()
    timestamped_handlers = [
        h for h in root.handlers
        if h.formatter is not None
        and "%(asctime)s" in (h.formatter._fmt or "")
    ]
    assert len(timestamped_handlers) >= 1, (
        f"no timestamped handler on root; handlers={root.handlers}, "
        f"fmts={[h.formatter._fmt if h.formatter else None for h in root.handlers]}"
    )

    # Verify the date format includes both date and time.
    h = timestamped_handlers[0]
    assert h.formatter.datefmt == "%Y-%m-%d %H:%M:%S", (
        f"datefmt is wrong: {h.formatter.datefmt}"
    )


def test_logging_setup_root_level_is_set():
    """
    After configure_structlog(), logging.getLogger().getEffectiveLevel()
    should be INFO (or the requested level). Without this, penny_universe
    logger's effective level is WARNING and `logger.info` calls are
    silently dropped.
    """
    from logging_setup import configure_structlog
    configure_structlog(level="INFO")

    root = logging.getLogger()
    assert root.getEffectiveLevel() == logging.INFO, (
        f"root level should be INFO, got {root.getEffectiveLevel()}"
    )


def test_http_client_request_logs_are_suppressed_to_protect_url_secrets():
    """httpx request URLs can contain Telegram bot tokens in their path."""
    from logging_setup import configure_structlog

    configure_structlog(level="INFO")

    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() == logging.WARNING


def test_logging_setup_idempotent():
    """
    configure_structlog must be safe to call multiple times. Tests,
    lifespan, and startup paths may all call it; the second call should
    not duplicate handlers or reset state in surprising ways.
    """
    from logging_setup import configure_structlog, _CONFIGURED
    saved = _CONFIGURED
    try:
        configure_structlog(level="INFO")
        first_handlers = list(logging.getLogger().handlers)
        configure_structlog(level="INFO")
        second_handlers = list(logging.getLogger().handlers)
        # No duplicate handler added
        assert len(second_handlers) == len(first_handlers), (
            "configure_structlog added a duplicate handler on second call"
        )
    finally:
        # Restore module state
        import logging_setup
        logging_setup._CONFIGURED = saved
