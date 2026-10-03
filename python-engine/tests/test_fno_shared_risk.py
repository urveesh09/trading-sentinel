"""F0 shared F&O risk read-model and reservation characterization tests."""
import hashlib
from datetime import date, datetime, timezone

import aiosqlite
import pytest

from fno_dr_book import init_dr_db
from fno_costs import calc_fno_costs
from fno_positions import init_fno_positions_db
from fno_shared_risk import (
    init_shared_fno_risk_db,
    SharedFnoRiskPolicy,
    reserve_shared_fno_risk,
    resolve_shared_fno_risk_reservation,
    shared_fno_entry_policy,
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


async def _terminal_cash(db_path, *, pnl, stamp, source=SOURCE, origin_ref=None):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO bankroll_ledger (timestamp,event_type,pnl,source,origin_ref) "
            "VALUES (?,?,?,?,?)",
            (stamp, "TRADE_CLOSED", pnl, source, origin_ref),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_shared_policy_counts_dr_and_partial_cash_for_both_new_books(db_path):
    """Origin labels never decide which F&O loss gets capital protection."""
    await _ready(db_path)
    await _terminal_cash(
        db_path, pnl=-3_100.0, stamp="2026-10-03T10:00:00+05:30",
        origin_ref="fno_dr_structure:17",
    )
    decision = await shared_fno_entry_policy(
        db_path, source=SOURCE, pool_rs=POOL, today_ist=date(2026, 10, 3),
    )
    assert not decision.allowed
    assert decision.reason.startswith("daily_loss_halt")
    assert decision.day_pnl_rs == -3_100.0

    # The one immediate admission operation protects either prospective book
    # with that exact same policy result, rather than a directional-only query.
    for book, key in (("SINGLE_LEG", "single-after-dr-loss"),
                      ("DEFINED_RISK", "dr-after-dr-loss")):
        refused = await reserve_shared_fno_risk(
            db_path, source=SOURCE, pool_rs=POOL, reservation_key=key,
            book=book, worst_case_cash_rs=1_000.0,
            entry_day_ist=date(2026, 10, 3),
        )
        assert not refused.allowed
        assert refused.reason.startswith("daily_loss_halt")


@pytest.mark.asyncio
async def test_shared_policy_keeps_existing_thresholds_and_source_isolation(db_path):
    await _ready(db_path)
    # Four distinct weekdays stay beneath the daily limit but pass the existing
    # 12% weekly brake. A live-source cash row cannot influence paper policy.
    for day in ("2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"):
        await _terminal_cash(
            db_path, pnl=-1_600.0, stamp=f"{day}T10:00:00+05:30",
            origin_ref="fno_position:partial",
        )
    await _terminal_cash(
        db_path, pnl=-50_000.0, stamp="2026-10-02T10:00:00+05:30",
        source="FNO_LIVE", origin_ref="fno_position:live",
    )
    decision = await shared_fno_entry_policy(
        db_path, source=SOURCE, pool_rs=POOL, today_ist=date(2026, 10, 2),
    )
    assert not decision.allowed
    assert decision.reason.startswith("weekly_loss_halt")
    assert not any("daily_loss_halt" in reason for reason in decision.active_halts)


@pytest.mark.asyncio
async def test_shared_policy_drawdown_and_ambiguous_cash_fail_closed(db_path):
    await _ready(db_path)
    await _terminal_cash(
        db_path, pnl=-12_501.0, stamp="2026-10-02T10:00:00+05:30",
        origin_ref="fno_position:3",
    )
    drawdown = await shared_fno_entry_policy(
        db_path, source=SOURCE, pool_rs=POOL, today_ist=date(2026, 10, 3),
    )
    assert not drawdown.allowed
    assert any(reason.startswith("drawdown_halt") for reason in drawdown.active_halts)

    await _terminal_cash(
        db_path, pnl=10.0, stamp="2026-10-03T10:00:00",
        origin_ref="fno_position:ambiguous-clock",
    )
    malformed = await shared_fno_entry_policy(
        db_path, source=SOURCE, pool_rs=POOL, today_ist=date(2026, 10, 3),
    )
    assert not malformed.allowed
    assert malformed.reason == "invalid_terminal_cash_event"


@pytest.mark.asyncio
async def test_shared_policy_preserves_affordable_clean_admission(db_path):
    await _ready(db_path)
    clean = await shared_fno_entry_policy(
        db_path, source=SOURCE, pool_rs=POOL, today_ist=date(2026, 10, 3),
        policy=SharedFnoRiskPolicy(),
    )
    assert clean.allowed
    admitted = await reserve_shared_fno_risk(
        db_path, source=SOURCE, pool_rs=POOL, reservation_key="clean-admission",
        book="DEFINED_RISK", worst_case_cash_rs=1_000.0,
        entry_day_ist=date(2026, 10, 3),
    )
    assert admitted.allowed


@pytest.mark.asyncio
async def test_partial_recovery_residual_requires_exact_cash_and_pro_rata_risk(db_path):
    await _ready(db_path)
    filled, entry, fill = 75, 100.0, 90.0
    gross = (fill - entry) * filled
    costs = calc_fno_costs(entry, fill, filled)
    pnl = gross - costs
    evidence = "{}"
    async with aiosqlite.connect(db_path) as db:
        position = await db.execute(
            "INSERT INTO fno_positions "
            "(source,tradingsymbol,status,qty,initial_qty,max_loss_rupees,initial_max_loss_rupees,"
            "entry_premium,settlement_generation) VALUES (?,?,?,?,?,?,?,?,?)",
            ("FNO_LIVE", "NIFTY26OCT25000CE", "OPEN", 75, 150, 750.0, 1_500.0,
             entry, 1),
        )
        position_id = int(position.lastrowid)
        ledger = await db.execute(
            "INSERT INTO bankroll_ledger "
            "(timestamp,event_type,pnl,source,origin_ref,settlement_generation) "
            "VALUES (?,?,?,?,?,?)",
            ("2026-10-03T10:00:00+05:30", "TRADE_CLOSED", pnl,
             "FNO_LIVE", f"fno_position:{position_id}", 1),
        )
        await db.execute(
            "INSERT INTO fno_exit_recoveries "
            "(position_id,source,intent_created_at,order_id,operator,account_id,"
            "broker_evidence_sha256,broker_evidence_json,terminal_status,filled_qty,"
            "remaining_qty,entry_premium,fill_price,gross_pnl,costs,pnl,settlement_generation,ledger_id,resolved_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (position_id, "FNO_LIVE", "2026-10-03T04:00:00+00:00", "EXIT-1",
             "reviewer", "account", hashlib.sha256(evidence.encode()).hexdigest(), evidence,
             "CANCELLED", filled, 75, entry, fill, gross, costs, pnl, 1,
             int(ledger.lastrowid), "2026-10-03T04:01:00+00:00"),
        )
        await db.commit()

    view = await shared_fno_risk_view(db_path, "FNO_LIVE", POOL)
    assert view.available
    assert view.open_worst_case_cash_rs == 750.0

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE fno_positions SET max_loss_rupees=751.0 WHERE id=?", (position_id,)
        )
        await db.commit()
    tampered = await shared_fno_risk_view(db_path, "FNO_LIVE", POOL)
    assert not tampered.available
    assert tampered.reason == "invalid_partial_recovery_evidence"

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE fno_positions SET max_loss_rupees=750.0 WHERE id=?", (position_id,)
        )
        await db.execute("DELETE FROM bankroll_ledger WHERE id=?", (int(ledger.lastrowid),))
        await db.commit()
    missing_cash = await shared_fno_risk_view(db_path, "FNO_LIVE", POOL)
    assert not missing_cash.available
    assert missing_cash.reason == "invalid_partial_recovery_evidence"


@pytest.mark.asyncio
async def test_partial_recovery_cash_and_receipt_evidence_cannot_be_rewritten(db_path):
    """F0-E prevents a scalar, cash, or receipt edit from creating capacity."""
    await _ready(db_path)
    filled, entry, fill = 75, 100.0, 90.0
    gross = (fill - entry) * filled
    costs = calc_fno_costs(entry, fill, filled)
    pnl = gross - costs
    evidence = "{}"
    async with aiosqlite.connect(db_path) as db:
        position = await db.execute(
            "INSERT INTO fno_positions "
            "(source,tradingsymbol,status,qty,initial_qty,max_loss_rupees,initial_max_loss_rupees,"
            "entry_premium,settlement_generation) VALUES (?,?,?,?,?,?,?,?,?)",
            ("FNO_LIVE", "NIFTY26OCT25000CE", "OPEN", 75, 150, 750.0, 1_500.0,
             entry, 1),
        )
        position_id = int(position.lastrowid)
        ledger = await db.execute(
            "INSERT INTO bankroll_ledger "
            "(timestamp,event_type,pnl,source,origin_ref,settlement_generation) VALUES (?,?,?,?,?,?)",
            ("2026-10-03T10:00:00+05:30", "TRADE_CLOSED", pnl,
             "FNO_LIVE", f"fno_position:{position_id}", 1),
        )
        recovery = await db.execute(
            "INSERT INTO fno_exit_recoveries "
            "(position_id,source,intent_created_at,order_id,operator,account_id,"
            "broker_evidence_sha256,broker_evidence_json,terminal_status,filled_qty,"
            "remaining_qty,entry_premium,fill_price,gross_pnl,costs,pnl,settlement_generation,ledger_id,resolved_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (position_id, "FNO_LIVE", "2026-10-03T04:00:00+00:00", "EXIT-1",
             "reviewer", "account", hashlib.sha256(evidence.encode()).hexdigest(), evidence,
             "CANCELLED", filled, 75, entry, fill, gross, costs, pnl, 1,
             int(ledger.lastrowid), "2026-10-03T04:01:00+00:00"),
        )
        await db.commit()
    assert (await shared_fno_risk_view(db_path, "FNO_LIVE", POOL)).available

    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE bankroll_ledger SET pnl=pnl+1 WHERE id=?", (int(ledger.lastrowid),))
        await db.commit()
    invalid_cash = await shared_fno_risk_view(db_path, "FNO_LIVE", POOL)
    assert not invalid_cash.available
    assert invalid_cash.reason == "invalid_partial_recovery_evidence"

    async with aiosqlite.connect(db_path) as db:
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute("UPDATE fno_positions SET initial_qty=75 WHERE id=?", (position_id,))
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute("UPDATE fno_exit_recoveries SET fill_price=91 WHERE id=?", (int(recovery.lastrowid),))
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute("DELETE FROM fno_exit_recoveries WHERE id=?", (int(recovery.lastrowid),))
