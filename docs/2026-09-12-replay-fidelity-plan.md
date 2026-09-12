# C implementation slice — archive conflicts and full-policy held-out evidence

ID / title:
C1+C6+C7 — unmocked multi-session full-policy replay, conflicting receipt rejection, and review integration.

Problem and user-visible impact:
The archive adapter currently selects the first valid packet for each leg at a receipt timestamp. Two different, individually valid packets can therefore be reduced to whichever appears first, making replay order-dependent. The existing held-out tests also construct low-level replay objects directly; they do not prove that outputs from the deployed full-policy evaluator and immutable archive adapter reach the review layer across sessions.

Current authoritative evidence:
Dev starts this slice clean at `3035957`, seven commits ahead of its remote. A/B and the scheduler warning correction are TESTED_DEV. `build_spread_observations` uses `next(...)` per leg inside a same-receipt batch and exposes only partial batches. `replay_full_policy` retains partial evidence but has no explicit conflicting-batch reason. `build_heldout_comparison` accepts chronological cases, while no adapter binds full-policy replay reports to held-out cases. Production remains read-only.

Files and contracts affected:
`intraday_spread_archive_adapter.py`, `partner_full_policy_replay.py`, `intraday_spread_holdout.py`, their focused tests, a reusable multi-session fixture, and the guide/atlas/plan/checklist. No operational ledger, order, broker, Telegram, cash or position contract is in scope.

Implementation steps and dependencies:
1. Deduplicate byte-identical same-leg packets, but classify multiple distinct valid packets for one leg and receipt as a conflict. Never select one by iteration order.
2. Preserve conflicts separately from partial batches and return an explicit decision-book-conflict diagnostic when a conflict is the newest relevant decision evidence.
3. Add a strict adapter from full-policy replay reports to held-out cases. It must require a verified report fingerprint, accepted deployed-policy manifest, full replay payload, immutable opportunity/signal identities, and supported CLOSED/NO_FILL/UNRESOLVED states.
4. Add an unmocked two-session archive fixture using the real evaluator, master verification, raw-packet verification, adapter, chronological replay and held-out aggregation. One session must produce a costed close and the other an accepted but unresolved entry.
5. Prove input-order independence, source tamper rejection, identical-observation cost stress, policy/profile isolation and immutable output behavior already covered by adjacent tests remains intact.

Acceptance / negative / restart / timing tests:
Focused tests must reject conflicting same-receipt books regardless of packet order, allow exact duplicate retries, surface conflicts in the full-policy report, and generate a held-out report from two unmocked archived sessions containing one finite costed close and one unresolved outcome. Rehashed report/manifest mutations and simplified evaluator manifests must fail. Rerun the complete research/replay/review group with warnings treated as errors where possible.

Data and configuration migration:
The archive build result gains an additive conflict collection with an empty default. Existing quote/master/capture bytes are not rewritten. No database or configuration migration is required.

Rollout and rollback:
Commit only in Dev. Rollback is the reviewed implementation commit; retained archives remain compatible because the change affects interpretation, not storage. Promotion and live collection observation remain under Workstream D and require the GitHub release path.

Status and verified commit:
TESTED_DEV; implementation commit pending. The changed archive/full-policy/holdout acceptance is 28 passed without warnings. The broader replay, qualification, capture, CLI, archive and orchestrator group is 139 passed with one pre-existing Starlette async-generator lifespan deprecation warning. The full Python repository is 2,502 passed, 3 skipped and the same 17 documented out-of-slice failures, with no new failure. Treating every warning as an error confirms the pure research paths are clean and intentionally stops the orchestrator group at that known application-import warning.

Documentation updated:
This plan slice was created before source edits. The system guide, code atlas, next-agent matrix and handover verification are reconciled with the tested behavior for the implementation commit.

Unresolved limits and exact next action:
This slice does not prove public-source scope, all delayed cancellation/partial-fill boundaries, expiry-roll correctness, adequate held-out sample size, profitability or deployment. After this slice, continue C with immutable cost-sensitivity and ordered-drawdown evidence for qualification review, then proceed to release acceptance.
