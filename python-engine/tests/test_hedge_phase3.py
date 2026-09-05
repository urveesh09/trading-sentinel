from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytz
import pytest

import hedge_advisory as ha
from config import settings
from fno_chain import ChainSnapshot
from fno_models import Contract, ContractQuote
from hedge_advisory import (
    Phase2MarketContext, Phase3MarketContext, build_phase3_hedge_reviews,
    partner_hedge_phase3_tick,
)
from hedge_analytics import PartnerPosition, PortfolioMarketStressReading
from hedge_formatters import (
    DISCLAIMER, format_calendar_diary_spread, format_iron_butterfly,
    format_long_vol_review, format_ratio_spread, format_gamma_exposure_alert,
)
from hedge_strategies import (
    calendar_diary_spread, iron_butterfly, long_straddle, long_strangle,
    ratio_spread,
)

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 9, 2, 11, 0))


def _snapshot(expiry=date(2026, 9, 24)):
    quotes = {}
    for kind, strike, bid, ask, token in (
        ("PE", 24300, 24, 26, 301), ("PE", 24800, 105, 108, 302),
        ("PE", 25000, 190, 194, 303), ("CE", 25000, 185, 189, 304),
        ("CE", 25200, 100, 103, 305), ("CE", 25700, 23, 25, 306),
    ):
        c = Contract(token, f"NIFTY{expiry:%y%m%d}{strike}{kind}", "NIFTY",
                     expiry, strike, kind, 65)
        quotes[(float(strike), kind)] = ContractQuote(
            c, bid=bid, ask=ask, ltp=(bid+ask)/2, oi=5000, volume=1000,
            last_trade_time=NOW,
        )
    fc = Contract(399, f"NIFTY{expiry:%y%m%d}FUT", "NIFTY", expiry, 0, "FUT", 65)
    fq = ContractQuote(fc, bid=24990, ask=25010, ltp=25000, oi=50000,
                       volume=10000, last_trade_time=NOW)
    return ChainSnapshot(NOW-timedelta(seconds=10), expiry, 25000, 25000, 65, fq, quotes)


def _position():
    return PartnerPosition(
        underlying="NIFTY", instrument_type="EQUITY", tradingsymbol="NIFTYBEES",
        signed_quantity=100, lot_size=1, entry_price=24000, current_price=25000,
        opened_at=NOW-timedelta(days=30), source="kite_holdings",
        price_as_of=NOW, updated_at=NOW, verification_status="RECONCILED",
    )


def test_phase3_formatters_preserve_risk_and_disclaimer():
    snap = _snapshot()
    plans = [long_straddle(snap, NOW), long_strangle(snap, NOW),
             iron_butterfly(snap, NOW, wing_width=200)]
    texts = [format_long_vol_review(plans[0]), format_long_vol_review(plans[1]),
             format_iron_butterfly(plans[2])]
    back = _snapshot(date(2026, 10, 29))
    back.quotes[(25000.0, "CE")].bid = 290
    back.quotes[(25000.0, "CE")].ask = 300
    texts.append(format_calendar_diary_spread(calendar_diary_spread(snap, back, NOW)))
    research = ratio_spread(snap, NOW, allow_unbounded=True)
    texts.append(format_ratio_spread(research))
    assert all(
        DISCLAIMER in text
        and (
            "automatic action" in text.lower()
            or "runtime emission is disabled" in text.lower()
        )
        for text in texts
    )
    assert "UNBOUNDED" in texts[-1]


def test_phase3_review_builder_requires_verified_event_and_respects_master_kinds(monkeypatch):
    snap = _snapshot()
    p2 = Phase2MarketContext("UNKNOWN", .14, .16, .20, None, None, 300.0, snap.taken_at)
    context = Phase3MarketContext(p2, event_window="EARNINGS_TOMORROW")
    monkeypatch.setattr(settings, "PARTNER_HEDGE_LONG_STRADDLE", True)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_LONG_STRANGLE", True)
    reviews = build_phase3_hedge_reviews([_position()], snap, context, now=NOW)
    assert {kind for kind, _, _ in reviews} >= {"long_straddle", "long_strangle"}
    quiet = build_phase3_hedge_reviews(
        [_position()], snap, Phase3MarketContext(p2, event_window="UNKNOWN"), now=NOW)
    assert not {"long_straddle", "long_strangle"} & {kind for kind, _, _ in quiet}


def test_phase3_defaults_and_ratio_runtime_gate_stay_off_until_go_live():
    assert settings.PARTNER_HEDGE_RATIO_SPREAD is False
    assert settings.PARTNER_HEDGE_PHASE3_ENABLED is False
    assert settings.PARTNER_HEDGE_PORTFOLIO_OVERLAY is True
    assert ratio_spread(_snapshot(), NOW) is None


def test_gamma_formatter_uses_analytics_rupee_units():
    text = format_gamma_exposure_alert("NIFTY", -125000.0, 3.5, as_of=NOW)
    assert "₹-125,000.00 per 1% underlying move" in text
    assert "delta/point" not in text


def test_phase3_butterfly_and_calendar_require_exact_research_thresholds(monkeypatch):
    front = _snapshot(date(2026, 9, 3))
    back = _snapshot(date(2026, 10, 29))
    p2 = Phase2MarketContext("RANGE", .20, .16, .80, 24_500, 25_500, 300.0, front.taken_at)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_IRON_BUTTERFLY", True)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_CALENDAR_SPREAD", True)
    kinds = {kind for kind, _, _ in build_phase3_hedge_reviews(
        [_position()], front, Phase3MarketContext(p2, back_atm_iv=.16),
        now=NOW, back_snapshot=back,
    )}
    assert {"iron_butterfly", "calendar_diary_spread"} <= kinds

    narrow_gap = {kind for kind, _, _ in build_phase3_hedge_reviews(
        [_position()], front, Phase3MarketContext(p2, back_atm_iv=.18),
        now=NOW, back_snapshot=back,
    )}
    assert "calendar_diary_spread" not in narrow_gap

    far_front = _snapshot(date(2026, 9, 24))
    far_p2 = Phase2MarketContext("RANGE", .20, .16, .80, 24_500, 25_500, 300.0, far_front.taken_at)
    far_kinds = {kind for kind, _, _ in build_phase3_hedge_reviews(
        [_position()], far_front, Phase3MarketContext(far_p2), now=NOW,
    )}
    assert "iron_butterfly" not in far_kinds


@pytest.mark.asyncio
async def test_phase3_tick_stops_before_calendar_and_broker_when_disabled_or_closed(monkeypatch):
    import main

    async def must_not_check_calendar(*args, **kwargs):
        raise AssertionError("Phase 3 gate must stop before calendar or broker work")

    monkeypatch.setattr(main, "is_trading_day", must_not_check_calendar)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_PHASE3_ENABLED", False)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_PHASE3_SHADOW_ENABLED", False)
    await partner_hedge_phase3_tick(NOW)

    monkeypatch.setattr(settings, "PARTNER_HEDGE_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_PHASE3_ENABLED", True)
    monkeypatch.setattr(ha, "partner_enabled", lambda: True)
    await partner_hedge_phase3_tick(IST.localize(datetime(2026, 9, 2, 16, 0)))


def test_portfolio_overlay_requires_complete_correlation_and_breadth_trigger(monkeypatch):
    snap = _snapshot()
    p2 = Phase2MarketContext("UNKNOWN", .14, .16, .20, None, None, 300.0, snap.taken_at)
    position = PartnerPosition(**{
        **_position().__dict__, "signed_quantity": 130,
    })
    monkeypatch.setattr(settings, "PARTNER_HEDGE_PORTFOLIO_OVERLAY", True)
    triggered = PortfolioMarketStressReading(
        .90, .10, None, True, False, True, 2, 50,
        "portfolio valuation history unavailable; drawdown trigger disabled",
    )
    kinds = {kind for kind, _, _ in build_phase3_hedge_reviews(
        [position], snap,
        Phase3MarketContext(
            p2, correlation=.90, portfolio_stress=triggered,
        ),
        now=NOW,
    )}
    assert "portfolio_corruption_overlay" in kinds

    incomplete = PortfolioMarketStressReading(
        None, None, None, False, False, False, 1, 0, "insufficient data",
    )
    kinds = {kind for kind, _, _ in build_phase3_hedge_reviews(
        [position], snap,
        Phase3MarketContext(p2, portfolio_stress=incomplete), now=NOW,
    )}
    assert "portfolio_corruption_overlay" not in kinds


@pytest.mark.asyncio
async def test_phase3_tick_builds_portfolio_stress_inside_phase3_job(monkeypatch):
    """Guard the job boundary: Phase 3 must not depend on Phase 1 locals."""
    import event_calendar
    import macro_events
    import main

    second = PartnerPosition(**{
        **_position().__dict__, "tradingsymbol": "BANKBEES",
    })
    stress = PortfolioMarketStressReading(
        .90, .10, None, True, False, True, 2, 50,
        "portfolio valuation history unavailable; drawdown trigger disabled",
    )

    async def yes(*args, **kwargs):
        return True

    async def no_op(*args, **kwargs):
        return None

    async def positions(*args, **kwargs):
        return [_position(), second]

    async def ready_portfolio(*args, **kwargs):
        return "READY_FOR_EVALUATION"

    async def closes(*args, **kwargs):
        return {"NIFTYBEES": tuple(range(1, 52)), "BANKBEES": tuple(range(2, 53))}

    async def snapshot(*args, **kwargs):
        return _snapshot()

    async def phase2(*args, **kwargs):
        snap = _snapshot()
        return Phase2MarketContext("UNKNOWN", .14, .16, .20, None, None, 300.0, snap.taken_at)

    captured = []

    def reviews(_positions, _snapshot_value, context, **kwargs):
        captured.append(context)
        return []

    monkeypatch.setattr(settings, "PARTNER_HEDGE_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_HEDGE_PHASE3_ENABLED", True)
    monkeypatch.setattr(ha, "partner_enabled", lambda: True)
    monkeypatch.setattr(main, "is_trading_day", yes)
    monkeypatch.setattr(main.kite, "access_token", "test-token")
    monkeypatch.setattr(ha, "init_hedge_advisory_db", no_op)
    monkeypatch.setattr(ha, "_set_service_state", no_op)
    monkeypatch.setattr(ha, "load_reconciled_open_partner_positions", positions)
    monkeypatch.setattr(ha, "_whole_portfolio_input_reason", ready_portfolio)
    monkeypatch.setattr(ha, "load_aligned_ohlcv_closes", closes)
    monkeypatch.setattr(ha, "portfolio_market_stress", lambda *args, **kwargs: stress)
    monkeypatch.setattr(
        ha, "get_instruments_for",
        lambda underlying: SimpleNamespace(
            ready=lambda today: True, option_expiries=[date(2026, 9, 24)],
        ),
    )
    monkeypatch.setattr(ha, "take_chain_snapshot", snapshot)
    monkeypatch.setattr(ha, "_phase2_market_context", phase2)
    monkeypatch.setattr(ha, "build_phase3_hedge_reviews", reviews)
    monkeypatch.setattr(event_calendar, "load_event_map", lambda path: {})
    monkeypatch.setattr(macro_events, "event_note_for", lambda day: None)

    await partner_hedge_phase3_tick(NOW)

    assert captured and captured[0].portfolio_stress is stress
    assert captured[0].correlation == .90
