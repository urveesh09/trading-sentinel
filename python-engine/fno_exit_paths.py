"""[SX-F1 2026-10-21] Every exit check of a held single-leg F&O option, kept
for research at the live clock.

The exit loop looks at each held option's bid every 10 seconds (fast exit)
and on every 90-second tick. The research quote archive samples the chain
about once a minute, so an exit rule's behaviour at the live clock (a profit
lock sold on one flickering bid, or not) cannot be replayed from it. Each
look is appended as one JSON line to
``<RESEARCH_ARCHIVE_PATH>/fno_exit_paths/<YYYY-MM-DD>.jsonl``: time, book,
position, contract, bid/ask/LTP, the front-future price and what the ladder
decided. The live-clock exit evaluator (research) replays declared exit
arms on these lines (plus the archive after the live exit).

Never awaited and never raises: the write runs in a worker thread after the
decision, so a slow or full disk cannot delay or fail an exit. Research only.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from config import settings

logger = structlog.get_logger()
_PENDING: set = set()


def exit_path_file(day: date) -> Path:
    return Path(settings.RESEARCH_ARCHIVE_PATH) / "fno_exit_paths" / f"{day.isoformat()}.jsonl"


def _num(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 4) if number == number else None


def line_for(now_ist: datetime, source: str, position: Any, *, bid: float, ask: float, ltp: float,
             fut: Optional[float], decision: Any) -> str:
    return json.dumps({
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
    }, separators=(",", ":"), sort_keys=True)


def _append(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _done(task) -> None:
    _PENDING.discard(task)
    try:
        error = task.exception()
    except BaseException:   # cancelled at shutdown
        return
    if error is not None:
        logger.warning("fno_exit_path_write_failed err=%s", type(error).__name__)


def record(now_ist: datetime, source: str, position: Any, *, bid: float, ask: float, ltp: float,
           fut: Optional[float], decision: Any):
    """Schedule one line; returns at once (the write's future, for tests) and never raises."""
    if not settings.FNO_EXIT_PATH_RECORDING:
        return None
    try:
        line = line_for(now_ist, source, position, bid=bid, ask=ask, ltp=ltp, fut=fut, decision=decision)
        task = asyncio.get_running_loop().run_in_executor(None, _append, exit_path_file(now_ist.date()), line)
    except Exception as exc:   # no loop (sync caller) or an unserialisable value
        logger.warning("fno_exit_path_record_skipped err=%s", type(exc).__name__)
        return None
    _PENDING.add(task)
    task.add_done_callback(_done)
    return task


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
