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


# ---- [STRUCTURAL-VIABILITY 2026-07-26] ------------------------------------
# A paper book whose smallest possible trade costs more than the whole account
# can never be promoted, no matter how good its paper record looks -- and its
# paper record is not evidence about anything the account could have done.
#
# F&O is the live case: the cheapest single NIFTY lot this book ever traded was
# Rs 5,967 against a Rs 5,000 account. Its Rs 250,000 notional allocation also
# inflated the drawdown budget to Rs 62,500 (12.5x the real account), so
# Rs 10,841 of paper losses still read as "within budget". The check therefore
# compares one lot against REAL capital, never against the notional allocation.

def _seed_fno_positions(db_path, rows):
    """rows: (source, entry_premium, lot_size)."""
    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE IF NOT EXISTS fno_positions "
        "(source TEXT, entry_premium REAL, lot_size INTEGER)"
    )
    con.executemany("INSERT INTO fno_positions VALUES (?,?,?)", rows)
    con.commit()
    con.close()


def test_unaffordable_lot_blocks_promotion(tmp_path):
    """One lot dearer than the whole account -> structurally_unaffordable."""
    from config import settings
    db = str(tmp_path / "cache.db")
    # 100 profitable paper trades: clears every statistical bar on its own.
    _seed(db, [("FNO_PAPER", 50.0, 1) for _ in range(100)])
    lot_cost = settings.INITIAL_BANKROLL + 1000.0      # unaffordable by construction
    _seed_fno_positions(db, [("FNO_PAPER", lot_cost / 65.0, 65)])

    fp = {s["key"]: s
          for s in asyncio.run(promotion_report(db))["strategies"]}["fno_paper"]
    assert fp["expectancy"] > 0                        # the stats are fine...
    assert fp["verdict"] == "not_ready"                # ...and it still cannot go live
    assert any("structurally_unaffordable" in r for r in fp["blocking_reasons"])
    assert fp["min_viable_trade"] == pytest.approx(lot_cost)


def test_affordable_lot_does_not_block(tmp_path):
    """A lot that fits inside the account must not trip the gate."""
    from config import settings
    db = str(tmp_path / "cache.db")
    _seed(db, [("FNO_PAPER", 50.0, 1) for _ in range(100)])
    _seed_fno_positions(db, [("FNO_PAPER", (settings.INITIAL_BANKROLL / 4) / 65.0, 65)])

    fp = {s["key"]: s
          for s in asyncio.run(promotion_report(db))["strategies"]}["fno_paper"]
    assert not any("structurally_unaffordable" in r for r in fp["blocking_reasons"])
    assert fp["verdict"] == "ready_for_live"


def test_equity_books_have_no_lot_floor(tmp_path):
    """Equity can always buy one share -- no structural floor applies."""
    db = str(tmp_path / "cache.db")
    _seed(db, [("EDGE_PAPER", 10.0, 1) for _ in range(100)])
    ep = {s["key"]: s
          for s in asyncio.run(promotion_report(db))["strategies"]}["penny_edge_paper"]
    assert ep["min_viable_trade"] is None
    assert ep["verdict"] == "ready_for_live"


def test_missing_fno_history_is_not_treated_as_unaffordable(tmp_path):
    """Absence of data is not evidence of unaffordability."""
    db = str(tmp_path / "cache.db")
    _seed(db, [("FNO_PAPER", 50.0, 1) for _ in range(100)])   # no fno_positions table
    fp = {s["key"]: s
          for s in asyncio.run(promotion_report(db))["strategies"]}["fno_paper"]
    assert fp["min_viable_trade"] is None
    assert not any("structurally_unaffordable" in r for r in fp["blocking_reasons"])
