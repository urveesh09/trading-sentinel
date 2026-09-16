"""[WORKFLOW-C.F8 2026-09-15] Tests for the
bankroll_ledger TRADE_OPENED entry created when an EDGE
position is opened.

Per the 2026-09-15 production audit F-8: GRAVISSHO
EDGE_PAPER position opened at 09:30 IST but was NEVER
recorded in bankroll_ledger. The EDGE_PAPER pool showed
₹91,244.66 (last update Sept 4) -- opening the position
didn't debit the pool. Day-end reconciliation couldn't
verify the open position existed.

The bounded fix: when an EDGE position is opened, write a
TRADE_OPENED row to bankroll_ledger with pnl=0 (no realised
P&L yet) and a notes field carrying the audit surface
(notional, shares, entry_price, stop_loss, sl_order_id).

The TRADE_OPENED row is purely additive: it does NOT
change division_equity() because pnl=0. The existing
allocation + SUM(pnl) formula is preserved.

These tests use a tmp_path DB so they don't require the
prod /data/cache.db. The existing
test_penny_edge_orchestrator.py skips on dev tree
(no /data/cache.db).
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys

import pytest


# Add the engine directory to sys.path so we can import
# the orchestrator without going through the project root
# conftest.
HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, "..", ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

import penny_edge_orchestrator as peo  # noqa: E402
from performance import init_ledger  # noqa: E402
from position_tracker import init_positions_db  # noqa: E402


def _read_ledger(db_path: str) -> list[dict]:
    """Read all rows from bankroll_ledger as dicts."""
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, timestamp, event_type, ticker, pnl,
                   bankroll_before, bankroll_after, notes, source
            FROM bankroll_ledger
            """
        ).fetchall()
    finally:
        conn.close()
    cols = ["id", "timestamp", "event_type", "ticker", "pnl",
            "bankroll_before", "bankroll_after", "notes", "source"]
    return [dict(zip(cols, r)) for r in rows]


# ─── _write_edge_position writes TRADE_OPENED ───────────────


def test_write_edge_position_writes_trade_opened(tmp_path):
    """[WORKFLOW-C.F8] Calling _write_edge_position
    writes a TRADE_OPENED row to bankroll_ledger. The
    GRAVISSHO bug was that no such row existed; this test
    pins that the fix is in place.
    """
    db_path = str(tmp_path / "cache.db")
    asyncio.run(init_positions_db(db_path))
    asyncio.run(init_ledger(db_path))

    asyncio.run(
        peo._write_edge_position(
            db_path=db_path,
            source=peo.SOURCE_PAPER,
            ticker="GRAVISSHO",
            entry_date_iso="2026-09-15",
            entry_price=46.97,
            shares=971,
            stop_loss=44.50,
            target_1=52.00,
            regime_at_entry="",
            sl_order_id="sl-abc-123",
        )
    )

    rows = _read_ledger(db_path)
    opened = [r for r in rows if r["event_type"] == "TRADE_OPENED"]
    assert len(opened) == 1, f"expected 1 TRADE_OPENED row, got {len(opened)}"
    row = opened[0]
    assert row["ticker"] == "GRAVISSHO"
    assert row["source"] == peo.SOURCE_PAPER
    assert row["pnl"] == 0.0


def test_write_edge_position_trade_opened_pnl_zero_preserves_equity(tmp_path):
    """[WORKFLOW-C.F8] The TRADE_OPENED row has pnl=0, so
    division_equity (= allocation + SUM(pnl)) is
    UNCHANGED. This is the load-bearing invariant: a
    -notional debit would break position sizing for
    subsequent opens.
    """
    db_path = str(tmp_path / "cache.db")
    asyncio.run(init_positions_db(db_path))
    asyncio.run(init_ledger(db_path))

    # Open two positions back-to-back.
    for ticker, price, qty in [
        ("TICKER_A", 100.0, 10),
        ("TICKER_B", 200.0, 5),
    ]:
        asyncio.run(
            peo._write_edge_position(
                db_path=db_path,
                source=peo.SOURCE_PAPER,
                ticker=ticker,
                entry_date_iso="2026-09-15",
                entry_price=price,
                shares=qty,
                stop_loss=price * 0.95,
                target_1=price * 1.10,
                regime_at_entry="",
            )
        )

    rows = _read_ledger(db_path)
    opened = [r for r in rows if r["event_type"] == "TRADE_OPENED"]
    assert len(opened) == 2

    # The TRADE_OPENED rows must have bankroll_before ==
    # bankroll_after (no realised P&L yet) and pnl=0.
    for row in opened:
        assert row["pnl"] == 0.0
        assert row["bankroll_before"] == row["bankroll_after"], (
            f"equity drift: before={row['bankroll_before']}, "
            f"after={row['bankroll_after']}"
        )


def test_write_edge_position_trade_opened_notes_carry_audit_surface(tmp_path):
    """[WORKFLOW-C.F8] The notes field carries the audit
    surface so an operator querying bankroll_ledger can see
    notional/shares/entry_price/stop_loss/sl_order_id
    WITHOUT joining positions.
    """
    db_path = str(tmp_path / "cache.db")
    asyncio.run(init_positions_db(db_path))
    asyncio.run(init_ledger(db_path))

    asyncio.run(
        peo._write_edge_position(
            db_path=db_path,
            source=peo.SOURCE_PAPER,
            ticker="GRAVISSHO",
            entry_date_iso="2026-09-15",
            entry_price=46.97,
            shares=971,
            stop_loss=44.50,
            target_1=52.00,
            regime_at_entry="",
            sl_order_id="sl-test-001",
        )
    )

    rows = _read_ledger(db_path)
    row = next(r for r in rows if r["event_type"] == "TRADE_OPENED")
    notes = row["notes"]
    # Audit surface: notional, shares, entry_price,
    # stop_loss, sl_order_id -- all key=value pairs.
    assert "notional=" in notes
    assert "shares=971" in notes
    assert "entry_price=46.97" in notes
    assert "stop_loss=44.50" in notes
    assert "sl_order_id=sl-test-001" in notes

    # Compute expected notional: 971 * 46.97 = 45,607.87
    # (notional rounding to 2dp).
    expected_notional = 971 * 46.97
    assert f"notional={expected_notional:.2f}" in notes


def test_write_edge_position_trade_opened_per_leg_source(tmp_path):
    """[WORKFLOW-C.F8] PAPER and LIVE legs each get their
    own TRADE_OPENED row with the correct source tag. The
    audit's GRAVISSHO was EDGE_PAPER; this test pins that
    EDGE_LIVE positions also get their own row.
    """
    db_path = str(tmp_path / "cache.db")
    asyncio.run(init_positions_db(db_path))
    asyncio.run(init_ledger(db_path))

    asyncio.run(
        peo._write_edge_position(
            db_path=db_path,
            source=peo.SOURCE_LIVE,
            ticker="TICKER_LIVE",
            entry_date_iso="2026-09-15",
            entry_price=100.0,
            shares=10,
            stop_loss=95.0,
            target_1=110.0,
            regime_at_entry="",
        )
    )

    rows = _read_ledger(db_path)
    live_opens = [
        r for r in rows
        if r["event_type"] == "TRADE_OPENED"
        and r["source"] == peo.SOURCE_LIVE
    ]
    assert len(live_opens) == 1
    assert live_opens[0]["ticker"] == "TICKER_LIVE"


def test_write_edge_position_trade_opened_does_not_affect_other_events(tmp_path):
    """[WORKFLOW-C.F8] TRADE_OPENED is purely additive: it
    doesn't interfere with TRADE_PARTIAL / TRADE_CLOSED /
    INITIAL events that may already exist. The ledger
    remains queryable for all event types.
    """
    db_path = str(tmp_path / "cache.db")
    asyncio.run(init_positions_db(db_path))
    asyncio.run(init_ledger(db_path))

    # Pre-seed an INITIAL event directly.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO bankroll_ledger
               (timestamp, event_type, ticker, pnl,
                bankroll_before, bankroll_after, notes, source)
               VALUES (?, 'INITIAL', NULL, 0.0, 0.0, 100000.0,
                       'seed_initial', ?)""",
            ("2026-09-01T00:00:00+00:00", peo.SOURCE_PAPER),
        )
        conn.commit()
    finally:
        conn.close()

    asyncio.run(
        peo._write_edge_position(
            db_path=db_path,
            source=peo.SOURCE_PAPER,
            ticker="GRAVISSHO",
            entry_date_iso="2026-09-15",
            entry_price=46.97,
            shares=971,
            stop_loss=44.50,
            target_1=52.00,
            regime_at_entry="",
        )
    )

    rows = _read_ledger(db_path)
    types = [r["event_type"] for r in rows]
    # ``init_ledger`` seeds a SYSTEM INITIAL row when the
    # table is empty. We then pre-seed a PAPER INITIAL,
    # then _write_edge_position adds a TRADE_OPENED. So
    # we expect: 2 INITIAL + 1 TRADE_OPENED = 3 rows.
    assert "INITIAL" in types
    assert "TRADE_OPENED" in types
    initial_count = sum(1 for r in rows if r["event_type"] == "INITIAL")
    opened_count = sum(1 for r in rows if r["event_type"] == "TRADE_OPENED")
    assert initial_count == 2  # SYSTEM (auto-seeded) + PAPER (test-seeded)
    assert opened_count == 1


# ─── Audit-trail query contract ─────────────────────────────


def test_audit_query_lists_open_positions(tmp_path):
    """[WORKFLOW-C.F8] The canonical audit query for F-8:
    ``SELECT ticker, notes FROM bankroll_ledger
    WHERE event_type='TRADE_OPENED'`` lists every open
    position's audit surface. This is the bounded fix:
    operators can NOW see open positions in the ledger.
    """
    db_path = str(tmp_path / "cache.db")
    asyncio.run(init_positions_db(db_path))
    asyncio.run(init_ledger(db_path))

    for ticker, price, qty in [
        ("GRAVISSHO", 46.97, 971),
        ("TICKER_X", 100.0, 10),
    ]:
        asyncio.run(
            peo._write_edge_position(
                db_path=db_path,
                source=peo.SOURCE_PAPER,
                ticker=ticker,
                entry_date_iso="2026-09-15",
                entry_price=price,
                shares=qty,
                stop_loss=price * 0.95,
                target_1=price * 1.10,
                regime_at_entry="",
            )
        )

    # Canonical audit query
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """SELECT ticker, notes FROM bankroll_ledger
               WHERE event_type='TRADE_OPENED'
                 AND source=?""",
            (peo.SOURCE_PAPER,),
        ).fetchall()
    finally:
        conn.close()

    tickers = sorted(r[0] for r in rows)
    assert tickers == ["GRAVISSHO", "TICKER_X"]
    # The notes column carries the full audit surface.
    for ticker, notes in rows:
        assert "notional=" in notes
        assert "shares=" in notes
        assert "entry_price=" in notes
