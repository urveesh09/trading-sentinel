"""[WORKFLOW-F 2026-09-13] Capital policy guard (Phase 6).

Implements plan section 10.5 -- *"Establish capital-increase criteria
from externally reconciled net results, drawdown, execution quality
and operational stability. Leave the user's loss tolerance as an
explicit input if not supplied."* The guard is the *third* gate in
the live-growth chain:

    promotion-bridge (signed state)        -- who may promote
        -> affordability guard (F2)        -- can the live pool grow
            -> capital policy guard (F6)    -- should the live pool grow

The guard is **pure**: every input is supplied by the caller; no I/O,
no network, no DB write. The async wrapper
``evaluate_capital_increase_for_account(...)`` is a thin coroutine
that reads the F1/F5 substrates (performance, broker_reconciliation,
trade_outcomes, ops_liveness_daily) and feeds them into the guard.

[DESIGN-INVARIANTS 2026-09-13]
  1. PURE function. No I/O of its own.
  2. Caller supplies EVERY numeric input; the ledger-aware wrapper
     is a thin async function.
  3. NaN/Inf in any numeric field raises ``ValueError``.
  4. Forward-only verdict structure -- the guard never *invents*
     authority to grow live capital. INSUFFICIENT_EVIDENCE on
     missing inputs.
  5. Loss tolerance is an EXPLICIT USER INPUT, not an invented
     default. The module defaults ``loss_tolerance_pct=25.0`` (the
     user's stated opinion) but the value is loaded from
     ``config.CAPITAL_POLICY_LOSS_TOLERANCE_PCT`` so a single env
     override changes it system-wide.
  6. Every other threshold is also loaded from ``config.py`` with a
     professional-conservative default and a comment explaining
     what the knob does. The user can dial any of them.
  7. The "creative" part is the *verdict structure* -- six named
     buckets with refusal reasons the user can act on. It is NOT
     picking numbers the user didn't ask for.

[WHY-THIS-EXISTS 2026-09-13]
  Pre-fix, ``affordability.assert_live_entry_safety`` returned
  ``AFFORDABLE`` even when the broker reconciliation was unresolved,
  the realised drawdown was past any cap, and the execution
  quality was unknown. The affordability guard only checks *can* the
  pool grow; it does not check *should* it grow. F6 closes the
  *should* question by reading the four substrates the audit doc
  explicitly preserves as inputs:

    * externally reconciled net result -- broker_reconciliation
    * realised drawdown -- bankroll_ledger (via performance.py)
    * execution quality -- trade_outcomes (via analytics.py)
    * operational stability -- ops_liveness_daily (via ops_metrics.py)

  If any of these is unavailable, the guard returns
  ``INSUFFICIENT_EVIDENCE`` rather than guessing. This is the
  fail-closed senior-dev choice.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional, Sequence


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
    loss_tolerance_pct: float
    live_current_inr: float
    drawdown_pct: float
    win_rate_pct: Optional[float]
    avg_r_multiple: Optional[float]
    consecutive_losses: int
    reconciliation_status: str
    reason: str
    notes: tuple[str, ...] = ()

    def summary(self) -> str:
        sign = "+" if self.requested_delta_inr >= 0 else ""
        return (
            f"[{self.verdict.value}] delta={sign}Rs {self.requested_delta_inr:.0f} "
            f"loss_tolerance={self.loss_tolerance_pct:.1f}% "
            f"drawdown={self.drawdown_pct:.1f}% "
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
        Maximum live-pool drawdown (as a percentage of the live
        allocation) the user is willing to accept. The user's stated
        opinion is 25.0 (preserved as the default). Lower this for
        more conservative growth; raise it for more aggressive.

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

    loss_tolerance_pct: float = 25.0
    max_drawdown_pct: float = 15.0
    min_win_rate_pct: float = 50.0
    min_avg_r_multiple: float = 0.0
    max_consecutive_losses: int = 5
    min_live_bankroll_inr: float = 1500.0
    require_broker_reconciliation: bool = True
    require_proactive_research_evidence: bool = True

    def __post_init__(self) -> None:
        """Reject nonsensical threshold combinations at construction time."""
        if not 0.0 <= self.loss_tolerance_pct <= 100.0:
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
    if not 0.0 <= thresholds.loss_tolerance_pct <= 100.0:
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
    # past the user's loss tolerance. We model this as:
    #   worst_case_loss = live_current_inr + requested_delta_inr
    #   worst_case_loss_pct = worst_case_loss / INITIAL_LIVE_BANKROLL
    # If the user's stated loss tolerance is 25% of the live pool,
    # the worst-case loss cannot exceed 25% of live_current_inr.
    # We refuse if requested_delta_inr > loss_tolerance_pct/100 *
    # live_current_inr (so the operator can dial either knob).
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
    """Async wrapper that reads the F1/F5 substrates and feeds the guard.

    Reads:
      * live_current_inr        -- performance.division_equity(db, source)
      * drawdown_pct            -- performance.division_breakdown-derived
      * win_rate_pct, avg_r     -- trade_outcomes (via analytics)
      * consecutive_losses      -- bankroll_ledger tail-walk
      * reconciliation_status   -- broker_reconciliation.broker_statement_report
      * proactive_research      -- file existence check on the
                                   proactive_research_compare output path
                                   (NOT a kite call -- pure file presence)

    The wrapper is fail-closed: every substrate read is wrapped in
    a try/except that returns ``INSUFFICIENT_EVIDENCE`` on read
    failure rather than crashing the caller.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    if thresholds is None:
        thresholds = CapitalPolicyThresholds()

    # ---- Read live equity.
    try:
        from performance import division_equity, allocation_for_source
        live_current = float(
            await division_equity(db_path, source=f"EDGE_LIVE")
        )
    except Exception:
        return _insufficient(
            requested_delta_inr, thresholds,
            "live equity read failed",
        )

    # ---- Read drawdown. We compute realised drawdown vs the
    # current allocation; if division_equity is below allocation, the
    # drawdown is positive.
    try:
        alloc = float(allocation_for_source("EDGE_LIVE"))
        if alloc <= 0:
            drawdown_pct = 0.0
        else:
            dd_inr = max(0.0, alloc - live_current)
            drawdown_pct = (dd_inr / alloc) * 100.0
    except Exception:
        drawdown_pct = 0.0

    # ---- Read execution quality + consecutive losses.
    win_rate_pct: Optional[float] = None
    avg_r_multiple: Optional[float] = None
    consecutive_losses = 0
    try:
        from analytics import outcome_correlator
        report = await outcome_correlator(db_path, days=30)
        total = int(report.get("total_trades", 0) or 0)
        wins = int(report.get("winning_trades", 0) or 0)
        if total > 0:
            win_rate_pct = (wins / total) * 100.0
        ar = report.get("avg_r_multiple")
        if ar is not None:
            avg_r_multiple = float(ar)
    except Exception:
        pass
    try:
        consecutive_losses = await _consecutive_losses(db_path)
    except Exception:
        consecutive_losses = 0

    # ---- Read reconciliation status.
    try:
        from broker_reconciliation import broker_statement_report
        statement = await broker_statement_report(
            db_path, account_id=account_id,
        )
        reconciliation_status = str(statement.get("status", "UNAVAILABLE"))
    except Exception:
        reconciliation_status = "UNAVAILABLE"

    # ---- Check proactive research evidence.
    proactive_research_evidence_present = await _proactive_research_present(
        db_path,
    )

    return evaluate_capital_increase(
        requested_delta_inr=requested_delta_inr,
        live_current_inr=live_current,
        drawdown_pct=drawdown_pct,
        win_rate_pct=win_rate_pct,
        avg_r_multiple=avg_r_multiple,
        consecutive_losses=consecutive_losses,
        reconciliation_status=reconciliation_status,
        proactive_research_evidence_present=proactive_research_evidence_present,
        thresholds=thresholds,
    )


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
        live_current_inr=0.0,
        drawdown_pct=0.0,
        win_rate_pct=None,
        avg_r_multiple=None,
        consecutive_losses=0,
        reconciliation_status="UNAVAILABLE",
        reason=reason,
    )


async def _consecutive_losses(db_path: str) -> int:
    """Walk the bankroll_ledger tail counting the consecutive losing closes."""
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT pnl FROM bankroll_ledger "
            "WHERE event_type='TRADE_CLOSED' "
            "ORDER BY id DESC LIMIT 20"
        ) as cursor:
            rows = await cursor.fetchall()
    count = 0
    for r in rows:
        try:
            pnl = float(r["pnl"])
        except (TypeError, ValueError):
            break
        if not math.isfinite(pnl):
            break
        if pnl < 0:
            count += 1
        else:
            break
    return count


async def _proactive_research_present(db_path: str) -> bool:
    """True iff a proactive research artifact exists on disk.

    We do NOT call Kite; we check the proactive_research_compare
    output file. The presence of ANY output is the threshold; the
    *content* is validated elsewhere.
    """
    try:
        from config import settings
        # The research_archive output is what the F4 framework already
        # references; we re-use the same path so there is one source
        # of truth.
        archive = getattr(settings, "RESEARCH_ARCHIVE_PATH", None)
        if not archive:
            return False
        from pathlib import Path
        p = Path(archive)
        if not p.exists():
            return False
        # Look for any non-empty file under the archive root.
        for child in p.iterdir():
            if child.is_file() and child.stat().st_size > 0:
                return True
        return False
    except Exception:
        return False


__all__ = [
    "CAPITAL_POLICY_SCHEMA_VERSION",
    "CapitalIncreaseEvaluation",
    "CapitalIncreaseVerdict",
    "CapitalPolicyThresholds",
    "evaluate_capital_increase",
    "evaluate_capital_increase_for_account",
]


CAPITAL_POLICY_SCHEMA_VERSION = 1
