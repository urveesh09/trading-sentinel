# T0 adaptive Penny policy slice — isolated prototype

## Problem and boundary

The existing `PEN_CONTEXT` experiment only filters a baseline accept. It cannot
measure a setup that the baseline rejected, and it has no persistent thesis
identity. This slice builds the minimum deterministic state machine needed to
test `PEN_TRADER_V1` without changing the Penny scanner, executor, settings,
database, broker client, scheduler, account reservation, or any F&O path.

The Dev worktree has unrelated, uncommitted review changes. This slice adds
new files only and does not modify or stage those changes.

## Contracts

- `adaptive_penny_policy.py` is a pure, JSON-round-trippable state machine:
  `WATCH -> ARMED -> ENTRY_INTENT -> OPEN -> EXIT_PENDING -> CLOSED`, with
  `INVALIDATED`, `EXPIRED`, and explicit `COOLDOWN`/new-thesis handling.
- A setup freezes its pre-confirmation anchor; it never recomputes an anchor
  from a confirmation candle. Observations must be complete and available at
  their decision time. Replayed duplicate observations are idempotent.
- The entry prototype supports continuation and bounded retest/reclaim timing,
  including a baseline-rejected setup label. Structural stop and position size
  are computed before any intent becomes executable; the stop can never widen.
- The module has no I/O and no import of broker/runtime components. It returns
  entry *intent*, never an order or fill.

## Acceptance

1. Tests cover frozen anchors, continuation/retest, baseline-rejected recovery,
   expiry, invalidation, duplicate/restart parity, stale evidence and terminal
   no-reentry.
2. Sizing is bounded by both initial risk and own-cash/per-position caps;
   unaffordable/invalid geometry yields no intent.
3. No source outside the isolated prototype/test pair changes. Existing review
   modifications remain unstaged.

## Rollout / remaining work

Offline only. A later dedicated replay adapter must feed this policy frozen
completed bars, use the existing Penny risk/executor contracts for admission,
and compare it at equal cash/risk against baseline. No candidate is enabled in
runtime. EDGE holding/cash replay, complete candidate lifecycle/economics,
native minute coverage, portfolio evidence, F&O compatibility, qualification
and any deployment remain open.

## Completion receipt

The prototype is implemented as `adaptive_penny_policy.py` with no runtime or
I/O imports. It contains the persistent Penny state record, causal completed
bar contract, a watch derived only from visible prior bars, frozen-anchor
continuation/retest candidate logic, explicit execution confirmations and
bounded pre-entry sizing. The setup's
`baseline_status` is recorded but never used as an eligibility prerequisite,
so a mechanically defined baseline-rejected setup can be represented without
weakening any shipped policy.

Focused verification:

```
python-engine\winvenv\Scripts\python.exe -m pytest python-engine\tests\test_adaptive_penny_policy.py python-engine\tests\test_non_fno_research.py python-engine\tests\test_penny_lifecycle_replay.py python-engine\tests\test_penny_engine_breakout.py python-engine\tests\test_penny_risk.py -q
```

Result: `76 passed`. `py_compile` and `git diff --check` passed. The shared
atlas was regenerated against the current Dev tree and now indexes 242 Python
modules; it remains unstaged because it also contains the existing independent
review changes that this slice must not absorb. Commit identity is added after
the isolated source commits. Source commits: `b08c934`, `fab80c6`. Dev only;
no broker action, push or deployment.
