"""Fail-closed readiness evidence for the partner hedge pipeline.

This module deliberately does not change any feature switch.  It gives the
operator a single, auditable answer to the question ``what is still missing
before Phase 2/3 may be enabled?``.  Readiness is *not* an execution
authorization; even a READY report cannot place an order.

The earnings calendar is operator maintained (``event_calendar.py`` treats a
missing calendar as permissive for the unrelated penny scanner).  Hedge
readiness is stricter: an earnings hedge cannot be enabled unless the file is
present, parseable, recently maintained, and contains at least one future
earnings/results row.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import aiosqlite

from config import settings
from event_calendar import load_event_map


IST = timezone(timedelta(hours=5, minutes=30))
PHASE2_STAGING_DAYS = 5
PHASE3_STAGING_DAYS = 7
PHASE3_SAMPLES_PER_KIND = 5
CALENDAR_MAX_AGE_DAYS = 45
CALENDAR_LOOKAHEAD_DAYS = 180
EVIDENCE_MAX_AGE_DAYS = 30

PHASE2_KINDS = frozenset({
    "covered_call_recommendation", "bull_put_spread", "bear_call_spread",
    "iron_condor", "delta_hedge_rebalance",
})
PHASE3_KINDS = frozenset({
    "gamma_exposure_alert", "long_straddle", "long_strangle",
    "calendar_diary_spread", "iron_butterfly", "earnings_event_hedge",
    "portfolio_corruption_overlay",
})
EVIDENCE_TYPES = frozenset({
    "phase2_live_chain_verification",
    "phase3_live_chain_verification",
    "phase2_sample_review",
    "phase3_sample_review",
    "phase2_staging_day",
    "phase3_staging_day",
})


def _now(now: Optional[datetime] = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(IST)


def _block(gate: str, reason: str, observed: Any = None, required: Any = None) -> dict:
    return {"gate": gate, "status": "BLOCKED", "observed": observed,
            "required": required, "reason": reason}


def inspect_earnings_calendar(
    csv_path: Optional[str] = None,
    *,
    now: Optional[datetime] = None,
    max_age_days: int = CALENDAR_MAX_AGE_DAYS,
) -> dict:
    """Return deterministic health information for the curated event CSV.

    Unlike :func:`event_calendar.event_block`, malformed/missing data is not
    silently allowed here.  This function is a gate diagnostic only; it does
    not alter the calendar cache or any trading state.
    """
    anchor = _now(now)
    path_text = str(csv_path or getattr(settings, "EVENT_CALENDAR_CSV_PATH", ""))
    result = {
        "path": path_text,
        "exists": False,
        "readable": False,
        "event_count": 0,
        "earnings_event_count": 0,
        "underlyings": [],
        "next_earnings": None,
        "file_modified_at": None,
        "age_days": None,
        "status": "BLOCKED",
        "blockers": [],
    }
    if not path_text:
        result["blockers"].append("EVENT_CALENDAR_CSV_PATH is empty")
        return result
    path = Path(path_text)
    if not path.is_file():
        result["blockers"].append("earnings calendar file is missing")
        return result
    result["exists"] = True
    try:
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).astimezone(IST)
        result["readable"] = os.access(path, os.R_OK)
        result["file_modified_at"] = modified.isoformat()
        result["age_days"] = round(max((anchor - modified).total_seconds(), 0) / 86400, 3)
    except OSError as exc:
        result["blockers"].append(f"earnings calendar stat failed: {type(exc).__name__}")
        return result
    if not result["readable"]:
        result["blockers"].append("earnings calendar file is not readable")
        return result
    try:
        events = load_event_map(path_text)
    except Exception as exc:  # defensive: readiness must never crash a route
        result["blockers"].append(f"earnings calendar parse failed: {type(exc).__name__}")
        return result
    earnings = []
    for ticker, rows in events.items():
        for event_day, event_type in rows:
            result["event_count"] += 1
            if str(event_type).upper() in {"RESULTS", "EARNINGS"}:
                result["earnings_event_count"] += 1
                if anchor.date() <= event_day <= anchor.date() + timedelta(days=CALENDAR_LOOKAHEAD_DAYS):
                    earnings.append((event_day, ticker, str(event_type).upper()))
    result["underlyings"] = sorted(events)
    if earnings:
        event_day, ticker, event_type = min(earnings)
        result["next_earnings"] = {
            "date": event_day.isoformat(), "underlying": ticker, "type": event_type,
        }
    if result["age_days"] is not None and result["age_days"] > max_age_days:
        result["blockers"].append(
            f"earnings calendar is stale ({result['age_days']:.1f}d > {max_age_days}d)"
        )
    if result["earnings_event_count"] == 0:
        result["blockers"].append("calendar contains no RESULTS/EARNINGS rows")
    elif result["next_earnings"] is None:
        result["blockers"].append("calendar contains no future earnings row in lookahead")
    if not result["blockers"]:
        result["status"] = "READY"
    return result


# Clear aliases make this contract discoverable to callers without duplicating
# the implementation.
earnings_calendar_readiness = inspect_earnings_calendar
calendar_readiness = inspect_earnings_calendar


async def init_readiness_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path, timeout=30) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS partner_hedge_gate_evidence (
                evidence_type TEXT NOT NULL,
                phase TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT '',
                evidence_ref TEXT NOT NULL DEFAULT '',
                observed_on TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                source TEXT NOT NULL,
                note TEXT,
                PRIMARY KEY (evidence_type, phase, kind, evidence_ref, observed_on)
            )
        """)
        await db.commit()


async def record_gate_evidence(
    db_path: str,
    *,
    evidence_type: str,
    phase: str,
    observed_on: date,
    source: str,
    kind: str = "",
    evidence_ref: str = "",
    note: Optional[str] = None,
    observed_at: Optional[datetime] = None,
) -> dict:
    """Record an operator attestation; it never enables a feature switch."""
    evidence_type = str(evidence_type).strip().lower()
    phase = str(phase).strip().lower()
    kind = str(kind or "").strip().lower()
    evidence_ref = str(evidence_ref or "").strip()
    source = str(source).strip()
    if evidence_type not in EVIDENCE_TYPES:
        raise ValueError("unsupported evidence_type")
    if phase not in {"phase2", "phase3"}:
        raise ValueError("phase must be phase2 or phase3")
    expected_phase = "phase2" if evidence_type.startswith("phase2_") else "phase3"
    if phase != expected_phase:
        raise ValueError("evidence_type and phase do not match")
    if not isinstance(observed_on, date) or isinstance(observed_on, datetime):
        raise ValueError("observed_on must be a date")
    if observed_on > _now(observed_at).date():
        raise ValueError("observed_on cannot be in the future")
    if not source or len(source) > 120:
        raise ValueError("source is required and must be <=120 characters")
    if evidence_type.endswith("_sample_review"):
        if not kind:
            raise ValueError("sample review evidence requires kind")
        if not evidence_ref or len(evidence_ref) > 160:
            raise ValueError("sample review evidence requires evidence_ref <=160 characters")
    elif evidence_ref:
        raise ValueError("evidence_ref is only valid for sample review evidence")
    allowed = PHASE2_KINDS if phase == "phase2" else PHASE3_KINDS
    if kind and kind not in allowed:
        raise ValueError("kind is not part of this phase")
    stamp = _now(observed_at).isoformat() if observed_at else datetime.now(timezone.utc).isoformat()
    await init_readiness_db(db_path)
    async with aiosqlite.connect(db_path, timeout=30) as db:
        await db.execute(
            "INSERT OR REPLACE INTO partner_hedge_gate_evidence "
            "(evidence_type, phase, kind, evidence_ref, observed_on, observed_at, source, note) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                evidence_type, phase, kind, evidence_ref,
                observed_on.isoformat(), stamp, source, note,
            ),
        )
        await db.commit()
    return {
        "evidence_type": evidence_type, "phase": phase, "kind": kind,
        "evidence_ref": evidence_ref,
        "observed_on": observed_on.isoformat(), "observed_at": stamp,
        "source": source, "note": note,
    }


async def _evidence(db_path: str, phase: str, now: datetime) -> list[dict]:
    await init_readiness_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT evidence_type, phase, kind, evidence_ref, observed_on, "
            "observed_at, source, note "
            "FROM partner_hedge_gate_evidence WHERE phase=? ORDER BY observed_on",
            (phase,),
        )
        rows = [dict(row) for row in await cur.fetchall()]
    cutoff = now.date() - timedelta(days=EVIDENCE_MAX_AGE_DAYS)
    return [row for row in rows if row.get("observed_on", "") >= cutoff.isoformat()]


async def assess_phase_readiness(db_path: str, phase: str, *, now: Optional[datetime] = None) -> dict:
    """Assess one phase using explicit evidence and current configuration."""
    phase = str(phase).strip().lower()
    if phase not in {"phase2", "phase3"}:
        raise ValueError("phase must be phase2 or phase3")
    anchor = _now(now)
    rows = await _evidence(db_path, phase, anchor)
    staging_type = f"{phase}_staging_day"
    staging_days = sorted({row["observed_on"] for row in rows if row["evidence_type"] == staging_type})
    required_staging = PHASE2_STAGING_DAYS if phase == "phase2" else PHASE3_STAGING_DAYS
    blockers = []
    if len(staging_days) < required_staging:
        blockers.append(_block(
            "staging_days", f"only {len(staging_days)} of {required_staging} required staging days recorded",
            len(staging_days), f">={required_staging}",
        ))
    live_type = f"{phase}_live_chain_verification"
    if not any(row["evidence_type"] == live_type for row in rows):
        blockers.append(_block("live_chain_verification", "manual live-chain verification is not recorded", 0, ">=1"))
    review_type = f"{phase}_sample_review"
    expected_kinds = PHASE2_KINDS if phase == "phase2" else PHASE3_KINDS
    review_counts = {
        kind: sum(
            row["evidence_type"] == review_type and row["kind"] == kind
            for row in rows
        )
        for kind in expected_kinds
    }
    reviewed = {kind for kind, count in review_counts.items() if count > 0}
    if phase == "phase3":
        missing = {
            kind: PHASE3_SAMPLES_PER_KIND - count
            for kind, count in sorted(review_counts.items())
            if count < PHASE3_SAMPLES_PER_KIND
        }
        if missing:
            blockers.append(_block(
                "sample_review",
                "five manual Telegram samples per emitted Phase 3 kind are required",
                missing,
                f">={PHASE3_SAMPLES_PER_KIND} per kind",
            ))
    if phase == "phase3" and bool(getattr(settings, "PARTNER_HEDGE_EARNINGS_EVENT", False)):
        calendar = inspect_earnings_calendar(now=anchor)
        if calendar["status"] != "READY":
            blockers.append(_block("earnings_calendar", "earnings hedge is enabled but its calendar is not ready", calendar["blockers"], "READY"))
    else:
        calendar = inspect_earnings_calendar(now=anchor)
    enabled = bool(getattr(settings, f"PARTNER_HEDGE_{phase.upper()}_ENABLED", False))
    return {
        "phase": phase, "enabled": enabled,
        "state": "READY" if not blockers else "BLOCKED",
        "can_enable": not blockers,
        "required_staging_days": required_staging,
        "staging_days": staging_days,
        "evidence_rows": len(rows), "reviewed_kinds": sorted(reviewed),
        "sample_review_counts": dict(sorted(review_counts.items())),
        "calendar": calendar, "blockers": blockers,
    }


async def assess_hedge_readiness(db_path: str, *, now: Optional[datetime] = None) -> dict:
    anchor = _now(now)
    phase2 = await assess_phase_readiness(db_path, "phase2", now=anchor)
    phase3 = await assess_phase_readiness(db_path, "phase3", now=anchor)
    return {
        "schema_version": 1,
        "as_of": anchor.isoformat(),
        "research_only": True,
        "automatic_execution": False,
        "can_place_orders": False,
        "can_enable": bool(phase2["can_enable"] and phase3["can_enable"]),
        "phases": {"phase2": phase2, "phase3": phase3},
        "blockers": phase2["blockers"] + phase3["blockers"],
        "warning": "Readiness evidence does not authorize order placement or configuration mutation.",
    }


__all__ = [
    "PHASE2_KINDS", "PHASE3_KINDS", "EVIDENCE_TYPES",
    "PHASE3_SAMPLES_PER_KIND",
    "inspect_earnings_calendar", "earnings_calendar_readiness", "calendar_readiness",
    "init_readiness_db", "record_gate_evidence", "assess_phase_readiness",
    "assess_hedge_readiness",
]
