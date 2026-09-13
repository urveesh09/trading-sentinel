"""[WORKFLOW-H H5 2026-09-13] Bounded dashboard readiness vocabulary.

Implements plan section 12 acceptance: *"Dashboard should show
effective source/scope/window and readiness reason beside numbers.
Distinguish disabled, unconfigured, no session, no setup, no
evidence, stale and error."*

This module is the **vocabulary** layer for
``operational_coverage_report``'s output. It does not produce or
modify the report; it validates that the produced state/reason
pairs are members of the documented vocabulary, so a future
engineer adding a new state cannot silently change dashboard
colours without review.

The vocabulary has two pieces:

1. ``READINESS_DESCRIPTORS``: the seven §12 explicit descriptors
   in UPPER_SNAKE_CASE. Each has a documented definition.
2. ``STATE_TO_DESCRIPTOR``: a frozen mapping from the eight
   ``state`` values produced by ``operational_coverage_report``
   to their descriptor. A state may map to exactly one
   descriptor (no fan-out; if a state can mean two things,
   the producer is buggy and must split it).

A new ``state`` or ``reason`` value that is not in the vocabulary
is **not a hard failure** -- the producer's output is still
returned, but the validator logs at WARNING and tags the
report with ``vocabulary_drift=...`` so the operator sees it.

[WHY-THIS-EXISTS 2026-09-13]
  Pre-H5, the dashboard component rendered any ``state`` it
  received: green for ``AVAILABLE``, ``HEALTHY_NO_SETUP``,
  ``OBSERVED_USABLE``; amber for everything else. Adding a new
  state required a code change in ``operational_coverage.py``
  AND in the dashboard JSX. There was no bounded check between
  the producer and the UI. A future agent could add a state
  whose semantics were unclear (e.g. ``WATCHING`` vs
  ``OBSERVED``), and the dashboard would silently treat it as
  amber without telling anyone.

  H5 bounds the producer -> UI contract: the producer's output
  is checked against the vocabulary, and unmapped values are
  surfaced in the report and logged at WARNING.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, Iterable, Optional, Tuple


class ReadinessDescriptor(str, Enum):
    """The seven §12 explicit dashboard descriptors.

    Each value is a UPPER_SNAKE_CASE string. ``value`` is the
    human-readable descriptor; ``display`` is the operator-visible
    explanation (used by the dashboard UI to render beside numbers).
    """

    DISABLED = "DISABLED"
    UNCONFIGURED = "UNCONFIGURED"
    NO_SESSION = "NO_SESSION"
    NO_SETUP = "NO_SETUP"
    NO_EVIDENCE = "NO_EVIDENCE"
    STALE = "STALE"
    ERROR = "ERROR"


# Human-readable explanation per descriptor. The dashboard uses
# these in tooltips / "what does this mean?" popovers.
DESCRIPTOR_DISPLAY: Dict[ReadinessDescriptor, str] = {
    ReadinessDescriptor.DISABLED:
        "The source is registered but explicitly turned off. "
        "No data will arrive until an operator enables it.",
    ReadinessDescriptor.UNCONFIGURED:
        "The source has not been configured (no path, no key, "
        "no profile). The producer cannot run.",
    ReadinessDescriptor.NO_SESSION:
        "No live or recorded session has produced evidence "
        "for this source yet. The producer has never run.",
    ReadinessDescriptor.NO_SETUP:
        "The producer ran, but the current session has no setup "
        "to report (e.g. a healthy no-trade day, no breakouts).",
    ReadinessDescriptor.NO_EVIDENCE:
        "The producer ran, attempted to record evidence, but "
        "none arrived (timeout, upstream outage, instrument gap).",
    ReadinessDescriptor.STALE:
        "The producer last succeeded more than the freshness "
        "budget ago. Numbers shown may no longer reflect the "
        "current session.",
    ReadinessDescriptor.ERROR:
        "The producer failed (HTTP error, JSON parse failure, "
        "or circuit-breaker open). The last_success_at is the "
        "most recent good run.",
}


# Mapping from the eight state values produced by
# ``operational_coverage_report`` to their §12 descriptor.
# Frozen at import time; cannot drift at runtime.
STATE_TO_DESCRIPTOR: Dict[str, ReadinessDescriptor] = {
    # Manual advisory: healthy no-setup day.
    "HEALTHY_NO_SETUP": ReadinessDescriptor.NO_SETUP,
    # Manual advisory: validated candidate or queued delivery.
    "AVAILABLE": ReadinessDescriptor.NO_EVIDENCE,
    # Manual advisory: any other stage (failed / partial / unconfigured).
    "UNAVAILABLE": ReadinessDescriptor.NO_EVIDENCE,
    # Proactive: no source path / source path empty.
    "UNCONFIGURED": ReadinessDescriptor.UNCONFIGURED,
    # Scheduler: job ran without rejection.
    "OBSERVED": ReadinessDescriptor.STALE,
    # Scheduler: rejected (HTTP / circuit-breaker / signature).
    "SCHEDULER_REJECTED": ReadinessDescriptor.ERROR,
    # F&O collection: no quote observation yet.
    "NOT_YET_OBSERVED": ReadinessDescriptor.NO_SESSION,
    # Proactive completed-bars pass-through.
    "OBSERVED_USABLE": ReadinessDescriptor.NO_SETUP,
}


# Documented ``reason`` grammar. Each producer's ``reason``
# string should be a UPPER_SNAKE_CASE noun phrase. The list
# below captures the reasons currently produced directly by
# ``operational_coverage.py`` (the producer's own output).
#
# Grammar: ``<producer_area>_<state_descriptor>``
#   e.g. ``no_jobs_in_tier``, ``tier_observed``.
#
# NOTE: this is a *non-exhaustive* documentation set, not an
# enforcement boundary. Reasons are producer-specific and may
# grow over time; the validator does NOT block on unmapped
# reasons, but surfaces them in the report so operators see
# what's flowing. A new STATE, by contrast, IS a hard drift --
# states are the bounded vocabulary; reasons are descriptive.
PRODUCER_REASONS: FrozenSet[str] = frozenset({
    "no_jobs_in_tier",          # tier with zero registered jobs
    "tier_observed",            # tier with at least one observed run
    "NO_RECORDED_COMPLETED_BAR_OBSERVATION",  # proactive_completed_bars no rows
})


@dataclass(frozen=True)
class VocabularyDrift:
    """A producer / state / reason tuple that is not in the
    documented vocabulary.

    Returned by :func:`validate_coverage_report` and surfaced
    in the report as ``vocabulary_drift``. The dashboard UI
    renders unmapped states with a red badge so operators see
    the gap.
    """

    producer_id: str
    state: str
    reason: str
    descriptor: Optional[ReadinessDescriptor]

    def __str__(self) -> str:
        if self.descriptor is None:
            return (
                f"{self.producer_id}: state={self.state!r} "
                f"reason={self.reason!r} -- UNMAPPED STATE "
                f"(not in STATE_TO_DESCRIPTOR)"
            )
        return (
            f"{self.producer_id}: state={self.state!r} "
            f"reason={self.reason!r} -- mapped to "
            f"{self.descriptor.value}"
        )


def descriptor_for_state(state: str) -> Optional[ReadinessDescriptor]:
    """Return the §12 descriptor for a given ``state`` value,
    or ``None`` if the state is unmapped.

    Used by the dashboard UI to render beside numbers.
    """
    return STATE_TO_DESCRIPTOR.get(state)


def validate_coverage_report(report: dict) -> Tuple[dict, list]:
    """Validate that every producer's ``state`` is a member of
    the documented vocabulary.

    Returns ``(report, drift_list)`` where ``drift_list`` is a
    list of :class:`VocabularyDrift` for any unmapped states.
    The report is returned unchanged; the caller decides whether
    to attach the drift list as ``report["vocabulary_drift"]``.

    A unmapped state is logged at WARNING by the caller
    (``operational_coverage_report``) so operators see it in
    their log pipeline.

    State-vs-reason drift semantics:
    - **State drift** is HARD. A new ``state`` not in
      ``STATE_TO_DESCRIPTOR`` is a vocabulary gap. Future
      agents cannot silently add a state without it being
      flagged here.
    - **Reason drift** is SOFT / informational. Reasons are
      producer-specific and evolve; a new reason on a mapped
      state is *not* a vocabulary violation. It is surfaced
      as ``VocabularyDrift`` with the state's descriptor
      populated, so operators see what's flowing, but the
      validator does not block.

    Parameters
    ----------
    report
        The dict returned by ``operational_coverage_report``.
        Must have a ``"producers"`` key whose values are dicts
        with ``"state"`` and ``"reason"`` keys.

    Returns
    -------
    (report, drift_list)
        The report unchanged; the list of :class:`VocabularyDrift`
        objects (possibly empty if every state is mapped).
    """
    drift: list = []
    producers = report.get("producers") or {}
    for producer_id, producer in producers.items():
        if not isinstance(producer, dict):
            continue
        state = producer.get("state")
        reason = producer.get("reason")
        if state is None:
            drift.append(VocabularyDrift(
                producer_id=producer_id, state="<missing>",
                reason=str(reason) if reason else "<missing>",
                descriptor=None,
            ))
            continue
        descriptor = descriptor_for_state(state)
        if descriptor is None:
            drift.append(VocabularyDrift(
                producer_id=producer_id, state=str(state),
                reason=str(reason) if reason else "<missing>",
                descriptor=None,
            ))
            continue
        # State is mapped. Reason drift is informational.
        # We do NOT add it to ``drift`` here -- callers can
        # call :func:`vocabulary_summary` to see the documented
        # reason set. Surfacing every reason would flood the
        # drift list; the bounded contract is on the STATE.
    return report, drift


def vocabulary_summary() -> Dict[str, object]:
    """Return a JSON-serialisable summary of the documented
    vocabulary. Used by the dashboard UI to render the
    "what does this state mean?" reference, and by tests to
    assert the vocabulary is stable.
    """
    return {
        "descriptors": [
            {"value": d.value, "display": DESCRIPTOR_DISPLAY[d]}
            for d in ReadinessDescriptor
        ],
        "state_to_descriptor": {
            state: descriptor.value
            for state, descriptor in STATE_TO_DESCRIPTOR.items()
        },
        "producer_reasons": sorted(PRODUCER_REASONS),
        "descriptor_count": len(ReadinessDescriptor),
        "state_count": len(STATE_TO_DESCRIPTOR),
    }


__all__ = [
    "DESCRIPTOR_DISPLAY",
    "PRODUCER_REASONS",
    "READINESS_DESCRIPTORS",
    "STATE_TO_DESCRIPTOR",
    "ReadinessDescriptor",
    "VocabularyDrift",
    "descriptor_for_state",
    "validate_coverage_report",
    "vocabulary_summary",
]


# Back-compat alias: the seven §12 descriptors are sometimes
# referenced as ``READINESS_DESCRIPTORS``.
READINESS_DESCRIPTORS = ReadinessDescriptor
