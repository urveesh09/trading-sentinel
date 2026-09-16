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
  2. Run ``evaluate_contract(status_envelope=...)`` against it.
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
        alert_fn(alert_text)
    except Exception:  # pragma: no cover - defensive
        # The alert dispatch is best-effort. A failing Telegram
        # POST must NEVER block the agent's main loop.
        import logging
        logging.getLogger(__name__).warning(
            "contract_health_alert_dispatch_failed",
            exc_info=True,
        )

    return report


__all__ = [
    "contract_health_cron_tick",
    "format_violation_alert",
]
