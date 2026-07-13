"""
[ROADMAP-2.6 2026-07-12] Kite endpoint (OCI relay) probe alarm logic.

Every quote/order transits KITE_BASE_URL; the probe cron pages the
operator when it goes dark. The alarm decision lives in the pure state
machine `_kite_probe_evaluate` so it can be exhausted here without a
network: one blip must NOT page, two consecutive failures must, repeat
pages are deduped to 1/30min, and recovery is announced exactly once.
"""
import pytest

from main import (
    KITE_PROBE_ALERT_MIN_INTERVAL_SEC,
    KITE_PROBE_FAILURES_TO_ALERT,
    _kite_probe_evaluate,
)


@pytest.fixture
def state():
    return {
        "consec_failures": 0,
        "down_since_monotonic": None,
        "last_alert_monotonic": None,
    }


class TestProbeStateMachine:
    def test_steady_healthy_is_silent(self, state):
        for t in (0.0, 180.0, 360.0):
            assert _kite_probe_evaluate(True, t, state) is None

    def test_single_blip_is_silent(self, state):
        """One failed probe then recovery: transient, no page and no
        recovery notice (we never told the operator anything was wrong)."""
        assert _kite_probe_evaluate(False, 0.0, state) is None
        assert _kite_probe_evaluate(True, 180.0, state) is None

    def test_second_consecutive_failure_pages(self, state):
        assert _kite_probe_evaluate(False, 0.0, state) is None
        msg = _kite_probe_evaluate(False, 180.0, state)
        assert msg is not None and "KITE ENDPOINT DOWN" in msg

    def test_threshold_constant_matches_behaviour(self, state):
        for i in range(KITE_PROBE_FAILURES_TO_ALERT - 1):
            assert _kite_probe_evaluate(False, i * 180.0, state) is None
        assert _kite_probe_evaluate(False, 999.0, state) is not None

    def test_repeat_pages_deduped_while_down(self, state):
        _kite_probe_evaluate(False, 0.0, state)
        assert _kite_probe_evaluate(False, 180.0, state) is not None
        # Still down 3 and 6 minutes later: inside the 30-min window.
        assert _kite_probe_evaluate(False, 360.0, state) is None
        assert _kite_probe_evaluate(False, 540.0, state) is None

    def test_repages_after_cooldown_while_still_down(self, state):
        _kite_probe_evaluate(False, 0.0, state)
        _kite_probe_evaluate(False, 180.0, state)
        t = 180.0 + KITE_PROBE_ALERT_MIN_INTERVAL_SEC + 1.0
        msg = _kite_probe_evaluate(False, t, state)
        assert msg is not None and "KITE ENDPOINT DOWN" in msg

    def test_recovery_announced_once(self, state):
        _kite_probe_evaluate(False, 0.0, state)
        _kite_probe_evaluate(False, 180.0, state)  # paged
        msg = _kite_probe_evaluate(True, 360.0, state)
        assert msg is not None and "RECOVERED" in msg
        # Steady healthy afterwards: silent.
        assert _kite_probe_evaluate(True, 540.0, state) is None

    def test_recovery_resets_for_next_outage(self, state):
        """Down -> recovered -> down again must page again immediately at
        the threshold (no leftover cooldown from the first outage)."""
        _kite_probe_evaluate(False, 0.0, state)
        _kite_probe_evaluate(False, 180.0, state)
        _kite_probe_evaluate(True, 360.0, state)
        assert _kite_probe_evaluate(False, 540.0, state) is None
        msg = _kite_probe_evaluate(False, 720.0, state)
        assert msg is not None and "KITE ENDPOINT DOWN" in msg

    def test_recovery_message_reports_downtime_minutes(self, state):
        _kite_probe_evaluate(False, 0.0, state)
        _kite_probe_evaluate(False, 180.0, state)   # threshold crossed here
        msg = _kite_probe_evaluate(True, 180.0 + 1800.0, state)
        assert "~30 min" in msg

    def test_down_message_points_at_runbook(self, state):
        _kite_probe_evaluate(False, 0.0, state)
        msg = _kite_probe_evaluate(False, 180.0, state)
        assert "relay-failover.md" in msg
        assert "smoke_relay.sh" in msg
