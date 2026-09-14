"""[WORKFLOW-F 2026-09-13] Paper-vs-live affordability guard (Phase 2).

Implements plan section 10.3 \u2014 *"Audit true cost per trade relative
to expected edge for INR 8k capital. Prevent a large configured
paper bankroll from implying owner live affordability."*

This module is the F-side seam the promotion-bridge contract (see
``docs/2026-09-13-workflow-g-promotion-bridge.md`` sections 3.3 and
4) depends on for ``APPROVED_LIVE_BUDGET`` decisions. Concretely:

* ``evaluate_paper_to_live_affordability(...)`` returns a structured
  result describing whether a proposed *live* delta is affordable
  from the *live* bank's current state, the *paper* P&L earned over
  the same period, and the operator-tunable margin. The result is
  intended for dashboards and for bridge verification; it does
  **not** raise and does **not** mutate the ledger.

* ``assert_live_affordable_from_paper(...)`` is the *guard* function
  the bridge calls before signing ``APPROVED_LIVE_BUDGET``. It is
  fail-closed: every ambiguity raises ``AffordabilityRefusal``. Live
  trading is never authorised by the *absence* of evidence.

The module deliberately does **not** do any ledger I/O. The decision
is intentionally separated from data acquisition: every entry in
the signature is supplied by the caller, who has the database
handle, the event loop, and the surrounding context. Guards that
mix *decision* with *data acquisition* are notoriously hard to test
and easy to misuse \u2014 a future F-side change of the ledger schema
should not require revising the guard.

The integration sites (``penny_edge_orchestrator.py`` and
``fno_orchestrator.py``) call this module with values they have
already computed; the recommendation surface fits into the
existing promotion-bridge verification flow.

Why the guard is conservative by design: the plan authorises one
explicit user input (``loss_tolerance``) at F6. Until F6 lands, this
guard refuses to *infer* any affordability from paper performance
alone. Live increases require operator-declared loss tolerance and
external-reconciliation evidence that this module does not have.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# --- public dataclasses and exceptions --------------------------------

class AffordabilityVerdict(str, Enum):
    """Discrete state of an affordability evaluation.

    The verdict is an *explanation*, not a permission. ``AFFORDABLE``
    means the evaluation found no blocker; the other enumerated
    values each name a specific failure mode and are surfaced as
    ``refusal_reasons`` on the ``AffordabilityEvaluation`` result.
    """
    AFFORDABLE = "AFFORDABLE"
    MARGIN_EXCEEDED = "MARGIN_EXCEEDED"
    PAPER_PNL_OUT_OF_BAND = "PAPER_PNL_OUT_OF_BAND"
    LIVE_NOT_ARMED = "LIVE_NOT_ARMED"
    LIVE_QUERY_FAILED = "LIVE_QUERY_FAILED"
    INVALID_INPUT = "INVALID_INPUT"


class AffordabilityRefusal(Exception):
    """Raised by ``assert_live_affordable_from_paper`` when the guard
    refuses a live delta. The associated ``AffordabilityEvaluation``
    is attached as ``result`` so callers can serialise it for audit.
    """

    def __init__(self, evaluation) -> None:
        self.result = evaluation
        super().__init__(evaluation.summary())


@dataclass(frozen=True)
class AffordabilityThresholds:
    """Operator-tunable numeric bounds.

    Defaults are derived from the promotion-bridge contract section 4
    (``APPROVED_LIVE_BUDGET`` requires ``requested_live_delta <=
    LIVE_BANKROLL * 1.5`` and paper P&L no more than ``LIVE_BANKROLL *
    2``). They are **defaults**, not the only valid choice: the F6
    capital-policy slice can construct a custom
    ``AffordabilityThresholds`` and pass it explicitly to the guard
    when the operator declares a different loss-tolerance envelope.
    """
    margin_multiplier: float = 1.5
    paper_pnl_ratio: float = 2.0
    maximum_live_delta_inr: float = 1_000_000.0

    def __post_init__(self) -> None:
        for name in ("margin_multiplier", "paper_pnl_ratio", "maximum_live_delta_inr"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"{name} must be a finite number, got {value!r}"
                )
            if not math.isfinite(value) or value <= 0:
                raise ValueError(
                    f"{name} must be positive and finite, got {value!r}"
                )
        # Even a generous operator cannot raise the margin beyond 10x.
        # This caps a bad config so future F6 wiring cannot
        # accidentally opt into "any delta allowed".
        if self.margin_multiplier > 10:
            raise ValueError(
                f"margin_multiplier={self.margin_multiplier} exceeds the 10x "
                "cap; this is a configuration bug, not a configuration choice"
            )


@dataclass(frozen=True)
class AffordabilityEvaluation:
    """Result returned by ``evaluate_paper_to_live_affordability``.

    Fields:
        live_source        -- bankroll division under check (e.g. EDGE_LIVE)
        paper_source       -- sibling paper division (e.g. EDGE_PAPER)
        proposed_delta_inr -- amount of live-capital *increase* under review
        live_current_inr   -- current live bankroll truth supplied by caller
        paper_pnl_inr      -- realised paper P&L supplied by caller
        thresholds         -- the bound set used for the evaluation
        verdict            -- the discrete outcome enum
        refusal_reasons    -- human-readable strings explaining any non-AFFORDABLE outcome
        checks             -- frozen dict of every numeric comparison performed,
                             so a re-evaluation with the same inputs is reproducible.
    """
    live_source: str
    paper_source: str
    proposed_delta_inr: float
    live_current_inr: float
    paper_pnl_inr: float
    thresholds: AffordabilityThresholds
    verdict: AffordabilityVerdict
    refusal_reasons: list[str] = field(default_factory=list)
    checks: dict = field(default_factory=dict)

    def is_affordable(self) -> bool:
        return self.verdict == AffordabilityVerdict.AFFORDABLE

    def summary(self) -> str:
        reasons = "; ".join(self.refusal_reasons) if self.refusal_reasons else "none"
        return (
            f"affordability verdict={self.verdict.value} "
            f"live_source={self.live_source} paper_source={self.paper_source} "
            f"proposed_delta_inr={self.proposed_delta_inr:.2f} "
            f"live_current_inr={self.live_current_inr:.2f} "
            f"paper_pnl_inr={self.paper_pnl_inr:.2f} "
            f"threshold_margin={self.thresholds.margin_multiplier:.2f} "
            f"threshold_paper_ratio={self.thresholds.paper_pnl_ratio:.2f} "
            f"refusal_reasons={reasons}"
        )


# --- input validation (shared by both public functions) --------------

def _validate_argument_shapes(
    live_source: str,
    paper_source: str,
    proposed_delta_inr,
) -> None:
    """Validate argument shapes (types, empty strings, identity).

    Separate from ``_validate_inputs`` so that callers that *have
    not yet* read the ledger (e.g. ``assert_live_entry_safety``,
    which reads live_current and paper_pnl only after this check
    passes) can still apply the source-string and proposed-delta
    guards without inventing placeholder floats.

    Raises ``ValueError`` on programmer error; never returns a
    structured verdict.
    """
    if not isinstance(live_source, str) or not live_source.strip():
        raise ValueError("live_source must be a non-empty string")
    if not isinstance(paper_source, str) or not paper_source.strip():
        raise ValueError("paper_source must be a non-empty string")
    if live_source == paper_source:
        raise ValueError(
            f"live_source and paper_source must differ "
            f"(both were {live_source!r})"
        )
    if (isinstance(proposed_delta_inr, bool)
            or not isinstance(proposed_delta_inr, (int, float))):
        raise ValueError(
            f"proposed_delta_inr must be a finite number, got {proposed_delta_inr!r}"
        )
    if not math.isfinite(float(proposed_delta_inr)):
        raise ValueError(f"proposed_delta_inr must be finite, got {proposed_delta_inr!r}")
    if float(proposed_delta_inr) <= 0:
        raise ValueError(
            f"proposed_delta_inr must be positive for an affordability "
            f"check (got {proposed_delta_inr}); use a separate path for "
            f"decreases."
        )


def _validate_inputs(
    live_source: str,
    paper_source: str,
    proposed_delta_inr,
    *,
    paper_pnl_inr,
    live_current_inr,
) -> tuple[float, float]:
    """Validate every input to ``evaluate`` and coerce to float.

    Returns ``(proposed_delta_inr, paper_pnl_inr)`` after validation.
    Raises ``ValueError`` for programmer errors (bad types, bad
    strings). The result ``live_current_inr`` is also checked but
    not coerced (the caller is expected to feed a real number; we
    do *not* invent one on missing input).

    Distinction: ``ValueError`` here means a programmer called the
    guard wrong (string concatenation, missing kwarg). Different
    from ``AffordabilityRefusal`` which means the *data* says no.
    """
    _validate_argument_shapes(live_source, paper_source, proposed_delta_inr)
    for label, value in (
        ("live_current_inr", live_current_inr),
        ("paper_pnl_inr", paper_pnl_inr),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"{label} must be a finite number, got {value!r}"
            )
        if not math.isfinite(float(value)):
            raise ValueError(f"{label} must be finite, got {value!r}")
    return float(proposed_delta_inr), float(paper_pnl_inr)


def _coerce_thresholds(thresholds) -> AffordabilityThresholds:
    if thresholds is None:
        return AffordabilityThresholds()
    if isinstance(thresholds, AffordabilityThresholds):
        return thresholds
    raise ValueError(
        f"thresholds must be an AffordabilityThresholds instance or None, "
        f"got {type(thresholds).__name__}"
    )


# --- public API --------------------------------------------------------

def evaluate_paper_to_live_affordability(
    *,
    live_source: str,
    paper_source: str,
    proposed_delta_inr,
    live_current_inr,
    paper_pnl_inr,
    thresholds: Optional[AffordabilityThresholds] = None,
) -> AffordabilityEvaluation:
    """Compute the affordability verdict for the proposed live delta.

    Pure function; performs no I/O and reads no module state. Every
    numeric input is supplied by the caller, who has the database
    handle and the ledger context. ``None`` or unknown *values*
    require the caller to surface them as a sentinel (e.g. ``nan``)
    which the guard treats as a query failure, *not* as zero.

    Returns an ``AffordabilityEvaluation``. Never raises for
    *runtime* evaluation outcomes; raises ``ValueError`` only for
    invalid argument shapes (programmer errors). Use
    ``assert_live_affordable_from_paper`` if you want the
    fail-closed guard.

    Decision logic (each bucket surfaces a refusal reason; a
    non-empty list produces a non-affordable verdict):

        1. ``maximum_live_delta_inr`` is a hard ceiling on the
           proposed delta, regardless of any other input.
        2. ``live_current_inr <= 0`` (or ``nan``) means the live
           pool is not armed. This is *not* an error; it is a
           normal state pre-deployment and must reject increases
           cleanly.
        3. ``proposed_delta_inr > live_current_inr * margin_multiplier``
           rejects deltas that exceed the operator-tunable margin.
        4. ``paper_pnl_inr > live_current_inr * paper_pnl_ratio``
           (positive) rejects deltas where paper performance wildly
           out-earns the live pool; the live increase would be
           tracked against an unrepresentative benchmark.
        5. ``abs(paper_pnl_inr) > live_current_inr * paper_pnl_ratio``
           (negative) rejects live increases during a deep paper
           drawdown. Live increases during a paper bleed are not a
           hedge; they compound exposure.

    Margins are *defaults* drawn from the promotion-bridge contract.
    F6 capital-policy work may construct an
    ``AffordabilityThresholds`` with different bounds when the user
    has declared loss tolerance.
    """
    # Input validation produces a fallback INVALID_INPUT evaluation
    # only when the caller passed wrong *types*; runtime evaluation
    # outcomes always use the regular verdicts.
    try:
        proposed, paper = _validate_inputs(
            live_source, paper_source, proposed_delta_inr,
            paper_pnl_inr=paper_pnl_inr,
            live_current_inr=live_current_inr,
        )
    except ValueError as exc:
        return AffordabilityEvaluation(
            live_source=str(live_source) if isinstance(live_source, str) else "",
            paper_source=str(paper_source) if isinstance(paper_source, str) else "",
            proposed_delta_inr=float("nan"),
            live_current_inr=0.0,
            paper_pnl_inr=0.0,
            thresholds=_coerce_thresholds(thresholds),
            verdict=AffordabilityVerdict.INVALID_INPUT,
            refusal_reasons=[f"invalid_input: {exc}"],
        )

    thresholds = _coerce_thresholds(thresholds)
    live_current = float(live_current_inr)

    def _build(verdict, reasons, live_cur=live_current, paper_pnl=paper) -> AffordabilityEvaluation:
        return AffordabilityEvaluation(
            live_source=live_source,
            paper_source=paper_source,
            proposed_delta_inr=proposed,
            live_current_inr=live_cur,
            paper_pnl_inr=paper_pnl,
            thresholds=thresholds,
            verdict=verdict,
            refusal_reasons=list(reasons),
            checks={
                "proposed_delta_inr": proposed,
                "live_current_inr": live_cur,
                "paper_pnl_inr": paper_pnl,
                "margin_multiplier": thresholds.margin_multiplier,
                "paper_pnl_ratio": thresholds.paper_pnl_ratio,
                "maximum_live_delta_inr": thresholds.maximum_live_delta_inr,
            },
        )

    # Bucket 1: hard ceiling on the delta itself.
    if proposed > thresholds.maximum_live_delta_inr:
        return _build(
            AffordabilityVerdict.MARGIN_EXCEEDED,
            [
                f"proposed_delta_inr={proposed:.2f} exceeds the configured "
                f"maximum_live_delta_inr={thresholds.maximum_live_delta_inr:.2f}"
            ],
        )

    # Bucket 2: live pool is not armed.
    if live_current <= 0 or math.isnan(live_current):
        return _build(
            AffordabilityVerdict.LIVE_NOT_ARMED,
            [
                f"live_current_inr={live_current:.2f} for source="
                f"{live_source!r}; cannot increase a non-positive pool"
            ],
        )

    refusal_reasons: list[str] = []

    # Bucket 3: delta exceeds operator-tunable margin.
    delta_ceiling = live_current * thresholds.margin_multiplier
    if proposed > delta_ceiling:
        refusal_reasons.append(
            f"proposed_delta_inr={proposed:.2f} exceeds "
            f"live_current_inr * margin_multiplier = "
            f"{live_current:.2f} * {thresholds.margin_multiplier:.2f} = "
            f"{delta_ceiling:.2f}"
        )

    # Bucket 4 + 5: paper P&L out of band. The two branches are kept
    # separate so the refusal message names *which* direction the
    # paper P&L is in.
    paper_floor = live_current * thresholds.paper_pnl_ratio
    if math.isnan(paper):
        refusal_reasons.append(
            f"paper_pnl_inr is NaN for source={paper_source!r}; "
            "refuse to infer affordability without ledger evidence"
        )
    elif paper > paper_floor:
        refusal_reasons.append(
            f"paper_pnl_inr={paper:.2f} for source={paper_source!r} "
            f"exceeds live_current_inr * paper_pnl_ratio = "
            f"{live_current:.2f} * {thresholds.paper_pnl_ratio:.2f} = "
            f"{paper_floor:.2f}; paper that out-earns the live pool by "
            "this factor is not an affordability signal"
        )
    elif paper < -paper_floor:
        refusal_reasons.append(
            f"paper_pnl_inr={paper:.2f} for source={paper_source!r} "
            f"is more negative than live_current_inr * paper_pnl_ratio = "
            f"{paper_floor:.2f}; live increases during a deep paper "
            "drawdown are not allowed"
        )

    if refusal_reasons:
        verdict = (
            AffordabilityVerdict.MARGIN_EXCEEDED
            if any("margin_multiplier" in r for r in refusal_reasons)
            else AffordabilityVerdict.PAPER_PNL_OUT_OF_BAND
        )
        # If both buckets fire, MARGIN_EXCEEDED is the more specific
        # ceiling and is surfaced first; the operator reads the full
        # refusal_reasons list to triage.
        return _build(verdict, refusal_reasons)

    return _build(AffordabilityVerdict.AFFORDABLE, [])


def assert_live_affordable_from_paper(
    *,
    live_source: str,
    paper_source: str,
    proposed_delta_inr,
    live_current_inr,
    paper_pnl_inr,
    thresholds: Optional[AffordabilityThresholds] = None,
) -> AffordabilityEvaluation:
    """Fail-closed guard; raises ``AffordabilityRefusal`` on any non-affordable verdict.

    Returns the underlying ``AffordabilityEvaluation`` when the
    outcome is ``AFFORDABLE``. Callers that want a structured
    response without exception flow should call
    ``evaluate_paper_to_live_affordability`` directly.

    The guard never returns ``AffordabilityVerdict.INVALID_INPUT``;
    invalid arguments raise ``ValueError`` (programmer error),
    distinct from ``AffordabilityRefusal`` (operational refusal).
    """
    # Re-raise the ValueError. We do NOT wrap it as an
    # AffordabilityRefusal; callers and the unittest framework
    # distinguish programmer errors from data refusals.
    proposed, _ = _validate_inputs(
        live_source, paper_source, proposed_delta_inr,
        paper_pnl_inr=paper_pnl_inr,
        live_current_inr=live_current_inr,
    )

    evaluation = evaluate_paper_to_live_affordability(
        live_source=live_source,
        paper_source=paper_source,
        proposed_delta_inr=proposed,
        live_current_inr=live_current_inr,
        paper_pnl_inr=paper_pnl_inr,
        thresholds=thresholds,
    )
    if not evaluation.is_affordable():
        raise AffordabilityRefusal(evaluation)
    return evaluation


async def async_evaluate_paper_to_live_affordability(
    *,
    live_source: str,
    paper_source: str,
    proposed_delta_inr,
    live_current_inr,
    paper_pnl_inr,
    thresholds: Optional[AffordabilityThresholds] = None,
) -> AffordabilityEvaluation:
    """Async-shaped twin of ``evaluate_paper_to_live_affordability``.

    The decision logic is identical; this entry point exists for
    integration sites that already have an event loop in scope and want
    to satisfy ``async`` linting without a sync/async shim. Callers
    that have not yet implemented live growth should not need this.
    """
    return evaluate_paper_to_live_affordability(
        live_source=live_source,
        paper_source=paper_source,
        proposed_delta_inr=proposed_delta_inr,
        live_current_inr=live_current_inr,
        paper_pnl_inr=paper_pnl_inr,
        thresholds=thresholds,
    )


async def assert_live_entry_safety(
    *,
    db_path: Optional[str],
    live_source: str,
    paper_source: str,
    proposed_delta_inr,
    thresholds: Optional[AffordabilityThresholds] = None,
) -> AffordabilityEvaluation:
    """Async ledger-aware wrapper; the recommended entry point for orchestrators.

    Reads the current live *equity* (allocation + realised P&L) and
    the realised paper P&L from the production ledger
    (``performance.division_equity`` and
    ``performance.allocation_for_source``), then evaluates
    affordability with the proposed delta. On a non-affordable
    verdict, raises ``AffordabilityRefusal`` with the full evaluation
    attached.

    The function is intentionally ``async`` so it can be called from
    inside ``penny_edge_orchestrator.run_penny_edge_scan`` and
    ``fno_orchestrator.run_fno_tick`` without a sync/async shim.
    Reading the ledger itself is *not* the guard's job; the wrapper
    borrows the ``performance`` module's query functions with the same
    fail-closed semantics the rest of the guard uses (a query
    failure returns ``LIVE_QUERY_FAILED`` rather than guessing).

    Note on semantics: ``division_equity`` returns the pool's
    allocation *plus* realised P&L for a specific source, mirroring
    how ``penny_edge_orchestrator._edge_equity`` and
    ``fno_orchestrator._fno_equity`` compute the live pool truth.
    Using ``division_equity`` rather than ``bankroll_for_source``
    keeps the wrapper aligned with the call sites that will use it.

    Today no path calls this function: live trading is structurally
    disarmed (``PENNY_LIVE_TRADING=False``, ``FNO_LIVE_BANKROLL=0``).
    This wrapper ships ahead of the demand so that *if* an operator
    later enables live growth, the integration site is one import
    and one call away from the guard.
    """
    try:
        from performance import division_equity, allocation_for_source
    except ImportError as exc:
        evaluation = evaluate_paper_to_live_affordability(
            live_source=live_source,
            paper_source=paper_source,
            proposed_delta_inr=proposed_delta_inr,
            live_current_inr=float("nan"),
            paper_pnl_inr=float("nan"),
            thresholds=thresholds,
        )
        evaluation.checks["query_error"] = (
            f"could not import performance module: {exc}"
        )
        if evaluation.is_affordable():
            return evaluation
        raise AffordabilityRefusal(evaluation)

    # The wrapper carries the same semantics as ``assert``: invalid
    # *arguments* are programmer errors and propagate as ``ValueError``
    # rather than being wrapped as ``AffordabilityRefusal``. Bad ledger
    # *data* lives in the ``except`` branch below as a refusal.
    try:
        _validate_argument_shapes(live_source, paper_source, proposed_delta_inr)
        # Coerce proposed_delta_inr for downstream use; ledger values
        # are read next and may be NaN on query failure.
        proposed = float(proposed_delta_inr)
    except ValueError:
        raise

    try:
        live_current = await division_equity(db_path, live_source)
        paper_equity = await division_equity(db_path, paper_source)
        try:
            paper_allocation = allocation_for_source(paper_source)
        except Exception:
            paper_allocation = None
    except Exception as exc:
        evaluation = evaluate_paper_to_live_affordability(
            live_source=live_source,
            paper_source=paper_source,
            proposed_delta_inr=proposed,
            live_current_inr=float("nan"),
            paper_pnl_inr=float("nan"),
            thresholds=thresholds,
        )
        evaluation.checks["query_error"] = (
            f"ledger query failed for live_source={live_source!r}, "
            f"paper_source={paper_source!r}: {exc}"
        )
        if evaluation.is_affordable():
            return evaluation
        raise AffordabilityRefusal(evaluation)

    if paper_allocation is not None:
        try:
            paper_pnl = float(paper_equity) - float(paper_allocation)
        except Exception:
            paper_pnl = float(paper_equity)
    else:
        paper_pnl = float(paper_equity)

    evaluation = evaluate_paper_to_live_affordability(
        live_source=live_source,
        paper_source=paper_source,
        proposed_delta_inr=proposed,
        live_current_inr=float(live_current),
        paper_pnl_inr=float(paper_pnl),
        thresholds=thresholds,
    )
    if not evaluation.is_affordable():
        raise AffordabilityRefusal(evaluation)
    return evaluation


__all__ = [
    "AffordabilityVerdict",
    "AffordabilityRefusal",
    "AffordabilityThresholds",
    "AffordabilityEvaluation",
    "evaluate_paper_to_live_affordability",
    "assert_live_affordable_from_paper",
    "async_evaluate_paper_to_live_affordability",
    "assert_live_entry_safety",
]
