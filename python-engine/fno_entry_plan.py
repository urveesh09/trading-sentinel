"""Pure single-leg F&O entry planning shared by the live tick and research replay.

Extracted from ``fno_orchestrator._try_entry_for_leg`` so the replay evaluates
*the same* decision instead of a copy that could drift. Given a fired signal,
a chain snapshot and the book's current state, it performs, in the shipped
order: strike selection (|delta| closest to FNO_TARGET_DELTA, ATM-or-ITM), the
§7 gate ladder, the no-pyramid same-contract refusal, pool sizing under the
risk and open-premium caps, the §4 max-loss constitution and the net reward/
risk check. No I/O: the caller reads state, logs the outcome and performs any
reservation and dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, FrozenSet, Optional, Sequence

from config import settings
from fno_chain import ChainSnapshot, select_strike_by_delta
from fno_engine_mom import MomSignal
from fno_gates import GateContext, evaluate_entry_gates_with_trace
from fno_models import ContractQuote, FnoDirection, Leg, OptionType
from fno_risk import lots_for_pool, min_viable_pool, validate_position


@dataclass(frozen=True)
class EntryState:
    """Book state an entry decision depends on (read by the caller)."""
    pool: float
    open_premium: float
    open_positions: int
    trades_today: int
    active_kill_switches: Sequence[str]
    held_symbols: FrozenSet[str]
    is_trading_day: bool
    is_expiry_day: bool


@dataclass
class EntryPlan:
    """Accepted plan, or the first reject reason with its audit fields."""
    accepted: bool
    reject_reason: str
    log_fields: dict = field(default_factory=dict)
    quote: Optional[ContractQuote] = None
    opt_type: Optional[OptionType] = None
    iv: float = 0.0
    delta: float = 0.0
    lots: int = 0
    lot_size: int = 0
    max_loss_rupees: float = 0.0
    gate_context: Optional[GateContext] = None
    reward_risk: Optional[float] = None
    rr_terms: dict = field(default_factory=dict)


def quote_age_sec(quote: ContractQuote, now_ist: datetime) -> float:
    return (now_ist - quote.last_trade_time).total_seconds() if quote.last_trade_time else float("inf")


def plan_single_leg_entry(sig: MomSignal, snap: ChainSnapshot, regime: str, now_ist: datetime,
                          state: EntryState) -> EntryPlan:
    opt_type = OptionType.CE if sig.direction == FnoDirection.LONG else OptionType.PE
    picked = select_strike_by_delta(snap, opt_type, now_ist)
    if picked is None:
        return EntryPlan(False, "no_strike_solves_delta")
    quote, iv, delta_val = picked
    contract = quote.contract
    ask = quote.ask
    lot_size = snap.lot_size or contract.lot_size

    ctx = GateContext(
        now_min=now_ist.hour * 60 + now_ist.minute,
        is_trading_day=state.is_trading_day,
        is_expiry_day=state.is_expiry_day,
        regime=regime,
        oi=quote.oi, volume=quote.volume,
        bid=quote.bid, ask=quote.ask, ltp=quote.ltp,
        quote_age_sec=quote_age_sec(quote, now_ist),
        forward=snap.forward, strike=contract.strike,
        is_call=(opt_type == OptionType.CE), iv=iv,
        pool=state.pool, premium=ask, lot_size=lot_size,
        open_premium=state.open_premium, open_positions=state.open_positions,
        trades_today=state.trades_today,
        active_kill_switches=list(state.active_kill_switches),
        chain_age_sec=snap.age_sec(now_ist),
    )
    contract_fields: dict[str, Any] = dict(
        tradingsymbol=contract.tradingsymbol, strike=contract.strike,
        opt_type=opt_type.value, expiry=contract.expiry.isoformat(),
        premium=ask, iv=iv, delta=delta_val, spread_pct=quote.spread_pct,
        oi=quote.oi, volume=quote.volume,
        min_pool_required=min_viable_pool(
            ask, lot_size, settings.FNO_STOP_PREMIUM_PCT, settings.FNO_MAX_RISK_PCT,
        ),
        # The pool the gate actually saw, so the row is falsifiable.
        pool_at_eval=round(float(state.pool), 2),
    )
    plan = EntryPlan(False, "", quote=quote, opt_type=opt_type, iv=iv, delta=delta_val,
                     lot_size=lot_size, gate_context=ctx)

    ok, reject, passed_gates = evaluate_entry_gates_with_trace(ctx)
    audit = {"passed_gates": passed_gates, "active_kill_switches": list(state.active_kill_switches)}
    if not ok:
        plan.reject_reason, plan.log_fields = reject, {**contract_fields, **audit}
        return plan

    # No pyramiding into a contract this leg already holds (count/premium caps
    # and the same-bar guard do not stop a later-bar repeat on one strike).
    if contract.tradingsymbol in state.held_symbols:
        plan.reject_reason, plan.log_fields = "already_holding_this_contract", {**contract_fields, **audit}
        return plan

    # Sizing (§3): decline rather than oversize; the marginal lot must also fit
    # the open-premium cap.
    lots = lots_for_pool(state.pool, ask, lot_size, settings.FNO_STOP_PREMIUM_PCT,
                         settings.FNO_MAX_RISK_PCT, settings.FNO_MAX_LOTS)
    while lots > 0 and state.open_premium + lots * ask * lot_size > settings.FNO_MAX_OPEN_PREMIUM_PCT * state.pool:
        lots -= 1
    if lots < 1:
        plan.reject_reason, plan.log_fields = "pool_below_min_viable", {**contract_fields, "lots": 0, **audit}
        return plan
    plan.lots = lots

    # §4 constitution: no order path exists for an unbounded/oversized loss.
    legs = [Leg(opt_type=opt_type, strike=contract.strike, quantity=lots, premium=ask)]
    ok_ml, reject_ml, ml = validate_position(legs, lot_size)
    plan.max_loss_rupees = ml
    if not ok_ml:
        plan.reject_reason = reject_ml
        plan.log_fields = {**contract_fields, "lots": lots, "max_loss_rupees": ml, **audit}
        return plan

    # A long option is only a trade if its payoff at target beats its loss at
    # stop after paying the spread twice (risk is the tighter of the delta-
    # implied loss at the underlying stop and the premium backstop).
    entry_u = float(snap.forward)
    stop_pts = abs(entry_u - float(sig.stop_underlying))
    target_pts = abs(float(sig.target_underlying) - entry_u)
    abs_delta = abs(float(delta_val)) or 0.0
    reward_rs = abs_delta * target_pts * (lots * lot_size)
    risk_prem_pts = min(abs_delta * stop_pts, ask * settings.FNO_STOP_PREMIUM_PCT)
    risk_rs = risk_prem_pts * (lots * lot_size)
    spread_rs = (quote.spread_pct or 0.0) * ask * (lots * lot_size)
    net_reward, net_risk = reward_rs - spread_rs, risk_rs + spread_rs
    rr = (net_reward / net_risk) if net_risk > 0 else 0.0
    plan.reward_risk = rr
    plan.rr_terms = {"reward": net_reward, "risk": net_risk, "spread": spread_rs, "stop_pts": stop_pts,
                     "target_pts": target_pts, "delta": abs_delta}
    if rr < settings.FNO_MIN_REWARD_RISK:
        plan.reject_reason = "reward_risk_below_min"
        plan.log_fields = {**contract_fields, "lots": lots, "max_loss_rupees": ml, **audit}
        return plan

    plan.accepted = True
    plan.log_fields = {**contract_fields, "lots": lots, "max_loss_rupees": ml, **audit}
    return plan
