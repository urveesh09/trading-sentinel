"""[O25] The pre-registered five-session proving week of the paper F&O single-leg book."""
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
import pytz

import fno_proving_week as week
import fno_positions as fpos
import fno_shared_risk
from config import settings
from fno_costs import calc_fno_costs

IST = pytz.timezone("Asia/Kolkata")
FRIDAY_CLOSE = IST.localize(datetime(2026, 10, 30, 15, 50))


@pytest.fixture
def halt(monkeypatch):
    """The paper book's drawdown-halt read, as the shared policy reports it (set by the test)."""
    state = {"available": True, "halts": ()}

    async def policy(db_path, *, source, pool_rs, today_ist, policy):
        return SimpleNamespace(active_halts=state["halts"], view=SimpleNamespace(available=state["available"]))

    monkeypatch.setattr(fno_shared_risk, "shared_fno_entry_policy", policy)
    return state


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch, halt):
    monkeypatch.setattr(settings, "FNO_PROVING_START", "2026-10-26")
    monkeypatch.setattr(settings, "FNO_PROVING_SESSIONS", 5)
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_CAPITAL", 12500.0)
    path = str(tmp_path / "week.db")
    await fpos.init_fno_positions_db(path)
    return path


async def _trade(db, day: str, *, entry: float, exit_: float, lots: int = 1, exit_day=None, hhmm="10:30"):
    """One closed paper single-leg trade with its two fills (P&L as the book books it)."""
    qty = 65 * lots
    pnl = (exit_ - entry) * qty - calc_fno_costs(entry, exit_, qty, exchange="NFO")
    position_id = await fpos.insert_position(
        db, source="FNO_PAPER", tradingsymbol=f"NIFTY{day[-2:]}{hhmm[:2]}CE", token=1, underlying="NIFTY",
        expiry="2026-11-03", strike=25000.0, opt_type="CE", direction="LONG", lots=lots, lot_size=65,
        qty=qty, entry_time=f"{day}T{hhmm}:00+05:30", entry_date=day, entry_premium=entry,
        entry_underlying=25000.0, delta_at_entry=0.55, iv_at_entry=0.12, atr_at_entry=40.0,
        stop_underlying=24950.0, target_underlying=25100.0, premium_stop=0.75 * entry,
        max_loss_rupees=entry * qty, bar_ts=f"{day} {hhmm}:00",
    )
    import aiosqlite
    async with aiosqlite.connect(db) as conn:
        await conn.execute("UPDATE fno_positions SET status='CLOSED', exit_date=?, exit_time=?, pnl=?, "
                           "exit_premium=?, exit_reason='trail_stop' WHERE id=?",
                           (exit_day or day, f"{exit_day or day}T13:00:00+05:30", pnl, exit_, position_id))
        await conn.commit()
    return pnl


def _one_lot(entry, exit_):
    return round((exit_ - entry) * 65 - calc_fno_costs(entry, exit_, 65, exchange="NFO"), 2)


def test_the_window_is_the_first_five_sessions_from_monday(db):
    assert [d.isoformat() for d in week.window_days(db)] == [
        "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"]


@pytest.mark.asyncio
async def test_a_week_that_traded_cleanly_and_did_not_lose_is_proved(db):
    await _trade(db, "2026-10-26", entry=120.0, exit_=90.0)
    actual = await _trade(db, "2026-10-28", entry=100.0, exit_=150.0, lots=2)
    await _trade(db, "2026-10-21", entry=120.0, exit_=10.0)                       # before the window
    result = await week.score(db, FRIDAY_CLOSE)
    expected = round(_one_lot(120.0, 90.0) + _one_lot(100.0, 150.0), 2)
    assert (result["verdict"], result["closed"], result["one_lot_net"]) == ("PROVED", 2, expected)
    assert result["actual_net"] == pytest.approx(round(_one_lot(120.0, 90.0) + actual, 2), abs=0.02)
    text = week.render(result, FRIDAY_CLOSE.date())
    assert text.startswith("📋 F&O proving week, day 5 of 5 (Fri 30 Oct)\nToday: no paper trade.")
    assert "✅ PROVED: it traded, did not lose at one lot, and nothing broke." in text
    assert f"₹12,500 at one lot would have taken 2 of them (skipped 0): ₹{12500 + expected:,.0f}." in text


@pytest.mark.asyncio
async def test_one_lot_pays_its_own_fixed_charges(db):
    """The review's case: a two-lot trade a little in profit is a loss at one lot."""
    two_lot = await _trade(db, "2026-10-27", entry=100.0, exit_=100.4, lots=2)
    result = await week.score(db, FRIDAY_CLOSE)
    assert two_lot / 2 > result["one_lot_net"] == _one_lot(100.0, 100.4)
    assert result["one_lot_net"] < 0 and result["verdict"] == "NOT_PROVED"


@pytest.mark.asyncio
async def test_an_unreadable_drawdown_halt_is_never_a_pass(db, halt):
    await _trade(db, "2026-10-27", entry=100.0, exit_=140.0)
    halt["available"] = False
    result = await week.score(db, FRIDAY_CLOSE)
    assert result["verdict"] == "UNAVAILABLE" and result["one_lot_net"] > 0
    assert "⚠️ UNAVAILABLE: the drawdown-halt state could not be read" in week.render(result, FRIDAY_CLOSE.date())
    halt.update(available=True, halts=("drawdown_halt equity=211000",))
    assert (await week.score(db, FRIDAY_CLOSE))["verdict"] == "NOT_PROVED"


@pytest.mark.asyncio
async def test_a_losing_week_an_unclean_week_and_an_empty_week(db, tmp_path):
    await _trade(db, "2026-10-27", entry=100.0, exit_=95.0)
    assert (await week.score(db, FRIDAY_CLOSE))["verdict"] == "NOT_PROVED"
    await _trade(db, "2026-10-29", entry=100.0, exit_=160.0, exit_day="2026-10-30")   # carried overnight
    result = await week.score(db, FRIDAY_CLOSE)
    assert result["verdict"] == "NOT_PROVED" and result["one_lot_net"] > 0
    assert "closed on 2026-10-30, not its entry day" in week.render(result, FRIDAY_CLOSE.date())
    empty = str(tmp_path / "empty.db")
    await fpos.init_fno_positions_db(empty)
    assert (await week.score(empty, FRIDAY_CLOSE))["verdict"] == "NO_EVIDENCE"


@pytest.mark.asyncio
async def test_mid_week_the_message_says_where_it_stands(db):
    await _trade(db, "2026-10-27", entry=100.0, exit_=120.0)
    tuesday = IST.localize(datetime(2026, 10, 27, 15, 50))
    result = await week.score(db, tuesday)
    assert result["verdict"] == "IN_PROGRESS" and result["sessions_done"] == 2
    text = week.render(result, tuesday.date())
    one_lot = _one_lot(100.0, 120.0)
    assert "day 2 of 5 (Tue 27 Oct)" in text and f"Today: NIFTY2710CE +₹{one_lot:,.0f} a lot (trail_stop)." in text
    assert text.endswith("Verdict after the close on Fri 30 Oct.")


def test_twelve_and_a_half_thousand_takes_one_lot_it_can_pay_for_one_at_a_time():
    trades = [
        {"entry_time": "2026-10-26T10:00", "exit_time": "2026-10-26T11:00", "entry_premium": 150.0, "lot_size": 65,
         "pnl": -1500.0, "one_lot": -1500.0},
        {"entry_time": "2026-10-26T10:30", "exit_time": "2026-10-26T12:00", "entry_premium": 100.0, "lot_size": 65,
         "pnl": 900.0, "one_lot": 900.0},                                   # overlaps the first: skipped
        {"entry_time": "2026-10-27T10:00", "exit_time": "2026-10-27T11:00", "entry_premium": 200.0, "lot_size": 65,
         "pnl": 4000.0, "one_lot": 4000.0},                                 # ₹13,000 a lot: too dear
        {"entry_time": "2026-10-28T10:00", "exit_time": "2026-10-28T11:00", "entry_premium": 120.0, "lot_size": 65,
         "pnl": 2000.0, "one_lot": 2000.0},
    ]
    assert week.replay_small_account(trades, 12500.0) == {"taken": 2, "skipped": 2, "end_cash": 13000.0}


@pytest.mark.asyncio
async def test_the_evening_message_goes_once_a_day(db):
    await _trade(db, "2026-10-26", entry=100.0, exit_=115.0)
    sent = []

    async def notify(text, *, event):
        sent.append(event)
        return True

    monday_close = IST.localize(datetime(2026, 10, 26, 15, 50))
    before_close = IST.localize(datetime(2026, 10, 26, 15, 0))
    assert await week.evening_report(db, before_close, notify=notify) is None       # the day is not done
    text = await week.evening_report(db, monday_close, notify=notify)
    assert text.startswith("📋 F&O proving week, day 1 of 5") and sent == ["fno_evening_report"]
    assert await week.evening_report(db, monday_close, notify=notify) is None and len(sent) == 1
    saturday = IST.localize(datetime(2026, 10, 31, 15, 50))
    assert await week.evening_report(db, saturday, notify=notify) is None            # outside the window
