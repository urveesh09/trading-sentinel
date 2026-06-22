# Deviation 2026-06-21: Task 9 — log_penny_signal test signature

**Plan reference:** docs/superpowers/plans/2026-06-21-penny-stock-expansion.md
line 3367-3373 (test_log_handles_db_failure_gracefully).

**Where:** python-engine/tests/test_penny_signal_log.py::test_log_handles_db_failure_gracefully

**What changed:** Added two missing required keyword arguments to the
log_penny_signal() call: `regime="PR1_CALM"` and `close=10.0`.

## Why

The plan's test code (lines 3367-3373):
```python
asyncio.run(log_penny_signal(
    bad_db, scan_id="x", ticker="X",
    leg="CNC", accepted=False, reject_reason="test"
))
```

The plan's own implementation signature (lines 3494-3510):
```python
async def log_penny_signal(
    db_path, scan_id, ticker, leg, accepted, regime, close,
    reject_reason=None, ...
)
```

`regime` and `close` are required positional parameters (no defaults). The
test omits both, raising `TypeError: log_penny_signal() missing 2 required
positional arguments: 'regime' and 'close'`. The test cannot execute as
written.

## Decision

The test's clear intent is "exercise the best-effort DB-failure path with
the minimum required args". Adding `regime="PR1_CALM"` and `close=10.0` as
arbitrary valid values preserves the test's intent. The implementation is
unchanged.

## Action

- python-engine/tests/test_penny_signal_log.py: added regime + close kwargs
  to the bad-DB test call. All 7 signal-log tests pass.
- python-engine/penny_signal_log.py: unchanged (plan body verbatim, lines
  3449-3557).
