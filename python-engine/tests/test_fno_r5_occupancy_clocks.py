"""F0-R5: existing occupancy limits enforced in the claim; post-admission clocks."""
import asyncio
from datetime import date, datetime, timedelta, timezone

import aiosqlite
import pytest

import fno_dr_book as book
import fno_shared_risk
from fno_dr_book import dr_post_admission_reject, init_dr_db, plan_structure
from fno_models import FnoDirection, OptionType
from fno_orchestrator import post_admission_entry_reject
from fno_positions import init_fno_positions_db
from fno_shared_risk import (
    EntryOccupancy, claim_shared_fno_entry_dispatch, init_shared_fno_risk_db,
    reserve_shared_fno_risk, resolve_shared_fno_entry_dispatch,
)
from performance import init_ledger
from tests.test_fno_dr_book import NOW as DR_NOW, FakeSnap

SOURCE = "FNO_PAPER"
POOL = 250_000.0
DAY = date(2026, 10, 5)


async def _ready(db_path):
    await init_ledger(db_path)
    await init_fno_positions_db(db_path)
    await init_dr_db(db_path)
    await init_shared_fno_risk_db(db_path)


async def _open_position(db_path, symbol="NIFTYA", *, status="OPEN", premium=100.0, qty=75,
                         entry_date=DAY.isoformat()):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO fno_positions (source,tradingsymbol,status,qty,entry_premium,max_loss_rupees,"
            "risk_fee_reserve_rupees,entry_date) VALUES (?,?,?,?,?,?,?,?)",
            (SOURCE, symbol, status, qty, premium, premium * qty, 50.0, entry_date))
        await db.commit()


def _occ(symbol="NIFTYX", premium=1_000.0, **limits):
    base = dict(entry_day=DAY, max_open=2, tradingsymbol=symbol, planned_premium_rs=premium,
                max_trades_per_day=3, max_open_premium_rs=37_500.0, no_pyramid=True)
    base.update(limits)
    return EntryOccupancy(**base)


async def _claim(db_path, key, occupancy, book_name="SINGLE_LEG"):
    admission = await reserve_shared_fno_risk(
        db_path, source=SOURCE, pool_rs=POOL, reservation_key=key, book=book_name,
        worst_case_cash_rs=1_000.0)
    assert admission.allowed, admission.reason
    return await claim_shared_fno_entry_dispatch(
        db_path, reservation_key=key, source=SOURCE, book=book_name, pool_rs=POOL,
        entry_day_ist=None, occupancy=occupancy)


async def _reservation(db_path, key):
    async with aiosqlite.connect(db_path) as db:
        return await (await db.execute(
            "SELECT state,resolution_reason FROM fno_risk_reservations WHERE reservation_key=?",
            (key,))).fetchone()


# ---- single-leg limits count in-flight claims --------------------------------------

@pytest.mark.asyncio
async def test_concurrency_counts_positions_and_in_flight_claims(db_path):
    await _ready(db_path)
    await _open_position(db_path)
    assert (await _claim(db_path, "a", _occ("NIFTYB"))).granted          # 1 open + this = 2
    denied = await _claim(db_path, "b", _occ("NIFTYC"))
    assert not denied.granted and denied.reason == "concurrency"
    assert await _reservation(db_path, "b") == ("RELEASED",
                                                 "occupancy_denied_before_dispatch:concurrency")
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute("SELECT reservation_key FROM fno_entry_dispatches")).fetchall()
    assert rows == [("a",)]


@pytest.mark.asyncio
async def test_no_pyramid_blocks_an_in_flight_claim_on_the_same_contract(db_path):
    await _ready(db_path)
    assert (await _claim(db_path, "a", _occ("NIFTYX", max_open=5))).granted
    denied = await _claim(db_path, "b", _occ("NIFTYX", max_open=5))
    assert not denied.granted and denied.reason == "already_holding_this_contract"
    assert (await _claim(db_path, "c", _occ("NIFTYY", max_open=5))).granted   # different strike


@pytest.mark.asyncio
async def test_trades_per_day_counts_todays_entries_and_in_flight_claims(db_path):
    await _ready(db_path)
    await _open_position(db_path, "NIFTYA", status="CLOSED")
    await _open_position(db_path, "NIFTYB", status="CLOSED")
    await _open_position(db_path, "NIFTYC", status="CLOSED", entry_date="2026-10-02")  # not today
    assert (await _claim(db_path, "a", _occ("NIFTYD", max_open=5))).granted       # 2 + this = 3
    denied = await _claim(db_path, "b", _occ("NIFTYE", max_open=5))
    assert not denied.granted and denied.reason == "trades_per_day"


@pytest.mark.asyncio
async def test_open_premium_cap_includes_in_flight_planned_premium(db_path):
    await _ready(db_path)
    await _open_position(db_path, premium=100.0, qty=150)                     # 15,000 committed
    assert (await _claim(db_path, "a", _occ("NIFTYB", premium=20_000.0, max_open=5))).granted
    denied = await _claim(db_path, "b", _occ("NIFTYC", premium=2_501.0, max_open=5))
    assert not denied.granted and denied.reason == "open_premium_cap"
    assert (await _claim(db_path, "c", _occ("NIFTYD", premium=2_500.0, max_open=5))).granted


@pytest.mark.asyncio
async def test_orphaned_or_unresolved_claims_keep_occupying_after_restart(db_path):
    await _ready(db_path)
    first = await _claim(db_path, "a", _occ("NIFTYA", max_open=1))
    await resolve_shared_fno_entry_dispatch(
        db_path, reservation_key="a", owner=first.owner, outcome="unknown", evidence={"order_id": "O"})
    denied = await _claim(db_path, "b", _occ("NIFTYB", max_open=1))
    assert not denied.granted and denied.reason == "concurrency"


@pytest.mark.asyncio
async def test_in_flight_claim_without_premium_evidence_fails_the_premium_check_closed(db_path):
    await _ready(db_path)
    await reserve_shared_fno_risk(db_path, source=SOURCE, pool_rs=POOL, reservation_key="legacy",
                                  book="SINGLE_LEG", worst_case_cash_rs=1_000.0)
    assert (await claim_shared_fno_entry_dispatch(
        db_path, reservation_key="legacy", source=SOURCE, book="SINGLE_LEG", pool_rs=POOL,
        entry_day_ist=None)).granted                                           # pre-R5 style claim
    denied = await _claim(db_path, "b", _occ("NIFTYB", max_open=5))
    assert not denied.granted and denied.reason == "inflight_premium_unknown"


@pytest.mark.asyncio
async def test_occupancy_facts_on_a_claim_are_immutable(db_path):
    await _ready(db_path)
    await _claim(db_path, "a", _occ())
    async with aiosqlite.connect(db_path) as db:
        with pytest.raises(aiosqlite.IntegrityError, match="dispatch evidence is immutable"):
            await db.execute("UPDATE fno_entry_dispatches SET planned_premium_rs=0")


# ---- defined-risk: one structure at a time under concurrency ----------------------

@pytest.mark.asyncio
async def test_concurrent_dr_openings_that_both_read_a_flat_book_open_exactly_one(db_path, monkeypatch):
    await _ready(db_path)
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.15)

    async def flat(*args, **kwargs):          # both callers pass the early filter
        return []

    monkeypatch.setattr(book, "open_structures", flat)
    snap = FakeSnap(25000, {(25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
                            (25000, OptionType.PE): 110.0})
    results = await asyncio.gather(
        book.maybe_open_dr_structure(db_path, snap, True, FnoDirection.LONG, DR_NOW),
        book.maybe_open_dr_structure(db_path, snap, True, FnoDirection.LONG,
                                     DR_NOW + timedelta(seconds=1)),
    )
    assert sorted(r is None for r in results) == [False, True]
    async with aiosqlite.connect(db_path) as db:
        structures = await (await db.execute(
            "SELECT COUNT(*) FROM fno_dr_positions WHERE status='OPEN'")).fetchone()
        reasons = [r[0] for r in await (await db.execute(
            "SELECT resolution_reason FROM fno_risk_reservations WHERE state='RELEASED'")).fetchall()]
    assert structures == (1,)
    assert reasons == ["occupancy_denied_before_dispatch:dr_structure_occupied"]


# ---- post-admission clocks --------------------------------------------------------

class _TimedSnap(FakeSnap):
    def __init__(self, *args, stamp, **kwargs):
        super().__init__(*args, **kwargs)
        self.stamp = stamp

    def age_sec(self, now):
        return (now - self.stamp).total_seconds()

    def quote(self, strike, opt):
        q = super().quote(strike, opt)
        if q is not None:
            q.last_trade_time = self.stamp
        return q


@pytest.mark.asyncio
@pytest.mark.parametrize("late_by,reason", [
    (timedelta(minutes=5), "post_admission_chain_freshness"),
    (timedelta(hours=4), "post_admission_entry_window"),
])
async def test_dr_delay_across_freshness_or_cutoff_after_claim_never_opens(
        db_path, monkeypatch, late_by, reason):
    await _ready(db_path)
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.15)
    snap = _TimedSnap(25000, {(25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
                              (25000, OptionType.PE): 110.0}, stamp=DR_NOW)
    state = {"late": False}
    real_claim = fno_shared_risk.claim_shared_fno_entry_dispatch

    async def slow_claim(*args, **kwargs):
        result = await real_claim(*args, **kwargs)
        state["late"] = True                   # the DB waits took this long
        return result

    monkeypatch.setattr(fno_shared_risk, "claim_shared_fno_entry_dispatch", slow_claim)
    clock = lambda: DR_NOW + late_by if state["late"] else DR_NOW  # noqa: E731
    opened = await book.maybe_open_dr_structure(
        db_path, snap, True, FnoDirection.LONG, DR_NOW, action_clock=clock)
    assert opened is None
    async with aiosqlite.connect(db_path) as db:
        assert (await (await db.execute("SELECT COUNT(*) FROM fno_dr_positions")).fetchone()) == (0,)
        claim = await (await db.execute(
            "SELECT state,outcome,evidence_json FROM fno_entry_dispatches")).fetchone()
        reservation = await (await db.execute("SELECT state FROM fno_risk_reservations")).fetchone()
    assert claim[0] == "RELEASED" and claim[1] == "no_dispatch" and reason in claim[2]
    assert reservation == ("RELEASED",)


@pytest.mark.asyncio
async def test_directional_delay_after_claim_releases_without_calling_the_executor(db_path, monkeypatch):
    import fno_instruments as fi
    import fno_orchestrator
    from tests.test_fno_orchestrator import (
        FakeKite, NOW, _breakout_bars, _build_book, _quote_table,
    )

    monkeypatch.setattr(book, "_enabled", lambda: False)            # isolate the directional book
    book_ = _build_book()
    monkeypatch.setattr(fi, "_instruments", book_)
    calls = []

    async def executor(self, tradingsymbol, qty, ask):
        calls.append(tradingsymbol)
        return {"status": "paper", "order_id": "P", "fill_price": ask}

    monkeypatch.setattr(fno_orchestrator.FnoExecutor, "execute_entry", executor)
    state = {"late": False}
    real_claim = fno_orchestrator.claim_shared_fno_entry_dispatch

    async def slow_claim(*args, **kwargs):
        result = await real_claim(*args, **kwargs)
        state["late"] = True
        return result

    monkeypatch.setattr(fno_orchestrator, "claim_shared_fno_entry_dispatch", slow_claim)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            moment = NOW + timedelta(minutes=10) if state["late"] else NOW
            return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)

    monkeypatch.setattr(fno_orchestrator, "datetime", Clock)
    kite = FakeKite(_breakout_bars(), _quote_table(book_, NOW))
    summary = await fno_orchestrator.run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL")
    assert calls == [] and summary["entries"] == []
    async with aiosqlite.connect(db_path) as db:
        claim = await (await db.execute(
            "SELECT state,outcome,evidence_json FROM fno_entry_dispatches WHERE book='SINGLE_LEG'"
        )).fetchone()
        positions = await (await db.execute("SELECT COUNT(*) FROM fno_positions")).fetchone()
    assert claim[0] == "RELEASED" and claim[1] == "no_dispatch"
    assert "post_admission_quote_freshness" in claim[2] or "post_admission_chain_freshness" in claim[2]
    assert positions == (0,)


def test_post_admission_helpers_use_the_existing_thresholds():
    stamp = datetime(2026, 7, 20, 11, 0)
    snap = _TimedSnap(25000, {(25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
                              (25000, OptionType.PE): 110.0}, stamp=stamp)
    quote = snap.quote(25000, OptionType.CE)
    assert post_admission_entry_reject(stamp + timedelta(seconds=30), quote, snap) is None
    assert post_admission_entry_reject(stamp + timedelta(seconds=90), quote, snap) == "chain_freshness"
    assert post_admission_entry_reject(stamp.replace(hour=15), quote, snap) == "entry_window"
    import fno_dr_book
    planned = None
    fno_dr_book_atm = fno_dr_book.atm_iv
    try:
        fno_dr_book.atm_iv = lambda s, n: 0.15
        planned = plan_structure(snap, True, FnoDirection.LONG, stamp)
    finally:
        fno_dr_book.atm_iv = fno_dr_book_atm
    assert planned is not None
    assert dr_post_admission_reject(stamp + timedelta(seconds=30), snap, planned) is None
    assert dr_post_admission_reject(stamp + timedelta(seconds=61), snap, planned) == "chain_freshness"
    assert dr_post_admission_reject(stamp.replace(hour=15), snap, planned) == "entry_window"
