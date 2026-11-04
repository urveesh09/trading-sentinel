# Final verification — completed

Final code commit **3c54914194ad2eeeaebcbbb51dac4ff92c01afe1**. Entire engine
suite: **6174 passed,4 skipped,0 failed,53 warnings in713.72s,exit0**.
All ten final source/contract hashes remained unchanged throughout the run.
Full-suite-result.json binds its log and source; existing test-mock shutdown
logging error is retained and explained there. No warnings suppressed.

Focused calendar/source/book/V2/surface:78 passed,1 Starlette deprecation
warning,13.06s. Financial audit:60 primary artifacts reconcile;30 actual-panel
legacy-control closes match. Results hash manifest and each original source/
data freeze verified. Atlas298 modules. Owner doc bytes preserved; Production
tracked diff empty at5e30ce0. No push/deployment/order or dependency change.

The following chronological records preserve intermediate results/failures.

# Verification and release state

- Windows scientific runtime:Python3.11.9 existing winvenv. No dependency
  change. Host Python3.14 lacks aiosqlite; not used for scoring/tests.
- Round1 freeze4d95c71:7 tests passed,24 paired model results.
- Round2 freezea8976d1:9 tests passed,24 paired model results.
- Finalists/older freezea4cf227:source/data/acceptance committed before first
  opening. Twelve older models completed, full ledger preserved. No tuning.
- `audit.py`:60 artifact ledgers reconcile trade notional/fee/net, quantities,
  daily own-cash reservation <=25000 and flat ending equity. Actual-panel
  legacy parity30 closes,zero share/summary differences. Fixed-rule seed and
  correlated-fill stresses preserved, including failures/negative returns.
- Final focused command:winvenv python -m pytest tests/test_overnight_enrichment.py
  tests/test_overnight_execution_evidence.py tests/test_overnight_v2.py
  tests/test_edge_overnight_paper.py tests/test_main_surface_characterization.py -q
  (paths relative to python-engine; actual invocation from root uses that prefix).
  76 passed, 1 pre-existing Starlette warning, 8.74s, exit 0.
- Scheduler golden regeneration deliberate:exactly three new default-off quote
  jobs at15:49/15:51/16:03; no old jobs/routes removed or rescheduled. Rechecked
  without update mode. Initial regeneration2passed/2intentional skips; normal
  mode4passed. Existing Starlette lifespan deprecation warning remains.
- Full engine suite log:_local/full-suite.txt; pending at this writing.
  Initial strict-collector version; later entry-shortlist hook and denominator
  refinements have a focused final rerun, recorded separately.
- Atlas regenerated after declarations; staged diff whitespace check and
  immediate post-commit documentation/plan consistency verification required.

No push/deployment, order, capital change, Production edit, existing-store
migration or reserved-history use. New collector flag defaults false, so no
new scheduled broker quote occurs until deliberately enabled. API reads do
not create stores. Rollback:disable only the new flag; old code stays intact.
Engineering checks establish mechanics, not profitable trading.

Implementation commit:c0f2fc324731f82c00c8141fd6423e3ffd24e56d. Immediate
post-commit source/docs review complete. Frozen source hashes match a4cf227
under original Windows line endings; all3 sealed older files unchanged.
The initial Git-blob-only assertion failed on CRLF representation, not source
logic; repository-check.json preserves the correction. Atlas298 modules, owner
document bytes preserved, Production HEAD5e30ce0 tracked diff empty.

Initial whole suite (before final shortlist/denominator refinements):6171
passed,1 failed(calendar wrapper contract),4 skipped,53 warnings,709.01s.
Failed log retained at_local/full-suite.txt. New wrapper source now exposes
the holiday gate directly, without an exemption or test change. Focused
calendar/source/surface result and final whole rerun recorded below.

Calendar/source/surface correction command:78 passed,1 existing Starlette
warning,13.06s,exit0. No guard test/allowlist was weakened. Final whole-suite
run uses the ten bound files in final-suite-source.json; no source edit is
permitted during that run. Golden changes are exactly three new default-off
quote jobs (15:49/15:51/16:03), preserving all prior jobs and routes.

Final code correction commit3c54914194ad2eeeaebcbbb51dac4ff92c01afe1.
Immediate post-commit docs/plan/atlas review completed by the commit helper.
Read-only independent review confirms the protocol is intentionally strict:
provider timestamps are exchange packet clocks (Kite official quote docs),
so a non-updating post-market packet can remain UNKNOWN; all raw observed
values are preserved. No request timestamp is substituted for exchange time.
Results manifest binds all60 primary full ledgers; per-day dated curves,
trades and intents are retained under_local. Both round source/data hashes
verified against their committed freezes, allowing original Windows line
endings. No source changed during the final entire-suite run.
