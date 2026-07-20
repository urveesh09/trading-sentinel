"""
[STRATEGY-PROMOTION 2026-07-20] Tests for analytics.promotion_report -- the
Phase-3 paper->live gate. A paper strategy is ready_for_live only with enough
trades, positive net-cost expectancy, and drawdown inside budget; live
strategies get a health read. The verdict must be a checked function of the
ledger, never a vibe.
"""
import asyncio
import sqlite3

import pytest

from analytics import promotion_report, format_promotion_report, _max_drawdown


def _seed(db_path, rows):
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE bankroll_ledger (source TEXT, pnl REAL, timestamp TEXT, event_type TEXT)")
    con.executemany(
        "INSERT INTO bankroll_ledger VALUES (?,?,?,?)",
        [(s, p, f"2026-07-{d:02d}T10:00:00Z", "TRADE_CLOSED") for (s, p, d) in rows],
    )
    con.commit()
    con.close()


def test_max_drawdown_peak_to_trough():
    # cum: 100 (peak 100), 40 (dd 60), 90 (dd 10), 30 (dd 70) -> max dd 70
    assert _max_drawdown([100, -60, 50, -60]) == pytest.approx(70.0)
    assert _max_drawdown([]) == 0.0
    assert _max_drawdown([10, 20, 30]) == 0.0   # monotonic up -> no drawdown


def test_promotion_verdicts(tmp_path):
    db = str(tmp_path / "cache.db")
    rows = (
        # EDGE_PAPER: 100 winning paper trades -> clears the bar
        [("EDGE_PAPER", 10.0, 1) for _ in range(100)]
        # FNO_PAPER: 40 trades, net negative -> not_ready (negative expectancy)
        + [("FNO_PAPER", -5.0, 2) for _ in range(40)]
        # MOMENTUM (live): a few winners -> healthy, no min-trade gate for live
        + [("MOMENTUM", 3.0, 3) for _ in range(10)]
    )
    _seed(db, rows)
    data = asyncio.run(promotion_report(db))
    by = {s["key"]: s for s in data["strategies"]}

    ep = by["penny_edge_paper"]
    assert ep["trades"] == 100 and ep["expectancy"] == pytest.approx(10.0)
    assert ep["verdict"] == "ready_for_live"
    assert ep["blocking_reasons"] == []

    fp = by["fno_paper"]
    assert fp["verdict"] == "not_ready"
    assert any("negative_expectancy" in r for r in fp["blocking_reasons"])

    mom = by["momentum"]
    assert mom["mode"] == "live"
    assert mom["verdict"] == "healthy"


def test_provisional_when_bar_met_but_sample_small(tmp_path):
    db = str(tmp_path / "cache.db")
    _seed(db, [("EDGE_PAPER", 8.0, 1) for _ in range(50)])   # 30 <= 50 < 100, positive
    data = asyncio.run(promotion_report(db))
    ep = {s["key"]: s for s in data["strategies"]}["penny_edge_paper"]
    assert ep["verdict"] == "provisional"
    assert ep["blocking_reasons"] == []


def test_insufficient_sample_blocks(tmp_path):
    db = str(tmp_path / "cache.db")
    _seed(db, [("EDGE_PAPER", 8.0, 1) for _ in range(5)])
    data = asyncio.run(promotion_report(db))
    ep = {s["key"]: s for s in data["strategies"]}["penny_edge_paper"]
    assert ep["verdict"] == "not_ready"
    assert any("insufficient_sample" in r for r in ep["blocking_reasons"])


def test_format_renders(tmp_path):
    db = str(tmp_path / "cache.db")
    _seed(db, [("EDGE_PAPER", 10.0, 1) for _ in range(100)])
    text = format_promotion_report(asyncio.run(promotion_report(db)))
    assert "Promotion ladder" in text
    assert "Ready for live:" in text
    assert "Penny Edge (paper)" in text
