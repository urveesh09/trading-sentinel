"""[ROADMAP-4.1 stage 3, 2026-07-13] Ops, token and circuit-breaker endpoints.

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

import asyncio

from config import settings
from token_lifecycle import TokenPayload

router = APIRouter()




@router.post("/token")
async def inject_token(payload: TokenPayload, request: Request):
    # [HIGH-002 2026-07-12] Same auth gate as the other internal mutating
    # endpoints (/positions/manual, /positions/close). Without it, anyone
    # on the docker network could inject an arbitrary Kite token and arm
    # trading. node-gateway already sends X-Internal-Secret on its
    # provisioning call (routes/auth.js), so the login flow is unchanged.
    _main._check_internal_secret(request, "inject_token")
    _main.kite.set_token(payload.access_token)
    # [FIX-PHASE3-AUDIT 2026-07-09] Loud (masked) breadcrumb + persist so
    # a restart no longer silently disarms the system.
    _main.logger.info(
        "kite_token_injected suffix=...%s len=%d",
        payload.access_token[-4:] if len(payload.access_token) >= 4 else "?",
        len(payload.access_token),
    )
    _main._persist_kite_token(payload.access_token)
    # Fire-and-forget: return 200 immediately so node-gateway's 2-second
    # AbortController does not trigger retries that spawn concurrent screener runs.
    # _main.post_login_initialization runs in the background (Q4 behaviour is preserved).
    asyncio.create_task(_main.post_login_initialization())
    return {"status": "ok"}




@router.get("/token/current")
async def get_current_token(request: Request):
    """[ROADMAP-2.1 2026-07-12] Serve the same-_main.IST-day token (if any) to
    node-gateway so a mid-day node restart re-arms execution without a
    manual re-login. Same auth gate as /token; the token only ever moves
    over the internal docker network, exactly like the login-time
    provisioning call in the opposite direction. Freshness rule is
    identical to the startup restore: stale/missing file => not armed."""
    _main._check_internal_secret(request, "get_current_token")
    payload = _main._load_persisted_kite_token_if_fresh()
    if payload is None:
        return {"armed": False}
    _main.logger.info(
        "kite_token_served suffix=...%s",
        payload["access_token"][-4:] if len(payload["access_token"]) >= 4 else "?",
    )
    return {"armed": True, "access_token": payload["access_token"]}




@router.post("/token/invalidate")
async def invalidate_token(request: Request):
    """[MED-010 / ROADMAP-4.6 2026-07-12] Called by node-gateway's
    /logout. Was a silent 404 since the logout handler was written --
    harmless before 2.1, but now the engine both KEEPS scanning with the
    token and SERVES it back to node via /token/current, so a logout
    that doesn't reach here isn't a logout at all. Clears the in-memory
    token AND the persisted same-day file (otherwise the next node boot
    would just re-arm from it)."""
    _main._check_internal_secret(request, "invalidate_token")
    _main.kite.set_token("")
    import os as _os
    path = _os.path.join(_os.path.dirname(settings.DB_PATH), "kite_token.json")
    try:
        _os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as e:
        _main.logger.warning("kite_token_file_remove_failed error=%s", str(e))
    _main.logger.info("kite_token_invalidated_by_operator")
    return {"status": "invalidated"}




@router.get("/ops/metrics")
async def get_ops_metrics(request: Request, days: int = 30):
    """[ROADMAP-2.8 2026-07-12] The persisted ops time-series: per-day
    _main.scheduler liveness (worst tick gaps) + per-day per-subsystem gate
    funnels. `liveness.market_gap_clean` over days=30 is the queryable
    form of the F&O go-live liveness condition (fno_risk condition 4)
    that used to require grepping rotated-away docker logs."""
    _main._check_internal_secret(request, "ops_metrics")
    from ops_metrics import funnel_window, liveness_report
    days = max(1, min(days, 365))
    return {
        "liveness": await liveness_report(settings.DB_PATH, days=days),
        "funnel": await funnel_window(settings.DB_PATH, days=days),
    }




@router.get("/circuit-breaker")
async def get_circuit_breaker():
    halted, reasons = await _main.check_circuit_breakers(settings.DB_PATH)
    return {"trading_halted": halted, "halt_reasons": reasons}




@router.post("/circuit-breaker/reset")
async def reset_circuit_breaker(request: Request):
    """[MED-006 / ROADMAP-4.6 2026-07-12] node-gateway has proxied this
    route since the April audit; it 404'd here. Re-baselines the
    drawdown peak + consecutive-loss streak via a CB_RESET ledger marker
    (see performance.record_cb_reset -- the floor and daily-loss CBs are
    deliberately NOT resettable). Secret-gated: this weakens a safety
    brake, it must never be callable anonymously."""
    _main._check_internal_secret(request, "reset_circuit_breaker")
    from performance import record_cb_reset
    await record_cb_reset(settings.DB_PATH)
    halted, reasons = await _main.check_circuit_breakers(settings.DB_PATH)
    return {"status": "reset_recorded", "trading_halted": halted,
            "halt_reasons": reasons}



@router.get("/health")
async def health_check():
    """Real /health (Phase B, 2026-06-25).

    Replaces the no-op `{"status": "ok"}` placeholder with a structured
    diagnostic of all subsystems. The operator can pull this via the
    /health Telegram command (cmd_health) or hit it directly via HTTP.

    Returns: {status: "OK" | "DEGRADED", subsystems: {...}, halted: bool, ...}
    The HTTP shape mirrors the structure used by build_health_snapshot()
    in penny_health.py.
    """
    try:
        from penny_health import build_health_snapshot
        snap = await build_health_snapshot(settings.DB_PATH)
        # [LOW-003 / ROADMAP-4.6 2026-07-12] The two liveness facts only
        # main.py knows (penny_health is DB-pure): is execution armed,
        # and is the job _main.scheduler actually running.
        snap["kite_connected"] = bool(_main.kite.access_token)
        snap["scheduler_running"] = bool(getattr(_main.scheduler, "running", False))
        # The HTTP status code reflects overall_status: 200 for OK,
        # 200 for DEGRADED too (the system is responding, just with
        # issues -- this lets load balancers distinguish "service down"
        # from "service up but unhappy"). Clients should read the
        # JSON body for actual state.
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=200, content=snap)
    except Exception as e:
        # Even the health check must not fail. Return a minimal payload
        # indicating DOWN so the operator knows python-engine is sick.
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "overall_status": "DOWN",
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            },
        )



@router.post("/test-momentum")
async def test_momentum_screener():
    """Manual trigger for testing the momentum scanner."""
    asyncio.create_task(_main.run_momentum_screener())
    return {"status": "momentum_scan_triggered"}
