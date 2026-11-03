# Round 8 — puts carry the edge: E03.2 (November 3, 2026)

Plain report: [EXPIRY_RESEARCH_E032_PUTS.md](../../../EXPIRY_RESEARCH_E032_PUTS.md). Plan frozen before any score:
[PLAN.md](PLAN.md) (`f55034b`). Starting checkout `b5e83e4` (the other agent's capital-reuse round).

**Result: E03.2 = E03.1 with put tickets at twice the reserve, an 8% buy limit and every leg sold from
15:14.** Over NIFTY 2024-2025 (continuous Rs 25,000 book): +21,518 ordinary / +20,001 adverse /
-2,438 severe, worst day -647, drawdown 754, against E03.1's +12,427 / +11,498 / -3,234, -478, 1,374.
Built in Dev as a disabled paper variant (`EXPIRY_E032_SHADOW_ENABLED=false`). **Both years are seen;
in-sample.** No Production, N11/N11T, A/B/C/D, E02/E03/E03.1 behaviour, `.env` or schema change; no
download; NIFTY 2023 not opened.

## The four frozen experiments (`round8.py` -> `results.json`)

| | Hypothesis | Result | Verdict |
|---|---|---|---|
| X1a | IV rises when the index falls (slope negative both years) | 2024 -0.50 IV points per 0.1% move; 2025 +0.07 | fail |
| X1a | Cheap puts on falls out-gain cheap calls on rises | mean return 2.28 vs 1.82 (2024), 1.70 vs 1.40 (2025); size-matched 2024 1.24 vs 1.31 | pass (mixed when matched) |
| X1b | `PUT2`: put tickets at 2x beat E03.1 both years and are at least as efficient | +15,581 / +5,937 (E03.1 +8,898 / +3,529); net per worst day 33.3 vs 26.0, per drawdown 28.5 vs 9.0 | **pass** |
| X2 | Week or day direction alignment (filters and 2x) | every arm below E03.1 | fail |
| X3 | Strike by delta 0.15 / 0.25 / 0.35 | -1,089 / +6,873 / +9,027 | fail |
| X4 | Holding a long leg from 15:14 to 15:28 loses (total and 7 of 9 days) | -28,393 over the measured legs, 6 of 8 days | fail (narrowly) |

E03.1's own tickets: calls 23 tickets +1,800 (2024 +835, 2025 +965); puts 18 tickets +10,627 (+8,063 / +2,564).

## Robustness (post-score, in-sample; `r8_diag.py` -> `diagnostics.json`, `final_checks.py`, `putdial.py`)

- The best day (2024-03-28, +5,850) is a put. Without each year's best day PUT2 still beats E03.1:
  2024 +3,810 vs +3,048, 2025 +4,085 vs +2,326 (ordinary).
- E03.1's puts are positive in all 8 quarters; its calls lose in three (2024 Q2, Q4, 2025 Q1).
- E02 (no runner) and E03 show the same gap in both years (E02 puts +3,024 / +2,235 vs calls +489 / +1,152).
- **Random entries show no put advantage** (2024 puts -1,194 vs calls +440 mean over 40 seeds): the
  asymmetry belongs to the signal. Reversed signals: calls bought against a down signal lose most
  (-420 / -2,248), so the down signals are the reliable ones. The F&O study found the same in its own
  strategy (`docs/FNO_WEAK_SPOTS_2026-10-31.md`: calls lost, puts earned, all three years; random flat).
- Permutation test, hero removed: puts +281 vs calls +78 per ticket, one-sided p = 0.125. Suggestive, not
  significant on its own.
- Selling at 15:14 instead of 15:28 changes nothing in 2024-2025 (no leg open then); the 8% limit changes
  nothing at ordinary/adverse fills and lifts severe from -3,638 to -2,438. Both are in E03.2.
- `putdial.py` (RISK_PLAN.md's frozen limits applied after the fact): puts at 2x and 3x pass all three
  limits (PUT3 +34,165, skeptical losing-year 19%, p95 drawdown 4,359); PUT4 fails the drawdown limit.
  3x is recorded as the next size step after fresh evidence, not built.

## E03.2 in the engine (Dev, disabled)

`expiry_e02.Variant` gains `put_mult`, `chase` and `flat` with defaults equal to today's behaviour (E02,
E03 and E03.1 unchanged; `test_expiry_e031`'s variant-count check now uses `len(VARIANTS)`). `E032`:
version `expiry-e032-v1`, play `E032`, own `<DB_PATH>.expiry-e032.db`, Rs 25,000 cash; a put ticket's
reserve and lot cap are doubled (`ticket_scale`), the day reserve doubles (`day_scale`), the buy limit is
8%, and the frozen policy carries `flat: 15:14` (`flat_time`). Scheduler and `EXPIRY_E032_SHADOW_ENABLED`
(false) as for E03.1.

Verification: `parity.py` -> `paper-parity.json`: 78 lab positions (both years, ordinary and adverse) through
`action`/`sell_base`, and 78 entry-sizing checks through `_lots`: **0 mismatches**. Focused tests
`test_expiry_e02/e03/e031/e032`: 43 passed. Full engine suite: see `engine-suite.txt`. Tests prove the code
follows the rule, not that the rule makes money.

## Plan slice

- Problem: owner wants an E03.2 that earns much more with risk that pays for itself.
- Contracts: E02/E03/E03.1 unchanged; E03.2 its own cash, DB, flag; policy frozen per ticket.
- Acceptance: frozen PUT2 test passed; parity 0 mismatches; focused and full suites pass.
- Rollout (owner): merge and rebuild, then `EXPIRY_E032_SHADOW_ENABLED=true` beside E03.1 for paired
  tickets. Rollback: flag false (open legs still exit) or revert; the E03.2 DB is separate.
- Remaining: the frozen exam with [EXAM_E032_ADDENDUM.md](EXAM_E032_ADDENDUM.md); 20 forward tickets; then
  the size question (3x) on fresh data only.

## Commands (Dev venv, from this folder)

```text
python round8.py score   # refuses unless freeze.json is committed and every hash matches
python r8_diag.py; python final_checks.py; python putdial.py; python parity.py
```
