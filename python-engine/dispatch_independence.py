"""[WORKFLOW-A.5 2026-09-17] Dispatch independence verification.

Per Workstream A in NEXT_AGENT_PLAN.md:
> Keep final dispatch revalidation independent: source
> availability does not grant transport authority.

The dispatcher (``partner_orchestrator._send_event``) must
not send a message just because the source data was
available. It must independently revalidate:

  1. partner is enabled
     (``settings.PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED``)
  2. within the configured session window
  3. trading day
  4. fresh-ish Kite access token

If any of these fail, the dispatcher suppresses the
message even if the source data was captured and the
candidate was constructed.

This module exposes:

  - ``DispatchGateStatus`` -- enum of gate outcomes.
  - ``check_dispatch_gates(...)`` -- pure, deterministic
    check that returns the gate status from explicit
    boolean inputs (so callers / tests don't need to
    instantiate the live ``settings`` / ``kite`` globals).
  - ``DispatchGateReport`` -- the report dataclass with
    each gate's status + a single ``overall_ok`` flag.
  - ``dispatch_independence_assertion(...)`` -- the
    single-call helper that returns a structured
    explanation string for the audit pipeline.

The live dispatcher in ``partner_orchestrator._send_event``
already implements these gates. This module pins the
contract so the audit pipeline can verify it without
having to mock the entire dispatcher.

Read-only. No DB writes. No network. No Telegram.
"""
from __future__ import annotations

import dataclasses
import enum
from datetime import datetime, time
from typing import Optional


class GateOutcome(str, enum.Enum):
    """Outcome of a single dispatch gate."""
    PASS = "PASS"
    FAIL = "FAIL"

    def exit_code(self) -> int:
        return 0 if self == GateOutcome.PASS else 1


@dataclasses.dataclass(frozen=True)
class DispatchGateStatus:
    """Per-gate result."""
    outcome: GateOutcome
    reason: str = ""


@dataclasses.dataclass(frozen=True)
class DispatchGateReport:
    """Combined report for all dispatch gates.

    Attributes:
        enabled: GateOutcome for ``partner_enabled``.
        in_session_window: GateOutcome for session window.
        is_trading_day: GateOutcome for trading day check.
        fresh_token: GateOutcome for fresh-ish token check.
        overall_ok: True iff all gates PASS.
    """
    enabled: DispatchGateStatus
    in_session_window: DispatchGateStatus
    is_trading_day: DispatchGateStatus
    fresh_token: DispatchGateStatus

    @property
    def overall_ok(self) -> bool:
        return all(
            g.outcome == GateOutcome.PASS
            for g in (self.enabled, self.in_session_window,
                       self.is_trading_day, self.fresh_token)
        )

    def failed_gates(self) -> tuple[str, ...]:
        """Names of gates that did not pass."""
        out: list[str] = []
        for name, gate in (
            ("enabled", self.enabled),
            ("in_session_window", self.in_session_window),
            ("is_trading_day", self.is_trading_day),
            ("fresh_token", self.fresh_token),
        ):
            if gate.outcome != GateOutcome.PASS:
                out.append(name)
        return tuple(out)

    def to_dict(self) -> dict:
        return {
            "enabled": {"outcome": self.enabled.outcome.value,
                          "reason": self.enabled.reason},
            "in_session_window": {
                "outcome": self.in_session_window.outcome.value,
                "reason": self.in_session_window.reason,
            },
            "is_trading_day": {
                "outcome": self.is_trading_day.outcome.value,
                "reason": self.is_trading_day.reason,
            },
            "fresh_token": {
                "outcome": self.fresh_token.outcome.value,
                "reason": self.fresh_token.reason,
            },
            "overall_ok": self.overall_ok,
            "failed_gates": list(self.failed_gates()),
        }


def check_dispatch_gates(
    *,
    now: datetime,
    enabled: bool,
    session_open_minute: int,
    session_close_minute: int,
    is_trading_day: bool,
    token_fresh: bool,
    token_max_age_seconds: int = 24 * 3600,
) -> DispatchGateReport:
    """Check all dispatch gates and return the combined report.

    Args:
        now: the current time (timezone-aware).
        enabled: whether partner delivery is enabled.
        session_open_minute: minutes since midnight (IST)
            when the session opens.
        session_close_minute: minutes since midnight (IST)
            when the session closes.
        is_trading_day: True iff today is a configured
            trading day.
        token_fresh: True iff the Kite access token is
            fresh-ish (not expired).
        token_max_age_seconds: the max age (seconds) before
            a token is considered stale. Default 24 hours.
            Currently unused (the dispatcher checks
            ``access_token`` truthiness, not age).

    Returns:
        A ``DispatchGateReport`` with each gate's outcome
        + the ``overall_ok`` aggregate.
    """
    minutes_now = now.hour * 60 + now.minute
    in_window = session_open_minute <= minutes_now <= session_close_minute
    return DispatchGateReport(
        enabled=DispatchGateStatus(
            outcome=GateOutcome.PASS if enabled else GateOutcome.FAIL,
            reason=(
                "delivery enabled"
                if enabled
                else "delivery disabled (PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED=False)"
            ),
        ),
        in_session_window=DispatchGateStatus(
            outcome=GateOutcome.PASS if in_window else GateOutcome.FAIL,
            reason=(
                f"now {minutes_now}min is within "
                f"[{session_open_minute}, {session_close_minute}]"
                if in_window
                else f"now {minutes_now}min is outside session window "
                f"[{session_open_minute}, {session_close_minute}]"
            ),
        ),
        is_trading_day=DispatchGateStatus(
            outcome=GateOutcome.PASS if is_trading_day else GateOutcome.FAIL,
            reason=(
                "today is a configured trading day"
                if is_trading_day
                else "today is not a configured trading day"
            ),
        ),
        fresh_token=DispatchGateStatus(
            outcome=GateOutcome.PASS if token_fresh else GateOutcome.FAIL,
            reason=(
                "kite access token is fresh"
                if token_fresh
                else "kite access token is missing or stale"
            ),
        ),
    )


def dispatch_independence_assertion(
    *,
    source_data_captured: bool,
    candidate_constructed: bool,
    dispatch_report: DispatchGateReport,
) -> str:
    """Single-call helper that asserts dispatch independence.

    Returns a structured explanation string suitable for
    audit logs. The point of this helper:

    Even if ``source_data_captured`` and
    ``candidate_constructed`` are both True, the message
    must NOT be dispatched unless the dispatch gates also
    pass. This pins the plan's rule: 'source availability
    does not grant transport authority'.

    Returns:
        A structured explanation of the gate result.
    """
    if source_data_captured and candidate_constructed:
        # Source is available -- but dispatch is governed by
        # the gates, not by source availability.
        if dispatch_report.overall_ok:
            return (
                "DISPATCH_INDEPENDENCE_OK: "
                "source available + candidate constructed + "
                "all dispatch gates passed"
            )
        failed = dispatch_report.failed_gates()
        return (
            "DISPATCH_SUPPRESSED_BY_GATES: "
            f"source available + candidate constructed, but gates "
            f"failed: {failed}. Source availability does NOT grant "
            "transport authority."
        )
    # Source not fully available -- dispatcher should already
    # have no candidate to dispatch.
    if not source_data_captured:
        return "DISPATCH_NOT_TRIGGERED: source not captured"
    return "DISPATCH_NOT_TRIGGERED: candidate not constructed"


__all__ = [
    "DispatchGateReport",
    "DispatchGateStatus",
    "GateOutcome",
    "check_dispatch_gates",
    "dispatch_independence_assertion",
]
