"""[WORKFLOW-B.4 2026-09-17] Tests for the conditional-protection
schema helper.

Per Workstream B in NEXT_AGENT_PLAN.md:
> Finish conditional-protection input capture and declare
> whether it can use the same replay schema or needs a
> separate evaluator.

These tests pin:

  - ``ReplaySchemaCompat`` enum exposes FULL / PARTIAL /
    INCOMPATIBLE.
  - ``assess_replay_compatibility`` returns the right
    verdict for MARKET_SETUP and CONDITIONAL_PROTECTION
    payloads.
  - Missing CONDITIONAL_PROTECTION-specific fields
    surface as PARTIAL (with conservative default).
  - 3+ missing fields produce INCOMPATIBLE.
  - Unknown scope = INCOMPATIBLE.
  - ``compatible_payload`` returns the right boolean.
  - ``conditional_protection_schema_notes`` returns the
    schema-compatibility statement.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))

from conditional_protection_schema import (  # noqa: E402  -- import path
    CONDITIONAL_PROTECTION_REQUIRED_FIELDS,
    CompatVerdict,
    ReplaySchemaCompat,
    assess_replay_compatibility,
    compatible_payload,
    conditional_protection_schema_notes,
)


def _full_market_setup_payload() -> dict:
    """A complete MARKET_SETUP payload."""
    return {
        "scope": "MARKET_SETUP",
        "underlying": "NIFTY",
        "exchange": "NSE",
        "thesis_id": "t1",
        "evidence": "QUALIFIED_FOR_ADVISORY",
        "policy_version": "v1",
        "quote_time": "2026-09-17T09:30:00+05:30",
        "valid_until": "2026-09-17T15:30:00+05:30",
        "legs": [{"side": "BUY"}],
        "invalidation": "below low",
        "management": "exit at target",
        "uncertainty": "liquidity uncertain",
        "holding_horizon": "INTRADAY",
    }


# -- 1. ReplaySchemaCompat enum ------------------------------


def test_replay_schema_compat_has_three_values():
    assert {c.value for c in ReplaySchemaCompat} == {
        "FULL", "PARTIAL", "INCOMPATIBLE",
    }


def test_conditional_protection_required_fields_constant():
    """[WORKFLOW-B.4 2026-09-17] CP-specific required
    fields per the plan: 'Conditional protection states
    the exposure assumption and coverage'."""
    assert "exposure_assumption" in CONDITIONAL_PROTECTION_REQUIRED_FIELDS
    assert "coverage_units" in CONDITIONAL_PROTECTION_REQUIRED_FIELDS


# -- 2. MARKET_SETUP payloads --------------------------------


def test_full_market_setup_payload_is_full():
    payload = _full_market_setup_payload()
    v = assess_replay_compatibility(payload)
    assert v.verdict == ReplaySchemaCompat.FULL
    assert v.missing_required == ()
    assert v.missing_cp_specific == ()


def test_market_setup_missing_one_field_is_partial():
    payload = _full_market_setup_payload()
    payload.pop("uncertainty")
    v = assess_replay_compatibility(payload)
    assert v.verdict == ReplaySchemaCompat.PARTIAL
    assert "uncertainty" in v.missing_required


def test_market_setup_missing_two_fields_is_partial():
    payload = _full_market_setup_payload()
    payload.pop("uncertainty")
    payload.pop("management")
    v = assess_replay_compatibility(payload)
    assert v.verdict == ReplaySchemaCompat.PARTIAL


def test_market_setup_missing_three_fields_is_incompatible():
    payload = _full_market_setup_payload()
    payload.pop("uncertainty")
    payload.pop("management")
    payload.pop("invalidation")
    v = assess_replay_compatibility(payload)
    assert v.verdict == ReplaySchemaCompat.INCOMPATIBLE


# -- 3. CONDITIONAL_PROTECTION payloads ----------------------


def test_full_conditional_protection_payload_is_full():
    payload = _full_market_setup_payload()
    payload["scope"] = "CONDITIONAL_PROTECTION"
    payload["exposure_assumption"] = "owner holds 1 lot NIFTY long"
    payload["coverage_units"] = 1
    v = assess_replay_compatibility(payload)
    assert v.verdict == ReplaySchemaCompat.FULL
    assert v.missing_cp_specific == ()


def test_cp_missing_exposure_assumption_is_partial():
    """[WORKFLOW-B.4 2026-09-17] Missing one CP-specific
    field = PARTIAL with conservative defaults."""
    payload = _full_market_setup_payload()
    payload["scope"] = "CONDITIONAL_PROTECTION"
    payload["coverage_units"] = 1
    # exposure_assumption missing.
    v = assess_replay_compatibility(payload)
    assert v.verdict == ReplaySchemaCompat.PARTIAL
    assert "exposure_assumption" in v.missing_cp_specific
    # The notes mention CP-specific defaults.
    assert any("CP" in n or "CONDITIONAL" in n for n in v.notes)


def test_cp_missing_both_cp_fields_is_partial():
    payload = _full_market_setup_payload()
    payload["scope"] = "CONDITIONAL_PROTECTION"
    # Both exposure_assumption and coverage_units missing.
    v = assess_replay_compatibility(payload)
    assert v.verdict == ReplaySchemaCompat.PARTIAL
    assert len(v.missing_cp_specific) == 2


def test_cp_missing_cp_fields_plus_one_common_is_incompatible():
    """[WORKFLOW-B.4 2026-09-17] 3 missing fields (2 CP + 1 common)
    = INCOMPATIBLE."""
    payload = _full_market_setup_payload()
    payload["scope"] = "CONDITIONAL_PROTECTION"
    payload.pop("uncertainty")
    # 1 common + 2 CP = 3 missing.
    v = assess_replay_compatibility(payload)
    assert v.verdict == ReplaySchemaCompat.INCOMPATIBLE
    assert len(v.missing_required) + len(v.missing_cp_specific) >= 3


# -- 4. Unknown scope --------------------------------------


def test_unknown_scope_is_incompatible():
    payload = _full_market_setup_payload()
    payload["scope"] = "BOGUS_SCOPE"
    v = assess_replay_compatibility(payload)
    assert v.verdict == ReplaySchemaCompat.INCOMPATIBLE
    assert any("scope" in n for n in v.notes)


def test_missing_scope_is_incompatible():
    payload = _full_market_setup_payload()
    payload.pop("scope")
    v = assess_replay_compatibility(payload)
    assert v.verdict == ReplaySchemaCompat.INCOMPATIBLE


# -- 5. compatible_payload ---------------------------------


def test_compatible_payload_true_for_full():
    assert compatible_payload(_full_market_setup_payload()) is True


def test_compatible_payload_true_for_partial():
    payload = _full_market_setup_payload()
    payload.pop("uncertainty")
    assert compatible_payload(payload) is True


def test_compatible_payload_false_for_incompatible():
    payload = _full_market_setup_payload()
    payload.pop("uncertainty")
    payload.pop("management")
    payload.pop("invalidation")
    assert compatible_payload(payload) is False


def test_compatible_payload_false_for_unknown_scope():
    payload = _full_market_setup_payload()
    payload["scope"] = "BOGUS"
    assert compatible_payload(payload) is False


# -- 6. CompatVerdict dataclass -----------------------------


def test_verdict_to_dict_includes_required_fields():
    payload = _full_market_setup_payload()
    v = assess_replay_compatibility(payload)
    d = v.to_dict()
    expected = {"verdict", "missing_required",
                "missing_cp_specific", "notes"}
    assert set(d.keys()) == expected


# -- 7. Schema notes ----------------------------------------


def test_schema_notes_mention_conditional_protection():
    notes = conditional_protection_schema_notes()
    assert "CONDITIONAL_PROTECTION" in notes


def test_schema_notes_declare_schema_compatibility():
    """[WORKFLOW-B.4 2026-09-17] The plan: 'declare whether
    it can use the same replay schema or needs a separate
    evaluator.' The notes must include the verdict."""
    notes = conditional_protection_schema_notes()
    # The notes should mention both the standard schema and
    # the fallback behavior.
    assert "replay schema" in notes.lower()
    assert ("PARTIAL" in notes
            or "FALL BACK" in notes.upper()
            or "fall back" in notes.lower()
            or "conservative" in notes.lower())
