# Round 8 anatomy — EN86–EN95

Developed and scored by Codex under PLAN8.md and freeze8.json. One fixed version per slot. No fresh historical holdout exists. These are development screens, not broker fills or proof of an edge.

**Practical review:** read [LESSONS8.md](LESSONS8.md). EN87 is an unproven positive development lead; EN91's mechanical tail-screen label does not override its continuous-wallet failure. No policy is promoted.

Machine-readable evidence: results8.json, anatomy8.json, verification8.json. Full tables: ANATOMY8-tables.md. Source/runner corrections: ERRATUM8.md.

## Financial summary

| Slot | Ordinary / adverse, NIFTY | Status |
|---|---:|---|
| EN87 | 6,114.14 / 5,840.68 | PROTECTION-LIKE — development only |
| EN88 | -10,865.26 / -23,578.85 | FAIL |
| EN89 | -3,531.18 / -3,296.83 | FAIL |
| EN90 | -3,027.34 / -8,661.12 | FAIL |
| EN91 | 18,686.48 / 3,371.47 | TAIL SCREEN — SOURCE UNVALIDATED |
| EN92 | -1,674.30 / -9,713.69 | FAIL |
| EN93 | -516.94 / -1,010.61 | INCONCLUSIVE — support |
| EN94 | 2,400.11 / -5,274.56 | FAIL |
| EN95 | -2,150.61 / -3,062.52 | FAIL |

SENSEX: DATA UNAVAILABLE for all nine new primaries because its stored OI is not supplied. Its baseline controls are reported separately in results8.json. No NIFTY positioning is substituted.

Independent-session sums and cash/brake-constrained wallets are different experiments. Do not add the shadow wallets together. No candidate is qualified while EN86 source validation remains incomplete.

## EN86 — source mechanism

Packet pilot: 2026-11-17, coverage 99.4%, 99 events. one recorded expiry; requires >=20 covered expiries and >=100 nonoverlapping events.
- RAW: canonical one-lot fixed-hold net -11,164.09, random-side expectation -10,163.61; 278 events. This is an overlapping-action diagnostic, not a funded book.
- RESID: canonical one-lot fixed-hold net -28,298.49, random-side expectation -38,782.50; 640 events. This is an overlapping-action diagnostic, not a funded book.
- CONTRACT: canonical one-lot fixed-hold net -14,958.69, random-side expectation -14,622.24; 311 events. This is an overlapping-action diagnostic, not a funded book.

## EN87 — OI at E03 entry clocks

**PROTECTION-LIKE — development only.** 25 parents on 23 of 197 expiries. Ordinary 6,114.14; adverse 5,840.68; without its best two days 2,644.90.

By year: 2023: 570.77, 2024: 2,094.68, 2025: 5,899.98, 2026: -2,451.29.

Where money came from: PUT 2,811.89, CALL 3,302.25.
By first exit: TIME 4,649.40, STOP -5,780.89, TARGET_BASE 7,569.74, TRAIL -324.11.

Versus matched E03: 15.78 per expiry; 95% long-group interval [-46.0718, 75.6027]; Holm p 1.0000.
Changed opportunities: 31 on 28 expiries. Matched-parent delta 506.61; new-only net 0.00; forgone control net -2,601.10.
Wallet: net 5,305.89, swept 3,773.25, trading cash 31,532.64, liquidation DD 2,448.21, first halt None.

## EN88 — OI residual beyond price

**FAIL.** 252 parents on 151 of 197 expiries. Ordinary -10,865.26; adverse -23,578.85; without its best two days -24,515.21.

By year: 2023: -4,663.13, 2024: -2,075.06, 2025: -5,075.75, 2026: 948.68.

Where money came from: PUT -3,050.37, CALL -7,814.89.
By first exit: STOP -40,752.49, TIME 9,004.71, STRUCTURE -9,228.48, TARGET_BASE 28,477.23, TRAIL 275.88, TARGET 1,357.89.

Versus matched E03: -70.41 per expiry; 95% long-group interval [-230.0603, 88.2321]; Holm p 1.0000.
Changed opportunities: 305 on 163 expiries. Matched-parent delta 0.00; new-only net -12,434.90; forgone control net 1,436.79.
Wallet: net -4,088.48, swept 0.00, trading cash 25,911.52, liquidation DD 4,091.72, first halt 2023-12-21.

## EN89 — Pullback/reclaim with price ceiling

**FAIL.** 31 parents on 27 of 197 expiries. Ordinary -3,531.18; adverse -3,296.83; without its best two days -7,068.80.

By year: 2023: -607.17, 2024: -5,807.47, 2025: 277.62, 2026: 2,605.84.

Where money came from: PUT -708.71, CALL -2,822.47.
By first exit: TIME 928.68, STOP -9,352.22, TRAIL 26.19, TARGET_BASE 3,537.62, TARGET 1,328.55.

Versus matched E03: -33.19 per expiry; 95% long-group interval [-130.6028, 64.0475]; Holm p 1.0000.
Changed opportunities: 84 on 69 expiries. Matched-parent delta 0.00; new-only net -2,710.45; forgone control net 3,827.16.
Wallet: net -4,002.17, swept 0.00, trading cash 25,997.83, liquidation DD 4,002.17, first halt 2025-06-12.

## EN90 — OI contraction versus growth

**FAIL.** 186 parents on 127 of 197 expiries. Ordinary -3,027.34; adverse -8,661.12; without its best two days -18,879.23.

By year: 2023: -1,569.07, 2024: 9,343.24, 2025: 1,042.52, 2026: -11,844.03.

Where money came from: PUT -6,430.88, CALL 3,403.54.
By first exit: TIME 7,610.57, STOP -38,432.10, STRUCTURE -4,249.07, TRAIL -690.01, TARGET_BASE 32,733.27.

Versus matched E03: -30.63 per expiry; 95% long-group interval [-255.05, 186.4206]; Holm p 1.0000.
Changed opportunities: 237 on 143 expiries. Matched-parent delta 0.00; new-only net -2,837.50; forgone control net 3,196.27.
Wallet: net -3,398.75, swept 431.73, trading cash 26,169.52, liquidation DD 4,275.18, first halt 2024-05-23.

## EN91 — 24-minute option-information hold

**TAIL SCREEN — SOURCE UNVALIDATED.** 162 parents on 116 of 197 expiries. Ordinary 18,686.48; adverse 3,371.47; without its best two days -7,979.36.

By year: 2023: 8,761.05, 2024: 4,994.92, 2025: 15,590.35, 2026: -10,659.84.

Where money came from: PUT 1,656.63, CALL 17,029.85.
By first exit: STOP -67,450.39, TARGET_BASE 75,730.81, TRAIL -643.53, STRUCTURE -4,681.10, TIME 4,415.17, TARGET 11,315.52.

Versus matched E03: 79.59 per expiry; 95% long-group interval [-179.4554, 333.311]; Holm p 1.0000.
Changed opportunities: 216 on 133 expiries. Matched-parent delta 45.41; new-only net 18,563.37; forgone control net 2,928.73.
Wallet: net -3,972.02, swept 72.08, trading cash 25,955.90, liquidation DD 4,116.19, first halt 2024-05-23.

## EN92 — One affordable higher-sensitivity contract

**FAIL.** 193 parents on 127 of 197 expiries. Ordinary -1,674.30; adverse -9,713.69; without its best two days -7,797.71.

By year: 2023: -1,857.62, 2024: 3,105.32, 2025: 1,735.76, 2026: -4,657.76.

Where money came from: PUT -6,504.00, CALL 4,829.70.
By first exit: TIME 12,852.28, STOP -29,947.48, STRUCTURE -7,655.45, TARGET 23,151.07, TRAIL -74.72.

Versus matched E03: -23.76 per expiry; 95% long-group interval [-174.2451, 122.3723]; Holm p 1.0000.
Changed opportunities: 247 on 143 expiries. Matched-parent delta -62.45; new-only net -1,689.55; forgone control net 2,928.73.
Wallet: net -2,706.05, swept 702.34, trading cash 26,591.61, liquidation DD 4,130.18, first halt 2024-08-14.

## EN93 — Realized net-payoff model

**INCONCLUSIVE — support.** 9 parents on 8 of 197 expiries. Ordinary -516.94; adverse -1,010.61; without its best two days -2,680.96.

By year: 2023: 0.00, 2024: 0.00, 2025: -418.44, 2026: -98.50.

Where money came from: PUT -516.94.
By first exit: TIME 1,152.66, STOP -1,669.60.

Versus matched E03: -17.89 per expiry; 95% long-group interval [-107.915, 70.5904]; Holm p 1.0000.
Changed opportunities: 64 on 53 expiries. Matched-parent delta 0.00; new-only net -516.94; forgone control net 3,006.43.
Wallet: net -1,691.27, swept 45.76, trading cash 28,262.97, liquidation DD 2,557.51, first halt None.

Forecast support: 51 eligible model dates; 9 selected potential events. Startup and missing-input decisions remain explicit. Conservative scores are heuristic, not guaranteed bounds.

## EN94 — Information reversal exit

**FAIL.** 165 parents on 116 of 197 expiries. Ordinary 2,400.11; adverse -5,274.56; without its best two days -10,760.43.

By year: 2023: -1,737.55, 2024: 10,027.92, 2025: -2,169.29, 2026: -3,720.97.

Where money came from: PUT 802.70, CALL 1,597.41.
By first exit: TIME 16,231.53, STOP -36,242.94, STRUCTURE -3,419.69, TARGET_BASE 25,078.70, OI_REVERSAL -595.61, TARGET 1,646.22, TRAIL -298.10.

Versus matched E03: -3.08 per expiry; 95% long-group interval [-186.7484, 175.99]; Holm p 1.0000.
Changed opportunities: 218 on 133 expiries. Matched-parent delta 0.00; new-only net 2,322.41; forgone control net 2,928.73.
Wallet: net -1,996.35, swept 1,076.67, trading cash 26,926.98, liquidation DD 4,159.43, first halt 2024-09-26.

## EN95 — Predetermined complete trader

**FAIL.** 35 parents on 31 of 197 expiries. Ordinary -2,150.61; adverse -3,062.52; without its best two days -5,091.41.

By year: 2023: -909.86, 2024: -5,283.40, 2025: 988.38, 2026: 3,054.27.

Where money came from: CALL -1,873.31, PUT -277.30.
By first exit: TIME 3,793.00, STOP -6,649.99, STRUCTURE -622.17, TARGET 1,328.55.

Versus matched E03: -26.18 per expiry; 95% long-group interval [-123.2533, 70.7922]; Holm p 1.0000.
Changed opportunities: 89 on 72 expiries. Matched-parent delta 136.48; new-only net -2,497.22; forgone control net 2,796.30.
Wallet: net -2,858.50, swept 21.87, trading cash 27,119.63, liquidation DD 3,038.48, first halt None.

Predetermined remove-one controls (not eligible replacement winners):
- EN95_noentry_ctl: -367.20 / -8,455.28 ordinary/adverse.
- EN95_nochooser_ctl: -1,983.92 / -1,762.53 ordinary/adverse.
- EN95_noexit_ctl: -2,150.61 / -3,062.52 ordinary/adverse.

## Verification, limits and remaining work

Control parity, mechanics, causal prefixes, calibration, one-shot scoring, financial reconciliation and forward rehearsals have separate receipts. The final verification receipt states what actually ran; the full engine suite is not implied.

No downloads, broker orders, Telegram messages, scheduler change or Production edits. E03.2 and EN55 remain unchanged. All financial results are old-data research with modeled fills; the packet mechanism has one expiry and cannot establish a profitable lead. New prospective observations and the explicit dated calendar/snapshot workflow are still needed.
