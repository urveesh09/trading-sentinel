import json

import aiosqlite
import pytest

from penny_execution_journal import (
    append_execution_event, attempt_event_payload, attempt_event_types,
    attempt_identity, execution_funnel,
    init_penny_execution_journal,
)
from penny_executor import PennyExecutor
from penny_models import PennyLeg


def _event(db_path, **overrides):
    attempt, candidate = attempt_identity("2026-08-10T11:00|AAA|10.4|10.3", "AAA", "MIS", "PENNY_PAPER")
    values = dict(
        db_path=str(db_path), attempt_id=attempt, scan_id="scan-first",
        candidate_key=candidate, ticker="AAA", leg="MIS",
        source="PENNY_PAPER", mode="paper", event_type="CANDIDATE_ACCEPTED",
        payload={"entry": 10.4}, event_ts="2026-08-10T05:30:00+00:00",
    )
    values.update(overrides)
    return values


@pytest.mark.asyncio
async def test_append_is_restart_idempotent_and_immutable(tmp_path):
    db = tmp_path / "journal.db"
    assert await append_execution_event(**_event(db)) is True
    # A restarted scanner can have a new scan id; stable candidate attempt wins.
    assert await append_execution_event(**_event(db, scan_id="scan-after-restart")) is False
    async with aiosqlite.connect(db) as connection:
        assert (await (await connection.execute(
            "SELECT COUNT(*) FROM penny_execution_events"
        )).fetchone())[0] == 1
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute("UPDATE penny_execution_events SET ticker='BAD'")
    assert await attempt_event_types(str(db), _event(db)["attempt_id"]) == ("CANDIDATE_ACCEPTED",)
    assert await attempt_event_payload(
        str(db), _event(db)["attempt_id"], "CANDIDATE_ACCEPTED",
    ) == {"entry": 10.4}


@pytest.mark.asyncio
async def test_strict_payload_and_source_isolation(tmp_path):
    db = tmp_path / "journal.db"
    with pytest.raises(ValueError, match="sensitive"):
        await append_execution_event(**_event(db, payload={"access_token": "never"}))
    with pytest.raises(ValueError, match="source/mode"):
        await append_execution_event(**_event(db, source="PENNY", mode="paper"))
    with pytest.raises(ValueError, match="timezone-aware"):
        await append_execution_event(**_event(db, event_ts="2026-08-10T05:30:00"))
    await append_execution_event(**_event(db))
    live_attempt, live_candidate = attempt_identity("live", "BBB", "MIS", "PENNY")
    await append_execution_event(**_event(
        db, attempt_id=live_attempt, candidate_key=live_candidate, ticker="BBB",
        source="PENNY", mode="live", event_type="ENTRY_REJECTED",
        payload={"reason": "broker rejected"},
    ))
    paper = await execution_funnel(str(db), source="PENNY_PAPER")
    live = await execution_funnel(str(db), source="PENNY")
    assert paper["evaluator_accepts"] == 1 and paper["failures"] == 0
    assert live["evaluator_accepts"] == 0 and live["failures"] == 1


@pytest.mark.asyncio
async def test_idempotency_collision_fails_closed(tmp_path):
    db = tmp_path / "journal.db"
    await append_execution_event(**_event(db))
    with pytest.raises(ValueError, match="collision"):
        await append_execution_event(**_event(db, payload={"entry": 99.0}))


@pytest.mark.asyncio
async def test_executor_paper_lifecycle_and_sink_failure_do_not_change_fill(monkeypatch):
    events = []
    async def sink(event, payload, context):
        events.append(event)
    executor = PennyExecutor(object(), paper_mode=True, event_sink=sink)
    async def ltp(_ticker):
        return 10.4
    monkeypatch.setattr(executor, "_live_ltp", ltp)
    result = await executor.execute_entry(
        "AAA", PennyLeg.MIS, 10.4, 10.2, 5, attempt_context={"id": "x"},
    )
    assert result["entry_status"] == "paper"
    assert result["fill_price"] == 10.4 and result["sl_order_id"].startswith("PAPER-SL-")
    assert events == ["ENTRY_FILLED", "SL_PLACED"]

    async def broken_sink(*_args):
        raise RuntimeError("locked")
    executor.event_sink = broken_sink
    again = await executor.execute_entry(
        "AAA", PennyLeg.MIS, 10.4, 10.2, 5, attempt_context={"id": "x"},
    )
    assert again["entry_status"] == "paper" and again["fill_price"] == 10.4
