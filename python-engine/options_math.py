"""
[FNO-MATH 2026-07-10] Option pricing math for the F&O subsystem (spec §6.3).

Pure and dependency-free: stdlib `math` only. No I/O, no config import, no
Kite. Exhaustively unit-tested in tests/test_options_math.py.

Everything prices on the FORWARD (Black-76), never on spot: using spot for
index options quietly biases every IV and every delta the module computes
(spec §6.2). The forward comes from the front-month futures LTP upstream.

Public API:
  black76_price(F, K, T, vol, r, is_call)  -> float
  implied_vol(price, F, K, T, r, is_call)  -> Optional[float]  (None on failure,
                                              never an exception, never 0.0)
  delta(F, K, T, vol, r, is_call)          -> float
  gamma(F, K, T, vol, r)                   -> float
  theta(F, K, T, vol, r, is_call)          -> float  (per calendar day)
  vega(F, K, T, vol, r)                    -> float  (per 1.00 of vol)

Conventions:
  F, K   in index points; T in YEARS; vol annualized (0.15 = 15%);
  r continuously-compounded risk-free rate (only discounts the premium
  in Black-76 -- a wrong r moves prices by basis points, not rupees).
"""
from __future__ import annotations

import math
from typing import Callable, Optional

# Brent bracket for the IV solve (spec §6.3). NSE weeklies live well
# inside this; anything outside is bad data, not a real vol.
IV_LO = 0.01
IV_HI = 3.0
_BRENT_TOL = 1e-8
_BRENT_MAX_ITER = 100


def norm_cdf(x: float) -> float:
    """Standard normal CDF via math.erf (double precision, no tables)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _d1_d2(F: float, K: float, T: float, vol: float) -> tuple[float, float]:
    sig_sqrt_t = vol * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * vol * vol * T) / sig_sqrt_t
    return d1, d1 - sig_sqrt_t


def black76_price(
    F: float, K: float, T: float, vol: float, r: float, is_call: bool,
) -> float:
    """Black-76 option price on forward F.

    Degenerate inputs (T<=0 or vol<=0) collapse to discounted intrinsic --
    the correct limit, and it keeps the IV solver's bracket endpoints
    well-defined instead of raising.
    """
    if F <= 0 or K <= 0:
        raise ValueError(f"F and K must be positive (F={F}, K={K})")
    df = math.exp(-r * T) if T > 0 else 1.0
    if T <= 0 or vol <= 0:
        intrinsic = (F - K) if is_call else (K - F)
        return df * max(0.0, intrinsic)
    d1, d2 = _d1_d2(F, K, T, vol)
    if is_call:
        return df * (F * norm_cdf(d1) - K * norm_cdf(d2))
    return df * (K * norm_cdf(-d2) - F * norm_cdf(-d1))


def _brentq(
    f: Callable[[float], float], a: float, b: float,
    tol: float = _BRENT_TOL, max_iter: int = _BRENT_MAX_ITER,
) -> Optional[float]:
    """Brent's method (inverse-quadratic / secant / bisection hybrid).

    Returns None if the root is not bracketed or iterations run out --
    the caller treats None as "no implied vol", never as 0.0.
    """
    fa, fb = f(a), f(b)
    if fa * fb > 0:
        return None
    if fa == 0.0:
        return a
    if fb == 0.0:
        return b
    if abs(fa) < abs(fb):
        a, b, fa, fb = b, a, fb, fa
    c, fc = a, fa
    mflag = True
    d = 0.0
    for _ in range(max_iter):
        if fb == 0.0 or abs(b - a) < tol:
            return b
        if fa != fc and fb != fc:
            # inverse quadratic interpolation
            s = (
                a * fb * fc / ((fa - fb) * (fa - fc))
                + b * fa * fc / ((fb - fa) * (fb - fc))
                + c * fa * fb / ((fc - fa) * (fc - fb))
            )
        else:
            # secant
            s = b - fb * (b - a) / (fb - fa)
        cond = (
            not ((3 * a + b) / 4 < s < b or b < s < (3 * a + b) / 4)
            or (mflag and abs(s - b) >= abs(b - c) / 2)
            or (not mflag and abs(s - b) >= abs(c - d) / 2)
            or (mflag and abs(b - c) < tol)
            or (not mflag and abs(c - d) < tol)
        )
        if cond:
            s = (a + b) / 2
            mflag = True
        else:
            mflag = False
        fs = f(s)
        d, c, fc = c, b, fb
        if fa * fs < 0:
            b, fb = s, fs
        else:
            a, fa = s, fs
        if abs(fa) < abs(fb):
            a, b, fa, fb = b, a, fb, fa
    return b if abs(fb) < 1e-6 else None


def implied_vol(
    price: float, F: float, K: float, T: float, r: float, is_call: bool,
) -> Optional[float]:
    """Implied volatility by Brent's method, bracketed [0.01, 3.0].

    Documented failure return: None. Never raises on bad market data,
    never silently returns 0.0 (spec §6.3). Failure cases:
      - non-positive inputs / expired contract
      - price below discounted intrinsic (arbitrage or freak print)
      - price above the vol=3.0 ceiling
    """
    if price <= 0 or F <= 0 or K <= 0 or T <= 0:
        return None
    try:
        f = lambda v: black76_price(F, K, T, v, r, is_call) - price
        return _brentq(f, IV_LO, IV_HI)
    except (ValueError, OverflowError):
        return None


def delta(F: float, K: float, T: float, vol: float, r: float, is_call: bool) -> float:
    """Black-76 forward delta. Converts an underlying-point stop into a
    premium stop (spec §8.4) and drives strike selection (§8.3)."""
    if T <= 0 or vol <= 0:
        intrinsic_itm = F > K if is_call else F < K
        base = 1.0 if intrinsic_itm else 0.0
        return base if is_call else -base
    df = math.exp(-r * T)
    d1, _ = _d1_d2(F, K, T, vol)
    return df * norm_cdf(d1) if is_call else df * (norm_cdf(d1) - 1.0)


def gamma(F: float, K: float, T: float, vol: float, r: float) -> float:
    if T <= 0 or vol <= 0:
        return 0.0
    df = math.exp(-r * T)
    d1, _ = _d1_d2(F, K, T, vol)
    return df * norm_pdf(d1) / (F * vol * math.sqrt(T))


def vega(F: float, K: float, T: float, vol: float, r: float) -> float:
    """Per 1.00 change in vol (divide by 100 for per-vol-point)."""
    if T <= 0 or vol <= 0:
        return 0.0
    df = math.exp(-r * T)
    d1, _ = _d1_d2(F, K, T, vol)
    return df * F * norm_pdf(d1) * math.sqrt(T)


def theta(F: float, K: float, T: float, vol: float, r: float, is_call: bool) -> float:
    """Black-76 theta, PER CALENDAR DAY (annual / 365). Negative for a
    long option -- the number the time stop exists to outrun (§8.5)."""
    if T <= 0 or vol <= 0:
        return 0.0
    df = math.exp(-r * T)
    d1, d2 = _d1_d2(F, K, T, vol)
    common = -df * F * norm_pdf(d1) * vol / (2.0 * math.sqrt(T))
    if is_call:
        annual = common - r * K * df * norm_cdf(d2) + r * F * df * norm_cdf(d1)
    else:
        annual = common + r * K * df * norm_cdf(-d2) - r * F * df * norm_cdf(-d1)
    return annual / 365.0
