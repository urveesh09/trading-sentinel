# Round 12. Funded range carry with staged hedge fills

Test a return source independent of the directional N11T entries. Use the shared ₹250,000 account. Only consider one short iron condor per day, at the first normal replay decision from 10:30 through 10:33 if native N11T stays flat with zero entries that day and shared brakes permit entry. Exclude own expiry day and require one or two calendar days until the dated front option expiry. The 09:15–10:29 completed futures range must be directionally flat, with absolute displacement at most a quarter of its range. The last 30 minutes must contract to at most half of the first 45-minute range, and the last close must remain inside the middle half of the full opening range.

Choose both short strikes at least one strike outside the observed range and buy 100-point wings. Require all four strikes within the native ATM ±5 grid, full-lot modeled depth, positive OI and current positive-volume option observations. Buy wings at the following replay decision, then sell shorts at the subsequent decision. Cancel or unwind if quotes or economics do not hold. Require at least ₹1,100 gross credit and at most ₹5,000 in full structure loss, estimated fees and fixed stress. Charge current cash using the actual staged prices. Reserve ₹6,500 width plus the worst initial wing purchase and ₹1,200 fee/friction buffer, with no overlap with another open trade. If active, reserve the book until legs are closed and log the N11T entry opportunity cost as account-level difference.

Cover shorts at ask on the next decision after a stop, target or cutoff. Then sell wings at bid on the following decision. Stop when the debit to close reaches twice the entry credit or the future breaches an inner strike. Target 40% of initial credit. Existing hard-flat priority applies, with coverage required through the staged close. Recompute fees by actual buy/sell side, including failed setup unwind, and add ₹400 per full spread and ₹200 per wing-only unwind. Refuse to qualify a result with unresolved legs. The minute tape uses modeled quotes and displayed size. Neither proves actual executable liquidity. Keep all years as development.

Use exact N11 and N11T reference receipts, one account per year, the original materiality and downside bars, and repeat at doubled friction only for a plausible arm. No short-order authority, runtime use, production change or expiry strategy change. Rollback is to retire the research arm.

## Result

| Development window | N11T | Shared account with range carry | Difference | Settled condors | Qualified range clocks with missing chain |
|---|---:|---:|---:|---:|---:|
| 2022 partial | −₹10,602.29 | −₹11,532.26 | −₹929.97 | 2 | 3 |
| 2023 | −₹11,536.98 | −₹11,536.98 | ₹0.00 | 0 | 3 |
| 2024 | ₹95,040.33 | ₹92,662.06 | −₹2,378.27 | 3 | 0 |
| 2025 | ₹63,478.57 | ₹62,980.72 | −₹497.85 | 2 | 3 |
| 2026 available window | ₹127,762.74 | ₹127,551.52 | −₹211.22 | 1 | 1 |
| Total | ₹264,142.37 | ₹260,125.06 | −₹4,017.31 | 8 | 10 |

**Rejected.** Only eight of 18 quiet opening-range clocks had complete modeled chains. All eight spreads settled. The aggregate was +₹861.25 before fees and added friction, −₹817.31 after fees alone and −₹4,017.31 with the frozen execution stress. The annual worst days matched N11T. The largest annual closed drawdown was 7.10%, compared with 7.09% for N11T. The net differences matched the incremental sleeve's standalone losses. This round did not advance to doubled stress. Five annual receipts preserve the exact staged fills, missed chains and no unresolved positions. The tape may also encode volume corrections, and the frozen native replay clock treats truthy minute volume as current; even the admitted quotes are modeled and cannot establish fills.

The freeze and runner are in `0fd52de`. Run `round12.py` with `N12_YEAR` set separately from 2022 through 2026 in the Dev virtual environment. The runner protects the five dated outputs against overwrites. No November 5 alternative P&L is claimed because this historical round has no complete November 5 lifecycle for the added strategy.
