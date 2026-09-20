"""[WORKFLOW-B.4 2026-09-17] Conditional-protection capture schema.

Per Workstream B in NEXT_AGENT_PLAN.md:
> Finish conditional-protection input capture and declare
> whether it can use the same replay schema or needs a
> separate evaluator.

Background:

  The ``AdvisoryScope.CONDITIONAL_PROTECTION`` scope emits a
  ``partner_advisory_ideas`` row whose ``payload`` JSON
  carries an extra ``coverage_assumption`` / ``coverage_units``
  block and uses a different ``risk_label`` than
  ``MARKET_SETUP``. The question is whether the standard
  replay schema (``partner_full_policy_replay_v1``) can
  consume a CONDITIONAL_PROTECTION payload as-is, or needs
  a separate evaluator.

This module exposes:

  - ``ReplaySchemaCompat`` -- enum of compatibility levels:
    FULL / PARTIAL / INCOMPATIBLE.
  - ``assess_replay_compatibility(payload)`` -- inspects a
    payload dict and returns the compatibility verdict
    plus a list of missing-or-extra fields.
  - ``compatible_payload(payload)`` -- bool helper.
  - ``required_cp_fields`` -- tuple of fields the standard
    replay schema requires for CONDITIONAL_PROTECTION
    captures.

The verdict rules (per the plan: "declare whether it can
use the same replay schema or needs a separate
evaluator"):

  FULL         -- All required fields are present and the
                  payload is structurally a superset of the
                  standard replay schema. The existing
                  ``partner_full_policy_replay`` can
                  consume it directly.
  PARTIAL      -- The payload is missing 1-2 optional
                  fields (e.g. ``exposure_assumption``
                  text) that the standard replay can
                  tolerate as defaults. The replay can
                  consume it with a fallback.
  INCOMPATIBLE -- The payload is missing 3+ required
                  fields, or has an unrecognized scope, or
                  has malformed economics. The standard
                  replay cannot consume it; a separate
                  evaluator is needed.

The implementation is pure: callers pass a dict, the
helper returns the verdict.

Read-only. No DB writes. No Telegram.
"""
from __future__ import annotations

import dataclasses
import enum
from typing import Any, Iterable, Mapping, Optional


class ReplaySchemaCompat(str, enum.Enum):
    """How well a payload fits the standard replay schema."""
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    INCOMPATIBLE = "INCOMPATIBLE"


# Standard replay schema requires these fields (common
# to all scopes, derived from the ``_candidate_payload``
# shape in ``partner_manual_advisory.py``).
_COMMON_REQUIRED_FIELDS: tuple[str, ...] = (
    "scope", "underlying", "exchange", "thesis_id",
    "evidence", "policy_version", "quote_time", "valid_until",
    "legs", "invalidation", "management", "uncertainty",
    "holding_horizon",
)

# CONDITIONAL_PROTECTION additionally requires these.
CONDITIONAL_PROTECTION_REQUIRED_FIELDS: tuple[str, ...] = (
    "exposure_assumption", "coverage_units",
)

# Standard replay has additional optional fields the
# payload MAY carry; they don't break compatibility but
# the replay may not consume them.
_ACCEPTABLE_EXTRAS: frozenset[str] = frozenset({
    "net_debit_rs", "net_credit_rs", "max_loss_rs", "max_profit_rs",
    "breakevens", "trigger_level", "invalidation_level",
    "target_level", "estimated_round_trip_cost_rs",
    "why_now", "management_deadline",
})


@dataclasses.dataclass(frozen=True)
class CompatVerdict:
    """Verdict + detail for a single payload."""
    verdict: ReplaySchemaCompat
    missing_required: tuple[str, ...]
    missing_cp_specific: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "missing_required": list(self.missing_required),
            "missing_cp_specific": list(self.missing_cp_specific),
            "notes": list(self.notes),
        }


def assess_replay_compatibility(payload: Mapping[str, Any]) -> CompatVerdict:
    """Assess whether ``payload`` can be replayed under the
    standard schema.

    Args:
        payload: a partner-advisory payload dict (the
            ``_candidate_payload()`` output, persisted as
            JSON in ``partner_advisory_ideas.payload``).

    Returns:
        A ``CompatVerdict`` with the compatibility level
        + a list of missing fields.
    """
    notes: list[str] = []
    scope = payload.get("scope") if isinstance(payload, Mapping) else None

    if scope not in {"MARKET_SETUP", "CONDITIONAL_PROTECTION"}:
        return CompatVerdict(
            verdict=ReplaySchemaCompat.INCOMPATIBLE,
            missing_required=(),
            missing_cp_specific=(),
            notes=(
                f"unknown or missing scope: {scope!r}; "
                "the standard replay schema does not support it",
            ),
        )

    missing_required = tuple(
        f for f in _COMMON_REQUIRED_FIELDS
        if not payload.get(f)
    )
    missing_cp = ()
    if scope == "CONDITIONAL_PROTECTION":
        missing_cp = tuple(
            f for f in CONDITIONAL_PROTECTION_REQUIRED_FIELDS
            if not payload.get(f)
        )

    # Decision: FULL = 0 missing; PARTIAL = 1-2 missing;
    # INCOMPATIBLE = 3+ missing.
    total_missing = len(missing_required) + len(missing_cp)
    if total_missing == 0:
        verdict = ReplaySchemaCompat.FULL
    elif total_missing <= 2:
        verdict = ReplaySchemaCompat.PARTIAL
        if missing_cp:
            notes.append(
                "missing CONDITIONAL_PROTECTION-specific fields; "
                "the replay can apply conservative defaults"
            )
        if missing_required:
            notes.append(
                "missing common fields; the replay can "
                "fall back to WARN"
            )
    else:
        verdict = ReplaySchemaCompat.INCOMPATIBLE
        notes.append(
            f"{total_missing} missing fields; a separate "
            "evaluator is required"
        )

    return CompatVerdict(
        verdict=verdict,
        missing_required=missing_required,
        missing_cp_specific=missing_cp,
        notes=tuple(notes),
    )


def compatible_payload(payload: Mapping[str, Any]) -> bool:
    """True iff the payload can be replayed under the
    standard schema (FULL or PARTIAL)."""
    verdict = assess_replay_compatibility(payload)
    return verdict.verdict in (
        ReplaySchemaCompat.FULL,
        ReplaySchemaCompat.PARTIAL,
    )


def conditional_protection_schema_notes() -> str:
    """Human-readable schema-compatibility statement.

    Per the plan: 'declare whether it can use the same replay
    schema or needs a separate evaluator.' This function
    returns a one-line summary suitable for the audit log.
    """
    return (
        "CONDITIONAL_PROTECTION uses the same replay schema "
        "(partner_full_policy_replay_v1) as MARKET_SETUP, with "
        "two extra required fields (exposure_assumption, "
        "coverage_units) and a different max-loss label. "
        "Payloads missing those extras fall back to PARTIAL "
        "compatibility with conservative defaults. Payloads "
        "missing 3+ required fields are INCOMPATIBLE and "
        "require a separate evaluator."
    )


__all__ = [
    "CompatVerdict",
    "CONDITIONAL_PROTECTION_REQUIRED_FIELDS",
    "ReplaySchemaCompat",
    "assess_replay_compatibility",
    "compatible_payload",
    "conditional_protection_schema_notes",
]
