# F4 (discrepancy-ID framework) — done and committed

## What landed (commit `ed86b6c`)

**Branch**: `codex/production-correction-hedge-p0`
**Files changed**: 4 (2 new, 2 modified), +1,728 / -1 lines
**Tests**: +42 net passing
**Whole-engine**: 2,836 passed / 4 skipped / 23 warnings in 126.59s
**Status**: F4 of the six-slot F plan delivered in partial form
(producer + framework; no consumer wire-up; no retroactive
DISC-A1..A5 population).

## Code surface

### New module: `python-engine/discrepancies.py` (550 lines)

```
DiscrepancyCategory(str, Enum)
    BROKER_RESIDUAL_NONZERO
    BROKER_STATEMENT_UNAVAILABLE
    ORIGIN_REF_PNL_DIFFERENCE
    ORIGIN_REF_SOURCE_MISMATCH
    ORIGIN_REF_HAS_NO_MATCHING_POSITION
    MULTIPLE_LEDGER_ROWS_SHARE_ORIGIN_REF
    ORIGIN_REF_POSITION_NOT_CLOSED_OR_UNVALUED
    LEDGER_PNL_NONFINITE_OR_MISSING
    INTERNAL_EVIDENCE_INVALID_AMOUNTS

DiscrepancyStatus(str, Enum)
    OPEN -> INVESTIGATING -> RESOLVED_EXPLAINED
    OPEN -> WITHDRAWN
    INVESTIGATING -> WITHDRAWN

init_discrepancies_db(db_path)
record_discrepancy(db_path, *, category, evidence_key, account_id,
                   source, severity, amount_inr=None,
                   evidence_refs=()) -> int     # idempotent
update_discrepancy_status(db_path, *, discrepancy_id, new_status,
                          actor, note=None) -> None    # forward-only
list_discrepancies(db_path, *, account_id=None, source=None,
                   category=None, status=None, since=None,
                   until=None, limit=200) -> list[DiscrepancyRecord]
record_from_broker_statement(db_path, *, broker_report, account_id,
                             actor='system') -> int | None
record_from_evidence_report(db_path, *, evidence_report, account_id,
                            actor='system') -> list[int]
record_current_state(db_path, *, account_id, actor='system',
                     broker_report=None,
                     evidence_report=None) -> dict
```

### New tests: `python-engine/tests/test_discrepancies.py` (42 tests)

- Schema version constant.
- Record validation: severity enum, empty evidence_key, NaN amount,
  malformed evidence refs, deduplication.
- Status transitions: OPEN→INVESTIGATING, OPEN→WITHDRAWN,
  INVESTIGATING→RESOLVED_EXPLAINED, INVESTIGATING→WITHDRAWN.
- Rejection: skip INVESTIGATING (OPEN→RESOLVED_EXPLAINED), reverse
  (RESOLVED→OPEN), unknown discrepancy_id, empty actor.
- Same-state idempotency: no extra log row written.
- Append-only DB triggers: UPDATE/DELETE on `discrepancies` blocked,
  UPDATE/DELETE on `discrepancy_status_log` blocked.
- Read API filters: account, source, category, status, date range,
  limit.
- Bridge: MATCH returns None, UNRESOLVED records residual, UNAVAILABLE
  records no-statement, MATCHED_INTERNAL skipped, unknown reason
  silently skipped, sheet-level invalid-amounts flag recorded,
  multiple unresolved details all recorded.
- End-to-end: `record_current_state` against real
  `performance.record_trade_close` + `broker_reconciliation.import_broker_statement`.

## Senior-dev design choices

1. **Append-only at the SQLite trigger level**, not at the
   application level. Even a buggy future caller cannot UPDATE or
   DELETE the rows.
2. **State transitions live in a separate table** (`discrepancy_status_log`),
   also append-only. The `discrepancies` table itself never changes
   after the first record. This is the same shape as the promotion
   bridge.
3. **Same-state transitions are idempotent no-ops** — they don't
   write a log row. This avoids log pollution from repeated
   `update_discrepancy_status` calls and matches the idempotency
   pattern of `record_discrepancy`.
4. **Bridge is the single mapping point** (`_REASON_TO_CATEGORY`).
   Adding a new reason string upstream becomes a single-line addition
   here; the existing report's behaviour is unchanged.
5. **`seen_evidence_keys` deduplication in the evidence-report bridge**.
   The same ledger row can appear in multiple source sheets; the
   bridge records the first occurrence and skips later duplicates.
6. **No retroactive DISC-A1..A5 population**. The five audit-doc
   entries remain `UNKNOWN / UNVERIFIED`; the framework *records*
   findings with stable IDs as evidence arrives. A future commit can
   back-fill when real evidence is obtained.
7. **`record_current_state` accepts pre-fetched payloads** so the
   test suite can pass canned reports and avoid Windows file-handle
   collisions on real SQLite.
8. **No DELETE on `discrepancies` even from the same caller** — even
   a `record_discrepancy` retry cannot overwrite a row, only the
   status log can be appended.

## Senior-dev self-corrections in this slice

1. **First validation pass had a bug**: my smoke test tried
   `OPEN → RESOLVED_EXPLAINED` *after* a successful transition,
   which is actually valid. Fixed the smoke test, then realised the
   real bug: `RESOLVED_EXPLAINED → RESOLVED_EXPLAINED` (self-transition)
   was being rejected, polluting the log. Added an explicit
   same-state-idempotency short-circuit and a test that asserts
   the log row count stays at 1.
2. **First bridge pass was reading from the wrong section** of the
   evidence report (`source_sheets[i].details` instead of top-level
   `sheets`). Caught by the end-to-end test. Fixed the bridge to
   read from `sheets` (the per-row detail section) and added an
   explicit docstring explaining the two sections.
3. **First end-to-end test used `origin_ref=""`** which the
   evidence report tags as `stable_origin_ref_missing` (not in our
   category map, silently skipped). Fixed to use a non-empty
   `origin_ref` that doesn't match any position, which tags as
   `origin_ref_has_no_matching_position` (a mapped category).

## Why this should not need the other agent's edits

- **Strictly additive.** No existing module is modified. The new
  module is standalone.
- **Pure read + append-only write.** The module never mutates any
  pre-existing table; it only creates two new tables (`discrepancies`,
  `discrepancy_status_log`) with their own triggers.
- **Bridge is single-source-of-truth.** The reason-string →
  category mapping lives in `_REASON_TO_CATEGORY`; adding a new
  reason upstream is a single-line addition that doesn't require
  touching the report logic or the DB layer.
- **Idempotency is enforced at every level** — recording, status
  transitions, and DB triggers. A future caller cannot double-record
  a finding or bypass the state machine.

## What was explicitly NOT done in this slice

- **No retroactive DISC-A1..A5 population.** The five audit-doc
  entries remain `UNKNOWN / UNVERIFIED`. The framework records
  findings with stable IDs as evidence arrives. A future commit
  can call `record_from_evidence_report` with hand-supplied evidence
  to back-fill the audit doc's five tentative references when real
  screenshots / ledger rows are obtained.
- **No consumer-side wire-up.** No orchestrator or CLI calls
  `record_current_state`. F5 (broker statement automation) is the
  natural wiring site.
- **No UI/dashboard changes.** Discrepancies are queryable via
  `list_discrepancies(...)` but no FastAPI route or Telegram
  message surfaces them yet.
- **No mutation of pre-existing tables.** F4 is an observer.

## Disclaimers (preserved per the source-backed discipline)

- **No real discrepancy-ID acceptance.** The framework exists; no
  orchestrator or CLI calls it yet; the five DISC-A1..A5 audit-doc
  entries remain unresolved. The value is structural (the durable
  record layer is ready for F5 wire-up, the append-only discipline
  is enforced at the SQLite trigger level, the forward-only state
  machine is in place) — not end-to-end (the operator still sees
  no discrepancy IDs in any surface today).
- **The five DISC-A1..A5 reconciliation warnings remain
  UNKNOWN / UNVERIFIED.** This slice did not touch them.
- **`EQUITY_INTRADAY_EFFECTIVE_DATE` remains None.** This slice
  did not touch cost provenance.
- **`kite_client.py` was not modified.** I used the existing
  `kite.get_quote` from F3's wire-up but did not touch the
  client itself.

## What's next

F5 (broker statement automation skeleton: CLI + FastAPI route, no
scheduler) is the natural next slice. The F5 CLI is the obvious
wiring site for `record_current_state` — every CLI invocation
records discrepancies as a side effect. Awaiting your call on
whether to continue F5 or pause for review.

## Reference paths

- `docs/2026-09-13-workflow-f-state-of-codebase-audit.md`
  section 9 (new this commit) — full module description and
  bridge documentation.
- `docs/NEXT_AGENT_PLAN.md` requirement matrix row F — updated
  this commit to reflect F1+F2+F3+F4 closure.
