"""
[FNO-CHAIN-TESTS 2026-07-10] Chain snapshot math (spec §6.2): forward
handling, parity cross-check, delta-based strike selection with the
never-OTM rule (§8.3).
"""
from datetime import date, datetime

import pytest
import pytz

import options_math
from fno_chain import (
    RISK_FREE_RATE, ChainSnapshot, _parity_forward, select_strike_by_delta,
    years_to_expiry,
)
from fno_models import Contract, ContractQuote, OptionType

IST = pytz.timezone("Asia/Kolkata")
EXPIRY = date(2026, 7, 14)
NOW = IST.localize(datetime(2026, 7, 10, 10, 0))
F = 25000.0


def _quote(strike: float, opt_type: str, vol: float = 0.15, half_spread: float = 0.5):
    T = years_to_expiry(EXPIRY, NOW)
    mid = options_math.black76_price(F, strike, T, vol, RISK_FREE_RATE, opt_type == "CE")
    c = Contract(
        token=int(strike) * 10 + (1 if opt_type == "CE" else 2),
        tradingsymbol=f"NIFTY{int(strike)}{opt_type}",
        name="NIFTY", expiry=EXPIRY, strike=strike,
        instrument_type=opt_type, lot_size=75,
    )
    return ContractQuote(
        contract=c, bid=mid - half_spread, ask=mid + half_spread, ltp=mid,
        oi=10000, volume=5000, last_trade_time=NOW,
    )


def _snapshot(strikes=(24800.0, 24900.0, 25000.0, 25100.0, 25200.0)) -> ChainSnapshot:
    quotes = {}
    for k in strikes:
        for ot in ("CE", "PE"):
            quotes[(k, ot)] = _quote(k, ot)
    return ChainSnapshot(
        taken_at=NOW, expiry=EXPIRY, forward=F, parity_forward=None,
        lot_size=75, fut_quote=None, quotes=quotes,
    )


# ---------------------------------------------------------------------------
# time to expiry
# ---------------------------------------------------------------------------

def test_years_to_expiry_positive_before_cutoff():
    T = years_to_expiry(EXPIRY, NOW)
    # 4 days + 5.5 hours, as a fraction of a year
    assert T == pytest.approx((4 * 24 + 5.5) * 3600 / (365 * 24 * 3600), rel=1e-6)


def test_years_to_expiry_zero_after_cutoff():
    after_close = IST.localize(datetime(2026, 7, 14, 15, 45))
    assert years_to_expiry(EXPIRY, after_close) == 0.0


# ---------------------------------------------------------------------------
# parity cross-check
# ---------------------------------------------------------------------------

def test_parity_forward_recovers_futures_price():
    snap = _snapshot()
    T = years_to_expiry(EXPIRY, NOW)
    pf = _parity_forward(snap.quotes, 25000.0, T)
    # Black-76 prices are parity-consistent by construction, so the
    # recovered forward is exact (mid spread is symmetric and cancels).
    assert pf == pytest.approx(F, abs=1e-6)


def test_parity_forward_none_when_one_sided():
    snap = _snapshot()
    q = snap.quotes[(25000.0, "PE")]
    q.bid = 0.0
    T = years_to_expiry(EXPIRY, NOW)
    assert _parity_forward(snap.quotes, 25000.0, T) is None


# ---------------------------------------------------------------------------
# §8.3 strike selection
# ---------------------------------------------------------------------------

def test_ce_selection_picks_atm_or_itm_closest_to_target():
    picked = select_strike_by_delta(_snapshot(), OptionType.CE, NOW)
    assert picked is not None
    quote, iv, d = picked
    # At this tenor (4d 5.5h) ATM 25000 has delta ~0.503 (dist 0.047),
    # narrowly beating 24900 at ~0.600 (dist 0.050).
    assert quote.contract.strike == 25000.0
    assert iv == pytest.approx(0.15, abs=0.01)
    assert 0.45 < d < 0.60


def test_pe_selection_picks_slightly_itm():
    picked = select_strike_by_delta(_snapshot(), OptionType.PE, NOW)
    assert picked is not None
    quote, iv, d = picked
    # for a put, ITM = strike above the forward
    assert quote.contract.strike == 25100.0
    assert -0.65 < d < -0.5


def test_never_otm_even_when_delta_is_closer():
    """Target 0.40 would be best matched by an OTM strike; the rule
    forbids it -- the nearest ATM-or-ITM strike wins instead."""
    picked = select_strike_by_delta(_snapshot(), OptionType.CE, NOW, target_delta=0.40)
    assert picked is not None
    quote, _, _ = picked
    assert quote.contract.strike <= F * 1.001


def test_returns_none_when_no_quote_solves():
    snap = _snapshot()
    for q in snap.quotes.values():
        q.bid = 0.0
        q.ask = 0.0
        q.ltp = 0.0
    assert select_strike_by_delta(snap, OptionType.CE, NOW) is None
