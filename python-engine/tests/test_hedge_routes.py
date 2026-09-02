from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from config import settings
from main import app


@pytest_asyncio.fixture
async def hedge_client(db_path, monkeypatch):
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _headers():
    return {"X-Internal-Secret": settings.INTERNAL_API_SECRET}


@pytest.mark.asyncio
async def test_hedge_routes_require_internal_auth(hedge_client):
    assert (await hedge_client.get("/partner/hedge/status")).status_code == 403
    assert (await hedge_client.get(
        "/partner/hedge/positions", headers={"X-Internal-Secret": "wrong"},
    )).status_code == 403


@pytest.mark.asyncio
async def test_position_intake_requires_reconciliation_before_status_counts_it(
    hedge_client,
):
    now = datetime(2026, 9, 2, 5, 30, tzinfo=timezone.utc).isoformat()
    created = await hedge_client.post(
        "/partner/hedge/positions", headers=_headers(), json={
            "underlying": "NIFTY", "instrument_type": "EQUITY",
            "tradingsymbol": "NIFTY_BETA_BOOK", "signed_quantity": 40000,
            "lot_size": 1, "entry_price": 95, "current_price": 100,
            "price_as_of": now, "opened_at": now, "source": "broker_import",
            "broker_order_id": "HEDGE-POS-1",
        },
    )
    assert created.status_code == 200, created.text
    position_id = created.json()["position_id"]
    status = (await hedge_client.get(
        "/partner/hedge/status", headers=_headers(),
    )).json()
    assert status["open_positions"] == 1
    assert status["reconciled_open_positions"] == 0
    assert status["phase2_enabled"] is False
    assert status["phase3_enabled"] is False
    assert status["automatic_execution"] is False

    reconciled = await hedge_client.post(
        f"/partner/hedge/positions/{position_id}/reconcile",
        headers=_headers(), json={
            "observed_quantity": 40000, "reconciled_at": now,
            "source": "broker_import", "current_price": 101,
            "price_as_of": now,
            "deliverable_quantity": 39000, "deliverable_as_of": now,
            "deliverable_source": "broker_holding_snapshot",
        },
    )
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["position"]["verification_status"] == "RECONCILED"
    assert reconciled.json()["position"]["deliverable_quantity"] == 39000
    status = (await hedge_client.get(
        "/partner/hedge/status", headers=_headers(),
    )).json()
    assert status["reconciled_open_positions"] == 1


@pytest.mark.asyncio
async def test_vix_intake_requires_source_and_timestamp(hedge_client):
    response = await hedge_client.post(
        "/partner/hedge/vix", headers=_headers(), json={
            "spot": 18.4,
            "observed_at": datetime(2026, 9, 2, 5, 30, tzinfo=timezone.utc).isoformat(),
            "source": "verified-manual",
        },
    )
    assert response.status_code == 200
    status = (await hedge_client.get(
        "/partner/hedge/status", headers=_headers(),
    )).json()
    assert status["latest_vix"]["spot"] == 18.4
    assert status["latest_vix"]["source"] == "verified-manual"


@pytest.mark.asyncio
async def test_semantically_invalid_position_returns_422(hedge_client):
    now = datetime(2026, 9, 2, 5, 30, tzinfo=timezone.utc).isoformat()
    response = await hedge_client.post(
        "/partner/hedge/positions", headers=_headers(), json={
            "underlying": "NIFTY", "instrument_type": "CE",
            "tradingsymbol": "NIFTY26SEP25000CE", "signed_quantity": -65,
            "lot_size": 65, "entry_price": 100, "opened_at": now,
            "source": "broker_import", "expiry": "2026-09-24",
            "strike": 25000, "quantity_basis": "UNITS",
        },
    )
    assert response.status_code == 422
    assert "explicit Greeks" in response.json()["detail"]


@pytest.mark.asyncio
async def test_fno_intake_requires_explicit_exchange_units(hedge_client):
    now = datetime(2026, 9, 2, 5, 30, tzinfo=timezone.utc).isoformat()
    response = await hedge_client.post(
        "/partner/hedge/positions", headers=_headers(), json={
            "underlying": "NIFTY", "instrument_type": "FUT",
            "tradingsymbol": "NIFTY26SEPFUT", "signed_quantity": -1,
            "lot_size": 65, "entry_price": 25000, "current_price": 25000,
            "price_as_of": now, "opened_at": now, "source": "broker_import",
        },
    )
    assert response.status_code == 422
    assert "quantity_basis=UNITS" in response.json()["detail"]


@pytest.mark.asyncio
async def test_fno_intake_accepts_whole_broker_units_case_insensitively(hedge_client):
    now = datetime(2026, 9, 2, 5, 30, tzinfo=timezone.utc).isoformat()
    response = await hedge_client.post(
        "/partner/hedge/positions", headers=_headers(), json={
            "underlying": "NIFTY", "instrument_type": "fut",
            "tradingsymbol": "NIFTY26SEPFUT", "signed_quantity": -65,
            "lot_size": 65, "quantity_basis": "units",
            "entry_price": 25000, "current_price": 25000,
            "price_as_of": now, "opened_at": now, "source": "broker_import",
        },
    )
    assert response.status_code == 200
    assert response.json()["signed_quantity"] == -65
    assert response.json()["quantity_basis"] == "UNITS"


@pytest.mark.asyncio
async def test_naive_vix_timestamp_returns_422(hedge_client):
    response = await hedge_client.post(
        "/partner/hedge/vix", headers=_headers(), json={
            "spot": 18.4, "observed_at": "2026-09-02T05:30:00",
            "source": "verified-manual",
        },
    )
    assert response.status_code == 422
    assert "timezone-aware" in response.json()["detail"]
