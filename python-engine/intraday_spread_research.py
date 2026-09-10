"""Immutable reporting for conservative intraday-spread research evidence."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

from intraday_spread_replay import ReplayResult
from partner_manual_advisory import INTRADAY_POLICY_VERSION


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _date_from_result(result: ReplayResult) -> str:
    try:
        return date.fromisoformat(str(result.entry_at)[:10]).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError("each replay result requires an ISO entry_at") from exc


def create_research_run_manifest(*, dataset_sha256: str, code_revision: str,
                                 session_dates: Iterable[str], declared_min_sessions: int,
                                 declared_min_closed_trades: int, policy_groups: Mapping[str, Any]) -> dict:
    """Create the frozen pre-outcome configuration a runner must persist first."""
    if len(dataset_sha256) != 64 or any(char not in "0123456789abcdef" for char in dataset_sha256.lower()):
        raise ValueError("dataset_sha256 must be a SHA-256 hex digest")
    sessions = sorted(set(str(day) for day in session_dates if str(day)))
    if not code_revision.strip() or not sessions or declared_min_sessions < 1 or declared_min_closed_trades < 1:
        raise ValueError("code revision, session dates and positive thresholds are required")
    # Explicitly accept only date-shaped session claims.  The final artifact
    # checks them against replay clocks rather than trusting this input alone.
    for day in sessions:
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError("session_dates must be ISO dates") from exc
    manifest = {"format": "intraday_spread_run_manifest_v1", "policy_version": INTRADAY_POLICY_VERSION,
                "dataset_sha256": dataset_sha256.lower(), "code_revision": code_revision.strip(), "session_dates": sessions,
                "predeclared_acceptance": {"min_sessions": declared_min_sessions, "min_closed_trades": declared_min_closed_trades,
                                             "requires_no_unresolved_outcomes": True},
                "policy_groups": dict(policy_groups)}
    manifest["manifest_sha256"] = _sha(manifest)
    return manifest


def build_research_artifact(*, dataset_sha256: str, code_revision: str,
                            results: Iterable[ReplayResult], session_dates: Iterable[str],
                            declared_min_sessions: int, declared_min_closed_trades: int,
                            policy_groups: Mapping[str, Any] | None = None,
                            run_manifest: Mapping[str, Any] | None = None) -> dict:
    """Produce a deterministic report without qualification or order authority.

    A production runner should persist ``create_research_run_manifest`` before
    it begins.  Supplying the inputs directly remains supported for old offline
    reports, but is prominently marked as a legacy, non-precommitted artifact.
    """
    groups = dict(policy_groups or {"UNSPECIFIED": {}})
    expected_manifest = create_research_run_manifest(dataset_sha256=dataset_sha256, code_revision=code_revision,
        session_dates=session_dates, declared_min_sessions=declared_min_sessions,
        declared_min_closed_trades=declared_min_closed_trades, policy_groups=groups)
    manifest_state = "PREDECLARED_MANIFEST_VERIFIED"
    if run_manifest is not None:
        supplied = dict(run_manifest); supplied_hash = supplied.pop("manifest_sha256", None)
        if supplied_hash != _sha(supplied) or supplied_hash != expected_manifest["manifest_sha256"]:
            raise ValueError("run_manifest does not match frozen research configuration")
    else:
        manifest_state = "LEGACY_MANIFEST_NOT_PREPERSISTED"
    submitted = [asdict(result) for result in results]
    unique: list[dict[str, Any]] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    # ReplayResult is immutable, so evidence SHA is a stable opportunity id.
    for row in submitted:
        identity = str(row.get("evidence_sha256", ""))
        if len(identity) != 64:
            raise ValueError("each replay result requires a stable evidence_sha256")
        if identity in seen:
            duplicates.append(identity); continue
        seen.add(identity); unique.append(row)
    actual_sessions = sorted({_date_from_result(ReplayResult(**row)) for row in unique})
    if actual_sessions and actual_sessions != expected_manifest["session_dates"]:
        raise ValueError("declared session_dates do not match replay evidence")
    closed = [row for row in unique if row["state"] == "CLOSED" and row["net_pnl_rs"] is not None]
    no_fill = [row for row in unique if row["state"] == "NO_FILL"]
    unresolved = [row for row in unique if row["state"] == "UNRESOLVED"]
    rejected = [row for row in unique if row["state"] == "REJECTED"]
    pnls = [float(row["net_pnl_rs"]) for row in closed]
    net = round(sum(pnls), 4) if pnls else None
    expectancy = round(net / len(closed), 4) if closed else None
    running, peak, max_drawdown = 0.0, 0.0, 0.0
    for value in pnls:
        running += value; peak = max(peak, running); max_drawdown = min(max_drawdown, running - peak)
    sufficient = (len(actual_sessions) >= declared_min_sessions and len(closed) >= declared_min_closed_trades
                  and not unresolved and not duplicates and manifest_state == "PREDECLARED_MANIFEST_VERIFIED")
    deterministic = {"format": "intraday_spread_research_v2", "manifest": expected_manifest,
                     "manifest_state": manifest_state, "results": unique,
                     "duplicate_opportunity_ids": sorted(set(duplicates)), "actual_session_dates": actual_sessions,
                     "outcomes": {"submitted": len(submitted), "deduplicated": len(unique), "closed": len(closed),
                     "no_fill": len(no_fill), "unresolved": len(unresolved), "rejected": len(rejected),
                     "net_pnl_rs": net, "net_expectancy_rs": expectancy},
                     "risk": {"max_sequential_drawdown_rs": round(max_drawdown, 4), "unseen_session_behavior": "NOT_MEASURED",
                              "interval_uncertainty": "Execution is bounded by recorded bid/ask/depth; missing exits remain unresolved."},
                     "automatic_qualification": False, "can_place_orders": False}
    artifact = {**deterministic, "created_at": datetime.now(timezone.utc).isoformat(),
                "review_state": "READY_FOR_HUMAN_REVIEW" if sufficient else "INSUFFICIENT_EVIDENCE",
                "limitations": ["No automatic qualification, advice delivery, or order authority.",
                                "Results are only as complete as archived quote coverage and immutable master provenance."]}
    artifact["evidence_sha256"] = _sha(deterministic)
    artifact["artifact_sha256"] = artifact["evidence_sha256"]  # compatibility alias; excludes report timestamp
    return artifact


def render_research_summary(artifact: dict) -> str:
    outcomes = artifact["outcomes"]
    return (f"Intraday debit-spread replay: {artifact['review_state']}. Sessions={len(artifact['actual_session_dates'])}; "
            f"closed={outcomes['closed']}; no-fill={outcomes['no_fill']}; unresolved={outcomes['unresolved']}; "
            f"net expectancy={outcomes['net_expectancy_rs']}. This is research evidence, not a delivery or order permission.")
