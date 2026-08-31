import asyncio

import aiosqlite
import pytest

from penny_position_reservations import (
    persist_reserved_penny_position,
    reserve_penny_position,
    set_penny_reservation_state,
)
from position_tracker import init_positions_db


async def _reserve(db, attempt, ticker, *, source="PENNY_PAPER", leg="MIS",
                   total=5, leg_cap=3):
    return await reserve_penny_position(
        str(db), attempt_id=attempt, source=source, ticker=ticker,
        product_type=leg, max_total=total, max_leg=leg_cap,
    )


@pytest.mark.asyncio
async def test_concurrent_total_cap_has_no_snapshot_race(tmp_path):
    db = tmp_path / "positions.db"
    await init_positions_db(str(db))
    results = await asyncio.gather(*(
        _reserve(db, f"attempt-{i}", f"TICKER{i}", total=2, leg_cap=5)
        for i in range(8)
    ))
    assert sum(item.granted for item in results) == 2
    async with aiosqlite.connect(db) as connection:
        count = (await (await connection.execute("""
            SELECT COUNT(*) FROM penny_position_reservations
            WHERE source='PENNY_PAPER' AND state='RESERVED'
        """)).fetchone())[0]
    assert count == 2


@pytest.mark.asyncio
async def test_same_ticker_is_unique_across_attempts_and_later_bars(tmp_path):
    db = tmp_path / "positions.db"
    await init_positions_db(str(db))
    first, second = await asyncio.gather(
        _reserve(db, "bar-1", " amdind "),
        _reserve(db, "bar-2", "AMDIND"),
    )
    assert sorted((first.granted, second.granted)) == [False, True]
    refused = second if first.granted else first
    assert refused.reason == "source_ticker_already_occupied"

    # A later bar is a new attempt identity, but cannot reopen the ticker.
    later = await _reserve(db, "bar-3", "AMDIND")
    assert later.granted is False
    assert later.reason == "source_ticker_already_occupied"


@pytest.mark.asyncio
async def test_same_attempt_retry_is_fail_closed(tmp_path):
    db = tmp_path / "positions.db"
    await init_positions_db(str(db))
    assert (await _reserve(db, "crash-window", "AMDIND")).granted
    retry = await _reserve(db, "crash-window", "AMDIND")
    assert retry.granted is False
    assert retry.idempotent is True
    assert retry.reason == "attempt_already_reserved"


@pytest.mark.asyncio
async def test_live_and_paper_occupancy_are_isolated(tmp_path):
    db = tmp_path / "positions.db"
    await init_positions_db(str(db))
    paper, live = await asyncio.gather(
        _reserve(db, "paper-1", "SAKHTISUG", source="PENNY_PAPER"),
        _reserve(db, "live-1", "SAKHTISUG", source="PENNY"),
    )
    assert paper.granted and live.granted


@pytest.mark.asyncio
async def test_product_type_caps_use_positions_and_reservations(tmp_path):
    db = tmp_path / "positions.db"
    await init_positions_db(str(db))
    async with aiosqlite.connect(db) as connection:
        await connection.execute("""
            INSERT INTO positions
                (ticker,source,status,product_type,exit_date)
            VALUES ('OLDMIS','PENNY_PAPER','OPEN','MIS',NULL),
                   ('OLDCNC','PENNY_PAPER','OPEN','CNC',NULL),
                   ('CLOSED','PENNY_PAPER','CLOSED','MIS','2026-08-30T10:00:00+00:00')
        """)
        await connection.commit()

    denied_mis = await _reserve(db, "mis-new", "MISNEW", leg="MIS", total=5, leg_cap=1)
    assert not denied_mis.granted
    assert denied_mis.reason == "max_mis_reached:1/1"
    allowed_cnc = await _reserve(db, "cnc-new", "CNCNEW", leg="CNC", total=5, leg_cap=2)
    assert allowed_cnc.granted


@pytest.mark.asyncio
async def test_unknown_outcome_stays_fail_closed_and_is_reconcilable(tmp_path):
    db = tmp_path / "positions.db"
    await init_positions_db(str(db))
    assert (await _reserve(db, "ambiguous", "RANASUG")).granted
    assert await set_penny_reservation_state(
        str(db), attempt_id="ambiguous", state="UNRESOLVED",
        note="broker transport failed after submission",
    )
    assert not (await _reserve(db, "next-bar", "RANASUG")).granted

    # Explicit reconciliation can safely free it; no TTL silently does so.
    assert await set_penny_reservation_state(
        str(db), attempt_id="ambiguous", state="RELEASED",
        note="broker confirms no position and no open order",
    )
    assert (await _reserve(db, "after-reconcile", "RANASUG")).granted


@pytest.mark.asyncio
async def test_position_insert_and_fulfillment_are_atomic_and_idempotent(tmp_path):
    db = tmp_path / "positions.db"
    await init_positions_db(str(db))
    assert (await _reserve(db, "filled-1", "VPRPL")).granted
    values = {
        "ticker": "VPRPL", "exchange": "NSE",
        "entry_date": "2026-08-31T04:00:00+00:00", "entry_price": 42.5,
        "shares": 10, "stop_loss_initial": 41.0,
        "trailing_stop_current": 41.0, "target_1": 44.0, "target_2": 46.0,
        "atr_14_at_entry": 0.0, "highest_close_since_entry": 42.5,
        "status": "OPEN", "source": "PENNY_PAPER", "product_type": "MIS",
        "regime_at_entry": "PR1_CALM", "sl_order_id": "PAPER-SL-1",
    }
    row_id = await persist_reserved_penny_position(
        str(db), attempt_id="filled-1", values=values,
    )
    assert await persist_reserved_penny_position(
        str(db), attempt_id="filled-1", values=values,
    ) == row_id
    async with aiosqlite.connect(db) as connection:
        positions = (await (await connection.execute(
            "SELECT COUNT(*) FROM positions WHERE penny_attempt_id='filled-1'"
        )).fetchone())[0]
        state = (await (await connection.execute("""
            SELECT state FROM penny_position_reservations WHERE attempt_id='filled-1'
        """)).fetchone())[0]
    assert positions == 1
    assert state == "FULFILLED"


@pytest.mark.asyncio
async def test_legacy_duplicate_positions_do_not_break_new_db_invariant(tmp_path):
    db = tmp_path / "positions.db"
    await init_positions_db(str(db))
    async with aiosqlite.connect(db) as connection:
        await connection.execute("""
            INSERT INTO positions (ticker,source,status,product_type,exit_date)
            VALUES ('DUP','PENNY_PAPER','OPEN','MIS',NULL),
                   ('DUP','PENNY_PAPER','OPEN','MIS',NULL)
        """)
        await connection.commit()
    denied = await _reserve(db, "new-attempt", "DUP")
    assert not denied.granted
    assert denied.reason == "source_ticker_already_occupied"
