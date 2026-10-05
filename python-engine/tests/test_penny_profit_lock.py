"""[PENNY-PROFIT-LOCK 2026-10-05] Classic Penny MIS paper profit protection."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from config import settings
from penny_executor import PennyExecutor
from penny_profit_lock import decide
from tests.test_penny_exit_lifecycle import _seed_position


def test_below_one_r_nothing_moves():
    d = decide(entry=100, initial_stop=95, target=110, stop=95, peak=100, ltp=104.9)
    assert (d.stop, d.peak, d.exit_reason) == (95, 104.9, None)


def test_one_r_locks_half_the_best_gain_and_only_rises():
    d = decide(entry=100, initial_stop=95, target=110, stop=95, peak=None, ltp=106)
    assert d.stop == 103.0 and d.peak == 106
    lower = decide(entry=100, initial_stop=95, target=110, stop=d.stop, peak=d.peak, ltp=104)
    assert lower.stop == 103.0 and lower.peak == 106


def test_lock_never_below_cost_breakeven():
    d = decide(entry=100, initial_stop=95, target=200, stop=95, peak=None, ltp=105,
               breakeven_per_share=3.0)
    assert d.stop == 103.0


def test_target_exits():
    assert decide(entry=100, initial_stop=95, target=110, stop=95, peak=None,
                  ltp=110).exit_reason == "target_paper"


def test_sutlejtex_oct5_path():
    """Production Oct 5: entry 37.70, stop 37.24, target 38.95; 15-min marks
    +3.4% (11:03) and +4.1% (11:18) before the 36.74 stop-out."""
    first = decide(entry=37.70, initial_stop=37.24, target=38.95, stop=37.24, peak=None, ltp=38.20)
    assert first.stop == 37.95                      # +1R reached: half of +0.50 locked
    hit = decide(entry=37.70, initial_stop=37.24, target=38.95, stop=first.stop,
                 peak=first.peak, ltp=38.98)
    assert hit.exit_reason == "target_paper"        # instead of -Rs9 at 36.74


async def _wire_paper(monkeypatch, ltp):
    import main

    position = await _seed_position(settings.DB_PATH)   # entry 100, stop 95, target 110
    kite = SimpleNamespace(place_order=AsyncMock(side_effect=AssertionError("broker called")))
    monkeypatch.setattr(main, "_penny_scanner",
                        SimpleNamespace(executor=PennyExecutor(kite, paper_mode=True),
                                        source_tag="PENNY_PAPER"))
    monkeypatch.setattr(main, "_penny_ltp", AsyncMock(side_effect=list(ltp)))
    monkeypatch.setattr(settings, "PENNY_PROFIT_LOCK_ENABLED", True)
    return main, position


async def _row():
    async with aiosqlite.connect(settings.DB_PATH) as db:
        pos = await (await db.execute(
            "SELECT trailing_stop_current,highest_close_since_entry,exit_date,realised_pnl "
            "FROM positions WHERE ticker='ABC'")).fetchone()
        notes = await (await db.execute(
            "SELECT notes FROM bankroll_ledger WHERE source='PENNY_PAPER'")).fetchall()
    return pos, [n[0] for n in notes]


@pytest.mark.asyncio
async def test_monitor_raises_then_banks_the_locked_profit(monkeypatch):
    main, _ = await _wire_paper(monkeypatch, [106.0, 102.9])
    assert (await main.run_penny_paper_stop_monitor())["stopped"] == []
    pos, _ = await _row()
    assert pos[0] == 103.0 and pos[1] == 106.0 and pos[2] is None
    assert (await main.run_penny_paper_stop_monitor())["stopped"] == ["ABC"]
    pos, notes = await _row()
    assert pos[2] and pos[3] > 0
    assert notes == ["confirmed_exit:profit_lock_paper"]


@pytest.mark.asyncio
async def test_monitor_takes_the_target(monkeypatch):
    main, _ = await _wire_paper(monkeypatch, [110.5])
    assert (await main.run_penny_paper_stop_monitor())["stopped"] == ["ABC"]
    pos, notes = await _row()
    assert pos[3] > 0 and notes == ["confirmed_exit:target_paper"]


@pytest.mark.asyncio
async def test_missing_quote_never_closes(monkeypatch):
    main, _ = await _wire_paper(monkeypatch, [0.0])
    assert (await main.run_penny_paper_stop_monitor())["stopped"] == []
    pos, notes = await _row()
    assert pos[2] is None and notes == []


@pytest.mark.asyncio
async def test_flag_off_keeps_fixed_stop(monkeypatch):
    main, _ = await _wire_paper(monkeypatch, [106.0])
    monkeypatch.setattr(settings, "PENNY_PROFIT_LOCK_ENABLED", False)
    await main.run_penny_paper_stop_monitor()
    pos, _ = await _row()
    assert pos[0] == 95.0
