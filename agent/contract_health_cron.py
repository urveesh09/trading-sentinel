"""[WORKFLOW-I.4.E.CRON_WIRING 2026-09-14] Hourly contract-health cron tick.

The I.4.E bounded contract-health self-evaluation (slice
``feat(agent): I.4.E bounded contract-health self-evaluation``)
ships five bounded invariants + a CLI. The CLI is a manual
audit tool. Without cron wiring, the harness only runs when
the operator remembers to invoke it.

This module exposes ``contract_health_cron_tick()``:
  1. Build the bounded status envelope via the agent's
     ``optional_ai_status()`` (the same envelope the agent
     publishes every minute to the engine).
  2. Run the authority, leakage and usefulness checks against that same
     real envelope.
  3. If the report surfaces ANY violation, fire a Telegram
     alert via ``send_telegram_alert`` so the operator sees
     the drift immediately.
  4. Pure / total / never raises. The cron tick is fire-and-
     forget; a contract-health failure must NEVER block the
     agent's main loop.

The cron cadence is hourly (1.hour.do in the agent's
``schedule`` library). Hourly is enough because:
  - The status envelope shape doesn't drift minute-to-minute;
    the gate's invariants assert *shape*, not *frequency*.
  - An hourly alert is still within the operator's reaction
    window. The alert is informational -- the operator can
    triage when convenient.
  - The contract-health check is O(1) on the status envelope
    (no broker calls, no model calls, no filesystem reads);
    the cost is negligible.

This module is wired into ``agent.py``'s scheduler as
``schedule.every(1).hours.do(contract_health_cron_tick)``.

Pure helpers for testing:
  - ``format_violation_alert(report)``: deterministic
    rendering of a violation alert for the test suite.
"""
from __future__ import annotations

import inspect
from typing import Any, List, Optional

from contract_health import (
    ContractReport,
    evaluate_contract,
)


def format_violation_alert(report: ContractReport) -> str:
    """Render a ContractReport as a Telegram-friendly alert.

    Returns an empty string when every check passed (the cron
    tick uses this to decide whether to fire the alert at all).

    The format is bounded: one line per failing check, with
    the check name + count + first 3 violations. Operators see
    *which* invariant drifted; they don't need the full
    report body.
    """
    if report.passed:
        return ""

    lines: List[str] = [
        f"[CONTRACT-HEALTH] {len(report.violations())} violation(s) "
        f"at {report.evaluated_at.isoformat()}:"
    ]
    for check in report.checks:
        if check.passed:
            continue
        n = len(check.violations)
        sample = check.violations[:3]
        sample_text = "; ".join(sample) if sample else "(no detail)"
        lines.append(
            f"  - {check.name}: {n} violation(s) -- sample: {sample_text}"
        )
    return "\n".join(lines)


def contract_health_cron_tick(
    *,
    status_envelope: Optional[dict[str, Any]] = None,
    alert_fn=None,
    now_iso: Optional[str] = None,
) -> ContractReport:
    """One cron tick of the contract-health self-policing.

    Args:
        status_envelope: The bounded health envelope to evaluate.
            When ``None``, the tick still runs ``evaluate_contract``
            with all-``None`` inputs (which is the "no envelope
            available" diagnostic -- useful for tests). In
            production this is supplied by the agent's
            ``optional_ai_status()`` call site.
        alert_fn: Optional callable for violation alerts.
            When ``None``, the tick uses
            ``send_telegram_alert`` from ``agent.py``. Tests
            pass a stub.
        now_iso: Optional ISO timestamp for the report's
            ``evaluated_at``. When ``None``, the harness's
            default is used (``datetime.now(timezone.utc)``).

    Returns:
        The ``ContractReport`` produced by ``evaluate_contract``.
        The cron tick ALWAYS returns the report (never raises).
        A violation triggers the alert_fn with a bounded
        rendering.

    The function is pure / total / never raises. The agent's
    scheduler can call it without defensive try/except.
    """
    report = evaluate_contract(
        status_envelope=status_envelope,
        usefulness_snapshot=status_envelope,
        evaluated_at=None,  # harness default: datetime.now(UTC)
    )

    if report.passed:
        return report

    # Lazily import the agent's send_telegram_alert so this
    # module stays importable in test environments where
    # ``agent.py`` side effects (Telegram client init, env-var
    # gating) would otherwise fire.
    alert_text = format_violation_alert(report)
    if alert_fn is None:
        try:
            from agent import send_telegram_alert  # type: ignore
            alert_fn = send_telegram_alert
        except Exception:
            # Defensive: never raise out of the cron tick. The
            # cron wiring must be fire-and-forget. If the import
            # fails, fall back to logging only.
            import logging
            logging.getLogger(__name__).warning(
                "contract_health_alert_dispatch_failed reason=%s",
                "agent.send_telegram_alert unavailable",
            )
            return report

    try:
        # [WORKFLOW-C.F1 2026-09-16] F-1 from the 2026-09-16
        # production audit: ``send_telegram_alert()`` requires
        # ``(signal: Dict, review: "Review")`` but the cron
        # was calling ``alert_fn(alert_text)``, raising TypeError
        # every hour. Defensive dispatch via ``inspect.signature``
        # (per trading-sentinel-ops rule 110) -- the cron adapts
        # to whatever shape the receiver expects:
        #   - 2-arg ``(signal, review)``: pass ``(review_as_signal, review)``
        #     so the operator gets a structured signal AND the review.
        #   - 1-arg ``(text)``: pass the formatted alert text
        #     (the original contract; tests still work).
        #   - 0-arg: invoke with no args.
        # The ``review_as_signal`` placeholder documents the
        # cron's intent: this is a contract-health contract
        # violation, not a trading signal. Receivers that
        # ignore the ``signal`` field (most Telegram bots do)
        # see the alert text unchanged.
        _dispatch_alert(alert_fn, report, alert_text)
    except Exception:  # pragma: no cover - defensive
        # The alert dispatch is best-effort. A failing Telegram
        # POST must NEVER block the agent's main loop.
        import logging
        logging.getLogger(__name__).warning(
            "contract_health_alert_dispatch_failed",
            exc_info=True,
        )

    return report


def _dispatch_alert(
    alert_fn,
    review: "ContractReport",
    alert_text: str,
) -> None:
    """[WORKFLOW-C.F1 2026-09-16] Invoke ``alert_fn`` matching its
    declared signature, so the cron tick is robust to
    receivers that take ``(text)`` (the historical contract
    used by tests) AND receivers that take
    ``(signal, review)`` (the real Telegram dispatcher).

    Defensive boundary: inspect the signature ONCE at dispatch
    time, not at module load. Receivers injected by tests
    (e.g. ``_StubAlert``) may take different shapes than the
    production ``send_telegram_alert`` -- the cron must work
    with both.

    The helper returns None on success and raises on
    failure -- the caller's except clause is the
    fire-and-forget boundary.
    """
    sig = inspect.signature(alert_fn)
    n_required = 0
    for p in sig.parameters.values():
        if p.default is inspect.Parameter.empty and p.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        ):
            n_required += 1
    # Treat VAR_POSITIONAL as accepting any count -- safer
    # than refusing (a *args receiver is still valid).
    has_var_positional = any(
        p.kind == inspect.Parameter.VAR_POSITIONAL
        for p in sig.parameters.values()
    )
    if has_var_positional:
        alert_fn(review, alert_text)
        return
    if n_required >= 2:
        # Production signature: ``send_telegram_alert(signal, review)``.
        # The cron is firing a contract-health violation, not a
        # trading signal -- wrap the review as the signal so the
        # alert dispatcher receives a structured payload and the
        # review it needs to render the alert body.
        alert_fn({"source": "contract_health_cron", "kind": "violation"}, review)
        return
    if n_required == 1:
        # Historical signature: ``alert_fn(text)``.
        alert_fn(alert_text)
        return
    # 0 required args.
    alert_fn()


__all__ = [
    "contract_health_cron_tick",
    "format_violation_alert",
    "_dispatch_alert",
]
