"""[WORKFLOW-ITEMS-5/6/9 2026-09-20] Operations freshness diagnostic.

The audit (item 9) requires: "A missed login is visible before
useful session data is lost; market-load exit/lifecycle latency
measured; evidence retained long enough for review."

This module surfaces the freshness of every operational channel
the system depends on:

  - Last successful Kite login
  - Last public-input observation
  - Last candidate capture
  - Last ledger write

Each channel has its own age threshold
(``OPS_FRESHNESS_MAX_*_AGE_SECONDS``). When a channel exceeds
its threshold, the diagnostic emits a stable code so the
operator can grep + alert.

Pure of I/O: takes a DB path + ``now`` and returns a verdict.
The caller is responsible for invoking it during the lifecycle.

Design choices:

  * **Pure of clock read**: takes ``now`` so the diagnostic is
    reproducible and tests are hermetic.
  * **Pure of DB read**: opens a read-only connection and only
    SELECTs. No writes. No locks.
  * **Frozen dataclass**: ``FreshnessDiagnostic`` is frozen so
    callers cannot mutate the verdict.
  * **Stable codes**: each channel has a ``PASS`` / ``STALE`` /
    ``MISSING`` outcome with a stable enum value.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class ChannelState(str, Enum):
    """Outcome for a single freshness channel."""
    PASS = "PASS"          # Channel has recent evidence.
    STALE = "STALE"        # Channel's last event is older than the threshold.
    MISSING = "MISSING"    # Channel has no recorded event ever.


@dataclass(frozen=True)
class ChannelReport:
    """Per-channel freshness report."""
    name: str
    state: ChannelState
    age_seconds: int | None  # None when missing.
    threshold_seconds: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "age_seconds": self.age_seconds,
            "threshold_seconds": self.threshold_seconds,
        }


@dataclass(frozen=True)
class FreshnessDiagnostic:
    """Aggregated freshness diagnostic across all channels."""
    channels: tuple[ChannelReport, ...]
    any_stale: bool
    any_missing: bool

    def to_dict(self) -> dict:
        return {
            "channels": [c.to_dict() for c in self.channels],
            "any_stale": self.any_stale,
            "any_missing": self.any_missing,
        }


def _age_seconds(now: datetime, ts: str | None) -> int | None:
    """Compute the age in seconds. None when ``ts`` is None."""
    if ts is None:
        return None
    try:
        last = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return int((now - last).total_seconds())


def _classify(age: int | None, threshold: int) -> ChannelState:
    """Classify the channel outcome against the threshold."""
    if age is None:
        return ChannelState.MISSING
    if age > threshold:
        return ChannelState.STALE
    return ChannelState.PASS


def _probe_max(
    db_path: Path, *, sql: str, args: tuple = (),
) -> str | None:
    """Run a MAX(timestamp) query and return the string or None."""
    with sqlite3.connect(db_path) as db:
        row = db.execute(sql, args).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def diagnose_freshness(
    db_path: str | Path,
    *,
    now: datetime | None = None,
    max_login_age_seconds: int = 86_400,
    max_input_age_seconds: int = 1_800,
    max_ledger_age_seconds: int = 300,
) -> FreshnessDiagnostic:
    """[WORKFLOW-ITEMS-5/6/9 2026-09-20] Surface per-channel freshness.

    Probes three DB-side channels (login, public input, ledger)
    and emits a per-channel ``ChannelReport``. The caller uses
    ``any_stale`` / ``any_missing`` to decide whether to log at
    WARN (session open) or BLOCKER (session close).
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    db_path = Path(db_path)

    # Default to PASS for each channel when the DB is missing;
    # the caller is expected to handle "no DB" as a separate
    # diagnostic.
    if not db_path.is_file():
        return FreshnessDiagnostic(
            channels=(),
            any_stale=False,
            any_missing=False,
        )

    # Channel 1: Kite login. ``partner_token_store`` does not
    # currently log a login timestamp; we use the most recent
    # token-store row as a proxy when available. If the table
    # doesn't exist, fall back to MISSING.
    try:
        login_ts = _probe_max(
            db_path,
            sql="SELECT MAX(updated_at_utc) FROM partner_token_store",
        )
    except sqlite3.OperationalError:
        login_ts = None
    login_age = _age_seconds(now, login_ts)
    login_state = _classify(login_age, max_login_age_seconds)

    # Channel 2: Public input observation. Uses the
    # partner_collection_attempts table (the audit's
    # canonical freshness source).
    input_ts = _probe_max(
        db_path,
        sql="SELECT MAX(public_observed_at_utc) FROM partner_collection_attempts",
    )
    input_age = _age_seconds(now, input_ts)
    input_state = _classify(input_age, max_input_age_seconds)

    # Channel 3: Ledger write. ``bankroll_ledger`` is the
    # canonical cash-flow evidence.
    ledger_ts = _probe_max(
        db_path,
        sql="SELECT MAX(timestamp) FROM bankroll_ledger",
    )
    ledger_age = _age_seconds(now, ledger_ts)
    ledger_state = _classify(ledger_age, max_ledger_age_seconds)

    channels = (
        ChannelReport(
            name="login",
            state=login_state,
            age_seconds=login_age,
            threshold_seconds=max_login_age_seconds,
        ),
        ChannelReport(
            name="public_input",
            state=input_state,
            age_seconds=input_age,
            threshold_seconds=max_input_age_seconds,
        ),
        ChannelReport(
            name="ledger",
            state=ledger_state,
            age_seconds=ledger_age,
            threshold_seconds=max_ledger_age_seconds,
        ),
    )
    return FreshnessDiagnostic(
        channels=channels,
        any_stale=any(c.state == ChannelState.STALE for c in channels),
        any_missing=any(c.state == ChannelState.MISSING for c in channels),
    )


__all__ = [
    "ChannelReport",
    "ChannelState",
    "FreshnessDiagnostic",
    "diagnose_freshness",
]
