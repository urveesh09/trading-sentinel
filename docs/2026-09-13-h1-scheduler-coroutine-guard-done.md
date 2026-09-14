# H1 (scheduler coroutine warning) — done and committed

## What landed (commit `dc298e5`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 7 (1 new, 6 modified), +354 / -4 lines
**Tests**: +8 net passing
**Whole-engine**: 2,930 passed / 4 skipped / 39 warnings in 129.02s
**Status**: H1 done; **PROD-ready for 2026-09-14 deployment**.

## The PROD gap we closed

Pre-fix, `run_penny_hourly_report` was the **only** penny subsystem job registered raw (no `_safe` wrapper, no first-line breadcrumb). Every other penny subsystem job — `_run_penny_edge_scan_safe`, `_run_penny_edge_exit_safe`, `_run_penny_accept_watchdog_safe`, etc. — has the `[PENNY-EDGE-BREADCRUMB 2026-07-06]` discipline: first-line diagnostic log + `_safe` wrapper that catches `Exception` and logs.

With the F3 wiring that pulls in `mark_to_market.mark_open_positions` and the F-series substrates (F1/F2/F4/F5/F6), a transient `NameError`/`AttributeError` in any of those reads would have propagated out of the cron — silently, because nothing would log an error. The hourly report would have stopped emitting for the rest of the day with **zero diagnostic signal**.

H1 ships:
1. `run_penny_hourly_report_safe` wrapper inside `register_penny_scheduler_jobs`.
2. The wrapper added to `ALL_CLOSURES` (the parametrised closure-resolution test).
3. The cron re-registered to use the wrapper with the standard `max_instances=1, coalesce=True, misfire_grace_time=600`.
4. Seven explicit coroutine-leak regression tests.

## Code surface

### `python-engine/scheduler_setup.py` (+73 lines)

```python
async def run_penny_hourly_report_safe():
    logger.info(
        "penny_hourly_report_invoked now_ist=%s source=cron_or_catchup",
        datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
    )
    try:
        today = datetime.now(IST).date()
        if not await _main.is_trading_day(today, settings.DB_PATH):
            logger.info("penny_hourly_report_skip reason=non_trading_day")
            return
        await run_penny_hourly_report()
    except Exception as exc:
        logger.error(
            "penny_hourly_report_failed err=%s", exc, exc_info=True,
        )
```

The cron registration was changed from:
```python
scheduler.add_job(run_penny_hourly_report, "cron", ..., id="penny_hourly_report")
```
to:
```python
scheduler.add_job(
    run_penny_hourly_report_safe, "cron", ...,
    id="penny_hourly_report",
    max_instances=1, coalesce=True, misfire_grace_time=600,
)
```

The bare `run_penny_hourly_report` in `main.py` is **untouched** — still callable manually; the wrapper is purely additive.

### `python-engine/tests/test_scheduler_closures_invoke.py` (+7 lines)

Added `run_penny_hourly_report_safe` to `ALL_CLOSURES`. The existing parametrised test `test_closure_resolves_its_globals_when_called` now exercises the wrapper's global-resolution region. A future refactor that moves the wrapper between modules and breaks a free name will fail this test loudly.

### `python-engine/tests/test_scheduler_h1_coroutine_guards.py` (NEW, 7 tests)

- `TestClosureRegistration.test_penny_hourly_safe_is_registered` — the wrapper appears in the jobs roster.
- `TestClosureRegistration.test_penny_hourly_safe_replaces_bare_registration` — the bare `run_penny_hourly_report` is **not** in the roster (regression against re-introducing the raw registration).
- `TestCoroutineLeakGuards.test_penny_hourly_safe_does_not_leak_on_substrate_failure` — substrate failure (RuntimeError) is caught; no unawaited coroutine surfaces.
- `TestCoroutineLeakGuards.test_penny_hourly_safe_catches_standard_exceptions` — ValueError, RuntimeError, KeyError, TypeError all caught.
- `TestCoroutineLeakGuards.test_penny_hourly_safe_logs_breadcrumb_on_success` — `penny_hourly_report_invoked` breadcrumb fires.
- `TestCoroutineLeakGuards.test_penny_hourly_safe_survives_create_task_await_cycle` — `create_task` + `await` (scheduler pattern) does not leak.
- `TestCoroutineLeakGuards.test_penny_hourly_safe_handles_f3_import_failure` — F3's `from mark_to_market import ...` failing is also caught.

### `python-engine/tests/main_surface_golden.json` + `add_job_census_golden.json` (regenerated)

Both goldens show exactly one line changed: `func: run_penny_hourly_report` → `func: run_penny_hourly_report_safe`. Nothing else drifted; verified by `git diff`.

## Senior-dev self-corrections in this slice

1. **First wrapper had the calendar gate OUTSIDE the try/except.** That meant `is_trading_day` raising would propagate past the wrapper. Caught by `test_penny_hourly_safe_does_not_leak_on_substrate_failure` (after I added the gate to satisfy the calendar-gating test). Moved the gate INSIDE the try block — the wrapper now protects breadcrumb + gate + run as a single protected region.
2. **First breadcrumb test used `caplog`, which doesn't capture structlog.** Switched to a structlog-recording proxy that re-registers jobs with a patched `main.logger`. Clean and direct.
3. **Cleaned up a rambling comment block in the breadcrumb test** once the right answer was found — the test now has a 2-line explanation instead of 60 lines of discovery narrative.

## Why this should not need the other agent's edits

- **Strictly additive.** No existing module is removed or renamed. The wrapper is a new closure; the cron re-registration is a single line.
- **Both goldens updated deliberately.** Each diff is exactly one line. The `TS_UPDATE_GOLDEN=1` audit trail is in the commit body.
- **41 existing scheduler tests still pass.** The closure-resolution test was extended, not replaced.
- **No F/G/D/I territory touched.** H1 stays inside `scheduler_setup.py` + its two test files + two golden files + the two doc files.

## What was explicitly NOT done in this slice

- **No H2 (timing priority tiers)** — deferred to the next H slice.
- **No H3 (intraday-cache diagnostic)** — deferred; will ship as Phase 3.
- **No H4 (cache-add)** — explicitly deferred per §12 (*"Cache only with explicit instrument, interval, completed-bar cutoff and freshness semantics"*); requires operator sign-off after H3's diagnostic conclusion.
- **No H5 (dashboard readiness)** — deferred; uses the substrate census from F-series, will be Phase 5.
- **No modification of `main.run_penny_hourly_report` body** — the wrapper catches failures from the existing body without changing it.

## Disclaimers preserved

- The five DISC-A1..A5 reconciliation warnings remain `UNKNOWN / UNVERIFIED` (out of H scope).
- `EQUITY_INTRADAY_EFFECTIVE_DATE` remains `None` (out of H scope).
- `kite_client.py` was not modified (H1 doesn't touch the kite layer).

## Verification

| | Before H1 | After H1 |
|---|---|---|
| **Python suite** | 2,922 pass | **2,930 pass** (+8) |
| **Time** | 129.85s | 129.02s |
| **Skipped** | 4 | 4 |
| **Warnings** | 39 | 39 (no new) |

Stable across 2 full-suite reruns.

## Production smoke test result

Manually ran the wrapper against a synthetic substrate failure:

```
[info] penny_hourly_report_invoked now_ist=2026-09-13 16:05:05 source=cron_or_catchup
[error] penny_hourly_report_failed err=PROD simulated substrate failure
Traceback (most recent call last):
  File "scheduler_setup.py", line 785, in run_penny_hourly_report_safe
    if not await _main.is_trading_day(today, settings.DB_PATH):
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<string>", line 10, in boom
RuntimeError: PROD simulated substrate failure
OK: wrapper caught substrate failure and did not raise
```

The breadcrumb fires, the failure is logged with full traceback, the wrapper returns cleanly. **The cron would survive to the next hour.**

## Reference paths

- `docs/2026-09-13-workflow-f-state-of-codebase-audit.md` section 12 (new this commit) — full wrapper description, test coverage, senior-dev invariants, verification numbers.
- `docs/NEXT_AGENT_PLAN.md` requirement matrix row H — updated this commit to reflect H1 PROD-ready status with explicit remaining-transition column.
- `python-engine/tests/main_surface_golden.json` + `add_job_census_golden.json` — regenerated this commit via `TS_UPDATE_GOLDEN=1` (one line each, no drift).

## Next H phases (deferred)

- **H2** (Phase 2): Scheduler timing priority-tier breakdown — `scheduler_timing_report` extended with per-tier p50/p95/p99 (exit / advice / scan / research).
- **H3** (Phase 3): Intraday-cache caller/key/window diagnostic — pure read-only enumeration of `intraday_cache` read sites + freshness classification.
- **H4** (Phase 4): Cache-add — DEFERRED until operator sign-off after H3's diagnostic conclusion.
- **H5** (Phase 5): Dashboard readiness reasons — `operational_coverage_report` extended with §12 vocabulary (`disabled`, `unconfigured`, `no_session`, `no_setup`, `no_evidence`, `stale`, `error`).
