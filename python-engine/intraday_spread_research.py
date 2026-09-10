"""Immutable reporting for exact-policy intraday spread replay evidence."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Iterable

from intraday_spread_replay import ReplayResult
from partner_manual_advisory import INTRADAY_POLICY_VERSION


def build_research_artifact(*, dataset_sha256: str, code_revision: str,
                            results: Iterable[ReplayResult], session_dates: Iterable[str],
                            declared_min_sessions: int, declared_min_closed_trades: int) -> dict:
    """Freeze a report without treating a positive outcome as qualification.

    Thresholds are recorded before review.  This helper only reports whether
    evidence is sufficient for human review; it never invokes the qualification
    registry or changes advice delivery.
    """
    if len(dataset_sha256) != 64 or any(char not in "0123456789abcdef" for char in dataset_sha256.lower()):
        raise ValueError("dataset_sha256 must be a SHA-256 hex digest")
    if not code_revision.strip() or declared_min_sessions < 1 or declared_min_closed_trades < 1:
        raise ValueError("code revision and positive declared thresholds are required")
    frozen = [asdict(result) for result in results]
    sessions = sorted(set(str(day) for day in session_dates if str(day)))
    closed = [row for row in frozen if row["state"] == "CLOSED" and row["net_pnl_rs"] is not None]
    no_fill = [row for row in frozen if row["state"] == "NO_FILL"]
    unresolved = [row for row in frozen if row["state"] == "UNRESOLVED"]
    net = round(sum(float(row["net_pnl_rs"]) for row in closed), 4) if closed else None
    expectancy = round(net / len(closed), 4) if closed else None
    sufficient = len(sessions) >= declared_min_sessions and len(closed) >= declared_min_closed_trades and not unresolved
    payload = {"format": "intraday_spread_research_v1", "created_at": datetime.now(timezone.utc).isoformat(),
               "policy_version": INTRADAY_POLICY_VERSION, "dataset_sha256": dataset_sha256,
               "code_revision": code_revision, "session_dates": sessions,
               "predeclared_acceptance": {"min_sessions": declared_min_sessions, "min_closed_trades": declared_min_closed_trades,
                                           "requires_no_unresolved_outcomes": True},
               "outcomes": {"submitted": len(frozen), "closed": len(closed), "no_fill": len(no_fill),
                            "unresolved": len(unresolved), "net_pnl_rs": net, "net_expectancy_rs": expectancy},
               "review_state": "READY_FOR_HUMAN_REVIEW" if sufficient else "INSUFFICIENT_EVIDENCE",
               "automatic_qualification": False, "can_place_orders": False,
               "limitations": ["Uses conservative two-leg executable quote assumptions.",
                               "No-fill and unresolved observations are retained, not optimised away.",
                               "A human review and separate registry action are required for any qualification."],
               "results": frozen}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["artifact_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return payload


def render_research_summary(artifact: dict) -> str:
    """Plain language summary that does not imply a profit or promotion claim."""
    outcomes = artifact["outcomes"]
    return (f"Intraday debit-spread replay: {artifact['review_state']}. "
            f"Sessions={len(artifact['session_dates'])}; closed={outcomes['closed']}; "
            f"no-fill={outcomes['no_fill']}; unresolved={outcomes['unresolved']}; "
            f"net expectancy={outcomes['net_expectancy_rs']}. "
            "This is research evidence, not a delivery or order permission.")
