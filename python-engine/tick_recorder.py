"""[TR01 2026-11-13] Live tick recorder: every price change of the NIFTY and SENSEX option chains, with 5-level
depth, from the owner's Kite websocket, kept on disk for research.

Why: the minute archive (research_quote_collector) holds one REST snapshot a minute of ~11 strikes. A human scalper
sees every change of the whole near-the-money chain; research can only learn from what was kept. The owner, Nov 13:
"the system records those things, anything and everything that you want".

What it records (one websocket connection, Kite's "full" mode: price, volumes, OI, 5 bids and 5 asks):
  - the indices NIFTY 50, SENSEX and INDIA VIX;
  - each index's front and next-month future;
  - options on the nearest TICK_RECORDER_EXPIRIES expiries, TICK_RECORDER_STRIKES strikes either side of the front
    future, CE and PE. The window is centred on the future's first price and widened (never narrowed) when the
    future moves more than half the window from the last centre, so a contract once recorded stays recorded all day.
    At most MAX_TOKENS instruments (Kite allows 3,000 on one connection).

Storage, under TICK_RECORDER_PATH/<day>/:
  - chunk-<HHMMSS>-<n>.bin.xz: every TICK_RECORDER_CHUNK_SEC, an xz stream of records grouped by instrument and in
    arrival order within one. A record is REC (receipt time in unix ns, packet length) followed by Kite's packet
    bytes, unchanged. Written as .part and renamed when whole, so a crash loses at most the open chunk.
  - instruments.jsonl: token, exchange, tradingsymbol, underlying, type, expiry, strike, lot size, tick size, when.
  - events.jsonl: connected, down, refused, capped, subscribed, session end, with times. Gaps are explicit.
  - manifest.json: every chunk's bytes, sha256, records and first/last receipt; rewritten after each chunk.
  - read_chunk() and decode_packet() turn a chunk back into rows (prices in rupees) for research.

Limits: TICK_RECORDER_DAY_MAX_BYTES a day and TICK_RECORDER_TOTAL_MAX_BYTES in all: recording stops (an event and
one owner message), nothing is deleted to make room. Day folders older than TICK_RECORDER_RETENTION_DAYS are removed
when a new day starts. It runs 09:00-15:41 IST on trading days with a token set today; a new login reconnects with
the new token; any other failure reconnects after a backoff (1 s doubling to 60 s); a refusal (401/403) waits
REFUSED_RETRY_SEC. One short owner message after the close says what was kept.

The access token is in the URL, so it is never logged: errors are logged by HTTP status or type only. Kite's text
frames (the owner's order updates, error notices) are counted and never stored.

Never: an order, a REST call (no share of the quote budget), or anything a trading decision reads.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import lzma
import os
import shutil
import struct
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

import pytz
import structlog

import background_tasks
from config import settings

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

FORMAT = "kite-full-v1"
REC = struct.Struct(">qH")              # receipt unix ns, packet length; then the packet
INDEX_TOKENS: Dict[str, Tuple[int, str]] = {"NIFTY 50": (256265, "NSE"), "SENSEX": (265, "BSE"),
                                            "INDIA VIX": (264969, "NSE")}
UNDERLYINGS = ("NIFTY", "SENSEX")
START_MIN, END_MIN = 9 * 60, 15 * 60 + 41
MAX_TOKENS = 2900
SUBSCRIBE_BATCH = 500
MAX_BUFFER_BYTES = 8 * 2 ** 20          # an early chunk when this much waits
HEARTBEAT_TIMEOUT_SEC = 10.0
OPEN_TIMEOUT_SEC = 10.0
BACKOFF_FIRST_SEC = 1.0
BACKOFF_MAX_SEC = 60.0
REFUSED_RETRY_SEC = 900.0
BOOK_RECHECK_SEC = 60.0
XZ_PRESET = 6

_stats: dict = {}
_task: dict = {"task": None}
_sleep = asyncio.sleep                   # (tests)


def _fresh_stats() -> dict:
    return {"state": "OFF", "since": None, "day": None, "connects": 0, "frames": 0, "packets": 0,
            "text_frames": 0, "bad_frames": 0, "instruments": 0, "chunks": 0, "bytes": 0, "live_sec": 0.0,
            "errors": {}, "capped": None, "note_sent_day": None, "refused_note_day": None}


_stats.update(_fresh_stats())


def stats() -> dict:
    return json.loads(json.dumps(_stats))


def reset() -> None:
    """Forget the numbers (tests)."""
    _stats.clear()
    _stats.update(_fresh_stats())


def enabled() -> bool:
    return bool(settings.TICK_RECORDER_ENABLED)


def _now() -> datetime:
    return datetime.now(IST)


def _api_key() -> str:
    return os.getenv("ZERODHA_API_KEY", "")


def _token(now: Optional[datetime] = None) -> Optional[str]:
    """The owner's Kite token, only if it was set today (yesterday's expired at the broker)."""
    try:
        import main as _main
        kite = _main.kite
    except Exception:
        return None
    token = getattr(kite, "access_token", "") or ""
    today = (now or _now()).date()
    return token if token and getattr(kite, "token_set_ist_date", None) == today else None


def _in_window(now: datetime) -> bool:
    minute = now.hour * 60 + now.minute
    return now.weekday() < 5 and START_MIN <= minute < END_MIN


def _should_run(now: datetime, day: str) -> bool:
    return enabled() and _in_window(now) and _stats.get("capped") != day and _token(now) is not None


def _url(token: str) -> str:
    return f"{settings.TICK_RECORDER_URL}?{urlencode({'api_key': _api_key(), 'access_token': token})}"


def _set(state: str, now: Optional[datetime] = None) -> None:
    if _stats["state"] != state:
        _stats["state"], _stats["since"] = state, (now or _now()).isoformat()


def _error(code: str) -> None:
    _stats["errors"][code] = _stats["errors"].get(code, 0) + 1


def _code(exc: BaseException) -> str:
    """An error's HTTP status or type name; never its message (it can carry the URL)."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return str(status) if status is not None else type(exc).__name__


# ----------------------------------------------------------------------------------------------------------------
# Kite's binary frames
# ----------------------------------------------------------------------------------------------------------------

def split_frame(frame: bytes) -> List[bytes]:
    """The packets of one binary frame (2-byte count, then 2-byte length + packet each); a heartbeat has none.

    Raises ValueError for a frame whose lengths do not add up: nothing of it is kept.
    """
    if len(frame) < 2:
        return []
    count = int.from_bytes(frame[0:2], "big")
    pos, out = 2, []
    for _ in range(count):
        if pos + 2 > len(frame):
            raise ValueError("truncated length")
        length = int.from_bytes(frame[pos:pos + 2], "big")
        pos += 2
        if length < 8 or pos + length > len(frame):
            raise ValueError("bad packet length")
        out.append(bytes(frame[pos:pos + length]))
        pos += length
    return out


def packet_token(packet: bytes) -> int:
    return int.from_bytes(packet[0:4], "big")


def _divisor(token: int) -> float:
    segment = token & 0xFF
    return 1e7 if segment == 3 else 1e4 if segment == 6 else 100.0


def _u32(packet: bytes, at: int) -> int:
    return struct.unpack_from(">I", packet, at)[0]


def packet_ltp(packet: bytes) -> Optional[float]:
    if len(packet) < 8:
        return None
    price = _u32(packet, 4) / _divisor(packet_token(packet))
    return price if price > 0 else None


def decode_packet(packet: bytes) -> dict:
    """One Kite packet as a dict (prices in rupees), the layout of Kite's websocket documentation."""
    token = packet_token(packet)
    div = _divisor(token)
    row: dict = {"token": token, "length": len(packet), "ltp": _u32(packet, 4) / div}
    if token & 0xFF == 9:                                   # an index
        if len(packet) >= 28:
            row.update(high=_u32(packet, 8) / div, low=_u32(packet, 12) / div, open=_u32(packet, 16) / div,
                       close=_u32(packet, 20) / div)
        if len(packet) >= 32:
            row["exchange_ts"] = _u32(packet, 28)
        return row
    if len(packet) >= 44:
        row.update(last_qty=_u32(packet, 8), avg_price=_u32(packet, 12) / div, volume=_u32(packet, 16),
                   buy_qty=_u32(packet, 20), sell_qty=_u32(packet, 24), open=_u32(packet, 28) / div,
                   high=_u32(packet, 32) / div, low=_u32(packet, 36) / div, close=_u32(packet, 40) / div)
    if len(packet) >= 184:
        row.update(last_trade_ts=_u32(packet, 44), oi=_u32(packet, 48), oi_high=_u32(packet, 52),
                   oi_low=_u32(packet, 56), exchange_ts=_u32(packet, 60))
        levels = [(_u32(packet, at), _u32(packet, at + 4) / div, struct.unpack_from(">H", packet, at + 8)[0])
                  for at in range(64, 184, 12)]
        row["bids"] = [{"qty": q, "price": p, "orders": o} for q, p, o in levels[:5]]
        row["asks"] = [{"qty": q, "price": p, "orders": o} for q, p, o in levels[5:]]
    return row


def read_chunk(path) -> List[dict]:
    """A chunk's records, decoded, each with its receipt time (``recv_ns``)."""
    raw = lzma.decompress(Path(path).read_bytes())
    rows, pos = [], 0
    while pos < len(raw):
        recv_ns, length = REC.unpack_from(raw, pos)
        pos += REC.size
        row = decode_packet(raw[pos:pos + length])
        row["recv_ns"] = recv_ns
        rows.append(row)
        pos += length
    return rows


# ----------------------------------------------------------------------------------------------------------------
# What to record
# ----------------------------------------------------------------------------------------------------------------

def _books() -> Dict[str, object]:
    from fno_underlyings import get_instruments_for
    return {name: get_instruments_for(name) for name in UNDERLYINGS}


def _contract_meta(contract, underlying: str, exchange: str) -> dict:
    return {"token": int(contract.token), "exchange": exchange, "tradingsymbol": contract.tradingsymbol,
            "underlying": underlying, "type": contract.instrument_type, "expiry": contract.expiry.isoformat(),
            "strike": float(contract.strike), "lot_size": int(contract.lot_size),
            "tick_size": float(contract.tick_size)}


class Universe:
    """The instruments subscribed today: grows, never shrinks."""

    def __init__(self, today: date, books: Optional[Dict[str, object]] = None,
                 expiries: Optional[int] = None, strikes: Optional[int] = None):
        self.today = today
        self.books = books if books is not None else _books()
        self.expiries = int(expiries if expiries is not None else settings.TICK_RECORDER_EXPIRIES)
        self.strikes = int(strikes if strikes is not None else settings.TICK_RECORDER_STRIKES)
        self.meta: Dict[int, dict] = {}
        self.front: Dict[int, str] = {}               # front future token -> underlying
        self.centre: Dict[str, float] = {}
        self.full = False
        self.ready_names: set = set()                 # books whose futures are in

    def missing(self) -> bool:
        """A book not ready at the start (its 08:00 refresh late): ``initial`` is tried again."""
        return any(name not in self.ready_names for name in self.books)

    def _add(self, meta: dict) -> bool:
        if meta["token"] in self.meta:
            return False
        if len(self.meta) >= MAX_TOKENS:
            self.full = True
            return False
        self.meta[meta["token"]] = meta
        return True

    def initial(self) -> List[dict]:
        """The indices and each ready book's front and next future."""
        added = []
        for name, (token, exchange) in INDEX_TOKENS.items():
            meta = {"token": token, "exchange": exchange, "tradingsymbol": name, "underlying": name,
                    "type": "INDEX", "expiry": None, "strike": 0.0, "lot_size": 0, "tick_size": 0.05}
            if self._add(meta):
                added.append(meta)
        for name, book in self.books.items():
            if name in self.ready_names or book is None or not book.ready(self.today):
                continue
            self.ready_names.add(name)
            exchange = getattr(book, "segment", "NFO")
            futures = [e for e in book.future_expiries if e >= self.today][:2]
            for i, expiry in enumerate(futures):
                contract = book.by_key.get((book.underlying, expiry.isoformat(), 0.0, "FUT"))
                if contract is None:
                    continue
                if i == 0:
                    self.front[int(contract.token)] = name
                meta = _contract_meta(contract, name, exchange)
                if self._add(meta):
                    added.append(meta)
        return added

    def on_future_price(self, token: int, price: Optional[float]) -> List[dict]:
        """New options to record when this front future's price starts or moves half a window from the centre."""
        name = self.front.get(token)
        if name is None or price is None or price <= 0:
            return []
        book = self.books.get(name)
        step = float(getattr(book, "strike_step", 0) or 0)
        if step <= 0:
            return []
        centre = self.centre.get(name)
        if centre is not None and abs(price - centre) < step * self.strikes / 2:
            return []
        self.centre[name] = price
        from fno_models import OptionType
        exchange = getattr(book, "segment", "NFO")
        added = []
        for expiry in [e for e in book.option_expiries if e >= self.today][:self.expiries]:
            for strike in book.strikes_window(price, self.strikes):
                for kind in (OptionType.CE, OptionType.PE):
                    contract = book.option(expiry, strike, kind)
                    if contract is not None:
                        meta = _contract_meta(contract, name, exchange)
                        if self._add(meta):
                            added.append(meta)
        return added


# ----------------------------------------------------------------------------------------------------------------
# The day's folder
# ----------------------------------------------------------------------------------------------------------------

def _atomic_json(path: Path, data: dict) -> None:
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _iso_ns(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).isoformat()


def tree_bytes(root: Path) -> int:
    total = 0
    for base, _dirs, files in os.walk(root):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(base, name))
            except OSError:
                pass
    return total


def prune(root: Path, today: date, keep_days: int) -> List[str]:
    """Remove whole day folders (named YYYY-MM-DD) older than ``keep_days``; nothing else is touched."""
    removed = []
    if keep_days <= 0 or not root.exists():
        return removed
    cutoff = today - timedelta(days=keep_days)
    for child in sorted(root.iterdir()):
        try:
            day = date.fromisoformat(child.name)
        except ValueError:
            continue
        if child.is_dir() and day < cutoff:
            shutil.rmtree(child)
            removed.append(child.name)
    return removed


class DayStore:
    """One day's chunks, instruments, events and manifest. ``add`` runs on the loop; ``write`` in a thread."""

    def __init__(self, root: Path, day: str, *, day_max: int, total_max: int, chunk_sec: float):
        self.root, self.day = Path(root), day
        self.dir = self.root / day
        self.dir.mkdir(parents=True, exist_ok=True)
        self.day_max, self.total_max, self.chunk_sec = int(day_max), int(total_max), float(chunk_sec)
        path = self.dir / "manifest.json"
        self.manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "format": FORMAT, "record": "REC >qH (receipt unix ns, packet length) + Kite packet", "day": day,
            "chunks": [], "complete": False}
        self.manifest["complete"] = False
        self.day_bytes = sum(int(c["bytes"]) for c in self.manifest["chunks"])
        self.other_bytes = max(0, tree_bytes(self.root) - tree_bytes(self.dir))
        self.capped: Optional[str] = None
        self.logged = self._logged_tokens()
        self._check_caps()
        self._reset()

    def _reset(self) -> None:
        self.buf: Dict[int, bytearray] = {}
        self.buf_bytes = self.buf_records = 0
        self.first_ns = self.last_ns = None
        self.started = time.monotonic()

    def _check_caps(self) -> None:
        if self.day_bytes >= self.day_max:
            self.capped = "day_cap"
        elif self.other_bytes + self.day_bytes >= self.total_max:
            self.capped = "total_cap"

    def add(self, token: int, recv_ns: int, packet: bytes) -> None:
        record = REC.pack(recv_ns, len(packet)) + packet
        self.buf.setdefault(token, bytearray()).extend(record)
        self.buf_bytes += len(record)
        self.buf_records += 1
        self.first_ns = recv_ns if self.first_ns is None else self.first_ns
        self.last_ns = recv_ns

    def due(self) -> bool:
        return self.buf_records > 0 and (time.monotonic() - self.started >= self.chunk_sec
                                         or self.buf_bytes >= MAX_BUFFER_BYTES)

    def take(self) -> Optional[dict]:
        if not self.buf_records:
            return None
        batch = {"buf": self.buf, "records": self.buf_records, "first_ns": self.first_ns, "last_ns": self.last_ns}
        self._reset()
        return batch

    def write(self, batch: Optional[dict]) -> Optional[dict]:
        """Compress and keep one batch; update the manifest and the caps (runs in a worker thread)."""
        if not batch:
            return None
        raw = b"".join(bytes(batch["buf"][token]) for token in sorted(batch["buf"]))
        data = lzma.compress(raw, preset=XZ_PRESET)
        seq = len(self.manifest["chunks"])
        stamp = datetime.fromtimestamp(batch["first_ns"] / 1e9, tz=timezone.utc).astimezone(IST).strftime("%H%M%S")
        name = f"chunk-{stamp}-{seq:04d}.bin.xz"
        temporary = self.dir / (name + ".part")
        temporary.write_bytes(data)
        os.replace(temporary, self.dir / name)
        entry = {"file": name, "bytes": len(data), "raw_bytes": len(raw), "sha256": hashlib.sha256(data).hexdigest(),
                 "records": batch["records"], "instruments": len(batch["buf"]),
                 "first_utc": _iso_ns(batch["first_ns"]), "last_utc": _iso_ns(batch["last_ns"])}
        self.manifest["chunks"].append(entry)
        _atomic_json(self.dir / "manifest.json", self.manifest)
        self.day_bytes += len(data)
        self._check_caps()
        return entry

    def close(self, complete: bool) -> None:
        self.manifest["complete"] = bool(complete)
        _atomic_json(self.dir / "manifest.json", self.manifest)

    def event(self, kind: str, **fields) -> None:
        line = {"at": _now().isoformat(), "event": kind, **fields}
        try:
            with open(self.dir / "events.jsonl", "a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, sort_keys=True) + "\n")
        except OSError as exc:
            _error("event_write_" + type(exc).__name__)

    def _logged_tokens(self) -> set:
        tokens, path = set(), self.dir / "instruments.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    tokens.add(int(json.loads(line)["token"]))
                except (ValueError, KeyError, TypeError):
                    pass
        return tokens

    def instruments(self, metas: Iterable[dict]) -> None:
        """Note each instrument once a day (a restart re-reads what is noted)."""
        fresh = [meta for meta in metas if int(meta["token"]) not in self.logged]
        if not fresh:
            return
        stamp = _now().isoformat()
        with open(self.dir / "instruments.jsonl", "a", encoding="utf-8") as handle:
            for meta in fresh:
                handle.write(json.dumps({**meta, "added_at": stamp}, sort_keys=True) + "\n")
        self.logged.update(int(meta["token"]) for meta in fresh)


# ----------------------------------------------------------------------------------------------------------------
# The connection
# ----------------------------------------------------------------------------------------------------------------

def _connect(url: str):
    import websockets           # imported here: without it the recorder is REFUSED, the engine runs on
    return websockets.connect(url, open_timeout=OPEN_TIMEOUT_SEC, ping_interval=None, close_timeout=2,
                              max_size=2 ** 22)


async def _subscribe(socket, metas: List[dict]) -> None:
    tokens = [meta["token"] for meta in metas]
    for at in range(0, len(tokens), SUBSCRIBE_BATCH):
        part = tokens[at:at + SUBSCRIBE_BATCH]
        await socket.send(json.dumps({"a": "subscribe", "v": part}))
        await socket.send(json.dumps({"a": "mode", "v": ["full", part]}))


def _on_frame(frame, store: DayStore, universe: Universe) -> List[dict]:
    """Keep one frame's packets; returns options to subscribe because a front future moved."""
    _stats["frames"] += 1
    if isinstance(frame, str):
        _stats["text_frames"] += 1                      # order updates and notices: counted, never stored
        try:
            if json.loads(frame).get("type") == "error":
                _error("kite_error")
        except (ValueError, AttributeError):
            pass
        return []
    try:
        packets = split_frame(frame)
    except ValueError:
        _stats["bad_frames"] += 1
        return []
    recv_ns = time.time_ns()
    new: List[dict] = []
    for packet in packets:
        token = packet_token(packet)
        if store.capped is None:
            store.add(token, recv_ns, packet)
        if token in universe.front:
            new += universe.on_future_price(token, packet_ltp(packet))
    _stats["packets"] += len(packets)
    return new


async def _flush(store: DayStore, pending: Optional[asyncio.Task]) -> Optional[asyncio.Task]:
    """Start writing the waiting batch in a thread; one write at a time."""
    if pending is not None and not pending.done():
        return pending                                  # still writing: the buffer keeps growing until then
    if pending is not None:
        _wrote(pending)
    batch = store.take()
    return asyncio.ensure_future(asyncio.to_thread(store.write, batch)) if batch else None


def _wrote(task: asyncio.Task) -> None:
    try:
        entry = task.result()
    except Exception as exc:
        _error("write_" + type(exc).__name__)
        logger.error("tick_recorder_write_failed err=%s", type(exc).__name__)
        return
    if entry:
        _stats["chunks"] += 1
        _stats["bytes"] += entry["bytes"]


async def run(connect: Optional[Callable] = None, clock: Optional[Callable[[], datetime]] = None,
              books: Optional[Dict[str, object]] = None) -> None:
    """Record while the session lasts (``_should_run``), reconnecting as the module doc says."""
    connect, clock = connect or _connect, clock or _now
    today = clock().date()
    day = today.isoformat()
    root = Path(settings.TICK_RECORDER_PATH)
    if _stats.get("day") != day:
        reset()
        _stats["day"] = day
    removed = await asyncio.to_thread(prune, root, today, int(settings.TICK_RECORDER_RETENTION_DAYS))
    store = await asyncio.to_thread(DayStore, root, day, day_max=settings.TICK_RECORDER_DAY_MAX_BYTES,
                                    total_max=settings.TICK_RECORDER_TOTAL_MAX_BYTES,
                                    chunk_sec=settings.TICK_RECORDER_CHUNK_SEC)
    if removed:
        store.event("pruned", days=removed)
    universe = Universe(today, books=books)
    pending: Optional[asyncio.Task] = None
    backoff = BACKOFF_FIRST_SEC
    try:
        while store.capped is None and _should_run(clock(), day):
            token = _token(clock())
            if not _api_key():
                _set("REFUSED", clock())
                _error("no_api_key")
                store.event("refused", code="no_api_key")
                break
            _set("CONNECTING", clock())
            try:
                async with connect(_url(token)) as socket:
                    _stats["connects"] += 1
                    _set("LIVE", clock())
                    live_from = book_check = time.monotonic()
                    store.event("connected", n=_stats["connects"])
                    backoff = BACKOFF_FIRST_SEC
                    metas = list(universe.meta.values()) or universe.initial()
                    store.instruments(metas)
                    await _subscribe(socket, metas)
                    try:
                        while store.capped is None and _token(clock()) == token and _should_run(clock(), day):
                            frame = await asyncio.wait_for(socket.recv(), HEARTBEAT_TIMEOUT_SEC)
                            new = _on_frame(frame, store, universe)
                            if universe.missing() and time.monotonic() - book_check >= BOOK_RECHECK_SEC:
                                book_check = time.monotonic()
                                new += universe.initial()
                            if new:
                                store.instruments(new)
                                await _subscribe(socket, new)
                                store.event("subscribed", added=len(new), total=len(universe.meta),
                                            full=universe.full)
                            _stats["instruments"] = len(universe.meta)
                            if store.due():
                                pending = await _flush(store, pending)
                    finally:
                        _stats["live_sec"] += time.monotonic() - live_from
                store.event("disconnected", reason="capped" if store.capped else "login_or_session")
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                code = "no_library" if isinstance(exc, ImportError) else _code(exc)
                _error(code)
                if code in ("401", "403", "no_library"):
                    _set("REFUSED", clock())
                    store.event("refused", code=code)
                    logger.warning("tick_recorder_refused code=%s", code)
                    await _refused_note(day, code)
                    await _sleep(REFUSED_RETRY_SEC)
                else:
                    _set("DOWN", clock())
                    store.event("down", code=code, retry_s=backoff)
                    logger.warning("tick_recorder_down err=%s retry_s=%.0f", code, backoff)
                    await _sleep(backoff)
                    backoff = min(backoff * 2, BACKOFF_MAX_SEC)
    finally:
        if pending is not None:
            try:
                await pending
            except Exception:
                pass
            _wrote(pending)
        try:
            last = await asyncio.to_thread(store.write, store.take())
            if last:
                _stats["chunks"] += 1
                _stats["bytes"] += last["bytes"]
        except Exception as exc:
            _error("write_" + type(exc).__name__)
        if store.capped:
            _stats["capped"] = day
            store.event("capped", reason=store.capped, day_bytes=store.day_bytes)
        ended = not _in_window(clock())
        if ended:
            store.event("session_end")
        try:
            await asyncio.to_thread(store.close, ended)
        except Exception as exc:
            _error("manifest_" + type(exc).__name__)
        _set("OFF")
        if ended or store.capped:
            await _day_note(day, store)


# ----------------------------------------------------------------------------------------------------------------
# The owner's messages and the scheduler's entry point
# ----------------------------------------------------------------------------------------------------------------

def day_summary(store: DayStore) -> dict:
    chunks = store.manifest["chunks"]
    instruments = set()
    path = store.dir / "instruments.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                instruments.add(json.loads(line)["token"])
            except (ValueError, KeyError):
                pass
    return {"instruments": len(instruments), "records": sum(int(c["records"]) for c in chunks),
            "bytes": sum(int(c["bytes"]) for c in chunks), "chunks": len(chunks),
            "connects": _stats["connects"], "live_min": round(_stats["live_sec"] / 60)}


def note_text(day: str, summary: dict, capped: Optional[str]) -> str:
    text = (f"📼 Tick recorder {day}: {summary['instruments']} contracts, {summary['records']:,} price changes, "
            f"{summary['bytes'] / 2 ** 20:.0f} MB, live {summary['live_min']} min")
    if summary["connects"] > 1:
        text += f", {summary['connects'] - 1} reconnects"
    if capped:
        text += f". Stopped at the {'day' if capped == 'day_cap' else 'total'} size limit"
    return text + "."


async def _day_note(day: str, store: DayStore) -> None:
    """One message a day (the manifest remembers it across a restart)."""
    if (not settings.TICK_RECORDER_DAILY_NOTE or _stats.get("note_sent_day") == day
            or store.manifest.get("note_sent")):
        return
    _stats["note_sent_day"] = day
    try:
        store.manifest["note_sent"] = True
        await asyncio.to_thread(_atomic_json, store.dir / "manifest.json", store.manifest)
        summary = await asyncio.to_thread(day_summary, store)
        from operator_alert import notify_operator
        await notify_operator(note_text(day, summary, store.capped), event="tick_recorder")
    except Exception as exc:
        logger.error("tick_recorder_note_failed err=%s", type(exc).__name__)


async def _refused_note(day: str, code: str) -> None:
    if _stats.get("refused_note_day") == day:
        return
    _stats["refused_note_day"] = day
    try:
        from operator_alert import notify_operator
        await notify_operator(f"📼 Tick recorder: Kite refused the live price feed ({code}). Nothing is recorded "
                              "today; trading is not affected.", event="tick_recorder")
    except Exception as exc:
        logger.error("tick_recorder_note_failed err=%s", type(exc).__name__)


async def _is_trading_day(day: date) -> bool:
    import main as _main
    return bool(await _main.is_trading_day(day, settings.DB_PATH))


async def ensure_tick(now: Optional[datetime] = None) -> dict:
    """Start the recorder when it should run and is not running (the scheduler calls this each minute)."""
    now = now or _now()
    day = now.date().isoformat()
    if not enabled():
        return {"status": "disabled"}
    if not _in_window(now):
        return {"status": "outside_session"}
    try:
        if not await _is_trading_day(now.date()):
            return {"status": "non_trading_day"}
    except Exception as exc:
        return {"status": "calendar_unavailable", "error_type": type(exc).__name__}
    if _stats.get("capped") == day:
        return {"status": "capped"}
    if _token(now) is None:
        return {"status": "no_fresh_token"}
    task = _task["task"]
    loop = asyncio.get_running_loop()
    if task is not None and not task.done() and task.get_loop() is loop:
        return {"status": _stats["state"], "packets": _stats["packets"], "instruments": _stats["instruments"]}
    _task["task"] = background_tasks.spawn(run(), name="tick_recorder", loop=loop)
    return {"status": "started"}
