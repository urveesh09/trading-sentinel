# F&O exit recovery implementation slice — 23 September 2026

## Problem and scope

An exit intent survives uncertain dispatch and local receipt failure. This
prevents a duplicate SELL, but there is no authenticated way to inspect and
reconcile terminal zero or partial fills. The full-close receipt represents
only an entire position. This slice covers single-leg FNO_LIVE positions and
does not turn a timeout into proof of non-execution.

## Contracts and files

- `fno_positions.py`: retain the durable intent; add append-only recovery
  evidence and atomic partial-fill/zero-fill transitions. Preserve ledger
  uniqueness with monotonic settlement generations.
- `fno_exit_recovery.py`: inspect fresh broker order and position evidence,
  validate account/symbol/side/quantity/status, and deny ambiguous evidence.
- `routes_ops.py`: internal-secret authenticated inspection and explicit
  operator resolution with a named actor and confirmation.
- `fno_orchestrator.py`: use the next position generation for later full close.
- Tests cover terminal zero, partial and full recovery, duplicate/concurrent
  attempts, restart, wrong order/account/symbol and nonterminal or stale data.

## Acceptance and rollout

Focused tests and relevant existing F&O/ledger/API tests must pass. The source
and generated atlas, system guide, plan and checklist must agree. Deploy only
through GitHub after review and backup. New tables/columns are additive; an
unresolved intent still blocks automatic exits until conclusive evidence is
available. Rollback preserves all intent, ledger and evidence rows; do not
delete an intent to force a retry. Live single-leg activation remains a
separate operator decision after real broker rehearsal.

## Remaining work

Implementation is complete in Dev. Same-day live broker evidence supports
terminal zero, partial and full exits; old broker order books remain out of
scope for automatic resolution because Kite retains them for one day. Current
Production source at merge `782bbb7` contains the preceding handover commit,
not this Dev increment. Operator broker rehearsal, release review and GitHub
promotion remain separate.

Verification (Windows `python-engine/winvenv`): focused recovery **22 passed**
after the cross-session risk, legacy migration and read-only inspection regressions were added; focused recovery/risk **37
passed**, one existing Starlette deprecation. Broad pre-golden run had **4,493
passed, four skipped, one expected route-golden failure**, 46 existing
framework deprecations. The deliberately regenerated golden diff adds exactly
the GET and POST recovery routes; subsequent route/F&O acceptance passed
**74 tests**. The latest broker-client/recovery/risk/surface group passed **65 tests**.
The original full run established no other failures. The atlas
was regenerated at **210 Python modules**. No schema removal, setting default,
broker order, partner message or Production edit occurred.

The additive migration adds original-size/risk fields to `fno_positions` and
creates `fno_exit_recoveries`; take a database backup before rollout. Rollback
should preserve these rows and the existing intents/ledger. If a recovery
cannot corroborate an older event, keep live single-leg entries disabled and
reconcile with broker statements and an operator-reviewed process.
