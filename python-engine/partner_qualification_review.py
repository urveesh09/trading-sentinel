"""Predeclared, human-reviewed qualification package assembly.

The package binds a frozen full-policy manifest to chronological held-out
outcomes.  It never writes the delivery qualification registry and therefore
cannot turn a favorable diagnostic into advice authority.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, asdict
from typing import Any, Mapping


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class QualificationCriteria:
    policy_manifest_sha256: str
    min_covered_sessions: int
    min_closed_outcomes: int
    max_unresolved_outcomes: int
    max_drawdown_rs: float
    stressed_fee_multiplier: float
    stressed_slippage_bps: float

    def validate(self) -> None:
        if len(self.policy_manifest_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.policy_manifest_sha256.lower()):
            raise ValueError("criteria requires a full-policy manifest digest")
        if self.min_covered_sessions < 1 or self.min_closed_outcomes < 1 or self.max_unresolved_outcomes < 0:
            raise ValueError("qualification sample criteria are invalid")
        if (not math.isfinite(self.max_drawdown_rs) or self.max_drawdown_rs >= 0
                or self.stressed_fee_multiplier < 1 or self.stressed_slippage_bps < 0):
            raise ValueError("qualification risk/cost criteria are invalid")


def build_qualification_review_package(*, policy_manifest: Mapping[str, Any], criteria: QualificationCriteria,
                                       heldout_report: Mapping[str, Any], readiness: Mapping[str, Any]) -> dict[str, Any]:
    """Build a per-index review package with visible non-qualification states."""
    criteria.validate()
    claimed = policy_manifest.get("manifest_sha256")
    if claimed != criteria.policy_manifest_sha256:
        raise ValueError("criteria does not match frozen full-policy manifest")
    if policy_manifest.get("evaluator") != "partner_manual_intraday_full_policy_v1":
        raise ValueError("only the complete deployed-policy manifest may be reviewed")
    if heldout_report.get("automatic_qualification") is not False:
        raise ValueError("heldout report must not claim automatic qualification")
    groups = heldout_report.get("groups")
    if not isinstance(groups, list):
        raise ValueError("heldout report groups are required")
    per_index = []
    for group in groups:
        if not isinstance(group, Mapping) or group.get("underlying") not in {"NIFTY", "SENSEX"}:
            raise ValueError("review package contains an unsupported index group")
        covered = sum(value == "OBSERVED" for value in (group.get("coverage") or {}).values())
        closed, unresolved = int(group.get("closed", 0)), int(group.get("unresolved", 0))
        net = float(group.get("net_pnl_rs", 0.0))
        # The heldout report may include individual P&Ls only in an attached
        # immutable report. Never fabricate a drawdown from its aggregate.
        drawdown_state = "REQUIRES_ORDERED_OUTCOMES"
        blockers = []
        if covered < criteria.min_covered_sessions:
            blockers.append("heldout_session_coverage_insufficient")
        if closed < criteria.min_closed_outcomes:
            blockers.append("closed_outcome_sample_insufficient")
        if unresolved > criteria.max_unresolved_outcomes:
            blockers.append("unresolved_outcomes_exceed_limit")
        if group.get("unavailable", 0):
            blockers.append("declared_holdout_coverage_unavailable")
        if not math.isfinite(net):
            blockers.append("nonfinite_net_outcome")
        per_index.append({"underlying": group["underlying"], "policy_id": group.get("policy_id"),
                          "covered_sessions": covered, "closed_outcomes": closed, "unresolved_outcomes": unresolved,
                          "net_pnl_rs": net, "drawdown_state": drawdown_state, "blockers": blockers,
                          "review_state": "READY_FOR_HUMAN_REVIEW" if not blockers else "INSUFFICIENT_EVIDENCE"})
    readiness_view = {
        "collection": readiness.get("collection", "UNKNOWN"),
        "causal_research": readiness.get("causal_research", "UNKNOWN"),
        "outcome_coverage": readiness.get("outcome_coverage", "UNKNOWN"),
        "reviewed_qualification": "HUMAN_REVIEW_REQUIRED",
        "telegram_routing": readiness.get("telegram_routing", "UNKNOWN"),
    }
    deterministic = {"format": "partner_qualification_review_v1", "policy_manifest_sha256": claimed,
                     "criteria": asdict(criteria), "heldout_evidence_sha256": heldout_report.get("evidence_sha256"),
                     "per_index": per_index, "readiness": readiness_view,
                     "automatic_qualification": False, "can_send_advice": False, "can_place_orders": False,
                     "limitations": ["A human must review ordered outcomes, cost stress and drawdown before registry promotion.",
                                     "A review package cannot authorize a policy whose manifest changes."]}
    return {**deterministic, "evidence_sha256": _sha(deterministic),
            "review_state": "HUMAN_REVIEW_REQUIRED" if any(row["review_state"] == "READY_FOR_HUMAN_REVIEW" for row in per_index)
            else "INSUFFICIENT_EVIDENCE"}
