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
