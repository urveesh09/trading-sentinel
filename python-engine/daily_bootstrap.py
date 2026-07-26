"""[BOOTSTRAP-2026-07-17] Token-aware daily bootstrap registry.

Why this module exists -- what happened on 2026-07-17:

The 08:00 IST cron cluster (penny universe refresh, F&O NFO instruments
snapshot) fired while the engine held NO fresh Kite token (Zerodha tokens
expire ~06:00 IST daily; the operator logged in at 08:05). Every job failed,
none retried, and APScheduler logged each as "executed successfully":

  - F&O skipped every tick from 09:15 to the power cut with
    `instruments_not_ready` -- the module was dead all day.
  - Penny ran on the PREVIOUS day's universe file (no promoter/PB corp
    data attached), so 81/81 tickers scanned "degraded" and the
    fundamentals gates restored by 6885a83 were bypassed-in-effect on
    their first live day.

The failure class is "daily job assumed a token that arrives later". This
registry inverts that: bootstrap tasks run when BOTH are true -- it is a
trading day AND a token issued TODAY is armed. Entry points:

  1. 08:00 cron  -> token fresh? run : send ONE Telegram reminder + defer.
  2. POST /token -> post_login_initialization calls run_pending("post_login"),
     so the moment the operator logs in, whatever is still pending runs.
  3. Safety tick (every 10 min, 08:00-15:30) -> catches transient task
     failures after a successful login (e.g. screener.in corp fetch blip).

Each task records success PER IST DAY in /data/daily_bootstrap_state.json
(atomic tmp+rename write -- see the 2026-07-13 truncate-on-write outage for
why). A task that failed stays pending and is retried by the next entry
point; a task that succeeded is never re-run that day, so repeated logins
are cheap no-ops.

Singletons (`kite`, task runners) are resolved lazily through `import main`
on every call -- the test suite patches them BY NAME on main (see
scheduler_setup.py's header comment for the full rationale).
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime

import pytz
import structlog

from config import settings

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

# Task name -> short human label used in logs / the reminder message.
TASK_LABELS = {
    "penny_universe": "penny universe + corp fundamentals refresh",
    "fno_instruments": "F&O NFO instruments snapshot",
}

_run_lock = asyncio.Lock()
_reminder_sent_for: str | None = None  # IST date iso of the last 08:00 reminder


def _state_path() -> str:
    return os.path.join(os.path.dirname(settings.DB_PATH), "daily_bootstrap_state.json")


def _today_ist() -> str:
    return datetime.now(IST).date().isoformat()


def _load_state() -> dict:
    """{"date": "YYYY-MM-DD", "done": {task: true}} -- resets on date change."""
    try:
        with open(_state_path()) as f:
            state = json.load(f)
        if state.get("date") == _today_ist():
            return state
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"date": _today_ist(), "done": {}}


def _save_state(state: dict) -> None:
    """Atomic write (tmp + rename). A torn/empty state file must never be
    possible: worst case it re-runs a task, but a truncated JSON here would
    throw on every subsequent load -- same shape as the 2026-07-13 token
    file outage."""
    path = _state_path()
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".bootstrap-")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    except OSError as e:
        logger.warning("daily_bootstrap_state_write_failed error=%s", str(e))


def token_is_fresh_today() -> bool:
    """A token counts as fresh only if it was ARMED today (IST).

    `kite.access_token` being non-empty is NOT enough: on a day where the
    engine never restarted, it still holds YESTERDAY'S token -- set, but
    expired at the broker (~06:00 IST). set_token() stamps
    `token_set_ist_date`; restore-on-startup goes through set_token too,
    and the restore path only accepts a same-day persisted token.
    """
    import main as _main

    kite = _main.kite
    if not getattr(kite, "access_token", ""):
        return False
    return getattr(kite, "token_set_ist_date", None) == datetime.now(IST).date()


def pending_tasks() -> list[str]:
    done = _load_state()["done"]
    return [t for t in TASK_LABELS if not done.get(t)]


def _mark_done(task: str) -> None:
    state = _load_state()
    state["done"][task] = True
    _save_state(state)


async def _run_task(task: str) -> bool:
    """Run one task; True == verified success (not merely 'did not raise')."""
    import main as _main

    if task == "penny_universe":
        # run_penny_universe_refresh returns True only when refresh_from_kite
        # actually produced a ranked universe (see its 2026-07-17 change).
        return bool(await _main.run_penny_universe_refresh())

    if task == "fno_instruments":
        # [PARTNER-TIPS 2026-07-18] Refresh every analytics book (NIFTY +
        # BANKNIFTY from one NFO dump, SENSEX from BFO) in one task.
        # Success is judged on NIFTY ALONE: that book feeds the live
        # paper-trading path; the others are tips-only and a BFO outage
        # must not hold the bootstrap task in "pending" all day.
        from fno_instruments import get_fno_instruments
        from fno_underlyings import refresh_all

        book = get_fno_instruments()
        today = datetime.now(IST).date()
        if book.ready(today):
            # NIFTY already fresh (e.g. disk rehydrate): still top up the
            # analytics books once, best-effort.
            try:
                await refresh_all(_main.kite)
            except Exception as e:
                logger.warning("daily_bootstrap_analytics_refresh_failed error=%s", str(e))
            return True
        try:
            results = await refresh_all(_main.kite)
        except Exception as e:
            logger.error("daily_bootstrap_fno_refresh_failed error=%s", str(e))
            return False
        failed = [k for k, v in results.items() if not v]
        if failed:
            logger.warning(
                "daily_bootstrap_analytics_books_failed names=%s -- partner "
                "tips degrade for these; NIFTY trading path judged separately",
                ",".join(failed),
            )
        return book.ready(today)

    logger.error("daily_bootstrap_unknown_task task=%s", task)
    return False


async def run_pending(trigger: str) -> dict:
    """Run every not-yet-done task for today. Returns {task: bool_ran_ok}.

    Serialised behind one lock: the 08:00 cron, a login and the safety tick
    can all fire within the same minute, and the tasks are not re-entrant
    (penny refresh holds its own in-progress flag but a doubled NFO dump is
    60-90k rows of wasted fetch).
    """
    import main as _main

    results: dict = {}
    today = datetime.now(IST).date()
    if not await _main.is_trading_day(today, settings.DB_PATH):
        logger.info("daily_bootstrap_skip reason=non_trading_day trigger=%s", trigger)
        return results
    if not token_is_fresh_today():
        logger.info("daily_bootstrap_skip reason=no_fresh_token trigger=%s", trigger)
        return results

    async with _run_lock:
        todo = pending_tasks()
        if not todo:
            return results
        logger.info(
            "daily_bootstrap_run trigger=%s tasks=%s", trigger, ",".join(todo)
        )
        for task in todo:
            try:
                ok = await _run_task(task)
            except Exception as e:
                logger.error(
                    "daily_bootstrap_task_crashed task=%s error=%s", task, str(e)
                )
                ok = False
            results[task] = ok
            if ok:
                _mark_done(task)
                logger.info("daily_bootstrap_task_done task=%s trigger=%s", task, trigger)
            else:
                logger.warning(
                    "daily_bootstrap_task_pending task=%s trigger=%s "
                    "-- will retry on next login or safety tick",
                    task, trigger,
                )
    return results


async def bootstrap_0800_job() -> None:
    """The 08:00 IST cron entry. Token fresh -> run; else remind + defer.

    The reminder is load-bearing: pre-2026-07-17 the operator's cue to log
    in was the 400-storm alert from the token-blind quote burst. Gating the
    burst removes that side-effect alarm, so this message replaces it."""
    global _reminder_sent_for
    import main as _main

    today = datetime.now(IST).date()
    if not await _main.is_trading_day(today, settings.DB_PATH):
        logger.info("daily_bootstrap_0800_skip reason=non_trading_day")
        return
    if token_is_fresh_today():
        await run_pending("cron_0800")
        return

    logger.warning("daily_bootstrap_deferred reason=no_fresh_token_at_0800")
    if _reminder_sent_for != today.isoformat():
        _reminder_sent_for = today.isoformat()
        from operator_alert import notify_operator

        pending = ", ".join(TASK_LABELS[t] for t in pending_tasks())
        await notify_operator(
            "⏳ *Daily bootstrap deferred* — no fresh Kite token at 08:00 IST "
            "(Zerodha tokens expire ~06:00 daily).\n"
            f"Waiting: {pending}.\n"
            "Log in via /login — the bootstrap runs automatically the moment "
            "the token arrives.",
            event="daily_bootstrap_deferred",
        )


async def premarket_login_nudge() -> None:
    """07:50 IST: remind the operator to log in BEFORE the 08:00 bootstrap.

    [LOGIN-NUDGE 2026-07-26] Zerodha access tokens die ~06:00 IST and the host
    boots around 06:35-06:50, so the engine starts every session token-blind and
    cannot bootstrap until a human authenticates. The only existing signal is the
    08:00 `daily_bootstrap_deferred` alert -- which fires when the window has
    *already* been missed.

    The margin is thinner than it looks: the penny-universe fetch takes ~55 min,
    so an 08:17 login (2026-07-24) finished at 09:12, three minutes before the
    09:15 open; a 07:05 login (2026-07-23) was comfortable. This nudge is the
    difference between a 10-minute heads-up and an hour of degraded scanning.
    Recommended twice in prior audits (2026-07-21, 2026-07-24) and never wired.

    No-ops when the token is already fresh, so a punctual operator hears nothing.
    """
    import main as _main

    now = datetime.now(IST)
    if not await _main.is_trading_day(now.date(), settings.DB_PATH):
        return
    if token_is_fresh_today():
        logger.info("premarket_login_nudge_skipped reason=token_already_fresh")
        return

    from operator_alert import notify_operator
    await notify_operator(
        "🔑 *Kite login needed* — no fresh token yet and the 08:00 bootstrap is "
        "10 minutes out. The penny-universe refresh takes ~55 min, so logging in "
        "now keeps the full universe ready before the 09:15 open. "
        f"Pending: {', '.join(pending_tasks()) or 'none'}.",
        event="premarket_login_nudge",
    )


async def bootstrap_safety_tick() -> None:
    """10-min safety net, 08:00-15:30 IST. No-op when nothing is pending or
    no fresh token; exists so a transient task failure after a successful
    login (or a login that raced the 08:00 cron) self-heals within 10
    minutes instead of staying broken until tomorrow."""
    import main as _main

    now = datetime.now(IST)
    nm = now.hour * 60 + now.minute
    if not (8 * 60 <= nm <= 15 * 60 + 30):
        return
    if not pending_tasks():
        return
    # [CALENDAR-GATE 2026-07-03] weekend / NSE-holiday early-return (also
    # re-checked inside run_pending; here it keeps weekend logs quiet).
    today = now.date()
    if not await _main.is_trading_day(today, settings.DB_PATH):
        return
    await run_pending("safety_tick")
