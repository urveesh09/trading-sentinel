# O31i verification and handoff

Dev research only. No application source/settings/migrations, broker authority,
capital activation, deployment, orders, messages or Production edits/restarts.
Production checkout remained `c97cb8c3ba0eeb4ac8e9966135b07034d760b40d`;
read-only HTTP availability checks returned200. These are sampled checks, not
continuous uptime or trading-performance proof. Other agents' dirty work is
preserved, including their three system-document slices and root ignore file.

## Source and evidence history

- `71fa7df`:48-genome source/config/data/selection/pass-rule freeze, pushed
  before screen scoring;12 families, four balanced genomes each, eight nulls,
  three controls,177 original replays. User's broad-search authorization is
  the explicit exception to the usual two-candidate rule.
- `36218eb`: independent nested same-direction credit/neutral expression
  source freeze before prices. Original15-structure scope consists of six
  parent debit/inverse-credit verticals and nine extension structures.
- `582ab63`: independent calendar plan/freeze. Initial launch failed on a
  wrong book-cache field before scoring. `2cf17d9` fixes that construction and
  adds all59-book/cache-isolation regression; `a832f56` commits its matching
  regenerated freeze. An intervening launch guard refused the uncommitted
  receipt; zero corrected replays occurred before the matching freeze.
- `0d617df`: all six reproduced main/TPB control files and222 complete records
  sealed before expression pricing; every control matches the prior verified
  study trade for trade. Same key with altered economics refuses evaluation.
- `60c27eb`: corrected screen, exact three-proposal selection and reconciled
  evidence pushed BEFORE child replays. GAP_REPAIR g0 LONG, EMA_CROSS g1 SHORT,
  CLOCK_MOMO g3 SHORT. Selection uses2024+2025 only, no altered thresholds.
- Final results/report: **0f139ba**, pushed. This following documentation
  handoff records that identity; its own SHA is in Git history. Source freezes
  remain unchanged. Result-schema correction is reporting only; originals remain intact.

## Completed execution

Use `python-engine/winvenv/Scripts/python.exe` (Python3.11.9), not the Windows
Store stub. All replay processes deny network and use sealed Dev archives.
Set ONLY `O30F_YEAR=2024` or `O30C_YEAR=2025/2026` for a given process.

```text
python -m pytest docs/research/simulation/2026-10-31-fno-broad-search/test_broad.py docs/research/simulation/2026-10-31-fno-broad-search/expressions/test_expression.py docs/research/simulation/2026-10-31-fno-broad-search/calendar/test_calendar.py docs/research/simulation/2026-10-31-fno-conditional-followup/test_follow.py docs/research/simulation/2026-10-31-fno-complements/test_gap.py -q
# 78 passed,39.93s
python -m pytest docs/research/fno/2026-10-31-weak-spots/test_lab_w.py python-engine/tests/test_fno_book.py python-engine/tests/test_fno_policy_replay.py -q
# 49 passed,22.44s
python -m pytest docs/research/simulation/2026-10-31-fno-broad-search/diagnostics/test_result_schema.py -q
# 11 passed,0.26s after final assertion; total138 focused checks
python scripts/build_system_code_atlas.py
# 291 application modules; no atlas diff
```

The first combined-test command had a filename typo and collected no tests;
the corrected command above passed. No full-engine-suite claim is made.

Long runs used existing `docs/research/fno/run_slice.py`,550-second bounded
slices, resume by atomic completed replay files. Main screen used three workers;
one separate corrected-calendar worker ran while the main screen was active,
then three corrected workers after it finished. Recorded free RAM stayed above
5GiB and Production responded normally. Scripts do not control live services.
Planned slice timeouts have `finished:false,returncode:1`; they are retained,
not relabeled successful child runs. Every final phase completed returncode0.

```text
python docs/research/fno/run_slice.py --seconds 550 --env O30F_YEAR=2024 --log docs/research/simulation/2026-10-31-fno-broad-search/_local/run-screen-2024.log -- docs/research/simulation/2026-10-31-fno-broad-search/lab_broad.py run --jobs 3 --phase screen
# repeat with O30C_YEAR=2025/2026, resuming until DONE59 for each year
python docs/research/simulation/2026-10-31-fno-broad-search/analyze_broad.py screen
# original177-replay screen;15 invalid special-session arms preserved
python docs/research/fno/run_slice.py --seconds 550 --env O30F_YEAR=2024 --log docs/research/simulation/2026-10-31-fno-broad-search/calendar/_local/run-screen-2024.log -- docs/research/simulation/2026-10-31-fno-broad-search/calendar/calendar_lab.py run --jobs 3 --phase screen
# all59 2024 arms rerun; initial one-worker slice preserved
python docs/research/simulation/2026-10-31-fno-broad-search/calendar/analyze_calendar.py screen
# zero invalid; same3 selected; selection committed60c27eb
python docs/research/fno/run_slice.py --seconds 550 --env O30F_YEAR=2024 --log docs/research/simulation/2026-10-31-fno-broad-search/calendar/_local/run-selected-2024.log -- docs/research/simulation/2026-10-31-fno-broad-search/calendar/calendar_lab.py run --jobs 3 --phase selected
# O30C_YEAR=2025/2026 next;6 books/year,94/94/78s; all returncode0
python docs/research/simulation/2026-10-31-fno-broad-search/calendar/analyze_calendar.py selected
# passing=[]; correctness issues={}
```

Canonical screen reuses118 original2025/26 files, since the date-specific
override cannot execute on any of those dates. Every reused file is hashed;
ordinary raw records and all main/TPB controls are identical after the repair.
Calendar source/plan froze before corrected prices were scored. Cutoffs12:00
and12:25 on the two12:30-close dates are explicit research-clock assumptions.
No invented quote during the90-minute break; missing exits would remain unknown.

```text
python docs/research/simulation/2026-10-31-fno-broad-search/spread_pairs.py
# 36 cells;222 original single-leg quote/fee parity;2,664 paired rows
python docs/research/simulation/2026-10-31-fno-broad-search/expressions/expression_lab.py run
# 54 cells;222 exact parent identities;3,996 bound rows; no leads
python docs/research/simulation/2026-10-31-fno-broad-search/expressions/verify_rows.py
# original2,664 rows rebound/repriced;6,660 total expression rows;
# zero economics mismatches/financial identity failures
python docs/research/simulation/2026-10-31-fno-broad-search/diagnostics/diagnose_failures.py run
# one process/year;47/110/65=222 causal-input mutation checks
python docs/research/simulation/2026-10-31-fno-broad-search/diagnostics/diagnose_failures.py report
# every feature/member/side partition reconciles; descriptive only
python docs/research/simulation/2026-10-31-fno-broad-search/diagnostics/verify_study.py inputs
# one process/year;248/248/203=699 raw/cache sessions identical;
# every frozen source/data/daily/memo/settings binding matches
python docs/research/simulation/2026-10-31-fno-broad-search/diagnostics/verify_study.py ledgers
# 254 files,39,085 records:39,070 closed,15 original unresolved,
# zero corrected unresolved; max net error0.00004999709 rupees;
# no clock/financial/memo errors; nested source/reused hashes match
python docs/research/simulation/2026-10-31-fno-broad-search/diagnostics/normalize_results.py
# strict v2:48 parent+3 child check strings converted;
# numeric statistical contracts checked, all other metrics/verdicts identical
python docs/research/simulation/2026-10-31-fno-broad-search/diagnostics/write_report.py
# complete README and all48-trial ledger from canonical v2 outputs
```

The frozen analyzer's NumPy boolean/default=str serialization defect did not
change in-memory rejection decisions, but its text `"False"` could be truthy
for downstream readers. Original raw-schema outputs and source remain intact;
canonical reports use `calendar/screen-results-v2.json` and
`calendar/selected-results-v2.json`. `RESULT_SCHEMA_PLAN.md`,11 regression
checks and `result-schema-crosschecks.json` document this strict reporting
repair. No strategy source, price, metric, selection or pass threshold changed.

## Evidence and practical limits

`crosschecks.json`, `input-crosschecks.json`, `expression-crosschecks.json`,
`result-schema-crosschecks.json` and original/final outputs are public derived
receipts. Private logs, raw prices/trades, cache comparisons and bound pairs
remain under ignored `_local/`. The39k+ replay records and6,660 expression rows
share699 actual archived sessions and222 expression-parent trades; they are not
independent samples. Every result remains unqualified research.

Original/source data are actual NIFTY futures/options archives with modeled
bid/ask, normalized lot65, current fee schedule, missing depth/known gaps,
56 negative-volume bars in the sealed2025 subset, and unknown regimes where
unrecorded. No new ICICI calls, daily quota use, login or download. No2023
option exam scored or frozen candidate list changed. Existing pre-2024 daily/
futures warmup is not represented as entirely absent prior-year information.
Annual fresh250k books are not compounded wealth or a15k-account simulation.
Reported falls use closed-trade cash, excluding intratrade marks.

The final helper packet under `_local/evidence-report/` is post-run consistency
packaging, created after the final handoff commit. It must be initialized,
sealed, reported and verified at one unchanged Git SHA. It is NOT a retrospective
pre-registration: the actual pre-run contracts are the commits above. Independent
books are separate receipts; no whole-system/portfolio total is inferred.

Remaining concrete work and unsupported data domains are in README.md and the
top system-plan handoff. Rollback is to stop research workers and retain all
results; this study has no application/deployment/migration rollback action.
