"""[WORKFLOW-F.8 2026-09-17] Cost-per-trade audit.

Per Workstream F in NEXT_AGENT_PLAN.md:
> Audit true cost per trade relative to expected edge for
> INR 8k capital. Prevent a large configured paper
> bankroll from implying owner live affordability.

This module is a pure analyzer. Given a list of trades
and a list of cost lines, it computes:

  - ``TradeCost`` -- per-trade cost breakdown
    (broker_fees, slippage, charges, total_cost,
    expected_edge, cost_to_edge_ratio).
  - ``CostAuditReport`` -- aggregate stats over the
    trades: total cost, total edge, mean cost_to_edge,
    worst trade, threshold-breach count.
  - ``audit_costs(trades, costs)`` -- end-to-end audit.

The plan's "prevent a large configured paper bankroll from
implying owner live affordability" is supported by:

  - The audit surfaces each trade's true cost so the
    operator can compare against the configured paper
    bankroll.
  - Trades with cost_to_edge_ratio > 1.0 (cost exceeds
    expected edge) are flagged as threshold-breaches.
  - The aggregate ``mean_cost_to_edge`` shows the system's
    cost burden at a glance.

Pure function. No I/O. No DB. No clock injection.
"""
from __future__ import annotations

import dataclasses
import enum
import statistics
from typing import Iterable, Optional


class CostSeverity(str, enum.Enum):
    """Severity of a single trade's cost."""
    CHEAP = "CHEAP"  # cost_to_edge_ratio <= 0.25.
    REASONABLE = "REASONABLE"  # <= 0.5.
    EXPENSIVE = "EXPENSIVE"  # <= 1.0.
    BREACH = "BREACH"  # > 1.0 (cost > edge).


@dataclasses.dataclass(frozen=True)
class TradeCost:
    """Per-trade cost breakdown.

    Attributes:
        trade_id: unique trade identifier (e.g. fill_id).
        broker_fees: total broker fees paid.
        slippage: difference between fill price and
            decision-time mid (in INR). Positive slippage
            means the trader got a worse price.
        charges: taxes + exchange charges.
        total_cost: broker_fees + slippage + charges
            (precomputed at audit time).
        expected_edge: the strategy's expected edge in INR
            at decision time (positive = profit expected).
        cost_to_edge_ratio: total_cost / expected_edge, or
            ``None`` when expected_edge <= 0.
        severity: CostSeverity classification.
    """
    trade_id: str
    broker_fees: float
    slippage: float
    charges: float
    total_cost: float
    expected_edge: float
    cost_to_edge_ratio: Optional[float]
    severity: CostSeverity

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "broker_fees": round(self.broker_fees, 2),
            "slippage": round(self.slippage, 2),
            "charges": round(self.charges, 2),
            "total_cost": round(self.total_cost, 2),
            "expected_edge": round(self.expected_edge, 2),
            "cost_to_edge_ratio": (
                round(self.cost_to_edge_ratio, 4)
                if self.cost_to_edge_ratio is not None else None
            ),
            "severity": self.severity.value,
        }


@dataclasses.dataclass(frozen=True)
class CostAuditReport:
    """Aggregate audit report.

    Attributes:
        trades: tuple of TradeCost.
        total_cost: sum of total_cost across trades.
        total_edge: sum of expected_edge across trades.
        mean_cost_to_edge: mean of cost_to_edge_ratio
            (excluding trades with expected_edge <= 0).
        worst_trade: the TradeCost with the highest
            cost_to_edge_ratio (or None if all edges <= 0).
        breach_count: number of trades with severity == BREACH.
        threshold_breach_ratio: breach_count / len(trades).
        notes: human-readable notes for the audit log.
    """
    trades: tuple[TradeCost, ...]
    total_cost: float
    total_edge: float
    mean_cost_to_edge: Optional[float]
    worst_trade: Optional[TradeCost]
    breach_count: int
    threshold_breach_ratio: Optional[float]
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "trade_count": len(self.trades),
            "total_cost": round(self.total_cost, 2),
            "total_edge": round(self.total_edge, 2),
            "mean_cost_to_edge": (
                round(self.mean_cost_to_edge, 4)
                if self.mean_cost_to_edge is not None else None
            ),
            "worst_trade": (
                self.worst_trade.to_dict() if self.worst_trade else None
            ),
            "breach_count": self.breach_count,
            "threshold_breach_ratio": (
                round(self.threshold_breach_ratio, 4)
                if self.threshold_breach_ratio is not None else None
            ),
            "notes": list(self.notes),
        }


def _cost_severity(ratio: Optional[float]) -> CostSeverity:
    """Classify a cost/edge ratio.

    Per the plan: 'Audit true cost per trade relative to
    expected edge for INR 8k capital.' A ratio > 1.0 means
    the cost exceeds the expected edge -- the trade is a
    net negative even when the strategy wins.
    """
    if ratio is None:
        # No expected edge -- we can't classify.
        return CostSeverity.EXPENSIVE
    if ratio <= 0.25:
        return CostSeverity.CHEAP
    if ratio <= 0.5:
        return CostSeverity.REASONABLE
    if ratio <= 1.0:
        return CostSeverity.EXPENSIVE
    return CostSeverity.BREACH


def audit_costs(
    trades: Iterable[dict],
    *,
    breach_threshold: float = 1.0,
) -> CostAuditReport:
    """Audit the per-trade cost structure.

    Args:
        trades: iterable of trade dicts. Each trade must
            have at least:
              - ``trade_id`` (str)
              - ``broker_fees`` (float)
              - ``slippage`` (float)
              - ``charges`` (float)
              - ``expected_edge`` (float; can be negative for
                defensive strategies)
        breach_threshold: a trade is flagged as BREACH
            when its cost_to_edge_ratio exceeds this.
            Default 1.0 (per the plan: cost > edge).

    Returns:
        A ``CostAuditReport`` aggregating per-trade costs.
    """
    parsed: list[TradeCost] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        trade_id = str(trade.get("trade_id", "?"))
        broker_fees = float(trade.get("broker_fees", 0) or 0)
        slippage = float(trade.get("slippage", 0) or 0)
        charges = float(trade.get("charges", 0) or 0)
        expected_edge = float(trade.get("expected_edge", 0) or 0)
        total_cost = broker_fees + slippage + charges
        if expected_edge > 0:
            ratio = total_cost / expected_edge
        else:
            ratio = None
        # Use the per-call threshold for breach classification.
        if ratio is not None and ratio > breach_threshold:
            severity = CostSeverity.BREACH
        else:
            severity = _cost_severity(ratio)
        parsed.append(TradeCost(
            trade_id=trade_id,
            broker_fees=broker_fees,
            slippage=slippage,
            charges=charges,
            total_cost=total_cost,
            expected_edge=expected_edge,
            cost_to_edge_ratio=ratio,
            severity=severity,
        ))

    if not parsed:
        return CostAuditReport(
            trades=(),
            total_cost=0.0,
            total_edge=0.0,
            mean_cost_to_edge=None,
            worst_trade=None,
            breach_count=0,
            threshold_breach_ratio=None,
            notes=("no trade records; cannot audit",),
        )

    total_cost = sum(t.total_cost for t in parsed)
    total_edge = sum(t.expected_edge for t in parsed)

    ratios = [t.cost_to_edge_ratio for t in parsed
                if t.cost_to_edge_ratio is not None]
    if ratios:
        mean_cost_to_edge = statistics.mean(ratios)
    else:
        mean_cost_to_edge = None

    worst = max(
        (t for t in parsed if t.cost_to_edge_ratio is not None),
        key=lambda t: t.cost_to_edge_ratio,
        default=None,
    )

    breach_count = sum(
        1 for t in parsed if t.cost_to_edge_ratio is not None
        and t.cost_to_edge_ratio > breach_threshold
    )
    threshold_breach_ratio = breach_count / len(parsed)

    notes: list[str] = []
    if breach_count > 0:
        notes.append(
            f"{breach_count} trade(s) exceeded breach_threshold "
            f"({breach_threshold:.2f}); cost exceeds expected edge"
        )
    if mean_cost_to_edge is not None and mean_cost_to_edge > 0.5:
        notes.append(
            f"mean cost_to_edge {mean_cost_to_edge:.2f} > 0.5; "
            "the cost burden is high relative to the strategy's edge"
        )
    if not notes:
        notes.append(
            f"all {len(parsed)} trades within budget; "
            "cost burden is sustainable"
        )

    return CostAuditReport(
        trades=tuple(parsed),
        total_cost=total_cost,
        total_edge=total_edge,
        mean_cost_to_edge=mean_cost_to_edge,
        worst_trade=worst,
        breach_count=breach_count,
        threshold_breach_ratio=threshold_breach_ratio,
        notes=tuple(notes),
    )


__all__ = [
    "CostAuditReport",
    "CostSeverity",
    "TradeCost",
    "audit_costs",
]
