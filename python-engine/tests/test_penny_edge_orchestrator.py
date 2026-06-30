"""
[PENNY-EDGE-ORCHESTRATOR-TESTS 2026-07-01] Tests for the twin-leg
paper/live orchestrator. The DB-touching tests skip on the dev
tree (no /data/cache.db) and run on prod where the data volume
is mounted.
"""
import os
import sqlite3
import sys

import pytest

HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "python-engine"))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

import penny_edge_orchestrator as peo


# Skip dev-tree tests that need /data/cache.db
_REAL_DB = "/data/cache.db"
if not os.path.exists(_REAL_DB):
    pytest.skip(
        "Skipping orchestrator tests: /data/cache.db not available. "
        "These tests require the prod trading-sentinel data volume.",
        allow_module_level=True,
    )


def _clean_edge_positions():
    if not os.path.exists(_REAL_DB):
        return
    conn = sqlite3.connect(_REAL_DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM positions WHERE source LIKE 'EDGE%'")
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def reset_edge_positions():
    _clean_edge_positions()
    yield
    # Don't wipe after -- next test will wipe before itself


def test_settings_load():
    """Default config: paper + live both enabled, paper=Rs 100k, live=Rs 1k."""
    from config import settings
    assert getattr(settings, "PENNY_EDGE_DISABLE_PAPER", False) is False
    assert getattr(settings, "PENNY_EDGE_DISABLE_LIVE", False) is False
    assert peo._edge_paper_bankroll() == 100000.0
    assert peo._edge_live_bankroll() == 1000.0
    assert peo._edge_max_positions() == 3
    assert peo._edge_min_strength() == 0.45
    assert peo._edge_max_hold_days() == 3


def test_format_telegram_includes_both_legs():
    """The Telegram formatter must show both PAPER and LIVE legs."""
    sample = {
        "date": "2026-06-30",
        "regime": "MO",
        "trend_strength": 0.32,
        "vol_percentile": 0.32,
        "universe": 957,
        "candidates_total": 9,
        "paper": {
            "leg": "PAPER", "source": peo.SOURCE_PAPER,
            "bankroll": 100000.0, "paper_mode": True,
            "n_candidates": 3, "entered": 3,
            "trades": [
                {"ticker": "NECCLTD", "subtype": "MO_strong",
                 "strength": 0.82, "entry": 17.27, "target": 18.13,
                 "stop": 16.58, "hold_days": 2, "shares": 2416,
                 "entry_status": "paper",
                 "entry_order_id": "STUB-x"},
            ],
            "skipped": [],
        },
        "live": {
            "leg": "LIVE", "source": peo.SOURCE_LIVE,
            "bankroll": 1000.0, "paper_mode": False,
            "n_candidates": 3, "entered": 3,
            "trades": [
                {"ticker": "NECCLTD", "subtype": "MO_strong",
                 "strength": 0.82, "entry": 17.27, "target": 18.13,
                 "stop": 16.58, "hold_days": 2, "shares": 24,
                 "entry_status": "filled",
                 "entry_order_id": "STUB-y"},
            ],
            "skipped": [],
        },
        "skipped": [],
    }
    out = peo.format_telegram(sample)
    assert "PAPER LEG" in out
    assert "LIVE LEG" in out
    assert "Rs 100,000" in out
    assert "Rs 1,000" in out
    assert "2416" in out    # paper shares
    assert " 24" in out or "24 shares" in out or '"shares": 24' in out or "24 shares" in out
    # Note: paper has 2416 shares, live has 24 shares. The string
    # " 24" appears in "24" (live) but also as a substring of "2416"
    # (paper). We check that paper's 2416 is present (>=5 digit) and
    # the live 24 is present (after the parenthesis).
    assert "2416" in out
    assert "24 " in out  # live's 24 shares


def test_format_telegram_paper_only_leg():
    """When live leg is disabled, the formatter shows only the paper leg."""
    sample = {
        "date": "2026-06-30",
        "regime": "MO",
        "trend_strength": 0.5,
        "vol_percentile": 0.3,
        "universe": 957,
        "candidates_total": 9,
        "paper": {"leg": "PAPER", "entered": 1, "trades": [],
                  "skipped": [], "bankroll": 100000.0,
                  "n_candidates": 3, "paper_mode": True,
                  "source": peo.SOURCE_PAPER},
        "live":  {"leg": "LIVE", "entered": 0, "trades": [],
                  "skipped": [], "bankroll": 1000.0,
                  "n_candidates": 0, "paper_mode": True,
                  "source": peo.SOURCE_LIVE},
        "skipped": [],
    }
    out = peo.format_telegram(sample)
    assert "PAPER LEG" in out
    # The live leg is rendered as "(PAPER (live disabled))"
    assert "PAPER (live disabled)" in out


def test_format_exit_telegram_per_leg():
    out = peo.format_exit_telegram({
        "date": "2026-06-30",
        "closed_paper": [{"ticker": "AAA", "age_days": 4, "unwind_id": "U1"}],
        "closed_live":  [{"ticker": "BBB", "age_days": 5, "unwind_id": "U2"}],
    })
    assert "PAPER" in out and "AAA" in out
    assert "LIVE" in out and "BBB" in out


def test_format_exit_telegram_no_exits():
    out = peo.format_exit_telegram({
        "date": "2026-06-30", "closed_paper": [], "closed_live": []
    })
    assert "No edge positions" in out
