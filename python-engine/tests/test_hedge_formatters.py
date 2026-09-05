from datetime import date, datetime, timedelta
import re

import pytest
import pytz

from fno_chain import ChainSnapshot
from fno_models import Contract, ContractQuote
from hedge_analytics import VixRegimeReading
from hedge_formatters import (
    DISCLAIMER, MAX_TELEGRAM_CHARS, format_collar_recommendation,
    format_bear_call_spread, format_bull_put_spread,
    format_covered_call_recommendation, format_delta_hedge_rebalance,
    format_futures_hedge_size, format_hedge_daily_summary, format_no_recommendation,
    format_iron_condor, format_protective_put_alert, format_vix_hedge_alert,
)
from hedge_strategies import (
    BearCallSpreadPlan, BullPutSpreadPlan, CollarPlan, CoveredCallPlan,
    DeltaRebalancePlan, IronCondorPlan, LegSpec, collar_recommendation,
    futures_hedge_size, protective_put_alert,
)

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 9, 2, 11, 0))
EXPIRY = date(2026, 9, 29)
FORBIDDEN = re.compile(r"execute|buy\s+now|sell\s+now|guaranteed", re.I)


def _contract(kind, strike, token, lot=65):
    return Contract(token, f"NIFTY{EXPIRY:%y%m%d}{int(strike)}{kind}",
                    "NIFTY", EXPIRY, strike, kind, lot)


def _quote(contract, bid, ask):
    return ContractQuote(
        contract, bid=bid, ask=ask, ltp=(bid + ask) / 2,
        oi=5_000, volume=1_000, last_trade_time=NOW,
    )


def _snapshot():
    put = _quote(_contract("PE", 24_500, 1), 70, 72)
    call = _quote(_contract("CE", 25_500, 2), 68, 70)
    future = _quote(_contract("FUT", 0, 3), 24_990, 25_010)
    return ChainSnapshot(
        NOW - timedelta(seconds=20), EXPIRY, 25_000, 25_000, 65,
        future, {(24_500.0, "PE"): put, (25_500.0, "CE"): call},
    )


@pytest.mark.parametrize("formatter,plan", [
    (format_protective_put_alert, lambda: protective_put_alert(_snapshot(), 100, NOW)),
    (format_collar_recommendation, lambda: collar_recommendation(_snapshot(), 130, NOW)),
    (format_futures_hedge_size, lambda: futures_hedge_size(
        _snapshot(), 4_000_000, hedge_ratio=.5, now_ist=NOW,
    )),
])
def test_plan_messages_are_safe_current_and_bounded(formatter, plan):
    value = plan()
    assert value is not None
    text = formatter(value)
    assert DISCLAIMER in text
    assert len(text) <= MAX_TELEGRAM_CHARS
    assert not FORBIDDEN.search(text)
    assert "Live as of:" in text
    assert EXPIRY.isoformat() in text
    assert "bid" in text and "ask" in text
    assert "Review" in text


def test_protective_message_makes_partial_coverage_explicit():
    text = format_protective_put_alert(protective_put_alert(_snapshot(), 100, NOW))
    assert "PARTIAL COVERAGE" in text
    assert "65/100" in text


def test_vix_message_is_informational_and_rejects_automatic_action():
    reading = VixRegimeReading(
        "ELEVATED", 20.0, .15, 1.2, True,
        "Review protection; no automatic action", True,
    )
    text = format_vix_hedge_alert(reading, as_of=NOW)
    assert "informational only" in text
    assert not FORBIDDEN.search(text)
    with pytest.raises(ValueError, match="automatic"):
        format_vix_hedge_alert(VixRegimeReading(
            "PANIC", 25.0, .25, 2.5, True, "bad", True, True,
        ), as_of=NOW)


def test_no_recommendation_sanitizes_untrusted_reason_and_preserves_disclaimer():
    text = format_no_recommendation(
        "nifty", "BUY NOW\n" + "x" * 10_000, as_of=NOW,
    )
    assert "[redacted]" in text
    assert not FORBIDDEN.search(text)
    assert len(text) <= MAX_TELEGRAM_CHARS
    assert text.endswith(DISCLAIMER)


def test_hedge_daily_summary_is_explicitly_non_personalized_without_inputs():
    text = format_hedge_daily_summary(
        "MORNING", open_positions=0, reconciled_positions=0,
        input_state="NO_PORTFOLIO_INPUT", as_of=NOW,
    )
    assert "0/0 open positions reconciled" in text
    assert "No personalized quantity" in text
    assert DISCLAIMER in text


def test_formatter_rejects_missing_live_contract_identity():
    plan = protective_put_alert(_snapshot(), 65, NOW)
    object.__setattr__(plan.legs[0], "tradingsymbol", "")
    with pytest.raises(ValueError, match="identity"):
        format_protective_put_alert(plan)


def _leg(side, kind, strike, premium, token, quantity=1):
    bid = premium if side == "SELL" else premium - 2
    ask = premium if side == "BUY" else premium + 2
    return LegSpec(
        side=side, opt_type=kind, strike=strike, expiry=EXPIRY,
        premium=premium, quantity=quantity, lot_size=65, contract_token=token,
        tradingsymbol=f"NIFTY{EXPIRY:%y%m%d}{int(strike)}{kind}",
        bid=bid, ask=ask,
    )


def _covered_call_plan():
    leg = _leg("SELL", "CE", 25_500, 68, 20)
    return CoveredCallPlan(
        strategy="covered_call_recommendation", underlying="NIFTY", spot=25_000,
        expiry=EXPIRY, taken_at=NOW, legs=(leg,), net_premium=68 * 65,
        max_profit=(25_500 - 25_000) * 65 + 68 * 65,
        max_loss=25_000 * 65 - 68 * 65, breakevens=(24_932,), hedge_ratio=1.0,
        rationale="Long confirmed index-equivalent holding; resistance is above spot.",
        covered_units=65, option_units=65, call_strike=25_500,
        cap_return_pct=(500 + 68) / 25_000, yield_pct=68 / 25_000,
        credit_points=68, credit_rupees=68 * 65,
    )


def _bull_put_plan():
    short, long = _leg("SELL", "PE", 24_500, 70, 21), _leg("BUY", "PE", 24_300, 40, 22)
    return BullPutSpreadPlan(
        strategy="bull_put_spread", underlying="NIFTY", spot=25_000, expiry=EXPIRY,
        taken_at=NOW, legs=(short, long), net_premium=30 * 65, max_profit=30 * 65,
        max_loss=170 * 65, breakevens=(24_470,), hedge_ratio=1.0,
        rationale="Support remains below the short put; IV is elevated versus history.",
        short_strike=24_500, long_strike=24_300, width=200, credit=30 * 65,
        credit_points=30, credit_rupees=30 * 65,
    )


def _bear_call_plan():
    short, long = _leg("SELL", "CE", 25_500, 70, 23), _leg("BUY", "CE", 25_700, 40, 24)
    return BearCallSpreadPlan(
        strategy="bear_call_spread", underlying="NIFTY", spot=25_000, expiry=EXPIRY,
        taken_at=NOW, legs=(short, long), net_premium=30 * 65, max_profit=30 * 65,
        max_loss=170 * 65, breakevens=(25_530,), hedge_ratio=1.0,
        rationale="Resistance is above the short call; upside momentum is weak.",
        short_strike=25_500, long_strike=25_700, width=200, credit=30 * 65,
        credit_points=30, credit_rupees=30 * 65,
    )


def _condor_plan():
    sp = _leg("SELL", "PE", 24_400, 60, 25)
    lp = _leg("BUY", "PE", 24_200, 20, 26)
    sc = _leg("SELL", "CE", 25_600, 65, 27)
    lc = _leg("BUY", "CE", 25_800, 20, 28)
    return IronCondorPlan(
        strategy="iron_condor", underlying="NIFTY", spot=25_000, expiry=EXPIRY,
        taken_at=NOW, legs=(sp, lp, sc, lc), net_premium=85 * 65,
        max_profit=85 * 65, max_loss=115 * 65, breakevens=(24_315, 25_685),
        hedge_ratio=1.0, rationale="Range regime; both tails have liquid wings.",
        short_put_strike=24_400, long_put_strike=24_200,
        short_call_strike=25_600, long_call_strike=25_800,
        body_low=24_400, body_high=25_600, put_width=200, call_width=200,
        credit=85 * 65, credit_points=85, credit_rupees=85 * 65,
    )


def _delta_plan():
    leg = _leg("SELL", "FUT", 0, 24_990, 29)
    return DeltaRebalancePlan(
        strategy="delta_hedge_rebalance", underlying="NIFTY", spot=25_000,
        expiry=EXPIRY, taken_at=NOW, legs=(leg,), net_premium=0.0,
        max_profit=float("inf"), max_loss=float("inf"), breakevens=(),
        hedge_ratio=1 / 2.4, rationale="Portfolio delta is above the neutral target.",
        side="SELL", lots=1, current_net_delta=2.4, target_net_delta=0.0,
        residual_delta=1.4,
    )


@pytest.mark.parametrize("formatter,plan,markers", [
    (format_covered_call_recommendation, _covered_call_plan, ("Premium received", "points", "DTE:")),
    (format_bull_put_spread, _bull_put_plan, ("Net credit received", "Defined maximum loss", "DTE:")),
    (format_bear_call_spread, _bear_call_plan, ("Net credit received", "Defined maximum loss", "DTE:")),
    (format_iron_condor, _condor_plan, ("Net credit received", "Defined maximum loss", "DTE:")),
    (format_delta_hedge_rebalance, _delta_plan, ("Whole-lot adjustment", "residual", "DTE:")),
])
def test_phase2_messages_are_explicit_and_partner_safe(formatter, plan, markers):
    text = formatter(plan())
    assert DISCLAIMER in text
    assert not FORBIDDEN.search(text)
    assert len(text) <= MAX_TELEGRAM_CHARS
    assert all(marker in text for marker in markers)
    assert "₹" in text
    assert "Context:" in text
    if formatter is not format_delta_hedge_rebalance:
        assert "Option-leg Greeks (model, snapshot):" in text


def test_phase2_formatters_reject_wrong_leg_topology_and_fabricated_metrics():
    plan = _bull_put_plan()
    object.__setattr__(plan, "legs", (plan.legs[1], plan.legs[0]))
    with pytest.raises(ValueError, match="wrong side/type or order"):
        format_bull_put_spread(plan)

    plan = _covered_call_plan()
    object.__setattr__(plan, "net_premium", 1.0)
    with pytest.raises(ValueError, match="malformed|premium"):
        format_covered_call_recommendation(plan)

    plan = _bear_call_plan()
    object.__setattr__(plan, "max_loss", 1.0)
    with pytest.raises(ValueError, match="malformed"):
        format_bear_call_spread(plan)

    plan = _condor_plan()
    object.__setattr__(plan.legs[-1], "lot_size", 50)
    with pytest.raises(ValueError, match="malformed"):
        format_iron_condor(plan)

    plan = _bull_put_plan()
    object.__setattr__(plan, "width", "200")
    with pytest.raises(ValueError, match="real number"):
        format_bull_put_spread(plan)


def test_delta_formatter_rejects_non_improving_or_non_exact_plan():
    plan = _delta_plan()
    object.__setattr__(plan, "side", "BUY")
    with pytest.raises(ValueError, match="malformed|side"):
        format_delta_hedge_rebalance(plan)
    object.__setattr__(plan, "side", "SELL")
    object.__setattr__(plan, "residual_delta", 3.0)
    with pytest.raises(ValueError, match="malformed|improve"):
        format_delta_hedge_rebalance(plan)
    plan = _delta_plan()
    object.__setattr__(plan, "net_premium", 10.0)
    with pytest.raises(ValueError, match="malformed|premium"):
        format_delta_hedge_rebalance(plan)


def test_quote_labels_use_points_not_rupee_currency():
    text = format_bull_put_spread(_bull_put_plan())
    assert "bid 70.00 points / ask 72.00 points" in text
    assert "bid ₹" not in text
