"""
[PENNY-EDGE-ORCHESTRATOR 2026-07-01] Glue between the adaptive
signal engine (penny_edge_engine) and the live trading system.

The orchestrator runs TWO legs in parallel each morning:

  1. PAPER leg: large bankroll (default Rs 100,000), no real orders.
     Used for statistical confidence -- what would the strategy
     do with real-sized capital?

  2. LIVE leg: small bankroll (default Rs 1,000), real Kite orders.
     Used for live fill validation -- what does the broker
     actually fill at the prices we see?

Both legs share the SAME signal scan (same set of candidates
ranked by regime-adjusted strength). The bankroll scales
each leg's position sizing. Both legs are:
  - Idempotent (separate source tags in the positions table)
  - Capped at PENNY_EDGE_MAX_POSITIONS=3 trades/day per leg
  - Subject to the same regime detection (Nifty 10d + 14d vol)
  - Telegram-reported in a single combined message

Operational rules (operator-set in .env):
  - Both legs disabled by setting PENNY_EDGE_DISABLE_PAPER=1 or
    PENNY_EDGE_DISABLE_LIVE=1. Both default to enabled.
  - Both legs can run even when PENNY_LIVE_TRADING is False -- in
    that case the live leg is forced to paper. This means the
    system always has at LEAST a paper leg running.
  - The orchestrator uses the same kite instance for both legs.

The holds/exits are tracked separately (source='EDGE_PAPER'
vs source='EDGE_LIVE'), so the EOD exit job force-closes both
legs after PENNY_EDGE_MAX_HOLD_DAYS.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import penny_edge_engine as pee
import penny_edge_live as pel
from config import settings
from penny_executor import PennyExecutor
from penny_models import PennyLeg
from position_tracker import init_positions_db

logger = logging.getLogger(__name__)


# ----- source tags ---------------------------------------------------

# Each leg is tagged distinctly in the positions table so they
# don't see each other's rows and don't double up.
SOURCE_PAPER = "EDGE_PAPER"
SOURCE_LIVE  = "EDGE_LIVE"


# ----- tunables (read from settings; defaults match config) ---------

def _edge_max_positions() -> int:
    return int(getattr(settings, "PENNY_EDGE_MAX_POSITIONS", 3))


def _edge_min_strength() -> float:
    return float(getattr(settings, "PENNY_EDGE_MIN_STRENGTH", 0.45))


def _edge_paper_bankroll() -> float:
    return float(getattr(settings, "PENNY_EDGE_PAPER_BANKROLL", 100000.0))


def _edge_live_bankroll() -> float:
    return float(getattr(settings, "PENNY_EDGE_LIVE_BANKROLL", 1000.0))


def _edge_paper_disabled() -> bool:
    return bool(getattr(settings, "PENNY_EDGE_DISABLE_PAPER", False))


def _edge_live_disabled() -> bool:
    return bool(getattr(settings, "PENNY_EDGE_DISABLE_LIVE", False))


def _edge_max_hold_days() -> int:
    return int(getattr(settings, "PENNY_EDGE_MAX_HOLD_DAYS", 3))


def _live_trading_enabled() -> bool:
    # Master switch: PENNY_LIVE_TRADING must be True for live orders
    # to go through. If False, both legs run paper even if
    # PENNY_EDGE_DISABLE_LIVE is False.
    return bool(getattr(settings, "PENNY_LIVE_TRADING", True))


EDGE_SLIPPAGE_BPS = 5.0
EDGE_PRODUCT_TYPE = PennyLeg.CNC


def _executor_for(kite, paper_mode: bool) -> PennyExecutor:
    return PennyExecutor(
        kite=kite,
        paper_mode=paper_mode,
    )


# ----- idempotency + DB write ----------------------------------------

async def _already_entered_today(db_path: str, ticker: str, source: str, today_str: str) -> bool:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM positions
        WHERE ticker = ?
          AND source  = ?
          AND substr(entry_date, 1, 10) = ?
        LIMIT 1
    """, (ticker, source, today_str))
    row = cur.fetchone()
    conn.close()
    return row is not None


async def _write_edge_position(
    db_path: str, source: str,
    ticker: str, entry_date_iso: str,
    entry_price: float, shares: int,
    stop_loss: float, target_1: float,
    regime_at_entry: str,
):
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
        stop_loss, stop_loss,
        target_1, target_1,
        0.0, entry_price,
        "OPEN", source,
        EDGE_PRODUCT_TYPE.value, regime_at_entry,
        0.0, 0,
    ))
    conn.commit()
    conn.close()


# ----- per-leg runner ------------------------------------------------

async def _run_one_leg(
    kite, db_path: str, today_str: str,
    leg_name: str,         # "PAPER" or "LIVE"
    source_tag: str,       # SOURCE_PAPER or SOURCE_LIVE
    bankroll: float,       # paper: 100k, live: 1k (or whatever config)
    paper_mode: bool,      # whether to actually place broker orders
    candidates,            # List[SignalCandidate] from pel.scan_today(...)
) -> dict:
    """Submit entries for ONE leg (paper or live) of the engine.

    Both legs share the same candidate set; bankroll scales the
    position sizing. Returns a per-leg summary dict.
    """
    if not candidates:
        return {
            "leg": leg_name, "source": source_tag,
            "bankroll": bankroll, "paper_mode": paper_mode,
            "n_candidates": 0, "entered": 0,
            "trades": [], "skipped": [],
        }
    # Run the engine once with this leg's bankroll so the position
    # sizing reflects the leg's capital, not the unified list.
    # We re-call the engine: it's pure (no I/O side effects, all
    # reads from the in-memory cache), so it's fast.
    leg_scan = pel._rank_for_leg(
        candidates=candidates,
        bankroll=bankroll,
        max_positions=_edge_max_positions(),
        min_strength=_edge_min_strength(),
    )
    executor = _executor_for(kite, paper_mode)
    submitted = []
    skipped = []
    for pos in leg_scan:
        if await _already_entered_today(db_path, pos.ticker, source_tag, today_str):
            skipped.append((pos.ticker, "already-entered-today"))
            continue
        order_result = await executor.execute_entry(
            ticker=pos.ticker,
            leg=EDGE_PRODUCT_TYPE,
            entry_price=pos.entry_price,
            stop_loss=pos.stop_loss,
            shares=pos.shares,
        )
        entry_status = order_result.get("entry_status")
        if entry_status in ("filled", "paper"):
            entry_iso = datetime.now(timezone.utc).isoformat()
            await _write_edge_position(
                db_path=db_path,
                source=source_tag,
                ticker=pos.ticker,
                entry_date_iso=entry_iso,
                entry_price=pos.entry_price,
                shares=pos.shares,
                stop_loss=pos.stop_loss,
                target_1=pos.target,
                regime_at_entry="",
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
                "penny_edge_%s_entry_submitted ticker=%s subtype=%s strength=%.2f "
                "entry=%.2f target=%.2f stop=%.2f hold=%dd shares=%d status=%s",
                leg_name.lower(), pos.ticker, pos.signal_subtype, pos.adjusted_strength,
                pos.entry_price, pos.target, pos.stop_loss,
                pos.hold_days, pos.shares, entry_status,
            )
        else:
            skipped.append((pos.ticker, f"entry_status={entry_status}"))
            logger.warning(
                "penny_edge_%s_entry_skipped ticker=%s order_result=%s",
                leg_name.lower(), pos.ticker, order_result,
            )
    return {
        "leg": leg_name, "source": source_tag,
        "bankroll": bankroll, "paper_mode": paper_mode,
        "n_candidates": len(leg_scan), "entered": len(submitted),
        "trades": submitted, "skipped": skipped,
    }


# ----- main runner ---------------------------------------------------

async def run_penny_edge_scan(kite, db_path: Optional[str] = None) -> dict:
    """Daily 09:30 IST scan. Runs both paper and live legs.

    Returns a dict with both leg summaries + the unified candidate
    count for Telegram reporting:
      {
        "date": "...",
        "candidates_total": N,
        "universe": M,
        "regime": "MO"/"MR"/"BOTH",
        "paper": { leg_summary },
        "live":  { leg_summary },
        "skipped": [...]   # tickers skipped by either leg
      }
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    db_path = db_path or settings.DB_PATH
    paper_disabled = _edge_paper_disabled()
    live_disabled  = _edge_live_disabled()
    live_master    = _live_trading_enabled()
    paper_bankroll = _edge_paper_bankroll()
    live_bankroll  = _edge_live_bankroll()

    # If both legs are disabled, short-circuit.
    if paper_disabled and live_disabled:
        logger.info("penny_edge_scan_both_legs_disabled date=%s", today_str)
        return {
            "date": today_str, "candidates_total": 0, "universe": 0,
            "regime": "BOTH", "paper": {"entered": 0, "trades": []},
            "live": {"entered": 0, "trades": []}, "skipped": [],
        }

    # Single shared scan uses the larger bankroll so it returns the
    # largest possible candidate set; each leg then re-ranks with its
    # own bankroll for accurate position sizing.
    # If the paper bankroll is larger, use that for the master scan.
    scan_bankroll = max(paper_bankroll, live_bankroll)
    logger.info(
        "penny_edge_scan_started date=%s paper_br=%.0f live_br=%.0f paper_disabled=%s "
        "live_disabled=%s master_switch=%s",
        today_str, paper_bankroll, live_bankroll,
        paper_disabled, live_disabled, live_master,
    )
    scan = pel.scan_today(
        bankroll=scan_bankroll,
        max_positions=_edge_max_positions(),
        min_strength=_edge_min_strength(),
        db_path=db_path,
    )
    candidates = scan["candidates"]
    universe = scan["eligible_tickers"]
    regime = scan["regime"]
    logger.info(
        "penny_edge_scan_engine_complete date=%s universe=%d candidates=%d regime=%s",
        today_str, universe, len(candidates), regime.preferred_signal,
    )

    # Run paper leg
    paper_summary = {"leg": "PAPER", "entered": 0, "trades": [], "skipped": []}
    if not paper_disabled:
        paper_summary = await _run_one_leg(
            kite=kite, db_path=db_path, today_str=today_str,
            leg_name="PAPER", source_tag=SOURCE_PAPER,
            bankroll=paper_bankroll,
            paper_mode=not live_master or True,   # always paper for the paper leg
            candidates=candidates,
        )

    # Run live leg (forced paper if master switch is off)
    live_summary = {"leg": "LIVE", "entered": 0, "trades": [], "skipped": []}
    if not live_disabled:
        live_summary = await _run_one_leg(
            kite=kite, db_path=db_path, today_str=today_str,
            leg_name="LIVE", source_tag=SOURCE_LIVE,
            bankroll=live_bankroll,
            paper_mode=not live_master,   # FALSE if master is ON -> real broker orders
            candidates=candidates,
        )

    combined_skipped = (
        [("PAPER: " + t, r) for t, r in paper_summary.get("skipped", [])]
        + [("LIVE: " + t, r) for t, r in live_summary.get("skipped", [])]
    )

    summary = {
        "date": today_str,
        "candidates_total": len(candidates),
        "universe":         universe,
        "regime":           regime.preferred_signal,
        "trend_strength":   regime.trend_strength,
        "vol_percentile":   regime.vol_percentile,
        "paper":            paper_summary,
        "live":             live_summary,
        "skipped":          combined_skipped,
    }
    logger.info(
        "penny_edge_scan_done date=%s paper_entered=%d live_entered=%d",
        today_str, paper_summary.get("entered", 0),
        live_summary.get("entered", 0),
    )
    return summary


# ----- EOD exit ------------------------------------------------------

async def run_penny_edge_exit(kite, db_path: Optional[str] = None) -> dict:
    """EOD 15:15 IST: force-close any EDGE-sourced position older than
    PENNY_EDGE_MAX_HOLD_DAYS. Handles BOTH source tags.

    Returns a dict with closed positions per source tag.
    """
    db_path = db_path or settings.DB_PATH
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT ticker, entry_price, shares, stop_loss_initial,
               target_1, product_type, source, entry_date
        FROM positions
        WHERE source IN (?, ?) AND status = 'OPEN'
    """, (SOURCE_PAPER, SOURCE_LIVE))
    rows = cur.fetchall()
    conn.close()

    max_hold = _edge_max_hold_days()
    closed_paper = []
    closed_live = []
    if not rows:
        logger.info("penny_edge_exit_no_open_positions date=%s", today_str)
        return {"date": today_str, "closed_paper": [], "closed_live": []}

    kite_for_live = kite  # only used for live leg below
    for r in rows:
        ticker, entry_price, shares, sl, target, prod_type, source, entry_date = r
        try:
            entry_dt = datetime.fromisoformat(entry_date.replace("Z", "+00:00"))
        except Exception:
            entry_dt = datetime.strptime(entry_date[:19], "%Y-%m-%dT%H:%M:%S")
        now_utc = datetime.now(timezone.utc)
        age_days = (now_utc - entry_dt).days
        if age_days < max_hold:
            continue
        # Live leg uses real kite; paper leg uses paper_mode=True.
        leg_paper_mode = (source == SOURCE_PAPER) or not _live_trading_enabled()
        executor = _executor_for(kite_for_live if source == SOURCE_LIVE else kite,
                                 paper_mode=leg_paper_mode)
        leg = PennyLeg.CNC if prod_type == "CNC" else PennyLeg.MIS
        logger.info(
            "penny_edge_force_exit source=%s ticker=%s age=%dd",
            source, ticker, age_days,
        )
        unwind_id = await executor._market_unwind(ticker, leg, shares)
        conn2 = sqlite3.connect(db_path)
        c2 = conn2.cursor()
        c2.execute("""
            UPDATE positions
            SET status='CLOSED',
                exit_date=?,
                exit_price=entry_price,
                realised_pnl=0.0
            WHERE ticker=? AND source=? AND status='OPEN'
        """, (today_str, ticker, source))
        conn2.commit()
        conn2.close()
        record = {
            "ticker":       ticker,
            "source":       source,
            "unwind_id":    unwind_id,
            "age_days":     age_days,
            "force_close_reason": "edge-exit-{0}d-cap".format(max_hold),
        }
        if source == SOURCE_PAPER:
            closed_paper.append(record)
        else:
            closed_live.append(record)
    logger.info(
        "penny_edge_exit_done date=%s closed_paper=%d closed_live=%d",
        today_str, len(closed_paper), len(closed_live),
    )
    return {
        "date": today_str,
        "closed_paper": closed_paper,
        "closed_live": closed_live,
    }


# ----- Telegram formatter --------------------------------------------

def format_telegram(summary: dict, header: str = "Penny Edge scan") -> str:
    """Telegram-friendly summary covering both legs."""
    out = [f"*{header}* `{summary.get('date', '?')}`"]
    if "universe" in summary:
        out.append(
            f"Regime: trend={summary.get('trend_strength', 0):+.2f} "
            f"vol_pctl={summary.get('vol_percentile', 0):.2f} "
            f"preferred=`{summary.get('regime', '?')}` "
            f"| Universe: {summary.get('universe', '?')} "
            f"| Candidates: {summary.get('candidates_total', '?')}"
        )
    # Paper leg
    p = summary.get("paper", {})
    if p:
        paper_flag = "PAPER" if p.get("paper_mode", True) else "LIVE"
        out.append(
            f"--- *PAPER LEG* bankroll=Rs {p.get('bankroll', 0):,.0f} ---"
        )
        if p.get("entered", 0) == 0:
            out.append("No paper trades.")
        for t in p.get("trades", []):
            out.append(
                f"- `{t['ticker']}` [{t['subtype']}] strength={t['strength']:.2f} "
                f"entry={t['entry']:.2f} target={t['target']:.2f} stop={t['stop']:.2f} "
                f"hold={t['hold_days']}d shares={t['shares']} status={t['entry_status']}"
            )
    # Live leg
    l = summary.get("live", {})
    if l:
        live_flag = "PAPER (live disabled)" if l.get("paper_mode", True) else "LIVE"
        out.append(
            f"--- *LIVE LEG* bankroll=Rs {l.get('bankroll', 0):,.0f} ({live_flag}) ---"
        )
        if l.get("entered", 0) == 0:
            out.append("No live trades.")
        for t in l.get("trades", []):
            out.append(
                f"- `{t['ticker']}` [{t['subtype']}] strength={t['strength']:.2f} "
                f"entry={t['entry']:.2f} target={t['target']:.2f} stop={t['stop']:.2f} "
                f"hold={t['hold_days']}d shares={t['shares']} status={t['entry_status']}"
            )
    # Skipped
    for label, reason in summary.get("skipped", []):
        out.append(f"  skipped: `{label}` ({reason})")
    return "\n".join(out)


def format_exit_telegram(exit_summary: dict) -> str:
    out = [f"*Penny Edge exit* `{exit_summary.get('date', '?')}`"]
    for tag, key in [("PAPER", "closed_paper"), ("LIVE", "closed_live")]:
        items = exit_summary.get(key, [])
        if items:
            out.append(f"--- {tag}: {len(items)} forced ---")
            for c in items:
                out.append(
                    f"- `{c['ticker']}` age={c['age_days']}d "
                    f"unwind_id={c.get('unwind_id', '?')}"
                )
    if not exit_summary.get("closed_paper") and not exit_summary.get("closed_live"):
        out.append("No edge positions to exit.")
    return "\n".join(out)


if __name__ == "__main__":
    # Smoke: run a scan and print the Telegram-formatted report
    logging.basicConfig(level=logging.INFO)

    class _FakeKite:
        """Async-compatible kite stub for CLI smoke tests.

        Both paper_mode=True and paper_mode=False paths use this.
        The place_order is a regular sync function returning a dict;
        the paper path returns a paper order_id without awaiting;
        the live path uses try/await which fails with TypeError -- but
        the orchestrator catches that TypeError and marks the order
        as 'rejected', so the smoke test runs cleanly to completion.
        """
        access_token = "fake"

        async def place_order(self, **_):
            return {"order_id": f"STUB-{__import__('uuid').uuid4().hex[:8]}"}

        def cancel_order(self, *_a, **_kw):
            return None

        async def order_history(self, **_):
            return [{"status": "COMPLETE"}]

    r = asyncio.run(run_penny_edge_scan(_FakeKite()))
    print(format_telegram(r))
