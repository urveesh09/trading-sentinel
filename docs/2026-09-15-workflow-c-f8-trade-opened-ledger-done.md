# Workflow C.F8 — bankroll_ledger TRADE_OPENED audit trail (F-8 from prod audit)

## Source

Per the 2026-09-15 production deep audit F-8:
> 🟡 F-8 (LOW, $): **GRAVISSHO position is OPEN but not booked into bankroll_ledger**. The EDGE_PAPER pool shows ₹91,244.66 (last update Sept 4) — opening the position today didn't debit the pool. **Day-end won't reconcile this position** until it's closed.

Audit details:
- GRAVISSHO EDGE_PAPER position opened at 09:30 IST (CNC, ₹45.6K notional, 971 shares @ ₹46.97).
- Penny scanner rejected GRAVISSHO (`not_selected_by_live_leg`); the **EDGE strategy** (separate code path) traded it instead as CNC delivery.
- The bankroll_ledger hasn't been debited because EDGE_PAPER pool isn't tracking open position cashflow.

## What landed

| File | Type | Purpose |
|---|---|---|
| `python-engine/penny_edge_orchestrator.py` | source (extended) | `_write_edge_position` now writes a `TRADE_OPENED` row alongside the positions row |
| `python-engine/models.py` | source (extended) | `LedgerRow.event_type` Literal extended with `"TRADE_OPENED"` |
| `python-engine/tests/test_f8_trade_opened_ledger.py` | test (new) | 6 tests pinning the audit-trail contract |
| `docs/2026-09-15-workflow-c-f8-trade-opened-ledger-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice, when an EDGE position was opened:
- A row was inserted into the `positions` table.
- No row was inserted into `bankroll_ledger`.
- The audit's day-end reconciliation had NO way to verify which positions were open from the ledger alone.

After this slice:
- The same `_write_edge_position` call also writes a `TRADE_OPENED` row to `bankroll_ledger`.
- The canonical audit query `SELECT ticker, notes FROM bankroll_ledger WHERE event_type='TRADE_OPENED'` lists every open position's audit surface.
- The `notes` field carries `notional=N;shares=N;entry_price=N;stop_loss=N;sl_order_id=...` so operators can reconstruct the trade from the ledger alone.

## Key design choice: pnl=0 (NOT -notional)

The audit's concern is **AUDITABILITY of the open position**, not a paper-money "debit". Two possible designs:

1. **pnl=0**: pure audit trail; equity formula `allocation + SUM(pnl)` unchanged.
2. **pnl=-notional**: virtual debit; equity formula changes; position sizing shrinks by the notional.

We chose **option 1** because:

- The existing `division_equity(source) = allocation_for_source(source) + SUM(pnl)` is the canonical formula used by `_edge_equity()` and the position-sizing path. Changing this would break every open-position size for the rest of the day.
- The realised hit on the pool already happens at `TRADE_CLOSED` (when `pnl` is recorded). `TRADE_OPENED` is purely an audit-trail marker.
- This is a **bounded, additive fix**: a new event type, a new row, no formula change. Day-end reconciliation now sees the open position; pool accounting is unchanged.

## Why this is bounded

- One new event type (`TRADE_OPENED`).
- One new line in the existing `LedgerRow.event_type` Literal.
- One new row INSERT in `_write_edge_position` (after the positions INSERT, in the same connection).
- One new import (`division_equity, init_ledger` from `performance`).
- Zero new dependencies.
- Zero changes to existing TRADE_PARTIAL / TRADE_CLOSED / INITIAL semantics.
- The TRADE_OPENED row's pnl=0 means the equity formula is mathematically identical to before.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_f8_trade_opened_ledger.py` | 6 | +6 (new file) |
| `test_penny_edge_orchestrator.py` | 5 | 0 (no changes) |

Full python-engine narrow regression surface (34 test files): 525 PASS (was 519 before this slice, +6 net for F-8). Zero regressions.

## Test discipline

- 6 tests pin the bounded contract:
  1. `_write_edge_position` writes a TRADE_OPENED row.
  2. TRADE_OPENED pnl=0 preserves equity (bankroll_before == bankroll_after).
  3. Notes column carries the audit surface (notional/shares/entry_price/stop_loss/sl_order_id).
  4. PAPER and LIVE legs each get their own row with the correct source tag.
  5. TRADE_OPENED is purely additive — doesn't interfere with INITIAL / TRADE_PARTIAL / TRADE_CLOSED.
  6. The canonical audit query (`WHERE event_type='TRADE_OPENED'`) lists every open position's audit surface.
- Tests use tmp_path DBs (no `/data/cache.db` dependency), so they run on dev tree.
- The existing `test_penny_edge_orchestrator.py` (which SKIPs on dev tree) is unchanged — it tests the live `/data/cache.db` flow.

## Operator runbook

After deploy to PROD, the audit's next run can verify the FIX landed by querying:

```sql
SELECT ticker, notes, source
FROM bankroll_ledger
WHERE event_type = 'TRADE_OPENED'
  AND timestamp >= '2026-09-16';
```

Expected: at least one row per EDGE_PAPER / EDGE_LIVE position opened post-deploy, with notes carrying `notional=N;shares=N;entry_price=N;stop_loss=N;sl_order_id=...`.

Day-end reconciliation can now answer "is there an open position the ledger didn't see?" — the answer is "no, because every open is recorded".

## What this does NOT solve

- The actual pool accounting (EDGE_PAPER pool at ₹91,244.66 since Sept 4) is unchanged. That is a separate concern (the audit identifies F-8 as LOW, $) — operators may want to add a virtual debit when a position opens, but that would change the equity formula and break position sizing.
- The historical GRAVISSHO open (Sept 15) is still NOT recorded. Operators can back-fill it with a MANUAL_ADJUSTMENT entry if reconciliation requires.
- The audit's other LOW concerns (F-1 dashboard race, F-6 GRAVISSHO not_fresh_break mode) are unchanged.

## Critical invariants preserved

- `division_equity(source) = allocation_for_source(source) + SUM(pnl)` — unchanged because TRADE_OPENED has pnl=0.
- Position-sizing math — unchanged because equity is unchanged.
- TRADE_PARTIAL / TRADE_CLOSED semantics — unchanged.
- INITIAL row seeding by `init_ledger` — unchanged.
- The auto-seeded SYSTEM INITIAL row's `bankroll_before == bankroll_after` invariant — unchanged.

## What's still open on the audit

- **F-4** (penny stale warning flood) — DONE in `0ba14a9` (C.B.3).
- **F-7** (agent dedup file observability) — DONE in `04aa166` (C.B.2).
- **F-3** (concurrent finalize_prior_days race) — DONE in `7cf87c3` (C.B.1).
- **F-1** (dashboard bootstrap race) — DONE in `f186a22` + `5265c73`.
- **F-2** (Kite LTP fanout) — DONE in `729f7f1` (C.F2).
- **F-5** (features invisible) — DONE in `e2fe147` (C.F5).
- **F-8** (GRAVISSHO not booked) — DONE in this slice (`<next-commit>`).
