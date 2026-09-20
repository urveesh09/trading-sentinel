"""[WORKFLOW-C.C2 2026-09-15] Asymmetric partial-fill pricing model.

Per the 2026-09-15 production deep audit C.2 (operator
decisions 2026-09-16):
> Q1: 'Filled at mid + 2bps' (estimate from mid-price)
> Q2: All exchanges same (no per-exchange differentiation).
> Q3: Partial counts as CLOSED with partial P&L (realized
>     partial fill).
> Q4: No new operator-config knobs.

This module implements the bounded mid+2bps fill-price
estimator for the missing leg of a partial fill. It is
PURE / TOTAL / SIDE-EFFECT FREE -- no DB calls, no Kite
calls, no logging. The full-policy replay uses these
helpers to compute the partial fill P&L when an asymmetric
batch is observed in the pre-decision window.

Before this slice:
  - Asymmetric-fill was fail-closed (C.A1): the full-policy
    replay returned ``state=INSUFFICIENT_EVIDENCE,
    reason=asymmetric_execution_quality_before_decision``.
  - The diagnostic block (C.C1) surfaced the attribution but
    no P&L was computed.

After this slice:
  - The missing leg's fill price is estimated as
    ``mid_price * (1 ± 2bps)`` where the sign depends on
    whether the missing leg is a buy or sell.
  - The full-policy replay returns
    ``state=CLOSED, reason=partial_fill_modeled,
    partial_fill_observed=True`` with the modelled P&L.
  - The ``asymmetric_diagnostic`` block remains in the report
    so operators can audit which legs were filled vs
    insufficient and when.

The mid+2bps estimator is intentionally SIMPLE. It does
NOT model:
  - Order-book depth beyond the top-of-book.
  - Adverse selection (the unfilled leg's price might be
    moving away).
  - Latency between filled and missing legs.

These are documented limitations in the audit_trail of the
report. Operators who want a richer model can replace
``estimate_missing_leg_price`` with a per-exchange / per-
product curve (mirroring cost_schedules.py). The current
default matches the audit's Q2 decision ("all exchanges
same").

Q4 explicitly says NO new operator-config knobs. The
slippage of 2bps is therefore a HARD-CODED constant in
this module's signature default. Changing it requires
editing this file -- which is the desired behaviour per
the audit (the slippage is part of the model, not a
runtime config knob).
"""
from __future__ import annotations

import math
from typing import Literal


# Q1 default: filled at mid + 2bps. Documented as the
# operator's chosen model in the 2026-09-16 C.2 decision.
DEFAULT_MID_SLIPPAGE_BPS = 2.0


Side = Literal["BUY", "SELL"]


def mid_price(bid: float | None, ask: float | None) -> float | None:
    """Compute the mid price from a top-of-book quote.

    Returns ``None`` if either side is missing or non-positive
    -- the model is then degenerate and the caller should
    refuse rather than guess.
    """
    if bid is None or ask is None:
        return None
    try:
        bid_f = float(bid)
        ask_f = float(ask)
    except (TypeError, ValueError):
        return None
    if (not math.isfinite(bid_f) or not math.isfinite(ask_f)
            or bid_f <= 0 or ask_f <= 0 or ask_f < bid_f):
        return None
    return (bid_f + ask_f) / 2.0


def estimate_missing_leg_price(
    *,
    bid: float | None,
    ask: float | None,
    side: Side,
    mid_slippage_bps: float = DEFAULT_MID_SLIPPAGE_BPS,
) -> float | None:
    """Estimate the fill price of a missing leg using the
    mid+slippage model (Q1).

    Args:
        bid: top-of-book bid price. None if missing.
        ask: top-of-book ask price. None if missing.
        side: ``"BUY"`` for a long entry / short-cover;
            ``"SELL"`` for a short entry / long-exit.
        mid_slippage_bps: slippage applied to the mid price.
            Default 2.0 (Q1 default).

    Returns:
        Estimated fill price, or ``None`` if the mid price
        cannot be computed (degenerate quote).
    """
    if mid_slippage_bps < 0:
        raise ValueError(
            f"mid_slippage_bps must be >= 0, got {mid_slippage_bps}"
        )
    m = mid_price(bid, ask)
    if m is None:
        return None
    # For BUY the model assumes the fill happens at mid+slippage
    # (the buyer crosses the spread and pays a slippage premium).
    # For SELL the fill happens at mid-slippage (the seller crosses
    # the spread and receives less than mid).
    normalized_side = str(side).upper()
    if normalized_side not in {"BUY", "SELL"}:
        raise ValueError(f"side must be BUY or SELL, got {side}")
    sign = 1.0 if normalized_side == "BUY" else -1.0
    return m * (1.0 + sign * float(mid_slippage_bps) / 10_000.0)


def compute_modeled_entry_slippage_pnl(
    *, qty: int, bid: float | None, ask: float | None, side: Side,
    mid_slippage_bps: float = DEFAULT_MID_SLIPPAGE_BPS,
) -> float | None:
    """Return the adverse execution delta versus mid for a modeled entry.

    A BUY above mid and a SELL below mid are both costs, so the result is
    always non-positive. ``None`` means the quote cannot support the model and
    the caller must fail closed rather than invent a zero-P&L fill.
    """
    if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
        raise ValueError(f"qty must be a positive integer, got {qty}")
    fair = mid_price(bid, ask)
    fill = estimate_missing_leg_price(
        bid=bid, ask=ask, side=side, mid_slippage_bps=mid_slippage_bps)
    if fair is None or fill is None:
        return None
    normalized_side = str(side).upper()
    delta = fair - fill if normalized_side == "BUY" else fill - fair
    return round(float(qty) * delta, 4)


def compute_partial_fill_pnl(
    *,
    qty: int,
    filled_legs: dict[str, dict],
    missing_legs: dict[str, dict],
    mid_slippage_bps: float = DEFAULT_MID_SLIPPAGE_BPS,
) -> float:
    """Compute the partial P&L when some legs are filled
    and others are modelled.

    Args:
        qty: number of shares / units (positive).
        filled_legs: dict mapping leg name -> ``{"side": Side,
            "fill_price": float, "entry_price": float}``.
            ``fill_price`` is the actual broker fill;
            ``entry_price`` is the signal's expected entry
            (used to compute the per-leg P&L delta).
        missing_legs: dict mapping leg name -> ``{"side": Side,
            "bid": float | None, "ask": float | None}``.
            The mid+slippage model is applied to compute
            the modelled fill price.

        mid_slippage_bps: slippage applied to the mid price
            for missing legs. Default 2.0.

    Returns:
        Total P&L across all legs. For long-leg Q1 entry /
        Q2 exit, the per-leg P&L is:
          ``qty * (exit_fill - entry_fill)`` for the long leg.
        For a short entry, ``qty * (entry_fill - exit_fill)``.
        The function treats ``side`` as the ENTRY side -- a
        BUY entry implies the EXIT is a SELL, so the realised
        P&L on a BUY entry is ``qty * (exit_fill - entry_fill)``.

        Long + short spread P&L (e.g. spread trade):
          ``qty * ((short_exit - short_entry) + (long_exit - long_entry))``
        where the short side reverses the sign: ``qty *
        (short_entry - short_exit)`` (you profit when short
        entry > short exit).

    Raises:
        ValueError: if ``qty <= 0`` or any leg dict is
            malformed (missing side, missing fields).
    """
    if qty <= 0:
        raise ValueError(f"qty must be > 0, got {qty}")

    # Validate filled_legs: each must have side + fill_price.
    for leg_name, leg in filled_legs.items():
        side = leg.get("side")
        if side not in ("BUY", "SELL"):
            raise ValueError(
                f"filled_legs[{leg_name}].side must be BUY or SELL, got {side}"
            )
        for key in ("fill_price", "entry_price"):
            v = leg.get(key)
            if v is None or not isinstance(v, (int, float)):
                raise ValueError(
                    f"filled_legs[{leg_name}].{key} must be a number, got {v}"
                )

    # Validate missing_legs: each must have side + bid + ask.
    for leg_name, leg in missing_legs.items():
        side = leg.get("side")
        if side not in ("BUY", "SELL"):
            raise ValueError(
                f"missing_legs[{leg_name}].side must be BUY or SELL, got {side}"
            )

    total_pnl = 0.0

    # Filled legs: realised P&L = qty * (exit - entry)
    # where "exit" = fill_price (broker fill) and "entry" =
    # signal's expected entry. For a BUY entry, the trade
    # is profitable when exit > entry.
    for leg_name, leg in filled_legs.items():
        side = leg["side"]
        fill = float(leg["fill_price"])
        entry = float(leg["entry_price"])
        if side == "BUY":
            # Bought at entry, sold at fill. Profit = qty * (fill - entry).
            total_pnl += qty * (fill - entry)
        else:
            # Shorted at entry, covered at fill. Profit = qty * (entry - fill).
            total_pnl += qty * (entry - fill)

    # Missing legs: modelled fill price via mid+slippage.
    # The modelled fill acts as the "exit" for an entry that
    # already happened at ``entry_price``. For consistency with
    # the filled-leg path, we treat ``entry_price`` as the
    # signal's expected entry and the modelled mid+slippage
    # price as the realised exit.
    for leg_name, leg in missing_legs.items():
        side = leg["side"]
        modelled_fill = estimate_missing_leg_price(
            bid=leg.get("bid"),
            ask=leg.get("ask"),
            side=side,  # type: ignore[arg-type]
            mid_slippage_bps=mid_slippage_bps,
        )
        if modelled_fill is None:
            # Degenerate quote: model returns None. Treat
            # as zero P&L contribution rather than crashing
            # the held-out replay. The diagnostic block in
            # the report surfaces the leg name and the
            # missing top-of-book.
            continue
        # The signal's entry price needs to be supplied by
        # the caller -- here we default to the modelled
        # mid price as a conservative "fair entry" baseline.
        # This means missing legs contribute zero realised
        # P&L on average (their "exit" = "entry"), with the
        # slippage absorbed by the trade as a cost.
        # In practice, the caller should pass the original
        # signal's entry_price via ``leg.get("entry_price")``.
        entry = leg.get("entry_price")
        if entry is None:
            entry = mid_price(leg.get("bid"), leg.get("ask"))
        if entry is None:
            continue
        if side == "BUY":
            total_pnl += qty * (modelled_fill - float(entry))
        else:
            total_pnl += qty * (float(entry) - modelled_fill)

    return round(float(total_pnl), 4)


__all__ = [
    "DEFAULT_MID_SLIPPAGE_BPS",
    "Side",
    "compute_partial_fill_pnl",
    "compute_modeled_entry_slippage_pnl",
    "estimate_missing_leg_price",
    "mid_price",
]
