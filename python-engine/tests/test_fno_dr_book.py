"""
[FNO-DR-BOOK 2026-07-20] Tests for the defined-risk paper book lifecycle:
the snapshot adapter, planning (debit spread on a signal, condor on a rich-IV
range day, stand-aside otherwise), mark-to-market, exit logic, and the
open/close storage round-trip.
"""
import asyncio
from datetime import date, datetime

import pytest

import fno_dr_book as book
from fno_dr_book import (
    evaluate_dr_exit, expected_move_pct_from_snapshot, iv_rank_proxy,
    plan_structure, premium_lookup_from_snapshot, structure_mtm_rs,
    insert_structure, open_structures, init_dr_db, PlannedStructure,
)
from fno_defined_risk import build_debit_spread, StructureKind
from fno_models import Contract, ContractQuote, FnoDirection, OptionType

STEP = 50.0
LOT = 75
NOW = datetime(2026, 7, 20, 11, 0)     # inside the entry window
SQUAREOFF = datetime(2026, 7, 20, 15, 15)


class FakeSnap:
    """Duck-types the bits of ChainSnapshot that fno_dr_book touches.

    NOTE: ChainSnapshot exposes the synthetic ``forward`` (futures LTP) as its
    pricing basis -- there is no ``spot`` attribute. This fake must mirror that
    exact name, otherwise the adapter can regress against a field the live
    snapshot never had (which is precisely what slipped past before)."""
    def __init__(self, forward, table, *, lot_size=LOT, include_contract=True):
        self.forward = forward
        self._t = {(float(k[0]), k[1].value): v for k, v in table.items()}
        self.expiry = date(2026, 7, 30)
        self._lot_size = lot_size
        self._include_contract = include_contract
    def quote(self, strike, opt):
        m = self._t.get((float(strike), opt.value))
        if m is None:
            return None
        contract = Contract(
            token=int(strike * 10) + (1 if opt == OptionType.CE else 2),
            tradingsymbol=f"NIFTY26JUL{int(strike)}{opt.value}", name="NIFTY",
            expiry=self.expiry, strike=float(strike), instrument_type=opt.value, lot_size=self._lot_size,
        )
        # A two-sided fake preserves the executable exit path while keeping
        # the original ``mid`` test values exact.
        quote = ContractQuote(contract=contract, bid=float(m) - 0.5, ask=float(m) + 0.5, ltp=float(m))
        if not self._include_contract:
            quote.contract = None
        return quote


# --------------------------------------------------------------------------
# adapters / helpers
# --------------------------------------------------------------------------

def test_premium_lookup_returns_none_for_missing_or_zero():
    snap = FakeSnap(25000, {(25000, OptionType.CE): 120.0, (25100, OptionType.CE): 0.0})
    prem = premium_lookup_from_snapshot(snap)
    assert prem(OptionType.CE, 25000) == 120.0
    assert prem(OptionType.CE, 25100) is None   # zero mid -> untradeable
    assert prem(OptionType.PE, 25000) is None   # missing


def test_expected_move_is_atm_straddle_over_spot():
    snap = FakeSnap(25000, {(25000, OptionType.CE): 120.0, (25000, OptionType.PE): 110.0})
    em = expected_move_pct_from_snapshot(snap, STEP)
    assert em == pytest.approx((120.0 + 110.0) / 25000)


def test_iv_rank_proxy_maps_iv_between_bands():
    assert iv_rank_proxy(None) is None
    assert iv_rank_proxy(0.10) == pytest.approx(0.0)
    assert iv_rank_proxy(0.20) == pytest.approx(1.0)
    assert iv_rank_proxy(0.15) == pytest.approx(0.5)


# --------------------------------------------------------------------------
# planning
# --------------------------------------------------------------------------

def test_plan_directional_signal_builds_debit_spread(monkeypatch):
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.15)
    snap = FakeSnap(25000, {
        (25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
        (25000, OptionType.PE): 110.0,   # for expected-move
    })
    planned = plan_structure(snap, True, FnoDirection.LONG, NOW)
    assert planned is not None
    assert planned.structure.kind == StructureKind.DEBIT_SPREAD
    assert planned.entry_underlying == 25000
    assert planned.structure.is_defined_risk


def test_plan_range_day_rich_iv_builds_condor(monkeypatch):
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.19)   # rich -> rank 0.9
    snap = FakeSnap(25000, {
        (25000, OptionType.CE): 60.0, (25000, OptionType.PE): 60.0,   # em = 0.0048 <= 1%
        (25200, OptionType.CE): 40.0, (25300, OptionType.CE): 20.0,
        (24800, OptionType.PE): 42.0, (24700, OptionType.PE): 22.0,
    })
    planned = plan_structure(snap, False, None, NOW)
    assert planned is not None
    assert planned.structure.kind == StructureKind.IRON_CONDOR


def test_plan_stands_aside_when_no_signal_and_cheap_iv(monkeypatch):
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.10)   # rank 0 -> no condor
    snap = FakeSnap(25000, {(25000, OptionType.CE): 60.0, (25000, OptionType.PE): 60.0})
    assert plan_structure(snap, False, None, NOW) is None


def test_plan_skips_structure_over_max_loss_ceiling(monkeypatch):
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.15)
    monkeypatch.setattr(book, "_max_loss_ceiling", lambda: 100.0)   # tiny ceiling
    snap = FakeSnap(25000, {
        (25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
        (25000, OptionType.PE): 110.0,
    })
    assert plan_structure(snap, True, FnoDirection.LONG, NOW) is None


def test_plan_uses_the_selected_contract_lot_and_retains_identity(monkeypatch):
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.15)
    snap = FakeSnap(25000, {
        (25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
        (25000, OptionType.PE): 110.0,
    }, lot_size=65)
    planned = plan_structure(snap, True, FnoDirection.LONG, NOW)
    assert planned is not None
    assert planned.structure.lot_size == 65
    assert {item["contract"]["lot_size"] for item in planned.contract_legs} == {65}
    assert {item["contract"]["expiry"] for item in planned.contract_legs} == {"2026-07-30"}


def test_plan_rejects_missing_contract_identity(monkeypatch):
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.15)
    snap = FakeSnap(25000, {
        (25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
        (25000, OptionType.PE): 110.0,
    }, include_contract=False)
    assert plan_structure(snap, True, FnoDirection.LONG, NOW) is None


def test_exact_leg_snapshot_uses_retained_tokens_after_rollover_and_large_move(monkeypatch):
    """Management must value the opened contracts, never a rebuilt ladder."""
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.15)
    entry = FakeSnap(25000, {
        (25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
        (25000, OptionType.PE): 110.0,
    })
    planned = plan_structure(entry, True, FnoDirection.LONG, NOW)
    assert planned is not None
    row = {"legs_json": book._bound_legs_to_json(planned.contract_legs)}
    tokens = book.exact_open_leg_tokens([row])
    assert tokens == sorted(item["contract"]["token"] for item in planned.contract_legs)

    # Simulate a later weekly expiry being nearest and a forward far outside
    # the retained entry window.  Neither can change the requested identities.
    quotes = {
        token: {"last_price": 99.0, "depth": {"buy": [{"price": 98.5}], "sell": [{"price": 99.5}]}}
        for token in tokens
    }
    snapshot = book.exact_leg_snapshot_from_quotes(
        [row], quotes, NOW, forward=28000.0,
    )
    assert snapshot is not None
    assert snapshot.expiry == date(2026, 7, 30)
    assert snapshot.forward == 28000.0
    assert snapshot.requested_tokens == tuple(tokens)
    assert {quote.contract.token for quote in snapshot.quotes.values()} == set(tokens)


def test_exact_leg_snapshot_refuses_missing_or_inconsistent_retained_identity(monkeypatch):
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.15)
    entry = FakeSnap(25000, {
        (25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
        (25000, OptionType.PE): 110.0,
    })
    planned = plan_structure(entry, True, FnoDirection.LONG, NOW)
    assert planned is not None
    row = {"legs_json": book._bound_legs_to_json(planned.contract_legs)}
    tokens = book.exact_open_leg_tokens([row])
    incomplete = {tokens[0]: {"last_price": 100.0, "depth": {}}}
    assert book.exact_leg_snapshot_from_quotes([row], incomplete, NOW, 25000.0) is None

    inconsistent = list(planned.contract_legs)
    inconsistent[1] = {
        **inconsistent[1],
        "contract": {**inconsistent[1]["contract"], "expiry": "2026-08-06"},
    }
    bad_row = {"legs_json": book._bound_legs_to_json(tuple(inconsistent))}
    full = {
        token: {"last_price": 100.0, "depth": {"buy": [{"price": 99.0}], "sell": [{"price": 101.0}]}}
        for token in book.exact_open_leg_tokens([bad_row])
    }
    assert book.exact_leg_snapshot_from_quotes([bad_row], full, NOW, 25000.0) is None


# --------------------------------------------------------------------------
# mark-to-market + exit
# --------------------------------------------------------------------------

def test_structure_mtm_marks_each_leg_to_current_mid():
    s = build_debit_spread(
        FnoDirection.LONG, 25000, STEP, 2,
        lambda o, k: {(OptionType.CE, 25000.0): 120.0, (OptionType.CE, 25100.0): 50.0}.get((o, k)),
        LOT,
    )
    cur = FakeSnap(25120, {(25000, OptionType.CE): 140.0, (25100, OptionType.CE): 60.0})
    prem = premium_lookup_from_snapshot(cur)
    mtm = structure_mtm_rs(s.legs, LOT, prem)
    # long +20, short -10 -> net +10 pts * 75
    assert mtm == pytest.approx((20.0 - 10.0) * LOT)


def test_mtm_none_when_a_leg_cannot_be_priced():
    s = build_debit_spread(
        FnoDirection.LONG, 25000, STEP, 2,
        lambda o, k: {(OptionType.CE, 25000.0): 120.0, (OptionType.CE, 25100.0): 50.0}.get((o, k)),
        LOT,
    )
    cur = FakeSnap(25120, {(25000, OptionType.CE): 140.0})   # short leg missing
    assert structure_mtm_rs(s.legs, LOT, premium_lookup_from_snapshot(cur)) is None


def test_exit_target_stop_and_squareoff():
    row = {"max_profit_rs": 2250.0, "max_loss_rs": 5250.0}
    assert evaluate_dr_exit(row, 1200.0, NOW) == (True, "target")     # >= 0.5*2250
    assert evaluate_dr_exit(row, -3200.0, NOW) == (True, "stop")      # <= -0.6*5250
    assert evaluate_dr_exit(row, 100.0, NOW) == (False, "hold")
    assert evaluate_dr_exit(row, None, NOW) == (False, "unpriced")
    assert evaluate_dr_exit(row, 100.0, SQUAREOFF)[0] is True          # time beats all


# --------------------------------------------------------------------------
# storage round-trip
# --------------------------------------------------------------------------

def test_insert_storage_retains_contract_identity(tmp_path):
    db = str(tmp_path / "cache.db")
    s = build_debit_spread(
        FnoDirection.LONG, 25000, STEP, 2,
        lambda o, k: {(OptionType.CE, 25000.0): 120.0, (OptionType.CE, 25100.0): 50.0}.get((o, k)),
        LOT,
    )
    snap = FakeSnap(25000, {
        (25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
    })
    contract_legs = book._selected_contract_legs(snap, s.legs)
    assert contract_legs is not None
    planned = PlannedStructure(structure=s, entry_underlying=25000.0, contract_legs=contract_legs)

    async def go():
        await init_dr_db(db)
        rid = await insert_structure(db, book.SOURCE_PAPER, planned, NOW)
        rows = await open_structures(db, book.SOURCE_PAPER)
        assert len(rows) == 1 and rows[0]["kind"] == "DEBIT_SPREAD"
        assert rows[0]["max_loss_rs"] == pytest.approx(s.max_loss_rs)
        assert rows[0]["id"] == rid
        assert book._bound_legs_from_row(rows[0]) is not None

    asyncio.run(go())


def test_hard_flat_with_missing_exact_leg_stays_unresolved_and_writes_no_cash(tmp_path, monkeypatch):
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.15)
    db = str(tmp_path / "cache.db")
    entry = FakeSnap(25000, {
        (25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
        (25000, OptionType.PE): 110.0,
    })
    planned = plan_structure(entry, True, FnoDirection.LONG, NOW)
    assert planned is not None

    async def go():
        await init_dr_db(db)
        await insert_structure(db, book.SOURCE_PAPER, planned, NOW)
        # The short call is absent at the hard-flat deadline.  It must not be
        # turned into the old zero-cash close.
        incomplete = FakeSnap(25000, {(25000, OptionType.CE): 150.0})
        assert await book.manage_dr_structures(db, incomplete, SQUAREOFF) == 0
        rows = await open_structures(db)
        assert len(rows) == 1
        assert rows[0]["status"] == "UNRESOLVED"
        assert rows[0]["settlement_state"] == "UNRESOLVED"
        import aiosqlite
        async with aiosqlite.connect(db) as conn:
            exists = await (await conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='bankroll_ledger'"
            )).fetchone()
            assert exists[0] == 0
    asyncio.run(go())


def test_exact_priced_close_is_atomic_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.15)
    db = str(tmp_path / "cache.db")
    entry = FakeSnap(25000, {
        (25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
        (25000, OptionType.PE): 110.0,
    })
    planned = plan_structure(entry, True, FnoDirection.LONG, NOW)
    assert planned is not None

    async def go():
        await init_dr_db(db)
        row_id = await insert_structure(db, book.SOURCE_PAPER, planned, NOW)
        # The mid valuation crosses the target and every leg has an executable
        # bid/ask.  The ledger cash and terminal row commit together.
        exit_snap = FakeSnap(25000, {
            (25000, OptionType.CE): 210.0, (25100, OptionType.CE): 50.0,
        })
        assert await book.manage_dr_structures(db, exit_snap, NOW) == 1
        assert await book.manage_dr_structures(db, exit_snap, NOW) == 0
        import aiosqlite
        async with aiosqlite.connect(db) as conn:
            conn.row_factory = aiosqlite.Row
            position = await (await conn.execute(
                "SELECT status, settlement_state, model_gross_pnl, cash_gross_pnl, pnl, pricing_policy "
                "FROM fno_dr_positions WHERE id=?", (row_id,)
            )).fetchone()
            assert position["status"] == "CLOSED"
            assert position["settlement_state"] == "SETTLED"
            assert position["pricing_policy"] == "ENTRY_MID_EXIT_BID_ASK_V1"
            assert position["model_gross_pnl"] != position["cash_gross_pnl"]
            cash_rows = await (await conn.execute(
                "SELECT pnl, origin_ref, settlement_generation FROM bankroll_ledger "
                "WHERE origin_ref=?", (f"fno_dr_structure:{row_id}",)
            )).fetchall()
            assert len(cash_rows) == 1
            assert cash_rows[0]["pnl"] == position["pnl"]
            assert cash_rows[0]["settlement_generation"] == 1
    asyncio.run(go())


def test_concurrent_exact_close_writes_one_terminal_cash_event(tmp_path, monkeypatch):
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.15)
    db = str(tmp_path / "cache.db")
    entry = FakeSnap(25000, {
        (25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
        (25000, OptionType.PE): 110.0,
    })
    planned = plan_structure(entry, True, FnoDirection.LONG, NOW)
    assert planned is not None

    async def go():
        await init_dr_db(db)
        row_id = await insert_structure(db, book.SOURCE_PAPER, planned, NOW)
        exit_snap = FakeSnap(25000, {
            (25000, OptionType.CE): 210.0, (25100, OptionType.CE): 50.0,
        })
        results = await asyncio.gather(
            book.manage_dr_structures(db, exit_snap, NOW),
            book.manage_dr_structures(db, exit_snap, NOW),
        )
        assert sum(results) == 1
        import aiosqlite
        async with aiosqlite.connect(db) as conn:
            cash_count = await (await conn.execute(
                "SELECT COUNT(*) FROM bankroll_ledger WHERE origin_ref=?", (f"fno_dr_structure:{row_id}",)
            )).fetchone()
            assert cash_count[0] == 1
    asyncio.run(go())


def test_ledger_write_failure_rolls_back_terminal_position_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.15)
    db = str(tmp_path / "cache.db")
    entry = FakeSnap(25000, {
        (25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
        (25000, OptionType.PE): 110.0,
    })
    planned = plan_structure(entry, True, FnoDirection.LONG, NOW)
    assert planned is not None

    async def go():
        await init_dr_db(db)
        row_id = await insert_structure(db, book.SOURCE_PAPER, planned, NOW)
        from performance import init_ledger
        await init_ledger(db)
        import aiosqlite
        # A database-side failure is closer to the real failure mode than a
        # mocked helper: it exercises the transaction containing both writes.
        async with aiosqlite.connect(db) as conn:
            await conn.execute(
                "CREATE TRIGGER fail_dr_cash BEFORE INSERT ON bankroll_ledger "
                f"WHEN NEW.origin_ref = 'fno_dr_structure:{row_id}' "
                "BEGIN SELECT RAISE(ABORT, 'injected terminal ledger failure'); END"
            )
            await conn.commit()
        exit_snap = FakeSnap(25000, {
            (25000, OptionType.CE): 210.0, (25100, OptionType.CE): 50.0,
        })
        assert await book.manage_dr_structures(db, exit_snap, NOW) == 0
        async with aiosqlite.connect(db) as conn:
            position = await (await conn.execute(
                "SELECT status FROM fno_dr_positions WHERE id=?", (row_id,)
            )).fetchone()
            assert position[0] == "OPEN"
            cash_count = await (await conn.execute(
                "SELECT COUNT(*) FROM bankroll_ledger WHERE origin_ref=?", (f"fno_dr_structure:{row_id}",)
            )).fetchone()
            assert cash_count[0] == 0
    asyncio.run(go())


@pytest.mark.parametrize("case", ["entry_window", "chain_age", "quote_age", "valid"])
def test_live_dr_admission_rechecks_after_database_reads(tmp_path, monkeypatch, case):
    monkeypatch.setattr(book, "atm_iv", lambda snap, now: 0.15)
    monkeypatch.setattr(book.settings, "FNO_DR_DISABLE_PAPER", False)
    from datetime import timedelta
    final_time = NOW.replace(hour=14, minute=46) if case == "entry_window" else NOW

    class TimedSnap(FakeSnap):
        def age_sec(self, now):
            return 121 if case == "chain_age" else 0

        def quote(self, strike, opt):
            quote = super().quote(strike, opt)
            if quote is not None:
                quote.last_trade_time = NOW - timedelta(seconds=121 if case == "quote_age" else 0)
            return quote

    snap = TimedSnap(25000, {
        (25000, OptionType.CE): 120.0, (25100, OptionType.CE): 50.0,
        (25000, OptionType.PE): 110.0,
    })

    async def go():
        await book.init_dr_db(str(tmp_path / "db.sqlite"))
        row_id = await book.maybe_open_dr_structure(
            str(tmp_path / "db.sqlite"), snap, True, FnoDirection.LONG, NOW,
            action_clock=lambda: final_time,
        )
        assert (row_id is not None) == (case == "valid")

    asyncio.run(go())
