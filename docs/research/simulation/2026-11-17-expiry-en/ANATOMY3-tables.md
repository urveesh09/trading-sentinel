# EN11–EN25 tables (rendered from results3.json and anatomy3.json by render3.py)

Rupees are the net after fees on one Rs 25,000 book per year (ordinary fills unless stated). t = tickets, w = winners.

## E03.2 (control)

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | -3,645 | -4,036 | -4,173 | -4,626 | -1,162 | 17 |
| 2024 | +15,581 | +14,629 | -2,582 | +3,810 | -647 | 19 |
| 2025 | +5,937 | +5,371 | +145 | +4,085 | -478 | 20 |
| **Sum** | **+17,872** | **+15,965** | **-6,610** | | | 56 |

## EN11 — FAIL

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | -4,006 | -4,120 | -4,030 | -4,148 | -831 | 17 | -3,645 |
| 2024 | +13,748 | +13,611 | -2,362 | +1,977 | -662 | 19 | +15,581 |
| 2025 | +4,964 | +4,311 | -102 | +3,111 | -713 | 20 | +5,937 |
| **Sum** | **+14,706** | **+13,801** | **-6,494** | | | 56 | +17,872 |

Checks failed: 2023_ordinary, 2023_adverse, 2024_ordinary, 2024_adverse, 2024_without_best, 2025_ordinary, 2025_adverse, 2025_without_best.

**2023** — 17 tickets, 4 winners, -4,006.
- *side:* C 10t 2w -1,732; P 7t 2w -2,275
- *first exit:* STOP_FAST 7t 0w -3,652; TIME 8t 2w -602; TRAIL_FAST 2t 2w +247
- *entry window:* 13:00-13:30 7t 1w -1,765; 13:30-14:00 5t 1w -943; 14:00-14:30 3t 2w -81; 14:30-15:00 2t 0w -1,218
- *days:* E03.2 traded that day 17t 4w -4,006
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 9 (6 better, 3 worse, -361).
- *biggest changes:* 2023-06-22 P +1,104 → +196 (TRAIL_FAST); 2023-12-07 P -830 → -390 (STOP_FAST); 2023-06-15 P -1,162 → -831 (STOP_FAST); 2023-08-31 P -343 → -635 (STOP_FAST)
- *best:* 2023-06-22 P +196 (TRAIL_FAST); 2023-07-27 P +142 (TIME); 2023-03-16 C +51 (TRAIL_FAST)
- *worst:* 2023-06-15 P -831 (STOP_FAST); 2023-03-16 P -753 (STOP_FAST); 2023-08-31 P -635 (STOP_FAST)

**2024** — 19 tickets, 8 winners, +13,748.
- *side:* C 11t 3w +22; P 8t 5w +13,726
- *first exit:* STOP_FAST 7t 0w -2,305; STRUCTURE_FAST 2t 0w -978; TARGET 1t 1w +1,044; TARGET_BASE 4t 4w +15,346; TIME 3t 1w +431; TRAIL_FAST 2t 2w +210
- *entry window:* 13:00-13:30 5t 1w +395; 13:30-14:00 4t 0w -1,408; 14:00-14:30 5t 3w +1,150; 14:30-15:00 5t 4w +13,610
- *days:* E03.2 traded that day 19t 8w +13,748
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 11 (8 better, 3 worse, -1,833).
- *biggest changes:* 2024-02-22 C +1,313 → -380 (STOP_FAST); 2024-08-22 P +953 → +174 (TRAIL_FAST); 2024-02-29 C -471 → +35 (TRAIL_FAST); 2024-01-11 P -647 → -482 (STOP_FAST)
- *best:* 2024-03-28 P +11,771 (TARGET_BASE+HERO_TARGET); 2024-08-08 P +1,377 (TARGET_BASE+RUNNER_TRAIL); 2024-07-18 C +1,150 (TARGET_BASE+RUNNER_TRAIL)
- *worst:* 2024-08-14 P -662 (STRUCTURE_FAST); 2024-01-11 P -482 (STOP_FAST); 2024-02-22 C -380 (STOP_FAST)

**2025** — 20 tickets, 13 winners, +4,964.
- *side:* C 11t 7w +1,244; P 9t 6w +3,720
- *first exit:* STOP_FAST 5t 0w -2,371; TARGET 1t 1w +691; TARGET_BASE 1t 1w +1,047; TIME 12t 10w +5,575; TRAIL_FAST 1t 1w +22
- *entry window:* 13:00-13:30 6t 4w +1,331; 13:30-14:00 6t 4w +1,871; 14:00-14:30 5t 4w +2,413; 14:30-15:00 3t 1w -650
- *days:* E03.2 traded that day 20t 13w +4,964
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 6 (3 better, 3 worse, -973).
- *biggest changes:* 2025-02-13 P +402 → -416 (STOP_FAST); 2025-05-22 P -279 → -713 (STOP_FAST); 2025-01-02 C -205 → +22 (TRAIL_FAST); 2025-03-06 C -478 → -439 (STOP_FAST)
- *best:* 2025-08-07 P +1,253 (TIME); 2025-09-02 P +1,047 (TARGET_BASE+RUNNER_TRAIL); 2025-06-12 P +966 (TIME)
- *worst:* 2025-05-22 P -713 (STOP_FAST); 2025-11-11 C -452 (STOP_FAST); 2025-03-06 C -439 (STOP_FAST)

## EN12 — INCONCLUSIVE

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | -3,645 | -4,036 | -4,173 | -4,626 | -1,162 | 17 | -3,645 |
| 2024 | +15,581 | +16,103 | -2,582 | +3,810 | -647 | 19 | +15,581 |
| 2025 | +6,882 | +5,371 | +145 | +4,890 | -478 | 20 | +5,937 |
| **Sum** | **+18,817** | **+17,439** | **-6,610** | | | 56 | +17,872 |

Checks failed: none.

**2023** — 17 tickets, 4 winners, -3,645.
- *side:* C 10t 2w -1,663; P 7t 2w -1,982
- *first exit:* STOP 5t 0w -3,709; TIME 11t 3w +26; TRAIL 1t 1w +38
- *entry window:* 13:00-13:30 7t 1w -1,913; 13:30-14:00 5t 1w -884; 14:00-14:30 3t 2w +740; 14:30-15:00 2t 0w -1,587
- *days:* E03.2 traded that day 17t 4w -3,645
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 0 (0 better, 0 worse, +0).
- *best:* 2023-06-22 P +1,104 (TIME); 2023-07-27 P +142 (TIME); 2023-04-27 C +49 (TIME)
- *worst:* 2023-06-15 P -1,162 (STOP); 2023-03-16 P -889 (STOP); 2023-12-07 P -830 (STOP)

**2024** — 19 tickets, 8 winners, +15,581.
- *side:* C 11t 3w +1,086; P 8t 5w +14,495
- *first exit:* STOP 6t 0w -2,207; STRUCTURE 1t 0w -322; TARGET 2t 2w +2,357; TARGET_BASE 4t 4w +15,346; TIME 5t 2w +877; TRAIL 1t 0w -471
- *entry window:* 13:00-13:30 5t 1w +528; 13:30-14:00 4t 1w +243; 14:00-14:30 5t 3w +1,741; 14:30-15:00 5t 3w +13,069
- *days:* E03.2 traded that day 19t 8w +15,581
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 0 (0 better, 0 worse, +0).
- *best:* 2024-03-28 P +11,771 (TARGET_BASE+HERO_TARGET); 2024-08-08 P +1,377 (TARGET_BASE+RUNNER_TRAIL); 2024-02-22 C +1,313 (TARGET)
- *worst:* 2024-01-11 P -647 (STOP); 2024-08-14 P -507 (TIME); 2024-02-29 C -471 (TRAIL)

**2025** — 20 tickets, 13 winners, +6,882.
- *side:* C 11t 6w +965; P 9t 7w +5,917
- *first exit:* STOP 2t 0w -969; TARGET 2t 2w +2,682; TIME 15t 11w +5,373; TRAIL 1t 0w -205
- *entry window:* 13:00-13:30 6t 4w +1,357; 13:30-14:00 6t 5w +2,649; 14:00-14:30 5t 4w +3,792; 14:30-15:00 3t 0w -916
- *days:* E03.2 traded that day 20t 13w +6,882
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 1 (1 better, 0 worse, +945).
- *biggest changes:* 2025-09-02 P +1,047 → +1,992 (TARGET)
- *best:* 2025-09-02 P +1,992 (TARGET); 2025-08-07 P +1,253 (TIME); 2025-06-12 P +966 (TIME)
- *worst:* 2025-11-11 C -491 (STOP); 2025-03-06 C -478 (STOP); 2025-02-06 C -325 (TIME)

## EN12_full_sale_diag — DIAGNOSTIC

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | -3,645 | -4,036 | -4,173 | -4,626 | -1,162 | 17 | -3,645 |
| 2024 | +9,586 | +8,674 | -2,582 | +6,718 | -647 | 20 | +15,581 |
| 2025 | +6,882 | +6,469 | +145 | +4,890 | -478 | 20 | +5,937 |
| **Sum** | **+12,823** | **+11,107** | **-6,610** | | | 57 | +17,872 |

**2023** — 17 tickets, 4 winners, -3,645.
- *side:* C 10t 2w -1,663; P 7t 2w -1,982
- *first exit:* STOP 5t 0w -3,709; TIME 11t 3w +26; TRAIL 1t 1w +38
- *entry window:* 13:00-13:30 7t 1w -1,913; 13:30-14:00 5t 1w -884; 14:00-14:30 3t 2w +740; 14:30-15:00 2t 0w -1,587
- *days:* E03.2 traded that day 17t 4w -3,645
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 0 (0 better, 0 worse, +0).
- *best:* 2023-06-22 P +1,104 (TIME); 2023-07-27 P +142 (TIME); 2023-04-27 C +49 (TIME)
- *worst:* 2023-06-15 P -1,162 (STOP); 2023-03-16 P -889 (STOP); 2023-12-07 P -830 (STOP)

**2024** — 20 tickets, 8 winners, +9,586.
- *side:* C 12t 3w +1,303; P 8t 5w +8,283
- *first exit:* STOP 6t 0w -2,207; STRUCTURE 1t 0w -322; TARGET 6t 6w +11,959; TIME 6t 2w +627; TRAIL 1t 0w -471
- *entry window:* 13:00-13:30 5t 1w +1,733; 13:30-14:00 5t 1w -7; 14:00-14:30 5t 3w +2,209; 14:30-15:00 5t 3w +5,652
- *days:* E03.2 traded that day 20t 8w +9,586
- *vs E03.2:* added 1 (0w, -250), removed 0 (0w, +0), changed 4 (3 better, 1 worse, -5,744).
- *biggest changes:* 2024-03-28 P +11,771 → +2,868 (TARGET); 2024-05-09 P +1,049 → +2,536 (TARGET); 2024-08-08 P +1,377 → +2,581 (TARGET); 2024-07-18 C +1,150 → +1,618 (TARGET)
- *best:* 2024-03-28 P +2,868 (TARGET); 2024-08-08 P +2,581 (TARGET); 2024-05-09 P +2,536 (TARGET)
- *worst:* 2024-01-11 P -647 (STOP); 2024-08-14 P -507 (TIME); 2024-02-29 C -471 (TRAIL)

**2025** — 20 tickets, 13 winners, +6,882.
- *side:* C 11t 6w +965; P 9t 7w +5,917
- *first exit:* STOP 2t 0w -969; TARGET 2t 2w +2,682; TIME 15t 11w +5,373; TRAIL 1t 0w -205
- *entry window:* 13:00-13:30 6t 4w +1,357; 13:30-14:00 6t 5w +2,649; 14:00-14:30 5t 4w +3,792; 14:30-15:00 3t 0w -916
- *days:* E03.2 traded that day 20t 13w +6,882
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 1 (1 better, 0 worse, +945).
- *biggest changes:* 2025-09-02 P +1,047 → +1,992 (TARGET)
- *best:* 2025-09-02 P +1,992 (TARGET); 2025-08-07 P +1,253 (TIME); 2025-06-12 P +966 (TIME)
- *worst:* 2025-11-11 C -491 (STOP); 2025-03-06 C -478 (STOP); 2025-02-06 C -325 (TIME)

## EN13 — FAIL

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | -2,608 | -3,206 | -3,383 | -3,012 | -862 | 32 | -3,645 |
| 2024 | -2,924 | -3,687 | -4,071 | -3,786 | -567 | 41 | +15,581 |
| 2025 | -4,033 | -4,046 | -4,030 | -4,315 | -624 | 29 | +5,937 |
| **Sum** | **-9,565** | **-10,938** | **-11,484** | | | 102 | +17,872 |

Checks failed: 2023_positive, 2023_without_best_ge_0, 2023_above_null, 2024_positive, 2024_without_best_ge_0, 2025_positive, 2025_without_best_ge_0, 2025_above_null, adverse_sum_positive. Null median: {'2023': -2128.1, '2024': -3696.91, '2025': -3368.65}.

**2023** — 32 tickets, 9 winners, -2,608.
- *side:* C 14t 3w -2,022; P 18t 6w -586
- *first exit:* SETUP_TARGET 8t 7w +1,671; STOP 2t 0w -864; STRUCTURE 10t 0w -2,392; TIME 12t 2w -1,023
- *entry window:* 13:00-13:30 22t 7w -1,213; 13:30-14:00 5t 0w -1,502; 14:00-14:30 4t 2w +237; 14:30-15:00 1t 0w -130
- *days:* E03.2 empty day 23t 6w -1,899; E03.2 traded that day 9t 3w -710
- *vs E03.2:* added 32 (9w, -2,608), removed 17 (4w, -3,645), changed 0 (0 better, 0 worse, +0).
- *best:* 2023-02-09 C +404 (SETUP_TARGET); 2023-02-23 P +356 (SETUP_TARGET); 2023-03-16 P +350 (SETUP_TARGET)
- *worst:* 2023-02-02 C -533 (STOP); 2023-10-19 C -354 (STRUCTURE); 2023-03-16 P -331 (STOP)

**2024** — 41 tickets, 13 winners, -2,924.
- *side:* C 18t 6w -1,618; P 23t 7w -1,306
- *first exit:* SETUP_TARGET 8t 7w +1,719; STOP 3t 0w -980; STRUCTURE 10t 0w -2,635; TARGET 1t 1w +425; TIME 19t 5w -1,453
- *entry window:* 13:00-13:30 25t 9w -1,526; 13:30-14:00 10t 2w -1,528; 14:00-14:30 1t 0w -68; 14:30-15:00 5t 2w +197
- *days:* E03.2 empty day 24t 7w -1,827; E03.2 traded that day 17t 6w -1,097
- *vs E03.2:* added 41 (13w, -2,924), removed 19 (8w, +15,581), changed 0 (0 better, 0 worse, +0).
- *best:* 2024-02-01 P +454 (SETUP_TARGET); 2024-04-04 P +425 (TARGET); 2024-02-01 P +408 (SETUP_TARGET)
- *worst:* 2024-02-29 P -423 (STRUCTURE); 2024-03-14 C -412 (STOP); 2024-05-09 C -364 (STOP)

**2025** — 29 tickets, 6 winners, -4,033.
- *side:* C 18t 3w -2,111; P 11t 3w -1,922
- *first exit:* SETUP_TARGET 4t 3w +525; STOP 5t 0w -1,825; STRUCTURE 6t 0w -1,151; TIME 14t 3w -1,582
- *entry window:* 13:00-13:30 17t 4w -1,565; 13:30-14:00 7t 2w -1,054; 14:00-14:30 5t 0w -1,415
- *days:* E03.2 empty day 17t 5w -2,043; E03.2 traded that day 12t 1w -1,990
- *vs E03.2:* added 29 (6w, -4,033), removed 20 (13w, +5,937), changed 0 (0 better, 0 worse, +0).
- *best:* 2025-03-13 P +282 (SETUP_TARGET); 2025-04-09 C +190 (SETUP_TARGET); 2025-10-28 P +98 (SETUP_TARGET)
- *worst:* 2025-03-20 P -477 (STOP); 2025-05-08 C -410 (STOP); 2025-04-17 P -397 (STOP)

## EN14 — FAIL

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | +1,768 | +1,162 | +669 | +566 | -1,221 | 28 | -3,645 |
| 2024 | -3,203 | -3,515 | -2,059 | -3,299 | -513 | 14 | +15,581 |
| 2025 | -1,064 | -1,714 | -3,228 | -2,176 | -595 | 22 | +5,937 |
| **Sum** | **-2,499** | **-4,067** | **-4,619** | | | 64 | +17,872 |

Checks failed: 2024_positive, 2024_without_best_ge_0, 2024_above_null, 2025_positive, 2025_without_best_ge_0, adverse_sum_positive. Null median: {'2023': -836.74, '2024': -1561.3, '2025': -1512.75}.

**2023** — 28 tickets, 14 winners, +1,768.
- *side:* C 16t 7w +1,269; P 12t 7w +499
- *first exit:* STOP 4t 0w -1,845; STRUCTURE 2t 0w -579; TARGET 1t 1w +1,203; TARGET_BASE 2t 2w +2,060; TIME 19t 11w +931
- *entry window:* 13:00-13:30 5t 1w +216; 13:30-14:00 15t 9w +393; 14:00-14:30 6t 3w +734; 14:30-15:00 2t 1w +426
- *days:* E03.2 empty day 17t 8w -817; E03.2 traded that day 11t 6w +2,585
- *vs E03.2:* added 28 (14w, +1,768), removed 17 (4w, -3,645), changed 0 (0 better, 0 worse, +0).
- *best:* 2023-08-10 P +1,203 (TARGET); 2023-09-07 C +1,134 (TARGET_BASE+RUNNER_TRAIL); 2023-03-16 C +926 (TARGET_BASE+RUNNER_TRAIL)
- *worst:* 2023-11-30 C -708 (STOP); 2023-11-30 C -513 (STOP); 2023-07-13 P -464 (STOP)

**2024** — 14 tickets, 4 winners, -3,203.
- *side:* C 8t 2w -1,595; P 6t 2w -1,608
- *first exit:* STOP 7t 0w -2,903; TIME 5t 3w -18; TRAIL 2t 1w -281
- *entry window:* 13:00-13:30 5t 2w -948; 13:30-14:00 5t 1w -1,229; 14:00-14:30 2t 1w -202; 14:30-15:00 2t 0w -824
- *days:* E03.2 empty day 5t 2w -503; E03.2 traded that day 9t 2w -2,700
- *vs E03.2:* added 13 (4w, -2,816), removed 18 (8w, +15,967), changed 0 (0 better, 0 worse, +0).
- *best:* 2024-06-20 C +136 (TIME); 2024-05-30 P +96 (TIME); 2024-07-11 C +84 (TIME)
- *worst:* 2024-06-20 P -536 (STOP); 2024-07-18 C -513 (STOP); 2024-08-22 P -497 (STOP)

**2025** — 22 tickets, 9 winners, -1,064.
- *side:* C 8t 1w -2,328; P 14t 8w +1,263
- *first exit:* STOP 9t 0w -4,152; TARGET 2t 2w +2,084; TIME 8t 6w +1,158; TRAIL 3t 1w -154
- *entry window:* 13:00-13:30 6t 3w -210; 13:30-14:00 7t 2w -673; 14:00-14:30 7t 4w +659; 14:30-15:00 2t 0w -841
- *days:* E03.2 empty day 6t 2w -1,427; E03.2 traded that day 16t 7w +363
- *vs E03.2:* added 20 (8w, -1,545), removed 18 (12w, +5,381), changed 1 (0 better, 1 worse, -75).
- *biggest changes:* 2025-09-02 P +1,047 → +972 (TARGET)
- *best:* 2025-12-09 P +1,111 (TARGET); 2025-09-02 P +972 (TARGET); 2025-07-03 P +476 (TIME)
- *worst:* 2025-08-07 C -666 (STOP); 2025-06-26 P -595 (STOP); 2025-11-11 C -491 (STOP)

## EN14_immediate_diag — DIAGNOSTIC

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | -3,307 | -3,855 | -3,861 | -4,129 | -788 | 39 | -3,645 |
| 2024 | -3,803 | -4,059 | -4,158 | -4,393 | -598 | 38 | +15,581 |
| 2025 | -3,097 | -3,191 | -4,104 | -4,572 | -868 | 35 | +5,937 |
| **Sum** | **-10,206** | **-11,105** | **-12,123** | | | 112 | +17,872 |

**2023** — 39 tickets, 15 winners, -3,307.
- *side:* C 18t 7w -1,260; P 21t 8w -2,047
- *first exit:* STOP 6t 0w -2,278; STRUCTURE 9t 0w -2,340; TIME 23t 14w +1,271; TRAIL 1t 1w +41
- *entry window:* 13:00-13:30 15t 5w -1,371; 13:30-14:00 15t 7w -500; 14:00-14:30 8t 3w -1,069; 14:30-15:00 1t 0w -367
- *days:* E03.2 empty day 24t 7w -3,512; E03.2 traded that day 15t 8w +205
- *vs E03.2:* added 39 (15w, -3,307), removed 17 (4w, -3,645), changed 0 (0 better, 0 worse, +0).
- *best:* 2023-02-16 P +865 (TIME); 2023-03-29 C +521 (TIME); 2023-03-23 P +223 (TIME)
- *worst:* 2023-07-06 C -588 (STOP); 2023-05-18 P -549 (STOP); 2023-03-16 P -397 (STRUCTURE)

**2024** — 38 tickets, 10 winners, -3,803.
- *side:* C 19t 6w -961; P 19t 4w -2,842
- *first exit:* STOP 8t 0w -2,601; STRUCTURE 13t 0w -3,127; TARGET 2t 2w +1,676; TIME 15t 8w +248
- *entry window:* 13:00-13:30 17t 4w -1,826; 13:30-14:00 9t 4w -188; 14:00-14:30 7t 1w -1,627; 14:30-15:00 5t 1w -162
- *days:* E03.2 empty day 23t 6w -2,857; E03.2 traded that day 15t 4w -946
- *vs E03.2:* added 38 (10w, -3,803), removed 19 (8w, +15,581), changed 0 (0 better, 0 worse, +0).
- *best:* 2024-02-29 C +966 (TARGET); 2024-04-04 C +710 (TARGET); 2024-02-15 C +350 (TIME)
- *worst:* 2024-03-28 C -452 (STOP); 2024-06-27 P -410 (STRUCTURE); 2024-01-18 C -393 (STOP)

**2025** — 35 tickets, 8 winners, -3,097.
- *side:* C 18t 5w -796; P 17t 3w -2,300
- *first exit:* STOP 9t 0w -3,172; STRUCTURE 10t 0w -2,342; TARGET 2t 2w +2,024; TIME 12t 6w +850; TRAIL 2t 0w -455
- *entry window:* 13:00-13:30 13t 3w +44; 13:30-14:00 9t 3w -1,178; 14:00-14:30 11t 2w -1,255; 14:30-15:00 2t 0w -708
- *days:* E03.2 empty day 20t 4w -1,829; E03.2 traded that day 15t 4w -1,268
- *vs E03.2:* added 35 (8w, -3,097), removed 20 (13w, +5,937), changed 0 (0 better, 0 worse, +0).
- *best:* 2025-03-20 C +1,475 (TARGET); 2025-04-17 C +719 (TIME); 2025-12-09 P +549 (TARGET)
- *worst:* 2025-06-05 P -520 (STOP); 2025-06-12 C -478 (STOP); 2025-01-02 C -471 (STOP)

## EN17 — FAIL

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | -628 | -693 | -610 | -628 | -308 | 3 | -3,645 |
| 2024 | -1,388 | -1,547 | -997 | -1,388 | -651 | 4 | +15,581 |
| 2025 | -1,525 | -2,119 | -3,173 | -2,470 | -696 | 8 | +5,937 |
| **Sum** | **-3,540** | **-4,358** | **-4,780** | | | 15 | +17,872 |

Checks failed: 2023_positive, 2023_without_best_ge_0, 2023_above_null, 2024_positive, 2024_without_best_ge_0, 2024_above_null, 2025_positive, 2025_without_best_ge_0, 2025_above_null, adverse_sum_positive. Null median: {'2023': -378.14, '2024': 567.33, '2025': -754.89}.

**2023** — 3 tickets, 0 winners, -628.
- *side:* PAIR 3t 0w -628
- *first exit:* FADE 3t 0w -628
- *entry window:* 13:30-14:00 2t 0w -319; 14:30-15:00 1t 0w -308
- *days:* E03.2 empty day 2t 0w -319; E03.2 traded that day 1t 0w -308
- *vs E03.2:* added 3 (0w, -628), removed 17 (4w, -3,645), changed 0 (0 better, 0 worse, +0).
- *best:* 2023-05-18 PAIR -36 (FADE); 2023-11-30 PAIR -283 (FADE); 2023-06-22 PAIR -308 (FADE)
- *worst:* 2023-06-22 PAIR -308 (FADE); 2023-11-30 PAIR -283 (FADE); 2023-05-18 PAIR -36 (FADE)

**2024** — 4 tickets, 0 winners, -1,388.
- *side:* PAIR 4t 0w -1,388
- *first exit:* FADE 2t 0w -367; ONE_LEG 1t 0w -370; PAIR_STOP 1t 0w -651
- *entry window:* 13:00-13:30 1t 0w -5; 13:30-14:00 2t 0w -1,012; 14:00-14:30 1t 0w -370
- *days:* E03.2 empty day 4t 0w -1,388
- *vs E03.2:* added 4 (0w, -1,388), removed 19 (8w, +15,581), changed 0 (0 better, 0 worse, +0).
- *best:* 2024-09-26 PAIR -5 (FADE); 2024-12-26 PAIR -362 (FADE); 2024-11-28 PAIR -370 (ONE_LEG)
- *worst:* 2024-04-18 PAIR -651 (PAIR_STOP); 2024-11-28 PAIR -370 (ONE_LEG); 2024-12-26 PAIR -362 (FADE)

**2025** — 8 tickets, 2 winners, -1,525.
- *side:* PAIR 8t 2w -1,525
- *first exit:* FADE 5t 1w -1,078; PAIR_STOP 2t 0w -1,392; PAIR_TARGET 1t 1w +946
- *entry window:* 13:00-13:30 1t 0w -696; 13:30-14:00 1t 0w -696; 14:00-14:30 4t 1w -600; 14:30-15:00 2t 1w +467
- *days:* E03.2 empty day 4t 1w -1,148; E03.2 traded that day 4t 1w -377
- *vs E03.2:* added 8 (2w, -1,525), removed 20 (13w, +5,937), changed 0 (0 better, 0 worse, +0).
- *best:* 2025-08-07 PAIR +946 (PAIR_TARGET); 2025-01-30 PAIR +70 (FADE); 2025-07-24 PAIR -46 (FADE)
- *worst:* 2025-06-05 PAIR -696 (PAIR_STOP); 2025-07-03 PAIR -696 (PAIR_STOP); 2025-09-02 PAIR -478 (FADE)

## EN19 — FAIL

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | +1,629 | +1,418 | -39 | +529 | -435 | 11 | -3,645 |
| 2024 | -2,530 | -2,628 | -957 | -2,798 | -542 | 12 | +15,581 |
| 2025 | -2,697 | -3,227 | -3,558 | -3,484 | -595 | 21 | +5,937 |
| **Sum** | **-3,599** | **-4,437** | **-4,555** | | | 44 | +17,872 |

Checks failed: 2024_positive, 2024_without_best_ge_0, 2024_above_null, 2025_positive, 2025_without_best_ge_0, adverse_sum_positive. Null median: {'2023': 228.29, '2024': -2221.4, '2025': -2997.23}.

**2023** — 11 tickets, 4 winners, +1,629.
- *side:* C 3t 1w +692; P 8t 3w +937
- *first exit:* RUNNER_TRAIL 5t 3w +2,749; STOP 5t 0w -1,231; TRAIL 1t 1w +110
- *entry window:* 14:00-14:30 4t 3w +2,376; 14:30-15:00 7t 1w -747
- *days:* E03.2 empty day 6t 2w +153; E03.2 traded that day 5t 2w +1,475
- *vs E03.2:* added 11 (4w, +1,629), removed 17 (4w, -3,645), changed 0 (0 better, 0 worse, +0).
- *best:* 2023-06-22 P +1,099 (RUNNER_TRAIL); 2023-11-16 C +928 (RUNNER_TRAIL); 2023-07-27 P +784 (RUNNER_TRAIL)
- *worst:* 2023-03-23 P -435 (STOP); 2023-07-13 P -292 (STOP); 2023-08-17 C -210 (STOP)

**2024** — 12 tickets, 3 winners, -2,530.
- *side:* C 5t 2w -988; P 7t 1w -1,543
- *first exit:* RUNNER_TRAIL 2t 2w +381; STOP 8t 0w -2,916; TRAIL 2t 1w +4
- *entry window:* 14:00-14:30 6t 0w -2,176; 14:30-15:00 6t 3w -354
- *days:* E03.2 empty day 6t 0w -1,820; E03.2 traded that day 6t 3w -710
- *vs E03.2:* added 11 (2w, -2,798), removed 18 (7w, +14,532), changed 1 (0 better, 1 worse, -781).
- *biggest changes:* 2024-05-09 P +1,049 → +268 (RUNNER_TRAIL)
- *best:* 2024-05-09 P +268 (RUNNER_TRAIL); 2024-06-27 C +113 (RUNNER_TRAIL); 2024-09-12 C +30 (TRAIL)
- *worst:* 2024-05-02 P -542 (STOP); 2024-03-14 C -462 (STOP); 2024-08-08 C -449 (STOP)

**2025** — 21 tickets, 6 winners, -2,697.
- *side:* C 7t 1w -1,452; P 14t 5w -1,245
- *first exit:* RUNNER_TRAIL 5t 5w +3,056; STOP 14t 0w -5,713; TRAIL 2t 1w -40
- *entry window:* 14:00-14:30 9t 4w -398; 14:30-15:00 12t 2w -2,299
- *days:* E03.2 empty day 10t 3w -1,831; E03.2 traded that day 11t 3w -867
- *vs E03.2:* added 20 (6w, -2,435), removed 19 (13w, +6,415), changed 1 (1 better, 0 worse, +215).
- *biggest changes:* 2025-03-06 C -478 → -263 (STOP)
- *best:* 2025-12-09 P +787 (RUNNER_TRAIL); 2025-05-08 P +691 (RUNNER_TRAIL); 2025-07-03 P +635 (RUNNER_TRAIL)
- *worst:* 2025-08-21 C -595 (STOP); 2025-11-18 P -585 (STOP); 2025-10-20 P -566 (STOP)

## EN20 — INCONCLUSIVE

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | -3,645 | -4,036 | -4,173 | -4,626 | -1,162 | 17 | -3,645 |
| 2024 | +15,216 | +14,284 | -2,582 | +3,446 | -647 | 19 | +15,581 |
| 2025 | +5,937 | +5,371 | +145 | +4,085 | -478 | 20 | +5,937 |
| **Sum** | **+17,508** | **+15,620** | **-6,610** | | | 56 | +17,872 |

Checks failed: 2024_ordinary, 2024_adverse, 2024_without_best.

**2023** — 17 tickets, 4 winners, -3,645.
- *side:* C 10t 2w -1,663; P 7t 2w -1,982
- *first exit:* STOP 5t 0w -3,709; TIME 11t 3w +26; TRAIL 1t 1w +38
- *entry window:* 13:00-13:30 7t 1w -1,913; 13:30-14:00 5t 1w -884; 14:00-14:30 3t 2w +740; 14:30-15:00 2t 0w -1,587
- *days:* E03.2 traded that day 17t 4w -3,645
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 0 (0 better, 0 worse, +0).
- *best:* 2023-06-22 P +1,104 (TIME); 2023-07-27 P +142 (TIME); 2023-04-27 C +49 (TIME)
- *worst:* 2023-06-15 P -1,162 (STOP); 2023-03-16 P -889 (STOP); 2023-12-07 P -830 (STOP)

**2024** — 19 tickets, 8 winners, +15,216.
- *side:* C 11t 3w +721; P 8t 5w +14,495
- *first exit:* STOP 6t 0w -2,207; STRUCTURE 1t 0w -322; TARGET 3t 3w +3,142; TARGET_BASE 3t 3w +14,197; TIME 5t 2w +877; TRAIL 1t 0w -471
- *entry window:* 13:00-13:30 5t 1w +528; 13:30-14:00 4t 1w +243; 14:00-14:30 5t 3w +1,376; 14:30-15:00 5t 3w +13,069
- *days:* E03.2 traded that day 19t 8w +15,216
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 1 (0 better, 1 worse, -364).
- *biggest changes:* 2024-07-18 C +1,150 → +785 (TARGET)
- *best:* 2024-03-28 P +11,771 (TARGET_BASE+HERO_TARGET); 2024-08-08 P +1,377 (TARGET_BASE+RUNNER_TRAIL); 2024-02-22 C +1,313 (TARGET)
- *worst:* 2024-01-11 P -647 (STOP); 2024-08-14 P -507 (TIME); 2024-02-29 C -471 (TRAIL)

**2025** — 20 tickets, 13 winners, +5,937.
- *side:* C 11t 6w +965; P 9t 7w +4,972
- *first exit:* STOP 2t 0w -969; TARGET 1t 1w +691; TARGET_BASE 1t 1w +1,047; TIME 15t 11w +5,373; TRAIL 1t 0w -205
- *entry window:* 13:00-13:30 6t 4w +1,357; 13:30-14:00 6t 5w +2,649; 14:00-14:30 5t 4w +2,847; 14:30-15:00 3t 0w -916
- *days:* E03.2 traded that day 20t 13w +5,937
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 0 (0 better, 0 worse, +0).
- *best:* 2025-08-07 P +1,253 (TIME); 2025-09-02 P +1,047 (TARGET_BASE+RUNNER_TRAIL); 2025-06-12 P +966 (TIME)
- *worst:* 2025-11-11 C -491 (STOP); 2025-03-06 C -478 (STOP); 2025-02-06 C -325 (TIME)

## EN20_no_retry_diag — DIAGNOSTIC

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | -4,007 | -4,041 | -4,173 | -4,149 | -1,162 | 16 | -3,645 |
| 2024 | +13,841 | +13,013 | -2,582 | +2,070 | -647 | 17 | +15,581 |
| 2025 | +5,937 | +5,371 | +145 | +4,085 | -478 | 20 | +5,937 |
| **Sum** | **+15,771** | **+14,343** | **-6,610** | | | 53 | +17,872 |

**2023** — 16 tickets, 3 winners, -4,007.
- *side:* C 9t 1w -1,701; P 7t 2w -2,306
- *first exit:* STOP 5t 0w -3,318; TIME 11t 3w -690
- *entry window:* 13:00-13:30 7t 1w -1,373; 13:30-14:00 5t 1w -884; 14:00-14:30 2t 1w -162; 14:30-15:00 2t 0w -1,587
- *days:* E03.2 traded that day 16t 3w -4,007
- *vs E03.2:* added 0 (0w, +0), removed 1 (1w, +38), changed 3 (2 better, 1 worse, -324).
- *biggest changes:* 2023-06-22 P +1,104 → +241 (TIME); 2023-12-07 P -830 → -439 (STOP); 2023-08-31 P -343 → -195 (TIME)
- *best:* 2023-06-22 P +241 (TIME); 2023-07-27 P +142 (TIME); 2023-04-27 C +49 (TIME)
- *worst:* 2023-06-15 P -1,162 (STOP); 2023-03-16 P -889 (STOP); 2023-12-07 P -439 (STOP)

**2024** — 17 tickets, 6 winners, +13,841.
- *side:* C 10t 2w -64; P 7t 4w +13,905
- *first exit:* STOP 6t 0w -2,207; STRUCTURE 1t 0w -322; TARGET 2t 2w +2,357; TARGET_BASE 3t 3w +14,197; TIME 4t 1w +287; TRAIL 1t 0w -471
- *entry window:* 13:00-13:30 5t 1w +528; 13:30-14:00 4t 1w +243; 14:00-14:30 3t 1w +1; 14:30-15:00 5t 3w +13,069
- *days:* E03.2 traded that day 17t 6w +13,841
- *vs E03.2:* added 0 (0w, +0), removed 2 (2w, +1,740), changed 0 (0 better, 0 worse, +0).
- *best:* 2024-03-28 P +11,771 (TARGET_BASE+HERO_TARGET); 2024-08-08 P +1,377 (TARGET_BASE+RUNNER_TRAIL); 2024-02-22 C +1,313 (TARGET)
- *worst:* 2024-01-11 P -647 (STOP); 2024-08-14 P -507 (TIME); 2024-02-29 C -471 (TRAIL)

**2025** — 20 tickets, 13 winners, +5,937.
- *side:* C 11t 6w +965; P 9t 7w +4,972
- *first exit:* STOP 2t 0w -969; TARGET 1t 1w +691; TARGET_BASE 1t 1w +1,047; TIME 15t 11w +5,373; TRAIL 1t 0w -205
- *entry window:* 13:00-13:30 6t 4w +1,357; 13:30-14:00 6t 5w +2,649; 14:00-14:30 5t 4w +2,847; 14:30-15:00 3t 0w -916
- *days:* E03.2 traded that day 20t 13w +5,937
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 0 (0 better, 0 worse, +0).
- *best:* 2025-08-07 P +1,253 (TIME); 2025-09-02 P +1,047 (TARGET_BASE+RUNNER_TRAIL); 2025-06-12 P +966 (TIME)
- *worst:* 2025-11-11 C -491 (STOP); 2025-03-06 C -478 (STOP); 2025-02-06 C -325 (TIME)

## EN21 — FAIL

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | -3,042 | -3,473 | -3,725 | -3,120 | -604 | 17 | -3,645 |
| 2024 | +21,293 | +20,381 | -2,509 | +2,864 | -729 | 20 | +15,581 |
| 2025 | +3,922 | +3,054 | -277 | +2,719 | -476 | 20 | +5,937 |
| **Sum** | **+22,173** | **+19,961** | **-6,512** | | | 57 | +17,872 |

Checks failed: 2024_without_best, 2025_ordinary, 2025_adverse, 2025_without_best.

**2023** — 17 tickets, 3 winners, -3,042.
- *side:* C 10t 2w -1,267; P 7t 1w -1,775
- *first exit:* STOP 5t 0w -2,150; TIME 10t 2w -800; TRAIL 2t 1w -91
- *entry window:* 13:00-13:30 7t 1w -1,209; 13:30-14:00 5t 1w -498; 14:00-14:30 3t 1w -494; 14:30-15:00 2t 0w -841
- *days:* E03.2 traded that day 17t 3w -3,042
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 11 (8 better, 3 worse, +604).
- *biggest changes:* 2023-06-22 P +1,104 → -129 (TRAIL); 2023-06-15 P -1,162 → -604 (STOP); 2023-03-16 P -889 → -468 (STOP); 2023-12-07 P -830 → -439 (STOP)
- *best:* 2023-07-27 P +79 (TIME); 2023-04-27 C +49 (TIME); 2023-03-16 C +38 (TRAIL)
- *worst:* 2023-06-15 P -604 (STOP); 2023-03-16 P -468 (STOP); 2023-12-07 P -439 (STOP)

**2024** — 20 tickets, 8 winners, +21,293.
- *side:* C 12t 3w +351; P 8t 5w +20,942
- *first exit:* STOP 7t 0w -2,935; STRUCTURE 1t 0w -185; TARGET 5t 5w +5,654; TARGET_BASE 1t 1w +18,429; TIME 6t 2w +331
- *entry window:* 13:00-13:30 5t 1w +663; 13:30-14:00 5t 1w +131; 14:00-14:30 5t 3w +836; 14:30-15:00 5t 3w +19,664
- *days:* E03.2 traded that day 20t 8w +21,293
- *vs E03.2:* added 1 (0w, -250), removed 0 (0w, +0), changed 10 (5 better, 5 worse, +5,963).
- *biggest changes:* 2024-03-28 P +11,771 → +18,429 (TARGET_BASE+HERO_TARGET); 2024-07-18 C +1,150 → +785 (TARGET); 2024-08-22 P +953 → +625 (TIME); 2024-02-29 C -471 → -729 (STOP)
- *best:* 2024-03-28 P +18,429 (TARGET_BASE+HERO_TARGET); 2024-02-22 C +1,313 (TARGET); 2024-08-08 P +1,267 (TARGET)
- *worst:* 2024-02-29 C -729 (STOP); 2024-01-11 P -647 (STOP); 2024-04-04 C -387 (STOP)

**2025** — 20 tickets, 13 winners, +3,922.
- *side:* C 11t 6w +926; P 9t 7w +2,996
- *first exit:* STOP 3t 0w -1,213; TARGET 1t 1w +691; TARGET_BASE 1t 1w +1,022; TIME 15t 11w +3,421
- *entry window:* 13:00-13:30 6t 4w +475; 13:30-14:00 6t 5w +1,918; 14:00-14:30 5t 4w +2,390; 14:30-15:00 3t 0w -862
- *days:* E03.2 traded that day 20t 13w +3,922
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 11 (3 better, 8 worse, -2,015).
- *biggest changes:* 2025-08-07 P +1,253 → +603 (TIME); 2025-06-12 P +966 → +459 (TIME); 2025-11-25 P +539 → +210 (TIME); 2025-01-02 C -205 → -459 (STOP)
- *best:* 2025-09-02 P +1,022 (TARGET_BASE+RUNNER_TRAIL); 2025-04-17 C +761 (TIME); 2025-08-21 P +722 (TIME)
- *worst:* 2025-11-11 C -491 (STOP); 2025-01-02 C -459 (STOP); 2025-02-06 C -325 (TIME)

## EN22 — FAIL

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | -4,069 | -4,045 | -4,504 | -4,211 | -1,162 | 16 | -3,645 |
| 2024 | +16,924 | +15,933 | -3,014 | +5,153 | -647 | 19 | +15,581 |
| 2025 | +5,901 | +5,371 | +109 | +4,049 | -550 | 20 | +5,937 |
| **Sum** | **+18,756** | **+17,260** | **-7,408** | | | 55 | +17,872 |

Checks failed: 2023_ordinary, 2023_adverse, 2025_ordinary, 2025_without_best.

**2023** — 16 tickets, 4 winners, -4,069.
- *side:* C 9t 2w -1,763; P 7t 2w -2,306
- *first exit:* STRUCTURE 4t 0w -2,996; TIME 11t 3w -1,111; TRAIL 1t 1w +38
- *entry window:* 13:00-13:30 6t 1w -1,304; 13:30-14:00 5t 1w -884; 14:00-14:30 3t 2w -228; 14:30-15:00 2t 0w -1,652
- *days:* E03.2 traded that day 16t 4w -4,069
- *vs E03.2:* added 0 (0w, +0), removed 1 (0w, -69), changed 5 (2 better, 3 worse, -493).
- *biggest changes:* 2023-06-22 P +1,104 → +241 (TIME); 2023-12-07 P -830 → -439 (STRUCTURE); 2023-08-31 P -343 → -195 (TIME); 2023-02-02 C -403 → -506 (STRUCTURE)
- *best:* 2023-06-22 P +241 (TIME); 2023-07-27 P +142 (TIME); 2023-04-27 C +49 (TIME)
- *worst:* 2023-06-15 P -1,162 (STRUCTURE); 2023-03-16 P -889 (STRUCTURE); 2023-02-02 C -506 (STRUCTURE)

**2024** — 19 tickets, 9 winners, +16,924.
- *side:* C 11t 4w +2,428; P 8t 5w +14,495
- *first exit:* STOP 1t 0w -183; STRUCTURE 3t 0w -1,476; TARGET 3t 3w +3,820; TARGET_BASE 4t 4w +15,346; TIME 7t 2w -113; TRAIL 1t 0w -471
- *entry window:* 13:00-13:30 5t 1w +528; 13:30-14:00 4t 1w -84; 14:00-14:30 5t 3w +1,624; 14:30-15:00 5t 4w +14,856
- *days:* E03.2 traded that day 19t 9w +16,924
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 4 (1 better, 3 worse, +1,343).
- *biggest changes:* 2024-09-12 C -325 → +1,463 (TARGET); 2024-04-04 C -387 → -568 (TIME); 2024-05-23 C -361 → -507 (STRUCTURE); 2024-04-25 C -305 → -422 (TIME)
- *best:* 2024-03-28 P +11,771 (TARGET_BASE+HERO_TARGET); 2024-09-12 C +1,463 (TARGET); 2024-08-08 P +1,377 (TARGET_BASE+RUNNER_TRAIL)
- *worst:* 2024-01-11 P -647 (STRUCTURE); 2024-04-04 C -568 (TIME); 2024-05-23 C -507 (STRUCTURE)

**2025** — 20 tickets, 13 winners, +5,901.
- *side:* C 11t 6w +929; P 9t 7w +4,972
- *first exit:* STRUCTURE 1t 0w -566; TARGET 1t 1w +691; TARGET_BASE 1t 1w +1,047; TIME 16t 11w +4,934; TRAIL 1t 0w -205
- *entry window:* 13:00-13:30 6t 4w +1,357; 13:30-14:00 6t 5w +2,575; 14:00-14:30 5t 4w +2,847; 14:30-15:00 3t 0w -877
- *days:* E03.2 traded that day 20t 13w +5,901
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 2 (1 better, 1 worse, -36).
- *biggest changes:* 2025-11-11 C -491 → -566 (STRUCTURE); 2025-03-06 C -478 → -439 (TIME)
- *best:* 2025-08-07 P +1,253 (TIME); 2025-09-02 P +1,047 (TARGET_BASE+RUNNER_TRAIL); 2025-06-12 P +966 (TIME)
- *worst:* 2025-11-11 C -566 (STRUCTURE); 2025-03-06 C -439 (TIME); 2025-02-06 C -325 (TIME)

## EN23 — FAIL

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | +2,815 | +3,035 | +0 | -901 | -711 | 7 | -3,645 |
| 2024 | -3,049 | -3,202 | -3,042 | -3,049 | -569 | 8 | +15,581 |
| 2025 | -1,176 | -1,065 | -1,904 | -2,669 | -708 | 10 | +5,937 |
| **Sum** | **-1,410** | **-1,232** | **-4,946** | | | 25 | +17,872 |

Checks failed: 2023_without_best_ge_0, 2024_positive, 2024_without_best_ge_0, 2025_positive, 2025_without_best_ge_0, 2025_above_null, adverse_sum_positive. Null median: {'2023': -229.85, '2024': -3500.39, '2025': -1102.72}.

**2023** — 7 tickets, 2 winners, +2,815.
- *side:* C 4t 0w -1,409; P 3t 2w +4,224
- *first exit:* STOP 4t 0w -1,802; TARGET 1t 1w +1,220; TARGET_BASE 1t 1w +3,715; TRAIL 1t 0w -319
- *entry window:* 15:00+ 7t 2w +2,815
- *days:* E03.2 empty day 6t 2w +3,201; E03.2 traded that day 1t 0w -387
- *vs E03.2:* added 7 (2w, +2,815), removed 17 (4w, -3,645), changed 0 (0 better, 0 worse, +0).
- *best:* 2023-02-23 P +3,715 (TARGET_BASE+FLAT_TIME); 2023-05-18 P +1,220 (TARGET); 2023-09-14 C -302 (STOP)
- *worst:* 2023-07-20 P -711 (STOP); 2023-07-06 C -402 (STOP); 2023-04-27 C -387 (STOP)

**2024** — 8 tickets, 0 winners, -3,049.
- *side:* C 2t 0w -883; P 6t 0w -2,166
- *first exit:* STOP 7t 0w -2,740; TRAIL 1t 0w -309
- *entry window:* 15:00+ 8t 0w -3,049
- *days:* E03.2 empty day 5t 0w -1,812; E03.2 traded that day 3t 0w -1,237
- *vs E03.2:* added 8 (0w, -3,049), removed 19 (8w, +15,581), changed 0 (0 better, 0 worse, +0).
- *best:* 2024-02-08 P -207 (STOP); 2024-03-07 P -295 (STOP); 2024-04-18 P -302 (STOP)
- *worst:* 2024-05-30 P -569 (STOP); 2024-06-20 P -484 (STOP); 2024-04-25 C -444 (STOP)

**2025** — 10 tickets, 2 winners, -1,176.
- *side:* C 3t 0w -1,607; P 7t 2w +431
- *first exit:* STOP 8t 0w -3,291; TARGET_BASE 2t 2w +2,115
- *entry window:* 15:00+ 10t 2w -1,176
- *days:* E03.2 empty day 9t 1w -2,669; E03.2 traded that day 1t 1w +1,493
- *vs E03.2:* added 10 (2w, -1,176), removed 20 (13w, +5,937), changed 0 (0 better, 0 worse, +0).
- *best:* 2025-08-21 P +1,493 (TARGET_BASE+FLAT_TIME); 2025-08-28 P +622 (TARGET_BASE+RUNNER_TRAIL); 2025-11-04 P -253 (STOP)
- *worst:* 2025-08-14 C -708 (STOP); 2025-06-05 C -461 (STOP); 2025-05-15 P -438 (STOP)

## EN24 — FAIL

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | -1,271 | -2,255 | -3,719 | -2,827 | -1,162 | 11 | -3,645 |
| 2024 | +3,595 | +2,945 | -2,582 | +2,218 | -647 | 15 | +15,581 |
| 2025 | +4,634 | +4,299 | -640 | +2,781 | -478 | 16 | +5,937 |
| **Sum** | **+6,958** | **+4,988** | **-6,941** | | | 42 | +17,872 |

Checks failed: 2024_ordinary, 2024_adverse, 2024_without_best, 2025_ordinary, 2025_adverse, 2025_without_best.

**2023** — 11 tickets, 3 winners, -1,271.
- *side:* C 7t 2w -935; P 4t 1w -336
- *first exit:* STOP 4t 0w -2,840; TIME 6t 2w +1,532; TRAIL 1t 1w +38
- *entry window:* 13:00-13:30 3t 1w -144; 13:30-14:00 3t 0w -854; 14:00-14:30 3t 2w +1,315; 14:30-15:00 2t 0w -1,587
- *days:* E03.2 traded that day 11t 3w -1,271
- *vs E03.2:* added 1 (0w, -850), removed 7 (1w, -2,649), changed 1 (1 better, 0 worse, +576).
- *biggest changes:* 2023-06-22 P +1,104 → +1,680 (TIME)
- *best:* 2023-06-22 P +1,680 (TIME); 2023-04-27 C +49 (TIME); 2023-03-16 C +38 (TRAIL)
- *worst:* 2023-06-15 P -1,162 (STOP); 2023-07-27 P -850 (STOP); 2023-08-17 C -426 (STOP)

**2024** — 15 tickets, 6 winners, +3,595.
- *side:* C 9t 2w +364; P 6t 4w +3,231
- *first exit:* STOP 6t 0w -2,207; TARGET 1t 1w +1,313; TARGET_BASE 3t 3w +3,576; TIME 4t 2w +1,384; TRAIL 1t 0w -471
- *entry window:* 13:00-13:30 4t 1w +1,035; 13:30-14:00 3t 1w +566; 14:00-14:30 5t 3w +1,741; 14:30-15:00 3t 1w +254
- *days:* E03.2 traded that day 15t 6w +3,595
- *vs E03.2:* added 0 (0w, +0), removed 4 (2w, +11,986), changed 0 (0 better, 0 worse, +0).
- *best:* 2024-08-08 P +1,377 (TARGET_BASE+RUNNER_TRAIL); 2024-02-22 C +1,313 (TARGET); 2024-07-18 C +1,150 (TARGET_BASE+RUNNER_TRAIL)
- *worst:* 2024-01-11 P -647 (STOP); 2024-02-29 C -471 (TRAIL); 2024-04-04 C -387 (STOP)

**2025** — 16 tickets, 10 winners, +4,634.
- *side:* C 10t 5w +706; P 6t 5w +3,927
- *first exit:* STOP 2t 0w -969; TARGET 1t 1w +691; TARGET_BASE 1t 1w +1,047; TIME 11t 8w +4,070; TRAIL 1t 0w -205
- *entry window:* 13:00-13:30 4t 2w +760; 13:30-14:00 6t 5w +2,649; 14:00-14:30 4t 3w +1,907; 14:30-15:00 2t 0w -683
- *days:* E03.2 traded that day 16t 10w +4,634
- *vs E03.2:* added 0 (0w, +0), removed 4 (3w, +1,303), changed 0 (0 better, 0 worse, +0).
- *best:* 2025-08-07 P +1,253 (TIME); 2025-09-02 P +1,047 (TARGET_BASE+RUNNER_TRAIL); 2025-06-12 P +966 (TIME)
- *worst:* 2025-11-11 C -491 (STOP); 2025-03-06 C -478 (STOP); 2025-02-06 C -325 (TIME)

## EN25 — FAIL

| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets | E03.2 ordinary |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | -3,359 | -3,661 | -4,127 | -4,102 | -1,142 | 16 | -3,645 |
| 2024 | +15,009 | +13,443 | +10,530 | +3,252 | -922 | 20 | +15,581 |
| 2025 | +6,124 | +5,631 | +2,585 | +4,584 | -458 | 20 | +5,937 |
| **Sum** | **+17,775** | **+15,414** | **+8,989** | | | 56 | +17,872 |

Checks failed: 2024_ordinary, 2024_adverse, 2024_without_best.

**2023** — 16 tickets, 5 winners, -3,359.
- *side:* C 9t 3w -1,143; P 7t 2w -2,216
- *first exit:* STOP 5t 0w -3,634; TARGET_BASE 1t 1w +860; TIME 9t 3w -636; TRAIL 1t 1w +51
- *entry window:* 13:00-13:30 6t 1w -1,467; 13:30-14:00 5t 2w -868; 14:00-14:30 3t 2w +525; 14:30-15:00 2t 0w -1,548
- *days:* E03.2 traded that day 16t 5w -3,359
- *vs E03.2:* added 0 (0w, +0), removed 1 (0w, -361), changed 15 (12 better, 3 worse, -75).
- *biggest changes:* 2023-06-22 P +1,104 → +860 (TARGET_BASE+RUNNER_TRAIL); 2023-02-09 C -0 → +58 (TIME); 2023-07-27 P +142 → +103 (TIME); 2023-08-31 P -343 → -304 (TIME)
- *best:* 2023-06-22 P +860 (TARGET_BASE+RUNNER_TRAIL); 2023-07-27 P +103 (TIME); 2023-04-27 C +71 (TIME)
- *worst:* 2023-06-15 P -1,142 (STOP); 2023-03-16 P -869 (STOP); 2023-12-07 P -830 (STOP)

**2024** — 20 tickets, 8 winners, +15,009.
- *side:* C 11t 3w +1,212; P 9t 5w +13,798
- *first exit:* STOP 6t 0w -2,988; STRUCTURE 1t 0w -316; TARGET 2t 2w +2,409; TARGET_BASE 4t 4w +15,411; TIME 5t 2w +988; TRAIL 2t 0w -495
- *entry window:* 13:00-13:30 5t 1w +733; 13:30-14:00 5t 1w -669; 14:00-14:30 5t 3w +1,737; 14:30-15:00 5t 3w +13,208
- *days:* E03.2 empty day 1t 0w -922; E03.2 traded that day 19t 8w +15,931
- *vs E03.2:* added 1 (0w, -922), removed 0 (0w, +0), changed 19 (12 better, 7 worse, +351).
- *biggest changes:* 2024-07-18 C -183 → -11 (TRAIL); 2024-05-09 P +1,049 → +1,160 (TARGET_BASE+RUNNER_TRAIL); 2024-08-22 P +953 → +1,018 (TIME); 2024-07-18 C +1,150 → +1,111 (TARGET_BASE+RUNNER_TRAIL)
- *best:* 2024-03-28 P +11,758 (TARGET_BASE+HERO_TARGET); 2024-08-08 P +1,383 (TARGET_BASE+RUNNER_TRAIL); 2024-02-22 C +1,332 (TARGET)
- *worst:* 2024-06-06 P -922 (STOP); 2024-01-11 P -666 (STOP); 2024-02-29 C -484 (TRAIL)

**2025** — 20 tickets, 14 winners, +6,124.
- *side:* C 11t 7w +1,276; P 9t 7w +4,848
- *first exit:* STOP 2t 0w -937; TARGET 1t 1w +678; TARGET_BASE 2t 2w +2,124; TIME 14t 10w +4,250; TRAIL 1t 1w +9
- *entry window:* 13:00-13:30 6t 4w +1,106; 13:30-14:00 6t 5w +2,692; 14:00-14:30 5t 4w +2,990; 14:30-15:00 3t 1w -663
- *days:* E03.2 traded that day 20t 14w +6,124
- *vs E03.2:* added 0 (0w, +0), removed 0 (0w, +0), changed 17 (11 better, 6 worse, +188).
- *biggest changes:* 2025-08-07 P +1,253 → +953 (TARGET_BASE+RUNNER_TRAIL); 2025-01-02 C -205 → +9 (TRAIL); 2025-09-02 P +1,047 → +1,170 (TARGET_BASE+RUNNER_TRAIL); 2025-08-21 P +941 → +999 (TIME)
- *best:* 2025-09-02 P +1,170 (TARGET_BASE+RUNNER_TRAIL); 2025-08-21 P +999 (TIME); 2025-06-12 P +966 (TIME)
- *worst:* 2025-11-11 C -478 (STOP); 2025-03-06 C -458 (STOP); 2025-02-06 C -325 (TIME)

## Slot diagnostics

```json
{
 "EN11": {
  "saved": 17,
  "saved_rs": 2133.38,
  "cut": 9,
  "cut_rs": -5300.3,
  "stopped_would_recover": 2,
  "their_now": -796.21,
  "their_control": 1714.45,
  "first_exits": {
   "STOP_FAST": 19,
   "TRAIL_FAST": 5,
   "STRUCTURE_FAST": 2
  }
 },
 "EN22": {
  "saved": 4,
  "saved_rs": 2365.71,
  "cut": 7,
  "cut_rs": -1551.28,
  "stopped_would_recover": 0,
  "their_now": 0.0,
  "their_control": 0.0,
  "first_exits": {
   "STRUCTURE": 4,
   "TIME": 6,
   "TARGET": 1
  }
 },
 "EN12": {
  "split_tickets": 4,
  "covered": 4,
  "lots_sold_at_2x": 5,
  "control_lots_sold_at_2x": 5,
  "runner_paths": {
   "TARGET_BASE+HERO_TARGET": {
    "tickets": 1,
    "winners": 1,
    "net": 11770.72
   },
   "TARGET_BASE+RUNNER_TRAIL": {
    "tickets": 3,
    "winners": 3,
    "net": 3575.65
   }
  },
  "delta_on_split_tickets": 0.0,
  "control_split_tickets": 5,
  "control_covered": 4
 },
 "EN20": {
  "retries": 1,
  "retry_winners": 1,
  "retry_net": 785.18
 },
 "EN21": {
  "added": 9,
  "added_winners": 6,
  "added_net": 19796.96,
  "added_control_net": 16016.35,
  "half_only": 23,
  "half_only_net": 1570.83,
  "half_only_control_net": 800.41
 },
 "EN25": {
  "missed": 3,
  "missed_in_control": 1,
  "missed_control_winners": 0,
  "missed_control_net": -361.07
 }
}
```

## EN11 1-second measurement

```json
{
 "entries": 94,
 "stopped_before_clock": 42,
 "contract_days": 10,
 "after": {
  "1s": {
   "median": 0.6366,
   "mean": 0.6335
  },
  "3s": {
   "median": 0.6353,
   "mean": 0.6328
  },
  "10s": {
   "median": 0.6351,
   "mean": 0.6302
  },
  "60s": {
   "median": 0.609,
   "mean": 0.6213
  }
 },
 "minute_cadence": {
  "median": 0.6067,
  "mean": 0.6373
 },
 "minute_never_triggered": 8,
 "recovered_within_60s": 16,
 "hold_to_clock_on_stopped": {
  "median": 0.5594,
  "mean": 0.6566
 },
 "fast1_minus_minute": -0.0038,
 "fast10_minus_minute": -0.0071
}
```

## EN15 breadth — FAIL

```json
{
 "names_present": 50,
 "sessions": 143,
 "expiry_sessions": 30,
 "bars": 1144,
 "all": {
  "n": 280,
  "breadth_hit": 0.4536,
  "index_only_hit": 0.4536,
  "disagreements": 0,
  "disagreement_breadth_hit": null,
  "mean_next_signed_bp": -0.134
 },
 "expiry_days": {
  "n": 61,
  "breadth_hit": 0.3934,
  "index_only_hit": 0.3934,
  "disagreements": 0,
  "disagreement_breadth_hit": null,
  "mean_next_signed_bp": -5.874
 },
 "verdict": "FAIL"
}
```

## EN16 next-expiry confirmation — FAIL

```json
{
 "confirmed": {
  "n": 155,
  "hit": 0.471,
  "mean_move": 3.82,
  "trades": 131,
  "mean_pnl": -67.85,
  "sum_pnl": -8887.73,
  "by_index": {
   "NIFTY": {
    "n": 78,
    "hit": 0.5
   },
   "SENSEX": {
    "n": 77,
    "hit": 0.4416
   }
  }
 },
 "unconfirmed": {
  "n": 7,
  "hit": 0.2857,
  "mean_move": -25.35,
  "trades": 7,
  "mean_pnl": -138.1,
  "sum_pnl": -966.7,
  "by_index": {
   "NIFTY": {
    "n": 4,
    "hit": 0.25
   },
   "SENSEX": {
    "n": 3,
    "hit": 0.3333
   }
  }
 },
 "unavailable": {
  "n": 0,
  "hit": null,
  "mean_move": null,
  "trades": 0,
  "mean_pnl": null,
  "sum_pnl": 0.0,
  "by_index": {
   "NIFTY": {
    "n": 0,
    "hit": null
   },
   "SENSEX": {
    "n": 0,
    "hit": null
   }
  }
 }
}
```

## EN18 strike by real cost — FAIL

```json
{
 "by_index": {
  "NIFTY": {
   "n": 1705,
   "alt_chosen": 0,
   "sessions": 9,
   "fund_rule": -76.49,
   "fund_base": -76.49,
   "one_rule": -57.64,
   "one_base": -57.64,
   "cost_rule": 0.06265,
   "cost_base": 0.06265,
   "sessions_rule_ge_base": "9"
  },
  "SENSEX": {
   "n": 1412,
   "alt_chosen": 0,
   "sessions": 10,
   "fund_rule": -74.04,
   "fund_base": -74.04,
   "one_rule": -65.25,
   "one_base": -65.25,
   "cost_rule": 0.05073,
   "cost_base": 0.05073,
   "sessions_rule_ge_base": "10"
  }
 },
 "sessions": 19,
 "sessions_rule_ge_base": 19,
 "verdict": "FAIL",
 "n_rows": 3737
}
```

