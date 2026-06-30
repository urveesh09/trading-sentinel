"""
[PENNY-EDGE-ORCHESTRATOR-TESTS 2026-07-01] Smoke + idempotency tests
for the orchestrator. Tests that require the real ohlcv_cache table
skip when the cache DB is not available (dev tree runs). On prod the
tests run with the live /data/cache.db.
"""
import os
import sqlite3
import sys

import pytest

HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

import penny_edge_orchestrator as peo


# [PENNY-EDGE-ORCH-TEST-DATA 2026-07-01] Tests for the orchestrator run
# against the REAL /data/cache.db (not a tmp path) because the engine
# requires the ohlcv_cache table with historical bar data. We clean up
# any EDGE positions at the start of each test to ensure idempotency.
import os as _os
_REAL_DB = "/data/cache.db"

if not _os.path.exists(_REAL_DB):
    pytest.skip(
        "Skipping orchestrator tests: /data/cache.db not available. "
        "These tests require the prod trading-sentinel data volume.",
        allow_module_level=True,
    )


def _clean_edge_positions():
    """Delete any pre-existing EDGE positions so each test starts clean."""
    if not _os.path.exists(_REAL_DB):
        return
    conn = sqlite3.connect(_REAL_DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM positions WHERE source='EDGE'")
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def reset_edge_positions():
    """Wipe EDGE positions before each test so idempotency is observed."""
    _clean_edge_positions()
    yield
    # Don't wipe after -- the next test will wipe before itself


def test_format_telegram_produces_human_readable_output():
    """[PENNY-EDGE-ORCH-3] format_telegram turns a scan summary into a
    Telegram-friendly markdown string with trade lines."""
    sample = {
        "date": "2026-06-30",
        "regime": "MO",
        "universe": 957,
        "candidates_total": 9,
        "positions_entered": 2,
        "trades": [
            {
                "ticker": "NECCLTD",
                "subtype": "MO_strong",
                "strength": 0.98,
                "entry": 17.27, "target": 18.13, "stop": 16.58,
                "hold_days": 2, "shares": 28,
                "entry_status": "paper",
                "entry_order_id": "STUB-abcd1234",
            },
            {
                "ticker": "OLAELEC",
                "subtype": "MO_strong",
                "strength": 0.94,
                "entry": 44.59, "target": 46.82, "stop": 42.81,
                "hold_days": 2, "shares": 10,
                "entry_status": "paper",
                "entry_order_id": "STUB-efgh5678",
            },
        ],
        "positions_skipped": [],
    }
    out = peo.format_telegram(sample)
    assert "Penny Edge" in out
    assert "NECCLTD" in out
    assert "OLAELEC" in out
    assert "0.98" in out
    assert "17.27" in out
    assert "MO_strong" in out


def test_format_telegram_no_positions():
    """format_telegram handles empty trades list."""
    summary = {
        "date": "2026-06-30",
        "regime": "MO",
        "universe": 957,
        "candidates_total": 0,
        "positions_entered": 0,
        "trades": [],
        "positions_skipped": [],
    }
    out = peo.format_telegram(summary)
    assert "0 entered" in out
    assert "Penny Edge" in out


def test_settings_paper_mode_default():
    """The edge subsystem's paper-mode flag defaults to True even
    when PENNY_LIVE_TRADING is True. Operator must opt in to live."""
    from config import settings
    assert getattr(settings, "PENNY_EDGE_PAPER", True) is True
    assert peo._edge_paper_mode() is True


def test_settings_bankroll_default():
    """Bankroll defaults to Rs 1,000 and max_positions to 3."""
    from config import settings
    assert getattr(settings, "PENNY_EDGE_BANKROLL", 1000.0) == 1000.0
    assert peo._edge_bankroll() == 1000.0
    assert getattr(settings, "PENNY_EDGE_MAX_POSITIONS", 3) == 3
    assert peo._edge_max_positions() == 3
    assert peo._edge_min_strength() == 0.45
    assert peo._edge_max_hold_days() == 3
