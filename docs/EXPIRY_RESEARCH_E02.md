# E02 R3 — a smaller, selective pullback ticket; research only

November 3, 2026. **E02 is built as a separate Dev paper incubator, disabled by
default. It is not a demonstrated out-of-sample profitable strategy.** The first
two candidates failed their untouched 2024 exam. Iteration continued with the
owner's authorization; the current R3 was fitted after both years were seen.
Its positive figures below must be read with that limitation.

The final joint-fit model earns **Rs 6,328.74 ordinary / Rs 5,669.02 adverse**
over 2024–2025, with 42 tickets, from one continuous Rs 25,000 cash book with no
refills. Worst modelled day is -Rs 571.61 / -Rs 591.11, realized drawdown
Rs 1,493.57 / Rs 1,396.37. Those are sample observations, not future loss bounds.
The very severe next-bar-high/low diagnostic loses Rs 3,219.14. No real order,
Production deployment, N11 change or main expiry-rule promotion occurred.

Full evidence: [E02 study](research/simulation/2026-11-03-expiry-e02/PLAN.md),
[R3 candidate audit](research/simulation/2026-11-03-expiry-e02/round03/candidate-audit.json),
[daily results](research/simulation/2026-11-03-expiry-e02/round03/daily-results.csv),
[trades](research/simulation/2026-11-03-expiry-e02/round03/trades.csv).

## What changed from the lottery

E02 does not buy C's ticket. It waits for a pullback within a strong trend:

1. A completed ten-minute index path has directional efficiency at least 0.7
   (net move divided by the sum of absolute minute moves). Price is within four
   ATR of the prior ten-minute mean.
2. The preceding two-minute net move pulls against that trend; the latest
   completed index close turns back toward it, and the latest future close
   moves in the same direction. Decisions use completed observations only.
3. Between 13:00 and 15:00, choose the nearest available out-of-the-money call
   or put costing roughly Rs 5–20. Strike distance must fit a causal reach
   proxy: past ATR times sqrt(minutes remaining to 15:30). This is a filter,
   not a calibrated probability of reaching the strike.
4. **One lot per ticket, at most two sequential tickets/day**, with a five-minute
   cooldown after a close. Each ticket reserves at most Rs 1,250 including fees;
   total original daily premium/fee reserve is at most Rs 2,500. Profits never
   replenish that day's allowance. No averaging down or leverage.
5. A planned 40% premium backstop; a stop two ATR away on the index; keep 60%
   of the premium peak from a 40% gain; sell the whole ticket at 2x; planned
   maximum hold eight minutes; flat requested from 15:28. At a 40% gain the
   60%-of-peak floor is still below entry, so it is not a cost-recovery promise.

The stop is wider than E01.1's, but the one-lot exposure is smaller. A gap or
missing bid can still lose the ticket's full reserved premium. The eight-minute
exit is a request: an unfilled exit stays pending, rather than becoming an
invented fill. The standalone book halves its daily allowance at Rs 1,500
realized drawdown, quarters at Rs 3,000, and stops new entries at Rs 4,000.
Existing positions continue their exits.

## The iteration history, including the failures

The inherited E01.1 2025 control first reproduced **106 complete position/event
records exactly**. Then the search explored box breaks, rolling breaks, retests,
pullbacks and fades, with coarse entry/exit settings and all fees.

| Stage | Genome evaluations | Result |
|---|---:|---|
| First 2025 round | 290 | Strong fitted breakout and pullback results |
| Second 2025 round | 476 | Tested a causal strike-reach filter and nearby rules |
| Fresh Jan–Jun / Jan–Sep fits | 181 + 175 | Their selected rules lost on later quarters |
| Joint 2024/2025, one-lot round | 663 | Neither first phase leader met the full target |
| Joint round, warm-started second phase | 961 | Found R3, now a joint in-sample hypothesis |

**2,746 rule evaluations**, plus separately recorded neighbour and execution
checks. Counts include cross-round duplicates and genes that do not affect a
particular exit path. They are not 2,746 independent discoveries. All ledgers
and source/configuration receipts remain in the study folders.

The first final source/input freeze was **`f2b95cd`**, before the 2024 option
paths were scored. That clean test failed:

| Original frozen finalist | 2024 ordinary | 2024 adverse |
|---|---:|---:|
| CORE | -3,083.58 | -3,191.26 |
| RUNNER | -3,079.55 | -3,096.31 |

Those results remain in
[exam-2024.json](research/simulation/2026-11-03-expiry-e02/exam-2024.json).
Neither was promoted. A first-half fit also lost -Rs 3,313 / -Rs 3,040 on Q3;
the later fit lost -Rs 3,029 / -Rs 3,019 on Q4. The genome's selection process
therefore cannot be trusted as an automatic adaptive trader.

Diagnosis found two issues. Early full-sized losses pushed the book into a
quarter-size allowance too small to afford its minimum ticket. Removing the
brakes lost still more: the original CORE's 2024 unbraked control lost roughly
Rs 8,400–8,600, so increasing risk was rejected. One-lot sizing reduced losses
but did not fix those negative entries. The later joint iteration changed the
entry to a strong-trend pullback, limited reach, lowered the minimum premium
and shortened the exit. **It did not turn the failed untouched exam into a pass.**

## R3's measured results

These are **current-size normalized, recorded-chain minute-bar experiments**:
NIFTY lot65 and the current native NFO fee schedule in both years. They are not
the rupees historically realizable under the lot sizes/taxes then in force.

| Year | Ordinary net | Adverse net | Ordinary without best day | Adverse without best day | Tickets |
|---|---:|---:|---:|---:|---:|
| 2024, now seen | +2,942.16 | +2,643.17 | +1,629.21 | +1,372.42 | 21 |
| 2025, already seen | +3,386.58 | +3,025.85 | +2,184.26 | +1,888.47 | 21 |

The same-cash E01.1 control, with the same early flat time, entry limits and
brakes, earns +Rs 118.97 / -Rs 4,037.76 in 2024 and -Rs 4,004.08 / -Rs 4,190.85
in 2025. It often stops early under its loss brakes. The earlier unconstrained
53-ticket E01.1 control (-Rs 20,638 ordinary in 2025) is retained separately;
it must not be confused with this finite-cash comparison.

Continuous R3 cash ends at Rs 31,328.74 ordinary / Rs 30,669.02 adverse.
There are 21 winning and 21 losing individual tickets ordinary; 20 and 22
adverse. Trade-level profit factor is 2.11 / 1.97. Fees are Rs 2,079.01 /
Rs 2,078.98. Removing the best session still leaves +Rs 5,015.79 / +Rs 4,398.27.
Sampled liquidation-mark drawdown is Rs 1,751.17 / Rs 1,734.54; these use
modelled close bids and sale fees, not intrabar or broker-equity observations.

The final candidate is positive under ordinary and adverse fills in **22 of
27 registered coarse neighbouring settings**, across both years. The other
five failures remain in the audit. A same-contract/entry/exit-clock friction
check adds 1% plus a tick per side and still earns +Rs 2,513.52 in 2024 and
+Rs 2,902.73 in 2025. This avoids relying solely on favourable stress nonfills.

The severe scenario buys at the next minute's high and sells at its low,
doubling spreads. Its continuous result is **-Rs 3,219.14**, not profitable.
That scenario also changes refusals and later admission paths, so it is an
execution-sensitivity diagnostic, not a mathematical worst-case account bound.
It is a material reason to require observed forward fills.

## Evidence and execution limits

- 52 expiry sessions in 2024 and 53 in 2025, actual option/index/front-future
  bars. Invalid price/volume rows remain excluded and counted; the missing
  2024 future minute is not filled. All 2023 prices remain protected.
- Native fees, whole lots, full-premium reserves and own cash. Ordinary fills
  use the next bar's open plus/minus a frozen spread model. Adverse uses that
  open with twice the spread and an additional max(one tick, 1% premium).
  The separate severe scenario uses the next bar's high/low.
- The order's quantity and limit are decided before the next bar. Missing or
  overpriced execution refuses a fill; future highs/lows never choose a strike
  or increase its size. Volume is a 20% participation proxy, not known depth.
- Stops are sampled-close decisions. The archive does not establish continuous
  stop monitoring or actual bid/ask execution. All R3 ordinary/adverse positions
  closed in the declared model; no assumed settlement inflates those totals.
- 2026's opening-strike files cannot replay R3's full entry choice. SENSEX also
  lacks a suitable full chain here and is **not qualified or enabled**. This is
  not an A+B+C or whole-Sentinel portfolio result. Independent paper results
  must not be added to a claimed account profit.

There is substantial selection risk: both years influenced R3, thousands of
settings were evaluated, only 42 final modelled tickets exist, and a prior clean
exam failed. Stable neighbours and profitable stress cases reduce some concerns
but cannot remove overfitting. The selection-risk motivation is described in
[Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).
No trader-advice page supplies a rule or a profit guarantee.

## What is implemented in Dev

`expiry_e02.py` records a separately funded research shadow. Its flag is
`EXPIRY_E02_SHADOW_ENABLED=false`. State and trades live in
`<DB_PATH>.expiry-e02.db`, tables `e02_state` and `e02_positions`; the operational
ledger and primary expiry store are not written. It sends no messages or
broker orders. The existing scheduler observes the saved archive after the
primary tick. At most one held E02 contract is added to the same quote batch
so it cannot disappear merely by moving outside ATM+/-8; no extra API request.

The forward basis is **SAMPLED_10S_FORWARD**. A valid minute needs at least four
timely fresh index/future observations; twelve consecutive completed bars are
needed for the signal. Native recording starts at 12:59, so this can delay the
first admission until about 13:11. That warmup sensitivity stays positive in
both years, but reduces 2024's adverse ex-best net to roughly Rs 151. It is a
meaningful data-basis limit, not proof of a durable margin of safety.

Forward execution uses current fresh five-level depth and the committed entry
limit. A disabled flag blocks new tickets but keeps open exits running. A stale
source, wrong expiry/lot, missing bid, corrupted cash or unresolved prior-day
position fails closed. Restart does not reset cash, reserve or qualification;
late activation does not fabricate earlier forward trades. Fees and exit policy
are saved at entry. Per-trade realized peaks are used in the paper book; that
sensitivity matches the historical R3 cash results on these inputs.

The current main remains **E01.1**, with A/B and existing shadows unchanged.
The old expiry AST is identical outside the added held-quote plumbing. N11 and
N11T code/settings/capital are untouched. The adapter and flag are Dev only;
Production is not edited or deployed by this task.

## Verification and continuation

The pure paper signal matches the research rule on **39,375 completed bars**,
zero mismatches. R3 native money/exit/controller audit checks **102 position
records**, zero mismatches. The original 106-position baseline parity remains
on record. Focused research/native checks: **39 passed**. The earlier combined
expiry/scheduler run: **172 passed**. Full-engine-suite result and exact command
status are recorded in the completion receipt, not inferred from these counts.
Tests establish mechanics, not trading profitability.

Source/candidate bindings are in
[forward-freeze.json](research/simulation/2026-11-03-expiry-e02/round03/forward-freeze.json).
The original failed freeze `f2b95cd` and every earlier outcome remain immutable.
The code atlas was regenerated. Existing unrelated owner changes are preserved.

Next evidence is forward paper observation of this fixed NIFTY rule, with real
quote/depth coverage, fees, drawdown, ex-best net and at least 20 closed new
episodes before another promotion decision. Sampled-bar versus exchange-bar
differences must be measured. SENSEX needs its own full-chain study. Neither
positive in-sample results nor passing code tests authorize real orders.
Any future deployment flows through GitHub; flag-off is the entry rollback,
while open legs keep their exits. There is no cash refill or hidden reset.
