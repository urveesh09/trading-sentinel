"""[WORKFLOW-F 2026-09-13] Affordability guard acceptance.

Closes F2 (sub-slices F2.a, F2.b, F2.c) of workstream F per
``docs/2026-09-13-workflow-f-state-of-codebase-audit.md`` section 6
future plan. F2 ships:

1. F2.a \u2014 a new ``affordability`` module with one advisor function
   (``evaluate_paper_to_live_affordability``) and one guard function
   (``assert_live_affordable_from_paper``) and the supporting data
   shapes (``AffordabilityThresholds``, ``AffordabilityEvaluation``,
   ``AffordabilityVerdict``, ``AffordabilityRefusal``).
2. F2.b \u2014 the guard is fail-closed: every ambiguity raises
   ``AffordabilityRefusal``.
3. F2.c \u2014 the wired entry points live in the orchestrators; this
   test file verifies the guard in isolation and does not couple to
   the live/paper orchestrator code paths.

The guard is a pure function: it does **no** ledger I/O. Every
input is supplied by the caller. This file proves the guard's
mathematical behaviour in isolation, including the failure surfaces
the integration sites will rely on (``LIVE_NOT_ARMED`` for FNO today
because ``FNO_LIVE_BANKROLL == 0``).

The tests are exhaustive along the decision tree:
  - affordability verdict across the five buckets;
  - guard's raise path raises ``AffordabilityRefusal`` exactly when the
    evaluation verdict is non-affordable;
  - the LIVE_NOT_ARMED bucket rejects even very small live increases;
  - the threshold guard (positive/finite/10x cap) blocks misconfig at
    construction time;
  - the AFFORDABLE bucket returns an evaluation with empty refusal list;
  - simultaneous bucket firings surface MARGIN_EXCEEDED first (the more
    specific ceiling) and carry both refusal reasons for triage;
  - the ``evaluate`` function never raises (bad-args become
    ``INVALID_INPUT`` evaluation), but the ``assert`` guard does;
  - the ``evaluate`` / ``assert`` distinction matters: dashboards
    call ``evaluate``; pre-trade guards call ``assert``.

The contract being tested maps 1:1 to ``docs/2026-09-13-workflow-f-state-of-codebase-audit.md``
section 6 future plan's F2 deliverables.
"""
from __future__ import annotations

import pytest

from affordability import (
    AffordabilityEvaluation,
    AffordabilityRefusal,
    AffordabilityThresholds,
    AffordabilityVerdict,
    assert_live_affordable_from_paper,
    evaluate_paper_to_live_affordability,
)


# ---------------------------------------------------------------------------
# Common inputs.
# ---------------------------------------------------------------------------

# A *minimal* default; individual tests opt in to ``paper_pnl_inr``
# explicitly. Keeping it out of the base avoids the duplicate-kwarg
# failure mode where a per-test override collides with the base.
_BASE_KW = dict(
    live_source="EDGE_LIVE",
    paper_source="EDGE_PAPER",
    live_current_inr=1000.0,
)

_ZERO_PAPER = dict(paper_pnl_inr=0.0)


def _call(proposed_delta_inr, **overrides):
    """Convenience wrapper so each test only states the args it varies.

    Defaults to ``paper_pnl_inr=0.0``. Tests that want a non-zero
    paper value pass it in ``**overrides``.
    """
    merged = {**_BASE_KW, **_ZERO_PAPER, "proposed_delta_inr": proposed_delta_inr}
    merged.update(overrides)
    return evaluate_paper_to_live_affordability(**merged)


# ---------------------------------------------------------------------------
# 1. Thresholds construction (the configuration is itself a guard).
# ---------------------------------------------------------------------------

class TestAffordabilityThresholds:
    def test_defaults_match_promotion_bridge_contract_section_4(self) -> None:
        """Defaults trace to the bridge contract document, not invention.

        ``docs/2026-09-13-workflow-g-promotion-bridge.md`` section 4
        states the bridge requires ``requested_live_delta <=
        LIVE_BANKROLL * 1.5`` and paper P&L no more than ``LIVE_BANKROLL *
        2``. The defaults here reproduce those numbers verbatim. A
        future contributor who changes either default must surface
        the change in a contract doc as well.
        """
        t = AffordabilityThresholds()
        assert t.margin_multiplier == 1.5
        assert t.paper_pnl_ratio == 2.0
        assert t.maximum_live_delta_inr == 1_000_000.0

    def test_non_finite_values_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive and finite"):
            AffordabilityThresholds(margin_multiplier=0)
        with pytest.raises(ValueError, match="positive and finite"):
            AffordabilityThresholds(paper_pnl_ratio=-1.0)
        with pytest.raises(ValueError, match="positive and finite"):
            AffordabilityThresholds(margin_multiplier=float("nan"))
        with pytest.raises(ValueError, match="positive and finite"):
            AffordabilityThresholds(margin_multiplier=float("inf"))

    def test_non_numeric_types_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite number"):
            AffordabilityThresholds(margin_multiplier="1.5")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="finite number"):
            AffordabilityThresholds(paper_pnl_ratio=None)  # type: ignore[arg-type]
        # ``bool`` is technically an int in Python; the guard
        # explicitly rejects it because ``isinstance(True, int)``
        # would otherwise accept silent booleans for margins.
        with pytest.raises(ValueError, match="finite number"):
            AffordabilityThresholds(margin_multiplier=True)  # type: ignore[arg-type]

    def test_extreme_margin_capped(self) -> None:
        """Generosity is configurable up to 10x; beyond that it is a bug."""
        with pytest.raises(ValueError, match="10x cap"):
            AffordabilityThresholds(margin_multiplier=11.0)
        with pytest.raises(ValueError, match="10x cap"):
            AffordabilityThresholds(margin_multiplier=1000.0)
        # The boundary itself is allowed.
        AffordabilityThresholds(margin_multiplier=10.0)


# ---------------------------------------------------------------------------
# 2. ``evaluate`` produces the right verdict for every decision bucket.
#    ``evaluate`` never raises; bad shapes return INVALID_INPUT evaluation.
# ---------------------------------------------------------------------------

class TestEvaluateVerdicts:
    """Each bucket of the decision tree gets its own test, asserting both
    the verdict and the *specific* refusal message so a future
    contributor who breaks one bucket knows which.
    """

    def test_affordable_baseline(self) -> None:
        ev = _call(1000.0)
        assert ev.verdict == AffordabilityVerdict.AFFORDABLE
        assert ev.is_affordable() is True
        assert ev.refusal_reasons == []

    def test_margin_exceeded(self) -> None:
        """Live 1000 * 1.5 = 1500 max. Delta of 2000 must fail."""
        ev = _call(2000.0)
        assert ev.verdict == AffordabilityVerdict.MARGIN_EXCEEDED
        assert ev.refusal_reasons, "expected at least one refusal reason"
        assert any("margin_multiplier" in r for r in ev.refusal_reasons), (
            f"expected a margin_multiplier message in {ev.refusal_reasons}"
        )

    def test_margin_exactly_at_boundary_is_affordable(self) -> None:
        """The boundary is *inclusive* on the affordable side.

        Live 1000 * 1.5 = 1500. A delta of exactly 1500 is *not*
        strictly greater than the ceiling, so the boundary is
        affordable. Ceilings are *inclusive* on the allowed side and
        *exclusive* on the refusal side: a delta at the ceiling
        passes; a delta beyond the ceiling fails.
        """
        ev = _call(1500.0)
        assert ev.verdict == AffordabilityVerdict.AFFORDABLE
        # One rupee beyond the ceiling rejects.
        ev = _call(1500.01)
        assert ev.verdict == AffordabilityVerdict.MARGIN_EXCEEDED

    def test_paper_pnl_positive_out_of_band(self) -> None:
        """Paper P&L 2500 against live 1000 exceeds 2x = 2000."""
        ev = _call(500.0, paper_pnl_inr=2500.0)
        assert ev.verdict == AffordabilityVerdict.PAPER_PNL_OUT_OF_BAND
        assert any("out-earns the live pool" in r for r in ev.refusal_reasons), (
            f"expected an out-earns message in {ev.refusal_reasons}"
        )

    def test_paper_pnl_negative_beyond_floor(self) -> None:
        """Paper drawdown 2500 against live 1000 = abs(paper_pnl) exceeds 2x."""
        ev = _call(500.0, paper_pnl_inr=-2500.0)
        assert ev.verdict == AffordabilityVerdict.PAPER_PNL_OUT_OF_BAND
        assert any("deep paper drawdown" in r for r in ev.refusal_reasons), (
            f"expected a deep-paper-drawdown message in {ev.refusal_reasons}"
        )

    def test_paper_pnl_within_band_anywhere_is_affordable(self) -> None:
        """paper_pnl at exactly the boundary is *not* out-of-band (rule is strict)."""
        # Live 1000, ratio 2.0 -> floor 2000. paper = 2000 exactly.
        ev = _call(1000.0, paper_pnl_inr=2000.0)
        assert ev.verdict == AffordabilityVerdict.AFFORDABLE
        # Negative boundary: -2000.
        ev = _call(1000.0, paper_pnl_inr=-2000.0)
        assert ev.verdict == AffordabilityVerdict.AFFORDABLE

    def test_live_not_armed_zero_pool(self) -> None:
        """FNO today has ``FNO_LIVE_BANKROLL == 0``; this is the expected
        state, not an error. The guard returns ``LIVE_NOT_ARMED`` so
        the operator sees a clear refusal reason rather than a
        surprise ``AFFORDABLE``.
        """
        ev = evaluate_paper_to_live_affordability(
            live_source="FNO_LIVE",
            paper_source="FNO_PAPER",
            proposed_delta_inr=10.0,    # tiny increase
            live_current_inr=0.0,        # not armed today
            paper_pnl_inr=0.0,
        )
        assert ev.verdict == AffordabilityVerdict.LIVE_NOT_ARMED
        assert any("non-positive pool" in r for r in ev.refusal_reasons)

    def test_live_not_armed_negative_pool(self) -> None:
        """Live pool can be negative after large drawdowns; same refusal."""
        ev = evaluate_paper_to_live_affordability(
            live_source="EDGE_LIVE",
            paper_source="EDGE_PAPER",
            proposed_delta_inr=1.0,
            live_current_inr=-50.0,
            paper_pnl_inr=0.0,
        )
        assert ev.verdict == AffordabilityVerdict.LIVE_NOT_ARMED

    def test_live_not_armed_nan_pool_is_invalid_input(self) -> None:
        """NaN is a malformed *input*, not a runtime condition.

        The guard's input validator catches non-finite numerics and
        returns ``INVALID_INPUT``. This is intentional: a NaN that
        reaches the guard is almost certainly a programmer-level
        mistake (e.g. a NULL float from a DB read passed without a
        coercion). The ``LIVE_NOT_ARMED`` verdict is reserved for
        ``live_current_inr == 0``, the documented "not armed" state.
        """
        ev = evaluate_paper_to_live_affordability(
            live_source="EDGE_LIVE",
            paper_source="EDGE_PAPER",
            proposed_delta_inr=100.0,
            live_current_inr=float("nan"),
            paper_pnl_inr=0.0,
        )
        assert ev.verdict == AffordabilityVerdict.INVALID_INPUT
        assert any("finite" in r for r in ev.refusal_reasons), (
            "expected a finite-argument message in the refusal reasons"
        )

    def test_paper_pnl_nan_is_invalid_input(self) -> None:
        """A NaN paper P&L is malformed input; the verdict is INVALID_INPUT.

        The previous conceptual version of this test expected
        ``PAPER_PNL_OUT_OF_BAND``, but that conflates a data refusal
        (paper P&L out of band) with a programmer error (caller
        passing NaN). The guard distinguishes them: a NaN is a
        programmer error and returns ``INVALID_INPUT``; a finite
        out-of-band paper P&L is a data refusal and returns
        ``PAPER_PNL_OUT_OF_BAND``.
        """
        ev = _call(500.0, paper_pnl_inr=float("nan"))
        assert ev.verdict == AffordabilityVerdict.INVALID_INPUT

    def test_maximum_live_delta_ceiling(self) -> None:
        """Even an affordable delta beyond ``maximum_live_delta_inr`` rejects."""
        ev = evaluate_paper_to_live_affordability(
            live_source="EDGE_LIVE",
            paper_source="EDGE_PAPER",
            proposed_delta_inr=2_000_000.0,  # > default 1_000_000
            live_current_inr=10_000_000.0,
            paper_pnl_inr=0.0,
        )
        assert ev.verdict == AffordabilityVerdict.MARGIN_EXCEEDED
        assert any("maximum_live_delta_inr" in r for r in ev.refusal_reasons)

    def test_maximum_live_delta_evaluated_before_live_check(self) -> None:
        """A delta that exceeds the ceiling must reject even if the live pool
        would otherwise be sufficient. Order matters: ceiling first."""
        ev = evaluate_paper_to_live_affordability(
            live_source="EDGE_LIVE",
            paper_source="EDGE_PAPER",
            proposed_delta_inr=2_000_000.0,
            live_current_inr=0.0,        # not armed
            paper_pnl_inr=0.0,
        )
        # The ceiling fires before we ever check the live pool state.
        assert ev.verdict == AffordabilityVerdict.MARGIN_EXCEEDED
        assert "maximum_live_delta_inr" in ev.refusal_reasons[0]

    def test_simultaneous_margin_and_paper_failures_margin_first(self) -> None:
        """When both buckets fire, the verdict is MARGIN_EXCEEDED but
        both refusal messages are kept for triage."""
        ev = _call(2_500.0, paper_pnl_inr=-3_000.0)
        assert ev.verdict == AffordabilityVerdict.MARGIN_EXCEEDED
        assert len(ev.refusal_reasons) == 2
        joined = " ".join(ev.refusal_reasons)
        assert "margin_multiplier" in joined
        assert "deep paper drawdown" in joined

    def test_only_one_source_per_evaluation(self) -> None:
        ev = evaluate_paper_to_live_affordability(
            live_source="EDGE_PAPER",  # same as paper
            paper_source="EDGE_PAPER",
            proposed_delta_inr=100.0,
            live_current_inr=1000.0,
            paper_pnl_inr=0.0,
        )
        assert ev.verdict == AffordabilityVerdict.INVALID_INPUT
        assert any("must differ" in r for r in ev.refusal_reasons)


# ---------------------------------------------------------------------------
# 3. ``evaluate`` vs ``assert``: bad-shape behaviour.
#    Bad shapes come from programmer errors, not data refusals.
#    ``evaluate`` returns INVALID_INPUT (never raises); ``assert``
#    raises ``ValueError`` because that's how Python signals
#    programmer bugs that should crash tests and integrations.
# ---------------------------------------------------------------------------

class TestEvaluateVsAssertBadShape:
    def test_evaluate_returns_invalid_input_for_empty_live_source(self) -> None:
        result = evaluate_paper_to_live_affordability(
            live_source="",
            paper_source="EDGE_PAPER",
            proposed_delta_inr=100.0,
            live_current_inr=1000.0,
            paper_pnl_inr=0.0,
        )
        assert result.verdict == AffordabilityVerdict.INVALID_INPUT
        assert result.is_affordable() is False

    def test_assert_raises_value_error_for_empty_live_source(self) -> None:
        with pytest.raises(ValueError, match="live_source"):
            assert_live_affordable_from_paper(
                live_source="",
                paper_source="EDGE_PAPER",
                proposed_delta_inr=100.0,
                live_current_inr=1000.0,
                paper_pnl_inr=0.0,
            )

    def test_evaluate_returns_invalid_input_for_zero_proposed_delta(self) -> None:
        # Zero is not an "increase"; evaluate surfaces it as INVALID_INPUT.
        result = evaluate_paper_to_live_affordability(
            **_BASE_KW,
            proposed_delta_inr=0,
            paper_pnl_inr=0.0,
        )
        assert result.verdict == AffordabilityVerdict.INVALID_INPUT
        assert any("must be positive" in r for r in result.refusal_reasons)

    def test_assert_raises_value_error_for_zero_proposed_delta(self) -> None:
        with pytest.raises(ValueError, match="must be positive for an affordability"):
            assert_live_affordable_from_paper(
                **_BASE_KW,
                proposed_delta_inr=0,
                paper_pnl_inr=0.0,
            )

    def test_assert_raises_value_error_for_negative_proposed_delta(self) -> None:
        with pytest.raises(ValueError, match="must be positive for an affordability"):
            assert_live_affordable_from_paper(
                **_BASE_KW,
                proposed_delta_inr=-100.0,
                paper_pnl_inr=0.0,
            )

    def test_evaluate_returns_invalid_input_for_non_numeric_proposed(self) -> None:
        # Note: type checker treats ``"100"`` as a string, so the
        # ``type: ignore`` lets Python evaluate the runtime path.
        result = evaluate_paper_to_live_affordability(
            **_BASE_KW,
            proposed_delta_inr="100",  # type: ignore[arg-type]
            paper_pnl_inr=0.0,
        )
        assert result.verdict == AffordabilityVerdict.INVALID_INPUT


# ---------------------------------------------------------------------------
# 4. ``assert_live_affordable_from_paper`` integration behaviour.
# ---------------------------------------------------------------------------

class TestAssertLiveAffordable:
    """The guard variant raises ``AffordabilityRefusal`` for any
    non-affordable verdict. The exception carries the evaluation so
    callers can serialise it for audit.
    """

    def test_affordable_returns_evaluation(self) -> None:
        ev = assert_live_affordable_from_paper(
            live_source="EDGE_LIVE",
            paper_source="EDGE_PAPER",
            proposed_delta_inr=1000.0,
            live_current_inr=2000.0,
            paper_pnl_inr=0.0,
        )
        assert ev.is_affordable() is True
        assert isinstance(ev, AffordabilityEvaluation)

    def test_margin_exceeded_raises_with_result_attached(self) -> None:
        with pytest.raises(AffordabilityRefusal) as excinfo:
            assert_live_affordable_from_paper(
                live_source="EDGE_LIVE",
                paper_source="EDGE_PAPER",
                proposed_delta_inr=10_000.0,
                live_current_inr=1000.0,
                paper_pnl_inr=0.0,
            )
        refusal = excinfo.value
        assert refusal.result.verdict == AffordabilityVerdict.MARGIN_EXCEEDED
        assert len(refusal.result.refusal_reasons) >= 1

    def test_live_not_armed_raises(self) -> None:
        """The every-day-path case: FNO live today is 0."""
        with pytest.raises(AffordabilityRefusal) as excinfo:
            assert_live_affordable_from_paper(
                live_source="FNO_LIVE",
                paper_source="FNO_PAPER",
                proposed_delta_inr=10.0,
                live_current_inr=0.0,
                paper_pnl_inr=0.0,
            )
        refusal = excinfo.value
        assert refusal.result.verdict == AffordabilityVerdict.LIVE_NOT_ARMED

    def test_paper_pnl_out_of_band_raises(self) -> None:
        with pytest.raises(AffordabilityRefusal) as excinfo:
            assert_live_affordable_from_paper(
                live_source="EDGE_LIVE",
                paper_source="EDGE_PAPER",
                proposed_delta_inr=500.0,
                live_current_inr=1000.0,
                paper_pnl_inr=-5000.0,
            )
        refusal = excinfo.value
        assert refusal.result.verdict == AffordabilityVerdict.PAPER_PNL_OUT_OF_BAND

    def test_refusal_message_is_informative(self) -> None:
        """The exception string carries the summary; humans can read
        the exception without unpacking ``result``.
        """
        with pytest.raises(AffordabilityRefusal) as excinfo:
            assert_live_affordable_from_paper(
                live_source="EDGE_LIVE",
                paper_source="EDGE_PAPER",
                proposed_delta_inr=2_000.0,
                live_current_inr=1000.0,
                paper_pnl_inr=0.0,
            )
        message = str(excinfo.value)
        assert "verdict=MARGIN_EXCEEDED" in message
        assert "EDGE_LIVE" in message
        assert "EDGE_PAPER" in message
        assert "margin_multiplier" in message


# ---------------------------------------------------------------------------
# 5. Cross-call consistency: identical inputs always produce identical results.
# ---------------------------------------------------------------------------

class TestDeterministic:
    """Reproduction contract: same inputs produce the same verdict and
    the same refusal reasons in the same order. The bridge audit
    pipeline relies on this for replay reproducibility.
    """

    def test_same_inputs_produce_identical_evaluations(self) -> None:
        kwargs = dict(
            live_source="EDGE_LIVE",
            paper_source="EDGE_PAPER",
            proposed_delta_inr=2000.0,
            live_current_inr=1000.0,
            paper_pnl_inr=-3000.0,
        )
        first = evaluate_paper_to_live_affordability(**kwargs)
        second = evaluate_paper_to_live_affordability(**kwargs)
        assert first.verdict == second.verdict
        assert first.refusal_reasons == second.refusal_reasons
        assert first.checks == second.checks

    def test_checks_dict_records_every_comparison(self) -> None:
        """A future audit can reproduce the verdict from the checks."""
        ev = evaluate_paper_to_live_affordability(
            live_source="EDGE_LIVE",
            paper_source="EDGE_PAPER",
            proposed_delta_inr=1501.0,
            live_current_inr=1000.0,
            paper_pnl_inr=2001.0,
        )
        assert ev.checks["proposed_delta_inr"] == 1501.0
        assert ev.checks["live_current_inr"] == 1000.0
        assert ev.checks["paper_pnl_inr"] == 2001.0
        assert ev.checks["margin_multiplier"] == 1.5
        assert ev.checks["paper_pnl_ratio"] == 2.0
        assert ev.checks["maximum_live_delta_inr"] == 1_000_000.0


# ---------------------------------------------------------------------------
# 6. Custom thresholds (the F6 seam).
# ---------------------------------------------------------------------------

class TestCustomThresholds:
    """F6 capital-policy work may construct a custom thresholds object
    drawn from operator-declared loss tolerance. The guard is
    parameterised on ``AffordabilityThresholds`` precisely so a
    tightening does not require re-implementing the guard.
    """

    def test_tighter_margin_blocks_previously_affordable_delta(self) -> None:
        loose = _call(1400.0)  # within default 1.5x
        assert loose.verdict == AffordabilityVerdict.AFFORDABLE

        tight = evaluate_paper_to_live_affordability(
            **_BASE_KW,
            proposed_delta_inr=1400.0,
            paper_pnl_inr=0.0,
            thresholds=AffordabilityThresholds(margin_multiplier=0.5, paper_pnl_ratio=2.0),
        )
        assert tight.verdict == AffordabilityVerdict.MARGIN_EXCEEDED

    def test_relaxed_paper_pnl_ratio_admits_previously_rejected(self) -> None:
        blocked = _call(500.0, paper_pnl_inr=3000.0)
        assert blocked.verdict == AffordabilityVerdict.PAPER_PNL_OUT_OF_BAND

        relaxed = evaluate_paper_to_live_affordability(
            **_BASE_KW,
            proposed_delta_inr=500.0,
            paper_pnl_inr=3000.0,
            thresholds=AffordabilityThresholds(margin_multiplier=1.5, paper_pnl_ratio=4.0),
        )
        assert relaxed.verdict == AffordabilityVerdict.AFFORDABLE

    def test_lower_maximum_live_delta_ceiling(self) -> None:
        ev = evaluate_paper_to_live_affordability(
            live_source="EDGE_LIVE",
            paper_source="EDGE_PAPER",
            proposed_delta_inr=10_500.0,
            live_current_inr=100_000.0,
            paper_pnl_inr=0.0,
            thresholds=AffordabilityThresholds(maximum_live_delta_inr=10_000.0),
        )
        assert ev.verdict == AffordabilityVerdict.MARGIN_EXCEEDED
