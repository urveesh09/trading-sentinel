import asyncio
import json
import os
import sys

import httpx
import pytest

HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from kite_client import KiteClient


@pytest.fixture
def halt_dir(tmp_path, monkeypatch):
    import halt_switch
    path = tmp_path / "halts"
    path.mkdir()
    monkeypatch.setattr(halt_switch, "HALT_DIR", str(path))
    return path


@pytest.fixture
def mock_kite_client():
    captured = []

    async def fast_acquire():
        return None

    client = KiteClient(db_path=":memory:")
    client.limiter.acquire = fast_acquire
    return client, captured


@pytest.fixture
def readiness_path(tmp_path, monkeypatch):
    import order_execution_readiness as readiness
    monkeypatch.setattr(readiness.settings, "ORDER_EXECUTION_STATE_PATH", str(tmp_path / "state.json"))
    readiness._reset_for_tests()
    yield tmp_path / "state.json"
    readiness._reset_for_tests()


def test_static_ip_rejection_classifier_is_specific():
    from order_execution_readiness import is_permission_or_static_ip_rejection
    assert is_permission_or_static_ip_rejection(403, '{"error_type":"PermissionException","message":"IP address not allowed to place orders"}')
    assert not is_permission_or_static_ip_rejection(403, "invalid session")
    assert not is_permission_or_static_ip_rejection(400, "IP address not allowed to place orders")


def test_blocked_state_persists_and_dedupes(readiness_path):
    import order_execution_readiness as readiness
    assert readiness.mark_blocked("static IP rejected", http_status=403) is True
    assert readiness.mark_blocked("static IP rejected", http_status=403) is False
    readiness._reset_for_tests()
    assert readiness.snapshot()["status"] == readiness.BLOCKED
    assert json.loads(readiness_path.read_text())["http_status"] == 403


def test_accepted_order_is_only_positive_authorization_evidence(readiness_path):
    import order_execution_readiness as readiness
    assert readiness.snapshot()["status"] == readiness.UNVERIFIED
    readiness.mark_authorized()
    assert readiness.snapshot()["status"] == readiness.AUTHORIZED


def test_permission_rejection_halts_entries_and_reports_blocked(
    mock_kite_client, readiness_path, halt_dir, monkeypatch
):
    import halt_switch
    import operator_alert
    import order_execution_readiness as readiness

    client, requests = mock_kite_client
    alerts = []

    async def fake_alert(message, *, event):
        alerts.append((message, event))
        return True

    monkeypatch.setattr(operator_alert, "notify_operator", fake_alert)

    async def rejected(request):
        requests.append({"method": request.method, "url": str(request.url), "content": request.content.decode()})
        return httpx.Response(
            403, request=request,
            json={"status": "error", "error_type": "PermissionException",
                  "message": "IP address is not allowed to place orders"},
        )

    client.client = httpx.AsyncClient(
        base_url="https://api.kite.test", transport=httpx.MockTransport(rejected)
    )
    result = asyncio.run(client.place_order(
        tradingsymbol="AAA", quantity=1, intent="entry", channel="penny",
    ))
    asyncio.run(client.client.aclose())

    assert result["status"] == "ERROR"
    assert result["execution_blocked"] is True
    assert readiness.snapshot()["status"] == readiness.BLOCKED
    assert halt_switch.halt_state("momentum")[0] is True
    assert len(alerts) == 1


def test_operator_status_surfaces_execution_state():
    from operator_status import format_status
    snap = {
        "halted": False, "halt_reasons": [],
        "order_execution": {"status": "BLOCKED"},
        "penny": {"regime": "SIDEWAYS", "balance_estimate": 1000,
                  "pnl_today": 0, "open_positions": 0},
        "nifty": {"market_regime": "SIDEWAYS", "balance": 1000,
                  "pnl_today": 0, "open_positions": 0},
    }
    assert "Broker orders: BLOCKED" in format_status(snap)
