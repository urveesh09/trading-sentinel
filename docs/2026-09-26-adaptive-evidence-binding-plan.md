# Adaptive trader phase 3 — source-bound paper evidence review

## Problem and scope

Phase 1 can replay a source-bound LTP path, while Phase 2 can reconcile an
admission, paper position and ledger cash lifecycle.  Neither artifact alone
proves that a particular exit-path replay belongs to that exact paper
admission.  Joining them by ticker, timestamp or a source-hash prefix would be
unsafe, especially for reopened symbols.

This Dev-only slice adds an explicit optional `admission_key` to future
momentum exit-study input entries and a read-only review that combines the
existing SQLite lifecycle audit with one immutable exit-study packet.  The
review accepts only exact opaque-key joins.  Legacy packets without a key and
missing/duplicate/mismatched records remain unavailable or unresolved.

## Files and contracts

- `momentum_exit_study.py`: preserve v1 packet compatibility; when supplied,
  validate an opaque bounded `admission_key` and retain it in every pair.
- `momentum_paper_evidence_review.py`: read only the named existing database
  and input packet, rebuild the current paired report, and join it only to the
  Phase 2 audit's exact admission key. It neither writes a report nor changes
  database state.
- Tests prove exact matching, ticker collision rejection, missing/duplicate
  keys, legacy packet unavailability, and absence of broker/network/order/
  Telegram authority.

## Acceptance, rollout and limits

The review must use a read-only database path and never create or migrate one.
It must preserve partial/terminal-cash separation supplied by the lifecycle
audit; a `CLOSED` path is not a reconciled paper result unless the linked cash
state is `MATCH`. It emits net paired delta only for complete, exact, matched
closed records and permanently reports qualification as `NOT_ASSESSED`.

No runtime caller, strategy threshold, exit policy, allocation, scheduler,
broker, EXEC, Telegram, partner delivery or Production file changes are in
scope. Promotion and fresh keyed/labeled records remain necessary before this
can assess any real sample. Roll back with a GitHub revert; never delete the
input packet, lifecycle data or generated evidence.

## Implementation receipt — Dev only

Implemented `momentum_paper_evidence_review.py` with a read-only CLI:

```powershell
.\python-engine\winvenv\Scripts\python.exe python-engine\momentum_paper_evidence_review.py `
  --db C:\path\to\existing\trading.db `
  --input C:\evidence\momentum-exit-study-input.json
```

The original `momentum_exit_study_input_v1` format remains accepted. A future
entry can additionally name its exact opaque `admission_key`; the Phase 3
review requires that field. It rebuilds the exit report from the immutable
input and joins only to the Phase 2 audit record with the exact same key.
Missing key, duplicate key, missing admission, ticker mismatch, non-opened
admission, unresolved lifecycle/cash, and incomplete path remain explicitly
unavailable or unresolved. It never compares simulated exit P&L to actual
cash as though the alternative had been traded.

Validation in Dev: 20 focused Phase 1/3 tests passed with warnings fatal; the
affected paper/exit/shadow/replay/position/accounting suite passed 214 tests
with one pre-existing Starlette lifespan deprecation warning. Python
compilation and `git diff --check` passed; the atlas was regenerated to 215
Python modules. This source has no runtime caller and has not changed
Production, strategy behavior, paper sizing, exits, allocation, scheduler,
broker, EXEC, Telegram, partner delivery or configuration. Commit/push identity
is recorded after the source commit.
