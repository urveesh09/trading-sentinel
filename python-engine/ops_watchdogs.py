"""[ROADMAP-4.1 2026-07-13] Ops watchdogs: scheduler liveness, daily ops
snapshot, and the Kite relay probe.

Extracted verbatim from main.py (roadmap 2.4 / 2.6 / 2.8 work). These are
the jobs that are supposed to notice when the engine has gone quiet, so
they belong together and away from the code they are watching.

Worth stating plainly, since 2026-07-13 tested them: the scheduler-tick
watchdog did its job (it fires when the APScheduler loop stalls) and the
relay probe did its job. Neither of them can see an engine that is ticking
happily with NO ACCESS TOKEN -- alive, scheduled, and trading nothing.
That gap is real and is tracked separately; it is not addressed by this
move.

Singletons are reached via a lazy `import main` -- see token_lifecycle for
why that is load-bearing rather than stylistic.
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

from config import settings

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")




# [ROADMAP-2.4 2026-07-12] Scheduler loop-progress tick. The existing
# penny-liveness heartbeat is a daemon THREAD -- it keeps ticking even
# when the asyncio loop / APScheduler is frozen (by design: it proves
# the process is alive). This job is the complement: it runs ON the
# scheduler as a normal job, so a fresh file timestamp proves jobs are
# actually firing. The agent container reads this file from /data (ro
# mount) and pages the operator when it goes stale during market hours
# -- the external watchdog that would have caught the 2026-07-07
# 6h32m freeze in minutes.
def _scheduler_tick_path() -> str:
    import os as _os
    return _os.path.join(_os.path.dirname(settings.DB_PATH), "scheduler_tick.json")




# [ROADMAP-2.8 2026-07-12] Previous-tick clock for the persistent
# liveness time-series. None after boot: a restart must not fabricate a
# gap (the gap it WOULD measure spans a different process's lifetime).
_scheduler_tick_state = {"prev_monotonic": None}




async def _scheduler_tick_job():
    import json as _json
    import os as _os
    try:
        path = _scheduler_tick_path()
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            _json.dump({
                "ts_epoch": time.time(),
                "ist": datetime.now(IST).isoformat(),
            }, fh)
        # Atomic replace so the agent's reader never sees a torn file.
        _os.replace(tmp, path)
    except Exception as e:
        logger.warning("scheduler_tick_write_failed error=%s", str(e))
    # [ROADMAP-2.8 2026-07-12] Fold this tick into ops_liveness_daily --
    # the persistent record of scheduler gaps that outlives the docker
    # log ring, and the attestation source for the F&O go-live liveness
    # gate. Separate try: a DB hiccup must not stop the file heartbeat
    # above, and vice versa.
    try:
        from ops_metrics import record_scheduler_tick
        import time as _time
        now_mono = _time.monotonic()
        prev = _scheduler_tick_state["prev_monotonic"]
        _scheduler_tick_state["prev_monotonic"] = now_mono
        gap = (now_mono - prev) if prev is not None else None
        await record_scheduler_tick(settings.DB_PATH, datetime.now(IST), gap)
    except Exception as e:
        logger.warning("scheduler_tick_record_failed error=%s", str(e))




# [ROADMAP-2.8 2026-07-12] Daily funnel snapshot: one ops_funnel_daily
# row per subsystem at 15:50 IST (after close, after the 15:45 accept-
# watchdogs) so accept/reject history survives log rotation.
async def _ops_daily_snapshot():
    now_ist = datetime.now(IST)
    if not await is_trading_day(now_ist.date(), settings.DB_PATH):
        return
    from ops_metrics import snapshot_funnels_for_day
    written = await snapshot_funnels_for_day(
        settings.DB_PATH, now_ist.strftime("%Y-%m-%d")
    )
    logger.info("ops_daily_snapshot_written counts=%s", written)




# [ROADMAP-2.6 2026-07-12] Kite endpoint (OCI relay) liveness probe.
# Every quote and order transits settings.KITE_BASE_URL -- on the home
# desktop that is the OCI relay 161.118.160.180:31527, a single
# unmonitored hop whose only check until now was the manual morning
# smoke_relay.sh. A 3-min market-hours cron probes it from inside this
# container (the real code path) and pages on 2 consecutive failures
# (one blip = transient, don't page), deduped to 1/30min while down,
# with a recovery notice when it comes back. Failover procedure:
# docs/runbooks/relay-failover.md.
_kite_probe_state = {
    "consec_failures": 0,
    "down_since_monotonic": None,   # set when the alert threshold is crossed
    "last_alert_monotonic": None,
}


KITE_PROBE_FAILURES_TO_ALERT = 2


KITE_PROBE_ALERT_MIN_INTERVAL_SEC = 1800.0




def _kite_probe_evaluate(ok: bool, now_monotonic: float, state: dict) -> str | None:
    """Pure state machine: fold one probe result into `state`, return the
    operator alert text to send (down page / recovery notice) or None.
    Kept side-effect-free so the alarm logic is fully testable."""
    if ok:
        state["consec_failures"] = 0
        down_since = state["down_since_monotonic"]
        if down_since is None:
            return None  # steady-state healthy, or a blip we never paged for
        state["down_since_monotonic"] = None
        state["last_alert_monotonic"] = None
        mins = (now_monotonic - down_since) / 60.0
        return (
            f"✅ KITE ENDPOINT RECOVERED: {settings.KITE_BASE_URL} is "
            f"reachable again (was down ~{mins:.0f} min). Quotes and "
            "orders are flowing normally."
        )
    state["consec_failures"] += 1
    if state["consec_failures"] < KITE_PROBE_FAILURES_TO_ALERT:
        return None
    if state["down_since_monotonic"] is None:
        state["down_since_monotonic"] = now_monotonic
    last = state["last_alert_monotonic"]
    if last is not None and (now_monotonic - last) < KITE_PROBE_ALERT_MIN_INTERVAL_SEC:
        return None
    state["last_alert_monotonic"] = now_monotonic
    return (
        f"📡 KITE ENDPOINT DOWN: {settings.KITE_BASE_URL} has failed "
        f"{state['consec_failures']} consecutive probes. ALL quotes and "
        "orders transit this endpoint -- scans and EXEC are blind until "
        "it recovers. Triage: `bash python-engine/smoke_relay.sh`, then "
        "docs/runbooks/relay-failover.md."
    )




async def _kite_endpoint_probe_tick():
    """3-min market-hours cron: probe the configured Kite endpoint."""
    now_ist = datetime.now(IST)
    nm = now_ist.hour * 60 + now_ist.minute
    if not (9 * 60 + 15 <= nm <= 15 * 60 + 30):
        return
    if not await is_trading_day(now_ist.date(), settings.DB_PATH):
        return
    import httpx as _httpx
    ok = False
    err = ""
    try:
        async with _httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.KITE_BASE_URL}/", timeout=8.0)
        # Any response < 500 means the hop is up (relay root proxies to
        # Kite's root, which returns 200 -- see smoke_relay.sh). A 5xx
        # from the relay means the path to Kite is broken even though
        # the relay process answered: that IS an outage for us.
        ok = resp.status_code < 500
        if not ok:
            err = f"HTTP {resp.status_code}"
    except Exception as e:
        err = str(e)
    if not ok:
        logger.warning(
            "kite_endpoint_probe_failed url=%s consec=%d error=%s",
            settings.KITE_BASE_URL,
            _kite_probe_state["consec_failures"] + 1, err,
        )
    import time as _time
    msg = _kite_probe_evaluate(ok, _time.monotonic(), _kite_probe_state)
    if msg is None:
        return
    try:
        async with _httpx.AsyncClient() as client:
            await client.post(
                f"{settings.CONTAINER_A_URL}/api/internal/notify",
                json={"message": msg},
                headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET or ""},
                timeout=5.0,
            )
    except Exception as e:
        logger.warning("kite_endpoint_probe_notify_failed error=%s", str(e))
