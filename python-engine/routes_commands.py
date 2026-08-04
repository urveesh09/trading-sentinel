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

    # [STRATEGY-PROMOTION 2026-07-20] /promotion -> paper->live readiness bar.
    if cmd.lower() in ("promotion", "promote", "ladder"):
        from analytics import promotion_report, format_promotion_report
        data = await promotion_report(settings.DB_PATH)
        return {"reply": format_promotion_report(data)}

    # [HALT 2026-08-05] Read-only view of the kill switch. Tripping and
    # clearing are POST (see top_level_command_post) -- a GET that can stop
    # trading is one link-preview away from an accident.
    if cmd.lower() in ("halt", "resume", "haltstatus"):
        import halt_switch
        return {"reply": _halt_status_text(halt_switch)}

    from penny_commands import dispatch as _penny_dispatch
    # penny_commands.dispatch is the universal entry point -- it
    # routes /health and /regime to the cross-subsystem handlers.
    return {"reply": _penny_dispatch(cmd, "", settings.DB_PATH)}


def _halt_status_text(halt_switch) -> str:
    """Global + per-channel kill-switch state, with the commands to change it."""
    lines = ["KILL SWITCH", "", f"  global   {halt_switch.describe(None)}"]
    for channel in ("momentum", "penny", "fno"):
        # channel_state ignores the global sentinel on purpose: during a global
        # halt every channel would otherwise echo the global line, hiding what
        # a global clear would leave behind.
        own, attribution = halt_switch.channel_state(channel)
        lines.append(f"  {channel:<8} {'HALTED' if own else 'armed'}")
        if own and attribution:
            lines.append(f"           {attribution.get('reason', '')}")
    lines += [
        "",
        "Entries are blocked while halted. Exits (stops, unwinds,",
        "square-off) are NEVER blocked.",
        "",
        "  /halt <reason>              trip globally",
        "  /halt <channel> <reason>    trip one channel",
        "  /resume global              clear the global halt",
        "  /resume <channel>           clear one channel",
        "",
        "A bare /halt or /resume only shows this view -- both mutations",
        "need an explicit argument.",
    ]
    return "\n".join(lines)


@router.post("/command/{cmd}")
async def top_level_command_post(cmd: str, request: Request):
    """[HALT 2026-08-05] Mutating top-level commands: /halt and /resume.

    POST, not GET, because these change whether the system can trade.
    """
    import halt_switch

    try:
        body = await request.json()
    except Exception:
        body = {}
    args = str((body or {}).get("args", "") or "").strip()

    name = cmd.lower()
    if name not in ("halt", "resume"):
        raise HTTPException(status_code=404, detail=f"unknown mutating command: {cmd}")

    known_channels = ("momentum", "penny", "fno")
    first, _, rest = args.partition(" ")
    channel = first.lower() if first.lower() in known_channels else None
    remainder = (rest if channel else args).strip()

    if name == "resume":
        # Strict, unlike /halt. `/resume momentom` (typo) must NOT fall through
        # to clearing the GLOBAL halt -- that is the one mistake here that
        # silently re-arms more than the operator asked for. Only the literal
        # word "global" or a known channel may clear anything.
        target = args.strip().lower()
        if target not in ("global",) + known_channels:
            return {"reply": (
                f"Unknown resume target {args!r}.\n"
                f"Use: /resume global | " + " | ".join(f"/resume {c}" for c in known_channels)
            )}
        channel = None if target == "global" else target

    if name == "halt":
        reason = remainder or "tripped from Telegram with no reason given"
        try:
            payload = halt_switch.trip(reason, by="operator", channel=channel)
        except OSError as exc:
            # A kill switch that cannot write is not a kill switch. Say so.
            return {"reply": f"FAILED to trip halt: {exc}\nTrading is STILL LIVE."}
        scope = payload.get("scope", "global")
        return {"reply": (
            f"HALTED ({scope}).\nreason: {payload.get('reason')}\n"
            f"at: {payload.get('tripped_at')}\n\n"
            "New entries are blocked. Exits still work.\n"
            # Always name the target: bare /resume is the read-only status
            # view, so "Clear with /resume" would be an instruction that does
            # nothing and reads as a failure to the operator.
            f"Clear with /resume {scope}."
        )}

    removed = halt_switch.clear(channel)
    scope = channel or "global"
    if not removed:
        return {"reply": f"No {scope} halt was set. Nothing to clear."}
    still, attribution = halt_switch.halt_state(channel)
    tail = ""
    if still:
        tail = (f"\n\nNOTE: still halted -- {(attribution or {}).get('scope')} "
                f"sentinel is present. Clear that too.")
    return {"reply": f"Cleared the {scope} halt. Entries re-enabled.{tail}"}



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


@router.get("/strategy/promotion")
async def get_strategy_promotion():
    """[STRATEGY-PROMOTION 2026-07-20] Paper->live promotion ladder: per
    strategy, whether it has earned live capital (trades, net-cost expectancy,
    drawdown budget)."""
    from analytics import promotion_report
    return await promotion_report(settings.DB_PATH)



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
