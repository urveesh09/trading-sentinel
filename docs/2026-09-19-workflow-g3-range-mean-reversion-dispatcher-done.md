# Workflow G.3 — Range Mean-Reversion Dispatcher (DONE)

> **Superseded timing detail:** G.7 found that this slice selected the last
> candidate up to the deadline while generic execution could start earlier.
> `2026-09-19-g7-range-comparison-causality-plan.md` corrects that temporal
> leakage, insufficient-history fallback and comparison alias gate. This file
> remains the historical G.3 receipt, not the current timing contract.

Date: 2026-09-19

## What

Closed the G.3 gap: the `RANGE_REVERSION_V1` entry profile no longer falls
through to `COMPLETED_BAR_CONFIRMATION_V1` when the range thesis is invalid.

Before this slice, the matrix note was:

> `RANGE_REVERSION_V1` dispatcher still routes through
> completed-bar-confirmation fallback.

After this slice, the dispatcher short-circuits the trade and returns
`NO_FILL` with one of four reasons that name the violated invariant:

  - `RANGE_REVERSION_WAIT_RANGE_NOT_INTACT`
    (range_pct > max_range_pct)
  - `RANGE_REVERSION_WAIT_RANGE_EXPANDING`
    (recent half-window's range > 1.5× older half's range)
  - `RANGE_REVERSION_WAIT_NO_LOWER_TOUCH`
    (entry bar's low is above the touch threshold)
  - `RANGE_REVERSION_WAIT_INSUFFICIENT_BARS`
    (fewer than 14 history bars)

When the range IS intact and the entry bar DOES touch the lower band, the
dispatcher ENTERs (delegating to the standard COMPLETED_BAR_CONFIRMATION
simulator) AND replaces the proposal's stop with the verifier's strict
invalidation — i.e. the recent low minus the strict-stop epsilon.

## How

The dispatch lives in `python-engine/proactive_intelligence.py` at
`simulate_shadow_research_trial`. The new branch sits BEFORE the
`_normalise_shadow_bars` call so it can short-circuit on invalid theses.

The dispatcher:

1. Splits `future_bars` into history (`timestamp <= data_cutoff`) and
   entry-bar candidates (`data_cutoff < timestamp <= entry_deadline`).
2. Picks the LAST candidate as the entry bar (the most recent bar in the
   window). Falls back to the last history bar when no future bar exists.
3. Picks the LAST 14 history bars as the analysis window.
4. Calls `range_reversion.range_reversion_entry(analysis + [entry_bar])`.
5. On ENTER, replaces `profiled.stop` with the verifier's `strict_stop`.
6. On any WAIT_*, returns `NO_FILL` with `RANGE_REVERSION_<signal>` reason.

The new `range_reversion.py` module (committed alongside) is a pure
verifier with four configurable thresholds and a frozen
`RangeReversionVerdict` dataclass. No side effects.

## Tests

  - `tests/test_range_reversion.py`: 21 unit tests pinning the verifier.
  - `tests/test_range_reversion_dispatcher.py`: 6 integration tests
    pinning the dispatcher (ENTER, strict-stop propagation,
    WAIT_RANGE_NOT_INTACT, WAIT_NO_LOWER_TOUCH, WAIT_RANGE_EXPANDING,
    divergence from COMPLETED_BAR_CONFIRMATION).

Combined:
  - python-engine: **4061 passed, 4 skipped** (no regressions).
  - scripts: **193 passed** (1 pre-existing flaky excluded).
  - agent: **338 passed**.

## Files

  - `python-engine/range_reversion.py` (new) — pure verifier.
  - `python-engine/tests/test_range_reversion.py` (new) — 21 unit tests.
  - `python-engine/proactive_intelligence.py` (modified) — dispatcher branch.
  - `python-engine/tests/test_range_reversion_dispatcher.py` (new) — 6
    integration tests.
