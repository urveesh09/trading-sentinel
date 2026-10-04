# Independent non-F&O review and same-data repeat — October 4

**Latest owner direction:** follow the
[adaptive trader development plan](2026-10-04-adaptive-non-fno-trader-development-plan.md)
for design and implementation order. R1–R5 below remain required fidelity and
qualification contracts; develop runnable stateful replacement candidates
alongside their causal adapters. This review and its results remain historical
evidence, not completed strategy improvement or permission for live promotion.

Review baseline: Dev `434c4cc` / implementation `65e050a`; clean worktree.
Review the source against the October 3 smart-entry/exit plan and October 4
N1–N3 slice. The owner authorizes minor corrections and repeat testing;
larger strategy/integration changes require a new plan, not implementation here.
F&O remains excluded and must not be hindered. Production stays untouched.

## Current slice before edits

Problem: new research-only candidates do not change baseline policies or the
Yahoo all-module runner's selections. Implementation cannot imply higher profit.
The Penny retest's anchor includes the previous high, so previous close cannot
be above that anchor. Investigate prior-volume coverage and Momentum lifecycle
clock/fill issues before accepting any candidate result.

Files/contracts: `non_fno_research.py`, `penny_lifecycle_replay.py`,
`momentum_replay.py`, new Lab/EDGE adapters, their tests; existing Yahoo CLI,
immutable archived Yahoo raw/import/validated data and policy manifests.
Only bounded research corrections are permitted; shipped strategy/risk,
shared cash, scheduler, broker and F&O defaults are not changed.

Acceptance: meaningful regression cases for any correction; focused existing
tests; identical July 1–September 30 requested dates, September 24–30 separate
intraday diagnostic, fixed archived universe/configuration and Yahoo snapshots.
Freeze all optional studies before scoring; retain failures/unavailability.
Baseline and candidate results remain distinct. Validate no F&O/runtime diff,
immutable data and documentation consistency; regenerate atlas if declarations
change. No live earnings, holdout qualification or full-system P&L claim.

Rollout/rollback: offline Dev only; default baseline remains selected. New run
directories never overwrite prior results. Roll back a correction through Git
or stop selecting its research helper. No runtime configuration/schema impact.

Remaining: review findings and larger follow-up slice, comparison receipts,
candidate coverage, untouched data and separately authorized rollout.

## Bounded corrections authorized in this review

- Penny: anchor a retest before both confirmation candles, and require a
  complete same-minute cumulative-volume prefix in earlier sessions. A missing
  opening minute must not become an artificially small volume baseline.
- Momentum's new model only: use shipped `atr_at_entry` and configured regime,
  refuse another-session/zero-volume fills, expose missing/late square-off
  evidence, and bind the actual exit settings/model in the research receipt.
  Preserve the existing default proxy and all shipped live functions.
- EDGE: correct fidelity metadata to PROXY/EVALUATOR_ONLY. Independent signal
  trials with incompatible daily time-stop ordering and no cash ledger must
  not be advertised as a completed shipped lifecycle. No exit-policy rewrite.

Meaningful regressions cover a previously impossible retest, consecutive
breakout suppression, gapped volume prefixes, next-day/zero-volume/late-deadline
refusal, ATR/regime forwarding and research scope. Larger issues below remain
planned rather than disguised as minor fixes.

## Larger follow-up plan — not implemented here

The original N0–N4 plan is **partially implemented**, not finished. N1 has
measurement extensions; N2 has a subset-only Penny context filter and an exit
diagnostic; N3 has disconnected pure Range/Swing helpers. Neither runtime
policy nor the all-module Yahoo selection changed. There is no N4 qualification.

| Slice | Problem/files/contracts | Acceptance | Rollout and rollback |
| --- | --- | --- | --- |
| R1: repeatable candidate interface | Yahoo CLI selects baseline only. Wire explicit named variants through existing Lab; retain original decision/funnel and all trial manifests. PEN_CONTEXT currently filters already accepted setups and cannot recover a baseline-rejected opportunity. Swing helper has no pullback/chase rule; Range's rolling-date ID does not establish a persistent deduplicated thesis. | Baseline unchanged; separate configs/results, no hidden gate changes, actual completed-bar context and current functions reused. Max two declared candidate policies/module plus baseline, with all earlier trials recorded. | Offline first; default BASELINE; disable candidate selection to roll back. |
| R2: exact EDGE execution, holding clock and cash | `edge_next_open_lifecycle` changes entry day but passes its entry-day bar to a simulator specified for bars after entry. For hold_days=1 it can choose a future daily target before a time exit priced at that same day's open. Shares stay discovery-sized after a gap; no entry slippage, open-position dedupe or shared cash. `non_fno_research.py`, daily replay/Lab, compare actual orchestrator semantics. | Freeze actual entry/exit clocks; no future high before an already due open exit; executable entry/geometry/risk revalidation, zero-volume and missing-session refusal. Match equal cash/risk, persistent positions, per-order costs and marked/unresolved equity. Show gap/holding-clock/capital counterexamples. | Research PROXY until proven; do not change runtime simulator/orchestrator just to fit a backtest. No live EDGE recovery bypass. |
| R3: causal Momentum path measurement | Bar timestamps are starts but accepted close is treated as entry at that start. The new high-first discretionary logic can skip a partial on the way to target, ratchet from a future high, and miss a stop crossed after that ratchet. Close decisions use the bar-start time. Partial unresolved cash is not reconciled. `momentum_replay.py`, existing exit/path studies and Lab. | Declared completed-bar availability/next executable entry; compare admissible intrabar paths or require quote evidence; mark ambiguous outcomes rather than call them conservative exact replay. Preserve hard intraday deadline, actual partial quantities/fees and realized/reserved/open equity. Golden cases against shipped exits and clock contracts. | Keep separate diagnostic model; proxy still available. No live exit changes; baseline selector rollback, existing positions keep admitted exits. |
| R4: context/data and remaining module lifecycle | PEN_CONTEXT needs five prior native same-minute profiles; previous five-session archive has at most four and gaps. No intraday warm-up is loaded. Swing/Range still lack complete execution/exit/cash replay, EDGE ranking/exit variants and PEN_EXIT are not completed. Existing approved-budget comparison is also absent. | Independently acquire native Yahoo warm-up before scoring, without changing scored dates; unavailable stays unavailable. Separate exact historical membership/context from current-universe approximation. Complete actual strategy lifecycle adapters; compare approved budgets only as a separately frozen study, never substitute for the original bankrolls. | Broker-free/isolated caches; no invented minutes or broker context; stop selecting any unavailable adapter. |
| R5: holdout and F&O compatibility | No complete trial ledger, untouched qualification or live resource isolation evidence. N0 cash/resource protections cannot be inferred from source-only research isolation. | Freeze new future holdout and acceptance before observing outcomes; credible costs/slippage stress, marked drawdown and dependence-aware uncertainty. Protect F&O cash headroom, decisions/exits, quote/API capacity and scheduler/DB deadlines in paired load/failure tests. | Remain offline/shadow until gates pass. Any GitHub promotion/canary remains separately authorized. Rollback only non-F&O entries and never removes exit authority/reservations. |

Implementation order: R1 and R4 data contracts, R2/R3 causal measurement, then
actual bounded candidate comparisons and R5. Do not tune thresholds to turn
this five-session sample positive. Positive/negative diagnostic changes from
more faithful exits are measurement differences, not newly deployed alpha.

## Completed review/testing receipt

[Results and interpretation](2026-10-04-non-fno-review-and-backtest-results.md)
record both completed same-parameter Yahoo repeats: all 16 outcomes and metrics
match the original before and after corrections. Three separately frozen studies
completed: PEN_CONTEXT zero entries/no profitability; Momentum shipped-exit
diagnostic −₹19.007674 (older proxy −₹0.827101); EDGE independent-trial PROXY
closed sum −₹60,813.839964, not portfolio loss or a validated lifecycle result.

130 focused tests passed (one existing HTTPX deprecation), affected source
compiled and diff checks passed. Atlas regenerated to 241 modules, deterministic
on repeat. Data/report/source verification binds 32 repeated outcomes, 2,406
raw-response hashes, both raw/validated snapshots, configurations/universes and
three frozen studies; large evidence stays local with retention receipts.
F&O catalogue and protected shipped/shared/F&O source paths are unchanged.
No Production access, broker action, settings/funding/schema/dependency change,
push or deployment. Source baseline `434c4cc`; review corrections/docs/results
remain Dev-local and uncommitted. R1–R5 and original N0–N4 acceptance are open.
