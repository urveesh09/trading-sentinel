# Fifteen-minute acceptance and rejection results

The [rules](ROUND22.md) were frozen at `a00c554`. The two native references match their original economic tuples for all five windows. Each new arm starts its own ₹250,000 NIFTY account per development window and uses the original dated option data, one-lot planner, modeled bid and ask, broker fees and added friction. The candidate bars require every actual intervening minute before the declared boundary. Both arms retained all refusal and unresolved states. Three signal and two gate-audit checks passed.

| Development window | N11T | Accept 15-minute break | Reject 15-minute break |
|---|---:|---:|---:|
| 2022 partial | −₹10,602.29 | −₹22,307.37 | −₹8,034.58 |
| 2023 | −₹11,536.98 | −₹25,365.72 | −₹12,631.35 |
| 2024 | +₹95,040.33 | +₹54,176.07 | +₹89,854.56 |
| 2025 | +₹63,478.57 | +₹17,375.81 | +₹61,552.93 |
| 2026 available window | +₹127,762.74 | +₹51,487.13 | +₹105,579.71 |
| Sum of separate yearly books | +₹264,142.37 | +₹75,365.92 | +₹236,321.27 |

**Reject both.** Acceptance added 201 trades and 103 underlying-stop exits. The incremental trades themselves lost ₹74,570.87, while changes in the remaining account path lost about ₹114,205.58. The latter includes position occupancy, sizing and shared risk feedback. It is the residual after removing the new trade P&L and does not attribute each displaced trade to a particular gate. The biggest annual residual was about ₹74,082 in 2026. The worst day was −₹6,102.10 and peak annual closed drawdown reached 11.40%, versus −₹5,640.85 and 7.09% on N11T.

Rejection added eight trades and lost ₹6,854.24 on them, with about ₹20,966.86 of additional loss in the rest of the account path. One winning 2022 trade improved that annual book by ₹2,567.71. It gave back that advantage in later windows, including −₹22,183.03 in 2026. Worst day matched N11T and peak annual closed drawdown was 7.33%. Both arms failed materiality, the annual net floor and the paired concentration test. Neither advanced to doubled stress or untouched validation. [Executable gate receipt](round22-gates.json).

On November 5 a native paper position was open at every eligible action clock from 10:15 through 12:30. Both new arms would have been refused on that fixed observed path. Recorded native singles were ₹4,821.18 and the separate regular spread was ₹2,545.91. [Observed gate receipt](round22-nov5.json).

Run `round22.py` once per `N12_YEAR`, then `round22_compare.py` on all five completed receipts. All results are local Dev research. No runtime, broker, authority, rollout, capital or expiry changes.
