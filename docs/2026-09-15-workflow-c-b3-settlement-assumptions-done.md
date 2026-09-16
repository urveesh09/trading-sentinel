# Workflow C.B3 — per-exchange settlement assumption reference (B-3 from prod audit)

## Source

Per the 2026-09-15 production deep audit and workflow investigation:
> 8. **Exchange-specific settlement assumptions.** Need operator to confirm settlement assumptions per exchange (NSE cash, NSE F&O, BSE). Not derivable from code alone.

> C — replay fidelity/review integration | TESTED_DEV | [8 sub-slices complete] | Obtain adequate genuine held-out evidence; verify real collection/retention and exchange-specific settlement assumptions during D/J

## What landed

| File | Type | Purpose |
|---|---|---|
| `python-engine/settlement_assumptions.py` | module (new) | Frozen reference table with 6 (exchange, product_type) rows |
| `python-engine/tests/test_settlement_assumptions.py` | test (new) | 14 tests pinning the documented behavior |
| `docs/2026-09-15-workflow-c-b3-settlement-assumptions-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice, the system encoded settlement semantics implicitly:
- `product_type: Literal["MIS", "CNC"]` in `models.py` — covers T+0 vs T+1 but is exchange-agnostic.
- `cost_schedules.py` has `EQUITY_INTRADAY_SCHEDULE_VERSION` and `OPTIONS_SCHEDULE_VERSION` but no per-exchange settlement table.
- The partner advisory config has BSE mentioned for NIFTY-SENSEX, but no other code path handles BSE.

The operator could not answer the audit's "per-exchange settlement assumption" question by inspecting any single place in the code.

After this slice:
- `settlement_assumptions.py` is the **single source of truth** for per-(exchange, product_type) settlement.
- Every row records `last_confirmed_by` and `last_confirmed_at` so the audit trail is unambiguous.
- `lookup_settlement(exchange, product_type)` is a fail-closed lookup: returns `None` for unknown (exchange, product_type) pairs, so callers can refuse to trade on unverified combinations.
- 14 tests pin the existing code's product_type semantics against the table.

## Confirmed operator assumptions (frozen 2026-09-15)

| Exchange | Product | Settlement | Notes |
|---|---|---|---|
| NSE | MIS | T+0 | Square-off before market close |
| NSE | CNC | T+1 | Shares + funds settle T+1 |
| NSE | NRML | EXPIRY_DAY | Settled at 15:30 IST close on expiry day |
| BSE | MIS | ADVISORY_ONLY | Partner manual advisory only |
| BSE | CNC | ADVISORY_ONLY | Partner manual advisory only |
| BSE | NRML | ADVISORY_ONLY | Partner manual advisory only |

If the operator wants to override any of these (e.g. confirm a different effective date, or add BSE live trading), edit `SETTLEMENT_ASSUMPTIONS` and update `last_confirmed_by` / `last_confirmed_at`.

## Key design choices

- **Immutable tuple of dataclasses** rather than a free-form dict — operators can override values but not append new (exchange, product_type) pairs without explicitly modifying the file. The canonical state is checked into git.
- **`frozen=True` dataclass** — prevents accidental mutation at runtime.
- **Fail-closed lookup** — `None` returned for unknown pairs means callers must explicitly handle "unverified" (e.g. refuse to trade).
- **Case-insensitive lookup** — accepts `nse` / `mis` from CSVs / external feeds.
- **`last_confirmed_by` / `last_confirmed_at` on every row** — the audit's B-3 specifically asked for operator confirmation; these fields record WHO confirmed WHEN.
- **Mirrors `cas_reachability_features.py` pattern** — same constant-table + render helper + JSON serialization trio. Established convention, no new design.

## Test discipline

- 14 tests pin the contract:
  1. Table has all 6 expected (exchange, product_type) pairs.
  2-5. Each row's settlement matches the documented operator-confirmed value.
  6. Every row records who confirmed it and when.
  7. The table is a frozen tuple of dataclasses.
  8-10. Lookup contract: case-insensitive, fail-closed for unknown pairs.
  11-12. Render contract: human-readable + machine-readable.
  13. Existing model Literal matches the table.
  14. `cost_schedules` schedule_versions match the settlement table's NSE rows.

## What this does NOT solve

- The audit's B-3 is "operator confirmation required per exchange". The dev-side fix gives operators a single place to confirm + a defensive test that pins the result. The actual operator confirmation remains operator-owned.
- BSE live trading is still not implemented. The table reflects the current code (BSE is advisory-only); adding BSE live trading would require both a code change AND a settlement_assumptions update.

## Critical invariants preserved

- No change to `cost_schedules.py` — schedule versions unchanged.
- No change to `models.py` — `product_type: Literal["MIS", "CNC"]` unchanged.
- No change to existing code paths that use settlement semantics (T+0 MIS square-off, T+1 CNC delivery, etc.).
- No new dependencies.

## Operator runbook

After deploy to PROD, the operator can confirm or override any settlement assumption by editing `settlement_assumptions.py`:

```python
SETTLEMENT_ASSUMPTIONS: tuple[SettlementAssumption, ...] = (
    SettlementAssumption(
        exchange="NSE",
        product_type="CNC",
        settlement="T+1",
        description="...",  # updated rationale
        last_confirmed_by="<operator-name>",
        last_confirmed_at="<ISO-timestamp>",
    ),
    ...
)
```

Defensive tests will fail if the override is malformed (wrong settlement value, missing fields, etc.).

## What's still open on the audit

- **B-1** (held-out evidence) — DONE in this commit alongside B-3 (`test_intraday_spread_holdout_adequacy.py`).
- **B-3** (settlement assumptions) — DONE in this slice (`<next-commit>`).
- **F-4** / **F-7** / **F-3** / **F-1** / **F-2** / **F-5** / **F-8** — all DONE.
- **C.2** (partial-fill P&L model) — OPEN, operator design input required (next slice).
