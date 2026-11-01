# N06 verification, environment and handoff

Dev: `C:/Users/Urveesh/Desktop/trading-sentinel`, branch
`codex/production-correction-hedge-p0`. Interpreter
`python-engine/winvenv/Scripts/python.exe` (Python3.11.9).
Client date2026-11-01, Asia/Kolkata. No packages installed. Production assessed
read-only at checkoutc97cb8c3ba0eeb4ac8e9966135b07034d760b40d.

## Pre-score checkpoints

Results/report **4525278348f1e87240a9f77442f482d4c1363303**, committed and pushed.
The following documentation-only handoff records this identity; final fixed-SHA
post-run helper packet is local and must not be confused with pre-score freezes.

- Source/config/input/reference freeze **a5b2d7c76ac6f37680d307594da7bcdb854e2185**,
  committed/pushed before any N06 annual scoring. `PLAN.md` and configuration
  frozen with source. All prior three checkpoint records remain byte-identical.
- Twelve fresh annual static controls match all saved trade economics exactly.
  The twelve source eval hashes are also bound in freeze/decision-manifest.
- Model/decision manifest **5c74b479938bbc2c0b079ef6615bdf6bc0098512**,
  committed/pushed before candidate cash scoring. Independent4194 candidate
  evidence-model/1398 decision checks passed. Private decision/model files hash
  bound; no policy/threshold/lot/fee change after seeing scores.
- All years2024–26 previously inspected; no new independent holdout.2023 option
  exam uninspected/unscored. Its existing declaration hash is retained, not its
  outcome. No downloads, login or Breeze/broker calls.

## Commands and observed results

Run from Dev with `$py='.\python-engine\winvenv\Scripts\python.exe'` and
`$study='docs/research/simulation/2026-11-01-fno-variant-selector'`.

1. `& $py -m pytest $study/test_variant.py -q --disable-warnings` —22 passed.
2. Same file plus N05`test_refine.py`, N04`test_exit.py`, N03`test_eff.py` —
   **92 passed**, including those22; do not double-count them.
3. `& $py -m pytest $study/reporting/test_evidence_guards.py -q --disable-warnings`
   —6 passed: lucky day, adverse path, losing labels, read-only source, private
   event detail exclusion, unavailable database not created.
4. `& $py -m pytest python-engine/tests/test_fno_exit_rules.py python-engine/tests/test_fno_policy_replay.py -q --disable-warnings`
   —11 passed. **109 distinct focused checks total; no full-suite claim.**
5. `& $py scripts/build_system_code_atlas.py` —291 modules; atlas no diff.
6. `& $py $study/variant_lab.py freeze` —write-once, all three years hashed.
7. For EACH year, clear inherited `O30F_YEAR`/`O30C_YEAR` process environment;
   set only `O30F_YEAR=2024`, or `O30C_YEAR=2025`/`2026` as appropriate;
   `& $py $study/variant_lab.py run --phase reference --jobs 3`.
   Three workers maximum. Twelve completed annual books, exits0;
   wrapper durations79.25/82.01/68.33s, private `run-reference-YEAR.log`.
8. `& $py $study/build_models.py` —write-once model manifest only after all12
   exact control comparisons;4194 independent model/1398 choice checks via
   `reporting/audit_selection.py`. `reporting/reuse_inputs.py` confirms inherited
   data/source bindings unchanged; prior699 raw/cache checks reused, not rerun.
9. Commit/push model manifest, THEN same year environment and
   `& $py $study/variant_lab.py run --phase candidate --jobs 3`.
   Six completed annual books, exits0,56.12/57.75/50.78s.
10. `& $py $study/analyze_variant.py` —18 annual books,911 closed financial/
    immutable-admission identities, no financial/memo/clock/cash errors;
    **zero candidates pass the strict frozen acceptance**, all verdicts retained.
11. For each year `& $py $study/reporting/audit_paths.py` —911 accepted trace
    bindings,1822 archive entry/exit prices,96 independently confirmed retests,
    73 first-exit lifecycles/3703 management observations/292 structural reviews.
    Private per-year receipts aggregated into `path-crosschecks.json`; zero errors.
12. `& $py $study/reporting/verify_statistics.py` —initial attempt failed due
    solely to independent checker's2026 calendar-block assumption; see
    `CHECKER_CORRECTION.md`. Corrected checker passes all18 cash paths/six weekly
    vectors/two comparisons/4096 four-week max-T draws seed110601. Max cash
    reconciliation residual1.75e-10Rs. Strategy/scoring/freeze unchanged.
13. `& $py $study/reporting/attribute_selector.py` —six comparisons reconcile
    whole cash-path deltas into identical-entry exit effects and unpaired entries.
14. `& $py $study/reporting/write_report.py` —complete README and separate
    FNO_RESEARCH_SELECTOR_N06 md/json. Earlier three checkpoint files unchanged.

Source/run `verify` checks Git-committed freezes, full inputs and actual decision
hashes before/after replay. All historical replay workers explicitly deny network.
Finished result caches are reused only by exact task key, never silently reset.
The write-once model/freeze commands are construction commands, not overwrite
commands. Keep existing evidence; do not delete/re-freeze to force a rerun.

## Production evidence and non-interference

`docker inspect python-engine --format '{{json .Mounts}}'` identified the existing
`production_trading-sentinel_trading_data` volume. One disposable existing-image
container ran `reporting/execution_inventory.py --data /data --out /out/execution-inventory.json`
with `--rm --network none --user quantuser`, data mount`/data:ro`, study source
mount`/research:ro`, only Dev `_local` writable. No Production secrets/env file.
SQLite mode=ro, explicit read transaction; only counts/date bounds exported.
Public sanitized aggregate: `execution-availability.json`.

51 CLOSED FNO_PAPER positions; no real execution-event/run tables;33 quote days
throughOct30;3 exit files throughOct29. Actual fill-cost evidence UNAVAILABLE,
not a zero-profit or zero-order claim. No raw broker identities or credentials.
Containers healthy; API sampledHTTP200 before/during/after research. Engine
StartedAt remained2026-11-01T01:41:39.3519856Z. No edit/restart/deployment,
settings/real-money/order/Telegram action. Production checkout unchanged.

An incidental read-only `git diff a5b2d7c` was issued in Production instead of
Dev and returned `bad revision` (that research commit is not in Production).
Corrected in Dev: `git diff 0187493 -- python-engine node-gateway agent scripts`
is empty. No files changed by that failed inspection.

## Scope, source status and remaining work

Only offline research and documentation changed in Dev; no migration or runtime
configuration impact. Atlas regenerated291/no diff. Unrelated `.gitignore`,
other-agent files and doc slices retained; selective commits preserve their
40/42/50-line checklist/plan/guide changes. No branch reset, pull or merge.

Fresh Rs250000 PER YEAR,65-unit normalized lots, original cash/brakes/2–3lot
caps/LOW-day1lot, historical candle quote model/current fees plus stress. Not a
whole-system portfolio, continuous wallet, actual cost or future profitability
claim. Quote gaps and56 original2025 negative-volume bars remain documented.
Only complete-bar observations and registered native deadlines are replayed.

Remaining: prospective keyed shadow outcomes for every policy, preserved quote
paths and separately authorized real fill/cost/cash reconciliation; a predeclared
future comparison before scoring;2023 deferred; sizing conditional and not
unlocked. Stop only analysis workers if needed; no Production rollback needed.
Post-run skill evidence packet is generated at the fixed final handoff SHA,
then report/verify run without further commits. It checks consistency and does
not retroactively preregister or qualify these seen-data strategies.
