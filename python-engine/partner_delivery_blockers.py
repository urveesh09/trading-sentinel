"""Read-only per-candidate partner delivery-blocker diagnostic (S5c).

Explains, for every persisted manual-advisory idea, why it was or was not
delivered: validation reasons, evidence class, qualification registry match at
decision time, delivery reasons and terminal status.  It also summarises the
separate collection-attempt journal per IST session/index.

Contract:
- SQLite is opened with ``mode=ro``; a missing database is reported as
  unavailable and is never created.  Nothing is written, registered,
  qualified, sent or ordered.  No network, broker or message imports.
- Attempts and ideas share no exact identity, so they are compared only as
  per-session/index aggregates and a disagreement is labelled as such rather
  than attributed to a specific candidate.
- Qualification rows are reported as registry facts only; this diagnostic does
  not re-verify authorization packages and never claims a strategy is qualified.
- Current delivery flags are a projection of *today's* configuration, never a
  claim about the configuration when a historical idea was evaluated.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
REPORT_FORMAT = "partner_delivery_blocker_report_v1"
QUALIFIED_EVIDENCE = "QUALIFIED_FOR_ADVISORY"
DELIVERED_STATUS = "DELIVERED_ACKNOWLEDGED"
_STATUS_BLOCKERS = {
    "VALIDATED_SHADOW": None,  # explained by evidence/qualification/delivery reasons
    "REJECTED": None,  # explained by validation reasons
    "QUEUED": "QUEUED_NOT_DISPATCHED",
    "SUPERSEDED_MARKET": "SUPERSEDED_BY_NEWER_MARKET_VERSION",
    "SUPERSEDED_PROFILE": "SUPERSEDED_BY_PROFILE_CHANGE",
    "RETIRED_SESSION_END": "RETIRED_AT_SESSION_END",
}


def _open_read_only(path: Optional[str | Path]) -> Tuple[Optional[sqlite3.Connection], Optional[str]]:
    if path is None:
        return None, "not_supplied"
    resolved = Path(path)
    if not resolved.is_file():
        return None, "database_missing"
    try:
        connection = sqlite3.connect(resolved.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0)
        connection.row_factory = sqlite3.Row
        return connection, None
    except sqlite3.Error as exc:
        return None, f"open_failed:{type(exc).__name__}"


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _in_window(day: Optional[str], session_from: Optional[date], session_to: Optional[date]) -> bool:
    if day is None:
        return session_from is None and session_to is None
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        return False
    return (session_from is None or parsed >= session_from) and (session_to is None or parsed <= session_to)


def _ist_day(timestamp: Optional[str]) -> Optional[str]:
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(IST).date().isoformat()


def candidate_blockers(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the ordered delivery blockers for one persisted idea row."""
    status = str(row.get("status") or "")
    evidence = str(row.get("evidence") or "")
    try:
        payload = json.loads(row.get("payload") or "{}")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
    except (TypeError, ValueError):
        return {"delivered": False, "primary_blocker": "MALFORMED_PAYLOAD",
                "blockers": ["MALFORMED_PAYLOAD"], "status": status}
    blockers: List[str] = []
    validation = [str(reason) for reason in payload.get("validation_reasons") or []]
    blockers.extend(f"VALIDATION:{reason}" for reason in validation)
    if status != DELIVERED_STATUS:
        if evidence != QUALIFIED_EVIDENCE:
            blockers.append(f"EVIDENCE:{evidence or 'MISSING'}")
        if not payload.get("qualification_registry_match"):
            blockers.append("NO_CURRENT_QUALIFICATION_AT_DECISION")
        for reason in payload.get("delivery_reasons") or []:
            if str(reason) not in validation:
                blockers.append(f"DELIVERY:{reason}")
        status_blocker = _STATUS_BLOCKERS.get(status, f"STATUS:{status or 'MISSING'}")
        if status_blocker:
            blockers.append(status_blocker)
        if not blockers:
            # A non-delivered idea without any retained reason is itself a finding.
            blockers.append("UNEXPLAINED_NOT_DELIVERED")
    return {
        "delivered": status == DELIVERED_STATUS,
        "primary_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "status": status,
    }


def _idea_rows(connection: sqlite3.Connection, session_from, session_to) -> List[Dict[str, Any]]:
    rows = connection.execute(
        "SELECT advisory_id, underlying, scope, status, evidence, profile_id, created_at, "
        "valid_until, payload FROM partner_advisory_ideas ORDER BY created_at, advisory_id"
    ).fetchall()
    ideas = []
    for row in rows:
        record = dict(row)
        try:
            payload = json.loads(record.get("payload") or "{}")
        except (TypeError, ValueError):
            payload = {}
        session = (payload.get("session_date") if isinstance(payload, dict) else None) or _ist_day(record["created_at"])
        if not _in_window(session, session_from, session_to):
            continue
        explained = candidate_blockers(record)
        ideas.append({
            "advisory_id": record["advisory_id"], "underlying": record["underlying"],
            "scope": record["scope"], "session_date": session, "created_at": record["created_at"],
            "valid_until": record["valid_until"], "profile_id": record["profile_id"],
            "evidence": record["evidence"], **explained,
        })
    return ideas


def _attempt_summary(connection: sqlite3.Connection, session_from, session_to) -> Dict[str, Dict[str, Any]]:
    rows = connection.execute(
        "SELECT underlying, tick_started_at_utc, candidate_state, terminal_state, terminal_reason "
        "FROM partner_collection_attempts"
    ).fetchall()
    summary: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        session = _ist_day(row["tick_started_at_utc"])
        if not _in_window(session, session_from, session_to):
            continue
        key = f"{session}:{row['underlying']}"
        bucket = summary.setdefault(key, {"attempts": 0, "terminal": Counter(), "terminal_reasons": Counter()})
        bucket["attempts"] += 1
        bucket["terminal"][str(row["terminal_state"])] += 1
        bucket["terminal_reasons"][f"{row['terminal_state']}:{row['terminal_reason'] or ''}"] += 1
    return {key: {"attempts": value["attempts"], "terminal": dict(sorted(value["terminal"].items())),
                  "terminal_reasons": dict(sorted(value["terminal_reasons"].items()))}
            for key, value in sorted(summary.items())}


def _qualification_rows(connection: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = connection.execute(
        "SELECT underlying, structure_kind, horizon, policy_version, status, reviewed_at "
        "FROM partner_advisory_strategy_qualifications ORDER BY underlying, structure_kind"
    ).fetchall()
    return [dict(row) for row in rows]


def build_delivery_blocker_report(
    *, db_path: str | Path, attempts_path: Optional[str | Path] = None,
    session_from: Optional[date] = None, session_to: Optional[date] = None,
    current_configuration: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the read-only report; never creates or mutates a database."""
    report: Dict[str, Any] = {
        "format": REPORT_FORMAT,
        "authority_effect": "NONE",
        "window": {"session_from": session_from.isoformat() if session_from else None,
                   "session_to": session_to.isoformat() if session_to else None},
        "current_configuration_projection": dict(current_configuration or {}),
        "interpretation": (
            "Diagnostic only. A blocker explains non-delivery; it is not a qualification, "
            "profitability or delivery-readiness verdict. Attempt/idea comparison is aggregate."
        ),
    }
    ideas_db, ideas_error = _open_read_only(db_path)
    ideas: List[Dict[str, Any]] = []
    if ideas_db is None:
        report["ideas_state"] = f"UNAVAILABLE:{ideas_error}"
        report["qualification_registry"] = {"state": f"UNAVAILABLE:{ideas_error}"}
    else:
        with closing(ideas_db):
            tables = _tables(ideas_db)
            if "partner_advisory_ideas" in tables:
                ideas = _idea_rows(ideas_db, session_from, session_to)
                report["ideas_state"] = "AVAILABLE"
            else:
                report["ideas_state"] = "UNAVAILABLE:table_missing"
            if "partner_advisory_strategy_qualifications" in tables:
                rows = _qualification_rows(ideas_db)
                report["qualification_registry"] = {
                    "state": "AVAILABLE", "rows": rows,
                    "note": "registry rows only; authorization packages are not re-verified here",
                }
            else:
                report["qualification_registry"] = {"state": "UNAVAILABLE:table_missing"}
    report["candidates"] = ideas
    attempts: Dict[str, Dict[str, Any]] = {}
    attempts_db, attempts_error = _open_read_only(attempts_path)
    if attempts_db is None:
        report["attempts_state"] = f"UNAVAILABLE:{attempts_error}"
    else:
        with closing(attempts_db):
            if "partner_collection_attempts" in _tables(attempts_db):
                attempts = _attempt_summary(attempts_db, session_from, session_to)
                report["attempts_state"] = "AVAILABLE"
            else:
                report["attempts_state"] = "UNAVAILABLE:table_missing"
    report["sessions"] = _session_summary(ideas, attempts)
    primary = Counter(idea["primary_blocker"] for idea in ideas if not idea["delivered"])
    report["totals"] = {
        "candidates": len(ideas),
        "delivered": sum(1 for idea in ideas if idea["delivered"]),
        "primary_blockers": dict(sorted(primary.items())),
        "sessions_with_attempt_idea_disagreement": sum(
            1 for value in report["sessions"].values() if value["attempt_idea_disagreement"]),
    }
    return report


def _session_summary(ideas: Iterable[Mapping[str, Any]], attempts: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    by_key: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"ideas_by_status": Counter()})
    for idea in ideas:
        by_key[f"{idea['session_date']}:{idea['underlying']}"]["ideas_by_status"][idea["status"]] += 1
    sessions = {}
    for key in sorted(set(by_key) | set(attempts)):
        statuses = dict(sorted(by_key[key]["ideas_by_status"].items())) if key in by_key else {}
        attempt = attempts.get(key)
        ideas_rejected = statuses.get("REJECTED", 0)
        attempts_rejected = (attempt or {}).get("terminal", {}).get("REJECTED", 0)
        sessions[key] = {
            "ideas_by_status": statuses,
            "attempts": attempt,
            # Persistence rejected more ideas than the attempt journal rejected:
            # the journal recorded a validation that persistence did not
            # reproduce (the S5a frozen-clock defect class).  Aggregate only.
            "attempt_idea_disagreement": bool(attempt is not None and ideas_rejected > attempts_rejected),
        }
    return sessions


__all__ = ["REPORT_FORMAT", "build_delivery_blocker_report", "candidate_blockers"]
