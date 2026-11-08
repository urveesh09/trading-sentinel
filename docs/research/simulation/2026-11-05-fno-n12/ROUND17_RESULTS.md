# Context-specific paper gate results

[Round 17](ROUND17.md) was frozen at `2f1bf16`. Both native references matched their saved economic records in all five windows. Two focused checks verified prior-only dates, distinct-date minimums, outlier handling and fallback. The replay used the same dated option data, costs and account as the controls. All scored windows remain development.

| Window | N11T | Release only | Two-way gate |
|---|---:|---:|---:|
| 2022 partial | −₹10,602.29 | −₹10,602.29 | −₹11,829.76 |
| 2023 | −₹11,536.98 | −₹11,536.98 | −₹11,536.98 |
| 2024 | +₹95,040.33 | +₹95,040.33 | +₹95,040.33 |
| 2025 | +₹63,478.57 | +₹63,478.57 | +₹63,478.57 |
| 2026 available window | +₹127,762.74 | +₹127,762.74 | +₹127,762.74 |
| Sum of separate accounts | +₹264,142.37 | +₹264,142.37 | +₹262,914.90 |

**Rejected.** The release-only rule admitted zero new trades. The two-way gate withheld four signal bars in partial 2022. Five native admissions disappeared across the changed account path, with net ₹1,227.47 of foregone profit. The largest omission was the ₹2,959.47 August 22 winning put. Worst day remained −₹5,640.85 across the full study and peak annual closed drawdown rose from 7.09% to 7.58%. Neither arm reached stress qualification.

The accounting audit found 58 previously admitted trades below the volatility line or with an unknown reading, including none in 2024 or the available 2026 window. Erasing every loss in that group while keeping all other outcomes and sizes fixed would add ₹42,536.72. The original materiality requirement is +₹52,828.47. This is a conditional ceiling for deleting existing losses, with perfect hindsight. Reopening entries or changing account feedback falls outside that bound. The independent one-lot shadow trades under the native hold condition netted +₹11,691.15 in partial 2022, −₹28,755.94 in 2023 and +₹4,359.59 in 2025. These are isolated shadow outcomes. They do not measure released trades under the shared cash and risk path. They explain why indiscriminately removing the brake is unsupported.

On November 5 Production recorded ATR at 1.2412% against 1.0501% usual at 09:30 IST. The actual gate was above its low-volatility line, so either candidate would leave this decision unchanged. Recorded NIFTY singles were +₹4,821.18 and the separate spread +₹2,545.91. This is a gate comparison against the observed book. [Read-only November 5 receipt](round15-17-nov5.json).

Run `round17.py` with `N12_YEAR` from 2022 through 2026. `gate_headroom.py` reproduces the separate bookkeeping diagnostic against the original signed receipts. Both are local Dev research with no runtime authority, configuration, deploy or broker changes.
