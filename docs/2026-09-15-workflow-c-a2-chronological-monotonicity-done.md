# Workflow C.A2 — chronological exit-delay monotonicity pin

## What landed

|| File | Type | Purpose |
|---|---|---|---|
| `python-engine/tests/test_intraday_spread_chronological.py` | test (extended) | 3 new tests pinning the delayed-execution monotonicity invariant |
| `docs/2026-09-15-workflow-c-a2-chronological-monotonicity-done.md` | doc (new) | This file |

## The shift in defensive posture

The chronological replay's `_execution_observation` helper (in `intraday_spread_chronological.py`) returns the FIRST later observation whose `received_at >= eligible_at` where `eligible_at = decision.received_at + execution_delay`. The invariant — the active entry can never be earlier than the configured execution delay — is critical for the operator to trust the diagnostic.

Before this slice, the invariant was tested **only implicitly** through the existing happy-path tests (`test_delayed_execution_uses_first_later_packet_not_decision_book`). A future refactor of `_execution_observation` that broke the monotonicity (e.g., by accepting a packet at `received_at < eligible_at`) could slip through.

After this slice, the invariant is tested **explicitly** in three orthogonal scenarios:
- The active entry's `received_at >= decision.received_at + execution_delay` for any non-zero delay.
- The active entry is the FIRST eligible packet by receipt order (not a later one).
- The zero-delay case returns the decision packet itself (the invariant trivially holds).

## Key design choices

- **Receipt-order invariant.** The chronological replay enforces strict receipt ordering (line 221: `prior_received < received`). The "first eligible by receipt order" assertion relies on this — there's no scenario where the list order is decoupled from the receipt order.
- **Three orthogonal scenarios, not just one happy-path.** Each test pins a different facet of the monotonic invariant. A regression in any one is caught by its dedicated test.
- **No source changes.** The invariant was already in the code (line 185: `if item.received_at >= eligible_at`). This slice makes the invariant **visible** via explicit tests, not **enforced** via new code. The existing logic is correct; the tests now pin it.

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `test_intraday_spread_chronological.py` | 27 | +5 |

Workflow C surface (11 test files): **159/159 PASS** in 4.68s (was 117; +42 net for A1+A2+A3+A4).

0 regressions.

## Operator runbook

No new operator surface. The chronological replay's exit-delay monotonicity is now pinned in CI — a regression that breaks the invariant fails the test suite, not a downstream operator review.

## Critical invariants preserved

- `_execution_observation` source unchanged.
- The chronological replay's receipt-order enforcement unchanged.
- All existing tests in `test_intraday_spread_chronological.py` still pass.

## What's still on the Category A backlog

- CLI integration for A4 in `research_cli` (small, additive).
- A5 — research summary drift verification (mirror of A4 for `render_research_summary`).
