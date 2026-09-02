from datetime import date, datetime, timedelta, timezone

import pytest

from hedge_analytics import (
    Greeks, PartnerHolding, PartnerPosition, aggregate_portfolio,
    assess_quote_freshness, close_partner_position, create_partner_position,
    get_partner_position, load_partner_positions,
    load_reconciled_open_partner_positions, position_is_actionable,
    reconcile_partner_position, size_futures_hedge, vix_regime_reading,
)


UTC = timezone.utc
NOW = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)


def equity(*, qty=1000, price=100.0, verification="RECONCILED", **changes):
    values = dict(
        underlying="NIFTY", instrument_type="EQUITY", tradingsymbol="NIFTYETF",
        signed_quantity=qty, lot_size=1, entry_price=95.0, current_price=price,
        price_as_of=NOW - timedelta(minutes=1), opened_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(minutes=1), source="broker_import",
        verification_status=verification,
    )
    values.update(changes)
    return PartnerPosition(**values)


def option(*, qty=-1, verification="RECONCILED", **changes):
    values = dict(
        underlying="NIFTY", instrument_type="PE", tradingsymbol="NIFTY26SEP24000PE",
        signed_quantity=qty, lot_size=65, entry_price=120.0, current_price=135.0,
        price_as_of=NOW - timedelta(minutes=1), opened_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(minutes=1), source="broker_import",
        verification_status=verification, expiry=date(2026, 9, 29), strike=24000.0,
        underlying_price=25000.0,
        greeks=Greeks(delta=-0.30, gamma=0.001, theta=-2.0, vega=5.0),
    )
    values.update(changes)
    return PartnerPosition(**values)


def test_signed_quantity_is_only_direction_and_option_greeks_are_required():
    with pytest.raises(ValueError, match="signed_quantity"):
        equity(qty=0)
    with pytest.raises(ValueError, match="explicit Greeks"):
        option(greeks=None)
    with pytest.raises(ValueError, match="equity lot_size"):
        equity(lot_size=65)


def test_frozen_types_and_position_net_greeks_apply_signed_contract_units():
    position = option(qty=-2)
    assert position.units == -130
    assert position.net_greeks == Greeks(delta=39.0, gamma=-0.13, theta=260.0, vega=-650.0)
    with pytest.raises(Exception):
        position.signed_quantity = 1


def test_holding_requires_quote_timestamp_when_a_current_quote_is_supplied():
    with pytest.raises(ValueError, match="price_as_of"):
        PartnerHolding("ABC", "ABC", 10, 100, 101)


def test_quote_freshness_fails_closed_for_missing_naive_future_and_stale_quotes():
    assert not assess_quote_freshness(None, now=NOW).fresh
    assert not assess_quote_freshness(datetime(2026, 9, 1, 10, 0), now=NOW).fresh
    assert not assess_quote_freshness(NOW - timedelta(minutes=6), now=NOW).fresh
    assert not assess_quote_freshness(NOW + timedelta(minutes=2), now=NOW).fresh
    assert assess_quote_freshness(NOW - timedelta(minutes=2), now=NOW).fresh


def test_actionable_guard_needs_reconciliation_current_and_fresh_data():
    assert position_is_actionable(equity(), now=NOW)
    assert not position_is_actionable(equity(verification="PENDING_CONFIRMATION"), now=NOW)
    assert not position_is_actionable(equity(price_as_of=NOW - timedelta(minutes=6)), now=NOW)
    assert not position_is_actionable(equity(current_price=None, price_as_of=None), now=NOW)


def test_portfolio_aggregation_shows_existing_hedge_percentage():
    long_book = equity(qty=20000)
    future_hedge = PartnerPosition(
        underlying="NIFTY", instrument_type="FUT", tradingsymbol="NIFTY26SEPFUT",
        signed_quantity=-1, lot_size=65, entry_price=25000.0, current_price=25000.0,
        price_as_of=NOW, opened_at=NOW, source="broker", verification_status="RECONCILED",
    )
    exposure = aggregate_portfolio([long_book, future_hedge])
    assert exposure.valid
    assert exposure.long_delta_notional == 2_000_000.0
    assert exposure.short_delta_notional == 1_625_000.0
    assert exposure.net_delta_notional == 375_000.0
    assert exposure.hedged_pct == 0.8125
    assert exposure.gross_notional == 3_625_000.0


def test_portfolio_fails_closed_for_unconfirmed_or_missing_price():
    assert not aggregate_portfolio([equity(verification="PENDING_CONFIRMATION")]).valid
    assert not aggregate_portfolio([equity(current_price=None, price_as_of=None)]).valid


def test_futures_sizing_rounds_toward_zero_and_reports_before_after_hedge_percentage():
    exposure = aggregate_portfolio([equity(qty=40_000)])
    sized = size_futures_hedge(
        exposure, futures_underlying="NIFTY", lot_size=65, futures_price=25000,
        target_hedge_ratio=0.50,
    )
    assert sized.valid
    assert sized.contracts_raw == pytest.approx(-2_000_000 / 1_625_000)
    assert sized.contracts_rounded == -1
    assert sized.existing_hedge_pct == 0.0
    assert sized.post_trade_hedge_pct == pytest.approx(1_625_000 / 4_000_000)
    assert sized.advisory_only


def test_futures_sizing_rejects_mixed_underlying_or_overhedging_one_lot():
    mixed = aggregate_portfolio([equity(), equity(underlying="BANKNIFTY", tradingsymbol="BNF")])
    assert not size_futures_hedge(mixed, futures_underlying="NIFTY", lot_size=65, futures_price=1, target_hedge_ratio=.5).valid
    tiny = aggregate_portfolio([equity(qty=1000)])
    sized = size_futures_hedge(tiny, futures_underlying="NIFTY", lot_size=65, futures_price=25000, target_hedge_ratio=.5)
    assert not sized.valid
    assert sized.contracts_rounded == 0


def test_vix_regime_is_deterministic_informational_and_handles_no_or_stale_data():
    history = [15.0] * 19 + [16.0]
    reading = vix_regime_reading(20.0, 15.0, history=history, observed_at=NOW, now=NOW)
    assert reading.regime == "PANIC"
    assert reading.should_review_protection
    assert not reading.automatic_action
    assert "automatic" in reading.posture
    assert vix_regime_reading(None).regime == "UNAVAILABLE"
    assert vix_regime_reading(20, history=history, observed_at=NOW - timedelta(minutes=16), now=NOW).regime == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_position_crud_reconciliation_and_reconciled_loader(db_path):
    pending = equity(verification="PENDING_CONFIRMATION", broker_order_id="ORD-1")
    created = await create_partner_position(db_path, pending)
    assert created.position_id is not None
    assert await load_reconciled_open_partner_positions(db_path) == []
    # Broker-order id makes re-import idempotent: it cannot create a duplicate.
    duplicate = await create_partner_position(db_path, pending)
    assert duplicate.position_id == created.position_id
    assert len(await load_partner_positions(db_path)) == 1
    with pytest.raises(ValueError, match="different partner position"):
        await create_partner_position(
            db_path, equity(verification="PENDING_CONFIRMATION",
                            broker_order_id="ORD-1", qty=999),
        )

    reconciled = await reconcile_partner_position(
        db_path, created.position_id, observed_quantity=900, reconciled_at=NOW,
        source="broker_import", current_price=101.0, price_as_of=NOW,
    )
    assert reconciled is not None
    assert reconciled.verification_status == "RECONCILED"
    assert reconciled.signed_quantity == 900
    assert [p.position_id for p in await load_reconciled_open_partner_positions(db_path)] == [created.position_id]
    closed = await close_partner_position(db_path, created.position_id, closed_at=NOW + timedelta(minutes=1), source="broker_import")
    assert closed.status == "CLOSED"
    assert await load_reconciled_open_partner_positions(db_path) == []
    assert (await get_partner_position(db_path, created.position_id)).closed_at == NOW + timedelta(minutes=1)


@pytest.mark.asyncio
async def test_open_option_cannot_be_reconciled_without_current_greeks(db_path):
    created = await create_partner_position(db_path, option(verification="PENDING_CONFIRMATION"))
    with pytest.raises(ValueError, match="current Greeks"):
        await reconcile_partner_position(
            db_path, created.position_id, observed_quantity=-1, reconciled_at=NOW,
            source="broker", current_price=130.0, price_as_of=NOW,
        )
    reconciled = await reconcile_partner_position(
        db_path, created.position_id, observed_quantity=-1, reconciled_at=NOW,
        source="broker", current_price=130.0, price_as_of=NOW,
        greeks=Greeks(delta=-.25, gamma=.001, theta=-2, vega=4),
        underlying_price=25050.0,
    )
    assert reconciled.verification_status == "RECONCILED"
