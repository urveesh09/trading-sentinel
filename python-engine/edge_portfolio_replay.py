"""R2: causal, own-cash EDGE portfolio replay and the EDGE_TRADER_V1 candidate.

Research only. Signals come from the shipped ``penny_edge_live.scan_today``
over a frozen daily cache; execution, cash and costs come from the shared
``daily_portfolio`` book. Nothing here fetches, orders or edits EDGE runtime.

BASELINE follows the live orchestrator as closely as daily bars allow: market
entry at the next open (09:30 proxy) behind the executor's 2% drift check,
protective stop, resting target, and the 15:15 time exit (close proxy) on the
first session whose calendar age reaches ``PENNY_EDGE_MAX_HOLD_DAYS``.

EDGE_TRADER_V1 treats MR and MO as different theses (declared before scoring):

* MO (momentum continuation) enters only if the next open holds the signal
  close; exits at the close on a giveback below the signal day's midpoint.
* MR (panic-drop bounce) enters only if the next open is above the signal
  day's low; exits at the close if the bounce fails below that low.
* Both lock breakeven after a +1R close and use the subtype hold (sessions
  after entry) within the live calendar cap.

EDGE_OVERNIGHT (October 5, 2026), designed on the seen Jan–Sep 2026 window.
An event study of the shipped candidates found that the return lives overnight:
close→next open averaged +0.90% (+1.98% at strength ≥0.8, positive in each of
the nine months), while next open→next close averaged −0.38%. The shipped clock
buys at that next open, so it misses the move and holds the fade.

This candidate keeps the shipped scan, ranking and sizing, but:

* buys at the signal session's close, the 15:20 CNC order proxy, with adverse
  ``overnight_entry_slippage_bps`` (1-minute data put the 15:20 price 0.07%
  under the close on average);
* sells at the next session's open (the pre-open auction).

There is no stop, because nothing can execute overnight. A missing or
zero-volume next session delays the sale to that ticker's next open.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import os
import sqlite3
import tempfile

from collections import Counter

from daily_portfolio import (
    BookConfig, DailySignal, OpenPosition, PortfolioUnavailable, RestingLevel, _trade_record, bars_by_ticker,
    calendar_from, penny_cnc_costs, penny_cnc_full_costs, run_daily_book, summarize,
)

EDGE_POLICIES = ("BASELINE", "EDGE_TRADER_V1", "EDGE_OVERNIGHT")
COST_MODELS = {"RUNTIME": penny_cnc_costs, "CNC_FULL": penny_cnc_full_costs}
MO_GAP_TOLERANCE = 0.005     # MO open may be at most 0.5% below the signal close
BREAKEVEN_R = 1.0

EdgeReplayUnavailable = PortfolioUnavailable


@dataclass(frozen=True)
class EdgeReplayConfig:
    tickers: tuple
    nifty_ticker: str = "NIFTYBEES"
    bankroll: float = 100000.0
    max_positions: int = 3
    min_strength: float = 0.45
    policy: str = "BASELINE"
    entry_drift_pct: float = 0.02      # penny_executor.MAX_ENTRY_DRIFT_PCT
    slippage_bps: float = 5.0          # penny_edge_orchestrator.EDGE_SLIPPAGE_BPS
    max_hold_days: int = 3             # PENNY_EDGE_MAX_HOLD_DAYS (calendar age)
    cost_model: str = "RUNTIME"        # CNC_FULL adds buy-side STT and DP charges
    overnight_entry_slippage_bps: float = 25.0
    # Capacity: never buy more than this share of the signal day's traded value
    # (penny 15:10-15:25 value can be thin; set from liquidity, not outcomes).
    overnight_max_participation: float = 0.01

    def __post_init__(self):
        if self.policy not in EDGE_POLICIES:
            raise ValueError(f"policy must be one of {EDGE_POLICIES}")
        if self.cost_model not in COST_MODELS:
            raise ValueError(f"cost_model must be one of {tuple(COST_MODELS)}")
        if not self.tickers:
            raise ValueError("EDGE replay requires an explicit universe")
        if not math.isfinite(self.bankroll) or self.bankroll <= 0:
            raise ValueError("bankroll must be positive")


class EdgeBaselinePolicy:
    def __init__(self, max_hold_days: int):
        self.max_hold_days = max_hold_days

    def admit(self, signal: DailySignal, open_price: float) -> str | None:
        return None

    def resting_levels(self, position: OpenPosition):
        return (RestingLevel(position.signal.target, 1.0, "TARGET"),)

    def on_partial(self, position: OpenPosition, level: RestingLevel) -> None:
        pass

    def hold_reached(self, position: OpenPosition, day: str, session_index: int) -> bool:
        return position.age_days(day) >= self.max_hold_days

    def at_close(self, position, bar, day, session_index):
        return "TIME" if self.hold_reached(position, day, session_index) else None


class EdgeTraderPolicy(EdgeBaselinePolicy):
    def admit(self, signal: DailySignal, open_price: float) -> str | None:
        if signal.kind.startswith("MO") and open_price < signal.reference_price * (1 - MO_GAP_TOLERANCE):
            return "THESIS_SKIP_MO_GAP_DOWN"
        if signal.kind.startswith("MR") and open_price <= signal.context["signal_low"]:
            return "THESIS_SKIP_MR_FRESH_BREAKDOWN"
        return None

    def hold_reached(self, position: OpenPosition, day: str, session_index: int) -> bool:
        held = session_index - position.entry_session
        return held >= position.signal.context["hold_days"] or super().hold_reached(position, day, session_index)

    def at_close(self, position, bar, day, session_index):
        kind = position.signal.kind
        if kind.startswith("MR") and bar["close"] < position.signal.context["signal_low"]:
            return "THESIS_MR_BOUNCE_FAILED"
        if kind.startswith("MO") and bar["close"] < position.signal.context["signal_mid"]:
            return "THESIS_MO_GAVE_BACK"
        if self.hold_reached(position, day, session_index):
            return "TIME"
        if bar["close"] >= position.entry_price + BREAKEVEN_R * position.initial_risk_per_share:
            position.stop = max(position.stop, position.entry_price)
        return None


def run_edge_portfolio(rows: list[tuple], *, start: str, end: str, config: EdgeReplayConfig) -> dict:
    from penny_edge_live import scan_today

    bars = bars_by_ticker(rows)
    missing = sorted({config.nifty_ticker, *config.tickers} - set(bars))
    if missing:
        raise PortfolioUnavailable("missing required daily history: " + ", ".join(missing))
    calendar = calendar_from(bars, config.nifty_ticker, start)
    costs = COST_MODELS[config.cost_model]
    policy = (EdgeTraderPolicy if config.policy == "EDGE_TRADER_V1" else EdgeBaselinePolicy)(config.max_hold_days)
    fd, path = tempfile.mkstemp(prefix="sentinel-edge-portfolio-", suffix=".sqlite")
    os.close(fd)
    scans = 0
    try:
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE ohlcv_cache (ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
        conn.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)", rows)
        conn.commit()
        conn.close()

        def signals(day: str, equity: float) -> list[DailySignal]:
            nonlocal scans
            scans += 1
            scan = scan_today(bankroll=equity, max_positions=config.max_positions, min_strength=config.min_strength,
                              db_path=path, as_of_date=day, nifty_ticker=config.nifty_ticker)
            out = []
            for candidate in scan["positions"]:
                bar = bars[candidate.ticker].get(day)
                if bar is None:
                    continue
                out.append(DailySignal(
                    candidate.ticker, day, candidate.entry_price, candidate.stop_loss, candidate.target,
                    candidate.shares, candidate.signal_subtype,
                    context={"signal_low": bar["low"], "signal_mid": (bar["open"] + bar["close"]) / 2,
                             "hold_days": candidate.hold_days,
                             "adjusted_strength": round(candidate.adjusted_strength, 6)}))
            return out

        if config.policy == "EDGE_OVERNIGHT":
            result = run_overnight_book(bars, calendar, end=end, signals_at_close=signals, config=config, costs=costs)
        else:
            result = run_daily_book(
                bars, calendar, end=end, signals_after_close=signals, policy=policy, costs=costs,
                config=BookConfig(bankroll=config.bankroll, slippage_bps=config.slippage_bps,
                                  entry_drift_pct=config.entry_drift_pct, max_entries_per_day=config.max_positions))
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    clock = ("scan_at_D_close; entry_D_close_as_1520_proxy; exit_next_session_open" if config.policy == "EDGE_OVERNIGHT"
             else "scan_after_D_close; entry_D+1_open_as_0930_proxy; stop_before_target; time_exit_at_close")
    return {"scope": "PORTFOLIO_PROXY", "policy": config.policy,
            "config": {**asdict(config), "tickers": list(config.tickers)},
            "clock": clock, "scans": scans, **result}


def run_overnight_book(bars, calendar, *, end: str, signals_at_close, config: EdgeReplayConfig, costs,
                       min_fill_fraction: float = 0.25, buy_cost_buffer: float = 0.002) -> dict:
    """Own-cash book: buy at session D's close, sell at the ticker's next open."""
    if not [day for day in calendar if day <= end]:
        raise PortfolioUnavailable("no sessions in requested window")
    entry_slip, exit_slip = config.overnight_entry_slippage_bps / 10000.0, config.slippage_bps / 10000.0
    cash, realized, capital_days = config.bankroll, 0.0, 0.0
    held: dict[str, OpenPosition] = {}
    trades: list[dict] = []
    outcomes: Counter = Counter()
    curve: list[tuple[str, float]] = []
    for session_index, day in enumerate(calendar):
        # 1. The opening auction sells everything held from an earlier close.
        for ticker in sorted(held):
            position, bar = held[ticker], bars.get(ticker, {}).get(day)
            if bar is None or bar["volume"] <= 0:
                position.state["delayed"] = True
                continue
            exit_price = bar["open"] * (1 - exit_slip)
            cost = costs(position.entry_price, exit_price, position.shares, False)
            net = (exit_price - position.entry_price) * position.shares - cost
            cash += exit_price * position.shares - cost
            realized += net
            reason = "OPEN_DELAYED" if position.state.get("delayed") else "NEXT_OPEN"
            position.shares_open = 0
            position.partial_fills.append({"date": day, "price": exit_price, "quantity": position.shares,
                                           "reason": reason, "net_pnl": net, "costs": cost})
            del held[ticker]
            trades.append(_trade_record(position, "CLOSED", reason))
        # 2. Close-time entries, only while the window is open.
        if day <= end:
            entered = 0
            for signal in signals_at_close(day, config.bankroll + realized):
                if entered >= config.max_positions:
                    outcomes["DAILY_ENTRY_CAP"] += 1
                    continue
                if signal.ticker in held:
                    outcomes["ALREADY_HELD"] += 1
                    continue
                bar = bars.get(signal.ticker, {}).get(day)
                if bar is None or bar["volume"] <= 0:
                    outcomes["NO_FILL_MISSING_OR_ZERO_VOLUME_SESSION"] += 1
                    continue
                entry_price = bar["close"] * (1 + entry_slip)
                if signal.stop >= entry_price:
                    outcomes["STOP_ALREADY_BREACHED"] += 1
                    continue
                capacity = int(config.overnight_max_participation * bar["close"] * bar["volume"] // entry_price)
                if capacity < min_fill_fraction * signal.planned_shares:
                    outcomes["LIQUIDITY_REJECTED"] += 1
                    continue
                shares = min(signal.planned_shares, capacity)
                if shares < signal.planned_shares:
                    outcomes["LIQUIDITY_LIMITED_RESIZE"] += 1
                affordable = int(cash // (entry_price * (1 + buy_cost_buffer)))
                if affordable < shares:
                    if affordable < min_fill_fraction * shares:
                        outcomes["CASH_REJECTED_DUST"] += 1
                        continue
                    outcomes["CASH_LIMITED_RESIZE"] += 1
                    shares = affordable
                cash -= entry_price * shares
                entered += 1
                outcomes["FILLED"] += 1
                held[signal.ticker] = OpenPosition(signal, day, session_index, entry_price, shares, signal.stop)
        marked = cash
        for ticker, position in held.items():
            last = bars.get(ticker, {}).get(day)
            marked += (last["close"] if last else position.entry_price) * position.shares
            capital_days += position.entry_price * position.shares
        curve.append((day, round(marked, 4)))
        if day > end and not held:
            break
    for ticker, position in sorted(held.items()):
        last_day = max(d for d in bars[ticker] if d <= calendar[-1])
        record = _trade_record(position, "OPEN_MARKED", None)
        record.update(mark_date=last_day, mark_price=bars[ticker][last_day]["close"])
        trades.append(record)
    return {"trades": trades, "admission_outcomes": dict(sorted((k, v) for k, v in outcomes.items() if v)),
            "summary": summarize(trades, curve, config.bankroll, capital_days), "equity_curve": curve}
