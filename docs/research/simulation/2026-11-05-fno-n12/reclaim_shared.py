"""Quote-only one-lot reclaim on the native shared directional book."""

from dataclasses import dataclass
from datetime import datetime

import fno_n11
from config import settings
from fno_adaptive_risk import Close
from fno_chain import ChainSnapshot
from fno_costs import calc_fno_costs
from fno_entry_plan import REENTRY_STOP_REASONS, EntryState, reentry_level
from fno_exit_rules import IST
from fno_positions import FnoPosition
from prior_range_reclaim import Signal
from reclaim_execution import RangeSleeve
from shared_control import PAPER, Exit, SharedControl, Step, Tick


RECLAIM = "PRIOR_RANGE_RECLAIM"


@dataclass(frozen=True)
class ReclaimQuote:
    signal: Signal
    signal_at: datetime
    chain: ChainSnapshot
    regime: str
    is_expiry_day: bool


@dataclass(frozen=True)
class ReclaimDecision:
    at: datetime
    signal_at: datetime
    reason: str
    cash_before_rs: float
    open_premium_rs: float
    trades_today: int
    risk_multiplier: float
    position_id: int | None = None


@dataclass(frozen=True)
class ReclaimStep:
    shared: Step
    entry: ReclaimDecision | None
    held_gap: tuple[datetime, str] | None


class ReclaimControl(SharedControl):
    def __init__(self, allocation, *, gate_tape=None, reclaim_stress=0.):
        super().__init__(allocation, gate_tape=gate_tape)
        self._sleeve = RangeSleeve(allocation, stress=reclaim_stress)

    def step_with_reclaim(self, tick: Tick, quote: ReclaimQuote | None = None) -> ReclaimStep:
        if quote is not None:
            if quote.chain.taken_at != tick.at:
                raise ValueError("reclaim requires a verified quote at this entry clock")
            self._sleeve._check_signal_clock(quote.signal, quote.signal_at, quote.chain)
        prior_gaps = len(self._sleeve.coverage_gaps)
        shared = super().step(tick)
        entry = self._enter_reclaim(tick, quote) if quote is not None else None
        gap = self._sleeve.coverage_gaps[-1] if len(self._sleeve.coverage_gaps) > prior_gaps else None
        return ReclaimStep(shared, entry, gap)

    def _enter_reclaim(self, tick, quote):
        now = tick.at.astimezone(IST)
        day = now.date()
        chain = quote.chain
        expiry_day = (quote.is_expiry_day or day >= chain.expiry
                      or (chain.fut_quote is not None and day >= chain.fut_quote.contract.expiry))
        halts, stance = self._risk(now)
        positions = self.positions.values()
        state = EntryState(
            pool=self.equity, open_premium=self._open_premium(),
            open_positions=sum(p.strategy != fno_n11.ADD for p in positions),
            trades_today=self._trades.get(day, 0), active_kill_switches=halts,
            held_symbols=frozenset(p.tradingsymbol for p in positions),
            is_trading_day=tick.trading_day, is_expiry_day=expiry_day,
            risk_multiplier=stance.multiplier, lot_ceiling=1,
            correlated_open_directions=frozenset(p.direction for p in positions),
            reentry_levels=self._stopped.get((day, "NIFTY")) if settings.FNO_REENTRY_REQUIRES_CONFIRMATION else None,
        )
        available = self._available(tick.spread_reserve_rs)
        position_id = None
        if self._sleeve._attempt_day == day:
            reason = "already_attempted"
        else:
            reason = self._sleeve._enter(quote.signal, quote.signal_at, chain, quote.regime,
                                         expiry_day, tick.trading_day, None, capital=(state, available))
            if reason == "accepted":
                position_id = self._register_reclaim(quote)
        return ReclaimDecision(now, quote.signal_at, reason, available, state.open_premium,
                               state.trades_today, stance.multiplier, position_id)

    def _register_reclaim(self, quote):
        p = self._sleeve.position
        contract = next(q.contract for q in quote.chain.quotes.values()
                        if (q.contract.token, q.contract.tradingsymbol) == (p.token, p.symbol))
        position_id = self._next_id
        self.positions[position_id] = FnoPosition(
            id=position_id, source=PAPER, tradingsymbol=p.symbol, token=p.token, underlying="NIFTY",
            expiry=contract.expiry.isoformat(), strike=contract.strike, opt_type=contract.instrument_type,
            direction=p.direction.value, lots=1, lot_size=p.qty, qty=p.qty, entry_time=p.entered.isoformat(),
            entry_date=p.entered.date().isoformat(), entry_premium=p.ask, entry_underlying=quote.chain.forward,
            delta_at_entry=p.delta, iv_at_entry=p.iv, atr_at_entry=0., stop_underlying=p.stop, target_underlying=p.target,
            premium_stop=p.premium_stop, trail_active=0, trail_stop_underlying=None, best_underlying=quote.chain.forward,
            max_loss_rupees=p.ask * p.qty, status="OPEN", bar_ts=quote.signal_at.isoformat(),
            settlement_generation=0, strategy=RECLAIM,
        )
        self._fees[position_id] = calc_fno_costs(p.ask, 0., p.qty) + self._sleeve.stress
        self._next_id += 1
        day = p.entered.date()
        self._trades[day] = self._trades.get(day, 0) + 1
        return position_id

    def _manage(self, p, now, future, bid):
        if p.strategy != RECLAIM:
            return super()._manage(p, now, future, bid)
        # SharedControl has already verified this token's usable bid and depth.
        _, close = self._sleeve.manage(now, future, token=p.token, bid=bid, bid_quantity=p.qty)
        if close is None:
            return None
        self.closes.append(Close(now, close.net, single_leg=True))
        day = now.date()
        self._directional_net[day] = self._directional_net.get(day, 0.) + close.net
        del self.positions[p.id], self._fees[p.id]
        if close.reason in REENTRY_STOP_REASONS:
            levels = self._stopped.setdefault((day, p.underlying), {})
            levels[p.direction] = reentry_level(p.direction, p.entry_underlying, p.stop_underlying,
                                                settings.FNO_REENTRY_MARGIN_R)
        return Exit(p.id, p.underlying, p.tradingsymbol, now, bid, p.qty, close.reason, close.fees, close.net)
