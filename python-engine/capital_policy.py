"""Offline F6 capital-policy evaluation, never an execution authorization.

Loss tolerance is unknown until explicitly supplied. The pure function evaluates
caller-declared inputs; their authenticity/account scope is not established by
this API. The account wrapper refuses until immutable source linkage and genuine
F/G/D evidence can be independently validated. Existing accountless histories
and arbitrary archive files are not account-specific growth authority.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional


# ---- enums ------------------------------------------------------------------

class CapitalIncreaseVerdict(str, Enum):
    """Outcome of evaluating a candidate live-capital-increase request.

    Every verdict other than AUTHORIZED is a refusal. The
    ``reason`` field on the result carries the per-gate detail so
    the operator (or the CLI) can act on it.
    """

    AUTHORIZED = "AUTHORIZED"
    LOSS_TOLERANCE_EXCEEDED = "LOSS_TOLERANCE_EXCEEDED"
    DRAWDOWN_TOO_HIGH = "DRAWDOWN_TOO_HIGH"
    EXECUTION_QUALITY_INSUFFICIENT = "EXECUTION_QUALITY_INSUFFICIENT"
    RECONCILIATION_UNRESOLVED = "RECONCILIATION_UNRESOLVED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


# ---- dataclasses ------------------------------------------------------------

@dataclass(frozen=True)
class CapitalIncreaseEvaluation:
    """Outcome of ``evaluate_capital_increase`` plus per-gate details."""

    verdict: CapitalIncreaseVerdict
    requested_delta_inr: float
    loss_tolerance_pct: Optional[float]
    live_current_inr: Optional[float]
    drawdown_pct: Optional[float]
    win_rate_pct: Optional[float]
    avg_r_multiple: Optional[float]
    consecutive_losses: Optional[int]
    reconciliation_status: str
    reason: str
    notes: tuple[str, ...] = ()

    def summary(self) -> str:
        sign = "+" if self.requested_delta_inr >= 0 else ""
        return (
            f"[{self.verdict.value}] delta={sign}Rs {self.requested_delta_inr:.0f} "
            f"loss_tolerance={'unknown' if self.loss_tolerance_pct is None else f'{self.loss_tolerance_pct:.1f}%'} "
            f"drawdown={'unknown' if self.drawdown_pct is None else f'{self.drawdown_pct:.1f}%'} "
            f"win_rate={'n/a' if self.win_rate_pct is None else f'{self.win_rate_pct:.1f}%'} "
            f"reconciliation={self.reconciliation_status} "
            f"reason={self.reason}"
        )


@dataclass(frozen=True)
class CapitalPolicyThresholds:
    """All numeric knobs in one place. Loaded from ``config.py``.

    Every field has a senior-dev default that errs conservative; the
    user (operator) overrides any of them via the corresponding
    ``CAPITAL_POLICY_*`` constant in ``config.py``. The defaults are
    *not* the user's stated loss tolerance -- that lives separately
    on ``CAPITAL_POLICY_LOSS_TOLERANCE_PCT`` because it is the
    explicit input the plan mandates.

    Fields:
      loss_tolerance_pct:
        Explicit user input, unknown by default. This diagnostic evaluator
        caps the requested addition by that percentage of declared bankroll;
        this allocation proxy is not proof of bounded trading loss.

      max_drawdown_pct:
        The *current* realised drawdown cap on the live pool. Any
        candidate increase is refused if current drawdown exceeds
        this. Default 15.0% (industry-standard live-equity drawdown
        floor; independent of loss tolerance because they measure
        different things).

      min_win_rate_pct:
        Minimum closed-trade win rate required. Default 50.0% (half
        of closed trades profitable). Lower for early systems with
        few trades; raise for mature systems.

      min_avg_r_multiple:
        Minimum average R-multiple of closed trades. Default 0.0
        (breakeven on R). Raise to require positive expectancy.

      max_consecutive_losses:
        Maximum consecutive losing closed trades permitted. Default
        5 (industry-standard operational stability gate).

      min_live_bankroll_inr:
        Minimum current live bankroll before any increase is even
        evaluated. Default 1500.0 (matches ``PENNY_EDGE_LIVE_BANKROLL``
        shipping default).

      require_broker_reconciliation:
        If True, an UNRESOLVED or UNAVAILABLE broker statement
        refuses the increase. Default True -- never grow live capital
        on unverified broker truth.

      require_proactive_research_evidence:
        If True, the absence of a proactive research artifact on
        file returns INSUFFICIENT_EVIDENCE. Default True -- never
        grow live capital on a system with no recorded research
        basis.
    """

    loss_tolerance_pct: Optional[float] = None
    max_drawdown_pct: float = 15.0
    min_win_rate_pct: float = 50.0
    min_avg_r_multiple: float = 0.0
    max_consecutive_losses: int = 5
    min_live_bankroll_inr: float = 1500.0
    require_broker_reconciliation: bool = True
    require_proactive_research_evidence: bool = True

    def __post_init__(self) -> None:
        """Reject nonsensical threshold combinations at construction time."""
        for name in ("loss_tolerance_pct", "max_drawdown_pct", "min_win_rate_pct", "min_avg_r_multiple", "min_live_bankroll_inr"):
            value = getattr(self, name)
            if name == "loss_tolerance_pct" and value is None:
                continue
            _validate_numeric(value, name)
        for name in ("require_broker_reconciliation", "require_proactive_research_evidence"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a bool")
        if self.loss_tolerance_pct is not None and not 0.0 <= self.loss_tolerance_pct <= 100.0:
            raise ValueError(
                f"loss_tolerance_pct must be in [0, 100], "
                f"got {self.loss_tolerance_pct}"
            )
        if not 0.0 <= self.max_drawdown_pct <= 100.0:
            raise ValueError(
                f"max_drawdown_pct must be in [0, 100], "
                f"got {self.max_drawdown_pct}"
            )
        if not 0.0 <= self.min_win_rate_pct <= 100.0:
            raise ValueError(
                f"min_win_rate_pct must be in [0, 100], "
                f"got {self.min_win_rate_pct}"
            )
        if self.min_live_bankroll_inr < 0:
            raise ValueError(
                f"min_live_bankroll_inr must be non-negative, "
                f"got {self.min_live_bankroll_inr}"
            )
        if not isinstance(self.max_consecutive_losses, int) or (
            isinstance(self.max_consecutive_losses, bool)
        ) or self.max_consecutive_losses < 0:
            raise ValueError(
                f"max_consecutive_losses must be a non-negative int, "
                f"got {self.max_consecutive_losses!r}"
            )


# ---- pure function ----------------------------------------------------------

def _validate_numeric(value: Any, field_name: str) -> float:
    """Coerce to float; reject NaN/Inf. Used for ALL numeric inputs."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a real number, not bool")
    try:
        n = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be a real number, got {value!r}"
        ) from exc
    if not math.isfinite(n):
        raise ValueError(f"{field_name} must be finite, got {value!r}")
    return n


def _validate_pct(value: Any, field_name: str, *, low: float, high: float) -> float:
    """Coerce + check [low, high] range."""
    n = _validate_numeric(value, field_name)
    if not low <= n <= high:
        raise ValueError(
            f"{field_name} must be within [{low}, {high}], got {n}"
        )
    return n


def _validate_thresholds(thresholds: CapitalPolicyThresholds) -> None:
    """Reject nonsensical threshold combinations at construction time."""
    if thresholds.loss_tolerance_pct is not None and not 0.0 <= thresholds.loss_tolerance_pct <= 100.0:
        raise ValueError(
            f"loss_tolerance_pct must be in [0, 100], "
            f"got {thresholds.loss_tolerance_pct}"
        )
    if not 0.0 <= thresholds.max_drawdown_pct <= 100.0:
        raise ValueError(
            f"max_drawdown_pct must be in [0, 100], "
            f"got {thresholds.max_drawdown_pct}"
        )
    if not 0.0 <= thresholds.min_win_rate_pct <= 100.0:
        raise ValueError(
            f"min_win_rate_pct must be in [0, 100], "
            f"got {thresholds.min_win_rate_pct}"
        )
    if thresholds.min_live_bankroll_inr < 0:
        raise ValueError(
            f"min_live_bankroll_inr must be non-negative, "
            f"got {thresholds.min_live_bankroll_inr}"
        )
    if thresholds.max_consecutive_losses < 0:
        raise ValueError(
            f"max_consecutive_losses must be non-negative, "
            f"got {thresholds.max_consecutive_losses}"
        )


def evaluate_capital_increase(
    *,
    requested_delta_inr: float,
    live_current_inr: float,
    drawdown_pct: float,
    win_rate_pct: Optional[float],
    avg_r_multiple: Optional[float],
    consecutive_losses: int,
    reconciliation_status: str,
    proactive_research_evidence_present: bool,
    thresholds: Optional[CapitalPolicyThresholds] = None,
) -> CapitalIncreaseEvaluation:
    """Evaluate a candidate live-capital-increase request.

    Pure function. Every numeric input is supplied by the caller;
    the ledger-aware wrapper is a thin coroutine in
    ``evaluate_capital_increase_for_account``.

    Returns a ``CapitalIncreaseEvaluation`` carrying the verdict and
    per-gate details. The caller (CLI, dashboard, orchestrator) is
    responsible for *acting* on the verdict; this function never
    mutates any ledger.
    """
    if thresholds is None:
        thresholds = CapitalPolicyThresholds()
    _validate_thresholds(thresholds)

    requested_delta_inr = _validate_numeric(
        requested_delta_inr, "requested_delta_inr",
    )
    if requested_delta_inr <= 0:
        raise ValueError("requested_delta_inr must be strictly positive; reductions are a separate policy")
    live_current_inr = _validate_numeric(
        live_current_inr, "live_current_inr",
    )
    drawdown_pct = _validate_pct(
        drawdown_pct, "drawdown_pct", low=0.0, high=100.0,
    )
    if win_rate_pct is not None:
        win_rate_pct = _validate_pct(
            win_rate_pct, "win_rate_pct", low=0.0, high=100.0,
        )
    if avg_r_multiple is not None:
        avg_r_multiple = _validate_numeric(
            avg_r_multiple, "avg_r_multiple",
        )
    if (
        not isinstance(consecutive_losses, int)
        or isinstance(consecutive_losses, bool)
        or consecutive_losses < 0
    ):
        raise ValueError(
            f"consecutive_losses must be a non-negative int, "
            f"got {consecutive_losses!r}"
        )
    if reconciliation_status not in {"MATCH", "UNRESOLVED", "UNAVAILABLE", "NOT_RUN"}:
        raise ValueError(
            f"reconciliation_status must be one of "
            f"MATCH/UNRESOLVED/UNAVAILABLE/NOT_RUN, got {reconciliation_status!r}"
        )
    if not isinstance(proactive_research_evidence_present, bool):
        raise ValueError(
            f"proactive_research_evidence_present must be a bool, "
            f"got {proactive_research_evidence_present!r}"
        )

    notes: list[str] = []

    if thresholds.loss_tolerance_pct is None:
        return _insufficient(requested_delta_inr, thresholds, "explicit user loss tolerance is unknown")
    if win_rate_pct is None or avg_r_multiple is None:
        return _insufficient(requested_delta_inr, thresholds, "execution quality is unknown")

    # ---- Gate 1: live bankroll must be at least the floor.
    if live_current_inr < thresholds.min_live_bankroll_inr:
        return CapitalIncreaseEvaluation(
            verdict=CapitalIncreaseVerdict.INSUFFICIENT_EVIDENCE,
            requested_delta_inr=requested_delta_inr,
            loss_tolerance_pct=thresholds.loss_tolerance_pct,
            live_current_inr=live_current_inr,
            drawdown_pct=drawdown_pct,
            win_rate_pct=win_rate_pct,
            avg_r_multiple=avg_r_multiple,
            consecutive_losses=consecutive_losses,
            reconciliation_status=reconciliation_status,
            reason=(
                f"live bankroll Rs {live_current_inr:.0f} is below the "
                f"evaluation floor Rs {thresholds.min_live_bankroll_inr:.0f}"
            ),
            notes=tuple(notes),
        )

    # ---- Gate 2: broker reconciliation (per F5) must be MATCH.
    if thresholds.require_broker_reconciliation:
        if reconciliation_status != "MATCH":
            return CapitalIncreaseEvaluation(
                verdict=CapitalIncreaseVerdict.RECONCILIATION_UNRESOLVED,
                requested_delta_inr=requested_delta_inr,
                loss_tolerance_pct=thresholds.loss_tolerance_pct,
                live_current_inr=live_current_inr,
                drawdown_pct=drawdown_pct,
                win_rate_pct=win_rate_pct,
                avg_r_multiple=avg_r_multiple,
                consecutive_losses=consecutive_losses,
                reconciliation_status=reconciliation_status,
                reason=(
                    f"broker reconciliation status is {reconciliation_status}; "
                    f"MATCH required before any live-capital increase"
                ),
                notes=tuple(notes),
            )

    # ---- Gate 3: current realised drawdown must be at or below the cap.
    if drawdown_pct > thresholds.max_drawdown_pct:
        return CapitalIncreaseEvaluation(
            verdict=CapitalIncreaseVerdict.DRAWDOWN_TOO_HIGH,
            requested_delta_inr=requested_delta_inr,
            loss_tolerance_pct=thresholds.loss_tolerance_pct,
            live_current_inr=live_current_inr,
            drawdown_pct=drawdown_pct,
            win_rate_pct=win_rate_pct,
            avg_r_multiple=avg_r_multiple,
            consecutive_losses=consecutive_losses,
            reconciliation_status=reconciliation_status,
            reason=(
                f"current realised drawdown {drawdown_pct:.1f}% exceeds "
                f"the cap {thresholds.max_drawdown_pct:.1f}%"
            ),
            notes=tuple(notes),
        )

    # ---- Gate 4: the proposed increase must not push the live pool
    # past an explicit allocation proxy. This is NOT a worst-case
    # trading-loss model or sufficient evidence for a live risk budget.
    max_additional_inr = (
        live_current_inr * thresholds.loss_tolerance_pct / 100.0
    )
    if requested_delta_inr > max_additional_inr:
        return CapitalIncreaseEvaluation(
            verdict=CapitalIncreaseVerdict.LOSS_TOLERANCE_EXCEEDED,
            requested_delta_inr=requested_delta_inr,
            loss_tolerance_pct=thresholds.loss_tolerance_pct,
            live_current_inr=live_current_inr,
            drawdown_pct=drawdown_pct,
            win_rate_pct=win_rate_pct,
            avg_r_multiple=avg_r_multiple,
            consecutive_losses=consecutive_losses,
            reconciliation_status=reconciliation_status,
            reason=(
                f"requested delta Rs {requested_delta_inr:.0f} exceeds the "
                f"user's loss-tolerance budget of Rs {max_additional_inr:.0f} "
                f"({thresholds.loss_tolerance_pct:.1f}% of live bankroll)"
            ),
            notes=tuple(notes),
        )

    # ---- Gate 5: execution quality. win_rate and avg_r_multiple are
    # optional but if KNOWN they must clear the floor.
    if win_rate_pct is not None and win_rate_pct < thresholds.min_win_rate_pct:
        return CapitalIncreaseEvaluation(
            verdict=CapitalIncreaseVerdict.EXECUTION_QUALITY_INSUFFICIENT,
            requested_delta_inr=requested_delta_inr,
            loss_tolerance_pct=thresholds.loss_tolerance_pct,
            live_current_inr=live_current_inr,
            drawdown_pct=drawdown_pct,
            win_rate_pct=win_rate_pct,
            avg_r_multiple=avg_r_multiple,
            consecutive_losses=consecutive_losses,
            reconciliation_status=reconciliation_status,
            reason=(
                f"win rate {win_rate_pct:.1f}% below the floor "
                f"{thresholds.min_win_rate_pct:.1f}%"
            ),
            notes=tuple(notes),
        )
    if avg_r_multiple is not None and avg_r_multiple < thresholds.min_avg_r_multiple:
        return CapitalIncreaseEvaluation(
            verdict=CapitalIncreaseVerdict.EXECUTION_QUALITY_INSUFFICIENT,
            requested_delta_inr=requested_delta_inr,
            loss_tolerance_pct=thresholds.loss_tolerance_pct,
            live_current_inr=live_current_inr,
            drawdown_pct=drawdown_pct,
            win_rate_pct=win_rate_pct,
            avg_r_multiple=avg_r_multiple,
            consecutive_losses=consecutive_losses,
            reconciliation_status=reconciliation_status,
            reason=(
                f"avg R-multiple {avg_r_multiple:.3f} below the floor "
                f"{thresholds.min_avg_r_multiple:.3f}"
            ),
            notes=tuple(notes),
        )

    # ---- Gate 6: operational stability (consecutive losses).
    if consecutive_losses > thresholds.max_consecutive_losses:
        return CapitalIncreaseEvaluation(
            verdict=CapitalIncreaseVerdict.EXECUTION_QUALITY_INSUFFICIENT,
            requested_delta_inr=requested_delta_inr,
            loss_tolerance_pct=thresholds.loss_tolerance_pct,
            live_current_inr=live_current_inr,
            drawdown_pct=drawdown_pct,
            win_rate_pct=win_rate_pct,
            avg_r_multiple=avg_r_multiple,
            consecutive_losses=consecutive_losses,
            reconciliation_status=reconciliation_status,
            reason=(
                f"consecutive losses {consecutive_losses} exceed the "
                f"stability gate {thresholds.max_consecutive_losses}"
            ),
            notes=tuple(notes),
        )

    # ---- Gate 7: proactive research evidence on file (per G).
    if thresholds.require_proactive_research_evidence:
        if not proactive_research_evidence_present:
            return CapitalIncreaseEvaluation(
                verdict=CapitalIncreaseVerdict.INSUFFICIENT_EVIDENCE,
                requested_delta_inr=requested_delta_inr,
                loss_tolerance_pct=thresholds.loss_tolerance_pct,
                live_current_inr=live_current_inr,
                drawdown_pct=drawdown_pct,
                win_rate_pct=win_rate_pct,
                avg_r_multiple=avg_r_multiple,
                consecutive_losses=consecutive_losses,
                reconciliation_status=reconciliation_status,
                reason=(
                    "no proactive research evidence on file; F6 refuses to "
                    "grow live capital without a recorded research basis"
                ),
                notes=tuple(notes),
            )

    # ---- All gates passed.
    return CapitalIncreaseEvaluation(
        verdict=CapitalIncreaseVerdict.AUTHORIZED,
        requested_delta_inr=requested_delta_inr,
        loss_tolerance_pct=thresholds.loss_tolerance_pct,
        live_current_inr=live_current_inr,
        drawdown_pct=drawdown_pct,
        win_rate_pct=win_rate_pct,
        avg_r_multiple=avg_r_multiple,
        consecutive_losses=consecutive_losses,
        reconciliation_status=reconciliation_status,
        reason="all gates passed",
        notes=tuple(notes),
    )


# ---- public async wrapper ----------------------------------------------------

async def evaluate_capital_increase_for_account(
    db_path: str,
    *,
    account_id: str,
    requested_delta_inr: float,
    thresholds: Optional[CapitalPolicyThresholds] = None,
    now_utc: Optional[datetime] = None,
) -> CapitalIncreaseEvaluation:
    """Refuse account evaluation until immutable account/source linkage exists.

    Current performance/quality/loss stores are accountless. A broker statement
    MATCH or archive file cannot link them to this account or validate G/D.
    No DB is opened and no missing quantity is fabricated as zero.
    """
    if not isinstance(account_id, str) or not account_id.strip():
        raise ValueError("account_id must be a nonblank string")
    requested_delta_inr = _validate_numeric(requested_delta_inr, "requested_delta_inr")
    if requested_delta_inr <= 0:
        raise ValueError("requested_delta_inr must be strictly positive")
    if thresholds is None:
        thresholds = CapitalPolicyThresholds()
    _validate_thresholds(thresholds)
    return _insufficient(requested_delta_inr, thresholds,
        "account-to-source linkage and independently validated F/G/D evidence are unavailable")


def _insufficient(
    requested_delta_inr: float,
    thresholds: CapitalPolicyThresholds,
    reason: str,
) -> CapitalIncreaseEvaluation:
    """Helper: build an INSUFFICIENT_EVIDENCE result with the given reason."""
    return CapitalIncreaseEvaluation(
        verdict=CapitalIncreaseVerdict.INSUFFICIENT_EVIDENCE,
        requested_delta_inr=requested_delta_inr,
        loss_tolerance_pct=thresholds.loss_tolerance_pct,
        live_current_inr=None,
        drawdown_pct=None,
        win_rate_pct=None,
        avg_r_multiple=None,
        consecutive_losses=None,
        reconciliation_status="UNAVAILABLE",
        reason=reason,
    )




__all__ = [
    "CAPITAL_POLICY_SCHEMA_VERSION",
    "CapitalIncreaseEvaluation",
    "CapitalIncreaseVerdict",
    "CapitalPolicyThresholds",
    "evaluate_capital_increase",
    "evaluate_capital_increase_for_account",
]


CAPITAL_POLICY_SCHEMA_VERSION = 2
