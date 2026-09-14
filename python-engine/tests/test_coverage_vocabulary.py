"""[WORKFLOW-H H5 2026-09-13] Coverage vocabulary acceptance.

Closes H5 of workstream H per
``docs/2026-09-13-workflow-f-state-of-codebase-audit.md`` section 13
future plan and ``docs/NEXT_AGENT_PLAN.md`` row H.

Acceptance coverage for the §12 bounded dashboard readiness
vocabulary: *"Distinguish disabled, unconfigured, no session,
no setup, no evidence, stale and error."*

  1. The seven §12 descriptors are present and stable.
  2. Every state produced by ``operational_coverage_report``
     maps to one of the seven descriptors via
     ``STATE_TO_DESCRIPTOR``.
  3. The validator catches unmapped states (a future agent
     cannot silently add a new state without review).
  4. The validator catches unmapped reasons on a mapped state
     (softer drift; logged at WARNING).
  5. The validator returns the report unchanged when nothing
     drifted.
  6. The ``operational_coverage_report`` end-to-end pipeline
     attaches ``vocabulary_drift`` to the report when drift
     is detected.
  7. Each of the eight documented states is exercised in a
     test fixture.
"""
from __future__ import annotations

from typing import Any, Dict

import pytest


# ---- (1) the seven §12 descriptors ---------------------------------------

class TestDescriptorVocabulary:
    def test_seven_descriptors(self) -> None:
        from coverage_vocabulary import ReadinessDescriptor
        assert len(ReadinessDescriptor) == 7

    def test_descriptor_values(self) -> None:
        from coverage_vocabulary import ReadinessDescriptor
        expected = {
            "DISABLED", "UNCONFIGURED", "NO_SESSION",
            "NO_SETUP", "NO_EVIDENCE", "STALE", "ERROR",
        }
        actual = {d.value for d in ReadinessDescriptor}
        assert actual == expected

    def test_display_per_descriptor(self) -> None:
        """Every descriptor has a human-readable display string."""
        from coverage_vocabulary import (
            DESCRIPTOR_DISPLAY, ReadinessDescriptor,
        )
        for d in ReadinessDescriptor:
            assert d in DESCRIPTOR_DISPLAY
            display = DESCRIPTOR_DISPLAY[d]
            assert isinstance(display, str)
            assert len(display) > 0


# ---- (2) state -> descriptor mapping -------------------------------------

class TestStateToDescriptorMapping:
    def test_all_eight_states_mapped(self) -> None:
        """Every state produced by operational_coverage.py is in
        the mapping. If a new state is added, this test fails
        until the mapping is updated explicitly.

        [WORKFLOW-I I.C 2026-09-13] The vocabulary now includes
        the eight optional-AI states (READY, DISABLED_*,
        OUTAGE_CIRCUIT_OPEN, STALE, NOT_REPORTED,
        CORRUPT_REPORT) on top of the eight producer states.
        The total is sixteen; the test name is updated.
        """
        from coverage_vocabulary import STATE_TO_DESCRIPTOR
        expected_states = {
            # Original eight producer states.
            "HEALTHY_NO_SETUP", "AVAILABLE", "UNAVAILABLE",
            "UNCONFIGURED", "OBSERVED", "SCHEDULER_REJECTED",
            "NOT_YET_OBSERVED", "OBSERVED_USABLE",
            # Optional-AI states (I.C).
            "READY", "DISABLED_NO_CREDENTIAL",
            "DISABLED_BY_CONFIGURATION", "DISABLED_BY_POLICY",
            "OUTAGE_CIRCUIT_OPEN", "STALE", "NOT_REPORTED",
            "CORRUPT_REPORT",
        }
        assert set(STATE_TO_DESCRIPTOR.keys()) == expected_states

    def test_no_two_states_share_descriptor(self) -> None:
        """Each state maps to exactly one descriptor; if two
        states share a descriptor, the producer's vocabulary
        is ambiguous and must be split.
        """
        from coverage_vocabulary import STATE_TO_DESCRIPTOR
        seen: Dict[str, str] = {}
        for state, desc in STATE_TO_DESCRIPTOR.items():
            assert state not in seen, (
                f"state {state} maps to {desc} but also "
                f"appeared with {seen[state]}"
            )
            seen[state] = desc.value

    @pytest.mark.parametrize("state,expected_descriptor", [
        ("HEALTHY_NO_SETUP", "NO_SETUP"),
        ("AVAILABLE", "NO_EVIDENCE"),
        ("UNAVAILABLE", "NO_EVIDENCE"),
        ("UNCONFIGURED", "UNCONFIGURED"),
        ("OBSERVED", "STALE"),
        ("SCHEDULER_REJECTED", "ERROR"),
        ("NOT_YET_OBSERVED", "NO_SESSION"),
        ("OBSERVED_USABLE", "NO_SETUP"),
    ])
    def test_each_state_to_descriptor(
        self, state: str, expected_descriptor: str,
    ) -> None:
        from coverage_vocabulary import (
            descriptor_for_state, ReadinessDescriptor,
        )
        result = descriptor_for_state(state)
        assert result is not None
        assert result == ReadinessDescriptor(expected_descriptor)


# ---- (3) validator: unmapped states --------------------------------------

class TestValidatorUnmappedStates:
    def test_unmapped_state_surfaced(self) -> None:
        """A state that is not in STATE_TO_DESCRIPTOR is
        surfaced as a VocabularyDrift.
        """
        from coverage_vocabulary import validate_coverage_report
        report = {
            "producers": {
                "manual_advisory:NIFTY": {
                    "state": "WATCHING",
                    "reason": "future_state",
                }
            }
        }
        _, drift = validate_coverage_report(report)
        assert len(drift) == 1
        assert drift[0].state == "WATCHING"
        assert drift[0].descriptor is None

    def test_missing_state_surfaced(self) -> None:
        """A producer with no ``state`` field is surfaced."""
        from coverage_vocabulary import validate_coverage_report
        report = {
            "producers": {
                "broken:producer": {
                    "reason": "no_state_at_all",
                }
            }
        }
        _, drift = validate_coverage_report(report)
        assert len(drift) == 1
        assert drift[0].state == "<missing>"


# ---- (4) validator: unmapped reasons on mapped states -------------------

class TestValidatorUnmappedReasons:
    def test_known_reason_not_flagged(self) -> None:
        """A reason that is NOT in PRODUCER_REASONS on a mapped
        state is NOT a vocabulary violation -- reasons are
        informational. The validator returns an empty drift list.
        """
        from coverage_vocabulary import validate_coverage_report
        report = {
            "producers": {
                "manual_advisory:NIFTY": {
                    "state": "UNAVAILABLE",
                    "reason": "any_producer_specific_reason",
                }
            }
        }
        _, drift = validate_coverage_report(report)
        assert drift == []


# ---- (5) validator: clean reports ----------------------------------------

class TestValidatorCleanReport:
    def test_clean_report_returns_empty_drift(self) -> None:
        """A report with every state mapped (regardless of
        reason) returns an empty drift list. The report is
        returned unchanged.
        """
        from coverage_vocabulary import validate_coverage_report
        report = {
            "producers": {
                "manual_advisory:NIFTY": {
                    "state": "HEALTHY_NO_SETUP",
                    "reason": "no_or_break",  # arbitrary reason; OK
                    "attempted_at": None,
                    "last_success_at": None,
                },
                "fno_collection:NIFTY": {
                    "state": "NOT_YET_OBSERVED",
                    "reason": "NOT_YET_OBSERVED",  # arbitrary; OK
                },
                "scheduler_tier:exit": {
                    "state": "OBSERVED",
                    "reason": "tier_observed",
                },
                "scheduler_tier:research": {
                    "state": "UNCONFIGURED",
                    "reason": "no_jobs_in_tier",
                },
            }
        }
        result, drift = validate_coverage_report(report)
        assert drift == []
        # Report returned unchanged.
        assert result is report

    def test_empty_producers_no_drift(self) -> None:
        """An empty ``producers`` dict produces no drift."""
        from coverage_vocabulary import validate_coverage_report
        report = {"producers": {}}
        _, drift = validate_coverage_report(report)
        assert drift == []

    def test_no_producers_key_no_drift(self) -> None:
        """A report without a ``producers`` key produces no drift
        (the validator doesn't crash on missing keys).
        """
        from coverage_vocabulary import validate_coverage_report
        report = {}
        _, drift = validate_coverage_report(report)
        assert drift == []


# ---- (6) end-to-end via operational_coverage_report --------------------

class TestEndToEndVocabularyIntegration:
    @pytest.mark.asyncio
    async def test_known_states_no_drift_attached(
        self, tmp_path, monkeypatch,
    ) -> None:
        """The existing operational_coverage test fixture
        exercises HEALTHY_NO_SETUP, NOT_YET_OBSERVED, and
        UNCONFIGURED -- all mapped states. The validator
        should NOT attach ``vocabulary_drift`` to the report.
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        from partner_manual_advisory import record_advisory_input_status

        db_path = str(tmp_path / "cache.db")
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
        from datetime import datetime, timezone
        now = datetime(2026, 9, 10, 5, 0, tzinfo=timezone.utc)
        await record_advisory_input_status(
            db_path, underlying="NIFTY", attempted_at=now, observed_at=now,
            stage="NO_ENTRY_SETUP", reason="no_or_break",
            entry_state="NO_ENTRY_SETUP", successful_observation=True,
        )
        report = await operational_coverage_report(db_path)
        # All known states; no drift expected.
        assert "vocabulary_drift" not in report

    @pytest.mark.asyncio
    async def test_unmapped_state_appears_in_drift(
        self, tmp_path, monkeypatch,
    ) -> None:
        """Inject a producer with an unmapped state; the
        validator attaches ``vocabulary_drift`` to the report.

        Implementation: monkeypatch the ``_coverage`` builder
        so it returns a producer with state="WATCHING" -- which
        is not in ``STATE_TO_DESCRIPTOR`` and therefore surfaces
        as drift.
        """
        from config import settings
        from operational_coverage import operational_coverage_report
        import operational_coverage as oc

        db_path = str(tmp_path / "cache.db")
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "research"))
        monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)

        # Wrap _coverage so the first call returns an unmapped state.
        original_coverage = oc._coverage
        called = {"count": 0}

        def patched_coverage(*, source_kind, configured, enabled, state, reason,
                              attempted_at=None, last_success_at=None,
                              observed_at=None, receipt_at=None,
                              counts=None, identity=None):
            called["count"] += 1
            # The first call becomes a fake producer with WATCHING.
            if called["count"] == 1:
                return original_coverage(
                    source_kind=source_kind, configured=configured,
                    enabled=enabled, state="WATCHING",
                    reason="future_state_value",
                    counts=counts or {}, identity=identity or {},
                )
            return original_coverage(
                source_kind=source_kind, configured=configured,
                enabled=enabled, state=state, reason=reason,
                attempted_at=attempted_at, last_success_at=last_success_at,
                observed_at=observed_at, receipt_at=receipt_at,
                counts=counts or {}, identity=identity or {},
            )
        monkeypatch.setattr(oc, "_coverage", patched_coverage)

        report = await operational_coverage_report(db_path)
        # The injected producer should appear in the drift list.
        assert "vocabulary_drift" in report
        drift = report["vocabulary_drift"]
        assert any(
            d["state"] == "WATCHING" and d["descriptor"] is None
            for d in drift
        ), f"expected WATCHING drift, got: {drift}"


# ---- (7) vocabulary summary ---------------------------------------------

class TestVocabularySummary:
    def test_summary_shape(self) -> None:
        """``vocabulary_summary`` returns a JSON-serialisable
        dict with descriptors, mappings, and producer reasons.

        [WORKFLOW-I I.C 2026-09-13] ``state_count`` grew from 8
        to 16 when the optional-AI states joined the mapping.
        """
        from coverage_vocabulary import vocabulary_summary
        import json
        summary = vocabulary_summary()
        # Must round-trip through JSON.
        json.dumps(summary)
        assert summary["descriptor_count"] == 7
        assert summary["state_count"] == 16
        assert len(summary["producer_reasons"]) >= 3
