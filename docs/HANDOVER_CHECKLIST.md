# Handover receipt and operator checklist

## Read order

1. [SYSTEM_GUIDE.md](SYSTEM_GUIDE.md): feature architecture, authority boundaries, before/after improvements and limitations.
2. [SYSTEM_CODE_ATLAS.md](SYSTEM_CODE_ATLAS.md): 155 top-level engine/agent Python modules plus gateway/dashboard source navigation, declarations, dependencies and tables.
3. [NEXT_AGENT_PLAN.md](NEXT_AGENT_PLAN.md): implementation workstreams, acceptance checks, expected effects and documentation ritual.
4. [September 12 replay progress](2026-09-12-full-policy-replay-progress.md) and [Production inventory/CAS findings](2026-09-12-production-evidence-and-cas-findings.md).

## What is being handed over

Dev branch: `codex/production-correction-hedge-p0`. This handover adds the final prior-book replay correction and documentation in one new commit; existing commits are preserved, not squashed. Identify the handover commit with `git log -1 --oneline` immediately after it is created, or search the log for `finalize replay and comprehensive system handover` later.

| Commit | Increment |
|---|---|
| `5a565df` | Full-policy inputs, capture and public-thesis replay foundations |
| `e043276` | Archived evidence validation and immutable diagnostics |
| `e4661d7` | Full-policy connector, independent lifecycle and execution risk limits |
| `0b13ed5` | Verified public capture loading |
| `d99ddd9` | Offline full-policy CLI and immutable report output |
| `273fdd4` | Candidate input preservation and capture isolation |
| `3f627cc` | Causal advisory clocks, durable collection coverage and scheduler warning correction |
| `e548d24` | Full-policy held-out integration and conflicting quote rejection |
| Final handover commit | Fresh prior-book support, regressions, system guide/atlas/plan and AGENTS ritual |

These are Dev changes. This handover does not push, merge, rebuild or deploy them. No partner message or broker order was sent. Production files were not edited. Check remote tracking before pushing: earlier conversational assumptions about remote state may be stale.

## Validation performed for this wrap-up

Final combined rerun: **171 Python tests passed, with the two warnings described below**. Dashboard **23 tests passed**, production build passed, changed Python/generator compilation passed, documentation links resolved, atlas regenerated and diff whitespace checks passed. These are scoped engineering checks, not a Production green light.

131 Python tests passed in the combined research/orchestrator set. Reproduce from Dev `python-engine`:

```powershell
.\winvenv\Scripts\python.exe -m pytest tests/test_partner_full_policy_replay.py tests/test_partner_qualification.py tests/test_partner_qualification_review.py tests/test_partner_research_capture.py tests/test_research_cli_qualification.py tests/test_intraday_spread_signal_artifact.py tests/test_intraday_spread_research.py tests/test_intraday_spread_replay.py tests/test_intraday_spread_holdout.py tests/test_intraday_spread_chronological.py tests/test_intraday_spread_archive_adapter.py tests/test_partner_orchestrator.py -q
```

Dashboard: 23 tests passed with `npm run test:unit`; `npm run build` passed from `node-gateway/client`. Existing warnings: Starlette async-generator lifespan deprecation in Python and an outdated Browserslist database during the build. No dependency updates were made to remove these warnings.

Additional scheduling/isolation suite: 40 tests passed after correcting an outdated test fixture to call the real ledger migration and using explicit UTF-8 source reads. Production accounting code was not changed for these test fixes. Command: `python -m pytest tests/test_scheduler_real_path_isolation.py tests/test_scheduler_telemetry.py tests/test_scheduler_closures_invoke.py tests/test_fno_isolation.py tests/test_paper_ledger_isolation.py -q` in the same environment. This run also emits an unawaited-coroutine warning from the scheduler-closure test path at scheduler_setup.py:594; investigate the fixture/runtime distinction before claiming warning-free scheduler acceptance.

This is not a rerun of the entire repository test suite, gateway/native database suite, broker integration or a live session. Gateway/agent code was not modified by this wrap-up. Full release acceptance remains a task before Production promotion. A successful offline replay test does not prove historical sample sufficiency or profit.

## Current outstanding limits

- Production public input archives were absent at the last read-only inventory; no complete real session replay was produced from that root.
- Dev now implements `FROZEN_COMPLETED_BAR_CUTOFF_V1`: tick/cutoff, public and chain request/receipt, construction and dispatch boundaries are distinct. It is not deployed or observed in Production.
- Dev now retains per-attempt public/candidate outcomes, requested/received chain tokens and conditional-protection inputs, and bounds advisory wait on archive writes. Timeout remains outcome-unknown because an in-flight worker thread cannot be killed; Production latency and retention still need observation.
- Public capture hashes prove supplied-file integrity, not uninterrupted sampling or independent authenticity.
- Full-policy outcomes now enter held-out aggregation only through a verified deployed-evaluator report and manifest. Cost calibration, contemporary entry-quality checks, ordered drawdown/cost-stress review evidence and adequate real-session coverage remain unfinished.
- CAS/session-phase correctness needs official-source-backed review across engine, gateway and research.
- Negative earlier performance and accounting discrepancies need forensic/reconciliation work.
- No actionable partner strategy was qualified by this work. No fixed tip-start date can be given.

## First next action

Review the A/B and C implementation diffs and their acceptance records, then finish Workstream C's immutable cost-sensitivity and ordered-drawdown evidence path into qualification review. Before promotion, resolve or explicitly baseline the broader repository failures and run the release suite. Preserve the working CLI and immutable v1/v2 artifacts.

## A/B implementation verification

- Focused Python acceptance: 185 tests passed across decision clocks, collection attempts, chain/scanner, captures, qualification/replay, orchestrator, archive readiness and authenticated hedge routes. The 64 pure-path tests passed with all warnings treated as errors; the integration group retains one pre-existing Starlette lifespan deprecation warning.
- Scheduler/isolation acceptance: 41 tests passed with `RuntimeWarning` treated as an error. The previously documented unawaited `_run_penny_edge_scan_safe` coroutine warning is fixed; registration now checks for a running event loop before constructing the coroutine.
- Dashboard: 25 unit tests passed and the Vite production build passed. The existing outdated Browserslist database warning remains.
- Gateway: all 317 tests passed (4 skipped) in a clean Node 20 Alpine container; the focused updated proxy contract passed 15 tests. Existing forced-exit/open-handle and Telegram-library warnings remain. Agent: 91 tests passed in the existing Production agent image with networking disabled.
- Latest full Python repository rerun after the C slice: 2,502 passed, 3 skipped and the same 17 failures, with 23 deprecation warnings and no unawaited-coroutine warning. The failures were outside the changed path: legacy test-created `bankroll_ledger` schemas omit `origin_ref`; the declared `PARTNER_BOT_ENABLED` default is already `True` while an older test expects `False`; several Windows source-inspection tests use CP1252 instead of UTF-8; and affected momentum-paper assertions cascade from the legacy ledger fixture. The 17 failures still prevent `RELEASE_VALIDATED` status even though the focused slices are green.
- Production remained read-only. No container was started, no message/order was sent, and no qualification was registered.

## C replay-fidelity verification

- The unmocked two-session fixture uses the real deployed evaluator, verified raw/canonical contract master, hashed raw quote packets, archive adapter, chronological replay and held-out aggregator. It produces one finite costed close and one unresolved accepted entry; neither result can grant qualification, delivery or order authority.
- Distinct valid same-leg packets at one receipt are now explicit conflicts independent of input order. Exact duplicate retries remain idempotent, and a relevant conflict produces `decision_book_conflict` rather than a conveniently selected book.
- Verified full-policy reports can enter held-out review through a strict adapter. Report/manifest tampering, simplified evaluators, conflicting states and malformed identities are rejected.
- Changed C acceptance: 28 tests passed warning-free. The broader full-policy/research/qualification/archive/orchestrator group passed 139 tests with one pre-existing Starlette async-generator lifespan deprecation warning.

## User-facing clarity

The system is better at preserving and testing what it actually observed and proposed. It is less likely to manufacture a historical fill or hide a missing exit in research. Those are prerequisites for finding a real edge, not proof that an edge has been found. The partner's saved intraday profile is a setup input, while qualification and Telegram delivery are separate checks.

## Commit ritual

Before the next implementation: update the plan slice. With each commit: update the guide/atlas/plan and verification evidence. After each commit: verify the actual diff and documentation agree. Instructions are also in Dev AGENTS.md so the ritual survives this conversation.
