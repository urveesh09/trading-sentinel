"""Regression coverage for the pre-CAS momentum EOD ownership boundary."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytz

from config import settings
from position_tracker import init_positions_db


IST = pytz.timezone("Asia/Kolkata")


def _ist(hour: int, minute: int, second: int = 0) -> datetime:
    return IST.localize(datetime(2026, 9, 16, hour, minute, second))


async def _seed_momentum(db_path: str) -> dict:
    await init_positions_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO positions (
                ticker,exchange,entry_date,entry_price,shares,
                stop_loss_initial,trailing_stop_current,target_1,target_2,
                atr_14_at_entry,highest_close_since_entry,status,source,
                product_type,regime_at_entry,sl_order_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "ABC", "NSE", "2026-09-16T05:00:00+00:00", 100.0, 10,
                95.0, 95.0, 110.0, 115.0, 1.0, 100.0, "OPEN",
                "MOMENTUM", "MIS", "PR1_CALM", "SL-OLD",
            ),
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM positions WHERE ticker='ABC'"
        )).fetchone()
    return dict(row)


def test_clock_hands_ownership_to_eod_before_cas():
    import main

    assert main._momentum_exit_clock(_ist(15, 12, 59)) == {
        "monitor_allowed": True, "eod_started": False, "submit_allowed": True,
    }
    assert main._momentum_exit_clock(_ist(15, 13, 0)) == {
        "monitor_allowed": False, "eod_started": True, "submit_allowed": True,
    }
    assert main._momentum_exit_clock(_ist(15, 14, 29))["submit_allowed"] is True
    assert main._momentum_exit_clock(_ist(15, 14, 30))["submit_allowed"] is False


@pytest.mark.asyncio
async def test_monitor_does_not_start_after_eod_handoff(monkeypatch):
    import main

    owned = AsyncMock()
    monkeypatch.setattr(main, "_momentum_intraday_monitor_owned", owned)
    monkeypatch.setattr(main, "is_trading_day", AsyncMock(return_value=True))
    monkeypatch.setattr(
        main, "_momentum_exit_clock",
        lambda: {"monitor_allowed": False, "eod_started": True, "submit_allowed": True},
    )

    await main.momentum_intraday_monitor()

    owned.assert_not_awaited()


@pytest.mark.asyncio
async def test_late_eod_start_never_touches_broker(monkeypatch):
    import main

    owned = AsyncMock()
    notify = AsyncMock()
    monkeypatch.setattr(main, "_auto_square_momentum_owned", owned)
    monkeypatch.setattr(main, "is_trading_day", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "_notify_operator", notify)
    monkeypatch.setattr(
        main, "_momentum_exit_clock",
        lambda: {"monitor_allowed": False, "eod_started": True, "submit_allowed": False},
    )

    await main.auto_square_momentum()

    owned.assert_not_awaited()
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_deadline_after_cancel_rearms_and_persists_stop(tmp_path, monkeypatch):
    import main

    db_path = str(tmp_path / "momentum.db")
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    position = await _seed_momentum(db_path)
    broker = SimpleNamespace(
        cancel_order=AsyncMock(return_value={"status": "CANCELLED"}),
        order_history=AsyncMock(return_value=[{
            "status": "CANCELLED", "filled_quantity": 0,
        }]),
        place_order=AsyncMock(return_value={"order_id": "SL-NEW"}),
    )
    notify = AsyncMock()
    post_square_off = AsyncMock(side_effect=AssertionError("late sell submitted"))
    clock = iter((
        {"monitor_allowed": False, "eod_started": True, "submit_allowed": True},
        {"monitor_allowed": False, "eod_started": True, "submit_allowed": False},
    ))
    monkeypatch.setattr(main, "kite", broker)
    monkeypatch.setattr(main, "is_trading_day", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "get_open_positions", AsyncMock(return_value=[position]))
    monkeypatch.setattr(main, "_notify_operator", notify)
    monkeypatch.setattr(main, "_post_square_off_with_reconcile", post_square_off)
    monkeypatch.setattr(main, "_momentum_exit_clock", lambda: next(clock))

    await main._auto_square_momentum_owned()

    post_square_off.assert_not_awaited()
    broker.place_order.assert_awaited_once()
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute(
            "SELECT sl_order_id,exit_date FROM positions WHERE ticker='ABC'"
        )).fetchone()
    assert row == ("SL-NEW", None)
    assert any(
        call.kwargs.get("event") == "momentum_eod_deadline_stop_restored"
        for call in notify.await_args_list
    )


def test_scheduler_registration_uses_pre_cas_start_and_single_owner():
    source = (__import__("pathlib").Path(__file__).parents[1] / "main.py").read_text(
        encoding="utf-8"
    )
    assert "minute=MOMENTUM_EOD_OWNERSHIP_MINUTE" in source
    assert "id=\"momentum_auto_square\",\n            max_instances=1, coalesce=True" in source
