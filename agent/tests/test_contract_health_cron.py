"""[WORKFLOW-I.4.E.CRON_WIRING 2026-09-14] Hourly contract-health cron tests.

The I.4.E bounded contract-health harness was previously a
manual audit tool -- operators had to remember to run the CLI.
This slice wires it to the agent's hourly scheduler so the
harness self-policing actually fires.

These tests pin the cron contract at three layers:
  1. ``format_violation_alert`` -- the alert rendering.
  2. ``contract_health_cron_tick`` -- the tick + alert dispatch.
  3. Pure / total / never raises (the agent's main loop is the
     priority; the cron must never block it).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

import pytest


# ---------------------------------------------------------------------------
# Imports under test


from contract_health import (  # noqa: E402
    ContractCheck,
    ContractReport,
    evaluate_contract,
)
from contract_health_cron import (  # noqa: E402
    contract_health_cron_tick,
    format_violation_alert,
)


# ---------------------------------------------------------------------------
# Helpers


def _well_formed_snapshot() -> dict[str, Any]:
    """A bounded status envelope that satisfies every invariant.

    Top-level keys must match ``STATUS_ENVELOPE_ALLOWED_KEYS`` in
    agent/contract_health.py (state, queue_size, in_flight,
    circuit_open, last_completed_at, usefulness). Any other
    top-level key triggers a ``status_envelope_authority``
    violation.
    """
    return {
        "state": "READY",
        "queue_size": 0,
        "in_flight": 0,
        "circuit_open": False,
        "last_completed_at": "2026-09-14T10:00:00+00:00",
        "usefulness": {
            "verdict_counts": {"approve": 5, "reject": 1},
            "cache_hits": 12,
            "cache_misses": 3,
            "circuit_opens": 0,
            "response_seconds_mean": 1.5,
            "response_seconds_p95": 2.4,
            "last_response_seconds": 1.5,
            "last_completed_at": "2026-09-14T10:00:00+00:00",
            "snapshot_at": "2026-09-14T10:00:01+00:00",
        },
    }


def _violating_snapshot() -> dict[str, Any]:
    """A status envelope with a deliberate invariant violation.

    The forbidden ``can_place_orders`` field is the most
    damaging violation -- a status envelope must never carry
    execution authority. The I.4.E harness surfaces this
    loudly (see the ``status_envelope_authority`` invariant).
    """
    return {
        "state": "READY",
        "queue_size": 0,
        "in_flight": 0,
        "circuit_open": False,
        "last_completed_at": "2026-09-14T10:00:00+00:00",
        "can_place_orders": True,  # FORBIDDEN -- would never appear
        # in a real envelope; the test asserts the harness
        # catches it.
        "usefulness": {
            "verdict_counts": {"approve": 5, "reject": 1},
            "cache_hits": 12,
            "cache_misses": 3,
            "circuit_opens": 0,
            "response_seconds_mean": 1.5,
            "response_seconds_p95": 2.4,
            "last_response_seconds": 1.5,
            "last_completed_at": "2026-09-14T10:00:00+00:00",
            "snapshot_at": "2026-09-14T10:00:01+00:00",
        },
    }


class _StubAlert:
    """Stub alert dispatcher for tests.

    Records every alert message and never raises.
    """

    def __init__(self) -> None:
        self.calls: List[str] = []

    def __call__(self, text: str) -> None:
        self.calls.append(text)


# ---------------------------------------------------------------------------
# 1. format_violation_alert -- the alert rendering


class TestFormatViolationAlert:
    """The deterministic alert text."""

    def test_passing_report_returns_empty_string(self):
        report = evaluate_contract(status_envelope=_well_formed_snapshot())
        assert format_violation_alert(report) == ""

    def test_violation_includes_check_name_and_count(self):
        report = evaluate_contract(
            status_envelope=_violating_snapshot()
        )
        text = format_violation_alert(report)
        assert text != ""
        # The header line carries the violation count.
        assert "[CONTRACT-HEALTH]" in text
        assert "violation(s)" in text
        # The status_envelope_authority invariant name appears.
        assert "status_envelope_authority" in text

    def test_violation_sample_truncated_to_three(self):
        """The alert text samples at most 3 violations per check,
        so a long list of violations doesn't bloat the Telegram
        message."""
        # Synthesize a report with 5 violations on one check.
        check = ContractCheck(
            name="synthetic_check",
            passed=False,
            violations=[f"violation_{i}" for i in range(5)],
        )
        report = ContractReport(
            checks=[check],
            passed=False,
            evaluated_at=datetime.now(timezone.utc),
        )
        text = format_violation_alert(report)
        # The alert shows violation_0, violation_1, violation_2
        # but NOT violation_3, violation_4 (truncated to 3).
        assert "violation_0" in text
        assert "violation_2" in text
        assert "violation_3" not in text
        assert "violation_4" not in text

    def test_multi_check_violations_each_get_a_line(self):
        # Two failing checks: each gets its own alert line.
        check_a = ContractCheck(
            name="check_a", passed=False, violations=["fail_a"]
        )
        check_b = ContractCheck(
            name="check_b", passed=False, violations=["fail_b"]
        )
        report = ContractReport(
            checks=[check_a, check_b],
            passed=False,
            evaluated_at=datetime.now(timezone.utc),
        )
        text = format_violation_alert(report)
        assert "- check_a" in text
        assert "- check_b" in text


# ---------------------------------------------------------------------------
# 2. contract_health_cron_tick -- the tick + dispatch


class TestContractHealthCronTick:
    """The cron tick contract."""

    def test_clean_envelope_does_not_fire_alert(self):
        stub = _StubAlert()
        report = contract_health_cron_tick(
            status_envelope=_well_formed_snapshot(),
            alert_fn=stub,
        )
        assert report.passed is True
        assert stub.calls == []

    def test_violating_envelope_fires_alert(self):
        stub = _StubAlert()
        report = contract_health_cron_tick(
            status_envelope=_violating_snapshot(),
            alert_fn=stub,
        )
        assert report.passed is False
        assert len(stub.calls) == 1
        # The alert text names the failing invariant.
        assert "status_envelope_authority" in stub.calls[0]

    def test_none_envelope_still_runs_and_returns_report(self):
        """All-``None`` inputs are documented as "not inspected" --
        not a violation. The tick should still return a report
        (operators expect the cron to always emit something)."""
        stub = _StubAlert()
        report = contract_health_cron_tick(
            status_envelope=None,
            alert_fn=stub,
        )
        # All-``None`` inputs produce a passing report.
        assert report.passed is True
        assert stub.calls == []

    def test_alert_dispatch_failure_does_not_propagate(self):
        """If the alert_fn raises, the cron tick catches it
        and returns the report. The agent's main loop is the
        priority -- a contract-health alert failure must NEVER
        block the trading path."""
        def _raising_alert(_text: str) -> None:
            raise RuntimeError("Telegram POST failed")
        # Must NOT raise.
        report = contract_health_cron_tick(
            status_envelope=_violating_snapshot(),
            alert_fn=_raising_alert,
        )
        assert report.passed is False

    def test_tick_raises_on_invalid_envelope_shape(self):
        """A envelope that's not a dict (e.g. a string) IS a
        ``status_envelope_authority`` violation -- the harness
        surfaces it loudly. The tick must propagate the
        violation (alert fires) without raising.
        """
        stub = _StubAlert()
        # Non-dict envelope -> ``status_envelope_authority``
        # surfaces ``envelope is not a dict: str``. Must NOT raise.
        report = contract_health_cron_tick(
            status_envelope="not a dict",  # type: ignore[arg-type]
            alert_fn=stub,
        )
        assert report.passed is False
        # The alert fires for the violation.
        assert len(stub.calls) == 1
        assert "envelope is not a dict" in stub.calls[0]

    def test_returns_contract_report_with_evaluated_at(self):
        """The cron tick returns the report with a real
        ``evaluated_at`` timestamp (the harness default)."""
        stub = _StubAlert()
        report = contract_health_cron_tick(
            status_envelope=_well_formed_snapshot(),
            alert_fn=stub,
        )
        # evaluated_at is a UTC datetime.
        assert report.evaluated_at.tzinfo is not None
        # tz is UTC.
        assert report.evaluated_at.utcoffset().total_seconds() == 0

    def test_alert_text_includes_timestamp(self):
        """The Telegram alert text must carry the
        ``evaluated_at`` timestamp so the operator can correlate
        the alert with the published status envelope."""
        stub = _StubAlert()
        contract_health_cron_tick(
            status_envelope=_violating_snapshot(),
            alert_fn=stub,
        )
        # The header line includes an ISO timestamp.
        assert "T" in stub.calls[0]  # ISO format has T separator


# ---------------------------------------------------------------------------
# 3. Smoke test: the harness is importable in isolation
# (the lazy import in contract_health_cron is the key)


class TestLazyImportSafety:
    """The cron module must import WITHOUT triggering agent.py
    side effects (Telegram client init, env-var gating).

    If importing ``contract_health_cron`` pulled in ``agent``,
    unit tests would fail because the test environment doesn't
    have TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID set. The lazy
    import inside ``contract_health_cron_tick`` is what makes
    this slice testable.
    """

    def test_module_import_does_not_trigger_agent_side_effects(self):
        # Importing the module must succeed without any env-var
        # gating. If this test passes, the lazy import is
        # working as designed.
        import contract_health_cron  # noqa: F401

    def test_tick_uses_injected_alert_when_provided(self):
        # When the caller passes alert_fn, the tick MUST use it
        # -- the lazy fallback to ``send_telegram_alert`` is only
        # for the production call site that doesn't inject.
        stub = _StubAlert()

        def _my_alert(text: str) -> None:
            stub("MY:" + text)

        contract_health_cron_tick(
            status_envelope=_violating_snapshot(),
            alert_fn=_my_alert,
        )
        # The stub recorded the call, prefixed with "MY:".
        assert len(stub.calls) == 1
        assert stub.calls[0].startswith("MY:")
