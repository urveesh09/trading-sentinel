"""
[PENNY-COMMANDS 2026-06-25] Telegram command handlers for the penny subsystem.

INTERACTIVE TELEGRAM (T3-B):
  Reads messages sent to the bot (via /penny <subcommand>), executes
  the corresponding handler, and returns a string reply that the
  node-gateway echoes back via Telegram.

  Commands:
    /penny stats    -> bankroll, today's P&L, open positions, current regime
    /penny regime   -> current regime + classification confidence reasons
    /penny skip <TICKER>    -> add ticker to runtime disable list
    /penny unskip <TICKER>  -> remove ticker from runtime disable list
    /penny skips    -> list currently-disabled tickers (overrides only)
    /penny help     -> list available commands

DESIGN PRINCIPLES (operator-mandated 2026-06-25):

1. Read-only by default. Most commands (stats, regime, help, skips)
   just query state. Only `skip` and `unskip` mutate.

2. The mutation commands only write to a JSON override file. They
   NEVER mutate in-process state directly (the python-engine is
   stateless across requests; the scanner reads the override file
   on every scan, so changes take effect within 30s).

3. The override file is PERSISTENT across container restarts. When
   you restart python-engine, your skip list survives.

4. No "execute trade" or "close position" commands exist here.
   Those are way too risky for a chat interface. Use the existing
   callbacks / exec endpoints for those.

DATA SOURCE:
  - bankroll: settings.PENNY_PAPER_BANKROLL or PENNY_LIVE_BANKROLL
  - today's P&L: bankroll_ledger WHERE source='PENNY' AND DATE = today
  - open positions: positions WHERE source='PENNY' AND status IN
    ('OPEN', 'CLOSED_T1')
  - regime: penny_regime_engine.today_regime (set at 09:20 daily)

This module talks only to stdlib + aiosqlite + config + positions.
NO import from engine, regime, risk_engine, portfolio, evaluate_signal,
evaluate_momentum_signal.
"""
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---- default --------------------------------------------------------

# Default path used when callers don't pass one. The runtime
# scanner (penny_risk.is_disabled) reads from settings.PENNY_DISABLE_OVERRIDES_PATH,
# which defaults to the same value. cmd_* helpers below also read from
# settings when called via dispatch(). This means tests that patch the
# settings path automatically get the right behaviour end-to-end.
DEFAULT_OVERRIDES_PATH = "python-engine/data/penny_disable_overrides.json"


def _resolve_path(path: Optional[str]) -> str:
    """Resolve the override file path.

    Priority: explicit arg > settings.PENNY_DISABLE_OVERRIDES_PATH > default.
    Used by cmd_* helpers so they all read from the same location.
    """
    if path:
        return path
    try:
        from config import settings
        return settings.PENNY_DISABLE_OVERRIDES_PATH
    except Exception:
        return DEFAULT_OVERRIDES_PATH


# ---- override file I/O ----------------------------------------------

def _read_overrides(path: str) -> dict:
    """Read the override JSON. Returns a fresh empty dict if the file
    is missing or malformed (fail-open)."""
    if not os.path.exists(path):
        return {"disabled": [], "enabled": []}
    try:
        with open(path) as f:
            d = json.load(f)
        # Normalise: ensure both keys exist as lists.
        d.setdefault("disabled", [])
        d.setdefault("enabled", [])
        # De-dup and uppercase
        d["disabled"] = sorted(set(s.upper() for s in d["disabled"]))
        d["enabled"] = sorted(set(s.upper() for s in d["enabled"]))
        return d
    except Exception as e:
        logger.warning("penny_command_overrides_read_failed path=%s error=%s",
                       path, str(e))
        return {"disabled": [], "enabled": []}


def _write_overrides(path: str, overrides: dict) -> None:
    """Write the override JSON atomically (write-to-tmp-then-rename
    so a partial write doesn't corrupt the file mid-scan)."""
    overrides["_updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(overrides, f, indent=2)
    os.replace(tmp, path)


# ---- public: queries for the scanner -------------------------------

def get_overridden_disabled_tickers(path: str = DEFAULT_OVERRIDES_PATH) -> List[str]:
    """Return the runtime disable list. Called by penny_risk.is_disabled
    on every scan, so changes take effect within ~30s."""
    return _read_overrides(path).get("disabled", [])


# ---- command handlers ------------------------------------------------

def cmd_help() -> str:
    return (
        "Penny commands:\n"
        "/penny stats - bankroll, today's P&L, open positions, regime\n"
        "/penny regime - current regime + reasons\n"
        "/penny skip TICKER - disable ticker (mid-day, persists)\n"
        "/penny unskip TICKER - re-enable ticker\n"
        "/penny skips - list currently-disabled tickers\n"
        "/penny help - this message"
    )


def cmd_stats(db_path: str) -> str:
    """Compact live snapshot. Reads only -- safe."""
    from config import settings
    is_live = bool(settings.PENNY_LIVE_TRADING)
    bankroll = settings.PENNY_LIVE_BANKROLL if is_live else settings.PENNY_PAPER_BANKROLL
    mode = "LIVE" if is_live else "PAPER"

    today = datetime.now(timezone.utc).date().isoformat()
    pnl = 0.0
    trade_count = 0
    try:
        with sqlite3.connect(db_path) as con:
            cur = con.execute(
                "SELECT COALESCE(SUM(pnl), 0.0), COUNT(*) "
                "FROM bankroll_ledger "
                "WHERE source='PENNY' AND event_type='TRADE_CLOSED' "
                "AND DATE(timestamp) = ?",
                (today,),
            )
            pnl, trade_count = cur.fetchone()
    except sqlite3.Error as e:
        logger.warning("penny_cmd_stats_ledger_query_failed error=%s", str(e))

    open_count = 0
    try:
        with sqlite3.connect(db_path) as con:
            cur = con.execute(
                "SELECT COUNT(*) FROM positions "
                "WHERE source='PENNY' AND status IN ('OPEN', 'CLOSED_T1')"
            )
            open_count = int(cur.fetchone()[0])
    except sqlite3.Error:
        pass

    # Regime comes from the engine singleton in main; we lazy-import
    # to avoid creating a circular dependency at import time.
    regime_str = "UNKNOWN"
    try:
        import main as _main
        re = _main._penny_regime_engine
        if re is not None and re.today_regime is not None:
            regime_str = re.today_regime.value
    except Exception:
        pass

    sign = "+" if pnl >= 0 else ""
    return (
        f"Penny stats [{mode}]\n"
        f"Bankroll: Rs {bankroll:.0f}\n"
        f"Today: {sign}Rs {pnl:.0f} across {trade_count} trades\n"
        f"Open positions: {open_count}\n"
        f"Regime: {regime_str}"
    )


def cmd_regime(db_path: str) -> str:
    """Current regime + the 1-3 reasons that justify the classification.

    [TIER3-REGIME-CONFIDENCE 2026-06-25] Until now /penny regime returned
    just the regime label. That hid WHY the system was in PR1 vs PR2
    vs PR3 -- a debugging nightmare. Now we return the vol_rank, vix_proxy,
    breadth inputs, the threshold each crossed (or didn't), and the
    raw Nifty-50-vs-EMA50 distance so the operator can spot drift
    before it becomes a problem.
    """
    try:
        import main as _main
        re = _main._penny_regime_engine
        if re is None:
            return "Penny regime: engine not initialised yet"
        if re.today_regime is None:
            return "Penny regime: not yet computed (today's classify runs at 09:20 IST)"
        # Compose: header + each reason on its own line.
        lines = [f"Penny regime: {re.today_regime.value}"]
        if re.as_of:
            lines.append(f"  computed: {re.as_of}")
        reasons = re.confidence_reasons()
        for r in reasons:
            lines.append(f"  - {r}")
        return "\n".join(lines)
    except Exception as e:
        return f"Penny regime: error reading ({type(e).__name__})"


def cmd_skip(ticker: str, path: Optional[str] = None) -> str:
    """Add ticker to runtime disable list. Idempotent."""
    path = _resolve_path(path)
    if not ticker or not ticker.strip():
        return "Usage: /penny skip TICKER"
    t = ticker.strip().upper()
    overrides = _read_overrides(path)
    if t in overrides["disabled"]:
        return f"{t} is already disabled."
    overrides["disabled"].append(t)
    # Also remove from enabled if present (mutually exclusive)
    if t in overrides["enabled"]:
        overrides["enabled"].remove(t)
    _write_overrides(path, overrides)
    return (
        f"✓ {t} will be skipped from the next penny scan (~30s). "
        f"Persistence: survives container restart."
    )


def cmd_unskip(ticker: str, path: Optional[str] = None) -> str:
    """Remove ticker from runtime disable list. Idempotent."""
    path = _resolve_path(path)
    if not ticker or not ticker.strip():
        return "Usage: /penny unskip TICKER"
    t = ticker.strip().upper()
    overrides = _read_overrides(path)
    if t not in overrides["disabled"]:
        return f"{t} is not in the runtime disable list."
    overrides["disabled"].remove(t)
    overrides["enabled"].append(t)
    _write_overrides(path, overrides)
    return f"✓ {t} re-enabled. Next scan will evaluate it again."


def cmd_skips(path: Optional[str] = None) -> str:
    """List runtime-disabled tickers."""
    path = _resolve_path(path)
    overrides = _read_overrides(path)
    disabled = overrides.get("disabled", [])
    if not disabled:
        return "Penny runtime disable list: (empty)"
    body = ", ".join(disabled)
    updated = overrides.get("_updated_at", "unknown")
    return f"Penny runtime disable list ({len(disabled)} tickers, updated {updated}):\n{body}"


# ---- top-level dispatch ----------------------------------------------

def dispatch(command: str, args: str, db_path: str) -> str:
    """Dispatch a Telegram command to the right handler.

    Args:
        command: the subcommand word (e.g. "stats", "skip")
        args:    any trailing argument string (e.g. "GOLDSTAR-SM")
        db_path: path to the trading database
    Returns: a string reply (will be echoed back to Telegram)
    """
    cmd = (command or "").strip().lower()
    if cmd == "help" or cmd == "":
        return cmd_help()
    if cmd == "stats":
        return cmd_stats(db_path)
    if cmd == "regime":
        return cmd_regime(db_path)
    if cmd == "skips":
        return cmd_skips()
    if cmd == "skip":
        return cmd_skip(args)
    if cmd == "unskip":
        return cmd_unskip(args)
    return f"Unknown command: '{cmd}'. Try /penny help."
