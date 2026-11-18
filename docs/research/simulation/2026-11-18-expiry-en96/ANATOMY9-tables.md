# Round 9 tables (rendered from results9.json / anatomy9.json by render9.py)

Rupees after charges, today's lots. Independent sessions = ₹30,000 and the full day room every session; wallet = one continuous ₹30,000 own-cash wallet with brakes and sweep. Development screen on already studied sessions; inference descriptive only.

## 1. Family verdicts

| family | label | reference | cells run | most selected | final pick | stitched wallet ord / adv | reference stitched ord / adv | adv halted days | outer paired adv per session | fallback folds | grid cells beating ref (adv) | grid median gain |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EN96 | INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds) | REF:EN87 | 32/32 | EN96:gate:0002 | reference | 3,730 / 3,900 | 3,659 / 3,769 | 0 | +1.3 | 3 | 26% | -4.8 |
| EN97 | INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds) | REF:EN87 | 18/18 | reference | reference | 3,659 / 3,769 | 3,659 / 3,769 | 0 | +0.0 | 5 | 0% | -5.2 |
| EN98 | INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds) | REF:EN87 | 12/12 | reference | reference | 3,659 / 3,769 | 3,659 / 3,769 | 0 | +0.0 | 5 | 0% | -29.6 |
| EN99 | INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds) | REF:EN87 | 17/29 | reference | reference | 3,659 / 3,769 | 3,659 / 3,769 | 0 | +0.0 | 5 | 0% | -26.1 |
| EN100 | INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds) | REF:EN87_ONE_LOT | 9/9 | EN100:chooser:0005 | reference | 2,631 / 2,123 | 1,864 / 1,461 | 0 | +6.8 | 4 | 88% | +24.6 |
| EN101 | INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds) | REF:EN87 | 18/18 | EN101:continuation:0002 | reference | 3,659 / 3,769 | 3,659 / 3,769 | 0 | +0.0 | 4 | 61% | +3.5 |
| EN102 | INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds) | REF:EN87 | 18/18 | reference | reference | 3,659 / 3,769 | 3,659 / 3,769 | 0 | +0.0 | 5 | 0% | +0.0 |
| EN103 | INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds) | REF:EN87 | 13/13 | reference | reference | 3,659 / 3,769 | 3,659 / 3,769 | 0 | +0.0 | 5 | 0% | -10.6 |
| EN104 | INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds) | REF:EN87 | 18/18 | EN104:lagged_agreement:0004 | reference | 3,659 / 3,769 | 3,659 / 3,769 | 0 | +0.0 | 4 | 50% | +0.1 |
| EN105 | INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds) | REF:EN87 | 0/64 | EN105|s160|100000 | reference | 3,730 / 5,342 | 3,659 / 3,769 | 0 | +16.2 | 3 | 0% | +0.0 |
| EN106 | NO IMPROVEMENT | REF:E032_native | 23/23 | EN106:native:0005 | reference | 2,496 / 1,535 | 2,057 / 1,242 | 5 | +5.0 | 1 | 14% | -35.4 |
| EN107 | INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds) | REF:EN87 | 16/16 | EN107:sources:0009 | reference | 3,659 / 3,769 | 3,659 / 3,769 | 0 | +0.0 | 4 | 6% | -20.9 |
| EN108 | INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds) | REF:EN87 | 18/18 | EN108:timing:0007 | reference | 3,032 / 2,350 | 3,659 / 3,769 | 0 | -27.7 | 3 | 0% | -25.9 |
| EN109 | NO IMPROVEMENT | REF:EN87 | 12/12 | EN109:grade:0008 | reference | 3,576 / 3,715 | 3,659 / 3,769 | 0 | -0.6 | 2 | 0% | -9.2 |
| EN110 | INCONCLUSIVE — selection support (no candidate passed in >=3 of 5 folds) | REF:EN87 | 18/18 | reference | reference | 3,659 / 3,769 | 3,659 / 3,769 | 0 | +0.0 | 5 | 59% | +3.8 |

Champions: none

## EN96: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gate:0001 | lookback_minutes=5, percentile=60, prior_covered_expiries=20 | 6,366 | 5,800 | -4,862 | 31/27 | 2,062 | 5,754 / 5,141 | 0/0 | 2,378 | -0.2 [-19.8, +19.9] | +7 (-27) / −1 (-279, 0W) / Δ0 | cc1fe9ea |
| gate:0002 | lookback_minutes=5, percentile=60, prior_covered_expiries=40 | 6,675 | 6,216 | -4,634 | 29/26 | 2,370 | 6,618 / 6,142 | 0/0 | 2,378 | +1.9 [-32.4, +37.1] | +7 (922) / −3 (361, 1W) / Δ0 | 6642f5ba |
| gate:0003 | lookback_minutes=5, percentile=70, prior_covered_expiries=20 | 6,178 | 5,670 | -4,668 | 30/26 | 1,873 | 5,683 / 5,011 | 0/0 | 2,448 | -0.9 [-20.4, +19.2] | +6 (-215) / −1 (-279, 0W) / Δ0 | 159cd5ee |
| gate:0004 | lookback_minutes=5, percentile=70, prior_covered_expiries=40 | 5,940 | 5,699 | -3,929 | 25/22 | 1,635 | 5,445 / 5,039 | 0/0 | 2,448 | -0.7 [-22.1, +21.1] | +3 (187) / −3 (361, 1W) / Δ0 | 67c7dad1 |
| gate:0005 | lookback_minutes=5, percentile=80, prior_covered_expiries=20 | 5,929 | 5,473 | -4,693 | 28/24 | 1,624 | 4,965 / 5,119 | 0/0 | 2,546 | -1.9 [-24.0, +20.8] | +5 (-533) / −2 (-348, 0W) / Δ0 | c24c8cfc |
| gate:0006 | lookback_minutes=5, percentile=80, prior_covered_expiries=40 | 6,009 | 5,807 | -3,811 | 24/21 | 1,704 | 5,514 / 5,147 | 0/0 | 2,448 | -0.2 [-21.7, +21.9] | +3 (187) / −4 (292, 1W) / Δ0 | 1ac98c7b |
| gate:0007 | lookback_minutes=5, percentile=90, prior_covered_expiries=20 | 3,729 | 4,153 | -3,954 | 21/21 | 353 | 4,007 / 4,318 | 0/0 | 2,448 | -8.6 [-33.7, +17.0] | +1 (-850) / −5 (1,535, 2W) / Δ0 | 4dd9b0ae |
| gate:0008 | lookback_minutes=5, percentile=90, prior_covered_expiries=40 | 3,840 | 4,297 | -3,091 | 20/19 | 465 | 4,119 / 4,479 | 0/0 | 2,448 | -7.8 [-34.2, +19.0] | +0 (0) / −5 (2,274, 2W) / Δ0 | ccd7ffcf |
| gate:0009 | lookback_minutes=10, percentile=60, prior_covered_expiries=20 | 7,983 | 7,417 | -4,544 | 30/27 | 3,678 | 7,057 / 6,525 | 0/0 | 2,378 | +8.0 [-7.4, +23.7] | +5 (1,869) / −0 (0, 0W) / Δ0 | 7e2cf0cb |
| gate:0010 | lookback_minutes=10, percentile=60, prior_covered_expiries=40 | 6,794 | 6,423 | -4,947 | 27/24 | 2,490 | 6,182 / 5,764 | 0/0 | 2,378 | +3.0 [-18.1, +24.5] | +4 (1,320) / −2 (640, 1W) / Δ0 | 4c691fba |
| gate:0011 | lookback_minutes=10, percentile=70, prior_covered_expiries=20 | 6,249 | 5,820 | -5,213 | 28/25 | 1,944 | 5,285 / 5,638 | 0/0 | 2,615 | -0.1 [-21.7, +22.0] | +3 (135) / −0 (0, 0W) / Δ0 | b05e8aaf |
| gate:0012 | lookback_minutes=10, percentile=70, prior_covered_expiries=40 | 7,468 | 7,091 | -4,228 | 26/23 | 3,164 | 6,542 / 6,199 | 0/0 | 2,378 | +6.3 [-12.4, +25.4] | +3 (1,994) / −2 (640, 1W) / Δ0 | 9c40222b |
| gate:0013 | lookback_minutes=10, percentile=80, prior_covered_expiries=20 | 4,996 | 4,632 | -5,213 | 27/25 | 1,527 | 4,033 / 4,450 | 0/0 | 2,615 | -6.1 [-20.3, +8.2] | +2 (-1,118) / −0 (0, 0W) / Δ0 | 87b87347 |
| gate:0014 | lookback_minutes=10, percentile=80, prior_covered_expiries=40 | 6,727 | 6,466 | -4,033 | 24/21 | 2,422 | 5,919 / 5,574 | 0/0 | 2,448 | +3.2 [-15.0, +21.8] | +1 (1,253) / −2 (640, 1W) / Δ0 | 7dd413b5 |
| gate:0015 | lookback_minutes=10, percentile=90, prior_covered_expiries=20 | 3,381 | 3,208 | -4,896 | 24/23 | 147 | 2,698 / 2,517 | 0/0 | 3,037 | -13.4 [-35.7, +8.7] | +1 (-850) / −2 (1,883, 2W) / Δ0 | a41aa245 |
| gate:0016 | lookback_minutes=10, percentile=90, prior_covered_expiries=40 | 3,669 | 3,567 | -4,033 | 22/20 | 435 | 2,999 / 2,970 | 0/0 | 3,167 | -11.5 [-34.1, +10.7] | +0 (0) / −3 (2,445, 2W) / Δ0 | 9c8edab5 |
| gate:0017 | lookback_minutes=15, percentile=60, prior_covered_expiries=20 | 6,438 | 5,950 | -5,407 | 29/26 | 2,133 | 5,356 / 5,768 | 0/0 | 2,615 | +0.6 [-21.1, +22.7] | +4 (323) / −0 (0, 0W) / Δ0 | f09a4f2b |
| gate:0018 | lookback_minutes=15, percentile=60, prior_covered_expiries=40 | 6,915 | 6,597 | -4,228 | 25/22 | 2,611 | 5,989 / 5,704 | 0/0 | 2,378 | +3.8 [-14.3, +22.4] | +2 (1,441) / −2 (640, 1W) / Δ0 | 140595b4 |
| gate:0019 | lookback_minutes=15, percentile=70, prior_covered_expiries=20 | 6,249 | 5,820 | -5,213 | 28/25 | 1,944 | 5,285 / 5,638 | 0/0 | 2,615 | -0.1 [-21.7, +22.0] | +3 (135) / −0 (0, 0W) / Δ0 | b05e8aaf |
| gate:0020 | lookback_minutes=15, percentile=70, prior_covered_expiries=40 | 6,915 | 6,597 | -4,228 | 25/22 | 2,611 | 5,989 / 5,704 | 0/0 | 2,378 | +3.8 [-14.3, +22.4] | +2 (1,441) / −2 (640, 1W) / Δ0 | 140595b4 |
| gate:0021 | lookback_minutes=15, percentile=80, prior_covered_expiries=20 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| gate:0022 | lookback_minutes=15, percentile=80, prior_covered_expiries=40 | 4,921 | 4,755 | -4,033 | 23/20 | 759 | 4,252 / 4,158 | 0/0 | 3,167 | -5.5 [-34.4, +23.3] | +1 (1,253) / −3 (2,445, 2W) / Δ0 | fbb73ccc |
| gate:0023 | lookback_minutes=15, percentile=90, prior_covered_expiries=20 | 1,886 | 1,967 | -4,397 | 20/19 | -1,347 | 1,249 / 1,370 | 0/0 | 3,037 | -19.7 [-46.9, +6.9] | +0 (0) / −5 (4,228, 4W) / Δ0 | 861d3baf |
| gate:0024 | lookback_minutes=15, percentile=90, prior_covered_expiries=40 | 2,432 | 1,074 | -5,221 | 18/17 | -802 | 1,383 / 477 | 0/0 | 2,159 | -24.2 [-50.0, +1.1] | +0 (0) / −7 (3,682, 5W) / Δ0 | b893f6e6 |
| gate:0025 | lookback_minutes=30, percentile=60, prior_covered_expiries=20 | 4,632 | 4,238 | -5,407 | 28/25 | 469 | 3,689 / 4,352 | 0/0 | 3,096 | -8.1 [-38.7, +22.5] | +4 (323) / −1 (1,806, 1W) / Δ0 | 779d2084 |
| gate:0026 | lookback_minutes=30, percentile=60, prior_covered_expiries=40 | 5,110 | 4,885 | -4,228 | 24/21 | 947 | 4,322 / 4,288 | 0/0 | 3,096 | -4.8 [-33.8, +24.1] | +2 (1,441) / −3 (2,445, 2W) / Δ0 | 411936aa |
| gate:0027 | lookback_minutes=30, percentile=70, prior_covered_expiries=20 | 2,503 | 2,830 | -3,747 | 23/21 | -730 | 2,119 / 2,233 | 0/0 | 3,206 | -15.3 [-39.6, +8.8] | +1 (-432) / −3 (3,179, 2W) / Δ0 | 3f512c5f |
| gate:0028 | lookback_minutes=30, percentile=70, prior_covered_expiries=40 | 4,493 | 4,755 | -3,747 | 23/20 | 330 | 4,109 / 4,158 | 0/0 | 3,206 | -5.5 [-34.4, +23.3] | +2 (821) / −4 (2,442, 2W) / Δ0 | 6700997b |
| gate:0029 | lookback_minutes=30, percentile=80, prior_covered_expiries=20 | 2,426 | 2,818 | -3,747 | 22/21 | -808 | 2,217 / 2,221 | 0/0 | 3,037 | -15.3 [-39.7, +8.7] | +1 (-432) / −4 (3,257, 3W) / Δ0 | b16d5d29 |
| gate:0030 | lookback_minutes=30, percentile=80, prior_covered_expiries=40 | 2,542 | 3,122 | -3,747 | 18/17 | -692 | 1,763 / 2,230 | 0/0 | 2,851 | -13.8 [-37.7, +10.2] | +0 (0) / −7 (3,573, 4W) / Δ0 | 6f8155df |
| gate:0031 | lookback_minutes=30, percentile=90, prior_covered_expiries=20 | 2,031 | 2,709 | -3,689 | 17/16 | -1,202 | 1,210 / 1,723 | 0/0 | 2,851 | -15.9 [-42.5, +10.4] | +1 (523) / −9 (4,606, 5W) / Δ0 | 64f14bc0 |
| gate:0032 | lookback_minutes=30, percentile=90, prior_covered_expiries=40 | 4,284 | 3,453 | -2,923 | 16/15 | 1,051 | 3,265 / 2,560 | 0/0 | 1,918 | -12.1 [-37.1, +12.9] | +0 (0) / −9 (1,830, 4W) / Δ0 | 81fdcb70 |
| ctl:sign_only | d*S15 > 0 | 3,428 | 3,281 | -12,163 | 45/41 | -876 | 5,450 / -3,575 | 0/0 | 3,238 | -13.0 [-54.9, +30.4] | +20 (-2,686) / −0 (0, 0W) / Δ0 | fde0b540 |
| ctl:no_gate | = matched E03 | 3,006 | 2,246 | -13,118 | 55/48 | -1,298 | -3,445 / -4,035 | 0/90 | 3,939 | -18.2 [-71.9, +37.3] | +30 (-2,601) / −0 (0, 0W) / Δ-507 | cdbd9644 |
| ctl:raw_crossings | round-8 raw OI crossings | 4,522 | -3,886 | -25,334 | 166/116 | -11,758 | -1,772 / -3,095 | 110/89 | 4,046 | -49.4 [-239.2, +137.6] | +165 (4,445) / −24 (6,036, 11W) / Δ0 | 676dfc21 |
| ctl:unrelated_day | OI from the 20th prior covered session, same minute | -118 | -388 | -1,649 | 4/3 | -1,175 | -118 / -388 | 0/0 | 1,344 | -31.6 [-90.1, +27.2] | +1 (1,057) / −22 (7,290, 11W) / Δ0 | 037fe959 |

**Stage B EN96:** 100: reference (NO_CANDIDATE_PASSED); 120: reference (NO_CANDIDATE_PASSED); 140: reference (NO_CANDIDATE_PASSED); 160: EN96:gate:0002; 180: EN96:gate:0002; 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN96:gate:0009, t 1.2390152839792423, family p 0.71875.

## EN97: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| basket:0001 | half_width=1, anchor=CURRENT_ATM, aggregation=POOLED | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| basket:0002 | half_width=1, anchor=CURRENT_ATM, aggregation=MEDIAN_LEAVE_ONE_PAIR_OUT | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| basket:0003 | half_width=1, anchor=LAG15_ATM, aggregation=POOLED | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| basket:0004 | half_width=1, anchor=LAG15_ATM, aggregation=MEDIAN_LEAVE_ONE_PAIR_OUT | 5,847 | 5,541 | -4,349 | 26/24 | 2,377 | 5,038 / 4,648 | 0/0 | 2,448 | -1.5 [-5.0, +2.0] | +1 (-268) / −0 (0, 0W) / Δ0 | 1a6630be |
| basket:0005 | half_width=1, anchor=FROZEN_1300_ATM, aggregation=POOLED | 4,841 | 4,662 | -1,605 | 21/21 | 1,466 | 5,052 / 4,662 | 0/0 | 2,448 | -6.0 [-32.0, +20.2] | +0 (0) / −4 (1,273, 2W) / Δ0 | ca9a4650 |
| basket:0006 | half_width=1, anchor=FROZEN_1300_ATM, aggregation=MEDIAN_LEAVE_ONE_PAIR_OUT | 4,573 | 4,362 | -1,922 | 22/22 | 1,198 | 4,784 / 4,362 | 0/0 | 2,448 | -7.5 [-33.5, +18.7] | +1 (-268) / −4 (1,273, 2W) / Δ0 | 8174ea81 |
| basket:0007 | half_width=2, anchor=CURRENT_ATM, aggregation=POOLED | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| basket:0008 | half_width=2, anchor=CURRENT_ATM, aggregation=MEDIAN_LEAVE_ONE_PAIR_OUT | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| basket:0009 | half_width=2, anchor=LAG15_ATM, aggregation=POOLED | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| basket:0010 | half_width=2, anchor=LAG15_ATM, aggregation=MEDIAN_LEAVE_ONE_PAIR_OUT | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| basket:0011 | half_width=2, anchor=FROZEN_1300_ATM, aggregation=POOLED | 4,953 | 4,809 | -2,852 | 23/22 | 1,578 | 5,164 / 4,809 | 0/0 | 2,448 | -5.2 [-31.3, +21.0] | +0 (0) / −2 (1,161, 1W) / Δ0 | 92d0a1b3 |
| basket:0012 | half_width=2, anchor=FROZEN_1300_ATM, aggregation=MEDIAN_LEAVE_ONE_PAIR_OUT | 4,953 | 4,809 | -2,852 | 23/22 | 1,578 | 5,164 / 4,809 | 0/0 | 2,448 | -5.2 [-31.3, +21.0] | +0 (0) / −2 (1,161, 1W) / Δ0 | 92d0a1b3 |
| basket:0013 | half_width=3, anchor=CURRENT_ATM, aggregation=POOLED | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| basket:0014 | half_width=3, anchor=CURRENT_ATM, aggregation=MEDIAN_LEAVE_ONE_PAIR_OUT | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| basket:0015 | half_width=3, anchor=LAG15_ATM, aggregation=POOLED | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| basket:0016 | half_width=3, anchor=LAG15_ATM, aggregation=MEDIAN_LEAVE_ONE_PAIR_OUT | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| basket:0017 | half_width=3, anchor=FROZEN_1300_ATM, aggregation=POOLED | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| basket:0018 | half_width=3, anchor=FROZEN_1300_ATM, aggregation=MEDIAN_LEAVE_ONE_PAIR_OUT | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| ctl:lag1_oi | S15 one minute stale, own threshold | 6,017 | 5,743 | -2,917 | 25/23 | 2,547 | 5,208 / 4,851 | 0/0 | 2,448 | -0.5 [-1.7, +0.7] | +1 (-20) / −1 (78, 1W) / Δ0 | 8aa86b53 |

**Stage B EN97:** 100: reference (NO_CANDIDATE_PASSED); 120: reference (NO_CANDIDATE_PASSED); 140: reference (NO_CANDIDATE_PASSED); 160: reference (NO_CANDIDATE_PASSED); 180: reference (NO_CANDIDATE_PASSED); 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN97:basket:0001, t 0.0, family p 1.0.

## EN98: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context:0001 | max_signed_atr_extension=0.5, min_er10=0 | 0 | 0 | 0 | 0/0 | 0 | 0 / 0 | 0/0 | 0 | -29.6 [-83.1, +24.1] | +0 (0) / −25 (6,114, 12W) / Δ0 | dad1a507 |
| context:0002 | max_signed_atr_extension=0.5, min_er10=0.25 | 0 | 0 | 0 | 0/0 | 0 | 0 / 0 | 0/0 | 0 | -29.6 [-83.1, +24.1] | +0 (0) / −25 (6,114, 12W) / Δ0 | dad1a507 |
| context:0003 | max_signed_atr_extension=0.5, min_er10=0.5 | 0 | 0 | 0 | 0/0 | 0 | 0 / 0 | 0/0 | 0 | -29.6 [-83.1, +24.1] | +0 (0) / −25 (6,114, 12W) / Δ0 | dad1a507 |
| context:0004 | max_signed_atr_extension=1, min_er10=0 | 0 | 0 | 0 | 0/0 | 0 | 0 / 0 | 0/0 | 0 | -29.6 [-83.1, +24.1] | +0 (0) / −25 (6,114, 12W) / Δ0 | dad1a507 |
| context:0005 | max_signed_atr_extension=1, min_er10=0.25 | 0 | 0 | 0 | 0/0 | 0 | 0 / 0 | 0/0 | 0 | -29.6 [-83.1, +24.1] | +0 (0) / −25 (6,114, 12W) / Δ0 | dad1a507 |
| context:0006 | max_signed_atr_extension=1, min_er10=0.5 | 0 | 0 | 0 | 0/0 | 0 | 0 / 0 | 0/0 | 0 | -29.6 [-83.1, +24.1] | +0 (0) / −25 (6,114, 12W) / Δ0 | dad1a507 |
| context:0007 | max_signed_atr_extension=2, min_er10=0 | 0 | 0 | 0 | 0/0 | 0 | 0 / 0 | 0/0 | 0 | -29.6 [-83.1, +24.1] | +0 (0) / −25 (6,114, 12W) / Δ0 | dad1a507 |
| context:0008 | max_signed_atr_extension=2, min_er10=0.25 | 0 | 0 | 0 | 0/0 | 0 | 0 / 0 | 0/0 | 0 | -29.6 [-83.1, +24.1] | +0 (0) / −25 (6,114, 12W) / Δ0 | dad1a507 |
| context:0009 | max_signed_atr_extension=2, min_er10=0.5 | 0 | 0 | 0 | 0/0 | 0 | 0 / 0 | 0/0 | 0 | -29.6 [-83.1, +24.1] | +0 (0) / −25 (6,114, 12W) / Δ0 | dad1a507 |
| context:0010 | max_signed_atr_extension=UNBOUNDED, min_er10=0 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| context:0011 | max_signed_atr_extension=UNBOUNDED, min_er10=0.25 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| context:0012 | max_signed_atr_extension=UNBOUNDED, min_er10=0.5 | 4,309 | 4,129 | -4,033 | 24/22 | 1,075 | 3,639 / 3,532 | 0/0 | 3,167 | -8.7 [-30.0, +12.2] | +0 (0) / −1 (1,806, 1W) / Δ0 | bb50d910 |
| ctl:reversed_ext_0.5 | diagnostic: keep only X > x | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| ctl:reversed_ext_1.0 | diagnostic: keep only X > x | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| ctl:reversed_ext_2.0 | diagnostic: keep only X > x | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |

**Stage B EN98:** 100: reference (NO_CANDIDATE_PASSED); 120: reference (NO_CANDIDATE_PASSED); 140: reference (NO_CANDIDATE_PASSED); 160: reference (NO_CANDIDATE_PASSED); 180: reference (NO_CANDIDATE_PASSED); 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN98:context:0010, t 0.0, family p 1.0.

## EN99: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| immediate:0001 | style=IMMEDIATE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| confirm:0001 | style=CONFIRM, ttl_minutes=1, progress_atr=0.1, ask_multiple=1.04 | 100 | 307 | -1,067 | 3/3 | -713 | 100 / 307 | 0/0 | 1,183 | -28.1 [-79.5, +23.6] | +3 (100) / −25 (6,114, 12W) / Δ0 | bfde0b79 |
| confirm:0002 | style=CONFIRM, ttl_minutes=1, progress_atr=0.1, ask_multiple=1.08 | 100 | 307 | -1,067 | 3/3 | -713 | 100 / 307 | 0/0 | 1,183 | -28.1 [-79.5, +23.6] | +3 (100) / −25 (6,114, 12W) / Δ0 | bfde0b79 |
| confirm:0003 | style=CONFIRM, ttl_minutes=1, progress_atr=0.25, ask_multiple=1.04 | -667 | -765 | -1,067 | 2/2 | -713 | -667 / -765 | 0/0 | 1,183 | -33.5 [-83.1, +16.4] | +2 (-667) / −25 (6,114, 12W) / Δ0 | 8e7ea83e |
| confirm:0004 | style=CONFIRM, ttl_minutes=1, progress_atr=0.25, ask_multiple=1.08 | -667 | -765 | -1,067 | 2/2 | -713 | -667 / -765 | 0/0 | 1,183 | -33.5 [-83.1, +16.4] | +2 (-667) / −25 (6,114, 12W) / Δ0 | 8e7ea83e |
| confirm:0005 | style=CONFIRM, ttl_minutes=3, progress_atr=0.1, ask_multiple=1.04 | 1,013 | 1,084 | -2,073 | 5/5 | -1,129 | 1,013 / 1,084 | 0/0 | 931 | -24.1 [-73.2, +24.9] | +5 (1,013) / −25 (6,114, 12W) / Δ0 | 13787270 |
| confirm:0006 | style=CONFIRM, ttl_minutes=3, progress_atr=0.1, ask_multiple=1.08 | 1,151 | 1,242 | -1,753 | 5/5 | -991 | 1,151 / 1,242 | 0/0 | 843 | -23.3 [-71.7, +24.9] | +5 (1,151) / −25 (6,114, 12W) / Δ0 | 457a2f97 |
| confirm:0007 | style=CONFIRM, ttl_minutes=3, progress_atr=0.25, ask_multiple=1.04 | 2,353 | 1,116 | -1,067 | 4/4 | -667 | 2,353 / 1,116 | 0/0 | 941 | -24.0 [-69.1, +21.3] | +4 (2,353) / −25 (6,114, 12W) / Δ0 | 71c68421 |
| confirm:0008 | style=CONFIRM, ttl_minutes=3, progress_atr=0.25, ask_multiple=1.08 | 2,353 | 2,119 | -1,067 | 4/4 | -667 | 2,353 / 2,119 | 0/0 | 941 | -18.9 [-65.0, +27.2] | +4 (2,353) / −25 (6,114, 12W) / Δ0 | 08c65761 |
| reclaim:0001 | style=PULLBACK_RECLAIM, ttl_minutes=3, pullback_atr=0.25, ask_multiple=1.04 | -461 | -520 | -1,006 | 1/1 | -461 | -461 / -520 | 0/0 | 831 | -32.3 [-87.5, +23.1] | +1 (-461) / −25 (6,114, 12W) / Δ0 | c4499ca5 |
| reclaim:0002 | style=PULLBACK_RECLAIM, ttl_minutes=3, pullback_atr=0.25, ask_multiple=1.08 | -323 | -362 | -687 | 1/1 | -323 | -323 / -362 | 0/0 | 570 | -31.5 [-86.1, +23.3] | +1 (-323) / −25 (6,114, 12W) / Δ0 | 9456134c |
| reclaim:0003 | style=PULLBACK_RECLAIM, ttl_minutes=3, pullback_atr=0.5, ask_multiple=1.04 | 0 | 0 | 0 | 0/0 | 0 | 0 / 0 | 0/0 | 0 | -29.6 [-83.1, +24.1] | +0 (0) / −25 (6,114, 12W) / Δ0 | dad1a507 |
| reclaim:0004 | style=PULLBACK_RECLAIM, ttl_minutes=3, pullback_atr=0.5, ask_multiple=1.08 | 0 | 0 | 0 | 0/0 | 0 | 0 / 0 | 0/0 | 0 | -29.6 [-83.1, +24.1] | +0 (0) / −25 (6,114, 12W) / Δ0 | dad1a507 |
| reclaim:0005 | style=PULLBACK_RECLAIM, ttl_minutes=5, pullback_atr=0.25, ask_multiple=1.04 | 2,392 | 2,151 | -1,631 | 4/4 | -726 | 2,392 / 2,151 | 0/0 | 1,095 | -18.7 [-92.3, +55.3] | +4 (2,392) / −25 (6,114, 12W) / Δ0 | 8b1353c5 |
| reclaim:0006 | style=PULLBACK_RECLAIM, ttl_minutes=5, pullback_atr=0.25, ask_multiple=1.08 | 2,530 | 2,309 | -1,311 | 4/4 | -588 | 2,530 / 2,309 | 0/0 | 834 | -17.9 [-90.9, +55.5] | +4 (2,530) / −25 (6,114, 12W) / Δ0 | 546080c2 |
| reclaim:0007 | style=PULLBACK_RECLAIM, ttl_minutes=5, pullback_atr=0.5, ask_multiple=1.04 | 2,853 | 2,671 | -625 | 3/3 | -264 | 2,853 / 2,671 | 0/0 | 586 | -16.1 [-88.0, +56.3] | +3 (2,853) / −25 (6,114, 12W) / Δ0 | 966f64e6 |
| reclaim:0008 | style=PULLBACK_RECLAIM, ttl_minutes=5, pullback_atr=0.5, ask_multiple=1.08 | 2,853 | 2,671 | -625 | 3/3 | -264 | 2,853 / 2,671 | 0/0 | 586 | -16.1 [-88.0, +56.3] | +3 (2,853) / −25 (6,114, 12W) / Δ0 | 966f64e6 |
| ctl:delay_1 | deterministic delay, no information re-check | 5,139 | 4,612 | -3,343 | 17/17 | 893 | 4,489 / 3,156 | 0/0 | 1,901 | -6.2 [-56.1, +43.9] | +17 (5,139) / −25 (6,114, 12W) / Δ0 | 1dc3f642 |
| ctl:delay_3 | deterministic delay, no information re-check | 6,956 | 6,082 | -2,564 | 15/14 | 2,435 | 6,956 / 5,536 | 0/0 | 1,618 | +1.2 [-68.3, +70.9] | +15 (6,956) / −25 (6,114, 12W) / Δ0 | 5c5b415f |
| ctl:delay_5 | deterministic delay, no information re-check | 2,870 | 1,994 | 11 | 12/12 | -1,751 | 1,112 / 378 | 0/0 | 1,905 | -19.5 [-89.6, +51.5] | +12 (2,870) / −25 (6,114, 12W) / Δ0 | acfa4cf3 |

**Stage B EN99:** 100: reference (NO_CANDIDATE_PASSED); 120: reference (NO_CANDIDATE_PASSED); 140: reference (NO_CANDIDATE_PASSED); 160: reference (NO_CANDIDATE_PASSED); 180: reference (NO_CANDIDATE_PASSED); 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN99:immediate:0001, t 0.0, family p 1.0.

## EN100: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| chooser:0001 | chooser=LEGACY, max_friction_ratio=0.05 | 1,966 | 1,755 | -835 | 11/10 | -273 | 1,966 / 1,755 | 0/0 | 950 | -6.6 [-19.8, +6.6] | +1 (93) / −15 (1,862, 6W) / Δ0 | 76617688 |
| chooser:0002 | chooser=LEGACY, max_friction_ratio=0.1 | 3,782 | 3,129 | -2,581 | 23/21 | 1,202 | 3,782 / 3,129 | 0/0 | 1,365 | +0.3 [-2.2, +2.8] | +1 (143) / −3 (96, 1W) / Δ0 | 9d26400b |
| chooser:0003 | chooser=LEGACY, max_friction_ratio=UNBOUNDED | 3,735 | 3,063 | -2,652 | 25/23 | 1,155 | 3,735 / 3,063 | 0/0 | 1,365 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | c9c0e31b |
| chooser:0004 | chooser=NEAREST_ATM_AFFORDABLE, max_friction_ratio=0.05 | 9,498 | 8,103 | -2,664 | 24/22 | 4,870 | 8,501 / 7,236 | 0/0 | 2,093 | +25.6 [+1.1, +50.9] | +0 (0) / −1 (-163, 0W) / Δ5,600 | 1165bce8 |
| chooser:0005 | chooser=NEAREST_ATM_AFFORDABLE, max_friction_ratio=0.1 | 9,335 | 7,914 | -3,099 | 25/23 | 4,707 | 9,537 / 8,171 | 0/0 | 2,161 | +24.6 [+0.4, +49.8] | +0 (0) / −0 (0, 0W) / Δ5,600 | d8197774 |
| chooser:0006 | chooser=NEAREST_ATM_AFFORDABLE, max_friction_ratio=UNBOUNDED | 9,335 | 7,914 | -3,099 | 25/23 | 4,707 | 9,537 / 8,171 | 0/0 | 2,161 | +24.6 [+0.4, +49.8] | +0 (0) / −0 (0, 0W) / Δ5,600 | d8197774 |
| chooser:0007 | chooser=MIN_FRICTION_OVER_RESERVE, max_friction_ratio=0.05 | 9,498 | 8,103 | -2,664 | 24/22 | 4,870 | 8,501 / 7,236 | 0/0 | 2,093 | +25.6 [+1.1, +50.9] | +0 (0) / −1 (-163, 0W) / Δ5,600 | 1165bce8 |
| chooser:0008 | chooser=MIN_FRICTION_OVER_RESERVE, max_friction_ratio=0.1 | 9,335 | 7,914 | -3,099 | 25/23 | 4,707 | 9,537 / 8,171 | 0/0 | 2,161 | +24.6 [+0.4, +49.8] | +0 (0) / −0 (0, 0W) / Δ5,600 | d8197774 |
| chooser:0009 | chooser=MIN_FRICTION_OVER_RESERVE, max_friction_ratio=UNBOUNDED | 9,335 | 7,914 | -3,099 | 25/23 | 4,707 | 9,537 / 8,171 | 0/0 | 2,161 | +24.6 [+0.4, +49.8] | +0 (0) / −0 (0, 0W) / Δ5,600 | d8197774 |
| ctl:nearest_unrestricted | EN92-style: no legacy admission | 6,103 | 4,517 | -4,072 | 30/26 | 1,475 | 4,684 / 1,360 | 0/0 | 3,235 | +7.4 [-29.6, +45.2] | +5 (-3,700) / −0 (0, 0W) / Δ6,068 | 8a7e2e0c |
| ctl:minfric_unrestricted | EN92-style: no legacy admission | 6,103 | 4,517 | -4,072 | 30/26 | 1,475 | 4,684 / 1,360 | 0/0 | 3,235 | +7.4 [-29.6, +45.2] | +5 (-3,700) / −0 (0, 0W) / Δ6,068 | 8a7e2e0c |

**Stage B EN100:** 100: reference (NO_CANDIDATE_PASSED); 120: reference (NO_CANDIDATE_PASSED); 140: reference (NO_CANDIDATE_PASSED); 160: reference (NO_CANDIDATE_PASSED); 180: EN100:chooser:0005; 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN100:chooser:0004, t 2.4683459470000915, family p 0.046875.

## EN101: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| continuation:0001 | absolute_hold_minutes=12, permission=INFORMATION, activation_net_over_reserve=0 | 7,102 | 6,815 | -3,508 | 25/23 | 2,636 | 7,072 / 6,218 | 0/0 | 2,837 | +4.9 [-20.5, +30.4] | +0 (0) / −0 (0, 0W) / Δ988 | 07b6aa46 |
| continuation:0002 | absolute_hold_minutes=12, permission=INFORMATION, activation_net_over_reserve=0.2 | 8,250 | 7,944 | -3,508 | 25/23 | 3,784 | 7,442 / 7,052 | 0/0 | 2,448 | +10.7 [-4.0, +25.5] | +0 (0) / −0 (0, 0W) / Δ2,136 | 6ebae763 |
| continuation:0003 | absolute_hold_minutes=12, permission=PRICE, activation_net_over_reserve=0 | 7,079 | 6,799 | -3,891 | 25/23 | 2,613 | 6,744 / 6,202 | 0/0 | 2,685 | +4.9 [-17.1, +27.1] | +0 (0) / −0 (0, 0W) / Δ965 | c74db8dc |
| continuation:0004 | absolute_hold_minutes=12, permission=PRICE, activation_net_over_reserve=0.2 | 7,770 | 7,470 | -3,891 | 25/23 | 3,304 | 6,962 / 6,578 | 0/0 | 2,448 | +8.3 [-5.0, +21.8] | +0 (0) / −0 (0, 0W) / Δ1,656 | 122affe7 |
| continuation:0005 | absolute_hold_minutes=12, permission=BOTH, activation_net_over_reserve=0 | 7,079 | 6,799 | -3,891 | 25/23 | 2,613 | 6,744 / 6,202 | 0/0 | 2,685 | +4.9 [-17.1, +27.1] | +0 (0) / −0 (0, 0W) / Δ965 | c74db8dc |
| continuation:0006 | absolute_hold_minutes=12, permission=BOTH, activation_net_over_reserve=0.2 | 7,770 | 7,470 | -3,891 | 25/23 | 3,304 | 6,962 / 6,578 | 0/0 | 2,448 | +8.3 [-5.0, +21.8] | +0 (0) / −0 (0, 0W) / Δ1,656 | 122affe7 |
| continuation:0007 | absolute_hold_minutes=16, permission=INFORMATION, activation_net_over_reserve=0 | 5,830 | 5,563 | -3,950 | 25/23 | 1,654 | 5,800 / 4,966 | 0/0 | 2,837 | -1.4 [-28.9, +26.3] | +0 (0) / −0 (0, 0W) / Δ-284 | 447174b5 |
| continuation:0008 | absolute_hold_minutes=16, permission=INFORMATION, activation_net_over_reserve=0.2 | 6,699 | 6,413 | -3,950 | 25/23 | 2,523 | 5,891 / 5,521 | 0/0 | 2,448 | +2.9 [-14.8, +21.0] | +0 (0) / −0 (0, 0W) / Δ585 | b6644697 |
| continuation:0009 | absolute_hold_minutes=16, permission=PRICE, activation_net_over_reserve=0 | 5,944 | 5,677 | -3,891 | 25/23 | 1,767 | 5,609 / 5,080 | 0/0 | 2,685 | -0.8 [-27.8, +26.5] | +0 (0) / −0 (0, 0W) / Δ-170 | d54bacec |
| continuation:0010 | absolute_hold_minutes=16, permission=PRICE, activation_net_over_reserve=0.2 | 6,823 | 6,530 | -3,891 | 25/23 | 2,646 | 6,014 / 5,638 | 0/0 | 2,448 | +3.5 [-13.4, +20.7] | +0 (0) / −0 (0, 0W) / Δ709 | 1efc2127 |
| continuation:0011 | absolute_hold_minutes=16, permission=BOTH, activation_net_over_reserve=0 | 5,944 | 5,677 | -3,891 | 25/23 | 1,767 | 5,609 / 5,080 | 0/0 | 2,685 | -0.8 [-27.8, +26.5] | +0 (0) / −0 (0, 0W) / Δ-170 | d54bacec |
| continuation:0012 | absolute_hold_minutes=16, permission=BOTH, activation_net_over_reserve=0.2 | 6,823 | 6,530 | -3,891 | 25/23 | 2,646 | 6,014 / 5,638 | 0/0 | 2,448 | +3.5 [-13.4, +20.7] | +0 (0) / −0 (0, 0W) / Δ709 | 1efc2127 |
| continuation:0013 | absolute_hold_minutes=24, permission=INFORMATION, activation_net_over_reserve=0 | 1,795 | 1,573 | -6,058 | 25/23 | -2,382 | 871 / 177 | 0/0 | 2,837 | -21.7 [-79.7, +37.0] | +0 (0) / −0 (0, 0W) / Δ-4,319 | 3891682f |
| continuation:0014 | absolute_hold_minutes=24, permission=INFORMATION, activation_net_over_reserve=0.2 | 4,053 | 3,799 | -6,058 | 25/23 | -124 | 3,244 / 2,906 | 0/0 | 2,448 | -10.4 [-54.8, +34.9] | +0 (0) / −0 (0, 0W) / Δ-2,062 | 09816e98 |
| continuation:0015 | absolute_hold_minutes=24, permission=PRICE, activation_net_over_reserve=0 | 5,743 | 5,476 | -3,891 | 25/23 | 1,566 | 5,408 / 4,879 | 0/0 | 2,685 | -1.9 [-26.9, +23.5] | +0 (0) / −0 (0, 0W) / Δ-372 | d7e91d80 |
| continuation:0016 | absolute_hold_minutes=24, permission=PRICE, activation_net_over_reserve=0.2 | 6,823 | 6,530 | -3,891 | 25/23 | 2,646 | 6,014 / 5,638 | 0/0 | 2,448 | +3.5 [-13.4, +20.7] | +0 (0) / −0 (0, 0W) / Δ709 | 1efc2127 |
| continuation:0017 | absolute_hold_minutes=24, permission=BOTH, activation_net_over_reserve=0 | 5,743 | 5,476 | -3,891 | 25/23 | 1,566 | 5,408 / 4,879 | 0/0 | 2,685 | -1.9 [-26.9, +23.5] | +0 (0) / −0 (0, 0W) / Δ-372 | d7e91d80 |
| continuation:0018 | absolute_hold_minutes=24, permission=BOTH, activation_net_over_reserve=0.2 | 6,823 | 6,530 | -3,891 | 25/23 | 2,646 | 6,014 / 5,638 | 0/0 | 2,448 | +3.5 [-13.4, +20.7] | +0 (0) / −0 (0, 0W) / Δ709 | 1efc2127 |
| ctl:fixed_hold_12 | fixed time exit | 7,961 | 7,766 | -3,538 | 25/23 | 3,495 | 8,185 / 7,357 | 0/0 | 2,837 | +9.8 [-18.2, +37.5] | +0 (0) / −0 (0, 0W) / Δ1,847 | 2d0d8274 |
| ctl:fixed_hold_16 | fixed time exit | 5,415 | 5,716 | -4,173 | 25/23 | 1,238 | 5,787 / 5,151 | 0/0 | 2,902 | -0.6 [-31.9, +30.7] | +0 (0) / −0 (0, 0W) / Δ-699 | f0ba085f |
| ctl:fixed_hold_24 | fixed time exit | 300 | 432 | -7,790 | 25/23 | -3,877 | 378 / -190 | 0/0 | 2,906 | -27.5 [-89.5, +35.2] | +0 (0) / −0 (0, 0W) / Δ-5,815 | 912a7620 |
| ctl:random_extension_12 | equal-activity control: extension probability = mean extensi | 5,735 | 5,724 | -4,189 | 25/23 | 2,265 | 5,179 / 4,909 | 0/0 | 2,448 | -0.6 [-2.0, +0.8] | +0 (0) / −0 (0, 0W) / Δ-380 | 49c92901 |
| ctl:random_extension_16 | equal-activity control: extension probability = mean extensi | 5,511 | 5,909 | -4,306 | 25/23 | 2,042 | 5,105 / 4,971 | 0/0 | 2,513 | +0.3 [-0.5, +1.1] | +0 (0) / −0 (0, 0W) / Δ-603 | 4c1d9b8e |
| ctl:random_extension_24 | equal-activity control: extension probability = mean extensi | 4,937 | 5,471 | -5,249 | 25/23 | 1,467 | 4,913 / 4,825 | 0/0 | 2,516 | -1.9 [-6.2, +2.5] | +0 (0) / −0 (0, 0W) / Δ-1,177 | 6e140644 |

**Stage B EN101:** 100: reference (NO_CANDIDATE_PASSED); 120: reference (NO_CANDIDATE_PASSED); 140: reference (NO_CANDIDATE_PASSED); 160: reference (NO_CANDIDATE_PASSED); 180: EN101:continuation:0002; 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN101:continuation:0002, t 1.7233080917402404, family p 0.3125.

## EN102: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| damage:0001 | opposing_oi_threshold_k=0, consecutive_observations=1, price_damage=NONE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0002 | opposing_oi_threshold_k=0, consecutive_observations=1, price_damage=ENTRY_DAMAGE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0003 | opposing_oi_threshold_k=0, consecutive_observations=1, price_damage=STRUCTURE_DAMAGE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0004 | opposing_oi_threshold_k=0, consecutive_observations=2, price_damage=NONE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0005 | opposing_oi_threshold_k=0, consecutive_observations=2, price_damage=ENTRY_DAMAGE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0006 | opposing_oi_threshold_k=0, consecutive_observations=2, price_damage=STRUCTURE_DAMAGE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0007 | opposing_oi_threshold_k=0, consecutive_observations=3, price_damage=NONE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0008 | opposing_oi_threshold_k=0, consecutive_observations=3, price_damage=ENTRY_DAMAGE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0009 | opposing_oi_threshold_k=0, consecutive_observations=3, price_damage=STRUCTURE_DAMAGE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0010 | opposing_oi_threshold_k=0.5, consecutive_observations=1, price_damage=NONE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0011 | opposing_oi_threshold_k=0.5, consecutive_observations=1, price_damage=ENTRY_DAMAGE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0012 | opposing_oi_threshold_k=0.5, consecutive_observations=1, price_damage=STRUCTURE_DAMAGE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0013 | opposing_oi_threshold_k=0.5, consecutive_observations=2, price_damage=NONE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0014 | opposing_oi_threshold_k=0.5, consecutive_observations=2, price_damage=ENTRY_DAMAGE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0015 | opposing_oi_threshold_k=0.5, consecutive_observations=2, price_damage=STRUCTURE_DAMAGE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0016 | opposing_oi_threshold_k=0.5, consecutive_observations=3, price_damage=NONE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0017 | opposing_oi_threshold_k=0.5, consecutive_observations=3, price_damage=ENTRY_DAMAGE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| damage:0018 | opposing_oi_threshold_k=0.5, consecutive_observations=3, price_damage=STRUCTURE_DAMAGE | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| ctl:damage_only_entry_1 | price damage without OI | 2,387 | 2,065 | -7,312 | 25/23 | -1,049 | 1,589 / 1,008 | 0/0 | 2,168 | -19.2 [-47.1, +9.0] | +0 (0) / −0 (0, 0W) / Δ-3,727 | 07ba5521 |
| ctl:damage_only_entry_2 | price damage without OI | 1,626 | 444 | -7,484 | 25/23 | -1,772 | 503 / 490 | 0/0 | 2,674 | -27.4 [-53.6, -1.4] | +0 (0) / −0 (0, 0W) / Δ-4,488 | 95d79600 |
| ctl:damage_only_entry_3 | price damage without OI | 3,630 | 3,504 | -5,454 | 25/23 | 161 | 2,472 / 3,166 | 0/0 | 2,586 | -11.9 [-42.4, +19.4] | +0 (0) / −0 (0, 0W) / Δ-2,484 | c033c2d1 |
| ctl:damage_only_structure_1 | price damage without OI | 4,132 | 4,196 | -5,862 | 25/23 | 136 | 3,642 / 3,456 | 0/0 | 2,276 | -8.3 [-48.5, +32.6] | +0 (0) / −0 (0, 0W) / Δ-1,982 | 8d60b386 |
| ctl:damage_only_structure_2 | price damage without OI | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| ctl:damage_only_structure_3 | price damage without OI | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| ctl:en94_archived | round-8 EN94 (raw entries + OI exit) | 2,400 | -5,275 | -24,396 | 165/116 | -10,760 | -1,996 / -3,102 | 110/110 | 4,159 | -56.4 [-224.6, +108.8] | +164 (2,322) / −24 (6,036, 11W) / Δ0 | b1466186 |

**Stage B EN102:** 100: reference (NO_CANDIDATE_PASSED); 120: reference (NO_CANDIDATE_PASSED); 140: reference (NO_CANDIDATE_PASSED); 160: reference (NO_CANDIDATE_PASSED); 180: reference (NO_CANDIDATE_PASSED); 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN102:damage:0001, t 0.0, family p 1.0.

## EN103: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| full:0001 | initial_fraction=1 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| staged:0001 | initial_fraction=ONE_THIRD, bid_gain=0.1, oi_permission=STILL_QUALIFIED | 4,221 | 3,939 | -1,973 | 25/23 | 1,570 | 4,221 / 3,939 | 0/0 | 1,771 | -9.7 [-38.0, +19.0] | +0 (0) / −0 (0, 0W) / Δ-1,893 | a697c60c |
| staged:0002 | initial_fraction=ONE_THIRD, bid_gain=0.1, oi_permission=AT_LEAST_ENTRY_STRENGTH | 4,111 | 3,825 | -2,258 | 25/23 | 1,459 | 4,111 / 3,825 | 0/0 | 1,771 | -10.2 [-37.2, +17.0] | +0 (0) / −0 (0, 0W) / Δ-2,003 | ca63b33d |
| staged:0003 | initial_fraction=ONE_THIRD, bid_gain=0.2, oi_permission=STILL_QUALIFIED | 3,784 | 3,585 | -1,973 | 25/23 | 1,204 | 3,784 / 3,585 | 0/0 | 1,477 | -11.4 [-40.0, +17.3] | +0 (0) / −0 (0, 0W) / Δ-2,331 | 837b86fa |
| staged:0004 | initial_fraction=ONE_THIRD, bid_gain=0.2, oi_permission=AT_LEAST_ENTRY_STRENGTH | 3,868 | 3,670 | -2,278 | 25/23 | 1,288 | 3,868 / 3,670 | 0/0 | 1,365 | -11.0 [-38.6, +16.8] | +0 (0) / −0 (0, 0W) / Δ-2,246 | 95c5d04e |
| staged:0005 | initial_fraction=ONE_THIRD, bid_gain=0.3, oi_permission=STILL_QUALIFIED | 3,784 | 3,883 | -1,973 | 25/23 | 1,204 | 3,784 / 3,883 | 0/0 | 1,477 | -9.9 [-38.9, +19.3] | +0 (0) / −0 (0, 0W) / Δ-2,331 | a005ef59 |
| staged:0006 | initial_fraction=ONE_THIRD, bid_gain=0.3, oi_permission=AT_LEAST_ENTRY_STRENGTH | 3,793 | 3,595 | -1,973 | 25/23 | 1,213 | 3,793 / 3,595 | 0/0 | 1,365 | -11.4 [-38.6, +16.0] | +0 (0) / −0 (0, 0W) / Δ-2,321 | da260ed7 |
| staged:0007 | initial_fraction=ONE_HALF, bid_gain=0.1, oi_permission=STILL_QUALIFIED | 4,221 | 3,939 | -1,973 | 25/23 | 1,570 | 4,221 / 3,939 | 0/0 | 1,771 | -9.7 [-38.0, +19.0] | +0 (0) / −0 (0, 0W) / Δ-1,893 | a697c60c |
| staged:0008 | initial_fraction=ONE_HALF, bid_gain=0.1, oi_permission=AT_LEAST_ENTRY_STRENGTH | 4,111 | 3,825 | -2,258 | 25/23 | 1,459 | 4,111 / 3,825 | 0/0 | 1,771 | -10.2 [-37.2, +17.0] | +0 (0) / −0 (0, 0W) / Δ-2,003 | ca63b33d |
| staged:0009 | initial_fraction=ONE_HALF, bid_gain=0.2, oi_permission=STILL_QUALIFIED | 3,784 | 3,585 | -1,973 | 25/23 | 1,204 | 3,784 / 3,585 | 0/0 | 1,477 | -11.4 [-40.0, +17.3] | +0 (0) / −0 (0, 0W) / Δ-2,331 | 837b86fa |
| staged:0010 | initial_fraction=ONE_HALF, bid_gain=0.2, oi_permission=AT_LEAST_ENTRY_STRENGTH | 3,868 | 3,670 | -2,278 | 25/23 | 1,288 | 3,868 / 3,670 | 0/0 | 1,365 | -11.0 [-38.6, +16.8] | +0 (0) / −0 (0, 0W) / Δ-2,246 | 95c5d04e |
| staged:0011 | initial_fraction=ONE_HALF, bid_gain=0.3, oi_permission=STILL_QUALIFIED | 3,784 | 3,883 | -1,973 | 25/23 | 1,204 | 3,784 / 3,883 | 0/0 | 1,477 | -9.9 [-38.9, +19.3] | +0 (0) / −0 (0, 0W) / Δ-2,331 | a005ef59 |
| staged:0012 | initial_fraction=ONE_HALF, bid_gain=0.3, oi_permission=AT_LEAST_ENTRY_STRENGTH | 3,793 | 3,595 | -1,973 | 25/23 | 1,213 | 3,793 / 3,595 | 0/0 | 1,365 | -11.4 [-38.6, +16.0] | +0 (0) / −0 (0, 0W) / Δ-2,321 | da260ed7 |
| ctl:conservative_full | full entry at the staged plan's lot count | 5,232 | 4,241 | -2,804 | 25/23 | 2,074 | 5,217 / 3,896 | 0/0 | 1,890 | -8.1 [-31.7, +15.8] | +0 (0) / −0 (0, 0W) / Δ-883 | 86bc04de |

**Stage B EN103:** 100: reference (NO_CANDIDATE_PASSED); 120: reference (NO_CANDIDATE_PASSED); 140: reference (NO_CANDIDATE_PASSED); 160: reference (NO_CANDIDATE_PASSED); 180: reference (NO_CANDIDATE_PASSED); 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN103:full:0001, t 0.0, family p 1.0.

## EN104: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lagged_agreement:0001 | ttl_minutes=1, direction_validity=E03_STILL_SAME, delayed_oi_percentile=70 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| lagged_agreement:0002 | ttl_minutes=1, direction_validity=E03_STILL_SAME, delayed_oi_percentile=80 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| lagged_agreement:0003 | ttl_minutes=1, direction_validity=E03_STILL_SAME, delayed_oi_percentile=90 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| lagged_agreement:0004 | ttl_minutes=1, direction_validity=STRUCTURE_HOLDS, delayed_oi_percentile=70 | 5,818 | 5,460 | -4,033 | 27/24 | 2,349 | 5,010 / 4,568 | 0/0 | 2,448 | -1.9 [-5.7, +1.8] | +2 (-296) / −0 (0, 0W) / Δ0 | 8b83f337 |
| lagged_agreement:0005 | ttl_minutes=1, direction_validity=STRUCTURE_HOLDS, delayed_oi_percentile=80 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| lagged_agreement:0006 | ttl_minutes=1, direction_validity=STRUCTURE_HOLDS, delayed_oi_percentile=90 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| lagged_agreement:0007 | ttl_minutes=3, direction_validity=E03_STILL_SAME, delayed_oi_percentile=70 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| lagged_agreement:0008 | ttl_minutes=3, direction_validity=E03_STILL_SAME, delayed_oi_percentile=80 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| lagged_agreement:0009 | ttl_minutes=3, direction_validity=E03_STILL_SAME, delayed_oi_percentile=90 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| lagged_agreement:0010 | ttl_minutes=3, direction_validity=STRUCTURE_HOLDS, delayed_oi_percentile=70 | 5,818 | 5,460 | -4,033 | 27/24 | 2,349 | 5,010 / 4,568 | 0/0 | 2,448 | -1.9 [-5.7, +1.8] | +2 (-296) / −0 (0, 0W) / Δ0 | 8b83f337 |
| lagged_agreement:0011 | ttl_minutes=3, direction_validity=STRUCTURE_HOLDS, delayed_oi_percentile=80 | 7,269 | 6,931 | -4,033 | 26/23 | 3,062 | 6,461 / 6,038 | 0/0 | 2,448 | +5.5 [-7.7, +19.1] | +1 (1,155) / −0 (0, 0W) / Δ0 | d6bc7628 |
| lagged_agreement:0012 | ttl_minutes=3, direction_validity=STRUCTURE_HOLDS, delayed_oi_percentile=90 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| lagged_agreement:0013 | ttl_minutes=5, direction_validity=E03_STILL_SAME, delayed_oi_percentile=70 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| lagged_agreement:0014 | ttl_minutes=5, direction_validity=E03_STILL_SAME, delayed_oi_percentile=80 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| lagged_agreement:0015 | ttl_minutes=5, direction_validity=E03_STILL_SAME, delayed_oi_percentile=90 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| lagged_agreement:0016 | ttl_minutes=5, direction_validity=STRUCTURE_HOLDS, delayed_oi_percentile=70 | 6,107 | 5,671 | -4,033 | 28/25 | 2,637 | 5,298 / 4,779 | 0/0 | 2,448 | -0.9 [-5.2, +3.4] | +3 (-7) / −0 (0, 0W) / Δ0 | 9756576d |
| lagged_agreement:0017 | ttl_minutes=5, direction_validity=STRUCTURE_HOLDS, delayed_oi_percentile=80 | 7,558 | 7,141 | -4,033 | 27/24 | 3,351 | 6,749 / 6,249 | 0/0 | 2,448 | +6.6 [-6.6, +20.0] | +2 (1,444) / −0 (0, 0W) / Δ0 | e2116d65 |
| lagged_agreement:0018 | ttl_minutes=5, direction_validity=STRUCTURE_HOLDS, delayed_oi_percentile=90 | 6,403 | 6,051 | -4,033 | 26/24 | 2,933 | 5,594 / 5,159 | 0/0 | 2,448 | +1.1 [-1.4, +3.5] | +1 (289) / −0 (0, 0W) / Δ0 | c854ec78 |
| ctl:unconditional_1 | failed-gate E03 events entered at +ttl | 8,204 | 7,210 | -7,303 | 40/35 | 1,251 | 7,110 / 6,844 | 0/0 | 2,750 | +6.9 [-67.5, +83.4] | +15 (2,090) / −0 (0, 0W) / Δ0 | afc51b87 |
| ctl:unconditional_3 | failed-gate E03 events entered at +ttl | 4,190 | 3,173 | -8,856 | 39/35 | -17 | 3,213 / -2,816 | 0/0 | 3,238 | -13.5 [-42.1, +15.9] | +14 (-1,924) / −0 (0, 0W) / Δ0 | 21d069ef |
| ctl:unconditional_5 | failed-gate E03 events entered at +ttl | 4,561 | 2,687 | -6,947 | 39/35 | 270 | 5,016 / 2,064 | 0/0 | 2,878 | -16.0 [-37.2, +5.4] | +14 (-1,553) / −0 (0, 0W) / Δ0 | 4213f644 |

**Stage B EN104:** 100: reference (NO_CANDIDATE_PASSED); 120: reference (NO_CANDIDATE_PASSED); 140: reference (NO_CANDIDATE_PASSED); 160: EN104:lagged_agreement:0004; 180: reference (NO_CANDIDATE_PASSED); 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN104:lagged_agreement:0017, t 1.1966421442566295, family p 0.75.

## EN106: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| native:0001 | mode=GATE, percentile=60 | 5,850 | 4,680 | -5,726 | 34/31 | 2,318 | 5,850 / 4,680 | 0/0 | 2,806 | -35.1 [-196.6, +127.8] | +1 (-850) / −33 (7,575, 12W) / Δ0 | e2309235 |
| native:0002 | mode=GATE, percentile=70 | 5,661 | 4,550 | -5,531 | 33/30 | 2,129 | 5,661 / 4,550 | 0/0 | 2,806 | -35.7 [-197.0, +126.9] | +1 (-850) / −34 (7,764, 13W) / Δ0 | 4aecc992 |
| native:0003 | mode=GATE, percentile=80 | 5,685 | 4,716 | -4,216 | 30/28 | 2,628 | 5,685 / 4,716 | 0/0 | 1,994 | -34.9 [-200.9, +131.9] | +0 (0) / −36 (8,591, 14W) / Δ0 | ffec074c |
| native:0004 | mode=GATE, percentile=90 | 2,232 | 1,569 | -3,962 | 24/23 | -761 | 2,232 / 1,569 | 0/0 | 2,502 | -50.9 [-227.6, +126.7] | +0 (0) / −42 (12,043, 19W) / Δ0 | e092f2bb |
| native:0005 | mode=VETO, percentile=60 | 13,670 | 11,065 | -12,152 | 63/57 | 47 | -4,123 / -4,036 | 146/164 | 4,181 | -2.6 [-15.9, +10.8] | +0 (0) / −3 (605, 1W) / Δ0 | 1db7fcec |
| native:0006 | mode=VETO, percentile=70 | 14,458 | 11,798 | -12,152 | 65/58 | 835 | -4,123 / -4,036 | 146/164 | 4,181 | +1.1 [-1.4, +3.6] | +0 (0) / −1 (-183, 0W) / Δ0 | 422d4649 |
| native:0007 | mode=VETO, percentile=80 | 14,458 | 11,798 | -12,152 | 65/58 | 835 | -4,123 / -4,036 | 146/164 | 4,181 | +1.1 [-1.4, +3.6] | +0 (0) / −1 (-183, 0W) / Δ0 | 422d4649 |
| native:0008 | mode=VETO, percentile=90 | 14,275 | 11,586 | -12,347 | 66/58 | 652 | -4,123 / -4,036 | 146/164 | 4,181 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | 0871ca04 |
| native:0009 | mode=TILT, percentile=60 | 5,074 | 3,255 | -9,365 | 66/58 | 1,665 | 5,074 / 2,705 | 0/0 | 2,577 | -42.3 [-178.5, +95.5] | +0 (0) / −0 (0, 0W) / Δ-9,202 | 238aff5c |
| native:0010 | mode=TILT, percentile=70 | 4,956 | 3,166 | -9,291 | 66/58 | 1,547 | 4,956 / 2,617 | 0/0 | 2,695 | -42.7 [-178.8, +94.8] | +0 (0) / −0 (0, 0W) / Δ-9,319 | d2a95342 |
| native:0011 | mode=TILT, percentile=80 | 4,495 | 2,748 | -9,089 | 66/58 | 1,562 | 4,495 / 2,198 | 0/0 | 2,695 | -44.9 [-181.7, +93.3] | +0 (0) / −0 (0, 0W) / Δ-9,780 | b18b5b3e |
| native:0012 | mode=TILT, percentile=90 | 4,446 | 2,763 | -8,700 | 67/58 | 1,576 | 4,446 / 2,214 | 0/0 | 2,695 | -44.8 [-179.1, +90.9] | +1 (-250) / −0 (0, 0W) / Δ-9,579 | c2d09869 |
| bridge:0001 | window_end=870, put_mult=1, money=MATCHED | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | -29.2 [-215.9, +158.9] | +0 (0) / −41 (8,406, 15W) / Δ245 | cc00eb67 |
| bridge:0002 | window_end=870, put_mult=1, money=NATIVE | 4,787 | 4,033 | -2,156 | 25/23 | 2,207 | 4,787 / 4,033 | 0/0 | 1,365 | -38.3 [-205.6, +130.1] | +0 (0) / −41 (8,406, 15W) / Δ-1,083 | 8350e8d6 |
| bridge:0003 | window_end=870, put_mult=2, money=MATCHED | 6,978 | 6,665 | -4,033 | 25/23 | 3,492 | 6,169 / 5,773 | 0/0 | 2,448 | -25.0 [-214.3, +165.6] | +0 (0) / −41 (8,406, 15W) / Δ1,108 | a0b7de71 |
| bridge:0004 | window_end=870, put_mult=2, money=NATIVE | 5,869 | 4,882 | -3,583 | 25/23 | 2,812 | 5,869 / 4,882 | 0/0 | 1,777 | -34.0 [-206.3, +139.2] | +0 (0) / −41 (8,406, 15W) / Δ0 | 62dac6ba |
| bridge:0005 | window_end=900, put_mult=1, money=MATCHED | 4,449 | 4,204 | -5,837 | 31/29 | 979 | 4,993 / 4,727 | 0/0 | 2,945 | -37.5 [-217.1, +143.4] | +1 (-635) / −36 (8,591, 14W) / Δ-601 | 22d1ef82 |
| bridge:0006 | window_end=900, put_mult=1, money=NATIVE | 4,890 | 4,218 | -2,789 | 30/28 | 2,310 | 4,890 / 4,218 | 0/0 | 1,602 | -37.4 [-196.1, +122.5] | +0 (0) / −36 (8,591, 14W) / Δ-794 | 263a802e |
| bridge:0007 | window_end=900, put_mult=2, money=MATCHED | 5,312 | 5,029 | -5,837 | 31/29 | 1,827 | 5,856 / 5,552 | 0/0 | 2,945 | -33.3 [-215.8, +150.3] | +1 (-635) / −36 (8,591, 14W) / Δ263 | 12150d43 |
| bridge:0008 | window_end=900, put_mult=2, money=NATIVE | 5,685 | 4,716 | -4,216 | 30/28 | 2,628 | 5,685 / 4,716 | 0/0 | 1,994 | -34.9 [-200.9, +131.9] | +0 (0) / −36 (8,591, 14W) / Δ0 | ffec074c |
| en55:0001 | mode=GATE | 4,372 | 3,749 | 1,004 | 30/29 | 1,573 | 4,372 / 3,749 | 0/0 | 2,045 | -39.8 [-199.9, +121.6] | +1 (-285) / −37 (8,606, 15W) / Δ-1,012 | 3bf482b7 |
| en55:0002 | mode=VETO | 14,085 | 12,016 | 2,188 | 65/58 | 1,966 | 4,366 / 12,533 | 0/0 | 4,006 | +2.2 [-30.6, +35.5] | +1 (-285) / −2 (-167, 1W) / Δ-72 | ae49ab59 |
| en55:0003 | mode=TILT | 2,877 | 1,673 | -3,338 | 68/59 | 20 | 2,877 / 1,541 | 0/0 | 3,754 | -50.3 [-189.5, +90.8] | +3 (-1,007) / −1 (15, 1W) / Δ-10,376 | 750bc9bb |
| ctl:en55_native | EN55 native | 13,165 | 11,056 | 991 | 68/59 | 1,045 | 3,445 / 11,573 | 0/0 | 4,006 | -2.7 [-39.3, +34.7] | +3 (-1,007) / −1 (15, 1W) / Δ-88 | e80d719a |

**Stage B EN106:** 100: EN106:native:0005; 120: EN106:native:0005; 140: EN106:native:0005; 160: EN106:native:0005; 180: reference (NO_CANDIDATE_PASSED); 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN106:native:0006, t 1.0, family p 0.68359375.

## EN107: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sources:0001 | combination=SYN, percentile=70 | 2,920 | 2,225 | -3,612 | 15/13 | 185 | 2,560 / 2,036 | 0/0 | 1,951 | -18.4 [-60.6, +24.4] | +4 (-1,418) / −14 (1,269, 5W) / Δ-507 | 40f047fe |
| sources:0002 | combination=SYN, percentile=80 | 2,541 | 2,037 | -2,472 | 11/10 | 117 | 2,181 / 1,684 | 0/0 | 1,839 | -19.3 [-55.8, +17.7] | +2 (-544) / −16 (3,029, 7W) / Δ0 | d9c3729c |
| sources:0003 | combination=BASIS, percentile=70 | -318 | -850 | -4,162 | 9/8 | -2,929 | -318 / -850 | 0/0 | 1,698 | -34.0 [-82.3, +14.8] | +3 (941) / −19 (7,373, 10W) / Δ0 | 756e35e4 |
| sources:0004 | combination=BASIS, percentile=80 | -2,109 | -2,518 | -4,448 | 7/6 | -3,467 | -1,698 / -2,078 | 0/0 | 2,169 | -42.4 [-94.3, +9.4] | +1 (-850) / −19 (7,373, 10W) / Δ0 | ce5c749f |
| sources:0005 | combination=OI_OR_SYN, percentile=70 | 4,592 | 4,036 | -6,775 | 31/26 | 287 | 3,934 / 4,440 | 0/0 | 2,615 | -9.2 [-33.4, +15.8] | +6 (-1,016) / −0 (0, 0W) / Δ-507 | 632ec648 |
| sources:0006 | combination=OI_OR_SYN, percentile=80 | 5,570 | 5,186 | -4,772 | 27/24 | 2,101 | 4,762 / 4,294 | 0/0 | 2,448 | -3.3 [-8.4, +1.8] | +2 (-544) / −0 (0, 0W) / Δ0 | 4eb69fb0 |
| sources:0007 | combination=OI_AND_SYN, percentile=70 | 4,577 | 4,009 | -2,049 | 12/12 | 1,842 | 4,577 / 4,009 | 0/0 | 1,395 | -9.3 [-51.4, +33.1] | +1 (-268) / −14 (1,269, 5W) / Δ0 | fd95465a |
| sources:0008 | combination=OI_AND_SYN, percentile=80 | 3,085 | 2,692 | -1,733 | 9/9 | 661 | 3,085 / 2,614 | 0/0 | 1,571 | -16.0 [-53.4, +21.9] | +0 (0) / −16 (3,029, 7W) / Δ0 | e7ebe51a |
| sources:0009 | combination=OI_OR_BASIS, percentile=70 | 6,788 | 6,300 | -4,927 | 29/26 | 2,483 | 5,824 / 6,118 | 0/0 | 2,615 | +2.3 [-24.0, +29.3] | +4 (674) / −0 (0, 0W) / Δ0 | a2811e12 |
| sources:0010 | combination=OI_OR_BASIS, percentile=80 | 5,264 | 4,932 | -4,896 | 26/24 | 1,795 | 4,410 / 3,946 | 0/0 | 2,448 | -4.6 [-15.3, +6.2] | +1 (-850) / −0 (0, 0W) / Δ0 | 8a3cf2c5 |
| sources:0011 | combination=OI_AND_BASIS, percentile=70 | -856 | -1,330 | -4,448 | 8/7 | -3,467 | -856 / -1,330 | 0/0 | 1,792 | -36.4 [-84.9, +12.4] | +2 (402) / −19 (7,373, 10W) / Δ0 | 59eaadde |
| sources:0012 | combination=OI_AND_BASIS, percentile=80 | -1,259 | -1,609 | -3,585 | 6/5 | -2,617 | -847 / -1,169 | 0/0 | 2,169 | -37.8 [-91.9, +16.0] | +0 (0) / −19 (7,373, 10W) / Δ0 | 0db886a0 |
| sources:0013 | combination=SYN_OR_BASIS, percentile=70 | 1,244 | 88 | -7,774 | 23/20 | -1,491 | 1,618 / 562 | 0/0 | 2,142 | -29.2 [-63.6, +5.9] | +7 (-477) / −9 (3,886, 4W) / Δ-507 | 3585be0d |
| sources:0014 | combination=SYN_OR_BASIS, percentile=80 | 432 | -481 | -6,920 | 18/16 | -2,303 | 250 / -592 | 0/0 | 2,142 | -32.1 [-64.2, +0.2] | +3 (-1,394) / −10 (4,288, 5W) / Δ0 | eb77e849 |
| sources:0015 | combination=VOTE2, percentile=70 | 2,363 | 1,391 | -6,497 | 19/18 | -373 | 2,430 / 1,557 | 0/0 | 2,142 | -22.6 [-54.9, +10.0] | +3 (135) / −9 (3,886, 4W) / Δ0 | 941d85d0 |
| sources:0016 | combination=VOTE2, percentile=80 | 1,826 | 1,082 | -5,318 | 15/14 | -909 | 1,894 / 1,264 | 0/0 | 1,918 | -24.2 [-57.9, +9.5] | +0 (0) / −10 (4,288, 5W) / Δ0 | 74f328a9 |

**Stage B EN107:** 100: reference (NO_CANDIDATE_PASSED); 120: reference (NO_CANDIDATE_PASSED); 140: reference (NO_CANDIDATE_PASSED); 160: EN107:sources:0009; 180: reference (NO_CANDIDATE_PASSED); 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN107:sources:0009, t 0.23460874480658833, family p 0.91015625.

## EN108: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| timing:0001 | efficiency=0.5, premium_high=20, percentile=70 | -2,334 | -3,021 | -21,822 | 89/70 | -8,819 | -3,753 / -3,911 | 95/95 | 4,052 | -45.0 [-131.7, +43.6] | +69 (-8,180) / −5 (193, 2W) / Δ-75 | 7e841dbd |
| timing:0002 | efficiency=0.5, premium_high=20, percentile=80 | 1 | -617 | -15,966 | 73/58 | -5,272 | -3,959 / -4,113 | 25/25 | 4,091 | -32.8 [-99.6, +35.3] | +52 (-6,662) / −4 (-623, 1W) / Δ-75 | f4285d58 |
| timing:0003 | efficiency=0.5, premium_high=20, percentile=90 | 546 | 932 | -10,965 | 52/42 | -4,727 | -3,973 / -4,016 | 34/50 | 4,125 | -24.9 [-104.8, +55.2] | +35 (-954) / −8 (4,540, 5W) / Δ-75 | 8f64c70d |
| timing:0004 | efficiency=0.5, premium_high=30, percentile=70 | -1,232 | -5,883 | -20,755 | 97/75 | -7,734 | -3,753 / -3,911 | 95/95 | 4,052 | -59.5 [-187.0, +70.7] | +78 (-7,474) / −6 (-627, 2W) / Δ-499 | 5a861515 |
| timing:0005 | efficiency=0.5, premium_high=30, percentile=80 | 1,259 | -3,318 | -15,729 | 80/62 | -4,161 | -4,123 / -4,034 | 25/50 | 4,198 | -46.5 [-143.0, +52.3] | +60 (-5,743) / −5 (-1,444, 1W) / Δ-555 | 9fe83b5b |
| timing:0006 | efficiency=0.5, premium_high=30, percentile=90 | -2,053 | -5,091 | -12,898 | 57/45 | -7,474 | -4,029 / -4,082 | 34/50 | 4,125 | -55.5 [-145.9, +35.5] | +40 (-2,753) / −8 (4,540, 5W) / Δ-875 | e5118a1c |
| timing:0007 | efficiency=0.6, premium_high=20, percentile=70 | 2,919 | 748 | -10,204 | 60/52 | -2,712 | -3,551 / -3,696 | 34/95 | 4,076 | -25.9 [-101.4, +51.2] | +38 (-1,197) / −3 (1,998, 2W) / Δ0 | 7bff7f44 |
| timing:0008 | efficiency=0.6, premium_high=20, percentile=80 | 3,277 | 1,557 | -6,982 | 51/45 | -449 | -1,268 / -1,966 | 0/0 | 3,518 | -21.7 [-76.3, +33.4] | +28 (-1,656) / −2 (1,182, 1W) / Δ0 | 6d919cbf |
| timing:0009 | efficiency=0.6, premium_high=20, percentile=90 | 1,908 | 796 | -5,710 | 40/35 | -1,770 | -2,302 / -2,335 | 0/0 | 3,566 | -25.6 [-72.6, +21.0] | +22 (1,203) / −7 (5,410, 5W) / Δ0 | 09398bfa |
| timing:0010 | efficiency=0.6, premium_high=30, percentile=70 | 2,579 | 556 | -8,935 | 66/55 | -3,052 | -3,551 / -3,696 | 34/95 | 4,076 | -26.8 [-126.0, +74.0] | +45 (-1,933) / −4 (1,178, 2W) / Δ-425 | c96b62df |
| timing:0011 | efficiency=0.6, premium_high=30, percentile=80 | 3,833 | 1,659 | -5,713 | 55/47 | -178 | -1,288 / -2,032 | 0/0 | 3,481 | -21.2 [-95.3, +53.6] | +33 (-1,439) / −3 (361, 1W) / Δ-481 | 3e8b4f03 |
| timing:0012 | efficiency=0.6, premium_high=30, percentile=90 | -359 | -1,863 | -6,489 | 43/36 | -4,329 | 1,713 / -2,401 | 0/0 | 3,036 | -39.1 [-113.0, +34.2] | +25 (-263) / −7 (5,410, 5W) / Δ-800 | 9de7b2fb |
| timing:0013 | efficiency=0.7, premium_high=20, percentile=70 | 6,249 | 5,820 | -5,213 | 28/25 | 1,944 | 5,285 / 5,638 | 0/0 | 2,615 | -0.1 [-21.7, +22.0] | +3 (135) / −0 (0, 0W) / Δ0 | b05e8aaf |
| timing:0014 | efficiency=0.7, premium_high=20, percentile=80 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| timing:0015 | efficiency=0.7, premium_high=20, percentile=90 | 1,886 | 1,967 | -4,397 | 20/19 | -1,347 | 1,249 / 1,370 | 0/0 | 3,037 | -19.7 [-46.9, +6.9] | +0 (0) / −5 (4,228, 4W) / Δ0 | 861d3baf |
| timing:0016 | efficiency=0.7, premium_high=30, percentile=70 | 3,009 | 1,554 | -6,267 | 32/27 | -1,296 | 4,146 / 4,194 | 0/0 | 3,012 | -21.8 [-56.2, +13.0] | +7 (-2,677) / −0 (0, 0W) / Δ-428 | ac438679 |
| timing:0017 | efficiency=0.7, premium_high=30, percentile=80 | 3,192 | 1,935 | -5,087 | 28/24 | -363 | 3,368 / 3,632 | 0/0 | 3,163 | -19.8 [-49.9, +10.2] | +3 (-2,495) / −0 (0, 0W) / Δ-428 | 1e757438 |
| timing:0018 | efficiency=0.7, premium_high=30, percentile=90 | -865 | -1,745 | -4,784 | 22/20 | -3,793 | -80 / 608 | 0/0 | 2,750 | -38.5 [-92.4, +14.6] | +2 (-1,951) / −5 (4,228, 4W) / Δ-800 | 9b40ae07 |
| ctl:ungated_e0.5_p20 | looser E03 without OI | -29,137 | -33,994 | -49,253 | 238/159 | -33,427 | -4,082 / -4,165 | 164/164 | 4,144 | -202.2 [-300.4, -102.1] | +219 (-33,817) / −6 (190, 2W) / Δ-1,244 | 75c3b756 |
| ctl:ungated_e0.5_p30 | looser E03 without OI | -29,359 | -39,681 | -55,742 | 253/163 | -34,076 | -4,077 / -4,007 | 165/165 | 4,086 | -231.1 [-369.0, -90.4] | +235 (-34,414) / −7 (-631, 2W) / Δ-1,690 | bb348581 |
| ctl:ungated_e0.6_p20 | looser E03 without OI | -13,144 | -19,949 | -31,187 | 153/118 | -17,434 | -4,086 / -4,012 | 134/134 | 4,093 | -130.9 [-228.7, -30.5] | +131 (-16,015) / −3 (1,998, 2W) / Δ-1,244 | 0a8ccd16 |
| ctl:ungated_e0.6_p30 | looser E03 without OI | -14,723 | -21,996 | -34,176 | 164/121 | -18,981 | -4,042 / -4,053 | 130/136 | 4,106 | -141.3 [-242.7, -37.6] | +143 (-17,991) / −4 (1,178, 2W) / Δ-1,669 | bc67d291 |
| ctl:ungated_e0.7_p30 | looser E03 without OI | -1,073 | -2,986 | -15,878 | 62/52 | -5,378 | -3,311 / -102 | 0/0 | 3,829 | -44.8 [-99.6, +11.7] | +37 (-6,253) / −0 (0, 0W) / Δ-935 | f814b418 |

**Stage B EN108:** 100: reference (NO_CANDIDATE_PASSED); 120: reference (NO_CANDIDATE_PASSED); 140: EN108:timing:0007; 160: EN108:timing:0011; 180: reference (NO_CANDIDATE_PASSED); 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN108:timing:0013, t 0.01539066504473484, family p 0.96484375.

## EN109: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| grade:0001 | weak_lots=0, agree_lots=1, strong_z=1.5 | 4,180 | 4,066 | -4,651 | 25/23 | 947 | 3,510 / 3,469 | 0/0 | 2,539 | -9.0 [-23.3, +4.8] | +0 (0) / −0 (0, 0W) / Δ-1,934 | 8b75fcd2 |
| grade:0002 | weak_lots=0, agree_lots=1, strong_z=2.0 | 4,488 | 3,529 | -3,662 | 25/23 | 1,559 | 4,636 / 3,788 | 0/0 | 1,918 | -11.7 [-30.0, +6.4] | +0 (0) / −0 (0, 0W) / Δ-1,627 | 42c02cdf |
| grade:0003 | weak_lots=0, agree_lots=2, strong_z=1.5 | 5,376 | 5,135 | -4,033 | 25/23 | 2,143 | 4,568 / 4,243 | 0/0 | 2,448 | -3.6 [-12.4, +5.0] | +0 (0) / −0 (0, 0W) / Δ-738 | a403b2cc |
| grade:0004 | weak_lots=0, agree_lots=2, strong_z=2.0 | 5,016 | 4,329 | -4,033 | 25/23 | 2,070 | 4,800 / 4,243 | 0/0 | 2,216 | -7.7 [-19.7, +4.2] | +0 (0) / −0 (0, 0W) / Δ-1,098 | 54bdd907 |
| grade:0005 | weak_lots=0, agree_lots=3, strong_z=1.5 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| grade:0006 | weak_lots=0, agree_lots=3, strong_z=2.0 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| grade:0007 | weak_lots=1, agree_lots=1, strong_z=1.5 | 3,349 | 2,923 | -7,502 | 38/35 | 116 | 3,051 / 2,600 | 0/0 | 2,770 | -14.8 [-30.8, +1.4] | +13 (-831) / −0 (0, 0W) / Δ-1,934 | 17ca58e0 |
| grade:0008 | weak_lots=1, agree_lots=1, strong_z=2.0 | 3,656 | 2,386 | -6,514 | 38/35 | 728 | 4,345 / 3,214 | 0/0 | 2,770 | -17.5 [-42.2, +7.6] | +13 (-831) / −0 (0, 0W) / Δ-1,627 | 68ee2a25 |
| grade:0009 | weak_lots=1, agree_lots=2, strong_z=1.5 | 4,545 | 3,992 | -6,885 | 38/35 | 1,032 | 4,138 / 3,592 | 0/0 | 2,770 | -9.4 [-28.9, +10.6] | +13 (-831) / −0 (0, 0W) / Δ-738 | 145d2ed7 |
| grade:0010 | weak_lots=1, agree_lots=2, strong_z=2.0 | 4,185 | 3,186 | -6,885 | 38/35 | 766 | 4,370 / 3,592 | 0/0 | 2,770 | -13.5 [-35.7, +9.3] | +13 (-831) / −0 (0, 0W) / Δ-1,098 | 44e95f2d |
| grade:0011 | weak_lots=1, agree_lots=3, strong_z=1.5 | 5,283 | 4,698 | -6,885 | 38/35 | 1,628 | 4,875 / 4,297 | 0/0 | 2,770 | -5.8 [-25.9, +15.0] | +13 (-831) / −0 (0, 0W) / Δ0 | b28b0dc5 |
| grade:0012 | weak_lots=1, agree_lots=3, strong_z=2.0 | 5,283 | 4,698 | -6,885 | 38/35 | 1,628 | 4,875 / 4,297 | 0/0 | 2,770 | -5.8 [-25.9, +15.0] | +13 (-831) / −0 (0, 0W) / Δ0 | b28b0dc5 |

**Stage B EN109:** 100: reference (NO_CANDIDATE_PASSED); 120: reference (NO_CANDIDATE_PASSED); 140: EN109:grade:0008; 160: EN109:grade:0011; 180: EN109:grade:0008; 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN109:grade:0005, t 0.0, family p 1.0.

## EN110: full grid (NIFTY)

| id | settings | ordinary | adverse | catastrophe | parents / expiries | without best two | wallet ord / adv | halted o/a | liq dd | paired adv per session [descr. 95%] | vs ref: added (net) / removed (net, winners) / matched Δ | ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| geometry:0001 | stop=0.25, target=0.6, runner_keep=0.5 | 3,140 | 1,809 | -4,969 | 25/23 | -196 | 3,111 / 1,300 | 0/0 | 2,006 | -20.5 [-43.0, +2.6] | +0 (0) / −0 (0, 0W) / Δ-2,974 | cf99d511 |
| geometry:0002 | stop=0.25, target=0.6, runner_keep=0.7 | 4,016 | 2,675 | -4,969 | 25/23 | 482 | 3,987 / 2,123 | 0/0 | 1,929 | -16.1 [-37.8, +6.1] | +0 (0) / −0 (0, 0W) / Δ-2,098 | f1ea0367 |
| geometry:0003 | stop=0.25, target=1.0, runner_keep=0.5 | 6,870 | 5,659 | -3,725 | 25/23 | 3,401 | 6,841 / 5,659 | 0/0 | 1,929 | -0.9 [-10.9, +9.0] | +0 (0) / −0 (0, 0W) / Δ756 | fc93ae22 |
| geometry:0004 | stop=0.25, target=1.0, runner_keep=0.7 | 7,801 | 6,580 | -3,725 | 25/23 | 3,979 | 7,772 / 6,580 | 0/0 | 1,929 | +3.8 [-10.2, +17.6] | +0 (0) / −0 (0, 0W) / Δ1,687 | 02d8ff83 |
| geometry:0005 | stop=0.25, target=1.5, runner_keep=0.5 | 11,930 | 10,508 | -3,725 | 25/23 | 6,285 | 11,900 / 10,508 | 0/0 | 1,929 | +23.7 [-7.5, +55.1] | +0 (0) / −0 (0, 0W) / Δ5,815 | af021d2a |
| geometry:0006 | stop=0.25, target=1.5, runner_keep=0.7 | 12,153 | 10,728 | -3,725 | 25/23 | 6,478 | 12,124 / 10,728 | 0/0 | 1,929 | +24.8 [-6.8, +56.7] | +0 (0) / −0 (0, 0W) / Δ6,039 | 4f58e747 |
| geometry:0007 | stop=0.35, target=0.6, runner_keep=0.5 | 2,384 | 1,991 | -5,277 | 25/23 | -952 | 1,933 / 1,482 | 0/0 | 2,448 | -19.5 [-39.7, +1.2] | +0 (0) / −0 (0, 0W) / Δ-3,730 | 5887000a |
| geometry:0008 | stop=0.35, target=0.6, runner_keep=0.7 | 3,260 | 2,857 | -5,277 | 25/23 | -274 | 2,893 / 1,887 | 0/0 | 2,448 | -15.1 [-32.8, +3.0] | +0 (0) / −0 (0, 0W) / Δ-2,854 | e2c96be0 |
| geometry:0009 | stop=0.35, target=1.0, runner_keep=0.5 | 6,114 | 5,841 | -4,033 | 25/23 | 2,645 | 5,306 / 4,948 | 0/0 | 2,448 | +0.0 [+0.0, +0.0] | +0 (0) / −0 (0, 0W) / Δ0 | cc00eb67 |
| geometry:0010 | stop=0.35, target=1.0, runner_keep=0.7 | 7,045 | 6,762 | -4,033 | 25/23 | 3,224 | 6,211 / 5,844 | 0/0 | 2,448 | +4.7 [-1.2, +10.5] | +0 (0) / −0 (0, 0W) / Δ931 | 33bad1d1 |
| geometry:0011 | stop=0.35, target=1.5, runner_keep=0.5 | 11,174 | 10,690 | -4,033 | 25/23 | 5,529 | 10,366 / 9,797 | 0/0 | 2,448 | +24.6 [+1.0, +48.5] | +0 (0) / −0 (0, 0W) / Δ5,060 | a1c400a1 |
| geometry:0012 | stop=0.35, target=1.5, runner_keep=0.7 | 11,398 | 10,910 | -4,033 | 25/23 | 5,722 | 10,563 / 9,992 | 0/0 | 2,448 | +25.7 [+1.7, +50.1] | +0 (0) / −0 (0, 0W) / Δ5,284 | 9ca66e3a |
| geometry:0013 | stop=0.5, target=0.6, runner_keep=0.5 | 2,683 | 2,296 | -5,173 | 25/23 | -654 | 1,475 / 2,140 | 0/0 | 2,711 | -18.0 [-46.8, +11.7] | +0 (0) / −0 (0, 0W) / Δ-3,431 | 4357777e |
| geometry:0014 | stop=0.5, target=0.6, runner_keep=0.7 | 3,559 | 3,162 | -5,173 | 25/23 | 24 | 2,109 / 2,545 | 0/0 | 2,534 | -13.6 [-39.5, +13.2] | +0 (0) / −0 (0, 0W) / Δ-2,556 | e14f22af |
| geometry:0015 | stop=0.5, target=1.0, runner_keep=0.5 | 6,413 | 6,146 | -3,929 | 25/23 | 2,943 | 4,962 / 5,176 | 0/0 | 2,534 | +1.5 [-14.3, +17.7] | +0 (0) / −0 (0, 0W) / Δ298 | d36ad5ef |
| geometry:0016 | stop=0.5, target=1.0, runner_keep=0.7 | 7,344 | 7,067 | -3,929 | 25/23 | 3,522 | 5,426 / 5,636 | 0/0 | 2,534 | +6.2 [-8.6, +21.4] | +0 (0) / −0 (0, 0W) / Δ1,229 | 78cfa40e |
| geometry:0017 | stop=0.5, target=1.5, runner_keep=0.5 | 11,472 | 10,994 | -3,929 | 25/23 | 5,828 | 8,918 / 8,934 | 0/0 | 2,534 | +26.2 [+6.6, +46.3] | +0 (0) / −0 (0, 0W) / Δ5,358 | dbd2b443 |
| geometry:0018 | stop=0.5, target=1.5, runner_keep=0.7 | 11,696 | 11,215 | -3,929 | 25/23 | 6,021 | 9,116 / 9,129 | 0/0 | 2,534 | +27.3 [+7.3, +48.0] | +0 (0) / −0 (0, 0W) / Δ5,582 | e9652fe4 |

**Stage B EN110:** 100: reference (NO_CANDIDATE_PASSED); 120: reference (NO_CANDIDATE_PASSED); 140: reference (NO_CANDIDATE_PASSED); 160: reference (NO_CANDIDATE_PASSED); 180: reference (NO_CANDIDATE_PASSED); 197: reference (NO_CANDIDATE_PASSED)

Uncalibrated family max-t (descriptive): best EN110:geometry:0018, t 3.208025999612975, family p 0.0390625.

## EN105: component combinations by boundary

**Boundary 100.** Components: {"signal": null, "context": null, "entry": null, "contract": null, "management": null, "size": null}. Pick: reference (NO_CANDIDATE_PASSED).
- Single-gene mean change (inner adverse / outer adverse): signal: +0.0 / +0.0 (identical pairs 32); context: +0.0 / +0.0 (identical pairs 32); entry: +0.0 / +0.0 (identical pairs 32); contract: +0.0 / +0.0 (identical pairs 32); management: +0.0 / +0.0 (identical pairs 32); size: +0.0 / +0.0 (identical pairs 32)
- Pair interactions (inner adverse): signalxcontext +0.0; signalxentry +0.0; signalxcontract +0.0; signalxmanagement +0.0; signalxsize +0.0; contextxentry +0.0; contextxcontract +0.0; contextxmanagement +0.0; contextxsize +0.0; entryxcontract +0.0; entryxmanagement +0.0; entryxsize +0.0; contractxmanagement +0.0; contractxsize +0.0; managementxsize +0.0
- Genotypes passing the constraints: 0/64; distinct ledgers 1.
- Outer block adverse, genotype 000000: 1,822; top three: 000000 1,822, 000001 1,822, 000010 1,822

**Boundary 120.** Components: {"signal": null, "context": null, "entry": null, "contract": null, "management": null, "size": null}. Pick: reference (NO_CANDIDATE_PASSED).
- Single-gene mean change (inner adverse / outer adverse): signal: +0.0 / +0.0 (identical pairs 32); context: +0.0 / +0.0 (identical pairs 32); entry: +0.0 / +0.0 (identical pairs 32); contract: +0.0 / +0.0 (identical pairs 32); management: +0.0 / +0.0 (identical pairs 32); size: +0.0 / +0.0 (identical pairs 32)
- Pair interactions (inner adverse): signalxcontext +0.0; signalxentry +0.0; signalxcontract +0.0; signalxmanagement +0.0; signalxsize +0.0; contextxentry +0.0; contextxcontract +0.0; contextxmanagement +0.0; contextxsize +0.0; entryxcontract +0.0; entryxmanagement +0.0; entryxsize +0.0; contractxmanagement +0.0; contractxsize +0.0; managementxsize +0.0
- Genotypes passing the constraints: 0/64; distinct ledgers 1.
- Outer block adverse, genotype 000000: 2,880; top three: 000000 2,880, 000001 2,880, 000010 2,880

**Boundary 140.** Components: {"signal": null, "context": null, "entry": null, "contract": null, "management": null, "size": null}. Pick: reference (NO_CANDIDATE_PASSED).
- Single-gene mean change (inner adverse / outer adverse): signal: +0.0 / +0.0 (identical pairs 32); context: +0.0 / +0.0 (identical pairs 32); entry: +0.0 / +0.0 (identical pairs 32); contract: +0.0 / +0.0 (identical pairs 32); management: +0.0 / +0.0 (identical pairs 32); size: +0.0 / +0.0 (identical pairs 32)
- Pair interactions (inner adverse): signalxcontext +0.0; signalxentry +0.0; signalxcontract +0.0; signalxmanagement +0.0; signalxsize +0.0; contextxentry +0.0; contextxcontract +0.0; contextxmanagement +0.0; contextxsize +0.0; entryxcontract +0.0; entryxmanagement +0.0; entryxsize +0.0; contractxmanagement +0.0; contractxsize +0.0; managementxsize +0.0
- Genotypes passing the constraints: 0/64; distinct ledgers 1.
- Outer block adverse, genotype 000000: 731; top three: 000000 731, 000001 731, 000010 731

**Boundary 160.** Components: {"signal": "EN96:gate:0002", "context": null, "entry": null, "contract": null, "management": null, "size": null}. Pick: EN105|s160|100000 (SELECTED).
- Single-gene mean change (inner adverse / outer adverse): signal: +2,491.4 / +0.0 (identical pairs 0); context: +0.0 / +0.0 (identical pairs 32); entry: +0.0 / +0.0 (identical pairs 32); contract: +0.0 / +0.0 (identical pairs 32); management: +0.0 / +0.0 (identical pairs 32); size: +0.0 / +0.0 (identical pairs 32)
- Pair interactions (inner adverse): signalxcontext +0.0; signalxentry +0.0; signalxcontract +0.0; signalxmanagement +0.0; signalxsize +0.0; contextxentry +0.0; contextxcontract +0.0; contextxmanagement +0.0; contextxsize +0.0; entryxcontract +0.0; entryxmanagement +0.0; entryxsize +0.0; contractxmanagement +0.0; contractxsize +0.0; managementxsize +0.0
- Genotypes passing the constraints: 32/64; distinct ledgers 2.
- Outer block adverse, genotype 000000: -244; top three: 000000 -244, 000001 -244, 000010 -244

**Boundary 180.** Components: {"signal": "EN96:gate:0002", "context": null, "entry": null, "contract": "EN100:chooser:0005", "management": "EN101:continuation:0002", "size": null}. Pick: EN105|s180|100110 (SELECTED).
- Single-gene mean change (inner adverse / outer adverse): signal: +3,096.9 / +152.6 (identical pairs 0); context: +0.0 / +0.0 (identical pairs 32); entry: +0.0 / +0.0 (identical pairs 32); contract: -262.7 / +1,420.2 (identical pairs 0); management: +1,873.6 / +0.0 (identical pairs 0); size: +0.0 / +0.0 (identical pairs 32)
- Pair interactions (inner adverse): signalxcontext +0.0; signalxentry +0.0; signalxcontract -333.0; signalxmanagement +1,458.1; signalxsize +0.0; contextxentry +0.0; contextxcontract +0.0; contextxmanagement +0.0; contextxsize +0.0; entryxcontract +0.0; entryxmanagement +0.0; entryxsize +0.0; contractxmanagement -2,264.9; contractxsize +0.0; managementxsize +0.0
- Genotypes passing the constraints: 48/64; distinct ledgers 8.
- Outer block adverse, genotype 000000: -1,419; top three: 100100 154, 100101 154, 100110 154

**Boundary 197.** Components: {"signal": null, "context": null, "entry": null, "contract": null, "management": null, "size": null}. Pick: reference (NO_CANDIDATE_PASSED).
- Single-gene mean change (inner adverse / outer adverse): signal: +0.0 / — (identical pairs 32); context: +0.0 / — (identical pairs 32); entry: +0.0 / — (identical pairs 32); contract: +0.0 / — (identical pairs 32); management: +0.0 / — (identical pairs 32); size: +0.0 / — (identical pairs 32)
- Pair interactions (inner adverse): signalxcontext +0.0; signalxentry +0.0; signalxcontract +0.0; signalxmanagement +0.0; signalxsize +0.0; contextxentry +0.0; contextxcontract +0.0; contextxmanagement +0.0; contextxsize +0.0; entryxcontract +0.0; entryxmanagement +0.0; entryxsize +0.0; contractxmanagement +0.0; contractxsize +0.0; managementxsize +0.0
- Genotypes passing the constraints: 0/64; distinct ledgers 1.

## SENSEX (no Stage B: 63 sessions)

| id | settings | ordinary | adverse | parents / expiries | wallet ord / adv | paired adv vs E03_env |
|---|---|---|---|---|---|---|
| EN107:sources:0001 | combination=SYN, percentile=70 | 0 | 0 | 0/0 | 0 / 0 | -75.3 |
| EN107:sources:0002 | combination=SYN, percentile=80 | 0 | 0 | 0/0 | 0 / 0 | -75.3 |
| EN107:sources:0003 | combination=BASIS, percentile=70 | 0 | 0 | 0/0 | 0 / 0 | -75.3 |
| EN107:sources:0004 | combination=BASIS, percentile=80 | 0 | 0 | 0/0 | 0 / 0 | -75.3 |
| EN107:sources:0013 | combination=SYN_OR_BASIS, percentile=70 | 0 | 0 | 0/0 | 0 / 0 | -75.3 |
| EN107:sources:0014 | combination=SYN_OR_BASIS, percentile=80 | 0 | 0 | 0/0 | 0 / 0 | -75.3 |
| EN107:sources:0015 | combination=VOTE2, percentile=70 | 0 | 0 | 0/0 | 0 / 0 | -75.3 |
| EN107:sources:0016 | combination=VOTE2, percentile=80 | 0 | 0 | 0/0 | 0 / 0 | -75.3 |
| REF:E03_env |  | 5,167 | 4,746 | 7/7 | 4,501 / 4,114 | — |
| REF:E032_native |  | 2,449 | 1,921 | 12/11 | 1,987 / 1,516 | -44.8 |
| REF:EN55_native |  | 2,470 | 2,237 | 10/9 | 2,470 / 2,237 | -39.8 |
| EN96:ctl:no_gate | = matched E03 | 5,167 | 4,746 | 7/7 | 4,501 / 4,114 | +0.0 |
| EN106:ctl:en55_native | EN55 native | 2,470 | 2,237 | 10/9 | 2,470 / 2,237 | +5.0 |
| EN108:ctl:ungated_e0.5_p20 | looser E03 without OI | 5 | -3,818 | 50/36 | 666 / -823 | -135.9 |
| EN108:ctl:ungated_e0.5_p30 | looser E03 without OI | 253 | -2,622 | 54/39 | 894 / -665 | -117.0 |
| EN108:ctl:ungated_e0.6_p20 | looser E03 without OI | 342 | -3,821 | 29/23 | 2,847 / 1,197 | -136.0 |
| EN108:ctl:ungated_e0.6_p30 | looser E03 without OI | -2,271 | -5,377 | 33/25 | 667 / -1,610 | -160.7 |
| EN108:ctl:ungated_e0.7_p30 | looser E03 without OI | 2,294 | 1,846 | 10/9 | 2,294 / 1,846 | -46.0 |

DATA UNAVAILABLE on SENSEX: 268 OI-dependent cells (null money).

## Diagnostics (descriptive)

**EN109_dose_response_one_lot_8min:** `{"ordinary": [{"z": "[-9,0)", "n": 11, "mean": -78.87}, {"z": "[0,1)", "n": 14, "mean": -40.41}, {"z": "[1,1.5)", "n": 5, "mean": 564.24}, {"z": "[1.5,2)", "n": 4, "mean": -301.43}, {"z": "[2,99)", "n": 22, "mean": 74.41}], "adverse": [{"z": "[-9,0)", "n": 11, "mean": -103.96}, {"z": "[0,1)", "n": 14, "mean": -65.23}, {"z": "[1,1.5)", "n": 5, "mean": 529.17}, {"z": "[1.5,2)", "n": 4, "mean": -323.35}, {"z": "[2,99)", "n": 21, "mean": 53.68}]}`

**EN96_random_retention:** `{"ordinary": {"seeds": 40, "median": 4586.57, "p90": 6895.74, "en87": 6114.14, "en87_rank": 31}, "adverse": {"seeds": 40, "median": 4168.84, "p90": 6455.89, "en87": 5840.68, "en87_rank": 31}, "eligible_signals": 68, "kept_signals": 38}`

**EN97_reference_basket:** `{"events": 38, "mean_valid_pairs": 5.0, "mean_largest_share": 0.422, "atm_changed_share": 0.816, "leave_traded_pair_out": {"still_agrees": 25}}`

**EN96_common_40_warmup:** `{"sessions": 156, "first": "2023-11-09", "reference_ordinary": 5474.28, "reference_adverse": 5278.75, "cells": {"EN96:gate:0001": {"ordinary": 6128.22, "adverse": 5828.68, "paired_adverse_mean": 3.525}, "EN96:gate:0002": {"ordinary": 6674.89, "adverse": 6216.2, "paired_adverse_mean": 6.009}, "EN96:gate:0003": {"ordinary": 5939.71, "adverse": 5698.62, "paired_adverse_mean": 2.691}, "EN96:gate:0004": {"ordinary": 5939.71, "adverse": 5698.62, "paired_adverse_mean": 2.691}, "EN96:gate:0005": {"ordinary": 6682.97, "adverse": 6474.44, "paired_adverse_mean": 7.665}, "EN96:gate:0006": {"ordinary": 6008.8, "adverse": 5806.68, "paired_adverse_mean": 3.384}, "EN96:gate:0007": {"ordinary": 3762.46, "adverse": 4284.48, "paired_adverse_mean": -6.374}, "EN96:gate:0008": {"ordinary": 3840.16, "adverse": 4297.22, "paired_adverse_mean": -6.292}, "EN96:gate:0009": {"ordinary": 7468.37, "adverse": 7091.0, "paired_adverse_mean": 11.617}, "EN96:gate:0010": {"ordinary": 6794.2, "adverse": 6423.24, "paired_adverse_mean": 7.336}, "EN96:gate:0011": {"ordinary": 6726.95, "adverse": 6466.47, "paired_adverse_mean": 7.614}, "EN96:gate:0012": {"ordinary": 7468.37, "adverse": 7091.0, "paired_adverse_mean": 11.617}, "EN96:gate:0013": {"ordinary": 5474.28, "adverse": 5278.75, "paired_adverse_mean": 0.0}, "EN96:gate:0014": {"ordinary": 6726.95, "adverse": 6466.47, "paired_adverse_mean": 7.614}, "EN96:gate:0015": {"ordinary": 3591.06, "adverse": 3554.65, "paired_adverse_mean": -11.052}, "EN96:gate:0016": {"ordinary": 3668.76, "adverse": 3567.39, "paired_adverse_mean": -10.97}, "EN96:gate:0017": {"ordinary": 6915.46, "adverse": 6596.53, "paired_adverse_mean": 8.447}, "EN96:gate:0018": {"ordinary": 6915.46, "adverse": 6596.53, "paired_adverse_mean": 8.447}, "EN96:gate:0019": {"ordinary": 6726.95, "adverse": 6466.47, "paired_adverse_mean": 7.614}, "EN96:gate:0020": {"ordinary": 6915.46, "adverse": 6596.53, "paired_adverse_mean": 8.447}, "EN96:gate:0021": {"ordinary": 5474.28, "adverse": 5278.75, "paired_adverse_mean": 0.0}, "EN96:gate:0022": {"ordinary": 4921.43, "adverse": 4755.11, "paired_adverse_mean": -3.357}, "EN96:gate:0023": {"ordinary": 1246.51, "adverse": 1404.92, "paired_adverse_mean": -24.832}, "EN96:gate:0024": {"ordinary": 2431.64, "adverse": 1074.24, "paired_adverse_mean": -26.952}, "EN96:gate:0025": {"ordinary": 5109.94, "adverse": 4885.17, "paired_adverse_mean": -2.523}, "EN96:gate:0026": {"ordinary": 5109.94, "adverse": 4885.17, "paired_adverse_mean": -2.523}, "EN96:gate:0027": {"ordinary": 1863.41, "adverse": 2268.42, "paired_adverse_mean": -19.297}, "EN96:gate:0028": {"ordinary": 4492.98, "adverse": 4755.11, "paired_adverse_mean": -3.357}, "EN96:gate:0029": {"ordinary": 1785.71, "adverse": 2255.68, "paired_adverse_mean": -19.379}, "EN96:gate:0030": {"ordinary": 2541.6, "adverse": 3122.01, "paired_adverse_mean": -13.825}, "EN96:gate:0031": {"ordinary": 1684.63, "adverse": 2459.86, "paired_adverse_mean": -18.07}, "EN96:gate:0032": {"ordinary": 4284.17, "adverse": 3452`

**EN99_unfilled_arm_markout_8min_one_lot:** `{"EN99:confirm:0001": {"n": 26, "mean": 201.62, "share_positive": 0.577}, "EN99:confirm:0002": {"n": 26, "mean": 201.62, "share_positive": 0.577}, "EN99:confirm:0003": {"n": 27, "mean": 200.3, "share_positive": 0.593}, "EN99:confirm:0004": {"n": 27, "mean": 200.3, "share_positive": 0.593}, "EN99:confirm:0005": {"n": 22, "mean": 161.17, "share_positive": 0.545}, "EN99:confirm:0006": {"n": 21, "mean": 160.95, "share_positive": 0.524}, "EN99:confirm:0007": {"n": 23, "mean": 216.34, "share_positive": 0.609}, "EN99:confirm:0008": {"n": 22, "mean": 218.64, "share_positive": 0.591}, "EN99:reclaim:0001": {"n": 25, "mean": 196.69, "share_positive": 0.6}, "EN99:reclaim:0002": {"n": 25, "mean": 196.69, "share_positive": 0.6}, "EN99:reclaim:0003": {"n": 26, "mean": 192.75, "share_positive": 0.615}, "EN99:reclaim:0004": {"n": 26, "mean": 192.75, "share_positive": 0.615}, "EN99:reclaim:0005": {"n": 22, "mean": 172.4, "share_positive": 0.591}, "EN99:reclaim:0006": {"n": 22, "mean": 172.4, "share_positive": 0.591}, "EN99:reclaim:0007": {"n": 23, "mean": 169.0, "share_positive": 0.609}, "EN99:reclaim:0008": {"n": 23, "mean": 169.0, "share_positive": 0.609}}`

## Arm and context logs (NIFTY, counts by status)

- EN104:ctl:unconditional_1: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TRIGGER": 16, "UNAFFORDABLE_AT_EVENT": 4, "TTL_EXPIRED": 9, "ARM_ACTIVE": 1}
- EN104:ctl:unconditional_3: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 7, "UNAFFORDABLE_AT_EVENT": 4, "TRIGGER": 16, "ARM_ACTIVE": 1, "WINDOW_END": 2}
- EN104:ctl:unconditional_5: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TRIGGER": 16, "UNAFFORDABLE_AT_EVENT": 4, "ARM_ACTIVE": 1, "WINDOW_END": 3, "TTL_EXPIRED": 6}
- EN104:lagged_agreement:0001: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 25, "UNAFFORDABLE_AT_EVENT": 4, "ARM_ACTIVE": 1}
- EN104:lagged_agreement:0002: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 25, "UNAFFORDABLE_AT_EVENT": 4, "ARM_ACTIVE": 1}
- EN104:lagged_agreement:0003: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 25, "UNAFFORDABLE_AT_EVENT": 4, "ARM_ACTIVE": 1}
- EN104:lagged_agreement:0004: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 22, "UNAFFORDABLE_AT_EVENT": 4, "TRIGGER": 2, "ARM_ACTIVE": 1, "STRUCTURE_BROKEN": 1}
- EN104:lagged_agreement:0005: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 24, "UNAFFORDABLE_AT_EVENT": 4, "ARM_ACTIVE": 1, "STRUCTURE_BROKEN": 1}
- EN104:lagged_agreement:0006: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 24, "UNAFFORDABLE_AT_EVENT": 4, "ARM_ACTIVE": 1, "STRUCTURE_BROKEN": 1}
- EN104:lagged_agreement:0007: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 23, "UNAFFORDABLE_AT_EVENT": 4, "ARM_ACTIVE": 1, "WINDOW_END": 2}
- EN104:lagged_agreement:0008: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 23, "UNAFFORDABLE_AT_EVENT": 4, "ARM_ACTIVE": 1, "WINDOW_END": 2}
- EN104:lagged_agreement:0009: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 23, "UNAFFORDABLE_AT_EVENT": 4, "ARM_ACTIVE": 1, "WINDOW_END": 2}
- EN104:lagged_agreement:0010: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 16, "UNAFFORDABLE_AT_EVENT": 4, "TRIGGER": 2, "ARM_ACTIVE": 1, "STRUCTURE_BROKEN": 5, "WINDOW_END": 2}
- EN104:lagged_agreement:0011: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 16, "UNAFFORDABLE_AT_EVENT": 4, "TRIGGER": 2, "ARM_ACTIVE": 1, "STRUCTURE_BROKEN": 5, "WINDOW_END": 2}
- EN104:lagged_agreement:0012: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 18, "UNAFFORDABLE_AT_EVENT": 4, "ARM_ACTIVE": 1, "STRUCTURE_BROKEN": 5, "WINDOW_END": 2}
- EN104:lagged_agreement:0013: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 22, "UNAFFORDABLE_AT_EVENT": 4, "ARM_ACTIVE": 1, "WINDOW_END": 3}
- EN104:lagged_agreement:0014: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 22, "UNAFFORDABLE_AT_EVENT": 4, "ARM_ACTIVE": 1, "WINDOW_END": 3}
- EN104:lagged_agreement:0015: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 22, "UNAFFORDABLE_AT_EVENT": 4, "ARM_ACTIVE": 1, "WINDOW_END": 3}
- EN104:lagged_agreement:0016: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 12, "UNAFFORDABLE_AT_EVENT": 4, "TRIGGER": 3, "ARM_ACTIVE": 1, "STRUCTURE_BROKEN": 7, "WINDOW_END": 3}
- EN104:lagged_agreement:0017: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 12, "UNAFFORDABLE_AT_EVENT": 4, "TRIGGER": 3, "ARM_ACTIVE": 1, "STRUCTURE_BROKEN": 7, "WINDOW_END": 3}
- EN104:lagged_agreement:0018: {"SOURCE_OR_WARMUP_UNAVAILABLE": 9, "TTL_EXPIRED": 14, "UNAFFORDABLE_AT_EVENT": 4, "TRIGGER": 1, "ARM_ACTIVE": 1, "STRUCTURE_BROKEN": 7, "WINDOW_END": 3}
- EN98:context:0001: {"DROPPED": 38}
- EN98:context:0002: {"DROPPED": 38}
- EN98:context:0003: {"DROPPED": 38}
- EN98:context:0004: {"DROPPED": 38}
- EN98:context:0005: {"DROPPED": 38}
- EN98:context:0006: {"DROPPED": 38}
- EN98:context:0007: {"DROPPED": 38}
- EN98:context:0008: {"DROPPED": 38}
- EN98:context:0009: {"DROPPED": 38}
- EN98:context:0010: {"KEPT": 38}
- EN98:context:0011: {"KEPT": 38}
- EN98:context:0012: {"KEPT": 36, "DROPPED": 2}
- EN99:confirm:0001: {"TRIGGER": 3, "TTL_EXPIRED": 26, "UNAFFORDABLE_AT_EVENT": 5, "ARM_ACTIVE": 4}
- EN99:confirm:0002: {"TRIGGER": 3, "TTL_EXPIRED": 26, "UNAFFORDABLE_AT_EVENT": 5, "ARM_ACTIVE": 4}
- EN99:confirm:0003: {"TTL_EXPIRED": 27, "UNAFFORDABLE_AT_EVENT": 5, "ARM_ACTIVE": 4, "TRIGGER": 2}
- EN99:confirm:0004: {"TTL_EXPIRED": 27, "UNAFFORDABLE_AT_EVENT": 5, "ARM_ACTIVE": 4, "TRIGGER": 2}
- EN99:confirm:0005: {"TRIGGER": 7, "WINDOW_END": 1, "TTL_EXPIRED": 20, "UNAFFORDABLE_AT_EVENT": 5, "ARM_ACTIVE": 4, "INFORMATION_LOST": 1}
- EN99:confirm:0006: {"TRIGGER": 8, "WINDOW_END": 1, "TTL_EXPIRED": 19, "UNAFFORDABLE_AT_EVENT": 5, "ARM_ACTIVE": 4, "INFORMATION_LOST": 1}
- EN99:confirm:0007: {"TRIGGER": 5, "WINDOW_END": 1, "TTL_EXPIRED": 21, "UNAFFORDABLE_AT_EVENT": 5, "ARM_ACTIVE": 5, "INFORMATION_LOST": 1}
- EN99:confirm:0008: {"TRIGGER": 6, "WINDOW_END": 1, "TTL_EXPIRED": 20, "UNAFFORDABLE_AT_EVENT": 5, "ARM_ACTIVE": 5, "INFORMATION_LOST": 1}
- EN99:reclaim:0001: {"TTL_EXPIRED": 24, "ARM_ACTIVE": 7, "UNAFFORDABLE_AT_EVENT": 5, "INFORMATION_LOST": 1, "TRIGGER": 1}
- EN99:reclaim:0002: {"TTL_EXPIRED": 24, "ARM_ACTIVE": 7, "UNAFFORDABLE_AT_EVENT": 5, "INFORMATION_LOST": 1, "TRIGGER": 1}
- EN99:reclaim:0003: {"TTL_EXPIRED": 25, "ARM_ACTIVE": 7, "UNAFFORDABLE_AT_EVENT": 5, "INFORMATION_LOST": 1}
- EN99:reclaim:0004: {"TTL_EXPIRED": 25, "ARM_ACTIVE": 7, "UNAFFORDABLE_AT_EVENT": 5, "INFORMATION_LOST": 1}
- EN99:reclaim:0005: {"WINDOW_END": 2, "ARM_ACTIVE": 7, "TTL_EXPIRED": 19, "UNAFFORDABLE_AT_EVENT": 5, "TRIGGER": 4, "INFORMATION_LOST": 1}
- EN99:reclaim:0006: {"WINDOW_END": 2, "ARM_ACTIVE": 7, "TTL_EXPIRED": 19, "UNAFFORDABLE_AT_EVENT": 5, "TRIGGER": 4, "INFORMATION_LOST": 1}
- EN99:reclaim:0007: {"WINDOW_END": 2, "ARM_ACTIVE": 7, "TTL_EXPIRED": 20, "UNAFFORDABLE_AT_EVENT": 5, "TRIGGER": 3, "INFORMATION_LOST": 1}
- EN99:reclaim:0008: {"WINDOW_END": 2, "ARM_ACTIVE": 7, "TTL_EXPIRED": 20, "UNAFFORDABLE_AT_EVENT": 5, "TRIGGER": 3, "INFORMATION_LOST": 1}

Dedup: {"NIFTY": {"configs": 286, "distinct": 181}, "SENSEX": {"configs": 18, "distinct": 9}}.

