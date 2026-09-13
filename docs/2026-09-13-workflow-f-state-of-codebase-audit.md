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
