from datetime import date, datetime
import math
from types import SimpleNamespace

import pytest

import round19 as study


def test_forecast_ratio_changes_only_scale_and_is_bounded():
    assert study.trail_scale(None) == 1.
    assert study.trail_scale((-4., -4.)) == 1.
    assert study.trail_scale((-4., -4. + 2. * math.log(1.1))) == pytest.approx(1.1)
    assert study.trail_scale((-4., -2.)) == 1.2
    assert study.trail_scale((-4., -6.)) == .8


def test_two_sided_costed_price_hurdle_uses_actual_paid_debit():
    now = datetime.fromisoformat("2026-02-02T10:00:59+05:30")
    expiry = date(2026, 2, 4)
    pair = []
    for token, right in enumerate(("CE", "PE"), 1):
        contract = SimpleNamespace(token=token, strike=24000., expiry=expiry, instrument_type=right)
        mid = study.black76_price(24000., 24000., study.years_to_expiry(expiry, now), .12,
                                  study.RISK_FREE_RATE, right == "CE")
        pair.append(SimpleNamespace(contract=contract, mid=mid, ask=mid + .5, bid=mid - .5))
    asks = {q.contract.token: q.ask for q in pair}
    move, nets = study.price_test(pair, asks, 24010., now, math.log(.04))
    assert move > 0 and min(nets) > 350.
    _, smaller_nets = study.price_test(pair, {k: v + 100. for k, v in asks.items()}, 24010., now, math.log(.04))
    assert max(smaller_nets) < 0.
