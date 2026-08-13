"""Scale-outs realise money once and close one coherent trade outcome."""

import sqlite3

import aiosqlite
import pytest

import main
from config import settings
from performance import init_ledger
from position_tracker import init_positions_db


@pytest.mark.asyncio
async def test_live_scale_out_then_close_has_one_aggregate_outcome(
    tmp_path, monkeypatch,
):
    db_path = str(tmp_path / "scale.db")
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    await init_ledger(db_path)
    await init_positions_db(db_path)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO positions (
                   ticker, exchange, entry_date, entry_price, shares,
                   stop_loss_initial, trailing_stop_current, target_1, target_2,
                   highest_close_since_entry, status, source, product_type,
                   t1_fired, initial_capital_at_risk
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "LIVE", "NSE", "2026-08-13T05:00:00+00:00", 100.0, 10,
                90.0, 90.0, 130.0, 130.0, 100.0, "OPEN", "MOMENTUM",
                "MIS", 0, 100.0,
            ),
        )
        await db.commit()

    pos = {
        "ticker": "LIVE", "entry_price": 100.0, "shares": 10,
        "stop_loss_initial": 90.0, "initial_capital_at_risk": 100.0,
        "source": "MOMENTUM", "product_type": "MIS", "realised_pnl": None,
    }
    assert await main._record_momentum_scale_out(
        pos, 110.0, sold_shares=5, runner_shares=5,
        new_stop=100.1, reason="scale_out_at_1R",
    )

    con = sqlite3.connect(db_path)
    assert con.execute(
        "SELECT event_type FROM bankroll_ledger WHERE source='MOMENTUM'"
    ).fetchall() == [("TRADE_PARTIAL",)]
    assert con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='trade_outcomes'"
    ).fetchone()[0] == 0
    con.row_factory = sqlite3.Row
    runner = dict(con.execute(
        "SELECT * FROM positions WHERE ticker='LIVE'"
    ).fetchone())
    con.close()

    assert await main._close_momentum_position(
        runner, 105.0, "CLOSED_TIME", "test_final",
    )

    con = sqlite3.connect(db_path)
    events = con.execute(
        "SELECT event_type FROM bankroll_ledger "
        "WHERE source='MOMENTUM' ORDER BY id"
    ).fetchall()
    assert events == [("TRADE_PARTIAL",), ("TRADE_CLOSED",)]
    position_pnl, position_r = con.execute(
        "SELECT realised_pnl, r_multiple FROM positions WHERE ticker='LIVE'"
    ).fetchone()
    ledger_pnl = con.execute(
        "SELECT SUM(pnl) FROM bankroll_ledger WHERE source='MOMENTUM'"
    ).fetchone()[0]
    outcomes = con.execute(
        "SELECT realised_pnl, r_multiple FROM trade_outcomes"
    ).fetchall()
    assert len(outcomes) == 1
    assert ledger_pnl == pytest.approx(position_pnl)
    assert position_r == pytest.approx(position_pnl / 100.0)
    assert outcomes[0][0] == pytest.approx(position_pnl)
    assert outcomes[0][1] == pytest.approx(position_r)


def test_legacy_unscaled_position_uses_current_quantity_for_initial_risk():
    pos = {
        "entry_price": 100.0,
        "stop_loss_initial": 90.0,
        "shares": 7,
        "initial_capital_at_risk": None,
    }
    assert main._momentum_initial_risk(pos) == 70.0
