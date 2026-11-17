# Ten F&O research slots · November 17, 2026

**Verdict.** No new rule passes. The most useful result is R6's decision to skip 56 marginal 10:00 orders. That removed ₹38,186 of modeled losses at ₹400 stress. The remaining book earned only ₹610 and depended on one trade worth ₹11,508. After Gold priority it lost ₹1,691. Keep Gold v5 as the baseline.

## Ten results

The net columns are the 2024–26 candidate totals on one ₹15,000 cash-funded order at most per session. ₹205 and ₹400 are extra round-trip stress per lot, on top of modeled spread and charges. All 700 futures sessions enter the denominator, including 201 sessions outside the complete non-expiry input panel. 499 dates could be scored by the widest forecast arm.

| Slot | Net at ₹205 | Net at ₹400 | What the result says |
|---|---:|---:|---|
| R1. Second-month futures | −₹26,898 | −₹41,891 | On 319 matched forecast days, RMSE rose from 25.23 to 25.56 bp and worsened in every year. The second contract contributed no usable 10:00 edge. |
| R2. Signed volume and concentration | −₹44,901 | −₹64,112 | Sign accuracy rose from 45.8% to 49.0%, while RMSE and P&L both worsened. The side proxy derived from bar closes offered no repeatable payoff. |
| R3. Same-clock prior returns | −₹29,924 | −₹48,460 | Forecast correlation improved from −0.055 to +0.048, and the book lost ₹6,011 less than its price control at ₹205. It still lost in every year and underperformed the matched coin at both costs. |
| R4. Opening path shape | −₹46,437 | −₹65,248 | Its RMSE gain was negative in each year. Adding opening path shape lost another ₹10,502 versus its price control at ₹205. |
| R5. Predict collectible rupees directly | −₹28,510 | −₹37,575 | It lost ₹16,927 less than the model trained on futures direction at ₹400, and ₹11,222 more than the matched coin. 57 of 90 orders filled in the model. |
| R6. Cap extreme training outcomes | **+₹4,112** | **+₹610** | 21 of 34 orders filled. All 34 decisions chose the same side as R5. The entire improvement came from abstaining on the other 56 decisions. |
| R7. Choose a 20- or 60-minute hold | −₹449 | −₹6,485 | Chose 27 short holds and 30 long holds. The extra choices cost ₹7,096 versus R6 at ₹400. |
| R8. Choose cheaper time value per unit of delta | −₹8,613 | −₹16,796 | Same R6 signals, 21 fills under either route. The alternative cost ₹17,406 at ₹400. |
| R9. Walk actual quoted depth | — | — | 24 overlapping archive sessions and zero R6 signals. This arm could not price a test entry or validate bar-model fills. |
| R10. Give Gold priority | +₹1,615 | −₹1,691 | 542 sessions clear at decision time. This blocks one R6 decision and leaves 20 modeled fills with no later Gold entry overlapping their held minutes. This is a timing diagnostic before any shared-wallet simulation. |

## Why the small positive fails

- R6 made **₹5.87 per market session** at ₹205 and **₹0.87** at ₹400. The target was ₹154 per session. At the heavier cost its 90% block-bootstrap interval was **−₹33.67 to +₹39.59** per session.
- At ₹400, R6 lost ₹7,992 in 2024 and earned ₹6,146 in 2025 and ₹2,456 in 2026. The 2026 result was one fill. Removing the best day (April 1, 2025) makes the full result **−₹10,897**. R6's improvement against R5 measured fewer losing entries on these dates and leaves confidence in the remaining entries unresolved.
- The order cap was binding on 13 of the 34 R6 decisions. This is a modeled limit-order rule with actual option minute prices and no queue or depth at entry. The costs, stop delay and no-fill accounting are explicit. None of these estimates establishes executable return.
- The Gold control reproduced **−₹15,281 in 2022** and **+₹8,50,883 in 2023–October 2026** at ₹205. R10 uses that replay's decision-time active/pending states and its later entries solely for the overlap count.

## Implication for the next round

Leave R6 as a documented filter hypothesis. A new 10:00 challenger would need a fresh signal source and enough quote-backed fills to show a return without its best trade. The stronger near-term use of the existing recorder is measuring stop costs on Gold at sub-minute resolution. SN460's eight labeled historical exits saw roughly ₹604 per lot of adverse movement before a full bid. More observations can tell whether earlier observable depth and the normal order path could have recovered any of that cost. Preserve existing forward cohorts and the sealed 2023 expiry-chain exam.

## Verification and provenance

- [Plan and prior work](PLAN.md), [frozen inputs](freeze.json), [full results](results.json), [verification receipt](verification.json). Daily fills and failures are retained locally in `_local/daily-receipts.json`.
- Frozen plan `ddf21285`. The first invocation reached the input coverage check and failed on a missing trade-serialization import before emitting a result. Scored source `4acf76ba` corrected that missing import while preserving the rules and gates. The first and completed logs are preserved separately.
- `python -B run.py --self-test` and the full offline run passed. 76 prior ledger state/net parity checks and 2,050 modeled fills across arms and controls reconciled. All modeled entry debits stayed within ₹15,000.
- All dates were already available to earlier research. Each prediction only fits earlier dates. The planned archived quote export had rotated before scoring. The available replacement manifest was frozen before scoring and R9 was restricted to its October 28 cutoff. The protected expiry outcome and the active forward scopes stayed sealed.
- Research files only in Dev. No runtime switches or migration. No orders, deployment or push from this work.
