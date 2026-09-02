from datetime import date, datetime, timedelta
import math

import pytz

from fno_chain import ChainSnapshot
from fno_models import Contract, ContractQuote, OptionType
from hedge_strategies import (
    BearCallSpreadPlan,
    BullPutSpreadPlan,
    CollarPlan,
    CoveredCallPlan,
    DeltaRebalancePlan,
    FuturesHedgeSizePlan,
    IronCondorPlan,
    IronButterflyPlan, LongVolPlan, CalendarSpreadPlan,
    ProtectivePutPlan,
    bear_call_spread,
    bull_put_spread,
    collar_recommendation,
    covered_call_recommendation,
    delta_hedge_rebalance,
    futures_hedge_size,
    iron_condor,
    iron_butterfly, long_straddle, long_strangle, calendar_diary_spread,
    ratio_spread,
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


def _phase2_snapshot(now=None):
    """Wide, live chain with exact 200-point wings for Phase 2 plans."""
    now = now or IST.localize(datetime(2026, 9, 1, 11, 0))
    expiry = date(2026, 9, 25)
    quotes = {}
    # The 24,500/25,500 legs are closest to .30 delta; the 24,300/25,700
    # legs are closest to .16 and therefore become the condor body.
    for kind, strike, bid, ask, token in (
        ("PE", 24100, 8, 10, 11),
        ("PE", 24300, 24, 26, 12),
        ("PE", 24500, 70, 72, 13),
        ("CE", 25500, 68, 70, 14),
        ("CE", 25700, 24, 26, 15),
        ("CE", 25900, 8, 10, 16),
    ):
        contract = _contract(kind, strike, expiry, token)
        quotes[(float(strike), kind)] = _quote(contract, bid, ask, now, oi=5_000, volume=1_000)
    future = _quote(_contract("FUT", 0, expiry, 17), 24990, 25010, now, oi=50_000, volume=10_000)
    return ChainSnapshot(now - timedelta(seconds=20), expiry, 25000, 25000, 65, future, quotes)


def _phase3_snapshot(now=None, expiry=None):
    now = now or IST.localize(datetime(2026, 9, 1, 11, 0))
    expiry = expiry or date(2026, 9, 25)
    quotes = {}
    for kind, strike, bid, ask, token in (
        ("PE", 24300, 24, 26, 31), ("PE", 24800, 105, 108, 32),
        ("PE", 25000, 190, 194, 33), ("CE", 25000, 185, 189, 34),
        ("CE", 25200, 100, 103, 35), ("CE", 25700, 23, 25, 36),
    ):
        c = _contract(kind, strike, expiry, token)
        quotes[(float(strike), kind)] = _quote(c, bid, ask, now, oi=8000, volume=2000)
    fut = _quote(_contract("FUT", 0, expiry, 37), 24990, 25010, now, oi=50000, volume=10000)
    return ChainSnapshot(now-timedelta(seconds=10), expiry, 25000, 25000, 65, fut, quotes)


def test_phase3_defined_risk_builders_use_executable_quotes():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    snap = _phase3_snapshot(now)
    straddle = long_straddle(snap, now)
    strangle = long_strangle(snap, now, target_delta=.20)
    butterfly = iron_butterfly(snap, now, wing_width=200, min_credit=1)
    assert isinstance(straddle, LongVolPlan)
    assert isinstance(strangle, LongVolPlan)
    assert isinstance(butterfly, IronButterflyPlan)
    for plan in (straddle, strangle):
        assert plan.max_loss == sum(leg.ask*leg.quantity*leg.lot_size for leg in plan.legs)
        assert plan.net_premium == -plan.max_loss
    assert butterfly.max_loss == (200-butterfly.credit_points)*65
    assert all(leg.premium == (leg.ask if leg.side == "BUY" else leg.bid) for leg in butterfly.legs)


def test_phase3_builders_fail_closed_on_missing_stale_or_unsafe_inputs():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    snap = _phase3_snapshot(now)
    del snap.quotes[(25000.0, "CE")]
    assert long_straddle(snap, now) is None
    assert iron_butterfly(snap, now, wing_width=200) is None
    assert ratio_spread(_phase3_snapshot(now), now) is None
    assert ratio_spread(_phase3_snapshot(now), now, allow_unbounded=True) is not None
    stale = _phase3_snapshot(now)
    stale.quotes[(25000.0, "PE")].last_trade_time = now-timedelta(minutes=10)
    assert long_straddle(stale, now) is None


def test_calendar_requires_same_strike_lot_and_later_expiry():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    front = _phase3_snapshot(now, date(2026, 9, 25))
    back = _phase3_snapshot(now, date(2026, 10, 30))
    # Back-month ATM ask must exceed the front-month bid.
    back.quotes[(25000.0, "CE")].bid = 290
    back.quotes[(25000.0, "CE")].ask = 300
    plan = calendar_diary_spread(front, back, now)
    assert isinstance(plan, CalendarSpreadPlan)
    assert plan.legs[0].expiry == front.expiry and plan.legs[1].expiry == back.expiry
    assert plan.max_loss == (300-front.quotes[(25000.0, "CE")].bid)*65
    assert calendar_diary_spread(back, front, now) is None


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


def test_covered_call_is_quote_backed_covered_and_explicit_about_units():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    plan = covered_call_recommendation(_phase2_snapshot(now), 130, now)
    assert isinstance(plan, CoveredCallPlan)
    leg = plan.legs[0]
    assert leg.side == "SELL"
    assert leg.premium == leg.bid
    assert leg.premium_points == leg.bid
    assert leg.premium_rupees_per_lot == leg.bid * 65
    assert leg.lot_size == 65
    assert plan.option_units == 130
    assert plan.credit_points == leg.bid
    assert plan.credit_rupees == plan.net_premium == leg.bid * 130
    assert covered_call_recommendation(_phase2_snapshot(now), 65, now, min_dte=30) is None
    assert covered_call_recommendation(_phase2_snapshot(now), 64, now) is None
    assert covered_call_recommendation(_phase2_snapshot(now), 100, now) is None


def test_credit_spreads_use_exact_wings_executable_prices_and_rupee_risk():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    snap = _phase2_snapshot(now)
    bull = bull_put_spread(snap, now, short_delta=.30, width=200, lots=2, min_credit=10)
    bear = bear_call_spread(snap, now, short_delta=.30, width=200, lots=2, min_credit=10)
    assert isinstance(bull, BullPutSpreadPlan)
    assert isinstance(bear, BearCallSpreadPlan)
    for plan in (bull, bear):
        short_leg, long_leg = plan.legs
        assert short_leg.side == "SELL" and short_leg.premium == short_leg.bid
        assert long_leg.side == "BUY" and long_leg.premium == long_leg.ask
        assert short_leg.expiry == long_leg.expiry == plan.expiry
        assert short_leg.lot_size == long_leg.lot_size == 65
        expected_points = short_leg.bid - long_leg.ask
        assert plan.credit_points == expected_points
        assert plan.credit_rupees == plan.credit == plan.net_premium == expected_points * 65 * 2
        assert plan.max_profit == plan.credit_rupees
        assert plan.max_loss == (plan.width - expected_points) * 65 * 2
        assert plan.max_loss > 0
    assert bull.long_strike == bull.short_strike - 200
    assert bear.long_strike == bear.short_strike + 200


def test_spreads_fail_closed_for_missing_wing_or_mixed_contract_identity():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    snap = _phase2_snapshot(now)
    del snap.quotes[(24300.0, "PE")]
    assert bull_put_spread(snap, now, short_delta=.30, width=200) is None

    snap = _phase2_snapshot(now)
    # The listed wing exists, but belongs to another underlying.  It must not
    # be combined with the NIFTY short leg.
    wrong = _contract("PE", 24300, snap.expiry, 99)
    wrong = Contract(wrong.token, wrong.tradingsymbol, "BANKNIFTY", wrong.expiry,
                     wrong.strike, wrong.instrument_type, wrong.lot_size)
    snap.quotes[(24300.0, "PE")] = _quote(wrong, 24, 26, now, oi=5_000, volume=1_000)
    assert bull_put_spread(snap, now, short_delta=.30, width=200) is None

    snap = _phase2_snapshot(now)
    snap.quotes[(25700.0, "CE")].last_trade_time = None
    assert bear_call_spread(snap, now, short_delta=.30, width=200) is None


def test_iron_condor_has_four_live_legs_and_exact_defined_risk_geometry():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    plan = iron_condor(_phase2_snapshot(now), now, short_put_delta=.16,
                       short_call_delta=.16, wing_width=200, lots=1, min_credit=10)
    assert isinstance(plan, IronCondorPlan)
    assert [leg.side for leg in plan.legs] == ["SELL", "BUY", "SELL", "BUY"]
    assert [leg.opt_type for leg in plan.legs] == ["PE", "PE", "CE", "CE"]
    assert all(leg.premium == (leg.bid if leg.side == "SELL" else leg.ask) for leg in plan.legs)
    assert plan.long_put_strike < plan.short_put_strike < plan.spot < plan.short_call_strike < plan.long_call_strike
    assert plan.put_width == plan.call_width == 200
    expected_points = ((plan.legs[0].bid - plan.legs[1].ask)
                       + (plan.legs[2].bid - plan.legs[3].ask))
    assert plan.credit_points == expected_points
    assert plan.credit_rupees == plan.credit == plan.net_premium == expected_points * 65
    assert plan.max_loss == (200 - expected_points) * 65
    assert plan.max_loss > 0


def test_iron_condor_fails_closed_when_quote_map_contract_key_disagrees():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    snap = _phase2_snapshot(now)
    # A map key cannot claim 24,300 while the resolved instrument is 24,250.
    mismatched = _contract("PE", 24250, snap.expiry, 77)
    snap.quotes[(24300.0, "PE")] = _quote(mismatched, 24, 26, now, oi=5_000, volume=1_000)
    assert iron_condor(snap, now, short_put_delta=.16, short_call_delta=.16, wing_width=200) is None


def test_delta_rebalance_uses_only_whole_live_futures_lots_and_never_crosses_target():
    now = IST.localize(datetime(2026, 9, 1, 11, 0))
    snap = _phase2_snapshot(now)
    sell = delta_hedge_rebalance(snap, current_net_delta=1.25, target_net_delta=0.0, now_ist=now)
    buy = delta_hedge_rebalance(snap, current_net_delta=-2.2, target_net_delta=0.0, now_ist=now)
    assert isinstance(sell, DeltaRebalancePlan)
    assert sell.side == "SELL" and sell.lots == 1 and sell.legs[0].premium == sell.legs[0].bid
    assert sell.residual_delta == .25
    assert isinstance(buy, DeltaRebalancePlan)
    assert buy.side == "BUY" and buy.lots == 2 and buy.legs[0].premium == buy.legs[0].ask
    assert buy.residual_delta == -.2
    # A sub-lot error is deliberately not turned into a fractional future.
    assert delta_hedge_rebalance(snap, current_net_delta=.9, now_ist=now) is None
    assert delta_hedge_rebalance(snap, current_net_delta=.15, now_ist=now) is None
    snap.fut_quote.last_trade_time = None
    assert delta_hedge_rebalance(snap, current_net_delta=2, now_ist=now) is None
