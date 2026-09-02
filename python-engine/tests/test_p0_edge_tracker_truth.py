import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import numpy as np
import pandas as pd
import pytest

import penny_edge_orchestrator as edge
from position_tracker import init_positions_db, update_daily_positions


async def _seed(db_path, *, source, ticker="EDGE", shares=10, sl_order_id=None):
    await init_positions_db(str(db_path))
    entry_date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO positions (
                ticker,exchange,entry_date,entry_price,shares,stop_loss_initial,
                trailing_stop_current,target_1,target_2,atr_14_at_entry,
                highest_close_since_entry,status,source,product_type,
                regime_at_entry,initial_capital_at_risk,sl_order_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ticker, "NSE", entry_date, 100.0, shares, 95.0, 95.0, 110.0,
             110.0, None, 100.0, "OPEN", source, "CNC", "", 50.0,
             sl_order_id),
        )
        await db.commit()
    return entry_date


class _BarsKite:
    async def get_historical(self, *_args, **_kwargs):
        return pd.DataFrame({
            "date": [datetime.now(timezone.utc)], "open": [100.0],
            "high": [101.0], "low": [99.0], "close": [100.0],
            "volume": [1000],
        })

    async def get_broker_positions(self):
        return {"net": [{
            "tradingsymbol": "EDGE", "product": "CNC", "quantity": 10,
        }]}


@pytest.mark.asyncio
async def test_edge_live_unknown_exit_remains_open(tmp_path, monkeypatch):
    db = tmp_path / "edge-unknown.db"
    await _seed(db, source=edge.SOURCE_LIVE)
    executor = SimpleNamespace(
        kite=_BarsKite(), paper_mode=False,
        resolve_unwind_tag=AsyncMock(return_value={
            "status": "NOT_FOUND", "order_id": None,
        }),
        _market_unwind=AsyncMock(return_value=None),
        execute_exit=AsyncMock(), _page_operator=AsyncMock(),
    )
    monkeypatch.setattr(edge, "_executor_for", lambda *_a, **_kw: executor)
    monkeypatch.setattr(edge, "_live_trading_enabled", lambda: True)

    summary = await edge.run_penny_edge_exit(_BarsKite(), str(db))

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT status,shares,exit_date,realised_pnl FROM positions"
        ).fetchone()
    assert row == ("OPEN", 10, None, None)
    assert summary["closed_live"] == []
    assert summary["unconfirmed_live"][0]["remaining_qty"] == 10
    executor.execute_exit.assert_not_awaited()
    executor._page_operator.assert_awaited_once()


@pytest.mark.asyncio
async def test_edge_live_partial_settles_only_confirmed_quantity(tmp_path, monkeypatch):
    db = tmp_path / "edge-partial.db"
    await _seed(db, source=edge.SOURCE_LIVE)
    executor = SimpleNamespace(
        kite=_BarsKite(), paper_mode=False,
        resolve_unwind_tag=AsyncMock(return_value={
            "status": "NOT_FOUND", "order_id": None,
        }),
        _market_unwind=AsyncMock(return_value="EXIT-1"),
        execute_exit=AsyncMock(return_value={
            "status": "PARTIAL", "order_id": "EXIT-1",
            "confirmed_qty": 4, "fill_price": 102.0,
        }),
        _page_operator=AsyncMock(),
    )
    monkeypatch.setattr(edge, "_executor_for", lambda *_a, **_kw: executor)
    monkeypatch.setattr(edge, "_live_trading_enabled", lambda: True)

    summary = await edge.run_penny_edge_exit(_BarsKite(), str(db))

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT status,shares,exit_date,realised_pnl FROM positions"
        ).fetchone()
    assert row[0:3] == ("OPEN", 6, None)
    assert row[3] > 0
    assert summary["closed_live"] == []
    assert summary["partial_live"][0]["confirmed_qty"] == 4
    assert summary["partial_live"][0]["remaining_qty"] == 6
    with sqlite3.connect(db) as conn:
        ledger = conn.execute(
            "SELECT event_type,pnl,source FROM bankroll_ledger WHERE source=?",
            (edge.SOURCE_LIVE,),
        ).fetchone()
    assert ledger[0] == "TRADE_PARTIAL"
    assert ledger[1] == pytest.approx(row[3])
    assert ledger[2] == edge.SOURCE_LIVE


@pytest.mark.asyncio
async def test_edge_lost_submit_response_recovers_tag_without_second_sell(tmp_path, monkeypatch):
    db = tmp_path / "edge-recover.db"
    await _seed(db, source=edge.SOURCE_LIVE)
    recover = AsyncMock(side_effect=[
        {"status": "NOT_FOUND", "order_id": None},
        {"status": "FOUND", "order_id": "EXIT-RECOVERED"},
    ])
    market = AsyncMock(side_effect=TimeoutError("response lost"))
    executor = SimpleNamespace(
        kite=_BarsKite(), paper_mode=False,
        resolve_unwind_tag=recover, _market_unwind=market,
        execute_exit=AsyncMock(return_value={
            "status": "COMPLETE", "order_id": "EXIT-RECOVERED",
            "confirmed_qty": 10, "fill_price": 101.0,
        }),
        _page_operator=AsyncMock(),
    )
    monkeypatch.setattr(edge, "_executor_for", lambda *_a, **_kw: executor)
    monkeypatch.setattr(edge, "_live_trading_enabled", lambda: True)

    first = await edge.run_penny_edge_exit(_BarsKite(), str(db))
    second = await edge.run_penny_edge_exit(_BarsKite(), str(db))

    assert first["unconfirmed_live"][0]["status"] == "UNKNOWN"
    assert len(second["closed_live"]) == 1
    market.assert_awaited_once()
    assert recover.await_count == 2
    first_tag = recover.await_args_list[0].args[0]
    second_tag = recover.await_args_list[1].args[0]
    assert first_tag == second_tag
    assert len(first_tag) == 20


@pytest.mark.asyncio
async def test_edge_live_unconfirmed_stop_cancel_blocks_second_sell(tmp_path, monkeypatch):
    db = tmp_path / "edge-stop-unknown.db"
    await _seed(db, source=edge.SOURCE_LIVE, sl_order_id="SL-1")
    kite = _BarsKite()
    kite.cancel_order = AsyncMock(return_value={"status": "ERROR"})
    kite.order_history = AsyncMock(return_value=[{"status": "OPEN", "filled_quantity": 0}])
    executor = SimpleNamespace(
        kite=kite, paper_mode=False, _market_unwind=AsyncMock(),
        execute_exit=AsyncMock(), _page_operator=AsyncMock(),
    )
    monkeypatch.setattr(edge, "_executor_for", lambda *_a, **_kw: executor)

    summary = await edge.run_penny_edge_exit(kite, str(db))

    executor._market_unwind.assert_not_awaited()
    assert summary["unconfirmed_live"][0]["message"] == (
        "protective stop cancellation unconfirmed"
    )
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT status,shares,sl_order_id FROM positions"
        ).fetchone() == ("OPEN", 10, "SL-1")


@pytest.mark.asyncio
async def test_edge_partial_stop_fill_settles_once_without_second_sell(tmp_path, monkeypatch):
    db = tmp_path / "edge-stop-partial.db"
    await _seed(db, source=edge.SOURCE_LIVE, sl_order_id="SL-2")
    kite = _BarsKite()
    kite.cancel_order = AsyncMock(return_value={"status": "CANCELLED"})
    kite.order_history = AsyncMock(return_value=[{
        "status": "CANCELLED", "filled_quantity": 4, "average_price": 96.0,
    }])
    executor = SimpleNamespace(
        kite=kite, paper_mode=False, _market_unwind=AsyncMock(),
        execute_exit=AsyncMock(), _page_operator=AsyncMock(),
    )
    monkeypatch.setattr(edge, "_executor_for", lambda *_a, **_kw: executor)

    summary = await edge.run_penny_edge_exit(kite, str(db))

    executor._market_unwind.assert_not_awaited()
    assert summary["partial_live"][0]["confirmed_qty"] == 4
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT status,shares,sl_order_id FROM positions"
        ).fetchone() == ("OPEN", 6, None)


@pytest.mark.asyncio
async def test_daily_ohlc_tracker_never_reads_or_settles_live_sources(tmp_path):
    db = tmp_path / "tracker-live.db"
    await _seed(db, source=edge.SOURCE_LIVE, ticker="LIVE")
    kite = SimpleNamespace(get_historical=AsyncMock())
    record = AsyncMock()

    await update_daily_positions(str(db), kite, datetime.now().date().isoformat(), record)

    kite.get_historical.assert_not_awaited()
    record.assert_not_awaited()
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT status,shares,exit_date FROM positions"
        ).fetchone() == ("OPEN", 10, None)


@pytest.mark.asyncio
async def test_daily_tracker_normalises_numpy_ohlc_to_sqlite_real(tmp_path):
    db = tmp_path / "tracker-types.db"
    await _seed(db, source="EDGE_PAPER", ticker="PAPER")
    kite = SimpleNamespace(get_historical=AsyncMock(return_value=pd.DataFrame({
        "open": np.array([100], dtype=np.int64),
        "high": np.array([112], dtype=np.int64),
        "low": np.array([99], dtype=np.int64),
        "close": np.array([108], dtype=np.int64),
    })))
    record = AsyncMock()

    await update_daily_positions(str(db), kite, datetime.now().date().isoformat(), record)

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT typeof(exit_price),typeof(highest_close_since_entry) FROM positions"
        ).fetchone()
    assert row == ("real", "real")
    record.assert_awaited_once()


@pytest.mark.asyncio
async def test_daily_tracker_retries_durable_pnl_delivery_after_callback_failure(tmp_path):
    db = tmp_path / "tracker-outbox.db"
    await _seed(db, source="EDGE_PAPER", ticker="OUTBOX")
    kite = SimpleNamespace(get_historical=AsyncMock(return_value=pd.DataFrame({
        "open": [100.0], "high": [112.0], "low": [99.0], "close": [108.0],
    })))
    record = AsyncMock(side_effect=[RuntimeError("ledger unavailable"), None])

    await update_daily_positions(str(db), kite, datetime.now().date().isoformat(), record)
    await update_daily_positions(str(db), kite, datetime.now().date().isoformat(), record)

    assert record.await_count == 2
    with sqlite3.connect(db) as conn:
        delivered = conn.execute(
            "SELECT delivered FROM position_pnl_outbox"
        ).fetchone()[0]
    assert delivered == 1
