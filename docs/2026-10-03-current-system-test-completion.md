# October 3 current-system testing completion receipt

Authorized task: test current Dev F&O for September 17–October 1 and the other
modules for Q3, then discuss improvements. Baseline `556209c`. Results are in
[the comprehensive assessment](2026-10-03-current-system-backtest-results.md)
and [machine summary](research/2026-10-03-current-system/summary.json).

## Verification commands and results

- `python-engine/winvenv/Scripts/python.exe scripts/run_current_system_review.py
  collect` collected read-only retained Production data through the documented
  stopped-container fallback. `archives`, `coverage`, each frozen `job --job ...`
  and `fno`/`fno --post-entry` produced preserved reports/receipts. Full command
  design and deviations are in the pre-execution plan.
- `python-engine/winvenv/Scripts/python.exe -m pytest
  scripts/tests/test_current_system_review.py
  python-engine/tests/test_penny_edge_connection_cleanup.py
  python-engine/tests/test_backtest_lab.py -q`: **28 passed**, one existing
  HTTPX `app` deprecation. These are software checks, not profitability tests.
- `python-engine/winvenv/Scripts/python.exe -m py_compile` on the orchestration,
  collector tests, corrected EDGE scanner and cleanup tests: passed.
- `python-engine/winvenv/Scripts/python.exe scripts/build_system_code_atlas.py`:
  **240 modules** indexed; deterministic regeneration checked.
- `git -c core.safecrlf=false diff --check`: passed.
- [Integrity receipt](research/2026-10-03-current-system/verification.json): all
  **19** report/receipt hashes and metrics agree; **11** delivered source/settings
  manifests match; **7** original/final outcomes agree; frozen snapshot,
  collection, evidence DB, stopped copy and **19** quote files hash-verified.
  Raw-to-compact counts reconcile for all three signal tables. Both actual Penny
  cash streams also agree under independent UTC normalization.
- Final read-only Production HEAD `044c016584118fd5c5b515fc6d03909dbcaa8c4b`;
  `docker inspect --format '{{.State.Running}}' python-engine` returned **false**.
  Its pre-existing untracked audits/migration directory were left untouched.

## Environment, changes and remaining work

Windows retained stopped-container data was used because a live `docker exec`
collector could not run. The initial empty collector and legacy-BLOB serialization
failure are preserved locally. EDGE's first replay failed temporary SQLite
cleanup on Windows; explicit connection closure fixes it without changing any
numeric policy. All original runs were preserved and completed primaries rerun
against current transitive manifests. No data imputation or gate relaxation.

All requested modules have a scoped outcome or explicit unavailable/excluded
contract. F&O recorded cash is not a fresh backtest; missing quote paths/leg
identities prevent exit scoring. Penny's complete minute coverage is only 2.91%;
its gap studies preserve unresolved exposure. Momentum's later-day exit fallback
prevents live MIS attribution; Swing lacks index warm-up. EDGE/Range do not have
full trade lifecycles. The partial Penny ledger's mixed-offset clock ordering
needs a later correction, although normalizing the actual streams changes none
of this study's cash metrics. Complete historical portfolio fidelity, executable
F&O inputs, operational acceptance and prospective qualification remain open.

No schema or runtime configuration impact. No thresholds, entries, exits,
sizing, budgets or provider/broker paths changed. Dev only: no Production edit,
restart, orders, push, deployment or strategy qualification.

Source/research commit **`4929bea40dc5347c0d0575c55e2c65daad227939`** is Dev-local.
Immediately after commit, guide/plan/checklist/results references and status
agreed, atlas regeneration was byte-identical, ignored raw evidence was not
tracked, and `git status --short` was empty. This receipt update is documentation
only; no source changes followed the study or those checks. Its documentation
commit also requires immediate consistency and clean-worktree verification.
