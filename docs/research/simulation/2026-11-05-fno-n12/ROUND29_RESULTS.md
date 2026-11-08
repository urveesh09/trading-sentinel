# Round 29 results — modeled crossing is a minority of the target

The fixed-clock accounting reconciliation completed for all five N11T windows. It preserves each N11T entry, quantity, exit, chronology and wallet result. For each parent and earned child, gross cash reconciled to recorded gross P&L, and gross less the frozen current option charges and separate execution stress reconciled to net P&L within ₹0.002 per parent.

| Window | Parent trades | Ticket clocks | Gross | Modeled option charges | Separate execution stress | Modeled close-to-price crossing |
|---|---:|---:|---:|---:|---:|---:|
| 2022 partial | 28 | 28 | −₹2,704.00 | ₹1,943.29 | ₹5,955.00 | ₹702.00 |
| 2023 | 28 | 29 | −₹3,474.25 | ₹1,902.73 | ₹6,160.00 | ₹578.50 |
| 2024 | 29 | 36 | ₹108,559.75 | ₹3,129.42 | ₹10,390.00 | ₹1,472.25 |
| 2025 | 73 | 74 | ₹87,412.00 | ₹5,968.43 | ₹17,965.00 | ₹2,583.75 |
| 2026 available window | 51 | 57 | ₹149,457.75 | ₹5,280.01 | ₹16,415.00 | ₹2,603.25 |
| Aggregate | 209 | 224 | ₹339,251.25 | ₹18,223.87 | ₹56,885.00 | ₹7,939.75 |

All 224 entry/exit ticket clocks matched the frozen side-price convention against a dated listed contract and its latest archived minute close at or before the clock. All 224 matched closes had positive archived minute volume; no tickets were unmatched and no zero-volume marks occurred. The close is a model reference, not a verified mid or executable fill. This is an accounting attribution, not a new order policy or proof that the modeled crossing could have been avoided.

N11T earned ₹264,142.37 when summing annual results rounded to the nearest paisa. Summing stored trade net first gives ₹264,142.381. The 20% materiality hurdle is about ₹52,828.48. The ₹7,939.75 matched crossing is 15.03% of that hurdle and 2.34% of reconstructed gross. The separate execution stress adds ₹56,885 to modeled costs. Removing the crossing effect alone cannot produce the target improvement at fixed trades and prices.

## November 5 recorded cash

The Nov 5 finished-session export is bound to manifest SHA-256 `8411f16cd034ad7ab5cde936a92c46148ce7ad70effd71bcb2428880d887bfe3`. The saved paper ledger records +₹4,821.18 for regular NIFTY single-leg trades, +₹2,545.91 for the separate defined-risk paper close, and +₹7,367.09 combined regular paper cash. An action-bound bid, ask and quantity receipt was not present for each relevant recorded entry and exit. Therefore Nov 5 price crossing is **unavailable**; the captured quote stream is not substituted for a quote bound to the recorded action. No crossing estimate is assigned.

## Verification and freeze

- Research contract: [ROUND29.md](ROUND29.md); frozen output: [round29-results.json](round29-results.json); freeze: [round29-freeze.json](round29-freeze.json).
- Run under Dev’s Windows engine interpreter from this directory: `C:/Users/Urveesh/Desktop/trading-sentinel/python-engine/winvenv/Scripts/python.exe round29.py` — exit 0. The script verified the frozen source identities, option-cost snapshot and five data/receipt/database manifests; its per-ticket assertions passed. The freeze is commit `747ec226949e6fb8d6ce5297ddc57f345abc8f5f`.
- The input 2022 panel is partial; 2026 is only the available window. Totals are independent annual books, not a unified portfolio outcome. Dev research only; no runtime or Production changes, orders, push or deployment.
