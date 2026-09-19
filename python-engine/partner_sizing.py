"""[WORKFLOW-E.5 2026-09-17] Liquidity-aware sizing.

Per Workstream E in NEXT_AGENT_PLAN.md:
> Explain uncertainty and liquidity limits without
> overwhelming the message.

This module computes liquidity-aware sizing for a partner
advisory card. Given a card with bid_quantity / ask_quantity
on each leg, it produces:

  - ``max_fillable_contracts`` -- how many contracts of the
    requested size can fill without walking past top-of-book.
  - ``walk_the_book_cost`` -- total slippage (in bps) if the
    requested size is larger than top-of-book.
  - ``liquidity_tier`` -- SURPLUS / TIGHT / INSUFFICIENT.
  - ``per_leg`` -- per-leg fillable / slippage breakdown.

The module is read-only: it does NOT place orders, does NOT
talk to a broker, does NOT modify the card. It only
computes hypothetical scenarios so the partner can decide
whether to scale down.

Usage::

    from partner_sizing import compute_liquidity_sizing

    result = compute_liquidity_sizing(card, requested_contracts=2)
    if result.liquidity_tier == "INSUFFICIENT":
        ...
"""
from __future__ import annotations

import dataclasses
import enum
from typing import Any, Optional


class LiquidityTier(str, enum.Enum):
    """How comfortably the requested size fits at top-of-book.

    - SURPLUS:        >= 5x top-of-book depth covers the
                      requested size. No concern.
    - TIGHT:          1x-5x top-of-book depth. Operator
                      should be cautious; partial fills likely.
    - INSUFFICIENT:   < 1x top-of-book depth. The requested
                      size cannot fill without walking
                      through the book. Operator must scale
                      down.
    """
    SURPLUS = "SURPLUS"
    TIGHT = "TIGHT"
    INSUFFICIENT = "INSUFFICIENT"

    def exit_code(self) -> int:
        return 1 if self == LiquidityTier.INSUFFICIENT else 0


@dataclasses.dataclass(frozen=True)
class LegLiquidity:
    """Per-leg liquidity summary.

    Attributes:
        leg_index: index into ``card['legs']``.
        tradingsymbol: leg's tradingsymbol for reporting.
        side: BUY / SELL.
        requested_contracts: number of contracts requested.
        top_of_book_quantity: bid_quantity (for SELL) or
            ask_quantity (for BUY) -- the depth at the
            inside price.
        fillable_contracts: how many contracts can fill
            without walking past top-of-book.
        slippage_bps_to_fill_requested: extra slippage (bps)
            to fill the requested size; 0 if fillable
            already covers it.
        tier: SURPLUS / TIGHT / INSUFFICIENT for this leg.
    """
    leg_index: int
    tradingsymbol: str
    side: str
    requested_contracts: int
    top_of_book_quantity: int
    fillable_contracts: int
    slippage_bps_to_fill_requested: float
    tier: LiquidityTier


@dataclasses.dataclass(frozen=True)
class LiquiditySizingResult:
    """Computed liquidity sizing for a partner card.

    Attributes:
        requested_contracts: how many contracts were requested.
        max_fillable_contracts: the most contracts that can
            fill across all legs simultaneously (the minimum
            fillable across legs).
        walk_the_book_cost_bps: total slippage in basis points
            to fill the requested size across all legs
            (sum of per-leg slippage).
        liquidity_tier: the worst-case tier across legs.
        per_leg: tuple of LegLiquidity, one per leg.
        warnings: human-readable warnings (e.g. "leg 1 cannot
            fill 2 contracts at top-of-book").
    """
    requested_contracts: int
    max_fillable_contracts: int
    walk_the_book_cost_bps: float
    liquidity_tier: LiquidityTier
    per_leg: tuple[LegLiquidity, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "requested_contracts": self.requested_contracts,
            "max_fillable_contracts": self.max_fillable_contracts,
            "walk_the_book_cost_bps": self.walk_the_book_cost_bps,
            "liquidity_tier": self.liquidity_tier.value,
            "per_leg": [
                {
                    "leg_index": leg.leg_index,
                    "tradingsymbol": leg.tradingsymbol,
                    "side": leg.side,
                    "requested_contracts": leg.requested_contracts,
                    "top_of_book_quantity": leg.top_of_book_quantity,
                    "fillable_contracts": leg.fillable_contracts,
                    "slippage_bps_to_fill_requested":
                        leg.slippage_bps_to_fill_requested,
                    "tier": leg.tier.value,
                }
                for leg in self.per_leg
            ],
            "warnings": list(self.warnings),
        }


def _walk_the_book_bps(requested: int, top_of_book: int,
                        walk_step_bps: float = 5.0) -> float:
    """Estimate slippage in bps to fill ``requested``
    contracts given ``top_of_book`` depth.

    The model is simple: if requested <= top_of_book, no
    slippage (0 bps). For each additional contract beyond
    top-of-book, add ``walk_step_bps`` (default 5 bps per
    contract). This is a heuristic -- real walking-the-book
    is non-linear and exchange-specific. We surface it as
    a WARN-tier signal, not a precise model.
    """
    if requested <= top_of_book:
        return 0.0
    extra = requested - top_of_book
    return float(extra * walk_step_bps)


def _tier_for(requested: int, top_of_book: int) -> LiquidityTier:
    """Classify the depth-vs-requested relationship.

    SURPLUS:        >= 5x requested.
    TIGHT:          1x <= ratio < 5x.
    INSUFFICIENT:   ratio < 1x (cannot fill at top-of-book).
    """
    if requested <= 0 or top_of_book <= 0:
        return LiquidityTier.INSUFFICIENT
    ratio = top_of_book / requested
    if ratio >= 5.0:
        return LiquidityTier.SURPLUS
    if ratio >= 1.0:
        return LiquidityTier.TIGHT
    return LiquidityTier.INSUFFICIENT


def compute_liquidity_sizing(card: dict, requested_contracts: int = 1,
                                walk_step_bps: float = 5.0,
                                slippage_tolerance_bps: float = 50.0,
                                ) -> LiquiditySizingResult:
    """Compute liquidity-aware sizing for a partner card.

    Args:
        card: a partner card dict (matches the dict shape
            ``_candidate_payload`` produces). Required keys:
            ``legs``, where each leg is a dict with at least
            ``side`` and ideally ``bid_quantity`` /
            ``ask_quantity`` / ``tradingsymbol``.
        requested_contracts: how many contracts the operator
            wants to fill per leg. Default 1.
        walk_step_bps: estimated slippage in bps per
            contract beyond top-of-book. Default 5 bps.
            Operator can override per exchange.
        slippage_tolerance_bps: total slippage above which
            the result is flagged with a warning. Default 50 bps.

    Returns:
        A ``LiquiditySizingResult`` with per-leg breakdown
        and an aggregate tier.

    Notes:
        If a leg has neither ``bid_quantity`` nor
        ``ask_quantity`` set, we treat top-of-book as 0
        and flag the leg as INSUFFICIENT with a warning.
    """
    legs = card.get("legs", []) if isinstance(card, dict) else []
    if not isinstance(legs, (list, tuple)) or not legs:
        raise ValueError("card must have a non-empty legs list")

    per_leg: list[LegLiquidity] = []
    warnings_list: list[str] = []

    for i, leg in enumerate(legs):
        if not isinstance(leg, dict):
            warnings_list.append(f"leg[{i}] is not a dict; skipping")
            continue
        side = str(leg.get("side", "")).upper()
        tradingsymbol = str(leg.get("tradingsymbol", "?"))
        # BUY legs consume ask_quantity (you hit the ask);
        # SELL legs consume bid_quantity.
        if side == "BUY":
            top_qty = leg.get("ask_quantity")
        elif side == "SELL":
            top_qty = leg.get("bid_quantity")
        else:
            top_qty = None

        # Sentinel: missing depth is INSUFFICIENT, top_qty=0.
        if top_qty is None:
            warnings_list.append(
                f"leg[{i}] ({tradingsymbol}) has no "
                f"{'ask' if side == 'BUY' else 'bid'}_quantity; "
                "cannot assess depth -- treating as INSUFFICIENT."
            )
            top_qty = 0

        try:
            top_qty_int = int(top_qty)
        except (TypeError, ValueError):
            warnings_list.append(
                f"leg[{i}] ({tradingsymbol}) has non-integer "
                f"top-of-book quantity ({top_qty!r}); treating as 0."
            )
            top_qty_int = 0

        fillable = min(requested_contracts, top_qty_int)
        slippage = _walk_the_book_bps(
            requested_contracts, top_qty_int, walk_step_bps=walk_step_bps,
        )
        tier = _tier_for(requested_contracts, top_qty_int)

        per_leg.append(LegLiquidity(
            leg_index=i,
            tradingsymbol=tradingsymbol,
            side=side,
            requested_contracts=requested_contracts,
            top_of_book_quantity=top_qty_int,
            fillable_contracts=fillable,
            slippage_bps_to_fill_requested=slippage,
            tier=tier,
        ))

        if tier == LiquidityTier.INSUFFICIENT:
            warnings_list.append(
                f"leg[{i}] ({tradingsymbol}, {side}): requested "
                f"{requested_contracts} contracts, top-of-book has "
                f"{top_qty_int} -- cannot fill without walking the book "
                f"(~{slippage:.0f} bps slippage)."
            )

    if not per_leg:
        raise ValueError("no valid legs found")

    # Aggregate.
    max_fillable = min(leg.fillable_contracts for leg in per_leg)
    total_slippage = sum(leg.slippage_bps_to_fill_requested
                          for leg in per_leg)
    # Worst-case tier across legs.
    tier_order = {
        LiquidityTier.SURPLUS: 0,
        LiquidityTier.TIGHT: 1,
        LiquidityTier.INSUFFICIENT: 2,
    }
    worst_tier = max((leg.tier for leg in per_leg),
                       key=lambda t: tier_order[t])
    if total_slippage > slippage_tolerance_bps:
        warnings_list.append(
            f"total slippage {total_slippage:.0f} bps exceeds "
            f"tolerance {slippage_tolerance_bps:.0f} bps -- "
            "operator should consider scaling down."
        )

    return LiquiditySizingResult(
        requested_contracts=requested_contracts,
        max_fillable_contracts=max_fillable,
        walk_the_book_cost_bps=total_slippage,
        liquidity_tier=worst_tier,
        per_leg=tuple(per_leg),
        warnings=tuple(warnings_list),
    )


__all__ = [
    "LiquidityTier",
    "LegLiquidity",
    "LiquiditySizingResult",
    "compute_liquidity_sizing",
]
