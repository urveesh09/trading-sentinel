"""
[MOMENTUM-PAPER 2026-07-26] Tests for the momentum paper book.

Live momentum entry is manual (Telegram EXEC), so the live ledger records what
the operator did, not what the strategy proposed -- 8 trades in months. The paper
book takes every accepted signal automatically so the strategy accumulates a
record of its own decisions.

Two properties matter more than the rest and are tested hardest:

  1. Paper P&L must NEVER reach real accounting. This system has already shipped
     that bug once: EDGE_PAPER profits were booked into the real SYSTEM pool and
     76% of the reported account turned out to be fiction.
  2. The module must not be able to place an order. Not "must not place one" --
     must not be ABLE to. The 2026-07-21..24 incident was a book sending real
     orders it was never meant to send.
"""
import asyncio
import sqlite3

import pytest

from config import settings
from momentum_paper import (
    SOURCE,
    momentum_paper_monitor,
    momentum_paper_square_off,
    open_momentum_paper_positions,
    paper_position_size,
)


def _db(tmp_path):
    """A positions + bankroll_ledger DB shaped like the real one."""
    path = str(tmp_path / "cache.db")
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE positions (
            ticker TEXT, exchange TEXT, entry_date TEXT, entry_price REAL, shares INTEGER,
            stop_loss_initial REAL, trailing_stop_current REAL, target_1 REAL, target_2 REAL,
            atr_14_at_entry REAL, highest_close_since_entry REAL, status TEXT, source TEXT,
            exit_price REAL, exit_date TEXT, realised_pnl REAL, r_multiple REAL,
            product_type TEXT, regime_at_entry TEXT, t1_fired INTEGER DEFAULT 0,
            vwap_at_entry REAL, initial_capital_at_risk REAL
        )""")
    con.execute("""
        CREATE TABLE bankroll_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, event_type TEXT,
            ticker TEXT, pnl REAL, bankroll_before REAL, bankroll_after REAL,
            notes TEXT, source TEXT
        )""")
    con.commit()
    con.close()
    return path


def _sig(ticker="ACME", close=100.0, stop=99.0, target=103.0):
    return {"ticker": ticker, "close": close, "stop_loss": stop,
            "target_1": target, "target_2": target, "regime": "REGIME_1_NORMAL",
            "vwap": close - 0.5}


async def _ltp_of(price):
    async def _fn(_ticker):
        return price
    return _fn


# ---- sizing --------------------------------------------------------

def test_size_uses_the_paper_pool_not_the_live_one():
    """Rs 50,000 must buy a position the Rs 2,500 live pool never could."""
    live = paper_position_size(close=500.0, stop_loss=497.5, pool=2500.0, risk_pct=0.10)
    paper = paper_position_size(close=500.0, stop_loss=497.5, pool=50000.0, risk_pct=0.10)
    assert paper > live
    assert paper * 500.0 <= 50000.0          # never exceeds the pool


def test_size_is_capped_by_the_pool():
    """A tiny per-share risk must not size past the pool."""
    shares = paper_position_size(close=100.0, stop_loss=99.99, pool=50000.0, risk_pct=0.10)
    assert shares * 100.0 <= 50000.0
    assert shares == 500


def test_size_is_capped_by_remaining_deployable_capital():
    shares = paper_position_size(
        close=100.0, stop_loss=99.0, pool=50_000.0, risk_pct=0.10,
        available_capital=1_250.0,
    )
    assert shares == 12
    assert shares * 100.0 <= 1_250.0


def test_size_rejects_malformed_risk():
    assert paper_position_size(100.0, 100.0, 50000.0, 0.10) == 0   # zero risk
    assert paper_position_size(100.0, 101.0, 50000.0, 0.10) == 0   # stop above entry
    assert paper_position_size(0.0, 0.0, 50000.0, 0.10) == 0


def test_paper_sizing_uses_the_live_regime_risk_schedule(tmp_path, monkeypatch):
    """R2 must not be paper-sized at the legacy/R1 10% risk fraction."""
    monkeypatch.setattr(settings, "MOMENTUM_PAPER_BANKROLL", 50_000.0)
    monkeypatch.setattr(settings, "MOMENTUM_RISK_PCT_R1", 0.10)
    monkeypatch.setattr(settings, "MOMENTUM_RISK_PCT_R2", 0.07)
    monkeypatch.setattr(settings, "MOMENTUM_RISK_PCT_R3", 0.00)

    db = _db(tmp_path)
    r1 = _sig("R1", close=100.0, stop=80.0, target=130.0)
    r2 = _sig("R2", close=100.0, stop=80.0, target=130.0)
    r3 = _sig("R3", close=100.0, stop=80.0, target=130.0)
    r2["regime"] = "REGIME_2_ELEVATED"
    r3["regime"] = "REGIME_3_CRISIS"

    opened = asyncio.run(open_momentum_paper_positions(db, [r1, r2, r3]))
    assert opened == ["R1", "R2"]
    con = sqlite3.connect(db)
    shares = dict(con.execute("SELECT ticker, shares FROM positions"))
    assert shares == {"R1": 250, "R2": 175}


def test_missing_regime_preserves_legacy_paper_risk(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MOMENTUM_RISK_PCT", 0.08)
    db = _db(tmp_path)
    sig = _sig(close=100.0, stop=90.0, target=130.0)
    sig.pop("regime")
    asyncio.run(open_momentum_paper_positions(db, [sig]))
    con = sqlite3.connect(db)
    assert con.execute("SELECT shares FROM positions").fetchone()[0] == 400


# ---- opening -------------------------------------------------------

def test_open_creates_a_paper_position(tmp_path):
    db = _db(tmp_path)
    opened = asyncio.run(open_momentum_paper_positions(db, [_sig()]))
    assert opened == ["ACME"]

    con = sqlite3.connect(db)
    row = con.execute(
        "SELECT source, status, product_type, shares, exit_date FROM positions"
    ).fetchone()
    assert row[0] == SOURCE and row[1] == "OPEN" and row[2] == "MIS"
    assert row[3] > 0 and row[4] is None


def test_open_batch_never_overcommits_shared_paper_pool(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MOMENTUM_PAPER_BANKROLL", 1_000.0)
    monkeypatch.setattr(settings, "MOMENTUM_RISK_PCT_R1", 0.10)
    db = _db(tmp_path)

    opened = asyncio.run(open_momentum_paper_positions(
        db,
        [_sig("A", close=600.0, stop=590.0),
         _sig("B", close=600.0, stop=590.0)],
    ))

    assert opened == ["A"]
    con = sqlite3.connect(db)
    deployed = con.execute(
        "SELECT COALESCE(SUM(entry_price * shares),0) FROM positions "
        "WHERE source=? AND exit_date IS NULL", (SOURCE,),
    ).fetchone()[0]
    assert deployed <= 1_000.0


def test_open_does_not_duplicate_an_already_held_ticker(tmp_path):
    """A signal repeating across scans must not stack the same position."""
    db = _db(tmp_path)
    asyncio.run(open_momentum_paper_positions(db, [_sig()]))
    again = asyncio.run(open_momentum_paper_positions(db, [_sig()]))
    assert again == []
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 1


def test_open_reopens_after_the_position_is_closed(tmp_path):
    """Yesterday's closed trade must not block today's signal."""
    db = _db(tmp_path)
    asyncio.run(open_momentum_paper_positions(db, [_sig()]))
    con = sqlite3.connect(db)
    con.execute("UPDATE positions SET exit_date='2026-07-25T10:00:00', status='CLOSED_TIME'")
    con.commit()
    con.close()
    assert asyncio.run(open_momentum_paper_positions(db, [_sig()])) == ["ACME"]


def test_open_is_a_noop_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MOMENTUM_PAPER_ENABLED", False)
    db = _db(tmp_path)
    assert asyncio.run(open_momentum_paper_positions(db, [_sig()])) == []


# ---- exits ---------------------------------------------------------

def test_monitor_takes_the_target_and_books_costs(tmp_path):
    from datetime import datetime
    db = _db(tmp_path)
    asyncio.run(open_momentum_paper_positions(db, [_sig(close=100.0, stop=99.0, target=103.0)]))

    async def run():
        return await momentum_paper_monitor(db, await _ltp_of(103.5),
                                            datetime(2026, 7, 27, 11, 0))
    res = asyncio.run(run())
    assert [t for t, _ in res["exited"]] == ["ACME"]

    con = sqlite3.connect(db)
    status, exit_price, pnl = con.execute(
        "SELECT status, exit_price, realised_pnl FROM positions"
    ).fetchone()
    assert exit_price == pytest.approx(103.5)
    assert status.startswith("CLOSED")
    # Gross would be 3.5/share; costs must have been deducted, so P&L is lower.
    shares = con.execute("SELECT shares FROM positions").fetchone()[0]
    assert 0 < pnl < 3.5 * shares


def test_square_off_flattens_everything(tmp_path):
    from datetime import datetime
    db = _db(tmp_path)
    asyncio.run(open_momentum_paper_positions(
        db, [_sig("A", 100.0, 50.0, 130.0),
             _sig("B", 50.0, 25.0, 65.0)],
    ))

    async def run():
        return await momentum_paper_square_off(db, await _ltp_of(101.0),
                                               datetime(2026, 7, 27, 15, 15))
    closed = asyncio.run(run())
    assert len(closed) == 2
    con = sqlite3.connect(db)
    assert con.execute(
        "SELECT COUNT(*) FROM positions WHERE exit_date IS NULL"
    ).fetchone()[0] == 0


def test_square_off_still_flattens_when_the_quote_is_missing(tmp_path):
    """An intraday book may never carry overnight, quote or no quote."""
    from datetime import datetime
    db = _db(tmp_path)
    asyncio.run(open_momentum_paper_positions(db, [_sig()]))

    async def none_ltp(_t):
        return None

    asyncio.run(momentum_paper_square_off(db, none_ltp, datetime(2026, 7, 27, 15, 15)))
    con = sqlite3.connect(db)
    assert con.execute(
        "SELECT COUNT(*) FROM positions WHERE exit_date IS NULL"
    ).fetchone()[0] == 0


def test_scale_out_books_equity_but_only_final_close_records_one_outcome(
    tmp_path, monkeypatch,
):
    from datetime import datetime

    monkeypatch.setattr(settings, "MOMENTUM_USE_SCALE_OUT", True)
    monkeypatch.setattr(settings, "MOMENTUM_SCALE_OUT_R", 1.0)
    monkeypatch.setattr(settings, "MOMENTUM_SCALE_OUT_FRAC", 0.5)
    db = _db(tmp_path)
    sig = _sig(close=100.0, stop=90.0, target=130.0)
    asyncio.run(open_momentum_paper_positions(db, [sig]))

    asyncio.run(momentum_paper_monitor(
        db, asyncio.run(_ltp_of(110.0)), datetime(2026, 7, 27, 11, 0),
    ))
    con = sqlite3.connect(db)
    assert con.execute(
        "SELECT event_type FROM bankroll_ledger"
    ).fetchall() == [("TRADE_PARTIAL",)]
    assert con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='trade_outcomes'"
    ).fetchone()[0] == 0

    asyncio.run(momentum_paper_square_off(
        db, asyncio.run(_ltp_of(105.0)), datetime(2026, 7, 27, 15, 15),
    ))
    events = con.execute(
        "SELECT event_type FROM bankroll_ledger ORDER BY id"
    ).fetchall()
    assert events == [("TRADE_PARTIAL",), ("TRADE_CLOSED",)]
    position_pnl, position_r, initial_risk = con.execute(
        "SELECT realised_pnl, r_multiple, initial_capital_at_risk FROM positions"
    ).fetchone()
    ledger_pnl = con.execute(
        "SELECT SUM(pnl) FROM bankroll_ledger WHERE source=?", (SOURCE,)
    ).fetchone()[0]
    outcome_pnl, outcome_r = con.execute(
        "SELECT realised_pnl, r_multiple FROM trade_outcomes"
    ).fetchone()
    assert ledger_pnl == pytest.approx(position_pnl)
    assert position_r == pytest.approx(position_pnl / initial_risk)
    assert outcome_pnl == pytest.approx(position_pnl)
    assert outcome_r == pytest.approx(position_r)
    assert con.execute("SELECT COUNT(*) FROM trade_outcomes").fetchone()[0] == 1


# ---- the two properties that matter most ---------------------------

def test_paper_pnl_never_reaches_real_accounting(tmp_path):
    """The EDGE_PAPER bug, guarded.

    nifty_bankroll and both circuit breakers filter source IN ('SYSTEM',
    'MOMENTUM'). 'MOMENTUM_PAPER' is a different string, and SQL IN is exact
    equality -- but that is exactly the kind of assumption that silently breaks
    when someone later writes `source LIKE 'MOMENTUM%'`.
    """
    from datetime import datetime
    from performance import nifty_bankroll

    db = _db(tmp_path)
    asyncio.run(open_momentum_paper_positions(db, [_sig()]))

    async def run():
        before = await nifty_bankroll(db)
        await momentum_paper_monitor(db, await _ltp_of(103.5),
                                     datetime(2026, 7, 27, 11, 0))
        return before, await nifty_bankroll(db)

    before, after = asyncio.run(run())
    assert before == after, "paper P&L leaked into the real Nifty bankroll"

    con = sqlite3.connect(db)
    rows = con.execute("SELECT source, pnl FROM bankroll_ledger").fetchall()
    assert rows and all(s == SOURCE for s, _ in rows)
    assert con.execute(
        "SELECT COUNT(*) FROM bankroll_ledger WHERE source IN ('SYSTEM','MOMENTUM')"
    ).fetchone()[0] == 0


def test_module_cannot_place_an_order():
    """Structural guarantee, not a runtime flag.

    momentum_paper must contain no order-placing capability at all. A flag that
    must stay False is one bad branch away from a real order; an absent code path
    is not.
    """
    import ast
    import inspect

    import momentum_paper

    tree = ast.parse(inspect.getsource(momentum_paper))

    # Every name actually called or attribute accessed -- comments and docstrings
    # are not in the AST, so prose describing the guarantee cannot trip it.
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            called.add(node.attr)
        elif isinstance(node, ast.Name):
            called.add(node.id)

    forbidden = {"place_order", "modify_order", "cancel_order", "square_off",
                 "auto_square_momentum", "post", "put", "delete"}
    leaked = called & forbidden
    assert not leaked, f"momentum_paper gained an order path: {sorted(leaked)}"

    # And it must not import anything that can reach the broker.
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for banned in ("httpx", "fno_executor", "kite", "requests"):
        assert banned not in imported, (
            f"momentum_paper imported {banned!r} -- it must stay unable to "
            "reach the broker; LTP is injected as ltp_fn"
        )


# ---- [PAPER-REGIME 2026-08-04] the enum-binding regression ----------------
#
# This book recorded ZERO trades between being built (2026-07-26) and
# 2026-08-04. Every open raised
#     Error binding parameter 15: type 'Regime' is not supported
# because production hands `regime` through as a pydantic Regime enum while
# every test above passes the STRING "REGIME_1_NORMAL". The suite was green
# and the feature was dead: 1,707 passing tests and not one of them exercised
# the type the real caller actually sends.
#
# So these tests use the real enum, and one of them asserts the invariant
# rather than the single field that happened to break.

@pytest.mark.asyncio
async def test_opens_a_position_when_regime_is_a_real_enum(tmp_path):
    tmp_db = _db(tmp_path)
    """The production caller passes Regime, not str."""
    from models import Regime
    sig = _sig()
    sig["regime"] = Regime.REGIME_1_NORMAL

    opened = await open_momentum_paper_positions(tmp_db, [sig])
    assert opened == ["ACME"], "enum regime must not silently abort the open"

    con = sqlite3.connect(tmp_db)
    row = con.execute(
        "SELECT source, regime_at_entry, shares FROM positions WHERE ticker='ACME'"
    ).fetchone()
    con.close()
    assert row is not None, "no position row was written"
    assert row[0] == "MOMENTUM_PAPER"
    assert row[1] == "REGIME_1_NORMAL", "enum must be stored as its string value"
    assert row[2] > 0


@pytest.mark.asyncio
async def test_every_bound_signal_field_survives_a_non_primitive_type(tmp_path):
    """The general invariant, not just the field that broke.

    Any value coming off an accepted signal can be a pydantic type; none of
    them may be handed to sqlite3 raw. Binding is all-or-nothing per row, so a
    single unsupported type loses the whole trade -- which is exactly how a
    regime enum erased nine days of paper evidence."""
    from models import Regime

    class _Weird:
        def __str__(self):
            return "108.5"

    tmp_db = _db(tmp_path)
    sig = _sig(ticker="WEIRD")
    sig["regime"] = Regime.REGIME_2_ELEVATED
    sig["atr_at_entry"] = _Weird()          # not a primitive, not an Enum

    opened = await open_momentum_paper_positions(tmp_db, [sig])
    assert opened == ["WEIRD"]

    con = sqlite3.connect(tmp_db)
    row = con.execute(
        "SELECT regime_at_entry, atr_14_at_entry FROM positions WHERE ticker='WEIRD'"
    ).fetchone()
    con.close()
    assert row[0] == "REGIME_2_ELEVATED"
    assert str(row[1]) == "108.5"


def test_sqlite_safe_passes_primitives_through_untouched():
    """It must not stringify numbers -- that would turn every price into TEXT."""
    from momentum_paper import _sqlite_safe
    assert _sqlite_safe(None) is None
    assert _sqlite_safe(3.5) == 3.5 and isinstance(_sqlite_safe(3.5), float)
    assert _sqlite_safe(7) == 7 and isinstance(_sqlite_safe(7), int)
    assert _sqlite_safe("REGIME_1_NORMAL") == "REGIME_1_NORMAL"
