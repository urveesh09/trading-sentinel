# Futures shock repair frequency verdict

The fixed rule found **23 opportunities against a required 30**. Retire this configuration at the frequency step. The source, thresholds and input hashes were committed at `57372d0` before the first count. The results describe observed setup frequency and contain no returns or P&L.

| Development window | Scoped sessions | Calendar exclusions | Invalid price clock or empty volume | Signals |
|---|---:|---:|---:|---:|
| 2023 | 245 | 52 | 2 | 9 |
| 2024 | 248 | 52 | 2 | 5 |
| 2025 | 248 | 54 | 1 | 6 |
| 2026 through October 28 | 203 | 43 | 1 | 3 |
| Total | 944 | 201 | 6 | 23 |

The rule produced 12 longs and 11 shorts. Two signal dates overlapped with the 85 prior-range signals and both decision clocks differed. This establishes that the two fixed screens select mostly different dates. It supplies no evidence about profit, fill probability or the direction of any later move. Preserve the result without tuning the volume multiplier or the recovery range on these windows.

Two read-only executions reproduced the same [date and clock report](shock-repair-count.json) after verifying the source and snapshot hashes. Eight focused rule checks passed after renaming the helper that pytest treated as its module setup hook. The wider focused suite passed 102 checks. The atlas indexes 304 modules. No option prices, post-signal returns, or sealed 2021 and 2022 outcomes were evaluated. Dev research only. The separate N012-A and range-reclaim market decisions still depend on their own sealed evidence.
