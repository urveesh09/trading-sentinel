from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_penny_experiment_requires_auth():
    import main

    async with AsyncClient(
        transport=ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        response = await client.get("/experiments/penny")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_penny_experiment_shape_and_honest_nulls(monkeypatch):
    import main
    from config import settings

    monkeypatch.setattr(settings, "PENNY_SHADOW_ENABLED", True)
    comparison = {"variants": [{
        "variant": "PEN_BASE", "evaluations": 3, "raw_accepts": 2,
        "distinct_candidates": 1, "repeat_accepts": 1,
        "accept_rate": 2 / 3, "top_rejects": [],
        "paper_entries": None, "fills": None, "closed_trades": None,
        "net_pnl": None, "expectancy": None,
        "warnings": ["evaluations are not trades"],
    }]}
    query = AsyncMock(return_value=comparison)
    monkeypatch.setattr(main, "penny_shadow_comparison", query)
    async with AsyncClient(
        transport=ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/experiments/penny",
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert set(body["registry"]) == {"PEN_BASE", "PEN_WINDOW", "PEN_VOLUME"}
    assert body["registry"]["PEN_WINDOW"]["time_start_min"] == 600
    assert body["registry"]["PEN_VOLUME"]["volume_multiplier"] == 1.5
    assert body["comparison"]["variants"][0]["net_pnl"] is None
    query.assert_awaited_once_with(settings.DB_PATH)


@pytest.mark.asyncio
async def test_penny_experiment_disabled_and_empty_states(monkeypatch):
    import main
    from config import settings

    query = AsyncMock(return_value={"variants": [{
        "variant": name, "evaluations": 0,
    } for name in main.PENNY_SHADOW_VARIANTS]})
    monkeypatch.setattr(main, "penny_shadow_comparison", query)
    async with AsyncClient(
        transport=ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        monkeypatch.setattr(settings, "PENNY_SHADOW_ENABLED", False)
        disabled = await client.get(
            "/experiments/penny",
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
        )
        assert disabled.json()["status"] == "disabled"
        query.assert_not_awaited()

        monkeypatch.setattr(settings, "PENNY_SHADOW_ENABLED", True)
        empty = await client.get(
            "/experiments/penny",
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
        )
    assert empty.json()["status"] == "empty"

