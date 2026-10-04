"""Pure single-leg entry planning and shared entry-halt arithmetic."""
from datetime import date, datetime, timedelta

import pytz

import options_math
from fno_chain import ChainSnapshot, RISK_FREE_RATE, years_to_expiry
from fno_engine_mom import MomSignal
from fno_entry_plan import EntryState, plan_single_leg_entry
from fno_models import Contract, ContractQuote, FnoDirection
from fno_shared_risk import SharedFnoRiskPolicy, entry_halts

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 9, 14, 10, 0, 30))
EXPIRY = date(2026, 9, 22)
FORWARD = 25_000.0


def chain(forward=FORWARD, iv=0.15, spread=0.004):
    T = years_to_expiry(EXPIRY, NOW)
    quotes, token = {}, 1000
    for strike in range(24_750, 25_300, 50):
        for kind in ("CE", "PE"):
            token += 1
            mid = options_math.black76_price(forward, strike, T, iv, RISK_FREE_RATE, kind == "CE")
            contract = Contract(token, f"NIFTY{strike}{kind}", "NIFTY", EXPIRY, float(strike), kind, 65)
            quotes[(float(strike), kind)] = ContractQuote(
                contract, bid=round(mid * (1 - spread / 2), 2), ask=round(mid * (1 + spread / 2), 2),
                ltp=round(mid, 2), oi=50_000, volume=20_000, last_trade_time=NOW - timedelta(seconds=3))
    fut = Contract(1, "NIFTYFUT", "NIFTY", EXPIRY, 0.0, "FUT", 65)
    return ChainSnapshot(taken_at=NOW, expiry=EXPIRY, forward=forward, parity_forward=None, lot_size=65,
                         fut_quote=ContractQuote(fut, ltp=forward), quotes=quotes)


def signal(stop_pts=40.0, r_mult=1.8, direction=FnoDirection.LONG):
    sign = 1 if direction == FnoDirection.LONG else -1
    return MomSignal(bar_ts="2026-09-14 09:55:00", direction=direction, close=FORWARD, atr=26.0,
                     stop_underlying=FORWARD - sign * stop_pts,
                     target_underlying=FORWARD + sign * r_mult * stop_pts)


def state(**overrides):
    base = dict(pool=250_000.0, open_premium=0.0, open_positions=0, trades_today=0, active_kill_switches=(),
                held_symbols=frozenset(), is_trading_day=True, is_expiry_day=False)
    base.update(overrides)
    return EntryState(**base)


def test_accepted_plan_picks_atm_or_itm_near_055_delta_and_fills_at_ask():
    plan = plan_single_leg_entry(signal(), chain(), "REGIME_1_NORMAL", NOW, state())
    assert plan.accepted, plan.reject_reason
    assert plan.quote.contract.instrument_type == "CE"
    assert plan.quote.contract.strike <= FORWARD * 1.001         # never OTM
    assert 0.45 <= abs(plan.delta) <= 0.65
    assert plan.lots >= 1 and plan.log_fields["premium"] == plan.quote.ask
    assert plan.reward_risk >= 1.30


def test_rejections_keep_shipped_reasons_and_order():
    base = plan_single_leg_entry(signal(), chain(), "REGIME_1_NORMAL", NOW, state())
    symbol = base.quote.contract.tradingsymbol
    held = plan_single_leg_entry(signal(), chain(), "REGIME_1_NORMAL", NOW, state(held_symbols=frozenset({symbol})))
    assert held.reject_reason == "already_holding_this_contract"
    halted = plan_single_leg_entry(signal(), chain(), "REGIME_1_NORMAL", NOW,
                                   state(active_kill_switches=("daily_loss_halt pnl=-20000",)))
    assert halted.reject_reason == "kill_switches_clear" and halted.log_fields["passed_gates"]
    poor = plan_single_leg_entry(signal(stop_pts=40.0, r_mult=0.6), chain(), "REGIME_1_NORMAL", NOW, state())
    assert poor.reject_reason == "reward_risk_below_min"
    tiny = plan_single_leg_entry(signal(), chain(), "REGIME_1_NORMAL", NOW, state(pool=5_000.0))
    assert tiny.reject_reason == "pool_below_min_viable"     # fno_gates._reject_reason mapping


def test_put_side_for_short_signal():
    plan = plan_single_leg_entry(signal(direction=FnoDirection.SHORT), chain(), "REGIME_1_NORMAL", NOW, state())
    assert plan.accepted and plan.quote.contract.instrument_type == "PE"
    assert plan.quote.contract.strike >= FORWARD * 0.999


def _at(day, hour=12):
    return IST.localize(datetime(2026, 9, day, hour, 0))


def test_entry_halts_daily_weekly_and_future_events():
    policy = SharedFnoRiskPolicy()
    loss = -0.07 * 250_000
    halts = entry_halts(trade_cash=[(_at(14), loss)], completed_newest_first=[(_at(14), loss)],
                        today_ist=date(2026, 9, 14), pool_rs=250_000, equity_rs=232_500, policy=policy)
    assert any(h.startswith("daily_loss_halt") for h in halts.active) and halts.day_pnl_rs == loss
    later = entry_halts(trade_cash=[(_at(15), loss)], completed_newest_first=[(_at(15), loss)],
                        today_ist=date(2026, 9, 14), pool_rs=250_000, equity_rs=250_000, policy=policy)
    assert later.active == () and later.day_pnl_rs == 0.0        # never a credit or debit from the future


def test_entry_halts_loss_streak_pause_and_reset():
    policy = SharedFnoRiskPolicy()
    streak = [(_at(14, 9 + i), -100.0) for i in range(6)][::-1]
    paused = entry_halts(trade_cash=[], completed_newest_first=streak, today_ist=date(2026, 9, 15),
                         pool_rs=250_000, equity_rs=249_400, policy=policy)
    assert paused.loss_streak == 6 and any("consecutive_loss_pause" in h for h in paused.active)
    reset = entry_halts(trade_cash=[], completed_newest_first=[(_at(14, 16), 50.0), *streak],
                        today_ist=date(2026, 9, 15), pool_rs=250_000, equity_rs=249_450, policy=policy)
    assert reset.loss_streak == 0 and reset.active == ()
    expired = entry_halts(trade_cash=[], completed_newest_first=streak, today_ist=date(2026, 9, 16),
                          pool_rs=250_000, equity_rs=249_400, policy=policy)
    assert expired.active == ()


def test_drawdown_cut_shrinks_to_one_lot_but_never_halts():
    """[FNO-GROWTH] A risk cut reduces size; it must not silently refuse every trade."""
    full = plan_single_leg_entry(signal(), chain(), "REGIME_1_NORMAL", NOW, state(pool=214_000.0))
    assert full.accepted and full.lots >= 1
    for multiplier in (0.5, 0.25):
        cut = plan_single_leg_entry(signal(), chain(), "REGIME_1_NORMAL", NOW,
                                    state(pool=214_000.0, risk_multiplier=multiplier))
        assert cut.accepted, cut.reject_reason
        assert 1 <= cut.lots <= full.lots
    # A pool too small for one lot at the normal budget still declines.
    tiny = plan_single_leg_entry(signal(), chain(), "REGIME_1_NORMAL", NOW,
                                 state(pool=40_000.0, risk_multiplier=0.25))
    assert not tiny.accepted and tiny.reject_reason == "pool_below_min_viable"
