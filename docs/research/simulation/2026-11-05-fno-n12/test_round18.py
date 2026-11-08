from datetime import date, timedelta

import round18 as study


def test_official_input_excludes_same_day_and_future():
    days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(24)]
    closes = {d: {"nifty": 100 + i, "vix": 12.} for i, d in enumerate(days)}
    baseline = study.official_features(closes, days, days[22])
    assert baseline is not None
    closes[days[22]] = closes[days[23]] = {"nifty": 1e9, "vix": 999.}
    assert study.official_features(closes, days, days[22]) == baseline
    closes[days[21]]["vix"] = None
    assert study.official_features(closes, days, days[22]) is None


def test_forecast_does_not_use_current_target_or_following_days():
    days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(90)]
    rows = [(day, .01 + i / 50000, (-4. + i / 300, .4 + (-1)**i / 30)) for i, day in enumerate(days)]
    reference = study.score(rows)["2025"][0]
    i = days.index(reference["day"])
    rows[i] = (days[i], 100., rows[i][2])
    other = study.score(rows[:i+1])["2025"][0]
    assert other["realized"] != reference["realized"]
    for name in ("realized_only_log_forecast", "implied_log_forecast"):
        assert other[name] == reference[name]
