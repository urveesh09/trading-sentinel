# Penny strategy search — November 4, 2026

## Problem and authority

Owner requests multiple strategy families and iterative improvement, including
genome methods, to find a materially better Penny strategy. Scope includes
classic Penny (MIS/CNC), Smart V1/V2 and EDGE; independent books stay separate.
Research, acquisition, tests and reviewable Dev code are authorized. Production
editing, deployment, real orders and spending the Breeze allowance are excluded.

## Contracts and files

New research-only `python-engine/penny_strategy_research.py` and a bounded
`scripts/run_penny_strategy_search.py` runner; tests beside the research module.
Reuse current pure strategy, cash-book, stop/profit-lock and fee functions.
Preserve historical replay files, source bindings, owner changes and evidence.
Record source/config/data hashes, all trials and failures, cash/mark accounting,
native intervals, missing sessions, corporate actions and fee/fill assumptions.
No strategy search on the reserved Jan–Jul 2026 Penny exam or protected F&O data.

## Data and evaluation sequence

1. Selectively export Production cash candles/metadata read-only into a fresh
   Dev snapshot with a consistent SQLite read transaction. No active DB copying.
   Inventory counts/coverage before any strategy scoring. Add existing seen
   Sep–Oct data only into a new snapshot; preserve originals and conflicting rows.
2. Freeze available development/calibration and validation windows from coverage,
   not profitability. Prefer later chronological validation; label previously
   observed forward periods conditional validation, never untouched qualification.
   Additional public daily history can supply an independent historical check.
3. Establish current classic profit-lock and continuous Smart V1/V2 baselines,
   with quoted-price proxies explicitly distinguished from actual depth/fills;
   retain EDGE/CNC fidelity limitations. Reconcile mechanics before searching.
4. Conduct three bounded rounds, no more than two new candidates per strategy
   family per round. Round 1 tests structural entry/exit alternatives; round 2
   addresses measured failure modes; round 3 may combine the supported changes
   or run a deterministic bounded genome on training data only. Record every
   trial, not only winners. Never optimize on validation.
5. Freeze finalists and acceptance before opening their validation outcomes.
   If validation rejects every strategy, retain the result and deliver the best
   development candidate with that failure, without relabelling it an improvement.

## Acceptance and audits

Same starting allocation and costs per paired book; own cash/no leverage;
completed-bar decisions and next executable evidence; conservative stop ties;
missing quotes/sessions stay unresolved, never perfect fills. Report net,
fees, net without best trade, marked drawdown, daily results including zero
days, activity/capital use, exits, sensitivity and exclusions. A promising
validation needs positive net and ex-best net, improvement over its baseline,
drawdown <= max(1.5x baseline, Rs 50 at Rs 2k), no unresolved exposure and
adequate activity. Larger allocations cannot masquerade as strategy gains.
Cash/fees/marks must reconcile; restart/causal-prefix tests cover the new
research contract. Stress wider spreads/slippage and retain failures.

## Rollout/rollback and documentation

Candidates are research-only, disabled and cannot order or notify. Existing
Production strategies remain unchanged. Commit freezes before scoring and
update system guide, active plan and checklist with our own changes only;
regenerate the code atlas when new declarations are added. Verify documentation
consistency immediately after each commit. Rollback is to use unchanged
runtime strategies and ignore the new research artifacts. No migration or
configuration impact is intended.

## Initial state

Dev `b6786e3`, Production `5e30ce0`; earlier inheritance assessment is available
beside this study. Owner's four modified tracked files and untracked evidence
are preserved. No implementation/scoring yet. Data feasibility determines the
final declared scope; unsupported coverage cannot be converted into profit.

## Current progress — November 4

- `ca3b748`: initial source/data/round-1 freeze, six initial mechanics checks.
- `e04b254`: round-2 overnight persistence hypotheses, initial failed daytime
  families retained; 23 focused checks and two causal-night tests.
- `dbfcde6`: audited 108-stock nominal-price cohort and Smart retest round.
- `15d9eff`: bounded 12-genome round, causal cache/unchanged-book parity checks.
- `bc53808`: per-observation Smart carry-rollover correction, identical-parameter
  rescore freeze, economic finalist deduplication and daily validation freeze;
  27 focused checks pass. Post-commit guide/plan/checklist/atlas consistency
  verified by the isolated staging helper at each commit. Owner bytes preserved.

Daily validation is now open: G05 passes the original paired acceptance at
Rs 25,000 and Rs 100,000; it improves native net by about 25% with about 21%
greater drawdown. It fails severe slippage and the Rs 2,000 capital check.
The primary Rs 100,000 net gain is about 14%, below the additional 20%
material-improvement hurdle. No wholesale Penny replacement or qualification.
Detailed fixed stress/size results are in `basis-v2/validation-results.json`.

All eight Smart training arms have been rerun after the rollover correction;
all six candidates remain negative. Final Smart validation and frozen
non-selection overnight attribution/prefix diagnostics remain to run. A
classic CNC reference, final financial audit/report and evidence sealing also
remain. Original exploratory scores/corrections are preserved. No Production,
native runtime binding, schema, actual capital, login or Breeze change.
