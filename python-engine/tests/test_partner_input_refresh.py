from datetime import datetime

import pytest
import pytz

from hedge_analytics import PartnerPosition, create_partner_position, load_partner_positions
from partner_input_refresh import apply_partner_input_snapshot, refresh_partner_input_once
from config import settings


IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 9, 5, 10, 0))


@pytest.mark.asyncio
async def test_complete_snapshot_reconciles_marks_records_vix_and_closes_absent_rows(db_path):
    stored = await create_partner_position(db_path, PartnerPosition(
        underlying="NIFTY", instrument_type="EQUITY", tradingsymbol="NIFTYBEES",
        signed_quantity=100, lot_size=1, entry_price=100, opened_at=NOW,
        source="synthetic_adapter", current_price=100, price_as_of=NOW,
    ))
    outcome = await apply_partner_input_snapshot(db_path, {
        "source": "synthetic_adapter", "observed_at": NOW.isoformat(), "complete": True,
        "positions": [{
            "position_id": stored.position_id, "observed_quantity": 125,
            "quantity_basis": "UNITS", "current_price": 102,
            "underlying_price": 102, "price_as_of": NOW.isoformat(),
        }],
        "vix": {"spot": 14.5, "observed_at": NOW.isoformat()},
    })
    assert outcome == {
        "source": "synthetic_adapter", "observed_at": NOW.isoformat(),
        "complete": True, "reconciled": 1, "closed": 0, "vix_recorded": True,
    }
    open_rows = await load_partner_positions(db_path)
    assert open_rows[0].signed_quantity == 125
    await apply_partner_input_snapshot(db_path, {
        "source": "synthetic_adapter", "observed_at": NOW.isoformat(),
        "complete": True, "positions": [],
    })
    assert await load_partner_positions(db_path) == []


@pytest.mark.asyncio
async def test_unconfigured_adapter_is_explicit_and_performs_no_network(db_path, monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_HEDGE_INPUT_ADAPTER_URL", "")
    assert await refresh_partner_input_once(db_path) == {"state": "INPUT_ADAPTER_UNCONFIGURED"}


@pytest.mark.asyncio
async def test_snapshot_cannot_reconcile_a_position_owned_by_another_source(db_path):
    stored = await create_partner_position(db_path, PartnerPosition(
        underlying="NIFTY", instrument_type="EQUITY", tradingsymbol="NIFTYBEES",
        signed_quantity=100, lot_size=1, entry_price=100, opened_at=NOW,
        source="owner_a", current_price=100, price_as_of=NOW,
    ))
    with pytest.raises(ValueError, match="does not own"):
        await apply_partner_input_snapshot(db_path, {
            "source": "owner_b", "observed_at": NOW.isoformat(), "complete": False,
            "positions": [{
                "position_id": stored.position_id, "observed_quantity": 100,
                "current_price": 100, "price_as_of": NOW.isoformat(),
            }],
        })
