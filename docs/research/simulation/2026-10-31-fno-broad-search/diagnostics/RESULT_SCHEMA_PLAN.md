# Post-run reporting-contract correction

Problem: the frozen analyzer computes max-t p-values with NumPy scalars.
Its generic default=str JSON writer serializes NumPy boolean check values as
"False"/"True" strings. In-memory all(checks.values()) used the correct boolean
and the failure verdicts are unchanged, but downstream truthiness is unsafe.
The frozen pre-run sources and original output files must remain intact.

Files/contracts: normalize_results.py, focused test_result_schema.py and new
calendar/screen-results-v2.json / selected-results-v2.json, plus report renderer.
Only known check booleans are normalized; statistical check values are verified
again from numeric p/t fields. Assert every qualification verdict remains the
same, reject ambiguous strings or inconsistent evidence, and seal original
and normalized hashes in result-schema-crosschecks.json. No selection change,
new strategy score, source re-freeze, runtime fix or performance retuning.

Acceptance: regression with real NumPy-to-JSON string reproducer, strict scalar
conversion/rejection, numeric-contract checks, identical non-check metrics and
unchanged verdicts. Reports consume v2; originals remain visible. Rollback by
using the original explicitly flawed reporting schema; no Production or
application/config/migration/deployment impact. Update guide/active plan and
handover with the correction and tests before committing final results.
