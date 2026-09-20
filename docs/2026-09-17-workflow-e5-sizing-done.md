# Workflow E.5 — partner liquidity-aware sizing

## Source

Per Workstream E in `NEXT_AGENT_PLAN.md`:
> Explain uncertainty and liquidity limits without
> overwhelming the message.

## Goal

A pure helper that, given a partner card and a requested
contracts count, reports:

  - **Per-leg tier**: SURPLUS / TIGHT / INSUFFICIENT
    (computed from `bid_quantity` / `ask_quantity` vs
    requested contracts).
  - **Max fillable contracts** at top-of-book across all
    legs (the minimum across legs).
  - **Walk-the-book cost** in basis points (estimated
    slippage if requested > top-of-book).
  - **Aggregate tier** (worst-case across legs).
  - **Warnings** for INSUFFICIENT legs and for slippage
    above operator-set tolerance.

Read-only. Does NOT place orders. Does NOT call brokers.

## What shipped

- **`python-engine/partner_sizing.py`** (new):
  - `LiquidityTier` enum: SURPLUS / TIGHT / INSUFFICIENT.
  - `LegLiquidity` dataclass: per-leg breakdown.
  - `LiquiditySizingResult` dataclass: aggregate result.
  - `compute_liquidity_sizing(card, requested_contracts,
     walk_step_bps, slippage_tolerance_bps)` -> result.

- **`python-engine/tests/test_partner_sizing.py`** (new):
  27 tests pinning the classification, fillable cap,
  walk-the-book cost model, aggregate tier rules, and
  error handling.

## Tier classification

| Ratio (top-of-book / requested) | Tier |
|---|---|
| >= 5x | SURPLUS |
| 1x to 5x | TIGHT |
| < 1x | INSUFFICIENT |

For BUY legs we use `ask_quantity`; for SELL legs we use
`bid_quantity`. Missing quantity -> INSUFFICIENT with a
warning.

## Walk-the-book model

If requested contracts > top-of-book depth, the surplus
contracts cost `walk_step_bps` (default 5 bps) each. This
is a heuristic; real walking-the-book is non-linear and
exchange-specific. The helper surfaces it as a WARN-tier
signal, not a precise model.

## Operator usage

```python
from partner_sizing import compute_liquidity_sizing, LiquidityTier

result = compute_liquidity_sizing(card, requested_contracts=2)
if result.liquidity_tier == LiquidityTier.INSUFFICIENT:
    # operator should scale down or wait for liquidity
    for leg in result.per_leg:
        if leg.tier == LiquidityTier.INSUFFICIENT:
            log.warning("leg %s cannot fill %d contracts at top-of-book",
                        leg.tradingsymbol, leg.requested_contracts)
```

## Tests

- `python-engine/tests/test_partner_sizing.py`: 27/27 PASS.
- Combined partner suite (advisory + renderer + sizing +
  orchestrator + hedge_readiness): 128/128 PASS.
- Agent regression: 338/338 PASS.

## Production untouched

No edits to `Production_Trading-sentinel/`. The helper is
a pure function and doesn't change any dispatch behavior.

## Next slice (E.6)

Audit-card-vs-rendered-card: read PROD's
`partner_advisory_ideas` table (read-only) and verify each
advisory's `rendered_card` is valid.
