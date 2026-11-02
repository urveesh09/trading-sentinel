# O31: the one-time NIFTY 2024 exam - technical summary

Research only. No runtime change, nothing deployed. Plain write-up: [`docs/FNO_2024_EXAM_2026-10-31.md`](../../../FNO_2024_EXAM_2026-10-31.md).

- **Sheets, frozen before any 2024 data existed:** `2a57ede` (day-router), `ff08fca` (earning-power), `bc5a93a` (risk-spectrum). Scored once each, in that order. None was edited.
- **Data binding, committed before any replay:** `d1da1dc`, `../2026-10-30-day-router/data-binding-2024.json`.
- **Replays:** 141 distinct (sheet 1: the 23 frozen books and the 134-entry library, several of them the same book), 51 (sheet 2: 6 shipped, 45 raw), 7 (sheet 3). The engine is unchanged since the freezes.
- **Run:** Oct 31, 2026, 5 workers, after hours (a Saturday). Production was not stopped or touched.

**Frozen verdicts:**
- Sheet 1: `candidate_confirmed` false, `robust_core_candidate` false, `positive_both_carries` false (1 of 14). Random median -7,035.
- Sheet 2: `stretch_rule_holds` true (LIVE, BEST, TPB; random median -11,554 to -5,525). Candidates at 3 lots, no brakes, +200: `LIVE|skip` passes (+16,344, fall 15.0%); `TPB|skip` (+13,669, fall 38.3%), `BEST|skip` (-47,759, fall 31.2%) and the pick (-6,775, fall 52.4%) fail.
- Sheet 3: `pick_holds` false (`TPB+rule|R2|OFF|COST` -60,581, fall 38.6%). `level_confirmed` true only because R2 lost less per rupee of fall than R5 (-0.56 against -0.60); both lost.

**Checks (`report_x.py`):** dataset, manifest and mirror hashes unchanged; `REF|LIVE` = sheet 2 `LIVE`, `REF|LIVE+tpb_all_days` = `BEST`, `N|TPB|OWN` = `TPB`, trade for trade; 30,854 trades read, 0 outside 2024, 0 on expiry days; each sheet's rule re-applied reproduces its stored verdict; `check_book` 0 problems on sheet 3; all 34,968 book-sessions covered, no memo conflict or named-signal miss.

**Half-days:** every verdict is unchanged without Mar 2 and May 18, and with open legs closed at the last bid. One distinct open leg among the frozen books (`NIFTY24030722500CE`, -192 per lot, in six books). Sheet 3 has none; sheet 2 shipped none; sheet 2 raw 4; the library has 67 across all books.

**Caveats:**
- Lot 65 in all years, for comparability.
- The extra cost is an assumption. Candles flatter fills by about Rs 100-200 per trade per lot.
- The rule was found on 2025 and 2026, and only 2024 tested it unseen.
- `report_x.py` is descriptive, written after scoring. It chooses nothing. The three-year tables mix the unseen 2024 with in-sample years.
- NIFTY 2024 is now seen. Remaining unseen: the forward sessions and real fills. NIFTY 2023 could serve as another exam if Breeze serves it (not probed).

**Reproduce:** the steps are in `docs/FNO_YEAR_DATA_TESTING_METHOD.md` section 14. Then `python-engine/winvenv/Scripts/python.exe docs/research/fno/2026-10-31-exam-2024/report_x.py`. It writes `report.json`. Sheet results are written once and refuse to overwrite.
