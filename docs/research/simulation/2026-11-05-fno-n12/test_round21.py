from datetime import date, timedelta

import round21 as study


def test_relative_return_uses_six_prior_closes_and_no_future():
    days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(9)]
    data = {"nifty": {d: 100. + i for i, d in enumerate(days)}, "equal": {d: 100. + 2 * i for i, d in enumerate(days)}}
    reference = study.prior_return(data, days, days[6])
    assert reference is not None and reference[1] > 0
    data["equal"][days[6]] *= 999.
    assert study.prior_return(data, days, days[6]) == reference
    del data["equal"][days[3]]
    assert study.prior_return(data, days, days[6]) is None


def test_current_outcome_does_not_enter_either_fit():
    days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(62)]
    rows = [(d, (1., i / 100, (-1.)**i, (-1.)**(i//2)), i / 100, i) for i, d in enumerate(days)]
    base = study.scores(rows)["2025"][0]
    day, inputs, _, _ = rows[60]
    changed = study.scores([*rows[:60], (day, inputs, 100000., 42.)])["2025"][0]
    assert base[2:4] == changed[2:4]
    assert base[1] != changed[1]
