# Workflow E.4 — partner card renderer

## Source

Per Workstream E in `NEXT_AGENT_PLAN.md`:
> Improve cards around decisions a manual trader can take:
> index/exchange, timestamp/validity, setup rationale, entry
> trigger and bounded price, exact contract legs/expiry/lot,
> total debit and modeled costs, maximum defined loss,
> invalidation/target and intraday deadline. Explain
> uncertainty and liquidity limits without overwhelming the
> message.

## Goal

Extract the card-rendering logic from
`partner_manual_advisory.py:render_advisory_card` into a
pure module that takes a dict (the same shape
`_candidate_payload()` produces) and returns the rendered
Telegram card body. The original function was tightly
coupled to the `AdvisoryCandidate` dataclass, which made it
hard to test rendering without instantiating the whole
dataclass tree.

## What shipped

- **`python-engine/partner_card_renderer.py`** (new):
  - `render_card(card: dict) -> str` — dict-driven renderer.
  - `validate_rendered_card(text, card) -> list[str]` —
    asserts the rendered text contains every required piece
    per the plan's checklist (scope header, data+valid
    until, intraday warning, manual action warning, why_now,
    structure, per-leg full detail, invalidation,
    management, uncertainty, evidence).
  - `render_and_validate(card)` — composed entry point.
  - `MAX_TELEGRAM_CHARS = 4096` — Telegram's hard cap.
  - `CardRenderError` — raised on over-limit or malformed
    cards. Operators see this as
    `advisory_card_over_telegram_limit` and the upstream
    caller short-circuits.

- **`python-engine/partner_manual_advisory.py`**: refactored
  `render_advisory_card` to delegate to the new module. The
  text output is byte-identical for the same input — proven
  by the existing 24 partner_manual_advisory tests passing
  without modification.

- **`python-engine/tests/test_partner_card_renderer.py`**
  (new): 36 tests pinning the renderer contract.

## Per-scope rendering

| Scope | Per-leg | Bounded price | Max loss label | Other |
|---|---|---|---|---|
| `MARKET_SETUP` | side/ratio/symbol/expiry/strike/type/lot/bid/ask | "Act only if: combined debit ≤ ₹N before fees" | "Risk: theoretical maximum loss" | breakevens, target, etc. |
| `CONDITIONAL_PROTECTION` | same | none | "Protection premium at risk" + "; this is not the loss bound of an unknown protected position" | coverage assumption |

The renderer enforces the differentiated labels per the
plan's rule: "Conditional protection states the exposure
assumption and coverage; market directional spreads are not
automatically personalized hedges."

## Tests

- `python-engine/tests/test_partner_card_renderer.py`: 36/36 PASS.
- Combined partner_manual_advisory + partner_card_renderer:
  60/60 PASS.
- Combined partner orchestrator + hedge readiness:
  101/101 PASS.
- Agent regression: 338/338 PASS.

## Production untouched

No edits to `Production_Trading-sentinel/`. The
`render_advisory_card` API is unchanged from the caller's
perspective; only the implementation is refactored to
delegate.

## Next slices (E.5 onward)

- **E.5** — liquidity-aware sizing — compute how many
  contracts can fill at top-of-book without crossing the
  spread.
- **E.6** — audit-card-vs-sent-card (operator-owned;
  requires Telegram delivery log access).
