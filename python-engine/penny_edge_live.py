"""
[PENNY-EDGE-LIVE 2026-07-01] Live signal scanner that wires
penny_edge_engine to the live ohlcv_cache and produces a
list of candidate trades for the day.

This is the integration layer. It:
  1. Loads today's bars from cache.db
  2. Computes signal features for every (date, ticker) pair
  3. Filters to candidates with strength >= min_strength
  4. Sorts by regime-adjusted strength
  5. Outputs the top N for execution (paper or live)

The actual ORDER PLACEMENT is NOT in this module. The orchestrator
(a new penny_edge_orchestrator.py -- to be written) takes the
candidates and decides whether to enter paper trades or live
trades via the existing penny_executor.

The HARD problem we don't solve here: live intraday risk
management. The engine's signals are computed once per day on
daily bars. Real penny trading happens on 1-minute bars during
the 09:30-14:30 window. v4 will need an intraday variant that
fires signals as they develop.

For now, this module is designed for end-of-day signals and
next-day open entries. This matches the empirical edge:
"buy at close, hold 1 day, exit at next-day close" works.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime
from typing import List, Optional

import penny_edge_engine as pee

logger = logging.getLogger(__name__)

DEFAULT_BANKROLL = 2500.0
DEFAULT_MAX_POSITIONS = 5
DEFAULT_MIN_STRENGTH = 0.30


def scan_today(
    bankroll: float = DEFAULT_BANKROLL,
    max_positions: int = DEFAULT_MAX_POSITIONS,
    min_strength: float = DEFAULT_MIN_STRENGTH,
    db_path: str = "/data/cache.db",
    as_of_date: Optional[str] = None,
    nifty_ticker: str = "NIFTYBEES",
) -> dict:
    """One-shot scanner. Pulls latest bars from the DB, computes
    signals, returns the top-N candidate Positions for as_of_date.

    Returns dict with:
      - 'date': the as-of date used
      - 'candidates': list of SignalCandidate (raw, before ranking)
      - 'positions': list of Position (after ranking, ready to enter)
      - 'regime': Regime object
      - 'eligible_tickers': count
      - 'rejected_signal_count': signals dropped due to min_strength
    """
    # [PENNY-FD-LEAK 2026-07-01] Use `with` so the connection is
    # closed even if any intermediate query raises. The previous bare
    # sqlite3.connect() leaked an FD on every exception path.
    with sqlite3.connect(db_path) as conn:
        # [PENNY-EDGE-ENGINE-GRACEFUL 2026-07-06] Verify ohlcv_cache
        # table exists BEFORE running any queries. A fresh deploy (or
        # a partial-restore from backup) can leave the DB without the
        # ohlcv_cache table; the previous behaviour was to crash with
        # `sqlite3.OperationalError: no such table: ohlcv_cache`, which
        # surfaced as a silent "no candidates" day in production
        # because the cron wrapper's try/except caught the exception
        # but logged only a `penny_edge_scan_failed err=...` line.
        # Now we emit a loud `penny_edge_scan_engine_db_unready` line
        # AND return an empty-candidates dict so the orchestrator's
        # own `penny_edge_scan_done` line still fires and the operator
        # sees "engine returned 0 (DB unready)" instead of
        # "engine crashed (DB unready)".
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ohlcv_cache'"
            )
            if not cur.fetchone():
                logger.error(
                    "penny_edge_scan_engine_db_unready reason=ohlcv_cache_table_missing "
                    "FIX=run penny_universe_refresh and wait one trading day "
                    "for the OHLCV cache to populate, OR restore the DB from backup."
                )
                return {
                    "date":                None,
                    "candidates":          [],
                    "positions":           [],
                    "regime":              pee.compute_regime(0.0, 0.5),
                    "eligible_tickers":    0,
                    "rejected_below_threshold": 0,
                    "n_candidates":        0,
                    "n_positions":         0,
                }
        except sqlite3.OperationalError as schema_exc:
            logger.error(
                "penny_edge_scan_engine_db_unready reason=schema_query_failed err=%s "
                "FIX=verify the DB at %s is readable and not corrupt.",
                str(schema_exc), db_path,
            )
            raise

        if as_of_date is None:
            # Use the most recent date in ohlcv_cache
            cur = conn.cursor()
            cur.execute("SELECT MAX(date) FROM ohlcv_cache")
            row = cur.fetchone()
            if not row or row[0] is None:
                # [PENNY-EDGE-ENGINE-GRACEFUL 2026-07-06] Same DB-unready
                # treatment as the missing-table path. An empty
                # ohlcv_cache (after schema check passed) means the
                # universe refresh hasn't populated yet -- emit a
                # loud diagnostic and return an empty-candidates dict
                # instead of crashing.
                logger.error(
                    "penny_edge_scan_engine_db_unready reason=ohlcv_cache_empty "
                    "FIX=run penny_universe_refresh and wait one trading day "
                    "for the OHLCV cache to populate."
                )
                return {
                    "date":                None,
                    "candidates":          [],
                    "positions":           [],
                    "regime":              pee.compute_regime(0.0, 0.5),
                    "eligible_tickers":    0,
                    "rejected_below_threshold": 0,
                    "n_candidates":        0,
                    "n_positions":         0,
                }
            as_of_date = str(row[0])
        # Load from earliest available to as_of_date (need 60+ days of history)
        cur = conn.cursor()
        cur.execute("SELECT MIN(date) FROM ohlcv_cache")
        row = cur.fetchone()
        from_date = str(row[0]) if row and row[0] else "2024-01-01"
        bars = pee.load_daily_bars_from_db(conn, from_date, as_of_date)
        cur.execute("""
            SELECT date, close FROM ohlcv_cache
            WHERE ticker = ? AND date <= ?
            ORDER BY date
        """, (nifty_ticker, as_of_date))
        nifty_rows = [{"date": r[0], "close": r[1]} for r in cur.fetchall()]
    # [PENNY-FD-LEAK 2026-07-01] The connection is closed by the
    # `with` block above; this comment marks the boundary.

    # Compute regime from Nifty proxy
    nifty_idx = len(nifty_rows) - 1
    regime = pee.compute_regime(0.0, 0.5)
    if nifty_idx >= 60:
        # Use the penny_edge_backtest helper for consistency
        from penny_edge_backtest import compute_nifty_regime
        regime = compute_nifty_regime(nifty_rows, nifty_idx)

    # Scan all tickers for as_of_date
    candidates: List[pee.SignalCandidate] = []
    rejected_count = 0
    eligible_tickers = 0
    for t, t_bars in bars.items():
        # Find the bar at as_of_date
        t_idx = None
        for i, b in enumerate(t_bars):
            if b["date"] == as_of_date:
                t_idx = i
                break
        if t_idx is None:
            continue
        eligible_tickers += 1
        try:
            sigs = pee.scan_single_ticker(t_bars, t_idx)
        except Exception as exc:
            logger.warning("scan_failed ticker=%s err=%s", t, exc)
            continue
        for c in sigs:
            # Override the date with as_of_date (in case per-ticker
            # history doesn't include it explicitly)
            candidates.append(pee.SignalCandidate(
                ticker=c.ticker,
                date=as_of_date,
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

    positions = pee.rank_and_pick(
        candidates, regime, bankroll,
        max_positions=max_positions,
        min_strength=min_strength,
    )
    return {
        "date":                as_of_date,
        "candidates":          candidates,
        "positions":           positions,
        "regime":              regime,
        "eligible_tickers":    eligible_tickers,
        "rejected_below_threshold": sum(
            1 for c in candidates
            if pee.adjust_strength_for_regime(c, regime) < min_strength
        ),
        "n_candidates":        len(candidates),
        "n_positions":         len(positions),
    }


def _rank_for_leg(
    candidates: List[pee.SignalCandidate],
    bankroll: float,
    max_positions: int,
    min_strength: float,
) -> List[pee.Position]:
    """Re-rank the same candidate list with a specific bankroll.

    Used by the orchestrator's paper/live twin-leg runner: both
    legs see the same signal universe, but each leg's position
    sizing is computed against ITS OWN bankroll. This way a paper
    leg with Rs 100k bankroll can show what a fuller-sized trade
    would be, while a live leg with Rs 1k bankroll stays tiny.
    """
    # Neutral regime so this helper is regime-independent.
    regime = pee.compute_regime(0.0, 0.5)
    return pee.rank_and_pick(
        candidates, regime, bankroll,
        max_positions=max_positions,
        min_strength=min_strength,
    )


def format_positions_report(scan_result: dict) -> str:
    """Format a Telegram-friendly report of the scan results."""
    out = []
    out.append(f"*Penny Edge Engine* `{scan_result['date']}`")
    regime = scan_result["regime"]
    out.append(
        f"Regime: trend={regime.trend_strength:+.2f} "
        f"vol_pctl={regime.vol_percentile:.2f} "
        f"preferred={regime.preferred_signal}"
    )
    out.append(
        f"Universe: {scan_result['eligible_tickers']} tickers; "
        f"{scan_result['n_candidates']} signals above threshold; "
        f"{scan_result['n_positions']} positions selected"
    )
    if not scan_result["positions"]:
        out.append("No positions. (Markets may be quiet or no signals qualified.)")
        return "\n".join(out)
    for i, p in enumerate(scan_result["positions"], 1):
        out.append(
            f"{i}. `{p.ticker}` [{p.signal_subtype}] "
            f"strength={p.adjusted_strength:.2f} "
            f"entry={p.entry_price:.2f} "
            f"target={p.target:.2f} "
            f"stop={p.stop_loss:.2f} "
            f"hold={p.hold_days}d "
            f"shares={p.shares}"
        )
    return "\n".join(out)
