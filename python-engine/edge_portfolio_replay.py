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
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import os
import sqlite3
import tempfile

from daily_portfolio import (
    BookConfig, DailySignal, OpenPosition, PortfolioUnavailable, RestingLevel, bars_by_ticker, calendar_from,
    penny_cnc_costs, run_daily_book,
)

EDGE_POLICIES = ("BASELINE", "EDGE_TRADER_V1")
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

    def __post_init__(self):
        if self.policy not in EDGE_POLICIES:
            raise ValueError(f"policy must be one of {EDGE_POLICIES}")
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

        result = run_daily_book(
            bars, calendar, end=end, signals_after_close=signals, policy=policy, costs=penny_cnc_costs,
            config=BookConfig(bankroll=config.bankroll, slippage_bps=config.slippage_bps,
                              entry_drift_pct=config.entry_drift_pct, max_entries_per_day=config.max_positions))
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    return {"scope": "PORTFOLIO_PROXY", "policy": config.policy,
            "config": {**asdict(config), "tickers": list(config.tickers)},
            "clock": "scan_after_D_close; entry_D+1_open_as_0930_proxy; stop_before_target; time_exit_at_close",
            "scans": scans, **result}
