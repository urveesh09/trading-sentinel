"""
[FNO-MATH-TESTS 2026-07-10] Exhaustive unit tests for options_math
(spec §6.3). Pure math -- every assertion is checkable by hand.
"""
import math

import pytest

from options_math import (
    IV_HI, IV_LO, black76_price, delta, gamma, implied_vol, norm_cdf,
    theta, vega, _brentq,
)

F, K, T, R = 25000.0, 25000.0, 7.0 / 365.0, 0.065


# ---------------------------------------------------------------------------
# pricing
# ---------------------------------------------------------------------------

def test_known_black76_value():
    # F=K=100, T=1, vol=0.2, r=0: C = 100*(2*N(0.1)-1) = 7.9656
    c = black76_price(100.0, 100.0, 1.0, 0.2, 0.0, is_call=True)
    assert c == pytest.approx(7.9656, abs=1e-3)


def test_put_call_parity():
    # C - P = e^(-rT) * (F - K), exact under Black-76
    for k in (24500.0, 25000.0, 25500.0):
        c = black76_price(F, k, T, 0.15, R, is_call=True)
        p = black76_price(F, k, T, 0.15, R, is_call=False)
        assert c - p == pytest.approx(math.exp(-R * T) * (F - k), abs=1e-9)


def test_price_monotone_in_vol():
    prices = [black76_price(F, K, T, v, R, True) for v in (0.10, 0.15, 0.25, 0.50)]
    assert prices == sorted(prices)
    assert prices[0] > 0


def test_degenerate_inputs_collapse_to_intrinsic():
    assert black76_price(F, 24000.0, 0.0, 0.15, R, True) == pytest.approx(1000.0)
    assert black76_price(F, 26000.0, T, 0.0, R, False) == pytest.approx(
        math.exp(-R * T) * 1000.0
    )
    assert black76_price(F, 26000.0, 0.0, 0.15, R, True) == 0.0


def test_nonpositive_forward_or_strike_raises():
    with pytest.raises(ValueError):
        black76_price(0.0, K, T, 0.15, R, True)
    with pytest.raises(ValueError):
        black76_price(F, -1.0, T, 0.15, R, True)


def test_norm_cdf_symmetry():
    assert norm_cdf(0.0) == pytest.approx(0.5)
    assert norm_cdf(1.0) + norm_cdf(-1.0) == pytest.approx(1.0)
    assert norm_cdf(1.0) == pytest.approx(0.841345, abs=1e-5)


# ---------------------------------------------------------------------------
# implied vol
# ---------------------------------------------------------------------------

def test_iv_round_trip():
    for true_vol in (0.08, 0.15, 0.40, 1.20):
        px = black76_price(F, K, T, true_vol, R, True)
        iv = implied_vol(px, F, K, T, R, True)
        assert iv is not None
        assert iv == pytest.approx(true_vol, abs=1e-5)


def test_iv_round_trip_put():
    px = black76_price(F, 25200.0, T, 0.18, R, False)
    iv = implied_vol(px, F, 25200.0, T, R, False)
    assert iv == pytest.approx(0.18, abs=1e-5)


def test_iv_below_intrinsic_returns_none_not_zero():
    """Documented failure return (spec §6.3): None, never an exception,
    never a silent 0.0. A premium below intrinsic is a freak print."""
    intrinsic = math.exp(-R * T) * 500.0
    iv = implied_vol(intrinsic * 0.5, F, 24500.0, T, R, True)
    assert iv is None


def test_iv_above_ceiling_returns_none():
    # Price beyond the vol=3.0 bracket top cannot solve.
    too_rich = black76_price(F, K, T, IV_HI, R, True) * 1.5
    assert implied_vol(too_rich, F, K, T, R, True) is None


def test_iv_degenerate_inputs_return_none():
    assert implied_vol(0.0, F, K, T, R, True) is None
    assert implied_vol(-5.0, F, K, T, R, True) is None
    assert implied_vol(100.0, F, K, 0.0, R, True) is None
    assert implied_vol(100.0, 0.0, K, T, R, True) is None


def test_brentq_unbracketed_returns_none():
    assert _brentq(lambda x: x * x + 1.0, IV_LO, IV_HI) is None


def test_brentq_endpoint_roots():
    assert _brentq(lambda x: x - IV_LO, IV_LO, IV_HI) == pytest.approx(IV_LO)
    assert _brentq(lambda x: x - IV_HI, IV_LO, IV_HI) == pytest.approx(IV_HI)


# ---------------------------------------------------------------------------
# greeks
# ---------------------------------------------------------------------------

def test_atm_call_delta_near_half():
    d = delta(F, K, T, 0.15, R, True)
    assert 0.45 < d < 0.56


def test_put_call_delta_parity():
    # call_delta - put_delta = e^(-rT), exact under Black-76
    dc = delta(F, K, T, 0.15, R, True)
    dp = delta(F, K, T, 0.15, R, False)
    assert dc - dp == pytest.approx(math.exp(-R * T), abs=1e-9)


def test_itm_call_delta_higher_than_otm():
    itm = delta(F, 24800.0, T, 0.12, R, True)
    otm = delta(F, 25200.0, T, 0.12, R, True)
    assert itm > 0.55 > otm


def test_expired_delta_is_binary():
    assert delta(25100.0, 25000.0, 0.0, 0.15, R, True) == 1.0
    assert delta(24900.0, 25000.0, 0.0, 0.15, R, True) == 0.0
    assert delta(24900.0, 25000.0, 0.0, 0.15, R, False) == -1.0
    assert delta(25100.0, 25000.0, 0.0, 0.15, R, False) == 0.0


def test_gamma_positive_and_peaks_atm():
    g_atm = gamma(F, K, T, 0.15, R)
    g_wing = gamma(F, 25500.0, T, 0.15, R)
    assert g_atm > g_wing > 0


def test_vega_positive_expired_zero():
    assert vega(F, K, T, 0.15, R) > 0
    assert vega(F, K, 0.0, 0.15, R) == 0.0
    assert gamma(F, K, 0.0, 0.15, R) == 0.0


def test_theta_negative_for_long_options():
    """The number the §8.5 time stop exists to outrun."""
    assert theta(F, K, T, 0.15, R, True) < 0
    assert theta(F, K, T, 0.15, R, False) < 0
    assert theta(F, K, 0.0, 0.15, R, True) == 0.0


def test_theta_magnitude_sane_for_weekly_atm():
    # ATM weekly NIFTY at 15% IV: premium ~= 260, ~7 days to run it off.
    px = black76_price(F, K, T, 0.15, R, True)
    th = theta(F, K, T, 0.15, R, True)
    assert abs(th) < px  # cannot lose more than the premium per day
    assert abs(th) > px / 30  # but a weekly decays fast
