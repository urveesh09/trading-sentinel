"""[T22-BG 2026-10-22] Fire-and-forget work is held until done and unwound at
shutdown. On Oct 22 a passing suite hung 3.5 h at exit: a startup catch-up task
was destroyed inside `aiosqlite.connect()` and its worker thread never stopped."""
import asyncio
import gc
import logging
import threading
import weakref
from datetime import datetime, timezone

import aiosqlite
import pytest

import background_tasks


async def _parked():
    await asyncio.get_running_loop().create_future()      # a future only this task holds


def _connection_threads() -> set:
    return {t for t in threading.enumerate() if isinstance(t, aiosqlite.Connection) and t.is_alive()}


@pytest.mark.asyncio
async def test_a_spawned_task_is_held_where_a_bare_task_is_collected():
    loop = asyncio.get_running_loop()
    handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda *_: None)            # the bare task's "destroyed but pending" note
    try:
        bare = weakref.ref(loop.create_task(_parked()))
        held = weakref.ref(background_tasks.spawn(_parked(), name="held"))
        await asyncio.sleep(0)
        gc.collect()
        assert bare() is None                              # asyncio alone lets an unreferenced task go
        assert held() is not None and not held().done()
    finally:
        loop.set_exception_handler(handler)
    assert await background_tasks.drain(grace=0) == 1


@pytest.mark.asyncio
async def test_shutdown_unwinds_a_task_inside_an_open_connection(tmp_path):
    opened = asyncio.Event()

    async def holds_a_connection():
        async with aiosqlite.connect(tmp_path / "held.db") as db:
            await db.execute("CREATE TABLE t (x)")
            opened.set()
            await asyncio.Event().wait()

    before = _connection_threads()
    background_tasks.spawn(holds_a_connection(), name="holder")
    await opened.wait()
    worker = _connection_threads() - before
    assert len(worker) == 1
    assert await background_tasks.drain(grace=0.05, timeout=2.0) == 1
    thread = worker.pop()
    thread.join(2.0)
    assert not thread.is_alive()                           # nothing left to keep the process alive


@pytest.mark.asyncio
async def test_shutdown_lets_a_finishing_write_finish_before_cancelling():
    written = []

    async def ledger_write():
        await asyncio.sleep(0.05)
        written.append("row")

    background_tasks.spawn(ledger_write(), name="ledger")
    assert await background_tasks.drain(grace=1.0, timeout=1.0) == 0
    assert written == ["row"]


@pytest.mark.asyncio
async def test_a_failed_background_task_is_logged_not_lost(caplog):
    async def fails():
        raise RuntimeError("disk full")

    caplog.set_level(logging.ERROR, logger="background_tasks")
    task = background_tasks.spawn(fails(), name="ledger_write")
    await asyncio.wait([task])
    await asyncio.sleep(0)
    assert any("background_task_failed name=ledger_write" in r.message and "disk full" in r.message
               for r in caplog.records)
    assert task not in background_tasks.pending()


def test_without_a_running_loop_the_coroutine_is_closed_not_leaked():
    async def work():
        return 1

    coro = work()
    with pytest.raises(RuntimeError):
        background_tasks.spawn(coro, name="no_loop")
    assert coro.cr_frame is None                           # closed: no "never awaited" warning


@pytest.mark.asyncio
async def test_the_penny_ledger_write_is_held_until_written():
    from penny_risk import PennyRiskEngine

    written = []

    async def writer(ticker, pnl):
        await asyncio.sleep(0)
        written.append(ticker)

    PennyRiskEngine(bankroll=2000.0, ledger_writer=writer).record_close(
        entry_price=10.0, exit_price=11.0, shares=100, is_intraday=True,
        when=datetime.now(timezone.utc), ticker="PENNY_A")
    loop = asyncio.get_running_loop()
    assert [t.get_name() for t in background_tasks.pending(loop)] == ["penny_ledger_write"]
    await background_tasks.drain(grace=1.0)
    assert written == ["PENNY_A"]


@pytest.mark.asyncio
async def test_every_startup_catch_up_the_scheduler_starts_is_held():
    import main as main_module

    class _Scheduler:
        def add_job(self, *args, **kwargs):
            pass

    before = set(asyncio.all_tasks())
    main_module.register_penny_scheduler_jobs(_Scheduler())
    started = set(asyncio.all_tasks()) - before
    # Which catch-up runs depends on the clock (09:30-15:15 scan, after 15:15
    # exit, after 15:45 watchdog); whichever ran is held and drained.
    loop = asyncio.get_running_loop()
    assert started <= set(background_tasks.pending(loop))
    await background_tasks.drain(grace=0)
    assert not background_tasks.pending(loop)


@pytest.mark.asyncio
async def test_a_connect_cancelled_while_opening_leaves_no_worker(tmp_path):
    """aiosqlite 0.20 caught only Exception while opening, so a cancellation
    there (a drain, a wait_for deadline) left the worker waiting forever.
    Fixed in aiosqlite 0.21.0 (#317); requirements pin it."""
    before = _connection_threads()

    async def opens():
        async with aiosqlite.connect(tmp_path / "c.db"):
            pass

    task = asyncio.get_running_loop().create_task(opens())
    await asyncio.sleep(0)                                 # parked inside connect
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    for thread in _connection_threads() - before:
        thread.join(2.0)
    assert not (_connection_threads() - before)
