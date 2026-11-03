"""N03: fixes from the two Nov 2 partner audits (Production evidence, 2026-11-02).

- P1: a plan prices the option on its own expiry's forward, not the monthly future's.
- L1/L2: every stop moved down is told; a stop still in profit gives back profit, it adds to no loss.
- C1: the close countdown is the time left when the message is built.
- R1, E1, K1, K2: in test_partner_watch, test_partner_buyer and test_partner_coach.
"""
from datetime import date, datetime, timedelta

import pandas as pd
import pytest
import pytz

import partner_watch as pw

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 11, 2, 10, 37, 33))


def _fut_bars(level: float) -> pd.DataFrame:
    idx = pd.date_range("2026-11-02 09:15", periods=17, freq="5min")
    return pd.DataFrame({"open": level, "high": level + 40.0, "low": level - 40.0, "close": level}, index=idx)


def _plan(opt_type="CE", entry=329.3, mid=327.45, strike=75800.0, **kw) -> pw.Plan:
    return pw.build_plan(entry=entry, qty=20, exchange="BFO", opt_type=opt_type, strike=strike,
                         expiry=date(2026, 11, 5), now=NOW, bought_at=NOW - timedelta(seconds=1), cash=28528.8,
                         option_bars=None, fut_bars=_fut_bars(75711.05), fut_price=75711.05, option_mid=mid, **kw)


def test_a_call_plan_is_priced_on_the_options_own_forward():
    """Nov 2, SENSEX 75800 CE (5 Nov) bought at 329.30 with the Nov 26 future at 75,711: priced on the future, the
    option's volatility read about 13% and its delta about 0.46, the stop came out too low and the target too
    high (the plan said 270.20 / 450.35; the card, priced on the chain's parity, ≈272.60 / 360-423)."""
    old = _plan()
    carry = _plan(fut_expiry=date(2026, 11, 26))
    parity = _plan(fut_expiry=date(2026, 11, 26), forward=75370.0)
    assert old.iv < 0.15                                       # the fault: a weekly priced off the monthly future
    assert 0.15 < parity.iv < 0.25 and parity.delta < old.delta
    assert parity.index_stop_option > old.index_stop_option and parity.target < old.target
    assert carry.delta < old.delta and carry.index_stop_option > old.index_stop_option and carry.target < old.target
    # The levels stay on the future, as the message names them; only the option's price at them changes.
    assert (old.stop_index, old.target_index) == (parity.stop_index, parity.target_index) == (
        carry.stop_index, carry.target_index)


def test_a_put_plan_moves_the_other_way():
    old = _plan("PE", entry=420.0, mid=419.0, strike=75700.0)
    parity = _plan("PE", entry=420.0, mid=419.0, strike=75700.0, fut_expiry=date(2026, 11, 26), forward=75370.0)
    assert parity.iv < old.iv and abs(parity.delta) > abs(old.delta)
    assert parity.index_stop_option < old.index_stop_option and parity.target > old.target


def test_the_forward_falls_back_safely():
    own, basis = pw.option_forward(75711.0, now=NOW, expiry=date(2026, 11, 5), fut_expiry=date(2026, 11, 26),
                                   forward=75370.0)
    assert basis == "PARITY" and own(75711.0) == pytest.approx(75370.0) and own(75600.0) == pytest.approx(75259.0)
    # A parity read more than 2% away is not used: carry from the future's expiry instead.
    own, basis = pw.option_forward(75711.0, now=NOW, expiry=date(2026, 11, 5), fut_expiry=date(2026, 11, 26),
                                   forward=70000.0)
    assert basis == "CARRY" and 75300.0 < own(75711.0) < 75711.0
    # Without the future's expiry (or the same expiry): as before.
    assert pw.option_forward(75711.0, now=NOW, expiry=date(2026, 11, 5))[1] == "FUTURE"
    assert pw.option_forward(75711.0, now=NOW, expiry=date(2026, 11, 26), fut_expiry=date(2026, 11, 26))[1] == "FUTURE"
    # Parity: F = K + (C - P) e^(rT); nothing without both prices.
    assert pw.parity_forward(100.0, 60.0, 23300.0, 1 / 365) == pytest.approx(23340.0, abs=0.1)
    assert pw.parity_forward(100.0, None, 23300.0, 1 / 365) is None


def test_a_stop_still_in_profit_gives_back_profit_and_is_not_called_a_loss():
    """Nov 2: "you moved your stop down ₹125 → ₹121. If it is hit: +₹2,003 instead of +₹2,522. A stop moved down
    adds to the loss you chose when you placed it." (NIFTY 23250 CE, 130 at 104.95)."""
    trip = pw.Trip("1", "NFO", "NIFTY26N0323250CE", "NRML", NOW, bought=130, buy_value=130 * 104.95)
    for reason in ("FIRST", "AGAIN"):
        text = pw.lowered_text(trip, 125.0, 121.0, reason)
        assert text.endswith("A stop moved down gives back profit it had kept for you.")
        assert "adds to the loss" not in text
    # Under the buy price the old wording stays.
    assert pw.lowered_text(trip, 100.0, 95.0, "FIRST").endswith(
        "A stop moved down adds to the loss you chose when you placed it.")


@pytest.mark.parametrize("at, said", [
    ((15, 20, 0), "20 minutes to the 15:40 close"),
    ((15, 30, 28), "9 minutes to the 15:40 close"),       # Nov 2: this one said "20 minutes"
    ((15, 38, 30), "1 minute to the 15:40 close"),
    ((15, 39, 40), "Under a minute to the 15:40 close"),
])
def test_the_close_countdown_is_the_time_left_when_sent(at, said):
    now = IST.localize(datetime(2026, 11, 2, *at))
    trip = pw.Trip("1", "NFO", "NIFTY26N0323550CE", "NRML", now, bought=130, buy_value=130 * 15.3)
    assert pw.close_text(trip, expiry_today=False, theta_day=None, now=now).startswith(f"⏳ {said} and you still hold")
    assert pw.close_text(trip, expiry_today=False, theta_day=None).startswith("⏳ 20 minutes to the 15:40 close")
