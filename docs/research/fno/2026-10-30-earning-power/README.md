# O30s: earning power on Rs 2.5 lakh - technical summary

Research only. No runtime change, nothing deployed. The plain-language write-up is [`docs/FNO_EARNING_POWER_2026-10-30.md`](../../../FNO_EARNING_POWER_2026-10-30.md).

| Step | Commit | What |
| --- | --- | --- |
| Freeze | `045351b` | 38 books + 20 random, RAW one-lot replays, the sizing grid and RULE |
| Results + Tier 2 freeze | `fd8e4c1` | `results.json`, `reference.json`, `report.json`, `freeze-t2.json` |
| Tier 2 results + 2024 sheet | `ff08fca` | `results-t2.json`, `exact.json`, `freeze-2024.json` |

## Verdicts

**Frozen (rupees, Rs 2.5 lakh, +Rs 200 per lot per trade):**
- 71 of 5,168 combinations pass: TPB 17, TPB|HOUSE 22, TPB|HOLD 11, TPB|ADD1 9, TPB|ADD2 8, LIVE|ADD2 2, S_LIVE+TPB 2.
- Pick: TPB|HOUSE, 3 lots, half when stretched: +61,695 / +65,438, fall 23%. Exact: +60,901 / +110,166.
- LIVE|ADD2 (risk 2%, shipped brakes, half), a pass, fails exact: 2025 +11,895 simulated, -41,332 exact.
- Cross-year: chosen on 2026, LIVE|ADD1 at 6 lots half: +542,198 then -241,512 on 2025 (fall 97%). Chosen on 2025, TPB|HOLD at 3 lots half: +79,260 then +65,195 on 2026, below TPB (+73,869) and BEST (+109,831) at the same size. Selecting by one year fails.
- RETEST, FAILCONF, SQUEEZE: none improves BEST or is positive alone at +Rs 200.
- Parity: shipped sizing and brakes in the simulator against the stored replays: LIVE -8,870 / +66,147 (stored -7,738 / +68,176), BEST -287 / +94,365 (+1,343 / +92,002), TPB +33,417 / +34,549 (+34,435 / +36,965); trades within 1.

**Tier 2, found by looking (pass over an entry with stretch >= 0.5), exact, shipped size and brakes, per lot:**

| Book | 2025 | 2026 | +200: 2025 / 2026 | Helps by RULE |
| --- | ---: | ---: | ---: | --- |
| LIVE | 271 | 80,912 | -27,329 / 59,712 | reference |
| LIVE with rule | 27,769 | 55,524 | 8,369 / 42,324 | no, 2026 lower |
| BEST | 34,517 | 80,232 | -8,283 / 46,432 | reference |
| BEST with rule | 56,904 | 51,885 | 23,904 / 28,485 | no, 2026 lower |
| TPB | 36,694 | 42,056 | 15,294 / 25,056 | reference |
| TPB with rule | 52,230 | 45,652 | 33,230 / 31,652 | **yes** |
| UNION with rule | 36,312 | 54,227 | -25,888 / 8,027 | no, negative after stress |
| DRIVE with rule | 59,677 | 32,420 | 16,677 / 2,620 | no |

Random median, one lot, no brakes, no extra cost: 2025 -28,877 without the rule, -16,771 with it; 2026 -17,201, -11,943. So it is at least partly a market effect. References reproduce exactly (`parity`).

Feb 1, 2026 (Budget Sunday) is +47,288 per lot of LIVE's +80,912.

## Reference (`reference.json`)

Hindsight ceiling per lot 966,746 / 969,121; direction only 474,166 / 541,577; the biggest 10% of days hold about 25% of it. Selling (information only): STRADDLE -15,955 / -52,689 after Rs 100 per leg per day, HEDGED -172,916 / -94,851. Margin is not modelled, stops are tested on minute closes, expiry days are skipped.

## Reproduction

Use `python-engine/winvenv/Scripts/python.exe`. In order: `lab_s.py run` per year (`O30C_YEAR`), `analyze_s.py`, `reference_s.py`, `report_s.py`, `lab_s2.py run` per year and per `O30S2_MODE`, `analyze_s2.py`, `report_s2.py`, `exact_s.py` as listed in `exact.json`. Tests: `python -m pytest test_lab_s.py test_lab_s2.py test_exam_s.py -q --timeout=190 -p no:cacheprovider` (25 passed).

`_local/` is ignored by Git. If a stopped slice leaves a `results-*.json` that does not parse, delete that file and run the same command again: the replays are kept.

## 2024

`freeze-2024.json` (`ff08fca`) is a second sheet, frozen before any 2024 data exists; the O30f sheet is unchanged and scored first. Run `exam_s.py run` (`O30F_YEAR=2024`, both `O30S2_MODE`), then `exam_s.py score` once. It asserts that the engine files have not changed since its freeze: if the engine has changed, run from a worktree at `ff08fca`. `exam_s.py run`, `score` have not been run (no data); their verdict logic is covered by `test_exam_s.py`.
