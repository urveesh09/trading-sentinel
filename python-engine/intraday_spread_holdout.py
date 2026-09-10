"""Frozen per-index/policy held-out summaries for chronological spread replay."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from intraday_spread_chronological import ChronologicalReplay


@dataclass(frozen=True)
class HeldOutCase:
    underlying: str
    policy_id: str
    session_date: str
    replay: ChronologicalReplay


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def build_heldout_comparison(*, dataset_sha256: str, code_revision: str,
                             training_sessions: Iterable[str], holdout_sessions: Iterable[str],
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
    submitted = list(cases)
    seen: set[str] = set()
    groups: dict[str, dict] = {}
    for case in submitted:
        if case.underlying not in {"NIFTY", "SENSEX"} or not case.policy_id or case.session_date not in holdout:
            raise ValueError("case does not belong to declared NIFTY/SENSEX holdout session")
        key = f"{case.underlying}:{case.policy_id}"
        if case.replay.evidence_sha256 in seen:
            raise ValueError("duplicate chronological evidence identity")
        seen.add(case.replay.evidence_sha256)
        bucket = groups.setdefault(key, {"underlying": case.underlying, "policy_id": case.policy_id,
                                         "sessions": [], "closed": 0, "no_fill": 0, "unresolved": 0, "net_pnl_rs": 0.0,
                                         "evidence_ids": []})
        bucket["sessions"].append(case.session_date); bucket["evidence_ids"].append(case.replay.evidence_sha256)
        if case.replay.state == "CLOSED":
            bucket["closed"] += 1; bucket["net_pnl_rs"] += float(case.replay.result.net_pnl_rs or 0)
        elif case.replay.state == "NO_FILL":
            bucket["no_fill"] += 1
        else:
            bucket["unresolved"] += 1
    for bucket in groups.values():
        bucket["sessions"] = sorted(set(bucket["sessions"])); bucket["evidence_ids"].sort()
        bucket["net_pnl_rs"] = round(bucket["net_pnl_rs"], 4)
        bucket["expectancy_rs"] = round(bucket["net_pnl_rs"] / bucket["closed"], 4) if bucket["closed"] else None
    deterministic = {"format": "intraday_spread_heldout_v1", "dataset_sha256": dataset_sha256.lower(),
                     "code_revision": code_revision.strip(), "training_sessions": train, "holdout_sessions": holdout,
                     "groups": [groups[key] for key in sorted(groups)], "case_count": len(submitted),
                     "automatic_qualification": False, "can_place_orders": False,
                     "limitations": ["A held-out summary is not evidence of future profitability.",
                                     "External collection coverage and unresolved exits must be reviewed by a human."]}
    return {**deterministic, "evidence_sha256": _digest(deterministic), "review_state": "HUMAN_REVIEW_REQUIRED"}
