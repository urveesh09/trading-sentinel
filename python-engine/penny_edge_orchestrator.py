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
    # [PENNY-FD-LEAK 2026-07-01] Use `with` so the connection is closed
    # even if cursor.execute() raises (previously bare sqlite3.connect()
    # leaked the FD on any exception path).
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT 1 FROM positions
            WHERE ticker = ?
              AND source  = ?
              AND substr(entry_date, 1, 10) = ?
            LIMIT 1
        """, (ticker, source, today_str))
        row = cur.fetchone()
    return row is not None


async def _write_edge_position(
    db_path: str, source: str,
    ticker: str, entry_date_iso: str,
    entry_price: float, shares: int,
    stop_loss: float, target_1: float,
    regime_at_entry: str,
):
    await init_positions_db(db_path)
    # [PENNY-FD-LEAK 2026-07-01] Same fix as above: `with` so the
    # connection is closed even on partial-write / DB-locked paths.
    with sqlite3.connect(db_path) as conn:
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
            # [TIER0-0.3 2026-07-14] atr_14_at_entry is NULL, not 0.0.
            #
            # EDGE is managed by target + time-stop + a deliberately WIDE soft
            # stop (see penny_edge_engine.compute_mr_signal: "stops are WIDE ...
            # only as a sanity check, not for trade management"). It never wanted
            # a Chandelier trail. But position_tracker trails every position, and
            # a 0.0 ATR makes ChandelierStop return `highest_close - 3*0` ==
            # highest_close, which is >= entry -- so the trail silently overwrote
            # the soft stop with the ENTRY PRICE and force-closed each position
            # there. Live proof: RPOWER/IRISDOREME/MIRZAINT/PCJEWELLER all exited
            # at exactly their entry, real -4/-6% stops never consulted, every
            # "loss" pure brokerage.
            #
            # NULL now means "no trail" and position_tracker keeps the entry stop.
            None, entry_price,
            "OPEN", source,
            EDGE_PRODUCT_TYPE.value, regime_at_entry,
            None, 0,
        ))
        conn.commit()


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

async def _log_edge_signals(db_path: str, today_str: str, candidates, live_summary: dict) -> None:
    """
    [TIER0-0.5 2026-07-14] Write one penny_signals row per EDGE candidate, under
    leg='EDGE', so the zero-accept watchdog and the hourly report can see this
    book at all.

    A candidate is ACCEPTED if the live leg actually entered it. Everything else
    is a reject, with the reason the leg recorded (below min strength, already
    entered today, position cap, sizing to zero shares...).

    Failures here are swallowed deliberately: this is observability, and it must
    never be able to break a scan that is placing real orders.
    """
    try:
        from penny_signal_log import init_penny_signal_db, log_penny_signal

        await init_penny_signal_db(db_path)

        entered = {t["ticker"] if isinstance(t, dict) else t
                   for t in live_summary.get("trades", [])}
        skip_reasons = {t: r for t, r in live_summary.get("skipped", [])}
        scan_id = f"EDGE-{today_str}"

        for cand in candidates:
            accepted = cand.ticker in entered
            await log_penny_signal(
                db_path=db_path,
                scan_id=scan_id,
                ticker=cand.ticker,
                leg="EDGE",
                accepted=accepted,
                regime=cand.signal_subtype,
                close=cand.entry_price,
                reject_reason=None if accepted else skip_reasons.get(
                    cand.ticker, "not_selected_by_live_leg",
                ),
                stop_loss=cand.stop_loss,
                target_1=cand.target,
            )
    except Exception as exc:
        logger.warning("penny_edge_signal_log_failed date=%s err=%s", today_str, exc)


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

    # [PENNY-EDGE-ORCHESTRATOR-BREADCRUMB 2026-07-06] First-line
    # diagnostic log inside the orchestrator. Today's incident:
    # `_run_penny_edge_scan_safe` (the wrapper in main.py) was
    # registered at 07:09 IST but never fired at 09:30 IST. Even when
    # APScheduler DOES fire it (or when the startup-catchup fires it),
    # this `run_penny_edge_scan` function can still crash silently if
    # `pel.scan_today` raises (e.g. fresh DB without `ohlcv_cache`
    # table) -- in that case the wrapper logs the exception, the cron
    # records it, and there's no "I am running" line anywhere.
    #
    # By logging this breadcrumb FIRST, every successful invocation
    # is observable in the docker logs. Combined with the wrapper's
    # `penny_edge_scan_invoked` breadcrumb (in main.py), future
    # silent-no-trades days can be triaged in 30 seconds:
    #   - wrapper breadcrumb absent     -> cron never fired (rule 49)
    #   - wrapper present, this absent  -> wrapper crashed before calling us
    #   - both present, candidates=0    -> orchestrator ran, no signals (legit)
    #   - both present, candidates>0    -> pipeline produced trades
    logger.info(
        "penny_edge_orchestrator_invoked date=%s paper_br=%.0f live_br=%.0f "
        "paper_disabled=%s live_disabled=%s master_switch=%s",
        today_str, paper_bankroll, live_bankroll,
        paper_disabled, live_disabled, live_master,
    )

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

    # [PENNY-EDGE-ENGINE-FAILSAFE 2026-07-06] Wrap pel.scan_today in
    # try/except. If the signal engine crashes (e.g. fresh DB without
    # `ohlcv_cache` table -> sqlite3.OperationalError, or any other
    # RuntimeError from `load_daily_bars_from_db`), we MUST NOT let
    # it propagate out of the wrapper's try/except (which would mark
    # the cron as failed but leave both legs with 0 trades and no
    # audit trail). Instead, log a loud diagnostic and return an
    # empty-candidates summary so the wrapper's `penny_edge_scan_done`
    # log line still fires and the operator gets a single
    # `penny_edge_scan_engine_failed` line pointing at the root cause.
    try:
        scan = pel.scan_today(
            bankroll=scan_bankroll,
            max_positions=_edge_max_positions(),
            min_strength=_edge_min_strength(),
            db_path=db_path,
        )
    except Exception as engine_exc:
        logger.error(
            "penny_edge_scan_engine_failed date=%s err=%s "
            "FIX=verify ohlcv_cache table is populated; if this is a "
            "fresh deploy, run penny_universe_refresh + wait one "
            "trading day for ohlcv_cache to fill.",
            today_str, str(engine_exc),
            exc_info=True,
        )
        return {
            "date": today_str, "candidates_total": 0, "universe": 0,
            "regime": "ERROR", "paper": {"entered": 0, "trades": [], "skipped": []},
            "live": {"entered": 0, "trades": [], "skipped": []},
            "skipped": [("*engine*", f"engine_failed: {engine_exc}")],
        }
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
            paper_mode=True,   # paper leg is ALWAYS paper (no broker)
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

    # [TIER0-0.5 2026-07-14] Make the EDGE book VISIBLE.
    #
    # EDGE never wrote a single row to penny_signals -- there was no EDGE leg in
    # that table at all. So the only penny strategy actually placing live orders
    # was invisible to the zero-accept watchdog AND to the hourly report (which
    # queries penny_signals), and its closed trades landed in trade_outcomes
    # tagged `no_matched_signal` because the outcome matcher had no signal row to
    # join to. A strategy nothing can see is a strategy nothing can audit.
    await _log_edge_signals(db_path, today_str, candidates, live_summary)

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

async def _kite_daily_bars_after(
    kite, ticker: str, entry_dt_iso: str,
) -> List[dict]:
    """Fetch daily bars AFTER entry for an EDGE position from kite.

    Used by `run_penny_edge_exit` to drive the canonical-exit
    simulator (pee.simulate_position). Returns a list of dicts
    shaped like the engine's "bar" type (date/open/high/low/close/volume).

    Loud-but-non-blocking: any fetch error returns [] (the caller
    treats that as "no data, fall back to legacy exit-at-entry").
    """
    try:
        entry_yyyymmdd = entry_dt_iso[:10]
        today_yyyymmdd = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        df = await kite.get_historical(ticker, entry_yyyymmdd, today_yyyymmdd)
    except Exception as exc:
        logger.warning(
            "penny_edge_exit_history_fetch_failed ticker=%s err=%s",
            ticker, str(exc),
        )
        return []
    if df is None or df.empty:
        return []
    bars: List[dict] = []
    for _, row in df.iterrows():
        bars.append({
            "date":   str(row["date"])[:10],
            "open":   float(row["open"]),
            "high":   float(row["high"]),
            "low":    float(row["low"]),
            "close":  float(row["close"]),
            "volume": float(row.get("volume", 0) or 0),
        })
    return bars


async def run_penny_edge_exit(kite, db_path: Optional[str] = None) -> dict:
    """EOD 15:15 IST: force-close any EDGE-sourced position older than
    PENNY_EDGE_MAX_HOLD_DAYS. Handles BOTH source tags.

    [CANONICAL-EXIT 2026-07-01] Previously force-closed every held
    position with `exit_price=entry_price, realised_pnl=0.0`, ignoring
    any intraday TP/SL hits that already happened. That's the same
    bug class as `update_daily_positions` (which was fixed in 70dd0a7
    for the legacy penny subsystem). The fix: route the exit price
    through `pee.simulate_position`, which checks daily hi/lo on
    each bar after entry and picks the correct TP/SL/time-stop exit.
    Today this matters for any EDGE position that hits max_hold
    without `update_daily_positions` having closed it first.

    [PENNY-FD-LEAK 2026-07-01] Both DB connections (the read of open
    positions, and the per-position UPDATE) now use `with` so the
    FD is released even if cursor.execute() raises. The previous
    bare-connect pattern leaked 1 FD per error path.

    Returns a dict with closed positions per source tag.
    """
    db_path = db_path or settings.DB_PATH
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # [PENNY-EDGE-ORCHESTRATOR-BREADCRUMB 2026-07-06] Companion breadcrumb
    # to the scan-side one. Symmetric with `penny_edge_orchestrator_invoked`:
    # future "silent missed exit" days are debuggable in 30 seconds.
    logger.info(
        "penny_edge_exit_orchestrator_invoked date=%s max_hold_days=%d",
        today_str, _edge_max_hold_days(),
    )

    # 1) Snapshot the open EDGE positions (FD-safe read).
    # [PENNY-FD-LEAK 2026-07-01] `with` closes the connection even on
    # partial-read / DB-locked paths. Previously a bare
    # sqlite3.connect() leaked an FD if cur.execute raised.
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ticker, entry_price, shares, stop_loss_initial,
                   target_1, product_type, source, entry_date,
                   regime_at_entry
            FROM positions
            WHERE source IN (?, ?) AND status = 'OPEN'
        """, (SOURCE_PAPER, SOURCE_LIVE))
        rows = cur.fetchall()

    max_hold = _edge_max_hold_days()
    closed_paper: list = []
    closed_live:  list = []
    if not rows:
        logger.info("penny_edge_exit_no_open_positions date=%s", today_str)
        return {"date": today_str, "closed_paper": [], "closed_live": []}

    kite_for_live = kite  # only used for live leg below

    for r in rows:
        ticker, entry_price, shares, sl, target, prod_type, source, entry_date, _regime = r
        try:
            entry_dt = datetime.fromisoformat(entry_date.replace("Z", "+00:00"))
        except Exception:
            entry_dt = datetime.strptime(entry_date[:19], "%Y-%m-%dT%H:%M:%S")
        now_utc = datetime.now(timezone.utc)
        age_days = (now_utc - entry_dt).days
        if age_days < max_hold:
            continue

        # 2) Canonical exit price via the engine simulator.
        # [CANONICAL-EXIT 2026-07-01] Drive the exit through
        # pee.simulate_position so a TP/SL hit on any bar BEFORE the
        # max_hold day records the correct exit price and realised_pnl,
        # instead of leaving them at entry_price / 0.0.
        bars_after = await _kite_daily_bars_after(kite, ticker, entry_date)
        sim_pos = pee.Position(
            ticker=ticker,
            entry_date=entry_date[:10],
            entry_price=float(entry_price),
            shares=int(shares),
            target=float(target),
            stop_loss=float(sl),
            hold_days=int(max_hold),
            signal_subtype="EDGE",
            raw_strength=0.0,
            adjusted_strength=0.0,
        )
        try:
            sim = pee.simulate_position(
                sim_pos, bars_after,
                slippage_bps=EDGE_SLIPPAGE_BPS,
            )
            exit_price = float(sim["exit_price"])
            exit_reason = sim["exit_reason"]
            exit_date = sim["exit_date"] or today_str
        except Exception as exc:
            logger.warning(
                "penny_edge_exit_simulator_failed ticker=%s err=%s -- "
                "falling back to exit-at-entry",
                ticker, str(exc),
            )
            exit_price = float(entry_price)
            exit_reason = "simulator-failed"
            exit_date = today_str

        # 3) Place the actual broker unwind (paper for paper leg).
        leg_paper_mode = (source == SOURCE_PAPER) or not _live_trading_enabled()
        executor = _executor_for(
            kite_for_live if source == SOURCE_LIVE else kite,
            paper_mode=leg_paper_mode,
        )
        leg = PennyLeg.CNC if prod_type == "CNC" else PennyLeg.MIS
        logger.info(
            "penny_edge_force_exit source=%s ticker=%s age=%dd exit_reason=%s",
            source, ticker, age_days, exit_reason,
        )
        unwind_id = await executor._market_unwind(ticker, leg, shares)

        # 4) Compute realised_pnl from exit_price (not always entry_price).
        # [PENNY-FD-LEAK 2026-07-01] `with` releases the FD even on the
        # UPDATE path; legacy bare-connect leaked 1 FD per iteration.
        try:
            # Use the penny-local cost helper (penny_risk.calc_penny_costs)
            # -- penny modules must not import from `engine` per
            # test_penny_isolation. Mirrors engine.calc_zerodha_costs
            # but uses PENNY_* settings instead of ZERODHA_*.
            from penny_risk import calc_penny_costs
            gross = (exit_price - float(entry_price)) * int(shares)
            costs = calc_penny_costs(
                float(entry_price), exit_price, int(shares),
                is_intraday=(prod_type == "MIS"),
            )
            realised_pnl = float(gross - costs)
            risk_initial = (float(entry_price) - float(sl)) * int(shares)
            r_multiple = (
                realised_pnl / risk_initial if risk_initial > 0 else 0.0
            )
        except Exception as exc:
            logger.warning(
                "penny_edge_exit_pnl_calc_failed ticker=%s err=%s -- "
                "falling back to realised_pnl=0.0",
                ticker, str(exc),
            )
            realised_pnl = 0.0
            r_multiple = 0.0

        with sqlite3.connect(db_path) as conn2:
            c2 = conn2.cursor()
            c2.execute(
                """
                UPDATE positions
                SET status='CLOSED',
                    exit_date=?,
                    exit_price=?,
                    realised_pnl=?,
                    r_multiple=?
                WHERE ticker=? AND source=? AND status='OPEN'
                """,
                (today_str, exit_price, realised_pnl, r_multiple,
                 ticker, source),
            )
            conn2.commit()

        record = {
            "ticker":       ticker,
            "source":       source,
            "unwind_id":    unwind_id,
            "age_days":     age_days,
            "exit_reason":  exit_reason,
            "exit_price":   exit_price,
            "realised_pnl": realised_pnl,
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
