"""
[PENNY-DAILY-ATTRIBUTION-TEST 2026-06-25] Tests for penny_daily_attribution.

These tests pin:
- Empty day -> "0 trades today" message
- Single winner -> win rate 100%, P&L positive
- Mixed winners/losers -> correct counts + P&L + win rate
- Worst/best trade computed correctly
- Date filtering is correct (today only, not yesterday)
- Open CNC positions are counted separately
- r_multiple parsed from notes when present
"""
import os
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta

import pytest


def _seed_db(path: str, rows: list, today_iso: str, open_positions: int = 0):
    """Create a minimal bankroll_ledger + positions schema with the
    given closed-trade rows + open-position count for today_iso.

    rows = [(ticker, pnl, notes, days_ago)]
        days_ago=0 means today, 1 means yesterday, etc.
    """
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS bankroll_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                event_type TEXT,
                ticker TEXT,
                pnl REAL,
                bankroll_before REAL,
                bankroll_after REAL,
                source TEXT,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT, status TEXT, source TEXT
            );
        """)
        for ticker, pnl, notes, days_ago in rows:
            ts_dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
            ts = ts_dt.isoformat()
            con.execute(
                "INSERT INTO bankroll_ledger "
                "(timestamp, event_type, ticker, pnl, bankroll_before, bankroll_after, source, notes) "
                "VALUES (?, 'TRADE_CLOSED', ?, ?, ?, ?, 'PENNY', ?)",
                (ts, ticker, pnl, 0.0, pnl, notes or ""),
            )
        for i in range(open_positions):
            con.execute(
                "INSERT INTO positions (ticker, status, source) VALUES (?, 'OPEN', 'PENNY')",
                (f"OPEN-{i}",),
            )


# ---- empty-day tests -------------------------------------------------

def test_empty_day_message(tmp_path):
    from penny_daily_attribution import build_daily_attribution
    db = str(tmp_path / "test.db")
    _seed_db(db, [], today_iso="2026-06-25")
    body = build_daily_attribution(db)
    assert "0 trades today" in body
    assert "0 open CNC positions" in body


# ---- single-winner ---------------------------------------------------

def test_single_winner(tmp_path):
    from penny_daily_attribution import build_daily_attribution
    db = str(tmp_path / "test.db")
    _seed_db(db, [
        ("AAA", 150.0, "r=1.5", 0),
    ], today_iso="2026-06-25")
    body = build_daily_attribution(db)
    assert "Trades: 1" in body
    assert "Winners: 1" in body
    assert "Losers: 0" in body
    assert "+Rs 150" in body
    assert "Win rate: 100.0%" in body
    assert "Best: AAA Rs +150" in body


# ---- mixed winners/losers ------------------------------------------

def test_mixed_day_metrics(tmp_path):
    from penny_daily_attribution import build_daily_attribution
    db = str(tmp_path / "test.db")
    _seed_db(db, [
        ("AAA", 200.0, "r=2.0", 0),
        ("BBB", -80.0, "r=-0.8", 0),    # loss
        ("CCC", 50.0, "r=0.5", 0),
        ("DDD", -30.0, "r=-0.3", 0),    # loss
        ("EEE", 0.0, "", 0),            # scratch
    ], today_iso="2026-06-25")
    body = build_daily_attribution(db)
    assert "Trades: 5" in body
    assert "Winners: 2" in body       # AAA + CCC
    assert "Losers: 2" in body        # BBB + DDD
    assert "Scratch: 1" in body       # EEE
    assert "+Rs 140" in body          # 200 - 80 + 50 - 30 + 0 = 140
    assert "Best: AAA Rs +200" in body
    assert "Worst: BBB Rs -80" in body


# ---- date filtering --------------------------------------------------

def test_only_today_counted(tmp_path):
    """Yesterday's trades should not appear in today's attribution."""
    from penny_daily_attribution import build_daily_attribution
    db = str(tmp_path / "test.db")
    _seed_db(db, [
        ("TODAY-WIN", 100.0, "", 0),
        ("YESTERDAY-WIN", 999.0, "", 1),   # should NOT count
        ("DAY-BEFORE-WIN", 888.0, "", 2),  # should NOT count
    ], today_iso="2026-06-25")
    body = build_daily_attribution(db)
    assert "Trades: 1" in body
    assert "TODAY-WIN" in body
    assert "YESTERDAY-WIN" not in body
    assert "DAY-BEFORE-WIN" not in body


# ---- source filtering (strict separation) --------------------------

def test_only_penny_source_counted(tmp_path):
    """Nifty / momentum trades should not appear in the penny attribution."""
    from penny_daily_attribution import build_daily_attribution
    db = str(tmp_path / "test.db")
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS bankroll_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, event_type TEXT, ticker TEXT,
                pnl REAL, bankroll_before REAL, bankroll_after REAL,
                source TEXT, notes TEXT
            );
        """)
        now = datetime.now(timezone.utc).isoformat()
        # Penny trade
        con.execute(
            "INSERT INTO bankroll_ledger VALUES (NULL, ?, 'TRADE_CLOSED', 'PENNY-WIN', 100, 0, 100, 'PENNY', '')",
            (now,),
        )
        # Nifty swing trade
        con.execute(
            "INSERT INTO bankroll_ledger VALUES (NULL, ?, 'TRADE_CLOSED', 'NIFTY-WIN', 500, 0, 500, 'SYSTEM', '')",
            (now,),
        )
        # Momentum trade
        con.execute(
            "INSERT INTO bankroll_ledger VALUES (NULL, ?, 'TRADE_CLOSED', 'MOM-WIN', 200, 0, 200, 'MOMENTUM', '')",
            (now,),
        )
    body = build_daily_attribution(db)
    assert "Trades: 1" in body
    assert "PENNY-WIN" in body
    assert "NIFTY-WIN" not in body
    assert "MOM-WIN" not in body


# ---- r_multiple parsing --------------------------------------------

def test_r_multiple_parsed_from_notes(tmp_path):
    from penny_daily_attribution import build_daily_attribution
    db = str(tmp_path / "test.db")
    _seed_db(db, [
        ("AAA", 150.0, "entry=12.0 sl=11.5 t1=12.5 r=1.5", 0),
        ("BBB", 50.0, "r=0.5", 0),
    ], today_iso="2026-06-25")
    body = build_daily_attribution(db)
    assert "Avg R: 1.0" in body    # (1.5 + 0.5) / 2 = 1.0


def test_r_multiple_handles_missing(tmp_path):
    """Trades without r= in notes should not crash the avg-R calculation."""
    from penny_daily_attribution import build_daily_attribution
    db = str(tmp_path / "test.db")
    _seed_db(db, [
        ("AAA", 100.0, "", 0),
        ("BBB", 50.0, "r=1.0", 0),
    ], today_iso="2026-06-25")
    body = build_daily_attribution(db)
    assert "Trades: 2" in body
    # Only BBB has r_multiple -> avg = 1.0
    assert "Avg R: 1.0" in body


# ---- open CNC positions ---------------------------------------------

def test_open_cnc_positions_counted_separately(tmp_path):
    """Open CNC positions are shown in a separate line, not in P&L."""
    from penny_daily_attribution import build_daily_attribution
    db = str(tmp_path / "test.db")
    _seed_db(db, [
        ("AAA", 100.0, "", 0),
    ], today_iso="2026-06-25", open_positions=2)
    body = build_daily_attribution(db)
    assert "Trades: 1" in body
    assert "+Rs 100" in body
    assert "Open CNC positions (held overnight): 2" in body


# ---- structured metrics ---------------------------------------------

def test_compute_daily_metrics_structured(tmp_path):
    from penny_daily_attribution import compute_daily_metrics
    db = str(tmp_path / "test.db")
    _seed_db(db, [
        ("AAA", 200.0, "r=2.0", 0),
        ("BBB", -100.0, "r=-1.0", 0),
    ], today_iso="2026-06-25")
    m = compute_daily_metrics(db)
    assert m.trade_count == 2
    assert m.winners == 1
    assert m.losers == 1
    assert m.scratch == 0
    assert m.total_pnl == 100.0
    assert m.win_rate == 50.0
    assert m.avg_r_multiple == 0.5   # (2.0 + -1.0) / 2
    assert m.best_trade.ticker == "AAA"
    assert m.worst_trade.ticker == "BBB"
    assert m.has_data is True


def test_compute_daily_metrics_empty(tmp_path):
    from penny_daily_attribution import compute_daily_metrics
    db = str(tmp_path / "test.db")
    _seed_db(db, [], today_iso="2026-06-25")
    m = compute_daily_metrics(db)
    assert m.trade_count == 0
    assert m.total_pnl == 0.0
    assert m.has_data is False
    assert m.win_rate == 0.0
    assert m.avg_r_multiple == 0.0
    assert m.best_trade is None
    assert m.worst_trade is None


# ---- message format constraints ------------------------------------

def test_message_under_1000_chars(tmp_path):
    """Telegram limit. We cap at 1000 chars to be safe."""
    from penny_daily_attribution import build_daily_attribution
    db = str(tmp_path / "test.db")
    rows = [(f"T{i:03d}", 100.0 if i % 2 else -50.0, "r=1.0", 0)
            for i in range(15)]
    _seed_db(db, rows, today_iso="2026-06-25", open_positions=1)
    body = build_daily_attribution(db)
    assert len(body) < 1000, f"Body is {len(body)} chars: {body!r}"
