"""[N11] The engine's N11 rules: pinned against the research's rule files where they exist, and wired against a real temporary database."""
from __future__ import annotations

import asyncio
import importlib.util
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import aiosqlite
import numpy as np
import pandas as pd
import pytest
import pytz

import fno_book
import fno_n11
import fno_positions as fpos
from config import settings
from fno_adaptive_risk import read_book_closes
from fno_costs import calc_fno_costs
from fno_engine_mom import MomSignal
from fno_entry_plan import EntryState
from fno_models import FnoDirection

IST = pytz.timezone("Asia/Kolkata")
ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "docs/research/simulation"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def at(day="2026-11-02", hhmm="11:00"):
    return IST.localize(datetime.fromisoformat(f"{day}T{hhmm}:00"))


@pytest.fixture
def n11_mode(monkeypatch):
    monkeypatch.setattr(settings, "FNO_BOOK", "N11")


# ---- the stand-aside and sizing ------------------------------------------------------------------------------------------

def test_stand_aside_needs_both_readings():
    bad, good = [-100.0] * 20, [100.0] * 20
    assert fno_n11.stand_aside(False, bad)
    assert not fno_n11.stand_aside(True, bad)
    assert not fno_n11.stand_aside(False, good)
    assert not fno_n11.stand_aside(False, [-100.0] * 19), "too little history: nothing waits"
    assert fno_n11.stand_aside(False, [100.0, -100.0] * 10), "a flat record isn't a good one"


def test_stand_aside_matches_the_research_rule():
    rules = _load("n11_rules_research", RESEARCH / "2026-11-02-fno-n11/n11_rules.py")
    rng = random.Random(3)
    for _ in range(500):
        nets = [rng.uniform(-3000, 3000) for _ in range(rng.randint(0, 40))]
        up = rng.random() < 0.5
        assert fno_n11.stand_aside(up, nets) == rules.stand_aside(up, nets)


def test_lot_ceiling():
    assert fno_n11.lot_ceiling("N11_TPB", 700, True, 0.0) == 2
    assert fno_n11.lot_ceiling("N11_TPB", 700, False, 0.0) == 1, "below usual volatility: one lot"
    assert fno_n11.lot_ceiling("N11_TPB", 700, True, -1.0) == 1, "after a realised loss today: one lot"
    assert fno_n11.lot_ceiling("N11_TPB", 700, True, 500.0) == 2
    assert fno_n11.lot_ceiling("N11_TPB_LOW", 719, True, 0.0) == 2
    assert fno_n11.lot_ceiling("N11_TPB_LOW", 720, True, 0.0) == 1, "a low-day pullback from 12:00: one lot"
    assert fno_n11.lot_ceiling("N11_EFF", 800, True, 0.0) == 2, "the morning rule is the low-day pullback's alone"


def test_vol_reading_matches_the_research_formula():
    """The same bars, the research's loop (n09_lab.vol_table) written out: the reading strictly before the day, the median of the 250 before that."""
    rng = np.random.default_rng(5)
    days = pd.bdate_range("2025-01-01", periods=330)
    close = 22000 + np.cumsum(rng.normal(0, 90, len(days)))
    high, low = close + rng.uniform(20, 160, len(days)), close - rng.uniform(20, 160, len(days))
    frame = pd.DataFrame({"date": days, "open": close, "high": high, "low": low, "close": close})
    target = days[-1].date()
    atr, prev, readings = None, None, []
    for i in range(len(days) - 1):
        tr = high[i] - low[i] if prev is None else max(high[i] - low[i], abs(high[i] - prev), abs(low[i] - prev))
        atr = tr if atr is None else atr + (tr - atr) / 14
        if i >= 14:
            readings.append(atr / close[i] * 100)
        prev = close[i]
    value, usual = fno_n11.vol_reading(frame, target)
    assert value == pytest.approx(readings[-1])
    assert usual == pytest.approx(float(np.median(readings[:-1][-250:])))


def test_vol_reading_never_reads_today():
    days = pd.bdate_range("2025-01-01", periods=200)
    frame = pd.DataFrame({"date": days, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0})
    target = days[-1].date()
    base = fno_n11.vol_reading(frame, target)
    frame.loc[frame.index[-1], ["high", "low"]] = [500.0, 1.0]
    assert fno_n11.vol_reading(frame, target) == base


def test_no_reading_means_one_lot_and_no_comfort():
    assert not fno_n11.vol_up(None, 1.0)
    assert not fno_n11.vol_up(1.0, None)


def test_entry_plan_ceiling_lowers_and_never_raises():
    assert EntryState.__dataclass_fields__["lot_ceiling"].default is None


# ---- EFF's retest and its soft clock ---------------------------------------------------------------------------------------

def _ctx(bar, close, *, low=None, high=None, opening=None, prev=None, hi4=100.0, lo4=90.0, fresh=True, start="2026-11-02 09:15:00", atr=4.0):
    return {"bar": bar, "close": close, "open": opening if opening is not None else close - 1, "high": high if high is not None else close + 1, "low": low if low is not None else close - 1,
            "previous_close": prev if prev is not None else close - 1, "atr": atr, "rvol": 1.5, "vwap": close, "prior4high": hi4, "prior4low": lo4, "fresh": fresh, "consecutive_from": start}


def test_retest_matches_the_research_state_machine_on_random_paths():
    rules = _load("eff_rules_research", RESEARCH / "2026-11-01-fno-eff-improvement/eff_rules.py")
    rng = random.Random(7)
    for _ in range(300):
        mine, theirs = fno_book.EffRetest(), rules.RetestState()
        price = 100.0
        minute = 600
        for _step in range(12):
            minute += 5
            bar = f"2026-11-02 {minute // 60:02d}:{minute % 60:02d}:00"
            price += rng.uniform(-3, 3)
            low, high = price - rng.uniform(0, 3), price + rng.uniform(0, 3)
            ctx = _ctx(bar, price, low=low, high=high, opening=price + rng.uniform(-2, 2), prev=price + rng.uniform(-2, 2), hi4=price + rng.uniform(-3, 3), lo4=price - rng.uniform(0, 6))
            if rng.random() < 0.3:
                sign = rng.choice([1, -1])
                original = MomSignal(bar_ts=bar, direction=FnoDirection.LONG if sign == 1 else FnoDirection.SHORT, close=price, atr=4.0,
                                     stop_underlying=price - sign * 8.0, target_underlying=price + sign * 14.4)
            else:
                original = MomSignal(bar_ts=bar, reject_reason="eff:no_trigger")
            a, ia = mine.step(original, ctx, "REGIME_1")
            b, ib = theirs.step(original, ctx, "REGIME_1")
            assert ia == ib
            assert (a is None) == (b is None)
            if a is not None:
                assert (a.bar_ts, a.close, a.stop_underlying, a.target_underlying, a.direction) == (b.bar_ts, b.close, b.stop_underlying, b.target_underlying, b.direction)


def test_retest_cancels_on_stale_or_crisis():
    state = fno_book.EffRetest()
    original = MomSignal(bar_ts="b", direction=FnoDirection.LONG, close=101.0, atr=4.0, stop_underlying=93.0, target_underlying=115.0)
    state.step(original, _ctx("2026-11-02 11:00:00", 101.0), "REGIME_1")
    assert state.pending is not None
    assert state.step(original, _ctx("2026-11-02 11:05:00", 101.0, fresh=False), "REGIME_1")[0] is None and state.pending is None


def test_eff_clock_matches_the_research_chain():
    horizon = _load("eff_rules_research2", RESEARCH / "2026-11-01-fno-eff-improvement/eff_rules.py").horizon
    choose = _load("anatomy_rules_research", RESEARCH / "2026-11-01-fno-failure-anatomy/anatomy_rules.py").choose
    rng = random.Random(9)
    for _ in range(3000):
        age, trail, entry = rng.uniform(0, 100), rng.random() < 0.2, rng.uniform(50, 300)
        bid, progress, lots = entry + rng.uniform(-40, 25), rng.uniform(-1, 2), rng.choice([1, 2])
        qty = lots * 65
        net = (bid - entry) * qty - calc_fno_costs(entry, bid, qty) - (200 + 5 * lots) * lots
        parent, _action = horizon(age, trail, net, progress, None, "LONG")
        expected, _why = choose("PREMIUM_STALL", parent == 30.0, age, bid, entry, None, None, "LONG")
        assert fno_n11.eff_clock(age, trail, bid, entry, qty, lots, progress) == expected, (age, trail, bid, entry, progress)


# ---- N11's exits --------------------------------------------------------------------------------------------------------

def test_exit_labels():
    assert fno_book.exit_overrides("N11_EFF")["FNO_TRAIL_ATR_MULT"] == 2.0 and fno_book.exit_overrides("N11_OR20")["FNO_TRAIL_ATR_MULT"] == 2.0
    assert fno_book.exit_overrides("N11_TPB") == fno_book.exit_overrides("TPB") == fno_book.exit_overrides("N11_TPB_LOW")
    assert fno_book.exit_overrides("N11_SHIPPED") == {}
    assert fno_book.exit_overrides("N11_OR20")["FNO_TIME_STOP_MIN"] == fno_book.exit_overrides("OR20")["FNO_TIME_STOP_MIN"]
    assert fno_book.exit_overrides("EFF")["FNO_TRAIL_ATR_MULT"] == 1.5, "an older position keeps its old exits"
    add = fno_book.exit_overrides("N11_ADD")
    assert add["FNO_PROFIT_LOCK_ENABLED"] is False and add["FNO_TIME_STOP_MIN"] >= 1e5


# ---- the book's signals ------------------------------------------------------------------------------------------------

def _fired(direction=FnoDirection.SHORT):
    return MomSignal(bar_ts="2026-11-02 10:55:00", direction=direction, close=100.0, atr=4.0, stop_underlying=108.0, target_underlying=85.6)


def _quiet():
    return MomSignal(bar_ts="2026-11-02 10:55:00", reject_reason="no_signal")


@pytest.fixture
def signals(monkeypatch):
    table = {"OR20": _quiet(), "TPB": _quiet(), "EFF": _quiet()}
    import fno_shadow
    monkeypatch.setattr(fno_shadow, "_variant_signal", lambda bars, regime, now, variant: table["TPB" if "PULLBACK" in variant.name else "OR20"])
    monkeypatch.setattr(fno_book, "eff_retest", lambda bars, regime, now, underlying: table["EFF"])
    monkeypatch.setattr(fno_book, "entry_stretch", lambda bars, now, direction: 0.1)
    return table


def test_trending_day_order_and_labels(signals):
    bars = pd.DataFrame()
    assert fno_book.n11_signal(bars, "R", at(), shipped=_fired(), adx_side="HIGH").strategy == "N11_SHIPPED"
    signals["OR20"] = _fired()
    assert fno_book.n11_signal(bars, "R", at(), shipped=_quiet(), adx_side="HIGH").strategy == "N11_OR20"
    signals["OR20"], signals["EFF"] = _quiet(), _fired()
    assert fno_book.n11_signal(bars, "R", at(), shipped=_quiet(), adx_side="HIGH").strategy == "N11_EFF"
    signals["EFF"], signals["TPB"] = _quiet(), _fired()
    assert fno_book.n11_signal(bars, "R", at(), shipped=_quiet(), adx_side="HIGH").strategy == "N11_TPB"


def test_sideways_day_is_the_put_pullback_only(signals):
    bars = pd.DataFrame()
    signals["OR20"] = _fired()
    out = fno_book.n11_signal(bars, "R", at(), shipped=_fired(), adx_side="LOW")
    assert out.direction is None, "breakouts don't trade a sideways day"
    signals["TPB"] = _fired()
    assert fno_book.n11_signal(bars, "R", at(), shipped=_quiet(), adx_side="LOW").strategy == "N11_TPB_LOW"
    signals["TPB"] = _fired(FnoDirection.LONG)
    out = fno_book.n11_signal(bars, "R", at(), shipped=_quiet(), adx_side="LOW")
    assert out.direction is None and out.reject_reason == "n11:low_direction"
    signals["TPB"] = _fired()
    out = fno_book.n11_signal(bars, "R", at(hhmm="14:00"), shipped=_quiet(), adx_side="LOW")
    assert out.direction is None and out.reject_reason == "n11:low_too_late"


def test_unknown_adx_takes_no_entry(signals):
    assert fno_book.n11_signal(pd.DataFrame(), "R", at(), shipped=_fired(), adx_side=None).direction is None


def test_stretched_first_signal_takes_no_entry_this_tick(signals, monkeypatch):
    monkeypatch.setattr(fno_book, "entry_stretch", lambda bars, now, direction: 0.5)
    signals["TPB"] = _fired()
    out = fno_book.n11_signal(pd.DataFrame(), "R", at(), shipped=_fired(), adx_side="HIGH")
    assert out.direction is None and out.reject_reason == "stretched:SHIPPED"


# ---- the honest charge -----------------------------------------------------------------------------------------------------

def test_budget_scales_down_never_up():
    assert fno_n11.budget(250000.0, 1.5) == 5000.0
    assert fno_n11.budget(250000.0, 1.0) == 5000.0
    assert fno_n11.budget(250000.0, 0.5) == 2500.0
    assert fno_n11.budget(100000.0, 1.0) == 2000.0


def test_charges_match_the_research_rules():
    rules = _load("n11_rules_research2", RESEARCH / "2026-11-02-fno-n11/n11_rules.py")
    fees = lambda a, b, n: 40.0 + 0.0015 * b * n  # noqa: E731
    rng = random.Random(11)
    for _ in range(500):
        direction = rng.choice(["LONG", "SHORT"])
        future, level = 21000 + rng.uniform(-200, 200), 21000 + rng.uniform(-200, 200)
        bid, delta, entry = rng.uniform(40, 300), rng.uniform(-0.7, 0.7), rng.uniform(40, 300)
        assert fno_n11.parent_loss_at_stop(direction, future, bid, delta, level, entry, 0.75 * entry, 130, 420.0, fees) == pytest.approx(
            rules.parent_loss_at_stop(direction, future, bid, delta, level, entry, 0.75 * entry, 130, 420.0, fees))
        assert fno_n11.child_full_loss(bid, 0.25, 65, 205.0, fees) == pytest.approx(rules.child_full_loss(bid, 0.25, 65, 205.0, fees))


def test_is_parent():
    assert fno_n11.is_parent(SimpleNamespace(strategy="N11_EFF")) and not fno_n11.is_parent(SimpleNamespace(strategy="N11_ADD"))
    assert not fno_n11.is_parent(SimpleNamespace(strategy="EFF")) and not fno_n11.is_parent(SimpleNamespace(strategy=None))


# ---- the database -------------------------------------------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db(tmp_path):
    fno_n11._READY.clear()
    return str(tmp_path / "n11.db")


def test_seed_is_the_research_record(db):
    nets = _run(fno_n11.paper_nets(db, at()))
    assert len(nets) >= 20 and round(sum(nets[-20:])) == 25308


def test_paper_reading_never_sees_its_own_exit(db):
    assert len(_run(fno_n11.paper_nets(db, IST.localize(datetime.fromisoformat("2026-10-23T15:10:59"))))) == len(fno_n11.SEED_NETS) - 1


def test_seed_is_idempotent(db):
    _run(fno_n11.init_db(db))
    fno_n11._READY.clear()
    _run(fno_n11.init_db(db))
    assert len(_run(fno_n11.paper_nets(db, at()))) == len(fno_n11.SEED_NETS)


async def _position(db, **change):
    fields = dict(source="FNO_PAPER", tradingsymbol="NIFTY26N0425000PE", token=11, underlying="NIFTY", expiry="2026-11-04", strike=25000.0, opt_type="PE", direction="SHORT",
                  lots=2, lot_size=65, qty=130, entry_time="2026-11-02T10:00:00+05:30", entry_date="2026-11-02", entry_premium=120.0, entry_underlying=25000.0,
                  delta_at_entry=-0.5, iv_at_entry=0.15, atr_at_entry=12.0, stop_underlying=25030.0, target_underlying=24946.0, premium_stop=90.0,
                  trail_active=0, trail_stop_underlying=None, best_underlying=25000.0, max_loss_rupees=15600.0, status="OPEN", entry_order_id=None, bar_ts="2026-11-02 09:55:00", strategy="N11_TPB")
    fields.update(change)
    await fpos.init_fno_positions_db(db)
    return await fpos.insert_position(db, **fields)


def test_child_counts_and_parent_link(db):
    async def body():
        parent = await _position(db)
        await _position(db, lots=1, qty=65, bar_ts=f"N11ADD:{parent}", strategy="N11_ADD")
        assert await fno_n11.child_counts(db, "FNO_PAPER", "2026-11-02") == (1, 1)
        assert await fno_n11.parent_open(db, "FNO_PAPER", f"N11ADD:{parent}")
        async with aiosqlite.connect(db) as conn:
            await conn.execute("UPDATE fno_positions SET status='CLOSED' WHERE id=?", (parent,))
            await conn.commit()
        assert not await fno_n11.parent_open(db, "FNO_PAPER", f"N11ADD:{parent}")
        assert await fno_n11.parent_open(db, "FNO_PAPER", "not-a-link"), "an unreadable link leaves its own stops in charge"
    _run(body())


def test_an_earned_lots_loss_is_no_strike_and_sets_no_reentry_level(db):
    async def body():
        await _position(db, strategy="N11_ADD", lots=1, qty=65, bar_ts="N11ADD:9")
        async with aiosqlite.connect(db) as conn:
            await conn.execute("UPDATE fno_positions SET status='CLOSED', exit_time='2026-11-02T11:00:00+05:30', exit_date='2026-11-02', pnl=-900, exit_reason='underlying_stop'")
            await conn.commit()
        closes = await read_book_closes(db, "FNO_PAPER")
        assert [c.single_leg for c in closes] == [False] and closes[0].pnl == -900
        assert await fpos.stopped_entry_levels_today(db, "FNO_PAPER", "NIFTY", "2026-11-02", ("underlying_stop",), 0.25) == {}
    _run(body())


def test_a_parents_loss_still_is(db):
    async def body():
        await _position(db)
        async with aiosqlite.connect(db) as conn:
            await conn.execute("UPDATE fno_positions SET status='CLOSED', exit_time='2026-11-02T11:00:00+05:30', exit_date='2026-11-02', pnl=-900, exit_reason='underlying_stop'")
            await conn.commit()
        assert [c.single_leg for c in await read_book_closes(db, "FNO_PAPER")] == [True]
        assert await fpos.stopped_entry_levels_today(db, "FNO_PAPER", "NIFTY", "2026-11-02", ("underlying_stop",), 0.25) != {}
        assert await fno_n11.realised_today(db, "FNO_PAPER", "2026-11-02") == -900.0
    _run(body())


class _Kite:
    def __init__(self, days=330):
        rng = np.random.default_rng(1)
        index = pd.bdate_range(end="2026-11-02", periods=days)
        close = 25000 + np.cumsum(rng.normal(0, 60, days))
        self.frame = pd.DataFrame({"date": index, "open": close, "high": close + 80, "low": close - 80, "close": close})

    async def get_historical(self, *_a, **_k):
        return self.frame


def test_gate_reads_once_and_notes_the_day(db, monkeypatch):
    fno_n11._VOL.clear()
    fno_n11._VOL_RETRY.clear()
    sent = []

    async def note(text, event=None):
        sent.append((text, event))
    import operator_alert
    monkeypatch.setattr(operator_alert, "notify_operator", note)

    async def body():
        kite = _Kite()
        before = await fno_n11.gate(db, kite, at(hhmm="09:20"))
        assert before["atr_pct"] is None and not before["stand"], "before 09:30 nothing is read, and the seed record is good"
        first = await fno_n11.gate(db, kite, at(hhmm="10:00"))
        second = await fno_n11.gate(db, kite, at(hhmm="10:01"))
        assert first["atr_pct"] == second["atr_pct"] and first["atr_pct"] is not None
    _run(body())
    assert len(sent) == 1 and sent[0][1] == "fno_n11_gate" and "Paper only" in sent[0][0]


def test_gate_failure_is_not_kept(db):
    fno_n11._VOL.clear()
    fno_n11._VOL_RETRY.clear()

    class Bad:
        async def get_historical(self, *_a, **_k):
            raise RuntimeError("down")

    assert _run(fno_n11.gate(db, Bad(), at()))["vol_up"] is False
    assert not fno_n11._VOL


def _paper_row(**change):
    row = dict(underlying="NIFTY", bar_ts="2026-11-02 10:55:00", strategy="N11_TPB", direction="SHORT", tradingsymbol="X", token=11, lot_size=65, entry_time="2026-11-02T11:00:00+05:30",
               entry_premium=100.0, entry_underlying=25000.0, stop_underlying=25030.0, target_underlying=24946.0, premium_stop=75.0, atr_at_entry=12.0, delta_at_entry=-0.5,
               best_underlying=25000.0, native_lots=2, vol_lots=2, stood_aside=0, status="OPEN", source=fno_n11.PAPER_SOURCE)
    row.update(change)
    return row


async def _insert_paper(db, **change):
    row = _paper_row(**change)
    await fno_n11.init_db(db)
    async with aiosqlite.connect(db) as conn:
        await conn.execute(f"INSERT INTO fno_n11_paper({','.join(row)}) VALUES({','.join('?' for _ in row)})", tuple(row.values()))
        await conn.commit()


def _quotes(bid):
    async def read(_kite, tokens):
        return {t: {"depth": {"buy": [{"price": bid}], "sell": [{"price": bid + 0.5}]}, "last_price": bid} for t in tokens}, None
    return read


def test_paper_lot_closes_on_its_stop_with_research_money(db):
    fno_n11._PAPER_LAST.clear()

    async def body():
        await _insert_paper(db)
        assert await fno_n11.manage_paper(None, db, at(hhmm="11:10"), {"NIFTY": 25031.0}, _quotes(85.0)) == 1
        async with aiosqlite.connect(db) as conn:
            row = await (await conn.execute("SELECT status, exit_reason, net FROM fno_n11_paper WHERE source=?", (fno_n11.PAPER_SOURCE,))).fetchone()
        assert row[0] == "CLOSED" and row[1] == "underlying_stop"
        assert row[2] == pytest.approx(-15.0 * 65 - calc_fno_costs(100.0, 85.0, 65) - 205.0)
    _run(body())


def test_paper_lot_keeps_its_trail_state_and_stays_open(db):
    fno_n11._PAPER_LAST.clear()

    async def body():
        await _insert_paper(db)
        assert await fno_n11.manage_paper(None, db, at(hhmm="11:10"), {"NIFTY": 24940.0}, _quotes(140.0)) == 0
        async with aiosqlite.connect(db) as conn:
            row = await (await conn.execute("SELECT status, trail_active, best_underlying FROM fno_n11_paper WHERE source=?", (fno_n11.PAPER_SOURCE,))).fetchone()
        assert row == ("OPEN", 1, 24940.0)
    _run(body())


def test_yesterdays_paper_lot_never_enters_the_record(db):
    fno_n11._PAPER_LAST.clear()

    async def body():
        await _insert_paper(db, entry_time="2026-10-30T11:00:00+05:30")
        before = len(await fno_n11.paper_nets(db, at()))
        await fno_n11.manage_paper(None, db, at(), {"NIFTY": 25031.0}, _quotes(85.0))
        assert len(await fno_n11.paper_nets(db, at())) == before
    _run(body())


def test_paper_manage_runs_about_once_a_minute_except_the_flat(db):
    fno_n11._PAPER_LAST.clear()
    calls = []

    async def read(_kite, tokens):
        calls.append(tokens)
        return {t: {"depth": {"buy": [{"price": 100.0}]}, "last_price": 100.0} for t in tokens}, None

    async def body():
        await _insert_paper(db)
        await fno_n11.manage_paper(None, db, at(hhmm="11:10"), {"NIFTY": 25000.0}, read)
        await fno_n11.manage_paper(None, db, at(hhmm="11:10"), {"NIFTY": 25000.0}, read)
        assert len(calls) == 1
        await fno_n11.manage_paper(None, db, at(hhmm="15:10"), {"NIFTY": 25000.0}, read)
        assert len(calls) == 2
    _run(body())


def test_shadow_table_sizes_the_same_trades():
    row = {"lot_size": 65, "entry_premium": 100.0, "exit_premium": 120.0, "net": 1.0, "native_lots": 2, "vol_lots": 1}
    table = fno_n11.shadow_table([row])
    one = 20.0 * 65 - calc_fno_costs(100.0, 120.0, 65) - 205.0
    two = 20.0 * 130 - calc_fno_costs(100.0, 120.0, 130) - 420.0
    assert table["trades"] == 1 and table["one_lot"] == pytest.approx(one) and table["N08"] == pytest.approx(two) and table["size_by_volatility"] == pytest.approx(one)


# ---- the earned lot end to end, on the real risk tables --------------------------------------------------------------------

class _PaperExec:
    paper_mode = True

    def __init__(self):
        self.calls = []

    async def execute_entry(self, symbol, qty, ask, **kw):
        self.calls.append((symbol, qty, ask, kw))
        return {"status": "paper", "fill_price": ask, "order_id": None}


async def _risk_tables(db):
    import fno_dr_book
    from fno_shared_risk import init_shared_fno_risk_db
    from performance import init_ledger
    await init_ledger(db)
    await fpos.init_fno_positions_db(db)
    await fno_dr_book.init_dr_db(db)
    await init_shared_fno_risk_db(db)


async def _equity():
    return 250000.0


def _depth(bid, ask):
    async def read(_kite, tokens):
        return {t: {"depth": {"buy": [{"price": bid}], "sell": [{"price": ask}]}, "last_price": bid} for t in tokens}, None
    return read


def test_add_fires_at_plus_one_r_inside_the_charge(db):
    async def body():
        await _risk_tables(db)
        parent = await _position(db, trail_active=1, trail_stop_underlying=24990.0)
        exe = _PaperExec()
        added = await fno_n11.maybe_add(None, db, "FNO_PAPER", exe, at(hhmm="11:00"), {"NIFTY": 24965.0}, 250000.0, _equity, _depth(130.0, 131.0))
        assert len(added) == 1 and exe.calls == [("NIFTY26N0425000PE", 65, 131.0, {})]
        rows = await fpos.open_positions(db, "FNO_PAPER")
        child = next(p for p in rows if p.strategy == fno_n11.ADD)
        assert child.bar_ts == f"N11ADD:{parent}" and child.lots == 1 and child.stop_underlying == 25000.0 and child.premium_stop == round(0.75 * 131.0, 2)
        again = await fno_n11.maybe_add(None, db, "FNO_PAPER", exe, at(hhmm="11:01"), {"NIFTY": 24960.0}, 250000.0, _equity, _depth(135.0, 136.0))
        assert again == [], "one earned lot, ever"
    _run(body())


def test_add_never_moves_the_held_lots_stop(db):
    async def body():
        await _risk_tables(db)
        await _position(db, trail_active=1, trail_stop_underlying=24990.0)
        before = next(p for p in await fpos.open_positions(db, "FNO_PAPER") if p.strategy == "N11_TPB")
        await fno_n11.maybe_add(None, db, "FNO_PAPER", _PaperExec(), at(hhmm="11:00"), {"NIFTY": 24965.0}, 250000.0, _equity, _depth(130.0, 131.0))
        after = next(p for p in await fpos.open_positions(db, "FNO_PAPER") if p.strategy == "N11_TPB")
        assert (after.premium_stop, after.stop_underlying, after.trail_stop_underlying) == (before.premium_stop, before.stop_underlying, before.trail_stop_underlying)
    _run(body())


@pytest.mark.parametrize("change,now,future,why", [
    ({"lots": 1, "qty": 65}, "11:00", 24965.0, "only a two-lot trade earns one"),
    ({}, "11:00", 24975.0, "not yet at +1R"),
    ({}, "14:45", 24965.0, "not from 14:45"),
    ({"strategy": "EFF"}, "11:00", 24965.0, "an older book's position never adds"),
])
def test_add_refused(db, change, now, future, why):
    async def body():
        await _risk_tables(db)
        await _position(db, **change)
        exe = _PaperExec()
        assert await fno_n11.maybe_add(None, db, "FNO_PAPER", exe, at(hhmm=now), {"NIFTY": future}, 250000.0, _equity, _depth(130.0, 131.0)) == [], why
        assert exe.calls == []
    _run(body())


def test_add_refused_when_the_honest_charge_doesnt_fit(db):
    """At first reach, with the held lots' stop still 30 points back on an expensive option, the two charges together pass Rs 5,000."""
    async def body():
        await _risk_tables(db)
        await _position(db, entry_premium=250.0, premium_stop=187.5, max_loss_rupees=32500.0)
        exe = _PaperExec()
        assert await fno_n11.maybe_add(None, db, "FNO_PAPER", exe, at(hhmm="11:00"), {"NIFTY": 24965.0}, 250000.0, _equity, _depth(262.0, 263.0)) == []
        assert exe.calls == []
    _run(body())


def test_tick_survives_every_step_failing(db, monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("step failed")
    for name in ("_volatility", "manage_paper", "maybe_add", "send_shadow_report_once"):
        monkeypatch.setattr(fno_n11, name, boom)
    assert _run(fno_n11.tick(None, db, executor=None, now=at(), fut_prices={}, pool_rs=250000.0, equity_reader=_equity, read_quote=None)) == []


def test_default_book_is_n11():
    from config import Settings
    assert Settings.model_fields["FNO_BOOK"].default == "N11"
    assert fno_book.N11_BOOK in fno_book.BOOKS


def test_book_switch_back(n11_mode, monkeypatch):
    assert fno_book.mode() == "N11"
    monkeypatch.setattr(settings, "FNO_BOOK", "UNION_ADX")
    assert fno_book.mode() == fno_book.ADX_BOOK
    assert date(2026, 11, 2) - timedelta(days=1) == date(2026, 11, 1)
