"""[O24g 2026-10-24] The partner's order updates over Kite's websocket: a doorbell for the trade watch.

Why: the watch reads the partner's order book every PARTNER_WATCH_POLL_SEC
(5 s), so a change waits up to that long (2.5 s on average) before it is
seen. Kite also pushes each order update of the logged-in user on its
websocket, as a text frame {"type": "order", "data": {...}}. This module
listens for those and wakes the watch (``partner_watch.wake``), which then
reads the book over REST as on every tick. The stream is never trusted for
state: an update missed, repeated or out of order changes only when the next
read happens, and the 5 s reads go on whatever the stream does.

  - Off unless PARTNER_WATCH_STREAM_ENABLED (and a partner API key). Each
    watch tick calls ``ensure``: it starts the stream while the partner's
    login is held, 09:00-15:40; the stream stops when the login is gone or
    the session ends, and reconnects for a new login.
  - PARTNER_KITE_WS_URL?api_key=..&access_token=.. with the partner's own
    key. A refusal (HTTP 401 or 403: a plan without the websocket) is
    REFUSED and tried again every REFUSED_RETRY_SEC, so an upgraded plan
    works without a restart; without the websockets library it is the same.
    Any other failure reconnects after a backoff (1 s, doubling to 60 s). No
    frame for HEARTBEAT_TIMEOUT_SEC (Kite sends a 1-byte heartbeat about
    every second): reconnect.
  - Binary frames (heartbeats, market data) are counted and dropped: nothing
    is subscribed.
  - The access token is in the URL, so it is never logged: errors are
    logged by type or HTTP status only, and Kite's error frames by kind.
  - ``stats()``: the state, connections, order updates, frames, errors, and
    the lag from the exchange's update time to receipt, for
    partner_watch_report.

Never: an order, a change or a cancellation (it only listens).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Callable, Optional
from urllib.parse import urlencode

import pytz
import structlog

import background_tasks
import partner_broker_sync as zerodha
from config import settings

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

START_MIN = 9 * 60                 # with the 09:00 login prompt
HEARTBEAT_TIMEOUT_SEC = 10.0
BACKOFF_FIRST_SEC = 1.0
BACKOFF_MAX_SEC = 60.0
REFUSED_RETRY_SEC = 1800.0
OPEN_TIMEOUT_SEC = 10.0
LAG_SAMPLES = 2000

_stats: dict = {}
_task: dict = {"task": None}
_sleep = asyncio.sleep               # (tests)


def _fresh_stats() -> dict:
    return {"state": "OFF", "since": None, "connects": 0, "updates": 0, "frames": 0, "errors": {}, "lag_ms": []}


_stats.update(_fresh_stats())


def enabled() -> bool:
    return bool(settings.PARTNER_WATCH_STREAM_ENABLED) and bool(settings.PARTNER_KITE_API_KEY)


def stats() -> dict:
    """A copy of the stream's numbers (for the tick statistics and the status)."""
    return json.loads(json.dumps(_stats))


def reset() -> None:
    """Forget the numbers (tests)."""
    _stats.clear()
    _stats.update(_fresh_stats())


def _clock() -> datetime:
    from partner_watch import _now
    return _now()


def _token() -> Optional[str]:
    session = zerodha._session
    return session.access_token if session is not None else None


def _should_run(now: datetime) -> bool:
    minute = now.hour * 60 + now.minute
    return enabled() and zerodha.connected(now) and START_MIN <= minute < zerodha.CLOSE_MIN


def _url(token: str) -> str:
    return f"{settings.PARTNER_KITE_WS_URL}?{urlencode({'api_key': settings.PARTNER_KITE_API_KEY, 'access_token': token})}"


def _set(state: str, now: Optional[datetime] = None) -> None:
    if _stats["state"] != state:
        _stats["state"], _stats["since"] = state, (now or datetime.now(IST)).isoformat()


def _error(code: str) -> None:
    _stats["errors"][code] = _stats["errors"].get(code, 0) + 1


def _code(exc: BaseException) -> str:
    """An error's HTTP status or type name; never its message (it can carry the URL)."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return str(status) if status is not None else type(exc).__name__


def ensure() -> None:
    """Start the stream when it should run and is not running (each watch tick calls this; it costs nothing)."""
    if not _should_run(_clock()):
        return
    loop = asyncio.get_running_loop()
    task = _task["task"]
    if task is not None and not task.done() and task.get_loop() is loop:
        return
    _task["task"] = background_tasks.spawn(run(), name="partner_watch_stream", loop=loop)


def _connect(url: str):
    import websockets           # imported here: the engine runs without it (the stream is then REFUSED)
    return websockets.connect(url, open_timeout=OPEN_TIMEOUT_SEC, ping_interval=None, close_timeout=2,
                              max_size=2 ** 20)


async def run(connect: Optional[Callable] = None, clock: Optional[Callable[[], datetime]] = None) -> None:
    """Listen while the stream should run (``_should_run``); reconnect as the module doc says."""
    connect, clock = connect or _connect, clock or _clock
    backoff = BACKOFF_FIRST_SEC
    try:
        while _should_run(clock()):
            token = _token()
            if token is None:
                break
            _set("CONNECTING", clock())
            try:
                async with connect(_url(token)) as socket:
                    _stats["connects"] += 1
                    _set("LIVE", clock())
                    backoff = BACKOFF_FIRST_SEC
                    while _token() == token and _should_run(clock()):
                        _frame(await asyncio.wait_for(socket.recv(), HEARTBEAT_TIMEOUT_SEC), clock())
                continue                                    # a new login, or the session is over
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                code = "no_library" if isinstance(exc, ImportError) else _code(exc)
                _error(code)
                if code in ("401", "403", "no_library"):
                    _set("REFUSED", clock())
                    logger.warning("partner_watch_stream_refused code=%s", code)
                    await _sleep(REFUSED_RETRY_SEC)
                else:
                    _set("DOWN", clock())
                    logger.warning("partner_watch_stream_down err=%s retry_s=%.0f", code, backoff)
                    await _sleep(backoff)
                    backoff = min(backoff * 2, BACKOFF_MAX_SEC)
    finally:
        _set("OFF")


def _frame(frame, now: datetime) -> None:
    """One frame: an order update wakes the watch; everything else is counted."""
    _stats["frames"] += 1
    if isinstance(frame, (bytes, bytearray)):
        return                                              # a heartbeat or market data: nothing is subscribed
    try:
        message = json.loads(frame)
    except ValueError:
        _error("bad_frame")
        return
    if not isinstance(message, dict):
        return
    kind = message.get("type")
    if kind == "order":
        _stats["updates"] += 1
        data = message.get("data") if isinstance(message.get("data"), dict) else {}
        at = zerodha.kite_time(data.get("exchange_update_timestamp") or data.get("exchange_timestamp")
                               or data.get("order_timestamp"))
        if at is not None and len(_stats["lag_ms"]) < LAG_SAMPLES:
            _stats["lag_ms"].append(round((now - at).total_seconds() * 1000))
        from partner_watch import wake
        wake("order")
    elif kind == "error":
        _error("kite_error")
        logger.warning("partner_watch_stream_kite_error")  # its text can echo the request: not logged
