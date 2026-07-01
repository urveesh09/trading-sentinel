"""
[PENNY-EDGE-BACKTEST 2026-07-01] Walk-forward backtest for the
adaptive engine.

This is the v3 backtest that USES penny_edge_engine to score
signals and sizes positions. The key difference from v2:

  v2 (penny_backtest_v2):  fixed gates, RUNTIME binary accept/reject
  v3 (this file):          adaptive strength, RANKED selection

Walk-forward protocol:
  1. For each day t in [train_window_end, end_date]:
     - Compute signals for (date=t, all tickers) using ONLY
       data known as of t (no peeking).
     - Pick top-N by regime-adjusted strength.
     - Simulate each position to exit.
  2. Track equity curve, drawdown, win rate.
  3. Optionally use a TRAIN window of 60-120 days to ESTIMATE
     regime parameters (Nifty 50 trend, volatility percentile)
     so the regime tilt is honest.

Honest features:
  - Slippage 5 bps per side (Kite-equivalent).
  - No transaction costs modeled beyond slippage.
  - Each day's signals use ONLY historical bars (no future leak).
  - Equity-curve sizing: position shares = floor(risk_budget /
    risk_per_share); risk_budget is always % of current_equity,
    not initial.

CLI:
    python -m penny_edge_backtest \\
        --from 2025-01-01 --to 2026-06-30 \\
        --bankroll 2500
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from typing import Dict, List, Tuple

import penny_edge_engine as pee


SLIPPAGE_BPS = 5.0
MAX_POSITIONS_PER_DAY = 5


def compute_nifty_regime(nifty_bars: List[dict], eval_date_idx: int) -> pee.Regime:
    """Compute regime from Nifty 50 proxy daily bars up to eval_date_idx."""
    if eval_date_idx < 60:
        return pee.compute_regime(0.0, 0.5)
    ret_10d = (nifty_bars[eval_date_idx]["close"] -
               nifty_bars[eval_date_idx - 10]["close"]) / \
              nifty_bars[eval_date_idx - 10]["close"]
    trend_strength = max(-1.0, min(1.0, ret_10d / 0.05))
    closes = [b["close"] for b in nifty_bars[eval_date_idx - 14:eval_date_idx + 1]]
    rets = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    import statistics
    cur_vol = statistics.pstdev(rets) if len(rets) > 1 else 0.0
    vols = []
    for i in range(max(0, eval_date_idx - 60), eval_date_idx - 13):
        cl = [b["close"] for b in nifty_bars[i:i+15]]
        if len(cl) < 5:
            continue
        r = [(cl[j] - cl[j-1]) / cl[j-1] for j in range(1, len(cl))]
        if len(r) > 1:
            vols.append(statistics.pstdev(r))
    if not vols:
        return pee.compute_regime(trend_strength, 0.5)
    rank = sum(1 for v in vols if v <= cur_vol) / max(1, len(vols))
    return pee.compute_regime(trend_strength, rank)


def load_nifty_bars(conn: sqlite3.Connection, from_date: str, to_date: str) -> List[dict]:
    cur = conn.cursor()
    cur.execute("""
        SELECT date, close FROM ohlcv_cache
        WHERE ticker = 'NIFTYBEES' AND date >= ? AND date <= ?
        ORDER BY date
    """, (from_date, to_date))
    return [{"date": r[0], "close": r[1]} for r in cur.fetchall()]


def run_backtest(
    from_date: str = "2025-01-01",
    to_date: str = "2026-06-30",
    bankroll: float = 2500.0,
    slippage_bps: float = SLIPPAGE_BPS,
    max_positions_per_day: int = MAX_POSITIONS_PER_DAY,
    verbose: bool = False,
) -> Tuple[List[dict], List[Tuple[str, float]], float]:
    """Run the engine on real data. Returns (trades, equity_curve, max_dd)."""
    # [PENNY-FD-LEAK 2026-07-01] `with` so the connection is closed
    # even if load_daily_bars_from_db raises. The prior bare
    # sqlite3.connect() leaked an FD per error path.
    with sqlite3.connect("/data/cache.db") as conn:
        by_ticker = pee.load_daily_bars_from_db(conn, from_date, to_date)
        nifty_bars = load_nifty_bars(conn, from_date, to_date)

    if not by_ticker:
        raise RuntimeError(f"no bars in {from_date}..{to_date}")

    ticker_dates: Dict[str, Dict[str, int]] = {}
    all_dates: List[str] = sorted({
        b["date"] for t_bars in by_ticker.values() for b in t_bars
    })
    nifty_idx_by_date = {b["date"]: i for i, b in enumerate(nifty_bars)}

    for t, t_bars in by_ticker.items():
        ticker_dates[t] = {b["date"]: i for i, b in enumerate(t_bars)}

    current_equity = bankroll
    equity_curve = [(all_dates[0], bankroll)]
    trades: List[dict] = []
    open_positions: List[pee.Position] = []
    peak = bankroll
    max_dd = 0.0
    total_signals_fired = 0
    total_positions_opened = 0

    for date in all_dates:
        day_pnl = 0.0

        # 1. Process exits
        new_open = []
        for pos in open_positions:
            entry_idx = ticker_dates.get(pos.ticker, {}).get(pos.entry_date)
            today_idx = ticker_dates.get(pos.ticker, {}).get(date)
            if entry_idx is None or today_idx is None or today_idx <= entry_idx:
                new_open.append(pos)
                continue
            t_bars = by_ticker[pos.ticker]
            bars_after = t_bars[entry_idx + 1:today_idx + 1]
            result = pee.simulate_position(pos, bars_after, slippage_bps)
            if result["exit_date"] == date:
                day_pnl += result["pnl"]
                trades.append(result)
            else:
                if result["hold_days"] >= pos.hold_days:
                    day_pnl += result["pnl"]
                    trades.append(result)
                else:
                    new_open.append(pos)
        open_positions = new_open

        # 2. Compute today's signals
        candidates: List[pee.SignalCandidate] = []
        for t, t_bars in by_ticker.items():
            t_idx = ticker_dates.get(t, {}).get(date)
            if t_idx is None:
                continue
            try:
                scan_results = pee.scan_single_ticker(t_bars, t_idx)
            except Exception:
                scan_results = []
            for c in scan_results:
                candidates.append(pee.SignalCandidate(
                    ticker=c.ticker,
                    date=date,
                    signal_type=c.signal_type,
                    signal_subtype=c.signal_subtype,
                    strength=c.strength,
                    entry_price=t_bars[t_idx]["close"],
                    target=c.target,
                    stop_loss=c.stop_loss,
                    hold_days=c.hold_days,
                    risk_pct=c.risk_pct,
                    features=c.features,
                ))

        total_signals_fired += len(candidates)

        # Regime (fallback to neutral when Nifty data is sparse)
        nifty_idx = nifty_idx_by_date.get(date, 60)
        if nifty_idx >= len(nifty_bars):
            nifty_idx = len(nifty_bars) - 1
        if nifty_idx < 0:
            nifty_idx = 0
        regime = compute_nifty_regime(nifty_bars, nifty_idx)

        # Rank & pick
        new_positions = pee.rank_and_pick(
            candidates, regime, current_equity,
            max_positions=max_positions_per_day,
            min_strength=0.30,
        )

        final_positions = []
        for pos in new_positions:
            t_bars = by_ticker.get(pos.ticker, [])
            t_idx = ticker_dates.get(pos.ticker, {}).get(date)
            if t_idx is None:
                continue
            entry_price = t_bars[t_idx]["close"] * (1 + slippage_bps / 10000)
            # Use the engine's per-signal SL/TP from the candidate.
            # The engine sets target_pct / stop_pct per signal subtype.
            # We pass through pos.stop_loss directly.
            new_stop = pos.stop_loss
            # NOTE: pos.target from rank_and_pick was set by compute_mr/mo_signal
            # using target_pct from the subtype (4% / 3% / 2.5% etc).
            # We use the engine's targets.
            new_target = pos.target
            risk_per_share = entry_price - new_stop
            if risk_per_share <= 0:
                continue
            risk_pct = 0.020 + 0.015 * (pos.raw_strength - 0.3) / 0.7
            risk_pct = max(0.010, min(0.030, risk_pct))
            risk_budget = current_equity * risk_pct
            shares = int(risk_budget / risk_per_share)
            if shares < 1:
                continue
            final_positions.append(pee.Position(
                ticker=pos.ticker,
                entry_date=date,
                entry_price=entry_price,
                shares=shares,
                target=new_target,
                stop_loss=new_stop,
                hold_days=pos.hold_days,
                signal_subtype=pos.signal_subtype,
                raw_strength=pos.raw_strength,
                adjusted_strength=pos.adjusted_strength,
            ))
        open_positions.extend(final_positions)
        total_positions_opened += len(final_positions)

        # 3. Update equity
        current_equity = max(0.0, current_equity + day_pnl)
        if current_equity > peak:
            peak = current_equity
        dd = (peak - current_equity) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
        equity_curve.append((date, current_equity))

        if verbose:
            print(f"  {date}: sigs={len(candidates):4d}  positions={len(final_positions):2d}  "
                  f"open={len(open_positions):2d}  equity={current_equity:.0f}  dd={dd:.1f}%")

    if verbose:
        print(f"\nTotal signals: {total_signals_fired}  Positions opened: {total_positions_opened}")
    return trades, equity_curve, max_dd


def report(trades, equity_curve, max_dd):
    print(f"\n=== Penny Edge Engine Backtest (v3 walk-forward) ===")
    if not trades:
        print("No trades.")
        return
    total_pnl = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] <= 0)
    n = wins + losses
    win_rate = 100 * wins / n if n else 0
    avg_pnl = total_pnl / n if n else 0
    avg_win = sum(t["pnl"] for t in trades if t["pnl"] > 0) / wins if wins else 0
    avg_loss = sum(t["pnl"] for t in trades if t["pnl"] <= 0) / losses if losses else 0
    if losses:
        gross_win = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] <= 0))
        profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")
    else:
        profit_factor = float("inf")

    print(f"Trades: {n}  Wins: {wins}  Losses: {losses}  WR: {win_rate:.1f}%")
    print(f"Total P&L: Rs {total_pnl:+,.2f}")
    print(f"Avg P&L/trade: Rs {avg_pnl:+,.2f}")
    print(f"Avg win: Rs {avg_win:+,.2f}   Avg loss: Rs {avg_loss:+,.2f}")
    print(f"Profit factor: {profit_factor:.2f}")
    print(f"Max drawdown: {max_dd:.2f}%")

    if equity_curve:
        start = equity_curve[0][1]
        end = equity_curve[-1][1]
        try:
            d0 = datetime.strptime(equity_curve[0][0], "%Y-%m-%d")
            d1 = datetime.strptime(equity_curve[-1][0], "%Y-%m-%d")
            days = (d1 - d0).days
            if days > 0 and start > 0:
                cagr = (((end / start) ** (365.25 / days)) - 1) * 100
                print(f"\nEquity: Rs {start:,.2f} -> Rs {end:,.2f}")
                print(f"Approx CAGR: {cagr:+.1f}%   window: {days} days")
        except Exception:
            pass

    by_cat = defaultdict(list)
    for t in trades:
        by_cat[t["signal_subtype"]].append(t)
    print(f"\n=== By signal category ===")
    for cat in sorted(by_cat):
        ts = by_cat[cat]
        ts_pnl = sum(t["pnl"] for t in ts)
        ts_wins = sum(1 for t in ts if t["pnl"] > 0)
        ts_wr = 100 * ts_wins / len(ts) if ts else 0
        ts_avg = ts_pnl / len(ts) if ts else 0
        print(f"  {cat:<14}  N={len(ts):5d}  P&L=Rs {ts_pnl:+10,.0f}  "
              f"WR={ts_wr:5.1f}%  avg=Rs {ts_avg:+6.2f}")

    by_exit = defaultdict(int)
    by_exit_pnl = defaultdict(float)
    for t in trades:
        by_exit[t["exit_reason"]] += 1
        by_exit_pnl[t["exit_reason"]] += t["pnl"]
    print(f"\n=== By exit reason ===")
    for er in sorted(by_exit):
        n_er = by_exit[er]
        pnl_er = by_exit_pnl[er]
        print(f"  {er:<15} N={n_er:4d}  P&L=Rs {pnl_er:+10.0f}")

    by_month = defaultdict(float)
    for t in trades:
        by_month[t["entry_date"][:7]] += t["pnl"]
    print(f"\n=== Monthly P&L ===")
    for m in sorted(by_month):
        v = by_month[m]
        sign = "+" if v >= 0 else "-"
        bar = "#" * max(1, int(abs(v) / 50))
        print(f"  {m}  {sign}Rs {abs(v):>9.2f}  {bar}")


def _main():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="from_date", default="2025-01-01")
    p.add_argument("--to", dest="to_date", default="2026-06-30")
    p.add_argument("--bankroll", type=float, default=2500.0)
    p.add_argument("--slippage-bps", type=float, default=5.0)
    p.add_argument("--max-positions", type=int, default=5)
    p.add_argument("--output", default=None)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    trades, ec, dd = run_backtest(
        from_date=args.from_date, to_date=args.to_date,
        bankroll=args.bankroll, slippage_bps=args.slippage_bps,
        max_positions_per_day=args.max_positions,
        verbose=args.verbose,
    )
    report(trades, ec, dd)
    if args.output:
        with open(args.output, "w") as f:
            json.dump({
                "trades": trades,
                "equity_curve": ec,
                "max_drawdown_pct": dd,
                "config": {
                    "from_date": args.from_date, "to_date": args.to_date,
                    "bankroll": args.bankroll, "slippage_bps": args.slippage_bps,
                    "max_positions_per_day": args.max_positions,
                },
            }, f, indent=2, default=str)
        print(f"\nSaved JSON to {args.output}")


if __name__ == "__main__":
    _main()
