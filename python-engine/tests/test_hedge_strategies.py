from datetime import date, datetime, timedelta
import math

import pytz

from fno_chain import ChainSnapshot
from fno_models import Contract, ContractQuote, OptionType
from hedge_strategies import (
    CollarPlan,
    FuturesHedgeSizePlan,
    ProtectivePutPlan,
    collar_recommendation,
    futures_hedge_size,
    protective_put_alert,
)

IST = pytz.timezone("Asia/Kolkata")


def _contract(kind, strike, expiry, token, lot=65):
    return Contract(token, f"NIFTY{expiry:%y%m%d}{int(strike)}{kind}", "NIFTY",
                    expiry, strike, kind, lot)


def _quote(c, bid, ask, now, oi=1000, volume=100):
    return ContractQuote(c, bid=bid, ask=ask, ltp=(bid + ask) / 2,
                         oi=oi, volume=volume, last_trade_time=now)


def _snapshot(now=None, expiry=None, include_call=True, fresh=True):
    now = now or IST.localize(datetime(2026, 9, 1, 11, 0))
    expiry = expiry or date(2026, 9, 25)
    q = {}
    # Prices are Black-76-compatible and deliberately use real two-sided
    # quote objects, rather than synthetic premium inputs to the builder.
    pe = _contract("PE", 24500, expiry, 1)
    q[(24500.0, "PE")] = _quote(pe, 70, 72, now)
    if include_call:
        ce = _contract("CE", 25500, expiry, 2)
        q[(25500.0, "CE")] = _quote(ce, 68, 70, now)
    fut = _contract("FUT", 0, expiry, 3)
    fq = _quote(fut, 24990, 25010, now)
    taken = now - timedelta(seconds=30 if fresh else 300)
    return ChainSnapshot(taken, expiry, 25000, 25000, 65, fq, q)


def test_protective_put_uses_live_quote_without_overhedging():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    plan = protective_put_alert(_snapshot(now), 100, now)
    assert isinstance(plan, ProtectivePutPlan)
    assert plan.legs[0].side == "BUY"
    assert plan.legs[0].premium == 72  # executable ask, not an invented mid
    assert plan.legs[0].quantity == 1
    assert plan.option_units == 65
    assert plan.hedge_ratio == 0.65
    assert plan.max_loss == 72 * 65
    assert plan.advisory_only is True


def test_protective_put_fails_closed_on_thin_or_stale_quotes():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    assert protective_put_alert(_snapshot(now, include_call=False), 65, now) is not None
    assert protective_put_alert(_snapshot(now, include_call=False), 65, now,
                                min_volume=10000) is None
    assert protective_put_alert(_snapshot(now, include_call=False, fresh=False), 65, now) is None
    q = _snapshot(now, include_call=False).quotes[(24500.0, "PE")]
    q.bid = 0
    assert protective_put_alert(_snapshot(now, include_call=False), 65, now) is not None
    assert protective_put_alert(ChainSnapshot(_snapshot(now).taken_at,
                                              _snapshot(now).expiry, 25000, 25000, 65,
                                              _snapshot(now).fut_quote,
                                              {(24500.0, "PE"): q}), 65, now) is None


def test_protective_put_rejects_nonpositive_holding_and_0dte():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    assert protective_put_alert(_snapshot(now), 0, now) is None
    assert protective_put_alert(_snapshot(now), 64, now) is None
    assert protective_put_alert(_snapshot(now, expiry=now.date()), 65, now) is None
    assert protective_put_alert(_snapshot(now, expiry=now.date()), 65, now,
                                allow_0dte=True) is not None


def test_collar_requires_whole_covered_lots_and_both_legs():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    plan = collar_recommendation(_snapshot(now), 130, now)
    assert isinstance(plan, CollarPlan)
    assert [x.side for x in plan.legs] == ["BUY", "SELL"]
    assert plan.net_debit == (72 - 68) * 130
    assert plan.put_strike < plan.call_strike
    assert plan.max_loss >= 0
    assert collar_recommendation(_snapshot(now), 100, now) is None
    assert collar_recommendation(_snapshot(now, include_call=False), 65, now) is None


def test_collar_refuses_inverted_strikes_and_wide_spreads():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    snap = _snapshot(now)
    # A call below forward is ignored as an unsuitable ITM candidate; the
    # builder may still use the valid OTM call that remains in this snapshot.
    c = _contract("CE", 24000, snap.expiry, 9)
    snap.quotes[(24000.0, "CE")] = _quote(c, 68, 70, now)
    assert collar_recommendation(snap, 65, now) is not None
    snap = _snapshot(now)
    q = snap.quotes[(24500.0, "PE")]
    q.bid, q.ask = 1, 100
    assert collar_recommendation(snap, 65, now) is None


def test_futures_size_uses_live_lot_size_and_never_rounds_up():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    plan = futures_hedge_size(_snapshot(now), 25000 * 65 * 2 + 1, now_ist=now)
    assert isinstance(plan, FuturesHedgeSizePlan)
    assert plan.lots == 2
    assert plan.notional == 25000 * 65
    assert plan.residual_delta == 1
    assert plan.legs[0].side == "SELL"
    assert plan.legs[0].premium == 24990


def test_futures_size_fails_closed_for_bad_inputs_and_quote():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    snap = _snapshot(now)
    assert futures_hedge_size(snap, 1, now_ist=now) is None
    assert futures_hedge_size(snap, 100000, beta=0, now_ist=now) is None
    assert futures_hedge_size(snap, 100000, hedge_ratio=1.1, now_ist=now) is None
    snap.fut_quote.bid = 0
    assert futures_hedge_size(snap, 10000000, now_ist=now) is None


def test_builders_require_timezone_aware_now():
    naive = datetime(2026, 9, 1, 11, 0)
    snap = _snapshot()
    assert protective_put_alert(snap, 65, naive) is None
    assert collar_recommendation(snap, 65, naive) is None
    assert futures_hedge_size(snap, 10000000, now_ist=naive) is None
