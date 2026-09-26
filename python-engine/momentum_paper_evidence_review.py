"""Read-only exact-key review of momentum paper and paired exit evidence.

The module intentionally has no runtime caller.  It binds a Phase-1 exit
study to the Phase-2 lifecycle audit only when the input packet names the same
opaque admission key stored with the paper position and ledger cash rows.
Ticker/time similarity is not a fallback identity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from momentum_exit_study import ExitStudyError, build_momentum_exit_study
from momentum_paper_audit import MomentumPaperAuditError, build_momentum_paper_decision_audit


SCHEMA = "momentum_paper_evidence_review_v1"


class MomentumPaperEvidenceReviewError(ValueError):
    """The review request is invalid; neither evidence source is modified."""


def _canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _round(value: float | None, digits: int = 6) -> float | None:
    return round(float(value), digits) if value is not None else None


def _review_pair(pair: dict[str, Any], *, audit_status: str,
                 by_key: dict[str, dict[str, Any]], duplicate_keys: set[str]) -> dict[str, Any]:
    key = pair.get("admission_key")
    base = {
        "entry_id": pair.get("entry_id"),
        "admission_key": key,
        "ticker": pair.get("ticker"),
        "exit_path_status": pair.get("status"),
        "exit_path_reason": pair.get("reason"),
        "baseline": pair.get("baseline"),
        "alternative": pair.get("alternative"),
    }
    if key is None:
        return {**base, "state": "UNAVAILABLE_ADMISSION_KEY_MISSING", "lifecycle": None}
    if key in duplicate_keys:
        return {**base, "state": "UNRESOLVED_DUPLICATE_ADMISSION_KEY", "lifecycle": None}
    if audit_status == "UNAVAILABLE":
        return {**base, "state": "UNAVAILABLE_LIFECYCLE_AUDIT", "lifecycle": None}
    lifecycle = by_key.get(str(key))
    if lifecycle is None:
        return {**base, "state": "UNRESOLVED_ADMISSION_NOT_FOUND", "lifecycle": None}
    if lifecycle.get("ticker") != pair.get("ticker"):
        return {**base, "state": "UNRESOLVED_TICKER_MISMATCH", "lifecycle": lifecycle}
    if lifecycle.get("outcome") != "opened":
        return {**base, "state": "UNRESOLVED_NONOPENED_ADMISSION", "lifecycle": lifecycle}
    if pair.get("status") != "COMPLETE":
        return {**base, "state": "INSUFFICIENT_EXIT_PATH", "lifecycle": lifecycle}
    if lifecycle.get("lifecycle") != "CLOSED" or lifecycle.get("cash", {}).get("state") != "MATCH":
        return {**base, "state": "UNRESOLVED_LIFECYCLE", "lifecycle": lifecycle}
    return {**base, "state": "COMPLETE", "lifecycle": lifecycle}


def build_momentum_paper_evidence_review(
    db_path: str, study_input_path: str, *, limit: int = 1000,
) -> dict[str, Any]:
    """Build a deterministic in-memory review without writing any evidence.

    ``db_path`` is passed to Phase 2's SQLite URI read-only audit.  The study
    input is read by the Phase 1 parser.  This function never creates a DB,
    output file, cache, network request, broker order or notification.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20_000:
        raise MomentumPaperEvidenceReviewError("limit must be an integer from 1 through 20000")
    audit = build_momentum_paper_decision_audit(db_path, limit=limit)
    try:
        exit_study = build_momentum_exit_study(study_input_path)
    except ExitStudyError as exc:
        raise MomentumPaperEvidenceReviewError(f"exit study input is invalid: {exc}") from exc

    opportunities = audit.get("opportunities", [])
    by_key = {
        str(row["admission_key"]): row
        for row in opportunities
        if isinstance(row, dict) and isinstance(row.get("admission_key"), str)
    }
    seen: set[str] = set()
    duplicate_keys: set[str] = set()
    for pair in exit_study["pairs"]:
        key = pair.get("admission_key")
        if isinstance(key, str):
            if key in seen:
                duplicate_keys.add(key)
            seen.add(key)
    reviewed = [_review_pair(pair, audit_status=str(audit.get("status")),
                              by_key=by_key, duplicate_keys=duplicate_keys)
                for pair in exit_study["pairs"]]
    complete = [row for row in reviewed if row["state"] == "COMPLETE"]
    deltas = [
        float(row["alternative"]["net_pnl"]) - float(row["baseline"]["net_pnl"])
        for row in complete
        if row["baseline"].get("status") == "CLOSED"
        and row["alternative"].get("status") == "CLOSED"
        and row["baseline"].get("net_pnl") is not None
        and row["alternative"].get("net_pnl") is not None
    ]
    review_status = "COMPLETE" if audit.get("status") == "COMPLETE" and len(complete) == len(reviewed) else "PARTIAL"
    return {
        "schema": SCHEMA,
        "status": review_status,
        "qualification": "NOT_ASSESSED",
        "authority": {"research_only": True, "can_place_orders": False, "authorization_effect": "NONE"},
        "lifecycle_audit": {
            "schema": audit.get("schema"), "status": audit.get("status"),
            "reason": audit.get("reason"), "truncated": audit.get("truncated"),
            "schema_availability": audit.get("schema_availability"),
        },
        "exit_study": {
            "schema": exit_study["schema"], "study_id": exit_study["study_id"],
            "input_fingerprint": exit_study["input_fingerprint"],
            "report_fingerprint": exit_study["report_fingerprint"],
        },
        "summary": {
            "submitted_pairs": len(reviewed), "complete_exact_lifecycles": len(complete),
            "unavailable_or_unresolved_pairs": len(reviewed) - len(complete),
            "paired_alternative_minus_baseline_net_pnl": _round(sum(deltas)) if deltas else None,
            "paired_delta_count": len(deltas),
        },
        "pairs": reviewed,
        "warning": "Read-only diagnostic linkage, not a profitability, qualification, promotion, advice, or order verdict.",
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only momentum-paper evidence review")
    parser.add_argument("--db", required=True, help="existing SQLite database")
    parser.add_argument("--input", required=True, help="Phase-1 exit-study input packet")
    parser.add_argument("--limit", type=int, default=1000, help="admission rows to inspect (1..20000)")
    args = parser.parse_args(argv)
    try:
        print(_canonical(build_momentum_paper_evidence_review(args.db, args.input, limit=args.limit)))
    except (MomentumPaperEvidenceReviewError, MomentumPaperAuditError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
