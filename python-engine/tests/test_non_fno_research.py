from non_fno_research import penny_context_gate


def _bar(open_, high, low, close, volume=100, date="2026-10-01"):
    return {"date": date, "open": open_, "high": high, "low": low, "close": close, "volume": volume}


def test_penny_context_requires_same_minute_profile_and_a_fresh_structure():
    baseline = {"accept": True}
    bars = [_bar(10, 10.2, 9.9, 10.0), _bar(10, 10.2, 9.9, 10.1), _bar(10.1, 10.5, 10.0, 10.4)]
    assert penny_context_gate(baseline, bars, [100, 110, 120, 130])["reason"] == "missing_same_minute_volume_profile"
    result = penny_context_gate(baseline, bars, [100, 110, 120, 130, 140])
    assert result["accepted"] is True
    assert result["reason"] == "fresh_breakout"


def test_penny_retest_anchors_before_confirmation_and_does_not_rechase():
    prior = _bar(10, 10.2, 9.9, 10)
    breakout = _bar(10.1, 10.5, 10, 10.4)
    retest = _bar(10.4, 10.45, 10.1, 10.3)
    result = penny_context_gate({"accept": True}, [prior, breakout, retest], [100] * 5)
    assert result["accepted"] and result["reason"] == "bounded_retest"
    assert result["anchor"] == 10.2
    chase = _bar(10.4, 10.7, 10.3, 10.6)
    result = penny_context_gate({"accept": True}, [prior, breakout, chase], [100] * 5)
    assert not result["accepted"]
