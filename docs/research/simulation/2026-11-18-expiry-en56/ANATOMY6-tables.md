# EN56–EN70 tables (rendered from results6.json)

Freeze head `e16bee2f`; sessions {'NIFTY': 197, 'SENSEX': 63}; evaluation starts {'EN61|NIFTY': '2024-01-11', 'EN62|NIFTY': '2023-06-22', 'EN61|SENSEX': '2026-07-16', 'EN62|SENSEX': '2025-12-18'}.

## Verdicts

| Slot | NIFTY | SENSEX |
|---|---|---|
| EN56 | ANSWERED | ANSWERED |
| EN57 | ANSWERED | ANSWERED |
| EN58 | INCONCLUSIVE | INCONCLUSIVE |
| EN59 | INCONCLUSIVE | INCONCLUSIVE |
| EN60 | FAIL | FAIL |
| EN61 | FAIL | INCONCLUSIVE |
| EN62 | FAIL | INCONCLUSIVE |
| EN63 | FAIL | INCONCLUSIVE |
| EN64 | FAIL | INCONCLUSIVE |
| EN65 | INCONCLUSIVE | INCONCLUSIVE |
| EN66 | ANSWERED | ANSWERED |
| EN67 | FAIL | FAIL |
| EN68 | ANSWERED | ANSWERED |
| EN69 | ANSWERED | ANSWERED |
| EN70 | PARITY NOT ESTABLISHED | — |

## The family test (18 hypotheses, Holm)

| Hypothesis | support | affected parents / expiries | bootstrap p | Holm p |
|---|---|---|---:|---:|
| EN58|NIFTY | False | — / — | 1.0 | 1.0 |
| EN58|SENSEX | False | — / — | 1.0 | 1.0 |
| EN59|NIFTY | False | 7 / 7 | 1.0 | 1.0 |
| EN59|SENSEX | False | 0 / 0 | 1.0 | 1.0 |
| EN60|NIFTY | True | — / — | 0.7406 | 1.0 |
| EN60|SENSEX | True | — / — | 0.7527 | 1.0 |
| EN61|NIFTY | True | — / — | 0.5693 | 1.0 |
| EN61|SENSEX | False | — / — | 1.0 | 1.0 |
| EN62|NIFTY | True | — / — | 0.9614 | 1.0 |
| EN62|SENSEX | False | — / — | 1.0 | 1.0 |
| EN63|NIFTY | True | 65 / 63 | 0.3362 | 1.0 |
| EN63|SENSEX | False | 8 / 8 | 1.0 | 1.0 |
| EN64|NIFTY | True | — / — | 0.8561 | 1.0 |
| EN64|SENSEX | False | — / — | 1.0 | 1.0 |
| EN65|NIFTY | False | 6 / 6 | 1.0 | 1.0 |
| EN65|SENSEX | False | 1 / 1 | 1.0 | 1.0 |
| EN67|NIFTY | True | 156 / 107 | 1.0 | 1.0 |
| EN67|SENSEX | True | 37 / 23 | 0.7832 | 1.0 |

## Every arm (fixed-cap net by fill level; wallet at ordinary fills)

| Arm | Index | ordinary | adverse | severe | w/o top 2 | worst | parents | expiries | wallet P | swept | halted | first halt | liq. DD | worst marked |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| E032_30k | NIFTY | 14,275 | 11,586 | -12,347 | 652 | -1,281 | 66 | 58 | -4,123 | 0 | 146 | 2024-01-18 | 4,181 | -1,395 |
| E032_30k | SENSEX | 2,449 | 1,921 | -4,599 | -4,089 | -1,125 | 12 | 11 | 1,987 | 2,422 | 0 | never | 3,557 | -1,125 |
| EN55 | NIFTY | 13,165 | 11,056 | 991 | 1,045 | -854 | 68 | 59 | 3,445 | 2,890 | 0 | never | 4,006 | -903 |
| EN55 | SENSEX | 2,470 | 2,237 | -1,606 | -3,008 | -784 | 10 | 9 | 2,470 | 2,277 | 0 | never | 2,879 | -854 |
| E032_sym | NIFTY | 7,174 | 5,440 | -8,277 | 11 | -793 | 68 | 59 | -4,245 | 0 | 86 | 2025-03-13 | 4,245 | -812 |
| E032_sym | SENSEX | -759 | -1,029 | -2,854 | -3,075 | -600 | 11 | 11 | -759 | 812 | 0 | never | 3,084 | -670 |
| E032_env | NIFTY | 1,567 | 949 | -17,724 | -6,817 | -1,464 | 59 | 59 | -4,103 | 0 | 86 | 2025-03-13 | 4,103 | -1,464 |
| E032_env | SENSEX | 1,542 | 975 | -4,644 | -4,997 | -1,125 | 11 | 11 | 1,687 | 2,327 | 0 | never | 3,153 | -1,130 |
| EN60 | NIFTY | -9,777 | -10,758 | -47,156 | -26,182 | -1,305 | 159 | 159 | -4,052 | 0 | 162 | 2023-09-28 | 4,091 | -2,000 |
| EN60 | SENSEX | -3,623 | -4,323 | -10,631 | -8,001 | -981 | 48 | 48 | -3,807 | 121 | 12 | 2026-07-23 | 4,049 | -1,102 |
| EN60_orb5_ctl | NIFTY | -22,351 | -26,164 | -28,018 | -26,774 | -1,016 | 155 | 155 | -3,301 | 360 | 154 | 2023-11-23 | 4,041 | -1,094 |
| EN60_orb5_ctl | SENSEX | -379 | -3,069 | -9,492 | -4,911 | -890 | 50 | 50 | -745 | 1,535 | 0 | never | 3,899 | -890 |
| EN60_1250_diag | NIFTY | -6,811 | -11,794 | -24,083 | -10,582 | -676 | 152 | 152 | -3,064 | 0 | 0 | never | 3,090 | -1,012 |
| EN60_1250_diag | SENSEX | -1,347 | -2,412 | -5,805 | -4,678 | -514 | 46 | 46 | -3,057 | 49 | 0 | never | 3,154 | -575 |
| EN62 | NIFTY | -16,264 | -21,707 | -17,229 | -23,686 | -1,149 | 94 | 94 | -1,940 | 1,070 | 144 | 2024-02-01 | 4,080 | -1,258 |
| EN62 | SENSEX | -6,010 | -6,958 | -7,221 | -8,699 | -902 | 22 | 22 | -2,378 | 710 | 0 | never | 3,806 | -902 |
| EN62_dir_ctl | NIFTY | -22,546 | -33,066 | -46,574 | -27,753 | -1,058 | 175 | 175 | -4,087 | 0 | 154 | 2023-11-23 | 4,093 | -2,000 |
| EN62_dir_ctl | SENSEX | -8,697 | -10,299 | -11,771 | -12,130 | -1,246 | 42 | 42 | -4,022 | 0 | 15 | 2026-07-02 | 4,045 | -1,311 |
| EN62_decay_ctl | NIFTY | -3,148 | -1,958 | -5,880 | -6,936 | -1,064 | 28 | 28 | -2,479 | 403 | 0 | never | 3,675 | -1,064 |
| EN62_decay_ctl | SENSEX | 2,172 | 382 | 0 | 238 | 0 | 4 | 4 | 2,172 | 1,086 | 0 | never | 189 | -189 |
| EN62_1250_diag | NIFTY | -11,218 | -13,038 | -9,634 | -14,130 | -598 | 94 | 94 | -2,258 | 379 | 0 | never | 3,048 | -630 |
| EN62_1250_diag | SENSEX | -2,696 | -3,178 | -3,922 | -4,238 | -475 | 21 | 21 | -1,787 | 465 | 0 | never | 2,727 | -475 |
| EN64 | NIFTY | -11,906 | -17,228 | -37,584 | -22,585 | -967 | 166 | 166 | -4,037 | 0 | 138 | 2024-03-14 | 4,063 | -997 |
| EN64 | SENSEX | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |
| EN64_ret_ctl | NIFTY | -27,282 | -34,176 | -34,149 | -30,715 | -1,037 | 169 | 169 | -3,740 | 172 | 150 | 2023-12-21 | 4,097 | -2,000 |
| EN64_ret_ctl | SENSEX | 128 | -3,034 | -11,492 | -4,013 | -864 | 54 | 54 | -2,291 | 0 | 0 | never | 2,988 | -874 |
| EN64_vol_ctl | NIFTY | -29,835 | -31,258 | -38,919 | -34,855 | -1,084 | 166 | 166 | -3,261 | 392 | 159 | 2023-10-19 | 4,046 | -2,000 |
| EN64_vol_ctl | SENSEX | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |
| EN64_1250_diag | NIFTY | -9,188 | -14,492 | -20,172 | -12,698 | -591 | 166 | 166 | -3,093 | 0 | 0 | never | 3,135 | -617 |
| EN64_1250_diag | SENSEX | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |
| EN63 | NIFTY | 282 | -2,695 | -7,915 | -5,021 | -1,022 | 64 | 64 | -4,209 | 0 | 27 | 2026-04-28 | 4,216 | -1,062 |
| EN63 | SENSEX | -503 | -1,282 | -2,118 | -2,971 | -1,351 | 6 | 6 | -503 | 493 | 0 | never | 1,758 | -1,440 |
| EN63_native8_ctl | NIFTY | -2,084 | -2,105 | -3,188 | -4,664 | -647 | 58 | 58 | 169 | 1,088 | 0 | never | 3,324 | -764 |
| EN63_native8_ctl | SENSEX | 942 | 1,155 | -1,489 | -1,374 | -582 | 8 | 8 | 942 | 717 | 0 | never | 1,192 | -589 |
| EN63_native15 | NIFTY | -2,956 | -2,588 | -2,980 | -5,536 | -647 | 58 | 58 | -1,064 | 738 | 0 | never | 3,178 | -764 |
| EN63_native15 | SENSEX | 624 | 979 | -1,764 | -1,243 | -582 | 8 | 8 | 624 | 692 | 0 | never | 1,247 | -589 |
| EN63_liq8 | NIFTY | 1,900 | -875 | -7,655 | -3,402 | -1,022 | 64 | 64 | -4,025 | 0 | 49 | 2025-11-25 | 4,041 | -1,062 |
| EN63_liq8 | SENSEX | 1,151 | 839 | -1,093 | -2,268 | -1,351 | 6 | 6 | 1,151 | 827 | 0 | never | 1,687 | -1,440 |
| EN63_cash_diag | NIFTY | -368 | 549 | -3,368 | -8,024 | -992 | 54 | 54 | -3,513 | 0 | 0 | never | 3,513 | -1,093 |
| EN63_cash_diag | SENSEX | -657 | 70 | -1,764 | -2,354 | -1,116 | 6 | 6 | -657 | 397 | 0 | never | 1,622 | -1,130 |
| EN65 | NIFTY | -2,105 | -4,138 | -14,069 | -6,564 | -992 | 60 | 60 | -4,079 | 0 | 86 | 2025-03-13 | 4,079 | -992 |
| EN65 | SENSEX | 1,151 | 800 | -2,662 | -2,730 | -836 | 10 | 10 | 1,151 | 1,511 | 0 | never | 2,571 | -854 |
| EN65_bank_ctl | NIFTY | -1,182 | -3,250 | -14,069 | -5,994 | -992 | 60 | 60 | -4,035 | 0 | 90 | 2025-02-13 | 4,048 | -992 |
| EN65_bank_ctl | SENSEX | 1,330 | 987 | -2,662 | -2,730 | -836 | 10 | 10 | 1,330 | 1,600 | 0 | never | 2,571 | -854 |
| EN65_en12_diag | NIFTY | 2,512 | 2,423 | -17,724 | -6,058 | -1,464 | 59 | 59 | -4,103 | 0 | 86 | 2025-03-13 | 4,103 | -1,464 |
| EN65_en12_diag | SENSEX | 1,632 | 1,065 | -4,644 | -4,997 | -1,125 | 11 | 11 | 1,778 | 2,372 | 0 | never | 3,153 | -1,130 |
| EN59 | NIFTY | -5,969 | -6,423 | -2,994 | -7,663 | -651 | 21 | 21 | -1,608 | 0 | 0 | never | 1,774 | -816 |
| EN59 | SENSEX | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |
| EN59_en52_ctl | NIFTY | -415 | -1,190 | -2,994 | -7,238 | -959 | 21 | 21 | -1,936 | 0 | 0 | never | 1,955 | -978 |
| EN59_en52_ctl | SENSEX | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |
| EN59_en52_5000 | NIFTY | 16,554 | 3,658 | -32,962 | -8,588 | -2,081 | 134 | 134 | -3,615 | 0 | 0 | never | 3,634 | -2,198 |
| EN59_en52_5000 | SENSEX | -8,351 | -16,355 | -9,239 | -16,729 | -1,831 | 36 | 36 | 2,975 | 2,792 | 0 | never | 2,671 | -1,893 |
| EN59_closeb_diag | NIFTY | -2,300 | -2,358 | -2,994 | -7,518 | -651 | 21 | 21 | -1,608 | 0 | 0 | never | 1,774 | -816 |
| EN59_closeb_diag | SENSEX | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |
| EN59_en51_2500 | NIFTY | -2,371 | -581 | -2,994 | -8,030 | -651 | 21 | 21 | -1,608 | 0 | 0 | never | 1,774 | -816 |
| EN59_en51_2500 | SENSEX | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |
| EN67 | NIFTY | -7,120 | -10,817 | -33,565 | -19,240 | -1,170 | 204 | 138 | -4,273 | 0 | 166 | 2023-08-31 | 4,286 | -1,274 |
| EN67 | SENSEX | 39 | -1,249 | -7,133 | -6,610 | -1,075 | 41 | 27 | 2,821 | 3,480 | 25 | 2026-04-23 | 4,140 | -1,247 |
| EN67_e5_s750_diag | NIFTY | -34,788 | -39,917 | -65,791 | -38,345 | -1,578 | 301 | 173 | -4,036 | 0 | 173 | 2023-07-13 | 4,074 | -1,734 |
| EN67_e5_s750_diag | SENSEX | -8,639 | -10,188 | -17,137 | -11,926 | -1,381 | 73 | 44 | -3,564 | 276 | 30 | 2026-03-19 | 4,186 | -1,393 |
| EN67_e5_s780_diag | NIFTY | -23,616 | -30,457 | -58,053 | -36,268 | -1,578 | 274 | 168 | -3,863 | 70 | 167 | 2023-08-24 | 4,062 | -1,734 |
| EN67_e5_s780_diag | SENSEX | -10,890 | -12,294 | -18,970 | -13,299 | -1,381 | 67 | 44 | -4,523 | 0 | 31 | 2026-03-12 | 4,525 | -1,393 |
| EN67_e6_s750_diag | NIFTY | -7,120 | -10,817 | -33,565 | -19,240 | -1,170 | 204 | 138 | -4,273 | 0 | 166 | 2023-08-31 | 4,286 | -1,274 |
| EN67_e6_s750_diag | SENSEX | 39 | -1,249 | -7,133 | -6,610 | -1,075 | 41 | 27 | 2,821 | 3,480 | 25 | 2026-04-23 | 4,140 | -1,247 |
| EN67_e6_s780_diag | NIFTY | 129 | -3,003 | -23,604 | -11,991 | -1,383 | 166 | 123 | -4,161 | 0 | 165 | 2023-09-07 | 4,310 | -1,383 |
| EN67_e6_s780_diag | SENSEX | -1,193 | -2,392 | -7,868 | -7,233 | -1,075 | 36 | 26 | 1,774 | 3,006 | 25 | 2026-04-23 | 4,237 | -1,247 |
| EN67_e7_s750_diag | NIFTY | 9,806 | 7,328 | -4,265 | -2,443 | -868 | 89 | 75 | -4,110 | 0 | 151 | 2023-12-14 | 4,117 | -930 |
| EN67_e7_s750_diag | SENSEX | 2,041 | 1,799 | -2,125 | -3,437 | -784 | 11 | 10 | 2,041 | 2,277 | 0 | never | 3,308 | -854 |
| EN67_e7_s780_diag | NIFTY | 13,165 | 11,056 | 991 | 1,045 | -854 | 68 | 59 | 3,445 | 2,890 | 0 | never | 4,006 | -903 |
| EN67_e7_s780_diag | SENSEX | 2,470 | 2,237 | -1,606 | -3,008 | -784 | 10 | 9 | 2,470 | 2,277 | 0 | never | 2,879 | -854 |
| EN67_e8_s750_diag | NIFTY | 11,392 | 10,639 | 3,715 | -398 | -735 | 28 | 28 | 11,392 | 6,154 | 0 | never | 1,480 | -903 |
| EN67_e8_s750_diag | SENSEX | 3,776 | 3,648 | 1,309 | -1,173 | -602 | 3 | 3 | 3,776 | 2,475 | 0 | never | 1,180 | -672 |
| EN67_e8_s780_diag | NIFTY | 12,464 | 11,773 | 5,021 | 674 | -735 | 24 | 24 | 12,464 | 6,541 | 0 | never | 1,480 | -903 |
| EN67_e8_s780_diag | SENSEX | 3,776 | 3,648 | 1,309 | -1,173 | -602 | 3 | 3 | 3,776 | 2,475 | 0 | never | 1,180 | -672 |
| EN57_p0s0r0 | NIFTY | 14,275 | 11,586 | -12,347 | 652 | -1,281 | 66 | 58 | -4,123 | 0 | 146 | 2024-01-18 | 4,181 | -1,395 |
| EN57_p0s0r0 | SENSEX | 2,449 | 1,921 | -4,599 | -4,089 | -1,125 | 12 | 11 | 1,987 | 2,422 | 0 | never | 3,557 | -1,125 |
| EN57_p0s0r1 | NIFTY | 15,952 | 12,448 | -12,347 | 2,195 | -1,281 | 67 | 58 | -4,123 | 0 | 146 | 2024-01-18 | 4,181 | -1,395 |
| EN57_p0s0r1 | SENSEX | 2,167 | 1,641 | -4,599 | -4,089 | -1,125 | 12 | 11 | 1,705 | 2,281 | 0 | never | 3,557 | -1,125 |
| EN57_p0s1r0 | NIFTY | 12,434 | 10,173 | -8,784 | 318 | -793 | 67 | 58 | 12,918 | 7,800 | 0 | never | 3,752 | -932 |
| EN57_p0s1r0 | SENSEX | 2,199 | 103 | -3,299 | -3,647 | -783 | 12 | 11 | 2,199 | 2,383 | 0 | never | 3,268 | -853 |
| EN57_p0s1r1 | NIFTY | 12,434 | 10,173 | -8,784 | 318 | -793 | 67 | 58 | 12,918 | 7,800 | 0 | never | 3,752 | -932 |
| EN57_p0s1r1 | SENSEX | 1,917 | -176 | -3,299 | -3,647 | -783 | 12 | 11 | 1,917 | 2,242 | 0 | never | 3,268 | -853 |
| EN57_p1s0r0 | NIFTY | 14,121 | 11,552 | 2,205 | 823 | -1,431 | 67 | 59 | -4,243 | 0 | 146 | 2024-01-18 | 4,302 | -1,470 |
| EN57_p1s0r0 | SENSEX | 2,836 | 2,565 | -1,374 | -3,530 | -1,032 | 10 | 9 | 2,260 | 2,476 | 0 | never | 3,486 | -1,119 |
| EN57_p1s0r1 | NIFTY | 15,823 | 13,222 | 3,894 | 1,737 | -1,431 | 68 | 59 | -4,243 | 0 | 146 | 2024-01-18 | 4,302 | -1,470 |
| EN57_p1s0r1 | SENSEX | 2,554 | 2,285 | -1,553 | -3,530 | -1,032 | 10 | 9 | 1,977 | 2,334 | 0 | never | 3,486 | -1,119 |
| EN57_p1s1r0 | NIFTY | 12,720 | 10,615 | 991 | 601 | -854 | 68 | 59 | 3,445 | 2,890 | 0 | never | 4,006 | -903 |
| EN57_p1s1r0 | SENSEX | 2,753 | 2,516 | -1,427 | -3,008 | -784 | 10 | 9 | 2,753 | 2,418 | 0 | never | 2,879 | -854 |
| EN57_p1s1r1 | NIFTY | 13,165 | 11,056 | 991 | 1,045 | -854 | 68 | 59 | 3,445 | 2,890 | 0 | never | 4,006 | -903 |
| EN57_p1s1r1 | SENSEX | 2,470 | 2,237 | -1,606 | -3,008 | -784 | 10 | 9 | 2,470 | 2,277 | 0 | never | 2,879 | -854 |
| EN61 | NIFTY | -612 | -4,065 | -6,581 | -3,855 | -733 | 39 | 39 | -3,028 | 0 | 0 | never | 3,102 | -811 |
| EN61 | SENSEX | -422 | 346 | -777 | -2,098 | -723 | 4 | 4 | -422 | 151 | 0 | never | 1,543 | -855 |
| EN61_r1_ctl | NIFTY | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |
| EN61_r1_ctl | SENSEX | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |
| EN61_r2_ctl | NIFTY | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |
| EN61_r2_ctl | SENSEX | 1,139 | 1,071 | 0 | 0 | 0 | 1 | 1 | 1,139 | 570 | 0 | never | 80 | -80 |
| EN61_r3_ctl | NIFTY | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |
| EN61_r3_ctl | SENSEX | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |
| EN61_r4_ctl | NIFTY | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |
| EN61_r4_ctl | SENSEX | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | never | 0 | 0 |

## Matched views used by the verdicts (evaluation sessions)

| Hypothesis | arm ord. | ctl ord. | arm adv. | ctl adv. | arm worst | ctl worst | arm w/o top 2 | arm wallet / halt | ctl wallet / halt |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| EN59|NIFTY | -5,969 | -415 | -6,423 | -1,190 | -651 | -959 | -7,663 | -1,608 / never | -1,936 / never |
| EN59|SENSEX | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 / never | 0 / never |
| EN60|NIFTY | -9,777 | 1,567 | -10,758 | 949 | -1,305 | -1,464 | -26,182 | -4,052 / 2023-09-28 | -4,103 / 2025-03-13 |
| EN60|SENSEX | -3,623 | 1,542 | -4,323 | 975 | -981 | -1,125 | -8,001 | -3,807 / 2026-07-23 | 1,687 / never |
| EN61|NIFTY | -612 | 7,220 | -4,065 | 6,290 | -733 | -1,464 | -3,855 | -3,028 / never | 7,070 / never |
| EN61|SENSEX | -422 | -142 | 346 | -194 | -723 | -142 | -2,098 | -422 / never | -142 / never |
| EN62|NIFTY | -16,264 | 4,784 | -21,707 | 3,467 | -1,149 | -1,464 | -23,686 | -1,940 / 2024-02-01 | 4,421 / never |
| EN62|SENSEX | -6,010 | -3,112 | -6,958 | -3,450 | -902 | -1,116 | -8,699 | -2,378 / never | -2,967 / never |
| EN63|NIFTY | 282 | -2,084 | -2,695 | -2,105 | -1,022 | -647 | -5,021 | -4,209 / 2026-04-28 | 169 / never |
| EN63|SENSEX | -503 | 942 | -1,282 | 1,155 | -1,351 | -582 | -2,971 | -503 / never | 942 / never |
| EN64|NIFTY | -11,906 | 1,567 | -17,228 | 949 | -967 | -1,464 | -22,585 | -4,037 / 2024-03-14 | -4,103 / 2025-03-13 |
| EN64|SENSEX | 0 | 1,542 | 0 | 975 | 0 | -1,125 | 0 | 0 / never | 1,687 / never |
| EN65|NIFTY | -2,105 | -1,182 | -4,138 | -3,250 | -992 | -992 | -6,564 | -4,079 / 2025-03-13 | -4,035 / 2025-02-13 |
| EN65|SENSEX | 1,151 | 1,330 | 800 | 987 | -836 | -836 | -2,730 | 1,151 / never | 1,330 / never |
| EN67|NIFTY | -7,120 | 13,165 | -10,817 | 11,056 | -1,170 | -854 | -19,240 | -4,273 / 2023-08-31 | 3,445 / never |
| EN67|SENSEX | 39 | 2,470 | -1,249 | 2,237 | -1,075 | -784 | -6,610 | 2,821 / 2026-04-23 | 2,470 / never |

## Random-side nulls (40 seeds, same trigger times)

| Slot | Index | primary (eval. sessions) | null median | null p10 | null p90 |
|---|---|---:|---:|---:|---:|
| EN60 | NIFTY | -9,777 | -13,885 | -24,960 | -1,045 |
| EN60 | SENSEX | -3,623 | -4,821 | -11,623 | -309 |
| EN62 | NIFTY | -16,264 | -10,665 | -16,735 | -3,109 |
| EN62 | SENSEX | -6,010 | -2,540 | -5,434 | -173 |
| EN64 | NIFTY | -11,906 | -5,505 | -13,076 | 6,696 |
| EN64 | SENSEX | 0 | 0 | 0 | 0 |

## Where each arm won and lost (ordinary fixed-cap tickets)

- **E032_30k NIFTY:** first exits: STOP 18 (0 won) -10,810; STRUCTURE 2 (0 won) -579; TARGET 3 (3 won) 3,048; TARGET_BASE 5 (5 won) 16,393; TIME 34 (18 won) 7,046; TRAIL 4 (1 won) -823. Sides: C 37 -569; P 29 14,844. Origins: E032 66 14,275. Years: 2023 -3,069; 2024 15,581; 2025 5,937; 2026 -4,173.
- **E032_30k SENSEX:** first exits: STOP 6 (0 won) -4,071; STRUCTURE 1 (0 won) -454; TARGET_BASE 1 (1 won) 5,255; TIME 4 (2 won) 1,719. Sides: C 5 -2,415; P 7 4,864. Origins: E032 12 2,449. Years: 2025 4,844; 2026 -2,395.
- **EN55 NIFTY:** first exits: STOP 19 (0 won) -8,340; STRUCTURE 2 (0 won) -412; TARGET 6 (6 won) 6,238; TARGET_BASE 2 (2 won) 11,790; TIME 34 (19 won) 4,265; TRAIL 5 (1 won) -376. Sides: C 38 -361; P 30 13,526. Origins: E032 68 13,165. Years: 2023 -3,040; 2024 13,205; 2025 5,334; 2026 -2,335.
- **EN55 SENSEX:** first exits: STOP 5 (0 won) -2,880; STRUCTURE 1 (0 won) -253; TARGET_BASE 1 (1 won) 4,950; TIME 3 (2 won) 654. Sides: C 3 -1,728; P 7 4,199. Origins: E032 10 2,470. Years: 2025 4,554; 2026 -2,084.
- **E032_sym NIFTY:** first exits: STOP 19 (0 won) -7,845; STRUCTURE 2 (0 won) -579; TARGET 6 (6 won) 6,531; TARGET_BASE 2 (2 won) 7,000; TIME 35 (18 won) 2,890; TRAIL 4 (1 won) -823. Sides: C 38 -819; P 30 7,993. Origins: E032 68 7,174. Years: 2023 -2,570; 2024 8,898; 2025 3,529; 2026 -2,682.
- **E032_sym SENSEX:** first exits: STOP 6 (0 won) -3,063; STRUCTURE 1 (0 won) -250; TARGET 1 (1 won) 1,698; TIME 3 (2 won) 857. Sides: C 5 -2,415; P 6 1,656. Origins: E032 11 -759. Years: 2025 1,625; 2026 -2,384.
- **E032_env NIFTY:** first exits: STOP 17 (0 won) -12,791; STRUCTURE 2 (0 won) -1,135; TARGET_BASE 6 (6 won) 13,216; TIME 31 (15 won) 3,568; TRAIL 3 (0 won) -1,290. Sides: C 34 -6,072; P 25 7,640. Origins: E032 59 1,567. Years: 2023 -5,652; 2024 4,558; 2025 6,689; 2026 -4,028.
- **E032_env SENSEX:** first exits: STOP 5 (0 won) -4,741; STRUCTURE 1 (0 won) -454; TARGET_BASE 1 (1 won) 5,255; TIME 4 (2 won) 1,481. Sides: C 4 -3,132; P 7 4,674. Origins: E032 11 1,542. Years: 2025 4,654; 2026 -3,112.
- **EN60 NIFTY:** first exits: CUSUM_REV 51 (6 won) -17,769; STOP 46 (0 won) -35,381; TARGET_BASE 14 (14 won) 35,315; TIME 43 (25 won) 8,481; TRAIL 5 (1 won) -422. Sides: C 70 14,054; P 89 -23,831. Origins: CUSUM 159 -9,777. Years: 2023 -9,629; 2024 3,185; 2025 -2,889; 2026 -444.
- **EN60 SENSEX:** first exits: CUSUM_REV 14 (2 won) -4,247; STOP 14 (0 won) -10,305; TARGET_BASE 4 (4 won) 6,546; TIME 16 (10 won) 4,383. Sides: C 18 2,156; P 30 -5,779. Origins: CUSUM 48 -3,623. Years: 2025 -4,865; 2026 1,242.
- **EN60_orb5_ctl NIFTY:** first exits: FSTOP 107 (3 won) -33,313; STOP 9 (0 won) -6,787; TARGET 1 (1 won) 1,196; TARGET_BASE 5 (5 won) 9,020; TIME 32 (19 won) 7,366; TRAIL 1 (1 won) 168. Sides: C 77 -8,626; P 78 -13,724. Origins: CUSUM_ORB5 155 -22,351. Years: 2023 -8,492; 2024 -8,126; 2025 -5,266; 2026 -467.
- **EN60_orb5_ctl SENSEX:** first exits: FSTOP 30 (1 won) -9,623; STOP 2 (0 won) -1,396; TARGET_BASE 5 (5 won) 7,650; TIME 11 (7 won) 2,931; TRAIL 2 (1 won) 59. Sides: C 24 -393; P 26 14. Origins: CUSUM_ORB5 50 -379. Years: 2025 1,078; 2026 -1,458.
- **EN60_1250_diag NIFTY:** first exits: CUSUM_REV 49 (6 won) -9,405; STOP 41 (0 won) -16,890; TARGET 12 (12 won) 14,987; TARGET_BASE 3 (3 won) 2,392; TIME 42 (21 won) 2,457; TRAIL 5 (1 won) -353. Sides: C 67 4,008; P 85 -10,819. Origins: CUSUM 152 -6,811. Years: 2023 -6,285; 2024 -95; 2025 -406; 2026 -26.
- **EN60_1250_diag SENSEX:** first exits: CUSUM_REV 13 (1 won) -2,791; STOP 15 (0 won) -5,906; TARGET 4 (4 won) 5,339; TIME 14 (9 won) 2,011. Sides: C 17 1,506; P 29 -2,853. Origins: CUSUM 46 -1,347. Years: 2025 -2,333; 2026 986.
- **EN62 NIFTY:** first exits: FSTOP 19 (0 won) -9,255; RESID_TARGET 10 (6 won) 8,660; STOP 32 (0 won) -25,041; TIME 33 (16 won) 9,373. Sides: C 53 -10,176; P 41 -6,088. Origins: RESID 94 -16,264. Years: 2023 -4,868; 2024 -3,965; 2025 1,449; 2026 -8,880.
- **EN62 SENSEX:** first exits: FSTOP 7 (1 won) -3,445; RESID_TARGET 3 (2 won) 1,184; STOP 5 (0 won) -3,767; TIME 7 (2 won) 19. Sides: C 12 -4,020; P 10 -1,990. Origins: RESID 22 -6,010. Years: 2025 1,419; 2026 -7,429.
- **EN62_dir_ctl NIFTY:** first exits: FSTOP 55 (0 won) -22,805; STOP 30 (0 won) -22,965; TIME 90 (50 won) 23,224. Sides: C 87 -13,632; P 88 -8,914. Origins: RESID_DIR 175 -22,546. Years: 2023 -6,241; 2024 -1,546; 2025 -3,224; 2026 -11,536.
- **EN62_dir_ctl SENSEX:** first exits: FSTOP 18 (1 won) -7,685; STOP 5 (0 won) -4,889; TIME 19 (9 won) 3,878. Sides: C 22 -8,041; P 20 -656. Origins: RESID_DIR 42 -8,697. Years: 2025 -751; 2026 -7,945.
- **EN62_decay_ctl NIFTY:** first exits: FSTOP 7 (0 won) -3,202; RESID_TARGET 5 (5 won) 7,012; STOP 9 (0 won) -6,783; TIME 7 (3 won) -175. Sides: C 18 1,125; P 10 -4,273. Origins: RESID_DECAY 28 -3,148. Years: 2023 -1,352; 2024 -2,709; 2025 1,528; 2026 -616.
- **EN62_decay_ctl SENSEX:** first exits: RESID_TARGET 1 (1 won) 1,654; TIME 3 (3 won) 518. Sides: C 3 2,044; P 1 128. Origins: RESID_DECAY 4 2,172. Years: 2025 0; 2026 2,172.
- **EN62_1250_diag NIFTY:** first exits: FSTOP 19 (0 won) -5,010; RESID_TARGET 10 (6 won) 3,251; STOP 33 (0 won) -13,659; TIME 32 (16 won) 4,200. Sides: C 52 -8,515; P 42 -2,703. Origins: RESID 94 -11,218. Years: 2023 -3,931; 2024 -2,950; 2025 357; 2026 -4,694.
- **EN62_1250_diag SENSEX:** first exits: FSTOP 7 (1 won) -1,825; RESID_TARGET 2 (1 won) 366; STOP 4 (0 won) -1,697; TIME 8 (3 won) 460. Sides: C 10 -2,080; P 11 -616. Origins: RESID 21 -2,696. Years: 2025 930; 2026 -3,626.
- **EN64 NIFTY:** first exits: EFF_EXIT 72 (5 won) -16,537; FSTOP 33 (0 won) -13,814; STOP 15 (0 won) -9,971; TARGET 1 (1 won) 1,202; TARGET_BASE 8 (8 won) 18,693; TIME 31 (21 won) 8,612; TRAIL 6 (3 won) -90. Sides: C 77 -5,252; P 89 -6,654. Origins: IMPACT 166 -11,906. Years: 2023 -4,720; 2024 -8,917; 2025 6,794; 2026 -5,063.
- **EN64_ret_ctl NIFTY:** first exits: EFF_EXIT 83 (6 won) -17,974; FSTOP 20 (0 won) -8,532; STOP 21 (0 won) -16,393; TARGET 1 (1 won) 1,196; TARGET_BASE 3 (3 won) 3,612; TIME 35 (21 won) 10,275; TRAIL 6 (5 won) 535. Sides: C 82 -7,440; P 87 -19,841. Origins: IMPACT_RET 169 -27,282. Years: 2023 -3,682; 2024 -12,329; 2025 -6,246; 2026 -5,024.
- **EN64_ret_ctl SENSEX:** first exits: EFF_EXIT 18 (2 won) -1,734; FSTOP 17 (0 won) -5,271; STOP 2 (0 won) -1,626; TARGET_BASE 1 (1 won) 2,060; TIME 14 (9 won) 6,616; TRAIL 2 (2 won) 83. Sides: C 24 -2,240; P 30 2,368. Origins: IMPACT_RET 54 128. Years: 2025 87; 2026 41.
- **EN64_vol_ctl NIFTY:** first exits: EFF_EXIT 59 (0 won) -17,689; FSTOP 50 (1 won) -19,063; STOP 18 (0 won) -14,235; TARGET 2 (2 won) 3,273; TARGET_BASE 6 (6 won) 11,528; TIME 23 (13 won) 6,439; TRAIL 8 (5 won) -88. Sides: C 77 -9,389; P 89 -20,446. Origins: IMPACT_VOL 166 -29,835. Years: 2023 -12,925; 2024 -8,261; 2025 -6,593; 2026 -2,056.
- **EN64_1250_diag NIFTY:** first exits: EFF_EXIT 71 (4 won) -9,689; FSTOP 33 (0 won) -7,521; STOP 16 (0 won) -5,768; TARGET 6 (6 won) 7,450; TARGET_BASE 4 (4 won) 3,580; TIME 29 (16 won) 3,031; TRAIL 7 (3 won) -271. Sides: C 78 -1,606; P 88 -7,582. Origins: IMPACT 166 -9,188. Years: 2023 -2,554; 2024 -2,322; 2025 -1,452; 2026 -2,859.
- **EN63 NIFTY:** first exits: STOP 19 (0 won) -11,208; STRUCTURE 11 (0 won) -5,079; TARGET 5 (5 won) 10,376; TIME 25 (17 won) 6,264; TRAIL 4 (1 won) -70. Sides: C 36 -993; P 28 1,275. Origins: E032 64 282. Years: 2023 -3,450; 2024 483; 2025 5,740; 2026 -2,491.
- **EN63 SENSEX:** first exits: STOP 2 (0 won) -2,450; STRUCTURE 1 (0 won) -354; TARGET 1 (1 won) 2,468; TRAIL 2 (0 won) -166. Sides: C 1 -1,100; P 5 597. Origins: E032 6 -503. Years: 2025 985; 2026 -1,488.
- **EN63_native8_ctl NIFTY:** first exits: STOP 18 (0 won) -6,486; STRUCTURE 2 (0 won) -441; TARGET 5 (5 won) 4,924; TIME 30 (14 won) 490; TRAIL 3 (0 won) -571. Sides: C 33 -2,828; P 25 744. Origins: E032 58 -2,084. Years: 2023 -2,917; 2024 -85; 2025 2,926; 2026 -2,008.
- **EN63_native8_ctl SENSEX:** first exits: STOP 2 (0 won) -988; STRUCTURE 1 (0 won) -250; TARGET 1 (1 won) 1,698; TIME 4 (2 won) 483. Sides: C 2 -676; P 6 1,619. Origins: E032 8 942. Years: 2025 1,435; 2026 -492.
- **EN63_native15 NIFTY:** first exits: STOP 23 (0 won) -8,516; STRUCTURE 5 (0 won) -1,361; TARGET 5 (5 won) 4,924; TIME 21 (15 won) 2,603; TRAIL 4 (0 won) -606. Sides: C 33 -2,812; P 25 -145. Origins: E032 58 -2,956. Years: 2023 -2,411; 2024 -435; 2025 2,429; 2026 -2,540.
- **EN63_native15 SENSEX:** first exits: STOP 2 (0 won) -988; STRUCTURE 1 (0 won) -250; TARGET 1 (1 won) 1,698; TIME 2 (2 won) 326; TRAIL 2 (0 won) -162. Sides: C 2 -425; P 6 1,049. Origins: E032 8 624. Years: 2025 1,214; 2026 -590.
- **EN63_liq8 NIFTY:** first exits: STOP 14 (0 won) -8,597; STRUCTURE 7 (0 won) -3,180; TARGET 4 (4 won) 9,225; TIME 38 (18 won) 4,487; TRAIL 1 (0 won) -34. Sides: C 36 -838; P 28 2,738. Origins: E032 64 1,900. Years: 2023 -4,349; 2024 1,174; 2025 6,577; 2026 -1,502.
- **EN63_liq8 SENSEX:** first exits: STOP 2 (0 won) -2,450; STRUCTURE 1 (0 won) -354; TARGET 1 (1 won) 2,468; TIME 2 (2 won) 1,487. Sides: C 1 -1,100; P 5 2,251. Origins: E032 6 1,151. Years: 2025 1,654; 2026 -503.
- **EN63_cash_diag NIFTY:** first exits: STOP 21 (0 won) -12,296; STRUCTURE 5 (0 won) -1,846; TARGET_BASE 4 (4 won) 10,061; TIME 21 (16 won) 4,714; TRAIL 3 (0 won) -1,002. Sides: C 30 -4,074; P 24 3,705. Origins: E032 54 -368. Years: 2023 -3,460; 2024 1,527; 2025 5,182; 2026 -3,617.
- **EN63_cash_diag SENSEX:** first exits: STOP 2 (0 won) -1,881; STRUCTURE 1 (0 won) -250; TARGET 1 (1 won) 1,698; TRAIL 2 (0 won) -223. Sides: C 1 -1,116; P 5 459. Origins: E032 6 -657. Years: 2025 794; 2026 -1,451.
- **EN65 NIFTY:** first exits: CHILD_STOP 6 (0 won) -922; CORE_BANK 6 (6 won) 9,886; STOP 18 (0 won) -10,386; STRUCTURE 2 (0 won) -925; TIME 31 (15 won) 1,533; TRAIL 3 (0 won) -1,290. Sides: C 36 -5,574; P 30 3,469. Origins: CHILD 6 -922; E032 60 -1,182. Years: 2023 -4,628; 2024 1,609; 2025 4,236; 2026 -3,321.
- **EN65 SENSEX:** first exits: CHILD_STOP 1 (0 won) -180; CORE_BANK 1 (1 won) 3,443; STOP 4 (0 won) -2,725; STRUCTURE 1 (0 won) -250; TIME 4 (2 won) 864. Sides: C 4 -2,055; P 7 3,205. Origins: CHILD 1 -180; E032 10 1,330. Years: 2025 3,021; 2026 -1,871.
- **EN65_bank_ctl NIFTY:** first exits: CORE_BANK 6 (6 won) 9,886; STOP 18 (0 won) -10,386; STRUCTURE 2 (0 won) -925; TIME 31 (15 won) 1,533; TRAIL 3 (0 won) -1,290. Sides: C 34 -5,268; P 26 4,085. Origins: E032 60 -1,182. Years: 2023 -4,628; 2024 2,225; 2025 4,542; 2026 -3,321.
- **EN65_bank_ctl SENSEX:** first exits: CORE_BANK 1 (1 won) 3,443; STOP 4 (0 won) -2,725; STRUCTURE 1 (0 won) -250; TIME 4 (2 won) 864. Sides: C 4 -2,055; P 6 3,385. Origins: E032 10 1,330. Years: 2025 3,201; 2026 -1,871.
- **EN65_en12_diag NIFTY:** first exits: STOP 17 (0 won) -12,791; STRUCTURE 2 (0 won) -1,135; TARGET 1 (1 won) 1,992; TARGET_BASE 5 (5 won) 12,169; TIME 31 (15 won) 3,568; TRAIL 3 (0 won) -1,290. Sides: C 34 -6,072; P 25 8,585. Origins: E032 59 2,512. Years: 2023 -5,652; 2024 4,558; 2025 7,634; 2026 -4,028.
- **EN65_en12_diag SENSEX:** first exits: STOP 5 (0 won) -4,741; STRUCTURE 1 (0 won) -454; TARGET_BASE 1 (1 won) 5,346; TIME 4 (2 won) 1,481. Sides: C 4 -3,132; P 7 4,764. Origins: E032 11 1,632. Years: 2025 4,745; 2026 -3,112.
- **EN59 NIFTY:** first exits: LEG_OUT 4 (3 won) 1,849; PACKAGE_FLOOR 1 (1 won) 634; STOP 16 (0 won) -8,452. Sides: S 21 -5,969. Origins: PAIR 21 -5,969. Years: 2023 -3,984; 2024 -39; 2025 -1,946; 2026 0.
- **EN59_en52_ctl NIFTY:** first exits: FLAT_TIME 1 (1 won) 1,507; LEG_OUT 6 (3 won) 5,783; RUNNER_TRAIL 1 (0 won) -933; STOP 13 (0 won) -6,772. Sides: S 21 -415. Origins: PAIR 21 -415. Years: 2023 -5,057; 2024 834; 2025 3,808; 2026 0.
- **EN59_en52_5000 NIFTY:** first exits: FLAT_TIME 8 (7 won) 23,735; HERO_TARGET 1 (1 won) 13,977; LEG_OUT 45 (18 won) 43,104; ONE_LEG 1 (0 won) -60; RUNNER_TRAIL 35 (2 won) -27,879; STOP 44 (0 won) -36,325. Sides: S 134 16,554. Origins: PAIR 134 16,554. Years: 2023 -3,861; 2024 8,258; 2025 11,473; 2026 684.
- **EN59_en52_5000 SENSEX:** first exits: FLAT_TIME 4 (3 won) 8,360; LEG_OUT 14 (7 won) 619; ONE_LEG 1 (0 won) -74; RUNNER_TRAIL 5 (0 won) -4,934; STOP 12 (0 won) -12,322. Sides: S 36 -8,351. Origins: PAIR 36 -8,351. Years: 2025 3,993; 2026 -12,343.
- **EN59_closeb_diag NIFTY:** first exits: STOP 16 (0 won) -8,452; TARGET 5 (5 won) 6,152. Sides: S 21 -2,300. Origins: PAIR 21 -2,300. Years: 2023 -3,572; 2024 3,439; 2025 -2,167; 2026 0.
- **EN59_en51_2500 NIFTY:** first exits: STOP 17 (0 won) -8,969; TARGET 4 (4 won) 6,598. Sides: S 21 -2,371. Origins: PAIR 21 -2,371. Years: 2023 -3,131; 2024 3,786; 2025 -3,026; 2026 0.
- **EN67 NIFTY:** first exits: STOP 59 (0 won) -26,423; STRUCTURE 16 (0 won) -4,982; TARGET 9 (9 won) 9,872; TARGET_BASE 2 (2 won) 11,790; TIME 112 (50 won) 3,723; TRAIL 6 (0 won) -1,101. Sides: C 96 -6,323; P 108 -797. Origins: E032 204 -7,120. Years: 2023 -5,030; 2024 3,513; 2025 -959; 2026 -4,645.
- **EN67 SENSEX:** first exits: STOP 14 (0 won) -7,320; STRUCTURE 5 (0 won) -1,609; TARGET 1 (1 won) 1,386; TARGET_BASE 2 (2 won) 6,271; TIME 19 (10 won) 1,310. Sides: C 13 -3,391; P 28 3,430. Origins: E032 41 39. Years: 2025 5,628; 2026 -5,589.
- **EN67_e5_s750_diag NIFTY:** first exits: STOP 78 (0 won) -36,317; STRUCTURE 32 (0 won) -9,720; TARGET 11 (11 won) 10,524; TARGET_BASE 3 (3 won) 3,477; TIME 169 (64 won) -1,531; TRAIL 8 (1 won) -1,221. Sides: C 151 -10,091; P 150 -24,697. Origins: E032 301 -34,788. Years: 2023 -10,503; 2024 -10,181; 2025 -2,410; 2026 -11,695.
- **EN67_e5_s750_diag SENSEX:** first exits: STOP 25 (0 won) -13,196; STRUCTURE 7 (0 won) -1,964; TARGET 4 (4 won) 3,977; TARGET_BASE 1 (1 won) 1,321; TIME 36 (17 won) 1,224. Sides: C 32 -4,497; P 41 -4,141. Origins: E032 73 -8,639. Years: 2025 -1,250; 2026 -7,388.
- **EN67_e5_s780_diag NIFTY:** first exits: STOP 90 (0 won) -42,285; STRUCTURE 21 (0 won) -5,918; TARGET 7 (7 won) 6,650; TARGET_BASE 4 (4 won) 13,800; TIME 140 (64 won) 6,214; TRAIL 12 (0 won) -2,078. Sides: C 129 -11,867; P 145 -11,749. Origins: E032 274 -23,616. Years: 2023 -8,177; 2024 -1,017; 2025 -2,537; 2026 -11,886.
- **EN67_e5_s780_diag SENSEX:** first exits: STOP 27 (0 won) -13,999; STRUCTURE 6 (0 won) -1,668; TARGET 4 (4 won) 3,977; TIME 30 (12 won) 800. Sides: C 28 -4,242; P 39 -6,648. Origins: E032 67 -10,890. Years: 2025 -2,901; 2026 -7,989.
- **EN67_e6_s750_diag NIFTY:** first exits: STOP 59 (0 won) -26,423; STRUCTURE 16 (0 won) -4,982; TARGET 9 (9 won) 9,872; TARGET_BASE 2 (2 won) 11,790; TIME 112 (50 won) 3,723; TRAIL 6 (0 won) -1,101. Sides: C 96 -6,323; P 108 -797. Origins: E032 204 -7,120. Years: 2023 -5,030; 2024 3,513; 2025 -959; 2026 -4,645.
- **EN67_e6_s750_diag SENSEX:** first exits: STOP 14 (0 won) -7,320; STRUCTURE 5 (0 won) -1,609; TARGET 1 (1 won) 1,386; TARGET_BASE 2 (2 won) 6,271; TIME 19 (10 won) 1,310. Sides: C 13 -3,391; P 28 3,430. Origins: E032 41 39. Years: 2025 5,628; 2026 -5,589.
- **EN67_e6_s780_diag NIFTY:** first exits: STOP 57 (0 won) -25,762; STRUCTURE 10 (0 won) -2,982; TARGET 6 (6 won) 6,118; TARGET_BASE 3 (3 won) 13,266; TIME 84 (50 won) 10,590; TRAIL 6 (0 won) -1,101. Sides: C 75 -5,566; P 91 5,694. Origins: E032 166 129. Years: 2023 -3,797; 2024 6,278; 2025 2,952; 2026 -5,304.
- **EN67_e6_s780_diag SENSEX:** first exits: STOP 14 (0 won) -7,320; STRUCTURE 4 (0 won) -1,180; TARGET 1 (1 won) 1,386; TARGET_BASE 1 (1 won) 4,950; TIME 16 (8 won) 971. Sides: C 11 -3,301; P 25 2,108. Origins: E032 36 -1,193. Years: 2025 4,922; 2026 -6,114.
- **EN67_e7_s750_diag NIFTY:** first exits: STOP 24 (0 won) -10,674; STRUCTURE 5 (0 won) -1,743; TARGET 7 (7 won) 8,163; TARGET_BASE 2 (2 won) 11,790; TIME 46 (21 won) 2,646; TRAIL 5 (1 won) -376. Sides: C 51 -1,121; P 38 10,928. Origins: E032 89 9,806. Years: 2023 -4,258; 2024 12,187; 2025 3,692; 2026 -1,815.
- **EN67_e7_s750_diag SENSEX:** first exits: STOP 5 (0 won) -2,880; STRUCTURE 2 (0 won) -682; TARGET_BASE 1 (1 won) 4,950; TIME 3 (2 won) 654. Sides: C 4 -2,157; P 7 4,199. Origins: E032 11 2,041. Years: 2025 4,125; 2026 -2,084.
- **EN67_e7_s780_diag NIFTY:** first exits: STOP 19 (0 won) -8,340; STRUCTURE 2 (0 won) -412; TARGET 6 (6 won) 6,238; TARGET_BASE 2 (2 won) 11,790; TIME 34 (19 won) 4,265; TRAIL 5 (1 won) -376. Sides: C 38 -361; P 30 13,526. Origins: E032 68 13,165. Years: 2023 -3,040; 2024 13,205; 2025 5,334; 2026 -2,335.
- **EN67_e7_s780_diag SENSEX:** first exits: STOP 5 (0 won) -2,880; STRUCTURE 1 (0 won) -253; TARGET_BASE 1 (1 won) 4,950; TIME 3 (2 won) 654. Sides: C 3 -1,728; P 7 4,199. Origins: E032 10 2,470. Years: 2025 4,554; 2026 -2,084.
- **EN67_e8_s750_diag NIFTY:** first exits: STOP 6 (0 won) -2,257; STRUCTURE 2 (0 won) -690; TARGET 1 (1 won) 1,077; TARGET_BASE 2 (2 won) 11,790; TIME 13 (7 won) 1,639; TRAIL 4 (1 won) -168. Sides: C 17 -2,141; P 11 13,533. Origins: E032 28 11,392. Years: 2023 -572; 2024 11,436; 2025 1,444; 2026 -916.
- **EN67_e8_s750_diag SENSEX:** first exits: STOP 2 (0 won) -1,173; TARGET_BASE 1 (1 won) 4,950. Sides: C 2 -1,173; P 1 4,950. Origins: E032 3 3,776. Years: 2025 4,950; 2026 -1,173.
- **EN67_e8_s780_diag NIFTY:** first exits: STOP 5 (0 won) -1,958; STRUCTURE 1 (0 won) -230; TARGET 1 (1 won) 1,077; TARGET_BASE 2 (2 won) 11,790; TIME 11 (7 won) 1,954; TRAIL 4 (1 won) -168. Sides: C 15 -1,598; P 9 14,062. Origins: E032 24 12,464. Years: 2023 -572; 2024 11,681; 2025 1,974; 2026 -618.
- **EN67_e8_s780_diag SENSEX:** first exits: STOP 2 (0 won) -1,173; TARGET_BASE 1 (1 won) 4,950. Sides: C 2 -1,173; P 1 4,950. Origins: E032 3 3,776. Years: 2025 4,950; 2026 -1,173.
- **EN57_p0s0r0 NIFTY:** first exits: STOP 18 (0 won) -10,810; STRUCTURE 2 (0 won) -579; TARGET 3 (3 won) 3,048; TARGET_BASE 5 (5 won) 16,393; TIME 34 (18 won) 7,046; TRAIL 4 (1 won) -823. Sides: C 37 -569; P 29 14,844. Origins: E032 66 14,275. Years: 2023 -3,069; 2024 15,581; 2025 5,937; 2026 -4,173.
- **EN57_p0s0r0 SENSEX:** first exits: STOP 6 (0 won) -4,071; STRUCTURE 1 (0 won) -454; TARGET_BASE 1 (1 won) 5,255; TIME 4 (2 won) 1,719. Sides: C 5 -2,415; P 7 4,864. Origins: E032 12 2,449. Years: 2025 4,844; 2026 -2,395.
- **EN57_p0s0r1 NIFTY:** first exits: STOP 18 (0 won) -10,810; STRUCTURE 2 (0 won) -579; TARGET 3 (3 won) 3,048; TARGET_BASE 5 (5 won) 18,320; TIME 35 (18 won) 6,796; TRAIL 4 (1 won) -823. Sides: C 38 -971; P 29 16,923. Origins: E032 67 15,952. Years: 2023 -3,069; 2024 16,482; 2025 6,712; 2026 -4,173.
- **EN57_p0s0r1 SENSEX:** first exits: STOP 6 (0 won) -4,071; STRUCTURE 1 (0 won) -454; TARGET_BASE 1 (1 won) 4,972; TIME 4 (2 won) 1,719. Sides: C 5 -2,415; P 7 4,581. Origins: E032 12 2,167. Years: 2025 4,562; 2026 -2,395.
- **EN57_p0s1r0 NIFTY:** first exits: STOP 19 (0 won) -8,156; STRUCTURE 2 (0 won) -441; TARGET 6 (6 won) 6,344; TARGET_BASE 2 (2 won) 11,352; TIME 34 (17 won) 3,837; TRAIL 4 (1 won) -502. Sides: C 38 -613; P 29 13,047. Origins: E032 67 12,434. Years: 2023 -3,176; 2024 13,244; 2025 5,049; 2026 -2,682.
- **EN57_p0s1r0 SENSEX:** first exits: STOP 6 (0 won) -3,422; STRUCTURE 1 (0 won) -250; TARGET_BASE 1 (1 won) 5,228; TIME 4 (2 won) 644. Sides: C 5 -2,415; P 7 4,614. Origins: E032 12 2,199. Years: 2025 4,767; 2026 -2,568.
- **EN57_p0s1r1 NIFTY:** first exits: STOP 19 (0 won) -8,156; STRUCTURE 2 (0 won) -441; TARGET 6 (6 won) 6,344; TARGET_BASE 2 (2 won) 11,352; TIME 34 (17 won) 3,837; TRAIL 4 (1 won) -502. Sides: C 38 -613; P 29 13,047. Origins: E032 67 12,434. Years: 2023 -3,176; 2024 13,244; 2025 5,049; 2026 -2,682.
- **EN57_p0s1r1 SENSEX:** first exits: STOP 6 (0 won) -3,422; STRUCTURE 1 (0 won) -250; TARGET_BASE 1 (1 won) 4,946; TIME 4 (2 won) 644. Sides: C 5 -2,415; P 7 4,331. Origins: E032 12 1,917. Years: 2025 4,484; 2026 -2,568.
- **EN57_p1s0r0 NIFTY:** first exits: STOP 18 (0 won) -11,323; STRUCTURE 2 (0 won) -546; TARGET 3 (3 won) 3,087; TARGET_BASE 7 (7 won) 18,861; TIME 32 (18 won) 4,666; TRAIL 5 (2 won) -623. Sides: C 37 -478; P 30 14,598. Origins: E032 67 14,121. Years: 2023 -3,294; 2024 15,009; 2025 6,073; 2026 -3,668.
- **EN57_p1s0r0 SENSEX:** first exits: STOP 5 (0 won) -3,610; STRUCTURE 1 (0 won) -460; TARGET_BASE 1 (1 won) 5,261; TIME 3 (2 won) 1,645. Sides: C 3 -1,728; P 7 4,564. Origins: E032 10 2,836. Years: 2025 4,951; 2026 -2,115.
- **EN57_p1s0r1 NIFTY:** first exits: STOP 18 (0 won) -11,323; STRUCTURE 2 (0 won) -546; TARGET 3 (3 won) 3,087; TARGET_BASE 7 (7 won) 20,800; TIME 33 (18 won) 4,429; TRAIL 5 (2 won) -623. Sides: C 38 -867; P 30 16,691. Origins: E032 68 15,823. Years: 2023 -3,294; 2024 15,924; 2025 6,862; 2026 -3,668.
- **EN57_p1s0r1 SENSEX:** first exits: STOP 5 (0 won) -3,610; STRUCTURE 1 (0 won) -460; TARGET_BASE 1 (1 won) 4,978; TIME 3 (2 won) 1,645. Sides: C 3 -1,728; P 7 4,282. Origins: E032 10 2,554. Years: 2025 4,669; 2026 -2,115.
- **EN57_p1s1r0 NIFTY:** first exits: STOP 19 (0 won) -8,340; STRUCTURE 2 (0 won) -412; TARGET 6 (6 won) 6,238; TARGET_BASE 2 (2 won) 11,346; TIME 34 (19 won) 4,265; TRAIL 5 (1 won) -376. Sides: C 38 -361; P 30 13,082. Origins: E032 68 12,720. Years: 2023 -3,040; 2024 12,761; 2025 5,334; 2026 -2,335.
- **EN57_p1s1r0 SENSEX:** first exits: STOP 5 (0 won) -2,880; STRUCTURE 1 (0 won) -253; TARGET_BASE 1 (1 won) 5,232; TIME 3 (2 won) 654. Sides: C 3 -1,728; P 7 4,481. Origins: E032 10 2,753. Years: 2025 4,837; 2026 -2,084.
- **EN57_p1s1r1 NIFTY:** first exits: STOP 19 (0 won) -8,340; STRUCTURE 2 (0 won) -412; TARGET 6 (6 won) 6,238; TARGET_BASE 2 (2 won) 11,790; TIME 34 (19 won) 4,265; TRAIL 5 (1 won) -376. Sides: C 38 -361; P 30 13,526. Origins: E032 68 13,165. Years: 2023 -3,040; 2024 13,205; 2025 5,334; 2026 -2,335.
- **EN57_p1s1r1 SENSEX:** first exits: STOP 5 (0 won) -2,880; STRUCTURE 1 (0 won) -253; TARGET_BASE 1 (1 won) 4,950; TIME 3 (2 won) 654. Sides: C 3 -1,728; P 7 4,199. Origins: E032 10 2,470. Years: 2025 4,554; 2026 -2,084.
- **EN61 NIFTY:** first exits: LOSS 20 (0 won) -9,874; TIMEOUT 11 (6 won) 1,168; WIN 8 (8 won) 8,094. Sides: C 24 -76; P 15 -536. Origins: EN61_HGB 39 -612. Years: 2023 0; 2024 -1,731; 2025 1,879; 2026 -760.
- **EN61 SENSEX:** first exits: LOSS 3 (0 won) -2,098; WIN 1 (1 won) 1,676. Sides: C 1 -723; P 3 301. Origins: EN61_HGB 4 -422. Years: 2025 0; 2026 -422.
- **EN61_r2_ctl SENSEX:** first exits: TIME 1 (1 won) 1,139. Sides: C 1 1,139. Origins: EN61_R2 1 1,139. Years: 2025 0; 2026 1,139.

## EN56: the opportunity library

### NIFTY (315,200 rows)

| Reserve · horizon · strike | decisions | filled | unaffordable | no fill | net / decision | net / fill | share > 0 | gross / fill | fees / fill | slippage / fill | no-spread net / fill | MAE | MFE | ever net-positive |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Rs 1250 · 3 min · ITM1 | 9850 | 5 | 9813 | 0 | 0 | 66 | 40.0% | 116 | 50 | 6 | 72 | -142 | 234 | 40.0% |
| Rs 1250 · 3 min · ATM | 9850 | 2319 | 7471 | 35 | -15 | -63 | 28.5% | -14 | 49 | 8 | -55 | -182 | 89 | 41.5% |
| Rs 1250 · 3 min · OTM1 | 9850 | 7169 | 2474 | 167 | -49 | -68 | 26.6% | -19 | 49 | 12 | -55 | -179 | 84 | 39.0% |
| Rs 1250 · 3 min · OTM2 | 9850 | 8575 | 794 | 406 | -59 | -67 | 19.6% | -19 | 49 | 16 | -51 | -155 | 65 | 28.9% |
| Rs 1250 · 8 min · ITM1 | 9850 | 5 | 9813 | 0 | 0 | 28 | 80.0% | 77 | 50 | 6 | 34 | -182 | 448 | 80.0% |
| Rs 1250 · 8 min · ATM | 9850 | 2319 | 7471 | 35 | -16 | -67 | 31.9% | -17 | 49 | 8 | -59 | -257 | 193 | 58.0% |
| Rs 1250 · 8 min · OTM1 | 9850 | 7169 | 2474 | 167 | -56 | -77 | 28.6% | -27 | 49 | 12 | -64 | -251 | 186 | 55.0% |
| Rs 1250 · 8 min · OTM2 | 9850 | 8575 | 794 | 406 | -67 | -76 | 22.6% | -28 | 49 | 16 | -60 | -212 | 148 | 43.7% |
| Rs 1250 · 15 min · ITM1 | 9850 | 5 | 9813 | 0 | 0 | 4 | 60.0% | 54 | 50 | 6 | 11 | -267 | 562 | 80.0% |
| Rs 1250 · 15 min · ATM | 9850 | 2319 | 7471 | 35 | -19 | -82 | 30.3% | -33 | 49 | 8 | -74 | -326 | 306 | 66.5% |
| Rs 1250 · 15 min · OTM1 | 9850 | 7169 | 2474 | 167 | -63 | -87 | 28.0% | -38 | 49 | 12 | -75 | -319 | 300 | 63.3% |
| Rs 1250 · 15 min · OTM2 | 9850 | 8575 | 794 | 406 | -81 | -93 | 21.8% | -44 | 49 | 16 | -76 | -265 | 238 | 52.1% |
| Rs 1250 · 30 min · ITM1 | 9850 | 5 | 9813 | 0 | -0 | -410 | 20.0% | -361 | 49 | 6 | -403 | -538 | 562 | 80.0% |
| Rs 1250 · 30 min · ATM | 9850 | 2319 | 7471 | 35 | -31 | -133 | 24.8% | -84 | 49 | 8 | -125 | -445 | 493 | 73.2% |
| Rs 1250 · 30 min · OTM1 | 9850 | 7169 | 2474 | 167 | -85 | -116 | 23.7% | -67 | 49 | 12 | -104 | -426 | 508 | 70.1% |
| Rs 1250 · 30 min · OTM2 | 9850 | 8575 | 794 | 406 | -102 | -117 | 18.2% | -68 | 49 | 16 | -100 | -351 | 413 | 59.2% |
| Rs 2500 · 3 min · ITM1 | 9850 | 296 | 9518 | 4 | -2 | -62 | 38.5% | -10 | 52 | 7 | -56 | -307 | 207 | 53.7% |
| Rs 2500 · 3 min · ATM | 9850 | 6883 | 2849 | 93 | -48 | -68 | 36.4% | -17 | 51 | 10 | -59 | -292 | 197 | 54.2% |
| Rs 2500 · 3 min · OTM1 | 9850 | 9045 | 571 | 194 | -65 | -71 | 31.6% | -20 | 51 | 16 | -55 | -271 | 179 | 47.1% |
| Rs 2500 · 3 min · OTM2 | 9850 | 9216 | 143 | 416 | -66 | -70 | 22.5% | -21 | 49 | 18 | -52 | -203 | 115 | 33.8% |
| Rs 2500 · 8 min · ITM1 | 9850 | 296 | 9518 | 4 | -3 | -95 | 38.9% | -43 | 52 | 7 | -88 | -472 | 388 | 64.5% |
| Rs 2500 · 8 min · ATM | 9850 | 6883 | 2849 | 93 | -52 | -75 | 37.5% | -23 | 51 | 10 | -65 | -434 | 387 | 68.1% |
| Rs 2500 · 8 min · OTM1 | 9850 | 9045 | 571 | 194 | -75 | -82 | 32.2% | -32 | 51 | 16 | -66 | -398 | 362 | 61.4% |
| Rs 2500 · 8 min · OTM2 | 9850 | 9216 | 143 | 416 | -75 | -80 | 24.5% | -31 | 49 | 18 | -62 | -287 | 241 | 47.6% |
| Rs 2500 · 15 min · ITM1 | 9850 | 296 | 9518 | 4 | -3 | -105 | 37.5% | -53 | 52 | 7 | -98 | -611 | 561 | 71.3% |
| Rs 2500 · 15 min · ATM | 9850 | 6883 | 2849 | 93 | -61 | -87 | 35.6% | -36 | 51 | 10 | -77 | -566 | 585 | 75.0% |
| Rs 2500 · 15 min · OTM1 | 9850 | 9045 | 571 | 194 | -92 | -100 | 30.4% | -49 | 51 | 16 | -84 | -515 | 558 | 68.5% |
| Rs 2500 · 15 min · OTM2 | 9850 | 9216 | 143 | 416 | -97 | -104 | 22.9% | -54 | 49 | 18 | -86 | -366 | 373 | 55.4% |
| Rs 2500 · 30 min · ITM1 | 9850 | 296 | 9518 | 4 | -6 | -191 | 34.5% | -139 | 52 | 7 | -184 | -840 | 780 | 77.0% |
| Rs 2500 · 30 min · ATM | 9850 | 6883 | 2849 | 93 | -83 | -119 | 32.8% | -67 | 51 | 10 | -109 | -772 | 924 | 80.8% |
| Rs 2500 · 30 min · OTM1 | 9850 | 9045 | 571 | 194 | -124 | -136 | 25.9% | -85 | 50 | 16 | -120 | -698 | 910 | 74.5% |
| Rs 2500 · 30 min · OTM2 | 9850 | 9216 | 143 | 416 | -128 | -137 | 19.4% | -87 | 49 | 18 | -118 | -491 | 620 | 62.3% |

| Adverse fills: reserve · horizon · strike | net / fill | share > 0 |
|---|---:|---:|
| Rs 1250 · 3 · ITM1 | 74 | 50.0% |
| Rs 1250 · 3 · ATM | -88 | 22.6% |
| Rs 1250 · 3 · OTM1 | -92 | 21.4% |
| Rs 1250 · 3 · OTM2 | -89 | 16.4% |
| Rs 1250 · 8 · ITM1 | -4 | 75.0% |
| Rs 1250 · 8 · ATM | -92 | 27.5% |
| Rs 1250 · 8 · OTM1 | -101 | 25.6% |
| Rs 1250 · 8 · OTM2 | -98 | 20.7% |
| Rs 1250 · 15 · ITM1 | -84 | 50.0% |
| Rs 1250 · 15 · ATM | -110 | 27.7% |
| Rs 1250 · 15 · OTM1 | -111 | 26.1% |
| Rs 1250 · 15 · OTM2 | -114 | 20.7% |
| Rs 1250 · 30 · ITM1 | -583 | 0.0% |
| Rs 1250 · 30 · ATM | -164 | 22.8% |
| Rs 1250 · 30 · OTM1 | -141 | 22.8% |
| Rs 1250 · 30 · OTM2 | -137 | 17.8% |
| Rs 2500 · 3 · ITM1 | -112 | 32.8% |
| Rs 2500 · 3 · ATM | -116 | 29.6% |
| Rs 2500 · 3 · OTM1 | -112 | 25.5% |
| Rs 2500 · 3 · OTM2 | -101 | 19.0% |
| Rs 2500 · 8 · ITM1 | -149 | 32.4% |
| Rs 2500 · 8 · ATM | -123 | 32.9% |
| Rs 2500 · 8 · OTM1 | -123 | 28.6% |
| Rs 2500 · 8 · OTM2 | -110 | 22.8% |
| Rs 2500 · 15 · ITM1 | -165 | 34.5% |
| Rs 2500 · 15 · ATM | -137 | 32.9% |
| Rs 2500 · 15 · OTM1 | -141 | 28.3% |
| Rs 2500 · 15 · OTM2 | -134 | 22.1% |
| Rs 2500 · 30 · ITM1 | -252 | 32.4% |
| Rs 2500 · 30 · ATM | -169 | 31.1% |
| Rs 2500 · 30 · OTM1 | -177 | 24.8% |
| Rs 2500 · 30 · OTM2 | -168 | 18.9% |

| Rs 2,500, bucket · horizon | fills | net / fill | share > 0 | calls | puts |
|---|---:|---:|---:|---:|---:|
| 12:30-13:00 · 3 min | 5792 | -70 | 29.9% | -67 | -73 |
| 12:30-13:00 · 8 min | 5792 | -81 | 32.1% | -73 | -89 |
| 12:30-13:00 · 15 min | 5792 | -104 | 30.1% | -92 | -115 |
| 12:30-13:00 · 30 min | 5792 | -151 | 28.2% | -146 | -156 |
| 13:00-13:30 · 3 min | 6052 | -65 | 29.5% | -70 | -60 |
| 13:00-13:30 · 8 min | 6052 | -72 | 31.4% | -80 | -63 |
| 13:00-13:30 · 15 min | 6052 | -78 | 31.8% | -107 | -48 |
| 13:00-13:30 · 30 min | 6052 | -79 | 28.5% | -142 | -16 |
| 13:30-14:00 · 3 min | 6189 | -66 | 31.2% | -65 | -66 |
| 13:30-14:00 · 8 min | 6189 | -69 | 31.9% | -78 | -60 |
| 13:30-14:00 · 15 min | 6189 | -75 | 30.5% | -92 | -59 |
| 13:30-14:00 · 30 min | 6189 | -105 | 25.1% | -125 | -86 |
| 14:00-14:30 · 3 min | 7407 | -77 | 28.4% | -76 | -78 |
| 14:00-14:30 · 8 min | 7407 | -94 | 28.9% | -101 | -86 |
| 14:00-14:30 · 15 min | 7407 | -128 | 25.2% | -131 | -126 |
| 14:00-14:30 · 30 min | 7407 | -183 | 21.3% | -134 | -232 |

| 13:00–14:30, reserve · horizon | at E03.2's minutes and side (mean, n) | random side at those minutes | the 5-minute grid |
|---|---|---|---|
| Rs 1250 · 3 min | [-62.82, 121] | [-80.83, 122] | [-67.53, 14295] |
| Rs 2500 · 3 min | [-63.81, 176] | [-94.6, 186] | [-69.72, 19648] |
| Rs 1250 · 8 min | [-13.97, 121] | [-47.11, 122] | [-75.94, 14295] |
| Rs 2500 · 8 min | [38.4, 176] | [-39.86, 186] | [-79.02, 19648] |
| Rs 1250 · 15 min | [-23.95, 121] | [-31.61, 122] | [-89.66, 14295] |
| Rs 2500 · 15 min | [-18.59, 176] | [-46.41, 186] | [-96.12, 19648] |
| Rs 1250 · 30 min | [-30.06, 121] | [40.95, 122] | [-117.72, 14295] |
| Rs 2500 · 30 min | [-8.12, 176] | [32.19, 186] | [-126.51, 19648] |

| Hindsight ceiling | expiries | best ≥ Rs 250 | best ≥ Rs 1,250 | best that first hit −35% | median best |
|---|---:|---:|---:|---:|---:|
| Rs 1250 | 197 | 196 | 121 | 21 | 1,595 |
| Rs 2500 | 197 | 197 | 181 | 12 | 3,405 |

Underlying diagnostic (Rs 2,500, 8 min): 25425 fills; direction right 49.5%; right but the option lost 40.4%; wrong but the option won 2.8%; delta-equivalent mean Rs -3 against option net Rs -79; correlation 0.7986.

### SENSEX (100,800 rows)

| Reserve · horizon · strike | decisions | filled | unaffordable | no fill | net / decision | net / fill | share > 0 | gross / fill | fees / fill | slippage / fill | no-spread net / fill | MAE | MFE | ever net-positive |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Rs 1250 · 3 min · ITM1 | 3150 | 0 | 3075 | 0 | 0 | — | — | — | — | — | — | — | — | — |
| Rs 1250 · 3 min · ATM | 3150 | 200 | 2868 | 10 | -4 | -66 | 34.0% | -17 | 49 | 3 | -63 | -206 | 110 | 47.0% |
| Rs 1250 · 3 min · OTM1 | 3150 | 1388 | 1649 | 36 | -23 | -53 | 32.6% | -4 | 49 | 3 | -50 | -183 | 106 | 47.1% |
| Rs 1250 · 3 min · OTM2 | 3150 | 2223 | 786 | 63 | -42 | -60 | 30.6% | -11 | 49 | 4 | -56 | -179 | 98 | 45.3% |
| Rs 1250 · 8 min · ITM1 | 3150 | 0 | 3075 | 0 | 0 | — | — | — | — | — | — | — | — | — |
| Rs 1250 · 8 min · ATM | 3150 | 200 | 2868 | 10 | -6 | -87 | 35.5% | -38 | 49 | 3 | -84 | -304 | 222 | 65.0% |
| Rs 1250 · 8 min · OTM1 | 3150 | 1388 | 1649 | 36 | -27 | -62 | 33.7% | -12 | 49 | 3 | -59 | -266 | 222 | 61.9% |
| Rs 1250 · 8 min · OTM2 | 3150 | 2223 | 786 | 63 | -48 | -68 | 31.6% | -19 | 49 | 4 | -64 | -259 | 209 | 60.9% |
| Rs 1250 · 15 min · ITM1 | 3150 | 0 | 3075 | 0 | 0 | — | — | — | — | — | — | — | — | — |
| Rs 1250 · 15 min · ATM | 3150 | 200 | 2868 | 10 | -7 | -112 | 32.5% | -63 | 49 | 3 | -109 | -389 | 324 | 70.5% |
| Rs 1250 · 15 min · OTM1 | 3150 | 1388 | 1649 | 36 | -27 | -62 | 33.4% | -13 | 49 | 3 | -59 | -342 | 351 | 70.1% |
| Rs 1250 · 15 min · OTM2 | 3150 | 2223 | 786 | 63 | -51 | -73 | 29.2% | -23 | 49 | 4 | -69 | -332 | 335 | 68.7% |
| Rs 1250 · 30 min · ITM1 | 3150 | 0 | 3075 | 0 | 0 | — | — | — | — | — | — | — | — | — |
| Rs 1250 · 30 min · ATM | 3150 | 200 | 2868 | 10 | -8 | -124 | 29.0% | -75 | 49 | 4 | -120 | -521 | 515 | 77.5% |
| Rs 1250 · 30 min · OTM1 | 3150 | 1388 | 1649 | 36 | -35 | -80 | 31.6% | -31 | 49 | 3 | -77 | -460 | 569 | 77.2% |
| Rs 1250 · 30 min · OTM2 | 3150 | 2223 | 786 | 63 | -64 | -91 | 26.9% | -42 | 49 | 4 | -87 | -444 | 564 | 75.2% |
| Rs 2500 · 3 min · ITM1 | 3150 | 307 | 2762 | 6 | -4 | -40 | 42.4% | 12 | 52 | 16 | -24 | -302 | 221 | 57.6% |
| Rs 2500 · 3 min · ATM | 3150 | 1923 | 1119 | 36 | -39 | -64 | 38.1% | -13 | 51 | 9 | -55 | -291 | 193 | 54.7% |
| Rs 2500 · 3 min · OTM1 | 3150 | 2691 | 335 | 47 | -55 | -65 | 37.6% | -13 | 51 | 7 | -58 | -302 | 220 | 55.6% |
| Rs 2500 · 3 min · OTM2 | 3150 | 2913 | 87 | 72 | -61 | -66 | 35.8% | -15 | 51 | 6 | -60 | -277 | 197 | 52.8% |
| Rs 2500 · 8 min · ITM1 | 3150 | 307 | 2762 | 6 | -4 | -45 | 42.0% | 7 | 52 | 16 | -30 | -449 | 416 | 72.0% |
| Rs 2500 · 8 min · ATM | 3150 | 1923 | 1119 | 36 | -46 | -76 | 38.3% | -24 | 51 | 9 | -66 | -438 | 378 | 68.6% |
| Rs 2500 · 8 min · OTM1 | 3150 | 2691 | 335 | 47 | -63 | -74 | 37.5% | -23 | 51 | 7 | -67 | -458 | 430 | 69.2% |
| Rs 2500 · 8 min · OTM2 | 3150 | 2913 | 87 | 72 | -69 | -75 | 35.6% | -24 | 51 | 6 | -69 | -414 | 387 | 66.9% |
| Rs 2500 · 15 min · ITM1 | 3150 | 307 | 2762 | 6 | -1 | -7 | 44.3% | 45 | 52 | 15 | 9 | -591 | 624 | 78.2% |
| Rs 2500 · 15 min · ATM | 3150 | 1923 | 1119 | 36 | -46 | -75 | 38.0% | -24 | 51 | 9 | -66 | -569 | 570 | 74.8% |
| Rs 2500 · 15 min · OTM1 | 3150 | 2691 | 335 | 47 | -66 | -78 | 35.3% | -26 | 51 | 7 | -70 | -598 | 655 | 75.4% |
| Rs 2500 · 15 min · OTM2 | 3150 | 2913 | 87 | 72 | -76 | -83 | 32.5% | -32 | 51 | 6 | -76 | -540 | 598 | 73.6% |
| Rs 2500 · 30 min · ITM1 | 3150 | 307 | 2762 | 6 | 2 | 21 | 41.0% | 73 | 52 | 15 | 36 | -807 | 982 | 84.7% |
| Rs 2500 · 30 min · ATM | 3150 | 1923 | 1119 | 36 | -53 | -86 | 36.8% | -35 | 51 | 9 | -77 | -777 | 903 | 80.9% |
| Rs 2500 · 30 min · OTM1 | 3150 | 2691 | 335 | 47 | -89 | -104 | 33.1% | -53 | 51 | 7 | -97 | -815 | 1,042 | 81.2% |
| Rs 2500 · 30 min · OTM2 | 3150 | 2913 | 87 | 72 | -98 | -106 | 30.1% | -56 | 51 | 7 | -100 | -731 | 971 | 79.5% |

| Adverse fills: reserve · horizon · strike | net / fill | share > 0 |
|---|---:|---:|
| Rs 1250 · 3 · ITM1 | — | — |
| Rs 1250 · 3 · ATM | -91 | 28.3% |
| Rs 1250 · 3 · OTM1 | -78 | 27.3% |
| Rs 1250 · 3 · OTM2 | -84 | 25.1% |
| Rs 1250 · 8 · ITM1 | — | — |
| Rs 1250 · 8 · ATM | -111 | 32.0% |
| Rs 1250 · 8 · OTM1 | -88 | 29.8% |
| Rs 1250 · 8 · OTM2 | -94 | 28.5% |
| Rs 1250 · 15 · ITM1 | — | — |
| Rs 1250 · 15 · ATM | -134 | 31.4% |
| Rs 1250 · 15 · OTM1 | -88 | 31.8% |
| Rs 1250 · 15 · OTM2 | -99 | 26.6% |
| Rs 1250 · 30 · ITM1 | — | — |
| Rs 1250 · 30 · ATM | -148 | 28.3% |
| Rs 1250 · 30 · OTM1 | -103 | 30.7% |
| Rs 1250 · 30 · OTM2 | -112 | 25.7% |
| Rs 2500 · 3 · ITM1 | -108 | 33.3% |
| Rs 2500 · 3 · ATM | -110 | 31.3% |
| Rs 2500 · 3 · OTM1 | -112 | 30.8% |
| Rs 2500 · 3 · OTM2 | -107 | 29.4% |
| Rs 2500 · 8 · ITM1 | -114 | 37.8% |
| Rs 2500 · 8 · ATM | -123 | 34.1% |
| Rs 2500 · 8 · OTM1 | -123 | 33.8% |
| Rs 2500 · 8 · OTM2 | -118 | 31.7% |
| Rs 2500 · 15 · ITM1 | -93 | 39.1% |
| Rs 2500 · 15 · ATM | -120 | 35.6% |
| Rs 2500 · 15 · OTM1 | -125 | 32.8% |
| Rs 2500 · 15 · OTM2 | -126 | 29.9% |
| Rs 2500 · 30 · ITM1 | -27 | 39.1% |
| Rs 2500 · 30 · ATM | -127 | 35.1% |
| Rs 2500 · 30 · OTM1 | -149 | 31.5% |
| Rs 2500 · 30 · OTM2 | -145 | 28.7% |

| Rs 2,500, bucket · horizon | fills | net / fill | share > 0 | calls | puts |
|---|---:|---:|---:|---:|---:|
| 12:30-13:00 · 3 min | 1666 | -54 | 38.5% | -75 | -35 |
| 12:30-13:00 · 8 min | 1666 | -65 | 37.9% | -93 | -39 |
| 12:30-13:00 · 15 min | 1666 | -92 | 34.9% | -138 | -48 |
| 12:30-13:00 · 30 min | 1666 | -151 | 34.2% | -276 | -33 |
| 13:00-13:30 · 3 min | 1841 | -63 | 36.9% | -101 | -24 |
| 13:00-13:30 · 8 min | 1841 | -67 | 37.5% | -143 | 9 |
| 13:00-13:30 · 15 min | 1841 | -76 | 35.7% | -166 | 14 |
| 13:00-13:30 · 30 min | 1841 | -59 | 35.4% | -177 | 60 |
| 13:30-14:00 · 3 min | 1950 | -66 | 37.1% | -80 | -52 |
| 13:30-14:00 · 8 min | 1950 | -76 | 36.5% | -114 | -39 |
| 13:30-14:00 · 15 min | 1950 | -56 | 36.0% | -176 | 62 |
| 13:30-14:00 · 30 min | 1950 | -34 | 34.2% | -346 | 271 |
| 14:00-14:30 · 3 min | 2377 | -70 | 36.9% | -74 | -67 |
| 14:00-14:30 · 8 min | 2377 | -83 | 37.0% | -85 | -80 |
| 14:00-14:30 · 15 min | 2377 | -82 | 34.5% | -47 | -115 |
| 14:00-14:30 · 30 min | 2377 | -136 | 30.0% | -20 | -249 |

| 13:00–14:30, reserve · horizon | at E03.2's minutes and side (mean, n) | random side at those minutes | the 5-minute grid |
|---|---|---|---|
| Rs 1250 · 3 min | [29.36, 17] | [-117.23, 13] | [-59.68, 3169] |
| Rs 2500 · 3 min | [38.98, 34] | [-131.23, 30] | [-66.73, 6168] |
| Rs 1250 · 8 min | [708.08, 17] | [360.64, 13] | [-68.87, 3169] |
| Rs 2500 · 8 min | [859.52, 34] | [468.73, 30] | [-75.88, 6168] |
| Rs 1250 · 15 min | [620.42, 17] | [266.51, 13] | [-71.34, 3169] |
| Rs 2500 · 15 min | [614.89, 34] | [283.62, 30] | [-71.84, 6168] |
| Rs 1250 · 30 min | [414.11, 17] | [134.07, 13] | [-85.88, 3169] |
| Rs 2500 · 30 min | [509.74, 34] | [120.92, 30] | [-80.83, 6168] |

| Hindsight ceiling | expiries | best ≥ Rs 250 | best ≥ Rs 1,250 | best that first hit −35% | median best |
|---|---:|---:|---:|---:|---:|
| Rs 1250 | 63 | 60 | 40 | 8 | 1,563 |
| Rs 2500 | 63 | 62 | 58 | 3 | 3,695 |

Underlying diagnostic (Rs 2,500, 8 min): 7834 fills; direction right 48.9%; right but the option lost 32.8%; wrong but the option won 8.4%; delta-equivalent mean Rs -6 against option net Rs -74; correlation 0.8165.

**EN56 on recorder depth, NIFTY Nov 17** (reserve · horizon: rows, packet net mean, bar-proxy net mean, packet − bar, correlation)

- Rs 1250 · 3 min: 69 rows; packet -75.6709; bar -79.2493; difference 3.5784; corr 0.9976
- Rs 1250 · 8 min: 69 rows; packet -47.23; bar -50.4791; difference 3.2491; corr 0.9995
- Rs 1250 · 15 min: 69 rows; packet -80.3259; bar -83.9974; difference 3.6714; corr 0.9993
- Rs 1250 · 30 min: 69 rows; packet 27.1413; bar 24.1754; difference 2.9659; corr 0.9998
- Rs 2500 · 3 min: 116 rows; packet -84.4131; bar -86.7932; difference 2.3801; corr 0.9982
- Rs 2500 · 8 min: 116 rows; packet -23.2011; bar -26.8397; difference 3.6385; corr 0.9995
- Rs 2500 · 15 min: 116 rows; packet -1.7255; bar -4.357; difference 2.6315; corr 0.9997
- Rs 2500 · 30 min: 116 rows; packet 294.4633; bar 292.0835; difference 2.3797; corr 0.9998

## EN57: what EN55's survival comes from

### NIFTY

Main effects on fixed-cap ordinary net (mean over the four pairs): patient 183, scout -2,354, stall 956.

| Against E03.2 | matched | Δ on matched | of which size | exit / price | fees | new parents (net) | lost parents (net) |
|---|---:|---:|---:|---:|---:|---|---|
| EN57_p0s0r1 | 66 | 1,927 | 0 | 1,930 | -4 | 1 (-250) | 0 (0) |
| EN57_p0s1r0 | 66 | -1,590 | -1,680 | 254 | -164 | 1 (-250) | 0 (0) |
| EN57_p0s1r1 | 66 | -1,590 | -1,680 | 254 | -164 | 1 (-250) | 0 (0) |
| EN57_p1s0r0 | 65 | 1,306 | 0 | 1,355 | -49 | 2 (-1,446) | 1 (15) |
| EN57_p1s0r1 | 65 | 3,246 | 0 | 3,299 | -53 | 3 (-1,683) | 1 (15) |
| EN57_p1s1r0 | 65 | -532 | -2,088 | 1,747 | -191 | 3 (-1,007) | 1 (15) |
| EN57_p1s1r1 | 65 | -88 | -2,088 | 2,192 | -192 | 3 (-1,007) | 1 (15) |
| EN55 | 65 | -88 | -2,088 | 2,192 | -192 | 3 (-1,007) | 1 (15) |

| Run | fixed | wallet P | halted | first halt | liq. DD |
|---|---:|---:|---:|---|---:|
| E032_30k|ticks1 | 13,759 | -4,082 | 151 | 2023-12-14 | 4,085 |
| E032_30k|ticks2 | 12,745 | -4,364 | 151 | 2023-12-14 | 4,364 |
| E032_30k|delay1 | 3,294 | 669 | 0 | never | 4,129 |
| E032_30k|passive_adversarial | 14,275 | -4,123 | 146 | 2024-01-18 | 4,181 |
| E032_30k|passive_none | 14,275 | -4,123 | 146 | 2024-01-18 | 4,181 |
| E032_30k|base | 14,275 | -4,123 | 146 | 2024-01-18 | 4,181 |
| E032_30k|from_2023Q1 | — | -4,123 | 146 | 2024-01-18 | 4,181 |
| E032_30k|from_2023Q2 | — | 16,422 | 0 | never | 4,087 |
| E032_30k|from_2023Q3 | — | 15,979 | 0 | never | 4,087 |
| E032_30k|from_2023Q4 | — | 16,739 | 0 | never | 4,087 |
| E032_30k|from_2024Q1 | — | 17,638 | 0 | never | 4,087 |
| E032_30k|from_2024Q2 | — | 5,673 | 0 | never | 4,087 |
| E032_30k|from_2024Q3 | — | 4,700 | 0 | never | 4,087 |
| E032_30k|from_2024Q4 | — | 2,325 | 0 | never | 4,087 |
| E032_30k|from_2025Q1 | — | 2,057 | 0 | never | 4,087 |
| E032_30k|from_2025Q2 | — | 2,664 | 0 | never | 4,087 |
| E032_30k|from_2025Q3 | — | 1,398 | 0 | never | 4,087 |
| E032_30k|from_2025Q4 | — | -2,780 | 0 | never | 4,087 |
| E032_30k|from_2026Q1 | — | -3,879 | 0 | never | 4,087 |
| E032_30k|from_2026Q2 | — | -2,846 | 0 | never | 3,092 |
| E032_30k|from_2026Q3 | — | -714 | 0 | never | 1,110 |
| E032_30k|from_2026Q4 | — | 0 | 0 | never | 0 |
| EN55|ticks1 | 12,127 | 12,631 | 0 | never | 3,700 |
| EN55|ticks2 | 11,754 | 12,267 | 0 | never | 3,794 |
| EN55|delay1 | 24,239 | 23,957 | 0 | never | 3,894 |
| EN55|passive_adversarial | -9,590 | -4,221 | 139 | 2024-03-07 | 4,221 |
| EN55|passive_none | -3,036 | -3,036 | 0 | never | 3,263 |
| EN55|base | 13,165 | 3,445 | 0 | never | 4,006 |
| EN55|from_2023Q1 | — | 3,445 | 0 | never | 4,006 |
| EN55|from_2023Q2 | — | 14,424 | 0 | never | 2,987 |
| EN55|from_2023Q3 | — | 15,274 | 0 | never | 2,987 |
| EN55|from_2023Q4 | — | 15,710 | 0 | never | 2,987 |
| EN55|from_2024Q1 | — | 16,204 | 0 | never | 2,987 |
| EN55|from_2024Q2 | — | 5,950 | 0 | never | 2,987 |
| EN55|from_2024Q3 | — | 5,087 | 0 | never | 2,987 |
| EN55|from_2024Q4 | — | 3,257 | 0 | never | 2,987 |
| EN55|from_2025Q1 | — | 2,999 | 0 | never | 2,987 |
| EN55|from_2025Q2 | — | 3,415 | 0 | never | 2,987 |
| EN55|from_2025Q3 | — | 2,125 | 0 | never | 2,987 |
| EN55|from_2025Q4 | — | -1,679 | 0 | never | 2,987 |
| EN55|from_2026Q1 | — | -2,335 | 0 | never | 2,987 |
| EN55|from_2026Q2 | — | -1,010 | 0 | never | 1,697 |
| EN55|from_2026Q3 | — | 267 | 0 | never | 472 |
| EN55|from_2026Q4 | — | 0 | 0 | never | 0 |

Halt crossings against each base run: {'E032_30k': 1, 'EN55': 1}. Wallet adverse − ordinary by factorial arm: {'EN57_p0s0r0': 87.34, 'EN57_p0s0r1': 87.34, 'EN57_p0s1r0': -11702.4, 'EN57_p0s1r1': -11702.4, 'EN57_p1s0r0': 177.1, 'EN57_p1s0r1': 177.1, 'EN57_p1s1r0': 7686.67, 'EN57_p1s1r1': 8127.82}.

Hero days removed: ['2024-03-28', '2025-08-07'].

- E032_30k|drop_first: fixed 2,504; wallet -4,123, halted 145 (first 2024-01-18)
- E032_30k|drop_second: fixed 12,423; wallet -4,123, halted 145 (first 2024-01-18)
- E032_30k|drop_both: fixed 652; wallet -4,123, halted 144 (first 2024-01-18)
- EN55|drop_first: fixed 2,841; wallet 2,767, halted 0 (first never)
- EN55|drop_second: fixed 11,369; wallet 1,649, halted 0 (first never)
- EN55|drop_both: fixed 1,045; wallet 971, halted 0 (first never)
### SENSEX

Main effects on fixed-cap ordinary net (mean over the four pairs): patient 470, scout -167, stall -282.

| Against E03.2 | matched | Δ on matched | of which size | exit / price | fees | new parents (net) | lost parents (net) |
|---|---:|---:|---:|---:|---:|---|---|
| EN57_p0s0r1 | 12 | -282 | 0 | -283 | 1 | 0 (0) | 0 (0) |
| EN57_p0s1r0 | 12 | -250 | -14 | -199 | -37 | 0 (0) | 0 (0) |
| EN57_p0s1r1 | 12 | -532 | -14 | -482 | -36 | 0 (0) | 0 (0) |
| EN57_p1s0r0 | 10 | -250 | 0 | -251 | 1 | 0 (0) | 2 (-637) |
| EN57_p1s0r1 | 10 | -533 | 0 | -534 | 1 | 0 (0) | 2 (-637) |
| EN57_p1s1r0 | 10 | -334 | -14 | -283 | -37 | 0 (0) | 2 (-637) |
| EN57_p1s1r1 | 10 | -616 | -14 | -566 | -36 | 0 (0) | 2 (-637) |
| EN55 | 10 | -616 | -14 | -566 | -36 | 0 (0) | 2 (-637) |

| Run | fixed | wallet P | halted | first halt | liq. DD |
|---|---:|---:|---:|---|---:|
| E032_30k|ticks1 | 2,405 | 1,947 | 0 | never | 3,574 |
| E032_30k|ticks2 | 2,361 | 1,907 | 0 | never | 3,591 |
| E032_30k|delay1 | -2,358 | -2,358 | 0 | never | 2,821 |
| E032_30k|passive_adversarial | 2,449 | 1,987 | 0 | never | 3,557 |
| E032_30k|passive_none | 2,449 | 1,987 | 0 | never | 3,557 |
| E032_30k|base | 2,449 | 1,987 | 0 | never | 3,557 |
| E032_30k|from_2025Q3 | — | 1,987 | 0 | never | 3,557 |
| E032_30k|from_2025Q4 | — | 1,273 | 0 | never | 3,557 |
| E032_30k|from_2026Q1 | — | -2,857 | 0 | never | 3,557 |
| E032_30k|from_2026Q2 | — | -389 | 0 | never | 1,883 |
| E032_30k|from_2026Q3 | — | -95 | 0 | never | 281 |
| E032_30k|from_2026Q4 | — | -95 | 0 | never | 281 |
| EN55|ticks1 | 2,453 | 2,453 | 0 | never | 2,885 |
| EN55|ticks2 | 2,436 | 2,436 | 0 | never | 2,891 |
| EN55|delay1 | 1,128 | 1,128 | 0 | never | 3,206 |
| EN55|passive_adversarial | -3,241 | -3,241 | 0 | never | 3,266 |
| EN55|passive_none | -164 | -164 | 0 | never | 189 |
| EN55|base | 2,470 | 2,470 | 0 | never | 2,879 |
| EN55|from_2025Q3 | — | 2,470 | 0 | never | 2,879 |
| EN55|from_2025Q4 | — | 2,162 | 0 | never | 2,879 |
| EN55|from_2026Q1 | — | -2,084 | 0 | never | 2,879 |
| EN55|from_2026Q2 | — | -296 | 0 | never | 1,090 |
| EN55|from_2026Q3 | — | 0 | 0 | never | 0 |
| EN55|from_2026Q4 | — | 0 | 0 | never | 0 |

Halt crossings against each base run: {'E032_30k': 0, 'EN55': 0}. Wallet adverse − ordinary by factorial arm: {'EN57_p0s0r0': -470.6, 'EN57_p0s0r1': -467.61, 'EN57_p0s1r0': -2095.99, 'EN57_p0s1r1': -2093.0, 'EN57_p1s0r0': -251.52, 'EN57_p1s0r1': -248.53, 'EN57_p1s1r0': -236.59, 'EN57_p1s1r1': -233.6}.


## EN58: entry policies on recorder depth (NIFTY Nov 17)

EN55 intents: [{'minute': 840, 'd': 1, 'lots': 1}]. Verdict: INCONCLUSIVE (one packet session).

| Tag · policy · proxy | n | filled | how | cost vs mid | 8-min net (sum) | fill +60 s | fill +180 s | missed winner | decision mid +180 s (filled / unfilled) |
|---|---:|---:|---|---:|---:|---:|---:|---:|---|
| EN55 · P0 · adversarial | 1 | 1 | {'PASSIVE': 1} | -0.3% | 391 | -3.1% | 5.9% | — | -2.5% / — |
| EN55 · P0 · through | 1 | 1 | {'PASSIVE': 1} | -0.3% | 391 | -3.1% | 5.9% | — | -2.5% / — |
| EN55 · P0 · volume | 1 | 1 | {'PASSIVE': 1} | -0.3% | 391 | -3.1% | 5.9% | — | -2.5% / — |
| EN55 · P1 · through | 1 | 1 | {'MARKET': 1} | 3.7% | 349 | -5.9% | -3.6% | — | -2.5% / — |
| EN55 · P2 · adversarial | 1 | 1 | {'FALLBACK': 1} | 4.0% | 346 | -7.1% | 0.9% | — | -2.5% / — |
| EN55 · P2 · through | 1 | 1 | {'FALLBACK': 1} | 4.0% | 346 | -7.1% | 0.9% | — | -2.5% / — |
| EN55 · P2 · volume | 1 | 1 | {'FALLBACK': 1} | 4.0% | 346 | -7.1% | 0.9% | — | -2.5% / — |
| EN55 · P3 · adversarial | 1 | 1 | {'FALLBACK': 1} | 4.0% | 346 | -7.1% | 0.9% | — | -2.5% / — |
| EN55 · P3 · through | 1 | 1 | {'FALLBACK': 1} | 4.0% | 346 | -7.1% | 0.9% | — | -2.5% / — |
| EN55 · P3 · volume | 1 | 1 | {'FALLBACK': 1} | 4.0% | 346 | -7.1% | 0.9% | — | -2.5% / — |
| GRID · P0 · adversarial | 50 | 43 | {'PASSIVE': 43, 'MISSED': 7} | -0.2% | -2,212 | nan% | nan% | 32.0% | -5.9% / 32.2% |
| GRID · P0 · through | 50 | 44 | {'PASSIVE': 44, 'MISSED': 6} | -0.2% | -1,658 | nan% | nan% | 26.8% | -4.3% / 27.1% |
| GRID · P0 · volume | 50 | 42 | {'PASSIVE': 42, 'MISSED': 8} | -0.2% | -2,156 | nan% | nan% | 28.0% | -5.9% / 27.4% |
| GRID · P1 · through | 50 | 48 | {'MARKET': 50} | -0.1% | -81 | nan% | nan% | 1.9% | -0.4% / -4.0% |
| GRID · P2 · adversarial | 50 | 40 | {'PASSIVE_RACE': 2, 'PASSIVE': 31, 'MISSED': 10, 'FALLBACK': 7} | 0.3% | -3,134 | nan% | nan% | 27.0% | -7.3% / 26.5% |
| GRID · P2 · through | 50 | 41 | {'PASSIVE_RACE': 2, 'PASSIVE': 32, 'MISSED': 9, 'FALLBACK': 7} | 0.3% | -2,580 | nan% | nan% | 23.0% | -5.6% / 22.4% |
| GRID · P2 · volume | 50 | 38 | {'PASSIVE_RACE': 2, 'PASSIVE': 28, 'MISSED': 12, 'FALLBACK': 8} | 0.4% | -3,088 | nan% | nan% | 22.5% | -7.4% / 21.2% |
| GRID · P3 · adversarial | 50 | 41 | {'PASSIVE_RACE': 6, 'PASSIVE': 23, 'MISSED': 8, 'MARKET': 8, 'FALLBACK': 5} | 0.3% | -3,352 | nan% | nan% | 28.0% | -6.7% / 27.3% |
| GRID · P3 · through | 50 | 42 | {'PASSIVE_RACE': 6, 'PASSIVE': 24, 'MISSED': 7, 'MARKET': 8, 'FALLBACK': 5} | 0.3% | -2,797 | nan% | nan% | 23.6% | -5.0% / 22.8% |
| GRID · P3 · volume | 50 | 40 | {'PASSIVE_RACE': 6, 'PASSIVE': 21, 'MISSED': 9, 'MARKET': 8, 'FALLBACK': 6} | 0.4% | -3,234 | nan% | nan% | 25.1% | -6.6% / 23.7% |

## EN61: the payoff model

- **NIFTY:** {'sessions': 197, 'scored_sessions': 147, 'hgb_abstained': 0, 'abstain_reasons': {}, 'max_expected': 0.0722, 'logloss_model': 0.9852, 'logloss_icpt': 1.0457, 'temperature_median': 0.9629, 'top_decile_label': -0.0738, 'bottom_decile_label': -0.0618, 'mean_label': -0.0422, 'positive_forecasts': 251, 'class_shares': {'WIN': 0.187, 'LOSS': 0.5891, 'TIMEOUT': 0.1955, 'NO_FILL': 0.0284}}
- **SENSEX:** {'sessions': 63, 'scored_sessions': 13, 'hgb_abstained': 0, 'abstain_reasons': {}, 'max_expected': 0.0266, 'logloss_model': 1.0916, 'logloss_icpt': 1.1192, 'temperature_median': 1.1345, 'top_decile_label': -0.0232, 'bottom_decile_label': 0.0079, 'mean_label': -0.0363, 'positive_forecasts': 15, 'class_shares': {'WIN': 0.1618, 'LOSS': 0.4755, 'TIMEOUT': 0.3431, 'NO_FILL': 0.0196}}

## EN66: one wallet for both indices

Period ['2025-07-29', '2026-10-08'], 126 sessions.

| Arm | fills | combined P | swept | halted | first halt | liq. DD | separate P (NIFTY + SENSEX) | parents / week | weeks won / lost / flat |
|---|---|---:|---:|---:|---|---:|---:|---:|---|
| E032_30k | ordinary | 5,480 | 4,892 | 46 | 2026-05-05 | 4,350 | 3,047 | 0.397 | 10 / 9 / 44 |
| E032_30k | adverse | 4,622 | 4,591 | 46 | 2026-05-05 | 4,598 | 1,969 | 0.397 | 10 / 9 / 44 |
| EN55 | ordinary | 4,754 | 4,437 | 40 | 2026-05-26 | 4,126 | 4,454 | 0.397 | 10 / 9 / 44 |
| EN55 | adverse | 4,185 | 4,198 | 40 | 2026-05-26 | 4,211 | 3,759 | 0.397 | 10 / 9 / 44 |
| E032_sym | ordinary | 1,688 | 2,482 | 0 | never | 3,513 | -102 | 0.429 | 11 / 10 / 42 |
| E032_sym | adverse | 1,170 | 2,324 | 0 | never | 3,707 | -1,422 | 0.429 | 11 / 10 / 42 |
| EN67 | ordinary | 6,852 | 5,506 | 61 | 2026-03-12 | 4,159 | 3,013 | 0.857 | 14 / 13 / 36 |
| EN67 | adverse | 5,367 | 4,694 | 62 | 2026-03-10 | 4,020 | 1,293 | 0.825 | 13 / 12 / 38 |

## EN68: the probability of a halt (policy replay, circular blocks)

| Arm | Book | paths × length (block) | P(halt) | P(year-end loss) | median | p5 | p95 | mean swept | liq. DD median / p95 |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| E032_30k | NIFTY | 2000 × 52 (4) | 6.1% | 31.2% | 1,762 | -3,609 | 15,694 | 2,591 | 2,337 / 4,144 |
| E032_30k | SENSEX | 2000 × 52 (4) | 15.8% | 45.7% | 628 | -4,182 | 10,534 | 1,766 | 2,762 / 4,327 |
| E032_30k | COMBINED | 2000 × 104 (8) | 49.2% | 47.3% | 546 | -4,287 | 13,034 | 2,361 | 4,054 / 4,444 |
| EN55 | NIFTY | 2000 × 52 (4) | 1.4% | 30.2% | 1,615 | -2,652 | 12,911 | 2,168 | 1,839 / 3,639 |
| EN55 | SENSEX | 2000 × 52 (4) | 4.3% | 42.5% | 1,480 | -3,742 | 9,558 | 1,649 | 2,046 / 4,052 |
| EN55 | COMBINED | 2000 × 104 (8) | 24.4% | 33.7% | 2,536 | -4,132 | 12,865 | 2,522 | 3,199 / 4,362 |
| E032_sym | NIFTY | 2000 × 52 (4) | 0.0% | 34.2% | 1,081 | -2,704 | 8,220 | 1,462 | 1,753 / 3,262 |
| E032_sym | SENSEX | 2000 × 52 (4) | 0.4% | 64.6% | -693 | -3,376 | 2,976 | 487 | 2,117 / 3,548 |
| E032_sym | COMBINED | 2000 × 104 (8) | 8.2% | 50.7% | -56 | -3,837 | 5,528 | 1,092 | 3,069 / 4,096 |
| EN67 | NIFTY | 2000 × 52 (4) | 69.2% | 82.6% | -3,204 | -4,277 | 6,617 | 955 | 4,142 / 4,396 |
| EN67 | SENSEX | 2000 × 52 (4) | 51.7% | 56.5% | -1,063 | -4,318 | 8,608 | 1,599 | 4,068 / 4,463 |
| EN67 | COMBINED | 2000 × 104 (8) | 83.2% | 62.6% | -1,904 | -4,286 | 9,458 | 1,811 | 4,185 / 4,462 |

## EN69: why the puts earn

### NIFTY

- **E032_30k C:** tickets 37, underlying 4,080, time -2,756, vol 220, model_err -0, execution -263, fees -1,849, net -569
- **E032_30k P:** tickets 29, underlying 22,421, time -5,918, vol -71, model_err -0, execution 46, fees -1,634, net 14,844
- **EN55 C:** tickets 38, underlying 3,634, time -2,192, vol 298, model_err -0, execution -211, fees -1,889, net -361
- **EN55 P:** tickets 30, underlying 21,291, time -4,209, vol -46, model_err 0, execution -1,628, fees -1,882, net 13,526

| Library (Rs 2,500, 8 min) | n | mean IV change | vol Rs / unit | underlying Rs / unit | time Rs / unit |
|---|---:|---:|---:|---:|---:|
| C|adverse | 6587 | 0.0023 | 0.2704 | -2.5412 | -0.6739 |
| C|favourable | 6134 | -0.00023 | -0.0231 | 3.6475 | -0.8014 |
| P|adverse | 6130 | 0.00217 | 0.2671 | -2.6061 | -0.6807 |
| P|favourable | 6546 | 8e-05 | 0.0223 | 3.4391 | -0.8044 |
### SENSEX

- **E032_30k P:** tickets 7, underlying 6,292, time -1,461, vol 265, model_err -0, execution 165, fees -397, net 4,864
- **E032_30k C:** tickets 5, underlying -1,553, time -387, vol -73, model_err 0, execution -158, fees -244, net -2,415
- **EN55 P:** tickets 7, underlying 5,154, time -946, vol 512, model_err -0, execution -88, fees -433, net 4,199
- **EN55 C:** tickets 3, underlying -1,246, time -186, vol -141, model_err -0, execution -10, fees -145, net -1,728

| Library (Rs 2,500, 8 min) | n | mean IV change | vol Rs / unit | underlying Rs / unit | time Rs / unit |
|---|---:|---:|---:|---:|---:|
| C|adverse | 1987 | 0.00168 | 1.1264 | -12.9891 | -2.8949 |
| C|favourable | 1820 | -2e-05 | 0.0141 | 15.9275 | -3.4095 |
| P|adverse | 1866 | 0.00123 | 0.7611 | -11.8701 | -3.0074 |
| P|favourable | 2089 | 0.00031 | 0.2608 | 16.973 | -3.3642 |

## EN70: recorder minute bars

Verdict: **PARITY NOT ESTABLISHED**. Reasons: ['option closes within 0.10 on 83.2% of bars (< 95%)', 'no independent futures (or index) minutes for the recorded days: the futures clause cannot be met'].

Parity: {'option_bars': 8700, 'option_close_ok': '7237', 'option_hl_ok': '6106', 'option_bars_vol': 8700, 'option_close_ok_vol': '7237', 'breeze_only': 0, 'tr01_only': 0, 'volume_ratio_median': 1.0, 'close_ok_share_vol': 0.8318, 'future_bars': 375, 'index_bars': 375, 'basis_sd': 11.051, 'basis_mean': 34.28, 'future_independent_source': False, 'index_independent_source': False, 'strikes': 21}.

Decisions: {'E032_30k': {'same': True, 'recorder': [[284, 1, '11-17-25500-CE', 1]], 'hybrid': [[284, 1, '11-17-25500-CE', 1]]}, 'EN55': {'same': True, 'recorder': [[284, 1, '11-17-25500-CE', 1]], 'hybrid': [[284, 1, '11-17-25500-CE', 1]]}}.

Nov 17 ledgers (seen day): {'E032_30k': {'net': 430.29, 'trades': 1, 'positions': [{'decision_minute': 840, 'side': 1, 'lots': 1, 'net': 430.29}]}, 'EN55': {'net': 475.81, 'trades': 1, 'positions': [{'decision_minute': 840, 'side': 1, 'lots': 1, 'net': 475.81}]}}.
