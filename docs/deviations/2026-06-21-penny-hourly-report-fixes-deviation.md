# Deviation 2026-06-21: Task 12 — 4 plan/implementation issues fixed

**Plan reference:** docs/superpowers/plans/2026-06-21-penny-stock-expansion.md
lines 4691-5110 (Task 12: hourly report).

**Where:** python-engine/penny_hourly_report.py and
python-engine/tests/test_penny_hourly_report.py.

## Issue 1: `requests` package not in venv

The plan code uses `import requests` and `requests.post(...)` for the
webhook delivery. The codebase's requirements.txt does not include
`requests`. Running the plan code verbatim produced `ModuleNotFoundError`.

**Fix:** Use stdlib `urllib.request` for the POST. Stdlib is the
minimum-dependency choice for a non-critical heartbeat. `httpx` is
available in the venv as a backup, but stdlib is the right default.

## Issue 2: `is_in_report_window` returns True at 14:01 (off-by-one)

Plan code: `return settings.PENNY_HOURLY_REPORT_START_HOUR <= now.hour
<= settings.PENNY_HOURLY_REPORT_END_HOUR`. With START=10, END=14, this
returns True for hour=10, 11, 12, 13, 14 — including 14:01+ (any time
within the 14th hour). The test asserts `is_in_report_window(14:01) is
False` — the plan test contradicts the plan body code.

**Fix:** Also require `now.minute == 0`. The report only fires at the
top of each hour (10:00, 11:00, ..., 14:00), not continuously through
the 14th hour.

```python
def is_in_report_window(now: datetime) -> bool:
    if now.minute != 0:
        return False
    return (settings.PENNY_HOURLY_REPORT_START_HOUR
            <= now.hour
            <= settings.PENNY_HOURLY_REPORT_END_HOUR)
```

## Issue 3: SQL upper bound excludes the boundary row

Plan code:
```sql
WHERE scanned_at >= ? AND scanned_at < ?
```
with `(hour_start.isoformat(), now.isoformat())`. A row inserted at
exactly `now` (e.g. by `log_penny_signal` called with a fixed `now`
mocked in the test) is excluded by the strict `<` upper bound.

**Fix:** Use `<= ?` for the upper bound. This includes the boundary
moment itself in the trailing-60-minutes window.

## Issue 4: Test setup missing `init_penny_signal_db` + datetime mismatch

Plan test `test_report_lists_filled_entries` calls
`log_penny_signal(db_path, ...)` without first calling
`init_penny_signal_db(db_path)`. The `penny_signals` table doesn't
exist yet, so the insert fails with `no such table: penny_signals`.

The test also passes a fixed `now=datetime(2026, 6, 21, 11, 30)` to
`build_report()`, but the row's `scanned_at` is the real
`datetime.now()` time (today's wall clock) — way outside the
2026-06-21 10:30-11:30 query window.

**Fix:**
1. Call `init_penny_signal_db(db_path)` first.
2. Mock `penny_signal_log.datetime` (with `wraps=real_dt` so the
   constructor still works) to return a fixed time matching the
   `now` passed to `build_report()`.

## Tests updated

Tests: 8/8 pass after the fixes. The 3 plan-test-bug fixes are
documented in the test file with inline comments.

## Action

- python-engine/penny_hourly_report.py: urllib.request for webhook,
  minute==0 in is_in_report_window, <= upper bound, UTC ISO normalization
- python-engine/tests/test_penny_hourly_report.py: init + datetime mock

Implementation body is plan-derived; only the bugs above were corrected.
