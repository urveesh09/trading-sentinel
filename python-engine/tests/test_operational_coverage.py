from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_coverage_distinguishes_healthy_no_setup_from_missing_producer(tmp_path, monkeypatch):
    from config import settings
    from operational_coverage import operational_coverage_report
    from partner_manual_advisory import record_advisory_input_status

    db_path = str(tmp_path / "cache.db")
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
    now = datetime(2026, 9, 10, 5, 0, tzinfo=timezone.utc)
    await record_advisory_input_status(
        db_path, underlying="NIFTY", attempted_at=now, observed_at=now,
        stage="NO_ENTRY_SETUP", reason="no_or_break", entry_state="NO_ENTRY_SETUP",
        successful_observation=True,
    )
    report = await operational_coverage_report(db_path)
    nifty = report["producers"]["manual_advisory:NIFTY"]
    sensex = report["producers"]["manual_advisory:SENSEX"]
    assert nifty["state"] == "HEALTHY_NO_SETUP"
    assert nifty["last_success_at"] is not None
    assert sensex["state"] == "UNAVAILABLE"
    assert sensex["reason"] == "no_manual_advisory_attempt_recorded"
    assert report["producers"]["fno_collection:NIFTY"]["state"] == "NOT_YET_OBSERVED"
    assert report["producers"]["proactive_completed_bars"]["state"] == "UNCONFIGURED"
