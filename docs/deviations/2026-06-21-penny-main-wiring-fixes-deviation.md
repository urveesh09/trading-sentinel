# Deviation 2026-06-21: Task 13 — Three real bugs fixed

**Plan reference:** docs/superpowers/plans/2026-06-21-penny-stock-expansion.md
lines 5110-5539 (Task 13: main.py scheduler wiring).

**Where:** python-engine/main.py, python-engine/tests/test_penny_main_integration.py.

## Three distinct bugs

### Bug 1: Plan test expected jobs to be visible at import time

Plan body code (lines 5265-5392) inlined 7 `scheduler.add_job(...)` calls
inside the FastAPI `lifespan()` async context manager. The test
(plan line 5165) inspected `main.scheduler.get_jobs()` after just
`import main`. This always returned an empty list because the
lifespan hadn't been entered.

**Fix:** Extracted the 7 job registrations to a module-level function
`register_penny_scheduler_jobs(scheduler)`. The lifespan calls it
inside its body; the test calls it directly with a fresh scheduler
(`_fresh_scheduler_with_penny_jobs()` helper).

### Bug 2: test_penny_universe_refresh_is_scheduled used "penny in j and refresh in j"

Original plan test:
```python
assert any("penny" in j and "refresh" in j for j in jobs), \
    f"no penny_universe_refresh job in scheduler: {jobs}"
```

This substring match would also accept `penny_regime_refresh` (which
also contains both "penny" and "refresh"). The test is meant to
verify the EXACT id `penny_universe_refresh`.

**Fix:** Use exact-string match `assert "penny_universe_refresh" in job_ids`.

### Bug 3: Pre-existing test_universe_expansion flakiness (NOT caused by penny)

`tests/test_universe_expansion.py::test_load_universe_with_fallback_uses_csv_when_present`
fails intermittently when the full suite runs in pytest's default
order. The test uses `monkeypatch.setattr(settings, "UNIVERSE_PATH", str(csv_path))`
to set a per-test UNIVERSE_PATH. The test PASSES when:
- Run in isolation
- Run as the first file
- Run after any specific file we tested

The test FAILS only in the default pytest run order, which suggests
another test (likely one that mutates `settings.UNIVERSE_PATH` or
imports `main.py` and triggers module-level side effects) is
interfering.

Verified this is **pre-existing** by stashing the penny main.py
changes and running the full suite -- the same test still fails
(plus the expected 4 main-integration failures since the penny
scheduler jobs aren't registered). The flakiness is not caused by
this branch.

**Mitigation:** Not in scope of this branch. The test is documented
as a known pre-existing flakiness. Recommend a follow-up to investigate
test isolation in the Nifty universe expansion tests.

## Decision

- Bug 1: extracted to a module-level function (cleaner separation,
  testable without booting FastAPI lifespan)
- Bug 2: tightened assertion to exact match
- Bug 3: documented, not fixed (pre-existing, not caused by this branch)

## Tests

8/8 tests in test_penny_main_integration.py pass after the fixes.
The 1 pre-existing flaky test in test_universe_expansion.py fails
identically with or without my main.py changes.
