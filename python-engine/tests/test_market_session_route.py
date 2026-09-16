"""Contract tests for the internal CAS-eligibility projection."""
from __future__ import annotations
import hashlib
import hmac

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from config import settings
from main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_cas_eligibility_requires_internal_secret(client):
    response = await client.get("/market-session/cas-eligibility?symbol=RELIANCE")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cas_eligibility_projects_python_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "CAS_PHASE1_FNO_UNDERLYINGS", " RELIANCE , INFY ")
    response = await client.get(
        "/market-session/cas-eligibility?symbol= reliance ",
        headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "RELIANCE"
    assert body["cas_eligible"] is True
    assert body["source"] == "python-engine/market_calendar.py::is_cas_eligible"
    assert isinstance(body["source_version"], str) and len(body["source_version"]) == 16
    assert isinstance(body["signature"], str) and len(body["signature"]) == 64
    signed = f"RELIANCE|true|{body['source_version']}".encode()
    assert body["signature"] == hmac.new(
        settings.INTERNAL_API_SECRET.encode(), signed, hashlib.sha256
    ).hexdigest()


@pytest.mark.asyncio
async def test_cas_eligibility_returns_false_for_unconfigured_symbol(client, monkeypatch):
    monkeypatch.setattr(settings, "CAS_PHASE1_FNO_UNDERLYINGS", "RELIANCE")
    response = await client.get(
        "/market-session/cas-eligibility?symbol=TCS",
        headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
    )
    assert response.status_code == 200
    assert response.json()["cas_eligible"] is False
