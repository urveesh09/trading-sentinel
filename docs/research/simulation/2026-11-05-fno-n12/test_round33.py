from datetime import date, timedelta
import math

import pytest

from round33 import MARKS, feature_row, walk


def test_basis_features_cancel_a_constant_same_session_level():
    cash = [20000. + i for i in range(len(MARKS))]
    future = [c * 1.003 for c in cash]
    assert feature_row(cash, future)[-2:] == pytest.approx((0., 0.))
    future[-1] *= 1.001
    assert feature_row(cash, future)[-2:] == pytest.approx((math.log(1.001), math.log(1.001)))


def test_same_day_target_cannot_change_its_prediction_or_price_gate():
    start = date(2024, 1, 1)
    rows = [((start + timedelta(days=i)).isoformat(), (1., i / 500., i % 2, i % 3, i % 5),
             i / 1000., 10., 20000.) for i in range(61)]
    original, = walk(rows)["2024"]
    day, features, _target, _points, decision_price = rows[-1]
    rows[-1] = day, features, 42., -90., decision_price
    changed, = walk(rows)["2024"]
    assert changed[1:3] != original[1:3]
    assert changed[3:] == original[3:]
