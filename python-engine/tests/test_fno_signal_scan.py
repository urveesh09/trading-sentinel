"""
[PARTNER-TIPS-TESTS 2026-07-18] Read-only signal-scan facade (plan WS2):
fired vs non-fired paths, the thin-chain tag (tips degrade, never
suppress), and per-underlying error isolation. Bars use the proven
synthetic-session builders from test_fno_engine_mom.
"""
from datetime import date, datetime

import pandas as pd
import pytest
import pytz

import fno_signal_scan as scan_mod
import options_math
from fno_chain import ChainSnapshot, years_to_expiry, RISK_FREE_RATE
from fno_models import Contract, ContractQuote, FnoDirection
from fno_underlyings import UnderlyingSpec

IST = pytz.timezone("Asia/Kolkata")
PRIOR_DAYS = ["2026-07-03", "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"]
TODAY = "2026-07-10"
NOW = IST.localize(datetime(2026, 7, 10, 10, 3))
EXPIRY = date(2026, 7, 14)
F = 25000.0
SPEC = UnderlyingSpec("NIFTY", "NFO")


def _flat_session(day, px=25000.0, vol=100.0):
    idx = pd.date_range(f"{day} 09:15", periods=74, freq="5min")
    return pd.DataFrame({
        "open": px, "high": px + 5, "low": px - 5, "close": px, "volume": vol,
    }, index=idx)


def _today_bars(rows):
    idx = pd.to_datetime([f"{TODAY} {hm}" for hm, *_ in rows])
    cols = list(zip(*[r[1:] for r in rows]))
    return pd.DataFrame({
        "open": cols[0], "high": cols[1], "low": cols[2],
        "close": cols[3], "volume": cols[4],
    }, index=idx)


OR_ROWS = [
    ("09:15", 25000, 25010, 24990, 25000, 100),
    ("09:20", 25000, 25008, 24992, 25000, 100),
    ("09:25", 25000, 25010, 24990, 25000, 100),
    ("09:30", 25000, 25007, 24993, 25000, 100),
    ("09:35", 25000, 25009, 24991, 25000, 100),
    ("09:40", 25000, 25010, 24990, 25000, 100),
]
LONG_ROWS = OR_ROWS + [
    ("09:45", 25000, 25008, 25000, 25005, 100),
    ("09:50", 25005, 25010, 25002, 25005, 100),
    ("09:55", 25010, 25105, 25005, 25100, 300),
]
QUIET_ROWS = OR_ROWS + [
    ("09:45", 25000, 25008, 25000, 25005, 100),
    ("09:50", 25005, 25010, 25002, 25005, 100),
]


def _frame(rows):
    return pd.concat([_flat_session(d) for d in PRIOR_DAYS] + [_today_bars(rows)])


def _quote(strike, ot, oi=10000, volume=5000, vol=0.15, half_spread=0.5):
    T = years_to_expiry(EXPIRY, NOW)
    mid = options_math.black76_price(F, strike, T, vol, RISK_FREE_RATE, ot == "CE")
    c = Contract(
        token=int(strike) * 10 + (1 if ot == "CE" else 2),
        tradingsymbol=f"NIFTY{int(strike)}{ot}", name="NIFTY",
        expiry=EXPIRY, strike=strike, instrument_type=ot, lot_size=75,
    )
    return ContractQuote(
        contract=c, bid=mid - half_spread, ask=mid + half_spread, ltp=mid,
        oi=oi, volume=volume, last_trade_time=NOW,
    )


def _chain(oi=10000, volume=5000):
    quotes = {}
    for k in (24800.0, 24900.0, 25000.0, 25100.0, 25200.0):
        for ot in ("CE", "PE"):
            quotes[(k, ot)] = _quote(k, ot, oi=oi, volume=volume)
    return ChainSnapshot(
        taken_at=NOW, expiry=EXPIRY, forward=F, parity_forward=None,
        lot_size=75, fut_quote=None, quotes=quotes,
    )


class _Book:
    def ready(self, today):
        return True

    def front_future(self, today):
        return Contract(token=900, tradingsymbol="NIFTYFUT", name="NIFTY",
                        expiry=date(2026, 7, 30), strike=0.0,
                        instrument_type="FUT", lot_size=75)


class _Kite:
    def __init__(self, bars):
        self.bars = bars

    async def get_intraday_by_token(self, token, frm, to, interval="5minute"):
        return self.bars


@pytest.fixture
def wired(monkeypatch):
    """Patch the book registry + chain snapshot; each test picks bars/chain."""
    state = {"chain": _chain(), "chain_calls": 0}
    monkeypatch.setattr(scan_mod, "get_instruments_for", lambda name: _Book())

    async def _fake_snapshot(kite, book, now, strike_window=None):
        state["chain_calls"] += 1
        return state["chain"]

    monkeypatch.setattr(scan_mod, "take_chain_snapshot", _fake_snapshot)
    return state


@pytest.mark.asyncio
async def test_fired_long_scan_picks_a_strike(wired):
    out = await scan_mod.scan_underlying(
        _Kite(_frame(LONG_ROWS)), SPEC, "REGIME_1_NORMAL", NOW,
    )
    assert out.error == ""
    assert out.sig.direction == FnoDirection.LONG
    assert out.pick is not None
    q, iv, delta = out.pick
    assert q.contract.instrument_type == "CE"
    assert abs(delta) >= 0.5          # ATM-or-ITM, never OTM
    assert not out.thin_chain
    assert wired["chain_calls"] == 1


@pytest.mark.asyncio
async def test_quiet_market_skips_the_chain_fetch(wired):
    out = await scan_mod.scan_underlying(
        _Kite(_frame(QUIET_ROWS)), SPEC, "REGIME_1_NORMAL", NOW,
    )
    assert out.sig is not None and out.sig.direction is None
    assert out.sig.or_high == 25010.0     # levels still present for the brief
    assert out.snap is None and out.pick is None
    assert wired["chain_calls"] == 0      # no signal -> no quote spend


@pytest.mark.asyncio
async def test_thin_chain_tags_instead_of_suppressing(wired):
    wired["chain"] = _chain(oi=10, volume=3)   # below FNO_MIN_OI / FNO_MIN_VOL
    out = await scan_mod.scan_underlying(
        _Kite(_frame(LONG_ROWS)), SPEC, "REGIME_1_NORMAL", NOW,
    )
    assert out.pick is not None           # the tip still carries a strike
    assert out.thin_chain
    assert any("OI" in r for r in out.thin_reasons)
    assert any("volume" in r for r in out.thin_reasons)


@pytest.mark.asyncio
async def test_chain_unavailable_is_an_error_not_a_raise(wired):
    wired["chain"] = None
    out = await scan_mod.scan_underlying(
        _Kite(_frame(LONG_ROWS)), SPEC, "REGIME_1_NORMAL", NOW,
    )
    assert out.error == "chain_unavailable"
    assert out.sig.direction == FnoDirection.LONG


@pytest.mark.asyncio
async def test_kite_exception_is_isolated(wired):
    class _Boom:
        async def get_intraday_by_token(self, *a, **kw):
            raise RuntimeError("kite down")

    out = await scan_mod.scan_underlying(_Boom(), SPEC, "REGIME_1_NORMAL", NOW)
    assert "kite down" in out.error
    assert out.sig is None


@pytest.mark.asyncio
async def test_instruments_not_ready(monkeypatch):
    class _Stale:
        def ready(self, today):
            return False

    monkeypatch.setattr(scan_mod, "get_instruments_for", lambda name: _Stale())
    out = await scan_mod.scan_underlying(
        _Kite(pd.DataFrame()), SPEC, "REGIME_1_NORMAL", NOW,
    )
    assert out.error == "instruments_not_ready"
