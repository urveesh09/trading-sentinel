"""
[PENNY-BACKTEST-ANALYSIS 2026-07-01] Diagnostic pass over the
v2 backtest output. Answers the operator's follow-up questions
without re-running the full replay.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from statistics import mean, median

# Connect to the DB the way the backtest does
def connect():
    conn = sqlite3.connect("/data/cache.db")
    conn.row_factory = sqlite3.Row
    return conn


def main():
    conn = connect()
    cur = conn.cursor()
    # 1. Universe turnover
    cur.execute("SELECT COUNT(DISTINCT ticker) FROM ohlcv_cache WHERE date >= '2025-01-01'")
    print(f"Tickers with data in 2025+: {cur.fetchone()[0]}")

    # 2. The 6000 most active tickers by trading volume (median daily)
    cur.execute("""
        SELECT ticker,
               COUNT(*) as days,
               AVG(volume) as avg_vol,
               MIN(close) as min_close,
               MAX(close) as max_close,
               AVG(close) as avg_close
        FROM ohlcv_cache
        WHERE date >= '2025-01-01'
        GROUP BY ticker
        ORDER BY avg_vol DESC
        LIMIT 20
    """)
    print("\n=== Top 20 tickers by avg volume (2025-2026) ===")
    print(f"  {'ticker':<14} {'days':>5} {'avg_vol':>12} {'price_band':>15}")
    for r in cur.fetchall():
        print(f"  {r[0]:<14} {r[1]:>5d} {r[2]:>12,.0f} {r[3]:.1f}-{r[4]:.1f}")

    # 3. The "penny band" tickers (1-55) sorted by volume
    cur.execute("""
        SELECT ticker,
               COUNT(*) as days,
               AVG(volume) as avg_vol,
               AVG(close) as avg_close
        FROM ohlcv_cache
        WHERE date >= '2025-01-01' AND close BETWEEN 1 AND 55
        GROUP BY ticker
        HAVING days >= 200
        ORDER BY avg_vol DESC
        LIMIT 15
    """)
    print("\n=== Top 15 penny-band (1-55) tickers by avg volume ===")
    for r in cur.fetchall():
        print(f"  {r[0]:<14} {r[1]:>5d}  vol={r[2]:>12,.0f}  price={r[3]:.2f}")

    # 4. Median volume distribution -- the gate's complaint
    cur.execute("""
        SELECT volume FROM ohlcv_cache
        WHERE date >= '2025-01-01' AND close BETWEEN 1 AND 55
        ORDER BY volume
    """)
    volumes_all = [r[0] for r in cur.fetchall()]
    if volumes_all:
        n = len(volumes_all)
        p10 = volumes_all[int(n*0.10)]
        p25 = volumes_all[int(n*0.25)]
        p50 = volumes_all[int(n*0.50)]
        p75 = volumes_all[int(n*0.75)]
        p90 = volumes_all[int(n*0.90)]
        print("\n=== Daily volume distribution across penny stocks (2025-2026) ===")
        print(f"  p10: {p10:,.0f} shares")
        print(f"  p25: {p25:,.0f} shares")
        print(f"  p50: {p50:,.0f} shares")
        print(f"  p75: {p75:,.0f} shares")
        print(f"  p90: {p90:,.0f} shares")

    # 5. How often does a stock's volume today exceed its 20d median by 1.8x?
    # Simulate: per (ticker, day), compute median(volume[-20:-1]) and check if volume[today] >= 1.8*median
    cur.execute("""
        WITH ranked AS (
            SELECT ticker, date, volume,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date) as rn
            FROM ohlcv_cache
            WHERE date >= '2025-01-01' AND close BETWEEN 1 AND 55
        ),
        with_median AS (
            SELECT ticker, date, volume,
                   AVG(volume) OVER (
                       PARTITION BY ticker
                       ORDER BY date
                       ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
                   ) as median_vol_20d
            FROM ranked
        )
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN volume >= 1.8 * median_vol_20d THEN 1 ELSE 0 END) as pass_18,
            SUM(CASE WHEN volume >= 1.5 * median_vol_20d THEN 1 ELSE 0 END) as pass_15,
            SUM(CASE WHEN volume >= 1.2 * median_vol_20d THEN 1 ELSE 0 END) as pass_12,
            SUM(CASE WHEN volume >= 1.0 * median_vol_20d THEN 1 ELSE 0 END) as pass_10
        FROM with_median
        WHERE median_vol_20d IS NOT NULL AND median_vol_20d > 0
    """)
    print("\n=== 'Volume >= X * 20d median' pass rate across penny stocks ===")
    row = cur.fetchone()
    if row:
        total, p18, p15, p12, p10 = row
        print(f"  total (date, ticker) pairs: {total:,}")
        print(f"  pass @ 1.0x (>= median):   {p10:>8,}  ({100*p10/total:5.2f}%)")
        print(f"  pass @ 1.2x:               {p12:>8,}  ({100*p12/total:5.2f}%)")
        print(f"  pass @ 1.5x:               {p15:>8,}  ({100*p15/total:5.2f}%)")
        print(f"  pass @ 1.8x (LIVE GATE):   {p18:>8,}  ({100*p18/total:5.2f}%)")

    # 6. Average next-day return after a 1.8x volume day
    cur.execute("""
        WITH ranked AS (
            SELECT ticker, date, volume, close, high, open
            FROM ohlcv_cache
            WHERE date >= '2025-01-01' AND close BETWEEN 1 AND 55
        ),
        with_median AS (
            SELECT ticker, date, volume, close,
                   AVG(volume) OVER (
                       PARTITION BY ticker
                       ORDER BY date
                       ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
                   ) as median_vol_20d,
                   LEAD(close) OVER (PARTITION BY ticker ORDER BY date) as next_close
            FROM ranked
        )
        SELECT
            100.0 * AVG(CASE WHEN volume >= 1.8 * median_vol_20d THEN (next_close - close) / close END) as avg_18_ret,
            100.0 * AVG(CASE WHEN volume >= 1.5 * median_vol_20d THEN (next_close - close) / close END) as avg_15_ret,
            100.0 * AVG(CASE WHEN volume >= 1.2 * median_vol_20d THEN (next_close - close) / close END) as avg_12_ret,
            100.0 * AVG(CASE WHEN volume >= 1.0 * median_vol_20d THEN (next_close - close) / close END) as avg_10_ret,
            COUNT(CASE WHEN volume >= 1.8 * median_vol_20d AND next_close IS NOT NULL THEN 1 END) as n_18,
            COUNT(CASE WHEN volume >= 1.5 * median_vol_20d AND next_close IS NOT NULL THEN 1 END) as n_15,
            COUNT(CASE WHEN volume >= 1.2 * median_vol_20d AND next_close IS NOT NULL THEN 1 END) as n_12,
            COUNT(CASE WHEN volume >= 1.0 * median_vol_20d AND next_close IS NOT NULL THEN 1 END) as n_10
        FROM with_median
        WHERE median_vol_20d IS NOT NULL AND median_vol_20d > 0
    """)
    print("\n=== Mean next-day return (%) by volume-surge threshold ===")
    row = cur.fetchone()
    if row:
        avg18, avg15, avg12, avg10, n18, n15, n12, n10 = row
        print(f"  1.0x (>=median, N={n10:>7,}): {avg10:+.3f}%")
        print(f"  1.2x              (N={n12:>7,}): {avg12:+.3f}%")
        print(f"  1.5x              (N={n15:>7,}): {avg15:+.3f}%")
        print(f"  1.8x (LIVE GATE,  (N={n18:>7,}): {avg18:+.3f}%")
        print("\n  IF these numbers are positive, volume surge IS a real signal")
        print("  IF they're near-zero or negative, volume surge is not predictive")

    # 7. Combine: when BOTH volume and breakout conditions are met, what's the next-day return?
    cur.execute("""
        WITH ranked AS (
            SELECT ticker, date, volume, close, high,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date) as rn
            FROM ohlcv_cache
            WHERE date >= '2025-01-01' AND close BETWEEN 1 AND 55
        ),
        with_features AS (
            SELECT ticker, date, volume, close, high,
                   LAG(high) OVER (PARTITION BY ticker ORDER BY date) as prev_high,
                   LAG(close) OVER (PARTITION BY ticker ORDER BY date) as prev_close,
                   AVG(volume) OVER (
                       PARTITION BY ticker
                       ORDER BY date
                       ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
                   ) as median_vol_20d,
                   LEAD(close) OVER (PARTITION BY ticker ORDER BY date) as next_close
            FROM ranked
        )
        SELECT
            100.0 * AVG(CASE
                WHEN volume >= 1.8 * median_vol_20d AND close > 1.003 * prev_high
                THEN (next_close - close) / close
            END) as ret_both_strict,
            100.0 * AVG(CASE
                WHEN volume >= 1.2 * median_vol_20d AND close > 1.0015 * prev_high
                THEN (next_close - close) / close
            END) as ret_both_relaxed,
            COUNT(CASE
                WHEN volume >= 1.8 * median_vol_20d AND close > 1.003 * prev_high
                AND next_close IS NOT NULL THEN 1
            END) as n_both_strict,
            COUNT(CASE
                WHEN volume >= 1.2 * median_vol_20d AND close > 1.0015 * prev_high
                AND next_close IS NOT NULL THEN 1
            END) as n_both_relaxed
        FROM with_features
        WHERE median_vol_20d IS NOT NULL AND median_vol_20d > 0
          AND prev_high IS NOT NULL
    """)
    print("\n=== Combined signal: volume AND breakout, next-day return ===")
    row = cur.fetchone()
    if row:
        r_strict, r_rel, n_strict, n_rel = row
        print(f"  Strict (1.8x vol + 0.3% breakout), N={n_strict:>7,}: {r_strict:+.3f}% per day")
        print(f"  Relaxed (1.2x vol + 0.15% breakout), N={n_rel:>7,}: {r_rel:+.3f}% per day")
        print("\n  THIS is the real test: if the COMBINED signal is positive")
        print("  the strategy has a real edge. If it's near-zero the strategy")
        print("  is noise, and tuning gates won't help.")

    conn.close()


if __name__ == "__main__":
    main()
