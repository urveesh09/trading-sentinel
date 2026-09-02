from datetime import date, datetime, timedelta
import re

import pytest
import pytz

from fno_chain import ChainSnapshot
from fno_models import Contract, ContractQuote
from hedge_analytics import VixRegimeReading
from hedge_formatters import (
    DISCLAIMER, MAX_TELEGRAM_CHARS, format_collar_recommendation,
    format_futures_hedge_size, format_no_recommendation,
    format_protective_put_alert, format_vix_hedge_alert,
)
from hedge_strategies import (
    collar_recommendation, futures_hedge_size, protective_put_alert,
)

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 9, 2, 11, 0))
EXPIRY = date(2026, 9, 29)
FORBIDDEN = re.compile(r"execute|buy\s+now|sell\s+now|guaranteed", re.I)


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


@pytest.mark.parametrize("formatter,plan", [
    (format_protective_put_alert, lambda: protective_put_alert(_snapshot(), 100, NOW)),
    (format_collar_recommendation, lambda: collar_recommendation(_snapshot(), 130, NOW)),
    (format_futures_hedge_size, lambda: futures_hedge_size(
        _snapshot(), 4_000_000, hedge_ratio=.5, now_ist=NOW,
    )),
])
def test_plan_messages_are_safe_current_and_bounded(formatter, plan):
    value = plan()
    assert value is not None
    text = formatter(value)
    assert DISCLAIMER in text
    assert len(text) <= MAX_TELEGRAM_CHARS
    assert not FORBIDDEN.search(text)
    assert "Live as of:" in text
    assert EXPIRY.isoformat() in text
    assert "bid" in text and "ask" in text
    assert "Review" in text


def test_protective_message_makes_partial_coverage_explicit():
    text = format_protective_put_alert(protective_put_alert(_snapshot(), 100, NOW))
    assert "PARTIAL COVERAGE" in text
    assert "65/100" in text


def test_vix_message_is_informational_and_rejects_automatic_action():
    reading = VixRegimeReading(
        "ELEVATED", 20.0, .15, 1.2, True,
        "Review protection; no automatic action", True,
    )
    text = format_vix_hedge_alert(reading, as_of=NOW)
    assert "informational only" in text
    assert not FORBIDDEN.search(text)
    with pytest.raises(ValueError, match="automatic"):
        format_vix_hedge_alert(VixRegimeReading(
            "PANIC", 25.0, .25, 2.5, True, "bad", True, True,
        ), as_of=NOW)


def test_no_recommendation_sanitizes_untrusted_reason_and_preserves_disclaimer():
    text = format_no_recommendation(
        "nifty", "BUY NOW\n" + "x" * 10_000, as_of=NOW,
    )
    assert "[redacted]" in text
    assert not FORBIDDEN.search(text)
    assert len(text) <= MAX_TELEGRAM_CHARS
    assert text.endswith(DISCLAIMER)


def test_formatter_rejects_missing_live_contract_identity():
    plan = protective_put_alert(_snapshot(), 65, NOW)
    object.__setattr__(plan.legs[0], "tradingsymbol", "")
    with pytest.raises(ValueError, match="identity"):
        format_protective_put_alert(plan)
