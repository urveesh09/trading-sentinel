"""Evidence-driven F&O sizing: shrink in drawdown, grow only when proven."""
from datetime import datetime, timedelta

import pytz

from fno_adaptive_risk import AdaptiveRiskPolicy, Close, risk_stance

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 10, 14, 11, 0))
POLICY = AdaptiveRiskPolicy()


def _trades(pnls, *, days_back=30, single_leg=True):
    start = NOW - timedelta(days=days_back)
    return [Close(start + timedelta(hours=i), float(p), single_leg) for i, p in enumerate(pnls)]


def test_fresh_book_trades_base_size():
    stance = risk_stance([], allocation=250_000, now=NOW, policy=POLICY)
    assert stance.multiplier == 1.0 and stance.reason == "base" and stance.closed_trades == 0


def test_drawdown_cuts_size_in_two_steps():
    cut1 = risk_stance(_trades([-5_000, -6_000]), allocation=250_000, now=NOW, policy=POLICY)   # 4.4% down
    assert (cut1.multiplier, cut1.reason) == (0.5, "drawdown_cut1")
    cut2 = risk_stance(_trades([-10_000, -11_000]), allocation=250_000, now=NOW, policy=POLICY)  # 8.4% down
    assert (cut2.multiplier, cut2.reason) == (0.25, "drawdown_cut2")
    # Drawdown is measured from the equity PEAK, not the allocation.
    from_peak = risk_stance(_trades([20_000, -12_000]), allocation=250_000, now=NOW, policy=POLICY)
    assert from_peak.drawdown_pct > 0.04 and from_peak.multiplier == 0.5


def test_size_grows_only_after_enough_profitable_trades_near_the_peak():
    winners = [3_000, -1_000] * 10                              # 20 trades, PF 3.0, at peak
    up1 = risk_stance(_trades(winners), allocation=250_000, now=NOW, policy=POLICY)
    assert (up1.multiplier, up1.reason) == (1.25, "proven_edge_up1")
    up2 = risk_stance(_trades(winners * 2), allocation=250_000, now=NOW, policy=POLICY)
    assert (up2.multiplier, up2.reason) == (1.5, "proven_edge_up2")
    too_few = risk_stance(_trades([3_000, -1_000] * 9), allocation=250_000, now=NOW, policy=POLICY)
    assert too_few.multiplier == 1.0
    # Profitable history but currently off the peak: no press.
    off_peak = risk_stance(_trades(winners + [-6_000]), allocation=250_000, now=NOW, policy=POLICY)
    assert off_peak.multiplier == 1.0 and off_peak.drawdown_pct > POLICY.near_peak


def test_two_strikes_end_single_leg_entries_for_the_day_only():
    today = [Close(NOW - timedelta(hours=2), -800, True), Close(NOW - timedelta(hours=1), -900, True)]
    halted = risk_stance(today, allocation=250_000, now=NOW, policy=POLICY)
    assert halted.single_leg_halted_today and halted.single_leg_losses_today == 2
    spread_losses = [Close(c.at, c.pnl, False) for c in today]          # capped-loss book does not count
    assert not risk_stance(spread_losses, allocation=250_000, now=NOW, policy=POLICY).single_leg_halted_today
    tomorrow = NOW + timedelta(days=1)
    assert not risk_stance(today, allocation=250_000, now=tomorrow, policy=POLICY).single_leg_halted_today


def test_future_closes_are_invisible_and_disabled_policy_is_neutral():
    later = [Close(NOW + timedelta(hours=1), -50_000, True)]
    assert risk_stance(later, allocation=250_000, now=NOW, policy=POLICY).multiplier == 1.0
    off = AdaptiveRiskPolicy(enabled=False)
    assert risk_stance(_trades([-30_000]), allocation=250_000, now=NOW, policy=off).multiplier == 1.0


def test_third_lot_exists_only_above_one_times():
    from tests.test_fno_entry_plan import NOW as PLAN_NOW, chain, signal, state
    from fno_entry_plan import plan_single_leg_entry
    cheap = chain(iv=0.06)                                        # cheap premium -> risk allows many lots
    base = plan_single_leg_entry(signal(), cheap, "REGIME_1_NORMAL", PLAN_NOW, state())
    pressed = plan_single_leg_entry(signal(), cheap, "REGIME_1_NORMAL", PLAN_NOW, state(risk_multiplier=1.5))
    halved = plan_single_leg_entry(signal(), cheap, "REGIME_1_NORMAL", PLAN_NOW, state(risk_multiplier=0.5))
    assert base.accepted and base.lots == 2
    assert pressed.accepted and pressed.lots == 3
    assert halved.lots < base.lots or halved.reject_reason == "pool_below_min_viable"
