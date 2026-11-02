# N01 intraday switching â€” verification and handoff

All work is offline Dev research. No application source, settings, migrations,
order authority, capital switch, Production files/services or Telegram delivery
changed. Production availability was sampled with read-only HTTP200 checks;
its Git checkout stayed `c97cb8c3ba0eeb4ac8e9966135b07034d760b40d`. This is not
broker health or continuous uptime proof. Unrelated dirty files/document slices
remain owned by their other authors and were not staged.

## Pre-score contracts and identities

- **2b1e2b0**: parent source, configuration, data, all45 books, information,
  costs and acceptance freeze pushed BEFORE base scoring. Six experts, three
  adaptive hypotheses, matched main/static/old-breakout controls. The owner's
  broad mixing/genome request authorizes three controlled variants here.
- **67e384e**:34 monthly model files and exact27 base outputs sealed BEFORE
  original18 adaptive replays. Models use3,669 counterfactual expert labels
  closed before each as-of month, prior252 sessions, fixed shrinkage/sample
  guards. Independent statistics reproduce all97 positive expert-cell ranks,
  max score discrepancy1.14e-13, zero future/unclosed labels used.
- **c3cd451**: separate N01-F input-freshness correction frozen before its
  scores. A latest-closed-bar state can outlive a long data gap; after its END
  is5min old, state becomes unavailable and regime-exit history empty. No
  strategy, cost, risk, timing or selection parameter tuning.
- **65f344e**: corrected34 model hashes sealed BEFORE18 corrected replays;
  original results retained. No STATIC training entry was stale, so all3,669
  labels and34 models are byte-identical to the original version. Reuse27 base
  economics by exact hashes; do not count these copies as fresh replays.
- Final results/report commit **6d1095d**, pushed. This following documentation
  handoff records that identity. Canonical output is **freshness/results.json**;
  root results.json is the preserved original version. Source freezes remain
  unchanged; reporting/auditor code is separate from decision-policy source.

## Completed commands

Interpreter: `python-engine/winvenv/Scripts/python.exe` (Python3.11.9).
Post-run observed library/platform versions are in environment.json; no packages
were installed or upgraded by this task. SciPy is absent and not required.
Use ONLY `O30F_YEAR=2024` OR `O30C_YEAR=2025/2026` for each year process.
No market-data API calls, download/login, Docker rebuild/restart or real orders.

```text
python -m pytest docs/research/simulation/2026-11-01-fno-intraday-router/test_router.py -q
# 23 passed,12.80s before source freeze
python -m pytest docs/research/simulation/2026-11-01-fno-intraday-router/test_router.py docs/research/simulation/2026-11-01-fno-intraday-router/freshness/test_freshness.py docs/research/simulation/2026-10-31-fno-broad-search/test_broad.py docs/research/simulation/2026-10-31-fno-broad-search/calendar/test_calendar.py docs/research/simulation/2026-10-31-fno-broad-search/expressions/test_expression.py docs/research/simulation/2026-10-31-fno-broad-search/diagnostics/test_result_schema.py docs/research/simulation/2026-10-31-fno-conditional-followup/test_follow.py docs/research/simulation/2026-10-31-fno-complements/test_gap.py docs/research/fno/2026-10-31-weak-spots/test_lab_w.py python-engine/tests/test_fno_book.py python-engine/tests/test_fno_policy_replay.py -q
# 166 passed,71.50s; earlier parent-only combined run161 passed,70.78s
python scripts/build_system_code_atlas.py
# 291 application modules; no atlas diff
python docs/research/simulation/2026-11-01-fno-intraday-router/router_lab.py freeze
# committed2b1e2b0 before base scoring
python docs/research/fno/run_slice.py --seconds 550 --env O30F_YEAR=2024 --log docs/research/simulation/2026-11-01-fno-intraday-router/_local/run-base-2024.log -- docs/research/simulation/2026-11-01-fno-intraday-router/router_lab.py run --phase base --jobs 3
# repeat O30C_YEAR=2025/2026;9 books/year,180/174/144s,all returncode0
python docs/research/simulation/2026-11-01-fno-intraday-router/analyze_router.py prepare
# each year; exact main/old-breakout trade-for-trade parity;
# 1,283/1,287/1,099=3,669 expert labels with immutable admissions
python docs/research/simulation/2026-11-01-fno-intraday-router/analyze_router.py train
# 34 chronological monthly models; hashes committed67e384e
python docs/research/simulation/2026-11-01-fno-intraday-router/reporting/verify_training.py
# 97 positive expert-cell choices independently verified by standard-library
# mean/stdev arithmetic, as-of labels, sample windows/counts and ranking
python docs/research/fno/run_slice.py --seconds 550 --env O30F_YEAR=2024 --log docs/research/simulation/2026-11-01-fno-intraday-router/_local/run-candidate-2024.log -- docs/research/simulation/2026-11-01-fno-intraday-router/router_lab.py run --phase candidate --jobs 3
# repeat O30C_YEAR=2025/2026;6/year,152/150/128s,all returncode0
python docs/research/simulation/2026-11-01-fno-intraday-router/analyze_router.py analyze
# original45-book analysis: passing=[],issues={},8,040 closed records
```

Freshness repair:

```text
python -m pytest docs/research/simulation/2026-11-01-fno-intraday-router/freshness/test_freshness.py -q
# 5 passed:4:59/5:00 boundary, long break, fresh/no-bar, no invented state exit
python docs/research/simulation/2026-11-01-fno-intraday-router/freshness/fresh_lab.py freeze
# source committedc3cd451 before corrected scores
python docs/research/simulation/2026-11-01-fno-intraday-router/freshness/analyze_fresh.py train
# no changed training labels/model bytes; new hashes committed65f344e
python docs/research/fno/run_slice.py --seconds 550 --env O30F_YEAR=2024 --log docs/research/simulation/2026-11-01-fno-intraday-router/freshness/_local/run-candidate-2024.log -- docs/research/simulation/2026-11-01-fno-intraday-router/freshness/fresh_lab.py run --jobs 3
# repeat O30C_YEAR=2025/2026;6/year,156/154/128s,all returncode0
python docs/research/simulation/2026-11-01-fno-intraday-router/freshness/analyze_fresh.py analyze
# passing=[],issues={},8,040 closed records incl5,200 reused base records
python docs/research/simulation/2026-11-01-fno-intraday-router/reporting/verify_decisions.py
# each year:1,362/776/702=2,840 routed trades;
# 5,680 exact archived entry/exit price checks;29 state exits verified
python docs/research/simulation/2026-11-01-fno-intraday-router/reporting/describe_contracts.py
# 803 old-breakout outcomes partitioned by DTE/clock/side;
# post-run descriptive only, not used for router selection/qualification
python docs/research/simulation/2026-11-01-fno-intraday-router/reporting/write_report.py
# readable report, exact strategy usage and first chronological mixed-day example
```

Each phase ran three guarded workers; immutable cached results support resume.
No550-second timeout was needed in these phases. The original corrected-report
attempt failed because six parent attribution JSON files had not been copied
into the new packet. All18 replays had completed successfully. They were copied
by exact hash, the failed attempt was preserved privately, and analysis reran
successfully. No source/model/trade changed for that artifact-path correction.
An uncommitted preliminary freshness-freeze snapshot was also retained before
fixing its reporting session-path wrapper; no correction scoring preceded the
committed matching source freeze. No full-engine-suite claim is made.

## Independent receipts and counts

- **63 fresh replays**:27 original base+18 original adaptive+18 corrected
  adaptive. Reused base copies add0 to that count. All18 corrected books match
  original trade economics/metrics/acceptance after excluding their new unique
  admission identifiers. The freshness guard fixes a latent boundary; it does
  not explain or improve the losing historical returns.
- **10,880 closed-record reconciliations** across those fresh executions;
  corrected combined analysis covers8,040 including5,200 reused base records.
  Zero unresolved, cash/whole-lot/cap/clock/metadata/memo defects; max fee-net
  discrepancy0.000049982 rupees. These records share699 archived sessions and
  counterfactual experts; they are not independent market observations.
- **699 sessions** (248/248/203) freshly parsed from sealed raw candles and
  identical to cached packets. All frozen source/data/daily/memo/settings hashes
  checked before/after. Private verifier/receipts under `_local/`.
- **2,840 corrected routed records** match causal entry states, direction,
  actual eligible experts, past model cutoff/fallback, immutable initial price,
  quantity, time/risk and unique book/year/leg identity. **5,680 prices** match
  the exact observation packets; **29 state exits** satisfy15min hold, three
  confirmed adverse states and priced bid. Normal management executes first.
- Current main and original low-ADX Donchian control match prior study records
  exactly. Normal-sized switching books preserve shared equity across intraday
  state/model changes; no independent expert P&Ls are added to fabricate a book.
- All boolean result flags are real JSON booleans; NumPy scalars are normalized
  by the new study writer before serialization. No default=str truthiness issue.

Public derived receipts: `base-crosschecks.json`, `input-crosschecks.json`,
`training-crosschecks.json`, both training manifests, `freshness/results.json`,
`freshness/label-view-crosschecks.json`, `freshness/training-crosschecks.json`,
`freshness/replay-comparison.json`, `freshness/decision-crosschecks.json`.
Private prices, individual expert labels/trades/model files, logs and full
dataset remain ignored. Their actual pre-score hashes and paths are retained.

## Interpretation and remaining work

All years were previously studied. Causal/past-only processing proves an
information boundary, not untouched out-of-sample validity or future profit.
The original2023 six-book exam is unchanged and unscored here. Prior-year daily/
futures warmup is not represented as entirely absent2023 information.

Current fees, normalized lot65, adverse modeled bid/ask, unknown archived regimes,
negative-volume/gap defects and special-session clock assumptions remain. The
63 runs are BAR_LIFECYCLE/partial historical execution evidence, not real fills,
broker margin proof, continuous wealth or a15k-account simulation. Closed-cash
drawdowns exclude intratrade marks; stops/brakes do not guarantee capital safety.

Final findings/next research contracts are in README.md and the top active-plan
handoff. No tested router is activated. Further entry/exit changes need their
own frozen experiment and prospective paper evidence; promotion/real-money
authority is separate. Rollback: stop research workers, retain both versions.
No application/deployment rollback is necessary.

The local `_local/evidence-report/` helper packet is post-run consistency
packaging at the final handoff Git SHA, not retrospective preregistration.
Its init/seal/report/verify must finish with no intervening commit. The true
pre-score contracts are the source/model commits above, and the helper cannot
independently prove strategy profitability or supplied execution fidelity.
