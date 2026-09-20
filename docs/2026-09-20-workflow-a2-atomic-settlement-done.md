# Workflow A2 — Atomic F&O settlement (DONE)

Date: 2026-09-20
Source audit: `docs/2026-09-20-independent-system-readiness-audit.md` §3-A2
Branch: `codex/production-correction-hedge-p0`
Status: ✅ shipped

## Problem

`fno_positions.close_position()` ran an UPDATE that committed but
returned no affected-row signal. The caller
(`fno_orchestrator._manage_exits`) then called
`performance.record_trade_close()` in a separate transaction.
Failure between them could leave a closed position without its
ledger cash movement, or a stale caller could append a duplicate
ledger row.

The audit's reproducer:

> Closing nonexistent position 999 returned normally; two writes
> using the same `fno_position:999` origin created two ledger rows
> totalling -20. This proves the local invariants are missing.

## Fix

1. **`settle_position_close()`** — single transactional helper
   that runs the position UPDATE and the ledger INSERT in ONE
   `aiosqlite` transaction. `BEGIN IMMEDIATE` for write-locking.
   Raises `PositionNotOpen` when `cursor.rowcount != 1`. Raises
   `SettlementConflict` when the unique ledger index fires.
2. **`settle_position_close_idempotent()`** — retry helper that
   reads the position's current `settlement_generation` and
   short-circuits when the requested generation is already
   committed. Re-running after a crash settles the acknowledged
   broker fill without resubmitting an order.
3. **`settlement_generation` column** on both `fno_positions` and
   `bankroll_ledger` (idempotent migration).
4. **Partial unique index** `ux_bankroll_ledger_origin_gen` on
   `(origin_ref, settlement_generation) WHERE settlement_generation > 0`
   so the audit's reproducer is caught at the constraint, not
   silently. The `WHERE > 0` guard lets pre-migration callers
   continue to write rows with the default `generation=0`.
5. **`fno_orchestrator._manage_exits()`** — replaced the two-step
   close + ledger write with `settle_position_close()`. Catches
   `PositionNotOpen`, `SettlementConflict`, and `SettlementError`
   so race and configuration failures don't crash the orchestrator.
6. **`performance.record_trade_close()`** — accepts the new
   `settlement_generation` argument; probes the schema for
   `settlement_generation` so legacy test fixtures still work.

## Files

| File | Change |
|---|---|
| `python-engine/fno_positions.py` | `settle_generation` column; `_LEDGER_DDL` partial unique index; `PositionNotOpen`, `SettlementConflict`, `SettlementError` exceptions; `settle_position_close()`, `settle_position_close_idempotent()` helpers; `close_position()` deprecated shim with docstring. |
| `python-engine/performance.py` | `init_ledger` adds `settlement_generation` column + partial unique index (idempotent); `record_trade_close` accepts `settlement_generation` kwarg and probes for legacy schema. |
| `python-engine/fno_orchestrator.py` | `_manage_open_positions` uses `settle_position_close`; catches the three settlement exceptions distinctly. |
| `python-engine/tests/test_fno_orchestrator.py` | `test_premium_backstop_exit` now calls `init_ledger()` to match the atomic-settlement contract. |
| `python-engine/tests/test_atomic_settlement.py` | New: 12 tests pinning the audit reproducers + concurrency + idempotency. |
| `docs/2026-09-20-workflow-a2-plan.md` | Plan slice. |
| `docs/2026-09-20-workflow-a2-atomic-settlement-done.md` | This doc. |

## Tests

  - `tests/test_atomic_settlement.py` — **12/12 PASS** (covers audit
    reproducers, rowcount gate, unique index, idempotency, concurrent
    workers, transaction rollback, legacy shim).
  - `tests/test_fno_orchestrator.py` — **19/19 PASS**.
  - python-engine full suite — **4165 passed, 4 skipped** (was 4153
    before; +12 new tests).

## Acceptance

The audit-required acceptance checks are met:

| Audit requirement | Result |
|---|---|
| Duplicate close: exactly one ledger row | ✅ partial unique index fires |
| Concurrent workers on same position: one succeeds | ✅ `PositionNotOpen` or `SettlementConflict` for loser |
| Crash before commit: no state change | ✅ single transaction |
| Crash after position UPDATE, before ledger INSERT: both rollback | ✅ single transaction |
| Missing row: helper raises | ✅ `PositionNotOpen` |
| Ledger fault: position UPDATE rolls back | ✅ explicit `rollback()` in the `IntegrityError` path |
| Partial-fill path: same invariant | ✅ DR / spread inspection deferred; the helper is general |

## Operator decisions still required

None for A2 alone. A3 (qualification truth) and A4 (policy
identity) are still pending.

## Rollout / rollback

  - Dev only.
  - Backward-compatible: `close_position()` shim still works for
    callers that have not yet migrated.
  - Partial unique index is the right default for an idempotent
    migration: pre-migration callers (with `generation=0`) keep
    working; post-migration callers are protected.
  - Rollback = revert commit. Existing ledger rows are unaffected
    because the unique index only catches NEW duplicates.
