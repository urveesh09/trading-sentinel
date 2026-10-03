"""F0 shared F&O risk read-model and reservation characterization tests."""
from datetime import datetime, timezone

import aiosqlite
import pytest

from fno_dr_book import init_dr_db
from fno_positions import init_fno_positions_db
from fno_shared_risk import (
    init_shared_fno_risk_db,
    reserve_shared_fno_risk,
    resolve_shared_fno_risk_reservation,
    shared_fno_risk_view,
)
from performance import init_ledger


SOURCE = "FNO_PAPER"
POOL = 50_000.0


async def _ready(db_path):
    await init_ledger(db_path)
    await init_fno_positions_db(db_path)
    await init_dr_db(db_path)
    await init_shared_fno_risk_db(db_path)


@pytest.mark.asyncio
async def test_view_combines_exact_cash_and_both_open_books(db_path):
    await _ready(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO bankroll_ledger (timestamp,event_type,pnl,source) VALUES (?,?,?,?)",
            ("2026-10-03T04:30:00+00:00", "TRADE_CLOSED", -1_500.0, SOURCE),
        )
        await db.execute(
            "INSERT INTO fno_positions (source,tradingsymbol,status,max_loss_rupees) VALUES (?,?,?,?)",
            (SOURCE, "NIFTY26OCT25000CE", "OPEN", 7_000.0),
        )
        await db.execute(
            "INSERT INTO fno_dr_positions (source,kind,legs_json,lot_size,lots,max_loss_rs,status) "
            "VALUES (?,?,?,?,?,?,?)",
            (SOURCE, "BULL_CALL_DEBIT", "[]", 75, 1, 4_000.0, "UNRESOLVED"),
        )
        await db.commit()

    view = await shared_fno_risk_view(db_path, SOURCE, POOL)
    assert view.available
    assert view.realised_pnl_rs == -1_500.0
    assert view.equity_rs == 48_500.0
    assert view.open_worst_case_cash_rs == 11_000.0
    assert view.available_worst_case_cash_rs == 37_500.0
    assert (view.single_leg_open_count, view.defined_risk_open_count) == (1, 1)


@pytest.mark.asyncio
async def test_view_fails_closed_for_missing_or_malformed_evidence(db_path):
    missing = await shared_fno_risk_view(db_path, SOURCE, POOL)
    assert not missing.available
    assert missing.available_worst_case_cash_rs is None
    await _ready(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO fno_dr_positions (source,kind,legs_json,lot_size,lots,max_loss_rs,status) "
            "VALUES (?,?,?,?,?,?,?)",
            (SOURCE, "IRON_CONDOR", "[]", 75, 1, None, "OPEN"),
        )
        await db.commit()
    malformed = await shared_fno_risk_view(db_path, SOURCE, POOL)
    assert not malformed.available
    assert malformed.reason == "invalid_defined_risk_worst_case_cash"


@pytest.mark.asyncio
async def test_reservation_is_atomic_idempotent_and_prevents_double_spend(db_path):
    await _ready(db_path)
    first = await reserve_shared_fno_risk(
        db_path, source=SOURCE, pool_rs=POOL, reservation_key="entry-a",
        book="SINGLE_LEG", worst_case_cash_rs=30_000.0,
        created_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
    )
    assert first.allowed and first.reason == "reserved"
    assert first.view.available_worst_case_cash_rs == 20_000.0

    duplicate = await reserve_shared_fno_risk(
        db_path, source=SOURCE, pool_rs=POOL, reservation_key="entry-a",
        book="SINGLE_LEG", worst_case_cash_rs=30_000.0,
    )
    assert duplicate.allowed and duplicate.reason == "already_reserved"
    assert duplicate.view.reserved_worst_case_cash_rs == 30_000.0

    competing = await reserve_shared_fno_risk(
        db_path, source=SOURCE, pool_rs=POOL, reservation_key="entry-b",
        book="DEFINED_RISK", worst_case_cash_rs=20_001.0,
    )
    assert not competing.allowed
    assert competing.reason == "shared_worst_case_cash_exhausted"
    assert competing.view.reserved_worst_case_cash_rs == 30_000.0


@pytest.mark.asyncio
async def test_reservation_never_uses_other_source_capacity(db_path):
    await _ready(db_path)
    await reserve_shared_fno_risk(
        db_path, source="FNO_LIVE", pool_rs=POOL, reservation_key="live-entry",
        book="SINGLE_LEG", worst_case_cash_rs=49_000.0,
    )
    paper = await reserve_shared_fno_risk(
        db_path, source=SOURCE, pool_rs=POOL, reservation_key="paper-entry",
        book="DEFINED_RISK", worst_case_cash_rs=49_000.0,
    )
    assert paper.allowed


@pytest.mark.asyncio
async def test_reservation_requires_auditable_one_way_resolution(db_path):
    await _ready(db_path)
    reserved = await reserve_shared_fno_risk(
        db_path, source=SOURCE, pool_rs=POOL, reservation_key="entry-c",
        book="SINGLE_LEG", worst_case_cash_rs=10_000.0,
    )
    assert reserved.allowed
    assert not await resolve_shared_fno_risk_reservation(
        db_path, reservation_key="entry-c", state="RELEASED",
    )
    assert await resolve_shared_fno_risk_reservation(
        db_path, reservation_key="entry-c", state="RELEASED",
        resolution_reason="executor_rejected_before_fill",
    )
    assert not await resolve_shared_fno_risk_reservation(
        db_path, reservation_key="entry-c", state="CONSUMED", position_ref="fno_position:7",
    )
    view = await shared_fno_risk_view(db_path, SOURCE, POOL)
    assert view.reservation_count == 0
    assert view.available_worst_case_cash_rs == POOL
