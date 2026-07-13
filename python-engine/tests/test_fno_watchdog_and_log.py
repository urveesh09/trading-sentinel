"""
[FNO-WATCHDOG-TESTS 2026-07-10] Zero-accept watchdog (spec §9.2) + the
signal log it reads. The critical behaviour: the alarm must distinguish
healthy self-regulation (pool_below_min_viable dominating) from a dead
gate (one reason at ~100% on every day).
"""
import os

import pytest

from fno_accept_watchdog import format_zero_accept_alert, zero_accept_scan
from fno_signal_log import init_fno_signal_db, log_fno_signal


async def _seed(db_path, day: str, reason: str, n: int, accepted: bool = False):
    for i in range(n):
        await log_fno_signal(
            db_path, scan_id=f"T-{day}-{i}", leg="FNO_PAPER",
            accepted=accepted, reject_reason="" if accepted else reason,
            bar_ts=f"{day} 10:{i:02d}:00",
        )


@pytest.mark.asyncio
async def test_self_regulation_is_not_an_alarm(db_path):
    await init_fno_signal_db(db_path)
    await _seed(db_path, "2026-07-08", "pool_below_min_viable", 5)
    await _seed(db_path, "2026-07-09", "pool_below_min_viable", 4)
    payload = await zero_accept_scan(db_path, n_days=2)
    assert payload is not None
    assert payload["self_regulating"] is True
    assert payload["dead_gate"] == ""
    msg = format_zero_accept_alert(payload)
    assert "self-regulation" in msg
    assert "ALARM" not in msg


@pytest.mark.asyncio
async def test_unvarying_histogram_is_a_dead_gate(db_path):
    await init_fno_signal_db(db_path)
    await _seed(db_path, "2026-07-08", "min_oi", 6)
    await _seed(db_path, "2026-07-09", "min_oi", 7)
    payload = await zero_accept_scan(db_path, n_days=2)
    assert payload is not None
    assert payload["self_regulating"] is False
    assert payload["dead_gate"] == "min_oi"
    msg = format_zero_accept_alert(payload)
    assert "ALARM" in msg and "min_oi" in msg


@pytest.mark.asyncio
async def test_varied_histogram_alarms_without_dead_gate_claim(db_path):
    await init_fno_signal_db(db_path)
    await _seed(db_path, "2026-07-08", "min_oi", 3)
    await _seed(db_path, "2026-07-08", "rvol_below_min", 3)
    await _seed(db_path, "2026-07-09", "max_spread", 4)
    payload = await zero_accept_scan(db_path, n_days=2)
    assert payload is not None
    assert payload["dead_gate"] == ""


@pytest.mark.asyncio
async def test_any_accept_in_window_is_healthy(db_path):
    await init_fno_signal_db(db_path)
    await _seed(db_path, "2026-07-08", "min_oi", 5)
    await _seed(db_path, "2026-07-09", "", 1, accepted=True)
    assert await zero_accept_scan(db_path, n_days=2) is None


@pytest.mark.asyncio
async def test_insufficient_history_is_silent(db_path):
    await init_fno_signal_db(db_path)
    await _seed(db_path, "2026-07-09", "min_oi", 5)
    assert await zero_accept_scan(db_path, n_days=2) is None


@pytest.mark.asyncio
async def test_missing_table_is_silent(db_path):
    assert await zero_accept_scan(db_path, n_days=2) is None


# ---------------------------------------------------------------------------
# signal log plumbing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_log_writes_csv_and_sqlite(db_path, patch_settings):
    await log_fno_signal(
        db_path, scan_id="T-1", leg="FNO_PAPER", accepted=True,
        bar_ts="2026-07-10 10:00:00", premium=100.5, lots=1,
    )
    csv_path = patch_settings.FNO_SIGNAL_LOG_PATH
    assert os.path.exists(csv_path)
    with open(csv_path) as f:
        header, row = f.read().strip().split("\n")
    assert header.startswith("scan_id,evaluated_at,bar_ts,leg")
    assert "T-1" in row and "FNO_PAPER" in row

    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT accepted, premium, lots FROM fno_signals WHERE scan_id='T-1'"
        ) as cur:
            r = await cur.fetchone()
    assert r == (1, 100.5, 1)
