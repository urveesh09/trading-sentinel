# N06 — test past-only selection before increasing exposure

This finishes the saved-variant selection slice. It is offline Dev research,
not a change to Production or evidence that profitable switching is proven.
All 2024–26 years were already seen; the 2023 option exam remains deferred.
Results/report committed and pushed in4525278; pre-score sourcea5b2d7c,
daily decision manifest5c74b47. Production unchanged.

## What the selector knows

Each day compare the preceding84 archived same-year sessions of four complete
shadow reference policies: original MAIN, original balanced retest BASE, early
STALL30, and structure-aware STRUCT30. Use only labels whose positions exited
before that day, never the current day's outcome, future bars or a partial trade.
Reset learning/persistence each January because these are fresh annual books.
MAIN_ANCHOR defaults to MAIN; STRUCT_ANCHOR defaults to STRUCT30.

A challenger needs eight weekly buckets, ten nonzero paired days, twelve
challenger/six anchor closes, positive weekly mean delta minus one standard
error, positive improvement after removing its best day, and no higher trailing
closed drawdown. It must qualify on two consecutive decision dates. Unsupported
choices immediately return to anchor. Tie order BASE/STALL30/STRUCT30/MAIN is
fixed. No parameter/grid changes followed results.

Selections are attached to admissions, together with immutable entry economics
and label cutoff. Later choices cannot change existing positions. MAIN retains
original EFF entries; balanced variants use the exact N03 retest. Pending retests
reset at day/variant transitions. Missing decisions refuse new research entries;
stale bars cannot route a new adaptive entry. Native stops, trail,60min soft
stagnation checks and hard flat remain active, including short sessions.
This daily variant selector does not claim a newly learned intraday regime.

## Measured modeled results

| Configuration | 2024 modeled net | 2025 | 2026 to Oct28 | Worst annual closed fall |
|---|---:|---:|---:|---:|
| MAIN | Rs+16,371 | Rs+5,710 | Rs+30,540 | 7.47% |
| BASE | Rs+56,192 | Rs+50,090 | Rs+54,153 | 5.22% |
| STALL30 | Rs+51,303 | Rs+54,051 | Rs+77,135 | 4.65% |
| STRUCT30 | Rs+57,243 | Rs+50,726 | Rs+61,496 | 5.00% |
| MAIN_ANCHOR | Rs+13,735 | Rs+3,809 | Rs+55,291 | 8.55% |
| STRUCT_ANCHOR | Rs+57,243 | Rs+50,726 | Rs+61,496 | 5.00% |

FreshRs250000 per year, original2/3-lot limits, LOW-day TPB one lot, normalized
65-unit lot; modeled candle bid/ask/current fees and stress(200+5*lots)*lots.
Independent annual books are not a continuous account or whole-system portfolio.
Closed-equity drawdown does not bound intratrade, gap, liquidity or future loss.

| Year / selector | Daily selections (includes no-entry days) |
|---|---|
| 2024 / MAIN_ANCHOR | MAIN: 195, STRUCT30: 53 |
| 2024 / STRUCT_ANCHOR | STRUCT30: 248 |
| 2025 / MAIN_ANCHOR | MAIN: 174, STALL30: 74 |
| 2025 / STRUCT_ANCHOR | STRUCT30: 248 |
| 2026 / MAIN_ANCHOR | MAIN: 113, STALL30: 90 |
| 2026 / STRUCT_ANCHOR | STRUCT30: 203 |

Daily selections include days with no admissible signal: they are not fills,
trades or switching profit. Actual admitted variants are in results.json.

## Frozen acceptance and failures

Source/input/config freeze committed before scoring. Twelve fresh static annual
controls reproduce all four saved policies exactly; daily choices/hash manifests
then committed before six candidate annual replays. Primary rule: at least all
three balanced references' net and no larger drawdown than any in EACH year;
positive net after removing best trade/day;>=12 annual/60 total closes;5/6
profitable half-years;t>=2 versus STALL30 and four-week-block two-arm max-T
p<=.05 (4096 draws,seed110601). Full monetary paths and exact drawdowns underlie
checks, rather than rounded displayed amounts.
The inherited frozen2026 blocks are Jan-May and Jun-Oct28, not calendar
half-years;2024/25 use Jan-Jun/Jul-Dec. CHECKER_CORRECTION.md preserves the
initial independent check's calendar-period assumption and its correction.
Neither replay scores nor the primary acceptance verdict changed.

| Candidate | Failed predeclared checks | t vs STALL30 | Adjusted p |
|---|---|---:|---:|
| MAIN_ANCHOR | without_best_trade, without_best_day, net_not_worse_all_references_each_year, drawdown_not_worse_all_references_each_year, paired_weekly_stall, max_t | -2.15 | 1.0000 |
| STRUCT_ANCHOR | net_not_worse_all_references_each_year, drawdown_not_worse_all_references_each_year, paired_weekly_stall, max_t | -1.03 | 0.9602 |

Passing candidates: **none**.
Even a pass on this repeatedly inspected history would not qualify deployment.
Chronological causality and guardrails are software properties; predictive
profitability requires fresh evidence. All failures and original static variants
are retained; do not choose a different benchmark or lower support after scoring.

## What this adds to the earlier learning

MAIN_ANCHOR produces aboutRs2636 LESS than MAIN in2024,Rs1901 LESS in2025,
andRs24751 MORE in2026; its worst annual closed fall increases to8.55%.
Positive past relative results did not reliably identify the next profitable
opportunity. It also gives up much of the fixed balanced variants' profit while
waiting for enough supporting labels. This does not establish that all possible
regime models fail; it rejects this particular frozen rolling-profit selector.

Selector-attribution.json separates matched economics from changed opportunities.
MAIN_ANCHOR's deltas versus MAIN arise from unpaired admissions/cash/priority
paths; matched economic admissions have zero paired exit delta in each year.
Therefore the2026 gain cannot be described as a pure smarter-exit effect.

For STRUCT_ANCHOR, BASE differs on at most1/1/2 days within a rolling window
in2024/25/26; STALL30 differs on at most2/4/4 days. The ten-paired-day guard
cannot justify either, and other guards also fail. MAIN qualifies for only one
isolated2026 date and fails two-day persistence. The resulting selector is
exactly the fixed STRUCT30 book; zero switches is not an adaptive improvement.
Do not lower these evidence requirements after seeing this outcome or promise
that a higher lot allocation would repair it. Preserve the earlier structural
loss-reduction lead separately from this failed selector test.

## Execution-evidence availability

Production's data volume was mounted read-only in a disposable network-disabled
container; SQLite used mode=ro and a read transaction. The privacy-minimal
inventory records51 closed FNO_PAPER positions, no real-execution event table and
no real-test run table. It also finds33 quote-archive days throughOct30 and three
exit-path files throughOct29. This establishes unavailable actual execution-cost
evidence, not proof that no order ever existed at a broker. Paper outcomes do not
replace real fills, charges, slippage, spread, partial fills or decision latency.
No credentials, account identifiers, broker/Telegram calls or raw live rows were
exported. No Production edits/restarts/deployments or money/settings changes.

## Verification and limits

See VERIFICATION.md, selection-crosschecks.json, path-crosschecks.json,
statistics-crosschecks.json, selector-attribution.json and input-reuse.json.
109 focused checks passed:92 research,6 adverse-history/read-only and11 native
exit/replay checks. 911 closed
financial/admission identities reconcile. Independent audits verify 1398 daily
choices, 4194 candidate evidence models and 1822 archived entry/exit
prices; 18 cash paths, six weekly vectors and both resampling tests agree.
Earlier699 raw/cache checks are reused only through exact inherited hashes;
none is counted as freshly executed. Known gaps and56 original2025 negative-volume
bars remain recorded. No historical live depth or complete live regime evidence
is invented. Shadow whole-policy labels use the same frozen modeled costs and
fresh annual accounting; deployment would first need durable prospective shadow
outcomes for ALL reference policies, not just the selected trades.

## Successor instructions and remaining work

1. Preserve FNO_RESEARCH_REFERENCE, FNO_RESEARCH_CHALLENGERS and
   FNO_RESEARCH_PROGRESS md/json identities. N06 adds a separate checkpoint,
   FNO_RESEARCH_SELECTOR_N06; it never silently replaces the three saved leads.
2. Do not repeat another threshold search and call it new validation. The bounded
   selector experiment is complete. Next collect dated, keyed prospective shadow
   admissions/quote paths and execution receipts under explicit operator authority.
   Join entry decision, real fill, exit fills, broker charges and cash lifecycle;
   keep missing/partial/unreconciled evidence unavailable. Inspect the existing
   live-test runbook without arming/restarting it automatically.
3. Before scoring a future period, freeze all compared policy IDs, clocks, costs,
   sample and review rule. Use the SAME unselected shadow opportunities. Report
   calendar coverage, no-trade periods and failures; do not wait only for wins.
4. The2023 exam is still deferred until the owner explicitly requests it. Historical
   testing is not authorization to download, score a holdout, deploy or trade.
5. Larger lots are not supported by these switching results. Conditional later
   sizing must retain own-cash/per-trade/daily/portfolio risk budgets, equal-risk
   controls and full-premium/gap/spread/concentration stress. Reduced losses in
   six prior cases do not identify a future winning trade or guarantee drawdown.

Rerun: use python-engine/winvenv/Scripts/python.exe; variant_lab.py verifies frozen
code/input hashes and committed manifests. Private inputs/evals remain _local,
ignored by Git; source, verdicts, hashes and commands are committed. Post-run
skill evidence packaging checks consistency, not preregistration or profitability.
