"""[WORKFLOW-J.7 2026-09-13] Tests for the Python
``execution_allowed`` helper in market_calendar.py.

The helper translates the bounded session phase into a
binary verdict on whether a broker order is allowed. The
Node mirror (``node-gateway/server/utils/market-hours.js``
``isExecutionAllowed``) MUST be bit-perfect with this
function; the golden-vector parity test in
``tests/unit/isExecutionAllowed.test.js`` enforces the
invariant from the Node side, and these tests pin the
Python contract from the Python side.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from pytz import timezone

from market_calendar import (
    _VALID_SESSION_PHASES,
    execution_allowed,
)


IST = timezone("Asia/Kolkata")


def _ist(year: int, month: int, day: int, hh: int, mm: int) -> datetime:
    """Build a UTC datetime that, when interpreted as the IST
    instant the caller asked for, lands on the right IST.
    IST = UTC + 5h30m, so UTC = IST - 5h30m.
    """
    return IST.localize(
        datetime(year, month, day, hh, mm)
    ).astimezone(timezone("UTC"))


# Pin a non-holiday trading day. Sep 7 2026 is a Monday with
# no holiday; Sep 14 is Ganesh Chaturthi (avoid).
MON = _ist(2026, 9, 7, 12, 0)


class TestExecutionAllowedClosedAndPremarket:
    """CLOSED and PRE_MARKET blocks. PRE_MARKET becomes
    allowed only with allow_pre_market=True.
    """

    def test_weekend_sunday_returns_closed_blocked(self):
        # Sep 6 2026 is a Sunday.
        sun = _ist(2026, 9, 6, 12, 0)
        verdict = execution_allowed(sun)
        assert verdict["allowed"] is False
        assert verdict["phase"] == "CLOSED"
        assert verdict["reason"] is not None

    def test_after_cash_close_returns_closed_blocked(self):
        verdict = execution_allowed(_ist(2026, 9, 7, 16, 0))
        assert verdict["allowed"] is False
        assert verdict["phase"] == "CLOSED"

    def test_pre_market_blocked_by_default(self):
        verdict = execution_allowed(_ist(2026, 9, 7, 9, 10))
        assert verdict["allowed"] is False
        assert verdict["phase"] == "PRE_MARKET"
        assert "pre-market" in verdict["reason"].lower()

    def test_pre_market_allowed_when_overridden(self):
        verdict = execution_allowed(
            _ist(2026, 9, 7, 9, 10), allow_pre_market=True,
        )
        assert verdict["allowed"] is True
        assert verdict["phase"] == "PRE_MARKET"
        assert verdict["reason"] is None


class TestExecutionAllowedContinuousTrading:
    """CONTINUOUS_TRADING is always allowed."""

    def test_open_9_15_allowed(self):
        verdict = execution_allowed(_ist(2026, 9, 7, 9, 15))
        assert verdict["allowed"] is True
        assert verdict["phase"] == "CONTINUOUS_TRADING"
        assert verdict["reason"] is None

    def test_mid_day_allowed(self):
        verdict = execution_allowed(_ist(2026, 9, 7, 12, 0))
        assert verdict["allowed"] is True
        assert verdict["phase"] == "CONTINUOUS_TRADING"

    def test_last_continuous_second_allowed(self):
        verdict = execution_allowed(_ist_sec(2026, 9, 7, 15, 14, 59))
        assert verdict["allowed"] is True
        assert verdict["phase"] == "CONTINUOUS_TRADING"


def _ist_sec(year: int, month: int, day: int, hh: int, mm: int, ss: int):
    """Build a UTC datetime from an IST instant with second
    granularity.
    """
    return IST.localize(
        datetime(year, month, day, hh, mm, ss)
    ).astimezone(timezone("UTC"))


class TestExecutionAllowedCasSubwindows:
    """All five CAS sub-windows block execution for cash."""

    def test_cas_reference_price_window_blocked(self):
        verdict = execution_allowed(
            _ist(2026, 9, 7, 15, 15),
            symbol="RELIANCE",
            cas_eligible=True,
        )
        assert verdict["allowed"] is False
        assert verdict["phase"] == "CAS_REFERENCE_PRICE_WINDOW"

    def test_cas_order_entry_blocked(self):
        verdict = execution_allowed(
            _ist(2026, 9, 7, 15, 20),
            symbol="RELIANCE",
            cas_eligible=True,
        )
        assert verdict["allowed"] is False
        assert verdict["phase"] == "CAS_ORDER_ENTRY"

    def test_cas_limit_entry_only_blocked(self):
        verdict = execution_allowed(
            _ist(2026, 9, 7, 15, 27),
            symbol="RELIANCE",
            cas_eligible=True,
        )
        assert verdict["allowed"] is False
        assert verdict["phase"] == "CAS_LIMIT_ENTRY_ONLY"

    def test_cas_matching_blocked(self):
        verdict = execution_allowed(
            _ist(2026, 9, 7, 15, 32),
            symbol="RELIANCE",
            cas_eligible=True,
        )
        assert verdict["allowed"] is False
        assert verdict["phase"] == "CAS_MATCHING"

    def test_cas_post_blocked_cash_only(self):
        verdict = execution_allowed(
            _ist(2026, 9, 7, 15, 50),
            symbol="RELIANCE",
            cas_eligible=True,
        )
        assert verdict["allowed"] is False
        assert verdict["phase"] == "CAS_POST"


class TestExecutionAllowedDerivatives:
    """Derivatives get DERIVATIVES_CAS_ALIGNED during the cash
    CAS window; the verdict is allowed.
    """

    def test_derivatives_cas_aligned_allowed_during_cash_matching(self):
        verdict = execution_allowed(
            _ist(2026, 9, 7, 15, 32),
            symbol="FUTIDX",
            is_derivative=True,
        )
        assert verdict["allowed"] is True
        assert verdict["phase"] == "DERIVATIVES_CAS_ALIGNED"

    def test_derivatives_39_minutes_allowed(self):
        verdict = execution_allowed(
            _ist(2026, 9, 7, 15, 39),
            symbol="FUTIDX",
            is_derivative=True,
        )
        assert verdict["allowed"] is True
        assert verdict["phase"] == "DERIVATIVES_CAS_ALIGNED"

    def test_derivatives_closed_after_15_40(self):
        verdict = execution_allowed(
            _ist(2026, 9, 7, 15, 50),
            symbol="FUTIDX",
            is_derivative=True,
        )
        assert verdict["allowed"] is False
        assert verdict["phase"] == "CLOSED"


class TestExecutionAllowedPurity:
    """The helper is pure / total: never raises, always
    returns the documented shape.
    """

    def test_none_observation_returns_unknown(self):
        verdict = execution_allowed(None)
        assert verdict["allowed"] is False
        assert verdict["phase"] == "UNKNOWN"

    def test_verdict_shape(self):
        verdict = execution_allowed(MON)
        assert set(verdict.keys()) == {"allowed", "phase", "reason"}
        assert isinstance(verdict["allowed"], bool)
        assert verdict["phase"] in _VALID_SESSION_PHASES
        assert verdict["reason"] is None or isinstance(
            verdict["reason"], str
        )

    def test_reason_is_none_when_allowed(self):
        verdict = execution_allowed(_ist(2026, 9, 7, 10, 0))
        assert verdict["allowed"] is True
        assert verdict["reason"] is None

    def test_reason_is_string_when_blocked(self):
        verdict = execution_allowed(_ist(2026, 9, 7, 16, 0))
        assert verdict["allowed"] is False
        assert isinstance(verdict["reason"], str)
        assert verdict["reason"]  # non-empty
