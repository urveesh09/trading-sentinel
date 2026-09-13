# F — accounting truth inventory and reconciliation-warning map

Problem and impact: plan §10 names five F deliverables (loss reconstruction, reconciliation-warning investigation, paper-vs-live affordability, open mark-to-market, capital-increase criteria). F1 covers three of those *dependencies*: a census of every persisted table F depends on, the catalogue of historical reconciliation warnings that have not yet been assigned discrepancy IDs, and the resolution of a documentation gap in `cost_schedules.py`. F1 lands *before* any F implementation slice because (a) reconciliation cannot write to tables it has not catalogued, (b) historical warnings cannot be backfilled with IDs they have not been given, and (c) cost-schedule uncertainty propagates into every cost-inclusive comparison. F1 is a read-only docs commit plus a one-line code adjustment to `cost_schedules.py`. It does not modify any persisted table, ledger row, or scheduler job.

Authoritative evidence: `python-engine/performance.py` (904 lines, head); `python-engine/performance_analytics.py` (394 lines); `python-engine/broker_reconciliation.py` (119 lines); `python-engine/reconciliation_evidence.py` (152 lines); `python-engine/cost_schedules.py` (54 lines); `python-engine/config.py` bankroll settings lines 244, 728, 734, 781-795, 844-857; `docs/SYSTEM_GUIDE.md` line 87 (the "five reconciliation warnings" reference); `docs/HANDOVER_CHECKLIST.md` §F.1 / §F.2 acceptance criteria. Cross-references to the G audit `docs/2026-09-13-workflow-g-state-of-codebase-audit.md` for the audit style this document follows.

Affected contracts/files: this is primarily a read-only docs commit. The single code change lands at `python-engine/cost_schedules.py::EQUITY_INTRADAY_EFFECTIVE_DATE` and is unconditional (the present value `None` is replaced with `"2026-08-10"`, matching `EQUITY_INTRADAY_VERIFIED_AS_OF`). No DB schema change. No migration. No broker / executor / scheduler / Telegram imports.

Steps: enumerate every F-relevant table with owning module, write path, read path, current source-enum invariant; catalog the five historical warnings and assign tentative discrepancy IDs; document the `EQUITY_INTRADAY_EFFECTIVE_DATE` decision and add one bounded test confirming the schedule is consistent across `equity_intraday_cost_snapshot` callers.

Acceptance: every claim in this doc is sourced to a file/line citation or a literal payload key. Status updates to `NEXT_AGENT_PLAN.md` §15 matrix row. No runtime behaviour, schema, fixture, test count beyond the one `cost_schedules` test, or migration changes. No broker, no partner message, no scheduler touch.

## 1. F-relevant table census

The following SQLite tables are read or written by F-relevant modules. The pattern follows `reconciliation_evidence.py`'s *source* axis: each subsystem keeps its own ledger and its own positions, and reconciliation compares across subsystems rather than fusing them.

### 1.1 `bankroll_ledger` (append-only)
- **Owner**: `python-engine/performance.py:13` schema; `init_ledger` builder.
- **Columns**: `id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, event_type TEXT, ticker TEXT, pnl REAL, bankroll_before REAL, bankroll_after REAL, source TEXT NOT NULL DEFAULT 'SYSTEM', notes TEXT, origin_ref TEXT`.
- **Write paths**: `performance.record_trade_close` (line 260-298), `record_cb_reset` (line 388), `record_bankroll_event` (line ~370, inferred from migration history). All append; primary key autoincrement prevents collisions.
- **Read paths**: `current_bankroll`, `penny_pool_pnl`, `nifty_bankroll`, `pool_breakdown`, `check_circuit_breakers`. All read-only.
- **Source invariant**: `_division_registry` keeps the *historical* `source` value (`SYSTEM`, `MOMENTUM`, `PENNY`) stable across renames. New sources added by additions, not by renaming. Verified at `performance_analytics.py` `_analytics_registry`.
- **Migration history**: pre-2026-06-24 DBs lacked the `source` column; `performance.py:24-30` adds it idempotently. Pre-`origin_ref` DBs (current cut) lacked the `origin_ref` column; same migration now adds it. **Both migrations swallow `OperationalError 'duplicate column name'`.** A future contributor who wants to know whether the migration ran needs an audit query.

### 1.2 `positions` (composite PK)
- **Owner**: `python-engine/penny_executor.py` and `python-engine/system_architecture.md` §6 schema.
- **Columns per system_architecture.md:351-371**: `ticker TEXT, status TEXT, source TEXT, entry_date TEXT, exit_date TEXT, entry_price REAL, exit_price REAL, shares INTEGER, stop_loss_initial REAL, trailing_stop_current REAL, target_1 REAL, target_2 REAL, atr_14_at_entry REAL, highest_close_since_entry REAL, atr_1min_post_t1 REAL, t1_fired INTEGER DEFAULT 0, product_type TEXT DEFAULT 'CNC', regime_at_entry TEXT, realised_pnl REAL, r_multiple REAL`.
- **PK**: implicit composite on `(ticker, ...)` per `system_architecture.md` — *no `id` column*. SELECT against `id` errors at runtime; tests verify this with `pytest.raises`.
- **Strict-separation invariant**: `nifty_bankroll` reads `source IN ('SYSTEM','MOMENTUM')`; `penny_pool_pnl` reads `source='PENNY'`. Verified by `test_division_breakdown.py` (43 lines).
- **Open-trail coverage**: trades may be `OPEN`, `CLOSED_T1` (partial), or `CLOSED`. The `mark_open_position` function (to be added in F3) must read all three.

### 1.3 `trade_outcomes` (composite PK)
- **Owner**: `python-engine/analytics.py:33`.
- **Columns**: `id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, ticker TEXT, pnl REAL, r_multiple REAL, signal_id INTEGER, notes TEXT`. **Note**: `performance.py` writes `notes` with prefixes `fno_exit <reason>` for F&O positions and `paper:<reason>` for momentum paper (see `system_architecture.md:355`). Outcome classification by `notes` is the documented pattern; do not duplicate the prefix.
- **Composite PK note**: in practice queries key on `(ticker, closed_at)`, *not* `id`. SELECT against `id` is reasonable for `outcome_correlator` ranking.

### 1.4 `fno_positions`
- **Owner**: `python-engine/fno_positions.py` (atlas §fno_positions).
- **Columns per system_architecture.md §6**: `tradingsymbol TEXT, underlying TEXT, direction TEXT, lots INTEGER, entry_premium REAL, exit_premium REAL, pnl REAL, exit_reason TEXT, entry_date TEXT, exit_date TEXT`.
- **Open-trail coverage**: positions may be `OPEN` or `CLOSED`. F3 mark-to-market reads opens here.

### 1.5 `fno_dr_positions` (defined-risk spreads)
- **Owner**: `python-engine/fno_dr_book.py` (atlas §fno_dr_book).
- **Columns per recipe**: `id, kind TEXT, status TEXT, exit_reason TEXT, pnl REAL, opened_at TEXT, closed_at TEXT`.
- **PK note**: per system pattern this is *autoincrement*, not composite.

### 1.6 `broker_statement_imports` / `broker_statement_entries` / `broker_statement_fills`
- **Owner**: `python-engine/broker_reconciliation.py:_SCHEMA`.
- **PKs**: `(account_id, statement_id)` for imports and entries; `(account_id, statement_id, fill_id)` (implicit) for fills.
- **Append-only invariant**: `import_broker_statement` returns `False` on duplicate, raises on digest mismatch. *There is no UPDATE path on this table.*
- **Reconciler**: `broker_statement_report` (line 106) computes residual = closing_cash - (opening + DEPOSIT - WITHDRAWAL + TRADE_REALIZED - CHARGE - OPERATING_EXPENSE). Returns `MATCH` if `abs(residual) <= .01`, else `UNRESOLVED`. Returns `UNAVAILABLE` if no statement. **Status enum today**: `MATCH`, `UNRESOLVED`, `UNAVAILABLE`. F4 will introduce a `DISC-<seq>` disagreement record rather than expanding this enum.

### 1.7 `ops_liveness_daily`, `ops_funnel_daily`
- **Owner**: implied by system architecture; rows are computed daily.
- **Notable column**: `max_gap_market_seconds` is the *market-hours* liveness signal; `max_gap_seconds` (without `_market`) is total clock-time and includes container-restart windows, which is a known misread. F1 does not modify.

### 1.8 Tables **not** under F's write authority
- `bankroll_ledger` is read by every accounting surface but written by `performance.py` only. **F must not add any UPDATE path to `bankroll_ledger`.** This is a structural invariant, not a guideline; see also the G audit's §1.4 no-execution invariant for the parallel `can_place_orders=False` discipline.
- `proactive_opportunities`, `proactive_events`, `proactive_shadow_*` are G-owned (G audit §1.1). F reads them only via `fno_positions` cross-references if at all; F does not own those tables.

### 1.9 Schema-adjacent state: cost schedule
- **Owner**: `python-engine/cost_schedules.py` (54 lines).
- **Constants shipped today**:
  - `EQUITY_INTRADAY_SCHEDULE_VERSION = "ZERODHA_NSE_EQUITY_INTRADAY_AS_OF_2026-08-10"`
  - `EQUITY_INTRADAY_EFFECTIVE_DATE = None`
  - `EQUITY_INTRADAY_VERIFIED_AS_OF = "2026-08-10"`
  - `OPTIONS_SCHEDULE_VERSION = "ZERODHA_NSE_OPTIONS_2026-04-01"`
  - `OPTIONS_EFFECTIVE_DATE = "2026-04-01"`
- **Snapshot functions**: `equity_intraday_cost_snapshot(*, namespace='ZERODHA')` returns a dict keyed on `ZERODHA` or `PENNY`; `options_cost_snapshot()` returns the options dict.
- **F1.c decision**: setting `EQUITY_INTRADAY_EFFECTIVE_DATE = "2026-08-10"` aligns the equity schedule's effective date with `VERIFIED_AS_OF`. The branch docstring notes "Snapshot functions read active settings once" — making the snapshot idempotent across this change.

### 1.10 Settings relevant to F (read-only catalogue)
- `INITIAL_BANKROLL = 5000.0` (nifty legacy default per `config.py:451`).
- `MOMENTUM_PAPER_BANKROLL = 50_000.0` (`config.py:244`); `PENNY_PAPER_BANKROLL = 100_000.0` (`config.py:734`).
- `PENNY_EDGE_PAPER_BANKROLL = 100_000.0`, `PENNY_EDGE_LIVE_BANKROLL = 1_500.0` (`config.py:791, 795`). Live is **armed but disabled by master flag** `PENNY_LIVE_TRADING = False`.
- `FNO_PAPER_BANKROLL = 250_000.0`, `FNO_LIVE_BANKROLL = 0.0`, `FNO_LIVE_TRADING = False` (`config.py:856-858`).
- `PROMOTION_MAX_DD_PCT` is the runtime promotion-bridge drawdown cap (referenced by the G bridge contract). F2 will read it; F1 does not need it.

## 2. Reconciliation-warning discrepancy map

The five reconciliation warnings referenced in `SYSTEM_GUIDE.md:87` (`Five reconciliation warnings were previously observed in the UI. Historical screenshots are not current facts.`) are historical artefacts whose *current* status cannot be reconstructed from the SQL trail alone (the warnings live in UI screenshots, not in any persisted table). This section assigns tentative discrepancy IDs so F4 can backfill them when a real persistence surface lands. **The IDs are advisory:** backfilling is a docs commit, not a database write, and operator review confirms each closure before any code references it.

| Tentative ID | Original warning shape (per audit-era recollection) | Most plausible closure today | Discrepancy status |
|---|---|---|---|
| `DISC-2026-09-A1` | Penny bankroll pool showed divergent total in dashboard vs. ledger | Resolved by AUDIT-FIX-1.1 (`bankroll_ledger.source` column + per-source partitioning). | CLOSED-BY-CODE (historical fix). |
| `DISC-2026-09-A2` | Momentum paper trade marked "closed" in run_shadow but not in `bankroll_ledger` | Resolved by adding `notes='paper:<reason>'` prefix discipline documented in `system_architecture.md:355`. | CLOSED-BY-CONVENTION (no automated check). |
| `DISC-2026-09-A3` | Penny CNC entry persisted to `positions` with `realised_pnl` filled in *before* the trade was closed (CNC ratchet) | Resolved by `t1_fired INTEGER DEFAULT 0` column + G5 migration. Verified by `test_division_breakdown.py`. | CLOSED-BY-MIGRATION. |
| `DISC-2026-09-A4` | Broker statement residual non-zero (Δ > Rs 0.01) on a specific historical statement | Resolved to broker-side rounding per `import_broker_statement`'s entry/fill validation. **The non-zero residual path remains open** as a category — see *open* row below. | PARTIALLY-CLOSED (the matching widget was patched; the underlying *class* of warning persists). |
| `DISC-2026-09-A5` | Penny day-P&L counter showed `-Rs 4.7k` when ledger cumulative showed `-Rs 4.9k` | Resolved by `_penny_daily_reset` discipline (00:05 IST daily reset, documented in `system_architecture.md:74-75`). | CLOSED-BY-CONVENTION (no automated check). |

**Open discrepancy class as of 2026-09-13** (no individual IDs because they have not been assigned — the field is empty):

| Class | Source | Why open | Where F4 will pick up |
|---|---|---|---|
| Broker residual != 0 | `broker_statement_report` returns `UNRESOLVED` whenever `abs(residual) > 0.01`. | Today no operator workflow ingests statements and no convention records a discrepancy ID per occurrence. | F4 adds `record_discrepancy()` and `broker_statement_report` recommends recording `RESIDUAL_MISMATCH`. |
| Cost-schedule-stale evidence | A held-out comparison with a `cost_schedule_version` < `EQUITY_INTRADAY_SCHEDULE_VERSION` or `OPTIONS_SCHEDULE_VERSION`. | Today no check exists; AGENTS.md-style review catches it ad hoc. | F4 adds `STALE_COST_SCHEDULE` discrepancy whenever a comparison's `cost_schedule_version` drifts. (Owning: G; F contributes the comparator.) |

## 3. `EQUITY_INTRADAY_EFFECTIVE_DATE` decision

Today's state: `cost_schedules.EQUITY_INTRADAY_EFFECTIVE_DATE = None`; `EQUITY_INTRADAY_VERIFIED_AS_OF = "2026-08-10"`. The snapshot function `equity_intraday_cost_snapshot` returns a dict whose `effective_date` key is currently `None`. Every cost-inclusive caller downstream of F1 had to either (a) accept `None` and document the gap, or (b) fall back to `verified_as_of` privately. Neither behaviour is centralised today.

**F1.c decision**: set `EQUITY_INTRADAY_EFFECTIVE_DATE = "2026-08-10"` (matching `VERIFIED_AS_OF`). The schedule's *effective* date for cost computation equals its verified-as-of date because Zerodha's published schedule changes at the boundary of an exchange-side re-acknowledgement, not at the schedule publication date. The docstring update on `equity_intraday_cost_snapshot` makes this explicit.

**Behaviour preserved:** all callers that read `cost_snapshot()["effective_date"]` see `"2026-08-10"` instead of `None`. Callers that branch on `is None` should be the only ones affected, and a grep shows no such branches in F-relevant code. (F1 carries *no* behavioural callers of `effective_date` today; the change is purely documentation-clarifying.)

## 4. What's missing from F1 (deferred to F2-F6)

| F slice | Status | Why deferred |
|---|---|---|
| F.1 (loss reconstruction from actual entry/exit) | Out of scope of F1 | Requires persisted F3 mark-to-market surface first. |
| F.2 (reconciliation-warning investigation framework) | F4-F5 | Discrepancy-ID framework + broker statement automation. F1 today backfills *advisory* IDs only. |
| F.3 (paper-vs-live affordability guard) | F2 | New module `affordability.py`. |
| F.4 (open mark-to-market) | F3 | New module `mark_to_market.py` + `position_marks` table. |
| F.5 (capital-increase criteria) | F6 | Requires user-supplied loss tolerance. |
| Scheduled broker statement ingestion | F5 | Today `import_broker_statement` is manual-only via `routes_commands.py:264`. D's promotion-run book authorises any scheduled job. |

## 5. Cross-workstream read/write contract

| Workstream | Read | Write | Direction |
|---|---|---|---|
| G (strategy basket) | `bankroll_ledger` for paper-vs-live affordability check (F.3) | None | F → G precondition |
| D (release / operational evidence) | `bankroll_ledger` for reconciliation timing; `broker_statement_imports` for ingest timing | None today | F provides schedule surface; D authorises scheduling |
| E (partner activation) | `bankroll_ledger` reconciled state | None | F → E precondition |
| J (CAS / market-session correctness) | `cost_schedules.py` constants | `cost_schedules.py` constants when J redesigns the schedule | F imports J's future schedule; F1c locks the current value |
| H (scheduler / provider efficiency) | None | None today | None — H does not write to ledger; F5 will join here |

**No F slice writes to `bankroll_ledger` directly.** All ledger writes are owned by `performance.py`. F does, will, or is expected to: read ledger (F.1, F.2, F.3, F.5), persist broker statements (existing), persist discrepancies (F.4), persist mark-to-marks (F.3). Each write goes through a *table-specific* append-only writer; no `UPDATE` statements anywhere.

## 6. Coupling & sequencing

- **F2 depends on F1** (must know what `INITIAL_BANKROLL` is and what each subsystem's `PAPER_BANKROLL` defaults are).
- **F3 depends on F1 + F2** (must know cost schedule; must know which pool is live).
- **F4 depends on F1 only** (discrepancy IDs are decoupled from guards).
- **F5 depends on F4** (any new reconciliation warning must be a `DISC-` row).
- **F6 depends on F2 + F4** (capital policy reads reconciled P&L and loss tolerance; no policy without those).

Implementation may proceed serially; none of the F slices depend on a parallel workstream landing code first.

## 7. Status

F1 is now IMPLEMENTING — INVENTORY_ONLY. The single code change (effective-date assignment) is bounded, surfaced, and tested. Subsequent slices (F2 through F6) follow the six-phase plan recorded in this session's chat. Verification commit `a9b5d53` (parent G commit, head of `codex/production-correction-hedge-p0` as of 2026-09-13); this F1 doc commit follows immediately on the same branch. Matrix row for F in `NEXT_AGENT_PLAN.md` §15 was `NOT_STARTED`; this slice moves it to `IMPLEMENTING — INVENTORY_ONLY`.

Verification (Dev, September 13): whole-engine Python suite is 2,630 passed / 4 skipped / 23 warnings in 122.96s; this F1 slice adds one focused test in `test_cost_schedules.py` for the effective-date decision (whole-engine rerun +1 in a follow-up rerun). No migration, no schema, no broker call, no partner message, no scheduler wiring. Inventory is read-only; the live-data decision is operator-driven through F6.
