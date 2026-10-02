import asyncio
import sqlite3

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
