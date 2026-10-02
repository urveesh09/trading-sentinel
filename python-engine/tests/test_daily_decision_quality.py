import asyncio
import sqlite3
import pytest

import daily_decision_quality as quality

from daily_decision_quality import build_daily_decision_quality_report


def test_daily_report_keeps_shadow_rejections_and_has_no_automatic_selection(tmp_path):
    path = str(tmp_path / "quality.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE momentum_shadow_evaluations (trading_date TEXT,ticker TEXT,bar_ts TEXT,variant TEXT,accepted INTEGER,reject_reason TEXT)")
    con.executemany("INSERT INTO momentum_shadow_evaluations VALUES (?,?,?,?,?,?)", [
        ("2026-10-02", "ACME", "2026-10-02T10:00:00+05:30", "MOM_BASE", 1, None),
        ("2026-10-02", "BETA", "2026-10-02T10:00:00+05:30", "MOM_BASE", 0, "MC3_volume"),
    ])
    con.commit(); con.close()
    report = asyncio.run(build_daily_decision_quality_report(path, "2026-10-02"))
    shadow = next(row for row in report["books"] if row["book"] == "MOMENTUM_SHADOW")
    assert shadow["opportunity_count"] == 2 and shadow["opened_count"] == 1
    assert shadow["rejected_or_not_selected"] == [{"ticker": "BETA", "policy": "MOM_BASE", "reason": "MC3_volume"}]
    assert report["selection"] == {"state": "HUMAN_REVIEW_REQUIRED", "automatic_change": "NONE", "reason": "Daily facts do not authorize retuning, capital changes, or qualification."}


def test_missing_database_stays_missing_and_rejections_have_an_explicit_unknown(tmp_path):
    missing = str(tmp_path / "missing.db")
    report = asyncio.run(build_daily_decision_quality_report(missing, "2026-10-02"))
    assert not __import__("pathlib").Path(missing).exists()
    assert report["rejected_hypotheses"] == [{"state": "NO_REJECTED_HYPOTHESIS_RECORDED"}]


def test_cash_drawdown_uses_event_order_not_admission_order():
    result = quality._cash_summary([
        {"event_type": "TRADE_PARTIAL", "timestamp": "2026-10-02T10:00:00+05:30", "pnl": 100},
        {"event_type": "TRADE_CLOSED", "timestamp": "2026-10-02T12:00:00+05:30", "pnl": 100},
        {"event_type": "TRADE_CLOSED", "timestamp": "2026-10-02T05:30:00Z", "pnl": -150},
    ])
    assert result["net_cash"] == 50
    assert result["daily_cash_drawdown"] == 150
    assert result["version_specific_cash_drawdown"] is None


@pytest.mark.parametrize("clock", ["2026-10-02T10:00:00+05:30", "2026-10-02T04:30:00Z", "2026-10-02T04:30:00"])
def test_cash_from_earlier_admission_is_counted_on_exit_day(monkeypatch, clock):
    monkeypatch.setattr(quality, "build_momentum_paper_decision_audit", lambda *_args: {
        "status": "COMPLETE", "cash_truth": "bankroll_ledger", "opportunities": [{
            "admission_key": "older", "recorded_at": "2026-10-01T10:00:00+05:30",
            "outcome": "opened", "cash": {"events": [
                {"event_type": "TRADE_CLOSED", "timestamp": clock, "pnl": -75},
            ]},
        }],
    })
    row = quality._momentum_book("unused.db", quality._day("2026-10-02"))
    assert row["opportunity_count"] == 0
    assert row["cash"]["net_cash"] == -75
    assert row["cash"]["daily_cash_drawdown"] == 75


def test_equal_clock_cash_does_not_invent_order_or_version_drawdown():
    result = quality._cash_summary([
        {"event_type": "TRADE_CLOSED", "timestamp": "2026-10-02T10:00:00+05:30", "pnl": 100},
        {"event_type": "TRADE_CLOSED", "timestamp": "2026-10-02T04:30:00Z", "pnl": -150},
    ])
    assert result["net_cash"] == -50
    assert result["daily_cash_drawdown"] is None
    assert result["cash_ordering"] == "UNAVAILABLE_CLOCK_ORDER"
