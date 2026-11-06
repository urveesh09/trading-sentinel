"""[SX-F1 2026-10-21] Every exit check of a held single-leg F&O option, kept
for research at the live clock.

The exit loop looks at each held option's bid every 10 seconds (fast exit)
and on every 90-second tick. The research quote archive samples the chain
about once a minute, so an exit rule's behaviour at the live clock (a profit
lock sold on one flickering bid, or not) cannot be replayed from it. Each
look is appended as one JSON line to
``<RESEARCH_ARCHIVE_PATH>/fno_exit_paths/<YYYY-MM-DD>.jsonl``: time, book,
position, contract, bid/ask/LTP, the front-future price, what the ladder
decided and a digest of the exit settings in force (the full settings ride
on a position's first look, so research replays the rules that were live).
The live-clock exit evaluator (research) replays declared exit arms on
these lines (plus the archive after the live exit).

[A22-R6 2026-10-22] Bounded, off the exit path (Oct 22 audit: every look
was a task on the shared default executor, unbounded, outside the research
archive's capacity controls). ``record`` only puts the line on a bounded
queue and returns; one dedicated writer thread appends batches through the
research archive's guarded writer (free-space reserve, daily byte budget,
cross-process lease) under a per-session file cap. A look that cannot be
kept is dropped and counted by reason (``stats()``, ops snapshot); a
dropped look shows in research as a gap in the path. The writer drains on
shutdown (``close``). Never awaited and never raises: a slow or full disk
cannot delay or fail an exit. Research only.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import queue
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from config import settings
from fno_models import Contract
from research_archive import _admit_bytes, guarded_write

logger = structlog.get_logger()

MAX_QUEUE = 2_000                    # looks waiting for the writer (~5 h of one position)
DAY_MAX_BYTES = 32 * 1024 * 1024     # one session's file
BATCH_MAX = 500
DROP_REASONS = ("queue_full", "day_cap", "storage", "write_error", "record_cap")
DR_PATH_SCHEMA = "fno_dr_management_look_v1"
N11_QUOTE_SCHEMA = "fno_n11_paper_quote_look_v1"
DR_PATH_FOLDER = "fno_dr_exit_paths"
DR_RECORD_MAX_BYTES = 64 * 1024
_STOP = object()
_lock = threading.Lock()
_writer: Optional["_Writer"] = None
_counts = {"queued": 0, "written": 0, **{f"dropped_{reason}": 0 for reason in DROP_REASONS}}
_first_looks: set = set()           # (day, source, position) seen this session


def exit_path_file(day: date) -> Path:
    return Path(settings.RESEARCH_ARCHIVE_PATH) / "fno_exit_paths" / f"{day.isoformat()}.jsonl"


def _num(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 4) if number == number else None


def params_digest(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class QuoteReceipt:
    received_at: datetime
    packet: dict
    contract: Contract | None = None


@dataclass(frozen=True)
class DirectionalReceipts:
    option: QuoteReceipt | None
    future: QuoteReceipt | None


def _receipt_fields(receipt: QuoteReceipt) -> dict:
    from research_quote_collector import _finite_positive, _provider_timestamp

    packet = receipt.packet
    _, provider_at, provider_error = _provider_timestamp(packet.get("timestamp"))
    _, traded_at, traded_error = _provider_timestamp(packet.get("last_trade_time"))
    return {"received_at": receipt.received_at.isoformat(), "packet_present": bool(packet),
            "provider_token": _finite_positive(packet.get("instrument_token"), int),
            "provider_at": provider_at, "provider_time_error": provider_error,
            "last_trade_at": traded_at, "last_trade_time_error": traded_error,
            "ltp": _finite_positive(packet.get("last_price"), float)}


def _top_level(packet: dict, side: str) -> tuple[float | None, int | None]:
    from research_quote_collector import _finite_positive

    depth = packet.get("depth")
    levels = depth.get(side) if isinstance(depth, dict) else None
    first = levels[0] if isinstance(levels, list) and levels else None
    if not isinstance(first, dict):
        return None, None
    price = _finite_positive(first.get("price"), float)
    return price, _finite_positive(first.get("quantity"), int) if price is not None else None


def _directional_fields(position: Any, receipts: DirectionalReceipts) -> dict:
    option = future = None
    if receipts.option is not None:
        packet = receipts.option.packet
        bid, bid_qty = _top_level(packet, "buy")
        ask, ask_qty = _top_level(packet, "sell")
        option = {**_receipt_fields(receipts.option), "bid": bid, "bid_qty": bid_qty,
                  "ask": ask, "ask_qty": ask_qty}
    if receipts.future is not None:
        contract = receipts.future.contract
        future = {**_receipt_fields(receipts.future), "token": contract.token,
                  "tradingsymbol": contract.tradingsymbol, "underlying": contract.name,
                  "expiry": contract.expiry.isoformat()}
    return {"schema": N11_QUOTE_SCHEMA, "held_qty": position.qty, "held_lot_size": position.lot_size,
            "held_expiry": position.expiry, "strategy": position.strategy, "option": option, "future": future}


def line_for(now_ist: datetime, source: str, position: Any, *, bid: float, ask: float, ltp: float,
             fut: Optional[float], decision: Any, params: Optional[dict] = None,
             first_look: bool = False, receipts: DirectionalReceipts | None = None) -> str:
    line = {
        "at": now_ist.isoformat(), "source": source, "position_id": getattr(position, "id", None),
        "token": getattr(position, "token", None), "tradingsymbol": getattr(position, "tradingsymbol", None),
        "underlying": getattr(position, "underlying", None), "direction": getattr(position, "direction", None),
        "bid": _num(bid), "ask": _num(ask), "ltp": _num(ltp), "fut": _num(fut),
        "exit_reason": getattr(decision, "exit_reason", "") or "",
        "best_premium": _num(getattr(decision, "best_premium", None)),
        "lock_floor": _num(getattr(decision, "profit_lock_floor", None)),
        "lock_breach_since": (decision.lock_breach_since.isoformat()
                              if getattr(decision, "lock_breach_since", None) else None),
        "trail_active": bool(getattr(decision, "trail_active", False)),
        "trail_stop": _num(getattr(decision, "trail_stop", None)),
    }
    if params is not None:
        line["params_sha"] = params_digest(params)
        if first_look:
            line["params"] = params
    if receipts is not None and source == "FNO_PAPER":
        line["quote_evidence"] = _directional_fields(position, receipts)
    return json.dumps(line, separators=(",", ":"), sort_keys=True, default=str)


def _count(key: str, n: int = 1) -> None:
    with _lock:
        before = _counts[key]
        _counts[key] = before + n
    if key.startswith("dropped_") and (before == 0 or (before + n) // 100 > before // 100):
        logger.warning("fno_exit_path_dropped reason=%s total=%d", key[len("dropped_"):], before + n)


@guarded_write
def _append_batch(archive_root: str, path: str, payload: bytes) -> None:
    """One batch for one session file, inside the research writer's guard."""
    _admit_bytes(len(payload))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "ab") as handle:
        handle.write(payload)
        handle.flush()


class _Writer:
    def __init__(self) -> None:
        self.queue: queue.Queue = queue.Queue(maxsize=MAX_QUEUE)
        self.thread = threading.Thread(target=self._run, name="fno-exit-paths", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while True:
            batch = [self.queue.get()]
            while len(batch) < BATCH_MAX:
                try:
                    batch.append(self.queue.get_nowait())
                except queue.Empty:
                    break
            stop = any(item is _STOP for item in batch)
            try:
                self._write([item for item in batch if item is not _STOP])
            except Exception as exc:     # never let the thread die on one batch
                logger.warning("fno_exit_path_batch_failed err=%s", type(exc).__name__)
            finally:
                for _ in batch:
                    self.queue.task_done()
            if stop:
                return

    def _write(self, items: list) -> None:
        groups: dict = {}
        for root, path, line in items:
            groups.setdefault((root, path), []).append(line)
        for (root, path), lines in groups.items():
            payload = "".join(line + "\n" for line in lines).encode("utf-8")
            target = Path(path)
            used = target.stat().st_size if target.exists() else 0
            if used + len(payload) > DAY_MAX_BYTES:
                _count("dropped_day_cap", len(lines))
                continue
            try:
                _append_batch(root, path, payload)
            except OSError as exc:
                text = str(exc)
                _count("dropped_storage" if ("reserve" in text or "budget" in text) else "dropped_write_error",
                       len(lines))
                continue
            _count("written", len(lines))


def _ensure_writer() -> "_Writer":
    global _writer
    with _lock:
        if _writer is None or not _writer.thread.is_alive():
            _writer = _Writer()
        return _writer


def record(now_ist: datetime, source: str, position: Any, *, bid: float, ask: float, ltp: float,
           fut: Optional[float], decision: Any, params: Optional[dict] = None,
           receipts: DirectionalReceipts | None = None) -> bool:
    """Queue one look; returns at once (True when queued) and never raises."""
    if not settings.FNO_EXIT_PATH_RECORDING:
        return False
    try:
        key = (now_ist.date().isoformat(), source, getattr(position, "id", None))
        if any(seen[0] != key[0] for seen in _first_looks):
            _first_looks.difference_update({seen for seen in _first_looks if seen[0] != key[0]})
        first = key not in _first_looks
        line = line_for(now_ist, source, position, bid=bid, ask=ask, ltp=ltp, fut=fut, decision=decision,
                        params=params, first_look=first, receipts=receipts)
        item = (str(settings.RESEARCH_ARCHIVE_PATH), str(exit_path_file(now_ist.date())), line)
        _ensure_writer().queue.put_nowait(item)
    except queue.Full:
        _count("dropped_queue_full")
        return False
    except Exception as exc:   # an unserialisable value or a thread that cannot start
        logger.warning("fno_exit_path_record_skipped err=%s", type(exc).__name__)
        return False
    if first:
        _first_looks.add(key)
    _count("queued")
    return True


def record_defined_risk(now_ist, rows, snap, raw_quotes, *, received_at, closed) -> bool:
    """Queue the exact held-spread management input after the manager returns."""
    if not settings.FNO_DR_EXIT_PATH_RECORDING:
        return False
    try:
        from fno_dr_book import exit_path_settings
        from research_quote_collector import normalise_quote

        events = []
        if snap is not None and received_at is not None:
            for quote in snap.quotes.values():
                contract = quote.contract
                raw = raw_quotes.get(contract.token)
                if raw is None:
                    continue
                packet = {key: raw[key] for key in (
                    "instrument_token", "last_price", "timestamp", "exchange_timestamp", "last_trade_time",
                ) if key in raw}
                depth = raw.get("depth") or {}
                packet["depth"] = {}
                for side in ("buy", "sell"):
                    levels = depth.get(side) or []
                    packet["depth"][side] = [
                        {key: levels[0][key] for key in ("price", "quantity", "orders") if key in levels[0]}
                    ] if levels else []
                events.append(normalise_quote(
                    contract, packet, source="KITE", mode="KITE_REST_DR_MANAGEMENT",
                    received_at=received_at, selection_reason="held_defined_risk_leg", exchange="NFO",
                ))
        record = {
            "schema": DR_PATH_SCHEMA, "at": now_ist.isoformat(),
            "position_refs": [f"fno_dr_positions:{int(row['id'])}" for row in rows],
            "received_at": received_at.isoformat() if received_at else None,
            "snapshot_available": snap is not None, "closed": int(closed),
            "params": exit_path_settings(), "quotes": events,
        }
        line = json.dumps(record, sort_keys=True, default=str, separators=(",", ":"), allow_nan=False)
        if len(line.encode("utf-8")) > DR_RECORD_MAX_BYTES:
            _count("dropped_record_cap")
            return False
        root = Path(settings.RESEARCH_ARCHIVE_PATH)
        path = root / DR_PATH_FOLDER / f"{now_ist.date().isoformat()}.jsonl"
        _ensure_writer().queue.put_nowait((str(root), str(path), line))
    except queue.Full:
        _count("dropped_queue_full")
        return False
    except Exception as exc:
        logger.warning("fno_dr_exit_path_record_skipped", error_type=type(exc).__name__)
        return False
    _count("queued")
    return True


def flush(timeout: float = 5.0) -> bool:
    """Wait until every queued look is written or dropped (tests, shutdown)."""
    writer = _writer
    if writer is None:
        return True
    with writer.queue.all_tasks_done:
        return writer.queue.all_tasks_done.wait_for(lambda: writer.queue.unfinished_tasks == 0, timeout)


def close(timeout: float = 5.0) -> None:
    """Drain and stop the writer (engine shutdown); never raises."""
    global _writer
    with _lock:
        writer, _writer = _writer, None
    if writer is None:
        return
    try:
        writer.queue.put(_STOP, timeout=timeout)
        writer.thread.join(timeout)
    except Exception as exc:
        logger.warning("fno_exit_path_close_failed err=%s", type(exc).__name__)


def stats() -> dict:
    with _lock:
        out = dict(_counts)
        writer = _writer
    out["pending"] = writer.queue.qsize() if writer is not None else 0
    out["recording"] = bool(settings.FNO_EXIT_PATH_RECORDING)
    out["defined_risk_recording"] = bool(settings.FNO_DR_EXIT_PATH_RECORDING)
    return out


def read_day(root: Path, day: str) -> list[dict]:
    """The recorded looks of one day (research), in file order."""
    path = Path(root) / "fno_exit_paths" / f"{day}.jsonl"
    if not path.is_file():
        return []
    out = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out
