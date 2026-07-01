"""
[OPERATOR-STATUS 2026-06-25] Cross-subsystem operator view.

Phase C components:
  - /status: one-screen all-systems view (bankroll per pool, deployed
    per pool, today's P&L per pool, regime per pool, halt state)
  - /performance: text-format of the /performance HTTP endpoint for
    Telegram. Strict-separation stance preserved (nifty-only by
    default; penny breakdown surfaced separately).
  - 16:00 IST end-of-day digest: single Telegram message summarising
    both pools (deferred to scheduler wiring; the build function here
    is reusable)
  - Hourly mid-session heartbeat: compact "all 3 subsystems OK"
    line. Auto-silences when nothing changed.

DESIGN PRINCIPLES (operator-mandated 2026-06-25):
1. READ-ONLY. No state mutation in any of these commands.
2. Strict-separation preserved: bankroll_ledger sources are queried
   individually (SYSTEM, MOMENTUM, PENNY). Nothing aggregates across
   pools except the operator-facing view.
3. Telegram-friendly formatting: compact (<1500 chars), clear sections.
4. Fail-open: any error returns a graceful message, never crashes.
5. /status is the operator's "all systems" single-screen view. It is
   intentionally heavier than /health (which is the diagnostic dump)
   -- /status is the *summary* meant for frequent pulls.
"""
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---- DB accessors ----------------------------------------------------

def _today_pnl_by_source(db_path: str) -> Dict[str, float]:
    """Sum today's TRADE_CLOSED rows grouped by source.
    Returns {source: total_pnl} with at least one entry per known source."""
    today = datetime.now(timezone.utc).date().isoformat()
    out: Dict[str, float] = {"PENNY": 0.0, "SYSTEM": 0.0, "MOMENTUM": 0.0}
    try:
        with sqlite3.connect(db_path) as con:
            cur = con.execute(
                "SELECT source, COALESCE(SUM(pnl), 0.0) FROM bankroll_ledger "
                "WHERE event_type='TRADE_CLOSED' AND DATE(timestamp)=? "
                "GROUP BY source",
                (today,),
            )
            for source, pnl in cur.fetchall():
                out[source] = float(pnl)
    except sqlite3.Error as e:
        logger.warning("status_today_pnl_query_failed error=%s", str(e))
    return out


def _open_count_by_source(db_path: str) -> Dict[str, int]:
    """Count open positions per source. Returns {source: count}."""
    out = {"PENNY": 0, "SYSTEM": 0, "MOMENTUM": 0}
    try:
        with sqlite3.connect(db_path) as con:
            cur = con.execute(
                "SELECT source, COUNT(*) FROM positions "
                "WHERE status IN ('OPEN', 'CLOSED_T1') "
                "GROUP BY source"
            )
            for source, count in cur.fetchall():
                if source in out:
                    out[source] = int(count)
    except sqlite3.Error as e:
        logger.warning("status_open_count_query_failed error=%s", str(e))
    return out


# ---- /status builder -------------------------------------------------

async def build_status_snapshot(db_path: str) -> Dict[str, Any]:
    """Build the cross-subsystem status snapshot.

    Combines: bankroll per pool, today's P&L per pool, open positions
    per pool, regime per pool, halt state, alert count (positions
    near SL, etc.).
    """
    import asyncio

    # Bankroll per pool
    nifty_bal: Optional[float] = None
    try:
        from performance import nifty_bankroll
        nifty_bal = float(await nifty_bankroll(db_path))
    except Exception as e:
        logger.warning("status_nifty_bankroll_failed error=%s", str(e))

    # Today's P&L by source
    today_by_source = _today_pnl_by_source(db_path)

    # Open positions by source
    open_by_source = _open_count_by_source(db_path)

    # Regime per pool (lazy main import)
    penny_regime = "UNKNOWN"
    nifty_regime = "UNKNOWN"
    halted = False
    halt_reasons: list = []
    try:
        import main as _main
        pre = getattr(_main, "_penny_regime_engine", None)
        if pre is not None and pre.today_regime is not None:
            penny_regime = pre.today_regime.value
        nifty_regime = getattr(_main, "market_regime", "UNKNOWN")
    except Exception as e:
        logger.warning("status_regime_query_failed error=%s", str(e))

    # Halt state
    try:
        from performance import check_circuit_breakers
        halted, halt_reasons = await check_circuit_breakers(db_path)
    except Exception as e:
        logger.warning("status_circuit_query_failed error=%s", str(e))

    # Penny bankroll is approximated as the *initial* penny pool (2500)
    # plus PENNY P&L today. This is a rough estimate; the daily
    # attribution job has the full picture.
    penny_pnl = today_by_source.get("PENNY", 0.0)
    penny_bal = 2500.0 + penny_pnl  # assume the penny pool is 2500

    # Nifty today = SYSTEM + MOMENTUM
    nifty_pnl_today = today_by_source.get("SYSTEM", 0.0) + today_by_source.get("MOMENTUM", 0.0)

    return {
        "penny": {
            "regime": penny_regime,
            "balance_estimate": penny_bal,
            "pnl_today": penny_pnl,
            "open_positions": open_by_source.get("PENNY", 0),
        },
        "nifty": {
            "market_regime": nifty_regime,
            "balance": nifty_bal,
            "pnl_today": nifty_pnl_today,
            "open_positions": open_by_source.get("SYSTEM", 0) + open_by_source.get("MOMENTUM", 0),
        },
        "halted": halted,
        "halt_reasons": halt_reasons,
        "by_source_today": today_by_source,
    }


# ---- /status formatter -----------------------------------------------

def format_status(snap: Dict[str, Any]) -> str:
    """Compact Telegram-ready status (<1500 chars)."""
    now = datetime.now(timezone.utc).astimezone()
    hh, mm = now.hour, now.minute

    lines = [f"System status ({hh:02d}:{mm:02d} IST)"]
    if snap["halted"]:
        reasons = "; ".join(snap["halt_reasons"][:3])
        more = f" (+{len(snap['halt_reasons'])-3} more)" if len(snap["halt_reasons"]) > 3 else ""
        lines.append(f"⚠ HALTED: {reasons}{more}")

    p = snap["penny"]
    p_sign = "+" if p["pnl_today"] >= 0 else ""
    lines.append(
        f"Penny ({p['regime']}): Rs {p['balance_estimate']:.0f} (est) | "
        f"today {p_sign}Rs {p['pnl_today']:.0f} | open={p['open_positions']}"
    )

    n = snap["nifty"]
    n_bal_str = f"Rs {n['balance']:.0f}" if n["balance"] is not None else "n/a"
    n_sign = "+" if n["pnl_today"] >= 0 else ""
    lines.append(
        f"Nifty ({n['market_regime']}): {n_bal_str} | "
        f"today {n_sign}Rs {n['pnl_today']:.0f} | open={n['open_positions']}"
    )

    return "\n".join(lines)


# ---- /performance formatter -----------------------------------------

def format_performance(perf: Dict[str, Any]) -> str:
    """Format the /performance HTTP response as a Telegram message.

    Strict-separation stance preserved: this is the Nifty view.
    Penny attribution lives in /penny attribution (T3-A).
    """
    try:
        total = perf.get("total_trades", 0)
        wins = perf.get("winning_trades", 0)
        losses = perf.get("losing_trades", 0)
        win_rate = perf.get("win_rate_pct", 0.0)
        avg_r = perf.get("avg_r_multiple", 0.0)
        realised = perf.get("total_realised_pnl", 0.0)
        unrealised = perf.get("unrealised_pnl", 0.0)
        r_total = realised + unrealised
        sign = "+" if r_total >= 0 else ""
        return (
            f"Performance (Nifty subsystem)\n"
            f"Trades: {total} (W:{wins} L:{losses}) | Win rate: {win_rate:.1f}%\n"
            f"Avg R: {avg_r:+.2f}\n"
            f"Realised: {sign}Rs {realised:.0f} | Unrealised: {('+' if unrealised >= 0 else '')}Rs {unrealised:.0f}\n"
            f"Total: {sign}Rs {r_total:.0f}\n"
            f"\n"
            f"Note: Penny attribution is at /penny attribution (T3-A)."
        )
    except Exception as e:
        return f"Performance: error formatting ({type(e).__name__})"


# ---- end-of-day digest ----------------------------------------------

def format_eod_digest(snap: Dict[str, Any]) -> str:
    """End-of-day digest for the 16:00 IST scheduled job.

    One Telegram message: both pools' P&L, open positions, regimes.
    Designed to be the LAST thing the operator sees before signing off.
    """
    now = datetime.now(timezone.utc).astimezone()
    hh, mm = now.hour, now.minute
    lines = [f"End-of-day digest ({hh:02d}:{mm:02d} IST)"]

    p = snap["penny"]
    p_sign = "+" if p["pnl_today"] >= 0 else ""
    lines.append(
        f"Penny: {p_sign}Rs {p['pnl_today']:.0f} across {p['open_positions']} "
        f"still-open positions"
    )

    n = snap["nifty"]
    n_sign = "+" if n["pnl_today"] >= 0 else ""
    lines.append(
        f"Nifty: {n_sign}Rs {n['pnl_today']:.0f} across "
        f"{n['open_positions']} still-open positions"
    )

    lines.append(
        f"Regimes (close): penny={p['regime']}, nifty={n['market_regime']}"
    )

    if snap["halted"]:
        reasons = "; ".join(snap["halt_reasons"][:3])
        lines.append(f"⚠ Day ended HALTED: {reasons}")

    lines.append("\n-- that's it for today --")
    return "\n".join(lines)


# ---- /status + /performance cmd surface ------------------------------

def cmd_status(db_path: str) -> str:
    """Telegram /status command. Cross-subsystem one-screen view."""
    try:
        from penny_health import build_health_snapshot_sync
        # build_status_snapshot uses async DB; use sync wrapper via
        # asyncio.run for the Telegram path (test context).
        import asyncio
        snap = asyncio.run(build_status_snapshot(db_path))
        return format_status(snap)
    except Exception as e:
        return f"Status: error reading ({type(e).__name__})"


def cmd_performance(db_path: str) -> str:
    """Telegram /performance command. Nifty subsystem only (strict-separation).

    [AUDIT-FIX-2.6 2026-06-25] Now calls the shared async helper
    `compute_performance_report(db_path)` directly (which the HTTP
    route also calls). Pre-fix this routed through fastapi.TestClient
    to hit the /performance HTTP route, which was awkward and broke
    in some test contexts where the FastAPI app wasn't importable.
    """
    try:
        import asyncio
        from main import compute_performance_report
        perf = asyncio.run(compute_performance_report(db_path))
        return format_performance(perf.model_dump())
    except Exception as e:
        return f"Performance: error reading ({type(e).__name__})"


# [ASYNC-SYNC-SPLIT 2026-07-01] cmd_eod_digest is reached from TWO
# contexts: (1) the Telegram cmd handler (sync, in any test context or
# CLI smoke), and (2) main._run_penny_eod_digest (async, in the running
# APScheduler event loop). Calling asyncio.run() from inside a running
# event loop raises RuntimeError("asyncio.run() cannot be called from a
# running event loop"), so the cron path was silently failing every
# 16:00 IST. The fix: split into the canonical async core + sync
# wrapper. Both paths now use the same code path through
# build_status_snapshot, with the only difference being whether the
# sync caller wraps it in asyncio.run() or the async caller awaits
# it directly. See skill/references/sentinel-bugs.md "Async/sync split
# for FastAPI handlers + sync callers" for the worked recipe.


async def build_eod_digest_snapshot_async(db_path: str) -> Dict[str, Any]:
    """Async core for cmd_eod_digest. Returns the raw status snapshot."""
    return await build_status_snapshot(db_path)


def build_eod_digest_snapshot_sync(db_path: str) -> Dict[str, Any]:
    """Sync wrapper for Telegram callers and CLI smoke tests."""
    import asyncio
    return asyncio.run(build_eod_digest_snapshot_async(db_path))


def cmd_eod_digest(db_path: str) -> str:
    """Telegram /eod command (and 16:00 IST scheduled job payload).

    For cron callers running inside an asyncio event loop, use
    `await build_eod_digest_snapshot_async(db_path)` directly and pass
    the result through `format_eod_digest()` instead -- calling this
    sync wrapper from a running loop raises RuntimeError.
    """
    try:
        snap = build_eod_digest_snapshot_sync(db_path)
        return format_eod_digest(snap)
    except Exception as e:
        return f"EOD digest: error reading ({type(e).__name__})"