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
import uuid as _uuid
from datetime import datetime

import httpx as _httpx
import pytz
import structlog

from config import settings
# [BUGFIX 2026-07-13] `is_trading_day` is used by _ops_daily_snapshot and
# _kite_endpoint_probe_tick but was NOT imported when these functions were
# extracted from main.py in the 4.1 stage-1 split. main.py had it at module
# scope; this module did not.
#
# It is the exact failure I built the split's safety net against, and it got
# through because that net (test_scheduler_closures_invoke) only INVOKED the 8
# closures inside register_*_scheduler_jobs -- not the module-level jobs stage 1
# had already moved. Import succeeded, the census saw the registration, the
# suite went green, and _ops_daily_snapshot would have raised NameError at 15:50
# every day, inside a try/except that logs and returns. The daily ops snapshot
# would simply have stopped, silently.
#
# The net is now widened to invoke EVERY scheduled job, not just the closures.
from market_calendar import is_trading_day

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
# liveness time-series. None after boot; startup recovers the prior process's
# wall-clock heartbeat explicitly, while ordinary in-process ticks use this
# monotonic clock so NTP/wall-time adjustments cannot fabricate a gap.
_scheduler_tick_state = {"prev_monotonic": None, "count": 0,
                         "boot_id": _uuid.uuid4().hex}




async def _scheduler_tick_job(*, recover_previous: bool = False):
    """Write the loop heartbeat and fold its gap into persistent metrics.

    ``recover_previous`` is used once, immediately after ``scheduler.start()``.
    The heartbeat file survives container/process restarts, so its wall-clock
    timestamp is the only evidence of a gap that crossed a process boundary.
    Normal interval ticks continue to use ``monotonic()``; wall time is used
    only for startup recovery because a monotonic clock cannot be compared
    across processes.

    Returns a small attestation dict for the startup log.  APScheduler ignores
    the return value on normal interval invocations.
    """
    import json as _json
    import os as _os
    previous_wall_gap = None
    recovered_previous = False
    prior = None
    now_epoch = time.time()
    path = _scheduler_tick_path()
    tick_count = int(_scheduler_tick_state.get("count", 0)) + 1
    _scheduler_tick_state["count"] = tick_count
    boot_id = _scheduler_tick_state.setdefault("boot_id", _uuid.uuid4().hex)
    if recover_previous:
        try:
            with open(path) as fh:
                prior = _json.load(fh)
            prior_epoch = float(prior["ts_epoch"])
            if prior_epoch > 0:
                # A backwards wall-clock adjustment must not fabricate a
                # negative liveness gap.
                previous_wall_gap = max(0.0, now_epoch - prior_epoch)
                recovered_previous = True
        except (FileNotFoundError, KeyError, TypeError, ValueError, OSError,
                _json.JSONDecodeError):
            # First-ever boot, an old-format file, or a torn external write:
            # start a fresh baseline.  The heartbeat write below still runs.
            pass
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            _json.dump({
                "ts_epoch": now_epoch,
                "ist": datetime.now(IST).isoformat(),
                "boot_id": boot_id,
                "pid": _os.getpid(),
                "scheduler_tick_count": tick_count,
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
        gap = previous_wall_gap if recovered_previous else (
            (now_mono - prev) if prev is not None else None
        )
        await record_scheduler_tick(settings.DB_PATH, datetime.now(IST), gap)
    except Exception as e:
        logger.warning("scheduler_tick_record_failed error=%s", str(e))
    # [O15-N1] Page a market-hours provider outage (start and end), through
    # the same acknowledged outbox; delivered by the retry just below.
    try:
        import main as _main_mod
        budget = getattr(getattr(_main_mod, "kite", None), "endpoint_budget", None)
        connectivity = budget.connectivity() if hasattr(budget, "connectivity") else None
        if connectivity and (connectivity.get("current") or connectivity.get("recent")):
            from lifecycle_receipts import open_exposure_counts, provider_outage_alerts
            if await is_trading_day(datetime.now(IST).date(), settings.DB_PATH):
                queued = provider_outage_alerts(
                    settings.DB_PATH, connectivity, time.time(),
                    exposure_fn=lambda: open_exposure_counts(settings.DB_PATH))
                if queued:
                    logger.warning("provider_outage_alert_queued ids=%s", ",".join(queued))
    except Exception as e:
        logger.warning("provider_outage_alert_failed error=%s", str(e))
    # [review F4] Retry any unacknowledged restart page (backoff inside).
    try:
        from lifecycle_receipts import deliver_restart_alerts, has_pending_alerts
        if has_pending_alerts(settings.DB_PATH):
            import main as _main_mod
            await deliver_restart_alerts(settings.DB_PATH, _main_mod._post_required_notice, time.time())
    except Exception as e:
        logger.warning("restart_alert_retry_failed error=%s", str(e))
    # This is deliberately distinct from penny_liveness_tick: it is emitted
    # by the APScheduler loop, whereas the latter is a process-thread pulse.
    logger.info("scheduler_progress_tick count=%s boot_id=%s", tick_count, boot_id)
    return {
        "recovered_previous": recovered_previous,
        "prior_gap_seconds": previous_wall_gap,
        # [O13-R1] the prior heartbeat as read, for the lifecycle receipt.
        "prior": prior if recover_previous else None,
        "boot_id": boot_id,
    }




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


# [O25c 2026-10-25] The order route, when it is not KITE_BASE_URL: the encrypted tunnel through the
# registered VM (KITE_ORDER_PROXY_URL; the gateway's KITE_PROXY_URL uses the same tunnel) or a separate
# relay (KITE_ORDER_BASE_URL). The probe above watches only KITE_BASE_URL, which is direct on the home
# desktop, so a dark tunnel would otherwise be noticed only when a real order failed.
_kite_order_route_probe_state = {
    "consec_failures": 0,
    "down_since_monotonic": None,
    "last_alert_monotonic": None,
}


def _order_route_probe_target() -> tuple[str, str] | None:
    """(URL to GET, proxy or "") of a separate order route; None when orders use KITE_BASE_URL."""
    proxy = (settings.KITE_ORDER_PROXY_URL or "").strip()
    base = (settings.KITE_ORDER_BASE_URL or "").strip().rstrip("/")
    if proxy:
        return f"{base or 'https://api.kite.trade'}/", proxy
    if base and base != settings.KITE_BASE_URL.rstrip("/"):
        return f"{base}/", ""
    return None




def _kite_probe_evaluate(ok: bool, now_monotonic: float, state: dict, route: str | None = None) -> str | None:
    """Pure state machine: fold one probe result into `state`, return the
    operator alert text to send (down page / recovery notice) or None.
    Kept side-effect-free so the alarm logic is fully testable.
    [O25c] ``route`` names the separate order route (password hidden) for its own texts."""
    if ok:
        state["consec_failures"] = 0
        down_since = state["down_since_monotonic"]
        if down_since is None:
            return None  # steady-state healthy, or a blip we never paged for
        state["down_since_monotonic"] = None
        state["last_alert_monotonic"] = None
        mins = (now_monotonic - down_since) / 60.0
        if route is not None:
            return f"✅ KITE ORDER ROUTE RECOVERED: {route} answers again (was down ~{mins:.0f} min)."
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
    if route is not None:
        return (
            f"📡 KITE ORDER ROUTE DOWN: {route} has failed {state['consec_failures']} consecutive probes. Real "
            "orders and exits cannot be sent this way, nor the gateway's Kite calls if it uses the tunnel; a "
            "resting broker stop still protects an open real position. On the VM: `sudo python3 kite_tunnel.py "
            "status` (docs/runbooks/fno-live-test.md)."
        )
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
    if not (9 * 60 + 15 <= nm <= 15 * 60 + 40):     # [O24-MC 2026-10-24] the session runs to the 15:40 derivatives close
        return
    if not await is_trading_day(now_ist.date(), settings.DB_PATH):
        return
    import time as _time
    from kite_client import redact_url_credentials
    ok, err = await _kite_probe_get(f"{settings.KITE_BASE_URL}/")
    if not ok:
        logger.warning(
            "kite_endpoint_probe_failed url=%s consec=%d error=%s",
            settings.KITE_BASE_URL,
            _kite_probe_state["consec_failures"] + 1, err,
        )
    msg = _kite_probe_evaluate(ok, _time.monotonic(), _kite_probe_state)
    if msg is not None:
        await _kite_probe_notify(msg)
    target = _order_route_probe_target()
    if target is None:
        return
    url, proxy = target
    route = url.rstrip("/") + (f" through {redact_url_credentials(proxy)}" if proxy else "")
    if proxy and (settings.KITE_ORDER_BASE_URL or "").strip():
        # [O25f] Both set: kite_client refuses every real order; nothing is sent through the pair.
        ok, err = False, "KITE_ORDER_PROXY_URL and KITE_ORDER_BASE_URL are both set"
    else:
        ok, err = await _kite_probe_get(url, proxy)
    if not ok:
        logger.warning("kite_order_route_probe_failed route=%s consec=%d error=%s", route,
                       _kite_order_route_probe_state["consec_failures"] + 1, redact_url_credentials(err))
    msg = _kite_probe_evaluate(ok, _time.monotonic(), _kite_order_route_probe_state, route=route)
    if msg is not None:
        await _kite_probe_notify(msg)


async def _kite_probe_get(url: str, proxy: str = "") -> tuple[bool, str]:
    """(answered, error): a GET of Kite's root, through ``proxy`` when one is given (no credentials sent)."""
    import httpx as _httpx
    try:
        async with (_httpx.AsyncClient(proxy=proxy) if proxy else _httpx.AsyncClient()) as client:
            resp = await client.get(url, timeout=8.0)
        # Any response < 500 means the hop is up (relay root proxies to
        # Kite's root, which returns 200 -- see smoke_relay.sh). A 5xx
        # from the relay means the path to Kite is broken even though
        # the relay process answered: that IS an outage for us.
        if resp.status_code < 500:
            return True, ""
        return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


async def _kite_probe_notify(msg: str) -> None:
    import httpx as _httpx
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


# ---------------------------------------------------------------------------
# [OUTAGE-2026-07-13 DEFECT 3+4] Trading-readiness watchdog.
# ---------------------------------------------------------------------------
# On 2026-07-13 the engine ran from 09:44 to close with no Kite token. It was
# alive, the scheduler ticked every 60s, /health returned 200, all five
# containers showed "healthy", and every single scan logged `no_access_token`.
# Zero Telegram messages were sent all day.
#
# Three existing watchdogs all looked straight past it:
#   * the scheduler-freeze watchdog watches for a STALLED loop -- the loop was
#     fine, it was just doing nothing;
#   * the relay probe watches Kite reachability -- Kite was reachable;
#   * the token reconciliation cron only paged on DISAGREEMENT between python
#     and node, and both sides were dead, which it read as agreement.
#
# The last of those is fixed in token_lifecycle. But it still depends on node
# being REACHABLE (it returns early when node is down), so it can be silenced by
# a second fault. This watchdog is the single-sided one: it asks the only
# question that matters, of the engine alone.
#
#     "It is a trading day, the market is open. Can I trade? No? Say so."
#
# Deliberately NOT wired to the docker healthcheck: that drives autoheal, which
# restarts the container, and no number of restarts produces a Kite token. See
# routes_ops.health_check.

_readiness_state = {"last_alert_monotonic": None, "was_ready": True}
READINESS_ALERT_MIN_INTERVAL_SEC = 1800.0   # re-page at most every 30 min


def _readiness_should_alert(
    ready: bool, now_monotonic: float, state: dict
) -> bool:
    """Pure decision, so the dedupe logic is testable without a clock.

    Alerts on the falling edge immediately, then at most every 30 minutes while
    still down. `None` sentinel rather than 0.0: time.monotonic() can be below
    the interval right after host boot, and 0.0 would suppress the very first
    page of the day -- which, on 2026-07-13, was the only one that mattered.
    """
    if ready:
        return False
    last = state["last_alert_monotonic"]
    if last is None:
        return True
    return (now_monotonic - last) >= READINESS_ALERT_MIN_INTERVAL_SEC


async def _trading_readiness_tick():
    """Market-hours cron: page if the engine cannot trade. Never raises."""
    try:
        import main as _main
        from market_calendar import is_trading_day
        from operator_alert import notify_operator

        now_ist = datetime.now(IST)
        nm = now_ist.hour * 60 + now_ist.minute
        # 09:30 -- 15:15 IST. Starts after the open (the operator's login lands
        # around 09:05-09:15 and post-login init takes ~20s, so paging at 09:16
        # would just be noise), ends before the 15:30 close.
        if not (9 * 60 + 30 <= nm <= 15 * 60 + 15):
            return
        if not await is_trading_day(now_ist.date(), settings.DB_PATH):
            return

        armed = bool(_main.kite.access_token)
        scheduler_running = bool(getattr(_main.scheduler, "running", False))
        from order_execution_readiness import BLOCKED, snapshot as order_readiness
        from halt_switch import halt_state
        execution = order_readiness()
        execution_blocked = execution["status"] == BLOCKED
        entry_halted, halt_attribution = halt_state(None)
        # [O9-R1 2026-10-09] Token + scheduler said "ready" all Oct 9 afternoon
        # while the empty symbol cache made every equity scan a no-op.
        status_of = getattr(_main.kite, "instrument_cache_status", None)
        cache = status_of() if callable(status_of) else {"usable": True}
        cache_ok = bool(cache.get("usable"))
        ready = (armed and scheduler_running and not execution_blocked
                 and not entry_halted and cache_ok)

        recovered = ready and not _readiness_state["was_ready"]
        _readiness_state["was_ready"] = ready

        if recovered:
            _readiness_state["last_alert_monotonic"] = None
            logger.info("trading_readiness_recovered")
            await notify_operator(
                "✅ ENGINE RE-ARMED — token, scheduler, and entry halt are clear. "
                f"Broker order authorization: {execution['status']}. "
                "UNVERIFIED means no accepted order has yet proved this route.",
                event="trading_readiness_recovered",
            )
            return

        now = time.monotonic()
        if not _readiness_should_alert(ready, now, _readiness_state):
            return
        _readiness_state["last_alert_monotonic"] = now

        reasons = []
        if not armed:
            reasons.append("no Kite token (the engine is not logged in)")
        if not scheduler_running:
            reasons.append("the job scheduler is not running")
        if execution_blocked:
            reasons.append(
                "Kite order authorization is BLOCKED: "
                + str(execution.get("reason") or "permission/static-IP rejection")
            )
        if not cache_ok:
            reasons.append(
                f"the NSE symbol list is unavailable (size {cache.get('size')}, "
                f"last error {cache.get('last_error_type') or 'none'}); "
                "new-entry equity scans cannot resolve symbols; Smart exits for held "
                "names fall back to symbol quotes -- recovery retries every 2 min"
            )
        if entry_halted:
            reasons.append(
                "global entry halt is active: "
                + str((halt_attribution or {}).get("reason") or "no reason recorded")
            )

        logger.error(
            "trading_readiness_failed armed=%s scheduler_running=%s "
            "execution_status=%s entry_halted=%s instrument_cache_size=%s",
            armed, scheduler_running, execution["status"], entry_halted, cache.get("size"),
        )
        await notify_operator(
            "🔴 NOT TRADING — the market is open and the engine cannot trade.\n\n"
            "Cause: " + "; ".join(reasons) + ".\n\n"
            "The engine is UP and looks healthy -- the scheduler is ticking and "
            "every container reports healthy -- but every scan is a no-op. This "
            "is the 2026-07-13 outage.\n\n"
            "If the token is missing, re-login via /login and check /data disk "
            "space. If order authorization is blocked, verify KITE_BASE_URL and "
            "the relay's current public IP in the Kite developer console; do not "
            "clear the halt until the route is corrected.",
            event="trading_readiness_failed",
        )
    except Exception as e:
        # A watchdog that crashes is a watchdog that is not watching.
        logger.error("trading_readiness_tick_failed error=%s", str(e))
