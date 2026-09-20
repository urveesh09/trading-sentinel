# Release PR handoff — 2026-09-20

## Suggested PR

**Title:** `feat: promote partner advisory, Workflow C correctness and release hardening`

- Base: `evolve/smart-strategies`
- Head: `codex/production-correction-hedge-p0`
- Resolved base SHA: `fef35e7880fab615741346615e608592350c1a07`
- Reviewed source head: `2766b000ce09bf3ae3a5ac4ed83d55d892b56e11`
- Reviewed range: `fef35e7880fab615741346615e608592350c1a07..2766b000ce09bf3ae3a5ac4ed83d55d892b56e11`
- Reviewed commits ahead: 32

This document is a final documentation-only commit after the reviewed source
head. Before opening the PR, regenerate the exact range so the displayed head
and count also include this handoff commit:

```powershell
git fetch origin
python scripts/build_release_notes.py `
  --repo . `
  --base-ref origin/evolve/smart-strategies `
  --out "$env:TEMP\sentinel-release-notes.md"
git rev-list --count origin/evolve/smart-strategies..HEAD
```

The generator now fails closed if the base does not resolve and records both
requested and immutable SHA ranges. Do not substitute a latest-30 log.

## Human summary

This release completes the bounded Dev portions of the partner-advisory and
Workflow C plan while preserving delivery and execution safety. It adds
operator diagnostics, auditable partner cards, liquidity-aware sizing,
session/capture completeness controls, held-out partial-fill evidence,
source-bound AI classifications, causal strategy comparison, broker-fill
reconciliation, and release-range integrity.

Safe optional-AI and manual-advisory features are explicitly enabled in the
deployment definition. Advanced personalized hedge Phase 2/3 remains shadow
only: the parent and shadow evaluation paths are enabled, but live delivery is
disabled. A staging day is recorded only after a genuine reconciled position
is processed with fresh option-chain context. No threshold was lowered, no
historical day is backfilled, and no live order or partner message is emitted
by this change.

## Important behavior corrections

- Partner readiness reads the actual persisted schemas and no longer treats
  advanced hedge `0/7` as a blocker for ordinary manual index advice.
- Partial-fill held-out review is bound to source quotes and modeled partials;
  synthetic/self-referential evidence cannot silently qualify.
- Range-strategy comparison is causal, preventing future information from
  contaminating evaluation.
- Optional-AI usefulness and news classifications are schema-bounded and tied
  to classified source evidence.
- Broker fills can be reconciled to internal references without mutating books
  to force agreement.
- Broker-statement text output is Windows-console safe (`INR` rather than an
  unencodable rupee glyph); amounts and reconciliation semantics are unchanged.
- Release notes now enumerate the exact immutable `base..HEAD` range and fail
  closed on an invalid/uninspectable base.

## Verification receipt

- Python engine: 4,122 passed, 4 skipped; 46 existing deprecation warnings.
- Agent image, offline: 357 passed.
- Corrected partner-readiness diagnostic: 27 passed with warnings fatal.
- Focused hedge/readiness suite: 59 passed.
- Release-note exact-range suite: 31 passed with warnings fatal, including a
  31-post-base boundary and a valid empty range.
- Complete scripts suite: 225 passed with warnings fatal.
- Dev `agent` and `python-engine` images built successfully; one existing
  Dockerfile casing warning remains.
- Release audit snapshot at source head: 80 discovered tables, 10 migration
  steps, 474 audited defaults, 13 defaults classified `RISKY` for operator
  review.

These receipts establish Dev regression fitness. They do not establish
deployment, partner qualification, live-market reachability or profitability.

## Configuration and migration impact

The deployment definition intentionally enables:

- MiniMax asynchronous review with safe proceed/advisory policy.
- News classification and optional-AI usefulness reporting.
- Manual partner advice.
- The advanced hedge parent and Phase 2/3 shadow paths.

Advanced hedge Phase 2/3 live delivery remains disabled. Credentials and
partner chat identifiers must still exist in the target environment; values
must never be placed in the PR body or logs.

No destructive migration is introduced. The release audit found the existing
lazy/idempotent schema surface described above. Operators must review all 13
`RISKY` defaults and follow the consistent backup/restore runbook before
promotion; static audit is not a restore proof.

## Rollout

1. Review this full range and all `RISKY` defaults; approve through GitHub.
2. Establish authorized quiescence and take a consistent backup of the actual
   Production data volume. Prove an isolated restore before migration/restart.
3. Promote through GitHub only. Never copy files into or edit the Production
   working copy directly.
4. Recreate affected application services and verify the deployed SHA and
   effective configuration, then check health/logs for at least ten minutes.
5. Log in for an intended market session. Verify optional-AI status, partner
   input state, manual advisory qualification and transport receipts.
6. For advanced personalized hedging, provide a real reconciled position and
   fresh chain, then observe one idempotent staging receipt for that IST date.
   Complete seven genuine qualifying days plus manual live-chain and per-kind
   sample review before considering live delivery.

## Rollback

Rollback is the prior GitHub release plus the proven pre-deploy data backup.
Do not use ad-hoc file copies, delete data, or infer schema compatibility from
unit tests. If release identity, migration, health or configuration checks fail,
keep partner delivery and live hedge phases disabled, stop the rollout, retain
logs/receipts and execute the documented restore path.

## Known prerequisites and remaining evidence

- Production application containers were last observed stopped with exit 137,
  `OOMKilled=false`; nginx was restarting. This is not a deploy receipt or an
  authorized maintenance window. Diagnose/restore explicitly during rollout.
- Production had credentials present but safe AI/manual-advisory flags unset;
  this branch corrects the declaration, but only deployment plus runtime
  verification proves effective activation.
- Three manual shadow ideas existed on 2026-09-17, but there was no strategy
  qualification, research artifact, advanced hedge evaluation/gate evidence,
  or reconciled partner position in the inspected Production database.
- The advanced hedge counter is therefore honestly `0/7`; elapsed uptime and
  closed/logged-out days do not count.
- Operator-supplied CAS staging captures, consistent backup/restore proof,
  previous-code schema compatibility, live-market observation and genuine
  held-out/qualification evidence remain outside this Dev-only release.
- Two local generated session-phase fixtures have timestamp-only changes and
  were intentionally not staged. They are not part of this PR range.

## Partner expectation

Code paths required to generate and transport manual advisory tips exist and
are enabled by this release definition, but tips cannot be promised merely by
deployment. After a healthy deploy, login and fresh data, allow roughly 5–10
valid logged-in market sessions (about 1–3 calendar weeks) for honest strategy
qualification and observation. Advanced personalized hedge suggestions have a
separate seven-genuine-session gate plus manual review. Market conditions may
extend either timeline; no code change can guarantee profitable signals.
