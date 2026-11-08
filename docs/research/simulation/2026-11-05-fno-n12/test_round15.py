from datetime import datetime

import pandas as pd
import pytest

import round15 as study


def fixture():
    stop = {"exit_time": "2026-02-02T10:22:01+05:30", "direction": "SHORT", "stop_underlying": 104.0}
    marks = pd.date_range("2026-02-02 09:55", "2026-02-02 10:30", freq="5min")
    rows = [(100., 105., 99., 101.)] * 6 + [(102., 110., 102., 109.), (500., 800., 1., 750.)]
    return stop, pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=marks)


def test_confirmed_break_uses_only_the_first_fully_post_stop_bar():
    stop, frame = fixture()
    at = datetime.fromisoformat("2026-02-02T10:30:59+05:30")
    assert study.candidate(stop, frame, at.replace(minute=29), 109.) is None
    assert study.candidate(stop, frame, at.replace(minute=35), 109.) is None
    signal = study.candidate(stop, frame, at, 109.)
    assert signal == study.candidate(stop, frame.iloc[:-1], at, 109.)
    assert signal.direction.value == "LONG"
    assert signal.stop_underlying < 105.0 < 109.
    assert signal.target_underlying == pytest.approx(109. + 2 * (109. - signal.stop_underlying))


def test_break_refuses_a_missing_bar_or_underlying_back_inside_range():
    stop, frame = fixture()
    at = datetime.fromisoformat("2026-02-02T10:30:59+05:30")
    assert study.candidate(stop, frame.drop(frame.index[3]), at, 109.) is None
    assert study.candidate(stop, frame, at, 104.9) is None
