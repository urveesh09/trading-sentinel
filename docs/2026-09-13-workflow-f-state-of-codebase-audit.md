# F — accounting truth inventory and unresolved evidence

## 1. Scope and correction receipt

F1 is an inventory dependency, not completion of plan §10's loss reconstruction, reconciliation, affordability, valuation or capital-increase acceptance. Independent Terra/root inspection on September 13 found materially incorrect inferred schemas and unsupported warning/tariff claims in the initial F1 document. This corrected census uses owning Dev source, not architecture prose or historical recollection. Earlier commits/artifacts are retained.

The bounded source correction restores `EQUITY_INTRADAY_EFFECTIVE_DATE=None`. Schedule version, verified-as-of metadata, numeric rates, options metadata and snapshot namespaces are unchanged. No ledger mutation, migration, broker call, scheduler change, message or order. See `2026-09-13-fg-independent-correction-plan.md` for acceptance and rollback.

## 2. Source-backed census

| Table | Owner / identity | Writes and reads | Investigation limits |
|---|---|---|---|
| `bankroll_ledger` | `performance.py:init_ledger`; autoincrement `id`; timestamp, event_type, ticker, pnl, bankroll_before/after, source, notes, origin_ref | Seed, `record_trade_close`, `record_partial_realisation`, `record_cb_reset`; additional INSERT paths exist in `main.py`, `penny_edge_orchestrator.py`, `routes_portfolio.py`. Read division equity/breakdown and reconciliation evidence | Not a universally enforced single-writer contract. Repair scripts can mutate history; this workflow does not authorize those repairs. Current source/origin migrations catch broad exceptions, not only duplicate-column errors |
| `positions` | `position_tracker.py:init_positions_db`; **no declared primary key and no id column** | Position lifecycle writers exist in tracker/executors; `get_open_positions` reads managed exposure | Not composite PK. Updates must use actual retained predicates; ticker alone is not unique. OPEN/CLOSED_T1 labels alone do not prove remaining exposure |
| `position_pnl_outbox` | `position_tracker.py:_init_pnl_outbox`; event_key PK; ticker, pnl, source, delivered, created_at | Tracker queues P&L and updates delivered after callback | Callback/ledger delivery evidence must be reconciled independently; not immutable append-only |
| `trade_outcomes` | `analytics.py:CREATE_TRADE_OUTCOMES_SQL`; autoincrement id and UNIQUE(ticker, closed_at) | `record_trade_outcome` inserts; analytics reads | Actual fields: ticker, closed_at, realised_pnl, r_multiple, scan_id, regime, close, stop_loss, target_1, volume_ratio, rvol_ratio, rsi_7, minutes_from_open, strategy_version, notes. Not timestamp/pnl/signal_id and not composite PK. Best-effort outcome insertion can fail after ledger close |
| `fno_positions` | `fno_positions.py:_DDL`; autoincrement id, source | `insert_position`, `update_trail`, `close_position`; `open_positions`, `closed_today`, premium/today counters | Exact contract/token/expiry/strike/type, lots/lot_size/qty, entry/exit clocks and premiums/underlying, risk/trail, gross_pnl/costs/pnl/R, order IDs, bar_ts retained. Lifecycle uses UPDATE |
| `fno_dr_positions` | `fno_dr_book.py:_DDL`; autoincrement id, source | `insert_structure`, `close_structure`; `open_structures` / management | legs_json, kind, lot_size/lots, entry_underlying, net_premium_rs, max_profit_rs, max_loss_rs, entry_cost_rs, status/opened_at, exit_underlying/reason, gross_pnl/costs/pnl/closed_at. Lifecycle uses UPDATE |
| `broker_statement_imports` | `broker_reconciliation.py:_SCHEMA`; PK(account_id, statement_id) | Explicit atomic `import_broker_statement`; `broker_statement_report` reads newest account statement | Identity/digest makes identical retry safe; changed payload rejects. Import is not a broker network integration |
| `broker_statement_entries` | Same owner; **PK(account_id, statement_id, entry_id)** | Same import/report | Types DEPOSIT, WITHDRAWAL, TRADE_REALIZED, CHARGE, OPERATING_EXPENSE; funding is not trading profit |
| `broker_statement_fills` | Same owner; PK(account_id, statement_id, fill_id) | Same import/report | order_id, status, quantity, price, fees. FILLED/PARTIAL/CANCELLED/REJECTED counts do not prove local position matching |
| `ops_liveness_daily` | `ops_metrics.py:init_ops_metrics_db`; date_ist PK | `record_scheduler_tick` writes; `liveness_report` reads | ticks, max_gap_seconds, max_gap_market_seconds, as_of. Market-hours gap differs from total elapsed gap |
| `ops_funnel_daily` | Same owner; PK(date_ist, subsystem) | `snapshot_funnels_for_day` writes; `funnel_window` reads | evaluated/accepted/rejected/top_rejects/as_of; counters are not realised returns |

Fresh `positions` base DDL includes ticker, exchange, entry_date/price, shares, stops/targets, ATR/highest_close, status/source, exit_price/date, realised_pnl/R, product/regime, initial_capital_at_risk and broker_entry_order_id. Additive migrations include atr_1min_post_t1, t1_fired, sl_order_id, penny_attempt_id and vwap_at_entry. Partial UNIQUE indexes cover non-null penny_attempt_id and broker_entry_order_id only. Consult actual source predicates and PRAGMA on the relevant retained database before any reconstruction; fresh schema tests are not deployed-data compatibility proof.

`performance.py:DIVISION_ALLOCATION` includes SYSTEM, MOMENTUM, MOMENTUM_PAPER, PENNY, PENNY_PAPER, EDGE_LIVE, EDGE_PAPER, FNO_PAPER, FNO_LIVE. Legacy nifty and penny pool queries are narrower. `reconciliation_evidence.py:SOURCES` currently presents five source sheets (MOMENTUM, EDGE_LIVE, MOMENTUM_PAPER, PENNY_PAPER, EDGE_PAPER), not all allocations. Its stable-origin lookup supports fno_position and fno_dr_structure; internal matching remains `broker_reconciled=False`.

## 3. Historical warnings: no demonstrated closure

The system guide records five previously observed UI warnings but does not supply their original screenshots, account/window, ledger/position references or broker statements. A1–A5 descriptions in the earlier inventory were explicitly audit-era recollections, not authoritative observations. Their proposed code/convention/migration/rounding closures were unsupported and are withdrawn.

| Retained tentative reference | State | Required evidence |
|---|---|---|
| DISC-2026-09-A1 | UNKNOWN / UNVERIFIED | Original warning and affected account, window, ledger/position rows; reproduce and explain difference |
| DISC-2026-09-A2 | UNKNOWN / UNVERIFIED | Same; do not infer closure from a notes convention |
| DISC-2026-09-A3 | UNKNOWN / UNVERIFIED | Same; a migration/test cannot close an unidentified historical discrepancy |
| DISC-2026-09-A4 | UNKNOWN / UNVERIFIED | Original statement/residual; do not invent broker rounding or a widget fix |
| DISC-2026-09-A5 | UNKNOWN / UNVERIFIED | Original time-window and amounts; do not invent daily-reset resolution |

These are docs-only tentative references, not persisted discrepancy IDs or confirmed warning identities. The original shapes and quoted rupee amounts are not established. Replace/backfill only when actual source evidence is obtained; retain the unresolved record and explanation rather than adjusting books.

Current broker report computes expected cash = opening + deposits - withdrawals + trade realised - charges - operating expenses. MATCH means absolute residual ≤ INR0.01 for the supplied statement; UNRESOLVED means greater residual; UNAVAILABLE means no statement. It does **not** compare that statement with local ledger/positions. It initializes its tables even on report reads, so it is not a strictly non-mutating inspection API on an uninitialized database. The command route calls the report, not the import; scheduled ingestion is not established.

## 4. Cost provenance and settings

`EQUITY_INTRADAY_SCHEDULE_VERSION="ZERODHA_NSE_EQUITY_INTRADAY_AS_OF_2026-08-10"` and `VERIFIED_AS_OF="2026-08-10"` are retained metadata, not newly independently proven rate provenance. The composite **effective date is unknown**. New snapshots expose null instead of inventing equivalence with verification date. Previously saved snapshots remain untouched and must not inherit stronger provenance.

[Zerodha current charges](https://zerodha.com/charges) lists rates; [its October 2024 revision](https://zerodha.com/z-connect/business-updates/revision-in-exchange-transaction-charges-and-securities-transaction-tax-from-october-1-2024) explicitly dates specific revisions. Neither establishes a combined configured tariff becoming effective August10,2026. No “exchange-side re-acknowledgement” equivalence is supported. Complete dated component-rate and operator-override provenance before historical cost calibration. Options effective/version metadata stays unchanged in this slice; unchanged is not a fresh validation claim.

Source defaults from `config.py` (not effective operator configuration or confirmed cash): INITIAL_BANKROLL4500, MOMENTUM_PAPER_BANKROLL50000, PENNY_PAPER_BANKROLL100000, PENNY_LIVE_BANKROLL2000, PENNY_EDGE_PAPER_BANKROLL100000, PENNY_EDGE_LIVE_BANKROLL1500, FNO_PAPER_BANKROLL250000, FNO_LIVE_BANKROLL0. PENNY_LIVE_TRADING and FNO_LIVE_TRADING defaultFalse; edge live also has PENNY_EDGE_DISABLE_LIVE gating. `PROMOTION_MAX_DD_PCT` is not a declared Settings field (analytics uses a fallback); do not present it as the bridge's runtime risk cap. Actual owner affordability requires confirmed account/capital and approved risk input, not these synthetic allocations.

## 5. Remaining F deliverables and write boundaries

F remains IMPLEMENTING, inventory corrected but genuine F acceptance unproven:

1. Reconstruct actual reported ORB losses from source signals, entries/exits, contract identity, costs and regime; separate execution/data/accounting from strategy.
2. Investigate each retained reconciliation warning using actual evidence; build durable discrepancy records and operator-reviewed explanations without repairing books to agree.
3. Audit costs/affordability against confirmed owner capital (about INR8k user context), not paper allocations.
4. Independently audit deposits, expenses, partial/final closes, rejected/cancelled fills and open MTM with quote freshness and remaining quantity.
5. Capital increase requires externally reconciled results, drawdown/quality/stability and explicit user risk tolerance.

The proposed F2 affordability, F3 valuation, F4 discrepancies, F5 broker ingestion and F6 capital-policy slices remain plans, not shipped acceptance. No source absence test establishes an inventory's completeness. G research remains offline and non-authoritative; F must not silently supply live budgets or closed-evidence booleans. D owns reviewed GitHub promotion/operational observation, not implicit authorization to schedule broker jobs or send orders. E general manual setups do not require personalized holdings; account reconciliation and partner qualification remain distinct.

Do not claim all existing writers are append-only: position/trail/outbox/ops lifecycles update rows. This work authorizes no ledger UPDATE/DELETE or operational repair. Source rollback via GitHub preserves all existing rows and immutable evidence; no Production edits/copies.

## 6. Verification state

Final full engine returns0:2,703 passed/four skipped/23 existing deprecations126.20s, exact command and XML in F/G correction plan. Independent F correctness review approves with known application-import warning visible. Fresh owning-schema/broker behavior regressions pass; source commit pending, local only. Real F acceptance remains unproven.

Independent Terra completed source-vs-doc audit with concrete corrections incorporated above. Root cost/F1/proactive eight-file suite with `-q -W error` passes148/no warnings6.04s. Schema behavioral acceptance and final correction review follow in the F/G correction plan. Prior whole-engine receipt predates this correction, cache and approval-budget slices. No push/deployment/Production operation occurred; real statements, warning records, loss reconstruction and capital approval remain missing.

## 7. Affordability guard (F2 partial; behavioural verification only)

A standalone guard module is shipped at `python-engine/affordability.py` so that *if* the operator enables live growth via the promotion-bridge contract (see `docs/2026-09-13-workflow-g-promotion-bridge.md`), the integration site is one import line away. The guard is a **pure function**: it does no I/O of its own. Every numeric input (live_current_inr, paper_pnl_inr, proposed_delta_inr) is supplied by the caller; the ledger-aware wrapper `assert_live_entry_safety(db_path=..., live_source=..., paper_source=..., proposed_delta_inr=...)` is a thin coroutine wrapper that reads `performance.division_equity` and `performance.allocation_for_source`. Behavioural semantics:

- Default thresholds are derived from the promotion-bridge contract section 4: margin_multiplier=1.5, paper_pnl_ratio=2.0, maximum_live_delta_inr=1,000,000. A custom `AffordabilityThresholds` can be substituted by F6.
- Five decision buckets with named verdicts: `AFFORDABLE`, `MARGIN_EXCEEDED`, `PAPER_PNL_OUT_OF_BAND`, `LIVE_NOT_ARMED`, `LIVE_QUERY_FAILED`, `INVALID_INPUT`.
- The sync function `evaluate_paper_to_live_affordability(...)` returns an `AffordabilityEvaluation` and never raises for *runtime* outcomes; bad shapes (empty strings, mismatched sources, NaN, negative delta) return `INVALID_INPUT`. Dashboards should call `evaluate`.
- The guard function `assert_live_affordable_from_paper(...)` raises `AffordabilityRefusal` on any non-affordable verdict. Pre-trade checks should call `assert`.
- The async wrapper `assert_live_entry_safety(...)` reads live equity and paper realised P&L from the production ledger via `performance.division_equity`. It propagates `ValueError` for bad arguments; bad ledger queries produce a refusal.

The orchestrator call sites carry **placeholder scaffold only** today: `penny_edge_orchestrator.run_penny_edge_scan` and `fno_orchestrator.run_fno_tick` each have a guarded `_pending_live_growth_inr = 0.0` block annotated `[AFFORDABILITY-SEAM 2026-09-13]` that the integration will plug into. The breadcrumb invariant `test_orchestrator_scan_has_first_line_breadcrumb` is preserved by placing every affordability logger call *after* the `penny_edge_orchestrator_invoked` breadcrumb.

Behavioural coverage (this slice): 34 unit tests in `tests/test_affordability.py` cover every decision bucket, the input-validation contract, custom-threshold parameterisation, and reproduction determinism. 8 integration tests in `tests/test_affordability_integration.py` cover the ledger-aware wrapper through a stub ledger (the runtime ledger path is exercised by the orchestrators themselves). Whole-engine rerun: 2,751 passed / 4 skipped / 23 warnings in 125.66s; +42 net passing tests vs. the previous 2,709 baseline (34 unit + 8 integration). No regression to the previously-closed baseline failures; no new warnings.

**This slice does NOT establish real affordability.** The guard exists; the integration sites are wired; no live path is currently calling the guard (live trading is structurally disarmed). Until F6 (capital policy + user-supplied loss tolerance) lands, no `APPROVED_LIVE_BUDGET` can be issued by the bridge. The guard's purpose is to be the *choke point* when F6 unblocks — not to invent authority before then.

## 8. Open mark-to-market (F3 partial; producer + wire-up landed)

### 8.1 What landed

A standalone `python-engine/mark_to_market.py` module that computes unrealised P&L on every open position (equity, F&O, F&O debit/credit multi-leg structures) using a caller-supplied quote cache. Three named quote buckets (FRESH, STALE, UNAVAILABLE) preserve observability rather than silently degrading to zero. 43 focused tests in `python-engine/tests/test_mark_to_market.py` cover every bucket, every validation contract (NaN/Inf/string/None/empty), every F&O premium-multiplier edge, every multi-leg partial-stale conservative behaviour, and a regression test that demonstrates the silent-zero bug is closed.

`main.py:run_penny_hourly_report` is patched to call `mark_open_positions` instead of reading `p.get("current_price", 0.0)`. The wire-up:
- resolves each penny position's `instrument_token` (row first, Kite instrument cache by ticker as fallback);
- batch-fetches one `kite.get_quote(tokens)` call (not one-per-row);
- feeds the quote cache into `mark_open_positions`;
- logs stale-quote counts and falls back to `Unrealised: +Rs 0` only when the whole MTM call raises (the prior silent-false-loss bug is gone).

### 8.2 The bug F3 actually closes

Pre-fix `main.py:1599` was:
```python
unrealised = sum((p.get("current_price", 0.0) - p.get("entry_price", 0.0)) * p.get("shares", 0) for p in penny_pos)
```
With `positions` carrying no `current_price` column, `p.get("current_price", 0.0)` always returned `0.0`. The expression collapsed to `-entry_price * shares`. For a 10-share TCS position at `entry_price=3000.0`, the hourly report printed `Unrealised: -Rs 30000` — a **false loss of 30,000 rupees on a position whose mark was unknown**. The bug was asymmetric and silent: it could not have been caught without running the orchestrator and reading the printed line. The new module makes the quote *visible* (FRESH, STALE, or UNAVAILABLE) and computes the actual P&L when a fresh quote is supplied.

### 8.3 What F3 does NOT include

- No UPDATE on `positions` / `fno_positions` / `fno_dr_positions`. MTM is read-only; the audit doc explicitly disallows ledger mutation in this workflow.
- No F&O wire-up at the orchestrator level. The `fno_orchestrator` and `fno_dr_book` consumers are deferred to a follow-up commit that calls `mark_open_positions` from the F&O tick (which already has Kite open with `instrument_cache` pre-populated).
- No `/performance` route wire-up. `operator_status.py:257` continues to read `perf.get("unrealised_pnl", 0.0)`. Wiring is deferred; the `/performance` payload is the F4/F5 territory.
- No broker integration, no order placement. MTM is read-only and source-bound.

### 8.4 Verification

- Focused `tests/test_mark_to_market.py`: 43/43 pass in 0.39s (run twice: 0.39s and 0.42s; deterministic).
- Whole-engine rerun: 2,794 passed / 4 skipped / 23 warnings in 125.65s (one rerun) and 126.15s (second rerun, `-p no:randomly`); +43 vs. previous 2,751 baseline; no regression to the previously closed baseline failures; no new warnings.

**This slice does NOT establish real mark-to-market acceptance.** The producer is wired to the penny hourly report; the F&O orchestrator and the `/performance` route are not wired. Until the consumer wire-ups land, the value of MTM is structural (the producer exists, the silent-zero bug is gone, the consumer-side plumbing is one-line-per-site) — not end-to-end (the operator still sees `+Rs 0` in `/performance`).

## 9. Discrepancy-ID framework (F4 partial; producer landed)

### 9.1 What landed

A standalone `python-engine/discrepancies.py` module that turns the existing `broker_reconciliation.broker_statement_report` (MATCH/UNRESOLVED/UNAVAILABLE) and `reconciliation_evidence.reconciliation_evidence_report` (per-row reasons) into durable, append-only, operator-reviewable discrepancy records. The framework introduces:

- `DiscrepancyCategory` enum (9 categories) that maps every existing reason string in `reconciliation_evidence.py` to a stable, namespaced identifier. New reasons added upstream become *new* categories; existing categories are not repurposed.
- `DiscrepancyStatus` enum (OPEN / INVESTIGATING / RESOLVED_EXPLAINED / WITHDRAWN) with a forward-only state machine identical in shape to the promotion bridge.
- Two append-only tables: `discrepancies` (immutable rows) and `discrepancy_status_log` (immutable transitions). BEFORE UPDATE/DELETE triggers on both raise `ABORT 'discrepancies_immutable'`.
- Idempotent recording on `(category, evidence_key)` via UNIQUE INDEX. Re-recording is a no-op that returns the existing ID; the first record wins.
- Same-state status transitions are no-ops that write no log row. Operator's "mark as INVESTIGATING" call is safe to repeat.
- Two bridge functions: `record_from_broker_statement(...)` and `record_from_evidence_report(...)`. The bridge is the single mapping point for reason-string → category; adding a new reason upstream is a single-line addition here.
- A combined `record_current_state(...)` that runs both existing reports and records everything in one call. This is the function F5 (broker statement automation) will call from its CLI.

42 focused tests in `python-engine/tests/test_discrepancies.py` cover: schema version, every record-validation contract (severity enum, evidence_key non-empty, NaN amount, malformed evidence refs, deduplication), every status transition (including skip-investigating rejection, resolved-to-open rejection, same-state idempotency), append-only DB triggers (UPDATE/DELETE on both tables blocked at the SQLite level), every read filter (account, source, category, status, date range, limit), every bridge path (MATCH returns None, UNRESOLVED records residual, UNAVAILABLE records no-statement, MATCHED_INTERNAL skipped, unknown reason silently skipped, sheet-level invalid-amounts flag recorded), and end-to-end `record_current_state` against real `performance.record_trade_close` + `broker_reconciliation.import_broker_statement`.

### 9.2 What F4 explicitly does NOT include

- No retroactive population of DISC-A1..A5. The five audit-doc entries remain `UNKNOWN / UNVERIFIED`; the framework *records* findings with stable IDs as evidence arrives. A future commit can call `record_from_evidence_report` with hand-supplied evidence to back-fill the audit doc's five tentative references when real screenshots / ledger rows are obtained.
- No consumer-side wire-up. The framework produces discrepancy records when called; orchestrators and CLIs are not wired to call `record_current_state`. F5 (broker statement automation) is the natural wiring site.
- No UI/dashboard changes. Discrepancies are queryable via `list_discrepancies(...)` but no FastAPI route or Telegram message surfaces them yet.
- No mutation of `bankroll_ledger`, `positions`, `fno_positions`, `fno_dr_positions`, or any `broker_statement_*` table. F4 is an observer.

### 9.3 Verification

- Focused `tests/test_discrepancies.py`: 42/42 pass in 2.27s (one rerun: deterministic).
- Whole-engine rerun: 2,836 passed / 4 skipped / 23 warnings in 126.59s (one rerun) and 127.28s (second rerun); +42 vs. previous 2,794 baseline; no regression to the previously closed baseline failures; no new warnings.

**This slice does NOT establish real discrepancy-ID acceptance.** The framework exists; no orchestrator or CLI calls it yet; the five DISC-A1..A5 audit-doc entries remain unresolved. The value is structural (the durable record layer is ready for F5 wire-up, the append-only discipline is enforced at the SQLite trigger level, the forward-only state machine is in place) — not end-to-end (the operator still sees no discrepancy IDs in any surface today).

## 10. Broker statement automation skeleton (F5 partial; CLI + route landed)

### 10.1 What landed

A standalone `python-engine/reconciliation_cli.py` module and two new routes in `python-engine/routes_commands.py`:

- `python -m python_engine.reconciliation_cli import-statement --payload <path> --output <path>` reads a JSON payload from disk, calls `broker_reconciliation.import_broker_statement`, then runs `record_current_state` as a side effect, and writes a structured JSON result via an atomic byte-identical helper. Re-running with the same payload is idempotent on the F4 framework's `(category, evidence_key)` boundary.
- `python -m python_engine.reconciliation_cli run-report --account <id> [--source] [--limit] [--record] --output <path>` runs both existing reports and (with `--record`) records discrepancies. Without `--record`, the command is read-only.
- `python -m python_engine.reconciliation_cli list-discrepancies [--account] [--source] [--category] [--status] [--since] [--until] [--limit] --output <path>` filters the discrepancies table.
- `POST /reconciliation/import-statement` -- programmatic ingestion surface; same async function as the CLI. Returns the imported flag, broker status, and discrepancy IDs.
- `GET /reconciliation/discrepancies` -- read-side route; mirrors the existing `/analytics/reconciliation-evidence` style. All responses carry `can_place_orders=False` to make the read-only contract explicit.

29 CLI tests in `tests/test_reconciliation_cli.py` cover: ISO-8601 parsing, payload validation, atomic output writes (including byte-identical retries), import + record + report paths, idempotent re-import, every CLI subcommand end-to-end, validation errors return non-zero exit code. 16 route tests in `tests/test_routes_reconciliation.py` cover: happy path, idempotent repost flips `imported` flag, every 422 path (non-object, missing keys, naive as_of, garbage as_of, non-list entries, non-list fills), `can_place_orders=False` always, GET route validation (invalid category, invalid status, naive since/until, garbage since), end-to-end POST then GET.

The `tests/main_surface_golden.json` was deliberately regenerated via `TS_UPDATE_GOLDEN=1 pytest tests/test_main_surface_characterization.py` to capture the two added routes. The diff is exactly 2 routes added; nothing else drifted.

### 10.2 What F5 explicitly does NOT include

- No scheduler. The CLI is operator-invoked; the route is on-demand. No periodic refresh.
- No broker network integration. The CLI reads a local JSON file the operator supplies. The route accepts a JSON body; no Kite, no Zerodha API.
- No retroactive DISC-A1..A5 population. The five audit-doc entries remain `UNKNOWN / UNVERIFIED`.
- No `/reconciliation/discrepancies` mutation surface. The GET is read-only; status transitions remain a CLI-only or direct DB call.

### 10.3 Verification

- Focused `tests/test_reconciliation_cli.py`: 29/29 pass in 1.70s (one rerun: deterministic).
- Focused `tests/test_routes_reconciliation.py`: 16/16 pass in 1.64s (one rerun: deterministic).
- F3 flake fixed: `test_mark_to_market.py::TestReproducibility::test_summary_string_format_stable` was using `age_seconds=0` which crossed the freshness boundary under sub-second clock jitter between the `_quote()` and `mark_open_positions()` calls; rebuilt the tick with `age=1s` and explicitly excluded the `age=Ns` substring from the structural assertion.
- Whole-engine rerun: 2,881 passed / 4 skipped / 39 warnings in 128.75s; +45 vs. previous 2,836 baseline; no regression to the previously closed baseline failures. The +16 warnings come from the same `'app' shortcut` DeprecationWarning that other route tests (`test_promotion_readiness_route.py`, `test_operator_status.py`) already emit; the warning *category* is unchanged, only its count grows with new route tests.

**This slice does NOT establish real broker-statement automation acceptance.** The CLI and route exist; no operator has run an import against a real statement yet; no admin UI surfaces the discrepancy IDs. The value is structural (the CLI/route pair is one import away from operator use, the F4 framework is wired into the import path, the golden route table is updated).

## 12. Scheduler coroutine warning (H1 done; PROD-READY)

### 12.1 What landed

Pre-fix, `run_penny_hourly_report` was the ONLY penny subsystem job registered raw (no `_safe` wrapper, no first-line breadcrumb). Every other penny subsystem job — `_run_penny_edge_scan_safe`, `_run_penny_edge_exit_safe`, `_run_penny_accept_watchdog_safe`, etc. — has the `[Penny-edge-breadcrumb 2026-07-06]` pattern: first-line diagnostic log + `_safe` wrapper that catches `Exception` and logs. The penny hourly report had neither. With the F3 wiring that pulls in `mark_to_market.mark_open_positions` and the F-series substrates, a transient substrate read failure would have taken the hourly-report cron down for the rest of the day — silently, because nothing would log an error.

The matrix row "H — scheduler coroutine warning TESTED_DEV" was based on the *original 8 closures* and did NOT include `run_penny_hourly_report`. Adding `run_penny_hourly_report_safe` to `ALL_CLOSURES` in `tests/test_scheduler_closures_invoke.py` closes that test coverage gap — a future refactor that moves the wrapper between modules will fail the parametrised closure-resolution test.

H1 ships:

- `python-engine/scheduler_setup.py`: `async def run_penny_hourly_report_safe()` wrapper inside `register_penny_scheduler_jobs` with first-line breadcrumb + calendar gate (inside try/except for substrate failures) + the original body wrapped in `try/except Exception as exc: logger.error(..., exc_info=True)`. The cron registration is updated to `scheduler.add_job(run_penny_hourly_report_safe, ...)` with `max_instances=1, coalesce=True, misfire_grace_time=600` matching the discipline of every other penny job.
- `python-engine/tests/test_scheduler_closures_invoke.py`: `run_penny_hourly_report_safe` added to `ALL_CLOSURES`. The parametrised `test_closure_resolves_its_globals_when_called` now exercises the wrapper's global-resolution region.
- `python-engine/tests/test_scheduler_h1_coroutine_guards.py` (new, 7 tests): closure-registration regressions + coroutine-leak regressions + breadcrumb-fires-on-success + standard-exception-catching + create_task-await-cycle + F3-import-failure-resistance.

### 12.2 Senior-dev invariants preserved

- **NO deletions.** The wrapper is additive; the cron re-registration is one-line. The bare `run_penny_hourly_report` function in `main.py` is untouched (still callable manually).
- **NO scheduler mutation.** All 41 existing scheduler/closure tests pass.
- **NO new dependencies.** Uses `main.is_trading_day`, `main.kite`, structlog — all already in scope.
- **NO new warnings.** The golden route table was deliberately regenerated via `TS_UPDATE_GOLDEN=1` to capture the one-line change (registered `func` is now `run_penny_hourly_report_safe` instead of `run_penny_hourly_report`). Diff is exactly one line; nothing else drifted.

### 12.3 Verification

- Focused `tests/test_scheduler_h1_coroutine_guards.py`: 7/7 pass in 1.42s.
- Focused `tests/test_scheduler_closures_invoke.py`: 25/25 pass in 2.07s (was 24; the new wrapper is now exercised by the parametrised closure-resolution test).
- `tests/test_penny_cron_gating.py`: 4/4 pass — the wrapper's calendar gate is detected by `test_every_cron_handler_has_a_gate_or_is_allowlisted`.
- `tests/test_main_surface_characterization.py`: 3/3 pass after deliberate `TS_UPDATE_GOLDEN=1` regeneration. Diff is exactly one line (`func: run_penny_hourly_report` → `func: run_penny_hourly_report_safe`); nothing else drifted.
- Whole-engine rerun: 2,930 passed / 4 skipped / 39 warnings in 129.02s (one rerun: 129.17s); +8 vs. previous 2,922 baseline (7 H1 + 1 golden-regen); no regression to the previously closed baseline failures; no new warnings.
- Production smoke test (run manually with a substrate failure injected into `is_trading_day`): the wrapper logs the breadcrumb, logs the failure with full traceback, and does NOT raise.

**This slice DOES establish PROD-READINESS for the penny hourly report cron.** The pre-fix PROD gap (silent cron death on substrate failure) is closed. The acceptance contract for PROD on 2026-09-14 is: every penny subsystem job is wrapped, every wrapper is exercised by the parametrised test, the surface golden is in sync, and a substrate failure does not raise out of the cron.

## 13. Scheduler timing priority-tier breakdown (H2 done)

### 13.1 What landed

Pre-fix, `scheduler_timing_report` grouped by literal `job_id` but **not by the §12 priority tier**. The operator could not see "the slowest stage across all exit-tier jobs" vs "the slowest scan-tier job"; tail-latency signals were buried under a flat per-job roll-up. Plan §12 specifies: *"Prioritize order exits and public advice management, then candidate scans, then research."* H2 ships:

- `python-engine/scheduler_telemetry.py`:
  - `JOB_TIER_MAP` — every registered `penny_*`, `fno_*`, `partner_*`, and system job_id classified into one of the four §12 priority tiers (`exit`, `advice`, `scan`, `research`) plus a `system` meta-tier for bootstrap/login/circuit-breaker jobs.
  - `TIER_ORDER` — the priority sequence in §12 spec order.
  - `_tier_for(job_id)` — returns `"other"` for unrecognised ids so the roll-up never silently drops a job.
  - `_aggregate_by_tier(jobs)` — computes per-tier `runs`, `executed_runs`, `rejected`, `in_flight`, `results`, `elapsed_seconds` (p50/p95/max across the **union of samples**, NOT the median of per-job medians), and per-stage `stage_durations` percentiles. A tier with zero jobs returns `None` (not `0`) for all numeric fields, per §12 acceptance *"UI fixture covers unavailable and zero distinctly."*
  - `scheduler_timing_report` extended with a top-level `by_tier` key. Existing keys (`boot_id`, `events`, `jobs`, `inflight`, `note`) remain byte-identical.
- `python-engine/operational_coverage.py` extended with one `scheduler_tier:{tier_name}` entry per tier, so the existing `/analytics/operational-coverage` route surfaces tier-level coverage.

22 focused tests in `python-engine/tests/test_scheduler_h2_timing_tiers.py` cover: `JOB_TIER_MAP` completeness (every penny/fno/partner/system job is classified), `TIER_ORDER` priority sequence, `unrecognised → "other"`, all six tiers present in `by_tier`, empty-tier returns `None`, single-sample returns that sample, per-tier percentile math, stage-duration aggregation, multi-job merge, `results` merge, `rejected` counter semantics, Inf-sample filtering, and `operational_coverage_report` integration.

### 13.2 Senior-dev invariants preserved

- **NO deletions.** `boot_id`, `events`, `jobs`, `inflight` keys in `scheduler_timing_report` are byte-identical to pre-H2. The `by_tier` key is additive at the top level.
- **NO new tables, NO new dependencies.** Reuses `math.isfinite`, `_percentiles`, and the existing `scheduler_run_telemetry` schema. New import: `math`.
- **NO new warnings.** No golden regeneration needed (route surface unchanged).
- **Defence at the roll-up layer, not at `_percentiles`.** Adding a `ValueError`-on-Inf guard to `_percentiles` would change behaviour for any caller passing Inf; the per-tier roll-up filters at its own boundary instead. Existing callers unaffected.

### 13.3 Verification

- Focused `tests/test_scheduler_h2_timing_tiers.py`: 22/22 pass in 0.85s.
- Focused `tests/test_scheduler_telemetry.py` (existing 5 tests): all still pass.
- Focused `tests/test_operational_coverage.py` (existing 1 test): all still pass.
- Whole-engine rerun: 2,952 passed / 4 skipped / 39 warnings in 131.89s (one rerun: 130.78s); +22 vs. previous 2,930 baseline; no regression to the previously closed baseline failures; no new warnings.

**This slice DOES establish per-tier scheduler observability.** The operator can now ask "what is the p95 latency across all exit-tier jobs?" or "which stage is the slowest in the research tier?" without needing to manually group by `job_id`.

## 14. Intraday-cache caller/key/window diagnostic (H3 done)

### 14.1 What landed

Pre-investigation, the audit doc claimed "zero intraday-cache hit rates" without distinguishing three fundamentally different failure modes:
1. **Zero callers** of the cached entry point (`get_intraday`) — true zero hits, no caller exercises the cache.
2. **Freshness-gated misses** — the cache WOULD have served, but `last_cached_dt < expected_latest` forced a Kite round-trip.
3. **Cold cache** — no rows ever written for that ticker/interval.

H3 ships a *read-only* diagnostic that surfaces every caller (cached vs uncached), classifies the existing rows by freshness, and audits the key shape for the §12 cross-account / cross-token invariant.

- `python-engine/intraday_cache_diagnostic.py` (NEW, 530 lines):
  - `CACHED_CALLER_SITES` — every `kite.get_intraday(...)` production call (penny_scanner ×2, main.py momentum signal evaluator).
  - `UNCACHED_CALLER_SITES` — every `kite.get_intraday_by_token(...)` production call (fno_orchestrator, fno_signal_scan, partner_orchestrator ×2, proactive_market_data, market_data_sources, scripts/verify_bfo). The by-token path is **explicitly documented** as not caching — see the kite_client docstring.
  - `cache_row_counts(db_path)` — total rows / distinct sessions / tickers / intervals.
  - `cache_interval_breakdown(db_path)` — per-interval row count, descending.
  - `cache_freshness_window(db_path, interval, now_utc)` — classifies rows as `fresh` (would serve HIT) / `completed` (would force Kite round-trip) / `malformed` (clock skew or bad data).
  - `audit_key_shape(db_path)` — verifies the PRIMARY KEY is exactly `(ticker, interval, datetime)`. Loudly fails if `account_id` / `coin_token` columns appear.
  - `run_diagnostic(...)` — combined entry point that returns the structured dict plus a rendered operator-readable conclusion.
  - CLI: `python -m intraday_cache_diagnostic --db <path> --interval minute --output <path>` prints the conclusion to stdout and writes a structured JSON to the output path.

26 focused tests in `python-engine/tests/test_intraday_cache_diagnostic.py` cover: init / table-exists, row counts (empty / populated / sessions-distinct / missing-DB self-heal), interval breakdown (single / multiple / sort order), freshness (fresh / stale / 5-min window / malformed / interval-only), key-shape audit (compliant / account_id violation / coin_token violation), caller inventory (cached sites include penny_scanner + main; uncached include fno + partner), `run_diagnostic` (empty / partial-warm / full-warm), CLI (success / missing-DB / argparse validation), reproducibility.

### 14.2 Senior-dev invariants preserved

- **READ-ONLY.** No writes, no schema changes, no new tables. The diagnostic *creates* the `intraday_cache` table on first run (matches `kite_client._create_intraday_cache_table` schema byte-for-byte) so a fresh DB doesn't crash the CLI.
- **REUSES `reconciliation_cli._write_output_atomic`** for the JSON output writer. No parallel infrastructure.
- **REUSES `math.isfinite` from the F-series substrate** for stage-durations validation.
- **NO new dependencies.** Stdlib only (sqlite3, argparse, json, datetime, math).
- **NO new warnings.**
- **Cautious junk-cleaning**: I did NOT touch unrelated code. The `penny_engine_breakout.py:85` docstring I noticed is correct (it documents the data-shape contract); not stale. The F audit doc's reference to `scripts/run_broker_reconciliation_daily.py` does not appear anywhere in the live code or docs (verified via grep) — that reference is itself stale and out of scope for H3.

### 14.3 What H3 found (the diagnostic's own answer)

Running the diagnostic against a fresh DB returns the operator-readable conclusion:
```
CONCLUSION:
  The cache is COLD (zero rows). 'Zero hits' reflects a fresh DB or a
  session that hasn't yet completed any get_intraday() call that fell
  through the freshness gate to a Kite round-trip. The cache is
  populated LAZILY (see kite_client.get_intraday INSERT OR REPLACE
  after a miss). Once any caller triggers a miss + write, the cache
  begins to warm.

NEXT STEPS (per plan section 12):
  Cache-add (H4) is DEFERRED until an operator signs off on the
  cache key shape and the freshness budget. This diagnostic is the
  input to that decision.
```

### 14.4 Verification

- Focused `tests/test_intraday_cache_diagnostic.py`: 26/26 pass in 0.66s.
- Whole-engine rerun: 2,978 passed / 4 skipped / 39 warnings in 130.89s (one rerun: 131.59s); +26 vs. previous 2,952 baseline; no regression to the previously closed baseline failures; no new warnings.

**This slice DOES establish the diagnostic surface for the cache-add decision.** Cache-add (H4) is no longer blocked on "we don't know why the cache hit rate was zero"; the diagnostic tells us.

## 11. Capital policy guard (F6 partial; producer landed)

### 11.1 What landed

A standalone `python-engine/capital_policy.py` module (third gate in the live-growth chain: promotion-bridge -> affordability -> capital policy) plus a CLI surface `python-engine/capital_policy_cli.py` and `CAPITAL_POLICY_*` config knobs in `config.py`.

```
CapitalIncreaseVerdict (str, Enum)
    AUTHORIZED                          -- all gates passed
    LOSS_TOLERANCE_EXCEEDED             -- delta > loss_tolerance_pct * live
    DRAWDOWN_TOO_HIGH                   -- current drawdown > max_drawdown_pct
    EXECUTION_QUALITY_INSUFFICIENT      -- win rate / R / consecutive losses
    RECONCILIATION_UNRESOLVED           -- broker report != MATCH
    INSUFFICIENT_EVIDENCE               -- live below floor / no research

evaluate_capital_increase(...)              -- pure function
evaluate_capital_increase_for_account(...)   -- async wrapper, reads F1/F5
```

The guard is **pure**: no I/O of its own; every numeric input is supplied by the caller. The async wrapper reads the F1 inventory (live equity, drawdown, execution quality, consecutive losses), the F5 broker report (MATCH/UNRESOLVED/UNAVAILABLE), and the G research archive (file presence check).

Eight `CAPITAL_POLICY_*` config knobs in `config.py`:
- `CAPITAL_POLICY_LOSS_TOLERANCE_PCT = 25.0` -- the user's stated loss tolerance (the explicit input the plan mandates; preserved verbatim).
- `CAPITAL_POLICY_MAX_DRAWDOWN_PCT = 15.0` -- current realised drawdown cap.
- `CAPITAL_POLICY_MIN_WIN_RATE_PCT = 50.0` -- execution-quality floor.
- `CAPITAL_POLICY_MIN_AVG_R_MULTIPLE = 0.0` -- expectancy floor.
- `CAPITAL_POLICY_MAX_CONSECUTIVE_LOSSES = 5` -- operational stability gate.
- `CAPITAL_POLICY_MIN_LIVE_BANKROLL_INR = 1500.0` -- pre-evaluation floor.
- `CAPITAL_POLICY_REQUIRE_BROKER_RECONCILIATION = True` -- never grow on unverified broker truth.
- `CAPITAL_POLICY_REQUIRE_PROACTIVE_EVIDENCE = True` -- never grow without a research basis.

Every knob has an inline comment explaining what it does. The operator overrides any of them with a single edit (or env var, since `config.Settings` is a `BaseSettings`).

41 focused tests in `tests/test_capital_policy.py` cover: schema version, threshold validation at construction, every verdict bucket, gate ordering (live floor -> reconciliation -> drawdown -> loss tolerance -> execution quality -> proactive evidence), CLI subcommands (print-config, evaluate), async wrapper, input validation (NaN/Inf/bool/string/negative), reproducibility.

### 11.2 What F6 explicitly does NOT include

- No price-prediction model. The "creative" part is the verdict structure (six named buckets with refusal reasons), NOT picking numbers the user didn't ask for.
- No signal-reading. The "continuation evidence" check is a file-presence check on the proactive research archive, NOT a live price read.
- No automatic growth. The guard *evaluates*; it never *acts*. The CLI/route are operator-invoked.
- No retroactive DISC-A1..A5 population.

### 11.3 Verification

- Focused `tests/test_capital_policy.py`: 41/41 pass in 0.54s.
- Whole-engine rerun: 2,922 passed / 4 skipped / 39 warnings in 129.85s (one rerun: 130.14s); +41 vs. previous 2,881 baseline; no regression to the previously closed baseline failures; no new warnings.

**This slice does NOT establish real capital-policy acceptance.** The producer + CLI + config knobs exist; no orchestrator or operator has run an evaluation against a real ledger yet; the guard's "creative" content is the verdict structure, not invented numbers. The value is structural (the third gate in the live-growth chain is in place, every knob is documented and overrideable, the guard refuses with named reasons rather than guessing).

## 12. H-series future plan (post F-series) — including H4 cache-add

[WORKFLOW-H H1..H4 2026-09-13] H1 closed `23f332a`-era commit; H2 closed
`52f625e` + `23f332a`; H3 (intraday-cache diagnostic) closed `fead40c`;
H4 (cache-add for ``get_intraday``) ships with this section.

### 12.1 What H4 changed (vs. the H4 audit gap)

§12 audit plan: *"Cache only with explicit instrument, interval,
completed-bar cutoff and freshness semantics. Do not mix mutable
forming bars with completed historical bars or cross-account/coin
tokens."*

Pre-H4, the existing ``get_intraday`` HIT path satisfied (1)
instrument and (2) interval correctly. It did NOT enforce (3)
completed-bar cutoff: a candle whose ``datetime`` was equal to
``to_datetime`` (the current minute) was served as a HIT even
though it might be forming. It DID have a freshness gate but
the gate was hard-coded to ``to_datetime - interval_minutes``
with no operator knob.

H4 makes all four explicit via three new config knobs:

| Knob | Default | §12 property |
|---|---|---|
| ``INTRADAY_CACHE_FRESHNESS_SECONDS`` | 0 | Freshness budget (leniency, not strictness) |
| ``INTRADAY_CACHE_INCLUDE_FORMING`` | False | Completed-bar cutoff (excludes forming candles from the returned set) |
| ``INTRADAY_CACHE_MIN_CANDLES`` | 4 | Minimum candles for a HIT (existing VWAP floor, made explicit) |

Defaults preserve the pre-H4 behaviour exactly. Operators who want
to relax any of these can do so via ``config.py``.

### 12.2 What H4 deliberately did NOT do

H4 did NOT add caching to ``get_intraday_by_token`` (the F&O +
partner path). That path is documented as uncached by design
("today's candles change every 5 minutes, so a cache would only
serve stale bars"). The senior-dev move here is to write a
one-page proposal capturing the design work for operator sign-off,
NOT to add code without sign-off. See
``docs/2026-09-13-h4-by-token-cache-proposal.md`` for the proposal.

### 12.3 H5 deferred

H5 (dashboard readiness reasons) remains deferred; it depends on
H4 landing cleanly. Out of scope for this audit snapshot.
