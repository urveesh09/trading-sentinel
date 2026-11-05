from datetime import date, timedelta
import math

import pytest

from round28 import ACTIVITY, activity, strikes_at, walk


def test_chain_activity_keeps_all_strike_identities_fixed():
    strikes = strikes_at(10009.)
    assert strikes == (9950, 10000, 10050)
    cells = {(at, strike, right): (10., 2 if right == "CE" else 1, 100.)
             for at in ACTIVITY for strike in strikes for right in ("CE", "PE")}
    for strike in strikes:
        cells[(ACTIVITY[-1], strike, "CE")] = (10., 2, 200.)
    assert activity(cells, strikes) == pytest.approx((math.log(2.), math.log(2.)))
    del cells[(ACTIVITY[12], strikes[0], "PE")]
    assert activity(cells, strikes) is None


def test_first_outcome_never_trains_its_own_prediction():
    rows = [((date(2024, 1, 1) + timedelta(days=i)).isoformat(), (1., i / 100., i % 3, i % 2),
             i / 1000., 2., 20000.) for i in range(61)]
    old = walk(rows)["2024"][0]
    day, features, _, points, entry = rows[-1]
    rows[-1] = (day, features, 9., points, entry)
    new = walk(rows)["2024"][0]
    assert old[1] != new[1]
    assert old[-2:] == new[-2:]
