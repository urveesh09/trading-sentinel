# O31e: the main book's weak spots - technical summary

Research only. No runtime change. Plain write-up: [`docs/FNO_WEAK_SPOTS_2026-10-31.md`](../../../FNO_WEAK_SPOTS_2026-10-31.md).

- **Diagnosis** (`run_diag.py`, `diagnose_w.py`, `diagnosis.json`), written before the freeze and shaping it. Found by looking.
- **Freeze:** `e6a7c78`. 67 books per year: EX and RAW MAIN, 15 changes in EX and RAW (groups C and D), 15 specialists in RAW (group E), 20 random closed-day books. 201 replays.
- **Results** (`analyze_w.py`, `results.json`): `improves` none; `better_balance` `D|tpb_puts_closed`; `every_year_better` `D|puts_from_25`, `D|only_puts_from_25`; `specialists_passing` none (`E|tpb_puts` is above zero every year, t 1.89).
- **Selection luck, changes:** 2024 `D|tpb_puts_closed` 15,337 against 16,371; 2025 `D|only_puts_from_25` 31,699 against 5,710; 2026 `D|only_puts_from_25` 68,432 against 30,540. Specialists: `E|tpb_puts` 13,199; `E|four_against_gap_10_30_to_12` -11,164; `E|tpb_puts` 23,559.
- **Direction control:** random closed days puts -84,856, calls -81,952; random ADX 30 days puts -14,133, calls -19,342.
- **Report** (`report_w.py`, `report.json`): the candidates in detail; descriptive, written after scoring.
- **Exam:** `freeze-2023.json`, fixed before any 2023 data exists. It needs a mirror and dataset path like `lab_f.py`'s for 2024, and a `download2023.py` by the download agent, modelled on `download2024.py` and `download2024_gaps.py` (Saturday sessions, year-end expiry). ICICI's 2023 availability is not probed.

**Checks:** `check_book` 0 problems in 201 replays; parity with +16,371 / +5,710 / +30,540 and the stored surface cell asserted; 8 tests pass (`test_lab_w.py`: causality of every entry and reading, filters, books, rules).

**Caveats:**
- All three years are seen and the list was shaped by looking.
- The new entries use one textbook or round setting each, not searched.
- LAST_HOUR runs with its own hard flat at 15:25; the engine's is 15:10.
- `SUPERTREND_VWAP` uses the 14-bar ATR and restarts each morning, not the textbook's 10-bar, continuous one.
- The library slice in the write-up comes from shipped-size replays; everything else is RAW or EX as labelled.
- A one-sided book's risk in a long calm rise is not measured here.

**Reproduce:** `lab_w.py`'s docstring. Windows workers re-import the main script, so every patch must be at module level; a first diagnosis run that imported inside a function wrote to the wrong study folder and was deleted and rerun.
