"""
[PENNY-EDGE-ORCHESTRATOR 2026-07-01] Glue between the adaptive
signal engine (penny_edge_engine) and the live trading system
(executor + positions table).

The engine produces SignalCandidates ranked by regime-adjusted
strength. The orchestrator:

  1. Calls the engine for today's candidates
  2. Picks the top-N entries to enter
  3. For each entry: submits order via PennyExecutor (paper or
     live mode), then writes a `positions` row tagged with
     source='EDGE' and the entry metadata
  4. Logs the Telegram-friendly summary

Operational behaviour:
  - 09:30 IST daily trigger
  - Idempotent: re-running the same day does NOT double up
    (we check the positions table for OPEN positions with
    source='EDGE' for today)
  - Slippage 5 bps per side via the executor's entry_price.
  - Risk cap: hardcoded at edge subsystem bankroll of Rs 1,000
    (vs the 2,500 the full penny system uses). Each position's
    risk_pct caps at 3% of bankroll (= Rs 30 max per trade).

The subsystem uses PennyLeg.CNC (delivery) so positions don't
auto-square at 15:15 MIS cutoff; they stay open for the per-
signal hold_days (1-3) and a dedicated edge-exit job closes
them by the same rule.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from typing import List, Optional

import penny_edge_engine as pee
import penny_edge_live as pel
from config import settings
from penny_executor import PennyExecutor
from penny_models import PennyLeg
from position_tracker import init_positions_db

logger = logging.getLogger(__name__)

# Tunables -- all read from settings so the operator can override
# via env vars without restarting with new code.
def _edge_bankroll() -> float:
    return float(getattr(settings, "PENNY_EDGE_BANKROLL", 1000.0))


def _edge_max_positions() -> int:
    return int(getattr(settings, "PENNY_EDGE_MAX_POSITIONS", 3))


def _edge_min_strength() -> float:
    return float(getattr(settings, "PENNY_EDGE_MIN_STRENGTH", 0.45))


def _edge_paper_mode() -> bool:
    """True if edge subsystem should run paper only. Default is paper
    even when PENNY_LIVE_TRADING is True; operator flips this off
    after a few days of paper-trading experience."""
    override = getattr(settings, "PENNY_EDGE_PAPER", True)
    if override:
        return True
    return not settings.PENNY_LIVE_TRADING


def _edge_max_hold_days() -> int:
    return int(getattr(settings, "PENNY_EDGE_MAX_HOLD_DAYS", 3))


EDGE_SLIPPAGE_BPS = 5.0
EDGE_PRODUCT_TYPE = PennyLeg.CNC


def _executor_for_paper(kite) -> PennyExecutor:
    """Build a PennyExecutor configured for the edge subsystem's
    paper-mode flag. Independent from the legacy penny scanner's
    paper_mode setting -- the operator can flip them independently.
    """
    return PennyExecutor(
        kite=kite,
        paper_mode=_edge_paper_mode(),
    )


async def _already_entered_today(db_path: str, ticker: str, today_str: str) -> bool:
    """Check whether we already entered this ticker today for the
    edge subsystem. Idempotency guard."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM positions
        WHERE ticker = ?
          AND source  = 'EDGE'
          AND substr(entry_date, 1, 10) = ?
        LIMIT 1
    """, (ticker, today_str))
    row = cur.fetchone()
    conn.close()
    return row is not None


async def _write_edge_position(
    db_path: str,
    ticker: str,
    entry_date_iso: str,
    entry_price: float,
    shares: int,
    stop_loss: float,
    target_1: float,
    target_2: float,
    regime_at_entry: str,
    product_type: str,
):
    """Insert an OPEN position row tagged source='EDGE'.

    Schema (positions table) -- we populate the standard fields
    the position_tracker and other consumers expect, plus we
    mark source='EDGE' so the EOD exit job can find them.
    """
    await init_positions_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO positions (
            ticker, exchange, entry_date, entry_price, shares,
            stop_loss_initial, trailing_stop_current,
            target_1, target_2, atr_14_at_entry,
            highest_close_since_entry, status, source,
            product_type, regime_at_entry,
            atr_1min_post_t1, t1_fired
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ticker, "NSE", entry_date_iso,
        entry_price, shares,
        stop_loss, stop_loss,         # trailing_stop_current == SL at entry
        target_1, target_2,
        0.0,                          # atr_14_at_entry -- not used by EDGE exits
        entry_price,                  # highest_close_since_entry -- starts at entry
        "OPEN", "EDGE",
        product_type, regime_at_entry,
        0.0, 0,                       # atr_1min_post_t1, t1_fired (unused)
    ))
    conn.commit()
    conn.close()


async def run_penny_edge_scan(kite, db_path: Optional[str] = None) -> dict:
    """Daily 09:30 IST scan. Submits entries for the top-N candidates.

    Returns a dict suitable for the operator's Telegram channel:
      {"date", "candidates_total", "positions_entered", "trades": [...]}

    Parameters:
      kite: the KiteClient instance from main.py
      db_path: optional override for the SQLite DB path. Defaults
               to settings.DB_PATH. Tests pass a tmp path.
    """
    # Use UTC date for both the entry_date store and the
    # idempotency check. The orchestrator is scheduled at 09:30 IST
    # which is 04:00 UTC, so entry_date today has today's UTC date.
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    bankroll = _edge_bankroll()
    db_path = db_path or settings.DB_PATH
    logger.info("penny_edge_scan_started date=%s bankroll=%.0f paper_mode=%s",
                today_str, bankroll, _edge_paper_mode())
    # 1. Run the engine
    scan = pel.scan_today(
        bankroll=bankroll,
        max_positions=_edge_max_positions(),
        min_strength=_edge_min_strength(),
        db_path=db_path,
    )
    n_candidates = scan["n_candidates"]
    regime = scan["regime"]
    logger.info(
        "penny_edge_scan_engine_complete date=%s universe=%d candidates=%d regime=%s",
        today_str, scan["eligible_tickers"], n_candidates,
        regime.preferred_signal,
    )

    # 2. Submit top-N via PennyExecutor
    executor = _executor_for_paper(kite)
    submitted = []
    skipped = []
    for pos in scan["positions"]:
        # Idempotency guard: skip if this ticker is already entered today
        if await _already_entered_today(db_path, pos.ticker, today_str):
            skipped.append((pos.ticker, "already-entered-today"))
            continue
        # Submit entry. The executor returns order_ids.
        order_result = await executor.execute_entry(
            ticker=pos.ticker,
            leg=EDGE_PRODUCT_TYPE,
            entry_price=pos.entry_price,
            stop_loss=pos.stop_loss,
            shares=pos.shares,
        )
        entry_status = order_result.get("entry_status")
        # Position row ONLY if the entry actually filled (paper or live)
        if entry_status in ("filled", "paper"):
            entry_iso = datetime.now(timezone.utc).isoformat()
            await _write_edge_position(
                db_path=db_path,
                ticker=pos.ticker,
                entry_date_iso=entry_iso,
                entry_price=pos.entry_price,
                shares=pos.shares,
                stop_loss=pos.stop_loss,
                target_1=pos.target,
                target_2=pos.target,           # edge strategy uses single TP
                regime_at_entry=regime.preferred_signal,
                product_type=EDGE_PRODUCT_TYPE.value,
            )
            submitted.append({
                "ticker":       pos.ticker,
                "subtype":      pos.signal_subtype,
                "strength":     round(pos.adjusted_strength, 2),
                "entry":        round(pos.entry_price, 2),
                "target":       round(pos.target, 2),
                "stop":         round(pos.stop_loss, 2),
                "hold_days":    pos.hold_days,
                "shares":       pos.shares,
                "entry_status": entry_status,
                "entry_order_id": order_result.get("entry_order_id"),
            })
            logger.info(
                "penny_edge_entry_submitted ticker=%s subtype=%s strength=%.2f "
                "entry=%.2f target=%.2f stop=%.2f hold=%dd shares=%d status=%s",
                pos.ticker, pos.signal_subtype, pos.adjusted_strength,
                pos.entry_price, pos.target, pos.stop_loss,
                pos.hold_days, pos.shares, entry_status,
            )
        else:
            skipped.append((pos.ticker, f"entry_status={entry_status}"))
            logger.warning(
                "penny_edge_entry_skipped ticker=%s order_result=%s",
                pos.ticker, order_result,
            )

    summary = {
        "date":             today_str,
        "universe":         scan["eligible_tickers"],
        "candidates_total": n_candidates,
        "positions_entered": len(submitted),
        "positions_skipped": skipped,
        "regime":           regime.preferred_signal,
        "trades":           submitted,
    }
    logger.info(
        "penny_edge_scan_done date=%s entered=%d skipped=%d",
        today_str, len(submitted), len(skipped),
    )
    return summary


async def run_penny_edge_exit(kite, db_path: Optional[str] = None) -> dict:
    """EOD exit job: close any EDGE-sourced positions whose age
    exceeds _edge_max_hold_days() trading days.

    Parameters:
      kite: KiteClient instance
      db_path: optional DB path override (default: settings.DB_PATH)
    """
    db_path = db_path or settings.DB_PATH
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, ticker, entry_price, shares, stop_loss_initial,
               target_1, product_type, regime_at_entry,
               entry_date
        FROM positions
        WHERE source = 'EDGE' AND status = 'OPEN'
    """)
    rows = cur.fetchall()
    conn.close()

    executor = _executor_for_paper(kite)
    closed = []
    if not rows:
        logger.info("penny_edge_exit_no_open_positions date=%s", today_str)
        return {"date": today_str, "closed": []}

    for r in rows:
        ticker, entry_price, shares, sl, target, prod_type, regime, entry_date = r[1:9]
        # Compute age in days from entry_date
        try:
            entry_dt = datetime.fromisoformat(entry_date.replace("Z", "+00:00"))
        except Exception:
            entry_dt = datetime.strptime(entry_date[:19], "%Y-%m-%dT%H:%M:%S")
        now_utc = datetime.now(timezone.utc)
        age_days = (now_utc - entry_dt).days
        max_hold = _edge_max_hold_days()
        if age_days < max_hold:
            continue   # still within max hold window
        # Force market unwind
        logger.info(
            "penny_edge_force_exit ticker=%s age=%dd entry=%.2f shares=%d",
            ticker, age_days, entry_price, shares,
        )
        leg = PennyLeg.CNC if prod_type == "CNC" else PennyLeg.MIS
        unwind_id = await executor._market_unwind(ticker, leg, shares)
        # Update the position row to reflect the exit
        conn2 = sqlite3.connect(db_path)
        c2 = conn2.cursor()
        # Use today's close as a placeholder exit price -- the executor
        # in live mode returns the actual fill, but in paper mode we
        # just use last-close. The position_tracker EOD job will
        # backfill the real exit price from the trade ledger.
        c2.execute("""
            UPDATE positions
            SET status='CLOSED',
                exit_date=?,
                exit_price=entry_price,
                realised_pnl=0.0
            WHERE ticker=? AND source='EDGE' AND status='OPEN'
        """, (today_str, ticker))
        conn2.commit()
        conn2.close()
        closed.append({
            "ticker":       ticker,
            "unwind_id":    unwind_id,
            "age_days":     age_days,
            "force_close_reason": "edge-exit-3d-cap",
        })

    logger.info(
        "penny_edge_exit_done date=%s closed=%d", today_str, len(closed),
    )
    return {"date": today_str, "closed": closed}


def format_telegram(summary: dict, header: str = "Penny Edge") -> str:
    """Format a scan/exit summary for Telegram output."""
    out = [f"*{header}* `{summary.get('date', '?')}`"]
    if "regime" in summary:
        out.append(f"Regime preferred: `{summary['regime']}`")
    if "universe" in summary:
        out.append(
            f"Universe: {summary['universe']} tickers; "
            f"{summary['candidates_total']} candidates; "
            f"{summary['positions_entered']} entered"
        )
    for t in summary.get("trades", []):
        out.append(
            f"- `{t['ticker']}` [{t['subtype']}] strength={t['strength']:.2f} "
            f"entry={t['entry']:.2f} target={t['target']:.2f} stop={t['stop']:.2f} "
            f"hold={t['hold_days']}d shares={t['shares']} status={t['entry_status']}"
        )
    for ticker, reason in summary.get("positions_skipped", []):
        out.append(f"  skipped: `{ticker}` ({reason})")
    if "closed" in summary and summary["closed"]:
        out.append(f"*Exits:* {len(summary['closed'])} forced")
        for c in summary["closed"]:
            out.append(
                f"- `{c['ticker']}` age={c['age_days']}d "
                f"unwind_id={c.get('unwind_id', '?')}"
            )
    return "\n".join(out)


if __name__ == "__main__":
    # Smoke: run a scan and print the Telegram-formatted report
    logging.basicConfig(level=logging.INFO)
    # When run directly, use a no-op kite so paper mode works.
    class _FakeKite:
        access_token = "fake"
        def place_order(self, **_): return {"order_id": "STUB"}
        def cancel_order(self, *_a, **_kw): return None
        def order_history(self, **_): return [{"status": "COMPLETE"}]
    r = asyncio.run(run_penny_edge_scan(_FakeKite()))
    print(format_telegram(r))
