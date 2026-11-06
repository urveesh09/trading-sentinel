"""Chronological directional mechanics for the two-index paper control."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from math import isfinite
from typing import Mapping

import fno_book
import fno_n11
from config import settings
from fno_adaptive_risk import Close, policy_from_settings as adaptive_policy, risk_stance
from fno_chain import ChainSnapshot
from fno_costs import calc_fno_costs, options_exchange_for
from fno_engine_mom import MomSignal
from fno_entry_plan import REENTRY_STOP_REASONS, EntryState, plan_single_leg_entry, reentry_level
from fno_exit_rules import IST, evaluate_single_leg_exit, live_single_leg_exit_params
from fno_positions import FnoPosition
from fno_shared_risk import entry_halts, policy_from_settings
from fno_underlyings import SPECS


VENUES = ("NIFTY", "SENSEX")
PAPER = "FNO_PAPER"


@dataclass(frozen=True)
class EntryObservation:
    signal: MomSignal
    chain: ChainSnapshot
    regime: str
    is_expiry_day: bool
    stand_aside: bool
    vol_up: bool
    paper_positive: bool
    spread_preferred: bool = False


@dataclass(frozen=True)
class VenueMarks:
    received_at: datetime
    future: float | None
    bids: Mapping[int, tuple[float, int]]  # exact option token -> (top bid, displayed quantity)


@dataclass(frozen=True)
class Tick:
    at: datetime
    spread_reserve_rs: float  # external confirmed exposure after the tick's spread management
    entries: Mapping[str, EntryObservation] = field(default_factory=dict)
    marks: Mapping[str, VenueMarks] = field(default_factory=dict)
    spread_closes: tuple[float, ...] = ()  # external confirmed close cash, in settlement order
    trading_day: bool = True


@dataclass(frozen=True)
class EntryDecision:
    venue: str
    bar_ts: str
    reason: str
    cash_before_rs: float
    position_id: int | None = None
    tolerance_reason: str | None = None


@dataclass(frozen=True)
class Exit:
    position_id: int
    venue: str
    symbol: str
    at: datetime
    premium: float
    qty: int
    reason: str
    fees: float
    net: float


@dataclass(frozen=True)
class Step:
    exits: tuple[Exit, ...]
    entries: tuple[EntryDecision, ...]
    missing_marks: tuple[int, ...]


class SharedControl:
    """In-memory directional control. The caller supplies verified, causal observations.

    A missing executable bid leaves a held contract unresolved. Record missing
    ticks even when a later bid exists. Historical comparison requires a
    separate clock/coverage check before scoring any result.
    """

    def __init__(self, allocation: float):
        if not isfinite(allocation) or allocation <= 0:
            raise ValueError("allocation must be positive and finite")
        self.allocation = allocation
        self.positions: dict[int, FnoPosition] = {}
        self.closes: list[Close] = []
        self._fees: dict[int, float] = {}
        self._lock_since: dict[int, datetime] = {}
        self._entries: set[tuple[str, str]] = set()
        self._trades: dict[date, int] = {}
        self._stopped: dict[tuple[date, str], dict[str, float]] = {}
        self._last_at: datetime | None = None
        self._next_id = 1

    @property
    def equity(self) -> float:
        return self.allocation + sum(close.pnl for close in self.closes)

    def _available(self, spread_reserve: float) -> float:
        exposure = sum(p.max_loss_rupees + self._fees[p.id] for p in self.positions.values())
        return max(0.0, self.equity - spread_reserve - exposure)

    def step(self, tick: Tick) -> Step:
        at = tick.at
        if at.utcoffset() is None or (self._last_at is not None and at <= self._last_at):
            raise ValueError("tick clocks must be aware and strictly increasing")
        if not isfinite(tick.spread_reserve_rs) or tick.spread_reserve_rs < 0:
            raise ValueError("spread reserve must be known and nonnegative")
        if not all(isfinite(net) for net in tick.spread_closes):
            raise ValueError("spread closes must be finite")
        if (tick.entries.keys() | tick.marks.keys()) - set(VENUES):
            raise ValueError("unsupported venue")
        for marks in tick.marks.values():
            received = marks.received_at
            if received.utcoffset() is None or received > at or (
                self._last_at is not None and received <= self._last_at
            ):
                raise ValueError("management mark must be new and known at the tick")
            if marks.future is not None and (not isfinite(marks.future) or marks.future <= 0):
                raise ValueError("invalid futures mark")
        now = at.astimezone(IST)
        if self.positions and self._last_at.astimezone(IST).date() != now.date():
            raise ValueError('previous session still has unresolved positions')
        for venue, observation in tick.entries.items():
            chain, signal = observation.chain, observation.signal
            if chain.taken_at.utcoffset() is None or chain.taken_at > at:
                raise ValueError("chain must be known at the tick")
            if (not signal.direction or not signal.bar_ts or signal.strategy not in fno_book.EXIT_OVERRIDES
                    or not signal.strategy.startswith(fno_n11.PREFIX) or signal.strategy == fno_n11.ADD):
                raise ValueError("expected a fired native N11 signal")
            bar_open = datetime.fromisoformat(signal.bar_ts)
            if (bar_open.tzinfo is not None or bar_open.date() != now.date()
                    or IST.localize(bar_open + timedelta(minutes=5)) > now):
                raise ValueError("signal bar must be closed on the tick's session")
            if not isfinite(chain.forward) or chain.forward <= 0:
                raise ValueError("invalid chain forward")
            if chain.fut_quote and chain.fut_quote.contract.name != venue:
                raise ValueError("chain futures venue mismatch")
            if any(q.contract.name != venue or q.contract.expiry != chain.expiry
                   or q.contract.lot_size <= 0 or (chain.lot_size and q.contract.lot_size != chain.lot_size)
                   or (q.last_trade_time is not None and (
                       q.last_trade_time.utcoffset() is None or q.last_trade_time > at
                   )) for q in chain.quotes.values()):
                raise ValueError("chain contract, lot or trade clock mismatch")

        exits, missing = [], []
        for position in tuple(self.positions.values()):
            marks = tick.marks.get(position.underlying)
            price, quantity = marks.bids.get(position.token, (0.0, 0)) if marks else (0.0, 0)
            if not isfinite(price) or price <= 0 or quantity < position.qty:
                self._lock_since.pop(position.id, None)
                missing.append(position.id)
                continue
            closed = self._manage(position, now, marks.future, price)
            if closed is not None:
                exits.append(closed)
        self.closes.extend(Close(now, net, single_leg=False) for net in tick.spread_closes)
        decisions = tuple(self._enter(venue, tick.entries[venue], now, tick)
                          for venue in VENUES if venue in tick.entries)
        self._last_at = at
        return Step(tuple(exits), decisions, tuple(missing))

    def _manage(self, p: FnoPosition, now: datetime, future: float | None, bid: float) -> Exit | None:
        exchange = options_exchange_for(p.underlying)
        params = {**live_single_leg_exit_params(settings), **fno_book.exit_overrides(p.strategy)}
        if p.strategy == "N11_EFF" and future is not None:
            risk = abs(p.entry_underlying - p.stop_underlying)
            progress = (future - p.entry_underlying) * (1 if p.direction == "LONG" else -1)
            age = (now - datetime.fromisoformat(p.entry_time)).total_seconds() / 60.0
            params["FNO_TIME_STOP_MIN"] = fno_n11.eff_clock(
                age, p.trail_active, bid, p.entry_premium, p.qty, p.lots,
                progress / risk if risk > 0 else 0.0, exchange=exchange,
            )
        decision = evaluate_single_leg_exit(
            p, now_ist=now, fut_price=future, exit_px_basis=bid,
            hard_flat=(now.hour * 60 + now.minute >= settings.FNO_HARD_FLAT_MIN),
            params=params, lock_breach_since=self._lock_since.get(p.id),
        )
        if decision.exit_reason:
            fees = calc_fno_costs(p.entry_premium, bid, p.qty, exchange=exchange)
            net = (bid - p.entry_premium) * p.qty - fees
            self.closes.append(Close(now, net, single_leg=True))
            del self.positions[p.id], self._fees[p.id]
            self._lock_since.pop(p.id, None)
            if decision.exit_reason in REENTRY_STOP_REASONS:
                levels = self._stopped.setdefault((now.date(), p.underlying), {})
                levels[p.direction] = reentry_level(
                    p.direction, p.entry_underlying, p.stop_underlying, settings.FNO_REENTRY_MARGIN_R,
                )
            return Exit(p.id, p.underlying, p.tradingsymbol, now, bid, p.qty, decision.exit_reason, fees, net)

        if decision.persist_trail:
            p.trail_active = int(decision.trail_active)
            p.trail_stop_underlying = decision.trail_stop
            p.best_underlying = decision.best_underlying
        p.best_premium = decision.best_premium
        if decision.lock_breach_since is None:
            self._lock_since.pop(p.id, None)
        else:
            self._lock_since[p.id] = decision.lock_breach_since
        return None

    def _enter(self, venue: str, obs: EntryObservation, now: datetime, tick: Tick) -> EntryDecision:
        signal, chain = obs.signal, obs.chain
        key = (venue, signal.bar_ts)
        available = self._available(tick.spread_reserve_rs)

        def reject(reason: str) -> EntryDecision:
            return EntryDecision(venue, signal.bar_ts, reason, available)

        if key in self._entries:
            return reject("bar_already_entered")
        if obs.stand_aside:
            return reject("n11:stand_aside")
        if obs.spread_preferred:
            return reject("vehicle_spread_preferred")

        day = now.date()
        positions = self.positions.values()
        cash = [(close.at, close.pnl) for close in self.closes]
        halts = entry_halts(
            trade_cash=cash, completed_newest_first=list(reversed(cash)), today_ist=day,
            pool_rs=self.allocation, equity_rs=self.equity, policy=policy_from_settings(),
        ).active
        stance = risk_stance(self.closes, allocation=self.allocation, now=now, policy=adaptive_policy())
        if stance.single_leg_halted_today:
            halts = (*halts, f"two_strike_day_halt losses={stance.single_leg_losses_today}")
        realised = sum(close.pnl for close in self.closes if close.single_leg and close.at.date() == day)
        ceiling = fno_n11.lot_ceiling(signal.strategy, now.hour * 60 + now.minute, obs.vol_up, realised)
        state = EntryState(
            pool=self.equity, open_premium=sum(p.entry_premium * p.qty for p in positions),
            open_positions=len(self.positions), trades_today=self._trades.get(day, 0),
            active_kill_switches=halts, held_symbols=frozenset(p.tradingsymbol for p in positions),
            is_trading_day=tick.trading_day, is_expiry_day=obs.is_expiry_day,
            risk_multiplier=stance.multiplier, lot_ceiling=ceiling,
            correlated_open_directions=frozenset(p.direction for p in positions if p.underlying != venue),
            reentry_levels=self._stopped.get((day, venue)) if settings.FNO_REENTRY_REQUIRES_CONFIRMATION else None,
        )
        first = plan_single_leg_entry(signal, chain, obs.regime, now, state)
        if not first.accepted:
            return reject(first.reject_reason)
        second = None
        if venue == "NIFTY":
            second = fno_n11.second_lot(
                first, state, stop_points=abs(chain.forward - signal.stop_underlying),
                ceiling=ceiling, is_vol_up=obs.vol_up, is_paper_positive=obs.paper_positive,
            )

        quote = first.quote
        exchange = SPECS[venue].segment
        fill = quote.ask
        for plan in (second.plan, first) if second is not None else (first,):
            qty = plan.lots * plan.lot_size
            fee_reserve = calc_fno_costs(fill, 0.0, qty, exchange=exchange)
            if plan.max_loss_rupees + fee_reserve > available:
                if plan is first:
                    return reject("shared_worst_case_cash_exhausted")
                continue
            if quote.ask_quantity < qty:
                return reject("entry_depth_unavailable")
            break

        contract = quote.contract
        stop = round((1.0 - settings.FNO_STOP_PREMIUM_PCT) * fill, 2)
        upgraded = second is not None and plan is second.plan
        if upgraded:
            stop = fno_n11.second_lot_stop(fill, qty, plan.lots, second.limit, stop)
        position_id = self._next_id
        self.positions[position_id] = FnoPosition(
            id=position_id, source=PAPER, tradingsymbol=contract.tradingsymbol, token=contract.token,
            underlying=venue, expiry=contract.expiry.isoformat(), strike=contract.strike,
            opt_type=contract.instrument_type, direction=signal.direction.value, lots=plan.lots,
            lot_size=plan.lot_size, qty=qty, entry_time=now.isoformat(), entry_date=day.isoformat(),
            entry_premium=fill, entry_underlying=chain.forward, delta_at_entry=plan.delta,
            iv_at_entry=plan.iv, atr_at_entry=signal.atr, stop_underlying=signal.stop_underlying,
            target_underlying=signal.target_underlying, premium_stop=stop, trail_active=0,
            trail_stop_underlying=None, best_underlying=chain.forward, max_loss_rupees=plan.max_loss_rupees,
            status="OPEN", bar_ts=signal.bar_ts, settlement_generation=0, strategy=signal.strategy,
        )
        self._fees[position_id] = fee_reserve
        self._next_id += 1
        self._entries.add(key)
        self._trades[day] = state.trades_today + 1
        return EntryDecision(venue, signal.bar_ts, "accepted", available, position_id,
                             second.reason if upgraded else None)
