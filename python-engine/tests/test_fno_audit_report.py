"""Regression coverage for read-only F&O decision/financial audit evidence."""
from __future__ import annotations

import sqlite3
from datetime import date

import aiosqlite
import pytest

from fno_audit_report import build_fno_daily_audit_report
from fno_signal_log import _encode_audit_list, init_fno_signal_db, log_fno_signal
from performance import init_ledger

DAY = date(2026, 9, 24)


def test_audit_lists_are_bounded_before_persistence():
    values = ["x" * 300 for _ in range(40)]

    encoded = _encode_audit_list(values)

    import json
    decoded = json.loads(encoded)
    assert len(decoded) == 32
    assert all(len(value) == 240 for value in decoded)


@pytest.mark.asyncio
async def test_report_groups_repeated_leg_rows_and_exposes_switch_evidence(db_path):
    """Three leg rows for one bar are not three independent opportunities."""
    passed = [
        "trading_day", "entry_window", "expiry_day_block", "regime_not_crisis",
        "min_oi", "min_volume", "two_sided_market", "max_spread",
        "quote_freshness", "intrinsic_floor", "quote_envelope", "iv_sanity",
        "pool_min_viable", "open_premium_cap", "concurrency", "trades_per_day",
    ]
    for leg in ("FNO_PAPER", "FNO_LIVE", "FNO_SHADOW"):
        await log_fno_signal(
            db_path, scan_id=f"scan-{leg}", leg=leg, accepted=False,
            reject_reason="kill_switches_clear", bar_ts="2026-09-24 11:35:00",
            underlying="NIFTY", direction="SHORT", passed_gates=passed,
            active_kill_switches=["daily_loss_halt pnl=-17000"],
        )

    report = await build_fno_daily_audit_report(db_path, DAY)

    evidence = report["signal_evidence"]
    assert evidence["status"] == "OK"
    assert evidence["row_count"] == 3
    assert evidence["decision_unit_count"] == 1
    assert evidence["re_evaluation_count"] == 2
    assert evidence["decision_units"][0]["evaluation_count"] == 3
    block = evidence["kill_switch_blocks"][0]
    assert block["passed_gates_status"] == "PRESENT"
    assert block["passed_gates"] == passed
    assert block["active_switches_status"] == "PRESENT"
    assert block["active_switches"] == [{
        "name": "daily_loss_halt",
        "observed": "daily_loss_halt pnl=-17000",
        "threshold_pct": 0.06,
        "condition": "IST-day realized P&L <= -threshold_pct * evaluated pool",
    }]


@pytest.mark.asyncio
async def test_report_keeps_partial_cash_and_closed_outcomes_separate(db_path):
    await init_ledger(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(
            "INSERT INTO bankroll_ledger "
            "(timestamp, event_type, ticker, pnl, bankroll_before, bankroll_after, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("2026-09-24T04:40:00+00:00", "TRADE_PARTIAL", "NIFTY1", 125.25, 0, 0, "FNO_PAPER"),
                ("2026-09-24T05:40:00+00:00", "TRADE_CLOSED", "NIFTY1", -25.25, 0, 0, "FNO_PAPER"),
                ("2026-09-24T06:40:00+00:00", "TRADE_CLOSED", "NIFTY2", 55.0, 0, 0, "FNO_LIVE"),
            ],
        )
        await db.commit()

    report = await build_fno_daily_audit_report(db_path, DAY)

    paper = report["financial"]["by_source"]["FNO_PAPER"]
    live = report["financial"]["by_source"]["FNO_LIVE"]
    assert report["financial"]["status"] == "OK"
    assert paper["mode"] == "paper"
    assert paper["partial"] == {"event_count": 1, "realised_pnl": 125.25}
    assert paper["closed"] == {"event_count": 1, "realised_pnl": -25.25}
    assert live["mode"] == "live"
    assert live["closed"] == {"event_count": 1, "realised_pnl": 55.0}
    assert paper["costs"]["status"] == "UNAVAILABLE"
    assert report["expectancy"] == {
        "status": "NOT_ASSESSED",
        "reason": "A daily realised P&L or small close count does not establish expectancy.",
        "closed_outcome_sample_size": 2,
    }


@pytest.mark.asyncio
async def test_legacy_signal_rows_are_readable_but_mark_audit_fields_unavailable(db_path):
    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE fno_signals (bar_ts TEXT, underlying TEXT, direction TEXT, "
        "leg TEXT, accepted INTEGER, reject_reason TEXT)"
    )
    con.execute(
        "INSERT INTO fno_signals VALUES (?, ?, ?, ?, ?, ?)",
        ("2026-09-24 11:35:00", "NIFTY", "SHORT", "FNO_PAPER", 0, "kill_switches_clear"),
    )
    con.commit()
    con.close()

    report = await build_fno_daily_audit_report(db_path, DAY)

    evidence = report["signal_evidence"]
    assert evidence["status"] == "OK"
    assert evidence["legacy_audit_fields"] is True
    assert evidence["kill_switch_blocks"][0]["passed_gates_status"] == "UNAVAILABLE_LEGACY_ROW"
    assert evidence["kill_switch_blocks"][0]["active_switches_status"] == "UNAVAILABLE_LEGACY_ROW"


@pytest.mark.asyncio
async def test_signal_log_migrates_audit_columns_as_text(db_path):
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE fno_signals (scan_id TEXT)")
    con.commit()
    con.close()

    await init_fno_signal_db(db_path)

    con = sqlite3.connect(db_path)
    columns = {row[1]: row[2] for row in con.execute("PRAGMA table_info(fno_signals)")}
    con.close()
    assert columns["passed_gates_json"] == "TEXT"
    assert columns["active_kill_switches_json"] == "TEXT"


@pytest.mark.asyncio
async def test_missing_database_stays_missing_and_is_reported_read_only(tmp_path):
    missing = tmp_path / "missing.db"

    report = await build_fno_daily_audit_report(str(missing), DAY)

    assert not missing.exists()
    assert report["read_only"] is True
    assert report["errors"] == ["database_unavailable_or_missing"]
