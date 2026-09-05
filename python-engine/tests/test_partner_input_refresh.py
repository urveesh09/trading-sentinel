from datetime import datetime

import pytest
import pytz

from hedge_analytics import PartnerPosition, create_partner_position, load_partner_positions
from partner_input_refresh import apply_partner_input_snapshot, refresh_partner_input_once
from config import settings


IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 9, 5, 10, 0))


def snapshot(*, source="synthetic_adapter", account_id="paper-1", snapshot_id="s-1", sequence=1,
             observed_at=NOW, complete=True, positions=None, **extra):
    return {"source": source, "account_id": account_id, "snapshot_id": snapshot_id,
            "sequence": sequence, "observed_at": observed_at.isoformat(), "complete": complete,
            "positions": [] if positions is None else positions, **extra}


@pytest.mark.asyncio
async def test_complete_snapshot_reconciles_marks_records_vix_and_closes_absent_rows(db_path):
    stored = await create_partner_position(db_path, PartnerPosition(
        underlying="NIFTY", instrument_type="EQUITY", tradingsymbol="NIFTYBEES",
        signed_quantity=100, lot_size=1, entry_price=100, opened_at=NOW,
        source="synthetic_adapter", current_price=100, price_as_of=NOW,
    ))
    outcome = await apply_partner_input_snapshot(db_path, snapshot(
        positions=[{
            "position_id": stored.position_id, "observed_quantity": 125,
            "quantity_basis": "UNITS", "current_price": 102,
            "underlying_price": 102, "price_as_of": NOW.isoformat(),
        }],
        vix={"spot": 14.5, "observed_at": NOW.isoformat()},
    ), received_at=NOW)
    assert outcome["accepted"] is True
    assert outcome["reconciled"] == 1
    assert outcome["vix_recorded"] is True
    open_rows = await load_partner_positions(db_path)
    assert open_rows[0].signed_quantity == 125
    await apply_partner_input_snapshot(db_path, snapshot(snapshot_id="s-2", sequence=2,
        observed_at=NOW.replace(minute=1)), received_at=NOW.replace(minute=1))
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
        await apply_partner_input_snapshot(db_path, snapshot(source="owner_b", complete=False,
            positions=[{
                "position_id": stored.position_id, "observed_quantity": 100,
                "current_price": 100, "price_as_of": NOW.isoformat(),
            }],
        ), received_at=NOW)


@pytest.mark.asyncio
async def test_invalid_later_row_rolls_back_every_position_change(db_path):
    first = await create_partner_position(db_path, PartnerPosition(
        underlying="NIFTY", instrument_type="EQUITY", tradingsymbol="NIFTYBEES",
        signed_quantity=40_000, lot_size=1, entry_price=100, opened_at=NOW,
        source="synthetic_adapter", current_price=100, price_as_of=NOW,
    ))
    with pytest.raises(ValueError, match="unknown position_id"):
        await apply_partner_input_snapshot(db_path, snapshot(positions=[
            {"position_id": first.position_id, "observed_quantity": 20_000,
             "current_price": 100, "price_as_of": NOW.isoformat()},
            {"position_id": 999999, "observed_quantity": 1},
        ]), received_at=NOW)
    assert (await load_partner_positions(db_path))[0].signed_quantity == 40_000


@pytest.mark.asyncio
async def test_stale_or_partial_snapshot_never_becomes_current_portfolio_truth(db_path):
    stored = await create_partner_position(db_path, PartnerPosition(
        underlying="NIFTY", instrument_type="EQUITY", tradingsymbol="NIFTYBEES",
        signed_quantity=100, lot_size=1, entry_price=100, opened_at=NOW,
        source="synthetic_adapter", current_price=100, price_as_of=NOW,
    ))
    await apply_partner_input_snapshot(db_path, snapshot(positions=[{
        "position_id": stored.position_id, "observed_quantity": 100,
        "current_price": 100, "price_as_of": NOW.isoformat(),
    }]), received_at=NOW)
    with pytest.raises(ValueError, match="stale|out-of-order|older"):
        await apply_partner_input_snapshot(db_path, snapshot(snapshot_id="old", sequence=0,
            observed_at=NOW.replace(hour=9), positions=[]), received_at=NOW.replace(minute=2))
    assert len(await load_partner_positions(db_path)) == 1
    partial = await apply_partner_input_snapshot(db_path, snapshot(snapshot_id="s-2", sequence=2,
        observed_at=NOW.replace(minute=1), complete=False, positions=[{
            "position_id": stored.position_id, "observed_quantity": 100,
            "current_price": 100, "price_as_of": NOW.isoformat(),
        }]), received_at=NOW.replace(minute=1))
    assert partial["complete"] is False


@pytest.mark.asyncio
async def test_invalid_vix_rejects_before_a_complete_snapshot_can_close_rows(db_path):
    stored = await create_partner_position(db_path, PartnerPosition(
        underlying="NIFTY", instrument_type="EQUITY", tradingsymbol="NIFTYBEES",
        signed_quantity=100, lot_size=1, entry_price=100, opened_at=NOW,
        source="synthetic_adapter", current_price=100, price_as_of=NOW,
    ))
    with pytest.raises(ValueError, match="vix.spot"):
        await apply_partner_input_snapshot(db_path, snapshot(
            positions=[], vix={"spot": -1, "observed_at": NOW.isoformat()},
        ), received_at=NOW)
    assert (await load_partner_positions(db_path))[0].position_id == stored.position_id
