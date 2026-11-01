# N10.1 verification record

Base7bbfb89. Immutable original source/config/input freeze c567f8e; exact controls f4f92f2. Trading source and all frozen inputs remained unchanged throughout every replay. No post-score rule change or silent re-freeze.

## Reproduction

Use python-engine/winvenv/Scripts/python.exe (Python3.11.9), from the Dev root. No new installation.

```powershell
$py = '.\python-engine\winvenv\Scripts\python.exe'
$study = 'docs/research/simulation/2026-11-02-fno-n101'
& $py "$study/prepare.py"  # initial use only: refuses to replace freeze.json
# Commit source/config/freeze BEFORE any candidate score.
& $py "$study/run_study.py" controls
& $py "$study/score_n101.py" parity
& $py "$study/run_study.py" annual
& $py "$study/run_study.py" carry
# Per year, set N08_YEAR=2023,2024,2025,2026 and run audit_n101.py.
& $py "$study/score_n101.py" report
& $py "$study/audit_watch_peak.py"
```

The runner preserves logs and refuses to overwrite an earlier invocation. Cached replay evaluations are retained; use a separately frozen new folder for new research, not deletion or relabelling. Do not open2022 or invoke a broker to reproduce this study.

## Focused verification

-27 new mechanics/independent checker tests passed (final new-file run1.69s);21 were frozen before scoring and6 additional independent validation cases were added without changing a trading rule.
-49 existing N10 tests passed1.44s.
-24 native cost/entry/exit/replay tests passed12.03s.
-100 DISTINCT focused tests; repeated invocations are not extra cases. No full-engine-suite claim.
-16 exact controls/856 old economic trade lifecycles.
-Atlas regenerated291 modules/no diff. No application source changed.

| Replay child | Year | Exit | Seconds |
|---|---|---:|---:|
| command-annual-2023 | 2023 | 0 | 96.77 |
| command-annual-2024 | 2024 | 0 | 79.56 |
| command-annual-2025 | 2025 | 0 | 87.14 |
| command-annual-2026 | 2026 | 0 | 73.91 |
| command-carry-2023 | 2023 | 0 | 245.09 |
| command-carry-2024 | 2024 | 0 | 200.38 |
| command-carry-2025 | 2025 | 0 | 224.89 |
| command-carry-2026 | 2026 | 0 | 192.2 |
| command-controls-2023 | 2023 | 0 | 95.81 |
| command-controls-2024 | 2024 | 0 | 80.09 |
| command-controls-2025 | 2025 | 0 | 87.0 |
| command-controls-2026 | 2026 | 0 | 73.47 |

Exactly80 annual executions:16 controls+16 new annual/cost+48 continuous year slices. Two replay workers maximum, sequential years. No extra parameter grid or unregistered arm.

| Final independent audit | Exit | Seconds |
|---|---:|---:|
| 2023 | 0 | 8.48 |
| 2024 | 0 | 6.64 |
| 2025 | 0 | 9.61 |
| 2026 | 0 | 7.62 |

Final audit totals: `{"books": 80, "cash_identities": 6066, "funded_adds": 71, "modeled_prices": 8608, "money": 4125, "native_admissions": 3914, "premium_stop_lifecycles": 71, "states": 76, "watch_attempts": 1465, "watch_releases": 6}`. All modeled prices were checked against cached candle-derived quotes, not represented as actual market depth/fills.

WATCH peak audit:72 watch-bearing windows and35 release checks INCLUDING carried repeated history. No release used a lagged peak or crossed the75% bound.18 terminal trackers lag a final winning close; independently computed actual peaks are preserved. This is a known state-reporting/integration gap, not hidden behind a passing profit claim.

## Failures and limits retained

-Before freeze: two new-test failures (zero quantity divided before validation; reserve-failure fixture started with an already-unfunded floor). Corrected before any score, then21 frozen cases passed.
-First helper init refused hyphenated module identifiers; retry used lowercase underscores. No evidence folder/result existed from that rejected call.
-First full carry audits failed because the checker rebuilt cash from a two-decimal extra-cost display. CHECKER_CORRECTION.md records exact differences and the original checker is preserved at f4f92f2. Corrected to the exact frozen cost function, NOT a larger cash tolerance. No rule, score or receipt changed.
-Opening equity resides in notes.start_equity. Same-time settlements preserve their existing order. These checker details were corrected before the first full audit.
-The initial helper registration/seal is retained privately at _local/evidence-report. A final fixed-SHA packet is created separately after the result/handoff commits; it is explicitly post-run consistency, not a replacement preregistration.

Original freeze: 974 source/config hashes and 1004 cached input/old receipt hashes. The full input tree was rehashed, not just the manifest. Daily binding asserts2023 uses daily-2023.json. Frozen fees, effective non-secret settings and book variants are in configuration.json.

All2023–26 years seen;2026 endsOct28. BAR_LIFECYCLE/PARTIAL; normalized65-unit lots/current fees/modeled spreads; original missing/clipped candles retained. No unknown day becomes a zero-return day. No untouched evidence, depth, broker execution or whole-system shared-capital proof. Small15000 live trial is outside this250000 reserve policy.

## Noninterference / delivery

Productionc97cb8c remained running at its original2026-11-01T01:41:39.3519856Z engine start; read-only API health200. At least about5.5GB host memory remained free during the two-worker replay. No edit/restart/build/deploy/env/migration/authority/live halt/lot/capital/order/Telegram/task registration, credential output/use for network access, provider call or2022 access. Existing owner dirty doc slices and untracked work are preserved.

Runtime/source independence is checked with git diff7bbfb89 for python-engine,node-gateway,agent,scripts and by frozen source hashes. This directory is research, never imported by the application. All original N08/N09/N09.1/N10 source, reports and2022 exam remain unchanged. Final commit identity is recorded in IDENTITY.json and the active plan.
