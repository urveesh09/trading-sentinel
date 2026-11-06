"""Own-wallet, one-lot paper execution for the frozen range-reclaim signal."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from config import settings
from fno_adaptive_risk import Close, policy_from_settings as adaptive_policy, risk_stance
from fno_chain import ChainSnapshot
from fno_costs import calc_fno_costs
from fno_engine_mom import MomSignal
from fno_entry_plan import EntryState, plan_single_leg_entry
from fno_exit_rules import IST
from fno_models import FnoDirection
from fno_shared_risk import entry_halts, policy_from_settings
from prior_range_reclaim import Signal


@dataclass(frozen=True)
class Position:
    entered: datetime
    symbol: str
    token: int
    direction: FnoDirection
    qty: int
    ask: float
    premium_stop: float
    stop: float
    target: float
    delta: float
    iv: float


@dataclass(frozen=True)
class Settlement:
    at: datetime
    reason: str
    bid: float
    fees: float
    stress: float
    net: float


class RangeSleeve:
    """Caller supplies the first complete chain and exact held observations."""

    def __init__(self, allocation=250_000., *, stress=205.):
        if not isfinite(allocation) or allocation <= 0 or not isfinite(stress) or stress < 0:
            raise ValueError("invalid standalone allocation or stress")
        self.allocation = allocation
        self.stress = stress
        self.position: Position | None = None
        self.closes: list[Close] = []
        self.coverage_gaps: list[tuple[datetime, str]] = []
        self._last_at = None
        self._attempt_day = None

    @property
    def equity(self):
        return self.allocation + sum(close.pnl for close in self.closes)

    def _advance(self, at):
        if at.utcoffset() is None or (self._last_at is not None and at <= self._last_at):
            raise ValueError("standalone clocks must be aware and strictly increasing")
        now = at.astimezone(IST)
        if self.position and self.position.entered.date() != now.date():
            raise ValueError("unresolved standalone position from an earlier session")
        self._last_at = now
        return now

    def enter(self, signal: Signal, signal_at: datetime, chain: ChainSnapshot, regime: str, *,
              is_expiry_day: bool, is_trading_day: bool = True) -> str:
        return self._enter(signal, signal_at, chain, regime, is_expiry_day, is_trading_day, traded=None)

    @staticmethod
    def _check_signal_clock(signal, signal_at, chain):
        if signal_at.utcoffset() is None or chain.taken_at.utcoffset() is None:
            raise ValueError("signal and quote clocks must be aware")
        signal_at = signal_at.astimezone(IST)
        if (signal_at.hour * 60 + signal_at.minute != signal.minute or signal_at.second or
                signal_at.microsecond or signal_at.date() != chain.taken_at.astimezone(IST).date()):
            raise ValueError("entry signal clock does not match the frozen completed bar")
        if not all(isfinite(value) for value in (signal.close, signal.stop, signal.target)):
            raise ValueError("invalid frozen signal geometry")
        return signal_at

    def _enter(self, signal, signal_at, chain, regime, is_expiry_day, is_trading_day, traded, *, capital=None):
        signal_at = self._check_signal_clock(signal, signal_at, chain)
        at = self._advance(chain.taken_at)
        if self._attempt_day == at.date():
            return "already_attempted"
        self._attempt_day = at.date()
        if not 0 <= (at - signal_at).total_seconds() < 60:
            return "first_quote_outside_window"
        if (not isfinite(chain.forward) or chain.forward <= 0 or chain.fut_quote is None
                or chain.fut_quote.contract.name != "NIFTY" or chain.fut_quote.contract.instrument_type != "FUT"
                or chain.fut_quote.ltp != chain.forward or chain.lot_size <= 0):
            return "unverified_nifty_future"
        if any(q.contract.name != "NIFTY" or q.contract.expiry != chain.expiry
               or q.contract.lot_size != chain.lot_size or (q.last_trade_time is not None and (
                   q.last_trade_time.utcoffset() is None or q.last_trade_time > at
               )) for q in chain.quotes.values()):
            return "unverified_nifty_chain"

        direction = FnoDirection(signal.direction)
        sign = 1 if direction == FnoDirection.LONG else -1
        planned = sign * (signal.close - signal.stop)
        risk = sign * (chain.forward - signal.stop)
        reward = sign * (signal.target - chain.forward)
        if not 0 < risk <= planned or reward < 1.5 * risk:
            return "reclaim_geometry_at_quote"

        state, available = self._own_capital(at, is_expiry_day, is_trading_day) if capital is None else capital
        sig = MomSignal(bar_ts=signal_at.isoformat(), direction=direction,
                        close=signal.close, stop_underlying=signal.stop, target_underlying=signal.target)
        plan = plan_single_leg_entry(sig, chain, regime, at, state)
        if not plan.accepted:
            return plan.reject_reason
        quote = plan.quote
        qty, ask = plan.lot_size, quote.ask
        if traded is None:
            if quote.ask_quantity < qty:
                return "ask_depth_unavailable"
        elif quote.contract.token not in traded or quote.last_trade_time != at:
            return "selected_contract_no_trade_this_minute"
        if ask * qty + calc_fno_costs(ask, 0., qty) + self.stress > available:
            return "full_cash_reserve"
        self.position = Position(at, quote.contract.tradingsymbol, quote.contract.token, direction, qty, ask,
                                 round(ask * (1 - settings.FNO_STOP_PREMIUM_PCT), 2),
                                 signal.stop, signal.target, plan.delta, plan.iv)
        return "accepted"

    def _own_capital(self, at, is_expiry_day, is_trading_day):
        cash = [(close.at, close.pnl) for close in self.closes]
        equity = self.equity
        halts = entry_halts(trade_cash=cash, completed_newest_first=list(reversed(cash)),
                            today_ist=at.date(), pool_rs=self.allocation, equity_rs=equity,
                            policy=policy_from_settings()).active
        stance = risk_stance(self.closes, allocation=self.allocation, now=at, policy=adaptive_policy())
        state = EntryState(equity, 0., 0, 0, halts, frozenset(), is_trading_day,
                           is_expiry_day, risk_multiplier=stance.multiplier, lot_ceiling=1)
        return state, equity

    def manage(self, at: datetime, future: float | None, *, token: int, bid: float,
               bid_quantity: int) -> tuple[str, Settlement | None]:
        supported = self.position is not None and bid_quantity >= self.position.qty
        return self._manage(at, future, token, bid, supported)

    def _manage(self, at, future, token, bid, supported):
        now = self._advance(at)
        p = self.position
        if p is None:
            return "flat", None
        if token != p.token or not isfinite(bid) or bid <= 0 or not supported:
            self.coverage_gaps.append((now, "held_bid_unavailable"))
            return "held_bid_unavailable", None
        hard_flat = now.hour * 60 + now.minute >= settings.FNO_HARD_FLAT_MIN
        if hard_flat:
            reason = "hard_flat"
        elif future is None or not isfinite(future) or future <= 0:
            self.coverage_gaps.append((now, "held_future_unavailable"))
            return "held_future_unavailable", None
        elif (future <= p.stop if p.direction == FnoDirection.LONG else future >= p.stop):
            reason = "underlying_stop"
        elif bid <= p.premium_stop:
            reason = "premium_backstop"
        elif (future >= p.target if p.direction == FnoDirection.LONG else future <= p.target):
            reason = "midpoint_target"
        else:
            return "hold", None
        fees = calc_fno_costs(p.ask, bid, p.qty)
        net = (bid - p.ask) * p.qty - fees - self.stress
        self.closes.append(Close(now, net, single_leg=True))
        self.position = None
        return "closed", Settlement(now, reason, bid, fees, self.stress, net)
