from datetime import date, datetime, timedelta, timezone

import pytest
import pytz

from config import settings
from fno_chain import ChainSnapshot
from fno_models import Contract, ContractQuote
from hedge_advisory import (
    build_hedge_reviews, load_vix_observations, partner_hedge_tick,
    record_vix_observation,
)
from hedge_analytics import PartnerPosition

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 9, 2, 11, 0))
EXPIRY = date(2026, 9, 29)


def _contract(kind, strike, token, lot=65):
    return Contract(token, f"NIFTY{EXPIRY:%y%m%d}{int(strike)}{kind}",
                    "NIFTY", EXPIRY, strike, kind, lot)


def _quote(contract, bid, ask):
    return ContractQuote(
        contract, bid=bid, ask=ask, ltp=(bid + ask) / 2,
        oi=5_000, volume=1_000, last_trade_time=NOW,
    )


def _snapshot():
    put = _quote(_contract("PE", 24_500, 1), 70, 72)
    call = _quote(_contract("CE", 25_500, 2), 68, 70)
    future = _quote(_contract("FUT", 0, 3), 24_990, 25_010)
    return ChainSnapshot(
        NOW - timedelta(seconds=20), EXPIRY, 25_000, 25_000, 65,
        future, {(24_500.0, "PE"): put, (25_500.0, "CE"): call},
    )


def _position(*, verification="RECONCILED", age_minutes=1):
    return PartnerPosition(
        underlying="NIFTY", instrument_type="EQUITY",
        tradingsymbol="NIFTY_BETA_BOOK", signed_quantity=40_000,
        lot_size=1, entry_price=95, current_price=100, beta=1,
        price_as_of=NOW - timedelta(minutes=age_minutes),
        opened_at=NOW - timedelta(days=2), updated_at=NOW,
        source="broker_import", verification_status=verification,
    )


def test_build_reviews_uses_reconciled_rupee_notional(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_HEDGE_PROTECTIVE_PUT", True)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_FUTURES", True)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_COLLAR", False)
    reviews = build_hedge_reviews([_position()], _snapshot(), now=NOW)
    by_kind = {kind: (plan, context) for kind, plan, context in reviews}
    assert set(by_kind) == {"protective_put_alert", "futures_hedge_size"}
    put = by_kind["protective_put_alert"][0]
    # ₹4m / NIFTY 25k = 160 equivalent units; two 65-unit lots are partial.
    assert put.protected_units == 160
    assert put.option_units == 130
    futures, sizing = by_kind["futures_hedge_size"]
    assert futures.lots == 1
    assert sizing.contracts_rounded == -1
    assert sizing.post_trade_hedge_pct == pytest.approx(1_625_000 / 4_000_000)


def test_build_reviews_fails_closed_for_stale_or_unreconciled_position(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_HEDGE_POSITION_MAX_AGE_MIN", 5)
    assert build_hedge_reviews([_position(age_minutes=6)], _snapshot(), now=NOW) == []
    assert build_hedge_reviews([
        _position(verification="PENDING_CONFIRMATION")
    ], _snapshot(), now=NOW) == []


@pytest.mark.asyncio
async def test_vix_intake_is_timestamped_sourced_and_idempotent(db_path):
    observed = datetime(2026, 9, 2, 4, 0, tzinfo=timezone.utc)
    await record_vix_observation(
        db_path, spot=18.2, observed_at=observed, source="verified-manual",
    )
    await record_vix_observation(
        db_path, spot=18.4, observed_at=observed, source="corrected-source",
    )
    rows = await load_vix_observations(db_path)
    assert len(rows) == 1
    assert rows[0]["spot"] == 18.4
    assert rows[0]["source"] == "corrected-source"
    with pytest.raises(ValueError, match="timezone-aware"):
        await record_vix_observation(
            db_path, spot=18, observed_at=datetime(2026, 9, 2, 10), source="x",
        )


@pytest.mark.asyncio
async def test_tick_is_zero_cost_when_phase_flag_is_disabled(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_HEDGE_ENABLED", False)
    await partner_hedge_tick(NOW)


@pytest.mark.asyncio
async def test_enabling_hedge_phase_suppresses_legacy_directional_scan(monkeypatch):
    import partner_orchestrator as legacy

    async def gates(*args, **kwargs):
        return True

    async def must_not_scan(*args, **kwargs):
        raise AssertionError("legacy directional scan must be suppressed")

    monkeypatch.setattr(settings, "PARTNER_HEDGE_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_SUPPRESS_DIRECTIONAL", True)
    monkeypatch.setattr(legacy, "_gates_open", gates)
    monkeypatch.setattr(legacy, "scan_underlying", must_not_scan)
    await legacy.partner_scan_tick(NOW)


@pytest.mark.asyncio
async def test_enabling_hedge_phase_suppresses_standalone_chain_noise(
    db_path, monkeypatch,
):
    import partner_orchestrator as legacy

    async def must_not_send(*args, **kwargs):
        raise AssertionError("standalone analytics message must be suppressed")

    monkeypatch.setattr(settings, "PARTNER_HEDGE_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_SUPPRESS_ANALYTICS", True)
    monkeypatch.setattr(legacy, "send_partner", must_not_send)
    await legacy._send_event(db_path, "pcr_shift", "NIFTY", "noise", NOW)
