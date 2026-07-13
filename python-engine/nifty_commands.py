"""
[NIFTY-COMMANDS 2026-06-25] Read-only Telegram command handlers for the
Nifty subsystem (swing + momentum).

DESIGN PRINCIPLES (operator-mandated 2026-06-25):
1. INFORMATION-ONLY. Per explicit operator directive, no /nifty command
   modifies state, executes trades, or affects signal evaluation.
   Read-only queries only. To skip a ticker or close a position,
   use the HTTP endpoints (POST /positions/close) or the inline
   callback buttons on signal alerts.
2. Read straight from the python-engine module-level globals
   (current_signals, current_momentum_signals, market_regime, last_run).
   These are updated by the existing scanner loops; no extra DB reads
   except for the bankroll/circuit-breaker queries which already have
   helper functions.
3. Compact Telegram format (<1000 chars per reply, often much less).
4. Fail-open: any error returns a "could not read X" message, never
   a crash.

PUBLIC API (called by main.py /nifty/command/{cmd} endpoint):
  cmd_nifty_stats(db_path)      -> bankroll, deployed, today's P&L
  cmd_nifty_swing()             -> list top 5 swing signals
  cmd_nifty_momentum()          -> list top 5 momentum signals
  cmd_nifty_regime()            -> current market_regime + age
  cmd_nifty_circuit(db_path)    -> halted? reasons? peak bankroll?
  cmd_nifty_help()              -> command list
  dispatch(cmd, args, db_path)  -> top-level router
"""
import logging
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---- helpers: lazy access to main module globals --------------------

def _get_globals():
    """Lazy import main to access module-level state. Avoids circular
    import at module load time."""
    import main as _main
    return _main


def _format_pnl(pnl: Optional[float], bankroll: float) -> str:
    """Format a P&L value with sign and Rs."""
    if pnl is None:
        return "n/a"
    sign = "+" if pnl >= 0 else ""
    util_pct = (pnl / bankroll * 100) if bankroll else 0
    return f"{sign}Rs {pnl:.0f} ({util_pct:+.1f}% of bankroll)"


def _today_pnl_penny_and_nifty(db_path: str) -> tuple:
    """Sum today's TRADE_CLOSED rows from bankroll_ledger, partitioned
    by source. Returns (penny_pnl, nifty_pnl)."""
    today = datetime.now(timezone.utc).date().isoformat()
    penny_pnl = 0.0
    nifty_pnl = 0.0
    try:
        with sqlite3.connect(db_path) as con:
            cur = con.execute(
                "SELECT source, COALESCE(SUM(pnl), 0.0) FROM bankroll_ledger "
                "WHERE event_type='TRADE_CLOSED' AND DATE(timestamp)=? "
                "GROUP BY source",
                (today,),
            )
            for source, pnl in cur.fetchall():
                if source == "PENNY":
                    penny_pnl = float(pnl)
                elif source in ("SYSTEM", "MOMENTUM"):
                    nifty_pnl += float(pnl)
    except sqlite3.Error as e:
        logger.warning("nifty_cmd_today_pnl_query_failed error=%s", str(e))
    return penny_pnl, nifty_pnl


# ---- individual commands --------------------------------------------

def cmd_nifty_help() -> str:
    return (
        "Nifty commands (read-only, no execution):\n"
        "/nifty stats - bankroll, deployed, today's P&L\n"
        "/nifty swing - list top swing signals (live)\n"
        "/nifty momentum - list top momentum signals (live)\n"
        "/nifty regime - current market regime + age\n"
        "/nifty circuit - circuit-breaker state (halted? why? peak?)\n"
        "/nifty help - this message"
    )


def cmd_nifty_stats(db_path: str) -> str:
    """Compact Nifty-subsystem snapshot (swing + momentum combined).

    Uses nifty_bankroll() which excludes penny (strict-separation).
    """
    try:
        from performance import nifty_bankroll
        from position_tracker import get_open_positions
        import asyncio
        is_live = False  # could pull from settings; "NIFTY" label is enough
        bankroll = asyncio.run(nifty_bankroll(db_path))
        # Deployed = sum of entry_price * shares for Nifty-subsystem positions.
        # [ROADMAP-4.3 2026-07-13] On failure this used to silently report
        # "Deployed: Rs 0 (0.0% util)" -- indistinguishable from a genuinely
        # empty book, and the exact number an operator would use to justify
        # deploying more capital. Say "unknown" instead, and log.
        deployed = 0.0
        deployed_known = True
        try:
            open_pos = asyncio.run(get_open_positions(db_path))
            for p in open_pos:
                # Strict-separation: skip penny rows.
                if p.get("source") == "PENNY":
                    continue
                ep = float(p.get("entry_price") or 0.0)
                sh = int(p.get("shares") or 0)
                deployed += ep * sh
        except Exception as e:
            deployed_known = False
            logger.error("nifty_cmd_stats_deployed_failed error=%s", str(e))

        if deployed_known:
            util_pct = (deployed / bankroll * 100) if bankroll else 0
            deployed_line = f"Deployed: Rs {deployed:.0f} ({util_pct:.1f}% util)"
        else:
            deployed_line = "Deployed: UNKNOWN (position read failed -- see logs)"

        penny_pnl, nifty_pnl = _today_pnl_penny_and_nifty(db_path)
        return (
            f"Nifty stats\n"
            f"Bankroll: Rs {bankroll:.0f}\n"
            f"{deployed_line}\n"
            f"Today: {_format_pnl(nifty_pnl, bankroll)}\n"
            f"  (penny today: {_format_pnl(penny_pnl, bankroll if bankroll else 1)})\n"
            f"Mode: {'LIVE' if is_live else 'PAPER'}"
        )
    except Exception as e:
        return f"Nifty stats: error reading ({type(e).__name__})"


def cmd_nifty_swing() -> str:
    """List top swing signals by score. Read-only."""
    try:
        m = _get_globals()
        signals = getattr(m, "current_signals", []) or []
        if not signals:
            return "Nifty swing: no active signals."
        # Sort by score desc, take top 5.
        sorted_sigs = sorted(signals, key=lambda s: getattr(s, "score", 0), reverse=True)[:5]
        lines = [f"Nifty swing ({len(signals)} active, top 5):"]
        for s in sorted_sigs:
            # OpenPosition/Signal objects have ticker, score, close, sl,
            # t1, t2. Use getattr to be robust to schema drift.
            ticker = getattr(s, "ticker", "?")
            score = getattr(s, "score", 0)
            close = getattr(s, "close", 0.0)
            sl = getattr(s, "stop_loss", 0.0)
            t1 = getattr(s, "target_1", 0.0)
            lines.append(
                f"  {ticker} score={score} entry={close:.2f} "
                f"sl={sl:.2f} t1={t1:.2f}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Nifty swing: error reading ({type(e).__name__})"


def cmd_nifty_momentum() -> str:
    """List top momentum signals by score. Read-only."""
    try:
        m = _get_globals()
        signals = getattr(m, "current_momentum_signals", []) or []
        if not signals:
            return "Nifty momentum: no active signals."
        sorted_sigs = sorted(signals, key=lambda s: getattr(s, "score", 0), reverse=True)[:5]
        lines = [f"Nifty momentum ({len(signals)} active, top 5):"]
        for s in sorted_sigs:
            ticker = getattr(s, "ticker", "?")
            score = getattr(s, "score", 0)
            close = getattr(s, "close", 0.0)
            sl = getattr(s, "stop_loss", 0.0)
            t1 = getattr(s, "target_1", 0.0)
            lines.append(
                f"  {ticker} score={score} entry={close:.2f} "
                f"sl={sl:.2f} t1={t1:.2f}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Nifty momentum: error reading ({type(e).__name__})"


def cmd_nifty_regime() -> str:
    """Current Nifty market regime + how long it's been set.

    The market_regime is computed by the Nifty scanner's regime engine
    (separate from penny's regime). The text is one of:
    BULL / CAUTION / BEAR_RS_ONLY / UNKNOWN (per models.market_regime).
    """
    try:
        m = _get_globals()
        regime = getattr(m, "market_regime", "UNKNOWN")
        last_run = getattr(m, "last_run", None)
        if last_run is None:
            age_str = "never computed"
        else:
            now_utc = datetime.now(timezone.utc)
            # Both should be tz-aware. last_run is set via datetime.now(UTC).
            if last_run.tzinfo is None:
                # Back-compat: assume UTC if naive.
                age_dt = last_run.replace(tzinfo=timezone.utc)
            else:
                age_dt = last_run
            age_min = (now_utc - age_dt).total_seconds() / 60
            if age_min < 60:
                age_str = f"{age_min:.0f} min ago"
            elif age_min < 60 * 24:
                age_str = f"{age_min/60:.1f} hours ago"
            else:
                age_str = f"{age_min/1440:.1f} days ago"
        return f"Nifty market regime: {regime} (last computed: {age_str})"
    except Exception as e:
        return f"Nifty regime: error reading ({type(e).__name__})"


def cmd_nifty_circuit(db_path: str) -> str:
    """Circuit-breaker state: halted? reasons? peak bankroll?"""
    try:
        from performance import check_circuit_breakers
        import asyncio
        halted, reasons = asyncio.run(check_circuit_breakers(db_path))
        if not halted:
            return "Nifty circuit: OK (no halt)"
        # Surface the first 3 reasons (full list could be long).
        rstr = "; ".join(reasons[:3])
        more = f" (+{len(reasons)-3} more)" if len(reasons) > 3 else ""
        return f"Nifty circuit: HALTED\nReasons: {rstr}{more}"
    except Exception as e:
        return f"Nifty circuit: error reading ({type(e).__name__})"


# ---- top-level dispatch ---------------------------------------------

def dispatch(cmd: str, args: str, db_path: str) -> str:
    """Route a /nifty <subcommand> to the right handler.

    Per operator-mandated constraint (2026-06-25): this dispatcher NEVER
    mutates state. All commands are read-only. State-changing
    operations (close position, disable ticker) are NOT routed here
    -- they live in the HTTP API and inline callback buttons.
    """
    cmd = (cmd or "").strip().lower()
    if cmd == "help" or cmd == "":
        return cmd_nifty_help()
    if cmd == "stats":
        return cmd_nifty_stats(db_path)
    if cmd == "swing":
        return cmd_nifty_swing()
    if cmd == "momentum":
        return cmd_nifty_momentum()
    if cmd == "regime":
        return cmd_nifty_regime()
    if cmd == "circuit":
        return cmd_nifty_circuit(db_path)
    return (
        f"Unknown /nifty subcommand: '{cmd}'. Try /nifty help.\n"
        f"Note: /nifty commands are read-only. To act on signals, use "
        f"the inline buttons or the HTTP API."
    )
