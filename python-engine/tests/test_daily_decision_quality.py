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
    # Two ticker/bar opportunities; one accepted shadow evaluation is not a position.
    assert shadow["opportunity_count"] == 2 and shadow["accepted_evaluations"] == 1
    assert shadow["variant_evaluations"] == 2 and shadow["opened_count"] is None
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


# [S8 R5 2026-10-02] Learning-report contracts.
def test_equal_clocks_are_ordered_by_ledger_row_identity():
    result = quality._cash_summary([
        {"event_type": "TRADE_CLOSED", "timestamp": "2026-10-02T10:00:00+05:30", "pnl": -50, "ledger_rowid": 8},
        {"event_type": "TRADE_CLOSED", "timestamp": "2026-10-02T10:00:00+05:30", "pnl": 100, "ledger_rowid": 7},
    ])
    assert result["cash_ordering"] == "CHRONOLOGICAL_LEDGER_ROWID_TIEBREAK"
    assert result["daily_cash_drawdown"] == 50


def test_absent_book_is_unavailable_and_variants_are_not_extra_opportunities(tmp_path):
    report = asyncio.run(build_daily_decision_quality_report(str(tmp_path / "none.db"), "2026-10-02"))
    absent = next(row for row in report["books"] if row["book"] == "PENNY_SHADOW")
    assert absent["opportunity_count"] is None and absent["source_lineage"]["status"] == "UNAVAILABLE"
    path = str(tmp_path / "shadow.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE momentum_shadow_evaluations (trading_date TEXT,ticker TEXT,bar_ts TEXT,variant TEXT,accepted INTEGER,reject_reason TEXT)")
    con.executemany("INSERT INTO momentum_shadow_evaluations VALUES (?,?,?,?,?,?)", [
        ("2026-10-02", "ACME", "t1", "MOM_BASE", 1, None), ("2026-10-02", "ACME", "t1", "MOM_TIGHT", 0, "rvol"),
        ("2026-10-02", "ACME", "t1", "MOM_WIDE", 1, None)])
    con.commit(); con.close()
    shadow = next(row for row in asyncio.run(build_daily_decision_quality_report(path, "2026-10-02"))["books"]
                  if row["book"] == "MOMENTUM_SHADOW")
    assert (shadow["opportunity_count"], shadow["variant_evaluations"], shadow["accepted_evaluations"]) == (1, 3, 2)


def test_trade_decomposition_lineage_missed_allocation_and_best_winner_exclusion(monkeypatch):
    def closed(key, net, regime):
        return {"admission_key": key, "ticker": key.upper(), "outcome": "opened", "recorded_at": "2026-10-02T10:00:00+05:30",
                "lifecycle": "CLOSED",
                "entry_economics": {"regime_at_entry": regime},
                "admission_economics": {"allocation_policy_version": "MOMENTUM_PAPER_FIXED_POOL_V1"},
                "source_packet": {"state": "VERIFIED_SOURCE_PACKET", "bar_ts": "2026-10-02T04:15:00+00:00",
                                  "received_at": "2026-10-02T04:31:00+00:00"},
                "position": {"entry_date": "2026-10-02T04:31:00+00:00", "exit_date": "2026-10-02T06:01:00+00:00",
                             "status": "TARGET_HIT", "r_multiple": 1.0},
                "cash": {"state": "MATCH", "net_pnl": net, "events": [
                    {"event_type": "TRADE_CLOSED", "timestamp": "2026-10-02T06:01:00+00:00", "pnl": net,
                     "ledger_rowid": hash(key) % 1000}]}}
    monkeypatch.setattr(quality, "build_momentum_paper_decision_audit", lambda *_a: {
        "status": "COMPLETE", "cash_truth": "bankroll_ledger", "opportunities": [
            closed("a", 900.0, "REGIME_1_NORMAL"), closed("b", -100.0, "REGIME_1_NORMAL"),
            closed("c", 50.0, "REGIME_2_ELEVATED"),
            {"admission_key": "d", "ticker": "D", "outcome": "zero_shares", "reason": "capital_exhausted",
             "recorded_at": "2026-10-02T10:00:00+05:30", "lifecycle": "NOT_OPENED_ZERO_SHARES", "cash": {"events": []}}]})
    book = quality._momentum_book("unused.db", quality._day("2026-10-02"))
    trade = next(t for t in book["trades"] if t["admission_key"] == "a")
    assert trade["seconds_from_signal_bar_timestamp"] == 960.0 and trade["hold_minutes"] == 90.0
    assert trade["giveback"] == "UNAVAILABLE_WITHOUT_VERIFIED_PATH"
    assert book["sensitivity"] == {"closed_trade_net_cash": 850.0, "best_winner_excluded_net_cash": -50.0}
    assert book["missed_allocation"] == {"capital_skipped_count": 1, "admission_keys": ["d"]}
    assert [(row["regime"], row["closed_trades"]) for row in book["lineage"]] == [
        ("REGIME_1_NORMAL", 2), ("REGIME_2_ELEVATED", 1)]
