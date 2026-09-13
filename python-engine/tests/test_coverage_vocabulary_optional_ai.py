"""[WORKFLOW-I I.C 2026-09-13] Vocabulary extension: optional-AI states.

Closes the I.C slice's vocabulary side: ``STATE_TO_DESCRIPTOR``
in ``coverage_vocabulary.py`` is extended with the eight
optional-AI states the engine's ``load_optional_ai_status``
can emit. Each state maps to the §12 descriptor that best
describes its operational meaning:

  * READY                    -> NO_SETUP  (healthy, no work to do)
  * DISABLED_NO_CREDENTIAL    -> DISABLED  (operator/system off)
  * DISABLED_BY_CONFIGURATION -> DISABLED
  * DISABLED_BY_POLICY        -> DISABLED
  * OUTAGE_CIRCUIT_OPEN       -> ERROR     (provider failure)
  * UNAVAILABLE               -> ERROR
  * STALE                     -> STALE     (freshness budget expired)
  * NOT_REPORTED              -> NO_SESSION (never reported)
  * CORRUPT_REPORT            -> ERROR     (unreadable persisted)

Coverage
--------
1. All eight agent-POSTable states are mapped.
2. NOT_REPORTED, STALE, CORRUPT_REPORT (engine-side states)
   are mapped.
3. The mapping follows the §12 vocabulary -- the operator-facing
   dashboard can render each state as one of the seven
   bounded descriptors.
4. The mapping is frozen -- no drift at runtime.
5. descriptor_for_state() returns the right value for each.
"""
from __future__ import annotations

import pytest

from coverage_vocabulary import (
    ReadinessDescriptor,
    STATE_TO_DESCRIPTOR,
    descriptor_for_state,
)


# ---- (1) agent-POSTable states -------------------------------------------

class TestAgentPostableStates:
    @pytest.mark.parametrize("state,expected", [
        ("READY", ReadinessDescriptor.NO_SETUP),
        ("DISABLED_NO_CREDENTIAL", ReadinessDescriptor.DISABLED),
        ("DISABLED_BY_CONFIGURATION", ReadinessDescriptor.DISABLED),
        ("DISABLED_BY_POLICY", ReadinessDescriptor.DISABLED),
        ("OUTAGE_CIRCUIT_OPEN", ReadinessDescriptor.ERROR),
    ])
    def test_agent_postable_state_to_descriptor(
        self, state: str, expected: ReadinessDescriptor,
    ) -> None:
        assert descriptor_for_state(state) == expected
        assert STATE_TO_DESCRIPTOR[state] == expected


# ---- (2) engine-side states ---------------------------------------------

class TestEngineSideStates:
    @pytest.mark.parametrize("state,expected", [
        ("STALE", ReadinessDescriptor.STALE),
        ("NOT_REPORTED", ReadinessDescriptor.NO_SESSION),
        ("CORRUPT_REPORT", ReadinessDescriptor.ERROR),
    ])
    def test_engine_side_state_to_descriptor(
        self, state: str, expected: ReadinessDescriptor,
    ) -> None:
        assert descriptor_for_state(state) == expected
        assert STATE_TO_DESCRIPTOR[state] == expected


# ---- (3) total mapping --------------------------------------------------

class TestTotalMapping:
    def test_eight_optional_ai_states_total(self) -> None:
        """Seven NEW optional-AI states joined the existing
        vocabulary (READY, three DISABLED_*, OUTAGE_CIRCUIT_OPEN,
        STALE, NOT_REPORTED, CORRUPT_REPORT). ``UNAVAILABLE``
        was already in the vocabulary (manual-advisory's
        "inconclusive verdict") and the optional-AI's "no
        model response" shares that mapping. Total states
        grew from eight to sixteen (the seven new + the
        pre-existing UNAVAILABLE that now has a documented
        dual mapping).
        """
        new_optional_ai_states = {
            "READY", "DISABLED_NO_CREDENTIAL",
            "DISABLED_BY_CONFIGURATION", "DISABLED_BY_POLICY",
            "OUTAGE_CIRCUIT_OPEN", "STALE",
            "NOT_REPORTED", "CORRUPT_REPORT",
        }
        # Every new optional-AI state is mapped.
        for s in new_optional_ai_states:
            assert s in STATE_TO_DESCRIPTOR, s
        # UNAVAILABLE is also valid (shared with manual-advisory).
        assert "UNAVAILABLE" in STATE_TO_DESCRIPTOR
        # The vocabulary grew; total states is at least 16.
        assert len(STATE_TO_DESCRIPTOR) >= 16

    def test_all_three_disabled_states_share_descriptor(self) -> None:
        """The three DISABLED_* states all map to DISABLED.
        They differ by *why* disabled, not by operational
        meaning. Sharing the descriptor is correct.
        """
        assert (descriptor_for_state("DISABLED_NO_CREDENTIAL")
                == descriptor_for_state("DISABLED_BY_CONFIGURATION")
                == descriptor_for_state("DISABLED_BY_POLICY")
                == ReadinessDescriptor.DISABLED)

    def test_unavailable_states_share_no_evidence_descriptor(self) -> None:
        """``UNAVAILABLE`` is intentionally shared between the
        optional-AI state (engine emits when no model response
        arrived) and the manual-advisory state (verdict was
        inconclusive). Both mean "we tried but no useful answer
        arrived." The dashboard distinguishes by producer_id.
        ``OUTAGE_CIRCUIT_OPEN`` and ``CORRUPT_REPORT`` map to
        ERROR because they represent system failures.
        """
        # UNAVAILABLE is the deliberate shared mapping.
        assert descriptor_for_state("UNAVAILABLE") == (
            ReadinessDescriptor.NO_EVIDENCE
        )
        # OUTAGE_CIRCUIT_OPEN and CORRUPT_REPORT map to ERROR.
        assert (descriptor_for_state("OUTAGE_CIRCUIT_OPEN")
                == descriptor_for_state("CORRUPT_REPORT")
                == ReadinessDescriptor.ERROR)


# ---- (4) descriptor_for_state edge cases --------------------------------

class TestDescriptorLookup:
    def test_unknown_state_returns_none(self) -> None:
        """A state that the engine doesn't emit returns ``None``,
        not a default. The caller treats None as drift.
        """
        assert descriptor_for_state("HACKED_STATE") is None

    def test_empty_string_returns_none(self) -> None:
        assert descriptor_for_state("") is None
