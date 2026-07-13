"""[ROADMAP-4.1 2026-07-13] Kite access-token lifecycle.

Extracted verbatim from main.py. The roadmap named token_lifecycle.py as
a natural seam; 2026-07-13 promoted it to the FIRST seam. The whole-day
outage that day lived entirely in this code:

  - _persist_kite_token() opens the cache file with "w", which TRUNCATES
    before writing. When the disk was full the write failed, leaving a
    ZERO-BYTE token file where a valid one had been.
  - The failure is swallowed as best-effort ("the in-memory token still
    works") -- true until the host rebooted 38 minutes later.
  - _load_persisted_kite_token_if_fresh() then hit the 0-byte file,
    raised JSONDecodeError, returned None, and the engine came up unarmed
    and never re-armed. Every scan for the rest of the day logged
    `no_access_token`.

None of that is FIXED here -- this commit is a pure move, and mixing a
behaviour change into a mechanical refactor is how you lose the ability to
say which one broke something. But the code now sits in one 180-line file
where it can be read, reasoned about, and repaired as a unit.

Singletons (`kite`) are reached via a lazy `import main`, matching the
idiom already used by penny_commands / penny_health / nifty_commands /
operator_status. That is not merely convention: the test-suite patches
`main.kite` BY NAME (monkeypatch.setattr(main, "kite", fake)), so binding
the object at import time here would silently detach those patches.
"""
from __future__ import annotations

import json as _json
import os as _os
import time
import time as _time
from datetime import datetime

import httpx as _httpx
import pytz
import structlog
from pydantic import BaseModel

from config import settings
from market_calendar import is_trading_day

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")


def _kite():
    """The live KiteClient singleton, resolved LAZILY on every call.

    Not `from main import kite` at module scope, for two reasons that both
    bite:
      1. main imports this module, so a top-level import back into main is
         a cycle.
      2. the suite patches the NAME (`monkeypatch.setattr(main, "kite",
         fake_kite)`). Binding the object once at import time would capture
         the real client and silently ignore every such patch -- tests that
         look like they exercise a fake would quietly hit the real thing.
    Resolving through the module attribute on each call preserves both.
    """
    import main as _main

    return _main.kite



# @app.post("/token")
# async def inject_token(request: Request):
#     data = await request.json()
# #    if data.get("secret") != settings.TOKEN_INJECTION_SECRET:
#  #       raise HTTPException(status_code=403, detail="Unauthorized")
#     kite.set_token(data["access_token"])
#     await post_login_initialization()
#     return {"status": "ok"}


class TokenPayload(BaseModel):
    access_token: str




# [FIX-PHASE3-AUDIT 2026-07-09] Token persistence + observability.
#
# Pre-fix, POST /token set kite.access_token IN MEMORY ONLY and logged
# nothing. Two production consequences on 2026-07-09:
#   1. The single most important state transition in the system (armed
#      vs disarmed) was invisible in the logs -- the audit had to infer
#      it from 26,311 downstream HTTP 400s.
#   2. Any container restart silently disarmed all strategies until the
#      operator manually logged in again. The 19:59 IST host reboot
#      wiped the day's token with no alert.
#
# The token is persisted to the /data named volume with an IST date
# stamp. On startup we restore it ONLY if it was saved today (Zerodha
# tokens expire daily around 06:00 IST, so a stale token is useless and
# restoring it would just produce a 400 storm -- the exact failure mode
# the no-token guards now prevent).

def _kite_token_cache_path() -> str:
    import os as _os
    return _os.path.join(_os.path.dirname(settings.DB_PATH), "kite_token.json")




def _persist_kite_token(token: str) -> bool:
    """Write the token atomically. Returns True on success.

    [OUTAGE-2026-07-13 DEFECT 1 + 2] This function cost a full trading day.

    It used to be `open(path, "w")` -- which TRUNCATES the file before writing
    a byte. When the disk filled at 09:06, the truncate succeeded and the write
    failed with ENOSPC, leaving a ZERO-BYTE kite_token.json where a valid token
    file had been. The failure was then swallowed as "best-effort; the in-memory
    token still works" -- true, right up until the host rebooted 38 minutes
    later, at which point the in-memory token died with the process and the
    restore path found the 0-byte file, raised JSONDecodeError, and brought the
    engine up UNARMED. Every scan for the rest of the day logged
    `no_access_token`. Nothing alerted.

    Two fixes, because there were two defects:

    1. ATOMIC: write to a temp file in the same directory, fsync it, then
       os.replace() onto the target. os.replace is atomic within a filesystem,
       so the destination is only ever the OLD valid token or the NEW valid one
       -- never a truncated husk. If the temp write fails, the existing file is
       untouched. (fsync before the rename matters: without it a crash can leave
       the rename durable but the contents not.)

    2. NOT BEST-EFFORT: the caller is told whether it worked. This file is the
       ONLY crash-recovery artifact the engine has -- calling its loss
       "best-effort" was the assumption that made a transient disk-full into a
       lost day. The caller now pages the operator.
    """
    import json as _json
    import os as _os

    path = _kite_token_cache_path()
    tmp = f"{path}.tmp"
    payload = {
        "access_token": token,
        "saved_date_ist": datetime.now(IST).strftime("%Y-%m-%d"),
    }
    try:
        with open(tmp, "w") as fh:
            _json.dump(payload, fh)
            fh.flush()
            _os.fsync(fh.fileno())
        _os.chmod(tmp, 0o600)
        _os.replace(tmp, path)  # atomic
        logger.info("kite_token_persisted path=%s", path)
        return True
    except Exception as e:
        logger.error(
            "kite_token_persist_failed error=%s path=%s "
            "impact=THE ENGINE CANNOT RE-ARM AFTER A RESTART -- the in-memory "
            "token works until the process dies, and then trading stops silently",
            str(e), path,
        )
        # Never leave a half-written temp behind for a later reader to trip on.
        try:
            _os.unlink(tmp)
        except OSError:
            pass
        return False




def _load_persisted_kite_token_if_fresh() -> dict | None:
    """Read the persisted token payload from /data and return it ONLY if
    it was saved today (IST). Returns None for missing/stale/corrupt.

    [ROADMAP-2.1 2026-07-12] Extracted from restore_kite_token_if_fresh
    so /token/current can serve node-gateway from the same freshness
    rule. Deliberately file-based rather than kite.access_token: the
    in-memory token carries no date stamp and could be yesterday's if
    this container has been up overnight -- handing that to node would
    re-arm execution with a dead token."""
    import json as _json
    import os as _os
    path = _kite_token_cache_path()
    try:
        if not _os.path.exists(path):
            return None
        with open(path) as fh:
            payload = _json.load(fh)
        saved_date = payload.get("saved_date_ist")
        token = payload.get("access_token")
        today_ist = datetime.now(IST).strftime("%Y-%m-%d")
        if not token or saved_date != today_ist:
            logger.info(
                "kite_token_restore_skipped saved_date=%s today=%s "
                "(stale -- operator must log in again)",
                saved_date, today_ist,
            )
            return None
        return payload
    except Exception as e:
        logger.warning("kite_token_restore_failed error=%s", str(e))
        return None




def restore_kite_token_if_fresh() -> bool:
    """Reload a same-IST-day token from /data on startup. Returns True
    when a token was restored. Called from the lifespan hook."""
    payload = _load_persisted_kite_token_if_fresh()
    if payload is None:
        return False
    _kite().set_token(payload["access_token"])
    logger.info("kite_token_restored saved_date=%s", payload.get("saved_date_ist"))
    return True




# [ROADMAP-2.1 2026-07-12] Token reconciliation: scans (python) and
# execution (node) hold independent token stores that can disagree --
# the exact split-brain of 2026-07-09, where scans ran all day while a
# restarted node had silently disarmed the EXEC buttons. A 15-min cron
# compares both sides during market hours and pages once (deduped to
# 1/hour) on disagreement. `None` sentinel, not 0.0: time.monotonic()
# can be below the window right after host boot.
_token_recon_state = {"last_alert_monotonic": None}


TOKEN_RECON_ALERT_MIN_INTERVAL_SEC = 3600.0




def _token_recon_mismatch_message(
    python_armed: bool, node_token_status: str | None
) -> str | None:
    """Pure decision: returns the operator alert text when the token state is
    wrong, else None. node_token_status is /api/health's token_status field:
    'active' | 'expired' | 'none' | None(unknown).

    [OUTAGE-2026-07-13 DEFECT 3] This function was written to catch SPLIT-BRAIN
    -- one side armed, the other not -- after the 2026-07-09 incident. It
    therefore returned None whenever the two sides AGREED... including when they
    agreed by both being DEAD.

    That is exactly what happened on 2026-07-13. python_armed=False,
    node_token_status="expired" -> False == False -> "they agree" -> silence.
    Every 15 minutes, for six hours of market time, while the engine scanned
    nothing and the operator had no idea.

    Both-unarmed during market hours is not agreement. It is the loudest thing
    this cron will ever see: the system is not trading.
    """
    if node_token_status is None:
        return None  # node unreachable -- healthcheck territory, not ours
    node_armed = node_token_status == "active"

    if not python_armed and not node_armed:
        return (
            "🔴 SYSTEM UNARMED: NOT TRADING\n\n"
            "Neither scans (python-engine) nor execution (node-gateway) hold a "
            f"Kite token (node token_status={node_token_status}).\n\n"
            "The engine is up and the scheduler is ticking, so everything LOOKS "
            "healthy -- but every scan is a no-op and no signal can be generated "
            "or executed. This is the 2026-07-13 outage.\n\n"
            "Re-login via the /login link now. If the login does not stick, "
            "check free disk space on /data -- a full disk prevents the token "
            "from being saved."
        )

    if python_armed == node_armed:
        return None  # both armed -- the healthy case

    if python_armed and not node_armed:
        return (
            "🔀 TOKEN SPLIT-BRAIN: scans (python-engine) are ARMED but "
            f"execution (node-gateway) is DISARMED (token_status={node_token_status}). "
            "EXEC buttons will fail until you re-login via the /login link "
            "(a node restart usually caused this)."
        )
    return (
        "🔀 TOKEN SPLIT-BRAIN: execution (node-gateway) is ARMED but "
        "scans (python-engine) have NO token. Signals will not be "
        "generated. Re-login via the /login link to re-arm both sides."
    )




async def _token_reconciliation_tick():
    """15-min market-hours cron: compare python vs node token state."""
    now_ist = datetime.now(IST)
    nm = now_ist.hour * 60 + now_ist.minute
    if not (9 * 60 + 15 <= nm <= 15 * 60 + 30):
        return
    if not await is_trading_day(now_ist.date(), settings.DB_PATH):
        return
    import httpx as _httpx
    try:
        async with _httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.CONTAINER_A_URL}/api/health", timeout=5.0
            )
            resp.raise_for_status()
            node_token_status = resp.json().get("token_status")
    except Exception as e:
        # Node being unreachable is the (future) healthcheck's problem
        # (roadmap 2.2) -- log it, don't page from here.
        logger.warning("token_recon_node_unreachable error=%s", str(e))
        return
    msg = _token_recon_mismatch_message(
        bool(_kite().access_token), node_token_status
    )
    if msg is None:
        return
    logger.warning(
        "token_recon_mismatch python_armed=%s node_status=%s",
        bool(_kite().access_token), node_token_status,
    )
    import time as _time
    now = _time.monotonic()
    last = _token_recon_state["last_alert_monotonic"]
    if last is not None and (now - last) < TOKEN_RECON_ALERT_MIN_INTERVAL_SEC:
        return
    _token_recon_state["last_alert_monotonic"] = now
    try:
        async with _httpx.AsyncClient() as client:
            await client.post(
                f"{settings.CONTAINER_A_URL}/api/internal/notify",
                json={"message": msg},
                headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET or ""},
                timeout=5.0,
            )
    except Exception as e:
        logger.warning("token_recon_notify_failed error=%s", str(e))
