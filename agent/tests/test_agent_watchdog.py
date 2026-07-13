"""
[ROADMAP-2.2 / 2.4 2026-07-12] Agent liveness surfaces.

2.2: touch_heartbeat() feeds the Dockerfile HEALTHCHECK (mtime of
     /tmp/agent_heartbeat) so a hung agent turns unhealthy -> autoheal.
2.4: check_engine_liveness() is the EXTERNAL loop-progress watchdog for
     python-engine: it reads /data/scheduler_tick.json (written every
     60s from the engine's scheduler loop) and pages via Telegram when
     it goes stale/missing during market hours -- the 2026-07-07
     6h32m-freeze detector.
"""
import json
import time
from datetime import datetime
from unittest.mock import patch

import pytest

import agent


def _write_tick(path, ts_epoch):
    path.write_text(json.dumps({"ts_epoch": ts_epoch, "ist": "test"}))


# ---------------------------------------------------------------------
# touch_heartbeat (2.2)
# ---------------------------------------------------------------------

class TestHeartbeat:
    def test_touch_writes_epoch(self, tmp_path, monkeypatch):
        hb = tmp_path / "agent_heartbeat"
        monkeypatch.setattr(agent, "HEARTBEAT_FILE", str(hb))

        agent.touch_heartbeat()

        assert hb.exists()
        assert abs(time.time() - float(hb.read_text())) < 5.0

    def test_touch_never_raises(self, monkeypatch):
        """Liveness reporting must not break the pipeline (e.g. read-only
        filesystem)."""
        monkeypatch.setattr(agent, "HEARTBEAT_FILE", "/nonexistent-dir/hb")
        agent.touch_heartbeat()  # must not raise


# ---------------------------------------------------------------------
# read_scheduler_tick_age (2.4)
# ---------------------------------------------------------------------

class TestReadSchedulerTickAge:
    def test_fresh_tick_reads_small_age(self, tmp_path):
        tick = tmp_path / "scheduler_tick.json"
        _write_tick(tick, time.time())
        age = agent.read_scheduler_tick_age(str(tick))
        assert age is not None and age < 5.0

    def test_stale_tick_reads_large_age(self, tmp_path):
        tick = tmp_path / "scheduler_tick.json"
        _write_tick(tick, time.time() - 3600)
        age = agent.read_scheduler_tick_age(str(tick))
        assert age is not None and age > 3500

    def test_missing_file_returns_none(self, tmp_path):
        assert agent.read_scheduler_tick_age(str(tmp_path / "nope.json")) is None

    def test_corrupt_file_returns_none(self, tmp_path):
        tick = tmp_path / "scheduler_tick.json"
        tick.write_text("{not json")
        assert agent.read_scheduler_tick_age(str(tick)) is None


# ---------------------------------------------------------------------
# check_engine_liveness (2.4)
# ---------------------------------------------------------------------

@pytest.fixture
def watchdog_env(tmp_path, monkeypatch):
    """Market hours forced ON, tick file in tmp, cooldown state reset."""
    tick = tmp_path / "scheduler_tick.json"
    monkeypatch.setattr(agent, "SCHEDULER_TICK_FILE", str(tick))
    monkeypatch.setattr(agent, "_is_market_hours", lambda now=None: True)
    monkeypatch.setattr(agent, "_engine_freeze_last_alert_ts", None)
    return tick


class TestCheckEngineLiveness:
    def test_fresh_tick_is_silent(self, watchdog_env):
        _write_tick(watchdog_env, time.time())
        with patch.object(agent.requests, "post") as mock_post:
            agent.check_engine_liveness()
        mock_post.assert_not_called()

    def test_stale_tick_pages_operator(self, watchdog_env):
        _write_tick(watchdog_env, time.time() - 3600)
        with patch.object(agent.requests, "post") as mock_post:
            agent.check_engine_liveness()
        mock_post.assert_called_once()
        text = mock_post.call_args.kwargs["json"]["text"]
        assert "FROZEN" in text

    def test_missing_file_pages_engine_down(self, watchdog_env):
        # File never written: engine down / never booted (the 19:59
        # host-reboot case) -- must page too.
        with patch.object(agent.requests, "post") as mock_post:
            agent.check_engine_liveness()
        mock_post.assert_called_once()
        text = mock_post.call_args.kwargs["json"]["text"]
        assert "DOWN" in text

    def test_repeat_alert_is_deduped_by_cooldown(self, watchdog_env):
        _write_tick(watchdog_env, time.time() - 3600)
        with patch.object(agent.requests, "post") as mock_post:
            agent.check_engine_liveness()
            agent.check_engine_liveness()
        assert mock_post.call_count == 1

    def test_silent_outside_market_hours(self, watchdog_env, monkeypatch):
        monkeypatch.setattr(agent, "_is_market_hours", lambda now=None: False)
        _write_tick(watchdog_env, time.time() - 3600)
        with patch.object(agent.requests, "post") as mock_post:
            agent.check_engine_liveness()
        mock_post.assert_not_called()


class TestMarketHours:
    def test_weekday_session_true(self):
        # Wed 2026-07-08 11:00 IST
        assert agent._is_market_hours(datetime(2026, 7, 8, 11, 0)) is True

    def test_weekday_pre_open_false(self):
        assert agent._is_market_hours(datetime(2026, 7, 8, 8, 59)) is False

    def test_weekday_post_close_false(self):
        assert agent._is_market_hours(datetime(2026, 7, 8, 15, 31)) is False

    def test_weekend_false(self):
        # Sat 2026-07-11
        assert agent._is_market_hours(datetime(2026, 7, 11, 11, 0)) is False
