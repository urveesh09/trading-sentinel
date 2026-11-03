# Expiry anticipation and modest extra risk — November 3, 2026

Owner now explicitly permits a little more risk if additional earnings justify
it, while prohibiting extreme risk. Investigate precursors to large moves and
whether execution can act before the opportunity is priced. This reopens
research after the failed E03.2, structural and auction studies; it does not
authorize live capital, enabling flags or editing Production.

## Data and contracts

Dev only. NIFTY 2024/2025's 105 selected expiry-minute tapes remain seen
development. NIFTY 2023 and the E03-family future exam are protected. No new
download, provider, broker, scheduler or message. Immutable earlier studies and
all original owner bytes preserved. Source/data/Production frozen before score.
Historical minute prices can test minute-scale anticipation, not subsecond
order-book or order-queue advantages. Price/volume/OI are not signed dealer flow.
No theories or provisional auction indices become executable historical prices.

## Round 1: two fixed sizing mechanisms, frozen before score

Baseline: unchanged E03.1, same signal, contract, fees, fills and book. New
research-only maximum ticket reserve **1,562.50** (25% above 1,250); maximum
daily original premium plus fees **3,125** (25% above 2,500), same own 25,000
cash, at most two sequential entries, at most three lots, same absolute
1,500/3,000/4,000 drawdown brakes, same stop/runner/flat rules. No profit refills.
No added leverage, short options or new strikes. A catastrophic day can still
lose the entire authorized reserve; stops are triggers, not fill guarantees.

1. **SCALE25**: first choose exactly the contract the original E03.1 can afford
   inside 1,250 at decision time. Increase its affordable lots (max three) inside
   1,562.50. The new allowance must not admit a nearer, previously unaffordable
   contract or a new signal. This is a sizing control, not a new entry edge.
2. **RUNNER25**: same original contract. Use extra reserve only if the baseline
   planned one lot and two lots now fit. Original two-/three-lot plans stay at
   their original lot count. Purpose: unlock a one-lot runner after selling one
   lot at 2x, without retaining a whole one-lot ticket or rolling to a cheap kicker.

Whole-book paths can diverge due runner duration, fills, cooldown and brakes;
do not force later entries equal or add reset-year results into continuous PnL.
Compare both new arms to baseline and to each other at all fill levels, both
years and continuous cash. Baseline event histories must match before scoring.

## Acceptance fixed before score

Higher profit alone is not a new edge. A worthwhile extra-risk hypothesis must:

- beat baseline net **after dividing by 1.25** in each year at ordinary/adverse
  fills, and beat baseline continuous net at those fills;
- have positive net excluding best day each year, positive continuous increment
  excluding the largest incremental day, no unresolved exposure;
- worst ordinary/adverse day no worse than -750, realized drawdown <=2,000;
- survive fixed added costs, coarse budget neighbours (20% and 30% extra,
  diagnostics only), continuous brakes and concentration checks. Severe results
  and full-premium losses are always disclosed, not a qualification loophole.

These are seen-year hypotheses only. A supported rule can proceed only to
disabled Dev paper implementation with a separate test/implementation slice;
no automatic promotion or live C replacement.

## Round 2: precursors, not a parameter genome

Separate pre-score contract will freeze two supervised prediction targets:
first executable 2x and 5x ticket outcomes before a 35% hard stop/time exit.
Features must precede entry: option price acceleration, relative traded volume,
OI change, index/future direction/noise, basis changes, moneyness/reach, time
and fees. No positive-volume-as-buying claim. Day grouping, causal labels,
training-only normalization, fixed regularization and cross-year/chronological
tests prevent overlapping labels or future transformations from leaking.
Both years are already seen and cannot be rebranded independent validation.
Predictive accuracy is separate from actual after-cost cash-book results.

## Files, checks, rollout and remaining work

Fresh folder `docs/research/simulation/2026-11-03-expiry-anticipation/`; report
`docs/EXPIRY_RESEARCH_ANTICIPATION.md`. Reuse E03.1 mechanics with asserted
generated hooks; materialized loops inspectable. Test causal sizing, unchanged
contract, no extra lots for RUNNER25's original multi-lot plans, costs, reserve,
cash, prefix stability and trained-model leakage. Full engine suite only if
runtime changes. Regenerate atlas and verify scope; maintain guide/plan/checklist
each commit, staging only our prefixes. Verify after every commit and remote
after push. No rollback of runtime necessary for isolated research. Original
PLAN immutable after freeze; progress tracked in STATUS.md.

Remaining: baseline, two sizing scores, frozen precursor study, diagnostics,
independent money/causality review, reporting, sealed receipts and Dev push.
