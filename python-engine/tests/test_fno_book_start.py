"""[F11] The paper book's fresh Rs 2,50,000: every reader of its money starts together, and nothing is lost."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import sqlite3

import aiosqlite
import pytest
import pytest_asyncio
from pydantic import ValidationError

from config import Settings, settings
import fno_adaptive_risk as far
import fno_book_start as fbs
from fno_dr_book import init_dr_db
from fno_policy_replay import run_replay
import fno_positions as fpos
import fno_risk
import fno_shared_risk as fsr
import performance
import performance_analytics as analytics
from tests.test_fno_policy_replay import DAY, _write_dataset

START = "2026-11-03"
POOL = 250000.0
# The moment before and after midnight IST on the start date, in the ledger's UTC.
BEFORE_UTC = "2026-11-02T18:29:59+00:00"
AFTER_UTC = "2026-11-02T18:30:00+00:00"
BEFORE_IST = "2026-11-02T23:59:59+05:30"
AFTER_IST = "2026-11-03T00:00:00+05:30"
NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)
TODAY = date(2026, 11, 3)


async def _add_close(db, stamp_utc: str, stamp_ist: str, pnl: float, position_id: int, source: str = "FNO_PAPER") -> None:
    """A settled single-leg trade: its position row and its exact ledger row."""
    exit_date = stamp_ist[:10]
    await db.execute(
        "INSERT INTO fno_positions (id,source,tradingsymbol,underlying,lots,lot_size,qty,entry_time,entry_date,entry_premium,"
        "status,exit_time,exit_date,exit_premium,exit_reason,gross_pnl,costs,pnl,settlement_generation) "
        "VALUES (?,?,'NIFTY26N0323000CE','NIFTY',1,65,65,?,?,100,'CLOSED',?,?,90,'stop',?,0,?,1)",
        (position_id, source, stamp_ist, exit_date, stamp_ist, exit_date, pnl, pnl))
    await db.execute(
        "INSERT INTO bankroll_ledger (timestamp,event_type,ticker,pnl,bankroll_before,bankroll_after,notes,source,origin_ref,"
        "settlement_generation) VALUES (?, 'TRADE_CLOSED', 'NIFTY26N0323000CE', ?, 0, 0, 'test', ?, ?, 1)",
        (stamp_utc, pnl, source, f"fno_position:{position_id}"))


@pytest_asyncio.fixture
async def book(tmp_path, monkeypatch):
    """Rs -33,844 before the start, in a losing streak, and two trades after it."""
    path = str(tmp_path / "book.db")
    await performance.init_ledger(path)
    await fpos.init_fno_positions_db(path)
    await init_dr_db(path)
    await fsr.init_shared_fno_risk_db(path)
    async with aiosqlite.connect(path) as db:
        await _add_close(db, "2026-11-02T07:00:00+00:00", "2026-11-02T12:30:00+05:30", -33000.0, 1)
        for number in range(2, 8):
            await _add_close(db, BEFORE_UTC, BEFORE_IST, -140.0 - number, number)
        await db.commit()
    monkeypatch.setattr(settings, "FNO_PAPER_BANKROLL", POOL)
    monkeypatch.setattr(settings, "FNO_PAPER_BOOK_START", START)
    return path


def _old_total() -> float:
    return -33000.0 - sum(140.0 + n for n in range(2, 8))


def _policy():
    return fsr.SharedFnoRiskPolicy(daily_loss_pct=.06, weekly_loss_pct=.12, monthly_loss_pct=.2, drawdown_pct=.15,
                                   max_consecutive_losses=6)


def test_the_setting_is_the_owners_date_and_a_bad_one_stops_the_deploy():
    assert Settings.model_fields["FNO_PAPER_BOOK_START"].default == START
    with pytest.raises(ValidationError):
        Settings(FNO_PAPER_BOOK_START="3 Nov")


def test_the_start_is_midnight_ist_and_only_for_the_paper_book(monkeypatch):
    monkeypatch.setattr(settings, "FNO_PAPER_BOOK_START", START)
    assert fbs.book_start("FNO_PAPER").isoformat() == AFTER_IST
    for other in ("FNO_LIVE", "MOMENTUM", "PENNY", "EDGE_PAPER", "MOMENTUM_PAPER", "SYSTEM"):
        assert fbs.book_start(other) is None and fbs.since_sql(other) == ("", ())
        assert fbs.in_book(other, datetime(2020, 1, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(settings, "FNO_PAPER_BOOK_START", " ")
    assert fbs.book_start("FNO_PAPER") is None and fbs.since_sql("FNO_PAPER") == ("", ())


def test_the_edge_of_the_start(monkeypatch):
    monkeypatch.setattr(settings, "FNO_PAPER_BOOK_START", START)
    assert not fbs.in_book("FNO_PAPER", datetime.fromisoformat(BEFORE_UTC))
    assert fbs.in_book("FNO_PAPER", datetime.fromisoformat(AFTER_UTC))


@pytest.mark.asyncio
async def test_every_reader_of_the_money_starts_at_the_allocation(book):
    assert await performance.division_equity(book, "FNO_PAPER") == POOL
    assert await performance.fno_bankroll(book, "FNO_PAPER") == POOL
    stance = far.risk_stance(await far.read_book_closes(book, "FNO_PAPER"), allocation=POOL, now=NOW, policy=far.AdaptiveRiskPolicy())
    assert stance.multiplier == 1.0 and stance.reason == "base" and stance.drawdown_pct == 0 and stance.closed_trades == 0
    assert stance.single_leg_losses_today == 0
    view = await fsr.shared_fno_risk_view(book, source="FNO_PAPER", pool_rs=POOL, observed_at=NOW)
    assert view.available and view.equity_rs == POOL and view.realised_pnl_rs == 0
    decision = await fsr.shared_fno_entry_policy(book, source="FNO_PAPER", pool_rs=POOL, today_ist=TODAY, policy=_policy(), observed_at=NOW)
    assert decision.allowed and not decision.active_halts and decision.completed_loss_streak == 0
    assert await fno_risk.kill_switch_status(book, "FNO_PAPER", POOL, TODAY) == []


@pytest.mark.asyncio
async def test_without_the_start_the_old_book_is_exactly_back(book, monkeypatch):
    monkeypatch.setattr(settings, "FNO_PAPER_BOOK_START", "")
    assert await performance.division_equity(book, "FNO_PAPER") == pytest.approx(POOL + _old_total())
    stance = far.risk_stance(await far.read_book_closes(book, "FNO_PAPER"), allocation=POOL, now=NOW, policy=far.AdaptiveRiskPolicy())
    assert stance.multiplier == .25 and stance.closed_trades == 7
    decision = await fsr.shared_fno_entry_policy(book, source="FNO_PAPER", pool_rs=POOL, today_ist=TODAY, policy=_policy(), observed_at=NOW)
    assert any(h.startswith("consecutive_loss_pause") for h in decision.active_halts)
    assert any(h.startswith("consecutive_loss_pause") for h in await fno_risk.kill_switch_status(book, "FNO_PAPER", POOL, TODAY))


@pytest.mark.asyncio
async def test_nothing_is_deleted_and_the_whole_life_evidence_still_reads_it(book):
    async with aiosqlite.connect(book) as db:
        assert (await (await db.execute("SELECT COUNT(*), SUM(pnl) FROM bankroll_ledger WHERE source='FNO_PAPER'")).fetchone()) == (7, pytest.approx(_old_total()))
        assert (await (await db.execute("SELECT COUNT(*) FROM fno_positions")).fetchone())[0] == 7
    from analytics import promotion_report
    row = next(s for s in (await promotion_report(book))["strategies"] if s["key"] == "fno_paper")
    assert row["trades"] == 7 and row["total_pnl"] == pytest.approx(_old_total(), abs=.01)


@pytest.mark.asyncio
async def test_new_trades_count_from_the_allocation(book):
    async with aiosqlite.connect(book) as db:
        await _add_close(db, AFTER_UTC, AFTER_IST, 1000.0, 20)
        await _add_close(db, "2026-11-03T05:00:00+00:00", "2026-11-03T10:30:00+05:30", -400.0, 21)
        await db.commit()
    assert await performance.division_equity(book, "FNO_PAPER") == POOL + 600.0
    closes = await far.read_book_closes(book, "FNO_PAPER")
    assert sorted(c.pnl for c in closes) == [-400.0, 1000.0]
    decision = await fsr.shared_fno_entry_policy(book, source="FNO_PAPER", pool_rs=POOL, today_ist=TODAY, policy=_policy(), observed_at=NOW)
    assert decision.allowed and decision.day_pnl_rs == 600.0 and decision.month_pnl_rs == 600.0 and decision.view.equity_rs == POOL + 600.0


@pytest.mark.asyncio
async def test_settlement_writes_the_same_balance_sizing_reads(book):
    """A close on the fresh book must not book against the old figure."""
    before = await performance.division_equity(book, "FNO_PAPER")
    await performance.record_trade_close(book, "NIFTY", -500.0, source="FNO_PAPER", origin_ref="fno_position:30", settlement_generation=1)
    async with aiosqlite.connect(book) as db:
        row = await (await db.execute("SELECT bankroll_before, bankroll_after FROM bankroll_ledger ORDER BY id DESC LIMIT 1")).fetchone()
    assert row == (before, pytest.approx(before - 500.0))


@pytest.mark.asyncio
async def test_a_settlement_gap_before_the_start_still_fails_closed(book):
    """Old rows no longer count as money, but they are still checked: a hole in the record stops entries."""
    async with aiosqlite.connect(book) as db:
        await db.execute("DELETE FROM bankroll_ledger WHERE origin_ref='fno_position:1'")
        await db.commit()
    view = await fsr.shared_fno_risk_view(book, source="FNO_PAPER", pool_rs=POOL, observed_at=NOW)
    assert not view.available and view.reason == "missing_settlement_cash"


@pytest.mark.asyncio
async def test_a_bad_old_row_still_fails_closed(book):
    async with aiosqlite.connect(book) as db:
        await db.execute("UPDATE bankroll_ledger SET timestamp='not a time' WHERE origin_ref='fno_position:2'")
        await db.commit()
    assert (await fsr.shared_fno_risk_view(book, source="FNO_PAPER", pool_rs=POOL, observed_at=NOW)).reason == "invalid_cash_event"


@pytest.mark.asyncio
async def test_the_real_money_books_money_never_moves(book):
    async with aiosqlite.connect(book) as db:
        await _add_close(db, BEFORE_UTC, BEFORE_IST, -1000.0, 40, source="FNO_LIVE")
        await db.commit()
    assert await performance.division_equity(book, "FNO_LIVE") == pytest.approx(performance.allocation_for_source("FNO_LIVE") - 1000.0)
    closes = await far.read_book_closes(book, "FNO_LIVE")
    assert [c.pnl for c in closes] == [-1000.0]


@pytest.mark.asyncio
async def test_the_division_tables_show_the_current_book_and_still_reconcile(book):
    async with aiosqlite.connect(book) as db:
        await _add_close(db, AFTER_UTC, AFTER_IST, 1000.0, 50)
        await db.commit()
    row = next(d for d in (await performance.division_breakdown(book))["divisions"] if d["key"] == "fno_paper")
    assert row["balance"] == POOL + 1000.0 and row["realised_pnl"] == 1000.0 and row["trades"] == 1
    page = next(d for d in (await analytics.division_performance(book))["divisions"] if d["source"] == "FNO_PAPER")
    assert page["ledger"]["equity"] == POOL + 1000.0 and page["ledger"]["trade_close_count"] == 1
    assert page["positions"]["closed_count"] == 1 and page["reconciliation"]["status"] == "MATCH"
    assert any("counts from 2026-11-03" in w for w in page["warnings"])


def _replay_with_an_old_loss(tmp_path):
    data = _write_dataset(tmp_path)
    con = sqlite3.connect(data / "fno-replay.sqlite")
    con.execute("INSERT INTO fno_positions (source, status, exit_time, pnl) VALUES "
                "('FNO_PAPER', 'CLOSED', '2026-08-31T14:00:00+05:30', -22000)")
    con.commit()
    con.close()
    return data


def test_a_replay_on_or_after_the_start_opens_at_the_allocation(tmp_path, monkeypatch):
    data = _replay_with_an_old_loss(tmp_path)
    monkeypatch.setattr(settings, "FNO_PAPER_BOOK_START", DAY.isoformat())
    result = run_replay(data, start=DAY.isoformat(), end=DAY.isoformat())
    assert result["start_equity"] == float(settings.FNO_PAPER_BANKROLL)
    assert result["decisions"][0]["risk_multiplier"] == 1.0


def test_a_replay_before_the_start_keeps_the_old_book(tmp_path, monkeypatch):
    data = _replay_with_an_old_loss(tmp_path)
    monkeypatch.setattr(settings, "FNO_PAPER_BOOK_START", (DAY + timedelta(days=1)).isoformat())
    result = run_replay(data, start=DAY.isoformat(), end=DAY.isoformat())
    assert result["start_equity"] == float(settings.FNO_PAPER_BANKROLL) - 22000
    assert result["decisions"][0]["risk_multiplier"] == .25


def test_a_replay_that_crosses_the_start_resets_there(tmp_path, monkeypatch):
    data = _replay_with_an_old_loss(tmp_path)
    before = DAY - timedelta(days=3)                                            # the Friday before, an empty session
    manifest = json.loads((data / "manifest.json").read_text())
    manifest["quote_days"] = [before.isoformat(), DAY.isoformat()]
    (data / "manifest.json").write_text(json.dumps(manifest))
    (data / "quotes" / before.isoformat()).mkdir()
    monkeypatch.setattr(settings, "FNO_PAPER_BOOK_START", DAY.isoformat())
    result = run_replay(data, start=before.isoformat(), end=DAY.isoformat())
    assert result["start_equity"] == float(settings.FNO_PAPER_BANKROLL) - 22000
    assert result["notes"]["paper_book_fresh_start_crossed"] == 1
    assert result["decisions"][0]["risk_multiplier"] == 1.0
