from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from config import settings
from penny_executor import PennyExecutor
from penny_models import PennyLeg
from performance import init_ledger
from position_tracker import init_positions_db


@pytest.mark.asyncio
async def test_paper_exit_never_touches_broker_and_is_deterministic():
    kite = SimpleNamespace(
        place_order=AsyncMock(side_effect=AssertionError("broker called")),
        get_quote=AsyncMock(side_effect=AssertionError("quote called")),
        order_history=AsyncMock(side_effect=AssertionError("history called")),
    )
    executor = PennyExecutor(kite, paper_mode=True)

    first = await executor.execute_exit(
        "ABC", PennyLeg.MIS, 10, reference_price=100.0,
    )
    second = await executor.execute_exit(
        "ABC", PennyLeg.MIS, 10, reference_price=100.0,
    )

    assert first == second
    assert first["status"] == "COMPLETE"
    assert first["confirmed_qty"] == 10
    assert first["fill_price"] == 99.0
    assert first["order_id"].startswith("PAPER-EXIT-")
    kite.place_order.assert_not_awaited()
    kite.get_quote.assert_not_awaited()
    kite.order_history.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_exit_settles_only_broker_confirmed_partial():
    kite = SimpleNamespace(
        place_order=AsyncMock(),
        order_history=AsyncMock(return_value=[{
            "status": "CANCELLED", "filled_quantity": 4,
            "average_price": 98.5,
        }]),
    )
    executor = PennyExecutor(
        kite, paper_mode=False, fill_timeout_sec=0.01, poll_interval_sec=0.001,
    )
    executor._page_operator = AsyncMock()

    result = await executor.execute_exit(
        "ABC", PennyLeg.MIS, 10,
        reference_price=100.0, existing_order_id="ORDER-1",
    )

    assert result["status"] == "PARTIAL"
    assert result["confirmed_qty"] == 4
    assert result["fill_price"] == 98.5
    kite.place_order.assert_not_awaited()
    executor._page_operator.assert_awaited_once()


@pytest.mark.asyncio
async def test_live_rejection_is_not_a_close_and_pages_operator():
    kite = SimpleNamespace(
        place_order=AsyncMock(return_value={
            "status": "REJECTED", "message": "blocked",
        }),
    )
    executor = PennyExecutor(kite, paper_mode=False)
    executor._page_operator = AsyncMock()

    result = await executor.execute_exit(
        "ABC", PennyLeg.MIS, 10, reference_price=100.0,
    )

    assert result["status"] == "REJECTED"
    assert result["confirmed_qty"] == 0
    assert result["order_id"] is None
    executor._page_operator.assert_awaited_once()


@pytest.mark.asyncio
async def test_entry_timeout_open_order_is_unverified_not_dead():
    kite = SimpleNamespace(
        instrument_cache={"ABC": 123},
        get_quote=AsyncMock(return_value={123: {"last_price": 100.0}}),
        place_order=AsyncMock(return_value={"order_id": "ENTRY-1"}),
        order_history=AsyncMock(return_value=[{"status": "OPEN"}]),
        cancel_order=AsyncMock(return_value={
            "order_id": "ENTRY-1", "status": "ERROR", "message": "timeout",
        }),
        get_broker_positions=AsyncMock(return_value={"net": []}),
    )
    executor = PennyExecutor(
        kite, paper_mode=False, fill_timeout_sec=0.001, poll_interval_sec=0.001,
    )
    executor._page_operator = AsyncMock()

    result = await executor.execute_entry(
        "ABC", PennyLeg.MIS, entry_price=100.0, stop_loss=95.0, shares=2,
    )

    assert result["entry_status"] == "timeout"
    assert "unverified" in result["reject_reason"]
    executor._page_operator.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconcile_open_order_with_empty_positions_is_unverified():
    kite = SimpleNamespace(
        order_history=AsyncMock(return_value=[{"status": "OPEN"}]),
        get_broker_positions=AsyncMock(return_value={"net": []}),
    )
    executor = PennyExecutor(kite, paper_mode=False)
    assert await executor._reconcile_after_timeout("ABC", "ENTRY-1", 2) == "UNVERIFIED"


async def _seed_position(db_path: str) -> dict:
    await init_positions_db(db_path)
    await init_ledger(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            INSERT INTO positions (
                ticker,exchange,entry_date,entry_price,shares,
                stop_loss_initial,trailing_stop_current,target_1,target_2,
                atr_14_at_entry,highest_close_since_entry,status,source,
                product_type,regime_at_entry,penny_attempt_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            "ABC", "NSE", "2026-08-31T06:00:00+00:00", 100.0, 10,
            95.0, 95.0, 110.0, 115.0, 1.0, 100.0, "OPEN",
            "PENNY_PAPER", "MIS", "PR1_CALM", "pen-test-entry",
        ))
        await db.commit()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM positions WHERE ticker='ABC'"
        )).fetchone()
    return dict(row)


@pytest.mark.asyncio
async def test_confirmed_settlement_is_atomic_and_restart_idempotent():
    import main

    position = await _seed_position(settings.DB_PATH)
    first = await main._settle_confirmed_penny_exit(
        position, confirmed_qty=10, fill_price=99.0, reason="mis_time_stop",
    )
    replay = await main._settle_confirmed_penny_exit(
        position, confirmed_qty=10, fill_price=99.0, reason="mis_time_stop",
    )

    assert first["settled"] == 10
    assert replay["settled"] == 0
    async with aiosqlite.connect(settings.DB_PATH) as db:
        pos = await (await db.execute(
            "SELECT status,shares,exit_date,realised_pnl FROM positions"
        )).fetchone()
        ledger_count = (await (await db.execute(
            "SELECT COUNT(*) FROM bankroll_ledger WHERE source='PENNY_PAPER'"
        )).fetchone())[0]
    assert pos[0] == "CLOSED_TIME"
    assert pos[1] == 0
    assert pos[2]
    assert pos[3] < -10.0  # adverse fill plus deterministic MIS costs
    assert ledger_count == 1


@pytest.mark.asyncio
async def test_scheduled_paper_exit_journals_once_and_settles_locally(monkeypatch):
    import main

    position = await _seed_position(settings.DB_PATH)
    kite = SimpleNamespace(
        place_order=AsyncMock(side_effect=AssertionError("broker called")),
        get_quote=AsyncMock(side_effect=AssertionError("quote called")),
    )
    executor = PennyExecutor(kite, paper_mode=True)
    monkeypatch.setattr(
        main, "_penny_scanner", SimpleNamespace(executor=executor, source_tag="PENNY_PAPER"),
    )

    result = await main._execute_scheduled_penny_exit(
        position, reason="mis_time_stop", reference_price=100.0,
    )
    assert result["settlement"]["settled"] == 10
    kite.place_order.assert_not_awaited()
    kite.get_quote.assert_not_awaited()

    async with aiosqlite.connect(settings.DB_PATH) as db:
        events = await (await db.execute("""
            SELECT event_type,COUNT(*) FROM penny_execution_events
            GROUP BY event_type ORDER BY event_type
        """)).fetchall()
    assert dict(events) == {
        "EXIT_CONFIRMED": 1,
        "EXIT_SIMULATED": 1,
        "POSITION_EXIT_SETTLED": 1,
    }


@pytest.mark.asyncio
async def test_unconfirmed_protective_stop_blocks_second_live_sell(monkeypatch):
    import main

    position = await _seed_position(settings.DB_PATH)
    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.execute(
            "UPDATE positions SET source='PENNY', sl_order_id='SL-1' WHERE ticker='ABC'"
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        position = dict(await (await db.execute(
            "SELECT * FROM positions WHERE ticker='ABC'"
        )).fetchone())
    kite = SimpleNamespace(
        cancel_order=AsyncMock(return_value={"status": "ERROR"}),
        order_history=AsyncMock(return_value=[{"status": "OPEN"}]),
        place_order=AsyncMock(side_effect=AssertionError("second sell submitted")),
    )
    executor = PennyExecutor(kite, paper_mode=False)
    executor._page_operator = AsyncMock()
    monkeypatch.setattr(
        main, "_penny_scanner", SimpleNamespace(executor=executor, source_tag="PENNY"),
    )

    result = await main._execute_scheduled_penny_exit(
        position, reason="mis_time_stop", reference_price=100.0,
    )

    assert result["status"] == "UNKNOWN"
    assert result["confirmed_qty"] == 0
    kite.place_order.assert_not_awaited()
    executor._page_operator.assert_awaited_once()


@pytest.mark.asyncio
async def test_partial_protective_stop_fill_is_consumed_once(monkeypatch):
    import main

    position = await _seed_position(settings.DB_PATH)
    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.execute(
            "UPDATE positions SET source='PENNY', sl_order_id='SL-1' WHERE ticker='ABC'"
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        position = dict(await (await db.execute(
            "SELECT * FROM positions WHERE ticker='ABC'"
        )).fetchone())
    kite = SimpleNamespace(
        cancel_order=AsyncMock(return_value={"status": "CANCELLED"}),
        order_history=AsyncMock(return_value=[{
            "status": "CANCELLED", "filled_quantity": 4,
            "average_price": 98.0,
        }]),
        place_order=AsyncMock(return_value={
            "status": "REJECTED", "message": "test residual rejection",
        }),
    )
    executor = PennyExecutor(kite, paper_mode=False)
    executor._page_operator = AsyncMock()
    monkeypatch.setattr(
        main, "_penny_scanner", SimpleNamespace(executor=executor, source_tag="PENNY"),
    )

    first = await main._execute_scheduled_penny_exit(
        position, reason="smart_eod", reference_price=100.0,
    )
    assert first["settlement"]["settled"] == 4
    kite.place_order.assert_not_awaited()
    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        residual = dict(await (await db.execute(
            "SELECT * FROM positions WHERE ticker='ABC'"
        )).fetchone())
        ledger_before = (await (await db.execute(
            "SELECT COUNT(*) FROM bankroll_ledger WHERE source='PENNY'"
        )).fetchone())[0]
    assert residual["shares"] == 6
    assert residual["sl_order_id"] is None

    await main._execute_scheduled_penny_exit(
        residual, reason="mis_time_stop", reference_price=100.0,
    )
    async with aiosqlite.connect(settings.DB_PATH) as db:
        ledger_after = (await (await db.execute(
            "SELECT COUNT(*) FROM bankroll_ledger WHERE source='PENNY'"
        )).fetchone())[0]
    assert ledger_after == ledger_before


@pytest.mark.asyncio
async def test_lost_exit_response_recovers_stable_tag_without_second_sell(monkeypatch):
    import main

    position = await _seed_position(settings.DB_PATH)
    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.execute("UPDATE positions SET source='PENNY' WHERE ticker='ABC'")
        await db.commit()
        db.row_factory = aiosqlite.Row
        position = dict(await (await db.execute(
            "SELECT * FROM positions WHERE ticker='ABC'"
        )).fetchone())

    accepted = {}

    async def place_then_lose_response(**kwargs):
        accepted.update(kwargs)
        raise TimeoutError("response lost after broker acceptance")

    async def order_book():
        if not accepted:
            return []
        return [{
            "order_id": "EXIT-1", "tag": accepted["tag"],
            "tradingsymbol": "ABC", "transaction_type": "SELL",
            "product": "MIS", "quantity": 10, "status": "COMPLETE",
        }]

    kite = SimpleNamespace(
        orders_snapshot=AsyncMock(side_effect=order_book),
        place_order=AsyncMock(side_effect=place_then_lose_response),
        order_history=AsyncMock(return_value=[{
            "status": "COMPLETE", "filled_quantity": 10,
            "average_price": 99.0,
        }]),
    )
    executor = PennyExecutor(
        kite, paper_mode=False, fill_timeout_sec=0.01, poll_interval_sec=0.001,
    )
    executor._page_operator = AsyncMock()
    monkeypatch.setattr(
        main, "_penny_scanner", SimpleNamespace(executor=executor, source_tag="PENNY"),
    )

    first = await main._execute_scheduled_penny_exit(
        position, reason="mis_time_stop", reference_price=100.0,
    )
    assert first["status"] == "UNKNOWN"
    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        still_open = dict(await (await db.execute(
            "SELECT * FROM positions WHERE ticker='ABC'"
        )).fetchone())
    assert still_open["exit_date"] is None

    recovered = await main._execute_scheduled_penny_exit(
        still_open, reason="mis_time_stop", reference_price=100.0,
    )
    assert recovered["status"] == "COMPLETE"
    assert recovered["settlement"]["settled"] == 10
    assert kite.place_order.await_count == 1
    assert len(accepted["tag"]) <= 20


@pytest.mark.asyncio
async def test_unreadable_order_book_blocks_new_live_exit(monkeypatch):
    import main

    position = await _seed_position(settings.DB_PATH)
    position["source"] = "PENNY"
    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.execute("UPDATE positions SET source='PENNY' WHERE ticker='ABC'")
        await db.commit()
    kite = SimpleNamespace(
        orders_snapshot=AsyncMock(return_value=None),
        place_order=AsyncMock(side_effect=AssertionError("SELL must not be sent")),
    )
    executor = PennyExecutor(kite, paper_mode=False)
    executor._page_operator = AsyncMock()
    monkeypatch.setattr(
        main, "_penny_scanner", SimpleNamespace(executor=executor, source_tag="PENNY"),
    )

    result = await main._execute_scheduled_penny_exit(
        position, reason="mis_time_stop", reference_price=100.0,
    )
    assert result["status"] == "UNKNOWN"
    kite.place_order.assert_not_awaited()
    executor._page_operator.assert_awaited_once()


@pytest.mark.asyncio
async def test_definitive_exit_rejection_returns_rejected_not_crash(monkeypatch):
    import main

    position = await _seed_position(settings.DB_PATH)
    position["source"] = "PENNY"
    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.execute("UPDATE positions SET source='PENNY' WHERE ticker='ABC'")
        await db.commit()
    kite = SimpleNamespace(
        orders_snapshot=AsyncMock(return_value=[]),
        place_order=AsyncMock(return_value={"status": "REJECTED", "message": "blocked"}),
    )
    executor = PennyExecutor(kite, paper_mode=False)
    executor._page_operator = AsyncMock()
    monkeypatch.setattr(
        main, "_penny_scanner", SimpleNamespace(executor=executor, source_tag="PENNY"),
    )

    result = await main._execute_scheduled_penny_exit(
        position, reason="mis_time_stop", reference_price=100.0,
    )

    assert result["status"] == "REJECTED"
    executor._page_operator.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminal_zero_fill_advances_to_deterministic_retry_tag():
    snapshots = [
        [{
            "order_id": "DEAD-1", "tag": "PENX0000000000000000",
            "tradingsymbol": "ABC", "transaction_type": "SELL",
            "product": "MIS", "quantity": 10, "status": "CANCELLED",
            "filled_quantity": 0,
        }],
        [],
    ]
    executor = PennyExecutor(
        SimpleNamespace(orders_snapshot=AsyncMock(side_effect=snapshots)),
        paper_mode=False,
    )

    recovered = await executor.resolve_unwind_tag(
        "PENX0000000000000000", "ABC", PennyLeg.MIS, 10,
    )

    assert recovered["status"] == "NOT_FOUND"
    assert recovered["tag"].startswith("PNRT")
    assert len(recovered["tag"]) == 20


@pytest.mark.asyncio
async def test_residual_stop_tag_fits_kite_limit(monkeypatch):
    import main

    broker = SimpleNamespace(place_order=AsyncMock(return_value={"order_id": "SL2"}))
    monkeypatch.setattr(main, "kite", broker)
    order_id = await main._rearm_momentum_residual_stop({
        "ticker": "ABC", "trailing_stop_current": 95.0,
        "product_type": "MIS",
    }, 3)
    assert order_id == "SL2"
    assert len(broker.place_order.await_args.kwargs["tag"]) <= 20


def test_square_off_contract_requires_quantity_and_average_price():
    import main

    unknown = SimpleNamespace(json=lambda: {
        "state": "UNKNOWN", "filled_quantity": 0, "average_price": None,
        "order_id": "O1",
    })
    partial = SimpleNamespace(json=lambda: {
        "state": "PARTIAL", "filled_quantity": 3, "average_price": 101.25,
        "order_id": "O2",
    })
    assert not main._square_off_fill_evidence(unknown, 10)["confirmed"]
    evidence = main._square_off_fill_evidence(partial, 10)
    assert evidence["confirmed"] and not evidence["complete"]
    assert evidence["remaining_quantity"] == 7
    terminal_full = SimpleNamespace(json=lambda: {
        "state": "PARTIAL", "terminal": True,
        "filled_quantity": 10, "average_price": 101.0, "order_id": "O3",
    })
    assert main._square_off_fill_evidence(terminal_full, 10)["complete"]


def test_momentum_square_off_key_ignores_scheduler_reason():
    import main

    pos = {
        "source": "MOMENTUM", "ticker": "ABC",
        "entry_date": "2026-08-31T06:00:00+00:00",
        "shares": 10, "product_type": "MIS",
    }
    first = main._momentum_square_off_key(pos)
    pos["reason"] = "AUTO_SQUARE_EOD"
    assert main._momentum_square_off_key(pos) == first
    pos["shares"] = 7
    assert main._momentum_square_off_key(pos) != first
