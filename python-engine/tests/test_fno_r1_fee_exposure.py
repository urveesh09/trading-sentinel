"""F0-R1: the fee reserve stays in shared exposure after a reservation is consumed."""
from datetime import datetime, timezone

import aiosqlite
import pytest

import fno_dr_book as book
from fno_costs import calc_fno_costs
from fno_defined_risk import build_debit_spread, structure_round_trip_cost
from fno_dr_book import PlannedStructure, init_dr_db, insert_structure
from fno_models import FnoDirection, OptionType
from fno_positions import init_fno_positions_db, insert_position_with_risk_reservation
from fno_shared_risk import (
    claim_shared_fno_entry_dispatch, init_shared_fno_risk_db, reserve_shared_fno_risk,
    shared_fno_risk_view,
)
from performance import init_ledger
from tests.test_fno_dr_book import LOT, NOW, STEP, FakeSnap

SOURCE = "FNO_PAPER"
FEE = calc_fno_costs(100.0, 0.0, 75)          # 50.57826385 at the current schedule
POOL = 7_500.0 + FEE + 1.0                     # the independent review's pool


async def _ready(db_path):
    await init_ledger(db_path)
    await init_fno_positions_db(db_path)
    await init_dr_db(db_path)
    await init_shared_fno_risk_db(db_path)


def _position(**overrides):
    fields = dict(
        source=SOURCE, tradingsymbol="NIFTY26OCT25000CE", token=1, underlying="NIFTY",
        expiry="2026-10-08", strike=25000.0, opt_type="CE", direction="LONG",
        lots=1, lot_size=75, qty=75, entry_time="2026-10-05T10:00:00+05:30",
        entry_date="2026-10-05", entry_premium=100.0, entry_underlying=25000.0,
        delta_at_entry=0.5, iv_at_entry=0.12, atr_at_entry=40.0,
        stop_underlying=24950.0, target_underlying=25080.0, premium_stop=80.0,
        trail_active=0, trail_stop_underlying=None, best_underlying=25000.0,
        max_loss_rupees=7_500.0, status="OPEN", entry_order_id="PAPER-1",
        bar_ts="2026-10-05T10:00:00+05:30",
    )
    fields.update(overrides)
    return fields


async def _reserve(db_path, key, amount, book_name="SINGLE_LEG", *, claim=True, pool=POOL):
    """Reserve, then (as every real caller must, F0-R2) claim the dispatch."""
    admission = await reserve_shared_fno_risk(
        db_path, source=SOURCE, pool_rs=pool, reservation_key=key,
        book=book_name, worst_case_cash_rs=amount,
        created_at=datetime(2026, 10, 5, 4, 30, tzinfo=timezone.utc),
    )
    if admission.allowed and claim:
        granted = await claim_shared_fno_entry_dispatch(
            db_path, reservation_key=key, source=SOURCE, book=book_name,
            pool_rs=pool, entry_day_ist=None,
        )
        assert granted.granted, granted.reason
    return admission


@pytest.mark.asyncio
async def test_review_reproduction_single_leg_fee_is_not_released_on_consumption(db_path):
    await _ready(db_path)
    admitted = await _reserve(db_path, "single-a", 7_500.0 + FEE)
    assert admitted.allowed
    before = admitted.view.available_worst_case_cash_rs
    assert before == pytest.approx(1.0)

    await insert_position_with_risk_reservation(db_path, reservation_key="single-a", **_position())
    after = await shared_fno_risk_view(db_path, SOURCE, POOL)
    assert after.available
    assert after.reserved_worst_case_cash_rs == 0.0
    assert after.open_fee_reserve_rs == pytest.approx(FEE)
    assert after.open_worst_case_cash_rs == pytest.approx(7_500.0 + FEE)
    assert after.available_worst_case_cash_rs == pytest.approx(before)   # was 51.58 before R1

    competing = await _reserve(db_path, "single-b", FEE, "DEFINED_RISK", claim=False)
    assert not competing.allowed
    assert competing.reason == "shared_worst_case_cash_exhausted"


@pytest.mark.asyncio
async def test_fee_reserve_uses_actual_fill_and_quantity_and_only_verified_difference_is_released(db_path):
    await _ready(db_path)
    await _reserve(db_path, "single-a", 7_500.0 + FEE)        # planned at ask 100
    await insert_position_with_risk_reservation(
        db_path, reservation_key="single-a", **_position(entry_premium=99.0),
    )
    async with aiosqlite.connect(db_path) as db:
        stored = (await (await db.execute(
            "SELECT risk_fee_reserve_rupees FROM fno_positions")).fetchone())[0]
    assert stored == pytest.approx(calc_fno_costs(99.0, 0.0, 75))
    view = await shared_fno_risk_view(db_path, SOURCE, POOL)
    released = FEE - calc_fno_costs(99.0, 0.0, 75)
    assert 0 <= released < 1.0
    assert view.available_worst_case_cash_rs == pytest.approx(1.0 + released)


@pytest.mark.asyncio
async def test_lifecycle_counts_exposure_once_and_hands_over_to_exact_cash(db_path):
    """RESERVED -> OPEN -> UNRESOLVED -> CLOSED at the catastrophe: capacity is conserved."""
    await _ready(db_path)
    reserved = await _reserve(db_path, "single-a", 7_500.0 + FEE)
    capacity = reserved.view.available_worst_case_cash_rs
    position_id = await insert_position_with_risk_reservation(
        db_path, reservation_key="single-a", **_position(),
    )
    states = [(await shared_fno_risk_view(db_path, SOURCE, POOL)).available_worst_case_cash_rs]
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE fno_positions SET status='UNRESOLVED' WHERE id=?", (position_id,))
        await db.commit()
    unresolved = await shared_fno_risk_view(db_path, SOURCE, POOL)
    states.append(unresolved.available_worst_case_cash_rs)
    assert unresolved.single_leg_open_count == 1
    async with aiosqlite.connect(db_path) as db:
        # As the exact settlement writer does: generation 1 plus its one cash row.
        await db.execute("UPDATE fno_positions SET status='CLOSED', settlement_generation=1 "
                         "WHERE id=?", (position_id,))
        await db.execute(
            "INSERT INTO bankroll_ledger (timestamp,event_type,pnl,source,origin_ref,settlement_generation) "
            "VALUES (?,?,?,?,?,?)",
            ("2026-10-05T09:00:00+00:00", "TRADE_CLOSED", -(7_500.0 + FEE), SOURCE,
             f"fno_position:{position_id}", 1),
        )
        await db.commit()
    closed = await shared_fno_risk_view(
        db_path, SOURCE, POOL, observed_at=datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc))
    states.append(closed.available_worst_case_cash_rs)
    assert closed.open_worst_case_cash_rs == 0.0 and closed.open_fee_reserve_rs == 0.0
    assert states == pytest.approx([capacity] * 3)


@pytest.mark.asyncio
async def test_review_reproduction_defined_risk_keeps_frozen_entry_cost(db_path):
    await _ready(db_path)
    spread = build_debit_spread(
        FnoDirection.LONG, 25000, STEP, 2,
        lambda o, k: {(OptionType.CE, 25000.0): 120.0, (OptionType.CE, 25100.0): 50.0}.get((o, k)),
        LOT,
    )
    snap = FakeSnap(25000, {(25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0})
    planned = PlannedStructure(
        structure=spread, entry_underlying=25000.0,
        contract_legs=book._selected_contract_legs(snap, spread.legs),
    )
    worst = spread.max_loss_rs + structure_round_trip_cost(spread)
    pool = worst + 1.0
    admitted = await _reserve(db_path, "dr-a", worst, "DEFINED_RISK", pool=pool)
    assert admitted.allowed
    await insert_structure(db_path, SOURCE, planned, NOW, reservation_key="dr-a")
    view = await shared_fno_risk_view(db_path, SOURCE, pool)
    assert view.open_fee_reserve_rs == pytest.approx(structure_round_trip_cost(spread))
    assert view.available_worst_case_cash_rs == pytest.approx(1.0)
    refused = await reserve_shared_fno_risk(
        db_path, source=SOURCE, pool_rs=pool, reservation_key="single-b",
        book="SINGLE_LEG", worst_case_cash_rs=structure_round_trip_cost(spread),
    )
    assert not refused.allowed


@pytest.mark.asyncio
@pytest.mark.parametrize("table,sql,reason", [
    ("fno_positions",
     "INSERT INTO fno_positions (source,tradingsymbol,status,qty,entry_premium,max_loss_rupees) "
     "VALUES ('FNO_PAPER','X','OPEN',75,100.0,7500.0)", "single_leg_fee_reserve_unbound"),
    ("fno_positions",
     "INSERT INTO fno_positions (source,tradingsymbol,status,qty,entry_premium,max_loss_rupees,"
     "risk_fee_reserve_rupees) VALUES ('FNO_PAPER','X','UNRESOLVED',75,100.0,7500.0,-1.0)",
     "single_leg_fee_reserve_unbound"),
    ("fno_positions",
     "INSERT INTO fno_positions (source,tradingsymbol,status,qty,entry_premium,max_loss_rupees,"
     "risk_fee_reserve_rupees) VALUES ('FNO_PAPER','X','OPEN',75,100.0,1500.0,50.0)",
     "structural_loss_below_premium_at_risk"),
    ("fno_positions",
     "INSERT INTO fno_positions (source,tradingsymbol,status,qty,max_loss_rupees,"
     "risk_fee_reserve_rupees) VALUES ('FNO_PAPER','X','OPEN',75,7500.0,50.0)",
     "structural_loss_below_premium_at_risk"),
    ("fno_dr_positions",
     "INSERT INTO fno_dr_positions (source,kind,legs_json,lot_size,lots,max_loss_rs,status) "
     "VALUES ('FNO_PAPER','DEBIT_SPREAD','[]',75,1,4000.0,'OPEN')", "defined_risk_fee_reserve_unbound"),
])
async def test_unbound_or_inconsistent_economics_fail_closed(db_path, table, sql, reason):
    await _ready(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(sql)
        await db.commit()
    view = await shared_fno_risk_view(db_path, SOURCE, 50_000.0)
    assert not view.available and view.available_worst_case_cash_rs is None
    assert view.reason == reason


@pytest.mark.asyncio
async def test_closed_legacy_rows_without_fee_evidence_do_not_block(db_path):
    await _ready(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT INTO fno_positions (source,tradingsymbol,status,max_loss_rupees) "
                         "VALUES ('FNO_PAPER','X','CLOSED',1500.0)")
        await db.execute("INSERT INTO fno_dr_positions (source,kind,legs_json,lot_size,lots,max_loss_rs,status) "
                         "VALUES ('FNO_PAPER','DEBIT_SPREAD','[]',75,1,4000.0,'CLOSED')")
        await db.commit()
    view = await shared_fno_risk_view(db_path, SOURCE, 50_000.0)
    assert view.available and view.available_worst_case_cash_rs == 50_000.0


@pytest.mark.asyncio
async def test_frozen_exposure_evidence_cannot_be_rewritten(db_path):
    await _ready(db_path)
    await _reserve(db_path, "single-a", 7_500.0 + FEE)
    position_id = await insert_position_with_risk_reservation(
        db_path, reservation_key="single-a", **_position(),
    )
    async with aiosqlite.connect(db_path) as db:
        dr = await db.execute(
            "INSERT INTO fno_dr_positions (source,kind,legs_json,lot_size,lots,max_loss_rs,"
            "entry_cost_rs,status) VALUES ('FNO_PAPER','DEBIT_SPREAD','[]',75,1,4000.0,90.0,'OPEN')")
        await db.commit()
        with pytest.raises(aiosqlite.IntegrityError, match="fee reserve is immutable"):
            await db.execute("UPDATE fno_positions SET risk_fee_reserve_rupees=0 WHERE id=?",
                             (position_id,))
        with pytest.raises(aiosqlite.IntegrityError, match="exposure evidence is immutable"):
            await db.execute("UPDATE fno_dr_positions SET entry_cost_rs=0 WHERE id=?", (dr.lastrowid,))
        with pytest.raises(aiosqlite.IntegrityError, match="exposure evidence is immutable"):
            await db.execute("UPDATE fno_dr_positions SET max_loss_rs=1 WHERE id=?", (dr.lastrowid,))
        # Lifecycle writers remain free to change status/settlement columns.
        await db.execute("UPDATE fno_dr_positions SET status='UNRESOLVED' WHERE id=?", (dr.lastrowid,))
        await db.commit()
