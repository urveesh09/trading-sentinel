"""C3: the classic Penny daily kill switch is fed from the durable ledger."""
from datetime import datetime, timezone
from types import SimpleNamespace

import aiosqlite
import pytest
import pytz

import main
from config import settings
from penny_risk import PennyRiskEngine
from performance import init_ledger

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 10, 7, 11, 0))


async def _ledger(path, rows):
    await init_ledger(path)
    async with aiosqlite.connect(path) as db:
        await db.executemany(
            "INSERT INTO bankroll_ledger (timestamp, event_type, ticker, pnl, bankroll_before, bankroll_after, source) "
            "VALUES (?,?,?,?,0,0,?)", rows)
        await db.commit()


def _utc(hh, mm, day=7):
    return IST.localize(datetime(2026, 10, day, hh, mm)).astimezone(timezone.utc).isoformat()


def _scanner(paper=True, bankroll=1000.0):
    return SimpleNamespace(paper_mode=paper, risk_engine=PennyRiskEngine(bankroll=bankroll))


@pytest.mark.asyncio
async def test_today_settled_paper_legs_trip_the_kill_switch(tmp_path, monkeypatch):
    db = str(tmp_path / "ledger.db")
    monkeypatch.setattr(settings, "DB_PATH", db)
    monkeypatch.setattr(settings, "PENNY_DAILY_KILL_SWITCH_PCT", 0.20)
    await _ledger(db, [
        (_utc(10, 40), "TRADE_PARTIAL", "AAA", -50.0, "PENNY_PAPER"),
        (_utc(10, 55), "TRADE_CLOSED", "AAA", -120.0, "PENNY_PAPER"),
        (_utc(0, 10), "TRADE_CLOSED", "BBB", -40.0, "PENNY_PAPER"),        # 00:10 IST today counts
        (_utc(23, 50, day=6), "TRADE_CLOSED", "OLD", -900.0, "PENNY_PAPER"),  # yesterday IST
        (_utc(10, 41), "TRADE_CLOSED", "LIVE", -900.0, "PENNY"),            # other book
        (_utc(10, 42), "TRADE_CLOSED", "MOM", -900.0, "MOMENTUM_PAPER"),
        (_utc(10, 43), "DEPOSIT", None, 5000.0, "PENNY_PAPER"),
    ])
    scanner = _scanner()
    assert await main.sync_penny_daily_brake(scanner, NOW) == pytest.approx(-210.0)
    assert scanner.risk_engine.daily_pnl_date == "2026-10-07"
    assert scanner.risk_engine.kill_switch_active(as_of=NOW) is True        # -210 <= -200


@pytest.mark.asyncio
async def test_a_restarted_engine_rebuilds_the_same_brake(tmp_path, monkeypatch):
    db = str(tmp_path / "ledger.db")
    monkeypatch.setattr(settings, "DB_PATH", db)
    await _ledger(db, [(_utc(10, 55), "TRADE_CLOSED", "AAA", -30.0, "PENNY_PAPER")])
    first, restarted = _scanner(), _scanner()
    await main.sync_penny_daily_brake(first, NOW)
    await main.sync_penny_daily_brake(restarted, NOW)
    assert first.risk_engine.daily_pnl == restarted.risk_engine.daily_pnl == pytest.approx(-30.0)
    assert restarted.risk_engine.kill_switch_active(as_of=NOW) is False


@pytest.mark.asyncio
async def test_unreadable_ledger_blocks_live_and_keeps_paper_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "missing-dir" / "ledger.db"))
    live, paper = _scanner(paper=False), _scanner()
    paper.risk_engine.daily_pnl, paper.risk_engine.daily_pnl_date = -5.0, "2026-10-07"
    await main.sync_penny_daily_brake(live, NOW)
    await main.sync_penny_daily_brake(paper, NOW)
    assert live.risk_engine.kill_switch_active(as_of=NOW) is True
    assert paper.risk_engine.daily_pnl == -5.0
