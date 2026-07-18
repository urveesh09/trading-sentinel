"""
[PARTNER-TIPS-TESTS 2026-07-18] Pure chain analytics (plan WS3):
hand-computed PCR/max-pain on a tiny synthetic chain, the buildup
truth table, IV/RV read boundaries, realized vol against a known
series, and expiry-note edges.
"""
import math
from datetime import date, datetime

import numpy as np
import pytest
import pytz

import fno_analytics as fa
import options_math
from fno_chain import RISK_FREE_RATE, ChainSnapshot, years_to_expiry
from fno_models import Contract, ContractQuote

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 7, 20, 11, 0))
EXPIRY = date(2026, 7, 23)
F = 25000.0


def _quote(strike, ot, oi, vol=0.15, half_spread=0.5):
    T = years_to_expiry(EXPIRY, NOW)
    mid = options_math.black76_price(F, strike, T, vol, RISK_FREE_RATE, ot == "CE")
    c = Contract(
        token=int(strike) * 10 + (1 if ot == "CE" else 2),
        tradingsymbol=f"NIFTY{int(strike)}{ot}",
        name="NIFTY", expiry=EXPIRY, strike=strike,
        instrument_type=ot, lot_size=75,
    )
    return ContractQuote(
        contract=c, bid=mid - half_spread, ask=mid + half_spread, ltp=mid,
        oi=oi, volume=5000, last_trade_time=NOW,
    )


def _snap(oi_map, fut_oi=100000, now=NOW, expiry=EXPIRY):
    """oi_map: {(strike, 'CE'|'PE'): oi}"""
    quotes = {k: _quote(k[0], k[1], oi) for k, oi in oi_map.items()}
    fut_c = Contract(
        token=900, tradingsymbol="NIFTYFUT", name="NIFTY", expiry=expiry,
        strike=0.0, instrument_type="FUT", lot_size=75,
    )
    fut_q = ContractQuote(contract=fut_c, bid=F - 1, ask=F + 1, ltp=F, oi=fut_oi)
    return ChainSnapshot(
        taken_at=now, expiry=expiry, forward=F, parity_forward=None,
        lot_size=75, fut_quote=fut_q, quotes=quotes,
    )


# ---------------------------------------------------------------------------
# PCR
# ---------------------------------------------------------------------------

def test_pcr_hand_computed():
    snap = _snap({
        (24900.0, "CE"): 1000, (24900.0, "PE"): 3000,
        (25000.0, "CE"): 2000, (25000.0, "PE"): 1500,
    })
    # (3000+1500) / (1000+2000) = 1.5
    assert fa.compute_pcr(snap) == pytest.approx(1.5)


def test_pcr_none_when_call_side_empty():
    snap = _snap({(25000.0, "CE"): 0, (25000.0, "PE"): 3000})
    assert fa.compute_pcr(snap) is None


# ---------------------------------------------------------------------------
# max pain
# ---------------------------------------------------------------------------

def test_max_pain_hand_computed():
    # CE OI rises with strike, PE OI falls with strike:
    #   S=24900: CE 0;                          PE 100*2000 + 200*1000 = 400k
    #   S=25000: CE 100*1000 = 100k;            PE 100*1000        = 100k
    #   S=25100: CE 200*1000 + 100*2000 = 400k; PE 0
    # 25000 minimizes total writer payout (200k vs 400k at the wings).
    snap = _snap({
        (24900.0, "CE"): 1000, (24900.0, "PE"): 3000,
        (25000.0, "CE"): 2000, (25000.0, "PE"): 2000,
        (25100.0, "CE"): 3000, (25100.0, "PE"): 1000,
    })
    assert fa.compute_max_pain(snap) == 25000.0


def test_max_pain_none_without_oi():
    snap = _snap({(25000.0, "CE"): 0, (25000.0, "PE"): 0})
    assert fa.compute_max_pain(snap) is None


# ---------------------------------------------------------------------------
# ATM IV
# ---------------------------------------------------------------------------

def test_atm_iv_recovers_the_pricing_vol():
    snap = _snap({(25000.0, "CE"): 5000, (25000.0, "PE"): 5000})
    iv = fa.atm_iv(snap, NOW)
    # quotes were priced at vol=0.15 with a small spread; the mid-implied
    # IV must come back near it
    assert iv == pytest.approx(0.15, abs=0.02)


def test_atm_iv_blackout_near_expiry_cutoff():
    # 14:30 on expiry day = 60 min to the 15:30 settlement -> inside the
    # 90-min Brent blackout window
    late = IST.localize(datetime(2026, 7, 23, 14, 30))
    snap = _snap({(25000.0, "CE"): 5000, (25000.0, "PE"): 5000},
                 now=late, expiry=date(2026, 7, 23))
    assert fa.atm_iv(snap, late) is None


def test_atm_iv_none_on_one_sided_book():
    snap = _snap({(25000.0, "CE"): 5000, (25000.0, "PE"): 5000})
    for q in snap.quotes.values():
        q.bid = 0.0
    assert fa.atm_iv(snap, NOW) is None


# ---------------------------------------------------------------------------
# realized vol + IV/RV read
# ---------------------------------------------------------------------------

def test_realized_vol_20d_known_series():
    # alternating +1%/-1% log-ish moves -> std of log returns ~0.01
    closes = [100.0]
    for i in range(30):
        closes.append(closes[-1] * (1.01 if i % 2 == 0 else 1 / 1.01))
    rv = fa.realized_vol_20d(closes)
    log_r = np.diff(np.log(np.asarray(closes)))
    expected = float(np.std(log_r[-20:], ddof=0) * math.sqrt(252))
    assert rv == pytest.approx(expected)
    assert 0.10 < rv < 0.25


def test_realized_vol_short_history_is_none_not_fallback():
    # regime's version falls back to RV_NORMAL_ANNUAL; the tips version
    # must say "unavailable" instead of quietly printing the baseline
    assert fa.realized_vol_20d([100.0] * 10) is None


def test_realized_vol_flat_series_is_none():
    assert fa.realized_vol_20d([100.0] * 30) is None


def test_iv_rv_read_bands():
    # clearly inside each band (exact boundary is float-representation
    # dependent and not worth pinning)
    assert fa.iv_rv_read(0.26, 0.20) == "RICH"     # ratio 1.30 >= 1.25
    assert fa.iv_rv_read(0.15, 0.20) == "CHEAP"    # ratio 0.75 <= 0.80
    assert fa.iv_rv_read(0.20, 0.20) == "FAIR"
    assert fa.iv_rv_read(None, 0.20) == "UNKNOWN"
    assert fa.iv_rv_read(0.20, None) == "UNKNOWN"
    assert fa.iv_rv_read(0.20, 0.0) == "UNKNOWN"


# ---------------------------------------------------------------------------
# OI walls / buildup / deltas
# ---------------------------------------------------------------------------

def test_oi_walls():
    snap = _snap({
        (24800.0, "PE"): 9000, (24900.0, "PE"): 4000,   # support = 24800
        (25100.0, "CE"): 3000, (25200.0, "CE"): 8000,   # resistance = 25200
        (25100.0, "PE"): 100,   # PE above forward: not support
        (24900.0, "CE"): 9999,  # CE below forward: not resistance
    })
    support, resistance = fa.oi_walls(snap)
    assert support == 24800.0
    assert resistance == 25200.0


def test_classify_buildup_truth_table():
    assert fa.classify_buildup(+10, +100) == "LONG_BUILDUP"
    assert fa.classify_buildup(+10, -100) == "SHORT_COVERING"
    assert fa.classify_buildup(-10, +100) == "SHORT_BUILDUP"
    assert fa.classify_buildup(-10, -100) == "LONG_UNWINDING"
    assert fa.classify_buildup(0, +100) == "NEUTRAL"
    assert fa.classify_buildup(+10, 0) == "NEUTRAL"


def test_strike_oi_deltas_ignores_window_shift():
    snap = _snap({(25000.0, "CE"): 7000, (25100.0, "CE"): 500})
    baseline = {(25000.0, "CE"): 5000}   # 25100 entered the window later
    deltas = fa.strike_oi_deltas(snap, baseline)
    assert deltas == {(25000.0, "CE"): 2000}


# ---------------------------------------------------------------------------
# expiry note
# ---------------------------------------------------------------------------

def test_expiry_note_edges():
    today = date(2026, 7, 23)
    assert "EXPIRY TODAY" in fa.expiry_note(today, today, None)
    note = fa.expiry_note(date(2026, 7, 24), today, 0.20)
    assert "expiry tomorrow" in note and "IV" in note
    assert "expiry tomorrow" in fa.expiry_note(date(2026, 7, 24), today, 0.10)
    assert fa.expiry_note(date(2026, 7, 30), today, None) == "7d to expiry"
    assert fa.expiry_note(date(2026, 7, 22), today, None) == ""   # past
    assert fa.expiry_note(None, today, None) == ""
