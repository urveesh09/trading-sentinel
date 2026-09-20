import os
from datetime import date, datetime, timedelta, timezone

import pytest

from hedge_readiness import (
    PHASE3_KINDS, assess_phase_readiness, inspect_earnings_calendar,
    record_gate_evidence, record_shadow_staging_day,
)


NOW = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)


def test_earnings_calendar_readiness_is_strict_and_auditable(tmp_path):
    missing = inspect_earnings_calendar(str(tmp_path / "missing.csv"), now=NOW)
    assert missing["status"] == "BLOCKED"
    assert "missing" in " ".join(missing["blockers"])

    calendar = tmp_path / "events.csv"
    calendar.write_text("ticker,event_date,event_type\nRELIANCE,2026-09-10,RESULTS\n", encoding="utf-8")
    os.utime(calendar, (NOW.timestamp(), NOW.timestamp()))
    ready = inspect_earnings_calendar(str(calendar), now=NOW)
    assert ready["status"] == "READY"
    assert ready["next_earnings"]["underlying"] == "RELIANCE"


@pytest.mark.asyncio
async def test_phase3_readiness_requires_real_staging_and_five_samples_per_kind(db_path):
    for offset in range(7):
        day = NOW.date() - timedelta(days=offset)
        await record_gate_evidence(
            db_path, evidence_type="phase3_staging_day", phase="phase3",
            observed_on=day, observed_at=NOW, source="staging-log-audit",
        )
    await record_gate_evidence(
        db_path, evidence_type="phase3_live_chain_verification", phase="phase3",
        observed_on=NOW.date(), observed_at=NOW, source="manual-chain-check",
    )
    blocked = await assess_phase_readiness(db_path, "phase3", now=NOW)
    assert blocked["state"] == "BLOCKED"
    assert any(item["gate"] == "sample_review" for item in blocked["blockers"])

    for kind in PHASE3_KINDS:
        for offset in range(5):
            await record_gate_evidence(
                db_path, evidence_type="phase3_sample_review", phase="phase3",
                kind=kind, observed_on=NOW.date(),
                observed_at=NOW, source="telegram-review",
                evidence_ref=f"{kind}-sample-{offset + 1}",
            )
    ready = await assess_phase_readiness(db_path, "phase3", now=NOW)
    assert ready["state"] == "READY"
    assert ready["can_enable"] is True
    assert all(value == 5 for value in ready["sample_review_counts"].values())


@pytest.mark.asyncio
async def test_gate_evidence_rejects_future_or_cross_phase_claims(db_path):
    with pytest.raises(ValueError, match="future"):
        await record_gate_evidence(
            db_path, evidence_type="phase2_staging_day", phase="phase2",
            observed_on=NOW.date() + timedelta(days=1), observed_at=NOW,
            source="invalid",
        )
    with pytest.raises(ValueError, match="do not match"):
        await record_gate_evidence(
            db_path, evidence_type="phase3_staging_day", phase="phase2",
            observed_on=NOW.date(), observed_at=NOW, source="invalid",
        )
    with pytest.raises(ValueError, match="evidence_ref"):
        await record_gate_evidence(
            db_path, evidence_type="phase3_sample_review", phase="phase3",
            kind=next(iter(PHASE3_KINDS)), observed_on=NOW.date(),
            observed_at=NOW, source="invalid",
        )


@pytest.mark.asyncio
async def test_shadow_staging_day_requires_real_processed_input_and_deduplicates(db_path):
    assert await record_shadow_staging_day(
        db_path,
        phase="phase3",
        observed_at=NOW,
        processed_underlyings=0,
        emitted_candidates=0,
    ) is None
    empty = await assess_phase_readiness(db_path, "phase3", now=NOW)
    assert empty["staging_days"] == []

    first = await record_shadow_staging_day(
        db_path,
        phase="phase3",
        observed_at=NOW,
        processed_underlyings=2,
        emitted_candidates=0,
    )
    second = await record_shadow_staging_day(
        db_path,
        phase="phase3",
        observed_at=NOW + timedelta(minutes=30),
        processed_underlyings=2,
        emitted_candidates=3,
    )
    report = await assess_phase_readiness(db_path, "phase3", now=NOW)

    assert first["source"] == "system:advanced-hedge-shadow"
    assert second["observed_on"] == first["observed_on"]
    assert report["staging_days"] == [NOW.astimezone().date().isoformat()]
    assert report["evidence_rows"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("processed_underlyings", -1),
    ("processed_underlyings", 1.5),
    ("emitted_candidates", -1),
    ("emitted_candidates", True),
])
async def test_shadow_staging_day_rejects_invalid_counters(db_path, field, value):
    kwargs = {
        "phase": "phase2",
        "observed_at": NOW,
        "processed_underlyings": 1,
        "emitted_candidates": 0,
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match="non-negative integer"):
        await record_shadow_staging_day(db_path, **kwargs)
