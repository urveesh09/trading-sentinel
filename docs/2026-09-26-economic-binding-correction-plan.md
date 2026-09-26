# Phase 3 economic binding correction

Problem: a correct key/ticker with 999 replay shares against 10 actual shares
was marked COMPLETE. Mutable remaining shares cannot prove original quantity.

Dev scope: atomically retain a bounded original-entry economics JSON snapshot
with each new opened paper admission; expose it read-only through the lifecycle
audit; compare every replay entry term before counting a paired delta. Legacy
snapshots stay unavailable, never backfilled from mutable positions.

Acceptance: mismatched quantity, time, entry, stop, target and optional exit
inputs are rejected; equivalent timezone instants match; missing/corrupt
snapshots are unavailable; original quantity survives scale-out; transaction
rollback cannot retain an opened snapshot. No live order/strategy changes.

Migration: additive nullable admission column, lazy/idempotent initialization.
Rollout: GitHub review/promotion, then fresh admissions and preserved LTP paths.
Rollback: revert code through GitHub without removing snapshots or cash rows.
Next: review a predeclared fresh sample; source-ref hashes alone do not prove
archive authenticity. Independently validate retained packet bytes/provenance
before any held-out interpretation. Partner qualification remains separate.

Verification (Dev, September 26): 70 focused tests passed; 42 pure
research/audit tests passed with `-W error`; 122 affected tests passed with one
existing Starlette lifespan deprecation warning. The first combined warnings-
fatal run exposed an unclosed test-runtime socket warning; no blanket warning
suppression or application fix was made for that unrelated hygiene issue.
Regression cases cover altered original quantity, entry time/price, stop,
target, ATR/VWAP/regime, corrupted snapshots, timezone equivalence, mutable
remaining shares, repeat admission and transactional rollback. Tests establish
binding correctness, not profitable exits or partner readiness.

Source receipt: `94adfc0`, pushed to `codex/production-correction-hedge-p0`.
Post-commit guide/plan/checklist/atlas consistency verified. Production was
neither edited nor restarted; migration is not deployed by this work.
Unrelated dirty fixtures and prior audit artifacts were left untouched.
