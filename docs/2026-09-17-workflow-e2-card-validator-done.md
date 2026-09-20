# Workflow E.2 — partner card validator

## Source

Per Workstream E in `NEXT_AGENT_PLAN.md`:
> Improve cards around decisions a manual trader can take:
> index/exchange, timestamp/validity, setup rationale, entry
> trigger and bounded price, exact contract legs/expiry/lot,
> total debit and modeled costs, maximum defined loss,
> invalidation/target and intraday deadline. Explain
> uncertainty and liquidity limits without overwhelming the
> message.
>
> Hedge-first must have an explicit interpretation.
> Conditional protection states the exposure assumption and
> coverage; market directional spreads are not automatically
> personalized hedges. Ask for exposure details only if
> personalized protection is requested. Do not describe an
> unconfirmed action as taken/closed.

## Goal

A bounded dev-side validator for the partner card payload
(the dict `_candidate_payload()` produces in
`partner_manual_advisory.py`). The validator runs as a
read-only CLI: it takes a JSON card and reports which
required fields are present, missing, or wrong-typed, and
surfaces the bounded improvements the plan asks for
(liquidity limits, hedge interpretation).

The validator does NOT change the partner dispatcher — it
catches missing fields before they reach Telegram so the
operator can fix the upstream producer.

## What it checks

### Required fields (per scope)

**Common (every scope)**:
- `scope`, `underlying`, `exchange`
- `quote_time`, `valid_until` (timestamp/validity)
- `policy_version`, `evidence`, `thesis_id`
- `legs` (array, ≥1 leg, each well-formed)
- `why_now`, `uncertainty`, `invalidation`, `management`
- `holding_horizon`, `management_deadline`

**`MARKET_SETUP` scope** (in addition):
- `net_debit_rs` or `net_credit_rs` (bounded price)
- `max_loss_rs`, `breakevens`
- `trigger_level`, `invalidation_level`, `target_level`
- `estimated_round_trip_cost_rs`

**`CONDITIONAL_PROTECTION` scope** (in addition):
- `exposure_assumption` (hedge interpretation)
- `coverage_units`

### Type / format checks

- Scope is one of `MARKET_SETUP` / `CONDITIONAL_PROTECTION`.
- Evidence is one of `QUALIFIED_FOR_ADVISORY` / `RESEARCH_PREVIEW`.
- Exchange is one of `NSE` / `BSE`.
- Timestamps are ISO 8601 with timezone.
- Calendar dates (leg `expiry`) are real (not `2026-13-99`).

### Per-leg checks (each leg must have)

- `side`: BUY / SELL.
- `option_type`: CE / PE.
- `ratio`: positive integer.
- `lot_size`: positive integer.
- `expiry`: ISO date (real, not syntactically).
- `strike`: positive number.
- `bid_quantity` / `ask_quantity` (WARN if missing — the
  operator can't size against top-of-book without these).

### Economics invariants

- `net_debit_rs` > 0 if set.
- `net_credit_rs` > 0 if set.
- `valid_until` > `quote_time` (strict).

### Hedge interpretation

For `CONDITIONAL_PROTECTION` scope, `exposure_assumption`
must contain one of:
- `long underlying` / `short underlying` / `held underlying`
- `personalized` / `owner holds` / `personal exposure`
- `generic` / `any holder` / `hypothetical` / `market view`

Per the plan: "Hedge-first must have an explicit
interpretation. Conditional protection states the exposure
assumption and coverage; market directional spreads are not
automatically personalized hedges."

### Status taxonomy

| Status | Exit code | Meaning |
|---|---|---|
| `PASS` | 0 | All checks passed |
| `WARN` | 0 | Soft gap (operator-actionable, non-blocking) |
| `FAIL` | 1 | Required field missing or wrong type |
| `BLOCKER` | 2 | Input is malformed (not a dict, missing file) |

WARNs do not block — they're the bounded improvement
hints (liquidity, hedge interpretation).

## What it does NOT do

- Does NOT mutate any state.
- Does NOT place orders.
- Does NOT send Telegram messages.
- Does NOT call live broker APIs.
- Does NOT change the dispatcher; it inspects a payload.

## Usage

```bash
# Validate a card from a file.
python scripts/validate_partner_card.py path/to/card.json

# Validate from stdin.
cat card.json | python scripts/validate_partner_card.py -

# Machine-readable JSON for piping.
python scripts/validate_partner_card.py card.json --json
```

## Tests

27/27 PASS in `scripts/tests/test_validate_partner_card.py`.
Combined scripts/ suite: 123/123 PASS.
Agent suite: 338/338 PASS (regression check).

## Production untouched

No edits to `Production_Trading-sentinel/`. Operator runs
the validator on dev or as a read-only check against the
JSON the dispatcher would produce.

## Next slice (E.3)

Hedge interpretation helper — read-only helper that, given
a hedge message + the operator's exposure assumption,
surfaces whether the message is personalized protection or
directional spread. E.2 emits WARN for vague assumptions;
E.3 surfaces the interpretation explicitly.
