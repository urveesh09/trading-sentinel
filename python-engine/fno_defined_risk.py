"""
[FNO-DEFINED-RISK 2026-07-20] Defined-risk multi-leg structures for the F&O
paper book (Phase 2 of the strategy-activation plan).

Why this exists
---------------
The P1 F&O engine buys a naked option off a directional ORB signal. On real
data that book is -Rs 4,274 over 3 paper trades: buying weekly ATM premium is
structurally theta-negative, and SEBI's own data (93% of individual F&O
traders lose, FY22-24) says naked long-option punting is exactly where retail
bleeds. This module replaces it with two *defined-risk* structures whose loss
is capped and whose cost is modelled honestly:

  A. DEBIT_SPREAD  -- directional, on a trend day + a directional signal.
     Buy ATM, sell the OTM strike `width` steps away (same option type).
     Caps theta and cost vs a naked long; loss capped at the net debit.

  B. IRON_CONDOR   -- neutral, on a range day (no directional signal, IV rich).
     Sell an OTM call spread + an OTM put spread. Premium-selling edge WITH
     capped tails (unlike a short strangle, which needs ~Rs 1.5L margin/lot
     and has unbounded loss -- non-viable and unsafe on a small account).

Purity
------
No I/O, no live-chain format, no penny_*/engine imports (fno isolation rule).
Structures are built at the 1-LOT unit; the orchestrator sizes lots later via
fno_risk.lots_for_pool. Payoff/max-loss come from the audited fno_risk
primitives (max_loss, _pnl_points) -- this module never re-derives option math,
so it cannot drift from the risk constitution.

The caller supplies a `PremiumLookup` -- a (opt_type, strike) -> mid-premium
function it adapts from the live chain snapshot -- so this module stays a pure
function of prices.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional

from fno_costs import calc_fno_costs
from fno_models import FnoDirection, Leg, OptionType
import fno_risk


class StructureKind(str, Enum):
    DEBIT_SPREAD = "DEBIT_SPREAD"
    IRON_CONDOR = "IRON_CONDOR"


# (opt_type, strike) -> mid premium (> 0), or None when the strike is missing
# / illiquid in the snapshot. Returning None makes the builder yield None
# (no structure) rather than fabricate a leg -- the module's honesty rule.
PremiumLookup = Callable[[OptionType, float], Optional[float]]


@dataclass(frozen=True)
class Structure:
    """A built, priced, defined-risk structure at the 1-lot unit."""
    kind: StructureKind
    legs: List[Leg]
    lot_size: int
    net_premium: float        # per-unit cashflow at entry: >0 credit, <0 debit
    max_profit_rs: float
    max_loss_rs: float
    breakevens: List[float]

    @property
    def is_defined_risk(self) -> bool:
        return math.isfinite(self.max_loss_rs)

    @property
    def reward_risk(self) -> float:
        return self.max_profit_rs / self.max_loss_rs if self.max_loss_rs > 0 else 0.0


# ---------------------------------------------------------------------------
# regime router: which structure (if any) fits today
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RouterParams:
    """Thresholds for select_structure. Defaults are deliberately
    conservative; the orchestrator can override from config/IV-rank history."""
    min_iv_rank_condor: float = 0.55      # sell premium only when it's rich
    max_expected_move_condor_pct: float = 0.010   # <=1.0% expected daily move
    min_expected_move_debit_pct: float = 0.004    # need some range to pay for a debit


def select_structure(
    has_directional_signal: bool,
    iv_rank: Optional[float],
    expected_move_pct: Optional[float],
    params: Optional[RouterParams] = None,
) -> Optional[StructureKind]:
    """Pick the structure for today's regime, or None (stand aside).

    - Directional signal + enough expected range  -> DEBIT_SPREAD (trend).
    - No signal + rich IV + contained expected move -> IRON_CONDOR (range).
    - Anything ambiguous -> None. Standing aside is a valid, common answer;
      the naked-ORB book's problem was that it always had to trade.
    """
    p = params or RouterParams()
    em = expected_move_pct
    if has_directional_signal:
        if em is None or em >= p.min_expected_move_debit_pct:
            return StructureKind.DEBIT_SPREAD
        return None
    # neutral: only sell premium when it is both rich AND the market is expected
    # to stay inside the wings.
    if (
        iv_rank is not None
        and expected_move_pct is not None
        and iv_rank >= p.min_iv_rank_condor
        and expected_move_pct <= p.max_expected_move_condor_pct
    ):
        return StructureKind.IRON_CONDOR
    return None


# ---------------------------------------------------------------------------
# shared profile computation (single source of truth = fno_risk)
# ---------------------------------------------------------------------------

def _profile(legs: List[Leg], lot_size: int):
    """(net_premium_per_unit, max_profit_rs, max_loss_rs, breakevens) for a
    1-lot structure, using only the audited fno_risk payoff primitives."""
    # Entry cashflow per unit: long legs pay premium (q>0 => cash out),
    # short legs receive it (q<0 => cash in).
    net_premium = -sum(leg.quantity * leg.premium for leg in legs)

    max_loss_rs = fno_risk.max_loss(legs, lot_size)

    strikes = sorted({leg.strike for leg in legs})
    far = max(strikes) * 2.0 if strikes else 0.0
    eval_pts = [0.0] + strikes + [far]
    max_profit_rs = max(fno_risk._pnl_points(legs, s) for s in eval_pts) * lot_size

    breakevens = _breakevens(legs, eval_pts)
    return net_premium, max_profit_rs, max_loss_rs, breakevens


def _breakevens(legs: List[Leg], eval_pts: List[float]) -> List[float]:
    """Zero-crossings of the piecewise-linear expiry P&L. Exact because the
    curve is linear between consecutive strikes."""
    xs = sorted(set(eval_pts))
    out: List[float] = []
    for a, b in zip(xs, xs[1:]):
        pa = fno_risk._pnl_points(legs, a)
        pb = fno_risk._pnl_points(legs, b)
        if pa == 0.0:
            out.append(round(a, 2))
        if (pa < 0 < pb) or (pa > 0 > pb):
            # linear interpolation for the crossing
            out.append(round(a + (b - a) * (-pa) / (pb - pa), 2))
    return sorted(set(out))


# ---------------------------------------------------------------------------
# structure builders (1-lot unit)
# ---------------------------------------------------------------------------

def build_debit_spread(
    direction: FnoDirection,
    atm_strike: float,
    strike_step: float,
    width: int,
    prem: PremiumLookup,
    lot_size: int,
) -> Optional[Structure]:
    """Buy ATM, sell the OTM strike `width` steps away, same option type.
    LONG -> call debit spread (bull); SHORT -> put debit spread (bear)."""
    if width < 1 or strike_step <= 0 or lot_size <= 0:
        return None
    opt = OptionType.CE if direction == FnoDirection.LONG else OptionType.PE
    long_strike = float(atm_strike)
    short_strike = (
        long_strike + width * strike_step
        if opt == OptionType.CE
        else long_strike - width * strike_step
    )
    lp = prem(opt, long_strike)
    sp = prem(opt, short_strike)
    if lp is None or sp is None or lp <= 0 or sp < 0 or sp >= lp:
        # sp >= lp would be a non-positive debit (mispriced/illiquid) -> skip.
        return None
    legs = [
        Leg(opt_type=opt, strike=long_strike, quantity=1, premium=float(lp)),
        Leg(opt_type=opt, strike=short_strike, quantity=-1, premium=float(sp)),
    ]
    net_premium, max_profit, max_loss, bes = _profile(legs, lot_size)
    return Structure(
        kind=StructureKind.DEBIT_SPREAD, legs=legs, lot_size=lot_size,
        net_premium=round(net_premium, 4), max_profit_rs=round(max_profit, 2),
        max_loss_rs=round(max_loss, 2), breakevens=bes,
    )


def build_iron_condor(
    atm_strike: float,
    strike_step: float,
    short_offset: int,
    wing_width: int,
    prem: PremiumLookup,
    lot_size: int,
) -> Optional[Structure]:
    """Sell an OTM call spread + an OTM put spread, symmetric around ATM.
    short_offset = steps from ATM to the short strikes; wing_width = steps
    from each short strike to its protective long wing."""
    if short_offset < 1 or wing_width < 1 or strike_step <= 0 or lot_size <= 0:
        return None
    call_short = atm_strike + short_offset * strike_step
    call_long = call_short + wing_width * strike_step
    put_short = atm_strike - short_offset * strike_step
    put_long = put_short - wing_width * strike_step
    cs, cl = prem(OptionType.CE, call_short), prem(OptionType.CE, call_long)
    ps, pl = prem(OptionType.PE, put_short), prem(OptionType.PE, put_long)
    if any(x is None or x < 0 for x in (cs, cl, ps, pl)):
        return None
    net_credit = (cs + ps) - (cl + pl)
    if net_credit <= 0:
        # No credit -> the structure has no edge and (width - credit) loss; skip.
        return None
    legs = [
        Leg(opt_type=OptionType.CE, strike=call_short, quantity=-1, premium=float(cs)),
        Leg(opt_type=OptionType.CE, strike=call_long, quantity=1, premium=float(cl)),
        Leg(opt_type=OptionType.PE, strike=put_short, quantity=-1, premium=float(ps)),
        Leg(opt_type=OptionType.PE, strike=put_long, quantity=1, premium=float(pl)),
    ]
    net_premium, max_profit, max_loss, bes = _profile(legs, lot_size)
    return Structure(
        kind=StructureKind.IRON_CONDOR, legs=legs, lot_size=lot_size,
        net_premium=round(net_premium, 4), max_profit_rs=round(max_profit, 2),
        max_loss_rs=round(max_loss, 2), breakevens=bes,
    )


# ---------------------------------------------------------------------------
# honest cost model for a multi-leg structure
# ---------------------------------------------------------------------------

def structure_round_trip_cost(structure: Structure) -> float:
    """Estimated round-trip transaction cost (Rs) for the whole structure at
    entry, before we know exit premiums: model each leg as a flat round trip
    (exit == entry premium) and sum. Conservative and consistent with
    fno_costs' 'the book must clear the cost' ethos -- every leg pays its own
    brokerage + taxes, which is what makes 4-leg condors expensive to churn."""
    lot = structure.lot_size
    return round(
        sum(calc_fno_costs(leg.premium, leg.premium, lot) for leg in structure.legs),
        2,
    )


def net_entry_credit_rs(structure: Structure) -> float:
    """Rupee cash received (credit, +) or paid (debit, -) at entry, per lot,
    before costs."""
    return round(structure.net_premium * structure.lot_size, 2)
