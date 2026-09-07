from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import settings
from optional_ai_status import load_optional_ai_status, record_optional_ai_status
# routes_ops intentionally holds a late module reference to main.  Importing
# the application first mirrors normal router registration and avoids testing
# it through an artificial circular-import path.
import main  # noqa: F401
import routes_ops


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes_ops.router)
    return TestClient(app)


@pytest.mark.asyncio
async def test_optional_ai_status_is_explicit_when_no_agent_has_reported(db_path):
    status = await load_optional_ai_status(db_path)
    assert status["state"] == "NOT_REPORTED"
    assert status["can_place_orders"] is False
    assert status["execution_authority"] == "NONE"


@pytest.mark.asyncio
async def test_outage_status_is_persisted_without_execution_authority(db_path):
    now = datetime(2026, 9, 7, 9, tzinfo=timezone.utc)
    status = await record_optional_ai_status(db_path, {
        "state": "OUTAGE_CIRCUIT_OPEN", "reported_at": now.isoformat(),
        "async_requested": True, "policy_allows_annotation": True,
        "reason": "provider_failures",
        "queue": {"pending": 0, "cached": 0, "daily_requests": 3,
                  "daily_budget": 40, "max_pending": 16, "circuit_state": "OPEN"},
    }, received_at=now)
    assert status["state"] == "OUTAGE_CIRCUIT_OPEN"
    assert status["detail"]["queue"]["circuit_state"] == "OPEN"
    assert status["can_place_orders"] is False


@pytest.mark.asyncio
async def test_old_ai_status_is_not_presented_as_current(db_path):
    now = datetime(2026, 9, 7, 9, tzinfo=timezone.utc)
    await record_optional_ai_status(db_path, {
        "state": "READY", "reported_at": now.isoformat(), "queue": {},
    }, received_at=now)
    status = await load_optional_ai_status(db_path, now=now + timedelta(minutes=4))
    assert status["state"] == "STALE"
    assert status["reported_state"] == "READY"


def test_optional_ai_status_routes_require_auth_and_preserve_no_order_contract():
    client = _client()
    payload = {
        "state": "OUTAGE_CIRCUIT_OPEN", "reported_at": datetime.now(timezone.utc).isoformat(),
        "async_requested": True, "policy_allows_annotation": True,
        "reason": "provider_failures", "queue": {"circuit_state": "OPEN"},
    }
    assert client.post("/ops/optional-ai-status", json=payload).status_code == 403
    response = client.post(
        "/ops/optional-ai-status", json=payload,
        headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
    )
    assert response.status_code == 200, response.text
    evidence = client.get(
        "/analytics/optional-ai-status",
        headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
    )
    assert evidence.status_code == 200
    assert evidence.json()["can_place_orders"] is False
    assert evidence.json()["execution_authority"] == "NONE"
