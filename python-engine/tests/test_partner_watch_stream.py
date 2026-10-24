"""[O24g] The order stream (partner_watch_stream.py), the watch's wake, and the delivery report.

The stream only wakes the watch; the watch then reads the book as on every
tick. Offline: a fake socket for drops, backoff, a refusal and a new login; a
real local websocket server for the whole path (an order update in, the
message out, found by the woken tick); the report on what a few ticks
recorded.
"""
import asyncio
import json

import aiosqlite
import pytest

import partner_broker_sync as zerodha
import partner_watch as pw
import partner_watch_report as report
import partner_watch_stream as stream
from config import settings
from tests.test_partner_watch import D, _login, _market, _o, kite, partner_app, watch  # noqa: F401


class FakeSocket:
    """One connection: its frames in order (a callable is done, then a heartbeat), then ``end`` is raised."""

    def __init__(self, frames, end=None):
        self.frames, self.end = list(frames), end or ConnectionError("closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def recv(self):
        if not self.frames:
            raise self.end
        frame = self.frames.pop(0)
        if callable(frame):
            frame()
            return b"\x00"
        return frame


@pytest.fixture
def streaming(monkeypatch):
    """The stream on, with a key; its sleeps recorded, not slept; its wakes recorded."""
    monkeypatch.setattr(settings, "PARTNER_WATCH_STREAM_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_KITE_API_KEY", "key123")
    stream.reset()
    sleeps, woke = [], []

    async def no_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(stream, "_sleep", no_sleep)
    monkeypatch.setattr(pw, "wake", lambda reason="order": woke.append(reason))
    yield sleeps, woke
    stream.reset()


ORDER = json.dumps({"type": "order", "data": {"order_id": "201", "status": "TRIGGER PENDING"}})


def test_only_an_order_update_wakes_the_watch(streaming):
    _sleeps, woke = streaming
    for frame in (b"\x00", b"ticks", "not json", json.dumps({"type": "message", "data": "hello"}),
                  json.dumps({"type": "error", "data": "Invalid access token"}),
                  json.dumps({"type": "order", "data": {"order_id": "1", "exchange_update_timestamp":
                                                        "2026-10-23 10:00:00"}})):
        stream._frame(frame, D(10, 0, 1))
    numbers = stream.stats()
    assert woke == ["order"]
    assert (numbers["frames"], numbers["updates"], numbers["errors"]) == (6, 1, {"bad_frame": 1, "kite_error": 1})
    assert numbers["lag_ms"] == [1000]                     # the exchange's update time to receipt


@pytest.mark.asyncio
async def test_the_stream_reconnects_with_backoff_and_ends_with_the_login(watch, kite, streaming):
    sleeps, woke = streaming
    await _login()
    urls = []
    plan = [FakeSocket([b"\x00", ORDER]),                  # an update, then the connection drops
            OSError("network unreachable"),                # the next try fails
            FakeSocket([ORDER, zerodha.disconnect])]       # an update, then the login is gone

    def connect(url):
        urls.append(url)
        item = plan.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    await stream.run(connect=connect, clock=lambda: D(10, 0))
    numbers = stream.stats()
    assert woke == ["order", "order"] and sleeps == [1.0, 2.0]
    assert (numbers["connects"], numbers["state"]) == (2, "OFF")
    assert numbers["errors"] == {"ConnectionError": 1, "OSError": 1}
    assert urls[0].startswith("wss://ws.kite.trade?api_key=key123&access_token=") and plan == []


@pytest.mark.asyncio
async def test_a_refused_stream_waits_long_and_never_logs_the_token(watch, kite, streaming, monkeypatch):
    sleeps, _woke = streaming
    await _login()
    token = zerodha._session.access_token
    logged = []

    class Recorder:                                        # what the stream module logs (whatever logging is set up)
        def warning(self, event, *args, **kwargs):
            logged.append(event % args if args else event)

        info = error = warning

    monkeypatch.setattr(stream, "logger", Recorder())

    class Refused(Exception):
        status_code = 403

    calls = []

    def connect(url):
        calls.append(url)
        if len(calls) == 1:
            raise ImportError("No module named 'websockets'")
        zerodha.disconnect()
        raise Refused(f"server rejected WebSocket connection: HTTP 403 for {url}")

    await stream.run(connect=connect, clock=lambda: D(10, 0))
    assert sleeps == [stream.REFUSED_RETRY_SEC, stream.REFUSED_RETRY_SEC]
    assert stream.stats()["errors"] == {"no_library": 1, "403": 1}
    assert logged == ["partner_watch_stream_refused code=no_library", "partner_watch_stream_refused code=403"]
    assert not any(token in line for line in logged)


@pytest.mark.asyncio
async def test_the_stream_reconnects_for_a_new_login_and_stops_at_the_close(watch, kite, streaming):
    sleeps, _woke = streaming
    await _login()
    first = zerodha._session.access_token
    tokens = []

    def new_login():
        zerodha._session.access_token = first + "x"

    clock = {"now": D(10, 0)}
    plan = [FakeSocket([new_login]), FakeSocket([lambda: clock.update(now=D(15, 40))])]

    def connect(url):
        tokens.append(url.rsplit("=", 1)[1])
        return plan.pop(0)

    await stream.run(connect=connect, clock=lambda: clock["now"])
    assert tokens == [first, first + "x"] and sleeps == [] and stream.stats()["state"] == "OFF"


@pytest.mark.asyncio
async def test_an_order_update_on_the_stream_wakes_the_watch_before_the_next_tick(watch, kite, monkeypatch):
    """The whole path on a local websocket server: the partner moves a stop down; Kite's order update arrives on
    the stream; the woken tick reads the book and the LOWERED message goes, found by the stream, before the next
    5 s tick would have run."""
    websockets = pytest.importorskip("websockets")
    await _login()
    market = _market(D(10, 0))
    kite["orders"] = [_o("101", "BUY", D(9, 59), average_price=75.05),
                      _o("201", "SELL", D(9, 59, 30), order_type="SL", status="TRIGGER PENDING", trigger_price=70.0)]
    for at in (D(10, 0, 0), D(10, 0, 5)):
        await pw.watch_tick(at, market=market)
    count, seen = len(watch), {}

    async def kite_ws(socket):
        seen["path"] = socket.path
        await socket.send(b"\x00")
        kite["orders"][1] = _o("201", "SELL", D(10, 0, 6), order_type="SL", status="TRIGGER PENDING",
                               trigger_price=60.0)
        await socket.send(ORDER)
        await socket.wait_closed()                         # until the stream goes

    async with websockets.serve(kite_ws, "127.0.0.1", 0) as server:
        monkeypatch.setattr(settings, "PARTNER_KITE_WS_URL", f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}")
        monkeypatch.setattr(settings, "PARTNER_WATCH_STREAM_ENABLED", True)
        monkeypatch.setattr(settings, "PARTNER_KITE_API_KEY", "key123")
        stream.reset()
        stream.ensure()
        for _ in range(200):
            if any(m["kind"] == "watch_lowered" for m in watch[count:]):
                break
            await asyncio.sleep(0.02)
        assert stream.stats()["state"] == "LIVE"
        task = stream._task["task"]
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    await pw.settle()
    assert "api_key=key123" in seen["path"] and "access_token=" in seen["path"]
    assert [m["kind"] for m in watch[count:]] == ["watch_lowered"]
    async with aiosqlite.connect(settings.DB_PATH) as db:
        found = await (await db.execute("SELECT kind, detected_by FROM partner_watch_messages WHERE kind IN "
                                        "('PLAN','LOWERED') ORDER BY created_at")).fetchall()
    assert found == [("PLAN", "poll"), ("LOWERED", "stream")]
    stream.reset()


@pytest.mark.asyncio
async def test_wakes_while_a_tick_runs_are_one_more_tick_and_a_scheduled_tick_skips(watch, monkeypatch):
    calls, gate = [], asyncio.Event()

    async def slow(now=None, *, market=None, woken=None):
        calls.append(woken)
        await gate.wait()
        return {"status": "COMPLETED", "ms": 1.0}

    monkeypatch.setattr(pw, "_watch_tick", slow)
    monkeypatch.setattr(pw, "WAKE_GAP_SEC", 0.0)
    first = asyncio.create_task(pw.watch_tick(D(10, 0)))
    await asyncio.sleep(0)
    assert await pw.watch_tick(D(10, 0, 5)) == {"status": "SKIPPED", "reason": "busy"}
    for _ in range(5):
        pw.wake("order")
    gate.set()
    await first
    await pw._tick["woken"]
    assert calls == [None, "order"]                        # the scheduled tick, then one woken tick for five wakes


@pytest.mark.asyncio
async def test_the_report_gives_delivery_and_tick_timings(watch, kite, monkeypatch, capsys):
    monkeypatch.setattr(pw, "_ticks", pw._TickStats())
    await _login()
    market = _market(D(10, 0))
    kite["orders"] = [_o("101", "BUY", D(10, 0), average_price=75.05)]
    for at in (D(10, 0, 5), D(10, 1, 10), D(10, 2, 5), D(10, 2, 10)):
        await pw.watch_tick(at, market=market)
    await pw.settle()
    await pw._ticks.save(settings.DB_PATH, D(10, 2, 11), force=True)
    data = report.report(settings.DB_PATH, "2026-10-23")
    plan, nostop = data["messages"]["PLAN"], data["messages"]["NO_STOP"]
    assert (plan["n"], plan["sent"], plan["outcomes"], plan["by"]) == (1, 1, {"acknowledged": 1}, {"poll": 1})
    assert 5.0 <= plan["seen_s"]["p50"] < 6.0              # bought 10:00:00, found by the 10:00:05 tick
    assert nostop["seen_s"]["p50"] == 5.0                  # due 10:02:00 (120 s after the buy), found at 10:02:05
    ticks = data["ticks"]["2026-10-23"]
    assert ticks["counts"]["COMPLETED"] == 4 and ticks["tick_ms"]["n"] == 4 and ticks["read_ms"]["n"] == 4
    assert report.spread([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]) == {
        "n": 20, "p50": 10, "p95": 19, "max": 20}
    assert report.main(["partner_watch_report", "2026-10-23"]) == 0
    text = capsys.readouterr().out
    assert "Trade watch, 2026-10-23 to 2026-10-23" in text and "  PLAN      1/1 (acknowledged 1); seen " in text
    assert "Ticks 2026-10-23 (1 part): COMPLETED 4;" in text
