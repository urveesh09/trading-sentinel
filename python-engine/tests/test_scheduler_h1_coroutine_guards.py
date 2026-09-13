"""[WORKFLOW-H H1 2026-09-13] Scheduler coroutine leak regressions.

PROD-CRITICAL: this workstream ships to production on 2026-09-14.
The H1 acceptance contract is:

  * Every scheduled penny subsystem job (including the previously-
    raw run_penny_hourly_report) is wrapped so a transient
    substrate failure does not silently kill the cron.
  * Every closure is exercised by the parametrised closure-
    resolution test (already wired by adding
    run_penny_hourly_report_safe to ALL_CLOSURES).
  * No new coroutine leaks are introduced by the F3 wiring of
    mark_open_positions into run_penny_hourly_report.
  * The startup-catchup breadcrumb at scheduler_setup.py:590 does
    not produce an unawaited coroutine when the running loop is
    unavailable (the original 2026-07-02 bug).

[WHY-THIS-EXISTS 2026-09-13]
  Pre-fix, run_penny_hourly_report was the ONLY penny subsystem job
  registered raw (no _safe wrapper, no first-line breadcrumb). The
  other penny closures have all three: breadcrumb + wrapper +
  safe-pattern. This asymmetry was a real PROD gap because a
  transient NameError / AttributeError in the F3 wiring would
  propagate out of the cron instead of being logged.
"""
from __future__ import annotations

import asyncio
import inspect
import warnings

import pytest

from apscheduler.schedulers.asyncio import AsyncIOScheduler


def _registered_jobs():
    """Register penny + fno + partner jobs against a throwaway scheduler."""
    import main

    probe = AsyncIOScheduler(timezone=main.IST)
    main.register_penny_scheduler_jobs(probe)
    main.register_fno_scheduler_jobs(probe)
    main.register_partner_scheduler_jobs(probe)
    return {j.func.__name__: j.func for j in probe.get_jobs()}


class TestClosureRegistration:
    def test_penny_hourly_safe_is_registered(self):
        """The H1 wrapper must appear in the registered jobs roster."""
        jobs = _registered_jobs()
        assert "run_penny_hourly_report_safe" in jobs

    def test_penny_hourly_safe_replaces_bare_registration(self):
        """After H1, the registered callable for penny_hourly_report
        is the wrapper -- NOT the bare run_penny_hourly_report.

        This is the regression that catches a future refactor that
        reverts the safe wrapper (the production gap we are closing).
        """
        jobs = _registered_jobs()
        assert "run_penny_hourly_report" not in jobs, (
            "bare run_penny_hourly_report must not be registered; "
            "use run_penny_hourly_report_safe. Re-registering the "
            "bare form is the 2026-09-13 PROD gap we are closing."
        )
        assert "run_penny_hourly_report_safe" in jobs


class TestCoroutineLeakGuards:
    def test_penny_hourly_safe_does_not_leak_on_substrate_failure(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        """The H1 wrapper must catch substrate failures and not leak
        an unawaited coroutine. Substrate failure is simulated by
        patching main.is_trading_day to raise; under the wrapper
        the failure is caught and logged, NOT propagated.

        We use warnings.catch_warnings with simplefilter='error' for
        RuntimeWarning so an unawaited coroutine would surface as
        an error -- the test fails loudly if a leak returns.
        """
        import main

        async def _boom(*_a, **_kw):
            raise RuntimeError("simulated substrate failure")

        monkeypatch.setattr(main, "is_trading_day", _boom)
        closure = _registered_jobs()["run_penny_hourly_report_safe"]
        assert inspect.iscoroutinefunction(closure)

        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            # The wrapper must catch the substrate failure and return.
            # No unawaited coroutine is created (the wrapper itself
            # is awaited by the test).
            asyncio.run(closure())

    def test_penny_hourly_safe_catches_standard_exceptions(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        """The wrapper catches ValueError, RuntimeError, KeyError, etc.

        These are the exception types that substrate failures can
        legitimately raise. The wrapper logs and returns -- it does
        NOT propagate.
        """
        import main

        for exc_type in (ValueError, RuntimeError, KeyError, TypeError):
            async def _raise_specific(*_a, **_kw):
                raise exc_type("simulated " + exc_type.__name__)

            monkeypatch.setattr(main, "is_trading_day", _raise_specific)
            closure = _registered_jobs()["run_penny_hourly_report_safe"]
            # Must not raise -- the wrapper catches.
            asyncio.run(closure())

    def test_penny_hourly_safe_logs_breadcrumb_on_success(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        """On success, the wrapper emits the
        penny_hourly_report_invoked breadcrumb -- the operator
        debugging signal that the cron actually fired. With
        is_trading_day -> False the body exits early at the
        calendar gate; we still expect the breadcrumb to fire.

        The wrapper is a closure inside
        register_penny_scheduler_jobs that captures ``logger``
        from the enclosing scope at registration time. We
        monkeypatch main.logger and re-register so the wrapper
        binds to our recorder proxy instead of the real structlog
        logger.
        """
        import main

        recorded: list[tuple[str, tuple]] = []
        real_logger = main.logger

        async def _closed(*_a, **_kw):
            return False

        monkeypatch.setattr(main, "is_trading_day", _closed)

        class _RecordingLogger:
            def __init__(self, real):
                self._real = real

            def info(self, *args, **kwargs):
                recorded.append(("info", args))
                return self._real.info(*args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._real, name)

        recording_logger = _RecordingLogger(real_logger)
        monkeypatch.setattr(main, "logger", recording_logger)

        # Re-register with the patched logger so the wrapper
        # closure binds to the recorder.
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        probe = AsyncIOScheduler(timezone=main.IST)
        main.register_penny_scheduler_jobs(probe)
        closure = next(
            j.func for j in probe.get_jobs()
            if j.func.__name__ == "run_penny_hourly_report_safe"
        )
        asyncio.run(closure())

        breadcrumb_seen = any(
            len(args) >= 1 and "penny_hourly_report_invoked" in str(args[0])
            for _level, args in recorded
        )
        assert breadcrumb_seen, (
            "penny_hourly_report_invoked breadcrumb missing; "
            "operators will not be able to confirm the cron fired. "
            "Recorded log calls: " + repr(recorded)
        )

    def test_penny_hourly_safe_survives_create_task_await_cycle(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        """The wrapper is correctly awaited through an async call
        chain -- it does not return an unawaited coroutine when
        invoked from another coroutine.

        create_task + await is the canonical pattern the scheduler
        uses (scheduler_setup.py:590). If the wrapper returned a
        bare coroutine that escaped without being awaited, the
        warnings filter would raise it as a RuntimeWarning.
        """
        import main

        async def _closed(*_a, **_kw):
            return False

        monkeypatch.setattr(main, "is_trading_day", _closed)
        closure = _registered_jobs()["run_penny_hourly_report_safe"]

        async def _caller():
            task = asyncio.create_task(closure())
            await task

        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            asyncio.run(_caller())

    def test_penny_hourly_safe_handles_f3_import_failure(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        """F3 wired from mark_to_market import mark_open_positions
        inside the try block. If that import fails, the body
        try/except catches it. The H1 wrapper catches anything
        else.

        We simulate the failure by patching builtins.__import__
        so any from mark_to_market import X raises ImportError.
        """
        import builtins

        import main

        real_import = builtins.__import__

        def _patched_import(name, *args, **kwargs):
            if name == "mark_to_market" or name.startswith("mark_to_market."):
                raise ImportError("simulated F3 import failure")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _patched_import)

        async def _closed(*_a, **_kw):
            return True  # pass the calendar gate so we hit F3 imports

        monkeypatch.setattr(main, "is_trading_day", _closed)
        closure = _registered_jobs()["run_penny_hourly_report_safe"]
        # Body's ImportError is caught by the body's try/except;
        # the wrapper catches anything else.
        asyncio.run(closure())
