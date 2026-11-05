# November 5 F&O and expiry findings

## Decisions

Keep N11T as the regular paper reference. The trend-aware exit is the lead for a prospective paper comparison. It missed the fixed requirement to improve every year. Reject taking half at the first target and adding to one-lot winners on the tested continuation rule. Keep the E03.2 strategy baseline and take the dated-contract fix and diagnostics through the normal promotion process when authorized. The two matched-risk expiry challengers did not establish an edge.

## NIFTY 2022

The read-only Breeze source had NIFTY option candles on 115 dates from June 3 through December 30. One Muhurat session was excluded under the existing method, leaving **114 option dates** in the comparison. There were 145 joint index/futures sessions in the June–December replay calendar. The preregistered 200-option-session threshold was not met. No SENSEX 2022 rows were available in the inspected archive. The local SENSEX ordinary option history starts in 2025, and N11T's lot tolerance is NIFTY-only.

The final ₹6,250 / 1.75× N11T and N11 had the same 28 closed trades on ₹2.5 lakh, normalized 65-unit lots, the existing minute candle spread model, native fees and the fixed execution stress. Both lost **₹10,602.29**. Worst day was **−₹4,410.47**. Largest closed drawdown was **₹17,809.29**. Net excluding the best trade was **−₹15,824.25**. No unresolved trades.

There were zero N11T tolerance additions. On all 28 admitted entries, elevated volatility and a profitable trailing 20-trade paper record never coincided. The 2022 paper record supplied only its own earlier closed observations. Both books are identical on this sample, so the incremental effect is untested. No challenger was fitted to 2022. The older all-books exam and its random-entry verdict were not scored on this partial window.

The history store held 2022 daily bars but lacked sufficient earlier warm-up. 332 daily OHLC bars each for NIFTY and NIFTY BANK, dated September 2020 through December 2021, were archived from Yahoo Finance after the official NSE API returned HTTP 503. The supplemented NIFTY pre-window series had 433 bars. Derivative prices came from the sealed Breeze snapshot. See `nifty-2022-inputs.json`, `nifty-2022-freeze.json` and `nifty-2022-results.json`.

## Regular F&O on the studied years

Each year starts at ₹2.5 lakh. This is a NIFTY single-leg research book with model spreads and stress. 2026 ends October 28. The unchanged N11T arm matched the earlier frozen economics trade for trade in all four years.

| Year | N11T | Trend-aware lock | Bank one lot at target | Confirmed one-lot add |
|---|---:|---:|---:|---:|
| 2023 | −11,536.98 | −11,131.51 | −11,536.98 | −11,536.98 |
| 2024 | +95,040.33 | +95,040.33 | +83,777.84 | +93,554.52 |
| 2025 | +63,478.57 | +65,415.09 | +61,908.33 | +63,478.57 |
| 2026 | +127,762.74 | +129,167.29 | +106,503.74 | +130,350.94 |
| Sum of separate years | +274,744.66 | +278,491.20 | +240,652.93 | +275,847.05 |

Trend reads three consecutive completed five-minute futures buckets. It relaxes the lock when the direction holds and tightens it when price structure turns adverse. The native structural stop, premium backstop and hard-flat order of precedence stay in the replay. Positive incremental net came from seven days and no changed day was worse. Removing the best incremental day leaves +₹2,731.24. The doubled execution-stress run preserved the ₹3,746.54 gain, from ₹209,512.97 to ₹213,259.51. No year had a worse worst day or closed drawdown. Improvement was zero in 2024, 2023 remained negative, and all four years were seen before this study.

Banking reduced realized upside and sometimes changed downstream sizing. The add gained ₹2,588.20 on one 2026 day, lost ₹1,485.81 in 2024, and earned nothing incremental in 2023 or 2025. The larger sum does not survive excluding its best incremental day. Previous WATCH/PREMIUM_LOCK and N11 add studies already found that stricter protection and size can give away more than they earn. Those failures informed the conditional tests here. See the earlier [N11 study](../../../FNO_RESEARCH_N11.md) and [N11T study](../../../FNO_RESEARCH_N11T.md).

## November 5 regular paper replay

The native exit reason, exact timestamp, paper price and P&L were reproduced on all three held NIFTY positions. No N11T extra lot was recorded in Production. The fixed-entry comparison keeps the separately recorded ₹2,545.91 spread close as a reference.

| Rule | Three single legs | With recorded spread held fixed | Difference |
|---|---:|---:|---:|
| N11 / N11T recorded | +4,821.18 | +7,367.09 | 0.00 |
| Trend-aware lock | +5,872.16 | +8,418.07 | +1,050.98 |
| Bank one lot at target | +4,821.18 | +7,367.09 | 0.00 |
| Confirmed one-lot add | +4,498.81 | +7,044.72 | −322.37 |

Trend reduced the first loss by ₹376.28 and improved the two closes by ₹269.23 and ₹405.47. It used the original held bid path for all three exits. The add bought the modeled lot at 13:40 near ₹228 and later sold at ₹224.30. Banking never triggered because the two-lot call did not reach its native target. These are conditional on recorded entries and a paper bid-fill model. No additional admissions or spread lifecycle were simulated. Two older SENSEX held-path controls did not reconcile and were excluded from the paired assessment. Nine earlier reconciled paths had no change under trend or banking.

## E03.2 and matched-risk expiry challengers

Ten afternoon recordings were found. October 6 lacks five-level packets for this study, leaving nine sessions across NIFTY and SENSEX, scored as independent ₹25,000 starts. Dated Kite instrument masters supplied option identity, expiry and lot size. Legacy A's recorded counts and net reconcile on all nine included days. E03.2 was counterfactual on the prior dates, since its main paper activation was later.

| Arm | Closed tickets | Net | Net excluding best day | Worst day |
|---|---:|---:|---:|---:|
| E03.2 with contract fix | 2 | −822.96 | −1,063.75 | −1,063.75 |
| Legacy A with original reserve | 13 | +6,229.26 | +843.03 | −856.42 |
| A at matched reserve, next packet | 8 | −2,042.23 | −2,070.96 | −1,212.41 |
| Same, two packets later | 8 | −1,833.56 | −1,833.56 | −1,088.98 |
| Retest at matched reserve, next packet | 2 | −797.88 | −797.88 | −796.24 |
| Same, two packets later | 2 | −637.00 | −799.24 | −799.24 |

A at its original reserve took greater full-premium exposure per call than E03.2, and its positive score depends heavily on one October 13 session. At matched risk, waiting for a confirmed retest cut the losses but left just two trades and a negative score. On November 5 both matched arms stayed flat. Legacy A bought the 79,300 call at 13:33:20. One lot required ₹2,132.06 versus the E03.2 call ceiling of ₹1,250, and realized ₹1,962.21 on paper. E03.2 passed zero signal checks. Of the 120 in-window checks, 11 were warm-up and 97 failed the efficiency threshold. The other 12 failed the pullback, stretch or futures-confirmation checks. No pricing or fill stage was reached that day.

The sampled replay did reach actual option selection on prior sessions and exposed the contract bug. Production's instrument model has `Contract.name`. The expiry selector and pending fill accessed `Contract.underlying`, which raised an exception. Dev commit `b6b0dbf` fixes both sites, uses real contract fixtures for NIFTY and SENSEX, and records stage counts for E03.2. There are no schema, flag, reserve or rule changes. The earlier quote-pressure, near-money, farther-OTM, and genome trials were read before this work. They motivate the limited confirmation test rather than another broad parameter search. See [expiry structure research](../../../EXPIRY_RESEARCH_E032_STRUCTURE.md) and [E03.2 puts](../../../EXPIRY_RESEARCH_E032_PUTS.md).

## Verification and limits

- Initial expiry replay mistakenly preloaded future packets. Its E03.2 results are invalid and retained. The repaired replay advances one packet at a time and explicitly verifies the day state. See `EXPIRY_CLOCK_CORRECTION.md`.
- The final November 5 receipt used the source at `b6b0dbf`, verified frozen inputs and replayed all 966 expiry packets. The simulation helper reported `EVIDENCE_CHECKS_PASSED` and `verified=true`. The recorded source snapshot is necessary to repeat the helper's source check after later documentation commits. See the [local receipt](_local/final-nov5-receipt/REPORT.md).
- The six focused expiry test files passed 111 tests on final source. The code atlas regenerated with 304 modules. Existing owner document bytes were checked and preserved.
- Production was checked read-only at `398d44ad`. The engine remained healthy with the same start timestamp. Research and the fix are committed locally in Dev. No push, deployment, data download from Breeze, capital change, broker order or message delivery was performed.
