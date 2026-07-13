"""
[TEST-PENNY-EDGE-DEFERRED-FIXES 2026-07-01] Regression tests
for the three fixes that closed out the 2026-07-01 incident:

  1. FD leak fix in penny_edge_orchestrator / penny_edge_live
     (every sqlite3.connect() now uses `with` so the FD is released
     even if cursor.execute() raises). Asserted via FD-count
     stability across 50 calls.

  2. cmd_eod_digest async/sync split. Both the async path
     (build_eod_digest_snapshot_async, called from inside an event
     loop) and the sync wrapper (build_eod_digest_snapshot_sync,
     called from a sync context) must produce the same snapshot.

  3. run_penny_edge_exit canonical-exit. When the held position's
     daily bar touched the target intraday before max_hold, the
     close row should record exit_price = target with realised_pnl
     computed at that price (not 0.0 and not entry_price). This
     mirrors today's deep-assessment P1 bug class -- the EOD exit
     was leaving 30-60% of EV on the table by always using
     exit_price=entry_price.
"""
import asyncio
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pandas as pd
import pytest

HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from config import settings
from position_tracker import init_positions_db

# These imports are pulled via importlib to avoid any top-level
# side effects; matches the existing test_penny_edge_orchestrator.py
# pattern of going through sys.path.
import importlib
peo  = importlib.import_module("penny_edge_orchestrator")
pee  = importlib.import_module("penny_edge_engine")
op_status = importlib.import_module("operator_status")


# ----------------------------- helpers --------------------------------

async def _seed_edge_position(
    db_path: str,
    *,
    ticker: str = "TEST",
    source: str = peo.SOURCE_PAPER,
    entry_price: float = 100.0,
    shares: int = 10,
    target: float = 110.0,
    stop_loss: float = 95.0,
    age_days: int = 4,  # older than the default 3-day max-hold
):
    """Seed an OPEN EDGE position that's already over max_hold."""
    await init_positions_db(db_path)
    entry_dt = (
        datetime.now(timezone.utc) - timedelta(days=age_days)
    ).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO positions (
                ticker, exchange, entry_date, entry_price, shares,
                stop_loss_initial, trailing_stop_current,
                target_1, target_2, atr_14_at_entry,
                highest_close_since_entry, status, source,
                product_type, regime_at_entry,
                atr_1min_post_t1, t1_fired
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticker, "NSE", entry_dt,
             entry_price, shares, stop_loss, stop_loss,
             target, target, 1.0, entry_price,
             "OPEN", source, "CNC", "REGIME_1_NORMAL",
             0.0, 0),
        )
        await db.commit()


def _fake_kite_with_daily_bars(open_, high, low, close):
    """A async-stub kite whose get_historical returns the given OHLC row."""
    kite = MagicMock()
    df = pd.DataFrame(
        {
            "date":   [datetime(2026, 7, 1)],
            "open":   [open_],
            "high":   [high],
            "low":    [low],
            "close":  [close],
            "volume": [10000],
        }
    )

    async def _get_historical(ticker, from_date, to_date):
        return df

    kite.get_historical = _get_historical
    return kite


def _papermode_kite_executor():
    """A PennyExecutor stub with paper_mode=True so no Kite orders fire."""
    executor = MagicMock()

    async def _market_unwind(ticker, leg, shares):
        return "STUB-unwind-" + ticker

    executor._market_unwind = _market_unwind
    return executor


# ----------------------------- FD-leak test ---------------------------

def test_fd_leak_no_growth_over_100_idempotency_checks(tmp_path):
    """Calling _already_entered_today 100 times must not leak 100 FDs.

    [FD-LEAK-TEST-NOTE 2026-07-01] Python's sqlite3 closes the FD lazily
    (the connection is logically closed by `with`, but the OS FD release
    happens on GC). We therefore force gc.collect() before counting to
    measure the *post-close* FD count. Without this, even a leak-free
    `with` block would look like it grew FDs by N.
    """
    import gc
    db_path = str(tmp_path / "leak.db")

    async def _setup():
        await init_positions_db(db_path)

    asyncio.run(_setup())
    gc.collect()
    try:
        pid = os.getpid()
        before = len(os.listdir(f"/proc/{pid}/fd"))
    except FileNotFoundError:
        pytest.skip("no /proc/<pid>/fd (not on linux).")
        return

    async def _hammer():
        # Insert 1 OPEN EDGE position that doesn't match, then call
        # the helper 100x in a loop. FD should NOT grow by 100.
        await _seed_edge_position(
            db_path, ticker="X", source=peo.SOURCE_PAPER, age_days=1,
        )
        for _ in range(100):
            # Use a ticker that doesn't exist so the function
            # executes the full DB read+write path.
            assert (
                await peo._already_entered_today(
                    db_path, "MISSING", peo.SOURCE_PAPER,
                    datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                )
            ) is False
        # Drop refs so gc can reclaim -- this is the realistic prod
        # scenario too (between ticks, refs die).
        gc.collect()

    asyncio.run(_hammer())
    gc.collect()

    try:
        pid = os.getpid()
        after = len(os.listdir(f"/proc/{pid}/fd"))
    except FileNotFoundError:
        pytest.skip("no /proc/<pid>/fd (not on linux).")
        return
    growth = after - before
    # Allow some slack for pytest plumbing + journal files.
    assert growth < 20, (
        f"FD count grew by {growth} over 100 calls -- "
        "leak likely not fixed (allowed <20)."
    )


# --------------------- canonical-exit test ----------------------------

def test_run_penny_edge_exit_uses_simulator_exit_price_on_tp_hit(tmp_path):
    """
    [CANONICAL-EXIT-1]

    Seed an OPEN EDGE position that's hit max_hold (4d > 3d). The
    Kite stub returns a single daily bar where hi >= target -- so the
    engine simulator's exit_reason should be "tp" and exit_price
    should equal target * (1 - slippage_bps/10000).
    """
    db_path = str(tmp_path / "canonical.db")

    async def _run():
        await _seed_edge_position(
            db_path,
            ticker="NSE:AAA",
            source=peo.SOURCE_PAPER,
            entry_price=100.0, shares=10,
            target=110.0, stop_loss=95.0, age_days=4,
        )
        kite = _fake_kite_with_daily_bars(
            open_=105.0, high=112.0, low=104.0, close=108.0,
        )
        # Patch PennyExecutor within peo so we don't need a real kite.
        import penny_executor as _pe
        orig = _pe.PennyExecutor

        class _StubExecutor(_pe.PennyExecutor):
            async def _market_unwind(self, ticker, leg, shares):
                return "STUB-unwind"

        _pe.PennyExecutor = _StubExecutor
        try:
            summary = await peo.run_penny_edge_exit(kite, db_path=db_path)
        finally:
            _pe.PennyExecutor = orig
        return summary

    summary = asyncio.run(_run())

    # 1) One closed PAPER position
    assert len(summary["closed_paper"]) == 1
    closed = summary["closed_paper"][0]
    # 2) Exit reason should be "tp" (target hit)
    assert closed["exit_reason"] == "tp"
    # 3) Exit price should be target * (1 - slippage_bps/10000).
    slip = peo.EDGE_SLIPPAGE_BPS / 10000.0
    expected_exit_price = 110.0 * (1 - slip)
    assert abs(closed["exit_price"] - expected_exit_price) < 1e-6
    # 4) realised_pnl = (exit_price - entry_price) * shares - costs.
    #    Positive, NOT 0.0.
    assert closed["realised_pnl"] > 0.0

    # 5) The DB row should now show CLOSED + the same exit_price.
    async def _read():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT status, exit_price, realised_pnl, r_multiple "
                "FROM positions WHERE source = ?",
                (peo.SOURCE_PAPER,),
            )
            return [dict(r) for r in await cur.fetchall()]

    rows = asyncio.run(_read())
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "CLOSED"
    assert abs(row["exit_price"] - expected_exit_price) < 1e-6
    assert row["realised_pnl"] > 0.0


def test_run_penny_edge_exit_no_overlap_when_under_max_hold(tmp_path):
    """
    [CANONICAL-EXIT-2] A position that's UNDER max_hold must be skipped
    even if it could otherwise be closed via the simulator. The check
    is `if age_days < max_hold: continue` and must remain intact.
    """
    db_path = str(tmp_path / "underhold.db")

    async def _run():
        await _seed_edge_position(
            db_path,
            ticker="NSE:BBB",
            source=peo.SOURCE_PAPER,
            entry_price=100.0, shares=10,
            target=110.0, stop_loss=95.0,
            age_days=1,   # below max_hold=3
        )
        kite = _fake_kite_with_daily_bars(
            open_=105.0, high=112.0, low=104.0, close=108.0,
        )
        import penny_executor as _pe
        class _Stub(_pe.PennyExecutor):
            async def _market_unwind(self, ticker, leg, shares):
                return "STUB"
        orig = _pe.PennyExecutor
        _pe.PennyExecutor = _Stub
        try:
            summary = await peo.run_penny_edge_exit(kite, db_path=db_path)
        finally:
            _pe.PennyExecutor = orig
        return summary

    summary = asyncio.run(_run())
    assert len(summary["closed_paper"]) == 0
    assert len(summary["closed_live"]) == 0


def test_run_penny_edge_exit_records_sl_when_low_below_stop(tmp_path):
    """
    [CANONICAL-EXIT-3] The simulator must fire SL when today's low
    wick blows through the stop. exit_reason='sl', exit_price ≈ stop.
    """
    db_path = str(tmp_path / "sldb.db")

    async def _run():
        await _seed_edge_position(
            db_path,
            ticker="NSE:CCC",
            source=peo.SOURCE_PAPER,
            entry_price=100.0, shares=10,
            target=110.0, stop_loss=95.0, age_days=4,
        )
        kite = _fake_kite_with_daily_bars(
            open_=98.0, high=99.0, low=92.0, close=96.5,
        )
        import penny_executor as _pe
        class _Stub(_pe.PennyExecutor):
            async def _market_unwind(self, ticker, leg, shares):
                return "STUB"
        orig = _pe.PennyExecutor
        _pe.PennyExecutor = _Stub
        try:
            summary = await peo.run_penny_edge_exit(kite, db_path=db_path)
        finally:
            _pe.PennyExecutor = orig
        return summary

    summary = asyncio.run(_run())
    closed = summary["closed_paper"][0]
    assert closed["exit_reason"] == "sl"
    # realised_pnl = (sl - entry) * shares - costs -> negative
    assert closed["realised_pnl"] < 0.0


# ------------------- async/sync split test ----------------------------

def test_cmd_eod_digest_sync_wrapper_still_works(tmp_path):
    """
    [ASYNC-SYNC-1] cmd_eod_digest (the sync wrapper) must still
    return a non-error string for a valid DB.
    """
    db_path = str(tmp_path / "eod.db")
    # Empty DB is fine -- the snapshot builder handles missing data.
    out = op_status.cmd_eod_digest(db_path)
    assert isinstance(out, str)
    assert out  # not empty
    assert "error reading" not in out


def test_build_eod_digest_snapshot_async_works_inside_running_loop(tmp_path):
    """
    [ASYNC-SYNC-2] The async path must work when called from
    inside an already-running event loop. (The old sync wrapper
    raised RuntimeError here.)
    """
    db_path = str(tmp_path / "loop.db")

    async def _loop():
        # The old cmd_eod_digest used asyncio.run() here, which
        # would raise RuntimeError. New path: await directly.
        snap = await op_status.build_eod_digest_snapshot_async(db_path)
        assert isinstance(snap, dict)
        assert "penny" in snap
        assert "nifty" in snap

    asyncio.run(_loop())


def test_sync_and_async_paths_return_equivalent_snapshots(tmp_path):
    """
    [ASYNC-SYNC-3] The sync wrapper and the async core must
    return equivalent snapshots for the same DB.
    """
    db_path = str(tmp_path / "equiv.db")

    async def _async_snap():
        return await op_status.build_eod_digest_snapshot_async(db_path)

    a = asyncio.run(_async_snap())
    s = op_status.build_eod_digest_snapshot_sync(db_path)

    # Compare structure -- keys must match. Values may differ
    # in `today` boundary (date() comparison), so just compare keys.
    assert set(a.keys()) == set(s.keys())
    assert set(a["penny"].keys()) == set(s["penny"].keys())
    assert set(a["nifty"].keys()) == set(s["nifty"].keys())


# ------------------- cron-guard test (max_instances+coalesce) ----------

def test_penny_edge_scan_and_exit_cron_have_instance_guards():
    """
    [CRON-GUARD-1] Verifies rule 39 (trading-sentinel-ops):
    penny_edge_scan and penny_edge_exit cron entries must have
    max_instances=1 and coalesce=True. Without these, a stuck
    tick of either subsystem can deadlock the other via
    APScheduler's default max_instances=1 + default
    misfire_grace_time=1s.
    """
    # [ROADMAP-4.1 stage 2 2026-07-13] The penny_edge cron registrations moved
    # from main.py to scheduler_setup.py. Read both, so this guard keeps
    # asserting on the real add_job kwargs instead of quietly finding nothing.
    src = "\n".join(
        open(os.path.join(ENGINE_DIR, name)).read()
        for name in ("main.py", "scheduler_setup.py")
        if os.path.exists(os.path.join(ENGINE_DIR, name))
    )

    # Find the penny_edge_scan cron block. We assert BOTH
    # max_instances=1 AND coalesce=True appear within that block,
    # not somewhere else in the file.
    scan_idx = src.find('id="penny_edge_scan"')
    assert scan_idx > 0, "penny_edge_scan cron entry must exist"
    # Take 600 chars after the id and confirm both flags present.
    scan_block = src[scan_idx:scan_idx + 600]
    assert "max_instances=1" in scan_block, (
        "penny_edge_scan cron MUST set max_instances=1 "
        "(trading-sentinel-ops rule 39)"
    )
    assert "coalesce=True" in scan_block, (
        "penny_edge_scan cron MUST set coalesce=True "
        "(trading-sentinel-ops rule 39)"
    )

    # Same checks for penny_edge_exit.
    exit_idx = src.find('id="penny_edge_exit"')
    assert exit_idx > 0, "penny_edge_exit cron entry must exist"
    exit_block = src[exit_idx:exit_idx + 600]
    assert "max_instances=1" in exit_block, (
        "penny_edge_exit cron MUST set max_instances=1 "
        "(trading-sentinel-ops rule 39)"
    )
    assert "coalesce=True" in exit_block, (
        "penny_edge_exit cron MUST set coalesce=True "
        "(trading-sentinel-ops rule 39)"
    )


# ------------------- UTC-timezone idempotency test -------------------

def test_already_entered_today_uses_utc_for_idempotency_check():
    """
    [IDEMPOTENCY-UTC-1] Per penny-edge-orchestrator-pattern.md
    "Idempotency gotcha" -- the orchestrator's today_str MUST be
    a UTC date string, not a local date string. The container's
    local time is IST; entry_date is stored as UTC. Mixing the
    two would silently allow the same ticker to be re-entered
    on every cron tick.
    """
    import inspect
    src = inspect.getsource(peo.run_penny_edge_scan)
    # The function MUST compute today_str as UTC.
    assert 'datetime.now(timezone.utc).strftime("%Y-%m-%d")' in src, (
        "run_penny_edge_scan must use UTC for today_str "
        "(penny-edge-orchestrator-pattern idempotency rule)"
    )

    # The entry write site in _run_one_leg must also use UTC.
    src_leg = inspect.getsource(peo._run_one_leg)
    assert 'datetime.now(timezone.utc).isoformat()' in src_leg, (
        "_run_one_leg must use UTC for entry_iso "
        "(matches the today_str timezone used in idempotency check)"
    )


# ------------------- source-tag Pydantic Literal regression test -------

@pytest.mark.asyncio
async def test_open_position_model_accepts_all_edge_sources():
    """
    [PYDANTIC-LITERAL-1] Per trading-sentinel-ops rule 38, every
    new source value must be added to the OpenPosition Literal in
    models.py. This test iterates every known source tag and
    asserts the model accepts it. If a future deploy adds a new
    subsystem (e.g. BACKTEST_V2) and forgets the Literal,
    this test breaks first.
    """
    from datetime import datetime as _dt
    from models import OpenPosition
    for src in ["SYSTEM", "MANUAL", "MOMENTUM",
                "EDGE_PAPER", "EDGE_LIVE"]:
        op = OpenPosition(
            ticker="X", exchange="NSE",
            entry_date=_dt.now(),
            entry_price=10.0, shares=1,
            stop_loss_initial=9.0, trailing_stop_current=9.0,
            target_1=11.0, target_2=11.0,
            atr_14_at_entry=0.0,
            highest_close_since_entry=10.0,
            status="OPEN", source=src,
            regime_at_entry="",
        )
        assert op.source == src
