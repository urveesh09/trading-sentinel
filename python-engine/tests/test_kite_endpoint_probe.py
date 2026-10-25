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



class TestOrderRouteProbe:
    """[O25c] The tunnel the real orders (and the gateway) use is watched in market hours too."""

    def test_only_a_separate_order_route_is_probed(self, monkeypatch):
        import ops_watchdogs as ow
        from config import settings
        monkeypatch.setattr(settings, "KITE_BASE_URL", "https://api.kite.trade")
        monkeypatch.setattr(settings, "KITE_ORDER_PROXY_URL", "")
        monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "")
        assert ow._order_route_probe_target() is None
        monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "https://api.kite.trade/")
        assert ow._order_route_probe_target() is None                       # the same endpoint as quotes
        monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "http://161.118.160.180:31527")
        assert ow._order_route_probe_target() == ("http://161.118.160.180:31527/", "")
        monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "")
        monkeypatch.setattr(settings, "KITE_ORDER_PROXY_URL", "http://kite:pw0123456789abcdef@161.118.160.180:31528")
        assert ow._order_route_probe_target() == ("https://api.kite.trade/",
                                                  "http://kite:pw0123456789abcdef@161.118.160.180:31528")

    def test_its_texts_name_the_route_and_what_still_protects_a_position(self, state):
        route = "https://api.kite.trade through http://kite:***@161.118.160.180:31528"
        assert _kite_probe_evaluate(False, 0.0, state, route=route) is None
        down = _kite_probe_evaluate(False, 180.0, state, route=route)
        assert down.startswith(f"📡 KITE ORDER ROUTE DOWN: {route} has failed 2 consecutive probes.")
        assert "resting broker stop still protects" in down and "kite_tunnel.py status" in down
        back = _kite_probe_evaluate(True, 780.0, state, route=route)
        assert back == f"✅ KITE ORDER ROUTE RECOVERED: {route} answers again (was down ~10 min)."

    @pytest.mark.asyncio
    async def test_a_dark_tunnel_pages_once_without_its_password_while_quotes_stay_quiet(self, monkeypatch):
        from datetime import datetime
        from types import SimpleNamespace

        import pytz

        import ops_watchdogs as ow
        from config import settings

        ist = pytz.timezone("Asia/Kolkata")
        monkeypatch.setattr(ow, "datetime", SimpleNamespace(now=lambda tz: ist.localize(datetime(2026, 11, 2, 11, 0))))

        async def trading(day, db_path):
            return True

        monkeypatch.setattr(ow, "is_trading_day", trading)
        monkeypatch.setattr(settings, "KITE_BASE_URL", "https://api.kite.trade")
        monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "")
        monkeypatch.setattr(settings, "KITE_ORDER_PROXY_URL", "http://kite:pw0123456789abcdef@161.118.160.180:31528")
        for key in ("consec_failures", "down_since_monotonic", "last_alert_monotonic"):
            monkeypatch.setitem(ow._kite_probe_state, key, 0 if key == "consec_failures" else None)
            monkeypatch.setitem(ow._kite_order_route_probe_state, key, 0 if key == "consec_failures" else None)
        probed, pages = [], []

        async def get(url, proxy=""):
            probed.append((url, proxy))
            if proxy:
                return False, "ProxyError: cannot reach http://kite:pw0123456789abcdef@161.118.160.180:31528"
            return True, ""

        async def notify(msg):
            pages.append(msg)

        monkeypatch.setattr(ow, "_kite_probe_get", get)
        monkeypatch.setattr(ow, "_kite_probe_notify", notify)
        await ow._kite_endpoint_probe_tick()
        await ow._kite_endpoint_probe_tick()
        await ow._kite_endpoint_probe_tick()
        assert probed[:2] == [("https://api.kite.trade/", ""),
                              ("https://api.kite.trade/", "http://kite:pw0123456789abcdef@161.118.160.180:31528")]
        assert len(pages) == 1 and pages[0].startswith("📡 KITE ORDER ROUTE DOWN: https://api.kite.trade through "
                                                       "http://kite:***@161.118.160.180:31528")
        assert "pw0123456789abcdef" not in pages[0]
