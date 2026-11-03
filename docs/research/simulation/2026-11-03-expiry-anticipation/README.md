# Expiry anticipation and modest extra risk

Plain report: [EXPIRY_RESEARCH_ANTICIPATION.md](../../../EXPIRY_RESEARCH_ANTICIPATION.md).
Starting contract [PLAN.md](PLAN.md), current completion [STATUS.md](STATUS.md).
No accepted candidate, no native engine/config/schema change, no deployment.

## Scope and inputs

105 already-seen NIFTY expiry-minute tapes, 52 in 2024 and 53 in 2025, from
`../2026-11-03-expiry-e02/_local/2024.sqlite` and `2025.sqlite`. Full hashes in
`initial.json`; prior source/research/Production fingerprints and owner bytes
are verified by `guard.py`. No new 2026 chain/quote experiment, acquisition,
2023 access or consumption of the protected future exam. Full SENSEX selection
is unavailable in this frozen input set, not inferred from opening-ATM files.

All financial figures are normalized to current 65-unit lots and native NFO
fees, not historically realized lot/tax PnL. BAR_LIFECYCLE / PARTIAL. Completed
current-bar decisions, next-bar open plus model spread/adverse costs or severe
high/low, 20% volume participation proxy; no historical depth or queue proof.
Own Rs 25,000 per counterfactual book, continuous across its stated calendar,
two sequential tickets, same absolute brakes. No sum of arms or independently
reset years is system profit. Different calendars have different controls.

## Frozen rounds

| Contract | Before-score commit | Mechanism |
|---|---|---|
| `freeze-size.json`, PLAN.md | `83fdf76` | SCALE25 / RUNNER25: same original contract, at most 25% more research reserve |
| `freeze-forecast.json`, PRECURSORS.md | `db05ff6` | Two executable-target probability models, fixed causal features and preprocessing |
| `freeze-return.json`, RETURNS.md | `0b77af6` | Two adverse net-return forecasts; no tuned probability cutoff |
| `freeze-smart.json`, SMART.md | `8b78a40` | Fixed prior-quarter hero forecast only gates extra second lot; original E03.1 remains |
| `freeze-forest.json`, FOREST.md | `2bb557e` | Two fixed nonlinear models, whole-day bootstrap, shallow supported/shrunk leaves |

Nine primary hypotheses, no hyperparameter genome, best-seed selection or
test-window threshold search. Both years were previously studied: fitting a
new model only on one year is not newly independent market validation. The
backwards-year transfer is a diagnostic, not deployable chronology. Causal
models refit quarterly on only completed prior quarters after 13 training
expiries; their 92-day portfolio starts April 4, 2024 with a fresh matched control.

## Data and artifact map

| Artifact | Meaning |
|---|---|
| `size-results.json`, `smart-results.json` | Whole book positions/events/days at all fills, independent years and continuous cash |
| `dataset-summary.json` | 18,787 overlapping decision examples, 37,574 executable 2x/5x labels; 105 day clusters |
| `_local/cases.npz`, `_local/cases-meta.json` | Hash-bound private feature matrices, labels and candidate metadata; no raw broker data pushed |
| `forecast-results.json`, `return-results.json`, `forest-results.json` | Fixed models, full funded book histories and evaluator diagnostics |
| `*-predictions.json` | Frozen inference outputs, no new selection rule |
| `audit-results.json` | 108 primary/control native lifecycle/accounting replays, all labels/features, 210 truncated-prefix checks |
| `diagnostics.json` | Three matched-calendar control audits; fixed 36 coarse-budget/12 friction runs; all factor descriptions and concentration |
| `decisions.json` | All nine fixed acceptance verdicts, none accepted |
| `daily-results.csv`, `trades.csv` | 7,602 model day rows and 1,580 repeated position rows; source/arm/calendar explicit |
| `verification.json` | Commands, 53 focused checks, native parity totals, runtime, atlas, tooling limits |
| `LITERATURE.md` | Primary sources; predictive information is not assumed profit |

Eight unresolved **training-label** outcomes remain conservative non-hits and
full-premium loss labels, not missing profitable trades or accepted settlement.
Actual funded portfolio histories have unresolved zero. Overlapping example
returns/precision are EVALUATOR diagnostics and may never be summed as PnL.
`hit` denotes a completed TARGET-reason exit after its bid trigger, not a
guarantee the later execution achieved exactly 2x/5x. Financial outcomes use
the actual later prices and fees. Different fill scenarios can refuse different
entries and change brakes, so they are not monotone bounds on identical trades.
Current fees, clipping of training tails and strong day-level model regularization
are assumptions; actual funded-book gains/losses are never clipped.

The risk arms use up to 1,562.50 ticket / 3,125 daily original reserve, same cash
and absolute brakes. The forecast portfolios retain original 1,250/2,500 caps
and one lot. No blanket assumption that a 35% stop fills at 35%. Marks are only
available complete-bar model bids with costs, not intrabar broker NAV.

## Reproduction

Use Dev `python-engine/winvenv/Scripts/python.exe` (3.11.9, numpy 1.26.4); no new
dependencies. No provider, scheduler, live DB or secrets passed. Guards refuse
changed or uncommitted freezes; results refuse overwrite. Inspect the original
outputs rather than retrying immutable score commands in place.

```text
size_study.py verify
forecast_study.py verify
return_study.py verify
smart_study.py verify
forest_study.py verify
guard.py verify
```

Tests: pass the five explicit `test_risk.py`, `test_precursor.py`,
`test_return.py`, `test_smart.py`, `test_forest.py` paths plus
`python-engine/tests/test_expiry_e02.py`, `test_expiry_e03.py`, `test_expiry_e031.py`
to `python -m pytest ... -q`. Avoid recursive collection after evidence source
copies and ignored pinned checkout exist. Exact command/log hashes are recorded.

Original execution: `size_study.py score`, `forecast_study.py score`,
`return_study.py score`, `smart_study.py score`, `forest_study.py score`,
`anticipation_audit.py`, `diagnostics.py`, `final_checks.py`. They are one-shot;
existing results/private dataset must not be overwritten. Raw selected DBs and
private arrays remain ignored local owner evidence; exact reproduction on
another machine needs those same bytes and frozen line endings. Never relax
a hash/clock/cash guard to make a result pass.

`risk_day.py` is materialized from E03.1 with one asserted room-sizing hook;
other loops change imported signal/pick functions. Native money/action parity
uses unchanged `expiry_e02.action`, `sell_base` and expiry_paper position/fee
functions with isolated in-memory positions. Entry price/depth fidelity remains
the declared historical bar model, not broker execution.

Staging shared docs uses only new prefixes + original HEAD tails. Original
owner working tails are preserved byte-for-byte in `_local/*.initial`; never
stage them wholesale. Runtime rollback/migration is unnecessary: isolated
research has no enabled book. No failed model gets the original future exam.

Research **22f8845**, pushed and remote-verified. [evidence/REPORT.md](evidence/REPORT.md) records 38 partial/unavailable receipts. `verify_anticipation_evidence.py` checks the same original source and money against its pinned commit after later documentation moves HEAD. No original guard is relaxed. Commit/push packet: [completion-receipt.json](completion-receipt.json).
