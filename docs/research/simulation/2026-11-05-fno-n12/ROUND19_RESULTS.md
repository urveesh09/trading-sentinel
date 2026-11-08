# Costed India VIX strategy results

The two independent arms were [frozen](ROUND19.md) at `31fbfaf`. Both reference trade records reconciled in all five windows. The forecast inputs exclude realized results. The replays start separate ₹250,000 accounts and use original dated option minutes, modeled bid and ask, native fees and the declared extra costs. All five windows are development.

| Window | N11T | Volatility-scaled trail | Price-screened option pair |
|---|---:|---:|---:|
| 2022 partial | −₹10,602.29 | −₹11,390.52 | −₹10,602.29 |
| 2023 | −₹11,536.98 | −₹11,540.22 | −₹11,536.98 |
| 2024 | +₹95,040.33 | +₹75,817.82 | +₹95,040.33 |
| 2025 | +₹63,478.57 | +₹62,103.22 | +₹63,478.57 |
| 2026 available window | +₹127,762.74 | +₹138,815.32 | +₹127,762.74 |
| Sum of separate windows | +₹264,142.37 | +₹253,805.62 | +₹264,142.37 |

**Reject both rules.** The trail lost ₹10,336.75 versus N11T and violated the annual bar. Worst day remained −₹5,640.85 and the largest annual closed drawdown remained 7.09%. Only nine dates changed and three improved. After removing those three positive incremental days the paired change was approximately −₹21,470.42. The 2024 November 12 put exited at 14:35 after a 1.3% tightening, giving up ₹18,051.52 of the benchmark's net profit. The 2026 January 23 put held to hard flat with a 15.1% wider distance and gained ₹10,782.25. Changes of either sign can materially alter a single trend capture. The aggregate forecast error result did not predict which case would occur.

The option pair produced no approved staged entry. At 326 forecast-covered clocks, 273 exceeded the complete debit reserve, 51 missed the repricing hurdle, and two lacked the exact pair. No cash-risk change or incremental P&L is justified by these refusals. There were no unresolved positions. Neither arm reached doubled stress.

`round19_pair_audit.py` reevaluated the same 273 rejected pairs against the frozen price hurdle without creating new admissions. None would clear it, including at a ₹15,000 full-debit reserve in the paper book. The audit reproduced the native economics and decision funnel. Its standalone cold memo changed only `named_memo_miss` telemetry, which was isolated before the comparison. The cash cap alone did not hide a qualifying pair.

## November 5 observed comparison

Six prior NSE derivatives reports bind dated contracts. The forecast added October 29, November 2 and November 4 futures observations to training. October 30 was missing the full clock and November 3 was NIFTY option expiry. November 5 remained outside training. Forecast annualized intraday volatility was 9.21% with realized data only, 7.89% with India VIX, and the recorded figure was 7.82%.

The held case verified every native exit reason, price, exact clock and cash total on 1,901 management looks. The forecast factor was 0.85628. It changed only the third position's conditional exit, from 14:20:43 at 224.30 to 13:56:03 at 234.45. Conditional net for the three fixed admissions rose from ₹4,821.18 to ₹5,479.67, a difference of ₹658.49. This uses the actual paper bid clock, with no alternate admissions, fills or post-close extension assumed. The recorded defined-risk net was a separate ₹2,545.91. The proposed pair was refused by prior native entry and four days to the dated front expiry. The complete observed-day receipt is [here](round19-nov5-results.json).

Run `round19.py` once per `N12_YEAR`. `round19_nov5.py <read-only-export>` verifies the saved export, previous official calendars, exact held setting digests and its source freeze. Four focused Round 18 and Round 19 tests passed. All changes are local Dev research. No setting, authority, Production or expiry changes.
