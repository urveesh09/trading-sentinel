"""Persisted, non-authoritative health evidence from the optional AI worker.

The agent is deliberately a separate container with no database write access.
It posts this small, authenticated status envelope to the engine instead.  The
record is operational evidence only: no value written here can approve a
signal, place an order, or change a deterministic decision.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite

from hedge_analytics import init_hedge_db

_MAX_STATUS_AGE = timedelta(minutes=3)
_ALLOWED_STATES = {
    "READY", "DISABLED_NO_CREDENTIAL", "DISABLED_BY_CONFIGURATION",
    "DISABLED_BY_POLICY", "OUTAGE_CIRCUIT_OPEN", "UNAVAILABLE",
}

# [WORKFLOW-I I.A 2026-09-13] Allow-list for the bounded ``usefulness``
# envelope bridged from the agent's I3 ``usefulness_snapshot``. Each
# Counters are non-negative integers; the cache rate is finite in [0, 1];
# latency aggregates are finite non-negative floats or null; and the last
# completion clock is a timezone-aware ISO timestamp or null. The bounded
# four verdict buckets are documented as a frozen set. For compatibility,
# partial historical envelopes remain readable and missing verdict buckets
# are normalised to zero.
#
# The bounded contract is enforced inside ``_clean_usefulness``,
# which is the only path that mutates the persisted detail. The
# numeric ranges below match the agent-side counters exactly
# (see ``agent/async_reviews.py::usefulness_snapshot``); any drift
# between the producer and the consumer surfaces as a ValidationError
# on the next status post, NOT as silent acceptance.
_ALLOWED_USEFULNESS_KEYS = frozenset({
    "total_completed_reviews",
    "cache_hits",
    "cache_misses",
    "cache_hit_rate",
    "circuit_opens",
    "response_seconds_mean",
    "response_seconds_p95",
    "response_seconds_last",
    "last_completed_at",
    "verdict_counts",
})
_ALLOWED_VERDICT_KEYS = frozenset({
    "APPROVE", "APPROVE_WITH_CONCERNS", "REVIEW_UNAVAILABLE", "REJECT",
})
_USEFULNESS_NON_NEG_INT_FIELDS = (
    "total_completed_reviews",
    "cache_hits",
    "cache_misses",
    "circuit_opens",
)
_USEFULNESS_NON_NEG_NUMBER_FIELDS = (
    "response_seconds_mean",
    "response_seconds_p95",
    "response_seconds_last",
)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS optional_ai_status_reports (
    report_key TEXT PRIMARY KEY CHECK (report_key = 'optional_ai'),
    state TEXT NOT NULL,
    reported_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    detail_json TEXT NOT NULL
);
"""


def _parse_aware_timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


async def _init(db_path: str) -> None:
    await init_hedge_db(db_path)
    async with aiosqlite.connect(db_path, timeout=30) as db:
        await db.execute("PRAGMA busy_timeout=5000")
        await db.executescript(_SCHEMA)
        await db.commit()


def _clean_usefulness(raw: Any) -> dict[str, Any]:
    """[WORKFLOW-I I.A 2026-09-13] Validate and normalise the bounded
    ``usefulness`` envelope.

    Contract:
        * Input is either absent (caller passes None or omits) or a
          dict whose keys are members of ``_ALLOWED_USEFULNESS_KEYS``.
          Any unknown key is rejected -- we do NOT silently drop.
        * ``total_completed_reviews``, ``cache_hits``, ``cache_misses``,
          ``circuit_opens`` are non-negative ints (bool rejected).
        * ``cache_hit_rate`` is a finite number in ``[0, 1]`` or
          ``None`` when there have been no lookups.
        * ``response_seconds_mean``, ``response_seconds_p95`` and
          ``response_seconds_last`` are finite non-negative numbers or
          ``None`` when no review has completed.
        * ``last_completed_at`` is a timezone-aware ISO timestamp or
          ``None`` and is normalised to UTC.
        * ``verdict_counts`` is a dict with exactly the four bounded
          verdict keys, each a non-negative int.
        * On any violation, ``ValueError`` is raised. The producer
          (agent) sees the error on the next status post and can
          self-correct.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("usefulness must be an object")
    unknown = set(raw.keys()) - _ALLOWED_USEFULNESS_KEYS
    if unknown:
        raise ValueError(
            f"usefulness has unknown keys: {sorted(unknown)!r}; "
            f"allowed keys are {sorted(_ALLOWED_USEFULNESS_KEYS)!r}"
        )
    clean: dict[str, Any] = {}
    for name in _USEFULNESS_NON_NEG_INT_FIELDS:
        value = raw.get(name)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"usefulness.{name} must be a non-negative integer"
            )
        clean[name] = value
    if "cache_hit_rate" in raw:
        rate = raw["cache_hit_rate"]
        if rate is None:
            clean["cache_hit_rate"] = None
        elif (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or not 0 <= rate <= 1
        ):
            raise ValueError(
                "usefulness.cache_hit_rate must be a finite number between 0 and 1"
            )
        else:
            clean["cache_hit_rate"] = float(rate)
    for name in _USEFULNESS_NON_NEG_NUMBER_FIELDS:
        if name not in raw:
            continue
        value = raw[name]
        if value is None:
            clean[name] = None
        elif (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(
                f"usefulness.{name} must be a finite non-negative number"
            )
        else:
            clean[name] = float(value)
    if "last_completed_at" in raw:
        completed_at = raw["last_completed_at"]
        clean["last_completed_at"] = (
            None
            if completed_at is None
            else _parse_aware_timestamp(
                completed_at, "usefulness.last_completed_at"
            ).isoformat()
        )
    # ``verdict_counts``: bounded 4-bucket dict.
    vc = raw.get("verdict_counts")
    if vc is not None:
        if not isinstance(vc, dict):
            raise ValueError("usefulness.verdict_counts must be an object")
        unknown_v = set(vc.keys()) - _ALLOWED_VERDICT_KEYS
        if unknown_v:
            raise ValueError(
                f"usefulness.verdict_counts has unknown keys: {sorted(unknown_v)!r}; "
                f"allowed keys are {sorted(_ALLOWED_VERDICT_KEYS)!r}"
            )
        clean_v: dict[str, int] = {}
        for v_name in _ALLOWED_VERDICT_KEYS:
            v_val = vc.get(v_name, 0)
            if (
                isinstance(v_val, bool)
                or not isinstance(v_val, int)
                or v_val < 0
            ):
                raise ValueError(
                    f"usefulness.verdict_counts.{v_name} must be a non-negative integer"
                )
            clean_v[v_name] = v_val
        clean["verdict_counts"] = clean_v
    if {
        "cache_hits", "cache_misses", "cache_hit_rate",
    }.issubset(raw):
        lookups = clean.get("cache_hits", 0) + clean.get("cache_misses", 0)
        expected_rate = None if lookups == 0 else clean["cache_hits"] / lookups
        actual_rate = clean.get("cache_hit_rate")
        if (
            (expected_rate is None) != (actual_rate is None)
            or (
                expected_rate is not None
                and not math.isclose(actual_rate, expected_rate, abs_tol=1e-12)
            )
        ):
            raise ValueError(
                "usefulness.cache_hit_rate is inconsistent with cache counters"
            )
    if "total_completed_reviews" in clean and "verdict_counts" in clean:
        if clean["total_completed_reviews"] != sum(
            clean["verdict_counts"].values()
        ):
            raise ValueError(
                "usefulness.total_completed_reviews is inconsistent with verdict counts"
            )
    return clean


async def record_optional_ai_status(
    db_path: str, payload: dict[str, Any], *, received_at: datetime | None = None,
) -> dict[str, Any]:
    """Validate and atomically retain one bounded agent status envelope."""
    if not isinstance(payload, dict):
        raise ValueError("status payload must be an object")
    state = payload.get("state")
    if state not in _ALLOWED_STATES:
        raise ValueError("unsupported optional AI state")
    reported_at = _parse_aware_timestamp(payload.get("reported_at"), "reported_at")
    received = (received_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if reported_at > received + timedelta(minutes=1):
        raise ValueError("reported_at exceeds permitted future skew")
    queue = payload.get("queue", {})
    if not isinstance(queue, dict):
        raise ValueError("queue must be an object")
    # Permit only bounded, presentation-safe operational fields.  In
    # particular this excludes prompts, signals, model output and credentials.
    clean_queue: dict[str, Any] = {}
    for name in ("pending", "cached", "daily_requests", "daily_budget", "max_pending"):
        value = queue.get(name)
        if value is not None:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"queue.{name} must be a non-negative integer")
            clean_queue[name] = value
    circuit_state = queue.get("circuit_state")
    if circuit_state is not None:
        if circuit_state not in {"OPEN", "CLOSED"}:
            raise ValueError("queue.circuit_state is invalid")
        clean_queue["circuit_state"] = circuit_state
    detail = {
        "async_requested": bool(payload.get("async_requested")),
        "policy_allows_annotation": bool(payload.get("policy_allows_annotation")),
        "queue": clean_queue,
        "reason": str(payload.get("reason") or "")[:160],
        "execution_authority": "NONE",
        "can_place_orders": False,
    }
    # [WORKFLOW-I I.A 2026-09-13] Bounded usefulness envelope. The
    # validator is strict: any unknown key, type mismatch, or
    # out-of-range value raises ``ValueError`` and the entire
    # status post is rejected (the previous report remains). This
    # is intentional -- a malformed usefulness field is a contract
    # drift and we want it visible, not silently dropped.
    clean_usefulness = _clean_usefulness(payload.get("usefulness"))
    if clean_usefulness:
        detail["usefulness"] = clean_usefulness
    await _init(db_path)
    async with aiosqlite.connect(db_path, timeout=30) as db:
        await db.execute("PRAGMA busy_timeout=5000")
        await db.execute(
            "INSERT OR REPLACE INTO optional_ai_status_reports "
            "(report_key,state,reported_at,received_at,detail_json) VALUES ('optional_ai',?,?,?,?)",
            (state, reported_at.isoformat(), received.isoformat(), json.dumps(detail, sort_keys=True)),
        )
        await db.commit()
    return await load_optional_ai_status(db_path, now=received)


async def load_optional_ai_status(
    db_path: str, *, now: datetime | None = None,
) -> dict[str, Any]:
    """Return last reported status, making absence/staleness explicit."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    await _init(db_path)
    async with aiosqlite.connect(db_path, timeout=30) as db:
        row = await (await db.execute(
            "SELECT state,reported_at,received_at,detail_json FROM optional_ai_status_reports "
            "WHERE report_key='optional_ai'"
        )).fetchone()
    base = {
        "mode": "OPTIONAL_ANNOTATION", "execution_authority": "NONE",
        "can_place_orders": False,
    }
    if row is None:
        return {**base, "state": "NOT_REPORTED", "stale": True,
                "reported_at": None, "reported_state": None,
                "received_at": None, "detail": {},
                "note": "No optional-AI worker report has been received."}
    try:
        reported_at = _parse_aware_timestamp(row[1], "stored reported_at")
        detail = json.loads(row[3])
    except (ValueError, TypeError, json.JSONDecodeError):
        return {**base, "state": "CORRUPT_REPORT", "stale": True,
                "reported_at": None, "reported_state": None,
                "received_at": None, "detail": {},
                "note": "The optional-AI status evidence is unreadable."}
    stale = current - reported_at > _MAX_STATUS_AGE
    return {
        **base, "state": "STALE" if stale else row[0], "reported_state": row[0],
        "reported_at": reported_at.isoformat(), "received_at": row[2], "stale": stale,
        "detail": detail,
        "note": "AI is an optional annotation. Deterministic signal, risk and delivery paths continue independently.",
    }
