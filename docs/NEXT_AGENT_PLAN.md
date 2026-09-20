# Trading Sentinel — next-agent execution plan

## September 20 Workflow I.4.D provenance correction (Dev only)

Classification is now bound to the exact feed snapshot shown to the verdict
model. The requested ticker, bounded source URL/name, aware publication clock
and source digest survive in each result; invalid source evidence fails closed
without a model call. HTTP(S)+host validation and a seven-day source-validity
boundary are explicit. Optional-review keys bind the deterministic
classification-context digest when the feature is enabled and preserve the
legacy key when disabled; the queue also rejects context-mismatched cache hits
for direct callers. Typed reviews retain digest/count/structured source
references and actual expiry on available, unavailable and worker-exception
paths. Synchronous late results are discarded as unavailable; cached repeats
can shorten but cannot extend validity. Focused warning-fatal acceptance is
**185 passed**, full isolated agent is **357 passed**, compilation/diff checks
pass, and the atlas remains **203
modules** after regeneration. No schema/config default/authority/trading
behavior changed. Production evidence is still required; I.4.G remains
deferred. See the
[active plan](2026-09-20-i4d-classification-provenance-plan.md).
Implementation commit: **`3495ecb`**; promotion remains GitHub-only.

## September 19 Workflow I usefulness-contract correction (Dev only)

The optional-AI status bridge no longer rejects the real ten-field usefulness
snapshot while accepting only reduced test doubles. Engine validation now
covers all producer fields and their internal counter/rate consistency; the
agent's hourly contract-health check uses the real status shape and actually
runs its leakage/usefulness invariants. The dashboard renders p95 response time
and last completion without converting absent legacy fields to zero. No schema,
flag-default, authority, delivery, risk, capital, strategy, or order behavior
changes. Focused engine is **72 passed** with four known deprecations, full
agent is **340 passed** warning-fatal, and dashboard is **46 passed** plus build.
Whole-engine validation is **4,117 passed/four skipped/46 known deprecations**;
implementation commit `8dd2c41` was consistency-checked and pushed to
`origin/codex/production-correction-hedge-p0`. Real
Production observations and operator-labelled usefulness remain required;
per-ticker I.4.G is still deferred. See the
[active plan](2026-09-19-workflow-i-usefulness-contract-plan.md).
This correction supersedes the historical six-field I.A allow-list wording in
the long-form state table below; the current authoritative contract has ten
fields.

## September 19 Workflow C.C2.SOURCE completion (Dev only)

The remaining causal-pricing defect in the modeled-partial path is corrected:
every modeled leg is bound to its own verified asymmetric quote packet rather
than priced from the earlier decision book. Missing legacy source projections
now return `INSUFFICIENT_EVIDENCE / partial_fill_model_unavailable`, and
held-out admission independently cross-checks source attribution and recomputes
the model. Focused acceptance is **87 passed** with warnings fatal; broader C
coverage is **259 passed**; whole-engine acceptance is **4,070 passed/four
skipped/42 known deprecations**. Genuine retained sessions, adequate predeclared
holdout coverage, human qualification and release/Production observation are
still required. Details are in the
[completed slice](2026-09-19-workflow-c-asymmetric-source-binding-plan.md).
Implementation commit `e2212cb` and verification receipt `1a97932` were pushed
to `origin/codex/production-correction-hedge-p0`. Production is unchanged.

## September 19 Workflow C.C2.HOLDOUT completion (Dev only)

`C.C2.HOLDOUT` closes the modeled-partial review seam. The evaluator now emits
a separately identified `MODELED_PARTIAL_FILL_V1` replay, and held-out/review
outputs split `full_closes` from `modeled_partial_closes`. Adverse mid-plus-2bps
entry slippage is non-positive; a degenerate missing-leg quote fails closed.
Modeled outcomes remain outside `VERIFIED_FULL_POLICY_REPORTS` until honest
cost-stress and archived-public-scope evidence exists. Verification: 90
focused, 134 broader qualification/held-out, 226 Workflow C/research, and
4,069 whole-engine tests passed; four skipped and 42 known deprecations in the
whole run. Details and remaining runtime evidence are in
[the completed slice](2026-09-19-workflow-c-partial-holdout-plan.md).
Production is read-only.

## 1. Mission, scope and non-negotiable user intent

September16 square-off acceptance update: pushed Dev commit `ee0a300` moves live momentum EOD ownership to 15:13 IST with a strict 15:14:30 submission cutoff and one shared monitor/EOD lock. Deadline expiry after protective-stop cancellation re-arms and persists replacement protection when possible and always escalates; no late sell is submitted. Focused momentum/calendar/lifecycle/surface coverage is green (79 passed), the scheduler/calendar regression subset is green (25 passed), agent is green (338 passed), and final Python is3730 passed/four skipped/42 existing deprecation warnings in214.84s. The completed pytest receipt again retained aiosqlite worker processes; the exact processes were stopped. Merge/release observation remains required before Production acceptance. This removes the identified 15:15 CAS collision in Dev source; it does not supply staging CAS evidence, broker execution verification or partner strategy qualification.

September16 current acceptance override: Dev correction `97e62e7` and receipt `93efbe4` are pushed, while Production is merge `967e07a` with source parent `315fa72`. Production containers are healthy, but `trading_ready=false`/order execution UNVERIFIED. The new partner-card path has zero qualifications, research artifacts and ideas; two observed sessions produced no setup. The independent J correction HMAC-binds eligibility, strictly expires/validates calendars, removes operational-coverage SQLite initialization races and makes SUMMARY verification deterministic without changing JSON output. Final validation: Python 3725 passed/four skipped/42 existing deprecation warnings (complete receipt, but lingering aiosqlite workers prevented natural process teardown); runtime-matching native Node 424 passed/four skipped; dashboard 43 passed plus build; agent 338 passed. Until merged/released/observed, historical J/H/DONE labels below are source-history claims, not operational acceptance. A single paper close of+INR2,194.54 is not repeatable/live expectancy.

September14 overriding acceptance status: external F2–F6/H/I/J source is preserved but F/J complete labels below are not independently accepted. [Independent audit](2026-09-14-external-work-independent-audit.md) identifies writer-contract, account/capital and live session defects requiring correction. G/C predeclared protocol correction is Dev-tested in ten-file acceptance:156 passed/no warnings6.84s using winvenv `-q -W error`. Full-run JUnit `sentinel-g-protocol-reviewed-20260914.xml` records3304 cases, zero failures/errors, four skips,173.475s; pytest teardown remains alive at inspection, so clean process exit/warning count is NOT confirmed. Next: reconcile this protocol commit, correct F3/F4/F5 and fail-closed F6, then execution/calendar defects and independent I review. Real heldout inputs, faithful range semantics, operator risk input, F/D evidence and GitHub release/session observation remain open; no full-goal completion or live promotion inferred.

Current September13 verification: F inventory/provenance corrections, cache integrity and immutable approval-budget/validity source pass full Dev engine **2,703 tests/four skips/23 existing deprecations in126.20s**, receipt `sentinel-fg-provenance-baseline-20260913.xml` in user Temp. F historical warning evidence, genuine G/C predeclared comparisons/approval gates, D release/session proof and other matrix residuals remain unfinished. No deployment or qualification inferred.

Improve Sentinel into an active, intelligent, cost-aware trading system for the owner and a timely intraday NIFTY/SENSEX manual-advisory system for the partner. The owner wants substantial profit and proactive discovery with mitigated risk. Treat that as a product objective, not a guarantee or justification to loosen safeguards. The engineering target is positive, repeatable net expectancy demonstrated with appropriate evidence, reliable execution/management, truthful accounting and bounded losses.

Do not spend another sequence of commits solely making evidence machinery safer without getting to operational collection, research comparisons and useful product outcomes. Each work item below must produce an observable result, with an explicit decision about what to do next. Equally, do not skip missing evidence to claim progress toward income.

The final requested handover wraps the current code and documentation; this plan preserves the broader unfinished mission. Read SYSTEM_GUIDE.md, SYSTEM_CODE_ATLAS.md and HANDOVER_CHECKLIST.md before implementation. Then inspect the actual worktree, branch, open PR and Production status. Historical chat and these documents are pointers, not fresh runtime truth.

## 2. User constraints to carry forward

- Owner capital: about INR 8k now; possible staged increases to INR 20–50k, INR 1 lakh, then INR 5 lakh only after confidence. Do not silently change capital or treat added funds as returns.
- Partner: independent manual intraday trader in NIFTY and SENSEX, prioritizing hedging. No overnight recommendation under the current policy.
- General tips do not require their personal strategy or holdings. Personalized protection does require actual exposure; conditional protection needs explicit assumptions.
- The owner accepts some risk and wants frequent proactive scanning. A trade quota is not a substitute for an edge.
- AI may help; deterministic operation must continue without it. No AI risk override or fabricated qualification.
- Changes belong in Dev. Promotion is through GitHub. No direct Production edits, live order tests or unrequested partner messages.
- Existing intraday profile was previously saved. Revalidate it rather than asking again reflexively. Ask only for genuinely missing operational preferences or credentials, through appropriate secure configuration.

## 3. Starting state

Recent work added full-policy replay, independent public lifecycle events, delayed-entry capital/risk checks, archived public inputs, candidate capture, immutable CLI reports, and pre-decision-book support. Detailed changes and limitations are in the system guide and September 12 progress record.

Last inspected Production archive had quote journals and masters but zero captured public-input files. At that inspection the application containers were stopped. Do not assume this remains true or that restarting is authorized by a research task. The new Dev commits had not been deployed by this work.

No qualified NIFTY/SENSEX strategy or reliable date for partner tips has been established. The current report functions intentionally return no qualification/delivery/order authority. General Telegram connectivity can be tested separately with an explicitly authorized TEST message; that does not qualify trading advice.

## 4. First working session: establish a reproducible baseline

1. Read git status, current branch, last commits and remote tracking. Preserve untracked audits, evidence and unrelated edits. Do not squash earlier commits without authorization.
2. Read HANDOVER_CHECKLIST.md and rerun only checks invalidated by current changes/environment.
3. Inspect Production containers, release identity and archive root read-only. Record time, SHA, source paths and limitations. Do not print `.env` or tokens.
4. Locate current profile, qualification records, readiness reasons and per-index data timestamps using authenticated/read-only surfaces. Explain each missing gate in plain language.
5. Write the active plan slice with IDs from this document, success conditions and a bounded acceptance procedure. Begin the highest-priority unblocked slice.

Deliverable: an updated state table separating Dev-tested, release-tested, deployed, input-ready, strategy-qualified and delivery-tested. A single green label is insufficient.

## 5. Workstream A — finish causal acquisition and decision timing

**Priority:** P0 for usable research. **Files:** `fno_signal_scan.py`, `partner_orchestrator.py`, `partner_qualification.py`, `partner_research_capture.py`, `partner_full_policy_replay.py`, `research_cli.py`.

Problem: the original tick clock precedes network acquisition. Newly captured candidate receipts honestly occur later, so feeding them back at the old clock is correctly rejected. Merely setting a replay timestamp later can change bar eligibility/strategy meaning and must not masquerade as the original decision.

Implementation:

1. Define explicit tick-start, public-response receipt, chain-response receipt, evaluation cutoff, candidate construction and dispatch clocks. Use injected clocks in tests.
2. Choose and document the deployed policy: either evaluate on a declared frozen completed-bar cutoff with later availability, or recompute at a genuine post-acquisition decision clock. Do not silently mix both.
3. Carry the chosen clocks and source IDs into the captured bundle and frozen decision manifest. Bind candidate and public captures to the same decision/run/account/index.
4. Ensure crossing a five-minute boundary, entry cutoff or session boundary during a fetch cannot create a backdated idea.
5. Keep final dispatch revalidation independent: source availability does not grant transport authority.

Acceptance: reproduce an actual delayed-fetch case without timestamp fabrication; delayed source past entry deadline yields no advice; identical frozen inputs reproduce identity; a newly eligible bar has an explicit new decision. Quote provider timestamps remain untouched. Test both indices and timezone-aware UTC/IST input.

Expected benefit: collected sessions become replayable and recommendations use genuinely available inputs. Risk: changing clocks can alter signal frequency/identity. Version the policy and invalidate incompatible prior qualifications. Retain old captures and migration notes.

## 6. Workstream B — complete collection coverage, not just valid files

**Priority:** P0. **Files:** archive/capture/quote collector/leg subscription modules, scheduler telemetry, ops readiness routes and dashboard hooks.

1. Persist per-attempt records with expected schedule/cutoff, index, source, requested/received contracts, completion/error and references to immutable artifacts.
2. Record public and candidate capture outcomes independently, including no-setup, missing-chain, disk-full, busy writer and malformed packet cases.
3. Preserve all selected legs through the advice lifecycle and management horizon. Verify shared-token accounting, terminal registrations, restarts and expiry changes.
4. Compute session completeness from expected market-aware intervals and retained attempt records. Distinguish never attempted, attempted unavailable, partial, stale, and complete. A directory containing valid files alone is not sufficient.
5. Track quote and public-event gaps independently. Avoid pretending a stop between unobserved samples has a known fill.
6. Finish conditional-protection input capture and declare whether it can use the same replay schema or needs a separate evaluator.
7. Bound disk work. Current `to_thread` avoids event-loop blocking but awaiting it can still delay the advisory job. Introduce a bounded queue only with saturation/drop evidence, cancellation semantics and restart tests; never spawn unlimited writes.

Acceptance: interrupted/restarted session reports gaps; one index failure does not erase the other; missing selected leg prevents complete replay; archive budget failure remains observable while public updates continue; no operational cash or position mutation occurs. Review retention cleanup so capture files and referenced masters outlive qualification review.

Expected benefit: usable evidence and an honest explanation of why qualification is pending. Dependency: A's clock contract. Failure mode: collecting everything without a storage budget creates contention; measure overhead at representative load before release.

## 7. Workstream C — replay fidelity and review integration

**Priority:** P0 before qualification. **Files:** all `intraday_spread_*`, `partner_full_policy_replay.py`, `partner_qualification_review.py`, CLI and tests.

1. Verify public-source scope includes the intended underlying/futures contract and relevant roll/expiry context, not only a name string.
2. Bind raw/canonical master, candidate chain, public inputs, selected contracts, code/config/profile and cost schedule to immutable evidence IDs.
3. Review delayed execution beyond capital/risk: price spread limits, liquidity, current quantity, economic reward/risk, stale public observations and exact expiry boundaries.
4. Validate manual delay and cancellation behavior at entry and exit, including an invalidation on the fill timestamp, no later book, partial book and missed management deadline.
5. Align management deadline/reminder semantics with the deployed policy; do not force a fill at an unavailable exact-minute quote or retroactively close unresolved exposure.
6. Reject conflicting same-receipt quote packets rather than selecting a convenient first packet. Include failure evidence in the report.
7. Freeze review criteria before held-out sessions; connect full-policy outcomes to review without replacing the full evaluator with `orb_threshold_v1`.
8. Preserve zero-opportunity days, no-fills, unresolved exposure and rejected candidates. Account for overlapping ideas and repeated evaluations so sample size means independent opportunities.

Acceptance: unmocked multi-session archive fixture reaches both a costed close and unresolved outcome; tampered sources fail; cost stress uses identical observations; changed policy/profile cannot inherit qualification; complete CLI reports are reproducible and cannot overwrite earlier economics.

Expected benefit: a defensible decision to deliver a specific strategy. It may demonstrate that the current ORB policy lacks an edge; that is useful evidence and should lead to comparison, not suppressed losses.

## 8. Workstream D — release and genuine operational evidence

**Priority:** P0 after the passive collection slice is reviewed. Do not wait for an entire innovation roadmap before deploying useful, tested passive evidence collection.

1. Run full relevant Python acceptance, scheduler/API contracts, gateway native-SQLite-compatible tests, dashboard tests/build and affected agent tests. Record exact command, runtime and failures.
2. Review migrations, defaults, flags and Docker volumes. Establish consistent backup/rollback procedures without deleting data.
3. Prepare a PR describing behavior, tests and remaining operational prerequisites. User authorization is required for actions outside existing scope, including actual partner messages or live canary orders.
4. Promote via the release runbook: reviewed branch/SHA, stamped builds, recreate application services, resolve nginx upstream and verify live fingerprints. Never claim a merge alone deployed new code.
5. Observe one real market session for collection correctness and latency. This session proves operations, not strategy profitability. Fix deterministic gaps promptly.
6. Continue evidence until the predeclared review has an adequate independent sample. Report opportunity count, uncertainty and unresolved risk—not a countdown in arbitrary days.

Acceptance: receipt confirms correct live SHA; per-index inputs and coverage are observable; no unsolicited messages/orders; source and delivery switches match intended rollout. Roll back code only with schema/archive compatibility checked.

## 9. Workstream E — partner product activation and usefulness

**Priority:** P1, prepared in parallel with evidence collection.

Checklist for meaningful delivery: saved intraday profile, current index inputs, valid candidate, genuine compatible qualification, configured destination/token, transport test, final dispatch/session gates. Diagnose each separately. Never require partner positions for a general market setup.

Improve cards around decisions a manual trader can take: index/exchange, timestamp/validity, setup rationale, entry trigger and bounded price, exact contract legs/expiry/lot, total debit and modeled costs, maximum defined loss, invalidation/target and intraday deadline. Explain uncertainty and liquidity limits without overwhelming the message.

Hedge-first must have an explicit interpretation. Conditional protection states the exposure assumption and coverage; market directional spreads are not automatically personalized hedges. Ask for exposure details only if personalized protection is requested. Do not describe an unconfirmed action as taken/closed.

Prioritize invalidation and urgent management above new ideas; suppress overlapping NIFTY/SENSEX directional exposure as appropriate. Keep destination backoff, ambiguity and claim ownership intact. A two-idea cap, if effective, is a maximum rather than a quality target.

Acceptance: representative message previews are understandable, actionable and internally consistent; TEST delivery is distinguishable from advice; duplicate/recovery tests pass; strategy approval is scoped and revocable; every suppressed idea has an operator-visible reason.

Expected benefit: timely usable information, rather than hedge logs/status spam. Outcome evaluation should measure timeliness, executability and costed thesis performance. Partner feedback is helpful but not broker-confirmed P&L.

## 10. Workstream F — trading losses and accounting truth

**Priority:** P1, independent of partner qualification.

1. Reconstruct the previously reported ORB losses from actual entry/exit records, signal input, spread/leg identity, fees and market regime. Separate strategy failure, execution slippage, stale data and accounting defects.
2. Investigate each reconciliation warning with retained ledger/position records and broker statements when supplied. Produce discrepancy IDs and explanations; never mutate books merely to make the dashboard agree.
3. Audit true cost per trade relative to expected edge for INR 8k capital. Prevent a large configured paper bankroll from implying owner live affordability.
4. Audit funding, expenses, partial closes, rejected/cancelled orders and open mark-to-market independently.
5. Establish capital-increase criteria from externally reconciled net results, drawdown, execution quality and operational stability. Leave the user's loss tolerance as an explicit input if not supplied.

Acceptance: per-strategy/mode/account reports reconcile or show precise unresolved differences; deposits are not profit; no forced trade is used to verify a status flag. Expected benefit: stop allocating to misunderstood losses and make future scaling decisions evidence-based.

## 11. Workstream G — strategy basket and entry/exit intelligence

**Priority:** P1/P2 after data/accounting reliability. These are hypotheses, not proven improvements.

Predeclare a small basket rather than searching hundreds of variants until one looks profitable:

| Research hypothesis | Intended condition | Comparison | Main risk |
|---|---|---|---|
| Trend continuation after bounded pullback | Directional session with liquidity | Existing ORB vs pullback entry | Missed strong moves; hindsight support levels |
| Breakout with completed-bar confirmation | Expansion from compression | First break vs confirmation | Worse entry price offsets fewer false breaks |
| Range mean reversion with strict invalidation | Stable range/no expansion | No-trade baseline and existing range logic | Regime shift produces tail losses |
| Cost-aware abstention | Weak edge relative to spread/fees | Same setup before/after cost threshold | Overfitting threshold to recent trades |
| Exit profile comparison | Existing accepted entries | Fixed stop/target vs bounded time/trailing exit | Selecting best exit after seeing the path |
| Exposure-aware allocation | Multiple simultaneous ideas | Independent allocation vs shared risk cap | Correlation estimate unstable on short samples |

Use `proactive_*`, watchlists and run identities to compare candidates without creating an execution consumer implicitly. Freeze training/holdout and cost assumptions. Report net expectancy with uncertainty, drawdown, frequency, turnover, rejected/no-fill count and capacity. Control for repeated trials and overlapping signals.

Acceptance: one retained comparison report can explain why a strategy is promoted, rejected or still uncertain. Promotion to live requires a separate reviewed bridge and risk budget. Expected benefit is improved selection/management; no fixed profit uplift should be predicted without evidence.

## 12. Workstream H — scheduling, provider efficiency and dashboard

Measure p50/p95/p99/max execution time, queue wait, provider calls, cache hits/misses and database/writer contention during market hours. Prioritize order exits and public advice management, then candidate scans, then research. Cache only with explicit instrument, interval, completed-bar cutoff and freshness semantics.

The wrap-up scheduler-closure tests passed but emitted an unawaited `_run_penny_edge_scan_safe` coroutine warning at scheduler_setup.py:594. Determine whether the mocked scheduling path or a runtime rejection path leaks the coroutine, add a warning-sensitive regression, and correct it before describing scheduler validation as warning-free.

Investigate historical zero intraday-cache hit rates: find actual caller/key/window behavior before adding a cache. Do not mix mutable forming bars with completed historical bars or cross-account/exchange tokens.

Dashboard should show effective source/scope/window and readiness reason beside numbers. Distinguish disabled, unconfigured, no session, no setup, no evidence, stale and error. Wire real Production account/run sources rather than replacing unexplained zeros with synthetic results.

Acceptance: lower measured contention without missed exits or lost evidence; mocked slow-provider tests plus retained live-session measurements; UI fixture covers unavailable and zero distinctly. Be precise: reducing a job average does not prove tail latency is controlled.

## 13. Workstream I — optional AI and news

Use AI for bounded annotation: explain a deterministic setup, classify sourced events, summarize risk context, compare research findings and identify missing evidence. Store model/prompt/version, source references, response time and expiry. The typed result must not change capital limits, qualification or order/delivery authority.

Test disabled mode, timeout, stale response, queue saturation, budget exhaustion and restart. Deterministic paths must still operate. News must have publication/event timestamps and a reliable source; an unsupported model statement is not a market fact.

Expected benefit: better explanations and event-awareness. Main risk: plausible but wrong context arriving too late. Evaluate annotation usefulness separately from trading outcome and do not add synchronous model latency to exits.

## 14. Workstream J — CAS and market-session correctness

Read [the CAS inventory](2026-09-12-production-evidence-and-cas-findings.md) and verify current official NSE/BSE/SEBI sources before implementation. September 12 NSE information described cash CAS eligibility and different session timings from continuous cash and equity derivatives.

Inventory hard-coded clocks in market calendars, gateway market-hours, scheduler jobs, bars, expiry/square-off, UI and replay. Introduce an exchange/security/session-phase model only after verifying effective dates and broker behavior. Preserve earlier strategy deadlines unless explicitly revised and qualified.

Do not assume auction imbalance is available in Kite's current feed. Verify actual feed fields/rights first. If unavailable, label that limitation rather than infer imbalance from LTP. Any auction-based strategy is separate research with auction execution semantics, not an extension of a continuous-market fill model.

Acceptance: ordinary days, eligibility differences, holidays, shortened/special sessions and phase transitions have tests. No accidental extension of partner holding horizon. Expected benefit: correct session behavior; an auction profit edge remains hypothetical.

## 15. Suggested order and dependency graph

Start A and B, then finish C. Release a reviewed passive collection slice through D as soon as its operational acceptance is satisfied. Prepare E's message/setup UX in parallel; activate only after compatible qualification. Run F independently because capital truth and losses matter now. Use G to replace an unpromising baseline with tested alternatives. H supports every operational phase. I is optional, and J begins with session correctness before strategy innovation.

Do not claim A–J complete because files exist. Maintain a requirement matrix with statuses: NOT_STARTED, IMPLEMENTING, TESTED_DEV, RELEASE_VALIDATED, DEPLOYED_OBSERVED, EVIDENCE_PENDING, ACCEPTED or REJECTED. Include the precise evidence reference for each status.

### Current requirement matrix — September 12 A/B slice

| Requirement | Status | Evidence | Remaining transition |
|---|---|---|---|
| A — causal acquisition/decision timing | TESTED_DEV | `docs/2026-09-12-clock-and-coverage-plan.md`; focused Python timing/capture/orchestrator tests | Full release acceptance, promotion and one observed session |
| B — per-attempt collection completeness | TESTED_DEV | Archive-local SQLite attempt journal, readiness API/card and restart/partial/unavailable/timeout tests | Production load/retention measurement and observed schedule coverage |
| H — scheduler coroutine warning | TESTED_DEV | 41 scheduler/isolation tests with RuntimeWarning fatal | Release acceptance and deployed scheduler observation |
| C — replay fidelity/review integration | TESTED_DEV | Real evaluator/archive multi-session fixture uses master-proven v3 public futures/roll captures and reaches costed close/unresolved outcomes; conflicts and unrelated packets are distinguished; exact deadlines/strictly-future expiry and delayed liquidity/cancellation/public-age gates are tested; source-bound stress/drawdown and pre-holdout criteria remain enforced; modeled asymmetric legs are bound to their verified source packets and separately identified | Obtain adequate genuine held-out evidence; verify real collection/retention and exchange-specific settlement assumptions during D/J; actual broker fills are not asserted by the modeled-partial research contract |
| D — release/operational evidence | IMPLEMENTING | Baseline: full Python 2,545 passed/3 skipped, scheduler 41 passed, dashboard 25/build, agent 91; resource plan: gateway 324 passed/4 skipped/natural exit, Python warning-fatal 32 and resource-fatal 181; `docs/2026-09-13-consistent-backup-plan.md`: offline verifier/runbook and 117 warning-fatal backup/deployment/migration/journal tests, native dummy-data CLI/tar roundtrip | Actual authorized quiescence/backup/restore and old/new schema compatibility, reviewed GitHub PR/release and real-session observation; currently application containers stopped, not implicitly restarted |
| E — partner activation/usefulness | EVIDENCE_PENDING | Existing profile/delivery gates remain independent | Genuine compatible qualification and authorized transport validation |
| F — trading losses and accounting truth | TESTED_DEV through F.10A; operational evidence still pending | Existing F1-F6 evidence remains in `docs/2026-09-13-workflow-f-state-of-codebase-audit.md` and the independent correction plan. F.10A adds `broker_internal_reconciliation.py`, three durable discrepancy categories, additive CLI/HTTP output and regressions for account binding, statement selection, fill aggregation, both position books, missing/duplicate/paper references, quantity excess and idempotency; see `docs/2026-09-19-f10a-broker-internal-reference-plan.md`. Unsupported sources also fail closed by contract. It never upgrades a reference match into broker reconciliation or authority. Focused: 118 passed; whole engine: 4,090 passed/four skipped. | Obtain genuine broker statements and perform operator review. Full bidirectional economic reconciliation remains blocked on statement period bounds, account-scoped internal books, universal order IDs and richer immutable fill metadata. Signed loss tolerance/capital decision, D release validation and deployed observation remain separate. |
| G — strategy basket and entry/exit intelligence | TESTED_DEV through G.7; pushed, genuine evidence pending | Existing predeclared protocol, exit composition, immutable caches and signed bridge remain documented in the G audit/promotion plans. G.7 makes `RANGE_REVERSION_V1` causal: first completed post-cutoff decision bar, 14 prior bars, execution strictly later, explicit fail-closed outcomes, verifier-derived stop/mean target, and no fallback to generic confirmation. The comparison protocol removes the obsolete alias/forced-uncertain rule but preserves completeness, economics, drawdown, paired uncertainty, immutable implementation identity and all no-authority fields. Focused 81, broader G 222 warning-fatal, and whole engine 4,095/four skipped pass; commits `fefa5a3`/`bc79325` pushed; see `docs/2026-09-19-g7-range-comparison-causality-plan.md`. | Obtain genuine predeclared held-out sessions and F/D evidence. BridgeDecision signing, shared-book capacity, default-v1 migration, release/deployment and strategy qualification remain separate operator/evidence gates. |
| H — scheduling / provider efficiency / dashboard | DONE (H1 scheduler coroutine warning closed and PROD-ready; H2 priority-tier breakdown closed; H3 intraday-cache caller/key/window diagnostic closed `fead40c`; H4 cache-add for ``get_intraday`` closed `d1d6e15` with three operator-tunable knobs honouring §12 four explicit semantics; H4.B by-token cache closed `bfb42ac` extending H4 to the F&O/partner path; H5 dashboard readiness vocabulary closed `b9cfc44` with bounded state->descriptor mapping and self-validation) | H1 — `python-engine/scheduler_setup.py`: ``run_penny_hourly_report_safe`` wrapper + cron re-registered with ``max_instances=1, coalesce=True, misfire_grace_time=600``; ALL_CLOSURES extended. H2 — `python-engine/scheduler_telemetry.py`: `JOB_TIER_MAP` + `TIER_ORDER` + `_tier_for` + `_aggregate_by_tier` + `by_tier` key in `scheduler_timing_report`; `operational_coverage.py` extended with `scheduler_tier:{tier}` entries. H3 — `python-engine/intraday_cache_diagnostic.py`: read-only diagnostic with `CACHED_CALLER_SITES`/`BY_TOKEN_CALLER_SITES` inventories, `cache_row_counts`/`cache_interval_breakdown`/`cache_freshness_window`/`audit_key_shape` queries, `cache_by_token_row_counts`/`cache_by_token_interval_breakdown` for the new table, `run_diagnostic` + CLI; reuses `reconciliation_cli._write_output_atomic`. H4 — `python-engine/kite_client.py:454-575`: explicit §12 four-semantics enforcement in `get_intraday` HIT path (instrument + interval + completed-bar cutoff + freshness); three new operator-tunable knobs in `python-engine/config.py`: `INTRADAY_CACHE_FRESHNESS_SECONDS=0`, `INTRADAY_CACHE_INCLUDE_FORMING=False`, `INTRADAY_CACHE_MIN_CANDLES=4`. H4.B — `python-engine/kite_client.py`: same four semantics extended to `get_intraday_by_token` via shared `_intraday_cache_gate_evaluate` helper; new `intraday_cache_by_token` table; daily interval exempt from forming-bar filter; `_interval_minutes("day") = 1440` (was a latent PROD crash on partner_orchestrator's daily calls). H5 — `python-engine/coverage_vocabulary.py`: seven §12 descriptors (DISABLED/UNCONFIGURED/NO_SESSION/NO_SETUP/NO_EVIDENCE/STALE/ERROR), `STATE_TO_DESCRIPTOR` mapping for the eight states produced by `operational_coverage_report`, `validate_coverage_report` called at end of report; drift attached to report under `vocabulary_drift`, logged at WARNING. 7 + 22 + 26 + 13 + 13 + 22 = 103 new H-series tests pass. whole-engine 3,026 passed/4 skipped/39 warnings (~+22 vs previous 3,004 after H4.B). No regression to the previously closed baseline failures; no new warnings. | H-series complete. Production acceptance remains separate per plan §15 |
| I — optional AI and news | IMPLEMENTING (I1 model/prompt/version provenance + response time closed `4ea9b54`; I2 news provenance — publication timestamps + source URLs closed `33d780c`; I3 usefulness-instrumentation snapshot + bounded CLI closed `f35d859`; I.A bridge I3 usefulness metrics from agent to engine closed `980636e` + `65d4bfe`; I.B surface I1 provenance in operator alert closed `d1e7d4f` + `9bd5286`; I.C operational_coverage_report includes optional AI closed `89a9804` + `c47941e`; I.F cross-container contract test closed `a226ec3` + `0f7120b`; I.4 deep-research proposal closed `aaa15d6`; **I.4.D source-event classification closed `c80e3fa` + `d60073b` + `bc0a0a6` + `557de73`**; **I.4.E bounded contract-health self-evaluation closed (5 invariants: status_envelope_authority, no_prompt_leakage, usefulness_counters_only, classifier_fail_closed, review_non_authoritative) + `evaluate_contract()` aggregate + read-only CLI `tools/contract_health_check.py` with print-config/check/self-check subcommands**; remaining I.4 opportunity G (per-ticker breakdown) explicitly deferred to separate slices after A/B/C/F prove themselves in PROD) | I1 — `agent/advisory.py`: `Review` gains six provenance fields (model/base_url/prompt_version/started_at/completed_at/response_seconds), all default None for backwards compatibility. `agent/agent.py`: `MINIMAX_PROMPT_VERSION` env var (default "v1"); `_attach_provenance` helper using `dataclasses.replace`; every return site of `analyze_with_minimax` wrapped. I2 — `agent/agent.py`: `NewsItem` frozen dataclass with title/source_url/published_at_raw/published_at_parsed/source_name/age_label; `fetch_news_items` returns structured list; `_parse_rss_pubdate` handles RFC 822 and RFC 1123; `_age_label` produces `fresh`/`N hours ago`/`N days ago`/`stale_aged_Nd`/`stale_or_unknown`/`future_dated`; `fetch_rss_feed` legacy string format preserved; `scrape_sentiment` renders structured `[age] (source) title` + `url:` lines. I3 — `agent/async_reviews.py`: bounded counters (`_response_seconds` buffer, `_verdict_counts`, `_cache_hits`, `_cache_misses`, `_circuit_opens`, `_last_response_seconds`, `_last_completed_at`); `submit` tracks cache hits/misses; `_run` captures response_seconds + verdict counts + circuit-open transitions; new `usefulness_snapshot()` returns 10 bounded JSON-serialisable fields. I.A — `agent/agent.py::publish_optional_ai_status` includes `usefulness_snapshot()` in payload; `python-engine/optional_ai_status.py` extends `clean_queue` allow-list; new `usefulness` envelope with bounded field validator; dashboard `OptionalAiEvidence` renders the new fields. I.B — `agent/advisory.py::Review.banner()` renders model + prompt_version + response_seconds when present; backwards-compatible (provenance absent → banner unchanged). I.C — `python-engine/operational_coverage.py` gains `optional_ai` producer with the standard `{state, reason, observed_at, ...}` contract; H5 vocabulary extended to map optional AI states to descriptors. I.F — `python-engine/tests/test_optional_ai_cross_container_contract.py` + `agent/tests/test_optional_ai_cross_container_contract.py` round-trip the bounded envelope and reject unknown keys. I.4 — `docs/2026-09-13-i4-deep-research.md` proposes 7 bounded AI-enrichment opportunities (A–G). I.4.D — `agent/news_classifier.py` pure/total bounded 8-category classifier; `analyze_with_minimax(pre_classifications=None)` with backward-compatible prompt; `_fetch_news_items_for_ticker`/`_maybe_classify_news` env-flagged helpers; operator CLI `agent/tools/news_classify_cli.py` (--ticker/--input/--dry-run/--json); 76 tests (36 module + 10 helper + 9 integration + 21 CLI + 6 async-queue via `inspect.signature` review). I.4.E — `agent/contract_health.py` pure self-evaluation (5 bounded invariants + `evaluate_contract()` aggregate + `ContractReport` with `schema_version="i4e-v1"`); operator CLI `agent/tools/contract_health_check.py` (print-config/check/self-check, read-only, exit 0/1/2); 53 tests pin the contract; agent suite grew 259 → 312 (+53 net). See [I.4.E done-doc](2026-09-14-i4e-contract-health-done.md) |. `agent/optional_ai_metrics.py` NEW: bounded CLI with `print-config` and `read-snapshot` subcommands, documented `CONFIG_CONTRACT`. 15 + 21 + 15 = 51 new tests pass. **I.A** — NEW `_ALLOWED_USEFULNESS_KEYS` / `_ALLOWED_VERDICT_KEYS` allow-lists in `python-engine/optional_ai_status.py` (6 top-level bounded fields + 4 verdict buckets); new `_clean_usefulness(raw)` validator that rejects unknown keys, bad types, bool-for-int, negative numbers, non-dict envelopes. NEW `record_optional_ai_status` integrates the validator: clean usefulness persisted under `detail.usefulness` when envelope present; absent when not. `OPTIONAL_AI_REPORT_USEFULNESS` opt-in env var. `agent/agent.py::publish_optional_ai_status` includes `usefulness_snapshot()` in payload. NEW `tests/test_optional_ai_usefulness_bridge.py` (21 tests across 4 classes: bounded validator / persistence / route surface / bounded contract — explicitly rejects `pitch`/`rationale`/`prompt`/`api_key` leaks). Whole-engine: python-engine 3026 → 3047 (+21); agent 153 → 174 (+21). **I.B** — `agent/advisory.py::Review.banner()` extended with model/prompt_version/response_seconds (1 decimal); backwards-compat substring tests preserved. NEW `tests/test_review_banner_provenance.py` (300 lines, banner-format contract). Whole-engine: 3047 → 3072 (+25); agent 174 unchanged. **I.C** — `python-engine/operational_coverage.py` extended with `optional_ai` producer sourced from `load_optional_ai_status`; H5 `STATE_TO_DESCRIPTOR` mapping extended with optional-AI states (`READY`, `DISABLED_*`, `OUTAGE_CIRCUIT_OPEN`, `UNAVAILABLE`). NEW `tests/test_coverage_vocabulary_optional_ai.py` (140 lines) + `tests/test_operational_coverage_optional_ai.py` (436 lines). Whole-engine: 3072 → 3097 (+25); agent unchanged. **I.F** — Cross-container contract test pins the producer/consumer invariant: a known-bad envelope (leaked prompt, leaked credentials, wrong types) is rejected at the engine boundary; the producer's `usefulness_snapshot()` is bit-shaped-compatible with the consumer's `_clean_usefulness()`. NEW `tests/test_optional_ai_cross_container_contract.py` (488 lines). Plus 4-line optional_ai_status consistency fix. NEW `tests/test_optional_ai_status_usefulness.py` (132 lines) on the agent side. **I.4** — `docs/2026-09-13-i4-deep-research.md` (the research proposal): 7 enrichment opportunities ranked by value/cost; recommended A+B+C+F as the visibility-focused slice (already implemented above); D (source-event classification, the §13 explicit gap), E (periodic self-evaluation), G (per-ticker breakdown) deferred to separate slices after A/B/C/F prove themselves in PROD. **I.4.D** — NEW `agent/news_classifier.py`: bounded source-event classifier against the fixed 8-category taxonomy (`REGULATORY`, `EARNINGS`, `M_AND_A`, `GUIDANCE`, `MACRO`, `RUMOR`, `TECHNICAL`, `UNKNOWN`). `NewsCategory` enum (string-valued); `ClassificationResult` frozen dataclass (ticker, title_hash, category, confidence [0,1], bounded rationale ≤ 280 chars, prompt_version, classified_at). `CONFIDENCE_THRESHOLD = 0.6` (fail-closed: below threshold → UNKNOWN). `CLASSIFIER_TIMEOUT_SEC = 1.0` (per-item latency budget per the deep-research doc). Pure / total: never raises; on timeout / parse error / disabled / model-exception returns `UNKNOWN` with confidence=0.0 and a human-readable rationale. Fixed taxonomy — a category the model invents (outside the enum) is forced to `UNKNOWN`. `DISABLE_CLASSIFIER` env var forces every classification to UNKNOWN (offline / CI / sandbox). `_extract_json_object` parser tolerates `<think>...</think>` blocks (MiniMax-M3 reasoning), `\`\`\`json\`\`\`` fences, leading prose, malformed input. **`c80e3fa`** ships the module + 36 tests (taxonomy, JSON parser, output normaliser, threshold rule, frozen immutability, title hashing, disabled/no-client paths, end-to-end with mock client, batch API, to_dict JSON-safety, config sanity). **`d60073b`** wires `pre_classifications` into `analyze_with_minimax` as an OPTIONAL keyword parameter; the verdict prompt gains a `CLASSIFIED SENTIMENT DATA` section (rendered ABOVE the existing `MULTI-SOURCE SENTIMENT DATA` section) listing `title_hash + category + confidence + rationale` per headline. When `pre_classifications` is None (the default, every existing caller's path), the prompt renders a placeholder text and is byte-identical to its pre-I.4.D shape. The verdict pipeline's existing path is unchanged. **`bc0a0a6`** adds two env-flagged helpers (`_fetch_news_items_for_ticker`, `_maybe_classify_news`) so the operator can flip `ENABLE_NEWS_CLASSIFIER=1` to wire classification into the call sites — the async-queue extension is explicitly deferred (carrying `pre_classifications` through `_Task` is a separate slice). The helpers never raise; the verdict pipeline's failure modes are unchanged. **`557de73`** lands the operator CLI `python -m agent.tools.news_classify_cli --ticker TICKER | --input PATH [--dry-run] [--json] [--limit N]` — runs without touching the verdict pipeline, exits 0/1/2/3 with structured diagnostics. 21 CLI tests pin the contract. Agent suite grew 213 → 253 (+40 across the 4 commits); zero regressions. | Annotations surface in operator dashboards; usefulness evaluation requires operator-supplied ground truth (deferred per plan §13 explicit constraint). I.A/B/C/F and the I.4 deep-research proposal are CLOSED. **I.4.D source-event classification is CLOSED.** Remaining I-series work (opportunities E and G per the I.4 proposal — periodic self-evaluation, per-ticker breakdown) is explicitly deferred — separate slices only after the visibility-focused work proves itself in PROD. |
| J — CAS and market-session correctness | IMPLEMENTING (J.1 classifier closed `d82258f`/`63a98ab`; J.2.1 eligibility list closed `ba117fb`; J.2.2 broker-behaviour probe closed `f6e07da`; J.2 docs sweep closed `211fc58`; J.3.1 probe-quality + classifier `cas_eligible` kwarg closed `6019279`; J.3 capture-review tool + runbook + receipt-directory scaffold closed `9ab8ad1`; J.4 wire `stamp_session_phase` to real classifier closed `cb309a8`; J.5 holiday reconciliation Python↔Node closed `e0061a4` + `c3d1649`; **J.5 holiday divergence actually fixed (Node fallback updated to 20 dates matching Python, drift detector now reports ALIGNED) closed `00dffbd` via independent correction plan `64e22a9`**; J.6 Node sessionPhase mirror closed `1b007c6` + `d5ae6de`; J.7 CAS-aware execution gating closed `cf43df8` + `c0d5c79`; **J.7 CAS-eligibility resolver hardened (Python `routes_market_session.py` is the single authoritative projection; Node `services/cas-eligibility.js` fetches it; `entrySessionVerdict` blocks before broker/DB calls when resolver unavailable) closed `00dffbd`**; J.8 operator dashboard session-phase card closed `6ced829` + `d00f463`; J.9 CAS-aware signal handling closed `e18a160` + `cea1c26`; J.10 CAS-branch reachability gate closed `ba91dcc` + `414207e`; **J.10.CLOSURE operator-facing SUMMARY.md surface closed `c734e4c` + `b8a490e`**; **holiday calendar validity bound (`NSE_HOLIDAYS_VALID_THROUGH = 2026-12-31`, `isHolidayCalendarUsable()` fails closed after that date) closed `fd450a3`**; operator-supplied staging captures still pending for J.10 to flip from UNREACHABLE to REACHABLE) | J.1: `python-engine/market_calendar.py` central constants + 10-phase classifier + `is_cas_eligible` + 41 tests. J.2.1: `CAS_PHASE1_FNO_UNDERLYINGS` env var (CSV) → `is_cas_eligible`. J.2.2: staging-only `tools/j2_cas_probe.py`. J.3.1: probe bumped to `SCHEMA_VERSION: 2` with inline JSON Schema; new flags `--schema-print` / `--eligibility-list` / `--require-eligible` / `--validate`; strict ISO 8601 parser; explicit `cas_eligible: bool | None = None` kwarg on `classify_session_phase`. J.3: NEW `tools/j2_capture_review.py` (six-point checklist + opt-in OHLC-continuity cross-window check); NEW `docs/2026-09-13-j3-capture-protocol.md`; NEW `docs/j2_captures/README.md`. J.4: `python-engine/proactive_intelligence.py::stamp_session_phase` wired to `classify_session_phase` via lazy import. Signature gains three opt-in keyword-only kwargs (`symbol`, `is_derivative`, `cas_eligible`). 17 new J.4 tests across 5 classes. J.5: `python-engine/market_calendar.py` re-verified canonical 20-date NSE Equity 2026 holiday list against NSE source. NEW `python-engine/holiday_drift.py`: pure drift detector (Node source as text + canonical set; reports `ALIGNED` / `DRIFT`). NEW `python-engine/tools/holiday_drift_check.py`: CI/operator CLI (exit 1 on drift). NEW `python-engine/routes_holidays.py`: GET `/holidays` route returning the canonical list; the response now exposes `valid_through: NSE_HOLIDAYS_VALID_THROUGH` so consumers can see when the static set expires. `main.py` wires the new route (1 import + 1 `include_router`; main_surface_golden.json updated for the +1 endpoint). NEW `python-engine/tests/test_holiday_drift.py`: 18 tests — the pre-correction drift signature (Python=20 / Node=18) is documented as historical; the post-correction state (Python=20 / Node=20 / drift=0 / verdict=ALIGNED) is pinned. `node-gateway/server/utils/market-hours.js` rewritten: live `NSE_HOLIDAYS` Set mutated in-place by an engine fetch at boot (5s timeout); `MARKET_HOURS_HOLIDAYS_JSON` env override; **the pre-correction 18-date `NSE_HOLIDAYS_FALLBACK` is replaced by the exact ISO projection of `market_calendar.NSE_HOLIDAYS_STATIC` (20 dates); `isHolidayCalendarUsable()` fails closed after `NSE_HOLIDAYS_VALID_THROUGH = '2026-12-31'`**; `replaceHolidays` records the source validity date so a successful engine refresh can extend the live set's validity. 6 new Node tests in `tests/unit/market-hours.test.js` (was 19, +4 for stale-calendar fail-closed and `isCashCasEligibilityResolutionWindow` → 23 total). Full python-engine suite: **3245 pass / 4 skip / 0 fail** (vs J.4 baseline 3225 / 4 / 1; +20 net, 1 net regression eliminated — the previously-failing surface test was a documented golden refresh). **J.7**: NEW Python `execution_allowed(observation_at, *, symbol, is_derivative, cas_eligible, allow_pre_market) -> {allowed, phase, reason}` in `python-engine/market_calendar.py`. Bit-perfect mirror in Node: `isExecutionAllowed(opts)` in `node-gateway/server/utils/market-hours.js`. Translation table: `CONTINUOUS_TRADING` / `DERIVATIVES_CAS_ALIGNED` -> allowed; `PRE_MARKET` -> blocked unless `allow_pre_market=true`; `CLOSED` / all `CAS_*` / `UNKNOWN` -> blocked. NEW `node-gateway/server/utils/errors.js::CasPhaseError(phase, reason)` (status 422, code `cas_phase_blocked`). Wired into `services/executor.js` (replaces J.6 observability with a hard CAS-aware guard; preserves `MarketClosedError` for the `CLOSED` phase) and `index.js` telegram callback (shows `verdict.reason` for CAS-blocked phases). NEW `python-engine/tests/test_execution_allowed.py` (19 tests across 5 classes: CLOSED/PRE_MARKET, CONTINUOUS_TRADING, CAS sub-windows, DERIVATIVES_CAS_ALIGNED, purity). NEW `python-engine/tests/fixtures/regenerate_execution_allowed_golden.py` produces 3,525 vectors and dual-writes both fixtures. NEW `node-gateway/server/tests/unit/isExecutionAllowed.test.js` (20 tests including the **golden-vector parity test** that asserts zero mismatches across all 3,525 vectors). All 4 existing mocks of `market-hours.js` extended to expose `isExecutionAllowed`. Window boundary correction: the J.6 docs listed CAS sub-window widths that did not match the live Python constants (15:30 -> 15:40 for CAS_MATCHING vs actual 15:30 -> 15:35); J.7 corrects the docs and tests use the actual constants (CAS_REFERENCE_PRICE_WINDOW 15:15-15:20, CAS_ORDER_ENTRY 15:20-15:25, CAS_LIMIT_ENTRY_ONLY 15:25-15:30, CAS_MATCHING 15:30-15:35, CAS_POST cash 15:35-16:00, DERIVATIVES_CAS_ALIGNED 15:30-15:40). Net: Node full suite **380 pass / 4 skip / 0 fail** (was 360/4/0 at J.6 close; +20 new); python-engine full suite **3267 pass / 4 skip / 1 pre-existing failure** (the J.6-documented `test_coverage_vocabulary.py::test_unmapped_state_appears_in_drift` aiosqlite-threading flake, verified zero J.7 imports). **J.7 hardening (independent correction plan)**: NEW `python-engine/routes_market_session.py` exposes `GET /market-session/cas-eligibility?symbol=...` (authenticated via `X-Internal-Secret`, returns `{symbol, cas_eligible, source, source_version}` where `source_version` is a SHA-256 of the configured CSV — no CSV disclosure). NEW `node-gateway/server/services/cas-eligibility.js`: `resolveCasEligibility(symbol, observationAt)` short-circuits outside `isCashCasEligibilityResolutionWindow` (the 15:15-15:29 IST cash-CAS-affected interval) with `{required: false, resolved: true, casEligible: false}`; inside the window it fetches the Python projection with the configured timeout; failures return `{required: true, resolved: false, casEligible: null, reason: ...}`. NEW `entrySessionVerdict(symbol, observationAt)` chains eligibility with the existing `isExecutionAllowed` verdict: an unresolved eligibility returns `{allowed: false, phase: 'CAS_ELIGIBILITY_UNAVAILABLE', reason: ...}`. `services/executor.js` and `index.js` now call `entrySessionVerdict(signalData.ticker, new Date())` BEFORE any DB UPDATE / EXECUTING transition / answerCallbackQuery; a `CAS_ELIGIBILITY_UNAVAILABLE` failure short-circuits execution; operator sees `show_alert: true`. NEW `tests/test_market_session_route.py` (3 tests: 403 without secret, 200 projects config, 200 returns false for unconfigured). NEW `tests/unit/cas-eligibility.test.js` (3 tests: no-fetch outside window, fetch inside window with X-Internal-Secret, fails closed when resolver unavailable). Updated `tests/unit/executor.test.js` (2 new tests: blocks before broker calls, passes actual ticker), `tests/integration/telegram-callbacks.test.js` (1 new test: blocks callback), `tests/integration/approved-snapshot.test.js` (mock added so existing tests reach executor). `utils/errors.js` now exports `CasPhaseError`. **J.10.CLOSURE**: NEW `update_summary(report, summary_path, *, captures_dir=None)` in `python-engine/cas_reachability_gate.py` renders the gate's verdict into a deterministic markdown SUMMARY.md. **Critical bug fix**: `_safe_phase_from_capture` was reading `doc["classifier"]["phase"]` and `doc["phase"]` -- the J.3 schema actually stores the bounded phase at `rows[i].classifier_phase`. The gate now iterates `rows[]` and reads `rows[0].classifier_phase`. NEW `--update-summary` / `--summary-path` flags on `python-engine/tools/cas_reachability_check.py`. NEW auto-update hook on `python-engine/tools/j2_capture_review.py` happy-path: the SUMMARY regenerates automatically when a capture review passes; fail-path leaves the SUMMARY untouched (fail-closed). NEW `python-engine/tests/test_cas_reachability_summary.py` (10 tests) and `python-engine/tests/test_j10_closure_e2e.py` (3 tests); `python-engine/tests/test_cas_reachability_gate.py` fixtures updated to the J.3 schema shape. **J.10.CLOSURE holiday validity**: `python-engine/market_calendar.py::NSE_HOLIDAYS_VALID_THROUGH = '2026-12-31'` is the documented validity period for the static set; `routes_holidays.py` exposes `valid_through` in the response. Net (after independent correction plan): python-engine +19 new tests (5 F6, 7 F3/F4/F5, 3 market-session, 4 holiday_drift updated); Node full suite **394 pass / 4 skip / 0 fail** (was 385 at J.10.CLOSURE close; +9 new); client 40/0/0 (no client changes). | **Operator-supplied staging captures still pending in staging** (CAS broker-behaviour verification). Plan §14: any auction-aware code must pass `tools/cas_reachability_check.py` before shipping -- this is the gate. The J.10.CLOSURE SUMMARY.md surface is the audit trail. `fno_chain.py::EXPIRY_CUTOFF_HOUR/_MIN = 15, 30` and `hedge_strategies.py::_EXPIRY_CUTOFF = time(15, 30)` preserved unchanged. Holiday reconciliation Python↔Node **DONE in J.5 + actually fixed in the independent correction plan (Node fallback aligned to 20 dates, drift=ALIGNED, holiday validity bound fail-closed at 2026-12-31)**; the `NSE_HOLIDAYS_FALLBACK` divergence is no longer a divergent degraded-mode -- it is now the exact ISO projection of the canonical Python set. Node `sessionPhase()` parity mirror **DONE in J.6**; J.7's CAS-aware execution gating **DONE in J.7** (and now hardened by the independent correction plan's authoritative Python projection + Node resolver); J.8's operator dashboard session-phase card **DONE in J.8**; J.9's CAS-aware signal handling **DONE in J.9**; J.10's CAS-branch reachability gate **DONE in J.10**; J.10.CLOSURE's operator-facing SUMMARY.md surface is the last J-series slice -- once operator-supplied staging captures land, the gate flips to REACHABLE and the J-series is operationally closed. |

## 16. Mandatory documentation and plan ritual

September 13 independent F/G audit correction: `2026-09-13-fg-independent-correction-plan.md` supersedes any implication that the whole new bridge/strategy basket is accepted. Atomic terminal-state/append-order fix, faithful trailing composition and immutable exit-cache manifests are tested in Dev. Approval budget/expiry/version checks now require immutable predeclared amount/DD/expiry and retain the original-clock validity window; twelve-file F/G acceptance passes 180 tests with warnings fatal. Reads still report `approval_usable=False`: frozen held-out/account/F/D evidence validation, faithful range semantics and unsupported F schema/provenance/historical closures remain open. External F/G work is preserved. The earlier whole-engine receipt predates cache and budget changes; full rerun remains required.

This is a user requirement for every future agent, including an agent continuing its own work:

1. Before editing, reconcile current state and write/update a plan slice: problem, user impact, affected files, dependencies, assumptions, acceptance tests, rollback and what will remain.
2. During implementation, record material discoveries and revise the plan when scope changes. Do not keep obsolete tasks marked pending or pretend abandoned approaches were implemented.
3. With every implementation commit, update SYSTEM_GUIDE.md for changed behavior and regenerate SYSTEM_CODE_ATLAS.md when files/declarations change. Update the active plan and acceptance evidence in the same commit when practical.
4. Immediately after every commit, inspect the commit/status. Confirm documentation and plan match actual behavior. If documentation was missed, make a prompt docs-only correction before further implementation.
5. Record commit ID, exact verification command/result, environment, migration/config impact, release/deployment status, remaining risks and next action. Never mark Production changed just because Dev was pushed.
6. At every handover, provide a concise current-state ledger and one executable next action. Preserve the whole product objective across context compaction.

Use the following plan slice template:

```text
ID / title:
Problem and user-visible impact:
Current authoritative evidence:
Files and contracts affected:
Implementation steps and dependencies:
Acceptance / negative / restart / timing tests:
Data and configuration migration:
Rollout and rollback:
Status and verified commit:
Documentation updated:
Unresolved limits and exact next action:
```

## 17. Completion and communication rules

A feature is done only when its acceptance conditions are met; a release is done only when promoted and verified; a strategy is qualified only when genuine reviewed evidence supports it. These are different claims.

Report progress as behavior and user value first, then tests and limits. Avoid repeated vague declarations that 'only operational evidence remains' while acquisition, collection or review integration is still unfinished. Avoid predicting a date for tips from the number of elapsed sessions alone. Explain what is missing and what action produces the needed evidence.

The next agent should review the complete Dev release diff/defaults and prepare the GitHub PR, while resolving actual authorized quiescence/backup/restore and previous-code schema compatibility using the consistent-backup plan/runbook. Production application containers were observed stopped; user was asked whether this was deliberate, with no implicit restart. The 17 earlier Python failures and two detected gateway handles are corrected; full baseline acceptance is 2,545 passed/3 skipped. Genuine Production collection and adequate held-out evidence remain required. Preserve the working replay/CLI, legacy-read compatibility and all retained artifacts. Do not restart the architecture from scratch.

## 18. September 20 closeout — AI activation and staging evidence

Status: **IMPLEMENTED_DEV, PUSHED; NOT DEPLOYED**. Source commit `1a6e0d9` is
on `origin/codex/production-correction-hedge-p0`. Detailed plan and Production facts:
`docs/2026-09-20-ai-and-partner-readiness-gap-plan.md`.

Completed in Dev:

- Compose explicitly enables bounded optional-AI annotation, source-event
  classification and usefulness reporting with non-blocking safe policies.
- Manual partner advisory is explicit; advanced hedge shadow observation is
  enabled while Phase-2/3 delivery remains explicitly disabled.
- A staging date is recorded only after genuine reconciled-portfolio and fresh
  option-chain shadow processing. One date is idempotent across repeated ticks.
- The E.1 readiness diagnostic now queries the deployed runtime schemas and
  hardened transport ledger. It no longer mislabels advanced Phase-3 0/7 as a
  blocker for ordinary manual index advice.
- Seven Phase-3 dates, live-chain verification and per-kind sample reviews are
  still required. No threshold was lowered and no delivery/order authority was
  added.

Remaining work is operational/evidence work, not another threshold change:

1. Promote through GitHub and restore healthy Production application services.
2. Verify deployed release/config identities and effective flags.
3. Log in on each intended market day and provide a genuine, fresh reconciled
   partner-position snapshot if advanced personalized hedge staging is wanted.
4. Observe actual shadow receipts/evaluations; perform live-chain and sample
   reviews. Do not backfill missed days from container uptime.
5. Separately complete genuine manual-advisory strategy qualification. The
   advanced hedge 7/7 counter is not that qualification and does not control
   generic NIFTY/SENSEX advisory scanning.

Acceptance receipt: 4,122 Python-engine tests passed/four skipped; 357 agent
tests passed in the built image with networking disabled; 27 corrected E.1
tests passed with warnings fatal; both affected images built; rendered and
runtime Compose flag checks match the safe matrix. Existing deprecation and
Dockerfile casing warnings remain. These checks establish Dev regression
fitness, not deployment, strategy profitability or qualification.
