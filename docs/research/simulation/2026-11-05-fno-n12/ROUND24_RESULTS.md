# Round 24 results. The entry mix gained a little

Frozen at `c04da20`. Both controls matched their saved trades in all five windows. The mixed arms had no unresolved position. Three focused tests checked the forecast threshold and scoped rule dispatch.

| Window | N11T | Recovery plus strike fallback | Same entries with conditioned exit |
|---|---:|---:|---:|
| Partial 2022 | −₹10,602 | −₹10,602 | −₹10,602 |
| 2023 | −₹11,537 | −₹12,022 | −₹12,022 |
| 2024 | +₹95,040 | +₹95,040 | +₹95,040 |
| 2025 | +₹63,479 | +₹65,408 | +₹65,408 |
| Available 2026 | +₹127,763 | +₹128,101 | +₹127,543 |
| Total across five ₹250,000 wallets | +₹264,142 | +₹265,925 | +₹265,368 |

The entry mix finished about ₹1,783 higher, or 0.68%. Its worst day remained −₹5,640.85 and maximum closed drawdown remained 7.09%. Eight net extra closes came from the recovery arm in 2023 and 2025, and one 2026 strike fallback improved net by ₹338.16 without raising the annual trade count. The only volatility-conditioned exit lost ₹557.93 against the entry mix. The combined results did not beat the target of ₹316,970.84. Excluding the strongest incremental days left a loss of ₹3,493.73 for the entry mix and ₹4,051.65 for the conditioned arm. Keep the strike fallback as a research component. The concentration and activity leave insufficient support for promotion. [Account gates](round24-gates.json).

**November 5.** Production recorded the N11 volatility gate above its line at 09:30:22 IST, before native entries, so the recovery override had no role. All three logged NIFTY paper refusals cited the daily trade limit. The reconstructed prior-only forecast passed the optional exit gate, but none of the 451 age-eligible recorded looks had the required price and structure. The check gave every positive observed bid the benefit of sufficient depth and freshness. The source recorded ₹4,821.18 of NIFTY singles P&L. There was no mixed-rule change on these recorded observations. This was a check of the recorded refusals and paths. [November 5 receipt](round24-nov5.json).

Use the Dev engine interpreter with `N12_YEAR` set from 2022 through 2026. `pytest -q test_round24.py` tests dispatch. `python round24.py` checks source and dataset hashes, verifies both controls and writes the annual receipt once. `round22_compare.compare` applies the original gates to either arm. `python round24_nov5.py <frozen export>` reproduces the held check. No doubled stress or forward qualification. Research only, with no runtime, account, settings, push or deployment changes.
