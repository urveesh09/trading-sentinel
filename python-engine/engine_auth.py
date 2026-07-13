"""[ROADMAP-4.1 2026-07-13] The internal-API secret gate.

Extracted verbatim from main.py. This is the single chokepoint that
decides whether an inbound request is allowed to arm a token, reset a
circuit breaker, or read ops metrics -- it has no business living in the
middle of a 4,200-line module alongside the scan orchestration.

Behaviour is UNCHANGED, deliberately: the gate is documented as
non-blocking at boot per the operator mandate of 2026-06-25 ("don't block
boot during market hours"), and this split is not the place to revisit
that decision.
"""
from __future__ import annotations

import asyncio

import structlog
from fastapi import HTTPException, Request

from config import settings

logger = structlog.get_logger()


# ---- [AUDIT-FIX-2.2] Internal-API-secret gate hardening -------------------

# Module-level flag so we only log the empty-secret warning once at
# startup (loud) + once per auth-failed call (medium). Avoids log spam.
_internal_secret_warning_emitted = False




def _check_internal_secret(request: Request, endpoint_name: str) -> None:
    """
    [AUDIT-FIX-2.2 2026-06-25] Centralised auth-gate for internal
    endpoints (/positions/manual, /positions/close, /api/internal/*,
    the CNC alert webhook target).

    Behaviour:
      - INTERNAL_API_SECRET env var is set + caller sends the right
        value -> allow.
      - INTERNAL_API_SECRET env var is set + caller sends wrong/missing
        value -> 403 (same as before; this fix doesn't change it).
      - INTERNAL_API_SECRET env var is EMPTY (not set in .env) -> 503.
        This is louder than 403 and tells the operator the endpoint
        is misconfigured, not that the caller is wrong. The system
        STAYS UP (other endpoints work) but refuses to mutate until
        the secret is configured.

    Why this matters: pre-fix, an empty secret defaulted `if secret !=
    ""` to True, allowing ANY caller (including an attacker on the
    docker network) to invoke internal endpoints by sending
    `X-Internal-Secret: ` (empty string). With the empty-secret
    setting, the attacker could close positions, send manual positions,
    etc.

    Why not hard-fail at startup: per operator mandate (2026-06-25),
    internal endpoints going down must NOT block the system during
    market hours. We log + refuse requests + emit Telegram alert, but
    the scanner loop keeps running.
    """
    global _internal_secret_warning_emitted
    configured = settings.INTERNAL_API_SECRET
    sent = request.headers.get("X-Internal-Secret", "")

    if not configured:
        # Misconfigured deployment: secret not set.
        if not _internal_secret_warning_emitted:
            # Loud one-time warning at first hit. After this, log at
            # WARNING level per call (rare event, should be fixed).
            logger.critical(
                "internal_api_secret_not_configured "
                "endpoint=%s FIX=set INTERNAL_API_SECRET env var to a non-empty value",
                endpoint_name,
            )
            # Telegram alert (best-effort, fire-and-forget so the sync
            # gate function can return immediately). create_task only
            # works inside a running event loop, so guard.
            try:
                import asyncio
                try:
                    asyncio.get_running_loop()
                    asyncio.create_task(_send_internal_secret_alert())
                except RuntimeError:
                    # No running loop (test context). The warning is
                    # enough -- we already logged at CRITICAL above.
                    pass
            except Exception:
                # Don't propagate -- notify failure must not block the gate.
                pass
            _internal_secret_warning_emitted = True
        else:
            logger.warning(
                "internal_api_secret_not_configured endpoint=%s",
                endpoint_name,
            )
        raise HTTPException(
            status_code=503,
            detail=(
                "Internal API not configured: INTERNAL_API_SECRET env "
                "var must be set to a non-empty value. Operator has "
                "been alerted. System continues running -- other "
                "endpoints and the scanner are unaffected."
            ),
        )

    # Normal auth: secret configured, check the caller's value.
    if sent != configured:
        raise HTTPException(status_code=403, detail="Unauthorized")




async def _send_internal_secret_alert() -> None:
    """[AUDIT-FIX-2.2] Best-effort Telegram alert when the secret
    is empty. Wrapped in its own function so the caller (sync gate)
    can fire-and-forget via asyncio.create_task."""
    try:
        import httpx as _httpx
        msg = (
            "🚨 **SECURITY: INTERNAL_API_SECRET not configured** 🚨\n"
            "Internal endpoints (/token, /positions/manual, "
            "/positions/close) are refusing requests with HTTP 503. Set "
            "INTERNAL_API_SECRET in .env to a non-empty value."
        )
        async with _httpx.AsyncClient() as _client:
            await _client.post(
                f"{settings.CONTAINER_A_URL}/api/internal/notify",
                json={"message": msg},
                headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET or ""},
                timeout=5.0,
            )
    except Exception as e:
        logger.warning("internal_secret_alert_failed error=%s", str(e))
