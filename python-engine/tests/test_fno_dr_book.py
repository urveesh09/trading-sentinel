"""
[FNO-DR-BOOK 2026-07-20] Tests for the defined-risk paper book lifecycle:
the snapshot adapter, planning (debit spread on a signal, condor on a rich-IV
range day, stand-aside otherwise), mark-to-market, exit logic, and the
open/close storage round-trip.
"""
import asyncio
from datetime import datetime

import pytest

import fno_dr_book as book
from fno_dr_book import (
    evaluate_dr_exit, expected_move_pct_from_snapshot, iv_rank_proxy,
    plan_structure, premium_lookup_from_snapshot, structure_mtm_rs,
    insert_structure, open_structures, close_structure, init_dr_db, PlannedStructure,
)
from fno_defined_risk import build_debit_spread, StructureKind
from fno_models import FnoDirection, OptionType

STEP = 50.0
LOT = 75
NOW = datetime(2026, 7, 20, 11, 0)     # inside the entry window
SQUAREOFF = datetime(2026, 7, 20, 15, 15)


class _Q:
    def __init__(self, mid):
        self._m = mid
    @property
    def mid(self):
        return self._m


class FakeSnap:
    """Duck-types the bits of ChainSnapshot that fno_dr_book touches."""
    def __init__(self, spot, table):
        self.spot = spot
        self._t = {(float(k[0]), k[1].value): v for k, v in table.items()}
    def quote(self, strike, opt):
        m = self._t.get((float(strike), opt.value))
        return _Q(m) if m is not None else None


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

def test_open_close_storage_roundtrip(tmp_path):
    db = str(tmp_path / "cache.db")
    s = build_debit_spread(
        FnoDirection.LONG, 25000, STEP, 2,
        lambda o, k: {(OptionType.CE, 25000.0): 120.0, (OptionType.CE, 25100.0): 50.0}.get((o, k)),
        LOT,
    )
    planned = PlannedStructure(structure=s, entry_underlying=25000.0)

    async def go():
        await init_dr_db(db)
        rid = await insert_structure(db, book.SOURCE_PAPER, planned, NOW)
        rows = await open_structures(db, book.SOURCE_PAPER)
        assert len(rows) == 1 and rows[0]["kind"] == "DEBIT_SPREAD"
        assert rows[0]["max_loss_rs"] == pytest.approx(s.max_loss_rs)
        await close_structure(db, rid, gross_pnl=750.0, costs=50.0,
                              exit_underlying=25120.0, reason="target", now_ist=SQUAREOFF)
        assert await open_structures(db, book.SOURCE_PAPER) == []

    asyncio.run(go())
