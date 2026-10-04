"""F0-R3: canonical cash events, bounded observation clock, completed-trade streak."""
from datetime import date, datetime, timedelta, timezone

import aiosqlite
import pytest

from fno_dr_book import init_dr_db
from fno_positions import init_fno_positions_db
from fno_shared_risk import (
    SharedFnoRiskPolicy, init_shared_fno_risk_db, shared_fno_entry_policy, shared_fno_risk_view,
)
from performance import init_ledger

SOURCE = "FNO_PAPER"
POOL = 50_000.0
TODAY = date(2026, 10, 5)                                    # Monday
NOON = datetime(2026, 10, 5, 6, 30, tzinfo=timezone.utc)     # 12:00 IST
POLICY = SharedFnoRiskPolicy()


async def _ready(db_path):
    await init_ledger(db_path)
    await init_fno_positions_db(db_path)
    await init_dr_db(db_path)
    await init_shared_fno_risk_db(db_path)


async def _cash(db_path, at, pnl, *, event_type="TRADE_CLOSED", origin=None, generation=0,
                source=SOURCE):
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "INSERT INTO bankroll_ledger (timestamp,event_type,pnl,source,origin_ref,"
            "settlement_generation) VALUES (?,?,?,?,?,?)",
            (at if isinstance(at, str) else at.isoformat(), event_type, pnl, source, origin,
             generation),
        )
        await db.commit()
        return cur.lastrowid


async def _position(db_path, *, status="CLOSED", generation=1, **extra):
    fields = {"source": SOURCE, "tradingsymbol": "NIFTYX", "status": status,
              "settlement_generation": generation, **extra}
    cols = ",".join(fields)
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            f"INSERT INTO fno_positions ({cols}) VALUES ({','.join('?' * len(fields))})",
            tuple(fields.values()))
        await db.commit()
        return cur.lastrowid


async def _policy(db_path, today=TODAY, observed=NOON):
    return await shared_fno_entry_policy(db_path, source=SOURCE, pool_rs=POOL, today_ist=today,
                                         policy=POLICY, observed_at=observed)


def _ist(day, hh, mm=0, ss=0):
    return datetime(day.year, day.month, day.day, hh, mm, ss,
                    tzinfo=timezone(timedelta(hours=5, minutes=30)))


# ---- cash types ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_partial_cash_is_counted_once_in_equity_and_the_daily_brake(db_path):
    await _ready(db_path)
    await _cash(db_path, _ist(TODAY, 10), -3_100.0, event_type="TRADE_PARTIAL")
    decision = await _policy(db_path)
    assert not decision.allowed and decision.reason.startswith("daily_loss_halt")
    assert decision.day_pnl_rs == -3_100.0
    assert decision.view.realised_pnl_rs == -3_100.0 and decision.view.equity_rs == 46_900.0


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type,pnl,reason", [
    ("FUNDING", 1_000.0, "unclassified_cash_event"),
    ("TRADE_OPENED", -5.0, "unclassified_cash_event"),
    ("INITIAL", 50_000.0, "unclassified_cash_event"),
])
async def test_unknown_or_nonzero_opening_cash_fails_closed(db_path, event_type, pnl, reason):
    await _ready(db_path)
    await _cash(db_path, _ist(TODAY, 10), pnl, event_type=event_type)
    view = await shared_fno_risk_view(db_path, SOURCE, POOL, observed_at=NOON)
    assert not view.available and view.reason == reason


@pytest.mark.asyncio
async def test_zero_opening_events_are_ignored(db_path):
    await _ready(db_path)
    await _cash(db_path, _ist(TODAY, 10), 0.0, event_type="TRADE_OPENED")
    assert (await _policy(db_path)).allowed


@pytest.mark.asyncio
async def test_positive_manual_cash_is_not_capacity_but_withdrawals_reduce_equity(db_path):
    await _ready(db_path)
    await _cash(db_path, _ist(TODAY, 9), 5_000.0, event_type="MANUAL_DEPOSIT")
    await _cash(db_path, _ist(TODAY, 9, 5), -2_000.0, event_type="MANUAL_WITHDRAWAL")
    view = await shared_fno_risk_view(db_path, SOURCE, POOL, observed_at=NOON)
    assert view.available
    assert view.equity_rs == 48_000.0 and view.available_worst_case_cash_rs == 48_000.0
    assert view.excluded_positive_manual_cash_rs == 5_000.0
    decision = await _policy(db_path)
    assert decision.allowed and decision.day_pnl_rs == 0.0      # not trading P&L


# ---- clock ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_future_positive_cash_cannot_mask_todays_loss(db_path):
    await _ready(db_path)
    await _cash(db_path, _ist(TODAY, 10), -3_100.0)
    await _cash(db_path, _ist(TODAY + timedelta(days=1), 10), 10_000.0)
    masked = await _policy(db_path)
    assert not masked.allowed and masked.reason == "future_cash_event"
    # Observed after both events but evaluated for TODAY: tomorrow's credit is outside the day.
    later = await _policy(db_path, observed=NOON + timedelta(days=2))
    assert not later.allowed and later.reason.startswith("daily_loss_halt")
    assert later.day_pnl_rs == -3_100.0


@pytest.mark.asyncio
async def test_naive_or_unparseable_cash_and_naive_observation_fail_closed(db_path):
    await _ready(db_path)
    await _cash(db_path, "2026-10-05T10:00:00", -1.0)
    assert (await _policy(db_path)).reason == "invalid_cash_event"
    view = await shared_fno_risk_view(db_path, SOURCE, POOL, observed_at=datetime(2026, 10, 5, 12))
    assert not view.available and view.reason == "invalid_observation_clock"


@pytest.mark.asyncio
@pytest.mark.parametrize("stamp,counted", [
    (datetime(2026, 10, 4, 18, 29, 59, tzinfo=timezone.utc), False),   # 23:59:59 IST Sunday
    (datetime(2026, 10, 4, 18, 30, 0, tzinfo=timezone.utc), True),     # 00:00:00 IST Monday
])
async def test_ist_midnight_boundary(db_path, stamp, counted):
    await _ready(db_path)
    await _cash(db_path, stamp, -3_100.0)
    decision = await _policy(db_path)
    assert decision.day_pnl_rs == (-3_100.0 if counted else 0.0)
    assert decision.allowed is (not counted)


@pytest.mark.asyncio
async def test_week_and_month_buckets_are_bounded(db_path):
    await _ready(db_path)
    await _cash(db_path, _ist(date(2026, 10, 4), 11), -6_500.0)    # Sunday: last ISO week
    await _cash(db_path, _ist(date(2026, 9, 30), 11), -4_000.0)    # last month
    decision = await _policy(db_path)
    assert decision.week_pnl_rs == 0.0          # Sunday belongs to the previous ISO week
    assert decision.month_pnl_rs == -6_500.0    # Sep 30 belongs to the previous month
    tuesday = await _policy(db_path, today=date(2026, 10, 6), observed=NOON + timedelta(days=1))
    assert tuesday.week_pnl_rs == 0.0
    sunday = await _policy(db_path, today=date(2026, 10, 4), observed=NOON)
    assert sunday.week_pnl_rs == -6_500.0 - 4_000.0                # Sep 28 - Oct 4 week
    assert sunday.month_pnl_rs == -6_500.0


# ---- lineage --------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_exact_cash_fails_closed_but_legacy_generation_zero_is_reported(db_path):
    await _ready(db_path)
    position = await _position(db_path, generation=1)
    await _cash(db_path, _ist(TODAY, 10), -100.0, origin=f"fno_position:{position}", generation=1)
    await _cash(db_path, _ist(TODAY, 10, 1), -100.0, origin="fno_position:999", generation=0)
    await _cash(db_path, _ist(TODAY, 10, 2), -100.0, origin="fno_position:999", generation=0)
    ok = await _policy(db_path)
    assert ok.allowed and ok.legacy_unlinked_cash_events == 2
    async with aiosqlite.connect(db_path) as db:
        # The ledger unique index already refuses this write; the reader must
        # also refuse it on a database that predates (or lost) that index.
        indexes = [row[0] for row in await (await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='bankroll_ledger' "
            "AND sql LIKE '%UNIQUE%'")).fetchall()]
        for name in indexes:
            await db.execute(f"DROP INDEX {name}")
        await db.commit()
    await _cash(db_path, _ist(TODAY, 10, 3), -100.0, origin=f"fno_position:{position}", generation=1)
    dup = await shared_fno_risk_view(db_path, SOURCE, POOL, observed_at=NOON)
    assert not dup.available and dup.reason == "duplicate_cash_event"


@pytest.mark.asyncio
async def test_settled_positions_must_carry_their_exact_cash(db_path):
    await _ready(db_path)
    position = await _position(db_path, generation=2)
    await _cash(db_path, _ist(TODAY, 10), -50.0, origin=f"fno_position:{position}", generation=1)
    missing = await shared_fno_risk_view(db_path, SOURCE, POOL, observed_at=NOON)
    assert not missing.available and missing.reason == "missing_settlement_cash"
    await _cash(db_path, _ist(TODAY, 11), -50.0, origin=f"fno_position:{position}", generation=2)
    assert (await shared_fno_risk_view(db_path, SOURCE, POOL, observed_at=NOON)).available


@pytest.mark.asyncio
async def test_settled_dr_structure_requires_its_cash_and_legacy_rows_do_not_block(db_path):
    await _ready(db_path)
    await _position(db_path, generation=0)                         # legacy single-leg close
    async with aiosqlite.connect(db_path) as db:
        legacy = await db.execute(
            "INSERT INTO fno_dr_positions (source,kind,legs_json,lot_size,lots,max_loss_rs,"
            "entry_cost_rs,status) VALUES (?,?,?,?,?,?,?,?)",
            (SOURCE, "DEBIT_SPREAD", "[]", 75, 1, 4000.0, 90.0, "CLOSED"))
        settled = await db.execute(
            "INSERT INTO fno_dr_positions (source,kind,legs_json,lot_size,lots,max_loss_rs,"
            "entry_cost_rs,status,settlement_state) VALUES (?,?,?,?,?,?,?,?,?)",
            (SOURCE, "DEBIT_SPREAD", "[]", 75, 1, 4000.0, 90.0, "CLOSED", "SETTLED"))
        await db.commit()
    missing = await shared_fno_risk_view(db_path, SOURCE, POOL, observed_at=NOON)
    assert not missing.available and missing.reason == "missing_settlement_cash"
    await _cash(db_path, _ist(TODAY, 10), 120.0, origin=f"fno_dr_structure:{settled.lastrowid}",
                generation=1)
    view = await shared_fno_risk_view(db_path, SOURCE, POOL, observed_at=NOON)
    assert view.available and view.legacy_unlinked_closed_positions == 2   # legacy single + legacy DR
    assert legacy.lastrowid != settled.lastrowid


# ---- completed-trade streak ---------------------------------------------------------

@pytest.mark.asyncio
async def test_six_partial_losses_of_one_trade_are_one_completed_loss(db_path):
    await _ready(db_path)
    position = await _position(db_path, generation=6)
    for generation in range(1, 7):
        await _cash(db_path, _ist(TODAY, 10, generation), -100.0,
                    origin=f"fno_position:{position}", generation=generation)
    decision = await _policy(db_path)
    assert decision.allowed and decision.completed_loss_streak == 1
    assert decision.day_pnl_rs == -600.0


@pytest.mark.asyncio
async def test_six_completed_losses_pause_entry(db_path):
    await _ready(db_path)
    for minute in range(6):
        position = await _position(db_path, generation=1)
        await _cash(db_path, _ist(TODAY, 10, minute), -100.0,
                    origin=f"fno_position:{position}", generation=1)
    decision = await _policy(db_path)
    assert not decision.allowed and decision.reason.startswith("consecutive_loss_pause streak=6")


@pytest.mark.asyncio
async def test_open_trade_partials_count_in_day_pnl_but_not_the_streak(db_path):
    await _ready(db_path)
    position = await _position(db_path, status="OPEN", generation=0, qty=75, initial_qty=75,
                               entry_premium=100.0, max_loss_rupees=7_500.0,
                               initial_max_loss_rupees=7_500.0, risk_fee_reserve_rupees=50.0)
    for minute in range(6):
        await _cash(db_path, _ist(TODAY, 10, minute), -100.0, event_type="TRADE_PARTIAL",
                    origin=f"fno_position:{position}")
    decision = await _policy(db_path)
    assert decision.allowed and decision.completed_loss_streak == 0
    assert decision.day_pnl_rs == -600.0


@pytest.mark.asyncio
async def test_streak_follows_the_cash_clock_not_row_ids(db_path):
    await _ready(db_path)
    win = await _position(db_path)
    loss = await _position(db_path)
    # The win is written first (lower id) but completes later; the loss is older.
    await _cash(db_path, _ist(TODAY, 11), 300.0, origin=f"fno_position:{win}", generation=1)
    await _cash(db_path, _ist(TODAY, 10), -100.0, origin=f"fno_position:{loss}", generation=1)
    assert (await _policy(db_path)).completed_loss_streak == 0


@pytest.mark.asyncio
async def test_equal_completion_clocks_are_ordered_by_id(db_path):
    await _ready(db_path)
    first, second = await _position(db_path), await _position(db_path)
    await _cash(db_path, _ist(TODAY, 10), 300.0, origin=f"fno_position:{first}", generation=1)
    await _cash(db_path, _ist(TODAY, 10), -100.0, origin=f"fno_position:{second}", generation=1)
    assert (await _policy(db_path)).completed_loss_streak == 1      # the later id is newest


@pytest.mark.asyncio
async def test_completed_trades_after_the_policy_day_are_ignored(db_path):
    await _ready(db_path)
    for minute in range(6):
        position = await _position(db_path)
        await _cash(db_path, _ist(TODAY, 10, minute), -100.0,
                    origin=f"fno_position:{position}", generation=1)
    yesterday = await _policy(db_path, today=TODAY - timedelta(days=1))
    assert yesterday.completed_loss_streak == 0 and yesterday.allowed
