# Funded range carry results

The frozen strategy and acceptance checks are in [Round 12](ROUND12.md).

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
