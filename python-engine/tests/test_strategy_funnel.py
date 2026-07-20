"""
[STRATEGY-FUNNEL 2026-07-20] Tests for analytics.strategy_funnel -- the
unified per-strategy activity + P&L heartbeat (Phase 1.1 of the activation
plan). The existing gate_funnel_report is momentum-only; this must compose
penny + momentum activity with per-source live-vs-paper P&L from the ledger,
so a dead/passive strategy (e.g. penny 0-accepts) is impossible to hide.
"""
import asyncio
import sqlite3

import pytest

from analytics import strategy_funnel, format_strategy_funnel

DAY = "2026-07-20"


def _seed(db_path):
    con = sqlite3.connect(db_path)
    c = con.cursor()
    # Minimal schemas -- only the columns the funnel reads.
    c.execute("CREATE TABLE bankroll_ledger (source TEXT, pnl REAL, timestamp TEXT, event_type TEXT)")
    c.execute("CREATE TABLE positions (source TEXT, status TEXT)")
    c.execute("CREATE TABLE fno_positions (source TEXT, status TEXT)")
    c.execute("CREATE TABLE momentum_signals (scanned_at TEXT, accepted INT, reject_reason TEXT)")
    c.execute("CREATE TABLE penny_signals (scanned_at TEXT, leg TEXT, accepted INT, reject_reason TEXT)")
    c.execute("CREATE TABLE fno_signals (evaluated_at TEXT, accepted INT, reject_reason TEXT)")

    # P&L for the day, per source (unified ledger).
    c.executemany(
        "INSERT INTO bankroll_ledger VALUES (?,?,?,?)",
        [
            ("MOMENTUM",   -1.75,    f"{DAY}T08:57:00Z", "TRADE_CLOSED"),
            ("SYSTEM",      9.03,    f"{DAY}T10:00:00Z", "TRADE_CLOSED"),
            ("EDGE_PAPER", -1612.89, f"{DAY}T09:30:00Z", "TRADE_CLOSED"),
            ("FNO_PAPER",  -1620.80, f"{DAY}T09:45:00Z", "TRADE_CLOSED"),
            ("MOMENTUM",    0.0,     "2026-07-19T08:00:00Z", "TRADE_CLOSED"),  # other day, ignored
        ],
    )
    # Momentum activity: 5 evals, 1 accept, 4 rejects.
    c.executemany(
        "INSERT INTO momentum_signals VALUES (?,?,?)",
        [(f"{DAY}T09:20:00+05:30", 1, "")]
        + [(f"{DAY}T09:20:00+05:30", 0, "no_recent_vwap_crossover") for _ in range(3)]
        + [(f"{DAY}T09:20:00+05:30", 0, "insufficient_intraday_candles")],
    )
    # Penny breakout (MIS): 3 evals, 0 accepts -- the passivity we must surface.
    c.executemany(
        "INSERT INTO penny_signals VALUES (?,?,?,?)",
        [(f"{DAY}T11:00:00+05:30", "MIS", 0, "quote_unavailable"),
         (f"{DAY}T11:00:00+05:30", "MIS", 0, "quote_unavailable"),
         (f"{DAY}T11:00:00+05:30", "MIS", 0, "intraday_fetch_failed")],
    )
    # An open momentum position (CLOSED_T1 counts as open-ish per the tracker).
    c.execute("INSERT INTO positions VALUES ('MOMENTUM','CLOSED_T1')")
    con.commit()
    con.close()


def test_strategy_funnel_composes_activity_and_pnl(tmp_path):
    db = str(tmp_path / "cache.db")
    _seed(db)
    data = asyncio.run(strategy_funnel(db, day_iso=DAY))

    assert data["day"] == DAY
    by_key = {s["key"]: s for s in data["strategies"]}

    # Momentum: activity + P&L both surfaced.
    mom = by_key["momentum"]
    assert mom["evals"] == 5 and mom["accepts"] == 1
    assert mom["pnl_today"] == -1.75
    assert mom["open_positions"] == 1
    assert mom["mode"] == "live"
    assert any("vwap" in r["reason"] for r in mom["top_rejects"])

    # Penny breakout: 3 scans, 0 accepts -- dead, and its reject reasons are
    # now SPECIFIC (post the evaluator-None fix), not opaque.
    pb = by_key["penny_breakout"]
    assert pb["evals"] == 3 and pb["accepts"] == 0
    assert any(r["reason"] == "quote_unavailable" for r in pb["top_rejects"])

    # Swing has no scan log -> P&L-only row, still counted.
    swing = by_key["swing"]
    assert swing["activity_tracked"] is False
    assert swing["pnl_today"] == 9.03

    # Live vs paper split: momentum(-1.75)+swing(9.03) live; edge/fno paper.
    assert data["totals"]["live_pnl"] == pytest.approx(7.28)
    assert data["totals"]["paper_pnl"] == pytest.approx(-3233.69)


def test_format_strategy_funnel_renders(tmp_path):
    db = str(tmp_path / "cache.db")
    _seed(db)
    data = asyncio.run(strategy_funnel(db, day_iso=DAY))
    text = format_strategy_funnel(data)
    assert "Strategy funnel" in text
    assert "Intraday Momentum" in text
    assert "Penny Breakout" in text
    assert "quote_unavailable" in text
    assert "paper" in text and "live" in text


def test_empty_day_is_all_zeros_not_error(tmp_path):
    db = str(tmp_path / "cache.db")
    _seed(db)
    data = asyncio.run(strategy_funnel(db, day_iso="2020-01-01"))
    assert data["totals"] == {"live_pnl": 0.0, "paper_pnl": 0.0}
    assert all(s["evals"] == 0 and s["pnl_today"] == 0.0 for s in data["strategies"])
