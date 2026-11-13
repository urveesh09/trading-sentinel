"""[TR01] The live tick recorder (tick_recorder.py): Kite's binary frames, the day's folder, the limits, the
connection loop and the scheduler's entry point. Offline: fake contract books and a fake socket."""
import asyncio
import json
import lzma
import struct
from datetime import date, datetime

import pytest

import tick_recorder as tr
from config import settings
from fno_models import Contract

IST = tr.IST
DAY = date(2026, 11, 16)                                     # a Monday


def at(h, m, s=0):
    return IST.localize(datetime(2026, 11, 16, h, m, s))


def full_packet(token, ltp, *, volume=1000, oi=5000, bids=None, asks=None):
    bids = bids or [(65, max(ltp - 5, 0), 3)] * 5
    asks = asks or [(130, ltp + 5, 4)] * 5
    lo = lambda x: max(x, 0)  # noqa: E731
    head = struct.pack(">11I", token, ltp, 2, ltp, volume, 900, 800, lo(ltp - 100), ltp + 100, lo(ltp - 200), lo(ltp - 50))
    ext = struct.pack(">5I", 1763270000, oi, oi + 10, oi - 10, 1763270001)
    depth = b"".join(struct.pack(">IIH2x", q, p, o) for q, p, o in list(bids) + list(asks))
    return head + ext + depth


def index_packet(token, ltp):
    return struct.pack(">8I", token, ltp, ltp + 10, ltp - 10, ltp - 5, ltp - 20, 0, 1763270002)


def frame(*packets):
    return len(packets).to_bytes(2, "big") + b"".join(len(p).to_bytes(2, "big") + p for p in packets)


class Book:
    """A contract book like fno_instruments.FnoInstruments for one underlying."""

    def __init__(self, und, segment, seg_code, centre, step, lot):
        self.underlying, self.segment, self.strike_step = und, segment, float(step)
        self.future_expiries = [date(2026, 11, 24), date(2026, 12, 29), date(2027, 1, 26)]
        self.option_expiries = [date(2026, 11, 12), date(2026, 11, 17), date(2026, 11, 24), date(2026, 12, 1),
                                date(2026, 12, 8)]
        self.by_key, n = {}, 1
        for e in self.future_expiries:
            self.by_key[(und, e.isoformat(), 0.0, "FUT")] = Contract((n << 8) | seg_code, f"{und}{e:%y%b}FUT", und,
                                                                     e, 0.0, "FUT", lot)
            n += 1
        for e in self.option_expiries:
            for k in range(-40, 41):
                strike = float(centre + k * step)
                for kind in ("CE", "PE"):
                    self.by_key[(und, e.isoformat(), strike, kind)] = Contract((n << 8) | seg_code,
                                                                               f"{und}{strike:.0f}{kind}", und, e,
                                                                               strike, kind, lot)
                    n += 1

    def ready(self, today):
        return True

    def strikes_window(self, forward, window):
        atm = round(forward / self.strike_step) * self.strike_step
        return [atm + i * self.strike_step for i in range(-window, window + 1)]

    def option(self, expiry, strike, kind):
        return self.by_key.get((self.underlying, expiry.isoformat(), float(strike), kind.value))

    def token(self, key):
        return self.by_key[key].token


def books():
    return {"NIFTY": Book("NIFTY", "NFO", 2, 25000, 50, 65), "SENSEX": Book("SENSEX", "BFO", 5, 82000, 100, 20)}


@pytest.fixture
def rec(tmp_path, monkeypatch):
    tr.reset()
    monkeypatch.setattr(settings, "TICK_RECORDER_ENABLED", True)
    monkeypatch.setattr(settings, "TICK_RECORDER_PATH", str(tmp_path / "ticks"))
    monkeypatch.setattr(settings, "TICK_RECORDER_EXPIRIES", 3)
    monkeypatch.setattr(settings, "TICK_RECORDER_STRIKES", 2)
    monkeypatch.setattr(settings, "TICK_RECORDER_CHUNK_SEC", 0.0)
    monkeypatch.setattr(settings, "TICK_RECORDER_DAY_MAX_BYTES", 10 ** 9)
    monkeypatch.setattr(settings, "TICK_RECORDER_TOTAL_MAX_BYTES", 10 ** 10)
    monkeypatch.setattr(settings, "TICK_RECORDER_RETENTION_DAYS", 60)
    monkeypatch.setattr(settings, "TICK_RECORDER_DAILY_NOTE", True)
    monkeypatch.setenv("ZERODHA_API_KEY", "key123")
    state = {"now": at(9, 15), "token": "tok-SECRET-1", "notes": [], "sleeps": []}
    monkeypatch.setattr(tr, "_token", lambda now=None: state["token"])
    monkeypatch.setattr(tr, "_now", lambda: state["now"])

    async def notify(text, event="operator_alert"):
        state["notes"].append(text)
        return True
    import operator_alert
    monkeypatch.setattr(operator_alert, "notify_operator", notify)

    async def sleep(sec):
        state["sleeps"].append(sec)
    monkeypatch.setattr(tr, "_sleep", sleep)
    yield state
    tr.reset()


class FakeSocket:
    """One connection: frames in order (a callable is called, then a heartbeat), then ``end`` is raised."""

    def __init__(self, frames, end=None):
        self.frames, self.end, self.sent = list(frames), end or ConnectionError("closed"), []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, text):
        self.sent.append(json.loads(text))

    async def recv(self):
        if not self.frames:
            raise self.end
        item = self.frames.pop(0)
        if callable(item):
            item()
            return b"\x00"
        return item


def connector(sockets, urls):
    def connect(url):
        urls.append(url)
        if not sockets:
            raise ConnectionError("no more")
        item = sockets.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item
    return connect


def day_dir(tmp_path):
    return tmp_path / "ticks" / DAY.isoformat()


def all_rows(path):
    rows = []
    for chunk in sorted(path.glob("chunk-*.bin.xz")):
        rows += tr.read_chunk(chunk)
    return rows


# --- frames and packets ------------------------------------------------------------------------------------------

def test_a_full_packet_is_decoded_as_kites_documentation_lays_it_out():
    token = (77 << 8) | 2
    packet = full_packet(token, 12345, bids=[(65, 12340 - i * 5, 2) for i in range(5)],
                         asks=[(130, 12350 + i * 5, 3) for i in range(5)])
    assert len(packet) == 184
    row = tr.decode_packet(packet)
    assert row["token"] == token and row["ltp"] == 123.45 and row["volume"] == 1000 and row["oi"] == 5000
    assert row["bids"][0] == {"qty": 65, "price": 123.40, "orders": 2}
    assert row["asks"][4] == {"qty": 130, "price": 123.70, "orders": 3}
    assert row["exchange_ts"] == 1763270001
    index = tr.decode_packet(index_packet(256265, 2500000))
    assert index["ltp"] == 25000.0 and index["high"] == 25000.10 and index["exchange_ts"] == 1763270002


def test_frames_split_into_packets_a_heartbeat_has_none_and_a_bad_frame_is_refused():
    a, b = full_packet(258, 100), index_packet(265, 8200000)
    assert tr.split_frame(frame(a, b)) == [a, b]
    assert tr.split_frame(b"\x00") == []
    with pytest.raises(ValueError):
        tr.split_frame(frame(a)[:-10])
    assert tr.packet_ltp(a) == 1.0 and tr.packet_token(b) == 265


# --- the day's folder ------------------------------------------------------------------------------------------

def test_a_chunk_keeps_every_packet_grouped_by_instrument_with_a_true_manifest(tmp_path, rec):
    store = tr.DayStore(tmp_path / "ticks", DAY.isoformat(), day_max=10 ** 9, total_max=10 ** 10, chunk_sec=0)
    p1, p2 = full_packet(258, 100), full_packet(514, 200)
    store.add(514, 3, p2)
    store.add(258, 1, p1)
    store.add(514, 2, full_packet(514, 201))
    entry = store.write(store.take())
    rows = tr.read_chunk(store.dir / entry["file"])
    assert [(r["token"], r["recv_ns"]) for r in rows] == [(258, 1), (514, 3), (514, 2)]
    manifest = json.loads((store.dir / "manifest.json").read_text())
    import hashlib
    assert manifest["chunks"][0]["sha256"] == hashlib.sha256((store.dir / entry["file"]).read_bytes()).hexdigest()
    assert manifest["chunks"][0]["records"] == 3 and manifest["format"] == tr.FORMAT
    assert not list(store.dir.glob("*.part"))


def test_the_limits_stop_recording_and_old_days_alone_are_pruned(tmp_path, rec):
    root = tmp_path / "ticks"
    store = tr.DayStore(root, DAY.isoformat(), day_max=50, total_max=10 ** 10, chunk_sec=0)
    store.add(258, 1, full_packet(258, 100))
    store.write(store.take())
    assert store.capped == "day_cap"
    (root / "2026-09-01").mkdir()
    (root / "2026-09-01" / "x.bin").write_bytes(b"x" * 1000)
    (root / "notes").mkdir()
    other = tr.DayStore(root, "2026-11-17", day_max=10 ** 9, total_max=500, chunk_sec=0)
    assert other.capped == "total_cap"
    assert tr.prune(root, date(2026, 11, 17), 60) == ["2026-09-01"]
    assert (root / "notes").exists() and (root / DAY.isoformat()).exists()


# --- what is recorded ------------------------------------------------------------------------------------------

def test_the_universe_starts_with_indices_and_futures_and_widens_but_never_narrows():
    b = books()
    u = tr.Universe(DAY, books=b, expiries=3, strikes=2)
    first = u.initial()
    assert {m["type"] for m in first} == {"INDEX", "FUT"} and len(first) == 3 + 2 * 2
    nifty_front = b["NIFTY"].token(("NIFTY", "2026-11-24", 0.0, "FUT"))
    chain = u.on_future_price(nifty_front, 25010.0)
    assert len(chain) == 3 * 5 * 2
    assert {m["expiry"] for m in chain} == {"2026-11-17", "2026-11-24", "2026-12-01"}   # not the expired 11-12
    assert {m["strike"] for m in chain} == {24900.0, 24950.0, 25000.0, 25050.0, 25100.0}
    assert u.on_future_price(nifty_front, 25040.0) == []                               # within half a window
    wider = u.on_future_price(nifty_front, 25120.0)
    assert {m["strike"] for m in wider} == {25150.0, 25200.0} and len(u.meta) == 7 + 30 + 12
    assert all(m["exchange"] == "NFO" for m in chain)
    sensex_front = b["SENSEX"].token(("SENSEX", "2026-11-24", 0.0, "FUT"))
    assert all(m["exchange"] == "BFO" for m in u.on_future_price(sensex_front, 82000.0))


def test_the_universe_stops_at_the_connection_limit(monkeypatch):
    monkeypatch.setattr(tr, "MAX_TOKENS", 10)
    b = books()
    u = tr.Universe(DAY, books=b, expiries=3, strikes=2)
    u.initial()
    u.on_future_price(b["NIFTY"].token(("NIFTY", "2026-11-24", 0.0, "FUT")), 25000.0)
    assert len(u.meta) == 10 and u.full


# --- the connection --------------------------------------------------------------------------------------------

def _session(b, rec, extra=()):
    nifty_front = b["NIFTY"].token(("NIFTY", "2026-11-24", 0.0, "FUT"))
    atm_ce = b["NIFTY"].token(("NIFTY", "2026-11-17", 25000.0, "CE"))

    def close():
        rec["now"] = at(15, 42)
    return [frame(full_packet(nifty_front, 2500000), index_packet(256265, 2498000)), b"\x00",
            json.dumps({"type": "order", "data": {"tradingsymbol": "SECRET_ORDER"}}),
            frame(full_packet(atm_ce, 15000), full_packet(atm_ce, 15100)), *extra, close], nifty_front, atm_ce


def test_a_session_is_recorded_whole_and_ends_with_one_owner_line(tmp_path, rec):
    b = books()
    frames, nifty_front, atm_ce = _session(b, rec)
    socket, urls = FakeSocket(frames), []
    asyncio.run(tr.run(connect=connector([socket], urls), clock=lambda: rec["now"], books=b))
    path = day_dir(tmp_path)
    rows = all_rows(path)
    assert [r["token"] for r in rows].count(atm_ce) == 2 and nifty_front in {r["token"] for r in rows}
    assert {r["ltp"] for r in rows if r["token"] == atm_ce} == {150.0, 151.0}
    subscribed = [t for m in socket.sent if m["a"] == "subscribe" for t in m["v"]]
    assert atm_ce in subscribed and 256265 in subscribed and 264969 in subscribed
    assert all(m["v"][0] == "full" for m in socket.sent if m["a"] == "mode")
    manifest = json.loads((path / "manifest.json").read_text())
    assert manifest["complete"] and manifest["note_sent"]
    events = [json.loads(x)["event"] for x in (path / "events.jsonl").read_text().splitlines()]
    assert events[0] == "connected" and "subscribed" in events and events[-1] == "session_end"
    tokens = {json.loads(x)["token"] for x in (path / "instruments.jsonl").read_text().splitlines()}
    assert atm_ce in tokens and len(tokens) == 7 + 30
    assert len(rec["notes"]) == 1 and "Tick recorder 2026-11-16" in rec["notes"][0]
    assert "4 price changes" in rec["notes"][0]
    on_disk = b"".join(p.read_bytes() for p in path.iterdir() if not p.name.endswith(".xz"))
    on_disk += b"".join(lzma.decompress(p.read_bytes()) for p in path.glob("*.xz"))
    assert b"SECRET_ORDER" not in on_disk and b"tok-SECRET" not in on_disk and b"key123" not in on_disk
    assert tr.stats()["text_frames"] == 1 and tr.stats()["state"] == "OFF"


def test_a_drop_reconnects_resubscribes_everything_and_never_writes_the_token(tmp_path, rec):
    b = books()
    nifty_front = b["NIFTY"].token(("NIFTY", "2026-11-24", 0.0, "FUT"))
    first = FakeSocket([frame(full_packet(nifty_front, 2500000))], end=RuntimeError("wss://ws.kite.trade?access_token=tok-SECRET-1"))
    frames, _f, atm_ce = _session(b, rec)
    second, urls = FakeSocket(frames), []
    asyncio.run(tr.run(connect=connector([first, second], urls), clock=lambda: rec["now"], books=b))
    assert len(urls) == 2 and rec["sleeps"] == [tr.BACKOFF_FIRST_SEC]
    resub = {t for m in second.sent if m["a"] == "subscribe" for t in m["v"]}
    assert atm_ce in resub                                   # the whole universe again, before any new price
    text = (day_dir(tmp_path) / "events.jsonl").read_text()
    assert '"code": "RuntimeError"' in text and "tok-SECRET" not in text
    assert tr.stats()["errors"] == {"RuntimeError": 1} and tr.stats()["connects"] == 2


def test_a_new_login_reconnects_with_the_new_token(tmp_path, rec):
    b = books()

    def relogin():
        rec["token"] = "tok-SECRET-2"
    frames, _f, _c = _session(b, rec)
    first, second, urls = FakeSocket([relogin]), FakeSocket(frames), []
    asyncio.run(tr.run(connect=connector([first, second], urls), clock=lambda: rec["now"], books=b))
    assert "tok-SECRET-1" in urls[0] and "tok-SECRET-2" in urls[1] and rec["sleeps"] == []


def test_a_refusal_waits_long_and_tells_the_owner_once(tmp_path, rec):
    class Refused(Exception):
        status_code = 403

    async def sleep(sec):
        rec["sleeps"].append(sec)
        if len(rec["sleeps"]) == 2:
            rec["now"] = at(15, 45)
    tr._sleep = sleep
    try:
        asyncio.run(tr.run(connect=connector([Refused(), Refused()], []), clock=lambda: rec["now"], books=books()))
    finally:
        tr._sleep = asyncio.sleep
    assert rec["sleeps"] == [tr.REFUSED_RETRY_SEC] * 2
    refusals = [n for n in rec["notes"] if "refused" in n]
    assert len(refusals) == 1 and "(403)" in refusals[0]


def test_the_day_limit_ends_the_day_and_says_so(tmp_path, rec, monkeypatch):
    monkeypatch.setattr(settings, "TICK_RECORDER_DAY_MAX_BYTES", 100)
    b = books()
    frames, _f, _c = _session(b, rec)
    asyncio.run(tr.run(connect=connector([FakeSocket(frames + [b"\x00"] * 5)], []), clock=lambda: rec["now"],
                       books=b))
    assert tr.stats()["capped"] == DAY.isoformat()
    assert any("size limit" in n for n in rec["notes"])
    rec["now"] = at(10, 0)
    assert not tr._should_run(rec["now"], DAY.isoformat())


# --- the scheduler's entry point --------------------------------------------------------------------------------

def test_ensure_starts_only_on_a_trading_day_in_the_session_with_todays_login(rec, monkeypatch):
    days = {"open": True}

    async def trading(day):
        return days["open"]
    monkeypatch.setattr(tr, "_is_trading_day", trading)
    started = []

    async def fake_run():
        started.append(1)
    monkeypatch.setattr(tr, "run", fake_run)

    async def go(now):
        result = await tr.ensure_tick(now)
        await asyncio.sleep(0)
        return result["status"]

    async def scenario():
        assert await go(at(8, 59)) == "outside_session"
        assert await go(at(15, 41)) == "outside_session"
        days["open"] = False
        assert await go(at(10, 0)) == "non_trading_day"
        days["open"] = True
        rec["token"] = None
        assert await go(at(10, 0)) == "no_fresh_token"
        rec["token"] = "tok-SECRET-1"
        assert await go(at(10, 0)) == "started"
        settings.TICK_RECORDER_ENABLED = False
        assert await go(at(10, 1)) == "disabled"
        settings.TICK_RECORDER_ENABLED = True
    asyncio.run(scenario())
    assert started == [1]
    tr._task["task"] = None
    assert asyncio.run(tr.ensure_tick(IST.localize(datetime(2026, 11, 14, 10, 0))))["status"] == "outside_session"


def test_a_book_ready_late_is_added_once_it_is_ready(tmp_path, rec, monkeypatch):
    monkeypatch.setattr(tr, "BOOK_RECHECK_SEC", 0.0)
    b = books()
    late = {"ready": False}
    b["SENSEX"].ready = lambda today: late["ready"]

    def refresh():
        late["ready"] = True
    frames, _f, _c = _session(b, rec, extra=(refresh, b"\x00"))
    socket = FakeSocket(frames)
    asyncio.run(tr.run(connect=connector([socket], []), clock=lambda: rec["now"], books=b))
    sensex_front = b["SENSEX"].token(("SENSEX", "2026-11-24", 0.0, "FUT"))
    first_batch = socket.sent[0]["v"]
    later = {t for m in socket.sent[2:] if m["a"] == "subscribe" for t in m["v"]}
    assert sensex_front not in first_batch and sensex_front in later
