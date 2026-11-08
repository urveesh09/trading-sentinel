# Rounds 32–35. More delta fit the cash budget and failed the profit screen

The reference remains the regular NIFTY N11T book. All five windows are previously seen development data, with partial 2022 and 2026 through October 28. Each native annual account starts at ₹250,000. These new option results use frozen native admissions and dated minute marks, with modeled bid/ask and adverse allowances. The new P&L figures are parent-trade attributions. The booked earned-child amounts stay separate, and no result assumes a new strategy would repeat the native account path. The ₹15,000 trial remains a separate experiment.

## Credit vertical and directional basis

The 50-point credit vertical selected and priced 67 of 209 native parents. Eighty entries did not meet the flat one-lot condition, 57 failed the risk comparison and five failed the credit condition. There were zero unresolved closes. The 67 replacements earned ₹1,212.25 gross and −₹35,035.06 after charges and friction, versus the same native parents’ +₹25,242.89. The resulting difference was **−₹60,277.95** at ordinary friction and **−₹74,012.95** when doubled. 2023 improved by ₹1,035.82. Large native gains in 2024–2026 outweighed that improvement. The vertical failed the priced entry comparison. [Freeze `aaefc5e`](ROUND32.md), [receipts](round32-results.json).

The cash–futures basis screen produced 793 paired prior-only forecasts. Adding the cash inputs worsened MSE by 1.99%, lowered sign accuracy by 1.64 percentage points and left −784.50 incremental futures points without the five best dates. There was one strong predicted move above the frozen hurdle, versus 20 required. The study stopped before option pricing. [Freeze `2106f65`](ROUND33.md), [receipts](round33-results.json).

## Two nearby lots instead of one

The entry preflight selected 53 cases across all five windows. Median modeled initial delta exposure rose 21.1%, full premium reserve fell 8.4% and estimated stop loss fell 7.9%. Every selected case fit the frozen one-lot cash and loss budget. All 53 priced in both exit arms. The premium guard triggered five early exits across 2023–2025. [Entry freeze `8727f54`](ROUND34.md), [entry receipt](round34-results.json), [exit freeze `1f82433`](ROUND35.md).

| Window | Replacements | Native clock change | Premium guard change |
|---|---:|---:|---:|
| Partial 2022 | 8 | +₹1,629.09 | +₹1,629.09 |
| 2023 | 14 | +₹33.85 | +₹66.29 |
| 2024 | 5 | −₹1,078.13 | −₹2,005.85 |
| 2025 | 21 | −₹808.89 | −₹348.28 |
| Available 2026 | 5 | +₹588.86 | +₹588.86 |
| Aggregate | 53 | +₹364.77 | −₹69.89 |
| Aggregate, doubled friction | 53 | +₹99.77 | −₹334.89 |
| Without five best incremental days |  | −₹6,447.45 | −₹6,882.11 |

Both left the conditional worst day at the native −₹5,640.85. Neither met the ₹10,000 diagnostic prerequisite or survived the concentration check. In partial 2022, three of eight alternatives helped and the median change was −₹47.03. Two winning puts contributed +₹2,125.58 together, more than the full year's improvement. The option selection amplified those winners, while four of five native losers lost more. The result gives no evidence of a broad fix for the partial 2022 failure. The entry geometry is useful as a sizing constraint, with economics still required for any different use. [Exit receipts](round35-results.json).

## November 5 and verification

The first NIFTY singles entry used two lots. Both later one-lot entries overlapped earlier positions, so none qualified for the flat one-lot alternatives. The archive also lacked action-bound quotes for both proposed credit-vertical legs. The basis screen requires exact cash minutes, while the recorded Production cash index had fifteen-minute bars. These checks leave the observed ₹4,821.18 singles result and the separate ₹2,545.91 defined-risk close as the session references. [Observed coverage](ROUND23_RESULTS.md), [paper cash](nov5-capital-results.json).

Ran `pytest -q test_round32.py test_round33.py test_round34.py test_round35.py` in the Dev engine environment, with nine passing tests. The four frozen runners verified source and archive hashes and completed. No arm advanced to shared-wallet or prospective qualification. Dev research only. No runtime, configuration, migration, orders, expiry, push or deployment changes.
