# Prior-session range reclaim signal count

The signal rule and the four development inputs were committed before counting at `27c4ada`. The script verified its frozen source hashes and the dataset files, opened the four existing Dev snapshots read-only and used only futures signal inputs. The annual count includes at most one signal per regular session.

| Previously observed window | Signals |
|---|---:|
| 2023 | 23 |
| 2024 | 25 |
| 2025 | 20 |
| 2026 through October 28 | 17 |
| Total | 85 |

The total clears the 30-signal prerequisite. There were 42 long and 43 short setups. This is a frequency check. It used no option outcomes, fills, post-signal returns or P&L. The [complete count](prior-range-count.json) records every scoped date, exclusions and the decision time of each signal. A second run reproduced the report exactly.

The next step is a frozen standalone execution test. Establish after-cost expectancy, downside and the effect of the first executable quote before considering competition with native N11T. The existing 2022 A exam and the proposed July–December 2021 candidate holdout are separate. For the first 2021 roll boundary, retain the June and July dated futures on their June overlap, plus daily NIFTY and NIFTY BANK warm-up through June. No untouched prices were read.

Verification used `python prior_range_reclaim.py` twice and the focused Dev pytest set for the candidate signal, paired/shared control, exam and native entry and exit rules. All 55 tests passed. The previous source commit regenerated the atlas to 304 modules. This results commit is Dev research with no runtime, configuration, migration or rollout effect.
