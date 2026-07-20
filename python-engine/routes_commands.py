"""[ROADMAP-4.1 stage 3, 2026-07-13] Telegram command dispatch and analytics endpoints.

Extracted verbatim from main.py. Registered on the app via
`app.include_router(router)`, so the route table -- paths, methods, endpoint
names, response models -- is byte-identical; the 24-route characterization
golden proves it.

EVERY business name is reached through `_main` at CALL time, not imported.
That is not stylistic. Two independent reasons, both load-bearing:

  1. Eight of main's globals are REBOUND at runtime via `global` statements
     (current_signals, market_regime, momentum_signals_today, last_run,
     rejected_signals, current_momentum_signals, last_momentum_date,
     _last_regime_state). `from main import current_signals` would capture the
     list that existed at import and serve it forever, while run_screener
     quietly rebinds main's name to a NEW list on every scan. The endpoint
     would go permanently stale and nothing would raise.

  2. The suite patches ~25 of these names BY NAME on main (kite,
     get_open_positions, record_trade_close, post_login_initialization,
     run_momentum_screener, ...). Import-time binding silently detaches every
     one of those patches.

The module-level `import main as _main` is safe despite main importing this
module: Python registers main in sys.modules BEFORE executing it, so we bind
the module object, and only ever touch its attributes at request time -- by
which point main is fully initialised.
"""
from fastapi import APIRouter, HTTPException, Request

import main as _main

from config import settings

router = APIRouter()




# [TIER3-INTERACTIVE-COMMANDS 2026-06-25] Telegram command endpoint.
# The node-gateway forwards /penny <subcommand> <args> messages to
# python-engine via these endpoints, then echoes the reply back to
# the user's Telegram chat. Read-only commands (stats, regime, help,
# skips) use GET. Mutating commands (skip, unskip) use POST.
@router.get("/penny/command/{cmd}")
async def penny_command_get(cmd: str):
    """GET handler for read-only commands. Returns plain text reply."""
    from penny_commands import dispatch
    return {"reply": dispatch(cmd, "", settings.DB_PATH)}




@router.post("/penny/command/{cmd}")
async def penny_command_post(cmd: str, payload: dict):
    """POST handler for mutating commands. Body: {"args": "<ticker>"}."""
    from penny_commands import dispatch
    args = (payload or {}).get("args", "")
    return {"reply": dispatch(cmd, args, settings.DB_PATH)}




# [TIER3-NIFTY-COMMANDS 2026-06-25] Read-only Nifty commands.
# Per operator mandate, these NEVER mutate state -- they're pure
# queries against _main.current_signals, _main.current_momentum_signals, and
# _main.market_regime globals + DB-backed bankroll/circuit-breaker reads.
# To act on Nifty signals use the inline callback buttons or the
# HTTP API (POST /positions/close, etc.).
@router.get("/nifty/command/{cmd}")
async def nifty_command_get(cmd: str):
    """GET handler for read-only Nifty commands."""
    from nifty_commands import dispatch
    return {"reply": dispatch(cmd, "", settings.DB_PATH)}




# No POST handler: by design, /nifty commands don't mutate state.


# [TIER3-CROSS-SUBSYSTEM-COMMANDS 2026-06-25] Phase B.
# Top-level /health and /regime (no /penny prefix). Same read-only
# posture as /nifty. The dispatcher routes by command name.
@router.get("/command/{cmd}")
async def top_level_command_get(cmd: str):
    """Top-level read-only commands: /health, /regime.

    These are cross-subsystem views (penny + nifty side by side)
    and don't fit under /penny or /nifty specifically. The gateway
    routes /health and /regime (no prefix) here.
    """
    # [DIVISION-BREAKDOWN 2026-07-15] /divisions and /bankroll render the full
    # per-division P&L attribution. Handled here (not via the sync penny
    # dispatch) because division_breakdown is async.
    if cmd.lower() in ("divisions", "bankroll"):
        from performance import division_breakdown, format_division_breakdown
        data = await division_breakdown(settings.DB_PATH)
        return {"reply": format_division_breakdown(data)}

    # [STRATEGY-FUNNEL 2026-07-20] /funnel -> per-strategy activity + P&L
    # heartbeat (evals, accepts, top reject reasons, live-vs-paper P&L).
    if cmd.lower() in ("funnel", "strategies"):
        from analytics import strategy_funnel, format_strategy_funnel
        data = await strategy_funnel(settings.DB_PATH)
        return {"reply": format_strategy_funnel(data)}

    from penny_commands import dispatch as _penny_dispatch
    # penny_commands.dispatch is the universal entry point -- it
    # routes /health and /regime to the cross-subsystem handlers.
    return {"reply": _penny_dispatch(cmd, "", settings.DB_PATH)}



# [ANALYTICS 2026-06-16] Self-improvement endpoints.
# GET /analytics/funnel?days=7     -> gate rejection counts (JSON)
# GET /analytics/suggestions?days=14 -> actionable suggestions (JSON)
# GET /analytics/outcomes?days=14  -> outcome correlator (JSON)
# CLI: `python -m analytics --days 14`  for a human terminal report.
@router.get("/analytics/funnel")
async def get_funnel(days: int = 7):
    from analytics import gate_funnel_report
    return await gate_funnel_report(settings.DB_PATH, days=days)


@router.get("/strategy/funnel")
async def get_strategy_funnel(date: str = None):
    """[STRATEGY-FUNNEL 2026-07-20] Unified per-strategy activity + P&L for
    one day (default today, IST). date=YYYY-MM-DD to backfill."""
    from analytics import strategy_funnel
    return await strategy_funnel(settings.DB_PATH, day_iso=date)



@router.get("/analytics/outcomes")
async def get_outcomes(days: int = 14):
    from analytics import outcome_correlator
    return await outcome_correlator(settings.DB_PATH, days=days)



@router.get("/analytics/suggestions")
async def get_suggestions(days: int = 14):
    from analytics import strategy_suggestions
    return await strategy_suggestions(settings.DB_PATH, days=days)


# [ROADMAP-5.1 2026-07-13] The numbers that can actually say whether there is an
# edge: expectancy (R and rupees), profit factor, max drawdown, each with a
# bootstrapped 95% CI.
#
# 90-day default window, not the 7/14 used above: these statistics need a
# sample, and a fortnight of this system's trade frequency cannot supply one.
# The response carries `n`, `reliable` and a conservative `verdict` -- an edge
# is only claimed when the CI on expectancy sits ENTIRELY above zero, so a
# flattering point estimate on eight trades reads as "not_demonstrated" rather
# than as a green light.
@router.get("/analytics/edge")
async def get_edge_statistics(days: int = 90, strategy: str | None = None):
    from analytics import edge_statistics
    return await edge_statistics(settings.DB_PATH, days=days, strategy=strategy)
