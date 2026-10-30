# O30r: the risk spectrum - technical summary

Research only. No runtime change, nothing deployed. The plain write-up and the verdict: [`docs/FNO_RISK_SPECTRUM_VERDICT_2026-10-30.md`](../../../FNO_RISK_SPECTRUM_VERDICT_2026-10-30.md).

- **Freeze:** `8fd8de8` (6 books x 28 levels with the extra cost, 3 books x 16 levels as replayed, 22 sensitivities).
- **Replays:** 692, shipped code: 238 on 2025, 238 on 2026 alone, 216 on 2026 carried from 2025's trades.
- **Extra cost in the money path:** Rs 200 per lot per trade + Rs 5 per lot for each lot in the order (an assumption).
- **Checks:** `check_book` found no problem in 692 replays. `SHIPPED|AS` reproduces the stored rupees exactly. Three books replayed twice per year are identical.

**Frozen answers (with the cost):**
- Balanced: `TPB+rule|R2|OFF`, +61,417 / +31,346, carried 3,49,696, fall 21%. 12 of 168 pass; `TPB+rule|SHIPPED` is second (+37,320 / +22,413, carried 3,29,141, fall 12%).
- Most money: `TPB+rule|R5|OFF`, carried 4,15,516, fall 51%.
- Lowest risk that earns: `TPB|R1|SCALED`, +152 / +13,580, fall 9%.
- Peaks with brakes off: TPB+rule R4 (2025), R5 (2026), so half the smaller is R2.
- Cross-year: chosen on 2025 `TPB+rule|R3|OFF`, then +25,501 on 2026 (fall 31%). Chosen on 2026 `LIVE+rule|R6|OFF`, then -1,11,959 on 2025 (fall 66%).

**Caveats:**
- Rule books were found by looking at both years.
- Brake levels are percentages of the fixed Rs 2.5 lakh, so a `SHIPPED` or `SCALED` book that hits its total stop stays stopped (as shipped). The carried run gives no restart.
- As-replayed rows at high risk reach hundreds of lots with no slippage and are not executable; one NIFTY order is limited to 54 lots since Oct 5, 2026.
- `analyze_s.sim` runs below exact at higher levels on the rule books and differs either way on the live book, because a larger account admits high-premium trades the one-lot replay refused.

**2024:** `exam_r.py` (`freeze-2024.json`), a third sheet, scored after the O30f and O30s sheets. Not run: no 2024 data exists. It refuses if the engine changed after its freeze; use a worktree at that commit.

**Reproduce:** `O30C_YEAR=2025 lab_r.py run --jobs 5` in `run_slice.py` slices until DONE, then 2026 (2025 must come first: the carried runs read it), `O30C_YEAR=2026 analyze_r.py`, `lab_r.py verify` per year, `verdict_r.py`. Tests: `python -m pytest test_lab_r.py test_exam_r.py -q --timeout=140 -p no:cacheprovider` (13 passed).
