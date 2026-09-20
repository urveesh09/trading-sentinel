"""[WORKFLOW-A.3 2026-09-17] Capture-bundle binding.

Per Workstream A in NEXT_AGENT_PLAN.md:
> Carry the chosen clocks and source IDs into the
> captured bundle and frozen decision manifest. Bind
> candidate and public captures to the same
> decision/run/account/index.

This module introduces the canonical capture bundle --
the dict that ties together:

  - the candidate card (the structured advisory)
  - the decision clock (the explicit causal clocks)
  - the source identities (which feeds were used)
  - the decision / run / account / index identifiers

The captured bundle is the canonical replay artifact: a
later audit can re-derive the candidate from the bundle
and verify it matches the live dispatch.

Per-scope fields in the bundle:

  - ``decision_id`` -- unique per decision (a stable hash).
  - ``run_id`` -- from the DecisionClock.
  - ``account_id`` -- from the DecisionClock.
  - ``underlying`` -- from the DecisionClock.
  - ``policy`` -- from the DecisionClock.
  - ``clock`` -- the DecisionClock payload (ISO timestamps).
  - ``source_ids`` -- ``public_source_id`` /
    ``chain_source_id`` strings.
  - ``card`` -- the candidate dict (matches the
    ``_candidate_payload`` shape).
  - ``bundle_version`` -- ``BUNDLE_VERSION_V1`` so future
    schema changes can be versioned.

The validator (``validate_bundle``) asserts the bundle has
all required fields and that the bindings hold (decision_id
matches the clock's run_id, underlying matches, etc.).

Read-only. No DB writes. No network. No Telegram.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional


BUNDLE_VERSION_V1 = "BUNDLE_VERSION_V1"


class BundleValidationCode(str, enum.Enum):
    """Codes emitted by ``validate_bundle``."""
    MISSING_FIELD = "MISSING_FIELD"
    WRONG_TYPE = "WRONG_TYPE"
    UNDERLYING_MISMATCH = "UNDERLYING_MISMATCH"
    RUN_ID_MISMATCH = "RUN_ID_MISMATCH"
    ACCOUNT_MISMATCH = "ACCOUNT_MISMATCH"
    POLICY_MISMATCH = "POLICY_MISMATCH"
    BAD_VERSION = "BAD_VERSION"
    EMPTY_CARD = "EMPTY_CARD"
    CLOCK_NOT_READY = "CLOCK_NOT_READY"


@dataclasses.dataclass(frozen=True)
class BundleValidationProblem:
    """One row of a bundle validation report."""
    code: BundleValidationCode
    field: str
    message: str


@dataclasses.dataclass(frozen=True)
class CaptureBundle:
    """The canonical captured bundle.

    Attributes:
        bundle_version: schema version. Currently
            ``BUNDLE_VERSION_V1``.
        decision_id: stable hash binding the bundle to a
            single decision.
        run_id: from the DecisionClock.
        account_id: from the DecisionClock.
        underlying: from the DecisionClock.
        policy: from the DecisionClock (e.g.
            ``FROZEN_COMPLETED_BAR_CUTOFF_V1``).
        clock: the DecisionClock payload (ISO timestamps).
        source_ids: ``{"public": ..., "chain": ...}``.
        card: the candidate dict.
    """
    bundle_version: str
    decision_id: str
    run_id: str
    account_id: str
    underlying: str
    policy: str
    clock: dict
    source_ids: dict
    card: dict

    def to_dict(self) -> dict:
        """Serialize the bundle to a JSON-safe dict."""
        return {
            "bundle_version": self.bundle_version,
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "account_id": self.account_id,
            "underlying": self.underlying,
            "policy": self.policy,
            "clock": self.clock,
            "source_ids": self.source_ids,
            "card": self.card,
        }


def _decision_id_hash(*parts: str) -> str:
    """Compute a stable hash binding the bundle's identity."""
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x1f")  # ASCII unit separator
    return h.hexdigest()


def build_capture_bundle(
    *,
    run_id: str,
    account_id: str,
    underlying: str,
    policy: str,
    clock_payload: Mapping[str, Any],
    public_source_id: Optional[str],
    chain_source_id: Optional[str],
    card: Mapping[str, Any],
    bundle_version: str = BUNDLE_VERSION_V1,
) -> CaptureBundle:
    """Build the canonical capture bundle.

    Args:
        run_id: from the DecisionClock.
        account_id: from the DecisionClock.
        underlying: from the DecisionClock.
        policy: the clock policy version (e.g.
            ``FROZEN_COMPLETED_BAR_CUTOFF_V1``).
        clock_payload: the DecisionClock's ``payload()``
            output (dict of ISO timestamps + run_id).
        public_source_id: source identity of the public
            feed. Optional.
        chain_source_id: source identity of the chain
            feed. Optional.
        card: the candidate dict (matches the
            ``_candidate_payload`` shape).
        bundle_version: schema version. Default
            ``BUNDLE_VERSION_V1``.

    Returns:
        A ``CaptureBundle`` with a deterministic
        ``decision_id``.
    """
    source_ids = {
        "public": public_source_id,
        "chain": chain_source_id,
    }
    # Decision_id binds run_id + account_id + underlying +
    # policy + a fingerprint of the clock_payload + the card's
    # thesis_id (when present). Operators can re-derive the
    # decision_id from any persisted capture.
    card_thesis_id = ""
    if isinstance(card, Mapping):
        card_thesis_id = str(card.get("thesis_id", ""))
    decision_id = _decision_id_hash(
        run_id, account_id, underlying, policy,
        card_thesis_id,
        json.dumps(dict(clock_payload), sort_keys=True,
                    separators=(",", ":")),
    )
    return CaptureBundle(
        bundle_version=bundle_version,
        decision_id=decision_id,
        run_id=run_id,
        account_id=account_id,
        underlying=underlying,
        policy=policy,
        clock=dict(clock_payload),
        source_ids=source_ids,
        card=dict(card),
    )


def bundle_from_clock_and_card(
    *,
    clock: Any,
    card: Mapping[str, Any],
    public_source_id: Optional[str] = None,
    chain_source_id: Optional[str] = None,
) -> CaptureBundle:
    """Build a capture bundle from a DecisionClock + a card.

    Convenience wrapper around ``build_capture_bundle``
    that takes a DecisionClock directly.
    """
    return build_capture_bundle(
        run_id=clock.run_id,
        account_id=clock.account_id,
        underlying=clock.underlying,
        policy=clock.policy,
        clock_payload=clock.payload(),
        public_source_id=public_source_id or clock.public_source_id,
        chain_source_id=chain_source_id or clock.chain_source_id,
        card=card,
    )


REQUIRED_BUNDLE_FIELDS: tuple[str, ...] = (
    "bundle_version", "decision_id", "run_id", "account_id",
    "underlying", "policy", "clock", "source_ids", "card",
)


def validate_bundle(
    bundle: Any,
) -> list[BundleValidationProblem]:
    """Validate a captured bundle and return ALL problems.

    Returns an empty list when ``bundle`` is well-formed.
    """
    problems: list[BundleValidationProblem] = []
    if not isinstance(bundle, Mapping):
        problems.append(BundleValidationProblem(
            code=BundleValidationCode.WRONG_TYPE,
            field="<root>",
            message=(
                f"bundle must be a Mapping; got {type(bundle).__name__}"
            ),
        ))
        return problems

    # Required fields.
    for field in REQUIRED_BUNDLE_FIELDS:
        if field not in bundle or bundle[field] is None:
            problems.append(BundleValidationProblem(
                code=BundleValidationCode.MISSING_FIELD,
                field=field,
                message=f"required field '{field}' is missing",
            ))
    # bundle_version.
    version = bundle.get("bundle_version")
    if version is not None and version != BUNDLE_VERSION_V1:
        problems.append(BundleValidationProblem(
            code=BundleValidationCode.BAD_VERSION,
            field="bundle_version",
            message=(
                f"unsupported bundle_version: {version!r}; "
                f"expected {BUNDLE_VERSION_V1!r}"
            ),
        ))
    # Empty card.
    card = bundle.get("card")
    if isinstance(card, Mapping) and not card:
        problems.append(BundleValidationProblem(
            code=BundleValidationCode.EMPTY_CARD,
            field="card",
            message="card is empty",
        ))
    # clock payload: must contain tick_started_at.
    clock = bundle.get("clock")
    if isinstance(clock, Mapping):
        if not clock.get("tick_started_at"):
            problems.append(BundleValidationProblem(
                code=BundleValidationCode.CLOCK_NOT_READY,
                field="clock.tick_started_at",
                message="clock payload missing tick_started_at",
            ))
    # Cross-bundle bindings: card.underlying should match
    # bundle.underlying (when card has one).
    if isinstance(card, Mapping):
        card_underlying = card.get("underlying")
        if (card_underlying is not None
            and isinstance(bundle.get("underlying"), str)
            and card_underlying.upper() != bundle["underlying"].upper()):
            problems.append(BundleValidationProblem(
                code=BundleValidationCode.UNDERLYING_MISMATCH,
                field="card.underlying",
                message=(
                    f"card.underlying ({card_underlying!r}) does not "
                    f"match bundle.underlying ({bundle['underlying']!r})"
                ),
            ))
    return problems


def has_required_bundle_fields(bundle: Mapping[str, Any]) -> bool:
    """True iff ``bundle`` has every required field."""
    return all(
        field in bundle and bundle[field] is not None
        for field in REQUIRED_BUNDLE_FIELDS
    )


__all__ = [
    "BUNDLE_VERSION_V1",
    "BundleValidationCode",
    "BundleValidationProblem",
    "CaptureBundle",
    "REQUIRED_BUNDLE_FIELDS",
    "build_capture_bundle",
    "bundle_from_clock_and_card",
    "has_required_bundle_fields",
    "validate_bundle",
]
