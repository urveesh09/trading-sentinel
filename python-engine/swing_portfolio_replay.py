"""T2: own-cash Swing portfolio replay and trader candidates (research only).

Signals are the shipped ``engine.evaluate_signal`` decisions from
``SwingDecisionClock`` (one before-open regime update per session, bars
strictly before the decision session). Execution, cash and costs come from the
shared ``daily_portfolio`` book; Swing's manual EXEC is modelled as a market
buy at the decision session's open.

BASELINE mirrors the daily position tracker's exits, with two declared,
conservative differences: a stop and a target touched on the same daily bar
resolve stop-first (the tracker books the target), and the Chandelier trail is
raised at the close and applies from the next bar (the tracker raises it with
today's close and then tests today's low against it).

* T1: half (at least one share) at ``target_1``, then stop to breakeven.
* T2: the rest at ``target_2`` (capped at entry + 5R in Regime 1).
* Trail: highest close since entry − regime multiple × ATR at entry.
* Time: close once the calendar age reaches 15 days.

Candidates (declared before scoring):

* ``SWING_PULLBACK_ENTRY`` — an extended signal (close more than
  ``EXTENSION_ATR`` ATR above EMA21) rests a limit at
  max(EMA21, close − ``PULLBACK_ATR`` × ATR) for ``PULLBACK_SESSIONS``
  sessions instead of chasing; unextended signals buy at the open. Exits are
  BASELINE's.
* ``SWING_TRADER_V1`` — the same entry; winners are not halved at T1:
  breakeven locks after a +1R close and the Chandelier trail plus T2 manage the
  run; a trend thesis ends after ``TREND_BREAK_CLOSES`` consecutive closes
  below the (causally updated) EMA21.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date

from daily_portfolio import (
    BookConfig, DailySignal, OpenPosition, RestingLevel, bars_by_ticker, calendar_from, run_daily_book,
    system_cnc_costs,
)

SWING_POLICIES = ("BASELINE", "SWING_PULLBACK_ENTRY", "SWING_TRADER_V1")
MAX_HOLD_DAYS = 15
EXTENSION_ATR = 1.0
PULLBACK_ATR = 1.0
PULLBACK_SESSIONS = 3
TREND_BREAK_CLOSES = 2
EMA_ALPHA = 2 / (21 + 1)


@dataclass(frozen=True)
class SwingReplayConfig:
    tickers: tuple
    nifty_ticker: str = "NIFTY 50"
    banknifty_ticker: str = "NIFTY BANK"
    bankroll: float = 4500.0
    policy: str = "BASELINE"
    slippage_bps: float = 5.0

    def __post_init__(self):
        if self.policy not in SWING_POLICIES:
            raise ValueError(f"policy must be one of {SWING_POLICIES}")
        if not self.tickers:
            raise ValueError("Swing replay requires an explicit universe")


def _chandelier_multiple(regime: str) -> float:
    from config import settings
    return {
        "REGIME_1_NORMAL": settings.CHANDELIER_ATR_REGIME1_MULT,
        "REGIME_2_ELEVATED": settings.CHANDELIER_ATR_REGIME2_MULT,
        "REGIME_3_CRISIS": settings.CHANDELIER_ATR_REGIME3_MULT,
    }.get(regime, settings.CHANDELIER_ATR_MULT)


def _target_2(position: OpenPosition) -> float:
    from config import settings
    signal = position.signal
    target = signal.context["target_2"]
    if signal.context["regime"] == "REGIME_1_NORMAL":
        target = min(target, position.entry_price + settings.HARD_CAP_R_REGIME1 * position.initial_risk_per_share)
    return target


class SwingBaselinePolicy:
    def admit(self, signal, open_price):
        return None

    def resting_levels(self, position: OpenPosition):
        levels = [RestingLevel(_target_2(position), 1.0, "TARGET_2")]
        if not position.state.get("t1_done"):
            levels.append(RestingLevel(position.signal.context["target_1"], 0.5, "TARGET_1_HALF"))
        return levels

    def on_partial(self, position: OpenPosition, level: RestingLevel) -> None:
        position.state["t1_done"] = True
        position.stop = max(position.stop, position.entry_price)

    def _trail(self, position: OpenPosition, close: float) -> None:
        highest = max(position.state.get("highest_close", position.entry_price), close)
        position.state["highest_close"] = highest
        context = position.signal.context
        position.stop = max(position.stop, highest - _chandelier_multiple(context["regime"]) * context["atr"])

    def at_close(self, position, bar, day, session_index):
        if position.age_days(day) >= MAX_HOLD_DAYS:
            return "TIME"
        self._trail(position, bar["close"])
        return None


class SwingTraderPolicy(SwingBaselinePolicy):
    def resting_levels(self, position: OpenPosition):
        return (RestingLevel(_target_2(position), 1.0, "TARGET_2"),)

    def at_close(self, position, bar, day, session_index):
        ema = position.state.get("ema21", position.signal.context["ema_21"])
        ema += EMA_ALPHA * (bar["close"] - ema)
        position.state["ema21"] = ema
        below = position.state.get("closes_below_ema", 0) + 1 if bar["close"] < ema else 0
        position.state["closes_below_ema"] = below
        if below >= TREND_BREAK_CLOSES:
            return "THESIS_TREND_BROKEN"
        if position.age_days(day) >= MAX_HOLD_DAYS:
            return "TIME"
        if bar["close"] >= position.entry_price + position.initial_risk_per_share:
            position.stop = max(position.stop, position.entry_price)
        self._trail(position, bar["close"])
        return None


def _entry_limit(detail: dict, policy: str) -> float | None:
    if policy == "BASELINE":
        return None
    close, ema, atr = float(detail["close"]), float(detail["ema_21"]), float(detail["atr_14"])
    if close - ema <= EXTENSION_ATR * atr:
        return None
    return max(ema, close - PULLBACK_ATR * atr)


def run_swing_portfolio(rows: list[tuple], *, start: str, end: str, config: SwingReplayConfig) -> dict:
    from config import settings
    from research_daily_decision_replay import SwingDecisionClock, _by_ticker

    bars = bars_by_ticker(rows)
    clock = SwingDecisionClock(_by_ticker(rows), tickers=tuple(config.tickers), nifty_ticker=config.nifty_ticker,
                               banknifty_ticker=config.banknifty_ticker, bankroll=config.bankroll)
    calendar = calendar_from(bars, config.nifty_ticker, start)
    next_session = dict(zip(calendar, calendar[1:]))
    skips: Counter = Counter()
    fired_total = 0

    def signals(day: str, equity: float) -> list[DailySignal]:
        nonlocal fired_total
        out = []
        for row in clock.decide(date.fromisoformat(next_session[day]), skips, bankroll=equity):
            if not row["fired"]:
                continue
            fired_total += 1
            detail = row["detail"]
            limit = _entry_limit(detail, config.policy)
            try:
                out.append(DailySignal(
                    row["ticker"], day, float(detail["close"]), float(detail["stop_loss"]),
                    float(detail["target_1"]), int(detail["shares"]),
                    "SWING_PULLBACK" if limit is not None else "SWING_MARKET",
                    entry_limit=limit, entry_valid_sessions=PULLBACK_SESSIONS if limit is not None else 1,
                    context={"target_1": float(detail["target_1"]), "target_2": float(detail["target_2"]),
                             "atr": float(detail["atr_14"]), "ema_21": float(detail["ema_21"]),
                             "regime": row["regime"], "score": detail.get("score", 0)}))
            except ValueError:
                skips["invalid_signal_geometry"] += 1
        out.sort(key=lambda s: (-float(s.context["score"] or 0), s.ticker))
        return out

    policy = SwingTraderPolicy() if config.policy == "SWING_TRADER_V1" else SwingBaselinePolicy()
    # The signal target is T1 for the book's entry geometry check; resting levels own exits.
    result = run_daily_book(
        bars, calendar, end=end, signals_after_close=signals, policy=policy, costs=system_cnc_costs,
        config=BookConfig(bankroll=config.bankroll, slippage_bps=config.slippage_bps,
                          max_open_positions=int(settings.MAX_OPEN_POSITIONS)))
    return {"scope": "PORTFOLIO_PROXY", "policy": config.policy,
            "config": {**asdict(config), "tickers": list(config.tickers)},
            "clock": "decision_before_open_from_prior_bars; market_or_resting_limit_entry; stop_before_targets",
            "fired_signals": fired_total, "skips": dict(sorted(skips.items())), **result}
