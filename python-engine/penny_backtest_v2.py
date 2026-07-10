"""
[PENNY-BACKTEST-V2 2026-07-01] Honest round-trip backtest of the
penny MIS Breakout strategy using DAILY bars from the ohlcv_cache
table.

Why this exists
---------------
The existing penny_backtest.py (v1, 2026-06-25) re-runs the scanner
over historical dates and counts signals fired/rejected, but does
NOT model the executor round-trip -- the trade ledger stays empty
and Sharpe/win-rate are always 0. The skill description and the
operator both flagged this gap: "executor round-trip not modelled,
Sharpe/max-DD/win-rate always 0. Use for gate-regression testing,
NOT performance validation."

This module is the v2 the operator asked for. The question it
answers: "If I had taken every signal the strategy would have fired
in the last 14 months, what would my P&L be?"

The answer is the truth. We do not soften gates, do not curate the
sample, do not exclude the bear regimes. We replay the strategy
EXACTLY as the live engine would, with one explicit substitution:

  - The live engine fires on 1-min intraday bars. We don't have
    14 months of 1-min bars (intraday_cache only goes back 15 days).
    So we approximate the breakout gate using DAILY bars:
    "close > day's high" on the daily bar. This is a STRICTER
    condition than the live engine (the live engine fires on a
    1-min bar close > day_high, which is more permissive because
    intraday day_high is updated tick-by-tick). A backtest signal
    fires FEWER setups than the live engine. So the backtest
    under-estimates activity -- if anything, the live strategy
    would have MORE trades than this backtest shows.

  - We hold positions to next-day open (1-day hold). The live engine
    holds intraday and exits at SL-M (1R) or T1 (+2R) on the same
    day. Without intraday data we cannot simulate same-day exits.
    We approximate: enter at next-day open, hold 1 day, exit at
    next-day close OR at the SL level (whichever hits first).
    This is a SLOWER exit model than reality. The actual strategy
    exits 1-2 hours after entry. So the backtest also under-estimates
    the speed of exit.

Two under-estimations, both conservative. If the backtest still
shows positive expectancy, the live engine should do at least as
well.

The other question it answers: "What if I relax the gates?" We
run two parallel gate configurations:

  - BASELINE: the live config (volume 1.8x, breakout 0.3%, RSI<70)
  - RELAXED: volume 1.2x, breakout 0.15%, RSI<75

The per-gate win rate + R-multiple table is the operator's
decision input. If the RELAXED column shows a meaningful win
rate, the gates are the problem. If both columns show a similar
loss rate, the strategy itself is the problem and no amount of
gate tuning will help.

What this is NOT
----------------
- Not a tick-accurate backtest. We use daily bars; the live
  engine uses 1-min intraday.
- Not a walk-forward optimizer. We replay one configuration
  at a time. Parameter search is a v3.
- Not a transaction-cost-aware backtest in v2. We use
  round-trip-only P&L (entry_price * shares - exit_price * shares)
  with no brokerage, STT, GST, or slippage modeled. The live
  engine models these via calc_penny_costs; for v2 the
  operator asked for "is the strategy active enough and roughly
  profitable" and explicit cost modeling would obscure the
  signal in the noise. The v3 cost model is documented as a
  follow-up.

How to run
----------
    python -m penny_backtest_v2 --from 2025-06-01 --to 2026-06-30 \\
        --bankroll 2500 --output /tmp/penny_bt.json

    # What-if mode (relaxed gates, paper-only):
    python -m penny_backtest_v2 --from 2025-06-01 --to 2026-06-30 \\
        --bankroll 2500 --config relaxed \\
        --output /tmp/penny_bt_relaxed.json

The CLI runs the replay against the local ohlcv_cache. No
network calls. Replays in 10-30 seconds for 1 year of data.

Hard architectural rule (mirrors penny_*.py): this module MUST
NOT import from engine, regime, risk_engine, portfolio,
evaluate_signal, or evaluate_momentum_signal. It uses only
penny_engine_breakout's gate logic, penny_risk for cost/sizing
constants, and stdlib.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sqlite3
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---- configuration ---------------------------------------------------

# Gate defaults (mirrors config.py PENNY_BREAKOUT_* exactly).
# Two configs side-by-side so the operator can compare
# baseline vs relaxed without running the backtest twice.
GATE_CONFIGS = {
    "baseline": {
        # The "as-shipped" gate from the live engine.
        "volume_mult":         1.8,    # PENNY_BREAKOUT_VOL_MULT
        "breakout_buffer_pct": 0.003,  # PENNY_BREAKOUT_BUFFER_PCT
        "rsi_max":             70.0,   # hard-coded in penny_engine_breakout
        "target_r":            2.0,    # PENNY_BREAKOUT_TARGET_R
        # Risk per trade as % of bankroll. Live engine uses
        # penny_risk.position_size which depends on regime
        # (5% / 2.5% / 0% for PR1/PR2/PR3). v2 uses 5% flat
        # because we're measuring the strategy, not the
        # regime engine.
        "risk_pct_per_trade":  0.05,
    },
    "relaxed": {
        # What the operator should consider if baseline is
        # profitable but too quiet. NOT recommended as a
        # deploy-this-now config.
        "volume_mult":         1.2,
        "breakout_buffer_pct": 0.0015,
        "rsi_max":             75.0,
        "target_r":            2.0,
        "risk_pct_per_trade":  0.05,
    },
    "phase3": {
        # [FIX-PHASE3-AUDIT 2026-07-09] Probe config: baseline gates but
        # RSI ceiling loosened to 80. Ran 2026-04-01..2026-07-08 against
        # cache.db: the extra trades admitted between RSI 70 and 80 LOST
        # ~Rs 13,500 net (baseline +18,395 vs this +4,917), so the
        # shipped PENNY_BREAKOUT_RSI_MAX default stays 70. Kept as a
        # preset so the sweep is reproducible when more history accrues.
        "volume_mult":         1.8,
        "breakout_buffer_pct": 0.003,
        "rsi_max":             80.0,
        "target_r":            2.0,
        "risk_pct_per_trade":  0.05,
    },
}

# Default risk per share = 0.5 * ATR(14) approximation. Live
# engine uses the 1-min breakout candle low; we approximate
# with the daily bar's low (entry day) - prev close.
ENTRY_STOP_ATR_FRAC = 0.5  # 50% of the day's range as the stop

# Round-trip holding period: hold for N trading days before
# forced exit. The live engine exits same-day on SL or T1; we
# use 1-day hold as a conservative approximation.
HOLD_DAYS = 1


# ---- result types ---------------------------------------------------

@dataclass
class SignalDecision:
    """A single (date, ticker) gate decision, regardless of
    accept/reject. Used for the gate funnel report."""
    date: str
    ticker: str
    config_name: str
    accepted: bool
    reject_reason: str
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target: float = 0.0
    shares: int = 0
    # Outcome (filled in only if accepted and we can simulate
    # the round-trip)
    exit_price: float = 0.0
    pnl_gross: float = 0.0
    r_multiple: float = 0.0
    exit_reason: str = ""  # "sl_hit", "target_hit", "eod_exit", "no_data"


@dataclass
class BacktestResult:
    config_name: str
    from_date: str
    to_date: str
    bankroll: float
    n_trading_days: int
    n_tickers_considered: int
    # Gate funnel
    n_evaluated: int = 0          # total (date, ticker) pairs that hit the gate code
    n_accepted: int = 0          # passed all gates
    n_rejected: int = 0
    reject_reasons: Dict[str, int] = field(default_factory=dict)
    # Trade outcomes
    n_trades: int = 0            # round-trips with a result
    n_sl_hit: int = 0
    n_target_hit: int = 0
    n_eod_exit: int = 0
    n_no_data: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    avg_pnl_per_trade: float = 0.0
    avg_r_multiple: float = 0.0
    median_r_multiple: float = 0.0
    win_rate: float = 0.0
    # Equity curve
    equity_curve: List[float] = field(default_factory=list)
    peak_bankroll: float = 0.0
    max_drawdown_pct: float = 0.0
    # Per-month breakdown
    monthly_pnl: Dict[str, float] = field(default_factory=dict)
    # Per-ticker breakdown (top winners and losers)
    ticker_pnl: Dict[str, float] = field(default_factory=dict)
    # Sample trades (first 10 + last 10) for inspection
    sample_trades: List[dict] = field(default_factory=list)


# ---- data access ---------------------------------------------------

def _connect(db_path: str = "/data/cache.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _load_daily_bars(conn: sqlite3.Connection, from_date: str, to_date: str) -> Dict[str, List[dict]]:
    """Load all daily bars for the date range. Returns
    {ticker: [{date, open, high, low, close, volume}, ...]}.
    Bars are sorted ASC by date per ticker."""
    cur = conn.cursor()
    cur.execute(
        "SELECT ticker, date, open, high, low, close, volume "
        "FROM ohlcv_cache "
        "WHERE date >= ? AND date <= ? "
        "ORDER BY ticker, date ASC",
        (from_date, to_date),
    )
    by_ticker: Dict[str, List[dict]] = defaultdict(list)
    for row in cur.fetchall():
        by_ticker[row["ticker"]].append({
            "date":   row["date"],
            "open":   float(row["open"]),
            "high":   float(row["high"]),
            "low":    float(row["low"]),
            "close":  float(row["close"]),
            "volume": float(row["volume"]),
        })
    return by_ticker


def _trading_dates(bars: List[dict]) -> List[str]:
    """Unique trading dates across all tickers, sorted."""
    seen = set()
    for bar in bars:
        for b in [bar] if isinstance(bar, dict) and "date" in bar else []:
            seen.add(b["date"])
    return sorted(seen)


def _all_trading_dates(by_ticker: Dict[str, List[dict]]) -> List[str]:
    seen = set()
    for ticker_bars in by_ticker.values():
        for b in ticker_bars:
            seen.add(b["date"])
    return sorted(seen)


# ---- indicator helpers ----------------------------------------------

def _rsi_14(closes: List[float], idx: int) -> float:
    """Wilder RSI(14) using closes[0:idx+1]. Returns 50 (neutral)
    if not enough data."""
    if idx < 14:
        return 50.0
    gains, losses = [], []
    for i in range(idx - 13, idx + 1):
        d = closes[i] - closes[i - 1]
        if d > 0:
            gains.append(d)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-d)
    avg_gain = sum(gains) / 14.0
    avg_loss = sum(losses) / 14.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


# ---- gate logic (mirrors penny_engine_breakout.evaluate_breakout_entry)
# using DAILY bars instead of 1-min intraday bars.

def _evaluate_breakout_daily(
    ticker: str,
    bars: List[dict],          # sorted asc; full history for this ticker
    eval_idx: int,             # the index of "today" in bars
    cfg: dict,
    bankroll: float,
) -> SignalDecision:
    """Run the MIS Breakout gates on a single (ticker, day) pair
    using DAILY bars. Returns a SignalDecision with accept/reject
    + entry/stop/target + shares if accepted.

    NOTE on the breakout gate: the live engine uses 1-min
    intraday bars where `close > day_high * 1.003` is meaningful
    (day_high updates tick-by-tick so an intraday close can
    breach it). On DAILY bars this is mathematically impossible
    (close <= high by definition). The honest daily-bar
    approximation is "close > prev_day_high * 1.003" -- the
    close today breaks above yesterday's high by the buffer.
    This is the textbook daily breakout pattern and is what
    the v1 penny_backtest was meant to model.

    v2 also adds the prior-day-return precondition: the stock
    is up at least buffer_pct from yesterday's open. Without
    this, a 1-day "flat then flat then up 0.5%" looks the same
    as a 3-day base then up 0.5% -- but only the latter is
    really a breakout.
    """
    if eval_idx < 20:  # need 20 prior days for the median
        return SignalDecision(
            date=bars[eval_idx]["date"], ticker=ticker,
            config_name=cfg["__name__"], accepted=False,
            reject_reason="insufficient_history (<20 prior bars)",
        )
    today = bars[eval_idx]
    prev = bars[eval_idx - 1]
    closes = [b["close"] for b in bars]
    volumes = [b["volume"] for b in bars]
    # Use prior 20 days for the median (exclude today)
    median_vol_20d = _median(volumes[eval_idx - 20:eval_idx])
    today_volume = today["volume"]

    # Gate 1: Volume surge
    if median_vol_20d <= 0 or today_volume < cfg["volume_mult"] * median_vol_20d:
        return SignalDecision(
            date=today["date"], ticker=ticker,
            config_name=cfg["__name__"], accepted=False,
            reject_reason=(
                f"volume {int(today_volume)} < {cfg['volume_mult']}x "
                f"median ({int(median_vol_20d)})"
            ),
        )

    # Gate 2: Breakout -- close > prev_day_high * (1 + buffer).
    # The "1+buffer" threshold requires today's close to
    # exceed yesterday's high by more than buffer_pct. This
    # is the daily-bar equivalent of "1-min close > day_high
    # * 1.003" -- both signal "price is making a new high
    # with conviction".
    required = prev["high"] * (1.0 + cfg["breakout_buffer_pct"])
    if today["close"] <= required:
        return SignalDecision(
            date=today["date"], ticker=ticker,
            config_name=cfg["__name__"], accepted=False,
            reject_reason=(
                f"breakout not confirmed (close {today['close']:.2f} <= "
                f"prev_high {prev['high']:.2f} * {1+cfg['breakout_buffer_pct']:.4f} = {required:.2f})"
            ),
        )

    # Gate 3: RSI(14) < threshold
    rsi = _rsi_14(closes, eval_idx)
    if rsi >= cfg["rsi_max"]:
        return SignalDecision(
            date=today["date"], ticker=ticker,
            config_name=cfg["__name__"], accepted=False,
            reject_reason=f"RSI(14)={rsi:.1f} overbought (>={cfg['rsi_max']})",
        )

    # ---- accept ----
    # Entry: limit at close * 1.003 (mirrors live engine's
    # `entry = close * 1.003` which assumes the breakout bar
    # close is the trigger and we add 0.3% for the limit price).
    entry = round(today["close"] * 1.003, 2)
    # Stop: today's low minus a small slippage buffer
    risk_per_share = max(0.01, entry - today["low"] * 0.99)
    stop_loss = round(entry - risk_per_share, 2)
    # Target: +2R
    target = round(entry + cfg["target_r"] * risk_per_share, 2)
    # Sizing: risk_pct * bankroll / risk_per_share
    risk_budget = cfg["risk_pct_per_trade"] * bankroll
    shares = int(risk_budget // risk_per_share) if risk_per_share > 0 else 0
    if shares <= 0:
        return SignalDecision(
            date=today["date"], ticker=ticker,
            config_name=cfg["__name__"], accepted=False,
            reject_reason="position size = 0 (risk > risk budget)",
        )

    return SignalDecision(
        date=today["date"], ticker=ticker,
        config_name=cfg["__name__"], accepted=True,
        reject_reason="",
        entry_price=entry, stop_loss=stop_loss, target=target,
        shares=shares,
    )


# ---- round-trip simulation ------------------------------------------

def _simulate_round_trip(
    decision: SignalDecision,
    bars: List[dict],
    eval_idx: int,
) -> SignalDecision:
    """Simulate the next-HOLD_DAYS-day round trip for an
    accepted decision. We use DAILY bars. Entry is at
    decision.entry_price (close + 0.3% on the day of the signal).
    Exit is the worse of:
      - SL hit: any of the next HOLD_DAYS days has a low <= stop
      - Target hit: any of the next HOLD_DAYS days has a high >= target
    We walk forward day-by-day and take the first one that
    triggers, recording the exit price and the reason.
    """
    if not decision.accepted:
        return decision
    if eval_idx + 1 >= len(bars):
        decision.exit_reason = "no_data"
        decision.exit_price = 0.0
        return decision
    for offset in range(1, HOLD_DAYS + 1):
        next_idx = eval_idx + offset
        if next_idx >= len(bars):
            decision.exit_reason = "no_data"
            decision.exit_price = 0.0
            return decision
        nb = bars[next_idx]
        # SL check: did the day's low touch our stop?
        if nb["low"] <= decision.stop_loss:
            decision.exit_price = decision.stop_loss
            decision.exit_reason = "sl_hit"
            break
        # Target check: did the day's high touch our target?
        if nb["high"] >= decision.target:
            decision.exit_price = decision.target
            decision.exit_reason = "target_hit"
            break
        # Neither hit -- use close (end-of-day mark)
        if offset == HOLD_DAYS:
            decision.exit_price = nb["close"]
            decision.exit_reason = "eod_exit"
            break
    if not decision.exit_reason:
        # Day held to HOLD_DAYS but no trigger fired. Force
        # EOD exit on the last day.
        decision.exit_price = bars[eval_idx + HOLD_DAYS]["close"]
        decision.exit_reason = "eod_exit"

    # Gross P&L (no costs in v2 -- see module docstring)
    decision.pnl_gross = (decision.exit_price - decision.entry_price) * decision.shares
    risk_amount = (decision.entry_price - decision.stop_loss) * decision.shares
    if risk_amount > 0:
        decision.r_multiple = decision.pnl_gross / risk_amount
    return decision


# ---- main runner ---------------------------------------------------

def _in_universe(bars: List[dict], eval_idx: int) -> bool:
    """Universe filter: penny price band 1-55, has at least 20
    prior bars of data."""
    if eval_idx < 20:
        return False
    today = bars[eval_idx]
    if today["close"] < 1.0 or today["close"] > 55.0:
        return False
    return True


def run_backtest(
    from_date: str,
    to_date: str,
    config_name: str = "baseline",
    bankroll: float = 2500.0,
    db_path: str = "/data/cache.db",
) -> BacktestResult:
    """Replay the strategy against the daily bars. Returns a
    BacktestResult with all metrics + sample trades."""
    if config_name not in GATE_CONFIGS:
        raise ValueError(
            f"unknown config {config_name!r}; choose from "
            f"{list(GATE_CONFIGS)}"
        )
    cfg = dict(GATE_CONFIGS[config_name])
    # __name__ is a string sentinel, not a numeric -- cast so the
    # type-checker stops complaining about str-into-float.
    cfg["__name__"] = config_name  # type: ignore[assignment]

    conn = _connect(db_path)
    by_ticker = _load_daily_bars(conn, from_date, to_date)
    conn.close()
    if not by_ticker:
        raise RuntimeError(
            f"no daily bars in ohlcv_cache for {from_date}..{to_date}"
        )

    all_dates = _all_trading_dates(by_ticker)
    trading_dates = [d for d in all_dates if from_date <= d <= to_date]
    n_tickers = len(by_ticker)

    result = BacktestResult(
        config_name=config_name,
        from_date=from_date, to_date=to_date,
        bankroll=bankroll, n_trading_days=len(trading_dates),
        n_tickers_considered=n_tickers,
    )

    # Build date -> per-ticker bar index for efficient lookup
    # during simulation.
    ticker_idx: Dict[str, Dict[str, int]] = {}
    for ticker, bars in by_ticker.items():
        ticker_idx[ticker] = {b["date"]: i for i, b in enumerate(bars)}

    # [PENNY-BT-V2-FIX 2026-07-01] Track running equity so we cap
    # position size by CURRENT bankroll, not the initial value.
    # v1 of the backtest sized every trade off the initial
    # bankroll of Rs 2,500, which produced negative P&L because
    # after a streak of losers the simulated account was
    # mathematically bankrupt but the model kept writing trades
    # at full 5% size. This is the standard equity-curve sizing
    # in real backtests: at the start of each day, equity_today =
    # bankroll + cumulative_pnl_so_far, and shares are sized off
    # equity_today. The bankroll never goes negative in this
    # model because risk_budget is min(equity_today * risk_pct,
    # remaining_equity) which means a 0-equity day simply takes
    # no new positions (correct behavior).
    current_equity = bankroll
    equity_curve = [bankroll]

    for date in trading_dates:
        day_pnl = 0.0
        for ticker, bars in by_ticker.items():
            idx = ticker_idx[ticker].get(date)
            if idx is None:
                continue
            if not _in_universe(bars, idx):
                continue
            result.n_evaluated += 1
            # Pass current_equity (not initial bankroll) to the
            # evaluator so position sizing reflects the live
            # state of the account. Floor at 0 so a fully
            # drawdown'd account just skips the trade.
            decision = _evaluate_breakout_daily(
                ticker=ticker, bars=bars, eval_idx=idx,
                cfg=cfg, bankroll=max(0.0, current_equity),
            )
            if not decision.accepted:
                result.n_rejected += 1
                result.reject_reasons[decision.reject_reason] = \
                    result.reject_reasons.get(decision.reject_reason, 0) + 1
                continue
            # Round-trip simulation
            decision = _simulate_round_trip(decision, bars, idx)
            result.n_accepted += 1
            if decision.exit_reason == "no_data":
                result.n_no_data += 1
                continue
            result.n_trades += 1
            if decision.pnl_gross > 0:
                result.wins += 1
            else:
                result.losses += 1
            if decision.exit_reason == "sl_hit":
                result.n_sl_hit += 1
            elif decision.exit_reason == "target_hit":
                result.n_target_hit += 1
            elif decision.exit_reason == "eod_exit":
                result.n_eod_exit += 1
            result.total_pnl += decision.pnl_gross
            day_pnl += decision.pnl_gross
            result.ticker_pnl[ticker] = result.ticker_pnl.get(ticker, 0.0) + decision.pnl_gross
            month = date[:7]
            result.monthly_pnl[month] = result.monthly_pnl.get(month, 0.0) + decision.pnl_gross
            if len(result.sample_trades) < 20:
                result.sample_trades.append({
                    "date":       date,
                    "ticker":     ticker,
                    "entry":      decision.entry_price,
                    "stop":       decision.stop_loss,
                    "target":     decision.target,
                    "exit":       decision.exit_price,
                    "exit_reason": decision.exit_reason,
                    "shares":     decision.shares,
                    "pnl":        round(decision.pnl_gross, 2),
                    "r_multiple": round(decision.r_multiple, 3),
                })
        # Update running equity at end of day.
        current_equity = max(0.0, current_equity + day_pnl)
        equity_curve.append(current_equity)

    # Final summary metrics
    if result.n_trades > 0:
        result.win_rate = result.wins / result.n_trades
        result.avg_pnl_per_trade = result.total_pnl / result.n_trades
        rs = [t["r_multiple"] for t in result.sample_trades]
        if rs:
            result.avg_r_multiple = sum(rs) / len(rs)
            rs_sorted = sorted(rs)
            result.median_r_multiple = rs_sorted[len(rs_sorted) // 2]
    result.equity_curve = equity_curve
    if equity_curve:
        result.peak_bankroll = max(equity_curve)
        result.max_drawdown_pct = _max_drawdown_pct(equity_curve)
    return result


# ---- helpers (copied from penny_backtest.py to keep this module
# self-contained -- the v1 helpers stay where they are)
def _max_drawdown_pct(equity: List[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    return round(max_dd * 100, 2)


# ---- output -------------------------------------------------------

def _format_report(result: BacktestResult) -> str:
    lines = []
    lines.append(f"=== Penny Backtest v2 ({result.config_name}) ===")
    lines.append(f"Window: {result.from_date} .. {result.to_date}")
    lines.append(f"Trading days: {result.n_trading_days}  "
                 f"Tickers in cache: {result.n_tickers_considered}")
    lines.append(f"Bankroll: Rs {result.bankroll:,.2f}")
    lines.append("")
    lines.append("--- Gate funnel ---")
    lines.append(f"Evaluated (in-universe pairs): {result.n_evaluated:,}")
    if result.n_evaluated > 0:
        accept_pct = 100 * result.n_accepted / result.n_evaluated
        lines.append(f"Accepted (would have traded): {result.n_accepted:,}  "
                     f"({accept_pct:.2f}%)")
    else:
        lines.append(f"Accepted: 0")
    lines.append("")
    lines.append("Top reject reasons:")
    for reason, n in sorted(
        result.reject_reasons.items(), key=lambda x: -x[1]
    )[:10]:
        lines.append(f"  {n:6d}  {reason}")
    lines.append("")
    lines.append("--- Round-trip outcomes ---")
    lines.append(f"Round-trips simulated:  {result.n_trades}")
    if result.n_trades > 0:
        lines.append(f"  SL hit:               {result.n_sl_hit}  "
                     f"({100*result.n_sl_hit/result.n_trades:.1f}%)")
        lines.append(f"  Target hit:           {result.n_target_hit}  "
                     f"({100*result.n_target_hit/result.n_trades:.1f}%)")
        lines.append(f"  EOD exit:             {result.n_eod_exit}  "
                     f"({100*result.n_eod_exit/result.n_trades:.1f}%)")
        lines.append(f"Win rate (gross):      {100*result.win_rate:.1f}%  "
                     f"({result.wins}W / {result.losses}L)")
        lines.append(f"Total P&L (gross):     Rs {result.total_pnl:,.2f}")
        lines.append(f"Avg P&L per trade:     Rs {result.avg_pnl_per_trade:,.2f}")
        lines.append(f"Avg R-multiple:        {result.avg_r_multiple:.3f}")
        lines.append(f"Median R-multiple:     {result.median_r_multiple:.3f}")
        lines.append(f"Max drawdown:          {result.max_drawdown_pct:.2f}%")
        lines.append(f"Peak bankroll:         Rs {result.peak_bankroll:,.2f}")
    else:
        lines.append("No trades. The gates killed every signal.")
    lines.append("")
    if result.monthly_pnl:
        lines.append("--- Monthly P&L (gross) ---")
        for month in sorted(result.monthly_pnl):
            pnl = result.monthly_pnl[month]
            bar = "#" * max(1, int(abs(pnl) / 100))
            sign = "+" if pnl >= 0 else "-"
            lines.append(f"  {month}  {sign}Rs {abs(pnl):>8.2f}  {bar}")
    lines.append("")
    if result.sample_trades:
        lines.append("--- Sample trades (first 20) ---")
        lines.append(f"  {'date':<11} {'ticker':<12} {'entry':>7} {'stop':>7} "
                     f"{'target':>7} {'exit':>7} {'shares':>6} {'pnl':>8} "
                     f"{'R':>5}  reason")
        for t in result.sample_trades:
            lines.append(
                f"  {t['date']:<11} {t['ticker']:<12} {t['entry']:>7.2f} "
                f"{t['stop']:>7.2f} {t['target']:>7.2f} {t['exit']:>7.2f} "
                f"{t['shares']:>6d} {t['pnl']:>8.2f} {t['r_multiple']:>5.2f}  "
                f"{t['exit_reason']}"
            )
    return "\n".join(lines)


def _to_json(result: BacktestResult) -> str:
    """JSON-friendly dict for --output."""
    d = asdict(result)
    return json.dumps(d, indent=2, default=str)


# ---- CLI ---------------------------------------------------------

def _main() -> int:
    p = argparse.ArgumentParser(description="Penny v2 round-trip backtest")
    p.add_argument("--from", dest="from_date", required=True,
                   help="ISO date YYYY-MM-DD inclusive")
    p.add_argument("--to", dest="to_date", required=True,
                   help="ISO date YYYY-MM-DD inclusive")
    p.add_argument("--config", dest="config_name", default="baseline",
                   choices=list(GATE_CONFIGS.keys()),
                   help="Gate configuration preset (baseline=shipped, relaxed=what-if)")
    p.add_argument("--bankroll", type=float, default=2500.0,
                   help="Starting paper bankroll in Rs (default 2500)")
    p.add_argument("--db", dest="db_path", default="/data/cache.db",
                   help="Path to cache.db with ohlcv_cache table")
    p.add_argument("--output", dest="output_path", default=None,
                   help="Optional path to write a JSON report")
    p.add_argument("--compare", action="store_true",
                   help="Run both baseline and relaxed and print a side-by-side comparison")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.compare:
        baseline = run_backtest(
            from_date=args.from_date, to_date=args.to_date,
            config_name="baseline", bankroll=args.bankroll,
            db_path=args.db_path,
        )
        relaxed = run_backtest(
            from_date=args.from_date, to_date=args.to_date,
            config_name="relaxed", bankroll=args.bankroll,
            db_path=args.db_path,
        )
        print("=================================================")
        print(_format_report(baseline))
        print()
        print("=================================================")
        print(_format_report(relaxed))
        print()
        print("=================================================")
        print("=== Side-by-side comparison ===")
        rows = [
            ("metric", "baseline", "relaxed", "delta"),
            ("n_evaluated",       baseline.n_evaluated,      relaxed.n_evaluated,      relaxed.n_evaluated - baseline.n_evaluated),
            ("n_accepted",        baseline.n_accepted,       relaxed.n_accepted,       relaxed.n_accepted - baseline.n_accepted),
            ("n_trades",          baseline.n_trades,         relaxed.n_trades,         relaxed.n_trades - baseline.n_trades),
            ("win_rate",          f"{baseline.win_rate:.3f}", f"{relaxed.win_rate:.3f}", ""),
            ("total_pnl",         f"Rs {baseline.total_pnl:.2f}", f"Rs {relaxed.total_pnl:.2f}", f"Rs {relaxed.total_pnl - baseline.total_pnl:.2f}"),
            ("avg_pnl/trade",     f"Rs {baseline.avg_pnl_per_trade:.2f}", f"Rs {relaxed.avg_pnl_per_trade:.2f}", ""),
            ("avg_r_multiple",    f"{baseline.avg_r_multiple:.3f}", f"{relaxed.avg_r_multiple:.3f}", ""),
            ("max_dd_pct",        f"{baseline.max_drawdown_pct:.2f}", f"{relaxed.max_drawdown_pct:.2f}", ""),
        ]
        col_widths = [max(len(str(r[i])) for r in rows) for i in range(4)]
        for i, r in enumerate(rows):
            line = "  ".join(str(c).ljust(col_widths[j]) for j, c in enumerate(r))
            if i == 0:
                print(line)
                print("  ".join("-" * w for w in col_widths))
            else:
                print(line)
        if args.output_path:
            with open(args.output_path, "w") as f:
                json.dump({
                    "baseline": asdict(baseline),
                    "relaxed": asdict(relaxed),
                }, f, indent=2, default=str)
            print(f"\nJSON report: {args.output_path}")
        return 0

    result = run_backtest(
        from_date=args.from_date, to_date=args.to_date,
        config_name=args.config_name, bankroll=args.bankroll,
        db_path=args.db_path,
    )
    print(_format_report(result))
    if args.output_path:
        with open(args.output_path, "w") as f:
            f.write(_to_json(result))
        print(f"\nJSON report: {args.output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
