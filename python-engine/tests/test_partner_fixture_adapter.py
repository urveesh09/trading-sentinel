from datetime import datetime, timedelta

import pytest
import pytz

from config import settings
from hedge_analytics import load_partner_positions
from partner_fixture_adapter import apply_fixture_account

IST = pytz.timezone("Asia/Kolkata")


@pytest.mark.asyncio
async def test_complete_fixture_creates_then_closes_external_lifecycle(db_path, monkeypatch):
    now = IST.localize(datetime(2026, 9, 2, 11))
    monkeypatch.setattr(settings, "PARTNER_HEDGE_INPUT_EXPECTED_SOURCE", "fixture")
    monkeypatch.setattr(settings, "PARTNER_HEDGE_INPUT_EXPECTED_ACCOUNT_ID", "fixture-account")
    base = {"source": "fixture", "account_id": "fixture-account", "complete": True,
            "observed_at": now.isoformat(), "positions": [{"external_position_id": "ext-1", "underlying": "NIFTY", "tradingsymbol": "NIFTY", "quantity": 100, "entry_price": 100, "current_price": 101}]}
    result = await apply_fixture_account(db_path, {**base, "snapshot_id": "one", "sequence": 1}, received_at=now)
    assert result["accepted"]
    later = now + timedelta(minutes=1)
    result = await apply_fixture_account(db_path, {**base, "snapshot_id": "two", "sequence": 2,
                                                   "observed_at": later.isoformat(), "positions": []}, received_at=later)
    assert (await load_partner_positions(db_path, include_closed=True))[0].status == "CLOSED"
    reopened_at = later + timedelta(minutes=1)
    await apply_fixture_account(db_path, {**base, "snapshot_id": "three", "sequence": 3,
                                          "observed_at": reopened_at.isoformat()}, received_at=reopened_at)
    rows = await load_partner_positions(db_path, include_closed=True)
    assert len(rows) == 2 and sum(row.status == "OPEN" for row in rows) == 1


@pytest.mark.asyncio
async def test_invalid_fixture_is_rejected_before_any_position_write(db_path, monkeypatch):
    now = IST.localize(datetime(2026, 9, 2, 11))
    monkeypatch.setattr(settings, "PARTNER_HEDGE_INPUT_EXPECTED_SOURCE", "fixture")
    monkeypatch.setattr(settings, "PARTNER_HEDGE_INPUT_EXPECTED_ACCOUNT_ID", "fixture-account")
    invalid = {"source": "fixture", "account_id": "fixture-account", "snapshot_id": "bad", "sequence": 1, "complete": True, "observed_at": now.isoformat(), "positions": [{"external_position_id": "ok", "underlying": "NIFTY", "tradingsymbol": "NIFTY", "quantity": 1, "entry_price": 100, "current_price": 100}, {"external_position_id": "bad", "underlying": "NIFTY", "tradingsymbol": "NIFTY", "quantity": "fraction", "entry_price": 100, "current_price": 100}]}
    with pytest.raises(ValueError, match="invalid fixture position"):
        await apply_fixture_account(db_path, invalid, received_at=now)
    assert await load_partner_positions(db_path, include_closed=True) == []
