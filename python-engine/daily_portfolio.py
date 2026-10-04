"""Shared own-cash daily portfolio book for research replays (EDGE, Swing, Range).

Research only: no fetch, order, database or runtime import. A module supplies
two things — the signals it would have produced after each session's close,
and an exit policy — and this book owns everything that must be identical
across strategies so their results are comparable:

* Clock: signals are decided after session D's close; orders work from D+1.
  A market order fills at D+1's open (the declared 09:30 proxy for daily data).
  A limit order rests for ``entry_valid_sessions`` sessions and fills at the
  open if it gaps through the limit, otherwise at the limit when the low
  reaches it. A missing or zero-volume session never fills.
* Entry checks: optional drift limit against the decision close (market orders
  only), stop below and target above the fill, and an optional policy
  ``admit`` veto. Quantity is re-sized to the signal's planned rupee risk at
  the actual fill, then capped by own cash; a cash-limited fill under
  ``min_fill_fraction`` of plan is skipped as dust.
* Intraday order on daily bars is unknown, so a protective stop is always
  resolved first (a gap below it fills at the open, except on the fill day).
  Resting sell levels are then processed in ascending price order. Close-time
  rules run last and cannot see a later bar.
* Own cash only (no margin), one position per ticker, optional caps on new
  entries per day and on concurrent positions, per-order costs from an injected
  cost function, daily marked equity, and positions still open when data ends
  are marked rather than closed.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
import math
from typing import Any, Callable, Mapping, Protocol, Sequence

CostFunction = Callable[[float, float, int, bool], float]


class PortfolioUnavailable(RuntimeError):
    """Required frozen daily evidence is absent or invalid."""


@dataclass(frozen=True)
class DailySignal:
    """What a strategy decided after ``signal_date``'s close."""
    ticker: str
    signal_date: str
    reference_price: float        # decision close; drift and risk reference
    stop: float
    target: float | None
    planned_shares: int           # the strategy's own sizing at reference_price
    kind: str                     # subtype / setup label used for attribution
    entry_limit: float | None = None
    entry_valid_sessions: int = 1
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not (math.isfinite(self.reference_price) and self.reference_price > 0
                and math.isfinite(self.stop) and 0 < self.stop < self.reference_price):
            raise ValueError(f"{self.ticker}: invalid signal geometry")
        if self.planned_shares < 1:
            raise ValueError(f"{self.ticker}: planned_shares must be positive")
        if self.entry_valid_sessions < 1:
            raise ValueError("entry_valid_sessions must be positive")


@dataclass
class OpenPosition:
    signal: DailySignal
    entry_date: str
    entry_session: int
    entry_price: float
    shares: int
    stop: float
    shares_open: int = 0
    partial_fills: list = field(default_factory=list)
    state: dict = field(default_factory=dict)      # exit-policy scratch space

    def __post_init__(self):
        self.shares_open = self.shares_open or self.shares

    @property
    def initial_risk_per_share(self) -> float:
        return self.entry_price - self.signal.stop

    def age_days(self, day: str) -> int:
        return (date.fromisoformat(day) - date.fromisoformat(self.entry_date)).days


@dataclass(frozen=True)
class RestingLevel:
    price: float
    fraction: float               # of the shares still open; 1.0 sells everything
    reason: str


class ExitPolicy(Protocol):
    def admit(self, signal: DailySignal, open_price: float) -> str | None:
        """Return a skip reason to veto an entry at this open, else None."""

    def resting_levels(self, position: OpenPosition) -> Sequence[RestingLevel]:
        """Resting sell orders active for today's bar (ascending is not required)."""

    def on_partial(self, position: OpenPosition, level: RestingLevel) -> None:
        """React to a filled resting level that left shares open."""

    def at_close(self, position: OpenPosition, bar: Mapping[str, float], day: str,
                 session_index: int) -> str | None:
        """Close-time decision: return an exit reason, or adjust ``position.stop``."""


@dataclass(frozen=True)
class BookConfig:
    bankroll: float
    slippage_bps: float = 5.0
    entry_drift_pct: float | None = None
    max_entries_per_day: int | None = None
    max_open_positions: int | None = None
    min_fill_fraction: float = 0.25
    buy_cost_buffer: float = 0.002

    def __post_init__(self):
        if not math.isfinite(self.bankroll) or self.bankroll <= 0:
            raise ValueError("bankroll must be positive")


def run_daily_book(
    bars: Mapping[str, Mapping[str, Mapping[str, float]]], calendar: Sequence[str], *, end: str,
    signals_after_close: Callable[[str, float], Sequence[DailySignal]], policy: ExitPolicy,
    config: BookConfig, costs: CostFunction,
) -> dict:
    """Run the book over ``calendar`` (sessions from the window start).

    ``signals_after_close(day, equity)`` is called only when the next session is
    still inside the window, so every entry falls inside the scored dates;
    held positions are then managed past ``end`` until flat or data ends.
    ``equity`` is bankroll plus realised P&L, the runtime sizing convention.
    """
    if not [day for day in calendar if day <= end]:
        raise PortfolioUnavailable("no sessions in requested window")
    slip = config.slippage_bps / 10000.0
    cash, realized, capital_days = config.bankroll, 0.0, 0.0
    open_positions: dict[str, OpenPosition] = {}
    pending: list[tuple[int, DailySignal]] = []     # (first eligible session, signal)
    trades: list[dict] = []
    outcomes: Counter = Counter()
    curve: list[tuple[str, float]] = []

    def close(position: OpenPosition, day: str, price: float, reason: str, quantity: int | None = None) -> None:
        nonlocal cash, realized
        quantity = position.shares_open if quantity is None else quantity
        exit_price = price * (1 - slip)
        cost = costs(position.entry_price, exit_price, quantity, day == position.entry_date)
        net = (exit_price - position.entry_price) * quantity - cost
        cash += exit_price * quantity - cost
        realized += net
        position.shares_open -= quantity
        position.partial_fills.append({"date": day, "price": exit_price, "quantity": quantity,
                                       "reason": reason, "net_pnl": net, "costs": cost})
        if position.shares_open == 0:
            del open_positions[position.signal.ticker]
            trades.append(_trade_record(position, "CLOSED", reason))

    for session_index, day in enumerate(calendar):
        # 1. Working entry orders.
        entered, still_pending = 0, []
        for first_session, signal in pending:
            ticker = signal.ticker
            if session_index - first_session >= signal.entry_valid_sessions:
                outcomes["ENTRY_ORDER_EXPIRED"] += 1
                continue
            if ticker in open_positions:
                outcomes["ALREADY_HELD"] += 1
                continue
            if config.max_entries_per_day is not None and entered >= config.max_entries_per_day:
                outcomes["DAILY_ENTRY_CAP"] += 1
                continue
            if config.max_open_positions is not None and len(open_positions) >= config.max_open_positions:
                outcomes["OPEN_POSITION_CAP"] += 1
                continue
            bar = bars.get(ticker, {}).get(day)
            if bar is None or bar["volume"] <= 0:
                outcomes["NO_FILL_MISSING_OR_ZERO_VOLUME_SESSION"] += 1
                continue
            if signal.entry_limit is None:
                fill = bar["open"]
                if (config.entry_drift_pct is not None
                        and abs(fill - signal.reference_price) / signal.reference_price > config.entry_drift_pct):
                    outcomes["DRIFT_REJECTED"] += 1
                    continue
            elif bar["open"] <= signal.entry_limit:
                fill = bar["open"]
            elif bar["low"] <= signal.entry_limit:
                fill = signal.entry_limit
            else:
                still_pending.append((first_session, signal))
                continue
            if signal.stop >= fill:
                outcomes["STOP_ALREADY_BREACHED"] += 1
                continue
            if signal.target is not None and signal.target <= fill:
                outcomes["TARGET_ALREADY_REACHED"] += 1
                continue
            veto = policy.admit(signal, fill)
            if veto:
                outcomes[veto] += 1
                continue
            entry_price = fill * (1 + slip)
            risk_rupees = signal.planned_shares * (signal.reference_price - signal.stop)
            shares = int(risk_rupees // (entry_price - signal.stop))
            affordable = int(cash // (entry_price * (1 + config.buy_cost_buffer)))
            if affordable < shares:
                if affordable < config.min_fill_fraction * shares:
                    outcomes["CASH_REJECTED_DUST"] += 1
                    continue
                outcomes["CASH_LIMITED_RESIZE"] += 1
                shares = affordable
            if shares < 1:
                outcomes["SIZE_ZERO"] += 1
                continue
            cash -= entry_price * shares
            entered += 1
            outcomes["FILLED"] += 1
            open_positions[ticker] = OpenPosition(signal, day, session_index, entry_price, shares, signal.stop)
        pending = still_pending

        # 2. Manage open positions on today's bar.
        for ticker in sorted(open_positions):
            position = open_positions[ticker]
            bar = bars.get(ticker, {}).get(day)
            if bar is None or bar["volume"] <= 0:
                continue   # no executable evidence today; the position stays open
            if bar["low"] <= position.stop:
                gap = day != position.entry_date and bar["open"] <= position.stop
                close(position, day, bar["open"] if gap else position.stop, "STOP_GAP" if gap else "STOP")
                continue
            for level in sorted(policy.resting_levels(position), key=lambda item: item.price):
                if bar["high"] < level.price or ticker not in open_positions:
                    continue
                quantity = position.shares_open
                if level.fraction < 1.0:
                    quantity = max(1, math.floor(position.shares_open * level.fraction))
                close(position, day, level.price, level.reason, quantity)
                if ticker in open_positions:
                    policy.on_partial(position, level)
            if ticker not in open_positions:
                continue
            reason = policy.at_close(position, bar, day, session_index)
            if reason:
                close(position, day, bar["close"], reason)

        # 3. Mark at the close, then decide tomorrow's orders.
        marked = cash
        for ticker, position in open_positions.items():
            last = bars.get(ticker, {}).get(day)
            marked += (last["close"] if last else position.entry_price) * position.shares_open
            capital_days += position.entry_price * position.shares_open
        curve.append((day, round(marked, 4)))
        if session_index + 1 < len(calendar) and calendar[session_index + 1] <= end:
            for signal in signals_after_close(day, config.bankroll + realized):
                pending.append((session_index + 1, signal))
        elif day > end and not open_positions:
            break
    outcomes["ENTRY_ORDER_EXPIRED"] += len(pending)
    for ticker, position in sorted(open_positions.items()):
        last_day = max(d for d in bars[ticker] if d <= calendar[-1])
        record = _trade_record(position, "OPEN_MARKED", None)
        record.update(mark_date=last_day, mark_price=bars[ticker][last_day]["close"])
        trades.append(record)
    return {"trades": trades, "admission_outcomes": dict(sorted((k, v) for k, v in outcomes.items() if v)),
            "summary": summarize(trades, curve, config.bankroll, capital_days), "equity_curve": curve}


def _trade_record(position: OpenPosition, status: str, reason: str | None) -> dict:
    signal = position.signal
    record = {
        "ticker": signal.ticker, "signal_date": signal.signal_date, "kind": signal.kind,
        "entry_date": position.entry_date, "entry_price": round(position.entry_price, 6),
        "shares": position.shares, "initial_stop": signal.stop, "final_stop": round(position.stop, 6),
        "target": signal.target, "planned_shares": signal.planned_shares, "status": status,
        "fills": [{**fill, "price": round(fill["price"], 6), "net_pnl": round(fill["net_pnl"], 4),
                   "costs": round(fill["costs"], 4)} for fill in position.partial_fills],
    }
    if status == "CLOSED":
        net = sum(fill["net_pnl"] for fill in position.partial_fills)
        costs = sum(fill["costs"] for fill in position.partial_fills)
        risk = position.initial_risk_per_share * position.shares
        record.update(exit_date=position.partial_fills[-1]["date"], exit_reason=reason,
                      exit_price=round(position.partial_fills[-1]["price"], 6), net_pnl=round(net, 4),
                      costs=round(costs, 4), gross_pnl=round(net + costs, 4),
                      r_multiple=round(net / risk, 6) if risk > 0 else None)
    return record


def summarize(trades: list[dict], curve: Sequence[tuple[str, float]], bankroll: float,
              capital_days: float) -> dict:
    closed = [t for t in trades if t["status"] == "CLOSED"]
    net = [t["net_pnl"] for t in closed]
    peak, drawdown = bankroll, 0.0
    for _, equity in curve:
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    by_kind: dict = defaultdict(lambda: {"closed": 0, "net_pnl": 0.0, "wins": 0})
    for trade in closed:
        row = by_kind[trade["kind"]]
        row["closed"] += 1
        row["net_pnl"] = round(row["net_pnl"] + trade["net_pnl"], 4)
        row["wins"] += int(trade["net_pnl"] > 0)
    best = max(net) if net else 0.0
    final = curve[-1][1] if curve else bankroll
    return {
        "entries": len(trades), "closed": len(closed),
        "open_marked": sum(t["status"] == "OPEN_MARKED" for t in trades),
        "net_pnl": round(sum(net), 4), "gross_pnl": round(sum(t["gross_pnl"] for t in closed), 4),
        "costs": round(sum(t["costs"] for t in closed), 4),
        "final_marked_equity": final, "marked_return_pct": round(100 * (final - bankroll) / bankroll, 4),
        "max_marked_drawdown": round(drawdown, 4), "max_marked_drawdown_pct": round(100 * drawdown / bankroll, 4),
        "win_rate_pct": round(100 * sum(x > 0 for x in net) / len(net), 2) if net else None,
        "profit_factor": (round(sum(x for x in net if x > 0) / abs(sum(x for x in net if x < 0)), 4)
                          if any(x < 0 for x in net) else None),
        "net_excluding_best_winner": round(sum(net) - best, 4) if best > 0 else round(sum(net), 4),
        "avg_capital_deployed_pct": round(100 * capital_days / (bankroll * max(len(curve), 1)), 4),
        "exit_reasons": dict(sorted(Counter(t.get("exit_reason") or t["status"] for t in trades).items())),
        "by_kind": dict(sorted(by_kind.items())),
    }


def bars_by_ticker(rows: Sequence[tuple]) -> dict[str, dict[str, dict[str, float]]]:
    out: dict = defaultdict(dict)
    for ticker, stamp, open_, high, low, close, volume in rows:
        out[str(ticker).upper()][str(stamp)] = {"open": float(open_), "high": float(high), "low": float(low),
                                                "close": float(close), "volume": float(volume)}
    return dict(out)


def calendar_from(bars: Mapping[str, Mapping[str, Any]], index_ticker: str, start: str) -> list[str]:
    if index_ticker not in bars:
        raise PortfolioUnavailable(f"missing required daily history: {index_ticker}")
    return sorted(day for day in bars[index_ticker] if day >= start)


def penny_cnc_costs(entry: float, exit_price: float, shares: int, intraday: bool) -> float:
    """Runtime Penny cost schedule; research refuses a cost-free bypass."""
    from config import settings
    from penny_risk import calc_penny_costs
    if getattr(settings, "PENNY_BROKERAGE_BYPASS", False):
        raise PortfolioUnavailable("PENNY_BROKERAGE_BYPASS is set; research refuses cost-free P&L")
    return float(calc_penny_costs(entry, exit_price, shares, is_intraday=intraday))


# Delivery charges the runtime Penny schedule omits (as of Oct 2026): STT is
# 0.1% on the BUY as well as the sell, and the depository charges a flat fee
# per scrip on every sell day (Zerodha/CDSL ~Rs 15.93 incl. GST). Runtime
# brokerage on delivery is kept although Zerodha charges none, so this model
# errs towards over-charging.
CNC_BUY_STT_PCT = 0.001
CNC_DP_CHARGE_PER_SELL = 15.93


def penny_cnc_full_costs(entry: float, exit_price: float, shares: int, intraday: bool) -> float:
    """Runtime Penny schedule plus the delivery charges it omits (CNC only)."""
    base = penny_cnc_costs(entry, exit_price, shares, intraday)
    if intraday:
        return base
    return round(base + entry * shares * CNC_BUY_STT_PCT + CNC_DP_CHARGE_PER_SELL, 4)


def system_cnc_costs(entry: float, exit_price: float, shares: int, intraday: bool) -> float:
    """Runtime SYSTEM (Swing/Range) Zerodha cost schedule."""
    from engine import calc_zerodha_costs
    return float(calc_zerodha_costs(entry, exit_price, shares, is_intraday=intraday))
