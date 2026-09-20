# Workflow E.3 — hedge interpretation helper

## Source

Per Workstream E in `NEXT_AGENT_PLAN.md`:
> Hedge-first must have an explicit interpretation.
> Conditional protection states the exposure assumption and
> coverage; **market directional spreads are not
> automatically personalized hedges.** Ask for exposure
> details only if personalized protection is requested. Do
> not describe an unconfirmed action as taken/closed.

## Goal

A read-only CLI helper that classifies a hedge message
(the dict that would become a partner advisory) into one of
three buckets:

| Bucket | Meaning | Exit |
|---|---|---|
| `PERSONALIZED_PROTECTION` | The plan hedges an existing position the operator holds | 0 |
| `DIRECTIONAL_SPREAD` | The plan is a market view expressed as an option spread | 0 |
| `UNCLEAR` | Cannot be classified; the partner MUST ask before acting | 2 |

The helper does NOT change the dispatcher. It surfaces the
classification so the operator can decide whether the
message should be dispatched as a hedge, as a directional
trade, or held until exposure details are provided.

## Classification rules (in priority order)

1. **Strategy is in PERSONAL_PROTECTION_STRATEGIES**
   (`ProtectivePutPlan`, `CollarPlan`, `CoveredCallPlan`,
   snake_case variants) -> PERSONALIZED_PROTECTION, UNLESS
   `hedge_ratio == 0.0` (in which case the protection has
   no effect, treat as DIRECTIONAL_SPREAD).

2. **Strategy is in DIRECTIONAL_STRATEGIES**
   (`BullPutSpreadPlan`, `BearCallSpreadPlan`,
   `IronCondorPlan`, `LongStraddlePlan`, `LongStranglePlan`,
   snake_case variants) -> DIRECTIONAL_SPREAD, UNLESS
   `hedge_ratio > 0.0` (which is suspicious: a directional
   spread with hedge_ratio > 0 doesn't make sense; classify
   as UNCLEAR).

3. **Strategy is empty or unrecognized** -> UNCLEAR.

The `UNCLEAR` exit code is 2 to signal BLOCKER to the
dispatch pipeline: the partner MUST ask for the exposure
assumption before acting.

## Field-path resolution

The helper accepts multiple field naming conventions because
the plan / existing code use both:

- `strategy`, `plan_strategy`, `kind`, `advisory.strategy`,
  `hedge_plan.strategy` (in priority order).
- `hedge_ratio`, `ratio`, `coverage_ratio`,
  `protected_fraction`.
- `covered_units`, `held_units`,
  `underlying_position_units`, `exposure_units`.
- `protected_units`, `option_units`, `hedge_units`.

If at least one of each pair is present, the message is
treated as complete for that dimension.

## Tests

25/25 PASS in
`scripts/tests/test_interpret_hedge_message.py`. Combined
scripts/ suite: 148/148 PASS. Agent regression: 338/338
PASS.

## Production untouched

No edits to `Production_Trading-sentinel/`. Operator runs
the helper on dev or as a read-only check against the JSON
the dispatcher would produce.

## Usage

```bash
# Interpret a hedge message from a file.
python scripts/interpret_hedge_message.py path/to/hedge.json

# From stdin.
cat hedge.json | python scripts/interpret_hedge_message.py -

# JSON output for piping.
python scripts/interpret_hedge_message.py hedge.json --json
```

## Example output

```json
{
  "interpretation": "PERSONALIZED_PROTECTION",
  "strategy": "ProtectivePutPlan",
  "hedge_ratio": 1.0,
  "covered_units": 1,
  "protected_units": null,
  "reason": "strategy 'ProtectivePutPlan' is a personalized protection: the operator holds the underlying and this plan hedges that exposure.",
  "evidence_paths": ["strategy", "hedge_ratio", "covered_units"],
  "missing_fields": []
}
```

## Next slices (E.4 onward)

- **E.4 (potential)**: card-renderer — extract the Telegram
  message body assembly into a pure function so it can be
  unit-tested in isolation. Bounded refactor of
  `partner_manual_advisory.py:render_advisory_card`.
- **E.5 (potential)**: audit-card-vs-sent-card — diff
  between what the dispatcher produced and what Telegram
  recorded. Operator-owned (Telegram delivery log access).
- **E.6 (potential)**: liquidity-aware sizing — given a
  validated card and an order size, compute how many
  contracts can be filled at top-of-book without crossing
  the spread by more than `X` bps. Bounded dev work.
