"""[WORKFLOW-G 2026-09-13] Append-only promotion-bridge persistence and state machine.

Implements the contract documented at ``docs/2026-09-13-workflow-g-promotion-
bridge.md``. Every held-out comparison report authored by ``proactive_*`` is
*consultative evidence only*; it never authorises orders. This module owns
the bridges that *might* one day carry such authority, and enforces the
forward-only state machine that the contract declares.

Architectural rules (all enforced here, all deliberate):

* **Append-only.** Updates to a bridge that already exists raise
  ``BridgeAlreadyExistsError``. Edits to a bridge's authorisation state
  are not permitted; transitions are recorded as new rows in
  ``promotion_bridge_transitions``, never as ``UPDATE`` of the bridge row.
* **Forward-only state.** ``UNSIGNED -> REFUSED``, ``UNSIGNED ->
  APPROVED_WITH_BUDGET`` and ``UNSIGNED -> APPROVED_LIVE_BUDGET`` are the
  only valid first transitions. ``REFUSED`` and ``APPROVED_*`` are terminal
  here; *amendment* is not a recognised operation. A new decision requires a
  new ``bridge_id``.
* **Read-only against cash.** This module never reads or writes
  ``bankroll_ledger``, ``positions`` or any broker surface. ``APPROVED_LIVE_
  BUDGET`` carries a ``live_bankroll_delta`` field for a future F / D
  integration, but no code path here deposits it; F (accounting truth) owns
  any actual money movement and is the only module permitted to do so.
* **Fail-closed on missing identity.** A bridge missing any of the seven
  required fields listed in bridge section 4 raises
  ``BridgeMissingFieldError``; integrity is checked at construction, not at
  persist, so callers cannot persist an incomplete bridge by mistake.
* **No scheduler, no transport, no broker client.** Two grep-able imports
  (cost-schedule version, shadow schema version) and one aiosqlite
  dependency; nothing else.

The DB lives at ``<settings.DB_PATH parent>/promotion_bridges.db`` by
default and is *intentionally separate* from ``cache.db``: a held-out
bridge record is a governance artefact, not a research ledger entry, and
must be auditable even if the research tables are truncated.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

import aiosqlite

from cost_schedules import EQUITY_INTRADAY_SCHEDULE_VERSION
from proactive_intelligence import _SHADOW_SCHEMA_VERSION


# --- enums ----------------------------------------------------------------

class AuthorisationState(str, Enum):
    UNSIGNED = "UNSIGNED"
    REFUSED = "REFUSED"
    APPROVED_WITH_BUDGET = "APPROVED_WITH_BUDGET"
    APPROVED_LIVE_BUDGET = "APPROVED_LIVE_BUDGET"


class BridgeTerminalError(Exception):
    """Base class for bridge misuse exceptions."""


class BridgeAlreadyExistsError(BridgeTerminalError):
    """Raised when persisting a bridge whose bridge_id is already present."""


class BridgeMissingFieldError(BridgeTerminalError):
    """Raised at construction when a required field is missing or empty."""


class BridgeInvalidStateError(BridgeTerminalError):
    """Raised when an attempted state transition violates the forward-only chain."""


class BridgeVersionMismatchError(BridgeTerminalError):
    """Raised when a bridge's stored schema or cost-schedule version drifts from current."""


class BridgeSignerError(BridgeTerminalError):
    """Raised when the operator identifier is empty or of an invalid form."""


# --- schema-related constants (kept inside the module to make the contract
# locatable from a single place) ---------------------------------------------

_BRIDGE_SCHEMA_VERSION = "promotion-bridge-v1"
_AUTHORISATION_STATES = frozenset(state.value for state in AuthorisationState)
_VALID_FORWARD_TRANSITIONS: dict[tuple[str, str], bool] = {
    # explicit allowlist rather than algorithmic derivation: makes the
    # state machine reviewable against bridge sections 3 and 6 at a glance
    (AuthorisationState.UNSIGNED.value, AuthorisationState.REFUSED.value): True,
    (AuthorisationState.UNSIGNED.value, AuthorisationState.APPROVED_WITH_BUDGET.value): True,
    (AuthorisationState.UNSIGNED.value, AuthorisationState.APPROVED_LIVE_BUDGET.value): True,
}
_SIGNER_PATTERN = re.compile(r"^[A-Za-z0-9._\-@ ]{1,64}$")

_BUDGET_FIELD_LIMITS = {
    # per-bridge budget caps and ttl so a single careless entry cannot
    # authorise unbounded drawdown even by mistake
    "research_budget_inr": (1.0, 1_000_000.0),
    "live_bankroll_delta": (1.0, 5_000_000.0),
    "max_drawdown_pct": (0.001, 0.50),
    "expiry_seconds": (60, 60 * 60 * 24 * 365),  # 1 minute to 1 year
}


def _validate_approval_budget(record: dict, state: str, *, require: bool = True) -> None:
    amount = "live_bankroll_delta" if state == AuthorisationState.APPROVED_LIVE_BUDGET.value else "research_budget_inr"
    for name in ((amount, "max_drawdown_pct", "expiry_seconds") if require else ()):
        if record.get(name) is None:
            raise BridgeMissingFieldError(f"{name} is required for {state}")
    for name, (lo, hi) in _BUDGET_FIELD_LIMITS.items():
        value = record.get(name)
        if value is None:
            continue
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not lo <= value <= hi or not math.isfinite(value)
                or (name == "expiry_seconds" and not isinstance(value, int))):
            raise BridgeMissingFieldError(f"{name} must be within [{lo}, {hi}] with a valid numeric type")


# --- dataclasses -----------------------------------------------------------

@dataclass(frozen=True)
class BridgeDecision:
    """The seven required fields plus four optional budget fields.

    Required (sections 4 and 8 of the bridge contract):
        proposal_run_id, evidence_identity_sha256, schema_version,
        cost_schedule_version, code_revision, decided_at_utc,
        decided_by, authorisation_state.

    Optional (only meaningful for APPROVED_* states):
        research_budget_inr, live_bankroll_delta, max_drawdown_pct,
        expiry_seconds.
    """
    proposal_run_id: str
    evidence_identity_sha256: str
    schema_version: str
    cost_schedule_version: str
    code_revision: str
    decided_at_utc: datetime
    decided_by: str
    authorisation_state: str
    bridge_id: str = field(default_factory=lambda: uuid4().hex)
    notes: str = ""
    # budget fields; only consulted for APPROVED_* states
    research_budget_inr: Optional[float] = None
    live_bankroll_delta: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    expiry_seconds: Optional[int] = None

    def __post_init__(self) -> None:
        # required-string fields: reject empty or whitespace-only values
        required_strings = (
            "proposal_run_id", "evidence_identity_sha256", "schema_version",
            "cost_schedule_version", "code_revision",
        )
        for name in required_strings:
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise BridgeMissingFieldError(
                    f"bridge field {name!r} is required and must be a non-empty string"
                )

        # decided_by: empty *and* pattern-violating are both sign-off
        # issues. An empty value is treated as "no signer was chosen" and
        # raises BridgeSignerError; a non-empty value that violates the
        # pattern also raises BridgeSignerError. We check this *before*
        # the loop above so the empty case reaches the more specific
        # exception class.
        if not isinstance(self.decided_by, str) or not self.decided_by.strip():
            raise BridgeSignerError(
                "decided_by is required; cannot persist a bridge with no operator identifier"
            )

        # evidence_identity_sha256 must look like a hex digest (length 64 = SHA-256)
        if not re.fullmatch(r"[0-9a-f]{64}", self.evidence_identity_sha256):
            raise BridgeMissingFieldError(
                "evidence_identity_sha256 must be a 64-char lowercase hex digest (SHA-256)"
            )

        # decided_at_utc must be tz-aware; refuse naive datetimes explicitly so
        # callers cannot accidentally lose the timezone by passing a UTC
        # value through ``datetime.utcnow()``.
        if self.decided_at_utc.tzinfo is None or self.decided_at_utc.utcoffset() is None:
            raise BridgeMissingFieldError("decided_at_utc must be timezone-aware")

        # decided_by must look like an operator identifier; allow common
        # forms (initials, github handle, email-like). 64-char cap to leave
        # room for human-readable text without letting arbitrary prose in.
        if not _SIGNER_PATTERN.fullmatch(self.decided_by):
            raise BridgeSignerError(
                "decided_by must match [A-Za-z0-9._-@ ]{1,64} (operator identifier, no secrets)"
            )

        # authorisation_state must be a known value
        if self.authorisation_state not in _AUTHORISATION_STATES:
            raise BridgeInvalidStateError(
                f"authorisation_state must be one of {sorted(_AUTHORISATION_STATES)}; "
                f"got {self.authorisation_state!r}"
            )

        # version guards: refuse bridges that pin stale schemas or cost
        # schedules without explicit override
        if self.schema_version != _SHADOW_SCHEMA_VERSION:
            raise BridgeVersionMismatchError(
                f"bridge schema_version={self.schema_version!r} does not match "
                f"current proactive stack {_SHADOW_SCHEMA_VERSION!r}; issue a new "
                f"bridge against the updated codebase instead."
            )
        if self.cost_schedule_version != EQUITY_INTRADAY_SCHEDULE_VERSION:
            raise BridgeVersionMismatchError(
                f"bridge cost_schedule_version={self.cost_schedule_version!r} does not "
                f"match current cost schedule {EQUITY_INTRADAY_SCHEDULE_VERSION!r}."
            )

        # Unsigned records may retain explicit predeclared budgets. Approval
        # requires the relevant amount, drawdown and expiry; none is inferred.
        if self.authorisation_state in {
            AuthorisationState.APPROVED_WITH_BUDGET.value,
            AuthorisationState.APPROVED_LIVE_BUDGET.value,
        }:
            self._validate_budget_fields()
        else:
            _validate_approval_budget(asdict(self), self.authorisation_state, require=False)

    def _validate_budget_fields(self) -> None:
        _validate_approval_budget(asdict(self), self.authorisation_state)


@dataclass(frozen=True)
class BridgeTransition:
    """One row of the transitions table; append-only, never updated."""
    bridge_id: str
    previous_state: Optional[str]
    new_state: str
    decided_by: str
    decided_at_utc: datetime
    notes: str = ""


# --- helpers ---------------------------------------------------------------

def _json_default(value: object) -> object:
    """JSON encoder fallback for dataclasses, datetimes, enums."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise TypeError("naive datetimes must not be persisted; use tz-aware")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _hash_evidence_payload(payload: dict) -> str:
    """Compute evidence_identity_sha256 as a stable canonical digest."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(canonical.encode()).hexdigest()


# --- persistence -----------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS promotion_bridges (
    bridge_id                TEXT PRIMARY KEY,
    proposal_run_id          TEXT NOT NULL,
    evidence_identity_sha256 TEXT NOT NULL,
    schema_version           TEXT NOT NULL,
    cost_schedule_version    TEXT NOT NULL,
    code_revision            TEXT NOT NULL,
    decided_at_utc           TEXT NOT NULL,
    decided_by               TEXT NOT NULL,
    authorisation_state      TEXT NOT NULL,
    notes                    TEXT NOT NULL DEFAULT '',
    research_budget_inr      REAL,
    live_bankroll_delta      REAL,
    max_drawdown_pct         REAL,
    expiry_seconds           INTEGER,
    schema_version_bridge    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS promotion_bridge_transitions (
    bridge_id       TEXT NOT NULL,
    previous_state  TEXT,
    new_state       TEXT NOT NULL,
    decided_by      TEXT NOT NULL,
    decided_at_utc  TEXT NOT NULL,
    notes           TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_pbt_bridge ON promotion_bridge_transitions(bridge_id);
"""


async def init_promotion_bridges(db_path: str) -> None:
    """Idempotent schema bring-up; safe to call on every startup."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


def default_db_path() -> str:
    """Path to the bridge DB; ``promotion_bridges.db`` alongside ``cache.db``."""
    from config import settings
    cache = Path(settings.DB_PATH).resolve()
    return str(cache.parent / "promotion_bridges.db")


async def persist_bridge(db_path: str, decision: BridgeDecision) -> str:
    """Persist a *new* bridge decision.

    Returns the ``bridge_id``. Raises ``BridgeAlreadyExistsError`` if the id
    already exists; the bridge cannot be amended and must be re-issued
    under a new ``bridge_id`` if the operator changes their mind.
    """
    await init_promotion_bridges(db_path)
    async with aiosqlite.connect(db_path) as db:
        try:
            await db.execute(
                "INSERT INTO promotion_bridges VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    decision.bridge_id,
                    decision.proposal_run_id,
                    decision.evidence_identity_sha256,
                    decision.schema_version,
                    decision.cost_schedule_version,
                    decision.code_revision,
                    decision.decided_at_utc.astimezone(timezone.utc).isoformat(),
                    decision.decided_by,
                    decision.authorisation_state,
                    decision.notes,
                    decision.research_budget_inr,
                    decision.live_bankroll_delta,
                    decision.max_drawdown_pct,
                    decision.expiry_seconds,
                    _BRIDGE_SCHEMA_VERSION,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise BridgeAlreadyExistsError(
                f"bridge_id={decision.bridge_id!r} already exists; bridges are append-only"
            ) from exc
        # An UNSIGNED bridge is recorded as a transition from NULL -> UNSIGNED
        # so the transitions table always carries the full history (including
        # creation), matching bridge section 6 ("append-only ledger-style
        # invariant").
        await db.execute(
            "INSERT INTO promotion_bridge_transitions VALUES (?,?,?,?,?,?)",
            (
                decision.bridge_id,
                None,
                decision.authorisation_state,
                decision.decided_by,
                decision.decided_at_utc.astimezone(timezone.utc).isoformat(),
                decision.notes,
            ),
        )
        await db.commit()
    return decision.bridge_id


async def transition_bridge(
    db_path: str,
    bridge_id: str,
    *,
    new_state: str,
    decided_by: str,
    decided_at_utc: datetime,
    notes: str = "",
) -> str:
    """Append a state transition to a *terminal-state* bridge.

    Refused or Approved bridges are terminal at the time of persist; this
    function exists so a *new* decision can be recorded against the same
    ``bridge_id`` *only* in the sense of a fresh transition (the prior
    row remains intact in the transitions table). The forward-only
    state-machine rules of bridge section 6 still apply: you cannot, e.g.,
    ``REFUSED -> APPROVED_WITH_BUDGET``.

    This function does not UPDATE the bridge's current state column; it
    only appends to ``promotion_bridge_transitions``. The latest authorised
    state of a bridge is therefore derivable from the transitions table
    alone; the ``promotion_bridges`` row is the *initial* decision, not the
    latest.
    """
    if new_state not in _AUTHORISATION_STATES:
        raise BridgeInvalidStateError(
            f"new_state must be one of {sorted(_AUTHORISATION_STATES)}; got {new_state!r}"
        )
    if decided_at_utc.tzinfo is None or decided_at_utc.utcoffset() is None:
        raise BridgeMissingFieldError("decided_at_utc must be timezone-aware")
    if not isinstance(decided_by, str) or not decided_by.strip() or not _SIGNER_PATTERN.fullmatch(decided_by):
        raise BridgeSignerError(
            "decided_by must match [A-Za-z0-9._-@ ]{1,64}"
        )

    await init_promotion_bridges(db_path)
    async with aiosqlite.connect(db_path) as db:
        # Serialize the current-state read with the append. Two callers must
        # not both observe UNSIGNED and commit conflicting terminal decisions.
        await db.execute("BEGIN IMMEDIATE")
        db.row_factory = sqlite3.Row
        async with db.execute(
            "SELECT * FROM promotion_bridges WHERE bridge_id = ?",
            (bridge_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise BridgeInvalidStateError(
                f"bridge_id={bridge_id!r} does not exist; cannot transition"
            )
        async with db.execute(
            "SELECT new_state FROM promotion_bridge_transitions "
            "WHERE bridge_id = ? ORDER BY rowid DESC LIMIT 1", (bridge_id,),
        ) as cursor:
            latest = await cursor.fetchone()
        previous_state = latest[0] if latest is not None else row["authorisation_state"]
        valid = _VALID_FORWARD_TRANSITIONS.get(
            (previous_state, new_state), False
        )
        if not valid:
            raise BridgeInvalidStateError(
                f"forward-only transition {previous_state!r} -> {new_state!r} is not "
                f"permitted by bridge contract section 6; issue a new bridge under a "
                f"new bridge_id."
            )
        if new_state in {AuthorisationState.APPROVED_WITH_BUDGET.value, AuthorisationState.APPROVED_LIVE_BUDGET.value}:
            if (row["schema_version"] != _SHADOW_SCHEMA_VERSION
                    or row["cost_schedule_version"] != EQUITY_INTRADAY_SCHEDULE_VERSION
                    or row["schema_version_bridge"] != _BRIDGE_SCHEMA_VERSION):
                raise BridgeVersionMismatchError("approval record version is stale")
            _validate_approval_budget(dict(row), new_state)
            original_at = datetime.fromisoformat(row["decided_at_utc"])
            if original_at.tzinfo is None or original_at.utcoffset() is None:
                raise BridgeMissingFieldError("stored original decision clock must be timezone-aware")
            if not original_at <= decided_at_utc < original_at + timedelta(seconds=row["expiry_seconds"]):
                raise BridgeMissingFieldError("approval is outside the original budget validity window")
        await db.execute(
            "INSERT INTO promotion_bridge_transitions VALUES (?,?,?,?,?,?)",
            (
                bridge_id,
                previous_state,
                new_state,
                decided_by,
                decided_at_utc.astimezone(timezone.utc).isoformat(),
                notes,
            ),
        )
        await db.commit()
    return bridge_id


async def read_bridge(db_path: str, bridge_id: str, *, now: Optional[datetime] = None) -> Optional[dict]:
    """Return the persisted bridge row plus its full transitions history.

    The transitions list is *authoritative* for current state; the bridge
    row is the initial decision. Returns ``None`` when no bridge exists
    with the given id; fail-closed callers must distinguish. Calls
    ``init_promotion_bridges`` first so an empty DB returns ``None``
    cleanly instead of raising.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise BridgeMissingFieldError("now must be timezone-aware")
    await init_promotion_bridges(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        async with db.execute(
            "SELECT * FROM promotion_bridges WHERE bridge_id = ?",
            (bridge_id,),
        ) as cursor:
            bridge_row = await cursor.fetchone()
        if bridge_row is None:
            return None
        async with db.execute(
            "SELECT previous_state, new_state, decided_by, decided_at_utc, notes "
            "FROM promotion_bridge_transitions WHERE bridge_id = ? "
            "ORDER BY rowid ASC",
            (bridge_id,),
        ) as cursor:
            transitions = [dict(row) async for row in cursor]
    state = transitions[-1]["new_state"] if transitions else bridge_row["authorisation_state"]
    budget_status = "NOT_APPROVED"
    expires_at = None
    if state in {AuthorisationState.APPROVED_WITH_BUDGET.value, AuthorisationState.APPROVED_LIVE_BUDGET.value}:
        try:
            _validate_approval_budget(dict(bridge_row), state)
            original_at = datetime.fromisoformat(bridge_row["decided_at_utc"])
            if original_at.tzinfo is None or original_at.utcoffset() is None:
                raise ValueError("stored clock is naive")
            expires_at = original_at + timedelta(seconds=bridge_row["expiry_seconds"])
            latest_at = datetime.fromisoformat(transitions[-1]["decided_at_utc"]) if transitions else original_at
            if latest_at.tzinfo is None or latest_at.utcoffset() is None:
                raise ValueError("stored signature clock is naive")
            if not original_at <= latest_at < expires_at:
                raise ValueError("stored approval is outside original budget validity")
            budget_status = "EXPIRED" if current >= expires_at else "NOT_YET_VALID" if current < max(original_at, latest_at) else "VALID_BUDGET_ONLY"
        except (BridgeMissingFieldError, ValueError, TypeError, OverflowError):
            budget_status = "INVALID_OR_MISSING_BUDGET"
        if (bridge_row["schema_version"] != _SHADOW_SCHEMA_VERSION
                or bridge_row["cost_schedule_version"] != EQUITY_INTRADAY_SCHEDULE_VERSION
                or bridge_row["schema_version_bridge"] != _BRIDGE_SCHEMA_VERSION):
            budget_status = "STALE_VERSION"
    return {
        "bridge": dict(bridge_row),
        "transitions": transitions,
        "current_state": state,
        "budget_status": budget_status,
        "budget_expires_at": expires_at.isoformat() if expires_at is not None else None,
        "approval_usable": False,
        "approval_blockers": ["FROZEN_HELDOUT_ACCOUNT_AND_F_D_EVIDENCE_NOT_VALIDATED"] if state.startswith("APPROVED_") else [],
        "research_only": True,
        "can_place_orders": False,
        "authorization_effect": "NONE",
    }


def compute_evidence_identity(payload: dict) -> str:
    """Public helper: SHA-256 of canonical JSON of an evidence payload.

    Used by callers building a bridge off a held-out comparison report.
    The same payload bytes must always produce the same digest.
    """
    return _hash_evidence_payload(payload)


def default_bridge_id() -> str:
    """Public helper for tests and operator code that want a v4 hex id."""
    return uuid4().hex


__all__ = [
    "AuthorisationState",
    "BridgeDecision",
    "BridgeTransition",
    "BridgeAlreadyExistsError",
    "BridgeMissingFieldError",
    "BridgeInvalidStateError",
    "BridgeVersionMismatchError",
    "BridgeSignerError",
    "compute_evidence_identity",
    "default_bridge_id",
    "default_db_path",
    "init_promotion_bridges",
    "persist_bridge",
    "read_bridge",
    "transition_bridge",
]
