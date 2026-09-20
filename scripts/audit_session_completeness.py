#!/usr/bin/env python3
"""[WORKFLOW-B.1 2026-09-17] Session completeness audit.

Per Workstream B in NEXT_AGENT_PLAN.md:
> Compute session completeness from expected market-aware
> intervals and retained attempt records. Distinguish
> never attempted, attempted unavailable, partial,
> stale, and complete. A directory containing valid files
> alone is not sufficient.

This tool reads PROD's
``partner-collection-attempts.sqlite3`` (read-only) and
emits a per-underlying session completeness report. The
report classifies each session into one of five states
(plus the ready/not-ready gate):

  NEVER_ATTEMPTED       -- no rows for the expected tick
                            window.
  ATTEMPTED_UNAVAILABLE -- rows exist, but every public
                            capture was UNAVAILABLE.
  PARTIAL               -- some legs captured but at
                            least one row is incomplete
                            (terminal_state missing, or
                            candidate not observed, or
                            requested contracts not in
                            received contracts).
  STALE                 -- public inputs are past their
                            freshness window OR no updates
                            within 2x the interval.
  COMPLETE              -- full coverage with fresh inputs.

Plus a ``can_qualify`` aggregate: True iff every
underlying is COMPLETE.

The underlying Python helper
(``partner_collection_attempts.PartnerCollectionAttemptStore.session_readiness``)
already implements the classification; this CLI tool wraps
it for operator use and emits a structured report.

Read-only. Never writes to the archive.

Usage::

    # Audit the live PROD archive (today's session).
    python scripts/audit_session_completeness.py \\
        --archive-root /data/archive

    # Audit a specific session date.
    python scripts/audit_session_completeness.py \\
        --archive-root /data/archive \\
        --session-date 2026-09-14

    # JSON output.
    python scripts/audit_session_completeness.py \\
        --archive-root /data/archive \\
        --json

Exit codes:
  0  -- every underlying COMPLETE.
  1  -- at least one underlying not COMPLETE.
  2  -- input invalid (missing DB / archive root).
"""
from __future__ import annotations

import argparse
import dataclasses
import enum
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
from zoneinfo import ZoneInfo


def _load_store_class():
    """Lazy-load PartnerCollectionAttemptStore so the module
    can be imported without immediately pulling partner_decision_clock
    into sys.modules. This keeps the import isolated and
    avoids polluting the module cache for tests that don't
    exercise the audit path."""
    _PYTHON_ENGINE = Path(__file__).resolve().parents[1] / "python-engine"
    sys.path.insert(0, str(_PYTHON_ENGINE))
    from partner_collection_attempts import PartnerCollectionAttemptStore  # type: ignore[import-not-found]  # noqa: E402
    return PartnerCollectionAttemptStore


IST = ZoneInfo("Asia/Kolkata")


class CompletenessState(str, enum.Enum):
    """The five session completeness states."""
    NEVER_ATTEMPTED = "NEVER_ATTEMPTED"
    ATTEMPTED_UNAVAILABLE = "ATTEMPTED_UNAVAILABLE"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    COMPLETE = "COMPLETE"

    def exit_code(self) -> int:
        return 0 if self == CompletenessState.COMPLETE else 1

    def is_blocking(self) -> bool:
        """A blocking state prevents qualification."""
        return self != CompletenessState.COMPLETE


@dataclasses.dataclass(frozen=True)
class UnderlyingAudit:
    """Per-underlying session audit row.

    Attributes:
        underlying: the underlying symbol (e.g. ``NIFTY``).
        state: the CompletenessState.
        attempted: number of collection attempts in the window.
        expected: number of expected attempts.
        missing_schedule_count: expected - attempted (clamped >= 0).
        unavailable_count: rows where public_state != OBSERVED.
        incomplete_count: rows where candidate_state is not
            OBSERVED/NOT_REQUIRED, or where requested contracts
            are not in received contracts.
        stale_input_count: rows where the public input is past
            its freshness window.
        latest_updated_at_utc: latest update timestamp
            (UTC) for any row in the window.
        blocking_reasons: human-readable list of why this
            session is blocking.
    """
    underlying: str
    state: CompletenessState
    attempted: int
    expected: int
    missing_schedule_count: int
    unavailable_count: int
    incomplete_count: int
    stale_input_count: int
    latest_updated_at_utc: Optional[str]
    blocking_reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "underlying": self.underlying,
            "state": self.state.value,
            "attempted": self.attempted,
            "expected": self.expected,
            "missing_schedule_count": self.missing_schedule_count,
            "unavailable_count": self.unavailable_count,
            "incomplete_count": self.incomplete_count,
            "stale_input_count": self.stale_input_count,
            "latest_updated_at_utc": self.latest_updated_at_utc,
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclasses.dataclass(frozen=True)
class SessionAuditReport:
    """Combined session audit report.

    Attributes:
        session_date: the session date (ISO string).
        archive_root: the archive root that was audited.
        expected_attempts_per_index: how many attempts the
            scheduler expected.
        underlyings: tuple of UnderlyingAudit, one per
            underlying audited.
        can_qualify: ALWAYS False. The audit (A5) makes this
            explicit: collection completeness does NOT confer
            strategy qualification. The field is preserved
            for byte-identical output but its value is
            constant.
        collection_complete: True iff every underlying is COMPLETE.
            The audit (A6) adds this as the new "every
            collection slot is filled" boolean.
        eligible_for_replay: True iff every underlying is
            COMPLETE. The audit (A6) adds this as the
            separate "ready for replay" boolean; replay can
            run on a complete collection but it still needs
            a registered qualification to authorise a
            card.
    """
    session_date: str
    archive_root: str
    expected_attempts_per_index: int
    underlyings: tuple[UnderlyingAudit, ...]

    @property
    def collection_complete(self) -> bool:
        return all(
            u.state == CompletenessState.COMPLETE for u in self.underlyings
        )

    @property
    def eligible_for_replay(self) -> bool:
        return self.collection_complete

    @property
    def can_qualify(self) -> bool:
        # [WORKFLOW-A5 2026-09-20] Collection completeness does
        # NOT confer strategy qualification. The audit's
        # explicit invariant: a clean collection is necessary
        # but not sufficient. A registered, verified, in-window
        # qualification is also required.
        return False

    def to_dict(self) -> dict:
        return {
            "session_date": self.session_date,
            "archive_root": self.archive_root,
            "expected_attempts_per_index": self.expected_attempts_per_index,
            # [WORKFLOW-A5/A6 2026-09-20] Two new diagnostic keys.
            # `collection_complete`: every slot is filled; this is
            # the audit's "collection is clean" boolean.
            # `eligible_for_replay`: same definition today, but
            # preserved separately so a future change can split
            # "complete collection" from "ready for replay".
            # `can_qualify` is preserved as a constant False.
            "collection_complete": self.collection_complete,
            "eligible_for_replay": self.eligible_for_replay,
            "can_qualify": self.can_qualify,
            "underlyings": [u.to_dict() for u in self.underlyings],
        }


def _blocking_reasons_for(audit: dict) -> tuple[str, ...]:
    """Compute the human-readable blocking reasons for a single
    underlying audit row."""
    reasons: list[str] = []
    state = audit.get("state")
    if state == CompletenessState.NEVER_ATTEMPTED.value:
        reasons.append(
            f"no attempts in window (expected {audit.get('expected', 0)})"
        )
    elif state == CompletenessState.ATTEMPTED_UNAVAILABLE.value:
        reasons.append(
            f"all {audit.get('attempted', 0)} attempts UNAVAILABLE"
        )
    elif state == CompletenessState.PARTIAL.value:
        missing = audit.get("missing_schedule_count", 0)
        incomplete = audit.get("incomplete_count", 0)
        if missing:
            reasons.append(f"missing {missing} expected attempts")
        if incomplete:
            reasons.append(
                f"{incomplete} attempt(s) incomplete (candidate/contract gap)"
            )
    elif state == CompletenessState.STALE.value:
        stale = audit.get("stale_input_count", 0)
        if stale:
            reasons.append(
                f"{stale} attempt(s) past public-input freshness window"
            )
        else:
            reasons.append("no updates within 2x interval")
    return tuple(reasons)


def audit_session(
    *,
    archive_root: str | Path,
    session_date: date,
    underlyings: Iterable[str],
    entry_start_minute: int,
    entry_end_minute: int,
    now: Optional[datetime] = None,
    interval_seconds: int = 120,
    scheduler_second: int = 50,
    market_open: Optional[bool] = None,
    max_public_age_seconds: int = 360,
) -> SessionAuditReport:
    """Audit a session's collection completeness.

    Args:
        archive_root: path to PROD's archive root (the
            directory containing
            ``partner-collection-attempts.sqlite3``).
        session_date: the date to audit.
        underlyings: which underlyings to audit (e.g.
            ``["NIFTY", "SENSEX"]``).
        entry_start_minute: minutes since midnight IST
            when the session window opens.
        entry_end_minute: minutes since midnight IST when
            the session window closes.
        now: the current time (timezone-aware). Defaults
            to ``datetime.now(timezone.utc)``.
        interval_seconds: how often the scheduler ticks.
            Default 120 (2 minutes).
        scheduler_second: which second of each minute the
            tick fires. Default 50.
        market_open: override the trading-day check.
            None = auto-detect (Mon-Fri = True).
        max_public_age_seconds: how stale a public input
            can be before it's flagged. Default 360 (6 min).

    Returns:
        A ``SessionAuditReport`` with per-underlying audits.
    """
    # Lazy-load here so the symbol can be imported without
    # pulling partner_decision_clock into sys.modules. This
    # keeps test isolation for other audit scripts that
    # don't exercise the partner-collection-attempts path.
    if now is None:
        now = datetime.now(timezone.utc)
    store_class = _load_store_class()
    store = store_class(archive_root)
    underlying_list = list(underlyings)
    raw = store.session_readiness(
        session_date=session_date, now=now,
        underlyings=underlying_list,
        entry_start_minute=entry_start_minute,
        entry_end_minute=entry_end_minute,
        interval_seconds=interval_seconds,
        scheduler_second=scheduler_second,
        market_open=market_open,
        max_public_age_seconds=max_public_age_seconds,
    )
    per_index = raw.get("per_index", {})
    audits: list[UnderlyingAudit] = []
    for name in (n.upper() for n in underlying_list):
        row = per_index.get(name, {})
        try:
            state = CompletenessState(row.get("state", "NEVER_ATTEMPTED"))
        except ValueError:
            state = CompletenessState.NEVER_ATTEMPTED
        audit = UnderlyingAudit(
            underlying=name,
            state=state,
            attempted=int(row.get("attempted", 0)),
            expected=int(row.get("expected", 0)),
            missing_schedule_count=int(row.get("missing_schedule_count", 0)),
            unavailable_count=int(row.get("unavailable_count", 0)),
            incomplete_count=int(row.get("incomplete_count", 0)),
            stale_input_count=int(row.get("stale_input_count", 0)),
            latest_updated_at_utc=row.get("latest_updated_at_utc"),
            blocking_reasons=_blocking_reasons_for(row),
        )
        audits.append(audit)
    return SessionAuditReport(
        session_date=session_date.isoformat(),
        archive_root=str(archive_root),
        expected_attempts_per_index=int(
            raw.get("expected_attempts_per_index", 0)
        ),
        underlyings=tuple(audits),
    )


def format_report(report: SessionAuditReport) -> str:
    """Render the audit report as a human-readable string."""
    lines = [
        "# Session completeness audit",
        "# --------------------------",
        f"# session_date:  {report.session_date}",
        f"# archive_root:  {report.archive_root}",
        f"# expected attempts per index: {report.expected_attempts_per_index}",
        f"# can_qualify:    {report.can_qualify}",
        "",
    ]
    if not report.underlyings:
        lines.append("No underlyings audited.")
        return "\n".join(lines) + "\n"
    for u in report.underlyings:
        lines.append(f"## [{u.state.value}] {u.underlying}")
        lines.append(
            f"  attempted={u.attempted}/{u.expected}  "
            f"missing={u.missing_schedule_count}  "
            f"unavailable={u.unavailable_count}  "
            f"incomplete={u.incomplete_count}  "
            f"stale_inputs={u.stale_input_count}"
        )
        if u.latest_updated_at_utc:
            lines.append(f"  latest_updated_at: {u.latest_updated_at_utc}")
        if u.blocking_reasons:
            lines.append(f"  blocking reasons:")
            for reason in u.blocking_reasons:
                lines.append(f"    - {reason}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", required=True,
                        help="path to PROD's archive root")
    parser.add_argument("--session-date", default=None,
                        help="ISO date (default: today, IST)")
    parser.add_argument("--underlyings", nargs="+",
                        default=["NIFTY", "SENSEX"],
                        help="underlyings to audit")
    parser.add_argument("--entry-start-minute", type=int,
                        default=9*60 + 15,
                        help="session open minute (default 9:15 IST)")
    parser.add_argument("--entry-end-minute", type=int,
                        default=15*60 + 30,
                        help="session close minute (default 15:30 IST)")
    parser.add_argument("--interval-seconds", type=int, default=120,
                        help="scheduler interval (default 120s)")
    parser.add_argument("--scheduler-second", type=int, default=50,
                        help="scheduler second (default 50)")
    parser.add_argument("--market-open", choices=["yes", "no", "auto"],
                        default="auto",
                        help="trading-day override (default auto)")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    # Lazy-load PartnerCollectionAttemptStore inside main so
    # the audit_session() / audit_session_completeness()
    # symbols can be imported without polluting sys.modules.
    # This keeps the test isolation for other audit tests
    # that don't exercise the partner-collection-attempts
    # path.
    store_class = _load_store_class()

    if args.session_date:
        session_date = date.fromisoformat(args.session_date)
    else:
        session_date = datetime.now(IST).date()

    market_open: Optional[bool]
    if args.market_open == "yes":
        market_open = True
    elif args.market_open == "no":
        market_open = False
    else:
        market_open = None

    archive_root = Path(args.archive_root)
    if not archive_root.is_dir():
        print(
            f"audit_session_completeness: archive root not found: "
            f"{archive_root}", file=sys.stderr,
        )
        return 2
    # Check the partner-collection-attempts.sqlite3 exists.
    db_path = archive_root / "partner-collection-attempts.sqlite3"
    if not db_path.is_file():
        print(
            f"audit_session_completeness: archive SQLite file not found: "
            f"{db_path}", file=sys.stderr,
        )
        return 2

    raw = store_class(archive_root).session_readiness(
        session_date=session_date, now=datetime.now(timezone.utc),
        underlyings=list(args.underlyings),
        entry_start_minute=args.entry_start_minute,
        entry_end_minute=args.entry_end_minute,
        interval_seconds=args.interval_seconds,
        scheduler_second=args.scheduler_second,
        market_open=market_open,
    )
    per_index = raw.get("per_index", {})
    audits: list[UnderlyingAudit] = []
    for name in (n.upper() for n in args.underlyings):
        row = per_index.get(name, {})
        try:
            state = CompletenessState(row.get("state", "NEVER_ATTEMPTED"))
        except ValueError:
            state = CompletenessState.NEVER_ATTEMPTED
        audits.append(UnderlyingAudit(
            underlying=name,
            state=state,
            attempted=int(row.get("attempted", 0)),
            expected=int(row.get("expected", 0)),
            missing_schedule_count=int(row.get("missing_schedule_count", 0)),
            unavailable_count=int(row.get("unavailable_count", 0)),
            incomplete_count=int(row.get("incomplete_count", 0)),
            stale_input_count=int(row.get("stale_input_count", 0)),
            latest_updated_at_utc=row.get("latest_updated_at_utc"),
            blocking_reasons=_blocking_reasons_for(row),
        ))
    report = SessionAuditReport(
        session_date=session_date.isoformat(),
        archive_root=str(archive_root),
        expected_attempts_per_index=int(
            raw.get("expected_attempts_per_index", 0)
        ),
        underlyings=tuple(audits),
    )
    if args.json:
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
    else:
        sys.stdout.write(format_report(report))
    if not report.can_qualify:
        return 1
    return 0


__all__ = [
    "CompletenessState",
    "SessionAuditReport",
    "UnderlyingAudit",
    "audit_session",
    "format_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
