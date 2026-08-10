"""
[PENNY-TEST 2026-06-24] Unit tests for the PENNY_BROKERAGE_BYPASS flag.

Verifies that when the flag is True, calc_penny_costs() returns 0.0 so
P&L math reflects gross edge only (no Rs 20/order brokerage, no STT,
no GST eating into the Rs 2,500 bankroll).

When the flag is False (the default, live mode), the function must
return the full cost model unchanged from prior behavior.

[ROADMAP-5.2 2026-07-13] CONTRACT CHANGE. The bypass is now IGNORED whenever
PENNY_LIVE_TRADING is on -- it is a paper/test flag, and a live run with it set
would book ZERO brokerage into the real ledger. That matters here because
PENNY_LIVE_TRADING defaults to FALSE; production must explicitly opt in.
These tests pin the flag combination explicitly.
"""
import os
import sys

# Ensure the python-engine directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from penny_risk import calc_penny_costs  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_penny_flags():
    """Snapshot and restore BOTH flags around every test in this file.

    settings is a process-wide singleton. Without this, a test that flips
    PENNY_LIVE_TRADING leaks it into every test that runs afterwards -- which is
    precisely the class of bug roadmap 5.2 exists to close, and which this file
    reintroduced the first time it was updated for the new interlock (it broke
    7 unrelated tests in test_performance and test_penny_config through pure
    ordering).
    """
    from config import settings
    live = settings.PENNY_LIVE_TRADING
    bypass = settings.PENNY_BROKERAGE_BYPASS
    yield
    settings.PENNY_LIVE_TRADING = live
    settings.PENNY_BROKERAGE_BYPASS = bypass


def _set_bypass(value: bool, live: bool = False):
    """Toggle PENNY_BROKERAGE_BYPASS (and, explicitly, the live flag it is now
    interlocked against -- see the module docstring). The autouse fixture above
    puts both back afterwards."""
    from config import settings
    settings.PENNY_BROKERAGE_BYPASS = value
    settings.PENNY_LIVE_TRADING = live


def test_bypass_true_returns_zero():
    """When PENNY_BROKERAGE_BYPASS=True IN PAPER MODE, costs are 0.0 regardless
    of price/qty. (In live mode the bypass is refused -- see
    test_brokerage_bypass_honesty.py.)"""
    _set_bypass(True, live=False)
    try:
        # Cheap share, 1 share, MIS
        c = calc_penny_costs(entry_price=20.0, exit_price=20.5, shares=1, is_intraday=True)
        assert c == 0.0, f"expected 0.0, got {c}"
        # Large position, CNC
        c2 = calc_penny_costs(entry_price=50.0, exit_price=55.0, shares=10, is_intraday=False)
        assert c2 == 0.0, f"expected 0.0, got {c2}"
    finally:
        _set_bypass(False)


def test_bypass_false_returns_real_costs():
    """When PENNY_BROKERAGE_BYPASS=False, costs reflect the full Zerodha model."""
    _set_bypass(False)
    # 1 share, MIS, Rs 0.50 profit -- cost must be > 0 (brokerage + STT + GST)
    c = calc_penny_costs(entry_price=20.0, exit_price=20.5, shares=1, is_intraday=True)
    assert c > 0.0, f"expected positive cost, got {c}"
    # Sanity check: Rs 20 brokerage cap per order -> 2 sides x Rs 20 = Rs 40 max.
    # For tiny positions this caps, so upper bound is ~Rs 45 (incl. STT + GST).
    assert c < 50.0, f"cost looks unreasonably large: {c}"


def test_bypass_round_trip_math_consistent():
    """Gross PnL with bypass on (PAPER mode) equals net PnL (no cost erosion)."""
    _set_bypass(True, live=False)
    try:
        entry, exit, shares = 25.0, 26.0, 5
        gross = (exit - entry) * shares  # = Rs 5.00
        c = calc_penny_costs(entry, exit, shares, is_intraday=True)
        net = gross - c
        assert net == gross, f"with bypass on, net ({net}) should equal gross ({gross})"
    finally:
        _set_bypass(False)
