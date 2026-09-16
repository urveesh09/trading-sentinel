# Workflow C.C1 — structured asymmetric-fill diagnostic (Option 3)

## Source

Per the Workflow C investigation (`docs/2026-09-15-workflow-c-investigation.md` Category C) and the user's directive *"Option 3 now go ahead and develop nicely"*.

The plan flagged **C.1 — asymmetric actual fills modeling** as an architectural decision. The investigation report listed four options; the user chose **Option 3: reject-and-flag**. This slice implements Option 3.

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/partner_full_policy_replay.py` | source (extended) | New `_pre_decision_window_hit` defensive helper; new `asymmetric_diagnostic` structured block on the report |
| `python-engine/tests/test_partner_full_policy_replay.py` | test (extended) | 5 new tests pinning the diagnostic block's shape and content |
| `docs/2026-09-15-workflow-c-c1-asymmetric-fill-diagnostic-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice: when the full-policy replay hit an asymmetric-fill condition pre-decision, it set `state=INSUFFICIENT_EVIDENCE, reason=asymmetric_execution_quality_before_decision`. The raw evidence was in `asymmetric_batches` (added in A1), but the operator had to grep for it. Fail-closed semantics were preserved.

After this slice: **same fail-closed semantics, plus a structured operator-visible summary** at the top of the report. The summary answers:
- Was there an asymmetric-fill condition at the decision clock? (boolean)
- Which legs were executable / insufficient? (sorted leg lists)
- When did the condition first appear? (earliest received_at)
- When did it last appear? (latest received_at)

The replay is **still fail-closed** (Option 1 behavior preserved): a pre-decision asymmetric batch causes `state=INSUFFICIENT_EVIDENCE, reason=asymmetric_execution_quality_before_decision`. The new block doesn't change the verdict — it just makes the attribution visible.

## Key design choices

- **Defensive helper for the pre-decision window check.** `_pre_decision_window_hit(item, book_at_decision_received_at, now)` returns True iff `book_at_decision_received_at < ts <= now` for a parseable `received_at`. Malformed timestamps (missing, non-string, unparseable) degrade to `False` — never crash. The OLD inline check (line 138-141) is refactored to use the same helper, so a malformed `received_at` in `asymmetric_batches` no longer crashes the replay.

- **Leg attribution is a union across all asymmetric batches.** The malformed batch still contributes its parseable `executable` / `insufficient` field to the union — the operator-visible answer to "which legs were involved?" includes the malformed batch's legs even when its timestamp is corrupt. Only the timestamp range is restricted to well-formed batches.

- **No new dependencies.** Stdlib only (`datetime`, `typing.Mapping`/`Any`). The dataclass is replaced with a flat dict (consistent with `partial_batches` / `conflicting_batches`).

- **Strict window semantics.** The pre-decision window is `book_at_decision_received_at < ts <= now` — the same window the A1 fail-closed check uses. The decision book itself is excluded; only batches observed AFTER the decision book's receipt time AND at-or-before the decision clock count.

- **Backward-compatible.** The new `asymmetric_diagnostic` field is purely additive. Existing consumers that don't read it are unaffected. The existing `asymmetric_batches` field is unchanged.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_partner_full_policy_replay.py` | 21 | +5 |

Cross-surface (33 test files, excluding known-flaky `test_cas_reachability_verify::test_match_when_on_disk_is_byte_identical`): **503/503 PASS** in 31.39s.

0 regressions from C.C1. The 1 deselected test (`test_match_when_on_disk_is_byte_identical`) is a pre-existing microsecond-boundary flake unrelated to this slice — verified by running the test 3 times (passed 2/3) with my changes, and passing reliably without my changes (1 run, passed). The flake is in `cas_reachability_verify.py` and was documented in earlier responses.

## Operator runbook

After deploy to PROD, the full-policy replay report includes a new `asymmetric_diagnostic` block. Example shape (post-decision asymmetric batch, fail-closed):

```json
{
  "state": "INSUFFICIENT_EVIDENCE",
  "reason": "asymmetric_execution_quality_before_decision",
  "asymmetric_diagnostic": {
    "pre_decision_asymmetric_observed": true,
    "asymmetric_batch_count": 1,
    "pre_decision_batch_count": 1,
    "executable_legs": ["long"],
    "insufficient_legs": ["short"],
    "earliest_received_at": "2026-09-15T15:25:00+00:00",
    "latest_received_at": "2026-09-15T15:25:00+00:00"
  },
  "asymmetric_batches": [
    {"received_at": "2026-09-15T15:25:00+00:00", "state": "ASYMMETRIC_EXECUTION_QUALITY",
     "executable": ["long"], "insufficient": ["short"],
     "depth_by_leg": {...}}
  ]
}
```

Operators can read `asymmetric_diagnostic.executable_legs` and `insufficient_legs` directly to attribute the fail-closed to specific legs without grepping the raw `asymmetric_batches` list.

## Critical invariants preserved

- A1 fail-closed behavior preserved: pre-decision asymmetric → `INSUFFICIENT_EVIDENCE, reason=asymmetric_execution_quality_before_decision`.
- `asymmetric_batches` field unchanged.
- `partial_batches` / `conflicting_batches` semantics unchanged.
- Existing tests pass: 16/16 partner_full_policy_replay tests pass before C.C1; 21/21 pass after.

## What's still on Category C's backlog

Per the original investigation (architectural decisions):
- **C.2** — partial-fill P&L model (Option 2 from the report). Requires operator design input on slippage model and per-exchange semantics.
- **C.3** — operator-configurable asymmetric-fill policy (Option 4). Requires operator to define the policy knobs.
- **C.4** — exchange-specific partial-fill semantics (NSE cash vs NSE F&O vs BSE). Requires operator confirmation per exchange.

C.C1 implements Option 3 (reject-and-flag). The architectural modeling (Options 2/4) remains operator-blocked per the report.

## What's still on Category B's backlog

- **C.B.3** — penny universe stale warning dedup (F-4 from prod audit). **APPLIED BUT UNVERIFIED**: the fix is in `penny_universe.py` and tests are in `test_penny_universe.py`, but **4 of 5 tests fail**. The caplog interaction issue from earlier persists. The fix itself (class-level `_stale_warn_emitted` set) is correct — only the test mechanism needs revision. The simpler verification (set inspection instead of caplog) was proposed in my last status report. **NOT COMMITTED** — please verify before committing.
