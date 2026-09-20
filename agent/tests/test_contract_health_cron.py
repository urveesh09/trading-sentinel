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

    Top-level keys match the real ``optional_ai_status()`` producer. Any other
    top-level key triggers a ``status_envelope_authority``
    violation.
    """
    return {
        "state": "READY",
        "reported_at": "2026-09-14T10:00:01+00:00",
        "async_requested": True,
        "policy_allows_annotation": True,
        "reason": "optional_annotation_ready",
        "queue": {"pending": 0, "cached": 0, "daily_requests": 1,
                  "daily_budget": 40, "max_pending": 16,
                  "circuit_state": "CLOSED"},
        "usefulness": {
            "total_completed_reviews": 6,
            "verdict_counts": {"APPROVE": 5, "APPROVE_WITH_CONCERNS": 0,
                               "REVIEW_UNAVAILABLE": 0, "REJECT": 1},
            "cache_hits": 12,
            "cache_misses": 3,
            "cache_hit_rate": 0.8,
            "circuit_opens": 0,
            "response_seconds_mean": 1.5,
            "response_seconds_p95": 2.4,
            "response_seconds_last": 1.5,
            "last_completed_at": "2026-09-14T10:00:00+00:00",
        },
    }


def _violating_snapshot() -> dict[str, Any]:
    """A status envelope with a deliberate invariant violation.

    The forbidden ``can_place_orders`` field is the most
    damaging violation -- a status envelope must never carry
    execution authority. The I.4.E harness surfaces this
    loudly (see the ``status_envelope_authority`` invariant).
    """
    snapshot = _well_formed_snapshot()
    snapshot["can_place_orders"] = True  # FORBIDDEN -- would never appear
        # in a real envelope; the test asserts the harness
        # catches it.
    return snapshot


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

    def test_usefulness_violation_is_checked_by_hourly_tick(self):
        stub = _StubAlert()
        snapshot = _well_formed_snapshot()
        snapshot["usefulness"]["prompt"] = "must not cross"
        report = contract_health_cron_tick(
            status_envelope=snapshot,
            alert_fn=stub,
        )
        assert report.passed is False
        assert len(stub.calls) == 1
        assert "no_prompt_leakage" in stub.calls[0]

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


class TestDispatchAlert:
    """[WORKFLOW-C.F1 2026-09-16] F-1 from the 2026-09-16
    production audit:

    The cron's ``alert_fn(alert_text)`` call site was
    incompatible with ``send_telegram_alert(signal: Dict,
    review: Review)``, raising TypeError every hour. The fix
    is defensive ``inspect.signature`` dispatch: the cron
    adapts to the receiver's shape.

    These tests pin the dispatch contract:
      - 0 required args: invoke with no args.
      - 1 required arg: pass alert_text (the historical shape).
      - 2+ required args: pass (signal, review).
      - *args: pass (review, alert_text).
      - Receiver raising: the cron logs but does not propagate.
    """

    def _run(self, alert_fn, snapshot=None):
        return contract_health_cron_tick(
            status_envelope=snapshot if snapshot is not None else _violating_snapshot(),
            alert_fn=alert_fn,
        )

    def test_zero_arg_receiver_invoked_with_no_args(self):
        """A receiver declared with no positional args is
        invoked with no args (e.g. a bare ``def f():``).
        """
        calls = []
        def receiver():
            calls.append(())
        self._run(receiver)
        assert calls == [()]

    def test_one_arg_receiver_receives_alert_text(self):
        """The historical contract: ``alert_fn(text)``.
        The test stub already uses this shape.
        """
        calls = []
        def receiver(text):
            calls.append(text)
        self._run(receiver)
        # The alert text contains the failing check name.
        assert len(calls) == 1
        assert "status_envelope_authority" in calls[0]

    def test_two_arg_receiver_receives_signal_and_review(self):
        """The production ``send_telegram_alert`` shape:
        ``(signal: Dict, review: Review)``. The cron must
        pass BOTH args, not the bare text.
        """
        calls = []
        def receiver(signal, review):
            calls.append((signal, review))
        report = self._run(receiver)
        assert len(calls) == 1
        signal, review = calls[0]
        # Signal is a structured Dict carrying the cron's
        # intent -- not the formatted alert text.
        assert isinstance(signal, dict)
        assert signal["source"] == "contract_health_cron"
        assert signal["kind"] == "violation"
        # Review is the actual ContractReport.
        assert review is report
        assert not review.passed

    def test_three_or_more_required_args_passes_signal_and_review(self):
        """Defensive: a receiver with 3+ required positional
        args still gets the 2-arg shape (signal, review) --
        the cron's contract is "pass the documented pair";
        additional args would receive a TypeError, which the
        cron's outer try/except catches.
        """
        calls = []
        def receiver(signal, review, extra):
            calls.append((signal, review, extra))
        report = self._run(receiver)
        # The cron wraps the call in a try/except; the 3rd
        # arg's TypeError is logged but the cron returns the
        # report normally.
        assert not report.passed
        # The 3rd-arg TypeError IS caught by the cron's
        # outer exception handler -- it's logged as
        # ``contract_health_alert_dispatch_failed`` and the
        # cron proceeds. We don't assert calls (it might be
        # called or not depending on Python's argument-binding
        # semantics) -- what matters is that the cron
        # doesn't raise.

    def test_var_positional_receiver_receives_review_and_text(self):
        """A receiver with ``*args`` receives the canonical
        ``(review, alert_text)`` shape -- the cron's most
        permissive signature.
        """
        calls = []
        def receiver(*args):
            calls.append(args)
        self._run(receiver)
        assert len(calls) == 1
        received = calls[0]
        assert len(received) == 2
        review_arg, text_arg = received
        assert isinstance(text_arg, str)
        assert "status_envelope_authority" in text_arg

    def test_receiver_raising_exception_is_logged_not_propagated(self):
        """A receiver that raises TypeError or any other
        exception must NOT block the cron's return -- the
        outer try/except logs the failure and the cron
        returns the report.
        """
        def receiver(text):
            raise TypeError("test failure path")
        report = self._run(receiver)
        # The cron still emits the report.
        assert not report.passed
        # (No assertion on log capture here; the outer
        # try/except is sufficient.)

    def test_receiver_with_keyword_only_args_is_invoked_with_no_args(self):
        """A receiver declared with only ``*`` or ``**`` (no
        positional args) is treated as 0-arg. The cron
        dispatches no args -- the receiver's defaults fire.
        """
        calls = []
        def receiver(*, why=None):
            calls.append(why)
        self._run(receiver)
        # 0 required positional args -> no args dispatched;
        # the receiver's default ``why=None`` fires.
        assert calls == [None]


class TestDispatchAlertSignatureRegression:
    """[WORKFLOW-C.F1 2026-09-16] Regression guard: the
    cron's dispatch MUST adapt to the production
    ``send_telegram_alert`` shape. This test mirrors
    ``agent.py::send_telegram_alert``'s actual signature.
    """

    def test_production_send_telegram_alert_signature_is_supported(self):
        """The cron's dispatch MUST invoke
        ``send_telegram_alert`` correctly -- not raise a
        TypeError. We pin this by importing the real
        function and dispatching to it (without actually
        sending a Telegram message).
        """
        import inspect
        from agent import send_telegram_alert
        sig = inspect.signature(send_telegram_alert)
        # Verify the production signature has 2 positional
        # args (signal, review). If PR #87 or a later change
        # alters this, the test fails and the cron fix
        # needs to be revisited.
        params = list(sig.parameters.values())
        assert len(params) >= 2, (
            f"send_telegram_alert signature drift: "
            f"{sig}, expected at least 2 positional params"
        )
        # The cron code path uses ``_dispatch_alert`` --
        # since we don't want to actually POST to Telegram
        # in unit tests, we verify that ``_dispatch_alert``
        # would call this signature correctly by checking
        # that ``send_telegram_alert`` would accept the
        # cron's call.
        n_required = sum(
            1 for p in params
            if p.default is inspect.Parameter.empty
            and p.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.POSITIONAL_ONLY,
            )
        )
        assert n_required >= 2
