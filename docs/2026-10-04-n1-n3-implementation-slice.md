# N1–N3 implementation slice — non-F&O research only

## Problem and boundary

The current non-F&O evidence mixes exact evaluator calls with simplified fills
and exits.  In particular, the Momentum replay exits the full quantity at T1,
and the EDGE evaluator has no executable next-session fill or lifecycle.
Those shortcuts can make an entry/exit idea look better than the deployed
contracts.  This slice makes the measurement more conservative before adding
candidate filters.

This is **Dev-only, broker-free research**.  It will not modify F&O code,
capital reservations, gateway execution, scheduler jobs, runtime strategy
defaults, database schemas, or live/paper entry admission.  Existing baseline
adapters and results remain available.

## Files and contracts

- Add pure, deterministic lifecycle/candidate helpers under
  `python-engine/non_fno_research.py`.  They consume only supplied completed
  bars and existing shipped decision/exit functions.
- Extend the Momentum replay with a named `LIVE_EXIT_LIFECYCLE` research exit
  model.  It must call `momentum_exits.evaluate_momentum_exit`, preserve
  partial quantities, broker-stop priority, costed fills, ratchets and
  unresolved positions.  The archived `TARGET_1_PROXY` stays the default.
- Add a research-only EDGE next-session lifecycle adapter and candidate
  adapters for Penny context/exit, Range net-room/thesis, Swing pullback/
  correlation exposure, and Momentum timing/exit parity.  Candidates must be
  separately named, retain baseline decisions and fail closed on unavailable
  context.

## Acceptance checks

1. No candidate may read a future bar to decide an entry.  EDGE fills only at
   the next executable session open; a gap through stop/target is a no-fill or
   conservative outcome, never a discovery-close fill.
2. Test stop/target same-bar ambiguity, gaps, zero/one-share partial handling,
   costed partial exits, rejected/missing evidence and open/unresolved marks.
3. Tests demonstrate calls into the shipped Momentum exit evaluator and EDGE
   scanner/ranker.  Baseline `TARGET_1_PROXY` behavior remains unchanged.
4. Candidate output is diagnostic/research-only and records a reason; it never
   creates an order, writes operational tables or changes a live threshold.
5. Focused unit/Lab regressions, compilation, `git diff --check`, and a
   regenerated code atlas pass.  A candidate result is not profitability or
   rollout evidence.

## Rollout, rollback and remaining work

Rollout is offline via the Backtest Lab or direct deterministic tests.  Roll
back by not selecting a new adapter; baseline adapters and live policies are
unchanged.  No position, protective stop, reservation or F&O exit can be
orphaned.

Remaining after this slice: point-in-time universe/event/manual-approval and
broker-fill archives, realistic quote/depth coverage, shared full-stock
portfolio reconstruction, N4 trial/holdout qualification and a separately
authorized F&O-resource compatibility/paper observation proposal.

## Completion receipt

Implemented October 4 in Dev only. `MomentumReplayConfig.exit_model` now names
either unchanged `TARGET_1_PROXY` or `LIVE_EXIT_LIFECYCLE`; the latter calls
the shipped exit evaluator and keeps partial/runner order accounting. The
Backtest Lab registers `penny_edge_next_open_lifecycle`, which calls the
shipped scan/ranker, uses a frozen ten-calendar-day post-window tail for a
next-open fill and routes exits through the shipped EDGE simulator.

`PEN_CONTEXT` is a default-off option on the Penny MIS lifecycle adapter. It
uses only completed bars and five earlier same-minute cumulative-volume
observations; unavailable profiles reject the candidate. `penny_exit_thesis`,
`range_candidate_gate` and `swing_candidate_gate` are explicit, pure research
helpers. No live scanner, exit, F&O file, gateway, scheduler, DB schema,
strategy setting or reservation was changed.

Focused verification before final documentation/atlas checks:

```
python-engine\winvenv\Scripts\python.exe -m pytest python-engine\tests\test_momentum_replay.py python-engine\tests\test_non_fno_research.py python-engine\tests\test_penny_lifecycle_replay.py python-engine\tests\test_backtest_lab.py python-engine\tests\test_backtest_cli.py python-engine\tests\test_penny_edge_engine.py python-engine\tests\test_range_reversion.py -q
```

Result: `109 passed`; one existing HTTPX deprecation warning. Affected modules
also passed `py_compile`. The completion commit, regenerated atlas and final
diff/clean-worktree results are recorded in the mandatory handover documents.
Source implementation commit: `65e050a`; atlas result: 241 Python modules.
