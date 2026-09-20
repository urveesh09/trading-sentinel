"""[WORKFLOW-I.4.E 2026-09-14] Bounded contract-health self-evaluation.

Per plan §13 ("The typed result must not change capital limits,
qualification or order/delivery authority"), this module is the
"guard the guards" layer that periodically asserts the bounded
contract on the agent's own surfaces:

    1. No execution authority in the status envelope
       (``can_place_orders=False`` + ``authorization_effect=NONE``).
    2. No prompt leakage in any persisted snapshot
       (the bounded status / usefulness envelope has a fixed
       allow-list of keys; any other key is a leak).
    3. No review content in the bounded usefulness snapshot
       (only counters cross the agent->engine bridge; never
       pitch/rationale/risks).
    4. Classifier is fail-closed: a ``ClassificationResult``
       below ``CONFIDENCE_THRESHOLD`` is forced to ``UNKNOWN``.
    5. Verdict is non-authoritative: a ``Review`` never carries
       a capital/qualification delta field.

Each invariant returns a ``ContractCheck`` with ``(name, passed,
violations, observed)``. ``evaluate_contract()`` runs every check
and returns a ``ContractReport`` with a top-level ``passed`` flag
(``True`` iff every check passed) and a bounded JSON-serialisable
``to_dict()``.

This module is intentionally pure and importable in isolation
(no model calls, no broker, no scheduler). It is the input to
either an operator CLI or a future cron; this slice ships the
pure surface and the CLI -- cron wiring is a follow-up.

Per inheritance §9, this is the bounded slice that "strengthens
the J.10 / F3-F6 / I.4.D surfaces with bounded improvements" --
no verdict semantics change, no F/G files touched, no deletions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional


# ---------------------------------------------------------------------------
# Bounded allow-lists (the contract)

#: Keys the agent is permitted to send in the bounded status envelope.
#: Any other key at the top level is a prompt-leak / schema-drift signal.
STATUS_ENVELOPE_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "state",
        "reported_at",
        "async_requested",
        "policy_allows_annotation",
        "reason",
        "queue",
        "usefulness",
    }
)

#: Keys permitted inside the ``usefulness`` sub-dict (counters only --
#: never review content). Pinning these here is what makes the
#: agent->engine bridge auditable.
USEFULNESS_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "total_completed_reviews",
        "verdict_counts",
        "cache_hits",
        "cache_misses",
        "cache_hit_rate",
        "circuit_opens",
        "response_seconds_mean",
        "response_seconds_p95",
        "response_seconds_last",
        "last_completed_at",
    }
)

#: Capital/qualification delta fields. A ``Review`` carrying any of
#: these is a contract violation -- the verdict is informational
#: only and must NEVER carry authority-bearing numbers.
FORBIDDEN_REVIEW_DELTA_FIELDS: frozenset[str] = frozenset(
    {
        "can_place_orders",
        "authorization_effect",
        "live_delta_inr",
        "capital_delta",
        "qualification",
        "approved_live_budget",
    }
)


# ---------------------------------------------------------------------------
# Result dataclasses


@dataclass(frozen=True)
class ContractCheck:
    """One bounded invariant check.

    Attributes:
        name: A short identifier for the invariant.
        passed: True iff zero violations.
        violations: A list of human-readable violation strings.
            Empty when ``passed`` is True.
        observed: Bounded structured context for the operator
            (e.g. which keys were present, how many results were
            inspected). Never contains review text or prompt
            content.
    """

    name: str
    passed: bool
    violations: List[str] = field(default_factory=list)
    observed: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "violations": list(self.violations),
            "observed": dict(self.observed),
        }


@dataclass(frozen=True)
class ContractReport:
    """Aggregate contract report.

    Attributes:
        checks: Per-invariant results in stable order.
        passed: True iff every check passed.
        evaluated_at: UTC datetime when the report was built.
        schema_version: Pinned so consumers can version the shape.
    """

    checks: List[ContractCheck]
    passed: bool
    evaluated_at: datetime
    schema_version: str = "i4e-v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evaluated_at": self.evaluated_at.isoformat(),
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
        }

    def violations(self) -> List[str]:
        """Flat list of every violation across every check.

        Convenient for the operator CLI -- one line per problem,
        no nesting.
        """
        out: List[str] = []
        for c in self.checks:
            for v in c.violations:
                out.append(f"{c.name}: {v}")
        return out


# ---------------------------------------------------------------------------
# The five bounded invariants


def check_status_envelope_authority(envelope: Optional[dict[str, Any]]) -> ContractCheck:
    """Invariant 1: the status envelope carries NO execution authority.

    The agent publishes a bounded health envelope to the engine.
    Per plan §13, this envelope MUST NOT carry ``can_place_orders``
    or ``authorization_effect`` set to anything other than their
    documented safe defaults (``False`` and ``"NONE"`` respectively).

    Returns a ``ContractCheck`` with the observed keys + values.
    """
    observed: dict[str, Any] = {
        "present": envelope is not None,
        "keys": sorted(envelope.keys()) if isinstance(envelope, dict) else [],
    }
    violations: List[str] = []

    if envelope is None:
        # No envelope published yet -- informational only, not a violation.
        return ContractCheck(
            name="status_envelope_authority",
            passed=True,
            observed=observed,
        )

    if not isinstance(envelope, dict):
        violations.append(f"envelope is not a dict: {type(envelope).__name__}")
        return ContractCheck(
            name="status_envelope_authority",
            passed=False,
            violations=violations,
            observed=observed,
        )

    # can_place_orders MUST be False (the bounded contract).
    if "can_place_orders" in envelope:
        v = envelope["can_place_orders"]
        if v is not False:
            violations.append(
                f"can_place_orders={v!r} (expected False; envelope must "
                "never carry execution authority)"
            )

    # authorization_effect MUST be NONE.
    if "authorization_effect" in envelope:
        v = envelope["authorization_effect"]
        if v != "NONE":
            violations.append(
                f"authorization_effect={v!r} (expected 'NONE'; envelope "
                "is diagnostic-only)"
            )

    # No unknown keys at the top level.
    extras = sorted(set(envelope.keys()) - STATUS_ENVELOPE_ALLOWED_KEYS)
    if extras:
        violations.append(
            f"unknown top-level keys (not in allow-list): {extras}"
        )

    # The usefulness sub-envelope, if present, must also respect its allow-list.
    if "usefulness" in envelope and isinstance(envelope["usefulness"], dict):
        u_keys = sorted(envelope["usefulness"].keys())
        u_extras = sorted(set(u_keys) - USEFULNESS_ALLOWED_KEYS)
        if u_extras:
            violations.append(
                f"usefulness envelope has unknown keys (not in "
                f"allow-list): {u_extras}"
            )
        observed["usefulness_keys"] = u_keys

    return ContractCheck(
        name="status_envelope_authority",
        passed=not violations,
        violations=violations,
        observed=observed,
    )


def check_no_prompt_leakage(snapshot: Optional[dict[str, Any]]) -> ContractCheck:
    """Invariant 2: no prompt leakage in any persisted snapshot.

    The bounded usefulness snapshot is the only agent-payload the
    engine persists; it must NEVER carry prompt content, model
    output, or reviewer rationale.

    This check accepts either a usefulness snapshot or a generic
    snapshot dict and rejects any payload that contains
    prompt-flavoured keys.
    """
    observed: dict[str, Any] = {"present": snapshot is not None}
    violations: List[str] = []

    if snapshot is None:
        return ContractCheck(
            name="no_prompt_leakage",
            passed=True,
            observed=observed,
        )

    if not isinstance(snapshot, dict):
        violations.append(f"snapshot is not a dict: {type(snapshot).__name__}")
        return ContractCheck(
            name="no_prompt_leakage",
            passed=False,
            violations=violations,
            observed=observed,
        )

    # Keys that would indicate prompt / reviewer content crossed the bridge.
    prompt_leak_keys = (
        "prompt",
        "prompt_text",
        "system_prompt",
        "raw_prompt",
        "review_text",
        "reviewer_output",
        "model_output",
        "raw_response",
        "rationale",
        "pitch",
        "risks",
        "analysis",
    )
    observed["keys"] = sorted(snapshot.keys())
    leaked = sorted(k for k in snapshot.keys() if k in prompt_leak_keys)
    if leaked:
        violations.append(
            f"prompt-flavoured keys present in snapshot: {leaked}"
        )

    # If the snapshot carries a usefulness sub-envelope, the same rule
    # applies recursively.
    usefulness = snapshot.get("usefulness")
    if isinstance(usefulness, dict):
        u_leaked = sorted(
            k for k in usefulness.keys() if k in prompt_leak_keys
        )
        if u_leaked:
            violations.append(
                f"prompt-flavoured keys inside usefulness envelope: "
                f"{u_leaked}"
            )
        observed["usefulness_keys"] = sorted(usefulness.keys())

    return ContractCheck(
        name="no_prompt_leakage",
        passed=not violations,
        violations=violations,
        observed=observed,
    )


def check_usefulness_counters_only(
    snapshot: Optional[dict[str, Any]],
) -> ContractCheck:
    """Invariant 3: the usefulness envelope carries counters only.

    If a usefulness sub-envelope is present, EVERY key must be in
    the bounded allow-list AND the values must be bounded primitives
    (int / float / str / None -- no nested dicts except for
    ``verdict_counts`` which is a dict of ``str -> int``).
    """
    observed: dict[str, Any] = {"present": snapshot is not None}
    violations: List[str] = []

    if snapshot is None or not isinstance(snapshot, dict):
        return ContractCheck(
            name="usefulness_counters_only",
            passed=True,
            observed=observed,
        )

    usefulness = snapshot.get("usefulness")
    if usefulness is None:
        return ContractCheck(
            name="usefulness_counters_only",
            passed=True,
            observed=observed,
        )

    if not isinstance(usefulness, dict):
        violations.append(
            f"usefulness envelope is not a dict: {type(usefulness).__name__}"
        )
        return ContractCheck(
            name="usefulness_counters_only",
            passed=False,
            violations=violations,
            observed=observed,
        )

    observed["usefulness_keys"] = sorted(usefulness.keys())
    for key, value in usefulness.items():
        if key not in USEFULNESS_ALLOWED_KEYS:
            violations.append(
                f"key {key!r} not in usefulness allow-list"
            )
            continue
        if key == "verdict_counts":
            # Must be a dict of str -> int.
            if not isinstance(value, dict):
                violations.append(
                    f"verdict_counts must be dict, got "
                    f"{type(value).__name__}"
                )
            else:
                for vc_key, vc_val in value.items():
                    if not isinstance(vc_key, str):
                        violations.append(
                            f"verdict_counts key {vc_key!r} not str"
                        )
                    if not isinstance(vc_val, int) or isinstance(vc_val, bool):
                        violations.append(
                            f"verdict_counts[{vc_key!r}] = {vc_val!r} "
                            "(not int)"
                        )
            continue
        # Every other key must be a bounded primitive.
        if isinstance(value, bool):
            # bool is a subclass of int in Python; we want to reject
            # raw bools for non-count keys.
            violations.append(
                f"usefulness[{key!r}] = {value!r} (bool not allowed)"
            )
            continue
        if not isinstance(value, (int, float, str, type(None))):
            violations.append(
                f"usefulness[{key!r}] = {type(value).__name__} "
                "(not a bounded primitive)"
            )

    return ContractCheck(
        name="usefulness_counters_only",
        passed=not violations,
        violations=violations,
        observed=observed,
    )


def check_classifier_fail_closed(
    classifications: Optional[Iterable[Any]],
    *,
    confidence_threshold: float = 0.6,
) -> ContractCheck:
    """Invariant 4: the classifier is fail-closed.

    For every ``ClassificationResult`` in the iterable (the
    dataclass from ``agent/news_classifier.py``), the contract is:

        - ``confidence >= confidence_threshold`` AND
        - ``category`` is in the enum (not ``UNKNOWN`` forced) AND
        - ``rationale`` is bounded (≤ 280 chars)

    A result below threshold MUST have ``category == UNKNOWN``.
    A result outside the enum MUST have ``category == UNKNOWN``.
    A result with an unbounded rationale is a violation.
    """
    observed: dict[str, Any] = {
        "n_inspected": 0,
        "confidence_threshold": confidence_threshold,
        "max_rationale_len": 0,
    }
    violations: List[str] = []

    if classifications is None:
        return ContractCheck(
            name="classifier_fail_closed",
            passed=True,
            observed=observed,
        )

    allowed_categories: Optional[frozenset[str]] = None
    try:
        # Imported lazily so this module stays importable in isolation
        # (no agent.py side-effects, no Telegram check, etc.).
        # Try the bare module name first (the project's convention),
        # then fall back to a dotted path for callers that do have
        # an ``agent`` package on sys.path.
        try:
            from news_classifier import NewsCategory as _NC
        except Exception:
            from agent.news_classifier import NewsCategory as _NC
        allowed_categories = frozenset(c.value for c in _NC)
    except Exception:  # pragma: no cover - import isolation
        allowed_categories = None

    for idx, c in enumerate(classifications):
        observed["n_inspected"] = idx + 1
        # The classifier's frozen dataclass is the only legitimate
        # shape; anything else is a contract violation.
        # Use duck-typing rather than `isinstance` to avoid an import
        # cycle in isolated test environments.
        category = getattr(c, "category", None)
        confidence = getattr(c, "confidence", None)
        rationale = getattr(c, "rationale", None)

        # 4a: below-threshold -> UNKNOWN
        if confidence is not None and isinstance(confidence, (int, float)):
            if confidence < confidence_threshold and category is not None:
                # ``UNKNOWN`` value is fixed by the classifier module;
                # we accept either the enum or its string value.
                if str(getattr(category, "value", category)) != "unknown":
                    violations.append(
                        f"classifications[{idx}]: confidence "
                        f"{confidence} < threshold {confidence_threshold} "
                        f"but category={category!r} (must be UNKNOWN)"
                    )

        # 4b: category outside enum -> violation (caller is expected
        # to have used the bounded enum).
        if allowed_categories is not None and category is not None:
            cv = str(getattr(category, "value", category))
            if cv not in allowed_categories:
                violations.append(
                    f"classifications[{idx}]: category={cv!r} not in "
                    f"the bounded enum {sorted(allowed_categories)}"
                )

        # 4c: rationale bounded.
        if rationale is not None:
            rlen = len(str(rationale))
            observed["max_rationale_len"] = max(
                observed["max_rationale_len"], rlen
            )
            if rlen > 280:
                violations.append(
                    f"classifications[{idx}]: rationale length "
                    f"{rlen} > 280 chars (bounded contract)"
                )

    return ContractCheck(
        name="classifier_fail_closed",
        passed=not violations,
        violations=violations,
        observed=observed,
    )


def check_review_non_authoritative(
    reviews: Optional[Iterable[Any]],
) -> ContractCheck:
    """Invariant 5: a ``Review`` never carries authority.

    Per plan §13: "The typed result must not change capital
    limits, qualification or order/delivery authority."

    A ``Review`` MUST NOT carry any of the ``FORBIDDEN_REVIEW_DELTA_FIELDS``.
    If it does, the verdict has crossed from informational to
    authoritative -- a contract violation.
    """
    observed: dict[str, Any] = {"n_inspected": 0}
    violations: List[str] = []

    if reviews is None:
        return ContractCheck(
            name="review_non_authoritative",
            passed=True,
            observed=observed,
        )

    for idx, r in enumerate(reviews):
        observed["n_inspected"] = idx + 1
        # Duck-typed check via dataclasses.fields if available;
        # fall back to ``__dict__`` so the module works against
        # both real Review objects and lightweight test stand-ins.
        field_names: list[str] = []
        try:
            from dataclasses import fields as _dc_fields

            field_names = [f.name for f in _dc_fields(r)]
        except Exception:
            field_names = list(getattr(r, "__dict__", {}).keys())
        leaked = sorted(
            k for k in field_names if k in FORBIDDEN_REVIEW_DELTA_FIELDS
        )
        if leaked:
            violations.append(
                f"reviews[{idx}]: carries forbidden authority fields "
                f"{leaked} (review must be informational only)"
            )

    return ContractCheck(
        name="review_non_authoritative",
        passed=not violations,
        violations=violations,
        observed=observed,
    )


# ---------------------------------------------------------------------------
# Aggregate


def evaluate_contract(
    *,
    status_envelope: Optional[dict[str, Any]] = None,
    usefulness_snapshot: Optional[dict[str, Any]] = None,
    classifications: Optional[Iterable[Any]] = None,
    reviews: Optional[Iterable[Any]] = None,
    confidence_threshold: float = 0.6,
    evaluated_at: Optional[datetime] = None,
) -> ContractReport:
    """Run every bounded invariant and return a ``ContractReport``.

    All inputs are optional. ``None`` means "not inspected in this
    run" -- informational, never a violation. This lets an operator
    call ``evaluate_contract()`` with only one surface available
    (e.g. just the status envelope) and still get a useful report.

    Args:
        status_envelope: The bounded health envelope the agent
            publishes to the engine.
        usefulness_snapshot: The bounded usefulness snapshot (the
            same dict, or the sub-envelope -- both shapes accepted).
        classifications: An iterable of ``ClassificationResult``
            (or anything with ``category`` / ``confidence`` /
            ``rationale`` attributes).
        reviews: An iterable of ``Review`` (or anything with the
            bounded dataclass fields).
        confidence_threshold: The classifier's documented
            fail-closed threshold. Defaults to 0.6 (the classifier
            module's ``CONFIDENCE_THRESHOLD``).
        evaluated_at: Override for tests. Defaults to ``datetime.now(UTC)``.

    Returns:
        A ``ContractReport`` with one ``ContractCheck`` per
        invariant in stable order.
    """
    if evaluated_at is None:
        evaluated_at = datetime.now(timezone.utc)

    checks: List[ContractCheck] = [
        check_status_envelope_authority(status_envelope),
        check_no_prompt_leakage(usefulness_snapshot),
        check_usefulness_counters_only(usefulness_snapshot),
        check_classifier_fail_closed(
            classifications, confidence_threshold=confidence_threshold
        ),
        check_review_non_authoritative(reviews),
    ]

    passed = all(c.passed for c in checks)

    return ContractReport(
        checks=checks,
        passed=passed,
        evaluated_at=evaluated_at,
    )


__all__ = [
    "STATUS_ENVELOPE_ALLOWED_KEYS",
    "USEFULNESS_ALLOWED_KEYS",
    "FORBIDDEN_REVIEW_DELTA_FIELDS",
    "ContractCheck",
    "ContractReport",
    "check_status_envelope_authority",
    "check_no_prompt_leakage",
    "check_usefulness_counters_only",
    "check_classifier_fail_closed",
    "check_review_non_authoritative",
    "evaluate_contract",
]
