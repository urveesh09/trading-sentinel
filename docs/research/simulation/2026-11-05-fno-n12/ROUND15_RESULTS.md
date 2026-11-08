# Confirmed-break reversal results

The [original round](ROUND15.md) was frozen at `14dd844`. The existing N11 and N11T economic tuples matched their saved receipts for all five windows. The candidate and N11T also matched contract, entry and exit clocks and prices, quantity, exit reason and net P&L on every trade. Two synthetic checks verified the exact post-stop bar and rejection of gapped or invalidated evidence.

| Development window | N11T and candidate | New trades | Candidate confirmations |
|---|---:|---:|---:|
| 2022 partial | −₹10,602.29 | 0 | 1 |
| 2023 | −₹11,536.98 | 0 | 0 |
| 2024 | +₹95,040.33 | 0 | 0 |
| 2025 | +₹63,478.57 | 0 | 0 |
| 2026 available window | +₹127,762.74 | 0 | 0 |

**Rejected for opportunity scarcity.** Partial 2022 produced one confirmation and the day-loss budget refused it. No comparison tests profitability of reversals because none filled. There is no justification for weakening the risk cap or the clock on the same result. Underlying stop attribution remains a property of the control. On November 5 the sole losing NIFTY position closed for `time_stop`, while the two wins closed for `profit_lock` and `trail_stop`. The recorded session therefore supplies no qualifying stop for this arm. NIFTY singles were +₹4,821.18 and the separate spread +₹2,545.91.

Run `round15.py` once per `N12_YEAR` with the Dev environment. The committed receipts retain the gate funnel. November 5 reasons were checked from the read-only saved Production export. No broker, runtime, capital, settings or expiry change.
