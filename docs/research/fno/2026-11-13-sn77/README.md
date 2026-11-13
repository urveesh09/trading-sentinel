# SN77: selling time value (defined risk) on Gold's quiet days (Nov 13, 2026): NOT PROVEN

**The idea:** on low-ADX days (known before the open), sell the time value buyers overpay.
- **Structures:** iron condors, bull-put and bear-call spreads, 1–3 strikes out of the money, with 1–2 strike wings.
- **Entry:** 09:30–11:00.
- **Exit:** 15:00, a profit target (50/70% of the credit), a stop (1–2× the credit) or the 20% day limit.
- **Pricing:** shorts sold at the bid and covered at the ask, wings the opposite way, charges per leg.
- **Margin proxy:** the maximum loss must fit ₹30k.
- **Grid:** 864 configurations.

**Result (`results-100.json`, `results-0.json`):**

| Stress per leg-lot | Configurations positive every year | Held-out picks (sum) |
|---|---:|---:|
| ₹100 | 0 | −₹1,02,096 |
| ₹0 | 0 | −₹51,496 |

The best by its worst year is a bull-put spread on quiet low-ADX days, which still lost in 3 of 4 years.

**What it teaches:** intraday option prices on non-expiry quiet days are roughly fair. Buying (SN02-B, SN04–SN09) and selling (SN77) both lose to charges and spreads. Gold's empty days have no intraday edge at 1-minute resolution within these costs.
