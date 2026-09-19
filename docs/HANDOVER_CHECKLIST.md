# Handover receipt and operator checklist

## September 19 Workflow F.10A (Dev tested)

The new read-only broker/internal report checks executed imported broker order
IDs against retained live references in both position books and records
missing, ambiguous and insufficient-scope results without granting any trading
or capital authority. A broker cash `MATCH` can no longer suppress a missing
internal order reference. The HTTP and CLI response changes are additive.

This slice has no table migration, history rewrite, configuration/default
change, broker/network call, order submission or partner delivery. It does add
three discrepancy category strings; rollback removes the producer/bridge, but
already appended rows require code that recognizes those values. Bidirectional
economic reconciliation still needs account-scoped internal books, statement
period bounds, universal order IDs, richer immutable fill data and genuine
broker evidence. Focused reconciliation acceptance: **118 passed/21 known
framework deprecations in 6.95s**. Whole engine: **4,090 passed/four skipped/46
known deprecations in 204.15s**; JUnit:
`C:/Users/Urveesh/AppData/Local/Temp/sentinel-f10a-broker-internal-final2-20260919.xml`.
The first whole run exposed an unrelated microsecond clock race in one MTM test
fixture; binding its quote and report to the same instant made that test
deterministic, and the exact final tree passed. Atlas regenerated at 203 Python
modules; changed Python compilation and diff checks passed. Production remains
unchanged. Implementation commit `1dde067` contains source, tests, atlas and
canonical documentation. Its immediate stat/status/guide/plan/atlas review
passed with a clean Dev worktree; push is pending.

## September 19 Workflow C.C2.SOURCE (Dev tested)

The modeled asymmetric path no longer borrows prices from the earlier decision
book. Each missing-leg estimate retains and uses its own archive-verified
packet hash, clock, bid/ask and quantity; incomplete legacy evidence fails
closed. Held-out admission cross-checks the source and recomputes the fill/P&L,
including rejection of a rehashed source mutation. Focused acceptance: **87
passed** with warnings fatal; broader C: **259 passed**; whole engine: **4,070
passed/four skipped/42 known deprecations in 205.51s**. JUnit is retained at
`C:/Users/Urveesh/AppData/Local/Temp/sentinel-workflow-c-source-binding-20260919.xml`.
No schema/config/data migration, broker call, delivery authority, flag change,
or Production edit. Implementation commit: `e2212cb` on
`codex/production-correction-hedge-p0`; verification receipt: `1a97932`. Both
were pushed to `origin/codex/production-correction-hedge-p0`. See
[the plan and receipt](2026-09-19-workflow-c-asymmetric-source-binding-plan.md).

## September 19 Workflow C.C2.HOLDOUT (Dev tested)

The modeled partial CLOSED path is now held-out ingestible and separately
counted, with negative adverse-entry slippage, degenerate-book fail-closed
behavior, strict provenance validation, and qualification propagation. It does
not claim verified full economics. Focused: **90 passed**; qualification and
held-out: **134 passed**; broader Workflow C/research/orchestrator: **226
passed**, one known Starlette warning; whole engine: **4,069 passed/four
skipped/42 known deprecations in 214.71s**. Atlas regenerated at 202 modules.
JUnit is retained at
`C:/Users/Urveesh/AppData/Local/Temp/sentinel-workflow-c-partial-holdout-20260919.xml`.
System Python lacked pytest, so validation used the checked-in Windows venv.
No schema/config migration, retained-data rewrite, external call, delivery,
broker action, or Production mutation. Implementation commit: `6348fdb` on
`codex/production-correction-hedge-p0`; immediate post-commit source/guide/plan/
checklist/atlas consistency review passed with a clean Dev worktree. The
read-only Production checkout remained at `fef35e7` with its pre-existing
untracked audit/migration files untouched. Commits `6348fdb` and `070e9c0`
were pushed to `origin/codex/production-correction-hedge-p0`. Merge/PR, real
held-out collection, qualification, deployment, and partner delivery evidence
remain unchecked.
See [the slice receipt](2026-09-19-workflow-c-partial-holdout-plan.md).

## September16 current-state override

Momentum/CAS release candidate: pushed Dev commit `ee0a300` schedules live momentum auto-square at 15:13 IST, transfers exclusive ownership from the monitor under a shared lock and enforces a 15:14:30 hard submission cutoff. The path checks before stop cancellation and immediately before submission; a pre-submit abort after cancellation attempts and persists replacement protection and pages the operator. Focused suites:79 passed; scheduler/calendar subset after restoring direct wrapper gates:25 passed; final Python:3730 passed/four skipped/42 existing deprecation warnings; agent:338 passed. The completed pytest receipt retained aiosqlite worker processes, and the exact processes were stopped. No schema/config migration, retained-data rewrite, broker call or Production mutation. Merge, deployment SHA and market-session observation remain unchecked.

Dev started clean/pushed at `6c54b78`; Production read-only checkout is merge `967e07a` and all six containers are up (three application containers healthy), but trading readiness remains false because broker order execution is unverified. Dev has eight commits after the deployed source parent, including the Production-found contract-health alert fix. Do not call those deployed. The new manual-card path has zero qualified strategies, artifacts, ideas or delivered cards; current saved profile/inputs and destination configuration do not substitute for genuine qualification.

Independent J negative review found resolver/calendar payload-binding defects after `00dffbd`; pushed Dev commit `97e62e7` now requires an HMAC-bound exact symbol/source/version response, rejects malformed holiday payloads atomically and expires engine-loaded as well as fallback calendars. It also fixes deterministic SUMMARY verification and serializes operational-coverage SQLite initialization to remove intermittent locks. Final verification: Python3725 passed/four skipped/42 existing deprecation warnings in213.57s; native runtime-matching Node424 passed/four skipped; dashboard43 passed plus build; agent338 passed. The completed Python run left aiosqlite worker threads alive after its receipt, so the exact test processes were stopped and clean teardown remains a follow-up. Merge/deploy/staging CAS captures remain pending; no Production file, service, partner channel or broker was mutated.

## September14 independently reviewed correction (Dev only)

G/C protocol source plus real-simulator/temp-SQLite acceptance are corrected; exact late freeze/output retries preserve immutable history, full manifest/cost/source identity is retained, all declared sessions and outcome states appear, seeded cluster CI matches the opportunity-weighted estimand, actual-price turnover replaces quantity-as-turnover, and every profile has explicit baseline/stress research gates. CLI tests isolate standalone `asyncio.run` in a worker thread; no runtime suppression or scheduler changes.

Command from Dev `python-engine`: `.\winvenv\Scripts\python.exe -m pytest tests/test_comparison_protocol_acceptance.py tests/test_research_cli_strategy_comparison.py tests/test_research_cli_qualification.py tests/test_proactive_intelligence.py tests/test_proactive_execution_research.py tests/test_proactive_exit_research.py tests/test_proactive_portfolio_research.py tests/test_trailing_stop_profile.py tests/test_promotion_bridge.py tests/test_range_reversion_profile.py -q -W error`:156 passed/no warnings6.84s, exit0. Full `-m pytest tests -q --junitxml=C:/Users/Urveesh/AppData/Local/Temp/sentinel-g-protocol-reviewed-20260914.xml`: receipt3304 cases/zero failures/errors/four skips173.475s; process teardown still active at inspection, exit/warning summary unconfirmed. Do not call this a clean full run yet.

Source commit8561820; immediate nine-file stat/status review confirms guide/plan/checklist/atlas and actual-source tests are included. Only the two preserved external golden generated-at edits remain dirty. Only new offline tables/triggers, no operational ALTER/history rewrite, no flags/order/transport authority. Preserve existing protocols; incompatible source identities require a newly frozen ID, never rewriting an old manifest. No push/deploy. F/J claimed closure is superseded by [independent findings](2026-09-14-external-work-independent-audit.md); I, real coverage/heldout results, risk preferences, account reconciliation and D release/session acceptance remain pending.

## September 14 J.10.CLOSURE + independent correction plan

J.10 CAS-branch reachability gate closed `ba91dcc` + `414207e`. J.10.CLOSURE operator-facing SUMMARY.md surface closed `c734e4c` (source, +820 lines, +13 new tests pinning SUMMARY contract + happy-path auto-update hook + critical schema-bug fix) + `b8a490e` (docs, +184 lines, J.10 done-doc + SUMMARY.md + plan/atlas/guide sweep). Critical bug fix during J.10.CLOSURE: `_safe_phase_from_capture` was reading `doc["classifier"]["phase"]` and `doc["phase"]` (top level); the J.3 capture schema stores the bounded phase at `rows[i].classifier_phase`. The gate was silently counting every capture as "skipped". Fixed to iterate `rows[]` and read `rows[0].classifier_phase`. Five fixtures in `test_cas_reachability_gate.py` and one fixture set in `test_cas_reachability_summary.py` were using the legacy shape; both files now use the J.3 schema shape. `docs/j2_captures/SUMMARY.md` is the persistent audit surface; the gate currently returns UNREACHABLE because `docs/j2_captures/` has no operator-supplied staging captures — flipping to REACHABLE is operator work (run probe in staging, review captures), per plan §14.

Independent correction plan (`docs/2026-09-14-independent-correction-plan.md`) closed in 5 source commits:

- `050e58a` — F6 fail-closed capital evidence: `loss_tolerance_pct` now `Optional[float]` (default flips to `None`; no more 25.0 fabricated engineering default); CLI never returns `can_grow_live_capital=True`; explicit `authorization_effect: NONE` field documents the diagnostic-only nature. +5 independent regressions (`tests/test_capital_policy_independent.py`).
- `2133a3c` — F3/F4/F5 writer/account/output contracts: `mark_to_market` `qty` is contract units (no double-`lot_size`); `complete_unrealised_pnl` returns `None` on non-FRESH; legacy fno_dr_book rows return `UNSUPPORTED`; `record_from_evidence_report` writes internal ledger facts under `INTERNAL_UNSCOPED_ACCOUNT_ID`; `_row_to_record` exposes `account_attribution`; `_payload_to_import_kwargs` rejects null/blank identity; `'imported'` key removed (operator can't verify the behavioural claim); byte-identical retry pinned. +7 independent regressions.
- `fd450a3` — F3 reporting follow-up + J.5 holiday reconciliation: `penny_hourly_report` renders 'UNAVAILABLE (incomplete/stale quotes)' instead of misleading `Rs +0`; `main.py` uses `complete_unrealised_pnl`; `market_calendar.NSE_HOLIDAYS_VALID_THROUGH = '2026-12-31'` is the documented static-set validity; `routes_holidays.py` exposes `valid_through` in the response. The pre-correction drift signature Python=20/Node=18 is documented as historical; the post-correction state Python=20/Node=20/drift=0/verdict=ALIGNED is pinned. `main_surface_golden.json` regenerated to include the new `routes_market_session` route.
- `00dffbd` — J/H live CAS eligibility + degraded calendar: NEW `routes_market_session.py` is the single authoritative Python projection (`/market-session/cas-eligibility`, authenticated, `source_version` is a SHA-256 hash of the configured CSV); NEW `services/cas-eligibility.js` is the only Node fetch path (short-circuits outside the 15:15-15:29 IST cash-CAS-affected interval via `isCashCasEligibilityResolutionWindow`); NEW `entrySessionVerdict` chains eligibility with `isExecutionAllowed` (unresolved eligibility returns `allowed: false, phase: 'CAS_ELIGIBILITY_UNAVAILABLE'`). `services/executor.js` and `index.js` call `entrySessionVerdict(signalData.ticker, new Date())` BEFORE any DB UPDATE / EXECUTING transition / answerCallbackQuery — `executor.executeSignal` is never reached; no `EXECUTING` status is recorded. The Node `NSE_HOLIDAYS_FALLBACK` is now the exact ISO projection of `market_calendar.NSE_HOLIDAYS_STATIC` (20 dates); `isHolidayCalendarUsable()` fails closed after `NSE_HOLIDAYS_VALID_THROUGH`. +9 new tests; updated `tests/integration/approved-snapshot.test.js` with `cas-eligibility` mock to prevent regressions.
- `64e22a9` — docs + chore: imported `docs/2026-09-14-independent-correction-plan.md`; refreshed session_phase golden timestamps.

**Final defensive regression** at the close of this slice:

- Python J + F + I + cas-reachability surface: **362/362 PASS** (was 3267/4/1 at J.7 close; +19 new tests across F6/F3/F4/F5/market-session; 0 regressions)
- Node full (excl. db.test): **394 pass / 4 skip / 0 fail** (was 385/4/0 at J.10.CLOSURE close; +9 new; 0 regressions)
- Client full: **40 pass / 0 fail** (unchanged; no client changes)
- Working tree: clean
- Branch: `codex/production-correction-hedge-p0`, 438 commits ahead of origin at this slice's close

The J series is now operationally closed (J.1 → J.2.1 → J.2.2 → J.3 → J.4 → J.5 → J.6 → J.7 → J.7-HARDENING → J.8 → J.9 → J.10 → J.10.CLOSURE = 13 sub-slices). F3/F4/F5/F6 are hardened. The only J-related follow-up is operator-supplied staging captures (gate-flip UNREACHABLE → REACHABLE); the only F-related follow-up is operator-signed `BridgeDecision` + actual release validation under D.

J.10 follow-up operator-surface enhancements (post-CLOSURE):
- `12912b1` per-branch captures catalog in SUMMARY + CLI; gate report gains `captures_by_branch: dict[str, list[str]]`; SUMMARY renders a `## Captures catalog` section with sub-headings per branch (zero-capture branches render `(no captures yet)`); CLI human output gains a `captures catalog:` block; CLI `--json` includes the field.
- `37f585f` end-to-end CLI test coverage (9 tests via subprocess) — pins exit codes, `--json` shape stability (exactly 7 keys), `--update-summary` writes SUMMARY.md, `--summary-path` overrides, `--write` persists JSON report.
- `1c35633` per-branch IST-window runbook in SUMMARY — fixed the legacy `--observation-at 15:22:00 IST` syntax bug (the probe CLI doesn't accept it); replaced with a per-branch IST-window cheat-sheet + two ISO 8601 example commands.
- `2b7a670` `--status` flag for shell prompts and monitoring — single-line output, exit code follows verdict, count-driven branch counting (5 captures on 1 branch = 1 branch captured).
- `181f6ee`, `4630131` docs sweeps to reflect the J.10.CLOSURE + independent correction plan + these follow-up enhancements.

Net J.10 follow-up slice delta: python-engine +18 new tests across 4 commits (3 catalog + 9 CLI + 3 runbook + 3 status). All defensive regressions clean: Python 380/380 PASS (was 3267/4/1 at J.7 close, +113 net); Node 394 pass / 4 skip / 0 fail (was 380/4/0 at J.7 close, +14 net); Client 40/40 PASS (no client changes).

I.4.D source-event classification (5 commits across two sessions):
- `c80e3fa`  bounded classifier module: fixed 8-category `NewsCategory` taxonomy (`REGULATORY`, `EARNINGS`, `M_AND_A`, `GUIDANCE`, `MACRO`, `RUMOR`, `TECHNICAL`, `UNKNOWN`); frozen `ClassificationResult` dataclass (ticker, title_hash 12 hex chars of SHA-256, category, confidence ∈ [0,1], bounded rationale ≤ 280 chars, prompt_version, classified_at); `CONFIDENCE_THRESHOLD = 0.6` (fail-closed: below threshold → UNKNOWN); `CLASSIFIER_TIMEOUT_SEC = 1.0` per-item latency budget; never raises (timeout / parse error / disabled / model exception → UNKNOWN + confidence=0.0); fixed taxonomy — a category the model invents (outside the enum) is forced to UNKNOWN; `DISABLE_CLASSIFIER` forces every result to UNKNOWN (offline / CI / sandbox); `_extract_json_object` parser tolerates `<think>...</think>` blocks (MiniMax-M3 reasoning), `\`\`\`json\`\`\`` fences, leading prose, malformed input. 36 module tests pin the contract.
- `d60073b`  verdict-prompt rendering: `analyze_with_minimax` gains an OPTIONAL `pre_classifications: Optional[List[ClassificationResult]] = None` parameter. When supplied, the prompt renders a `CLASSIFIED SENTIMENT DATA` section (above the existing `MULTI-SOURCE SENTIMENT DATA` section) listing `title_hash + category + confidence + rationale` per headline; when None (the default, every existing caller's path), the prompt renders a placeholder text and is byte-identical to its pre-I.4.D shape. The verdict pipeline's existing path is unchanged. 9 integration tests pin the contract.
- `bc0a0a6`  env-flagged helpers: `_fetch_news_items_for_ticker(ticker)` and `_maybe_classify_news(ticker)`. The latter returns `None` when `ENABLE_NEWS_CLASSIFIER != '1'` (default), `[]` when the flag is on but the classifier is disabled / no items fetched / exception raised (fail-closed), or a list of `ClassificationResult` otherwise. Both helpers never raise. The verdict pipeline's failure modes are unchanged. 10 helper tests pin the contract.
- `557de73`  operator CLI: `python -m agent.tools.news_classify_cli --ticker TICKER | --input PATH [--dry-run] [--json] [--limit N]`. Runs without touching the verdict pipeline (lazy-imports `agent.fetch_news_items` only for `--ticker`); exits 0/1/2/3 with structured diagnostics. 21 CLI tests pin the contract.
- `099907d`  async-queue extension: `AsyncReviewQueue._Task` gains a frozen `pre_classifications: tuple = ()` field; `submit()` gains a `pre_classifications: Optional[List[ClassificationResult]] = None` kwarg; the worker inspects the reviewer's signature via `inspect.signature` and forwards the kwarg when supported, falling back to the original 3-arg shape when not (backwards-compatible with the existing lambda-reviewer test suite). The call sites at lines 1393/1599 of `agent.py` now compute `pre_classifications = _maybe_classify_news(ticker)` and forward it to both `queue_optional_ai_review` and the synchronous `analyze_with_minimax` fallback. **`ENABLE_NEWS_CLASSIFIER=1` now fires end-to-end through the momentum async path AND the synchronous fallback.** 6 async-queue tests pin the contract.

Net I.4.D slice delta: agent suite 213 → 259 (+46 across 5 commits: 36 module + 9 integration + 10 helper + 21 CLI + 6 async-queue). All defensive regressions clean: Python 380/380 PASS (no Python-engine changes); Node 394 pass / 4 skip / 0 fail (no Node changes); Client 40/40 PASS (no client changes); agent 259/259 PASS.

The I.4.D slice is the only plan-§13 explicit gap that previously had no implementation. With this slice, the I-series bounded-annotation surface is complete for `summarize` (I.2 + I.B) + `identify-missing-evidence` (conviction) + **`classify` (I.4.D)**. Remaining I.4 opportunities (E: periodic self-evaluation; G: per-ticker breakdown) are explicitly deferred per the I.4 deep-research doc and the plan-§13 contract (operator-supplied ground truth).

## Read order

0. **[2026-09-14-inheritance-i4d-handoff.md](2026-09-14-inheritance-i4d-handoff.md)** — the comprehensive handoff binder for the next session. Covers current state, what landed in this session, the user's repeated mantras (verbatim), senior-dev protocols, the vision, files NOT to touch, session-search anchors, and stopping criteria. **READ THIS FIRST.**
0a. **[2026-09-14-i4e-contract-health-done.md](2026-09-14-i4e-contract-health-done.md)** — the I.4.E bounded contract-health self-evaluation done-doc (the slice that closed "guard the guards"; 5 invariants + read-only CLI; agent suite grew 259 → 312).
0b. **[2026-09-14-j10-dedup-done.md](2026-09-14-j10-dedup-done.md)** — the J.10.DEDUP done-doc (capture-fingerprint dedup on the J.10 gate; the gate now counts unique observations per branch; duplicates surfaced for audit but do not inflate the verdict; python-engine narrow regression surface 364 → 404).
0c. **[2026-09-14-j10-freshness-done.md](2026-09-14-j10-freshness-done.md)** — the J.10.FRESHNESS done-doc (`--captures-since <DAYS>` filter + `captures_skipped_stale` report field; the gate now defends on three axes — bounded phase, unique observation, fresh evidence; python-engine narrow regression surface 404 → 434).
0d. **[2026-09-14-j10-min-threshold-done.md](2026-09-14-j10-min-threshold-done.md)** — the J.10.MIN_THRESHOLD done-doc (`--min-unique-per-branch <N>` threshold filter + `min_unique_per_branch` report field; the gate now defends on four axes; python-engine narrow regression surface 434 → 454).
0e. **[2026-09-14-j10-capture-summary-aggregate-done.md](2026-09-14-j10-capture-summary-aggregate-done.md)** — the J.10.CAPTURE_SUMMARY_AGGREGATE done-doc (per-day histogram + `captures_per_day` field + `## Captures per day` SUMMARY section; evidence velocity over time; python-engine narrow regression surface 454 → 474).
0f. **[2026-09-14-j10-write-atomic-done.md](2026-09-14-j10-write-atomic-done.md)** — the J.10.WRITE_ATOMIC done-doc (atomic + byte-identical JSON write for the gate's audit trail; mirrors the F5 `reconciliation_cli._write_output_atomic` discipline; python-engine narrow regression surface 474 → 487).
0g. **[2026-09-14-j10-capture-listing-done.md](2026-09-14-j10-capture-listing-done.md)** — the J.10.CAPTURE_LISTING done-doc (`--list-captures` CLI flag + `list_captures`/`format_listing` helpers + `i10-capture-listing-v1` schema; fast, side-effect-free audit tool; python-engine narrow regression surface 487 → 510).
0h. **[2026-09-14-j10-branch-histogram-done.md](2026-09-14-j10-branch-histogram-done.md)** — the J.10.BRANCH_HISTOGRAM done-doc (per-branch-per-day matrix + `branch_per_day` field + `## Captures per branch per day` SUMMARY section + `--show-branch-histogram` CLI flag; evidence density per branch per day; python-engine narrow regression surface 510 → 527).
0i. **[2026-09-14-i4e-cron-wiring-done.md](2026-09-14-i4e-cron-wiring-done.md)** — the I.4.E.CRON_WIRING done-doc (`contract_health_cron_tick` + hourly `schedule.every(1).hours.do` registration in `agent.py` + double try/except fire-and-forget guard + Telegram alert on violation; the I.4.E harness now self-policing; agent suite 312 → 325).
0j. **[2026-09-14-j10-summary-verify-done.md](2026-09-14-j10-summary-verify-done.md)** — the J.10.SUMMARY_VERIFY done-doc (`--verify-summary` CLI flag + `verify_summary`/`DiffKind`/`VerificationReport` helpers + byte-identical drift detection + `GENERATED_AT_DIFFER` (benign) vs `BYTES_DIFFER` (real) distinction + mutually-exclusive refusal with `--update-summary`; drift detection that never overwrites; J.10 surface 220 → 244).
0k. **[2026-09-14-j10-capture-oldest-newest-done.md](2026-09-14-j10-capture-oldest-newest-done.md)** — the J.10.CAPTURE_OLDEST_NEWEST done-doc (`oldest_newest_per_branch` + `format_recency_table` + `recency_by_branch` field + `## Captures recency per branch` SUMMARY section; per-branch timestamp range for stale-evidence + single-day-cluster + wide-span detection; first-occurrence-paths filter for dedup consistency; J.10 surface 244 → 272).
1. [SYSTEM_GUIDE.md](SYSTEM_GUIDE.md): feature architecture, authority boundaries, before/after improvements and limitations.
2. [SYSTEM_CODE_ATLAS.md](SYSTEM_CODE_ATLAS.md): 171 top-level engine/agent Python modules plus gateway/dashboard source navigation, declarations, dependencies and tables (September14 regeneration; +1 module after the I.4.D slice: `routes_market_session.py` was added in the J.7-HARDENING commit, then `agent/news_classifier.py` in `c80e3fa`).
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
| `760c086` | Predeclared criteria, source-bound stress economics and close-ordered drawdown |
| `e1c6687` | Master-proven public futures/roll scope and exact delayed-execution boundaries |
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
- Full-policy outcomes now enter held-out aggregation through a verified deployed-evaluator report, manifest and same-observation cost artifact. Ordered drawdown and exact declared stress gates are implemented. Real cost calibration, contemporary entry-quality checks and adequate real-session coverage remain unfinished.
- CAS/session-phase correctness needs official-source-backed review across engine, gateway and research.
- Negative earlier performance and accounting discrepancies need forensic/reconciliation work.
- No actionable partner strategy was qualified by this work. No fixed tip-start date can be given.

## First next action

F correction source `e00874b`; immediate eleven-file stat/status review confirms clean Dev, matching source/guide/atlas/plan and independent review incorporated. Local only, not pushed/deployed. Next implementation: genuine G/C predeclared comparison protocol and evidence validation; F forensic/account/statement inputs remain unresolved, not closed by this inventory correction.

Latest whole-engine receipt (F provenance/cache/budget source): `.\winvenv\Scripts\python.exe -m pytest tests -q --junitxml=C:/Users/Urveesh/AppData/Local/Temp/sentinel-fg-provenance-baseline-20260913.xml` from Dev engine returns0: **2,703 passed/four skipped/23 existing deprecations,126.20s**. Supersedes previous whole-engine counts. Runtime/assertions frozen; F explanatory test docstring alone edited during run. Independent F review finds no correctness blocker with existing route-import deprecation visible. Not qualification, real reconciliation, deployment or actual backup compatibility.

F source/provenance correction: unknown equity tariff effective date restored with rates/version/as-of/options untouched; owning schemas/PKs, writers, settings and unsupported A1–A5 closure claims corrected. Eight-file acceptance150 passed with all warnings fatal6.48s; ten-file154 passed7.07s with one existing Starlette deprecation and ResourceWarning/unraisable warnings fatal. Fresh DB fixtures exercise real initializers and broker import; not deployed-data reconciliation. Full engine rerun in progress; source frozen. Independent final review pending. See F/G correction plan; local only, no Production/remote mutation.

Approval-budget source commit `2cbe1a3`; immediate seven-file stat/status review confirms clean Dev and matching guide/atlas/plan. Independent final bridge review passes 65 tests with warnings fatal, no blocker. Local only, not pushed/deployed; required genuine evidence validation remains open.

Approval-budget/validity follow-up: twelve-file F/G suite **180 passed**, no warnings, 6.60s, current Dev winvenv with `-q -W error`. Required predeclared amount/DD/expiry, type/finite bounds, original half-open validity window, stale/legacy reads, exact expiry, whitespace signer and malformed historical signature regressions pass. No schema/default/order/transport changes. `approval_usable=False` remains explicit until genuine frozen held-out/account/F/D evidence is validated. Source commit pending; no push/deployment. Next: actual comparison/evidence validation and bounded F provenance/schema corrections, not a declaration of full G acceptance.

Exit-cache source commit `dd60b0c`; immediate seven-file commit/status review confirms clean Dev and matching documentation. Next correction is approval budget/evidence/expiry validation; F evidence corrections and faithful range comparison remain open. Local only, not pushed/deployed.

Exit-cache integrity follow-up: ten-file proactive/G suite **137 passed**, warnings fatal, 5.99s, current Dev winvenv. Retained v3 companion manifests bind full effective proposal/clock/cost/bar/evaluator identity; the result table retains its previous four columns and all legacy rows. Compatible concurrent retries remain idempotent; conflicting reuse fails. Old four-value writer shape tested on an isolated database, not actual deployed-data compatibility. No Production ops/remote promotion. See F/G correction plan for exact command and remaining approval/range/F evidence work.

Trailing-composition source commit `5bede72`; immediate seven-file stat/status review confirms clean Dev and matching guide/atlas/plan. Local only; no Production or remote promotion. Next implementation: separate exit-cache full proposal/clock/implementation identity, then remaining approval-validation and F evidence corrections.

Trailing-composition follow-up: root ten-file proactive/G command with `-q -W error` passes **121 tests**, no warnings, 5.53s; Terra independently approves causal entry/limit/confirmation/exit dispatch and retained primary-run immutability. Full current engine `.\winvenv\Scripts\python.exe -m pytest tests -q --junitxml=C:/Users/Urveesh/AppData/Local/Temp/sentinel-fg-trailing-baseline-20260913.xml` from Dev `python-engine` returns0: **2,656 passed/four skipped/23 existing Starlette-httpx deprecations**, 124.91s, source frozen during run. This supersedes earlier whole-engine counts and includes the parallel F/G changes plus current fixes; it does not validate unsupported strategy/governance claims. Exact scoped command and remaining exit-cache identity/bridge approval/range/F evidence gaps: `2026-09-13-fg-independent-correction-plan.md`.

Independent-review terminal-state source commit `13fb426`; immediate seven-file stat/status confirms clean Dev and matching documentation, local only. Remaining audit corrections are explicit in the F/G correction plan; terminal-state acceptance does not accept the entire governance bridge or strategy basket.

User-requested independent F/G audit found concrete bridge terminal-state and trailing-dispatch defects plus unsupported F provenance/schema/closure claims. First atomic bridge correction passes **81 tests** in the seven-file F/G group with `-q -W error`, 1.63s, Dev engine winvenv; six new regressions cover terminal amendment, reverse transition, concurrent first decisions and backdated append clocks. Full approval validation/trailing composition/F evidence corrections remain required; see `2026-09-13-fg-independent-correction-plan.md`. No live permission inferred.

Optional annotation validity source commit `59e915a`; immediate seven-file stat/status review confirms clean Dev and matching guide/atlas/plan, local only. Final focused Windows validity tests 14 passed with all warnings fatal in 1.14s.

I validity slice: `2026-09-13-optional-ai-validity-plan.md`; READY/CACHED no longer outlive original/shortened validity or cache TTL, exact-deadline results discarded, nested signal inputs snapshotted. Current isolated agent suite **98 passed**, warnings fatal, 2.10s: `docker run --rm --pull=never --network none --entrypoint python --mount type=bind,source=C:\Users\Urveesh\Desktop\trading-sentinel\agent,target=/app,readonly trading-sentinel-agent-test:latest -m pytest tests -q -p no:cacheprovider -W error`. No credentials/Production mounts, all helpers removed automatically. This is not complete I provenance/news usefulness. F/G are being independently audited at user request; do not overwrite the other agent's implementation.

Refreshed target/default review: [September 13 release target review](2026-09-13-release-target-review.md). Dev merge `7150ac7` non-destructively reconciles target `954e25a`; pre/post tree identical, clean status and target ancestor verified. The historical triple-dot inflation is resolved without source changes or force push. Docker/Compose/ledger migration code match the refreshed target. Partner delivery defaults are enabled in both versions: explicitly verify effective passive rollout switches, never claim disabled-by-default. Local only, not pushed/deployed.

Latest whole-engine receipt on Dev `0f3a2a0`: `.\winvenv\Scripts\python.exe -m pytest tests -q --junitxml=C:/Users/Urveesh/AppData/Local/Temp/sentinel-d-final-baseline-20260913.xml` from `python-engine`: **2,569 passed/four skipped/23 existing deprecations, 121.31s**, exit0. Supersedes earlier whole-engine count; not deployment or strategy qualification.

Review the complete Dev release diff/defaults and prepare the GitHub PR; resolve actual authorized quiescence/backup/restore and previous-code compatibility using the consistent-backup runbook. Production application containers were observed stopped, with no implicit restart; user was asked whether deliberate. C's boundaries and baseline/resource fixes are tested in Dev. Preserve the working CLI and immutable v1/v2/v3 artifacts; do not infer deployment or qualification.

## September 13 backup/rollback safety verification

Source commit `cd92830`; immediate post-commit stat/status review confirms the eight-file tool/runbook slice and clean Dev worktree. Local only, not pushed or deployed.

`2026-09-13-consistent-backup-plan.md` and `consistent-data-backup-runbook.md` define full-tree/WAL capture, explicit exclusive maintenance ownership, no operational deletion and rollback that preserves newer history. Offline `scripts/verify_data_backup.py` verifies exact retained inventory/hash and SQLite integrity in scratch, never claims live consistency. Root reviewed Terra's implementation and corrected directory-only iteration, source-enumeration bounds/errors, parent case aliases and weak/optional test setup. Independent Luna audit inventories stores/retention/migration hazards incorporated in runbook.

Final Windows command from `python-engine`: `.\winvenv\Scripts\python.exe -m pytest tests/test_data_backup_verification.py tests/test_deployment_verification.py tests/test_performance.py tests/test_partner_collection_attempts.py tests/test_research_leg_subscriptions.py tests/test_partner_research_capture.py -q -W error`: **117 passed, one symlink-privilege skip, no warnings**, 5.01s. Backup/deployment subset: 29 passed/one skip. WAL source connection remains open through capture; fixture byte snapshot confirms no source mutation and recovered ledger row. Missing WAL, matching corrupt SQLite, tampering, traversal/Windows aliases, hardlinks/devices, duplicate members/root, bounded expansion/enumeration, changing source/archive and receipt overwrite have negative tests. Receipt overwrite is not hidden by optional symlink skip.

Documented helper commands were checked with dummy data, cached Python3.11-slim and Alpine images, `--pull=never --network none`, no Production volume: inventory → Alpine `tar -C /source -cf /backup/data.tar .` → verifier all return exit0. Retained fixture/receipt: `C:/Users/Urveesh/AppData/Local/Temp/sentinel-d-backup-native-20260913`. This proves CLI/native-tar compatibility, not an actual Production restore. The existing engine image lacks pytest; no dependencies were installed into it, and native command smoke replaced that unavailable cross-platform test environment. Atlas regeneration unchanged at 155 modules, compilation and diff check pass.

Read-only Docker snapshot: actual `/data` volume `production_trading-sentinel_trading_data`; engine/gateway RW, agent RO; all three stopped exit137, OOMKilled=false around 01:01 UTC. Autoheal/nginx/ngrok run. No root stop/restart or Production edit occurred. This state is not a quiescence/maintenance receipt. Actual backup, isolated restore on actual data, old/new complete compatibility, PR/release and real market-session evidence remain outstanding.

## September 13 resource ownership verification

Source commit `93ce675`; post-commit behavior/documentation consistency checked with clean Dev status. Local only, not pushed/deployed.

`2026-09-13-resource-clean-release-plan.md`: native Node 20 Alpine gateway `./node_modules/.bin/jest --runInBand --detectOpenHandles` passes **324 tests/four skipped** (25 suites passed/one skipped) in 16.927s and returns exit 0 naturally, with no detected open handles. Networking was disconnected after npm ci; current Dev source was recopied before acceptance. Focused token/dead-letter tests: 15 passed, natural exit. Original-code negative controls: fetch-rejection cleanup fails with one remaining timer; stalled-body regression fails by timeout. Neither working source nor Production was reverted for these controls; only a scratch container copy was replaced. Logs retained in the user Temp directory as `sentinel-d-resource-gateway-20260913.log`, `sentinel-d-timer-negative-20260913.log`, and `sentinel-d-body-negative-20260913.log`. Scratch container and original-source temp helper were removed; no operational volume was attached/deleted.

Python: Terra isolates `test_option_lookup`'s manual loop; root converts it to pytest-managed async. Original four-file instrument/scanner/full-policy/multisession command with `-W error`: **32 passed**, no warnings, 3.41s. Broader 15-file research/qualification/archive/orchestrator group with `-W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning`: **181 passed**, one existing Starlette deprecation, 7.83s. No warning suppression or global loop fixture added. Earlier full Python baseline remains 2,545 passed/three skips; only the equivalent test loop changes after that whole-suite run. Changed JS syntax checks/Python compilation, atlas regeneration (unchanged 155 modules) and diff check pass. This is TESTED_DEV; D release/real evidence still incomplete.

## September 13 D acceptance baseline

Implementation commit `f7e33cb` restores the full acceptance baseline. Post-commit source/docs diff and clean Dev status were checked. Atlas regeneration remains identical at 155 modules. This is local Dev only, not pushed/released.

Plan/evidence: `2026-09-13-release-baseline-plan.md`. Full Dev engine command: `.\winvenv\Scripts\python.exe -m pytest tests -q --junitxml=C:/Users/Urveesh/AppData/Local/Temp/sentinel-d-baseline-20260913.xml` from `python-engine`: **2,545 passed, three skipped, 23 existing Starlette/httpx deprecations in 126.27 seconds**. This supersedes the earlier 17-failure baseline. No tests were excluded or marked xfail to hide failures.

The corrected fixture/source-guard/default group passes 148 tests (one skip, one existing Starlette warning). Migration regression preserves legacy rows, exercises repeat initialization and retains new close provenance. Momentum's helper mirrors the migrated column because both sync and async tests call it; division/audit fixtures call the real migration. Scheduler/isolation passes 41 tests with RuntimeWarning fatal (one existing Starlette deprecation). Dashboard passes 25 unit tests and Vite build (existing Browserslist warning); agent passes 91 tests in the existing test image with networking disabled and current Dev source mounted read-only. Runtime accounting, flags, clocks and transport authority did not change.

Gateway: **318 passed/four skipped** (25 suites passed/one skipped), 17.739 seconds, temporary Node 20 Alpine native-SQLite environment. Dependency installation uses no repository `.env` or persistent volumes; the acceptance rerun disconnects networking after installation. The existing script uses forceExit and detects two open handles: token-restore timer on fetch rejection and fake-token Telegram polling in alert-dead-letter tests. Log: `C:/Users/Urveesh/AppData/Local/Temp/sentinel-d-gateway-20260913.log`. The temporary container was removed after preserving its log, with no operational volumes involved. No actual partner message or broker order was requested or submitted. The Windows combined all-warning-fatal socket investigation is still pending. No Production edits, push, merge or deployment occurred.

## A/B implementation verification

- Focused Python acceptance: 185 tests passed across decision clocks, collection attempts, chain/scanner, captures, qualification/replay, orchestrator, archive readiness and authenticated hedge routes. The 64 pure-path tests passed with all warnings treated as errors; the integration group retains one pre-existing Starlette lifespan deprecation warning.
- Scheduler/isolation acceptance: 41 tests passed with `RuntimeWarning` treated as an error. The previously documented unawaited `_run_penny_edge_scan_safe` coroutine warning is fixed; registration now checks for a running event loop before constructing the coroutine.
- Dashboard: 25 unit tests passed and the Vite production build passed. The existing outdated Browserslist database warning remains.
- Gateway: all 317 tests passed (4 skipped) in a clean Node 20 Alpine container; the focused updated proxy contract passed 15 tests. Existing forced-exit/open-handle and Telegram-library warnings remain. Agent: 91 tests passed in the existing Production agent image with networking disabled.
- Latest full Python repository rerun after the hardened C economics slice: 2,514 passed, 3 skipped and the same 17 failures, with 23 deprecation warnings and no unawaited-coroutine warning. The failures were outside the changed path: legacy test-created `bankroll_ledger` schemas omit `origin_ref`; the declared `PARTNER_BOT_ENABLED` default is already `True` while an older test expects `False`; several Windows source-inspection tests use CP1252 instead of UTF-8; and affected momentum-paper assertions cascade from the legacy ledger fixture. The 17 failures still prevent `RELEASE_VALIDATED` status even though the focused slices are green.
- Production remained read-only. No container was started, no message/order was sent, and no qualification was registered.

## C replay-fidelity verification

- Source/execution-boundary acceptance: v3 futures scope is independently proven against raw/canonical dated master evidence, including the complete front/roll expiry selection. Legacy/caller-supplied inputs cannot claim verified held-out provenance. The unmocked multi-session fixture now uses retained public captures rather than caller price dictionaries.
- Exact entry/management instants, excluded same-day option expiry, fill-timestamp embedded cancellation, delayed public-age checks, liquidity/quantity/cost-inclusive reward gates, unrelated archive packets and nonnegative gross-notional slippage have focused regressions. Missing, partial and late exits preserve unresolved exposure. Finalized quote segments require manifest integrity.
- The expanded focused group passes 143 tests, including rejection of decision bars not bound to a supplied capture and a forged scope that omits the actual front future. The final broad C/research/orchestrator group passes 185 tests. The combined warning-fatal run exposes an unclosed Windows asyncio socket during test-group transitions; isolated full-policy/multisession warning-fatal acceptance passes 15 tests. This warning is not silently suppressed and requires baseline investigation in D. Follow-up subagent review attempts failed on account usage limits; the earlier read-only findings were incorporated and locally checked.
- Source-final repository comparison: 2,526 passed, 3 skipped, the same 17 documented failures and 23 warnings in 122.40 seconds. The final additional decision-frame negative test passes in the 143/185-test groups. This is no new source-path regression, not release validation; the baseline failures and remaining gateway/dashboard/agent acceptance must be addressed in D.

- The unmocked two-session fixture uses the real deployed evaluator, verified raw/canonical contract master, hashed raw quote packets, archive adapter, chronological replay and held-out aggregator. It produces one finite costed close and one unresolved accepted entry; neither result can grant qualification, delivery or order authority.
- Distinct valid same-leg packets at one receipt are now explicit conflicts independent of input order. Exact duplicate retries remain idempotent, and a relevant conflict produces `decision_book_conflict` rather than a conveniently selected book.
- Verified full-policy reports can enter held-out review through a strict adapter. Report/manifest tampering, simplified evaluators, conflicting states and malformed identities are rejected.
- Changed C acceptance: 28 tests passed warning-free. The broader full-policy/research/qualification/archive/orchestrator group passed 139 tests with one pre-existing Starlette async-generator lifespan deprecation warning.
- Full-policy reports now always retain a fingerprinted baseline plus caller-declared fee/slippage scenarios calculated from identical observations. Held-out aggregation revalidates full nested artifacts/source identities, sorts realised outcomes by timezone-aware close clocks, retains individual economics and computes sequential drawdown. Qualification review requires a policy/profile-bound immutable criteria manifest frozen before holdout, exact stress coordinates, unique outcome identities and matching non-closed states; legacy evidence remains readable but receives blockers. After independent invariant/test audits, the expanded focused group passes 61 tests warning-free and the broader group passes 151 tests with the same Starlette warning.

## User-facing clarity

The system is better at preserving and testing what it actually observed and proposed. It is less likely to manufacture a historical fill or hide a missing exit in research. Those are prerequisites for finding a real edge, not proof that an edge has been found. The partner's saved intraday profile is a setup input, while qualification and Telegram delivery are separate checks.

## Commit ritual

Before the next implementation: update the plan slice. With each commit: update the guide/atlas/plan and verification evidence. After each commit: verify the actual diff and documentation agree. Instructions are also in Dev AGENTS.md so the ritual survives this conversation.
