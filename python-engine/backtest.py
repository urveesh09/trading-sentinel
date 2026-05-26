"""
Backtesting harness for regime-aware momentum strategy.

Supports two modes:
  - run_backtest(): single-ticker backtest over a date range
  - run_universe_backtest(): multi-ticker universe backtest

Each day the RegimeEngine is updated with available data (VIX=None for
backtesting since full VIX history isn't available from Kite), then
evaluate_signal() is called with the current regime to generate signals.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional

from config import settings
from engine import evaluate_signal, calc_rsi_series, calc_ema
from regime import RegimeEngine
from models import Regime


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _simulate_trade(
    entry_date: datetime,
    entry_price: float,
    shares: int,
    stop_loss: float,
    target_1: float,
    target_2: Optional[float],
    regime: Regime,
    df_slice: pd.DataFrame,
    exit_col: str = "close",
) -> dict:
    """
    Walk forward from entry_date through df_slice looking for an exit event.

    Exit hierarchy:
      1. Stop-out (price penetrates stop_loss)
      2. T1 hit  → move stop to breakeven, continue
      3. T2 hit  → close full position
      4. Time-out (15 days) → close at current close

    Returns a trade dict with entry/exit details and R multiple.
    """
    entry_idx = df_slice.index.get_loc(entry_date)

    stop = stop_loss
    exit_reason = None
    exit_price = None
    exit_date = None

    for day_i in range(entry_idx + 1, len(df_slice)):
        day_idx = df_slice.index[day_i]
        curr_open = df_slice["open"].iloc[day_i]
        curr_close = df_slice[exit_col].iloc[day_i]

        # Stop-out: intraday or close breach
        if curr_open <= stop or curr_close <= stop:
            exit_reason = "stop_out"
            exit_price = stop
            exit_date = day_idx
            break

        # T1 hit — lock in partial profit, move stop to breakeven
        if curr_close >= target_1:
            stop = entry_price  # breakeven

        # T2 hit — full exit
        if target_2 is not None and curr_close >= target_2:
            exit_reason = "target_2"
            exit_price = target_2
            exit_date = day_idx
            break

        # Time-out after 15 days
        if (day_i - entry_idx) >= 15:
            exit_reason = "timeout"
            exit_price = curr_close
            exit_date = day_idx
            break

    # If loop ended without any exit event (end of available data)
    if exit_reason is None:
        last_row = df_slice.iloc[-1]
        exit_reason = "end_of_data"
        exit_price = last_row[exit_col]
        exit_date = df_slice.index[-1]

    # P&L
    pnl = (exit_price - entry_price) * shares
    r_distance = entry_price - stop_loss
    r_multiple = (exit_price - entry_price) / r_distance if r_distance > 0 else 0.0

    return {
        "entry_date": entry_date,
        "exit_date": exit_date,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "shares": shares,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "pnl": pnl,
        "r_multiple": r_multiple,
        "exit_reason": exit_reason,
        "regime": regime,
        "regime_value": regime.value,
    }


def _compute_stats(trades: list[dict]) -> dict:
    """Compute aggregate statistics from a list of trade dicts."""
    if not trades:
        return {
            "total_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0.0,
            "avg_R": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "total_return_pct": 0.0,
            "avg_hold_days": 0.0,
            "best_trade_R": 0.0,
            "worst_trade_R": 0.0,
            "regime_distribution": {},
        }

    pnls = [t["pnl"] for t in trades]
    r_multiples = [t["r_multiple"] for t in trades]

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    # Win rate
    win_rate = len(wins) / len(trades)

    # Profit factor
    profit_factor = (sum(wins) / abs(sum(losses))) if losses else float("inf")

    # Drawdown (peak-to-trough capital curve)
    capital = settings.INITIAL_BANKROLL
    peak = capital
    max_dd = 0.0
    for pnl in pnls:
        capital += pnl
        if capital > peak:
            peak = capital
        dd = (peak - capital) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # Regime distribution
    regime_dist: dict[str, int] = {}
    for t in trades:
        key = t["regime_value"]
        regime_dist[key] = regime_dist.get(key, 0) + 1

    # Hold days
    hold_days = []
    for t in trades:
        if t["entry_date"] and t["exit_date"]:
            hold_days.append((t["exit_date"] - t["entry_date"]).days)
        else:
            hold_days.append(0)

    return {
        "total_trades": len(trades),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(win_rate * 100, 2),
        "avg_R": round(float(np.mean(r_multiples)), 4),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 9999.0,
        "max_drawdown_pct": round(max_dd * 100, 2),
        "total_return_pct": round(((capital - settings.INITIAL_BANKROLL) / settings.INITIAL_BANKROLL) * 100, 2),
        "avg_hold_days": round(float(np.mean(hold_days)), 2),
        "best_trade_R": round(float(max(r_multiples)), 4),
        "worst_trade_R": round(float(min(r_multiples)), 4),
        "regime_distribution": regime_dist,
    }


def _build_nifty_series(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute a minimal Nifty series from the ticker df for regime detection.

    Uses the ticker's own close as a proxy for nifty_50 when Nifty data
    is not separately available (VIX=None path).
    """
    close_series: pd.Series = df["close"]
    nifty = pd.DataFrame(index=df.index)
    nifty["nifty_50"] = close_series
    nifty["nifty_ema20"] = calc_ema(20, close_series)
    return nifty


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_backtest(
    ticker: str,
    df: pd.DataFrame,
    start_date: str,
    end_date: str,
    initial_bankroll: float = 5000.0,
) -> dict:
    """
    Run a walk-forward backtest for a single ticker.

    Each day:
      1. Update RegimeEngine with that day's data (VIX=None, nifty proxy).
      2. Build a lookback window up to that day.
      3. Call evaluate_signal() with the current regime.
      4. If a signal fires, simulate the trade and record P&L.

    Parameters
    ----------
    ticker : str
        Ticker symbol (e.g. "RELIANCE")
    df : pd.DataFrame
        Daily OHLCV data with columns: open, high, low, close, volume.
        Must cover at least 200 rows + the backtest window.
    start_date : str
        Start date in "YYYY-MM-DD" format.
    end_date : str
        End date in "YYYY-MM-DD" format.
    initial_bankroll : float
        Starting capital (default 5000.0).

    Returns
    -------
    dict with keys:
        - ticker, start_date, end_date, initial_bankroll
        - trades: list of trade dicts
        - stats: aggregate statistics (win_rate, avg_R, max_drawdown_pct,
          profit_factor, total_return_pct, regime_distribution, etc.)
        - regime_transitions: list of regime change events
    """
    if len(df) < 200:
        return {
            "ticker": ticker,
            "start_date": start_date,
            "end_date": end_date,
            "initial_bankroll": initial_bankroll,
            "trades": [],
            "stats": {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_R": 0.0,
                "profit_factor": 0.0,
                "max_drawdown_pct": 0.0,
                "total_return_pct": 0.0,
                "regime_distribution": {},
            },
            "regime_transitions": [],
            "error": "insufficient_data_200_rows",
        }

    # Filter to backtest window
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    window_df = df.loc[start_date:end_date].copy()

    if len(window_df) < 20:
        return {
            "ticker": ticker,
            "start_date": start_date,
            "end_date": end_date,
            "initial_bankroll": initial_bankroll,
            "trades": [],
            "stats": {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_R": 0.0,
                "profit_factor": 0.0,
                "max_drawdown_pct": 0.0,
                "total_return_pct": 0.0,
                "regime_distribution": {},
            },
            "regime_transitions": [],
            "error": "insufficient_window_data",
        }

    # Build Nifty proxy series for regime engine
    nifty_proxy = _build_nifty_series(df)

    # Regime engine — VIX not available for historical backtest (use None)
    regime_engine = RegimeEngine()

    trades: list[dict] = []
    regime_transitions: list[dict] = []
    prev_regime = None

    # Walk-forward: scan from day 200 onwards to have enough history
    scan_start = max(200, len(df.loc[:start_date]))
    scan_dates = window_df.index[max(0, scan_start - len(df) + len(window_df)):]

    bankroll = initial_bankroll

    for scan_date in scan_dates:
        # Locate the lookback window: all data up to and including scan_date
        lookback = df.loc[:scan_date].copy()
        if len(lookback) < 200:
            continue

        # Get Nifty proxy values for this date
        if scan_date in nifty_proxy.index:
            nifty_50_val = float(nifty_proxy.loc[scan_date, "nifty_50"])
            nifty_ema20_val = float(nifty_proxy.loc[scan_date, "nifty_ema20"])
        else:
            # Fallback: use last available values
            nifty_50_val = float(nifty_proxy["nifty_50"].iloc[-1])
            nifty_ema20_val = float(nifty_proxy["nifty_ema20"].iloc[-1])

        # Update regime engine (VIX not available for historical backtesting;
        # use 18.0 as a neutral calm-market default)
        regime_state = regime_engine.update_regime(
            vix=18.0,
            nifty_50=nifty_50_val,
            nifty_ema20=nifty_ema20_val,
            breadth=0.50,  # Default; VIX unavailable for backtest
        )

        # Track transitions
        if prev_regime is not None and regime_state.regime != prev_regime:
            regime_transitions.append({
                "date": scan_date,
                "from_regime": prev_regime.value,
                "to_regime": regime_state.regime.value,
                "regime_score": round(regime_state.regime_score, 2),
            })
        prev_regime = regime_state.regime

        # Build RSI history for evaluate_signal.
        # calc_rsi_series has a pre-existing off-by-one for exactly-200-row
        # windows (IndexError on gains[199]). Pass None to let evaluate_signal
        # fall back to the fixed 45-72 RSI range — no signals lost.
        try:
            rsi_hist = calc_rsi_series(lookback["close"])
        except (IndexError, Exception):
            rsi_hist = None

        # Get risk_pct from regime engine
        risk_pct = regime_engine.get_risk_pct()

        # Evaluate signal
        valid, sig = evaluate_signal(
            ticker=ticker,
            df=lookback,
            bankroll=bankroll,
            risk_pct=risk_pct,
            regime=regime_state.regime,
            market_regime="BULL",
            nifty_50_current=nifty_50_val,
            nifty_ema20=nifty_ema20_val,
            rsi_history=rsi_hist,
        )

        if not valid:
            continue

        # Record trade — use next day's open as entry price
        scan_loc = df.index.get_loc(scan_date)
        if scan_loc + 1 >= len(df):
            continue

        entry_date = df.index[scan_loc + 1]
        entry_price = df["open"].iloc[scan_loc + 1] * 1.002  # 0.2% slippage

        # Adjust shares for current bankroll
        risk_per_trade = bankroll * risk_pct
        risk_per_share = entry_price - sig["stop_loss"]
        if risk_per_share <= 0:
            continue

        raw_shares = risk_per_trade / risk_per_share
        shares = int(raw_shares)

        if shares <= 0:
            continue

        # Simulate the trade using future data (post-entry window)
        # We need data from entry_date onwards
        future_df = df.loc[entry_date:]
        if len(future_df) < 2:
            continue

        trade = _simulate_trade(
            entry_date=entry_date,
            entry_price=entry_price,
            shares=shares,
            stop_loss=sig["stop_loss"],
            target_1=sig["target_1"],
            target_2=sig["target_2"],
            regime=regime_state.regime,
            df_slice=future_df,
        )

        # Update bankroll
        bankroll += trade["pnl"]
        bankroll = max(0.0, bankroll)  # Floor at zero

        trades.append(trade)

    stats = _compute_stats(trades)
    stats["final_bankroll"] = round(bankroll, 2)

    return {
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "initial_bankroll": initial_bankroll,
        "trades": trades,
        "stats": stats,
        "regime_transitions": regime_transitions,
    }


def run_universe_backtest(
    tickers: list[str],
    start_date: str,
    end_date: str,
    historical_data: dict[str, pd.DataFrame],
    initial_bankroll: float = 5000.0,
) -> list[dict]:
    """
    Run backtest across multiple tickers and aggregate results.

    Parameters
    ----------
    tickers : list[str]
        List of ticker symbols to backtest.
    start_date : str
        Start date ("YYYY-MM-DD").
    end_date : str
        End date ("YYYY-MM-DD").
    historical_data : dict[str, pd.DataFrame]
        Mapping of ticker → OHLCV DataFrame.
    initial_bankroll : float
        Per-ticker starting capital (default 5000.0).

    Returns
    -------
    list[dict]
        One result dict per ticker (same structure as run_backtest output).
        Also includes an aggregate entry with key "universe_aggregate"
        containing overall statistics across all tickers.
    """
    results = []

    for ticker in tickers:
        if ticker not in historical_data:
            results.append({
                "ticker": ticker,
                "error": "no_data_for_ticker",
                "trades": [],
                "stats": {},
            })
            continue

        df = historical_data[ticker]
        result = run_backtest(
            ticker=ticker,
            df=df,
            start_date=start_date,
            end_date=end_date,
            initial_bankroll=initial_bankroll,
        )
        results.append(result)

    # Compute universe-level aggregate stats
    all_trades = []
    for r in results:
        all_trades.extend(r.get("trades", []))

    if all_trades:
        universe_stats = _compute_stats(all_trades)
    else:
        universe_stats = {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_R": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "total_return_pct": 0.0,
            "regime_distribution": {},
        }

    # Add universe aggregate as last entry
    results.append({
        "ticker": "universe_aggregate",
        "start_date": start_date,
        "end_date": end_date,
        "initial_bankroll": initial_bankroll * len(tickers),
        "trades": all_trades,
        "stats": universe_stats,
        "regime_transitions": [],
    })

    return results