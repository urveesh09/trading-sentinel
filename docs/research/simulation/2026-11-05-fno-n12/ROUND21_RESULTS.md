# Equal-weight participation results

The [causal direction screen](ROUND21.md) was frozen at `c2c1abe`. It uses 1,447 official paired daily closes and the five sealed NIFTY futures windows, with two focused causality tests. It scored 795 sessions after warmup. Both models used the same preceding observations. Three regular sessions lacked a required futures clock and 231 calendar days were excluded.

| Development window | Forecasts | MSE improvement | Change in sign accuracy | Incremental signed futures points |
|---|---:|---:|---:|---:|
| 2022 partial | 55 | −0.22% | +5.45 pp | +47.60 |
| 2023 | 193 | −1.07% | −2.59 pp | +0.40 |
| 2024 | 194 | −0.51% | +1.55 pp | +391.30 |
| 2025 | 193 | +0.03% | +1.04 pp | +629.40 |
| 2026 available window | 160 | −0.21% | −1.25 pp | −310.00 |
| All scored dates | 795 | −0.37% | +0.13 pp | +758.70 |

**Rejected.** The breadth model had −753.80 signed futures points before any costs. Its relative improvement fell to −400.10 points after removing the five best incremental days. All three declared gates failed. The experiment estimates predictive value over a fixed morning horizon. It does not price an option strategy, qualify an entry or change the November 5 observed comparison. Keep the source for distinct future research without reusing these results as an untouched validation window. [Paired daily evidence](round21-results.json).

Run `round21.py` under the Dev virtual environment. No Production, risk, cash, settings, authority or expiry changes.
