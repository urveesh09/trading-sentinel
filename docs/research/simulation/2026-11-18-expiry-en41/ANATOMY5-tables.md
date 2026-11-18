# EN41–EN55 tables (rendered from results5.json and anatomy5.json by render5.py)

Fixed-cap: each expiry on its own (full day reserve, Rs 30,000 cash, no brakes). Wallet: one continuous Rs 30,000 book with brakes on the trading high-water and 50% profit sweeps (E032_25k: Rs 25,000, no sweeps). PF = profit factor of expiry results.

Sessions: {"NIFTY": 197, "SENSEX": 63}

## Status

```json
{
 "EN44": "FAIL",
 "EN45": "FAIL",
 "EN49": "INCONCLUSIVE",
 "EN51": "FAIL",
 "EN52": "FAIL",
 "EN54": "FAIL",
 "EN46": "FAIL",
 "EN47": "FAIL",
 "EN50": "INCONCLUSIVE",
 "EN53": "FAIL",
 "EN41": "DATA_UNAVAILABLE",
 "EN42": "DATA_UNAVAILABLE",
 "EN43": "DATA_UNAVAILABLE",
 "EN48": "INCONCLUSIVE",
 "EN55": "FORWARD-ONLY"
}
```

## Tests (one-sided sign-flip permutation, Holm across the ten primaries)

```json
{
 "raw": {
  "EN44": 0.9862,
  "EN45": 1.0,
  "EN49": 1.0,
  "EN51": 0.9045,
  "EN52": 0.395,
  "EN54": 0.9192,
  "EN46": 0.7318,
  "EN47": 0.8387,
  "EN50": 1.0,
  "EN53": 0.7867
 },
 "holm": {
  "EN52": 1.0,
  "EN46": 1.0,
  "EN53": 1.0,
  "EN47": 1.0,
  "EN51": 1.0,
  "EN54": 1.0,
  "EN44": 1.0,
  "EN45": 1.0,
  "EN49": 1.0,
  "EN50": 1.0
 }
}
```

## E032_25k — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +14,275 | +11,586 | -12,347 | +652 | -1,281 | 66 / 58 | 1.993 | 20,877 (P -4,123) | 0 | 146 |
| SENSEX | +2,449 | +1,921 | -4,599 | -4,089 | -1,125 | 12 / 11 | 1.51 | 26,987 (P +1,987) | 0 | 0 |

**NIFTY**: 66 tickets, 27 winners, +14,275. By year: {"2023": -3069.4, "2024": 15580.74, "2025": 5936.81, "2026": -4172.95}
- *side:* C 37t 12w -569; P 29t 15w +14,844
- *first exit:* STOP 18t 0w -10,810; STRUCTURE 2t 0w -579; TARGET 3t 3w +3,048; TARGET_BASE 5t 5w +16,393; TIME 34t 18w +7,046; TRAIL 4t 1w -823
- *window:* 12:30-13:30 18t 6w -28; 13:30-14:30 35t 18w +6,274; 14:30-15:00 13t 3w +8,029
- *vs control:* added 0 (+0), removed 0 (+0), changed 0 (0 better, 0 worse, +0)
- *best:* 2024-03-28 P +11,771 (TARGET_BASE+HERO_TARGET); 2023-06-22 P +1,680 (TIME); 2024-08-08 P +1,377 (TARGET_BASE+RUNNER_TRAIL)
- *worst:* 2023-06-15 P -1,162 (STOP); 2026-04-21 P -1,025 (STOP); 2026-05-26 P -889 (STOP)

**SENSEX**: 12 tickets, 3 winners, +2,449. By year: {"2025": 4844.31, "2026": -2395.13}
- *side:* C 5t 0w -2,415; P 7t 3w +4,864
- *first exit:* STOP 6t 0w -4,071; STRUCTURE 1t 0w -454; TARGET_BASE 1t 1w +5,255; TIME 4t 2w +1,719
- *window:* 12:30-13:30 2t 0w -637; 13:30-14:30 5t 3w +6,576; 14:30-15:00 5t 0w -3,490
- *vs control:* added 0 (+0), removed 0 (+0), changed 0 (0 better, 0 worse, +0)
- *best:* 2025-11-13 P +5,255 (TARGET_BASE+RUNNER_TRAIL); 2026-06-25 P +1,284 (TIME); 2025-08-26 P +714 (TIME)
- *worst:* 2025-10-30 P -1,125 (STOP); 2026-03-12 P -627 (STOP); 2026-01-22 C -600 (STOP)

## E032_30k — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +14,275 | +11,586 | -12,347 | +652 | -1,281 | 66 / 58 | 1.993 | 25,877 (P -4,123) | 0 | 146 |
| SENSEX | +2,449 | +1,921 | -4,599 | -4,089 | -1,125 | 12 / 11 | 1.51 | 29,565 (P +1,987) | 2,422 | 0 |

**NIFTY**: 66 tickets, 27 winners, +14,275. By year: {"2023": -3069.4, "2024": 15580.74, "2025": 5936.81, "2026": -4172.95}
- *side:* C 37t 12w -569; P 29t 15w +14,844
- *first exit:* STOP 18t 0w -10,810; STRUCTURE 2t 0w -579; TARGET 3t 3w +3,048; TARGET_BASE 5t 5w +16,393; TIME 34t 18w +7,046; TRAIL 4t 1w -823
- *window:* 12:30-13:30 18t 6w -28; 13:30-14:30 35t 18w +6,274; 14:30-15:00 13t 3w +8,029
- *vs control:* added 0 (+0), removed 0 (+0), changed 0 (0 better, 0 worse, +0)
- *best:* 2024-03-28 P +11,771 (TARGET_BASE+HERO_TARGET); 2023-06-22 P +1,680 (TIME); 2024-08-08 P +1,377 (TARGET_BASE+RUNNER_TRAIL)
- *worst:* 2023-06-15 P -1,162 (STOP); 2026-04-21 P -1,025 (STOP); 2026-05-26 P -889 (STOP)

**SENSEX**: 12 tickets, 3 winners, +2,449. By year: {"2025": 4844.31, "2026": -2395.13}
- *side:* C 5t 0w -2,415; P 7t 3w +4,864
- *first exit:* STOP 6t 0w -4,071; STRUCTURE 1t 0w -454; TARGET_BASE 1t 1w +5,255; TIME 4t 2w +1,719
- *window:* 12:30-13:30 2t 0w -637; 13:30-14:30 5t 3w +6,576; 14:30-15:00 5t 0w -3,490
- *vs control:* added 0 (+0), removed 0 (+0), changed 0 (0 better, 0 worse, +0)
- *best:* 2025-11-13 P +5,255 (TARGET_BASE+RUNNER_TRAIL); 2026-06-25 P +1,284 (TIME); 2025-08-26 P +714 (TIME)
- *worst:* 2025-10-30 P -1,125 (STOP); 2026-03-12 P -627 (STOP); 2026-01-22 C -600 (STOP)

## E032_sym — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +7,174 | +5,440 | -8,277 | +11 | -793 | 68 / 59 | 1.654 | 25,755 (P -4,245) | 0 | 86 |
| SENSEX | -759 | -1,029 | -2,854 | -3,075 | -600 | 11 / 11 | 0.777 | 28,429 (P -759) | 812 | 0 |

**NIFTY**: 68 tickets, 27 winners, +7,174. By year: {"2023": -2570.38, "2024": 8897.97, "2025": 3528.74, "2026": -2682.22}
- *side:* C 38t 12w -819; P 30t 15w +7,993
- *first exit:* STOP 19t 0w -7,845; STRUCTURE 2t 0w -579; TARGET 6t 6w +6,531; TARGET_BASE 2t 2w +7,000; TIME 35t 18w +2,890; TRAIL 4t 1w -823
- *window:* 12:30-13:30 19t 6w -364; 13:30-14:30 36t 18w +3,387; 14:30-15:00 13t 3w +4,151
- *vs control:* added 2 (-432), removed 0 (+0), changed 29 (14 better, 15 worse, -6,669)
- *best:* 2024-03-28 P +5,850 (TARGET_BASE+HERO_TARGET); 2024-02-22 C +1,313 (TARGET); 2024-08-08 P +1,267 (TARGET)
- *worst:* 2023-06-15 P -604 (STOP); 2026-04-21 P -536 (STOP); 2026-02-24 C -519 (STOP)

**SENSEX**: 11 tickets, 3 winners, -759. By year: {"2025": 1624.85, "2026": -2383.82}
- *side:* C 5t 0w -2,415; P 6t 3w +1,656
- *first exit:* STOP 6t 0w -3,063; STRUCTURE 1t 0w -250; TARGET 1t 1w +1,698; TIME 3t 2w +857
- *window:* 12:30-13:30 1t 0w -250; 13:30-14:30 5t 3w +1,973; 14:30-15:00 5t 0w -2,482
- *vs control:* added 0 (+0), removed 1 (-184), changed 6 (3 better, 3 worse, -3,392)
- *best:* 2025-11-13 P +1,698 (TARGET); 2026-06-25 P +618 (TIME); 2025-08-26 P +333 (TIME)
- *worst:* 2026-01-22 C -600 (STOP); 2026-03-05 C -596 (STOP); 2026-05-21 C -582 (STOP)

## EN44 — FAIL

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | -4,298 | -5,214 | -3,511 | -5,824 | -513 | 43 / 41 | 0.417 | 26,801 (P -3,199) | 0 | 0 |
| SENSEX | +0 | +0 | +0 | +0 | +0 | 0 / 0 | None | 30,000 (P +0) | 0 | 0 |

NIFTY: FAIL; failed checks: ordinary_positive, adverse_positive, without_top2_positive, above_null; support {'tickets': 43, 'expiries': 41}
SENSEX: DATA_UNAVAILABLE; failed checks: none

**NIFTY**: 43 tickets, 10 winners, -4,298. By year: {"2023": -983.59, "2024": -1571.52, "2025": -1742.63, "2026": 0.0}
- *side:* C 15t 3w -2,951; P 28t 7w -1,347
- *first exit:* FSTOP 18t 0w -3,285; STOP 7t 0w -2,912; TARGET 1t 1w +801; TIME 17t 9w +1,099
- *window:* 09:45-11:00 38t 8w -4,333; 11:00-12:30 5t 2w +35
- *vs control:* added 43 (-4,298), removed 68 (+7,174), changed 0 (0 better, 0 worse, +0)
- *best:* 2025-10-14 P +801 (TARGET); 2024-09-19 P +725 (TIME); 2023-03-09 P +454 (TIME)
- *worst:* 2024-01-18 C -491 (STOP); 2025-04-17 C -488 (STOP); 2025-03-20 P -452 (STOP)

**SENSEX**: 0 tickets, 0 winners, +0. By year: {"2025": 0.0, "2026": 0.0}
- *side:* 
- *first exit:* 
- *window:* 
- *vs control:* added 0 (+0), removed 11 (-759), changed 0 (0 better, 0 worse, +0)
- *best:* 
- *worst:* 

## EN44_now_diag — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | -5,987 | -9,362 | -8,318 | -7,669 | -622 | 112 / 102 | 0.619 | 25,982 (P -4,018) | 0 | 92 |
| SENSEX | +0 | +0 | +0 | +0 | +0 | 0 / 0 | None | 30,000 (P +0) | 0 | 0 |

**NIFTY**: 112 tickets, 33 winners, -5,987. By year: {"2023": -2123.47, "2024": -3000.36, "2025": -863.51, "2026": 0.0}
- *side:* C 52t 14w -4,764; P 60t 19w -1,223
- *first exit:* FSTOP 35t 0w -6,542; STOP 12t 0w -4,636; TARGET 3t 3w +2,441; TIME 60t 28w +2,660; TRAIL 2t 2w +89
- *window:* 09:45-11:00 101t 32w -4,117; 11:00-12:30 11t 1w -1,870
- *vs control:* added 112 (-5,987), removed 66 (+14,275), changed 0 (0 better, 0 worse, +0)
- *best:* 2023-08-10 P +856 (TARGET); 2025-09-02 C +826 (TIME); 2024-11-07 P +804 (TARGET)
- *worst:* 2023-11-16 C -507 (STOP); 2023-03-16 C -504 (STOP); 2025-04-09 P -410 (STOP)

**SENSEX**: 0 tickets, 0 winners, +0. By year: {"2025": 0.0, "2026": 0.0}
- *side:* 
- *first exit:* 
- *window:* 
- *vs control:* added 0 (+0), removed 12 (+2,449), changed 0 (0 better, 0 worse, +0)
- *best:* 
- *worst:* 

## EN44_noon_diag — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | -3,487 | -4,663 | -5,562 | -5,834 | -465 | 63 / 62 | 0.618 | 26,211 (P -3,781) | 8 | 0 |
| SENSEX | +233 | -14 | -461 | -633 | -317 | 12 / 12 | 1.22 | 30,032 (P +233) | 201 | 0 |

**NIFTY**: 63 tickets, 20 winners, -3,487. By year: {"2023": -2618.23, "2024": -501.3, "2025": 633.07, "2026": -1000.84}
- *side:* C 27t 10w -558; P 36t 10w -2,929
- *first exit:* FSTOP 32t 1w -6,498; STOP 4t 0w -1,485; TARGET 2t 2w +2,347; TIME 22t 15w +2,030; TRAIL 3t 2w +118
- *window:* 12:30-13:30 52t 16w -3,748; 13:30-14:30 11t 4w +261
- *vs control:* added 63 (-3,487), removed 66 (+14,275), changed 0 (0 better, 0 worse, +0)
- *best:* 2025-01-30 P +1,361 (TARGET); 2025-09-23 C +986 (TARGET); 2026-01-13 P +529 (TIME)
- *worst:* 2023-09-07 C -465 (STOP); 2023-10-26 P -419 (STOP); 2024-11-07 P -380 (FSTOP)

**SENSEX**: 12 tickets, 4 winners, +233. By year: {"2025": 63.67, "2026": 169.63}
- *side:* C 8t 2w +116; P 4t 2w +117
- *first exit:* FSTOP 5t 0w -694; STOP 1t 0w -317; TIME 6t 4w +1,245
- *window:* 12:30-13:30 10t 3w -49; 13:30-14:30 2t 1w +282
- *vs control:* added 12 (+233), removed 12 (+2,449), changed 0 (0 better, 0 worse, +0)
- *best:* 2026-08-20 C +489 (TIME); 2025-10-09 C +377 (TIME); 2025-08-05 P +216 (TIME)
- *worst:* 2026-02-12 C -317 (STOP); 2025-12-04 P -217 (FSTOP); 2025-08-12 C -188 (FSTOP)

## EN45 — FAIL

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | -10,898 | -14,180 | -14,599 | -11,983 | -619 | 136 / 95 | 0.182 | 26,271 (P -3,437) | 291 | 69 |
| SENSEX | -2,270 | -2,816 | -2,635 | -2,940 | -553 | 24 / 18 | 0.314 | 27,356 (P -2,644) | 0 | 0 |

NIFTY: FAIL; failed checks: ordinary_positive, adverse_positive, without_top2_positive, above_null; support {'tickets': 136, 'expiries': 95}
SENSEX: INCONCLUSIVE; failed checks: ordinary_positive, adverse_positive, without_top2_positive, above_null; support {'tickets': 24, 'expiries': 18}

**NIFTY**: 136 tickets, 34 winners, -10,898. By year: {"2023": -2274.53, "2024": -2516.05, "2025": -4745.79, "2026": -1361.83}
- *side:* C 69t 16w -5,072; P 67t 18w -5,826
- *first exit:* FSTOP 38t 0w -7,748; FTARGET 32t 17w +1,551; STOP 1t 0w -439; TIME 65t 17w -4,262
- *window:* 09:45-11:00 43t 10w -3,094; 11:00-12:30 44t 8w -3,960; 12:30-13:30 31t 9w -1,824; 13:30-14:30 17t 7w -1,870; 14:30-15:00 1t 0w -150
- *vs control:* added 136 (-10,898), removed 68 (+7,174), changed 0 (0 better, 0 worse, +0)
- *best:* 2024-06-06 C +541 (TIME); 2023-04-06 C +502 (TIME); 2023-02-02 P +496 (FTARGET)
- *worst:* 2023-08-10 C -439 (STOP); 2025-09-02 C -400 (TIME); 2024-06-06 P -390 (FSTOP)

**SENSEX**: 24 tickets, 8 winners, -2,270. By year: {"2025": -1331.55, "2026": -938.85}
- *side:* C 14t 4w -905; P 10t 4w -1,366
- *first exit:* FSTOP 4t 1w -481; FTARGET 9t 5w +513; STOP 6t 0w -2,418; TIME 5t 2w +115
- *window:* 11:00-12:30 6t 3w +497; 12:30-13:30 11t 5w -849; 13:30-14:30 6t 0w -1,497; 14:30-15:00 1t 0w -422
- *vs control:* added 24 (-2,270), removed 11 (-759), changed 0 (0 better, 0 worse, +0)
- *best:* 2025-12-04 C +433 (FTARGET); 2026-05-07 P +309 (TIME); 2026-07-23 P +233 (FTARGET)
- *worst:* 2026-06-04 P -481 (STOP); 2025-08-19 P -422 (STOP); 2026-03-12 P -410 (STOP)

## EN45_now_diag — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | -17,079 | -24,167 | -31,519 | -18,501 | -703 | 265 / 150 | 0.226 | 26,121 (P -3,711) | 168 | 147 |
| SENSEX | -872 | -2,275 | -6,482 | -2,672 | -649 | 62 / 38 | 0.82 | 29,161 (P -189) | 650 | 0 |

**NIFTY**: 265 tickets, 65 winners, -17,079. By year: {"2023": -4607.65, "2024": -5703.55, "2025": -4851.98, "2026": -1915.8}
- *side:* C 147t 39w -9,407; P 118t 26w -7,672
- *first exit:* FSTOP 155t 2w -21,970; FTARGET 22t 18w +2,812; STOP 1t 0w -478; TARGET 1t 1w +921; TIME 86t 44w +1,636
- *window:* 09:45-11:00 132t 32w -8,172; 11:00-12:30 73t 17w -5,173; 12:30-13:30 35t 7w -3,170; 13:30-14:30 25t 9w -564
- *vs control:* added 265 (-17,079), removed 66 (+14,275), changed 0 (0 better, 0 worse, +0)
- *best:* 2026-02-03 C +921 (TARGET); 2024-05-16 P +366 (TIME); 2023-05-11 P +339 (FTARGET)
- *worst:* 2023-10-05 C -478 (STOP); 2025-12-09 P -351 (FSTOP); 2026-03-24 P -319 (FSTOP)

**SENSEX**: 62 tickets, 20 winners, -872. By year: {"2025": 1073.37, "2026": -1944.87}
- *side:* C 32t 9w -577; P 30t 11w -295
- *first exit:* FSTOP 29t 1w -3,958; FTARGET 15t 11w +3,051; STOP 1t 0w -384; TIME 17t 8w +419
- *window:* 11:00-12:30 20t 8w +1,145; 12:30-13:30 27t 6w -2,154; 13:30-14:30 15t 6w +138
- *vs control:* added 62 (-872), removed 12 (+2,449), changed 0 (0 better, 0 worse, +0)
- *best:* 2025-11-13 C +657 (TIME); 2026-04-23 P +598 (FTARGET); 2025-11-06 C +486 (FTARGET)
- *worst:* 2026-06-04 P -384 (STOP); 2026-03-12 P -364 (TIME); 2026-05-07 P -347 (FSTOP)

## EN46 — FAIL

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +1,202 | +663 | -2,496 | -1,355 | -793 | 28 / 27 | 1.225 | 29,591 (P +1,202) | 1,611 | 0 |
| SENSEX | -414 | -633 | -2,520 | -2,730 | -600 | 9 / 9 | 0.865 | 28,774 (P -414) | 812 | 0 |

NIFTY: FAIL; failed checks: ordinary, adverse, without_top2
SENSEX: FAIL; failed checks: adverse_positive

**NIFTY**: 28 tickets, 12 winners, +1,202. By year: {"2023": -480.57, "2024": 1416.13, "2025": 2041.61, "2026": -1774.8}
- *side:* C 16t 5w -317; P 12t 7w +1,520
- *first exit:* STOP 11t 0w -4,653; STRUCTURE 1t 0w -256; TARGET 3t 3w +3,529; TIME 10t 8w +2,935; TRAIL 3t 1w -352
- *window:* 13:30-14:30 21t 11w +2,304; 14:30-15:00 7t 1w -1,102
- *vs control:* added 2 (-116), removed 42 (+5,856), changed 0 (0 better, 0 worse, +0)
- *best:* 2024-02-22 C +1,313 (TARGET); 2024-05-09 P +1,244 (TARGET); 2025-09-02 P +972 (TARGET)
- *worst:* 2026-04-21 P -536 (STOP); 2025-11-11 C -491 (STOP); 2025-03-06 C -478 (STOP)

**SENSEX**: 9 tickets, 3 winners, -414. By year: {"2025": 1624.85, "2026": -2038.84}
- *side:* C 4t 0w -2,320; P 5t 3w +1,906
- *first exit:* STOP 6t 0w -3,063; TARGET 1t 1w +1,698; TIME 2t 2w +952
- *window:* 13:30-14:30 4t 3w +2,068; 14:30-15:00 5t 0w -2,482
- *vs control:* added 0 (+0), removed 2 (-345), changed 0 (0 better, 0 worse, +0)
- *best:* 2025-11-13 P +1,698 (TARGET); 2026-06-25 P +618 (TIME); 2025-08-26 P +333 (TIME)
- *worst:* 2026-01-22 C -600 (STOP); 2026-03-05 C -596 (STOP); 2026-05-21 C -582 (STOP)

## EN46_zero_diag — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +0 | +0 | +0 | +0 | +0 | 0 / 0 | None | 30,000 (P +0) | 0 | 0 |
| SENSEX | +0 | +0 | +0 | +0 | +0 | 0 / 0 | None | 30,000 (P +0) | 0 | 0 |

**NIFTY**: 0 tickets, 0 winners, +0. By year: {"2023": 0.0, "2024": 0.0, "2025": 0.0, "2026": 0.0}
- *side:* 
- *first exit:* 
- *window:* 
- *vs control:* added 0 (+0), removed 66 (+14,275), changed 0 (0 better, 0 worse, +0)
- *best:* 
- *worst:* 

**SENSEX**: 0 tickets, 0 winners, +0. By year: {"2025": 0.0, "2026": 0.0}
- *side:* 
- *first exit:* 
- *window:* 
- *vs control:* added 0 (+0), removed 12 (+2,449), changed 0 (0 better, 0 worse, +0)
- *best:* 
- *worst:* 

## EN36_sym_diag — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +1,538 | +554 | -3,834 | -819 | -478 | 35 / 34 | 1.249 | 30,358 (P +1,538) | 1,180 | 0 |
| SENSEX | -27 | -239 | -1,633 | -1,992 | -600 | 8 / 8 | 0.988 | 29,132 (P -27) | 840 | 0 |

**NIFTY**: 35 tickets, 12 winners, +1,538. By year: {"2023": -682.54, "2024": 1038.25, "2025": 1829.74, "2026": -647.77}
- *side:* C 22t 5w -678; P 13t 7w +2,216
- *first exit:* STOP 11t 0w -4,280; TARGET 4t 4w +4,596; TIME 18t 8w +1,878; TRAIL 2t 0w -657
- *window:* 12:30-13:30 7t 1w +311; 13:30-14:30 21t 10w +2,490; 14:30-15:00 7t 1w -1,264
- *vs control:* added 2 (-284), removed 33 (+11,099), changed 13 (6 better, 7 worse, -1,354)
- *best:* 2024-02-22 C +1,313 (TARGET); 2024-08-08 P +1,267 (TARGET); 2024-06-27 C +1,044 (TARGET)
- *worst:* 2025-03-06 C -478 (STOP); 2024-01-11 P -478 (STOP); 2024-02-29 C -471 (TRAIL)

**SENSEX**: 8 tickets, 3 winners, -27. By year: {"2025": 1680.11, "2026": -1707.6}
- *side:* C 3t 0w -1,738; P 5t 3w +1,711
- *first exit:* STOP 4t 0w -2,075; STRUCTURE 1t 0w -250; TARGET 1t 1w +1,347; TIME 2t 2w +952
- *window:* 12:30-13:30 1t 0w -250; 13:30-14:30 3t 3w +2,298; 14:30-15:00 4t 0w -2,075
- *vs control:* added 1 (+1,347), removed 5 (+3,270), changed 4 (2 better, 2 worse, -553)
- *best:* 2025-11-13 P +1,347 (TARGET); 2026-06-25 P +618 (TIME); 2025-08-26 P +333 (TIME)
- *worst:* 2026-01-22 C -600 (STOP); 2026-03-05 C -596 (STOP); 2026-04-30 C -543 (STOP)

## EN47 — FAIL

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | -1,071 | -1,146 | -792 | -1,204 | -477 | 4 / 4 | 0.11 | 28,862 (P -1,071) | 66 | 0 |
| SENSEX | -543 | -563 | +0 | -543 | -543 | 1 / 1 | 0.0 | 29,457 (P -543) | 0 | 0 |

NIFTY: FAIL; failed checks: ordinary, adverse, without_top2, adverse_positive
SENSEX: FAIL; failed checks: adverse_positive

**NIFTY**: 4 tickets, 1 winners, -1,071. By year: {"2023": 132.91, "2024": 0.0, "2025": -1204.02, "2026": 0.0}
- *side:* C 1t 0w -477; P 3t 1w -594
- *first exit:* STOP 3t 0w -1,204; TIME 1t 1w +133
- *window:* 13:30-14:30 1t 1w +133; 14:30-15:00 3t 0w -1,204
- *vs control:* added 4 (-1,071), removed 68 (+7,174), changed 0 (0 better, 0 worse, +0)
- *best:* 2023-10-19 P +133 (TIME); 2025-03-13 P -263 (STOP); 2025-03-27 P -464 (STOP)
- *worst:* 2025-04-17 C -477 (STOP); 2025-03-27 P -464 (STOP); 2025-03-13 P -263 (STOP)

**SENSEX**: 1 tickets, 0 winners, -543. By year: {"2025": 0.0, "2026": -542.67}
- *side:* C 1t 0w -543
- *first exit:* STOP 1t 0w -543
- *window:* 14:30-15:00 1t 0w -543
- *vs control:* added 0 (+0), removed 10 (-216), changed 0 (0 better, 0 worse, +0)
- *best:* 2026-04-30 C -543 (STOP)
- *worst:* 2026-04-30 C -543 (STOP)

## EN47_native1_diag — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +2,649 | +1,138 | -7,880 | +91 | -578 | 69 / 59 | 1.299 | 30,165 (P +2,649) | 2,484 | 0 |
| SENSEX | -949 | -1,203 | -2,854 | -3,265 | -600 | 11 / 11 | 0.721 | 28,333 (P -949) | 717 | 0 |

**NIFTY**: 69 tickets, 27 winners, +2,649. By year: {"2023": -2370.67, "2024": 3844.64, "2025": 3493.62, "2026": -2318.95}
- *side:* C 39t 12w -379; P 30t 15w +3,028
- *first exit:* STOP 20t 0w -6,490; STRUCTURE 2t 0w -441; TARGET 8t 8w +7,998; TIME 35t 18w +2,115; TRAIL 4t 1w -533
- *window:* 12:30-13:30 19t 6w -78; 13:30-14:30 36t 18w +2,314; 14:30-15:00 14t 3w +412
- *vs control:* added 3 (-676), removed 0 (+0), changed 38 (22 better, 16 worse, -10,951)
- *best:* 2024-02-22 C +1,313 (TARGET); 2024-08-08 P +1,267 (TARGET); 2024-05-09 P +1,244 (TARGET)
- *worst:* 2026-02-24 C -519 (STOP); 2025-11-11 C -491 (STOP); 2023-03-16 P -468 (STOP)

**SENSEX**: 11 tickets, 3 winners, -949. By year: {"2025": 1434.53, "2026": -2383.82}
- *side:* C 5t 0w -2,415; P 6t 3w +1,465
- *first exit:* STOP 6t 0w -3,063; STRUCTURE 1t 0w -250; TARGET 1t 1w +1,698; TIME 3t 2w +667
- *window:* 12:30-13:30 1t 0w -250; 13:30-14:30 5t 3w +1,783; 14:30-15:00 5t 0w -2,482
- *vs control:* added 0 (+0), removed 1 (-184), changed 6 (3 better, 3 worse, -3,582)
- *best:* 2025-11-13 P +1,698 (TARGET); 2026-06-25 P +618 (TIME); 2025-08-26 P +143 (TIME)
- *worst:* 2026-01-22 C -600 (STOP); 2026-03-05 C -596 (STOP); 2026-05-21 C -582 (STOP)

## EN49 — INCONCLUSIVE

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +0 | +0 | +0 | +0 | +0 | 0 / 0 | None | 30,000 (P +0) | 0 | 0 |
| SENSEX | +0 | +0 | +0 | +0 | +0 | 0 / 0 | None | 30,000 (P +0) | 0 | 0 |

NIFTY: INCONCLUSIVE; failed checks: ordinary_positive, adverse_positive, without_top2_positive, above_null; support {'tickets': 0, 'expiries': 0}
SENSEX: INCONCLUSIVE; failed checks: ordinary_positive, adverse_positive, without_top2_positive, above_null; support {'tickets': 0, 'expiries': 0}

**NIFTY**: 0 tickets, 0 winners, +0. By year: {"2023": 0.0, "2024": 0.0, "2025": 0.0, "2026": 0.0}
- *side:* 
- *first exit:* 
- *window:* 
- *vs control:* added 0 (+0), removed 68 (+7,174), changed 0 (0 better, 0 worse, +0)
- *best:* 
- *worst:* 

**SENSEX**: 0 tickets, 0 winners, +0. By year: {"2025": 0.0, "2026": 0.0}
- *side:* 
- *first exit:* 
- *window:* 
- *vs control:* added 0 (+0), removed 11 (-759), changed 0 (0 better, 0 worse, +0)
- *best:* 
- *worst:* 

## EN49_icpt_diag — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +0 | +0 | +0 | +0 | +0 | 0 / 0 | None | 30,000 (P +0) | 0 | 0 |
| SENSEX | +0 | +0 | +0 | +0 | +0 | 0 / 0 | None | 30,000 (P +0) | 0 | 0 |

**NIFTY**: 0 tickets, 0 winners, +0. By year: {"2023": 0.0, "2024": 0.0, "2025": 0.0, "2026": 0.0}
- *side:* 
- *first exit:* 
- *window:* 
- *vs control:* added 0 (+0), removed 66 (+14,275), changed 0 (0 better, 0 worse, +0)
- *best:* 
- *worst:* 

**SENSEX**: 0 tickets, 0 winners, +0. By year: {"2025": 0.0, "2026": 0.0}
- *side:* 
- *first exit:* 
- *window:* 
- *vs control:* added 0 (+0), removed 12 (+2,449), changed 0 (0 better, 0 worse, +0)
- *best:* 
- *worst:* 

## EN49_trend_diag — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | -19,597 | -27,809 | -73,817 | -21,205 | -849 | 392 / 196 | 0.416 | 25,875 (P -4,125) | 0 | 146 |
| SENSEX | -7,769 | -9,504 | -20,683 | -8,721 | -711 | 122 / 62 | 0.303 | 28,073 (P -1,604) | 324 | 0 |

**NIFTY**: 392 tickets, 121 winners, -19,597. By year: {"2023": -4309.5, "2024": -5170.83, "2025": -4544.34, "2026": -5571.88}
- *side:* C 180t 55w -9,582; P 212t 66w -10,015
- *first exit:* STOP 8t 0w -2,596; STRUCTURE 28t 0w -7,753; TARGET 1t 1w +1,109; TIME 355t 120w -10,356
- *window:* 09:45-11:00 294t 93w -12,727; 11:00-12:30 57t 18w -3,066; 12:30-13:30 33t 10w -2,504; 13:30-14:30 6t 0w -867; 14:30-15:00 2t 0w -433
- *vs control:* added 392 (-19,597), removed 66 (+14,275), changed 0 (0 better, 0 worse, +0)
- *best:* 2024-11-07 P +1,109 (TARGET); 2023-04-06 C +878 (TIME); 2024-02-15 C +732 (TIME)
- *worst:* 2023-02-02 C -436 (STRUCTURE); 2023-02-02 P -413 (STRUCTURE); 2026-01-06 C -407 (STRUCTURE)

**SENSEX**: 122 tickets, 41 winners, -7,769. By year: {"2025": -2654.85, "2026": -5113.71}
- *side:* C 70t 21w -4,463; P 52t 20w -3,306
- *first exit:* STOP 3t 0w -1,520; STRUCTURE 11t 0w -3,183; TIME 107t 40w -3,071; TRAIL 1t 1w +5
- *window:* 11:00-12:30 90t 32w -4,329; 12:30-13:30 25t 6w -3,481; 13:30-14:30 7t 3w +41
- *vs control:* added 122 (-7,769), removed 12 (+2,449), changed 0 (0 better, 0 worse, +0)
- *best:* 2025-08-19 C +484 (TIME); 2026-08-20 C +415 (TIME); 2025-09-04 P +378 (TIME)
- *worst:* 2026-05-07 P -622 (STOP); 2026-03-19 C -459 (STOP); 2025-10-30 P -438 (STOP)

## EN50 — INCONCLUSIVE

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +6,227 | +4,564 | -8,436 | -936 | -793 | 68 / 59 | 1.554 | 25,755 (P -4,245) | 0 | 86 |
| SENSEX | -759 | -1,029 | -2,854 | -3,075 | -600 | 11 / 11 | 0.777 | 28,429 (P -759) | 812 | 0 |

NIFTY: FAIL; failed checks: ordinary, adverse, without_top2
SENSEX: FAIL; failed checks: adverse_positive

**NIFTY**: 68 tickets, 24 winners, +6,227. By year: {"2023": -2570.38, "2024": 8897.97, "2025": 2766.46, "2026": -2867.12}
- *side:* C 38t 11w -965; P 30t 13w +7,192
- *first exit:* MODEL_EXIT 3t 0w -259; STOP 19t 0w -7,845; STRUCTURE 2t 0w -579; TARGET 6t 6w +6,531; TARGET_BASE 2t 2w +7,000; TIME 32t 15w +2,202; TRAIL 4t 1w -823
- *window:* 12:30-13:30 19t 4w -1,126; 13:30-14:30 36t 17w +3,202; 14:30-15:00 13t 3w +4,151
- *vs control:* added 0 (+0), removed 0 (+0), changed 3 (0 better, 3 worse, -947)
- *best:* 2024-03-28 P +5,850 (TARGET_BASE+HERO_TARGET); 2024-02-22 C +1,313 (TARGET); 2024-08-08 P +1,267 (TARGET)
- *worst:* 2023-06-15 P -604 (STOP); 2026-04-21 P -536 (STOP); 2026-02-24 C -519 (STOP)

**SENSEX**: 11 tickets, 3 winners, -759. By year: {"2025": 1624.85, "2026": -2383.82}
- *side:* C 5t 0w -2,415; P 6t 3w +1,656
- *first exit:* STOP 6t 0w -3,063; STRUCTURE 1t 0w -250; TARGET 1t 1w +1,698; TIME 3t 2w +857
- *window:* 12:30-13:30 1t 0w -250; 13:30-14:30 5t 3w +1,973; 14:30-15:00 5t 0w -2,482
- *vs control:* added 0 (+0), removed 0 (+0), changed 0 (0 better, 0 worse, +0)
- *best:* 2025-11-13 P +1,698 (TARGET); 2026-06-25 P +618 (TIME); 2025-08-26 P +333 (TIME)
- *worst:* 2026-01-22 C -600 (STOP); 2026-03-05 C -596 (STOP); 2026-05-21 C -582 (STOP)

## EN50_3min_diag — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | -980 | -3,061 | -10,233 | -3,160 | -537 | 68 / 59 | 0.877 | 28,598 (P -980) | 422 | 0 |
| SENSEX | -1,251 | -1,533 | -1,902 | -2,210 | -596 | 12 / 11 | 0.51 | 28,532 (P -1,251) | 217 | 0 |

**NIFTY**: 68 tickets, 25 winners, -980. By year: {"2023": -1058.79, "2024": 1506.36, "2025": 388.76, "2026": -1816.13}
- *side:* C 38t 12w -527; P 30t 13w -453
- *first exit:* STOP 9t 0w -3,607; TARGET 2t 2w +1,735; TARGET_BASE 1t 1w +1,150; TIME 56t 22w -257
- *window:* 12:30-13:30 19t 6w -669; 13:30-14:30 36t 14w +448; 14:30-15:00 13t 5w -759
- *vs control:* added 2 (+223), removed 0 (+0), changed 57 (29 better, 28 worse, -15,478)
- *best:* 2024-07-18 C +1,150 (TARGET_BASE+RUNNER_TRAIL); 2024-06-27 C +1,044 (TARGET); 2025-09-02 P +771 (TIME)
- *worst:* 2025-11-11 C -491 (STOP); 2025-03-06 C -478 (STOP); 2026-05-26 P -468 (STOP)

**SENSEX**: 12 tickets, 5 winners, -1,251. By year: {"2025": 429.32, "2026": -1680.14}
- *side:* C 5t 1w -1,554; P 7t 4w +303
- *first exit:* STOP 4t 0w -1,882; STRUCTURE 1t 0w -250; TIME 7t 5w +882
- *window:* 12:30-13:30 1t 0w -250; 13:30-14:30 6t 4w +876; 14:30-15:00 5t 1w -1,877
- *vs control:* added 1 (+342), removed 1 (-184), changed 9 (5 better, 4 worse, -4,225)
- *best:* 2026-06-25 P +461 (TIME); 2025-11-13 P +342 (TIME); 2025-08-26 P +337 (TIME)
- *worst:* 2026-03-05 C -596 (STOP); 2026-04-30 C -543 (STOP); 2025-10-30 P -406 (STOP)

## EN29_sym_diag — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +7,022 | +5,287 | -8,277 | -141 | -793 | 68 / 59 | 1.64 | 25,755 (P -4,245) | 0 | 86 |
| SENSEX | -759 | -1,029 | -2,854 | -3,075 | -600 | 11 / 11 | 0.777 | 28,429 (P -759) | 812 | 0 |

**NIFTY**: 68 tickets, 27 winners, +7,022. By year: {"2023": -2570.38, "2024": 8745.51, "2025": 3528.74, "2026": -2682.22}
- *side:* C 38t 12w -971; P 30t 15w +7,993
- *first exit:* STOP 19t 0w -7,845; STRUCTURE 2t 0w -579; TARGET 6t 6w +6,531; TARGET_BASE 2t 2w +6,847; TIME 35t 18w +2,890; TRAIL 4t 1w -823
- *window:* 12:30-13:30 19t 6w -364; 13:30-14:30 36t 18w +3,235; 14:30-15:00 13t 3w +4,151
- *vs control:* added 2 (-432), removed 0 (+0), changed 30 (14 better, 16 worse, -6,821)
- *best:* 2024-03-28 P +5,850 (TARGET_BASE+HERO_TARGET); 2024-02-22 C +1,313 (TARGET); 2024-08-08 P +1,267 (TARGET)
- *worst:* 2023-06-15 P -604 (STOP); 2026-04-21 P -536 (STOP); 2026-02-24 C -519 (STOP)

**SENSEX**: 11 tickets, 3 winners, -759. By year: {"2025": 1624.85, "2026": -2383.82}
- *side:* C 5t 0w -2,415; P 6t 3w +1,656
- *first exit:* STOP 6t 0w -3,063; STRUCTURE 1t 0w -250; TARGET 1t 1w +1,698; TIME 3t 2w +857
- *window:* 12:30-13:30 1t 0w -250; 13:30-14:30 5t 3w +1,973; 14:30-15:00 5t 0w -2,482
- *vs control:* added 0 (+0), removed 1 (-184), changed 6 (3 better, 3 worse, -3,392)
- *best:* 2025-11-13 P +1,698 (TARGET); 2026-06-25 P +618 (TIME); 2025-08-26 P +333 (TIME)
- *worst:* 2026-01-22 C -600 (STOP); 2026-03-05 C -596 (STOP); 2026-05-21 C -582 (STOP)

## EN51 — FAIL

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | -17,539 | -28,977 | -27,276 | -32,482 | -1,377 | 134 / 134 | 0.775 | 27,398 (P -2,145) | 456 | 0 |
| SENSEX | -4,932 | -10,007 | -9,239 | -7,956 | -1,248 | 36 / 36 | 0.77 | 28,320 (P -1,226) | 454 | 0 |

NIFTY: FAIL; failed checks: ordinary_positive, adverse_positive, without_top2_positive; support {'tickets': 134, 'expiries': 134}
SENSEX: FAIL; failed checks: ordinary_positive, adverse_positive, without_top2_positive; support {'tickets': 36, 'expiries': 36}

**NIFTY**: 134 tickets, 44 winners, -17,539. By year: {"2023": -10795.99, "2024": 6684.34, "2025": -10623.46, "2026": -2803.4}
- *side:* S 134t 44w -17,539
- *first exit:* FLAT_TIME 4t 2w -259; ONE_LEG 1t 0w -60; STOP 87t 0w -76,634; TARGET 42t 42w +59,414
- *window:* 12:30-13:30 134t 44w -17,539
- *vs control:* added 134 (-17,539), removed 68 (+7,174), changed 0 (0 better, 0 worse, +0)
- *best:* 2024-04-18 S +10,083 (TARGET+TARGET); 2024-12-26 S +4,860 (TARGET+TARGET); 2024-02-15 S +2,030 (TARGET+TARGET)
- *worst:* 2023-12-21 S -1,377 (STOP+STOP); 2024-09-19 S -1,318 (STOP+STOP); 2023-07-06 S -1,243 (STOP+STOP)

**SENSEX**: 36 tickets, 14 winners, -4,932. By year: {"2025": 362.36, "2026": -5294.54}
- *side:* S 36t 14w -4,932
- *first exit:* FLAT_TIME 1t 0w -499; ONE_LEG 1t 0w -74; STOP 20t 0w -20,874; TARGET 14t 14w +16,515
- *window:* 12:30-13:30 36t 14w -4,932
- *vs control:* added 36 (-4,932), removed 11 (-759), changed 0 (0 better, 0 worse, +0)
- *best:* 2025-12-24 S +1,537 (TARGET+TARGET); 2026-01-14 S +1,487 (TARGET+TARGET); 2025-11-06 S +1,450 (TARGET+TARGET)
- *worst:* 2026-02-05 S -1,248 (STOP+STOP); 2025-08-19 S -1,197 (STOP+STOP); 2026-08-27 S -1,172 (STOP+STOP)

## EN51_hold_diag — control / diagnostic

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | -45,581 | -48,598 | -29,762 | -75,221 | -4,373 | 134 / 134 | 0.75 | 25,652 (P -4,348) | 0 | 193 |
| SENSEX | -6,449 | -9,103 | -11,509 | -19,423 | -3,461 | 36 / 36 | 0.845 | 30,304 (P +2,749) | 2,445 | 0 |

**NIFTY**: 134 tickets, 44 winners, -45,581. By year: {"2023": -20675.77, "2024": -16836.11, "2025": -3754.54, "2026": -4314.97}
- *side:* S 134t 44w -45,581
- *first exit:* FLAT_TIME 130t 44w -37,329; ONE_LEG 1t 0w -60; UNRESOLVED 3t 0w -8,192
- *window:* 12:30-13:30 134t 44w -45,581
- *vs control:* added 134 (-45,581), removed 66 (+14,275), changed 0 (0 better, 0 worse, +0)
- *best:* 2024-04-18 S +16,418 (FLAT_TIME+FLAT_TIME); 2024-02-22 S +13,222 (FLAT_TIME+FLAT_TIME); 2026-01-20 S +9,137 (FLAT_TIME+FLAT_TIME)
- *worst:* 2023-09-14 S -4,373 (FLAT_TIME); 2023-12-21 S -4,241 (FLAT_TIME+FLAT_TIME); 2024-03-14 S -4,085 (FLAT_TIME+FLAT_TIME)

**SENSEX**: 36 tickets, 13 winners, -6,449. By year: {"2025": 8019.92, "2026": -14469.24}
- *side:* S 36t 13w -6,449
- *first exit:* FLAT_TIME 35t 13w -6,375; ONE_LEG 1t 0w -74
- *window:* 12:30-13:30 36t 13w -6,449
- *vs control:* added 36 (-6,449), removed 12 (+2,449), changed 0 (0 better, 0 worse, +0)
- *best:* 2025-10-23 S +7,384 (FLAT_TIME+FLAT_TIME); 2026-06-25 S +5,590 (FLAT_TIME+FLAT_TIME); 2025-07-29 S +4,890 (FLAT_TIME+FLAT_TIME)
- *worst:* 2025-11-20 S -3,461 (FLAT_TIME+FLAT_TIME); 2026-07-23 S -3,328 (FLAT_TIME+FLAT_TIME); 2026-02-05 S -3,080 (FLAT_TIME+FLAT_TIME)

## EN52 — FAIL

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +16,554 | +3,658 | -32,962 | -8,588 | -2,081 | 134 / 134 | 1.178 | 26,385 (P -3,615) | 0 | 0 |
| SENSEX | -8,351 | -16,355 | -9,239 | -16,729 | -1,831 | 36 / 36 | 0.68 | 30,183 (P +2,975) | 2,792 | 0 |

NIFTY: FAIL; failed checks: without_top2_positive; support {'tickets': 134, 'expiries': 134}
SENSEX: FAIL; failed checks: ordinary_positive, adverse_positive, without_top2_positive; support {'tickets': 36, 'expiries': 36}

**NIFTY**: 134 tickets, 28 winners, +16,554. By year: {"2023": -3860.83, "2024": 8257.61, "2025": 11473.07, "2026": 683.66}
- *side:* S 134t 28w +16,554
- *first exit:* FLAT_TIME 8t 7w +23,735; HERO_TARGET 1t 1w +13,977; LEG_OUT 45t 18w +43,104; ONE_LEG 1t 0w -60; RUNNER_TRAIL 35t 2w -27,879; STOP 44t 0w -36,325
- *window:* 12:30-13:30 134t 28w +16,554
- *vs control:* added 134 (+16,554), removed 68 (+7,174), changed 0 (0 better, 0 worse, +0)
- *best:* 2024-02-22 S +13,977 (HERO_TARGET+LEG_OUT); 2025-09-02 S +11,164 (LEG_OUT+HERO_TARGET); 2026-01-20 S +10,013 (LEG_OUT+FLAT_TIME)
- *worst:* 2026-07-14 S -2,081 (LEG_OUT+RUNNER_TRAIL); 2023-08-03 S -1,970 (LEG_OUT+RUNNER_TRAIL); 2023-12-21 S -1,925 (LEG_OUT+RUNNER_TRAIL)

**SENSEX**: 36 tickets, 10 winners, -8,351. By year: {"2025": 3992.51, "2026": -12343.22}
- *side:* S 36t 10w -8,351
- *first exit:* FLAT_TIME 4t 3w +8,360; LEG_OUT 14t 7w +619; ONE_LEG 1t 0w -74; RUNNER_TRAIL 5t 0w -4,934; STOP 12t 0w -12,322
- *window:* 12:30-13:30 36t 10w -8,351
- *vs control:* added 36 (-8,351), removed 11 (-759), changed 0 (0 better, 0 worse, +0)
- *best:* 2025-07-29 S +5,585 (FLAT_TIME+LEG_OUT); 2025-11-06 S +2,794 (LEG_OUT+FLAT_TIME); 2025-10-16 S +1,726 (FLAT_TIME+LEG_OUT)
- *worst:* 2025-08-19 S -1,831 (LEG_OUT+RUNNER_TRAIL); 2025-11-13 S -1,562 (RUNNER_TRAIL+LEG_OUT); 2026-07-30 S -1,309 (LEG_OUT+RUNNER_TRAIL)

## EN53 — FAIL

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +5,273 | +2,021 | -9,847 | -285 | -1,179 | 64 / 55 | 1.341 | 25,843 (P -4,157) | 0 | 151 |
| SENSEX | +259 | -99 | -9 | -3,160 | -1,351 | 7 / 7 | 1.07 | 29,432 (P +259) | 827 | 0 |

NIFTY: FAIL; failed checks: ordinary, adverse, without_top2
SENSEX: FAIL; failed checks: ordinary, adverse, adverse_positive

**NIFTY**: 64 tickets, 24 winners, +5,273. By year: {"2023": -4766.68, "2024": 6449.52, "2025": 6654.84, "2026": -3064.41}
- *side:* C 35t 10w +2,096; P 29t 14w +3,177
- *first exit:* STOP 15t 0w -9,505; STRUCTURE 6t 0w -2,782; TARGET 6t 6w +12,374; TIME 35t 18w +5,593; TRAIL 1t 0w -34; UNRESOLVED 1t 0w -372
- *window:* 12:30-13:30 16t 4w -753; 13:30-14:30 26t 16w +6,558; 14:30-15:00 22t 4w -532
- *vs control:* added 17 (-7,701), removed 19 (+1,268), changed 44 (28 better, 16 worse, -33)
- *best:* 2024-09-12 C +2,850 (TARGET); 2025-12-30 C +2,452 (TARGET); 2024-02-22 C +2,176 (TARGET)
- *worst:* 2026-02-17 C -1,143 (STOP); 2026-02-24 C -969 (STOP); 2024-06-27 C -968 (STOP)

**SENSEX**: 7 tickets, 3 winners, +259. By year: {"2025": 1653.92, "2026": -1395.25}
- *side:* C 2t 0w -1,992; P 5t 3w +2,251
- *first exit:* STOP 3t 0w -3,343; STRUCTURE 1t 0w -354; TARGET 1t 1w +2,468; TIME 2t 2w +1,487
- *window:* 12:30-13:30 1t 0w -354; 13:30-14:30 4t 3w +2,856; 14:30-15:00 2t 0w -2,243
- *vs control:* added 0 (+0), removed 5 (-2,101), changed 7 (1 better, 6 worse, -4,291)
- *best:* 2025-11-13 P +2,468 (TARGET); 2026-06-25 P +951 (TIME); 2025-08-26 P +537 (TIME)
- *worst:* 2025-10-30 P -1,351 (STOP); 2026-05-21 C -1,100 (STOP); 2026-04-30 C -892 (STOP)

## EN54 — FAIL

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | -15,220 | -22,031 | -17,331 | -22,111 | -1,377 | 71 / 71 | 0.617 | 26,676 (P -3,324) | 0 | 0 |
| SENSEX | +630 | -1,874 | -6,871 | -2,394 | -1,248 | 24 / 24 | 1.049 | 27,960 (P -2,040) | 0 | 0 |

NIFTY: FAIL; failed checks: ordinary_positive, adverse_positive, without_top2_positive; support {'tickets': 71, 'expiries': 71}
SENSEX: INCONCLUSIVE; failed checks: adverse_positive, without_top2_positive; support {'tickets': 24, 'expiries': 24}

**NIFTY**: 71 tickets, 19 winners, -15,220. By year: {"2023": -7437.19, "2024": -3499.77, "2025": -4015.33, "2026": -267.78}
- *side:* S 71t 19w -15,220
- *first exit:* FLAT_TIME 3t 1w -1,049; ONE_LEG 1t 0w -60; STOP 49t 0w -38,530; TARGET 18t 18w +24,418
- *window:* 12:30-13:30 71t 19w -15,220
- *vs control:* added 71 (-15,220), removed 68 (+7,174), changed 0 (0 better, 0 worse, +0)
- *best:* 2024-12-26 S +4,860 (TARGET+TARGET); 2024-02-15 S +2,030 (TARGET+TARGET); 2026-08-25 S +1,986 (TARGET+TARGET)
- *worst:* 2023-12-21 S -1,377 (STOP+STOP); 2024-09-19 S -1,318 (STOP+STOP); 2024-03-14 S -1,191 (STOP+STOP)

**SENSEX**: 24 tickets, 11 winners, +630. By year: {"2025": 1426.29, "2026": -796.37}
- *side:* S 24t 11w +630
- *first exit:* FLAT_TIME 1t 0w -499; STOP 12t 0w -12,311; TARGET 11t 11w +13,439
- *window:* 12:30-13:30 24t 11w +630
- *vs control:* added 24 (+630), removed 11 (-759), changed 0 (0 better, 0 worse, +0)
- *best:* 2025-12-24 S +1,537 (TARGET+TARGET); 2026-01-14 S +1,487 (TARGET+TARGET); 2025-11-06 S +1,450 (TARGET+TARGET)
- *worst:* 2026-02-05 S -1,248 (STOP+STOP); 2025-08-19 S -1,197 (STOP+STOP); 2026-06-25 S -1,141 (STOP+STOP)

## EN55 — FORWARD-ONLY

| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | +13,165 | +11,056 | +991 | +1,045 | -854 | 68 / 59 | 2.179 | 30,555 (P +3,445) | 2,890 | 0 |
| SENSEX | +2,470 | +2,237 | -1,606 | -3,008 | -784 | 10 / 9 | 1.745 | 30,193 (P +2,470) | 2,277 | 0 |

**NIFTY**: 68 tickets, 28 winners, +13,165. By year: {"2023": -3039.56, "2024": 13205.32, "2025": 5334.4, "2026": -2335.46}
- *side:* C 38t 13w -361; P 30t 15w +13,526
- *first exit:* STOP 19t 0w -8,340; STRUCTURE 2t 0w -412; TARGET 6t 6w +6,238; TARGET_BASE 2t 2w +11,790; TIME 34t 19w +4,265; TRAIL 5t 1w -376
- *window:* 12:30-13:30 17t 5w +796; 13:30-14:30 37t 20w +3,731; 14:30-15:00 14t 3w +8,638
- *vs control:* added 3 (-1,007), removed 1 (+15), changed 64 (38 better, 26 worse, -88)
- *best:* 2024-03-28 P +10,324 (TARGET_BASE+HERO_TARGET); 2024-05-09 P +1,467 (TARGET_BASE+RUNNER_STALL); 2024-02-22 C +1,332 (TARGET)
- *worst:* 2024-02-29 C -735 (STOP); 2024-01-11 P -666 (STOP); 2026-04-21 P -624 (STOP)

**SENSEX**: 10 tickets, 3 winners, +2,470. By year: {"2025": 4554.39, "2026": -2084.05}
- *side:* C 3t 0w -1,728; P 7t 3w +4,199
- *first exit:* STOP 5t 0w -2,880; STRUCTURE 1t 0w -253; TARGET_BASE 1t 1w +4,950; TIME 3t 2w +654
- *window:* 12:30-13:30 2t 0w -436; 13:30-14:30 4t 3w +5,215; 14:30-15:00 4t 0w -2,309
- *vs control:* added 0 (+0), removed 2 (-637), changed 10 (6 better, 4 worse, -616)
- *best:* 2025-11-13 P +4,950 (TARGET_BASE+RUNNER_STALL); 2026-06-25 P +529 (TIME); 2025-08-26 P +308 (TIME)
- *worst:* 2025-10-30 P -703 (STOP); 2026-01-22 C -602 (STOP); 2026-05-21 C -572 (STOP)

## Capital (the three E03.2 controls and EN55 as continuous wallets)

```json
{
 "E032_25k": {
  "NIFTY": {
   "ordinary": {
    "P": -4122.87,
    "swept": 0.0,
    "wallet": 20877.13,
    "halted": 146,
    "first_halt": "2024-01-18",
    "drawdown": 4122.87,
    "worst": -1161.74,
    "trades": 18
   },
   "adverse": {
    "P": -4035.53,
    "swept": 0.0,
    "wallet": 20964.47,
    "halted": 164,
    "first_halt": "2023-09-14",
    "drawdown": 4035.53,
    "worst": -1220.22,
    "trades": 14
   }
  },
  "SENSEX": {
   "ordinary": {
    "P": 1987.0,
    "swept": 0.0,
    "wallet": 26987.0,
    "halted": 0,
    "first_halt": null,
    "drawdown": 3380.86,
    "worst": -1124.54,
    "trades": 12
   },
   "adverse": {
    "P": 1516.4,
    "swept": 0.0,
    "wallet": 26516.4,
    "halted": 0,
    "first_halt": null,
    "drawdown": 3547.8,
    "worst": -1169.52,
    "trades": 12
   }
  }
 },
 "E032_30k": {
  "NIFTY": {
   "ordinary": {
    "P": -4122.87,
    "swept": 0.0,
    "wallet": 25877.13,
    "halted": 146,
    "first_halt": "2024-01-18",
    "drawdown": 4122.87,
    "worst": -1161.74,
    "trades": 18
   },
   "adverse": {
    "P": -4035.53,
    "swept": 0.0,
    "wallet": 25964.47,
    "halted": 164,
    "first_halt": "2023-09-14",
    "drawdown": 4035.53,
    "worst": -1220.22,
    "trades": 14
   }
  },
  "SENSEX": {
   "ordinary": {
    "P": 1987.0,
    "swept": 2422.16,
    "wallet": 29564.84,
    "halted": 0,
    "first_halt": null,
    "drawdown": 3380.86,
    "worst": -1124.54,
    "trades": 12
   },
   "adverse": {
    "P": 1516.4,
    "swept": 2299.8,
    "wallet": 29216.6,
    "halted": 0,
    "first_halt": null,
    "drawdown": 3547.8,
    "worst": -1169.52,
    "trades": 12
   }
  }
 },
 "E032_sym": {
  "NIFTY": {
   "ordinary": {
    "P": -4244.59,
    "swept": 0.0,
    "wallet": 25755.41,
    "halted": 86,
    "first_halt": "2025-03-13",
    "drawdown": 4244.59,
    "worst": -604.47,
    "trades": 32
   },
   "adverse": {
    "P": -4198.51,
    "swept": 0.0,
    "wallet": 25801.49,
    "halted": 86,
    "first_halt": "2025-03-13",
    "drawdown": 4198.51,
    "worst": -633.71,
    "trades": 30
   }
  },
  "SENSEX": {
   "ordinary": {
    "P": -758.97,
    "swept": 812.42,
    "wallet": 28428.61,
    "halted": 0,
    "first_halt": null,
    "drawdown": 2907.37,
    "worst": -599.66,
    "trades": 11
   },
   "adverse": {
    "P": -1477.3,
    "swept": 766.47,
    "wallet": 27756.23,
    "halted": 0,
    "first_halt": null,
    "drawdown": 3026.33,
    "worst": -619.66,
    "trades": 11
   }
  }
 },
 "EN55": {
  "NIFTY": {
   "ordinary": {
    "P": 3445.05,
    "swept": 2890.26,
    "wallet": 30554.79,
    "halted": 0,
    "first_halt": null,
    "drawdown": 3613.14,
    "worst": -854.3,
    "trades": 68
   },
   "adverse": {
    "P": 11572.87,
    "swept": 7027.17,
    "wallet": 34545.7,
    "halted": 0,
    "first_halt": null,
    "drawdown": 3465.46,
    "worst": -870.52,
    "trades": 67
   }
  },
  "SENSEX": {
   "ordinary": {
    "P": 2470.34,
    "swept": 2277.2,
    "wallet": 30193.14,
    "halted": 0,
    "first_halt": null,
    "drawdown": 2613.16,
    "worst": -784.45,
    "trades": 10
   },
   "adverse": {
    "P": 2236.74,
    "swept": 2195.83,
    "wallet": 30040.91,
    "halted": 0,
    "first_halt": null,
    "drawdown": 2664.07,
    "worst": -805.41,
    "trades": 10
   }
  }
 }
}
```

## Nulls

```json
{
 "EN44": {
  "NIFTY": -3693.69,
  "SENSEX": 0.0
 },
 "EN45": {
  "NIFTY": -8405.44,
  "SENSEX": -636.38
 },
 "EN49": {
  "NIFTY": 0.0,
  "SENSEX": 0.0
 }
}
```

## Diagnostics

```json
{
 "EN49_NIFTY": {
  "rows": 12632,
  "mean_label": -0.069,
  "share_mu_pos": 0.0,
  "share_mu_and_p5_pos": 0.0,
  "max_mu": -0.0408,
  "calibration_top_decile": {
   "bottom_decile_label": -0.0994,
   "top_decile_label": -0.0558
  }
 },
 "EN49_SENSEX": {
  "rows": 1067,
  "mean_label": -0.0538,
  "share_mu_pos": 0.0,
  "share_mu_and_p5_pos": 0.0,
  "max_mu": -0.0166,
  "calibration_top_decile": {
   "bottom_decile_label": -0.0508,
   "top_decile_label": -0.036
  }
 },
 "EN46_gate": {
  "NIFTY|drift|pays": 34,
  "NIFTY|drift|refused": 46,
  "NIFTY|drift|no_contract": 24,
  "SENSEX|drift|pays": 12,
  "SENSEX|drift|no_contract": 5,
  "SENSEX|drift|refused": 2,
  "NIFTY|zero|refused": 80,
  "NIFTY|zero|no_contract": 24,
  "SENSEX|zero|refused": 14,
  "SENSEX|zero|no_contract": 5
 },
 "EN47_NIFTY": {
  "common": 0,
  "different_strike": 0,
  "common_net": 0,
  "native1_common_net": 0
 },
 "EN50_NIFTY_exits": {
  "MODEL_EXIT": {
   "tickets": 3,
   "winners": 0,
   "net": -258.54
  },
  "STOP": {
   "tickets": 19,
   "winners": 0,
   "net": -7844.98
  },
  "STRUCTURE": {
   "tickets": 2,
   "winners": 0,
   "net": -578.7
  },
  "TARGET": {
   "tickets": 6,
   "winners": 6,
   "net": 6531.4
  },
  "TARGET_BASE+HERO_TARGET": {
   "tickets": 1,
   "winners": 1,
   "net": 5849.96
  },
  "TARGET_BASE+RUNNER_TRAIL": {
   "tickets": 1,
   "winners": 1,
   "net": 1149.56
  },
  "TIME": {
   "tickets": 32,
   "winners": 15,
   "net": 2201.61
  },
  "TRAIL": {
   "tickets": 4,
   "winners": 1,
   "net": -823.38
  }
 },
 "EN51_NIFTY_exits": {
  "FLAT_TIME+FLAT_TIME": {
   "tickets": 4,
   "winners": 2,
   "net": -258.63
  },
  "ONE_LEG": {
   "tickets": 1,
   "winners": 0,
   "net": -59.99
  },
  "STOP+STOP": {
   "tickets": 87,
   "winners": 0,
   "net": -76633.69
  },
  "TARGET+TARGET": {
   "tickets": 42,
   "winners": 42,
   "net": 59413.8
  }
 },
 "EN52_NIFTY_exits": {
  "FLAT_TIME+FLAT_TIME": {
   "tickets": 1,
   "winners": 0,
   "net": -554.1
  },
  "FLAT_TIME+LEG_OUT": {
   "tickets": 7,
   "winners": 7,
   "net": 24289.58
  },
  "HERO_TARGET+LEG_OUT": {
   "tickets": 1,
   "winners": 1,
   "net": 13977.49
  },
  "LEG_OUT+FLAT_TIME": {
   "tickets": 13,
   "winners": 12,
   "net": 45030.88
  },
  "LEG_OUT+HERO_TARGET": {
   "tickets": 2,
   "winners": 2,
   "net": 16480.24
  },
  "LEG_OUT+RUNNER_TRAIL": {
   "tickets": 30,
   "winners": 4,
   "net": -18407.24
  },
  "ONE_LEG": {
   "tickets": 1,
   "winners": 0,
   "net": -59.99
  },
  "RUNNER_TRAIL+LEG_OUT": {
   "tickets": 35,
   "winners": 2,
   "net": -27878.61
  },
  "STOP+STOP": {
   "tickets": 44,
   "winners": 0,
   "net": -36324.74
  }
 },
 "EN54_NIFTY_exits": {
  "FLAT_TIME+FLAT_TIME": {
   "tickets": 3,
   "winners": 1,
   "net": -1048.65
  },
  "ONE_LEG": {
   "tickets": 1,
   "winners": 0,
   "net": -59.99
  },
  "STOP+STOP": {
   "tickets": 49,
   "winners": 0,
   "net": -38529.59
  },
  "TARGET+TARGET": {
   "tickets": 18,
   "winners": 18,
   "net": 24418.16
  }
 },
 "EN44_NIFTY_exits": {
  "FSTOP": {
   "tickets": 18,
   "winners": 0,
   "net": -3285.27
  },
  "STOP": {
   "tickets": 7,
   "winners": 0,
   "net": -2912.38
  },
  "TARGET": {
   "tickets": 1,
   "winners": 1,
   "net": 800.7
  },
  "TIME": {
   "tickets": 17,
   "winners": 9,
   "net": 1099.21
  }
 },
 "EN45_NIFTY_exits": {
  "FSTOP": {
   "tickets": 38,
   "winners": 0,
   "net": -7747.69
  },
  "FTARGET": {
   "tickets": 32,
   "winners": 17,
   "net": 1550.94
  },
  "STOP": {
   "tickets": 1,
   "winners": 0,
   "net": -439.04
  },
  "TIME": {
   "tickets": 65,
   "winners": 17,
   "net": -4262.41
  }
 },
 "EN51_NIFTY_refusals": {
  "no_atm_pair": 1,
  "reserve": 62
 },
 "EN54_NIFTY_refusals": {
  "no_atm_pair": 1,
  "not_cheap": 109,
  "reserve": 16
 },
 "EN47_SENSEX": {
  "common": 1,
  "different_strike": 0,
  "common_net": -542.67,
  "native1_common_net": -542.67
 },
 "EN50_SENSEX_exits": {
  "STOP": {
   "tickets": 6,
   "winners": 0,
   "net": -3063.3
  },
  "STRUCTURE": {
   "tickets": 1,
   "winners": 0,
   "net": -250.38
  },
  "TARGET": {
   "tickets": 1,
   "winners": 1,
   "net": 1697.72
  },
  "TIME": {
   "tickets": 3,
   "winners": 2,
   "net": 856.99
  }
 },
 "EN51_SENSEX_exits": {
  "FLAT_TIME+FLAT_TIME": {
   "tickets": 1,
   "winners": 0,
   "net": -498.68
  },
  "ONE_LEG": {
   "tickets": 1,
   "winners": 0,
   "net": -74.36
  },
  "STOP+STOP": {
   "tickets": 20,
   "winners": 0,
   "net": -20874.47
  },
  "TARGET+TARGET": {
   "tickets": 14,
   "winners": 14,
   "net": 16515.33
  }
 },
 "EN52_SENSEX_exits": {
  "FLAT_TIME+FLAT_TIME": {
   "tickets": 1,
   "winners": 0,
   "net": -498.68
  },
  "FLAT_TIME+LEG_OUT": {
   "tickets": 3,
   "winners": 3,
   "net": 8859.17
  },
  "LEG_OUT+FLAT_TIME": {
   "tickets": 4,
   "winners": 4,
   "net": 6489.11
  },
  "LEG_OUT+RUNNER_TRAIL": {
   "tickets": 10,
   "winners": 3,
   "net": -5869.73
  },
  "ONE_LEG": {
   "tickets": 1,
   "winners": 0,
   "net": -74.36
  },
  "RUNNER_TRAIL+LEG_OUT": {
   "tickets": 5,
   "winners": 0,
   "net": -4934.17
  },
  "STOP+STOP": {
   "tickets": 12,
   "winners": 0,
   "net": -12322.05
  }
 },
 "EN54_SENSEX_exits": {
  "FLAT_TIME+FLAT_TIME": {
   "tickets": 1,
   "winners": 0,
   "net": -498.68
  },
  "STOP+STOP": {
   "tickets": 12,
   "winners": 0,
   "net": -12310.6
  },
  "TARGET+TARGET": {
   "tickets": 11,
   "winners": 11,
   "net": 13439.2
  }
 },
 "EN44_SENSEX_exits": {},
 "EN45_SENSEX_exits": {
  "FSTOP": {
   "tickets": 4,
   "winners": 1,
   "net": -481.38
  },
  "FTARGET": {
   "tickets": 9,
   "winners": 5,
   "net": 513.33
  },
  "STOP": {
   "tickets": 6,
   "winners": 0,
   "net": -2417.62
  },
  "TIME": {
   "tickets": 5,
   "winners": 2,
   "net": 115.27
  }
 },
 "EN51_SENSEX_refusals": {
  "reserve": 27
 },
 "EN54_SENSEX_refusals": {
  "not_cheap": 23,
  "reserve": 16
 }
}
```

## Slots without data

```json
{
 "EN41": "Needs receipt-clock futures depth packets. TR01 (Production Docker volume, since Nov 13) holds at most two expiry sessions and has not been exported or sealed; its export is a separate, owner-authorised task.",
 "EN42": "Same data as EN41.",
 "EN43": "Needs dated NIFTY/SENSEX weights and sub-minute constituent prices; only Kite 15-minute bars (Jan-Jul 2026, current basket) are held.",
 "EN48": "Officially verified RBI decision dates in the scored history: Aug 8 2024 (2024-25 schedule, RBI press release of Mar 27 2024) is the only one on a NIFTY expiry session; far below 30 tickets on 20 expiries. The 2023-24 schedule was not verified in this round."
}
```

