"""Frozen per-index/policy held-out summaries for chronological spread replay."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from dataclasses import dataclass
from typing import Iterable

from intraday_spread_chronological import ChronologicalReplay


@dataclass(frozen=True)
class HeldOutCase:
    underlying: str
    policy_id: str
    session_date: str
    replay: ChronologicalReplay
    # Stable upstream identity, not a rendered report/evidence hash.  It binds
    # the case to its selected opportunity before holdout aggregation.
    opportunity_id: str
    signal_artifact_sha256: str


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def build_heldout_comparison(*, dataset_sha256: str, code_revision: str,
                              training_sessions: Iterable[str], holdout_sessions: Iterable[str],
                              declared_coverage: Iterable[tuple[str, str, str]],
                              cases: Iterable[HeldOutCase]) -> dict:
    """Summarise pre-separated sessions without selecting a winning policy.

    The result never auto-qualifies.  Empty/no-fill/unresolved sessions remain
    in their group counts, which prevents an attractive subset of closed
    outcomes from standing in for all collected opportunities.
    """
    if len(dataset_sha256) != 64 or any(char not in "0123456789abcdef" for char in dataset_sha256.lower()):
        raise ValueError("dataset_sha256 must be a SHA-256 hex digest")
    train, holdout = sorted(set(training_sessions)), sorted(set(holdout_sessions))
    if not code_revision.strip() or not train or not holdout or set(train) & set(holdout):
        raise ValueError("non-overlapping non-empty training and holdout sessions are required")
    try:
        if max(date.fromisoformat(day) for day in train) >= min(date.fromisoformat(day) for day in holdout):
            raise ValueError("training sessions must precede all holdout sessions")
    except ValueError as exc:
        if str(exc) == "training sessions must precede all holdout sessions":
            raise
        raise ValueError("training and holdout sessions must be ISO dates") from exc
    declared = sorted(set(declared_coverage))
    if not declared or any(index not in {"NIFTY", "SENSEX"} or not policy or day not in holdout
                           for index, policy, day in declared):
        raise ValueError("declared coverage must name NIFTY/SENSEX policy and holdout session")
    submitted = list(cases)
    seen_evidence: set[str] = set()
    seen_opportunities: set[tuple[str, str, str, str]] = set()
    groups: dict[str, dict] = {}
    for index, policy, day in declared:
        key = f"{index}:{policy}"
        groups.setdefault(key, {"underlying": index, "policy_id": policy,
                                "sessions": [], "coverage": {}, "closed": 0, "no_fill": 0,
                                "unresolved": 0, "unavailable": 0, "net_pnl_rs": 0.0,
                                "evidence_ids": [], "opportunity_ids": [], "signal_artifact_ids": []})["coverage"].setdefault(day, "UNAVAILABLE")
    for case in submitted:
        if ((case.underlying, case.policy_id, case.session_date) not in declared
                or not case.opportunity_id or len(case.signal_artifact_sha256) != 64):
            raise ValueError("case does not belong to declared NIFTY/SENSEX holdout session")
        key = f"{case.underlying}:{case.policy_id}"
        stable_identity = (case.underlying, case.policy_id, case.session_date, case.opportunity_id)
        if case.replay.evidence_sha256 in seen_evidence or stable_identity in seen_opportunities:
            raise ValueError("duplicate chronological evidence identity")
        seen_evidence.add(case.replay.evidence_sha256); seen_opportunities.add(stable_identity)
        bucket = groups[key]
        state = case.replay.state
        # A session may contain multiple independent candidate decisions.  The
        # matrix tracks whether it was observed; outcome counts preserve every
        # attempted opportunity rather than discarding later losses/no-fills.
        bucket["coverage"][case.session_date] = "OBSERVED"
        bucket["sessions"].append(case.session_date); bucket["evidence_ids"].append(case.replay.evidence_sha256)
        bucket["opportunity_ids"].append(case.opportunity_id); bucket["signal_artifact_ids"].append(case.signal_artifact_sha256.lower())
        if case.replay.state == "CLOSED":
            pnl = case.replay.result.net_pnl_rs
            if pnl is None or not math.isfinite(float(pnl)):
                raise ValueError("closed heldout replay requires finite net P&L")
            bucket["closed"] += 1; bucket["net_pnl_rs"] += float(pnl)
        elif case.replay.state == "NO_FILL":
            bucket["no_fill"] += 1
        elif case.replay.state == "UNRESOLVED":
            bucket["unresolved"] += 1
        else:
            raise ValueError("heldout replay has an unsupported state")
    for bucket in groups.values():
        bucket["unavailable"] = sum(state == "UNAVAILABLE" for state in bucket["coverage"].values())
        bucket["sessions"] = sorted(set(bucket["sessions"])); bucket["evidence_ids"].sort(); bucket["opportunity_ids"].sort()
        bucket["signal_artifact_ids"] = sorted(set(bucket["signal_artifact_ids"]))
        bucket["net_pnl_rs"] = round(bucket["net_pnl_rs"], 4)
        evaluated = bucket["closed"] + bucket["no_fill"] + bucket["unresolved"]
        bucket["evaluated"] = evaluated
        bucket["expectancy_rs"] = round(bucket["net_pnl_rs"] / evaluated, 4) if evaluated else None
    deterministic = {"format": "intraday_spread_heldout_v1", "dataset_sha256": dataset_sha256.lower(),
                     "code_revision": code_revision.strip(), "training_sessions": train, "holdout_sessions": holdout,
                      "groups": [groups[key] for key in sorted(groups)], "case_count": len(submitted),
                      "declared_coverage": [{"underlying": index, "policy_id": policy, "session_date": day}
                                            for index, policy, day in declared],
                     "automatic_qualification": False, "can_place_orders": False,
                     "limitations": ["A held-out summary is not evidence of future profitability.",
                                     "External collection coverage and unresolved exits must be reviewed by a human."]}
    return {**deterministic, "evidence_sha256": _digest(deterministic), "review_state": "HUMAN_REVIEW_REQUIRED"}
