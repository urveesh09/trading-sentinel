# Adaptive trader phase 2 — momentum paper decision baseline

## Problem and scope

The first paired exit study evaluates source-bound quote packets, but the live
paper book still lacks a durable primary-key lineage from an accepted paper
admission through its position and partial/final cash events. Ticker/date
matching would be unsafe: a ticker can reopen, a partial and terminal cash row
are different accounting events, and historical records are not proof of a
one-to-one relationship.

This Phase 2 Dev slice completes only the momentum-paper part of roadmap A.
It adds an opaque admission identity to future `MOMENTUM_PAPER` positions and
uses that same identity as the existing ledger `origin_ref` for that position's
partial and terminal cash records. A new read-only audit builder reports each
admission attempt, known lifecycle state, cash reconciliation, net R/cash,
open risk, and explicit unavailable/legacy links. It does not infer a
relationship for old rows.

## Contracts and files

- `position_tracker.py`: add nullable `paper_admission_key` to `positions`,
  with a partial unique index. It is additive; existing rows remain NULL.
- `momentum_paper.py`: store the immutable existing admission key when opening
  a position after the normal admission decision, and pass it to partial/final
  paper ledger writes. A legacy/minimal schema that lacks the additive column
  remains operable but is deliberately unlinked in audit output.
- `performance.py`: allow `record_partial_realisation` to store an optional
  `origin_ref` when the ledger supports it. Existing callers and legacy schemas
  retain their current behavior.
- Add `momentum_paper_audit.py` plus tests. It opens *only an existing SQLite
  database in read-only mode, never initializes/migrates it, and emits a
  deterministic `momentum_paper_decision_audit_v1` object/CLI result.

The audit must group accounting by exact admission key, not ticker/date or a
prefix. It must retain `opened`, `already_held`, `zero_shares`, `disabled`,
`upstream_deduplicated`, and `transaction_failure` outcomes, separate partial
cash from terminal cash, use the ledger as cash truth, and report position P&L
only as an independent check. It must label missing link columns, unlinked
position/cash events, duplicate keys, missing terminal cash, and legacy rows
as unavailable or unresolved—not zero, matched, or profitable.

## Acceptance

1. Future opened paper positions retain their exact immutable admission key; a
   scale-out and final close retain that exact key in ledger origin metadata.
2. A repeated/closed/reopened signal has distinct immutable admission keys and
   cannot merge its cash with the prior life.
3. A read-only report reconciles a complete partial-plus-final lifecycle,
   preserves open risk and does not double-count partial cash as a closed trade.
4. Missing DB/schema/identity/cash rows are explicit and the report never
   creates the requested database.
5. Tests prove no order/network/Telegram capability, normal paper behavior is
   unchanged, and legacy test schemas still work.

## Rollout, rollback and remaining work

This adds a normal additive schema migration when the existing application
startup calls `init_positions_db`; it has no configuration or backfill. Before
using the report operationally, promote through reviewed GitHub flow and allow
newly opened paper positions to produce keyed evidence. Historical rows remain
visible but cannot be retroactively linked. Roll back through GitHub if needed;
do not delete new evidence or modify Production directly.

After this slice, use retained source-bound quote packets to run phase 1's
paired exit study on a predeclared sample, then research independent strategy
hypotheses and held-out data. The audit is diagnostic and cannot establish a
profit edge, qualify partner advice, or grant any new live authority.

## Implementation receipt — Dev only

Implemented `momentum_paper_audit.py` with:

```powershell
.\python-engine\winvenv\Scripts\python.exe python-engine\momentum_paper_audit.py `
  --db C:\path\to\existing\trading.db --limit 1000
```

The CLI only prints canonical JSON and opens the named database in SQLite
read-only mode; a missing database returns `UNAVAILABLE` without creating a
file.  It never joins by ticker/date.  Future `MOMENTUM_PAPER` positions retain
the existing opaque admission key in additive `positions.paper_admission_key`,
and the corresponding partial/terminal ledger events retain the same key as
`origin_ref`.  The report uses the ledger as cash truth, checks position P&L
independently, and labels legacy link columns, unlinked cash, missing terminal
cash and duplicate position keys explicitly.

Validation in Dev: 9 new audit/lifecycle tests passed with warnings fatal; the
affected momentum paper/exit/shadow/replay/position/accounting surface passed
194 tests with one pre-existing Starlette lifespan deprecation warning. Python
compilation and `git diff --check` passed. The atlas was regenerated to 214
Python modules. This is an additive Dev schema migration with no configuration
or backfill; no Production service/data, broker action, Telegram message,
runtime strategy rule, paper sizing, EXEC gate or partner delivery behavior was
changed. Source commit `94871f2` is pushed to
`codex/production-correction-hedge-p0`; it is not deployed.
