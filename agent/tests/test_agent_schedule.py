"""
Tests for agent.py schedule registration (Q3, Q9).

Q3: schedule uses getattr loop — each weekday must get DISTINCT job objects.
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
        "GEMINI_API_KEY": "fake",
        "TELEGRAM_BOT_TOKEN": "fake",
        "TELEGRAM_CHAT_ID": "99999",
        "QUANT_ENGINE_URL": "http://localhost:8000/signals",
    }):
        # Patch google.genai to avoid import errors
        mock_genai = MagicMock()
        mock_types = MagicMock()
        sys.modules["google"] = MagicMock()
        sys.modules["google.genai"] = mock_genai
        sys.modules["google.genai.types"] = mock_types

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
    """Q9: Momentum pipeline runs at :55, not :15."""

    def test_momentum_at_55_for_all_hours(self, load_agent_main):
        """run_momentum_pipeline at 10:55, 11:55, 12:55, 13:55, 14:55."""
        expected_times = {"10:55", "11:55", "12:55", "13:55", "14:55"}
        momentum_jobs = [
            j for j in schedule.get_jobs()
            if "run_momentum_pipeline" in str(j.job_func)
        ]
        actual_times = {
            j.at_time.strftime("%H:%M") for j in momentum_jobs if j.at_time
        }
        assert expected_times.issubset(actual_times), (
            f"Missing momentum times. Expected {expected_times}, got {actual_times}"
        )

    def test_momentum_per_time_slot_has_5_weekday_jobs(self, load_agent_main):
        """Each :55 time slot should have exactly 5 jobs (Mon-Fri)."""
        for hour in ["10:55", "11:55", "12:55", "13:55", "14:55"]:
            jobs = [
                j for j in schedule.get_jobs()
                if "run_momentum_pipeline" in str(j.job_func)
                and j.at_time is not None
                and j.at_time.strftime("%H:%M") == hour
            ]
            assert len(jobs) == 5, f"Expected 5 jobs for {hour}, got {len(jobs)}"

    def test_no_momentum_at_00_15_30_45(self, load_agent_main):
        """Momentum must NOT be at :00, :15, :30, or :45."""
        bad_minutes = {"00", "15", "30", "45"}
        momentum_jobs = [
            j for j in schedule.get_jobs()
            if "run_momentum_pipeline" in str(j.job_func)
            and j.at_time is not None
        ]
        for j in momentum_jobs:
            minute = j.at_time.strftime("%M")
            assert minute not in bad_minutes, (
                f"Momentum job found at minute :{minute} — should only be at :55"
            )

    def test_total_momentum_jobs(self, load_agent_main):
        """5 time slots × 5 weekdays = 25 momentum jobs total."""
        momentum_jobs = [
            j for j in schedule.get_jobs()
            if "run_momentum_pipeline" in str(j.job_func)
        ]
        assert len(momentum_jobs) == 25, f"Expected 25 momentum jobs, got {len(momentum_jobs)}"
