"""
[TIER0-0.2 2026-07-14] Paper money must never enter a live pool.

What happened: `daily_post_market` called

    update_daily_positions(db, kite, today, lambda t, p: record_trade_close(db, t, p))

The lambda dropped the position's source, so record_trade_close fell back to its
default `source="SYSTEM"`. But update_daily_positions walks EVERY open position --
including EDGE_PAPER ones, which are sized off a ₹100,000 imaginary bankroll while
the real book is ₹5,000.

So the paper leg's P&L was booked into the live pool:

    EDGE_PAPER net  = +3,826.27      <- paper money, ₹100k bankroll
    EDGE_LIVE  net  =    +39.16
    MOMENTUM   net  =    -23.33
                      ----------
    ledger reported   ₹8,842.11      the account actually held ₹5,015.83

76% of the reported P&L was fiction, and every downstream number -- edge_stats,
win rate, expectancy, the A/B comparisons this roadmap depends on -- inherited it.

The repo already had the right primitive (`bankroll_for_source`) and a conformance
rule that sizing must never use the mixed `current_bankroll()`. It just had one
caller that silently mislabelled the source.
"""
import pytest

import performance
from performance import bankroll_for_source, record_trade_close


PAPER_SOURCES = ("EDGE_PAPER", "FNO_PAPER", "PENNY_PAPER")
LIVE_SOURCES = ("SYSTEM", "MOMENTUM", "PENNY", "EDGE_LIVE")


@pytest.fixture
def db(tmp_path, monkeypatch):
    import sqlite3
    path = str(tmp_path / "cache.db")
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE bankroll_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, event_type TEXT, ticker TEXT, pnl REAL,
            bankroll_before REAL, bankroll_after REAL, source TEXT
        )
    """)
    con.commit()
    con.close()
    return path


@pytest.mark.asyncio
async def test_paper_pnl_does_not_move_the_live_pool(db, monkeypatch):
    """The regression, stated directly."""
    monkeypatch.setattr("analytics.record_trade_outcome", None, raising=False)

    live_before = await bankroll_for_source(db, "SYSTEM")

    # The EDGE paper leg books a fat ₹100k-sized win.
    await record_trade_close(db, "MCLOUD", 1325.18, source="EDGE_PAPER")

    live_after = await bankroll_for_source(db, "SYSTEM")

    assert live_after == live_before, (
        "paper P&L moved the live SYSTEM pool -- this is the ₹3,826 of fiction "
        "that made a ₹5,016 account report ₹8,842"
    )

    # ...and it is still recorded, in its own pool.
    paper = await bankroll_for_source(db, "EDGE_PAPER")
    assert paper == pytest.approx(performance.settings.INITIAL_BANKROLL + 1325.18)


@pytest.mark.asyncio
async def test_each_pool_only_sees_its_own_trades(db):
    await record_trade_close(db, "AAA", 100.0, source="MOMENTUM")
    await record_trade_close(db, "BBB", 5000.0, source="EDGE_PAPER")
    await record_trade_close(db, "CCC", -10.0, source="EDGE_LIVE")

    base = performance.settings.INITIAL_BANKROLL
    assert await bankroll_for_source(db, "MOMENTUM") == pytest.approx(base + 100.0)
    assert await bankroll_for_source(db, "EDGE_LIVE") == pytest.approx(base - 10.0)
    assert await bankroll_for_source(db, "SYSTEM") == pytest.approx(base)


@pytest.mark.asyncio
async def test_no_paper_source_leaks_into_any_live_pool(db):
    """The conformance rule, over the full cross-product."""
    for src in PAPER_SOURCES:
        await record_trade_close(db, "PAPERCO", 9999.0, source=src)

    base = performance.settings.INITIAL_BANKROLL
    for live in LIVE_SOURCES:
        assert await bankroll_for_source(db, live) == pytest.approx(base), (
            f"paper P&L reached the live pool {live!r}"
        )


@pytest.mark.asyncio
async def test_update_daily_positions_passes_the_source_through():
    """
    The actual defect was the CALLBACK SIGNATURE. position_tracker calls
    record_pnl_cb(ticker, pnl, source); if a caller binds a 2-arg lambda, the
    source is lost and record_trade_close silently defaults to SYSTEM.

    Pin the arity so a future 2-arg lambda fails loudly here rather than quietly
    in the ledger.
    """
    import inspect
    from position_tracker import update_daily_positions

    src = inspect.getsource(update_daily_positions)
    assert "record_pnl_cb(ticker, realised_pnl, " in src, (
        "update_daily_positions must pass the position's source to the ledger "
        "callback -- dropping it books paper trades into the live book"
    )


# ---- [SOURCE-REQUIRED 2026-07-26] the same trap, three more callers ----
# The 2026-07-14 fix above patched ONE caller and left record_trade_close's
# `source="SYSTEM"` default in place. The trap stayed open: _close_momentum_position,
# auto_square_momentum and POST /positions/close had never passed source either,
# so every SYSTEM row in the live ledger turned out to belong to a MOMENTUM
# position. Swing was credited with 12 losing trades it never took, and momentum's
# real record was split across two divisions -- so the promotion ladder was judging
# both books on the wrong rows.
#
# The default is now gone. These tests pin the property, not the call sites, so a
# fourth caller cannot reintroduce it.

def test_record_trade_close_has_no_default_source():
    """Attribution must be explicit at every call site."""
    import inspect

    from performance import record_trade_close

    sig = inspect.signature(record_trade_close)
    src = sig.parameters["source"]
    assert src.default is inspect.Parameter.empty, (
        "record_trade_close regained a default source -- a caller that forgets to "
        "attribute P&L will silently book it to whichever division that default names"
    )
    assert src.kind is inspect.Parameter.KEYWORD_ONLY, (
        "source must be keyword-only so it cannot be supplied positionally by accident"
    )


def test_no_production_caller_omits_source():
    """Every record_trade_close call in the engine names its division.

    A signature check alone would not catch a caller passing source=None or
    building kwargs dynamically, and this is the property that actually matters.
    """
    import ast
    import pathlib

    engine_dir = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for py in engine_dir.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name != "record_trade_close":
                continue
            kwargs = {k.arg for k in node.keywords if k.arg}
            has_splat = any(k.arg is None for k in node.keywords)
            if "source" not in kwargs and not has_splat:
                offenders.append(f"{py.name}:{node.lineno}")
    assert not offenders, (
        "record_trade_close called without an explicit source at: "
        + ", ".join(offenders)
    )
