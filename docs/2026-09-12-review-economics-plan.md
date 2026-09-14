# C implementation slice — immutable stress economics and ordered drawdown

ID / title:
C3+C7 — bind same-observation cost stress and ordered held-out economics into qualification review.

Problem and user-visible impact:
The chronological engine can calculate cost scenarios, but full-policy reports do not retain them and the qualification-review package deliberately reports `REQUIRES_ORDERED_OUTCOMES`. Consequently its declared stressed fee/slippage and drawdown criteria are validated syntactically but never evaluated. A package can appear ready for human review without proving those economic gates.

Current authoritative evidence:
Dev starts clean at `6eaf676`, nine commits ahead of its remote. `replay_cost_scenarios` is deterministic and reuses observations, but `replay_full_policy` does not call it. `HeldOutCase` carries a replay and identities only. Held-out groups aggregate net P&L without immutable close ordering. `build_qualification_review_package` always emits `REQUIRES_ORDERED_OUTCOMES` and does not consume the criteria's stressed fee/slippage fields. Production remains read-only.

Files and contracts affected:
`partner_full_policy_replay.py`, `intraday_spread_holdout.py`, `partner_qualification_review.py`, `research_cli.py`, focused tests and handover documentation. All outputs remain diagnostic with no qualification, message or order authority.

Implementation steps and dependencies:
1. Generate a fingerprinted cost-sensitivity artifact inside each accepted full-policy replay from the exact chronological option/public observations and final frozen execution policy. Baseline plus caller-declared fee/slippage stresses are explicit.
2. Let the CLI accept stress arrays as research-policy metadata, remove them before constructing `ChronologicalPolicy`, and preserve them in the immutable report.
3. Verify and bind each cost artifact when adapting a full-policy report to a held-out case. Reject tampering or scope/policy mismatch.
4. Make held-out aggregation deterministic by sorting outcomes by genuine entry/exit clocks and stable identity. Retain each outcome, compute baseline sequential drawdown, and retain per-opportunity stress scenarios/evidence IDs.
5. Freeze policy/profile-bound criteria, exact stress coordinates and declared coverage in an immutable manifest dated before the first holdout session. Bind that identity into the held-out report and final review package.
6. Evaluate the predeclared exact stress point and maximum realised-equity drawdown in qualification review. Retain/revalidate complete nested cost artifacts and source report/manifest identities; missing, duplicated, mismatched, nonfinite or state-changing stressed economics remain blockers. Never auto-promote.

Acceptance / negative / restart / timing tests:
Prove baseline and stress scenarios share the same observation evidence, a baseline is retained even for stress-only input, booleans/duplicate coordinates fail, caller ordering cannot alter close-ordered drawdown, a loss sequence breaches the declared drawdown limit, missing or state-changing stress is a blocker, the exact declared stress is required, legacy reports remain readable but blocked, nested/source tampering fails, criteria precede and exactly bind holdout scope, CLI arrays are parsed without changing the execution-policy schema, and packages remain unable to send advice/place orders. Rerun the full C/research group and repository regression comparison.

Data and configuration migration:
Reports and held-out groups gain additive fields. Existing immutable reports remain readable but cannot satisfy the new economic gates because their stress/criteria provenance is missing. Criteria use the stable frozen policy/profile digest rather than a session-specific decision-manifest digest. No database/configuration migration is required.

Rollout and rollback:
Dev commit only. Revert the implementation commit to roll back interpretation; never rewrite stored reports. Promotion and live observation remain Workstream D.

Status and verified commit:
TESTED_DEV in implementation commit `760c086`. After two independent read-only reviews and their corrections, the focused full-policy/holdout/review/CLI/chronology suite passes 61 tests warning-free. The broader C research/orchestrator group passes 151 tests with one pre-existing Starlette lifespan deprecation warning. The final full Python repository comparison is 2,514 passed, 3 skipped and the same 17 documented out-of-slice failures with 23 warnings; no new failure was introduced.

Documentation updated:
This slice was recorded before source edits. Guide, atlas, matrix and checklist are reconciled with the tested behavior for the implementation commit.

Unresolved limits and exact next action:
This does not calibrate real brokerage/slippage, prove archive completeness, produce adequate independent samples or qualify a strategy. Afterward finish remaining C source/expiry and delayed/partial execution acceptance, then address the release baseline in D.
