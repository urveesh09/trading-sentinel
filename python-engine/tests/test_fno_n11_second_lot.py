"""[N11T] The tolerance's second lot: pinned against the research's rule file, its limits on random inputs, and wired through the real entry path on a temporary database."""
from __future__ import annotations

import asyncio
import importlib.util
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import aiosqlite
import pytest
import pytz

import fno_n11
import fno_positions as fpos
from config import Settings, settings
from fno_costs import calc_fno_costs
from fno_engine_mom import MomSignal
from fno_entry_plan import EntryPlan
from fno_models import FnoDirection, OptionType

IST = pytz.timezone("Asia/Kolkata")
ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "docs/research/simulation/2026-11-02-fno-n11/n11_rules.py"
LOT = 65
NOW = IST.localize(datetime(2026, 11, 2, 11, 0))


def _rules():
    spec = importlib.util.spec_from_file_location("n11_rules_second", RESEARCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fees(a, b, n):
    return calc_fno_costs(a, b, n)


def _quote(ask=250.0):
    contract = SimpleNamespace(tradingsymbol="NIFTY26N0425000PE", token=11, strike=25000.0, lot_size=LOT, expiry=date(2026, 11, 4))
    return SimpleNamespace(ask=ask, contract=contract)


def _first(ask=250.0, lots=1, delta=-0.5, accepted=True):
    return EntryPlan(accepted, "", log_fields={"passed_gates": [], "lots": lots, "max_loss_rupees": ask * lots * LOT}, quote=_quote(ask), opt_type=OptionType.PE, iv=0.15, delta=delta, lots=lots, lot_size=LOT, max_loss_rupees=ask * lots * LOT)


def _state(pool=250000.0, m=1.0, open_premium=0.0):
    return SimpleNamespace(pool=pool, risk_multiplier=m, open_premium=open_premium)


def _second(first=None, state=None, **change):
    kwargs = dict(stop_points=20.0, ceiling=2, is_vol_up=True, is_paper_positive=True)
    kwargs.update(change)
    return fno_n11.second_lot(first or _first(), state or _state(), **kwargs)


# ---- the amount -----------------------------------------------------------------------------------------------------------

def test_the_amount_is_the_plans_and_on_by_default():
    assert Settings.model_fields["FNO_N11_TOLERANCE_ENABLED"].default is True
    assert Settings.model_fields["FNO_N11_TOLERANCE_RUPEES"].default == 6250.0
    assert Settings.model_fields["FNO_N11_TOLERANCE_STOP_FACTOR"].default == 1.75


def test_limit_shrinks_in_a_drawdown_and_never_grows():
    assert fno_n11.tolerance_limit(1.0) == 6250.0
    assert fno_n11.tolerance_limit(1.5) == 6250.0, "a winning streak never lifts it"
    assert fno_n11.tolerance_limit(0.5) == 3125.0
    assert fno_n11.tolerance_limit(0.25) == 1562.5


# ---- each condition, one at a time -----------------------------------------------------------------------------------------

def test_the_good_case_takes_a_second_lot():
    out = _second()
    assert out.plan.lots == 2 and out.limit == 6250.0 and out.reason == fno_n11.STOP_FITS
    assert out.plan.max_loss_rupees == 250.0 * 2 * LOT and out.plan.log_fields["lots"] == 2


@pytest.mark.parametrize("change", [{"is_vol_up": False}, {"is_paper_positive": False}, {"ceiling": 1}])
def test_every_reading_must_be_good(change):
    assert _second(**change) is None


def test_the_switch_turns_it_off(monkeypatch):
    monkeypatch.setattr(settings, "FNO_N11_TOLERANCE_ENABLED", False)
    assert _second() is None


def test_it_adds_only_to_an_accepted_one_lot_trade():
    assert _second(first=_first(accepted=False)) is None, "it admits no new trade"
    assert _second(first=_first(ask=100.0, lots=2)) is None, "no third lot"


def test_a_stop_too_far_for_its_backstop_stays_one_lot():
    assert _second(stop_points=60.0) is None, "1.75 x 0.5 x 60 = 52.5 points, past the 43 or so the limit allows"


def test_a_cheap_option_needs_no_stop_check_because_its_normal_backstop_fits():
    out = _second(first=_first(ask=190.0), stop_points=500.0)
    assert out.reason == fno_n11.BACKSTOP_FITS
    assert _second(first=_first(ask=193.0), stop_points=500.0) is None, "Rs 193 x 25% x 130 is past Rs 6,250"


def test_the_open_premium_cap_has_the_last_word():
    room = 0.15 * 250000.0 - 2 * 250.0 * LOT
    assert _second(state=_state(open_premium=room)) is not None
    assert _second(state=_state(open_premium=room + 1.0)) is None


def test_the_structural_cap_has_the_last_word():
    assert _second(first=_first(ask=308.0), state=_state(pool=500000.0)) is None, "Rs 308 x 130 is past the Rs 40,000 structural cap"


# ---- the backstop --------------------------------------------------------------------------------------------------------

def test_planned_loss_stays_inside_the_limit_on_random_trades():
    rng = random.Random(21)
    tightened = 0
    for _ in range(3000):
        ask = round(rng.uniform(60.0, 300.0) * 20) / 20
        limit = rng.choice([6250.0, 6250.0, 3125.0, 4687.5])
        native = round(0.75 * ask, 2)
        stop = fno_n11.second_lot_stop(ask, 130, 2, limit, native)
        assert stop >= native
        if stop > native:
            tightened += 1
            planned = (ask - stop) * 130 + calc_fno_costs(ask, stop, 130) + fno_n11.extra_cost(2)
            assert planned <= limit + 1e-6, (ask, limit, stop, planned)
    assert tightened > 1000


def test_a_tick_rounds_the_stop_up_never_down():
    assert fno_n11.stop_price(250.0, 43.33) == 206.7


def test_stop_matches_the_research_rule():
    rules = _rules()
    rng = random.Random(4)
    for _ in range(1000):
        ask, limit, lots = rng.uniform(40, 320), rng.uniform(1500, 7500), rng.choice([1, 2])
        qty = lots * LOT
        extra = fno_n11.extra_cost(lots)
        ours, theirs = fno_n11.backstop_points(limit, ask, qty, extra, _fees), rules.backstop_points(limit, ask, qty, extra, _fees)
        assert ours == theirs
        if ours is not None:
            assert fno_n11.stop_price(ask, ours) == rules.stop_price(ask, ours)


def test_the_reason_matches_the_research_size_rule():
    """Research's true_risk_lots answers the stop's half on the same inputs. The budget's half is the planner's own arithmetic, and parity_final.py compares both on every entry of four years."""
    rules = _rules()
    rng = random.Random(8)
    for _ in range(3000):
        ask, delta, stop = rng.uniform(60, 300), rng.uniform(-0.7, 0.7), rng.uniform(1, 90)
        if int(6250.0 // (ask * LOT * 0.25)) >= 2:
            continue
        lots, _points = rules.true_risk_lots(1, 2, ask, delta, stop, LOT, 6250.0, 1.75, 0.25, _fees, fno_n11.extra_cost)
        assert (fno_n11.second_lot_reason(ask, delta, stop, LOT, 250000.0, 1.0, _fees) == fno_n11.STOP_FITS) == (lots == 2), (ask, delta, stop)


def test_the_paper_reading_matches_the_research_rule():
    rules = _rules()
    rng = random.Random(6)
    for _ in range(500):
        nets = [rng.uniform(-3000, 3000) for _ in range(rng.randint(0, 40))]
        assert fno_n11.paper_positive(nets) == rules.evidence_positive(nets)


def test_a_proven_stance_keeps_its_own_room_and_the_limit_stays():
    assert fno_n11.second_lot_reason(225.0, -0.5, 500.0, LOT, 250000.0, 1.5, _fees) == fno_n11.BACKSTOP_FITS, "the stance already allows Rs 7,500 on the 25% measure"
    assert _second(first=_first(ask=250.0), state=_state(m=1.5)).limit == 6250.0


def test_a_drawdown_shrinks_what_fits():
    assert fno_n11.second_lot_reason(250.0, -0.5, 30.0, LOT, 250000.0, 1.0, _fees) == fno_n11.STOP_FITS, "the whole limit fits this stop"
    assert fno_n11.second_lot_reason(250.0, -0.5, 30.0, LOT, 250000.0, 0.5, _fees) is None, "half the limit doesn't"
    assert fno_n11.second_lot_reason(250.0, -0.5, 8.0, LOT, 250000.0, 0.5, _fees) == fno_n11.STOP_FITS


# ---- the real entry path ---------------------------------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db(tmp_path):
    fno_n11._READY.clear()
    return str(tmp_path / "second.db")


class _PaperExec:
    def __init__(self):
        self.qty = []

    async def execute_entry(self, symbol, qty, ask, **kw):
        self.qty.append(qty)
        return {"status": "paper", "fill_price": ask, "order_id": None}


def _sig(strategy="N11_TPB"):
    return MomSignal(bar_ts="2026-11-02 10:55:00", direction=FnoDirection.SHORT, close=25000.0, atr=12.0, stop_underlying=25020.0, target_underlying=24960.0, strategy=strategy)


def _accepted_plan(sig, snap, regime, now, state):
    plan = _first()
    plan.reward_risk = 2.0
    plan.gate_context = SimpleNamespace(now_min=660, quote_age_sec=0.0, chain_age_sec=0.0)
    plan.quote = SimpleNamespace(ask=250.0, spread_pct=0.01, oi=1000, volume=1000, contract=SimpleNamespace(tradingsymbol="NIFTY26N0425000PE", token=11, strike=25000.0, lot_size=LOT, expiry=date(2026, 11, 4)))
    plan.iv = 0.15
    return plan


@pytest.fixture
def wired(monkeypatch):
    """The entry path with its book reads real and its market reads fixed: the N11 gate is good, and the planner accepts one lot at Rs 250."""
    import fno_orchestrator as fo
    good = {"vol_up": True, "above_line": True, "stand": False, "paper_sum": 5000.0, "paper_count": 22, "paper_positive": True}

    async def gate(db_path, kite, now):
        return dict(good)
    monkeypatch.setattr(fno_n11, "gate", gate)
    monkeypatch.setattr(fo, "plan_single_leg_entry", _accepted_plan)
    monkeypatch.setattr(settings, "FNO_BOOK", "N11")
    monkeypatch.setattr(settings, "FNO_DR_DISABLE_PAPER", True)
    return SimpleNamespace(fo=fo, good=good)


async def _enter(fo, db, *, source="FNO_PAPER", underlying="NIFTY", sig=None, exe=None, pool=250000.0):
    from performance import init_ledger
    await init_ledger(db)
    await fpos.init_fno_positions_db(db)
    exe = exe or _PaperExec()
    snap = SimpleNamespace(forward=25000.0, lot_size=LOT, age_sec=lambda now: 0.0)
    book = SimpleNamespace(segment="NFO", is_expiry_day=lambda day: False)
    entry = await fo._try_entry_for_leg(None, db, source, pool, exe, sig or _sig(), snap, "REGIME_1_NORMAL", NOW, "scan", True, shared_pool_rs=pool, underlying=underlying, underlying_book=book)
    rows = await fpos.open_positions(db, source)
    return entry, rows, exe


def _second_rows(db):
    async def body():
        await fno_n11.init_db(db)
        async with aiosqlite.connect(db) as conn:
            return await (await conn.execute("SELECT position_id, reason, limit_rupees, native_stop, premium_stop FROM fno_n11_second_lot")).fetchall()
    return _run(body())


def test_a_paper_nifty_trade_takes_its_second_lot_with_a_tighter_backstop(wired, db):
    entry, rows, exe = _run(_enter(wired.fo, db))
    assert entry["lots"] == 2 and exe.qty == [130] and entry["second_lot_limit"] == 6250.0
    position = rows[0]
    assert position.lots == 2 and position.qty == 130 and position.max_loss_rupees == 250.0 * 130
    assert position.premium_stop > round(0.75 * 250.0, 2)
    planned = (250.0 - position.premium_stop) * 130 + calc_fno_costs(250.0, position.premium_stop, 130) + 420.0
    assert planned <= 6250.0
    assert _second_rows(db) == [(position.id, fno_n11.STOP_FITS, 6250.0, 187.5, position.premium_stop)]
    assert "second lot, plan up to Rs 6,250" in wired.fo.format_fno_telegram({"entries": [{"source": "FNO_PAPER", "symbol": "X", "direction": "SHORT", "delta": -0.5, "iv": 0.15, "fill": 250.0, **entry}]})


def test_the_switch_off_is_exactly_n11(wired, db, monkeypatch):
    monkeypatch.setattr(settings, "FNO_N11_TOLERANCE_ENABLED", False)
    entry, rows, exe = _run(_enter(wired.fo, db))
    assert entry["lots"] == 1 and exe.qty == [65] and "second_lot_limit" not in entry
    assert rows[0].premium_stop == round(0.75 * 250.0, 2) and _second_rows(db) == []


@pytest.mark.parametrize("reading", ["vol_up", "paper_positive"])
def test_a_bad_reading_is_exactly_n11(wired, db, reading):
    wired.good[reading] = False
    entry, rows, _exe = _run(_enter(wired.fo, db))
    assert entry["lots"] == 1 and rows[0].premium_stop == round(0.75 * 250.0, 2) and _second_rows(db) == []


def test_a_realised_loss_today_is_exactly_n11(wired, db):
    async def body():
        await fpos.init_fno_positions_db(db)
        async with aiosqlite.connect(db) as conn:
            cols = [r[1] for r in await (await conn.execute("PRAGMA table_info(fno_positions)")).fetchall()]
            fields = {"source": "FNO_PAPER", "tradingsymbol": "OLD", "token": 9, "underlying": "NIFTY", "expiry": "2026-11-04", "strike": 25000.0, "opt_type": "PE", "direction": "SHORT", "lots": 1, "lot_size": LOT, "qty": LOT,
                      "entry_time": "2026-11-02T09:50:00+05:30", "entry_date": "2026-11-02", "entry_premium": 100.0, "exit_premium": 90.0, "entry_underlying": 25000.0, "stop_underlying": 25020.0, "target_underlying": 24960.0,
                      "premium_stop": 75.0, "best_underlying": 25000.0, "max_loss_rupees": 6500.0, "status": "CLOSED", "exit_date": "2026-11-02", "exit_time": "2026-11-02T10:10:00+05:30", "exit_reason": "underlying_stop", "pnl": -650.0, "bar_ts": "b0", "strategy": "N11_TPB"}
            fields = {k: v for k, v in fields.items() if k in cols}
            await conn.execute(f"INSERT INTO fno_positions({','.join(fields)}) VALUES({','.join('?' for _ in fields)})", tuple(fields.values()))
            await conn.commit()
        return await _enter(wired.fo, db)
    entry, _rows, _exe = _run(body())
    assert entry["lots"] == 1 and _second_rows(db) == []


def test_real_money_never_takes_a_second_lot(wired, db):
    entry, rows, _exe = _run(_enter(wired.fo, db, source="FNO_LIVE", exe=SimpleNamespace(execute_entry=_PaperExec().execute_entry)))
    assert entry["lots"] == 1 and rows[0].premium_stop == round(0.75 * 250.0, 2) and _second_rows(db) == []


def test_sensex_was_never_tested_so_it_stays_one_lot(wired, db):
    entry, _rows, _exe = _run(_enter(wired.fo, db, underlying="SENSEX"))
    assert entry["lots"] == 1 and _second_rows(db) == []


def test_a_refused_reservation_keeps_the_first_lot(wired, db, monkeypatch):
    real = wired.fo.reserve_shared_fno_risk
    asked = []

    async def tight(db_path, **kw):
        asked.append(kw["worst_case_cash_rs"])
        if kw["worst_case_cash_rs"] > 20000.0:
            return SimpleNamespace(allowed=False, reason="shared_worst_case_cash_exhausted", view=None)
        return await real(db_path, **kw)
    monkeypatch.setattr(wired.fo, "reserve_shared_fno_risk", tight)
    entry, rows, exe = _run(_enter(wired.fo, db))
    assert entry["lots"] == 1 and exe.qty == [65] and len(asked) == 2 and asked[0] > asked[1]
    assert rows[0].premium_stop == round(0.75 * 250.0, 2) and _second_rows(db) == []


def test_a_failed_evidence_row_never_fails_the_entry(wired, db, monkeypatch):
    async def boom(*a, **kw):
        raise RuntimeError("disk")
    monkeypatch.setattr(fno_n11, "record_second_lot", boom)
    entry, rows, _exe = _run(_enter(wired.fo, db))
    assert entry["lots"] == 2 and rows[0].lots == 2


# ---- the evening report ------------------------------------------------------------------------------------------------------

def test_the_report_says_what_the_second_lots_made(wired, db, monkeypatch):
    sent = []

    async def notify(text, event=None):
        sent.append(text)
    import operator_alert
    monkeypatch.setattr(operator_alert, "notify_operator", notify)

    async def body():
        await _enter(wired.fo, db)
        await fno_n11.init_db(db)
        evening = NOW.replace(hour=15, minute=20)
        async with aiosqlite.connect(db) as conn:
            await conn.execute("UPDATE fno_positions SET status='CLOSED', exit_premium=270.0, pnl=2400.0, exit_date='2026-11-02'")
            await conn.execute("INSERT INTO fno_n11_gate(session_date,atr_pct,usual,vol_up,above_line,recorded_at) VALUES('2026-11-02',1.2,1.0,1,1,'x')")
            await conn.commit()
        assert await fno_n11.send_shadow_report_once(db, evening)
    _run(body())
    own = (270.0 - 250.0) * LOT - (calc_fno_costs(250.0, 270.0, 130) - calc_fno_costs(250.0, 270.0, 65))
    assert f"Second lots today: 1, about Rs {own:+,.0f}" in sent[0] and f"plain N11 about Rs {2400.0 - own:+,.0f}" in sent[0]


def test_a_day_without_one_says_so(db, monkeypatch):
    sent = []

    async def notify(text, event=None):
        sent.append(text)
    import operator_alert
    monkeypatch.setattr(operator_alert, "notify_operator", notify)

    async def body():
        await fno_n11.init_db(db)
        await fpos.init_fno_positions_db(db)
        async with aiosqlite.connect(db) as conn:
            await conn.execute("INSERT INTO fno_n11_gate(session_date,atr_pct,usual,vol_up,above_line,recorded_at) VALUES('2026-11-02',1.2,1.0,1,1,'x')")
            await conn.commit()
        assert await fno_n11.send_shadow_report_once(db, NOW.replace(hour=15, minute=20))
    _run(body())
    assert "No second lots today." in sent[0]


def test_a_failed_second_lot_read_keeps_the_report(db, monkeypatch):
    sent = []

    async def notify(text, event=None):
        sent.append(text)

    async def boom(*a, **kw):
        raise RuntimeError("locked")
    import operator_alert
    monkeypatch.setattr(operator_alert, "notify_operator", notify)
    monkeypatch.setattr(fno_n11, "second_lots_today", boom)

    async def body():
        await fno_n11.init_db(db)
        await fpos.init_fno_positions_db(db)
        async with aiosqlite.connect(db) as conn:
            await conn.execute("INSERT INTO fno_n11_gate(session_date,atr_pct,usual,vol_up,above_line,recorded_at) VALUES('2026-11-02',1.2,1.0,1,1,'x')")
            await conn.commit()
        assert await fno_n11.send_shadow_report_once(db, NOW.replace(hour=15, minute=20))
    _run(body())
    assert len(sent) == 1 and "Second lots" not in sent[0]
