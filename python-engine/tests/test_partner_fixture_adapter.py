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
    retried = await apply_fixture_account(db_path, {**base, "snapshot_id": "one", "sequence": 1}, received_at=now)
    assert retried["idempotent"]
    assert len(await load_partner_positions(db_path, include_closed=True)) == 1
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


@pytest.mark.asyncio
async def test_rejected_fixture_envelope_does_not_create_a_position(db_path, monkeypatch):
    """Creation and the ordered snapshot envelope are one transaction boundary."""
    now = IST.localize(datetime(2026, 9, 2, 11))
    monkeypatch.setattr(settings, "PARTNER_HEDGE_INPUT_EXPECTED_SOURCE", "fixture")
    monkeypatch.setattr(settings, "PARTNER_HEDGE_INPUT_EXPECTED_ACCOUNT_ID", "fixture-account")
    rejected = {
        "source": "fixture", "account_id": "fixture-account", "snapshot_id": "bad-order",
        "sequence": -1, "complete": True, "observed_at": now.isoformat(),
        "positions": [{"external_position_id": "would-have-been-created", "underlying": "NIFTY",
                       "tradingsymbol": "NIFTY", "quantity": 1, "entry_price": 100,
                       "current_price": 100}],
    }
    with pytest.raises(ValueError, match="sequence"):
        await apply_fixture_account(db_path, rejected, received_at=now)
    assert await load_partner_positions(db_path, include_closed=True) == []


@pytest.mark.asyncio
async def test_complete_fixture_accepts_an_option_with_explicit_greeks(db_path, monkeypatch):
    now = IST.localize(datetime(2026, 9, 2, 11))
    monkeypatch.setattr(settings, "PARTNER_HEDGE_INPUT_EXPECTED_SOURCE", "fixture")
    monkeypatch.setattr(settings, "PARTNER_HEDGE_INPUT_EXPECTED_ACCOUNT_ID", "fixture-account")
    fixture = {
        "source": "fixture", "account_id": "fixture-account", "snapshot_id": "option-one",
        "sequence": 1, "complete": True, "observed_at": now.isoformat(),
        "positions": [{
            "external_position_id": "nifty-put", "instrument_type": "PE", "underlying": "NIFTY",
            "tradingsymbol": "NIFTY26SEP24500PE", "quantity": 50, "lot_size": 50,
            "entry_price": 110, "current_price": 125, "underlying_price": 24_450,
            "expiry": "2026-09-24", "strike": 24_500,
            "greeks": {"delta": -0.42, "gamma": 0.001, "theta": -1.8, "vega": 2.4},
        }],
    }
    result = await apply_fixture_account(db_path, fixture, received_at=now)
    assert result["accepted"]
    [position] = await load_partner_positions(db_path)
    assert position.instrument_type == "PE"
    assert position.verification_status == "RECONCILED"
    assert position.price_as_of == now
    assert position.greeks and position.greeks.delta == pytest.approx(-0.42)


@pytest.mark.asyncio
async def test_fixture_corporate_action_creates_an_adjusted_lifecycle_without_rewriting_history(db_path, monkeypatch):
    now = IST.localize(datetime(2026, 9, 2, 11))
    monkeypatch.setattr(settings, "PARTNER_HEDGE_INPUT_EXPECTED_SOURCE", "fixture")
    monkeypatch.setattr(settings, "PARTNER_HEDGE_INPUT_EXPECTED_ACCOUNT_ID", "fixture-account")
    base_position = {"external_position_id": "split-share", "underlying": "ACME", "tradingsymbol": "ACME",
                     "quantity": 10, "entry_price": 100, "current_price": 105}
    base = {"source": "fixture", "account_id": "fixture-account", "complete": True,
            "observed_at": now.isoformat(), "positions": [base_position]}
    assert (await apply_fixture_account(db_path, {**base, "snapshot_id": "before-split", "sequence": 1}, received_at=now))["accepted"]
    adjusted_at = now + timedelta(minutes=1)
    adjusted = {**base_position, "quantity": 20, "entry_price": 50, "current_price": 53,
                "corporate_action": {"event_id": "acme-2-for-1", "type": "SPLIT", "factor": 2,
                                     "effective_at": adjusted_at.isoformat()}}
    result = await apply_fixture_account(
        db_path, {**base, "snapshot_id": "after-split", "sequence": 2,
                   "observed_at": adjusted_at.isoformat(), "positions": [adjusted]}, received_at=adjusted_at,
    )
    assert result["accepted"]
    rows = await load_partner_positions(db_path, include_closed=True)
    assert len(rows) == 2 and sum(row.status == "OPEN" for row in rows) == 1
    historical = next(row for row in rows if row.status == "CLOSED")
    current = next(row for row in rows if row.status == "OPEN")
    # Closed positions correctly report zero current exposure; their immutable
    # entry economics remain intact and the adjusted exposure is a new row.
    assert (historical.signed_quantity, historical.entry_price) == (0, 100)
    assert (current.signed_quantity, current.entry_price) == (20, 50)
    # Replaying the same adjusted lifecycle is a normal newer snapshot, not a
    # second split lifecycle.
    replay_at = adjusted_at + timedelta(minutes=1)
    await apply_fixture_account(
        db_path, {**base, "snapshot_id": "after-split-replay", "sequence": 3,
                   "observed_at": replay_at.isoformat(), "positions": [adjusted]}, received_at=replay_at,
    )
    assert len(await load_partner_positions(db_path, include_closed=True)) == 2
