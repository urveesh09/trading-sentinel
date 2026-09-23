"""External fills and unknown dispatches must survive local accounting faults."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock
import asyncio
import sqlite3
from contextlib import closing

import pytest

from tests.test_atomic_settlement import fno_db, _insert_open_position
import fno_positions as fp
from fno_orchestrator import _manage_open_positions
from fno_executor import FnoExecutor

NOW = datetime(2026, 9, 13, 15, 20, tzinfo=timezone.utc)


def setup_executor():
    kite = AsyncMock()
    kite.get_quote.return_value = {1: {"last_price": 110, "depth": {"buy": [{"price": 110}]}}}
    executor = AsyncMock()
    executor.execute_exit.return_value = {"status": "filled", "order_id": "broker-1", "fill_price": 110}
    return kite, executor


@pytest.mark.asyncio
async def test_ledger_failure_recovers_without_second_external_exit(fno_db):
    position_id = await _insert_open_position(fno_db)
    kite, executor = setup_executor()
    with closing(sqlite3.connect(fno_db, isolation_level=None)) as db:
        db.execute("CREATE TRIGGER fail_close BEFORE INSERT ON bankroll_ledger BEGIN SELECT RAISE(ABORT,'fault'); END")
    assert await _manage_open_positions(kite, fno_db, "FNO_PAPER", executor, NOW, 19500) == []
    assert await fp.exit_execution_receipt(fno_db, position_id, "FNO_PAPER")
    with closing(sqlite3.connect(fno_db, isolation_level=None)) as db:
        assert db.execute("SELECT status FROM fno_positions").fetchone()[0] == "OPEN"
        db.execute("DROP TRIGGER fail_close")
    result = await _manage_open_positions(kite, fno_db, "FNO_PAPER", executor, NOW, 19500)
    assert len(result) == 1
    executor.execute_exit.assert_awaited_once()
    with closing(sqlite3.connect(fno_db, isolation_level=None)) as db:
        assert db.execute("SELECT COUNT(*) FROM bankroll_ledger WHERE event_type='TRADE_CLOSED'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM fno_exit_intents").fetchone()[0] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["receipt", "dispatch", "unfilled"])
async def test_ambiguous_exit_stays_claimed_across_ticks(fno_db, monkeypatch, failure):
    await _insert_open_position(fno_db)
    kite, executor = setup_executor()
    if failure == "receipt":
        monkeypatch.setattr(fp, "record_exit_execution_receipt", AsyncMock(side_effect=RuntimeError("disk")))
    elif failure == "dispatch":
        executor.execute_exit.side_effect = TimeoutError("unknown broker result")
    else:
        executor.execute_exit.return_value = {"status": "unfilled", "order_id": "broker-1"}
    for _ in range(2):
        assert await _manage_open_positions(kite, fno_db, "FNO_PAPER", executor, NOW, 19500) == []
    executor.execute_exit.assert_awaited_once()
    with closing(sqlite3.connect(fno_db, isolation_level=None)) as db:
        assert db.execute("SELECT COUNT(*) FROM fno_exit_intents").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_concurrent_claim_and_unreadable_evidence_fail_closed(fno_db):
    pid = await _insert_open_position(fno_db)
    claims = await asyncio.gather(*(fp.claim_exit_intent(fno_db, pid, "FNO_PAPER") for _ in range(2)))
    assert sorted(claims) == [False, True]
    with closing(sqlite3.connect(fno_db, isolation_level=None)) as db:
        db.execute("DROP TABLE fno_exit_execution_receipts")
    with pytest.raises(sqlite3.OperationalError):
        await fp.exit_execution_receipt(fno_db, pid, "FNO_PAPER")


@pytest.mark.asyncio
async def test_executor_does_not_replace_uncertain_order():
    executor = FnoExecutor(AsyncMock(), paper_mode=False, source_tag="FNO_LIVE")
    executor._place_limit = AsyncMock(return_value={"order_id": "broker-1"})
    executor._wait_for_fill = AsyncMock(return_value=None)
    result = await executor.execute_exit("NIFTY", 75, 110, .05)
    assert result["status"] == "unfilled"
    executor._place_limit.assert_awaited_once()
