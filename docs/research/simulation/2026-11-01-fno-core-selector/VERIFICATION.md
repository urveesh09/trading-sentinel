# N02 verification and successor handoff

Offline Dev research only. No application source/configuration/migration,
real-money switch, order, Telegram delivery, Production file or Docker service
changed. Other authors' dirty files/document slices were preserved and not
staged.2023 was not scored; its existing frozen exam hash stays unchanged.

## Identities and ordering

- **cb222ba**: source/config/data/daily/memo/legacy-evidence freeze pushed
  BEFORE12 reference replays. PLAN.md contains both hypotheses and unchanged
  acceptance. No parameters or underlying entry/exit functions retuned.
- **8e2d795**: exact reference parity and independently verified699 daily
  choices per policy sealed BEFORE six candidate replays. decision-manifest
  binds every reference evaluation and private per-year decision file.
- Results/report identity is recorded by the immediately following handoff
  prefix in SYSTEM_GUIDE/NEXT_AGENT_PLAN/HANDOVER_CHECKLIST. The root results.json
  is canonical. No candidate passes; no activation/qualification inferred.
- Flat decision source, configuration and PLAN/SOURCES remain frozen. Later
  reporting/ scripts test and describe results only. No second scoring rule,
  threshold relaxation or offspring after observing candidate returns.

## Completed commands and actual results

Interpreter: python-engine/winvenv/Scripts/python.exe, Python3.11.9. Bare Windows
python is a Store shim and was not used. No packages installed/upgraded. Only
O30F_YEAR=2024 OR O30C_YEAR=2025/2026 is set for a given replay process.
Research replay and verification block external network use. No data API/login.

```text
python -m pytest docs/research/simulation/2026-11-01-fno-core-selector/test_core.py -q
#12 passed,1.35s and1.49s before freeze; repeated12 passed,1.63s
python -m pytest docs/research/fno/2026-10-31-weak-spots/test_lab_w.py python-engine/tests/test_fno_book.py python-engine/tests/test_fno_policy_replay.py -q
#49 passed,22.44s
python -m pytest docs/research/simulation/2026-11-01-fno-core-selector/test_core.py docs/research/simulation/2026-11-01-fno-core-selector/reporting/test_contract.py -q
#16 passed,1.57s; adds exact stale-bar boundary and successful low-cap restore
python docs/research/simulation/2026-11-01-fno-core-selector/core_lab.py freeze
#source/data/configuration frozen and committed cb222ba before scoring
python docs/research/fno/run_slice.py --seconds 550 --env O30F_YEAR=2024 --log docs/research/simulation/2026-11-01-fno-core-selector/_local/run-reference-2024.log -- docs/research/simulation/2026-11-01-fno-core-selector/core_lab.py run --phase reference --jobs 3
#repeat with O30C_YEAR=2025/2026;4 books/year,74/80/64s,returncode0
python docs/research/simulation/2026-11-01-fno-core-selector/analyze_core.py train
#569 reference closes verified; nine exact legacy controls;699 daily models
python docs/research/simulation/2026-11-01-fno-core-selector/reporting/verify_training.py
#699 models,1398 relative scores,1398 policy choices,zero future/unclosed labels
#max independent score/arithmetic error2.274e-13; hashes sealed8e2d795
python docs/research/simulation/2026-11-01-fno-core-selector/_local/check_all_inputs.py
#248+248+203=699 raw/cache observations freshly compared; zero mismatches
python docs/research/fno/run_slice.py --seconds 550 --env O30F_YEAR=2024 --log docs/research/simulation/2026-11-01-fno-core-selector/_local/run-candidate-2024.log -- docs/research/simulation/2026-11-01-fno-core-selector/core_lab.py run --phase candidate --jobs 3
#repeat with O30C_YEAR=2025/2026;2 books/year,40/42/36s,returncode0
python docs/research/simulation/2026-11-01-fno-core-selector/analyze_core.py analyze
#18 fresh annual books,806 closed records,zero financial/memo/clock errors
#max net-equation rounding residual0.00004965 rupees (tolerance0.0001)
#zero candidates pass declared unchanged rule
python docs/research/simulation/2026-11-01-fno-core-selector/_local/check_all_executions.py
#per-year verifier reporting/verify_executions.py,172/383/251 admissions
#806 exact accepted trace bindings,1612 archive quote checks;zero errors
python docs/research/simulation/2026-11-01-fno-core-selector/reporting/describe_outcomes.py
#actual main/low-addition accounting; no unmatched P&L added back
python docs/research/simulation/2026-11-01-fno-core-selector/reporting/write_report.py
#README generated from canonical records, including stronger static references
python scripts/build_system_code_atlas.py
#291 application modules; no atlas diff
```

The private _local/run_phase.py wrapper sequentially runs all three year slices
and train/analyze. It parses returncode/finished separately, resumes completed
keys, and never interprets a timeout as a completed score. All six slices above
completed within their first550-second budget; no replay failures/retries.
Private input/execution wrappers have no strategy authority; public reporting/
contains the independent execution/training verifiers. Missing private results
must be regenerated under the exact freeze, not guessed from rounded tables.

Two initial rg commands used unsupported Windows wildcard directory arguments
and returned path-syntax errors; bounded directory searches corrected them.
They changed no code/data. No failed test or candidate result was hidden.

## What the checks establish

- Independent whole-policy controls MAIN/NO_EFF/TPB_FULL: exact nine old
  economics after member-name normalization, not merely matching summary P&L.
- All18 books retain current cash/risk/max-size/expiry/crisis/daily-loss,
  management and entry/exit-deadline contracts, fee/stress costs and immutable
  entry identities. Profile changes do not remap open positions or reset risk.
- LOW additions are puts only; TPB_ONE LOW entry quantity is65. Successful and
  failed admissions restore both main lot caps. Main entry order/first-firing
  stretch rejection is preserved. Candidate signal-bar END age>=5min refuses
  a new admission; exact boundary tests pass. Normal management is unchanged.
- Every accepted trace binds its exact chosen profile, closed signal, clock,
  strategy, gate and archived ask/bid. Both2026 candidates match all33 MAIN
  signal/entry opportunities, but seven main quantities differ; only26 match
  complete economics. CORE_SELECT2025 intentionally omits three EFF entries.
- Models independently match prior84-session samples, strictly earlier closes,
  paired weekly arithmetic, eligibility/ranking and two-day persistence. Test
  mutation of current/future/unclosed outcomes leaves earlier choices unchanged.
- Post-entry signed underlying moves and main/added accounting are descriptive
  only, never passed back to policy choice or threshold fitting.

## Limits and next work

65 unique focused checks here (16+49), not the full engine suite. The frozen
three-year sample is already seen; chronological labels are causal but repeated
hypothesis design is not independent out-of-sample validation. Two-arm max-t is
exploratory and does not correct all earlier searches. Best-day dependence and
paired significance fail for both candidates; keep those failures visible.

Annual cash resets are declared experimental accounts, not a34-month wallet.
All fills are candle-derived/model quotes with normalized65-unit lots/current
fees; missing historical depth/regimes, gaps and the unchanged56 known2025
negative-volume bars limit fidelity. Closed-cash drawdown is not intraday MTM
drawdown or a live capital-loss guarantee. This does not validate the small
real-money test, partner qualification/delivery or profitability.

Next contract is in README: preserve MAIN as an explicit option, keep static
TPB_ONE/TPB_FULL comparisons, distinguish selection from sizing using a matched
one-lot control, audit causal option-payoff feature availability, freeze at most
two new hypotheses before scores. Underlying EFF exit changes require their own
later freeze. Do not test2023 until the owner later requests it. No deployment,
configuration, migration or money approval is implied. Rollback stops research
workers; all completed outputs are resumable, no Production rollback needed.

Read-only Production check returned HTTP200 from /api/health; checkout remained
c97cb8c3ba0eeb4ac8e9966135b07034d760b40d. These are sampled availability checks,
not continuous uptime, broker-route/subscription or trading-health proof.

After the final documentation commit, _local/evidence-report is packaged and
verified at that unchanged handoff SHA. It is post-run consistency packaging,
not preregistration; genuine pre-score contracts are cb222ba and8e2d795 above.
