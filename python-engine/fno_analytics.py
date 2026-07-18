"""
[PARTNER-TIPS 2026-07-18] Pure options-chain analytics (WS3).

Everything here is computed from data the engine ALREADY fetches (the
wide chain snapshot + daily closes); this module just does the math the
liquidity gates never needed: PCR, max pain, ATM IV, IV-vs-realized-vol
read, OI walls, futures OI buildup classification, expiry/theta notes.

Pure: dataclasses/pandas in, floats/strings out. No I/O, no Kite, no DB
(mirrors fno_engine_mom's discipline; storage lives in fno_oi_store).
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

import options_math
from config import settings
from fno_chain import RISK_FREE_RATE, ChainSnapshot, years_to_expiry

logger = structlog.get_logger()

# Brent IV solves get numerically unstable as T->0; inside this window on
# expiry day we report IV as unavailable rather than as a wrong number.
EXPIRY_IV_BLACKOUT_MIN = 90


def compute_pcr(snap: ChainSnapshot) -> Optional[float]:
    """Put-call ratio on OPEN INTEREST over the snapshot's strike window.
    None when the call side carries no OI (a 0-divide would be a lie,
    not an infinity worth reporting)."""
    put_oi = sum(q.oi for (_, ot), q in snap.quotes.items() if ot == "PE")
    call_oi = sum(q.oi for (_, ot), q in snap.quotes.items() if ot == "CE")
    if call_oi <= 0:
        return None
    return put_oi / call_oi


def compute_max_pain(snap: ChainSnapshot) -> Optional[float]:
    """Strike minimizing total option-writer payout at expiry settlement.

    For candidate settlement S: payout = sum_CE OI*(S-K)+ + sum_PE OI*(K-S)+.
    Standard expiry-week reference level; only meaningful when the window
    actually carries OI."""
    strikes = sorted({k for (k, _) in snap.quotes})
    if not strikes:
        return None
    ce = {k: q.oi for (k, ot), q in snap.quotes.items() if ot == "CE"}
    pe = {k: q.oi for (k, ot), q in snap.quotes.items() if ot == "PE"}
    if sum(ce.values()) + sum(pe.values()) <= 0:
        return None
    best_strike, best_pain = None, float("inf")
    for s in strikes:
        pain = sum(oi * max(0.0, s - k) for k, oi in ce.items()) + \
               sum(oi * max(0.0, k - s) for k, oi in pe.items())
        if pain < best_pain:
            best_strike, best_pain = s, pain
    return best_strike


def atm_iv(snap: ChainSnapshot, now_ist: datetime) -> Optional[float]:
    """Mean of the ATM CE/PE Black-76 IVs (needs both legs two-sided so
    one stale leg can't skew the read). None near expiry cutoff."""
    T = years_to_expiry(snap.expiry, now_ist)
    if snap.expiry == now_ist.date():
        minutes_left = T * 365.0 * 24 * 60
        if minutes_left <= EXPIRY_IV_BLACKOUT_MIN:
            return None
    if T <= 0 or snap.forward <= 0:
        return None
    strikes = sorted({k for (k, _) in snap.quotes})
    if not strikes:
        return None
    atm = min(strikes, key=lambda k: abs(k - snap.forward))
    ivs: List[float] = []
    for ot in ("CE", "PE"):
        q = snap.quotes.get((atm, ot))
        if q is None or not q.two_sided or q.mid <= 0:
            continue
        iv = options_math.implied_vol(
            q.mid, snap.forward, atm, T, RISK_FREE_RATE, ot == "CE"
        )
        if iv is not None:
            ivs.append(iv)
    if not ivs:
        return None
    return sum(ivs) / len(ivs)


def realized_vol_20d(daily_closes) -> Optional[float]:
    """20-day annualized realized vol from a daily close series. Same
    math as regime.RegimeEngine._calc_realized_vol, but returns None
    (instead of a safe fallback) on short history -- a tips message must
    say "unavailable", not quietly print the normal baseline."""
    closes = np.asarray(list(daily_closes), dtype=float)
    if len(closes) < 21:
        return None
    log_returns = np.diff(np.log(closes))
    if len(log_returns) < 20:
        return None
    rv = float(np.std(log_returns[-20:], ddof=0) * (252 ** 0.5))
    return rv if rv > 0 else None


def iv_rv_read(iv: Optional[float], rv: Optional[float]) -> str:
    """Premium rich/cheap read for an option BUYER. RICH = IV well above
    realized (long premium fights gravity), CHEAP = IV below realized
    (buyer-friendly), FAIR between, UNKNOWN when either leg is missing."""
    if iv is None or rv is None or rv <= 0:
        return "UNKNOWN"
    ratio = iv / rv
    if ratio >= settings.PARTNER_IV_RICH_RATIO:
        return "RICH"
    if ratio <= settings.PARTNER_IV_CHEAP_RATIO:
        return "CHEAP"
    return "FAIR"


def oi_walls(snap: ChainSnapshot) -> Tuple[Optional[float], Optional[float]]:
    """(support, resistance): the max-PE-OI strike at/below the forward
    and the max-CE-OI strike at/above it. Heavy writer concentration
    behaves as a magnet/barrier intraday -- exactly the level an index
    option buyer wants marked on their chart."""
    support, sup_oi = None, 0
    resistance, res_oi = None, 0
    for (strike, ot), q in snap.quotes.items():
        if ot == "PE" and strike <= snap.forward and q.oi > sup_oi:
            support, sup_oi = strike, q.oi
        if ot == "CE" and strike >= snap.forward and q.oi > res_oi:
            resistance, res_oi = strike, q.oi
    return support, resistance


def classify_buildup(px_chg: float, oi_chg: float) -> str:
    """Classic futures price x OI 4-way. Zero on either axis reports
    NEUTRAL rather than forcing a quadrant."""
    if px_chg == 0 or oi_chg == 0:
        return "NEUTRAL"
    if px_chg > 0:
        return "LONG_BUILDUP" if oi_chg > 0 else "SHORT_COVERING"
    return "SHORT_BUILDUP" if oi_chg > 0 else "LONG_UNWINDING"


def strike_oi_deltas(
    snap: ChainSnapshot, baseline: Dict[Tuple[float, str], int],
) -> Dict[Tuple[float, str], int]:
    """Per-(strike, opt_type) OI change vs a stored baseline (usually the
    open snapshot). Only strikes present in BOTH sides are diffed --
    a strike that entered the window because the forward moved is not an
    OI change, it's a window shift."""
    out: Dict[Tuple[float, str], int] = {}
    for key, q in snap.quotes.items():
        if key in baseline:
            out[key] = q.oi - baseline[key]
    return out


def expiry_note(expiry: Optional[date], today: date, iv: Optional[float]) -> str:
    """Human DTE note with a theta warning where a buyer needs one."""
    if expiry is None:
        return ""
    dte = (expiry - today).days
    if dte < 0:
        return ""
    if dte == 0:
        return "EXPIRY TODAY — theta burns premium by the hour; intraday scalps only"
    if dte == 1:
        base = "expiry tomorrow — overnight theta is brutal on long premium"
        if iv is not None and iv > 0.15:
            base += "; elevated IV can crush on top"
        return base
    return f"{dte}d to expiry"
