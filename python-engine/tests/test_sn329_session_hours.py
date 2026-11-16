"""[SN329 2026-11-16] NSE CAS 2.0 session hours from 2026-12-07 (NSE FAQ updated 2026-11-06): derivatives close at
15:45; expiring index contracts stop at 15:30 on their expiry day; the cash auction runs 15:30-15:45. Sessions before
2026-12-07 keep the 15:40 close and the 15:15-15:35 auction."""
from datetime import date, datetime, time

import pytz

import market_calendar as mc

IST = pytz.timezone("Asia/Kolkata")


def at(day, hh, mm):
    return IST.localize(datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:00"))


def test_close_times_by_date():
    assert mc.derivatives_close_time(date(2026, 12, 4)) == time(15, 40)
    assert mc.derivatives_close_time(date(2026, 12, 7)) == time(15, 45)
    assert mc.derivatives_close_minute(date(2027, 1, 5)) == 945
    assert mc.expiring_index_close_time(date(2026, 12, 1)) == time(15, 40)
    assert mc.expiring_index_close_time(date(2026, 12, 8)) == time(15, 30)


def test_derivative_phases_both_regimes():
    phase = lambda d, h, m: mc.classify_session_phase(at(d, h, m), is_derivative=True, cas_eligible=False)  # noqa: E731
    assert phase("2026-12-04", 15, 29) == mc.SESSION_PHASE_CONTINUOUS_TRADING
    assert phase("2026-12-04", 15, 35) == mc.SESSION_PHASE_DERIVATIVES_CAS_ALIGNED
    assert phase("2026-12-04", 15, 42) == mc.SESSION_PHASE_CLOSED
    assert phase("2026-12-07", 15, 29) == mc.SESSION_PHASE_CONTINUOUS_TRADING
    assert phase("2026-12-07", 15, 42) == mc.SESSION_PHASE_DERIVATIVES_CAS_ALIGNED
    assert phase("2026-12-07", 15, 46) == mc.SESSION_PHASE_CLOSED


def test_cash_auction_both_regimes():
    phase = lambda d, h, m: mc.classify_session_phase(at(d, h, m), symbol="X", is_derivative=False, cas_eligible=True)  # noqa: E731
    assert phase("2026-11-16", 15, 20) == mc.SESSION_PHASE_CAS_ORDER_ENTRY
    assert phase("2026-11-16", 15, 32) == mc.SESSION_PHASE_CAS_MATCHING
    assert phase("2026-12-07", 15, 20) == mc.SESSION_PHASE_CONTINUOUS_TRADING
    assert phase("2026-12-07", 15, 30) == mc.SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW
    assert phase("2026-12-07", 15, 33) == mc.SESSION_PHASE_CAS_ORDER_ENTRY
    assert phase("2026-12-07", 15, 38) == mc.SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY
    assert phase("2026-12-07", 15, 42) == mc.SESSION_PHASE_CAS_MATCHING
    assert phase("2026-12-07", 15, 47) == mc.SESSION_PHASE_CAS_POST
    non = mc.classify_session_phase(at("2026-12-07", 15, 25), symbol="X", is_derivative=False, cas_eligible=False)
    assert non == mc.SESSION_PHASE_CONTINUOUS_TRADING


def test_years_to_expiry_stops_at_1530_on_expiry_from_dec7():
    import fno_chain
    assert fno_chain.years_to_expiry(date(2026, 12, 8), at("2026-12-08", 15, 29)) > 0
    assert fno_chain.years_to_expiry(date(2026, 12, 8), at("2026-12-08", 15, 31)) == 0
    assert fno_chain.years_to_expiry(date(2026, 12, 1), at("2026-12-01", 15, 35)) > 0
    import hedge_strategies
    assert hedge_strategies._years_to_expiry(date(2026, 12, 8), at("2026-12-08", 15, 31)) == 0


def test_partner_and_recorder_windows_follow_the_date():
    import partner_broker_sync as z
    import tick_recorder
    assert z.CLOSE_MIN == 940
    assert z.close_min("2026-12-04") == 940 and z.close_min("2026-12-07") == 945
    assert z.close_min(at("2026-12-07", 10, 0)) == 945
    assert not z._complete("2026-12-07", at("2026-12-07", 15, 42)) and z._complete("2026-12-07", at("2026-12-07", 15, 45))
    assert z._complete("2026-12-04", at("2026-12-04", 15, 40))
    assert tick_recorder._end_min(at("2026-12-04", 15, 0)) == 941
    assert tick_recorder._end_min(at("2026-12-07", 15, 0)) == 946
