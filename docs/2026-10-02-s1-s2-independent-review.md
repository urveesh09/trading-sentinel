# S1/S2 independent Dev review — October 2

## Verdict

Reviewed the six commits `9e26e1b`, `8b7aca2`, `5ae54a8`, `b019855`,
`d2319e2`, `568c68c` against the consolidated plan and regression contracts.
S1's principal implementation meets the exact-contract, selected-lot,
unresolved-unpriced-close and atomic/idempotent settlement contracts tested.
S2 is useful but not complete against its original acceptance scope. Its
documentation had incorrectly classified remaining development as operational
evidence only. Do not use that classification to close S2.

## Small corrections made

- Refresh live management time after held-option/DR reads, not only before
  them; assess hard-flat separately for each directional position.
- Recheck existing session/chain/quote gates at final directional dispatch and
  DR admission after pre-admission DB reads. No broker operation, admission or
  cash mutation is deadline-cancelled. No new trade-quality threshold is added.
- Keep the tick-start completed-bar evaluation cutoff separate from refreshed
  action clocks. Supplied deterministic replay/test clocks retain old behavior.
- Preserve timezone offsets in quote-age evidence; any missing/malformed held
  leg timestamp makes oldest exact-leg age unavailable, not apparently complete.
- Retain management read outcomes, action time and management lag in scheduler
  completion/overrun structured logs; previously these were discarded by the
  wrapper. This does not add fields to the scheduler telemetry database.

Files: `python-engine/fno_orchestrator.py`, `fno_dr_book.py`,
`scheduler_setup.py`, their focused regression tests, all four handover docs,
and the consolidated plan. No schema or deployment configuration change.

## Remaining S2 development — do next as separate reviewed slices

1. **Exact-held-leg DR management reads:** use retained tokens/expiry, not a
   nearest-expiry ATM chain reconstruction; retain the same total read budget.
   Tests must move the forward beyond the retained strike window and change
   nearest expiry while proving exact open legs remain manageable; absent or
   mismatched observations must stay unresolved without invented cash.
2. **Shared-provider priority/fairness:** inspect the limiter/request admission
   boundary and give due management precedence over queued speculative/research
   reads without raising request rate/concurrency. Exit-first ordering inside a
   tick does not prioritize that tick against other jobs. Regression acceptance:
   saturated research cannot consume the entire management budget while lower
   priority work still has bounded fairness; cancellation leaves no orphan retry.
3. **Timing attribution:** distinguish DB wait, DR/provider stages, retry/backoff
   and timeout-path partial timing. Current detailed quote metrics are returned
   only on completed calls; a cancelled call cannot prove which stage consumed
   its budget. Keep unavailable explicit and bounded, without recording secrets.
4. **Recovery/operational acceptance:** verify stale IN_FLIGHT handling against
   the plan, then obtain three complete deployed market sessions for lag, p95/max,
   skips, read deadlines and unresolved exposure. These are not profitability
   evidence or automatic partner authorization.

## Verification and environment

Windows Dev Python: `python-engine/winvenv/Scripts/python.exe`. Tests use
temporary SQLite databases and simulated providers; no broker/network order
dispatch or Production runtime interaction. Before corrections, all 83 affected
tests passed, including the previously deselected exit-recovery regression; its
old grouped failure was not reproduced in this run.

Expanded affected command (run from `python-engine`):

```powershell
.\winvenv\Scripts\python.exe -m pytest tests/test_fno_dr_book.py tests/test_fno_audit_report.py tests/test_fno_orchestrator.py tests/test_fno_audit_phase1_fixes.py tests/test_fno_exit_recovery_boundary.py tests/test_kite_client_methods.py tests/test_scheduler_closures_invoke.py tests/test_scheduler_telemetry.py tests/test_fno_shadow.py -q
```

Result: **139 passed, two known deprecation warnings, no deselections**.
Warnings-fatal focused DR/audit and new clock-boundary checks: **33 passed**
(`-W error`; DR/audit files plus the new orchestrator and exit-boundary tests).
`python -m py_compile` passed for the three changed source modules;
`python scripts/build_system_code_atlas.py` indexed 215 modules; `git diff
--check` passed (normal Windows LF/CRLF notices only). Known unrelated Starlette
lifespan and HTTPX app-shortcut deprecations remain; this is not a claim of a
clean warnings-fatal full suite. Existing golden-fixture edits and untracked
user artifacts are preserved.

## Rollout and status

Corrections remain Dev-local, not pushed or deployed at this review. Production
is untouched and not restarted. Promote/revert the scoped correction through
GitHub; preserve active obligations and retained evidence. No migration,
live-order authority, owner EXEC, AI-default policy, strategy threshold,
provider rate or scheduler cadence changes. Commit identity, if committed,
is recoverable through `git log -- docs/2026-10-02-s1-s2-independent-review.md`.
