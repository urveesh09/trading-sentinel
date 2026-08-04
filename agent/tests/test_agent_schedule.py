"""
Tests for agent.py schedule registration (Q3, Q9).

Q3: schedule uses getattr loop - each weekday must get DISTINCT job objects.
Q9: Momentum pipeline runs at :55, NOT :15.
"""

import schedule
from unittest.mock import patch, MagicMock
import importlib
import sys
import os
import pytest


@pytest.fixture(autouse=True)
def clean_schedule():
    """Clear all schedule jobs before each test."""
    schedule.clear()
    yield
    schedule.clear()


@pytest.fixture
def load_agent_main():
    """
    Import agent.py and call main() with the while-loop patched out.
    We patch `schedule.run_pending` to break the infinite loop.
    """
    # Patch external deps that fire on import
    with patch.dict(os.environ, {
        "MINIMAX_API_KEY": "fake",
        "TELEGRAM_BOT_TOKEN": "fake",
        "TELEGRAM_CHAT_ID": "99999",
        "QUANT_ENGINE_URL": "http://localhost:8000/signals",
    }):
        # Patch the openai SDK to avoid import errors / network clients
        sys.modules["openai"] = MagicMock()

        # Remove cached agent module if any
        if "agent" in sys.modules:
            del sys.modules["agent"]

        # Add agent dir to path
        agent_dir = os.path.join(
            os.path.dirname(__file__), ".."
        )
        if agent_dir not in sys.path:
            sys.path.insert(0, agent_dir)

        import agent as agent_mod

        # Call main() but break the while loop immediately
        import time
        original_sleep = time.sleep

        call_count = [0]
        def fake_sleep(secs):
            call_count[0] += 1
            if call_count[0] >= 1:
                raise KeyboardInterrupt()

        with patch("time.sleep", side_effect=fake_sleep):
            try:
                agent_mod.main()
            except KeyboardInterrupt:
                pass

        return agent_mod


class TestScheduleRegistration:
    """Q3: All 5 weekdays must have distinct schedule objects."""

    def test_all_weekdays_have_health_open_jobs(self, load_agent_main):
        """system_health_check('OPEN') at 09:15 for Mon-Fri = 5 jobs."""
        open_jobs = [
            j for j in schedule.get_jobs()
            if "system_health_check" in str(j.job_func)
            and j.at_time is not None
            and j.at_time.strftime("%H:%M") == "09:15"
        ]
        assert len(open_jobs) == 5, f"Expected 5 OPEN health jobs, got {len(open_jobs)}"

    def test_all_weekdays_have_health_close_jobs(self, load_agent_main):
        """system_health_check('CLOSE') at 15:30 for Mon-Fri = 5 jobs."""
        close_jobs = [
            j for j in schedule.get_jobs()
            if "system_health_check" in str(j.job_func)
            and j.at_time is not None
            and j.at_time.strftime("%H:%M") == "15:30"
        ]
        assert len(close_jobs) == 5, f"Expected 5 CLOSE health jobs, got {len(close_jobs)}"

    def test_swing_pipeline_at_0925_for_all_weekdays(self, load_agent_main):
        """run_pipeline at 09:25 for Mon-Fri = 5 jobs."""
        jobs = [
            j for j in schedule.get_jobs()
            if "run_pipeline" in str(j.job_func)
            and "momentum" not in str(j.job_func).lower()
            and j.at_time is not None
            and j.at_time.strftime("%H:%M") == "09:25"
        ]
        assert len(jobs) == 5, f"Expected 5 swing 09:25 jobs, got {len(jobs)}"

    def test_swing_pipeline_at_1450_for_all_weekdays(self, load_agent_main):
        """run_pipeline at 14:50 for Mon-Fri = 5 jobs."""
        jobs = [
            j for j in schedule.get_jobs()
            if "run_pipeline" in str(j.job_func)
            and "momentum" not in str(j.job_func).lower()
            and j.at_time is not None
            and j.at_time.strftime("%H:%M") == "14:50"
        ]
        assert len(jobs) == 5, f"Expected 5 swing 14:50 jobs, got {len(jobs)}"

    def test_job_objects_are_distinct_in_memory(self, load_agent_main):
        """Each job is a distinct object, not overwritten (Q3)."""
        all_jobs = schedule.get_jobs()
        ids = [id(j) for j in all_jobs]
        assert len(ids) == len(set(ids)), "Some job objects share the same memory address (overwritten)"

    def test_daily_clear_memory_at_0000(self, load_agent_main):
        """clear_memory registered at 00:00."""
        clear_jobs = [
            j for j in schedule.get_jobs()
            if "clear_memory" in str(j.job_func)
            and j.at_time is not None
            and j.at_time.strftime("%H:%M") == "00:00"
        ]
        assert len(clear_jobs) >= 1


class TestMomentumSchedule:
    """[POLL-CADENCE 2026-08-04] Momentum now polls on a bare 3-minute
    interval, gated to market hours inside run_momentum_pipeline().

    It used to be a fixed :10/:25/:40/:55 weekday grid sized for scans that
    took 5.6-9.1 min. Scans got faster and the grid became dead time: on
    2026-08-03 all three accepted signals waited 7.1-7.6 minutes between
    engine accept and Telegram alert, with a 15-minute worst case. Latency
    moves the fill away from the price the signal was priced on, which is
    how SUMICHEM's entry drifted -0.37% before the operator ever saw the
    button."""

    def test_momentum_polls_on_a_bare_interval_not_a_time_grid(self, load_agent_main):
        """No momentum job may be pinned to a wall-clock slot."""
        momentum_jobs = [
            j for j in schedule.get_jobs()
            if "run_momentum_pipeline" in str(j.job_func)
        ]
        assert momentum_jobs, "no momentum poll job registered"
        pinned = [j for j in momentum_jobs if j.at_time is not None]
        assert not pinned, (
            f"{len(pinned)} momentum jobs are still pinned to wall-clock slots; "
            "the interval poll replaced the grid"
        )

    def test_exactly_one_momentum_job(self, load_agent_main):
        """One interval job, not 110 weekday jobs."""
        momentum_jobs = [
            j for j in schedule.get_jobs()
            if "run_momentum_pipeline" in str(j.job_func)
        ]
        assert len(momentum_jobs) == 1, (
            f"expected a single interval job, got {len(momentum_jobs)}"
        )

    def test_poll_interval_is_three_minutes(self, load_agent_main):
        """Caps the agent's share of alert latency at 3 min."""
        job = next(
            j for j in schedule.get_jobs()
            if "run_momentum_pipeline" in str(j.job_func)
        )
        assert job.interval == 3
        assert job.unit == "minutes"

    def test_pipeline_is_gated_to_market_hours(self, load_agent_main):
        """A bare interval fires around the clock, so the gate lives in the
        function. Without it the agent would poll ~470 times a night."""
        import datetime as _dt
        agent = load_agent_main
        # Sunday 11:00 -- weekend
        assert agent._is_market_hours(_dt.datetime(2026, 8, 2, 11, 0)) is False
        # Monday 03:00 -- before the open
        assert agent._is_market_hours(_dt.datetime(2026, 8, 3, 3, 0)) is False
        # Monday 23:00 -- after the close
        assert agent._is_market_hours(_dt.datetime(2026, 8, 3, 23, 0)) is False
        # Monday 11:02 -- the minute SUMICHEM was accepted
        assert agent._is_market_hours(_dt.datetime(2026, 8, 3, 11, 2)) is True
