# Workflow F.10A — broker/internal order-reference verification

**Status:** TESTED_DEV and pushed. Implementation commit `1dde067` and
verification receipt `d2735e9` are on
`origin/codex/production-correction-hedge-p0`. Production is unchanged.

## Problem

`broker_statement_report` verifies only the broker statement's own cash
arithmetic. `reconciliation_evidence_report` independently checks Sentinel's
ledger/position links. No current path compares executed broker order IDs with
the order references retained by `positions` or `fno_positions`. A cash
`MATCH` can therefore coexist with broker fills that are missing, duplicated,
paper-only, or inconsistent with the internal book.

## Files and contracts

- New `python-engine/broker_internal_reconciliation.py`: read-only report for
  one imported statement. Aggregate unique executed fills by `order_id`, then
  compare them with supported internal references:
  `positions.broker_entry_order_id` and live `fno_positions.entry_order_id` /
  `exit_order_id`.
- `python-engine/discrepancies.py`: additive stable categories and an
  idempotent bridge for unresolved, ambiguous, and insufficient-scope results.
- `python-engine/reconciliation_cli.py`: include the report in
  `import-statement` and `run-report`; recording remains explicit for
  `run-report` and follows the existing append-only behavior for imports.
- Focused tests cover account binding, latest/explicit statement selection,
  multiple fills per order, unique matches, duplicates, paper-only references,
  missing schemas/references, quantity excess, idempotency and CLI wiring.

The configured account ID is an operator declaration. Internal position tables
have no account column, so even a unique reference reports
`account_attribution_verified=false` and `broker_reconciled=false`. This slice
checks broker-executed orders in one direction only; it cannot prove that every
internal order appears in a broker statement.

## Acceptance checks

1. Pre-change F baseline remains green: 98 focused tests.
2. Blank/mismatched configured account, absent required schemas, missing
   statement, or no executed fill evidence returns `INSUFFICIENT_SCOPE` and
   never a match.
3. Every unique broker `FILLED`/`PARTIAL` fill ID is aggregated once by order;
   `CANCELLED`/`REJECTED` evidence is reported separately.
4. A unique supported live reference returns `MATCHED_REFERENCE` only. Missing,
   paper-only, unsupported, duplicate, or quantity-exceeding references return
   `UNRESOLVED`; incomplete table coverage cannot be upgraded by a partial
   match.
5. Durable records are idempotent and preserve the unscoped internal-account
   limitation. Broker cash `MATCH` cannot erase cross-book discrepancies.
6. Existing report/CLI/discrepancy routes remain compatible, focused and whole
   engine tests pass, compilation/atlas/diff checks pass.

## Rollout and rollback

This is an additive offline diagnostic/report shape and additive discrepancy
enum surface. It introduces no database migration or mutable operational
table, makes no broker/network call, and grants no order/capital/delivery
authority. Promote through GitHub. Roll back the implementation commit to
remove the bridge; previously appended discrepancy rows remain immutable and
readable only by code that knows their category values.

## Remaining F work after this slice

Bidirectional economic reconciliation still needs statement period bounds,
broker account binding on internal books, universal retained order IDs, richer
fill metadata and actual broker-supplied evidence. Operator review of durable
discrepancies, signed loss tolerance/capital decisions and release observation
remain separate gates.

## Verification receipt

- Pre-change reconciliation baseline: 98 passed, 17 known framework warnings.
- New paths with warnings fatal: 93 passed, no warnings.
- Final focused reconciliation surface: 118 passed, 21 known Starlette/httpx
  deprecations in 6.95 seconds.
- First whole-engine run: 4,089 passed, four skipped, one unrelated failure,
  46 known deprecations. The failure proved that one MTM test sampled a quote
  clock after its report clock; on a Windows clock tick the correctly
  fail-closed runtime treated the quote as future-dated. The fixture now binds
  both values to the same instant.
- Final exact-tree whole-engine run: 4,090 passed, four skipped, 46 known
  deprecations in 204.15 seconds. JUnit:
  `C:/Users/Urveesh/AppData/Local/Temp/sentinel-f10a-broker-internal-final2-20260919.xml`.
- Atlas regenerated at 203 Python modules. Changed Python compilation and
  `git diff --check` passed. The atlas generator/full suite refreshed two
  generated-at-only session golden files; those unrelated changes were
  removed with no semantic fixture change.

No schema/table migration, data rewrite, config/default change, broker/network
call, order/capital authority or partner delivery occurred. All implementation
is confined to Dev; Production remains untouched. Implementation commit
`1dde067` contains source, tests, atlas and canonical documentation; its
immediate stat/status/guide/plan/atlas consistency review passed with a clean
Dev worktree. Receipt commit `d2735e9` passed its immediate consistency review;
both commits were pushed to `origin/codex/production-correction-hedge-p0`.
This is remote Dev source, not a merge, release or deployment.
