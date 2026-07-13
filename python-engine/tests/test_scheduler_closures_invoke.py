"""[ROADMAP-4.1 stage 2, 2026-07-13] Invoke every scheduled closure.

THIS FILE IS THE PREREQUISITE FOR MOVING register_*_scheduler_jobs.

register_penny_scheduler_jobs and register_fno_scheduler_jobs define 8 async
closures and hand them to APScheduler. Python resolves a function's globals at
CALL time, against the module where the function was DEFINED. So if those
closures move to a new module and even one free name fails to come with them,
the result is a NameError raised only when the job actually fires -- in
production, at 09:20 on a Tuesday -- where the `_safe` wrappers catch it, log
it, and return. The scan simply never happens. Silently.

Nothing catches that today:
  * import succeeds (the body is never executed at import time);
  * the add_job census sees the registration, not the body;
  * and only 3 of the 8 closures are so much as NAMED in the test suite.

That is precisely the 2026-07-13 failure signature -- a healthy-looking engine
that quietly does nothing -- so it is not a risk worth taking on trust.

These tests do the one thing that proves the closures still resolve: they CALL
each one. The assertion is deliberately weak (it must not raise NameError /
AttributeError); the point is exercising the body, not re-testing the
subsystems, which have their own suites. A closure that runs to completion --
or that fails on a mocked-out dependency -- has resolved its globals.
"""
import inspect

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler


ALL_CLOSURES = [
    "_run_penny_edge_scan_safe",
    "_run_penny_edge_exit_safe",
    "_run_penny_accept_watchdog_safe",
    "_run_penny_premarket_report",
    "_run_fno_instruments_refresh",
    "_run_fno_tick_safe",
    "_run_fno_hourly_report_safe",
    "_run_fno_accept_watchdog_safe",
]


def _registered_jobs():
    """Register both families against a throwaway scheduler and return
    {func_name: callable} for every job. This is how we get our hands on the
    closures -- they are not importable, they only exist once register_* has
    run."""
    import main

    probe = AsyncIOScheduler(timezone=main.IST)
    main.register_penny_scheduler_jobs(probe)
    main.register_fno_scheduler_jobs(probe)
    return {j.func.__name__: j.func for j in probe.get_jobs()}


def test_all_eight_closures_are_registered():
    """If a closure stops being registered, the rest of this file would pass
    vacuously. Pin the roster first."""
    jobs = _registered_jobs()
    missing = [c for c in ALL_CLOSURES if c not in jobs]
    assert not missing, f"closures missing from the scheduler: {missing}"


@pytest.mark.parametrize("closure_name", ALL_CLOSURES)
@pytest.mark.asyncio
async def test_closure_resolves_its_globals_when_called(closure_name, monkeypatch):
    """Call the closure for real. It must not die on an unresolvable name.

    We force the calendar gate CLOSED (is_trading_day -> False) so each closure
    takes its earliest exit: enough to execute the top of the body -- the
    `datetime.now(IST)`, the `settings.X` reads, the `is_trading_day(...)` call
    -- without touching Kite, the network, or the database.

    That is exactly the region where a botched move breaks: the free names.
    """
    import main

    async def _closed(*a, **kw):
        return False

    # Patched BY NAME on main, which is the whole reason the moved code must
    # resolve these through main rather than binding them at import time.
    monkeypatch.setattr(main, "is_trading_day", _closed)

    closure = _registered_jobs()[closure_name]
    assert inspect.iscoroutinefunction(closure)

    try:
        await closure()
    except (NameError, AttributeError) as e:
        pytest.fail(
            f"{closure_name} could not resolve a global: {e!r}\n"
            f"This is the 4.1-stage-2 failure mode: the closure moved modules "
            f"and a free name did not come with it. In production this raises "
            f"only when the job fires, and the _safe wrapper swallows it -- "
            f"the scan just never runs."
        )
    except Exception:
        # Any OTHER exception is fine for this test's purpose: the body ran,
        # so its globals resolved. Subsystem behaviour is covered elsewhere.
        pass


# ===================================================================
# The net, widened.
# ===================================================================
# The version of this file that shipped with 4.1 stage 2 invoked only the 8
# closures. That gap let a REAL bug through: ops_watchdogs._ops_daily_snapshot
# calls is_trading_day, which stage 1 had failed to import into the new module.
# Import succeeded. The census saw the registration. The suite went green. And
# the job would have raised NameError at 15:50 every day, inside a try/except
# that logs and returns -- the daily ops snapshot would just have stopped.
#
# The lesson is that "the 8 closures" was never the right boundary. The right
# boundary is EVERY function the scheduler will call. So: call them all.

# Jobs that do real work even outside market hours and are not calendar-gated by
# design (see test_penny_cron_gating.NO_GATE_NEEDED). Invoking them here would
# hit Kite or rewrite state, and they were never moved between modules anyway.
_NOT_INVOKED = {
    "refresh_instrument_cache",
    "clear_intraday_cache",
    "_penny_daily_reset",
    "_scheduler_tick_job",     # writes a heartbeat file; covered by its own test
}


@pytest.mark.asyncio
async def test_every_scheduled_job_resolves_its_globals(monkeypatch):
    """Call EVERY registered job, not just the closures.

    Same contract as above: the assertion is only that the body can resolve its
    names. With the calendar gate forced closed, each job takes its earliest
    exit -- which is exactly the region where a botched move breaks.
    """
    import main

    async def _closed(*a, **kw):
        return False

    # Patch on every module that resolves the gate, since the extracted modules
    # import it directly rather than through main.
    import ops_watchdogs
    import scheduler_setup  # noqa: F401  (ensures it is importable)

    monkeypatch.setattr(main, "is_trading_day", _closed)
    monkeypatch.setattr(ops_watchdogs, "is_trading_day", _closed)

    jobs = _registered_jobs()

    # Plus the jobs main registers inline in lifespan(), which _registered_jobs
    # cannot see -- reach them by name off their modules.
    extra = {
        "_ops_daily_snapshot": ops_watchdogs._ops_daily_snapshot,
        "_kite_endpoint_probe_tick": ops_watchdogs._kite_endpoint_probe_tick,
    }
    jobs.update(extra)

    failures = []
    for name, fn in sorted(jobs.items()):
        if name in _NOT_INVOKED:
            continue
        if not inspect.iscoroutinefunction(fn):
            continue
        try:
            await fn()
        except (NameError, AttributeError) as e:
            failures.append(f"{name}: {e!r}")
        except Exception:
            pass  # body ran; its globals resolved

    assert not failures, (
        "scheduled job(s) could not resolve a global -- they would raise only "
        "when the job FIRES, in production, inside a _safe wrapper that logs "
        "and returns. The scan/report simply never happens:\n  "
        + "\n  ".join(failures)
    )


@pytest.mark.asyncio
async def test_calendar_gate_is_actually_honoured(monkeypatch):
    """Sanity-check the mechanism the test above leans on: with the calendar
    gate closed, the closures must not proceed into real work. If this ever
    stops holding, the invocation tests above are reaching further than
    intended and could start hitting the network."""
    import main

    called = {"n": 0}

    async def _closed(*a, **kw):
        called["n"] += 1
        return False

    monkeypatch.setattr(main, "is_trading_day", _closed)

    jobs = _registered_jobs()
    for name in ALL_CLOSURES:
        try:
            await jobs[name]()
        except (NameError, AttributeError):
            raise
        except Exception:
            pass

    assert called["n"] > 0, (
        "no closure consulted is_trading_day -- either the calendar gate "
        "regressed, or these closures are no longer gated (see "
        "test_penny_cron_gating)."
    )
