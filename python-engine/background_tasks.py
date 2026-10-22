"""Fire-and-forget tasks the engine must not lose.

[T22-BG 2026-10-22] asyncio keeps only a weak reference to a running task: a
task nobody holds can be collected before it finishes, and one still pending
when its loop closes is destroyed without running its `finally` and
`async with` exits. Such a task inside `aiosqlite.connect()` leaves the
connection's worker thread (non-daemon in aiosqlite 0.20) waiting forever,
and the interpreter can then never exit. Every background coroutine goes
through `spawn`, which holds the task until it is done and logs a failure;
shutdown lets it finish briefly, then cancels and waits for it (`drain`).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine, Optional

logger = logging.getLogger(__name__)

_tasks: set = set()


def spawn(coro: Coroutine[Any, Any, Any], *, name: str,
          loop: Optional[asyncio.AbstractEventLoop] = None) -> asyncio.Task:
    """Start `coro` on `loop` (default: the running loop) and hold it until done.

    Raises RuntimeError when there is no running loop and none is given; the
    coroutine is closed first, so it is never left un-awaited.
    """
    try:
        loop = loop or asyncio.get_running_loop()
    except RuntimeError:
        coro.close()
        raise
    task = loop.create_task(coro)
    try:
        task.set_name(name)
    except AttributeError:
        pass
    _tasks.add(task)
    task.add_done_callback(_finished)
    return task


def _finished(task: asyncio.Task) -> None:
    _tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("background_task_failed name=%s err=%s: %s", task.get_name(), type(exc).__name__, exc,
                     exc_info=exc)


def pending(loop: Optional[asyncio.AbstractEventLoop] = None) -> list:
    """Background tasks not yet done, optionally only those on `loop`."""
    return [task for task in list(_tasks)
            if not task.done() and (loop is None or task.get_loop() is loop)]


async def drain(grace: float = 2.0, timeout: float = 5.0) -> int:
    """Shutdown: give this loop's background tasks `grace` seconds to finish,
    then cancel the rest and wait up to `timeout` for them to unwind.
    Returns how many were cancelled; never raises."""
    loop = asyncio.get_running_loop()
    tasks = pending(loop)
    if not tasks:
        return 0
    try:
        if grace > 0:
            await asyncio.wait(tasks, timeout=grace)
        left = [task for task in tasks if not task.done()]
        for task in left:
            task.cancel()
        if left:
            await asyncio.wait(left, timeout=timeout)
            logger.warning("background_tasks_cancelled count=%d names=%s", len(left),
                           sorted(task.get_name() for task in left))
        return len(left)
    except Exception as exc:
        logger.warning("background_tasks_drain_failed err=%s", type(exc).__name__)
        return 0
