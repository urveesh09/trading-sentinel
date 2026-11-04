# Penny strategy search — three rounds, November 4, 2026

## Result

**No robust wholesale replacement for Penny was established.** The best frozen
overnight finalist, **G05**, earns 25% more modeled net than the shipped
overnight book at its native Rs 25,000 allocation, with 21% greater drawdown.
However, its advantage is concentrated in 2024, largely attributable to fewer,
larger positions, and fragile to execution costs. The best Smart alternative
reduces losses but remains unprofitable. No candidate is deployed or qualified.

This is the completed result of the requested iterative search, including
failed hypotheses and genome trials. A profitable-looking row has not been
turned into a claim of profitable live trading. All source is in Dev;
Production, actual capital, flags, orders and the Breeze allowance are unchanged.

## Search and evidence

- Three Smart rounds: six candidate parameter sets beside continuous V1/V2.
- Daily round 1: trend pullback and recovered-panic/flush families.
- Daily round 2: standalone stock-specific overnight persistence/pressure.
- Daily round 3: a fixed-seed, capped population of 12 genomes (two retained
  round-2 seeds plus ten new variants), using training and calibration only.
  Later variants preserve the shipped EDGE signals, regime and sizing, varying
  overnight evidence and concentration. This is a bounded genome search, not
  an unlimited evolutionary optimizer.
- In total: **20 candidate parameter configurations**, with one economic
  duplicate explicitly removed from finalist selection; every trial retained.
- **87 completed score artifacts** cover exploratory/corrected training,
  calibration, references, final validation, capital and execution stresses.
  These are separate experiments; their profits are never added together.
- **119 focused tests passed**, one existing deprecation warning, process exit 0.
  Additional real-input baseline/cache parity and 20 real-input causal-prefix
  checks pass. Cash, gross/fee/net and final-equity identities were reconciled.

## Data, clocks and what validation means here

Public acquisition made 766 Yahoo requests, independently of Breeze. NSE
price-basis checks retained one successful 2024 file and a failed 2019 probe.
The Production cash cache was exported using a consistent read-only transaction
to Dev, not copied as an active SQLite main file. No broker market-data or order
API was called. **Breeze calls: zero.**

The starting list is the fixed union of the existing research and November 3
operational universes: 153 symbols. It is not historical point-in-time membership.
The nominal-price audit excludes all 45 reported split/bonus histories from the
primary daily comparison, leaving the same **108-symbol restricted cohort** for
all daily arms. Available NSE January 2, 2024 close checks matched within 0.5%
for retained names. See `BASIS_CORRECTION.md`. Missing histories, invalid rows,
new listings, absent fundamentals and other corporate actions remain limits;
108 requested names do not mean 108 eligible/tradable stocks on every date.

Daily development is 2019–2022; calibration is 2023; frozen final validation is
2024–2025. Those validation years have been used by earlier Sentinel studies,
so this is **conditional historical validation, not untouched qualification**.
The restricted surviving universe also prevents a general historical investment
return claim. Daily buys use a close proxy for the 15:20 order, sales a next-open
proxy; actual spreads, depth, auction participation and circuit availability
are not observed. No overnight stop execution is assumed.

Intraday development is September 7–October 16, 2026; final validation is
October 19–November 3. The 24-symbol compute bound is selected by development
minute availability, with alphabetical ties, before outcomes. Both baselines
and candidates use exactly that list and source snapshot. Validation dates were
also already partly observed through Production, so no untouched claim applies.

Current B1 contracts show only seven COMPLETE development symbol-days and one
COMPLETE validation symbol-day in the 153-name requested panel; most are PARTIAL.
The explicit gap-sensitivity model therefore cannot establish full execution
fidelity. Invalid days are excluded, gaps are not forward-filled and missing
exits remain pending. Trades use completed-bar decisions and subsequent traded
minute-open proxies with declared spread, not reconstructed bid/ask depth.
The replay is not expected to reproduce Production P&L on different dates,
membership, quotes or opening exposure.

The reserved January–July 2026 `penny-noise-t3` archive was not opened for prices,
trained or scored. F&O/expiry data and their protected exams were not used.

## Iterations and lessons

### Round 1: ordinary short-hold long strategies do not earn their costs

On the corrected daily cohort and Rs 100,000 starting capital, pullback loses
Rs 39,350.62 over 472 closes; flush/recovery loses Rs 63,225.48 over 663.
Both lose before costs. Three-session time exits dominate. More activity and
a fee-only explanation are unsupported.

The shipped main multi-day EDGE proxy also loses on this fixed historical
panel; the separate shipped overnight proxy is strongly positive. That finding
directs the later daily rounds toward the overnight payoff rather than tuning
the failed daytime hold. These are counterfactual bar experiments, not the
actual historical Production account or exact runtime auction fills.

The corrected Smart V1/V2 development baselines lose Rs 91.50 / Rs 82.46.
Participation/VWAP confirmation improves the result to -Rs 18.83 but still
loses after costs. Simply allowing more thesis failures and longer stalls
loses Rs 71.68. More patience alone does not create an entry edge.

### Round 2: entry timing improves Smart; standalone night forecasts disappoint

Smart retest entry reaches -Rs 3.90 on 65 closes; day-high structure loses
Rs 29.47 on 51. Retest is the better entry hypothesis, but not yet profitable.

Standalone daily night persistence loses Rs 33,643.31; pressure earns
Rs 29,674.63 on the 2019–2022 corrected cohort, both far behind the shipped
overnight proxy. Wholesale replacement of its candidate generation is rejected.

### Round 3: keep the shipped daily engine; retain failed Smart management

The 12-genome population combines the shipped EDGE opportunity set with causal
night evidence and two/three-slot allocations. Selection uses training
ex-best-winner economics and worst train/calibration performance relative to
drawdown, never the final validation outcome. G07/G09 produce identical economic
histories, so the corrected selector retains G07 and G05, not two copies of one
result. All 12 genotypes remain in `basis-v2/genome-selection.json` and its v2
deduplicated selector.

Smart winner-room and cleaner-retest variants lose Rs 24.77 / Rs 15.86 on
development. The two frozen Smart finalists are retest and cleaner retest.
The later management changes do not rescue the family on validation.

## Best daily finalist: G05

Its **active rules** are simple:

1. Keep the shipped EDGE signal generation, regime, minimum strength, ranking,
   risk-plan quantities and daily-bar realism refusals.
2. Require a shrunk mean of the stock's last 60 overnight returns of at least
   0.1%. Each return ends on or before today's decision close, is clipped to
   +/-5%, and the mean is multiplied by `60 / (60 + 20)`.
3. Fill up to **two positions**, with the own-cash share/capacity rules, buy at
   the declared close proxy and sell at the next observed session open.

The selected genome's strength weight is 1.0: its day-fade and volatility-tilt
genes do not affect ranking. They are not marketed as working predictors.
The tested candidate specification is in `candidate.json`.

Paired continuous 2024–2025 experiments, same initial capital and current fee
schedule throughout, 25 bps adverse entry / 10 bps adverse exit:

| Rs 25,000 starting book | Shipped overnight | G05 |
|---|---:|---:|
| After-cost net | 14,465.31 | 18,096.96 |
| Net without best trade | 13,225.77 | 16,464.34 |
| Marked drawdown | 2,135.90 | 2,583.14 |
| Closes | 337 | 258 |
| Profit factor | 1.7091 | 1.8611 |
| 2024 entry-dated net | 8,749.29 | 13,302.89 |
| 2025 entry-dated net | 5,716.02 | 4,794.08 |
| Distinct entry days | 218 | 198 |

G05 increases full-period net by **25.11%**, drawdown by **20.94%**, with 23.44%
fewer closed trades. It underperforms in 2025; improved aggregate net is not
consistent annual dominance. Both books compound their own realised equity;
the 2025 figures are contributions within continuous books, not fresh-year
independent returns.

At Rs 100,000 the gain is only 13.66%: Rs 75,771.13 versus Rs 66,664.55, with
drawdown Rs 11,031.90 versus Rs 8,309.60. It passes the original four-part paired
acceptance at both allocations but **misses the additional 20% material-gain
hurdle on the primary Rs 100,000 experiment**. Neither book works at Rs 2,000:
delivery fees and small tickets nearly exhaust that modeled book.

### Attribution prevents an unsupported new-alpha claim

Fixed post-validation controls at Rs 25,000:

| Control | Net | Drawdown |
|---|---:|---:|
| Shipped three-slot book | 14,465.31 | 2,135.90 |
| Two slots, no overnight-mean screen | 20,202.40 | 3,151.90 |
| Three slots, with overnight-mean screen | 12,586.21 | 1,567.00 |
| G05: two slots and screen | 18,096.96 | 2,583.14 |

The overnight screen reduces risk, but does not supply the aggregate profit
gain by itself. Much of G05's gain comes from holding fewer, larger positions.
The two-slot diagnostic is not silently promoted as a newly selected winner:
it was a post-validation attribution control, not a frozen finalist.

A descriptive 20-session block resampling interval for G05's native realized
PnL difference is approximately **-Rs 2,350 to +Rs 8,917**. It includes zero.
This conditions on observed cash paths; it is not a probability of future
profit, a full rebalanced bootstrap, or correction for all historical searches.

### Execution stress rejects a strong replacement claim

| Native Rs 25,000 friction | Shipped net | G05 net |
|---|---:|---:|
| Entry 25 bps / exit 10 bps | 14,465.31 | 18,096.96 |
| Entry 50 bps / exit 30 bps | -1,848.66 | -35.03 |
| Entry 100 bps / exit 60 bps | -16,697.30 | -15,954.57 |

Even the middle stress removes native-book profitability. Missing bid/ask depth
and actual auction fills therefore remain decisive. A paper pilot cannot be
justified from the pleasant headline alone, and no live activation follows.

## Smart final validation: losses reduced, both candidates rejected

Rs 2,000 books, October 19–November 3, 24 frozen names, 10 bps modeled total
spread and current intraday charges:

| Policy | Closes | Net | Ex-best | Marked drawdown |
|---|---:|---:|---:|---:|
| V1 | 56 | -117.00 | -124.35 | 128.67 |
| V2 | 55 | -85.31 | -87.43 | 92.22 |
| S2 retest | 27 | -55.39 | -55.98 | 62.30 |
| S3 cleaner retest | 33 | -52.17 | -52.64 | 57.79 |

The best loss reduction versus V2 is **38.84%**. It still loses before fees,
and neither finalist passes acceptance. Wider-spread results remain negative;
trade count collapses at the highest spread, which is abstention, not profit.
No Smart candidate is promoted over V1/V2.

Cleaner retest averages approximately -Rs 1.58 per close versus V2's -Rs 1.55.
Its lower total loss largely reflects fewer trades, not improved per-trade
expectancy. It should not be presented as a profitable or smarter replacement
merely because the aggregate loss is smaller.

The new replay's initial carry-rollover bug was corrected and **all eight**
baseline/candidate training parameter sets rerun before final selection.
Original results remain. See `CASH_ROLLOVER_CORRECTION.md`. All completed flat
Smart runs reconcile final cash to initial allocation plus the recorded net
closes. Runtime source/bindings and live paper books were never patched.

## Classic reference and unsupported conclusions

Classic MIS with the current pure profit lock closes three losing trades for
-Rs 8.83 and leaves one unresolved exposure on the development panel. The new
reference refuses the older adapter's premature future-gap fill/cash release.
This is a partial reference, not a valid total return or an improvement verdict.

Classic CNC reference: October 19–27 entries with a November 2 exit tail,
constant PR1 and fresh declared paper book. Its 144 evaluations produce no
accepted entry; RSI/trend/history rejections are retained. Its native receipt
has null P&L, not invented profit. No separate CNC improvement is established.
MIS/CNC joint capacity, historical regime/universe and scheduler continuity
are not reconstructed by adding these separate experiments.

## Verification, status and next valid evidence

- Shipped EDGE scan/cache candidate sizing parity passes on synthetic cases;
  on real January 2–10, 2023 input, native and cached own-cash equity curves and
  financial summaries are exactly equal. This covers the declared adapter,
  not historical quote/auction execution.
- Twenty real-data prefix truncations preserve candidate decisions exactly.
- All daily validation gross/fees/net, positive quantities, overnight dates,
  final cash and nonnegative equity identities pass. Flat Smart cash identities
  pass; unresolved positions are never erased to claim profit.
- 119 relevant mechanics/strategy/replay tests pass; compilation and atlas
  verification are recorded in `verification.json`. No full application suite
  or live order test was needed for these new research-only tools.
- All raw replies, failed probes, initial invalid-for-nominal-band comparisons,
  source freezes, duplicate genotype, initial rollover scores and corrections
  are retained. No invalid output is silently overwritten.
- `evidence-hashes.json` seals 891 artifacts; `verification.json` records
  39,040 repeated closed-trade financial identity checks and 28 flat Smart
  cash reconciliations. These are repeated experimental records, not unique
  real trades. `trial-ledger.json` preserves all 20 candidate configurations.

Implementation/freeze history: `ca3b748`, `e04b254`, `dbfcde6`, `15d9eff`,
`bc53808`, `0dbf22c`, `0cc9df6`; final packaging identity is recorded in the
completion receipt/Git log. Required system docs and active plan were updated
with each implementation slice and checked immediately after commits. Owner
working changes were staged separately and remain preserved.

Research is **Dev-only, committed locally, not pushed or deployed**. No schema,
dependency, native strategy, bankroll, live/paper switch or provider-allowance
change. Existing Production tracked files remain clean. No broker, Telegram or
order operation occurred. Test success is not strategy profitability or partner
qualification.

The economically meaningful next evidence is prospective, paired quote/auction
execution on fresh dates with frozen rules, at the actual native allocation.
`FORWARD_EXAM.md` defines that exam without installing a collector, scheduling
a job or changing Production. Further tuning on the now-seen validation years
cannot turn them back into an untouched test.
