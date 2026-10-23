"""[S23-COST1] One equity charge contract: intraday when sold the session it was bought."""
import sqlite3
from datetime import date, datetime, timedelta, timezone

import aiosqlite
import pandas as pd
import pytest

import penny_edge_orchestrator as edge
from engine import calc_zerodha_costs
from equity_charges import charged_as_intraday, session_date
from penny_risk import calc_penny_costs
from position_tracker import init_positions_db, settlement_costs, update_daily_positions

DCMSRIND = {"product_type": "CNC", "entry_date": "2026-10-22T09:30:07.707831+05:30", "entry_price": 54.30}


@pytest.mark.parametrize("product, entry, exit_, expected", [
    ("MIS", "2026-10-20", "2026-10-22", True),                      # MIS is always intraday
    ("CNC", "2026-10-22T09:30:07+05:30", "2026-10-22", True),       # sold the session it was bought
    ("cnc", "2026-10-22", date(2026, 10, 22), True),
    ("CNC", "2026-10-22T09:30:07+05:30", "2026-10-23", False),      # held overnight
    ("CNC", "not a date", "2026-10-22", False),                     # unreadable keeps delivery
    (None, None, None, True),                                       # legacy default: intraday
])
def test_which_schedule_a_round_trip_pays(product, entry, exit_, expected):
    assert charged_as_intraday(product, entry, exit_) is expected


def test_a_utc_clock_is_read_as_its_ist_session():
    # 20:00 UTC on Oct 22 is 01:30 IST on Oct 23.
    assert session_date("2026-10-22T20:00:00+00:00") == date(2026, 10, 23)
    assert charged_as_intraday("CNC", "2026-10-22T20:00:00+00:00", "2026-10-23", default_product="CNC")


def test_the_audited_dcmsrind_close_pays_intraday_charges():
    # Oct 22 EDGE_PAPER: 873 shares bought 54.30, stopped 51.5424 the same day.
    # The tracker booked 82.5848 (old CNC branch); delivery would be 118.3074.
    assert settlement_costs(DCMSRIND, 51.5424, 873, "2026-10-22") == pytest.approx(48.8374, abs=1e-4)
    assert settlement_costs(DCMSRIND, 51.5424, 873, "2026-10-23") == pytest.approx(118.3074, abs=1e-4)


@pytest.mark.parametrize("entry, exit_, shares", [(54.30, 51.5424, 873), (100.0, 102.0, 10), (6.5, 7.1, 3000)])
@pytest.mark.parametrize("intraday", [True, False])
def test_engine_and_penny_schedules_are_one_contract(entry, exit_, shares, intraday):
    assert calc_zerodha_costs(entry, exit_, shares, intraday) == calc_penny_costs(entry, exit_, shares, intraday)


def test_delivery_charges_have_no_brokerage_and_stt_on_both_legs():
    buy, sell = 1000.0, 1020.0
    turnover = buy + sell
    regulatory = turnover * (0.0000307 + 0.000001 + 0.000000001)
    expected = 0.001 * turnover + 0.00015 * buy + 15.34 + regulatory * 1.18
    assert calc_zerodha_costs(100.0, 102.0, 10, is_intraday=False) == pytest.approx(expected, abs=1e-4)


async def _seed(db_path, *, entry_date: str, ticker="SAMEDAY"):
    await init_positions_db(str(db_path))
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO positions (
                ticker,exchange,entry_date,entry_price,shares,stop_loss_initial,
                trailing_stop_current,target_1,target_2,atr_14_at_entry,
                highest_close_since_entry,status,source,product_type,
                regime_at_entry,initial_capital_at_risk
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ticker, "NSE", entry_date, 100.0, 10, 95.0, 95.0, 110.0, 110.0, None, 100.0,
             "OPEN", "EDGE_PAPER", "CNC", "", 50.0),
        )
        await db.commit()


class _StopBar:
    async def get_historical(self, *_args, **_kwargs):
        return pd.DataFrame({"date": [datetime.now(timezone.utc)], "open": [100.0], "high": [101.0],
                             "low": [94.0], "close": [96.0], "volume": [1000]})


@pytest.mark.asyncio
@pytest.mark.parametrize("held_days, intraday", [(0, True), (3, False)])
async def test_the_tracker_settles_by_holding_not_by_product(tmp_path, held_days, intraday):
    db = tmp_path / "tracker.db"
    today = date(2026, 10, 22)
    await _seed(db, entry_date=f"{today - timedelta(days=held_days)}T09:30:00+05:30")
    booked = []

    async def record(ticker, pnl, source):
        booked.append(pnl)

    await update_daily_positions(str(db), _StopBar(), today.isoformat(), record)
    expected = (95.0 - 100.0) * 10 - calc_penny_costs(100.0, 95.0, 10, is_intraday=intraday)
    with sqlite3.connect(db) as conn:
        status, pnl = conn.execute("SELECT status, realised_pnl FROM positions").fetchone()
    assert status == "STOPPED_OUT"
    assert pnl == pytest.approx(expected, abs=1e-4)


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_date, intraday", [("2026-10-22", True), ("2026-10-23", False)])
async def test_the_confirmed_edge_exit_uses_the_same_rule(tmp_path, exit_date, intraday):
    db = tmp_path / "edge.db"
    await _seed(db, entry_date="2026-10-22T09:30:00+05:30", ticker="EDGE")
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        position = dict(conn.execute("SELECT * FROM positions").fetchone())
    out = await edge._settle_confirmed_edge_fill(str(db), position, confirmed_qty=10, fill_price=95.0,
                                                  exit_reason="stop", exit_date=exit_date)
    assert out["pnl"] == pytest.approx(-50.0 - calc_penny_costs(100.0, 95.0, 10, is_intraday=intraday), abs=1e-4)
