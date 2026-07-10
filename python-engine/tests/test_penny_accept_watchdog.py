"""
[GAP-2 ZERO-ACCEPT ALARM 2026-07-10] Tests for penny_accept_watchdog.

The scenario that motivates every test here: 215,814 evaluations, 0
accepts, nine months, no alert (BUG-1). The watchdog must fire on that
world, stay silent on a healthy one, and tell a dead gate apart from a
quiet market.
"""
import asyncio

import pytest

from penny_accept_watchdog import (
    DEAD_GATE_DOMINANCE,
    format_zero_accept_alert,
    zero_accept_scan,
)
from penny_signal_log import init_penny_signal_db, log_penny_signal


def _run(coro):
    return asyncio.run(coro)


async def _seed_day(db_path, day, *, evals, accepts=0, reason="breakout not confirmed (close 10.00 <= 10.34)",
                    varied=False):
    """Insert `evals` rows dated `day` (ISO date), `accepts` of them accepted."""
    import aiosqlite
    await init_penny_signal_db(db_path)
    varied_reasons = [
        "breakout not confirmed (close 10.00 <= 10.34)",
        "volume 1234 < 1.8x median (9999)",
        "RSI(14)=75.0 overbought",
        "outside breakout time window (500 min)",
    ]
    async with aiosqlite.connect(db_path) as db:
        for i in range(evals):
            accepted = 1 if i < accepts else 0
            r = "" if accepted else (
                varied_reasons[i % len(varied_reasons)] if varied else reason
            )
            await db.execute(
                "INSERT INTO penny_signals (scan_id, scanned_at, ticker, leg,"
                " accepted, reject_reason, regime, close) VALUES (?,?,?,?,?,?,?,?)",
                (f"scan-{day}", f"{day}T06:0{i % 10}:00+00:00", f"T{i}",
                 "MIS", accepted, r, "PR1_CALM", 10.0),
            )
        await db.commit()


class TestZeroAcceptScan:
    def test_healthy_day_with_accepts_is_silent(self, tmp_path):
        db = str(tmp_path / "t.db")
        _run(_seed_day(db, "2026-07-09", evals=50, accepts=0))
        _run(_seed_day(db, "2026-07-10", evals=50, accepts=2))
        assert _run(zero_accept_scan(db, n_days=2)) is None

    def test_insufficient_history_is_silent(self, tmp_path):
        """One zero-accept day when n_days=2 must NOT alert -- a single
        quiet day is normal; the alarm is about consecutive days."""
        db = str(tmp_path / "t.db")
        _run(_seed_day(db, "2026-07-10", evals=50, accepts=0))
        assert _run(zero_accept_scan(db, n_days=2)) is None

    def test_missing_table_is_silent(self, tmp_path):
        """[Rule 57] A fresh container with no penny_signals table has
        nothing to audit; the watchdog logs and returns None instead of
        raising into the scheduler."""
        import aiosqlite

        async def _make_empty_db(path):
            async with aiosqlite.connect(path) as db:
                await db.execute("CREATE TABLE unrelated (x INTEGER)")
                await db.commit()

        db = str(tmp_path / "empty.db")
        _run(_make_empty_db(db))
        assert _run(zero_accept_scan(db, n_days=2)) is None

    def test_bug1_world_fires_with_dead_gate_flag(self, tmp_path):
        """THE BUG-1 regression: N consecutive days, evaluations > 0,
        zero accepts, one reason dominating every day => alert payload
        with dead_gate set."""
        db = str(tmp_path / "t.db")
        _run(_seed_day(db, "2026-07-09", evals=100, accepts=0))
        _run(_seed_day(db, "2026-07-10", evals=100, accepts=0))
        payload = _run(zero_accept_scan(db, n_days=2))
        assert payload is not None, (
            "200 evaluations, 0 accepts across 2 days MUST alert -- this "
            "is the exact world BUG-1 created for nine months"
        )
        assert payload["days"] == ["2026-07-09", "2026-07-10"]
        assert payload["evaluations"] == 200
        assert payload["accepts"] == 0
        assert payload["dead_gate"] == "breakout not confirmed"
        assert payload["top_reasons"][0][0] == "breakout not confirmed"

    def test_varied_rejects_fire_without_dead_gate_flag(self, tmp_path):
        """Zero accepts with a VARIED histogram is a quiet market, not a
        dead gate: alert, but calmly (dead_gate=None)."""
        db = str(tmp_path / "t.db")
        _run(_seed_day(db, "2026-07-09", evals=40, accepts=0, varied=True))
        _run(_seed_day(db, "2026-07-10", evals=40, accepts=0, varied=True))
        payload = _run(zero_accept_scan(db, n_days=2))
        assert payload is not None
        assert payload["dead_gate"] is None

    def test_accept_on_earlier_day_in_window_is_silent(self, tmp_path):
        db = str(tmp_path / "t.db")
        _run(_seed_day(db, "2026-07-08", evals=50, accepts=1))
        _run(_seed_day(db, "2026-07-09", evals=50, accepts=0))
        assert _run(zero_accept_scan(db, n_days=2)) is None

    def test_window_looks_at_evaluation_days_not_calendar_days(self, tmp_path):
        """A weekend (no rows) must not reset the streak: the window is
        the last N DISTINCT days that have rows."""
        db = str(tmp_path / "t.db")
        _run(_seed_day(db, "2026-07-03", evals=50, accepts=0))  # Friday
        _run(_seed_day(db, "2026-07-06", evals=50, accepts=0))  # Monday
        payload = _run(zero_accept_scan(db, n_days=2))
        assert payload is not None
        assert payload["days"] == ["2026-07-03", "2026-07-06"]

    def test_leg_filter(self, tmp_path):
        """leg="CNC" audits only the CNC rows: MIS accepts must not
        mask a dead CNC leg (the BUG-6 blind spot, inverted)."""
        db = str(tmp_path / "t.db")
        import aiosqlite

        async def _seed_cnc(path):
            await init_penny_signal_db(path)
            async with aiosqlite.connect(path) as dbc:
                for day in ("2026-07-09", "2026-07-10"):
                    await dbc.execute(
                        "INSERT INTO penny_signals (scan_id, scanned_at, ticker,"
                        " leg, accepted, reject_reason, regime, close)"
                        " VALUES (?,?,?,?,?,?,?,?)",
                        (f"s-{day}", f"{day}T04:00:00+00:00", "AAA", "MIS",
                         1, "", "PR1_CALM", 10.0),
                    )
                    await dbc.execute(
                        "INSERT INTO penny_signals (scan_id, scanned_at, ticker,"
                        " leg, accepted, reject_reason, regime, close)"
                        " VALUES (?,?,?,?,?,?,?,?)",
                        (f"s-{day}", f"{day}T04:00:00+00:00", "BBB", "CNC",
                         0, "RSI(2)=55.0 not below threshold", "PR1_CALM", 10.0),
                    )
                await dbc.commit()

        _run(_seed_cnc(db))
        assert _run(zero_accept_scan(db, n_days=2)) is None  # MIS accepts mask it
        payload = _run(zero_accept_scan(db, n_days=2, leg="CNC"))
        assert payload is not None
        assert payload["leg"] == "CNC"


class TestFormatAlert:
    def test_dead_gate_message_is_loud_and_carries_histogram(self):
        msg = format_zero_accept_alert({
            "days": ["2026-07-09", "2026-07-10"],
            "evaluations": 200,
            "accepts": 0,
            "top_reasons": [("breakout not confirmed", 200, 100.0)],
            "dead_gate": "breakout not confirmed",
            "per_day": [],
            "leg": "ALL",
        })
        assert "DEAD-GATE" in msg
        assert "breakout not confirmed" in msg
        assert "200" in msg

    def test_quiet_market_message_is_calm(self):
        msg = format_zero_accept_alert({
            "days": ["2026-07-09", "2026-07-10"],
            "evaluations": 80,
            "accepts": 0,
            "top_reasons": [("volume", 40, 50.0), ("RSI(14)=", 40, 50.0)],
            "dead_gate": None,
            "per_day": [],
            "leg": "ALL",
        })
        assert "DEAD-GATE" not in msg
        assert "zero-accept" in msg
