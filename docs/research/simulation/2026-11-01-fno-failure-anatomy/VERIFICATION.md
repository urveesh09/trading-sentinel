# N07 verification and successor handoff

Dev `C:/Users/Urveesh/Desktop/trading-sentinel`, branch
`codex/production-correction-hedge-p0`; interpreter
`python-engine/winvenv/Scripts/python.exe`, Python3.11.9; date2026-11-01 IST.
No packages installed, no acquisition/logins/Breeze/broker/Telegram calls.
2023 option exam remains deferred/uninspected/unscored; prior declaration hash
preserved. All2024–26 evaluation history already seen; no independent validation.

## Construction and freezes

- Original source/config/diagnosis/input freeze3ec85032a77413c933f8ade1e36c97edf06c852d
  committed/pushed before scoring. `freeze.json` retained verbatim.
- All18 NORMAL/ONE BASE/N04/N05 annual controls exactly reproduce source N05
  lifecycle economics. control-parity.json committed/pushed in8cb9a86.
- First candidate attempt exits1 after6.28s BEFORE pool/candidate evaluation,
  FileNotFoundError caused by __main__ self-import of build_controls. Original
  failure at `_local/preflight-failure-original.log`, hash in SOURCE_CORRECTION.
- Preflight-only correctione67fd64deaba907451de50a3370bf717fb967fa8 and active
  freeze-v2.json committed/pushed BEFORE any candidate score. SOURCE_CORRECTION
  binds original freeze/failure, all18 static evals/zero candidate evals, unchanged
  ASTs of entry/review/manage/close/books/reference_files/bindings and unchanged
  rules/config. Fix directly verifies committed control receipts/eval bytes and
  avoids loading the patched replay graph twice. No threshold/strategy tuning.
- `anatomy_lab.verify()` checks committed active freeze, all sources/inputs/old
  records and original freeze/correction hashes before and after each replay.
  Candidate preflight also verifies committed parity receipt and all36 old/fresh
  control file hashes. All completed old static controls retained and reused.

## Tests and replay commands

All from Dev with `$py='.\python-engine\winvenv\Scripts\python.exe'` and
`$study='docs/research/simulation/2026-11-01-fno-failure-anatomy'`.

1. `& $py $study/diagnose.py` plus per-year`diagnose_paths.py`: all169 N04 trades,
   exact changed N03/N04/N05 economic pairs and29 N06 selected N04 trades; prior
   decision evidence separated from later labels. Raw/eval inputs hash-bound.
2. `pytest` new`test_anatomy.py` plus N05`test_refine.py`, N04`test_exit.py`,
   N03`test_eff.py`:98 passed initially, including28 new; after the preflight-only
   correction the new file passes29 (additional real-CLI control regression).
   Therefore99 distinct research checks. Native`test_fno_exit_rules.py` plus
   `test_fno_policy_replay.py`:11 passed. **110 total; no full-suite claim.**
3. `& $py scripts/build_system_code_atlas.py`:291 modules, no atlas diff.
4. `& $py $study/anatomy_lab.py freeze`: original v1 and later explicitly named
   v2 freezes retained; write-once. Do not delete/re-freeze existing evidence.
5. For each year clear inherited O30F_YEAR/O30C_YEAR; set ONLY O30F_YEAR=2024
   or O30C_YEAR=2025/2026. `& $py $study/anatomy_lab.py run --phase reference --jobs 3`.
6. `& $py $study/build_controls.py`:18 exact controls. Then committed controls
   before candidate scoring. `& $py $study/anatomy_lab.py check-controls` regression
   passes without importing a second runner instance.
7. Same year environment, `run --phase candidate --jobs 3`:12 NORMAL/ONE candidate
   annual books plus15 NO_EXTRA_STRESS diagnostic annuals. Three workers maximum,
   inherited RAM guard. Research network explicitly denied. Final successful
   commands/durations (initial preflight failure retained separately):

| Phase | Year | Exit | Seconds |
|---|---|---:|---:|
| reference | 2024 | 0 | 83.75 |
| reference | 2025 | 0 | 88.99 |
| reference | 2026 | 0 | 75.81 |
| candidate | 2024 | 0 | 116.91 |
| candidate | 2025 | 0 | 121.2 |
| candidate | 2026 | 0 | 107.86 |

8. `& $py $study/analyze_anatomy.py`:45 full annual cash books;18 exact controls;
   2545 closed financial/immutable admission identities. Current fees, extra costs,
   own cash/lot caps and entry/exit clocks reconcile; no memo/financial errors.
9. Per-year`reporting/audit_paths.py`:2545 accepted trace bindings,
   5090 archived prices,345 retests,345 first-exit lifecycles/
   17213 management observations/478 structural reviews independently checked.
   Ordinary exits and research predicates re-evaluated using declared cost for
   EACH book, including0extra stress; no missed-bid interpolation/perfect peaks.
10. `reporting/verify_statistics.py`:45 cash paths,15 weekly vectors, all period/
    profit/DD/sample/best-trade/day flags, two four-week-block max-T comparisons
    (4096draws,seed110701) independently verified. Cash residual<3e-10Rs.
11. `reporting/repair_effects.py`:36 comparisons,66 changed exact pairs, all
    gains/losses/unpaired contributions retained. Both candidates are identical
    economically in ALL9 year/sizing/cost comparisons, not independent successes.
12. `reporting/entry_anatomy.py`: ALL169 known-at-entry contexts and later wins/
    losses separated; no new filter fitted. `explain_failures.py` and
    `trace_resizing.py` preserve all member losses/cost components/selector cases
    and separately identify changed quantities, not false same-economics pairs.
13. `reporting/reuse_inputs.py`: inherited source/data hashes unchanged; earlier
    699 raw/cache checks explicitly reused, ZERO fresh raw/cache checks claimed.
    Original gaps and56 negative-volume2025 bars retained, not silently repaired.
14. `reporting/write_report.py`: full results, failures, opportunity costs,
    sensitivity/one-lot tables and separate FNO_RESEARCH_FAILURES_N07 md/json.
    Old N03/N04/N05/N06 records remain unchanged.

## Findings and limits

PREMIUM_AWARE_RETEST_N07 canonical NORMAL|PREMIUM_STALL yields57,982/52,023/77,135,
annual CLOSED falls2.16/4.77/2.76%. All-year net/no-extra-DD improvement over N05,
also in fixed-one-lot diagnostic. It sacrifices2025 N04 net2027.60 and higher
4.77%vs4.65%closed fall;2026 equals N04. Frozen strict against-BOTH acceptance
fails, t0.65/p0.4384 vsN04; secondary t1.70vsN05 is not promoted to primary.
No-extra-stress candidates match N04 exactly; actual-cost evidence still absent.
The effect is cost-aware loss management, not proven predictive switching.

Fresh250k PER YEAR, normalized65unitlot, original2/3caps/LOW TPB1, modeled
bid/ask/current fees/stress. No continuous wallet, shared multi-module portfolio,
real-depth/IV/Greek attribution or forecast for the small real test. Closed DD
excludes intratrade/gap risk and is not a future limit. Later peaks/recoveries
are descriptive labels and never early signals. Event-followup is explicitly
POST-result context, not a new date filter or primary-rule change.

## Production and source non-interference

Production checkoutc97cb8c3ba0eeb4ac8e9966135b07034d760b40d, engine healthy;
StartedAt2026-11-01T01:41:39.3519856Z unchanged; API sampled200 throughout.
No Production file/env/service/money/lot/order/Telegram/restart/deploy changes.
Application diff against Dev f008ae4 (python-engine/node-gateway/agent/scripts)
is empty. Only own research/docs committed; unrelated owner dirt retained,
including40/42/50-line checklist/plan/guide slices. Atlas291/no diff. No migration.

Rollback stops only research workers; all completed normally except the retained
preflight failure, no Production rollback. All results/source/docs are Dev/pushed,
not deployed. Final fixed-SHA post-run skill report/verify is consistency packaging,
not retrospective preregistration or profitability qualification.

Remaining: predeclared prospective keyed shadow/quote/cost/cash evidence for
N04/N05/N07; complete independently sourced event-calendar research if pursued,
not a filter on one observed losing date;51 prior-green losers motivate a separate
profit-retention hypothesis with opportunity-cost controls.2023 deferred until
explicit request; no automatic risk/lot/deployment authority.
