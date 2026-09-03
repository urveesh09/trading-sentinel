import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
import pytz

import hedge_advisory as ha
from config import settings
from fno_chain import ChainSnapshot
from fno_models import Contract, ContractQuote
from hedge_advisory import (
    Phase2MarketContext, _claim, _complete_claim, _record, _release_claim,
    build_hedge_reviews, build_phase2_hedge_reviews,
    load_vix_observations, partner_hedge_phase2_tick, partner_hedge_tick,
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


def _phase2_snapshot():
    quotes = {}
    for kind, strike, bid, ask, token in (
        ("PE", 24_100, 8, 10, 11), ("PE", 24_300, 24, 26, 12),
        ("PE", 24_500, 70, 72, 13), ("CE", 25_500, 68, 70, 14),
        ("CE", 25_700, 24, 26, 15), ("CE", 25_900, 8, 10, 16),
        ("CE", 25_000, 299, 301, 18), ("PE", 25_000, 299, 301, 19),
    ):
        contract = _contract(kind, strike, token)
        quotes[(float(strike), kind)] = _quote(contract, bid, ask)
    future = _quote(_contract("FUT", 0, 17), 24_990, 25_010)
    return ChainSnapshot(
        NOW - timedelta(seconds=20), EXPIRY, 25_000, 25_000, 65,
        future, quotes,
    )


def _context(snapshot, *, mode="BEAR_TREND", rank=.80, support=24_500,
             resistance=25_500, expected_move=400):
    return Phase2MarketContext(
        mode=mode, atm_iv=.22, realized_vol=.16, iv_rank=rank,
        support=support, resistance=resistance, expected_move=expected_move,
        as_of=snapshot.taken_at,
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


def test_collar_requires_current_verified_deliverable_holding(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_HEDGE_PROTECTIVE_PUT", False)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_FUTURES", False)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_COLLAR", True)
    direct = PartnerPosition(**{
        **_position().__dict__, "tradingsymbol": "NIFTY", "signed_quantity": 130,
        "deliverable_quantity": 130, "deliverable_as_of": NOW,
        "deliverable_source": "broker_holding_snapshot",
    })
    assert {kind for kind, _, _ in build_hedge_reviews(
        [direct], _snapshot(), now=NOW,
    )} == {"collar_recommendation"}
    unverified = PartnerPosition(**{
        **direct.__dict__, "deliverable_source": "manual_note",
    })
    assert build_hedge_reviews([unverified], _snapshot(), now=NOW) == []


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
async def test_message_claim_is_atomic_and_daily_cap_counts_deliveries(db_path):
    first, second = await asyncio.gather(
        _claim(db_path, "delta_hedge_rebalance", "NIFTY:a", now=NOW,
               underlying="NIFTY", daily_cap=1),
        _claim(db_path, "delta_hedge_rebalance", "NIFTY:a", now=NOW,
               underlying="NIFTY", daily_cap=1),
    )
    assert int(first is not None) + int(second is not None) == 1
    await _record(db_path, "delta_hedge_rebalance", "NIFTY:a", True, now=NOW)
    assert not await _claim(
        db_path, "delta_hedge_rebalance", "NIFTY:b", now=NOW + timedelta(hours=1),
        underlying="NIFTY", daily_cap=1,
    )


@pytest.mark.asyncio
async def test_failed_message_claim_can_be_released_and_retried(db_path):
    assert await _claim(db_path, "bear_call_spread", "NIFTY:a", now=NOW)
    await _release_claim(db_path, "bear_call_spread", "NIFTY:a")
    assert await _claim(db_path, "bear_call_spread", "NIFTY:a", now=NOW)


@pytest.mark.asyncio
async def test_expired_claim_can_only_be_finalized_by_its_new_owner(db_path):
    old = await _claim(db_path, "iron_condor", "NIFTY:a", now=NOW)
    new = await _claim(
        db_path, "iron_condor", "NIFTY:a", now=NOW + timedelta(hours=2),
    )
    assert old and new and old != new
    assert not await _complete_claim(
        db_path, "iron_condor", "NIFTY:a", old, detail={}, now=NOW,
    )
    assert await _complete_claim(
        db_path, "iron_condor", "NIFTY:a", new, detail={},
        now=NOW + timedelta(hours=2),
    )


@pytest.mark.asyncio
async def test_tick_is_zero_cost_when_phase_flag_is_disabled(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_HEDGE_ENABLED", False)
    await partner_hedge_tick(NOW)


@pytest.mark.asyncio
async def test_phase2_tick_is_zero_cost_when_its_independent_gate_is_off(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_HEDGE_PHASE2_ENABLED", False)
    await partner_hedge_phase2_tick(NOW)


@pytest.mark.asyncio
async def test_phase2_tick_stops_before_calendar_or_broker_work_outside_market_hours(
    monkeypatch,
):
    import main

    async def must_not_check_calendar(*args, **kwargs):
        raise AssertionError("out-of-hours Phase 2 tick must stop at the time gate")

    monkeypatch.setattr(settings, "PARTNER_HEDGE_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_PHASE2_ENABLED", True)
    monkeypatch.setattr(ha, "partner_enabled", lambda: True)
    monkeypatch.setattr(main, "is_trading_day", must_not_check_calendar)
    after_close = IST.localize(datetime(2026, 9, 2, 16, 0))
    await partner_hedge_phase2_tick(after_close)


def test_phase2_bear_call_and_delta_are_tied_to_long_exposure(monkeypatch):
    snapshot = _phase2_snapshot()
    reviews = build_phase2_hedge_reviews(
        [_position()], snapshot, _context(snapshot), now=NOW,
    )
    kinds = {kind for kind, _, _ in reviews}
    assert "bear_call_spread" in kinds
    assert "delta_hedge_rebalance" in kinds
    assert "bull_put_spread" not in kinds


def test_phase2_bull_put_is_only_added_for_verified_short_delta_in_bull_mode():
    snapshot = _phase2_snapshot()
    short_future = PartnerPosition(
        underlying="NIFTY", instrument_type="FUT",
        tradingsymbol="NIFTY26SEPFUT", signed_quantity=-130, lot_size=65,
        quantity_basis="UNITS", entry_price=25_000, current_price=25_000,
        price_as_of=NOW - timedelta(minutes=1), opened_at=NOW - timedelta(days=1),
        source="broker_import", verification_status="RECONCILED",
    )
    kinds = {kind for kind, _, _ in build_phase2_hedge_reviews(
        [short_future], snapshot, _context(snapshot, mode="BULL_TREND"), now=NOW,
    )}
    assert "bull_put_spread" in kinds
    assert "bear_call_spread" not in kinds


def test_phase2_covered_call_requires_same_day_verified_deliverable_holding():
    snapshot = _phase2_snapshot()
    direct = _position().__dict__ | {
        "tradingsymbol": "NIFTY", "signed_quantity": 130,
        "deliverable_quantity": 130, "deliverable_as_of": NOW,
        "deliverable_source": "broker_holding_snapshot",
    }
    current = PartnerPosition(**direct)
    kinds = {kind for kind, _, _ in build_phase2_hedge_reviews(
        [current], snapshot, _context(snapshot, mode="BULL_TREND"), now=NOW,
    )}
    assert "covered_call_recommendation" in kinds

    stale = PartnerPosition(**{
        **direct, "deliverable_as_of": NOW - timedelta(days=1),
    })
    stale_kinds = {kind for kind, _, _ in build_phase2_hedge_reviews(
        [stale], snapshot, _context(snapshot, mode="BULL_TREND"), now=NOW,
    )}
    assert "covered_call_recommendation" not in stale_kinds

    intraday_stale = PartnerPosition(**{
        **direct, "deliverable_as_of": NOW - timedelta(hours=1),
    })
    intraday_stale_kinds = {kind for kind, _, _ in build_phase2_hedge_reviews(
        [intraday_stale], snapshot, _context(snapshot, mode="BULL_TREND"), now=NOW,
    )}
    assert "covered_call_recommendation" not in intraday_stale_kinds

    unverified = PartnerPosition(**{
        **direct, "deliverable_source": "manual_note",
    })
    unverified_kinds = {kind for kind, _, _ in build_phase2_hedge_reviews(
        [unverified], snapshot, _context(snapshot, mode="BULL_TREND"), now=NOW,
    )}
    assert "covered_call_recommendation" not in unverified_kinds


def test_phase2_premium_reviews_fail_closed_without_rank_or_exact_regime():
    snapshot = _phase2_snapshot()
    context = _context(snapshot, mode="UNKNOWN", rank=None)
    kinds = {kind for kind, _, _ in build_phase2_hedge_reviews(
        [_position()], snapshot, context, now=NOW,
    )}
    assert kinds == {"delta_hedge_rebalance"}


def test_phase2_condor_requires_verified_range_width_and_iv_over_rv():
    snapshot = _phase2_snapshot()
    wide_range = _context(
        snapshot, mode="RANGE", support=24_500, resistance=25_500,
        expected_move=400,
    )
    kinds = {kind for kind, _, _ in build_phase2_hedge_reviews(
        [_position()], snapshot, wide_range, now=NOW,
    )}
    assert "iron_condor" in kinds
    narrow = Phase2MarketContext(**{
        **wide_range.__dict__, "expected_move": 600,
    })
    narrow_kinds = {kind for kind, _, _ in build_phase2_hedge_reviews(
        [_position()], snapshot, narrow, now=NOW,
    )}
    assert "iron_condor" not in narrow_kinds


@pytest.mark.asyncio
async def test_phase2_context_does_not_reuse_prior_day_realized_vol(monkeypatch):
    import main
    import partner_orchestrator as legacy

    snapshot = _phase2_snapshot()
    monkeypatch.setattr(main, "_fno_regime_str", lambda: "REGIME_1_NORMAL")
    monkeypatch.setattr(main, "market_regime", "BULL")
    monkeypatch.setattr(main, "last_run", NOW.astimezone(timezone.utc))
    monkeypatch.setattr(ha.fno_analytics, "atm_iv_skew", lambda *args: (.20, .22))
    monkeypatch.setattr(ha.fno_analytics, "oi_walls", lambda *args: (24_500, 25_500))

    async def history(*args, **kwargs):
        return [(NOW.date() - timedelta(days=i + 1), .10 + i / 1000) for i in range(20)]

    monkeypatch.setattr(ha, "load_chain_iv_history", history)
    monkeypatch.setattr(legacy, "_rv_cache", {"NIFTY": .16})
    monkeypatch.setattr(legacy, "_rv_as_of", {"NIFTY": NOW.date() - timedelta(days=1)})
    stale = await ha._phase2_market_context("unused.db", snapshot, NOW)
    assert stale.mode == "BULL_TREND"
    assert stale.realized_vol is None

    legacy._rv_as_of["NIFTY"] = NOW.date()
    current = await ha._phase2_market_context("unused.db", snapshot, NOW)
    assert current.realized_vol == .16
    assert current.iv_rank is not None

    snapshot.quotes[(25_000.0, "PE")].last_trade_time = NOW - timedelta(minutes=10)
    stale_iv = await ha._phase2_market_context("unused.db", snapshot, NOW)
    assert stale_iv.atm_iv is None
    assert stale_iv.iv_rank is None


@pytest.mark.asyncio
async def test_phase2_context_rejects_prior_day_directional_regime(monkeypatch):
    import main

    snapshot = _phase2_snapshot()
    async def no_history(*args, **kwargs):
        return []

    monkeypatch.setattr(ha, "load_chain_iv_history", no_history)
    monkeypatch.setattr(main, "_fno_regime_str", lambda: "REGIME_1_NORMAL")
    monkeypatch.setattr(main, "market_regime", "BULL")
    monkeypatch.setattr(main, "last_run", NOW - timedelta(days=1))
    context = await ha._phase2_market_context("unused.db", snapshot, NOW)
    assert context.mode == "UNKNOWN"


@pytest.mark.asyncio
async def test_phase2_context_promotes_range_only_from_current_neutral_flow(monkeypatch):
    import fno_oi_store
    import main
    import partner_orchestrator as legacy

    snapshot = _phase2_snapshot()
    monkeypatch.setattr(main, "_fno_regime_str", lambda: "REGIME_1_NORMAL")
    monkeypatch.setattr(main, "market_regime", "CAUTION")
    monkeypatch.setattr(main, "last_run", NOW.astimezone(timezone.utc))
    monkeypatch.setattr(ha.fno_analytics, "atm_iv_skew", lambda *args: (.04, .04))

    async def history(*args, **kwargs):
        return [(NOW.date() - timedelta(days=i + 1), .03 + i / 1000) for i in range(20)]

    async def opening(*args, **kwargs):
        return {"fut_ltp": 24_990, "fut_oi": snapshot.fut_quote.oi}

    monkeypatch.setattr(ha, "load_chain_iv_history", history)
    monkeypatch.setattr(fno_oi_store, "first_fut_row_today", opening)
    monkeypatch.setattr(legacy, "_rv_cache", {"NIFTY": .03})
    monkeypatch.setattr(legacy, "_rv_as_of", {"NIFTY": NOW.date()})
    context = await ha._phase2_market_context("unused.db", snapshot, NOW)
    assert context.mode == "RANGE"

    async def trending(*args, **kwargs):
        return {"fut_ltp": 24_000, "fut_oi": snapshot.fut_quote.oi + 1}

    monkeypatch.setattr(fno_oi_store, "first_fut_row_today", trending)
    assert (await ha._phase2_market_context("unused.db", snapshot, NOW)).mode == "UNKNOWN"


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
