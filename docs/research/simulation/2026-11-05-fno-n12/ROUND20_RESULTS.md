# Option-wing direction results

The [separate directional arm](ROUND20.md) was frozen at `4a54f48`. It required two actual minute option surfaces on the same dated expiry, option-price parity and balanced wing strikes. The prior-only volatility forecast scaled the market-move and stop distances. The original native controls reproduced, and two focused tests passed for no extrapolation and complete-bar timing.

| Development window | Two usable snapshots | Reached the planner | Additional positions |
|---|---:|---:|---:|
| 2022 partial | 29 | 0 | 0 |
| 2023 | 188 | 0 | 0 |
| 2024 | 176 | 0 | 0 |
| 2025 | 187 | 0 | 0 |
| 2026 available window | 157 | 0 | 0 |
| Total | 737 | 0 | 0 |

**Rejected at the declared bounds.** Only one pair moved beyond the one-volatility-point threshold. It failed the price-move band. Every annual account result matched N11T. The study establishes scarcity of this exact signal. It supplies no evidence of what would happen with a weaker skew or an alternate clock. November 5 had the native 09:45 paper trade open at 10:16, which independently refuses the extra admission. [Observed native positions](round15-17-nov5.json).

Run `round20.py` with `N12_YEAR` from 2022 through 2026. No live pricing, risk authority, account, settings or expiry change follows.
