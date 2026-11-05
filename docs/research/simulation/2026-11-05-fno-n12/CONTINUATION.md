# November 5 F&O research continuation

## Ordinary SENSEX calendar sleeve

All 132 prior-session exchange files validated for the 66 proposed dates. Each confirms NIFTY's date exclusion and a later SENSEX expiry, with the BSE front future identified. The dated minute archive supplies both contract types on 61 of the 66 dates. The opening and square-off check admits 53 dates, then the continuous-futures check leaves 19 in 2025 and 33 in 2026. The sparse October 19 session had 140 missing minutes, correcting the count printed in the strict freeze notes. The exclusion was set from coverage before scoring that session. All five missing dated tapes and the additional incomplete futures sessions remain in the local data manifest.

| Window | N11 | N11T | Strict calendar and native OI | Strict calendar and prior BSE OI | Change vs N11T |
|---|---:|---:|---:|---:|---:|
| 2025 | ₹53,094.68 | ₹63,478.57 | ₹63,478.57 | ₹60,757.05 | −₹2,721.52 |
| 2026 available window | ₹120,551.27 | ₹127,762.74 | ₹127,762.74 | ₹142,059.78 | +₹14,297.04 |

Both NIFTY controls reproduced each frozen trade. A single cash ledger records any difference in later NIFTY sizing. The 2026 improvement includes ₹11,994.78 directly from SENSEX and ₹2,302.26 of NIFTY cash-path effects. There were three SENSEX closes in 2025 and 11 in 2026, all one lot and no unresolved positions. Worst day and annual closed drawdown matched N11T in both years.

Native OI refused all 95 planner checks. The archived SENSEX option tape has zero in the OI field for all 557,063 rows in 2026 and 326,686 of 339,570 in 2025. The separate lagged-OI rule uses the last official BSE closing OI for the same contract only when the observation has zero OI. It keeps the normal modeled quote age and volume conditions. In three archive sessions, 17,387 actual quote observations passed both OI rules and three passed only the current OI rule. These are repeated observations and not independent trades. The audit covers the sampled listed strikes, not all possible tape or calendar conditions. [OI audit](round10-oi-audit.json), [2025 replay](round10-2025-base.json), [2026 replay](round10-2026-base.json).

**Rejected.** The increase across the two windows was ₹11,575.51, then −₹8,322.97 after excluding the five best incremental days. The 2025 annual decline also exceeded the ₹2,500 limit. The strategy did not qualify for doubled execution stress. Both historical controls model NIFTY only. No superiority over the incumbent dual-index system follows. The January–October windows are now development evidence. [Public BSE reports](https://www.bseindia.com/markets/marketinfo/bhavcopy), [NSE derivatives reports](https://www.nseindia.com/all-reports-derivatives).

## November 5 and the regular spread

The November 4 exchange files place NIFTY's nearest option expiry on November 9 and SENSEX's on November 5. The sleeve therefore contributes zero extra orders under the observed opening state. The recorded three NIFTY singles net remains ₹4,821.18 and the separate debit spread remains ₹2,545.91. [November 5 receipt](round9-nov5.json).

The spread research helper incorrectly computed entry fees using one lot per leg. Actual structure 38 has three lots, and its ₹193.84 cost now passes full-quantity validation. The Dev source correction is `b4f99ce`. The original source and uncorrected receipt are preserved at `916a0e0`. The rerun has 38 position rows, 28 without exact bound legs, four outside ordinary scope and six with exact identity. All six fail the existing joint-quote gap requirement. On November 5 there is no simultaneous archived quote for both legs between the recorded entry and close, a gap of 19,168.921 seconds. No candidate spread-exit P&L is available. The live settlement remains independently verified by the existing cash ledger. [Initial failure](round11-dr-results.json), [corrected replay](round11-dr-results-v2.json), [gap audit](round11-gap-audit.json).

## Verification and next work

Dev only. No runtime caller of the corrected spread verifier, configuration change, schema change, account change, push or deployment. Production was read only for spread ledger attribution, with HEAD `398d44ad`. The seven focused F&O files passed 176 tests. The atlas was regenerated for the verifier line changes. All study files and receipts were checked for whitespace errors. Keep the ₹15,000 trial separate.

Use the next slice for independent regular-F&O entries with their own exits. Prior matched-clock spread work did not show a gain. A fair spread lifecycle needs both leg prices at each management decision, depth, full reserved loss and shared cash. The ordinary spread manager already requests the exact held tokens together. A research recorder can capture those existing responses with the decision clock and no additional broker request. Before choosing any new exit, require baseline parity on the resulting forward evidence. Historical bar-lifecycle comparisons should use side-of-book fills and a separately tested hedge-first/unwind model. Do not carry sparse completed-trade marks into a whole-account profitability claim.
