"""
Walk-forward backtest for the EDGE / Connors RSI-2 book.

WHY THIS EXISTS
---------------
The operator's standing rule is that real capital does not get risked without
evidence the strategy will not lose. Until 2026-08-04 no such evidence could
exist for any book in this system:

  * momentum and F&O are intraday, and clear_intraday_cache deleted everything
    older than yesterday every night (fixed -- see INTRADAY_RETENTION_DAYS);
  * the daily books had history, but nothing that replayed the shipped gates
    against it. Every parameter was therefore tuned in-sample on the handful
    of trades the operator happened to take.

Connors is the one book that could be evaluated the day this was written: it is
pure daily-close logic and ohlcv_cache holds daily bars. It is also the only
live book that has ever been net positive, so it is the natural first candidate
for real money -- which makes "does it actually have an edge" the question that
has to be answered before anything is armed.

WHAT IT MEASURES HONESTLY
-------------------------
  * No lookahead. The signal is computed from closes THROUGH day i; the entry
    is day i+1's OPEN, the first price actually transactable after the decision.
  * Stop-before-target within a bar. When a daily bar's range spans both, the
    loss is assumed -- daily bars cannot tell us which came first, and the
    optimistic assumption is how backtests lie.
  * Real Zerodha CNC costs on every trade, via the same calc_zerodha_costs the
    live book uses.
  * No overlapping positions in one ticker.
  * Sizing is a constant. Share count does not change an R-multiple, and
    holding it fixed keeps the study about the SIGNAL rather than the
    position-sizing rules.

WHAT IT CANNOT TELL YOU
-----------------------
Significance. At the shipped gates this produces a single-digit number of
trades over the available history, and a good mean R across nine trades is
noise. The `t` column is printed for exactly that reason: treat anything under
~2 as "no answer yet", not as a green light. Depth accumulates now that
DAILY_HISTORY_DAYS is a rolling window; re-run this then.

USAGE
-----
    docker exec -e PYTHONPATH=/app:/app/.venv/lib/python3.11/site-packages \\
        python-engine python /app/tools/connors_backtest.py [--sweep]

--sweep varies the RSI(2) buy threshold and toggles the rising-confirmation
gate, which is the comparison that matters: it shows both how many signals a
configuration produces AND whether they make money. A gate is only worth
loosening if what it excluded has positive expectancy.
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, "/app")

from config import settings                      # noqa: E402
from engine import calc_zerodha_costs            # noqa: E402
from penny_engine_connors import _rsi_2, _sma    # noqa: E402

# The engine's history floor is 250 bars (SMA-200 + warm-up). A little headroom
# keeps the first evaluated bar away from the boundary.
MIN_BARS = 260
SHARES = 100

Bar = Tuple[str, float, float, float, float, float]   # date, o, h, l, c, v


def load_bars(db_path: str, min_len: int = MIN_BARS + 5) -> Dict[str, List[Bar]]:
    """Daily OHLCV per ticker, ordered, with unusable rows dropped."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    bars: Dict[str, List[Bar]] = defaultdict(list)
    for tkr, d, o, h, l, c, v in conn.execute(
        "SELECT ticker, date, open, high, low, close, volume FROM ohlcv_cache "
        "WHERE close IS NOT NULL AND open IS NOT NULL ORDER BY ticker, date"
    ):
        try:
            bars[tkr].append((d, float(o), float(h), float(l), float(c), float(v or 0)))
        except (TypeError, ValueError):
            continue          # a few rows carry non-numeric prices
    return {t: b for t, b in bars.items() if len(b) >= min_len}


def _entry_signal(hist: List[float], vols: List[float], i: int,
                  rsi_buy: float, require_rising: bool) -> Optional[str]:
    """Mirror of evaluate_connors_entry's gate stack, in gate order.

    Reimplemented rather than called because the sweep has to vary two gates
    that the production function reads from settings. It is pinned to the
    production behaviour by test_connors_backtest.py, which asserts that at
    the shipped configuration this agrees with evaluate_connors_entry.
    Returns a reject reason, or None when the signal fires.
    """
    last = hist[-1]
    sma_200, sma_50 = _sma(hist, 200), _sma(hist, 50)
    if sma_200 is None or sma_50 is None:
        return "SMA not available"
    if last <= sma_200:
        return "below 200 SMA"
    if last <= sma_50:
        return "below 50 SMA"

    rsi = _rsi_2(hist)
    if rsi >= rsi_buy:
        return "RSI(2) not below buy threshold"
    if require_rising and not (rsi > _rsi_2(hist[:-1]) > _rsi_2(hist[:-2])):
        return "RSI not rising for 2 bars"

    avg20 = sum(vols[i - 19: i + 1]) / 20 if i >= 19 else 0.0
    if avg20 <= 0 or vols[i] < 0.5 * avg20:
        return "volume too low"
    return None


def simulate(bars: Dict[str, List[Bar]], rsi_buy: float,
             require_rising: bool) -> Tuple[List[dict], Dict[str, int], int]:
    trades: List[dict] = []
    rejects: Dict[str, int] = defaultdict(int)
    evaluated = 0
    max_hold = settings.PENNY_CONNORS_MAX_HOLD_DAYS

    for tkr, b in bars.items():
        closes = [x[4] for x in b]
        vols = [x[5] for x in b]
        i = MIN_BARS
        # Stop early enough that EVERY simulated trade gets a full exit window:
        # entry needs bar i+1, and the hold needs max_hold bars after that.
        #
        # Admitting truncated trades is not a rounding detail. A trade with no
        # room left falls through to the max_hold branch and exits at whatever
        # the final cached close happens to be -- an arbitrary price, not an
        # exit rule. Over a period when the market drifted up, those arbitrary
        # exits were systematically favourable: with the truncated tail
        # included, the no-confirmation configuration reported mean R +0.009
        # and PF 1.06 (a profitable strategy); excluding it, the same
        # configuration is mean R -0.037 and PF 0.93 (a losing one). The sign
        # of the answer depended entirely on this bound.
        last_entry = len(b) - 1 - max_hold
        while i < last_entry:
            evaluated += 1
            reason = _entry_signal(closes[max(0, i - 300): i + 1], vols, i,
                                   rsi_buy, require_rising)
            if reason is not None:
                rejects[reason] += 1
                i += 1
                continue

            entry = b[i + 1][1]                       # next bar's OPEN
            if entry <= 0:
                i += 1
                continue
            stop = entry * (1 - settings.PENNY_CONNORS_STOP_PCT)
            t1 = entry * (1 + settings.PENNY_CONNORS_T1_PCT)
            t2 = entry * (1 + settings.PENNY_CONNORS_T2_PCT)
            risk_ps = entry - stop

            exit_px: Optional[float] = None
            exit_reason = ""
            for k in range(1, max_hold + 1):
                j = i + k
                if j >= len(b):
                    break
                _d, _o, high, low, _c, _v = b[j]
                # Stop first: a daily bar cannot order intrabar events, so
                # assume the loss when both levels are inside the range.
                if low <= stop:
                    exit_px, exit_reason = stop, "stop"
                    break
                if high >= t2:
                    exit_px, exit_reason = t2, "t2"
                    break
                if high >= t1:
                    exit_px, exit_reason = t1, "t1"
                    break
            if exit_px is None:
                j = min(i + max_hold, len(b) - 1)
                exit_px, exit_reason = b[j][4], "max_hold"

            gross = (exit_px - entry) * SHARES
            costs = calc_zerodha_costs(entry, exit_px, SHARES, is_intraday=False)
            pnl = gross - costs
            trades.append({
                "ticker": tkr, "date": b[i][0], "entry": entry,
                "exit": exit_px, "reason": exit_reason, "pnl": pnl,
                "r_net": pnl / (risk_ps * SHARES) if risk_ps > 0 else 0.0,
            })
            i += max_hold                              # no overlapping positions

    return trades, dict(rejects), evaluated


def stats(trades: List[dict]) -> dict:
    if not trades:
        return {"n": 0}
    pnl = [t["pnl"] for t in trades]
    rn = [t["r_net"] for t in trades]
    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p <= 0]
    gross_w, gross_l = sum(wins), abs(sum(losses))
    sd = statistics.pstdev(rn) if len(rn) > 1 else 0.0
    se = sd / len(rn) ** 0.5 if rn else 0.0
    return {
        "n": len(trades),
        "win_pct": len(wins) / len(pnl) * 100,
        "mean_r": statistics.mean(rn),
        "total_pnl": sum(pnl),
        "profit_factor": (gross_w / gross_l) if gross_l else float("inf"),
        "t_stat": (statistics.mean(rn) / se) if se else 0.0,
    }


def _print_row(label: str, s: dict) -> None:
    if not s["n"]:
        print(f"{label:<32}{0:>9}{'-':>7}{'-':>9}{'-':>12}{'-':>7}{'-':>7}")
        return
    print(f"{label:<32}{s['n']:>9}{s['win_pct']:>7.1f}{s['mean_r']:>+9.4f}"
          f"{s['total_pnl']:>12,.0f}{s['profit_factor']:>7.2f}{s['t_stat']:>7.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=settings.DB_PATH)
    ap.add_argument("--sweep", action="store_true",
                    help="vary RSI(2) threshold and the rising-confirmation gate")
    args = ap.parse_args()

    bars = load_bars(args.db)
    print(f"tickers with >= {MIN_BARS + 5} daily bars: {len(bars):,}")
    print()
    header = (f"{'config':<32}{'signals':>9}{'win%':>7}{'meanR':>9}"
              f"{'totalPnL':>12}{'PF':>7}{'t':>7}")
    print(header)
    print("-" * len(header))

    configs = [(settings.PENNY_CONNORS_RSI2_BUY, True)]
    if args.sweep:
        configs = [(r, g) for r in (10.0, 15.0, 20.0, 25.0) for g in (True, False)]

    last_rejects: Dict[str, int] = {}
    for rsi_buy, rising in configs:
        trades, rejects, _ev = simulate(bars, rsi_buy, rising)
        _print_row(f"RSI<{rsi_buy:.0f} rising={'Y' if rising else 'N'}", stats(trades))
        last_rejects = rejects

    print()
    print("reject funnel (last configuration):")
    for reason, n in sorted(last_rejects.items(), key=lambda kv: -kv[1]):
        print(f"   {n:>9,}  {reason}")
    print()
    print("Reminder: t < ~2 means this has not answered the question yet.")


if __name__ == "__main__":
    main()
