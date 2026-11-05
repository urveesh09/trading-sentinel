# India VIX forecasting results

The [forecast](ROUND18.md) was frozen at `eadf74e`. The runner rehashed the official NSE closes and the five futures databases, selected the dated monthly NIFTY future and excluded own option-expiry days. It scored 775 paired forecasts after the rolling warmup. There were 231 calendar exclusions and three incomplete futures windows. Both forecast models used identical training dates and all current-session data stayed outside the predictors. Two causality tests passed.

| Development window | Forecasts | Realized-only log MSE | With prior implied ratio | Error improvement |
|---|---:|---:|---:|---:|
| 2022 partial | 35 | 0.3945 | 0.3407 | 13.6% |
| 2023 | 192 | 0.3459 | 0.3218 | 7.0% |
| 2024 | 194 | 0.7187 | 0.6135 | 14.6% |
| 2025 | 194 | 0.5078 | 0.4269 | 15.9% |
| 2026 available window | 160 | 0.4989 | 0.3326 | 33.3% |
| All scored dates | 775 | 0.5135 | 0.4242 | 17.4% |

**Passed the forecasting gate.** QLIKE improved in aggregate from −3.9714 to −4.0406, with small deterioration in 2022 and 2023. The model forecasts intraday variation. It supplies neither trade direction nor an expected option return. All dates remain development because prior research has used these periods. [Paired forecasts and outcomes](round18-results.json), [features-only handoff](round18-forecasts.json).

The forecast advanced to the distinct [costed trade decisions](ROUND19.md). November 5 is assessed separately in the [observed-day comparison](ROUND19_NOV5.md). No production, settings, brokerage, exposure or expiry change follows from this result.
