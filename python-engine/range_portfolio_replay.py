"""T2: own-cash Range Reversion portfolio replay and trader candidates (research).

Range Reversion is a SHADOW profile with no shipped daily execution horizon,
so BASELINE declares the most literal lifecycle of the shipped verdict:
``range_reversion_entry`` returns ENTER on day D's completed bar → market buy
at D+1's open, strict stop and mean target from the verdict, time exit at the
close once ``BASELINE_HOLD_SESSIONS`` sessions have passed since entry.

Candidates (declared before scoring; at most two per round):

* ``RANGE_RECLAIM_ENTRY`` — a touch only ARMS a thesis on the frozen range
  (low, mean, stop). Entry needs a stabilization close within
  ``ARM_SESSIONS``: close above the prior close and above the open, with no
  close below the range low since the touch. Exits are BASELINE's.
* ``RANGE_TRADER_V1`` — the same entry plus thesis exits: a close back below
  the range low ends the thesis, a trade that has not covered
  ``MIN_PROGRESS`` of the way to the mean after ``PROGRESS_SESSIONS`` is dead
  money, breakeven locks once half the way is covered, and the hold is capped
  at ``TRADER_MAX_SESSIONS``.

Sizing for every policy: ``RISK_PCT`` of current equity at the verdict stop,
capped at an equal slot (equity / ``settings.MAX_OPEN_POSITIONS``) because
range stops are often well under 1% away and pure risk sizing would ask for
more notional than the book holds. Own cash only, at most that many
concurrent positions, SYSTEM (Zerodha delivery) costs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from daily_portfolio import (
    BookConfig, DailySignal, OpenPosition, RestingLevel, bars_by_ticker, calendar_from, run_daily_book,
    system_cnc_costs,
)

RANGE_POLICIES = ("BASELINE", "RANGE_RECLAIM_ENTRY", "RANGE_TRADER_V1")
RISK_PCT = 0.01
BASELINE_HOLD_SESSIONS = 5
ARM_SESSIONS = 3
PROGRESS_SESSIONS = 3
MIN_PROGRESS = 0.30
BREAKEVEN_PROGRESS = 0.50
TRADER_MAX_SESSIONS = 7


@dataclass(frozen=True)
class RangeReplayConfig:
    tickers: tuple
    calendar_ticker: str = "NIFTY 50"
    bankroll: float = 100000.0
    policy: str = "BASELINE"
    window_size: int = 14
    max_range_pct: float = 0.06
    expansion_limit: float = 1.5
    touch_tolerance_pct: float = 0.005
    strict_stop_epsilon: float = 0.001
    slippage_bps: float = 5.0

    def __post_init__(self):
        if self.policy not in RANGE_POLICIES:
            raise ValueError(f"policy must be one of {RANGE_POLICIES}")
        if not self.tickers:
            raise ValueError("Range replay requires an explicit universe")

    def verdict_kwargs(self) -> dict:
        return {key: getattr(self, key) for key in (
            "window_size", "max_range_pct", "expansion_limit", "touch_tolerance_pct", "strict_stop_epsilon")}


class RangeBaselinePolicy:
    def admit(self, signal, open_price):
        return None

    def resting_levels(self, position: OpenPosition):
        return (RestingLevel(position.signal.target, 1.0, "TARGET_MEAN"),)

    def on_partial(self, position, level):
        pass

    def at_close(self, position, bar, day, session_index):
        if session_index - position.entry_session >= BASELINE_HOLD_SESSIONS:
            return "TIME"
        return None


class RangeTraderPolicy(RangeBaselinePolicy):
    def at_close(self, position, bar, day, session_index):
        signal, held = position.signal, session_index - position.entry_session
        if bar["close"] < signal.context["range_low"]:
            return "THESIS_RANGE_BROKEN"
        distance = signal.target - position.entry_price
        progress = (bar["close"] - position.entry_price) / distance if distance > 0 else 0.0
        if held >= PROGRESS_SESSIONS and progress < MIN_PROGRESS:
            return "THESIS_NO_PROGRESS"
        if held >= TRADER_MAX_SESSIONS:
            return "TIME"
        if progress >= BREAKEVEN_PROGRESS:
            position.stop = max(position.stop, position.entry_price)
        return None


def _signal(ticker: str, day: str, close: float, low: float, mean: float, stop: float,
            equity: float, slots: int, kind: str) -> DailySignal | None:
    if not (0 < stop < close < mean):
        return None
    shares = min(int(equity * RISK_PCT // (close - stop)), int(equity / slots // close))
    if shares < 1:
        return None
    return DailySignal(ticker, day, close, stop, mean, shares, kind,
                       context={"range_low": low, "reward_risk": (mean - close) / (close - stop)})


def run_range_portfolio(rows: list[tuple], *, start: str, end: str, config: RangeReplayConfig) -> dict:
    from config import settings
    from range_reversion import EntrySignal, range_reversion_entry

    bars = bars_by_ticker(rows)
    calendar = calendar_from(bars, config.calendar_ticker, start)
    slots = int(settings.MAX_OPEN_POSITIONS)
    tickers = [t for t in config.tickers if t in bars]
    histories = {t: sorted(bars[t]) for t in tickers}
    positions = {t: {d: i for i, d in enumerate(dates)} for t, dates in histories.items()}
    lookback = config.window_size + 1
    armed: dict[str, dict] = {}
    funnel: dict[str, int] = {}

    def count(key: str) -> None:
        funnel[key] = funnel.get(key, 0) + 1

    def signals(day: str, equity: float) -> list[DailySignal]:
        out = []
        for ticker in tickers:
            today = bars[ticker].get(day)
            if today is None:
                continue
            dates = histories[ticker]
            index = positions[ticker][day]
            history = [bars[ticker][d] for d in dates[max(0, index + 1 - lookback):index + 1]]
            verdict = range_reversion_entry(history, **config.verdict_kwargs())
            touched = verdict.signal == EntrySignal.ENTER
            count("verdict:" + verdict.signal.value)
            if config.policy == "BASELINE":
                if touched:
                    signal = _signal(ticker, day, today["close"], verdict.recent_low, verdict.mean_target,
                                     verdict.strict_stop, equity, slots, "RANGE_TOUCH")
                    if signal:
                        out.append(signal)
                continue
            thesis = armed.get(ticker)
            if thesis is not None:
                thesis["age"] += 1
                if today["close"] < thesis["low"]:
                    count("arm:invalidated_close_below_range")
                    armed.pop(ticker)
                    thesis = None
                elif thesis["age"] > ARM_SESSIONS:
                    count("arm:expired")
                    armed.pop(ticker)
                    thesis = None
            if thesis is None and touched:
                thesis = armed[ticker] = {"low": verdict.recent_low, "mean": verdict.mean_target,
                                          "stop": verdict.strict_stop, "age": 0}
                count("arm:armed")
            if thesis is None or index == 0:
                continue
            previous = bars[ticker][dates[index - 1]]
            if today["close"] > previous["close"] and today["close"] > today["open"]:
                signal = _signal(ticker, day, today["close"], thesis["low"], thesis["mean"], thesis["stop"],
                                 equity, slots, "RANGE_RECLAIM")
                armed.pop(ticker)
                count("arm:entry" if signal else "arm:geometry_spent")
                if signal:
                    out.append(signal)
        out.sort(key=lambda s: (-s.context["reward_risk"], s.ticker))
        return out

    policy = RangeTraderPolicy() if config.policy == "RANGE_TRADER_V1" else RangeBaselinePolicy()
    result = run_daily_book(
        bars, calendar, end=end, signals_after_close=signals, policy=policy, costs=system_cnc_costs,
        config=BookConfig(bankroll=config.bankroll, slippage_bps=config.slippage_bps,
                          max_open_positions=slots))
    return {"scope": "PORTFOLIO_PROXY", "policy": config.policy,
            "config": {**asdict(config), "tickers": list(config.tickers)},
            "clock": "verdict_after_D_close; entry_D+1_open; stop_before_target; time/thesis_exit_at_close",
            "funnel": dict(sorted(funnel.items())), **result}
