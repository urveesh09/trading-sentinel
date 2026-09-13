# C implementation slice — source scope and execution boundaries

ID / title:
C1+C3+C4+C5 — bind the public futures contract/roll context and replay exact deployed execution boundaries.

Problem and user-visible impact:
Retained public bars currently identify an underlying and futures token but do not prove the selected futures symbol, exchange/segment, expiry, dated master or front-contract selection context. Replay also rechecks full-lot depth and capital/risk, but not every deployed spread/liquidity gate after a manual delay; it accepts same-day expiry although candidate construction requires a strictly future expiry, and minute-only comparisons can accept packets after an exact published deadline.

Current authoritative evidence:
Dev is clean at `fa0607f`, eleven commits ahead of its remote. `observe_underlying` selects `book.front_future(today)` from the current listed expiries, but `partner_observed_public_input_v2` retains only `future_token`. The archive adapter preserves top-of-book depth plus OI/volume. `build_directional_debit_spread` rejects `snapshot.expiry <= now.date()` and publishes exact 14:45/15:15 clocks. Base replay currently rejects only `expiry < entry_date`, compares only minute values, and does not reapply maximum leg spread, OI, volume or cost-inclusive expiry reward at the delayed book.

Files and contracts affected:
`fno_instruments.py`, `fno_signal_scan.py`, `partner_research_capture.py`, `intraday_spread_archive_adapter.py`, `intraday_spread_replay.py`, `intraday_spread_chronological.py`, `partner_full_policy_replay.py`, focused tests and handover documentation. Production remains read-only. All artifacts remain diagnostic and have no qualification, delivery or order authority.

Implementation steps and dependencies:
1. Retain the raw dated instrument-master digest on the in-memory/disk book and capture the exact selected futures identity, interval, segment/exchange, selection date, eligible futures expiries, next roll contract and nearest strictly-future option expiry.
2. Introduce a v3 public capture. Validate its structured scope and scope digest on load; expose it through lifecycle sources. Independently prove selected/next futures and the complete eligible expiry selection against the raw/canonical archived master, and bind the actual decision frame/regime/cutoff to a supplied capture. Legacy v1/v2 remains readable but explicitly unscoped and cannot satisfy strict full-policy replay.
3. Require archived public lifecycle inputs used by full-policy replay to match the replay underlying, segment, dated master and selected front-future rule. Bind the scope IDs in the immutable report.
4. Extend archived replay quotes with raw-bound observed OI/volume and reapply the deployed maximum spread, minimum OI/volume/full-lot depth, public-age and cost-inclusive positive expiry-reward checks at the actual delayed entry packet. Charge slippage on gross leg notional; a distressed negative net-credit close cannot create negative costs. Ignore unrelated contracts rather than inventing partial selected-leg batches. Verify finalized quote-segment manifests.
5. Require a strictly future option expiry, compare entry/management boundaries as exact dated IST instants, and cap a delayed public-thesis exit by the declared maximum wait and management deadline. Never manufacture an exact-minute fill; absent, partial or late books remain unresolved.

Acceptance / negative / restart / timing tests:
Prove a scanner capture retains a tamper-evident future/master/roll scope; token/name-only and mismatched master/segment/front selection fail strict replay; legacy captures stay readable but scoped as legacy. Prove delayed entry is cancelled on the eligible fill timestamp, wide/thin/current-quantity/cost-erased packets do not fill, exact-expiry-day entry is rejected, 14:45:00 is the last entry instant, 15:15:00 is the last management instant, 15:15:01 is unresolved, a breach with no/partial/too-late later book is unresolved, and the first timely executable later book is used. Rerun focused C tests, broader research/orchestrator tests and the full Python comparison.

Data and configuration migration:
Public captures gain a v3 additive structured scope. Existing immutable v1/v2 files remain readable and labelled `LEGACY_UNSCOPED`; they are not rewritten and cannot supply strict source proof. Instrument cache JSON gains source-digest/provider/segment metadata; a legacy cache without a raw source digest requires a normal provider refresh rather than fabricating provenance. Replay dataclasses gain optional quote evidence fields and policy gates with backward-compatible permissive defaults; full-policy replay supplies deployed values. Caller-supplied public dictionaries remain diagnostic and cannot produce verified held-out evidence.

Rollout and rollback:
Dev commit only. Revert the implementation commit to restore interpretation; never rewrite retained evidence. Promotion and live-session observation remain Workstream D and require the normal GitHub/release path.

Status:
TESTED_DEV in implementation commit `e1c6687`. The expanded focused source/replay/management group passes 143 tests; the final broad C/research/orchestrator group passes 185 tests with the existing Starlette lifespan warning. Isolated full-policy/multisession warning-fatal acceptance passes 15 tests. Combined warning-fatal runs expose an unclosed Windows asyncio socket at test-group transitions; this remains an explicit D baseline investigation, not a suppressed warning. Both initial read-only audits produced actionable findings that were incorporated; follow-up review attempts failed on account usage limits, so final review was local. Compile, atlas generation and diff checks pass. The source-final repository comparison is 2,526 passed, 3 skipped and the same 17 documented failures, with 23 warnings in 122.40 seconds; the subsequently added decision-frame negative test also passes in the final focused/broad groups. No new failure was introduced. The final XML is retained at `C:/Users/Urveesh/AppData/Local/Temp/sentinel-c-boundaries-20260913-final.xml`.

Unresolved limits and exact next action:
This slice cannot retroactively make legacy captures scoped, prove complete real-session coverage or qualify profitability. It models full-lot executable books, not asymmetric actual fills. Exchange-specific futures settlement/after-close roll assumptions remain J verification work; no new settlement clock was invented. Continue D's repository/gateway/dashboard/agent acceptance and GitHub release preparation, then obtain genuine Production collection and predeclared independent holdout evidence without touching Production directly.
