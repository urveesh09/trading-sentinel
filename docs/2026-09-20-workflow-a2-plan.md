# Plan — A2: Atomic F&O settlement

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §3-A2

## Problem

`fno_positions.close_position()` runs an UPDATE that commits, but
returns no affected-row signal. The caller (`fno_orchestrator._manage_exits`)
then calls `performance.record_trade_close()` in a separate transaction.
Failure between them can leave a closed position without its ledger
cash movement, or a stale caller can append a ledger row after a
no-op position update.

The audit's reproducer:

> Closing nonexistent position 999 returned normally; two writes using
> the same `fno_position:999` origin created two ledger rows totalling
> -20. This proves the local invariants are missing.

## Fix

A single transactional helper `settle_position_close()` that:

1. Runs the position UPDATE and the ledger INSERT in one
   `aiosqlite` transaction.
2. Requires `cursor.rowcount == 1` for the UPDATE; raises on
   zero (already closed or missing).
3. Persists a `settlement_generation` on the position so retries
   settle the acknowledged fill without resubmitting an order.
4. Adds a unique index on `(origin_ref, generation)` for the
   ledger so duplicates fail at the constraint, not silently.
5. Records the broker fill evidence separately so retry can
   re-settle from the broker's acknowledgement.

## Files affected

  - `python-engine/fno_positions.py` — add `settlement_generation`
    column + unique index; add `settle_position_close()` helper.
  - `python-engine/performance.py` — make `record_trade_close`
    accept and persist a `settlement_generation` argument;
    honour a unique index on `(origin_ref, generation)`.
  - `python-engine/fno_orchestrator.py` — replace the two-step
    close + ledger write with the new helper.
  - `python-engine/tests/test_atomic_settlement.py` — new test file
    with the audit's reproducers + concurrency tests.
  - `docs/2026-09-20-workflow-a2-atomic-settlement-done.md`.

## Acceptance

  - Duplicate close: exactly one ledger row.
  - Concurrent workers (two tasks racing on the same position):
    one succeeds, the other raises.
  - Crash before commit: no state change.
  - Crash after position UPDATE, before ledger INSERT:
    both rollback (transaction).
  - Missing row: helper raises.
  - Ledger fault: position UPDATE rolls back.
  - Partial-fill path: same invariant applies after inspecting
    the partial-close contract.

## Data and configuration migration

  - New column: `fno_positions.settlement_generation INTEGER NOT NULL DEFAULT 0`.
  - New unique index: `bankroll_ledger(origin_ref, settlement_generation)`.
  - Both migrations are idempotent (``ALTER TABLE ADD COLUMN`` /
    ``CREATE UNIQUE INDEX IF NOT EXISTS``) so existing databases
    are not invalidated.
  - Existing closed positions get ``settlement_generation = 0``
    on the first migration; the corresponding ledger row also has
    ``generation = 0`` after migration.

## Rollout and rollback

  - Dev only.
  - Backward-compatible: ``close_position()`` is preserved as a
    deprecated thin shim that calls the new helper with
    ``generation=next_value``.
  - Rollback = revert commit. Existing ledger rows are unaffected
    because the unique index only catches NEW duplicates; legacy
    duplicates (if any) are pre-existing and out of scope.

## Status

  - Plan committed before implementation: this doc.

## Documentation updated

  - `docs/2026-09-20-workflow-a2-atomic-settlement-done.md` (new).
  - `python-engine/fno_positions.py` docstring: rewrite the
    settlement contract.
  - `python-engine/performance.py` docstring: enumerate the
    settlement_generation argument.
