# N03 verification, identities and remaining work

Dev offline NIFTY single-leg research only. No application code/configuration,
migration, money switch, order, partner message or Production edit/restart.
No new packages/downloads/API login. All2024–2026 years already seen.2023 option
data/exam uninspected and unscored; its existing freeze hash stays unchanged.
Inherited prior daily/futures warmup is declared, not a2023 option backtest.

## Pre-score identities and reporting correction

- **2de5448** source/config/data/memo/daily/decision-file/57-book/acceptance
  freeze committed and pushed BEFORE the new scores. Two independent EFF
  hypotheses only; no combined third arm or parameter grid. All flat policy,
  source, PLAN and configuration files remain byte-identical to that freeze.
- **31d1dd9** reporting-only correction committed before reviewing outcomes:
  original analyze_eff.py incorrectly asserted all LOW TPB entries were65.
  TPB_FULL explicitly retains normal sizing. Nested reporting/reconcile.py
  changes ONLY that assertion: all LOW entries must be puts and TPB_ONE LOW
  entries65. No strategy, book, input, cost or acceptance changes. The original
  frozen file/assertion is preserved; corrected reporter is canonical.
- All57 engine replays succeeded. The long-running wrapper had already loaded
  the old reporter path, so its final automatic analysis call exited1 on that
  known assertion. That is a retained reporting failure, not a failed strategy
  replay, and produced no results.json. Running the separate corrected reporter
  then reconciled all57 books without score/rule changes; zero candidates pass.
- Results/report commit identity is recorded by the immediately following
  handoff prefix in SYSTEM_GUIDE/NEXT_AGENT_PLAN/HANDOVER_CHECKLIST. root
  results.json is canonical; reporting/ scripts describe/audit, never route.

## Commands and measured results

Use python-engine/winvenv/Scripts/python.exe (Python3.11.9). Bare Windows python
is a Store shim. Only O30F_YEAR=2024 OR O30C_YEAR=2025/2026 per process. Private
wrappers run each year sequentially and parse completion/returncode separately.
All engine slices completed in their first550-second budget, three workers,
under the inherited memory guard. No failed/time-limited replay was discarded.

```text
python -m pytest docs/research/simulation/2026-11-01-fno-eff-improvement/test_eff.py -q
#27 passed1.41s; added hard-flat/per-leg checks29 passed1.40s;
#final pre-score30 passed1.37s (30 unique new tests)
python docs/research/simulation/2026-11-01-fno-eff-improvement/_local/prepare.py
#reporting/probe_features.py for each year, then eff_lab.py freeze
#63 old MAIN EFF admission locations18/27/18 have fresh contexts/bid/ask;
#feature-audit.json is availability evidence, not counterfactual entry decisions
python scripts/build_system_code_atlas.py
#291 modules; no atlas diff; repeated during reporting correction/final work
python docs/research/fno/run_slice.py --seconds 550 --env O30F_YEAR=2024 --log docs/research/simulation/2026-11-01-fno-eff-improvement/_local/run-2024.log -- docs/research/simulation/2026-11-01-fno-eff-improvement/eff_lab.py run --jobs 3
#repeat O30C_YEAR=2025/2026;19 books/year194/210/176s,allreturncode0
python -m pytest docs/research/fno/2026-10-31-weak-spots/test_lab_w.py python-engine/tests/test_fno_book.py python-engine/tests/test_fno_policy_replay.py -q
#49 passed22.05s; together79 unique focused tests, not full engine suite
python docs/research/simulation/2026-11-01-fno-eff-improvement/analyze_eff.py
#retained old reporting assertion fails, exit1; no policy/freeze mutation
python docs/research/simulation/2026-11-01-fno-eff-improvement/reporting/reconcile.py
#57 fresh full-cash annual books,2001 closes;12 N02 controls exact;
#zero financial/memo/clock/identity errors; zero candidates pass
python docs/research/simulation/2026-11-01-fno-eff-improvement/_local/check_all_inputs.py
#699 raw/cache sessions248/248/203 identical, source bindings unchanged
python docs/research/simulation/2026-11-01-fno-eff-improvement/_local/verify_all.py
#independent reporting/verify_paths.py per year;2001 accepted trace bindings;
#4002 actual archive ask/bid prices;144 causal retest confirmations;
#381 HORIZON lifecycles to first executable exit over15001 observations;
#38 replayed lifecycles actually extended, all urgent exits preserved
#reporting/describe_effects.py reconciles12 normal/fixed candidate books
python docs/research/simulation/2026-11-01-fno-eff-improvement/reporting/verify_statistics.py
#57 annual paths,19 weekly vectors,eight relative/multiplicity tests;
#4-week blocks,4096 shared resamples,seed110301;zero score/p/cash errors
#max cash summation residual2.474e-10;zero exact-versus-rounded flag differences
python docs/research/simulation/2026-11-01-fno-eff-improvement/reporting/coverage.py
#248/248/203 sessions all have observations; per-session gaps/exclusions retained
#all remain PARTIAL under the candle/depth/regime model, not real-fill coverage
python docs/research/simulation/2026-11-01-fno-eff-improvement/reporting/write_report.py
#complete measured README and57-run inventory, all failures visible
python -m py_compile <reporting/reconcile.py> <reporting/verify_paths.py> <reporting/describe_effects.py>
#success; paths are in this study's reporting/ directory
```

Early bounded rg used a nonexistent wildcard directory path and returned a
path error. Correct directory reads succeeded. No code/data was changed by it.
No market API, broker, messaging or scheduler was started by a replay/verifier.

## What is verified

Normal BASE MAIN/TPB_ONE/TPB_FULL/CORE_SELECT exactly match all12 corresponding
N02 annual control economics, except fresh admission IDs generated for this
experiment. All57 books preserve cash/fee/stress/whole-lot rules, both size caps,
normal entry/hard-flat limits and explicit special-session clocks. Fixed-one-lot
diagnostics retain brakes. N02 daily CORE_SELECT decisions are reused by exact
hashes, not trained on modified strategy outcomes. All trades bind immutable
initial time/premium/quantity/stop/target and accepted trace at their exact key.

RETEST's shared original named-signal memo is unchanged. Independent audit
recomputes original EFF signal, broken level/ATR, every intervening closed bar,
zone/stop/gap/window validity and actual confirmation target. Current/future-bar
mutation, repeated-bar consistency, no same-bar entry and day/crisis/age resets
are covered. All three non-EFF members retain their native functions;
any different opportunities/exposures through shared cash are reported explicitly.

HORIZON policy is per open leg and restored on success/error. Independent exit
replay reconstructs entry terms, actual successive observations, net liquidation
including stress, progress, independently computed causal VWAP/continuation,
trail state and first executable ordinary exit. Hard-flat and stop priorities
are retained. Holding beyond60min alone can be next-observation timing; the
ever_extended flag is separately reconstructed. Counts overlap repeated books,
not independent market samples. No stop/quote fill is invented in a data gap.

Exact-entry exit pairing in effect-accounting.json requires identical immutable
entry time/premium/quantity/stop/target. Resized, missing or different entries
remain unpaired. Member contribution differences are accounting of complete
actual paths, not an oracle adding rejected trades or independent profits.
Statistics are independently recalculated from cash closes; all eight candidate
comparisons are included, not only the attractive one. All failures preserved.

## Interpretation and limits

RETEST main normal +37,258/+14,899/+25,066 versus BASE +16,371/+5,710/+30,540;
closed drawdown lower each year. TPB_ONE+RETEST +56,192/+50,090/+54,153, more
balanced on seen data but worse2026 than its baseline. HORIZON helps2026 and
harms earlier years. Standalone EFF never becomes consistently profitable.
Matched one-lot MAIN RETEST improves all three totals but is diagnostic and
does not establish pure EFF improvement or authorize a new live size cap.

No normal candidate passes the unchanged all-year/paired/statistical bar.
No additional offspring or thresholds were tried after the scores. Two-component
HORIZON does not isolate stall-only versus continuation-only alpha; that is the
next separately frozen two-arm study. Do not combine winners by hindsight year.
Keep2023 deferred until the owner later requests its examination. No prospective
profitability, live readiness, partner qualification/delivery or capital-loss
guarantee follows from tests or these repeatedly studied historical years.

Normalized65 lots/current fees, candle-derived adverse quotes, known gaps and
unknown historical regimes/depth limit execution fidelity. The same sealed2025
inputs contain56 negative-volume bars; they were not silently repaired or days
dropped to improve scores. Invalid continuation falls back to original exit
management. Annual cash resets and closed-cash drawdown are declared experimental
models, not a continuous account or worst intraday MTM loss.

Read-only Production health samples returned HTTP200; checkout remained
c97cb8c3ba0eeb4ac8e9966135b07034d760b40d. This is sampled availability, not
continuous uptime/broker-route/subscription verification. All implementation is
in Dev and pushed; no deployment/configuration/migration/Production rollback.
Other authors' dirty files/doc slices remain unstaged. Stop research workers for
rollback; completed outputs are resumable. Research workers finish before handoff.

After final documentation commit, _local/evidence-report packages all19 policy
experiments at that unchanged handoff SHA and runs helper report/verify. This
is post-run consistency packaging, not preregistration or economic proof; real
pre-score source/contract identity is2de5448, corrected reporter31d1dd9.
