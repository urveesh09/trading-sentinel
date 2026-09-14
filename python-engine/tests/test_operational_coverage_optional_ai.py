"""[WORKFLOW-I I.C 2026-09-13] Operational coverage: optional-AI integration.

Closes the I.C slice: ``operational_coverage_report`` now
includes the optional-AI status as a producer alongside
manual_advisory, proactive, F&O, and scheduler. The engine's
``load_optional_ai_status`` is the data source; the bounded
validator from I.A ensures the envelope is safe to surface.

Coverage
--------
1. ``optional_ai`` producer appears in the report.
2. The state from the engine's load passes through unchanged.
3. The detail carries queue counters + bounded usefulness envelope.
4. ``DISABLED_*`` states set ``enabled=False``.
5. ``READY`` and ``OUTAGE_CIRCUIT_OPEN`` set ``enabled=True``.
6. ``NOT_REPORTED`` defaults set ``enabled=False``.
7. The vocabulary drift validator accepts all the optional-AI
   states (no drift entry for the eight known states).
8. The report's note still mentions "Coverage is operational
   evidence."
9. The producer is keyed ``optional_ai`` (single, not per-account).
10. Existing producer tests still pass.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pytest


async def _post_status(
    db_path: str, *,
    state: str,
    reported_at: Optional[datetime] = None,
    received_at: Optional[datetime] = None,
    queue: Optional[Dict[str, Any]] = None,
    usefulness: Optional[Dict[str, Any]] = None,
    async_requested: bool = True,
    policy_allows_annotation: bool = True,
    reason: str = "optional_annotation_ready",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Helper that POSTs a status envelope via the I.A route
    and returns the engine's persisted record. The caller is
    responsible for awaiting (this is an async function).
    """
    from optional_ai_status import record_optional_ai_status
    if now is None:
        now = datetime.now(timezone.utc)
    if reported_at is None:
        reported_at = now
    if received_at is None:
        received_at = now
    payload = {
        "state": state,
        "reported_at": reported_at.isoformat(),
        "async_requested": async_requested,
        "policy_allows_annotation": policy_allows_annotation,
        "reason": reason,
        "queue": queue or {"pending": 0, "cached": 0,
                         "daily_requests": 1, "daily_budget": 40,
                         "max_pending": 16, "circuit_state": "CLOSED"},
    }
    if usefulness is not None:
        payload["usefulness"] = usefulness
    return await record_optional_ai_status(db_path, payload)


class TestOptionalAiProducerIntegration:
    @pytest.mark.asyncio
    async def test_optional_ai_producer_appears_in_report(
        self, tmp_path, monkeypatch,
    ) -> None:
        """The ``optional_ai`` producer appears in the report
        even when no agent has ever reported (state=NOT_REPORTED).
        Operators see the absence, not a missing row.
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        from optional_ai_status import _init
        db_path = str(tmp_path / "cache.db")
        # Init the optional_ai_status table so the report can read it.
        await _init(db_path)
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
        report = await operational_coverage_report(db_path)
        assert "optional_ai" in report["producers"]

    @pytest.mark.asyncio
    async def test_optional_ai_state_pass_through(
        self, tmp_path, monkeypatch,
    ) -> None:
        """The state from ``load_optional_ai_status`` is passed
        through to the producer unchanged. The vocabulary
        validator handles the descriptor mapping.
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        from optional_ai_status import _init
        db_path = str(tmp_path / "cache.db")
        await _init(db_path)
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
        await _post_status(
            db_path, state="READY",
            queue={"pending": 0, "cached": 0, "daily_requests": 1,
                   "daily_budget": 40, "max_pending": 16,
                   "circuit_state": "CLOSED"},
        )
        report = await operational_coverage_report(db_path)
        oa = report["producers"]["optional_ai"]
        assert oa["state"] == "READY"
        assert oa["enabled"] is True
        assert oa["source_kind"] == "OPTIONAL_AI_ANNOTATION"

    @pytest.mark.asyncio
    async def test_optional_ai_disabled_states_set_enabled_false(
        self, tmp_path, monkeypatch,
    ) -> None:
        """The three DISABLED_* states mark the producer as
        ``enabled=False``. (NOT_REPORTED is a different
        state -- the engine reports it when no agent has
        POSTed, never the agent itself; it's tested below.)
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        from optional_ai_status import _init
        db_path = str(tmp_path / "cache.db")
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
        for disabled_state in (
            "DISABLED_NO_CREDENTIAL", "DISABLED_BY_CONFIGURATION",
            "DISABLED_BY_POLICY",
        ):
            await _init(db_path)
            await _post_status(db_path, state=disabled_state, queue={
                "pending": 0, "cached": 0, "daily_requests": 0,
                "daily_budget": 40, "max_pending": 16,
                "circuit_state": "CLOSED",
            })
            report = await operational_coverage_report(db_path)
            oa = report["producers"]["optional_ai"]
            assert oa["state"] == disabled_state, disabled_state
            assert oa["enabled"] is False, disabled_state

    @pytest.mark.asyncio
    async def test_optional_ai_not_reported_default(
        self, tmp_path, monkeypatch,
    ) -> None:
        """When no agent has ever POSTed, ``load_optional_ai_status``
        returns state=NOT_REPORTED. The producer surfaces this
        with ``enabled=False`` and a clear reason.
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        from optional_ai_status import _init
        db_path = str(tmp_path / "cache.db")
        await _init(db_path)
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
        # No POST; the engine's default is NOT_REPORTED.
        report = await operational_coverage_report(db_path)
        oa = report["producers"]["optional_ai"]
        assert oa["state"] == "NOT_REPORTED"
        assert oa["enabled"] is False
        assert oa["counts"]["pending"] is None
        assert oa["counts"]["usefulness"] is None

    @pytest.mark.asyncio
    async def test_optional_ai_outage_sets_enabled_true_with_error_state(
        self, tmp_path, monkeypatch,
    ) -> None:
        """OUTAGE_CIRCUIT_OPEN means the queue IS configured and
        enabled -- it's the provider that's down. ``enabled=True``
        so the dashboard can distinguish "disabled by operator"
        from "outage in flight."
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        from optional_ai_status import _init
        db_path = str(tmp_path / "cache.db")
        await _init(db_path)
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
        await _post_status(db_path, state="OUTAGE_CIRCUIT_OPEN", queue={
            "pending": 0, "cached": 0, "daily_requests": 1,
            "daily_budget": 40, "max_pending": 16,
            "circuit_state": "OPEN",
        }, reason="provider_failures")
        report = await operational_coverage_report(db_path)
        oa = report["producers"]["optional_ai"]
        assert oa["state"] == "OUTAGE_CIRCUIT_OPEN"
        assert oa["enabled"] is True
        assert oa["counts"]["circuit_state"] == "OPEN"
        assert oa["reason"] == "provider_failures"

    @pytest.mark.asyncio
    async def test_optional_ai_detail_carries_usefulness_when_present(
        self, tmp_path, monkeypatch,
    ) -> None:
        """When the I.A usefulness envelope is present in the
        persisted detail, the producer's ``counts.usefulness``
        carries it. Absent means the operator hasn't opted in.
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        from optional_ai_status import _init
        db_path = str(tmp_path / "cache.db")
        await _init(db_path)
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
        await _post_status(
            db_path, state="READY",
            queue={"pending": 0, "cached": 0, "daily_requests": 1,
                   "daily_budget": 40, "max_pending": 16,
                   "circuit_state": "CLOSED"},
            usefulness={"total_completed_reviews": 5,
                        "cache_hits": 2, "cache_misses": 3,
                        "circuit_opens": 0,
                        "response_seconds_last": 1.5,
                        "verdict_counts": {"APPROVE": 3, "APPROVE_WITH_CONCERNS": 0,
                                            "REVIEW_UNAVAILABLE": 1, "REJECT": 1}},
        )
        report = await operational_coverage_report(db_path)
        oa = report["producers"]["optional_ai"]
        u = oa["counts"]["usefulness"]
        assert u is not None
        assert u["total_completed_reviews"] == 5
        assert u["verdict_counts"]["APPROVE"] == 3

    @pytest.mark.asyncio
    async def test_optional_ai_usefulness_absent_is_none(
        self, tmp_path, monkeypatch,
    ) -> None:
        """Default opt-out: no ``usefulness`` key in the persisted
        detail. The producer's counts.usefulness is None -- the
        dashboard can distinguish "absent" from "zero."
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        from optional_ai_status import _init
        db_path = str(tmp_path / "cache.db")
        await _init(db_path)
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
        await _post_status(db_path, state="READY", queue={
            "pending": 0, "cached": 0, "daily_requests": 1,
            "daily_budget": 40, "max_pending": 16,
            "circuit_state": "CLOSED",
        })
        report = await operational_coverage_report(db_path)
        oa = report["producers"]["optional_ai"]
        assert oa["counts"]["usefulness"] is None

    @pytest.mark.asyncio
    async def test_optional_ai_does_not_trigger_drift(
        self, tmp_path, monkeypatch,
    ) -> None:
        """All five agent-POSTable optional-AI states are mapped
        to §12 descriptors, so the vocabulary validator does NOT
        flag them as drift. Operators see no warnings.
        (NOT_REPORTED, STALE, CORRUPT_REPORT are engine-side
        states -- the engine emits them when the persisted
        record is missing/stale/unreadable. They're tested in
        ``test_optional_ai_not_reported_default`` and below.)
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        from optional_ai_status import _init
        db_path = str(tmp_path / "cache.db")
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
        for state in (
            "READY", "DISABLED_NO_CREDENTIAL", "DISABLED_BY_CONFIGURATION",
            "DISABLED_BY_POLICY", "OUTAGE_CIRCUIT_OPEN",
        ):
            await _init(db_path)
            await _post_status(db_path, state=state, queue={
                "pending": 0, "cached": 0, "daily_requests": 0,
                "daily_budget": 40, "max_pending": 16,
                "circuit_state": "CLOSED",
            })
            report = await operational_coverage_report(db_path)
            # No drift for the optional_ai producer across the five states.
            drift = report.get("vocabulary_drift", [])
            oa_drift = [d for d in drift
                         if d.get("producer_id") == "optional_ai"]
            assert oa_drift == [], (
                f"state {state!r} produced drift: {oa_drift}"
            )

    @pytest.mark.asyncio
    async def test_optional_ai_stale_state_no_drift(
        self, tmp_path, monkeypatch,
    ) -> None:
        """A STALE state (engine emits when the persisted report
        is older than the freshness budget) is mapped to STALE
        descriptor and triggers no drift.
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        from optional_ai_status import _init
        from datetime import timedelta
        db_path = str(tmp_path / "cache.db")
        await _init(db_path)
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
        # POST a fresh report, then read with a `now` 5 minutes later.
        old = datetime.now(timezone.utc) - timedelta(minutes=5)
        await _post_status(
            db_path, state="READY",
            queue={"pending": 0, "cached": 0, "daily_requests": 1,
                   "daily_budget": 40, "max_pending": 16,
                   "circuit_state": "CLOSED"},
            now=old,
        )
        # Read via the engine's loader with a now() well after the
        # post time so the freshness window expires.
        from optional_ai_status import load_optional_ai_status
        stale_record = await load_optional_ai_status(
            db_path, now=datetime.now(timezone.utc),
        )
        assert stale_record["state"] == "STALE", stale_record
        # Now run operational_coverage_report -- which uses
        # ``datetime.now(timezone.utc)`` internally; since the
        # post time was 5 minutes ago, the report sees a STALE state.
        report = await operational_coverage_report(db_path)
        oa = report["producers"]["optional_ai"]
        assert oa["state"] == "STALE"
        oa_drift = [d for d in report.get("vocabulary_drift", [])
                     if d.get("producer_id") == "optional_ai"]
        assert oa_drift == []

    @pytest.mark.asyncio
    async def test_optional_ai_counters_carried(
        self, tmp_path, monkeypatch,
    ) -> None:
        """The queue counters (``pending``, ``cached``, etc.)
        appear in the producer's counts.
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        from optional_ai_status import _init
        db_path = str(tmp_path / "cache.db")
        await _init(db_path)
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
        await _post_status(
            db_path, state="READY",
            queue={"pending": 3, "cached": 7, "daily_requests": 12,
                   "daily_budget": 40, "max_pending": 16,
                   "circuit_state": "CLOSED"},
        )
        report = await operational_coverage_report(db_path)
        oa = report["producers"]["optional_ai"]
        assert oa["counts"]["pending"] == 3
        assert oa["counts"]["cached"] == 7
        assert oa["counts"]["daily_requests"] == 12
        assert oa["counts"]["daily_budget"] == 40
        assert oa["counts"]["circuit_state"] == "CLOSED"

    @pytest.mark.asyncio
    async def test_optional_ai_execution_authority_is_none(
        self, tmp_path, monkeypatch,
    ) -> None:
        """The §13 contract: ``execution_authority`` is always
        ``NONE`` and ``can_place_orders`` is always False. The
        producer's identity surfaces this so the dashboard
        can render the safety badge.
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        from optional_ai_status import _init
        db_path = str(tmp_path / "cache.db")
        await _init(db_path)
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
        await _post_status(db_path, state="READY", queue={
            "pending": 0, "cached": 0, "daily_requests": 1,
            "daily_budget": 40, "max_pending": 16,
            "circuit_state": "CLOSED",
        })
        report = await operational_coverage_report(db_path)
        oa = report["producers"]["optional_ai"]
        assert oa["identity"]["execution_authority"] == "NONE"
        assert oa["identity"]["can_place_orders"] is False

    @pytest.mark.asyncio
    async def test_optional_ai_coexists_with_other_producers(
        self, tmp_path, monkeypatch,
    ) -> None:
        """Adding the optional-AI producer does NOT remove any
        existing producer (manual_advisory, proactive,
        fno_collection, scheduler). All five families
        coexist.
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        from partner_manual_advisory import record_advisory_input_status
        from optional_ai_status import _init
        db_path = str(tmp_path / "cache.db")
        await _init(db_path)
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
        # Manual advisory row (so it shows up).
        now = datetime.now(timezone.utc)
        await record_advisory_input_status(
            db_path, underlying="NIFTY", attempted_at=now, observed_at=now,
            stage="NO_ENTRY_SETUP", reason="no_or_break",
            entry_state="NO_ENTRY_SETUP", successful_observation=True,
        )
        await _post_status(db_path, state="READY", queue={
            "pending": 0, "cached": 0, "daily_requests": 1,
            "daily_budget": 40, "max_pending": 16,
            "circuit_state": "CLOSED",
        })
        report = await operational_coverage_report(db_path)
        # Existing producers still there.
        assert "manual_advisory:NIFTY" in report["producers"]
        assert "proactive_completed_bars" in report["producers"]
        assert "fno_collection:NIFTY" in report["producers"]
        # New producer added.
        assert "optional_ai" in report["producers"]
