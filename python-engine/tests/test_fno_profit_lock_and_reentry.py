"""FNO-PROFIT-LOCK and FNO-REENTRY (2026-10-07): keep a won gain; re-enter only past a failed idea."""
from datetime import datetime
from types import SimpleNamespace

import aiosqlite
import pytest
import pytz

import fno_positions as fpos
from fno_entry_plan import (REENTRY_STOP_REASONS, plan_single_leg_entry, reentry_confirmed,
                            reentry_level)
from fno_exit_rules import evaluate_single_leg_exit, profit_lock_floor
from fno_models import FnoDirection
from tests.test_fno_entry_plan import FORWARD, NOW as PLAN_NOW, chain, signal, state

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 10, 7, 11, 0))
LOCK = {"FNO_TRAIL_ATR_MULT": 1.0, "FNO_TIME_STOP_MIN": 45, "FNO_TIME_STOP_MIN_R": 0.5,
        "FNO_TIME_STOP_RESPECTS_PREMIUM": True, "FNO_STOP_PREMIUM_PCT": 0.25,
        "FNO_PROFIT_LOCK_ENABLED": True, "FNO_PROFIT_LOCK_ARM_R": 0.4,
        "FNO_PROFIT_LOCK_FLOOR_R": 0.1, "FNO_PROFIT_LOCK_KEEP_FRACTION": 0.5}


def _pos(best_premium=None, entry_premium=200.0):
    # Long call, entry underlying 22,600, stop 40 points below, target far away.
    return SimpleNamespace(direction="LONG", entry_underlying=22600.0, stop_underlying=22560.0,
                           target_underlying=22800.0, atr_at_entry=30.0, entry_premium=entry_premium,
                           premium_stop=150.0, entry_time=NOW.isoformat(), trail_active=0,
                           trail_stop_underlying=None, best_underlying=22600.0, best_premium=best_premium)


def _step(pos, bid, fut=22610.0, params=LOCK):
    decision = evaluate_single_leg_exit(pos, now_ist=NOW, fut_price=fut, exit_px_basis=bid,
                                        hard_flat=False, params=params)
    pos.best_premium = decision.best_premium
    return decision


# ---------------------------------------------------------------- profit lock

def test_floor_arms_only_after_the_gain_reaches_arm_r_and_keeps_half():
    # premium-R = 200 x 0.25 = 50; arm at +20 (0.4 R); floor = max(entry + 5, entry + half the gain)
    assert profit_lock_floor(200.0, 219.0, LOCK) is None
    assert profit_lock_floor(200.0, 220.0, LOCK) == pytest.approx(210.0)
    assert profit_lock_floor(200.0, 240.0, LOCK) == pytest.approx(220.0)
    assert profit_lock_floor(200.0, 240.0, {**LOCK, "FNO_PROFIT_LOCK_KEEP_FRACTION": 0.0}) == pytest.approx(205.0)
    assert profit_lock_floor(200.0, 400.0, {**LOCK, "FNO_PROFIT_LOCK_ENABLED": False}) is None
    assert profit_lock_floor(200.0, 400.0, {}) is None                     # old param maps: off


def test_a_gain_given_back_exits_with_a_profit_instead_of_the_time_stop():
    pos = _pos()
    assert _step(pos, 205.0).exit_reason == ""
    assert _step(pos, 230.0).exit_reason == ""                             # armed; floor now 215
    assert _step(pos, 216.0).exit_reason == ""
    d = _step(pos, 214.0)
    assert d.exit_reason == "profit_lock" and d.profit_lock_floor == pytest.approx(215.0)


def test_one_sample_cannot_both_arm_and_fire_the_lock():
    pos = _pos(best_premium=None)
    assert _step(pos, 230.0).exit_reason == ""
    assert pos.best_premium == 230.0


def test_stops_keep_precedence_and_no_futures_quote_still_locks():
    pos = _pos(best_premium=240.0)
    assert _step(pos, 214.0, fut=22550.0).exit_reason == "underlying_stop"
    pos = _pos(best_premium=240.0)
    assert _step(pos, 214.0, fut=None).exit_reason == "profit_lock"
    pos = _pos(best_premium=240.0)
    assert _step(pos, 214.0, params={**LOCK, "FNO_PROFIT_LOCK_ENABLED": False}).exit_reason == ""


# ---------------------------------------------------------------- re-entry confirmation

def test_reentry_level_requires_a_margin_past_the_failed_entry():
    # Oct 7: put entered at 22,611.1 with its stop at 22,654.88 (43.8 points)
    level = reentry_level("SHORT", 22611.1, 22654.878, 0.25)
    assert level == pytest.approx(22611.1 - 0.25 * 43.778, abs=1e-3)
    levels = {"SHORT": level}
    assert not reentry_confirmed("SHORT", 22619.2, levels)                 # the 14:00 put: blocked
    assert not reentry_confirmed("SHORT", 22610.2, levels)                 # 0.9 pt past: still blocked
    assert reentry_confirmed("SHORT", 22590.0, levels)                     # a clear new low: allowed
    assert reentry_confirmed("LONG", 22700.0, levels)                      # other direction: never blocked
    assert reentry_confirmed("SHORT", 22619.2, None)


def test_plan_refuses_an_unconfirmed_reentry_with_its_level():
    blocked = plan_single_leg_entry(signal(), chain(), "REGIME_1_NORMAL", PLAN_NOW,
                                    state(reentry_levels={"LONG": FORWARD + 10.0}))
    assert blocked.reject_reason == "reentry_not_confirmed"
    assert blocked.log_fields["reentry_level"] == FORWARD + 10.0
    allowed = plan_single_leg_entry(signal(), chain(), "REGIME_1_NORMAL", PLAN_NOW,
                                    state(reentry_levels={"SHORT": FORWARD - 10.0}))
    assert allowed.accepted, allowed.reject_reason


@pytest.mark.asyncio
async def test_levels_come_from_todays_stopped_trades_on_the_same_underlying(tmp_path):
    db = str(tmp_path / "fno.db")
    await fpos.init_fno_positions_db(db)
    rows = [  # (underlying, direction, entry, stop, reason, exit_date, exit_time)
        ("NIFTY", "SHORT", 22611.1, 22654.9, "underlying_stop", "2026-10-07", "2026-10-07T13:36:09"),
        ("NIFTY", "LONG", 22500.0, 22460.0, "time_stop", "2026-10-07", "2026-10-07T12:00:00"),
        ("SENSEX", "SHORT", 74000.0, 74100.0, "underlying_stop", "2026-10-07", "2026-10-07T13:00:00"),
        ("NIFTY", "SHORT", 22000.0, 22040.0, "underlying_stop", "2026-10-06", "2026-10-06T13:00:00"),
    ]
    async with aiosqlite.connect(db) as conn:
        for i, (und, direction, entry, stop, reason, day, at) in enumerate(rows, 1):
            await conn.execute(
                "INSERT INTO fno_positions (id, source, tradingsymbol, token, underlying, direction, lots, lot_size, "
                "qty, entry_time, entry_date, entry_premium, entry_underlying, stop_underlying, status, exit_reason, "
                "exit_date, exit_time) VALUES (?,?,?,?,?,?,1,65,65,?,?,100,?,?,'CLOSED',?,?,?)",
                (i, "FNO_PAPER", f"S{i}", i, und, direction, at, day, entry, stop, reason, day, at))
        await conn.commit()
    levels = await fpos.stopped_entry_levels_today(db, "FNO_PAPER", "NIFTY", "2026-10-07",
                                                   REENTRY_STOP_REASONS, 0.25)
    assert levels == {"SHORT": pytest.approx(22611.1 - 0.25 * 43.8, abs=1e-3)}


@pytest.mark.asyncio
async def test_best_premium_persists_with_the_trail(tmp_path):
    db = str(tmp_path / "fno.db")
    await fpos.init_fno_positions_db(db)
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            "INSERT INTO fno_positions (id, source, tradingsymbol, token, underlying, direction, lots, lot_size, qty, "
            "entry_time, entry_date, entry_premium, entry_underlying, stop_underlying, target_underlying, premium_stop, "
            "trail_active, best_underlying, max_loss_rupees, status, bar_ts, delta_at_entry, iv_at_entry, "
            "atr_at_entry, expiry, strike, opt_type) VALUES (1,'FNO_PAPER','X',1,'NIFTY','LONG',1,65,65,"
            "'2026-10-07T11:00:00+05:30','2026-10-07',200,22600,22560,22800,150,0,22600,1000,'OPEN','b',0.5,0.15,30,"
            "'2026-10-13',22600,'CE')")
        await conn.commit()
    await fpos.update_trail(db, 1, 0, None, 22610.0, 231.5)
    await fpos.update_trail(db, 1, 0, None, 22612.0)                     # no premium this tick: kept
    (pos,) = await fpos.open_positions(db, "FNO_PAPER")
    assert pos.best_premium == 231.5 and pos.best_underlying == 22612.0


# ---------------------------------------------------------------- O8-F1 / O8-F2 (Oct 8 audit)

@pytest.mark.asyncio
async def test_best_premium_ratchet_is_monotonic_and_open_only(tmp_path):
    db = str(tmp_path / "fno.db")
    await fpos.init_fno_positions_db(db)
    await fpos.insert_position(db, **_open_row())
    await fpos.update_best_premium(db, 1, 230.0)
    await fpos.update_best_premium(db, 1, 210.0)                         # lower: ignored
    (pos,) = await fpos.open_positions(db, "FNO_PAPER")
    assert pos.best_premium == 230.0


def _open_row(**over):
    row = dict(source="FNO_PAPER", tradingsymbol="NIFTY26OCT22600CE", token=4242, underlying="NIFTY",
               expiry="2026-10-13", strike=22600.0, opt_type="CE", direction="LONG", lots=1, lot_size=65,
               qty=65, entry_time=NOW.isoformat(), entry_date="2026-10-07", entry_premium=200.0,
               entry_underlying=22600.0, delta_at_entry=0.5, iv_at_entry=0.15, atr_at_entry=30.0,
               stop_underlying=22560.0, target_underlying=22800.0, premium_stop=150.0, trail_active=0,
               trail_stop_underlying=None, best_underlying=22600.0, max_loss_rupees=3250.0, status="OPEN",
               entry_order_id="PAPER-TEST", bar_ts="2026-10-07 10:55:00")
    row.update(over)
    return row


@pytest.mark.asyncio
async def test_a_peak_seen_without_futures_survives_to_arm_the_lock(tmp_path):
    """Audit O8-F1: a new option peak on a tick with no futures quote was
    computed but never stored, so the lock could not arm from it."""
    from unittest.mock import AsyncMock, MagicMock
    from fno_executor import FnoExecutor
    from fno_orchestrator import _manage_open_positions
    db = str(tmp_path / "fno.db")
    await fpos.init_fno_positions_db(db)
    await fpos.insert_position(db, **_open_row())
    kite = MagicMock()
    kite.get_quote = AsyncMock(return_value={4242: {"last_price": 230.0, "depth": {"buy": [{"price": 230.0}]}}})
    executor = FnoExecutor(kite, paper_mode=True, source_tag="FNO_PAPER")
    closed = await _manage_open_positions(kite, db, "FNO_PAPER", executor, NOW, fut_price=None)
    assert closed == []
    (pos,) = await fpos.open_positions(db, "FNO_PAPER")
    assert pos.best_premium == 230.0                                     # kept without futures
    # The next sample is judged against that stored peak: floor = 215.
    decision = evaluate_single_leg_exit(pos, now_ist=NOW, fut_price=None, exit_px_basis=212.0,
                                        hard_flat=False, params=LOCK)
    assert decision.exit_reason == "profit_lock" and decision.profit_lock_floor == pytest.approx(215.0)


def _time_stop_case(direction, entry_u, stop_u, fut):
    params = {**LOCK, "FNO_PROFIT_LOCK_ENABLED": False}
    pos = SimpleNamespace(direction=direction, entry_underlying=entry_u, stop_underlying=stop_u,
                          target_underlying=entry_u + (200 if direction == "LONG" else -200),
                          atr_at_entry=30.0, entry_premium=200.0, premium_stop=150.0,
                          entry_time=(NOW.replace(hour=9, minute=55)).isoformat(), trail_active=0,
                          trail_stop_underlying=None, best_underlying=entry_u, best_premium=None)
    return pos, params


@pytest.mark.parametrize("direction,entry_u,stop_u,fut", [
    ("LONG", 22600.0, 22560.0, 22601.0),     # bought call, little underlying progress
    ("SHORT", 22600.0, 22640.0, 22599.0),    # bought put, little underlying progress
])
def test_time_stop_defers_only_a_profitable_bought_option_either_side(direction, entry_u, stop_u, fut):
    """Audit O8-F2: both sides BUY the option, so a premium above entry is a
    profit for a put exactly as for a call."""
    pos, params = _time_stop_case(direction, entry_u, stop_u, fut)
    winning = evaluate_single_leg_exit(pos, now_ist=NOW, fut_price=fut, exit_px_basis=220.0,
                                       hard_flat=False, params=params)
    assert winning.exit_reason == "" and winning.time_stop_deferred["premium_pnl_per_unit"] == pytest.approx(20.0)
    losing = evaluate_single_leg_exit(pos, now_ist=NOW, fut_price=fut, exit_px_basis=180.0,
                                      hard_flat=False, params=params)
    assert losing.exit_reason == "time_stop" and losing.time_stop_deferred is None


def test_live_default_banks_a_small_profit_at_the_time_stop():
    """With the sign corrected, deferring in profit replayed -Rs 5,267 against
    +Rs 6,968 for banking (docs/research/fno/2026-10-08-time-stop-sign)."""
    from config import settings
    from fno_exit_rules import live_single_leg_exit_params
    params = live_single_leg_exit_params(settings)
    assert params["FNO_TIME_STOP_RESPECTS_PREMIUM"] is False
    pos, _ = _time_stop_case("SHORT", 22600.0, 22640.0, 22599.0)
    decision = evaluate_single_leg_exit(pos, now_ist=NOW, fut_price=22599.0, exit_px_basis=215.0,
                                        hard_flat=False, params=params)
    assert decision.exit_reason == "time_stop" and decision.time_stop_deferred is None
