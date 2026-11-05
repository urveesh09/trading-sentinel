# Opening-compression straddle results

The [cash and execution rules](ROUND16.md) were frozen at `1ec5f90`. Use the original N11 and N11T references and one ₹250,000 development account per window. The runner verifies the original option database hash and the controls. It requires positive actual option-candle volume to support each modeled quote. Three synthetic tests cover completed bars, staged cancellation and cash or fee mechanics.

| Window | Eligible compression clocks | Missing option pair | Refused on price or reserve | Additional trades |
|---|---:|---:|---:|---:|
| 2022 partial | 9 | 0 | 9 | 0 |
| 2023 | 14 | 0 | 14 | 0 |
| 2024 | 4 | 0 | 4 | 0 |
| 2025 | 6 | 0 | 6 | 0 |
| 2026 available window | 7 | 1 | 6 | 0 |
| Total | 40 | 1 | 39 | 0 |

**Rejected for economics at admission.** The 39 available two-leg pairs failed the opening-range price bound, the cash reserve bound or both. The frozen receipt records the combined refusal. There were no staged purchases or unresolved positions. Each year's book metrics remained equal to N11T, totaling ₹264,142.37 over separate yearly accounts. The comparison cannot estimate profit from buying those rejected pairs. On November 5 the recorded singles had already entered before 11:00 and the nearest NIFTY option expiry was November 9. Either gate removes the proposed trade. [Dated expiry and paper reference](round9-nov5.json).

Run `round16.py` with `N12_YEAR` from 2022 through 2026. No runtime, live order, allocation or expiry changes. Retire this hypothesis at the declared bounds.
