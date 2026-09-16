"""[WORKFLOW-C.B1 2026-09-15] Held-out evidence adequacy diagnostic.

Per the 2026-09-15 production deep audit B-1:
> 6. **Adequate genuine held-out evidence.** Need real production
> sessions with non-tampered captures. Per inheritance doc §11
> and AGENTS.md: this requires the operator to run the J.3 capture
> review happy-path under live conditions.

The plan doc's acceptance criterion for held-out evidence is:
> "two unmocked archived sessions containing one finite costed
> close and one unresolved outcome"

So a held-out sample is "ADEQUATE" iff it contains AT LEAST:
  - 1 CLOSED case (finite costed close with measurable P&L).
  - 1 UNRESOLVED case (no fill, ambiguous exit, or non-closed).

This module is a BOUNDED diagnostic. It does NOT collect
sessions or run live Kite calls -- that requires the operator
to run the J.3 capture review happy-path under live conditions.
The diagnostic ONLY inspects an existing ``build_heldout_comparison``
report and returns a verdict.

The verdict is fail-closed: if any threshold is unmet, the
diagnostic returns ``INADEQUATE`` with a list of unmet
thresholds. Callers (the operator, future automation) can use
this to decide whether to ship a qualification decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Sequence

AdequacyVerdict = Literal["ADEQUATE", "INADEQUATE"]


@dataclass(frozen=True)
class AdequacyThresholds:
    """Minimum held-out evidence thresholds.

    Defaults are the plan doc's acceptance criterion: at least
    1 CLOSED + 1 UNRESOLVED case across the held-out groups.
    Operators can override via the constructor.
    """
    min_closed: int = 1
    min_unresolved: int = 1
    # NO_FILL is informational; no minimum required.
    # But it's surfaced in the diagnostic for completeness.
    min_no_fill: int = 0
    # At least one case must have verified full-policy cost
    # evidence (cost_sensitivity is not None).
    require_full_policy_evidence: bool = True


@dataclass(frozen=True)
class HeldOutAdequacy:
    """The diagnostic verdict for a held-out comparison report.

    Attributes:
        verdict: ADEQUATE or INADEQUATE.
        total_closed: aggregate closed count across all groups.
        total_unresolved: aggregate unresolved count.
        total_no_fill: aggregate no_fill count.
        total_evaluated: aggregate evaluated count.
        unmet_thresholds: list of human-readable unmet
            threshold descriptions (empty when ADEQUATE).
        per_group_counts: per-group breakdown.
        thresholds: the thresholds that were applied.
    """
    verdict: AdequacyVerdict
    total_closed: int
    total_unresolved: int
    total_no_fill: int
    total_evaluated: int
    unmet_thresholds: tuple[str, ...]
    per_group_counts: tuple[dict, ...]
    thresholds: AdequacyThresholds = field(default_factory=AdequacyThresholds)


def evaluate_heldout_adequacy(
    report: Mapping,
    *,
    thresholds: AdequacyThresholds | None = None,
) -> HeldOutAdequacy:
    """Evaluate whether a held-out comparison report meets
    the adequacy thresholds for qualification review.

    Args:
        report: a dict returned by ``build_heldout_comparison``.
            Must have a ``groups`` key (list of per-group dicts).
        thresholds: optional override of the default minimums.
            None uses the plan-doc defaults (1 closed + 1 unresolved).

    Returns:
        HeldOutAdequacy with the verdict and breakdown.
    """
    if thresholds is None:
        thresholds = AdequacyThresholds()
    if "groups" not in report:
        raise ValueError("report must have a 'groups' field")
    groups = report.get("groups")
    if not isinstance(groups, list):
        raise ValueError("report must have a list-valued 'groups' field")

    per_group: list[dict] = []
    total_closed = 0
    total_unresolved = 0
    total_no_fill = 0
    total_evaluated = 0
    full_policy_evidence_present = False

    for bucket in groups:
        if not isinstance(bucket, Mapping):
            continue
        closed = int(bucket.get("closed", 0))
        no_fill = int(bucket.get("no_fill", 0))
        unresolved = int(bucket.get("unresolved", 0))
        evaluated = int(bucket.get("evaluated", 0))
        # ``cost_sensitivity`` is per-bucket; a non-empty list
        # means verified full-policy cost evidence was attached
        # for at least one case in this bucket.
        cost_sensitivity = bucket.get("cost_sensitivity", [])
        if cost_sensitivity:
            full_policy_evidence_present = True
        per_group.append({
            "underlying": bucket.get("underlying"),
            "policy_id": bucket.get("policy_id"),
            "closed": closed,
            "no_fill": no_fill,
            "unresolved": unresolved,
            "evaluated": evaluated,
            "cost_sensitivity_count": len(cost_sensitivity) if isinstance(cost_sensitivity, list) else 0,
        })
        total_closed += closed
        total_unresolved += unresolved
        total_no_fill += no_fill
        total_evaluated += evaluated

    unmet: list[str] = []
    if total_closed < thresholds.min_closed:
        unmet.append(
            f"closed={total_closed} < min_closed={thresholds.min_closed}"
        )
    if total_unresolved < thresholds.min_unresolved:
        unmet.append(
            f"unresolved={total_unresolved} < min_unresolved={thresholds.min_unresolved}"
        )
    if total_no_fill < thresholds.min_no_fill:
        unmet.append(
            f"no_fill={total_no_fill} < min_no_fill={thresholds.min_no_fill}"
        )
    if thresholds.require_full_policy_evidence and not full_policy_evidence_present:
        unmet.append(
            "no verified full-policy cost evidence attached to any group"
        )
    if total_evaluated == 0:
        unmet.append("evaluated=0 (no opportunities recorded in any group)")

    verdict: AdequacyVerdict = "ADEQUATE" if not unmet else "INADEQUATE"
    return HeldOutAdequacy(
        verdict=verdict,
        total_closed=total_closed,
        total_unresolved=total_unresolved,
        total_no_fill=total_no_fill,
        total_evaluated=total_evaluated,
        unmet_thresholds=tuple(unmet),
        per_group_counts=tuple(per_group),
        thresholds=thresholds,
    )


def format_adequacy(adequacy: HeldOutAdequacy) -> str:
    """Render an adequacy diagnostic as a human-readable table."""
    lines = [
        "# Held-out evidence adequacy diagnostic",
        "# -------------------------------------",
        f"# Verdict: {adequacy.verdict}",
        f"# Total closed:    {adequacy.total_closed}",
        f"# Total unresolved:{adequacy.total_unresolved}",
        f"# Total no_fill:   {adequacy.total_no_fill}",
        f"# Total evaluated: {adequacy.total_evaluated}",
        "",
        "# Per-group breakdown:",
        f"{'UNDERLYING':<10}  {'POLICY':<30}  {'CLOSED':<8}  {'NO_FILL':<8}  {'UNRESOLVED':<12}  {'EVAL':<6}  CS",
        f"{'-' * 10}  {'-' * 30}  {'-' * 8}  {'-' * 8}  {'-' * 12}  {'-' * 6}  --",
    ]
    for row in adequacy.per_group_counts:
        lines.append(
            f"{str(row['underlying']):<10}  {str(row['policy_id']):<30}  "
            f"{row['closed']:<8}  {row['no_fill']:<8}  {row['unresolved']:<12}  "
            f"{row['evaluated']:<6}  {row['cost_sensitivity_count']}"
        )
    if adequacy.unmet_thresholds:
        lines.append("")
        lines.append("# Unmet thresholds:")
        for item in adequacy.unmet_thresholds:
            lines.append(f"  - {item}")
    return "\n".join(lines) + "\n"


__all__ = [
    "AdequacyThresholds",
    "AdequacyVerdict",
    "HeldOutAdequacy",
    "evaluate_heldout_adequacy",
    "format_adequacy",
]
