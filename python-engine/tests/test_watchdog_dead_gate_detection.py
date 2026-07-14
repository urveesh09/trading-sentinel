"""
[TIER0-0.5 2026-07-14] The zero-accept watchdog must NAME the dead gate.

The watchdog fired correctly on 2026-07-14 -- but it reported `dead_gate=none`
while the penny book sat at 0 accepts across 349,297 lifetime evaluations. So the
alert read like a slow market instead of "your gate is broken", and the dead gate
survived another day.

Cause: dead-gate detection required one reason to clear DEAD_GATE_DOMINANCE (90%)
on EVERY day in the window, independently. The real data:

    2026-07-13   regime PR3_HOT = 68.6%    <- below the bar
    2026-07-14   regime PR3_HOT = 96.0%
    window       regime PR3_HOT = 94.8%    <- obviously the dead gate

One quieter day diluted the per-day AND and the detector went silent. Dominance is
now judged over the WINDOW, with a per-day check only that the same reason leads
every day (which is what actually rules out a one-day spike).
"""
import pytest

import penny_accept_watchdog as w
from penny_accept_watchdog import (
    DEAD_GATE_DOMINANCE, SUSPECT_GATE_DOMINANCE, format_zero_accept_alert,
)


@pytest.fixture
def db(tmp_path):
    import sqlite3
    path = str(tmp_path / "cache.db")
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE penny_signals (
            scanned_at TEXT, ticker TEXT, leg TEXT,
            accepted INTEGER, reject_reason TEXT
        )
    """)
    con.commit()
    con.close()
    return path


async def _seed(path, rows):
    """rows: list of (day, reason, count)."""
    import aiosqlite
    async with aiosqlite.connect(path) as con:
        for day, reason, count in rows:
            for i in range(count):
                await con.execute(
                    "INSERT INTO penny_signals "
                    "(scanned_at, ticker, leg, accepted, reject_reason) "
                    "VALUES (?, ?, 'MIS', 0, ?)",
                    (f"{day}T10:0{i % 6}:00", f"T{i}", reason),
                )
        await con.commit()


@pytest.mark.asyncio
async def test_the_real_2026_07_14_shape_is_now_named_a_dead_gate(db):
    """
    The exact production distribution that produced `dead_gate=none`. It must now
    be identified.
    """
    # Real production volumes, scaled 10x down. The day sizes are wildly uneven
    # (2,765 vs 61,418 rows) and that skew is exactly why the window share
    # (94.8%) is so much higher than the quiet day's per-day share (68.6%).
    await _seed(db, [
        # 2026-07-13: 277 rows, PR3_HOT at 68.6% -- below the 90% per-day bar.
        ("2026-07-13", "regime PR3_HOT (no new entries)", 190),
        ("2026-07-13", "outside breakout time window (569 min)", 87),
        # 2026-07-14: 6,142 rows, PR3_HOT at 96%.
        ("2026-07-14", "regime PR3_HOT (no new entries)", 5896),
        ("2026-07-14", "evaluator returned None (see prior warn/error)", 246),
    ])

    payload = await w.zero_accept_scan(db, n_days=2, leg="MIS")

    assert payload is not None, "0 accepts across 2 days must raise an alarm"
    assert payload["dead_gate"] == "regime PR3_HOT", (
        "PR3_HOT is 94.8% of window rejects and leads BOTH days -- it is the dead "
        f"gate. Got: {payload['dead_gate']!r}"
    )

    msg = format_zero_accept_alert(payload)
    assert "DEAD-GATE SUSPECTED" in msg
    assert "regime PR3_HOT" in msg


@pytest.mark.asyncio
async def test_a_lopsided_but_sub_threshold_gate_is_still_named_as_suspect(db):
    """
    Below the dead-gate bar, the old code said nothing at all. With 0 accepts, a
    reason taking most of the rejects must still be named -- silence is what made
    a broken book look healthy.
    """
    await _seed(db, [
        ("2026-07-13", "regime PR3_HOT (no new entries)", 70),
        ("2026-07-13", "volume too low", 30),
        ("2026-07-14", "regime PR3_HOT (no new entries)", 70),
        ("2026-07-14", "volume too low", 30),
    ])

    payload = await w.zero_accept_scan(db, n_days=2, leg="MIS")

    assert payload["dead_gate"] is None          # 70% < 90%
    assert payload["suspect_gate"] == "regime PR3_HOT"   # but >= 60%, and leads daily

    msg = format_zero_accept_alert(payload)
    assert "prime suspect" in msg


@pytest.mark.asyncio
async def test_a_genuinely_varied_histogram_names_no_gate(db):
    """A quiet market really can produce 0 accepts. Don't cry dead-gate at it."""
    await _seed(db, [
        ("2026-07-13", "volume too low", 30),
        ("2026-07-13", "outside breakout time window", 25),
        ("2026-07-13", "RSI(14)=75 above max", 25),
        ("2026-07-13", "breakout not confirmed", 20),
        ("2026-07-14", "volume too low", 28),
        ("2026-07-14", "outside breakout time window", 27),
        ("2026-07-14", "RSI(14)=75 above max", 25),
        ("2026-07-14", "breakout not confirmed", 20),
    ])

    payload = await w.zero_accept_scan(db, n_days=2, leg="MIS")

    assert payload is not None            # still a zero-accept alarm...
    assert payload["dead_gate"] is None   # ...but no single gate to blame
    assert payload["suspect_gate"] is None


@pytest.mark.asyncio
async def test_one_day_spike_cannot_be_blamed_as_the_dead_gate(db):
    """
    The per-day check that survives: a reason must LEAD every day. A reason that
    explodes on one day only is a market event, not an unsatisfiable gate.
    """
    await _seed(db, [
        ("2026-07-13", "volume too low", 90),
        ("2026-07-13", "circuit_blocked", 10),
        # A one-off halt day.
        ("2026-07-14", "circuit_blocked", 950),
        ("2026-07-14", "volume too low", 50),
    ])

    payload = await w.zero_accept_scan(db, n_days=2, leg="MIS")

    assert payload["dead_gate"] is None, (
        "circuit_blocked leads only ONE day -- it is an event, not a dead gate"
    )


@pytest.mark.asyncio
async def test_an_accept_anywhere_in_the_window_silences_the_alarm(db):
    import aiosqlite
    await _seed(db, [("2026-07-13", "regime PR3_HOT (no new entries)", 100)])
    async with aiosqlite.connect(db) as con:
        await con.execute(
            "INSERT INTO penny_signals "
            "(scanned_at, ticker, leg, accepted, reject_reason) "
            "VALUES ('2026-07-14T10:00:00', 'GOODCO', 'MIS', 1, NULL)"
        )
        await con.commit()

    assert await w.zero_accept_scan(db, n_days=2, leg="MIS") is None
