from datetime import datetime

import pandas as pd
import pytest

import round20 as study


def test_wing_refuses_extrapolation_and_missing_neighbor():
    strikes = [23750., 23800., 23850., 23900., 23950., 24000., 24050.]
    assert study.neighbors(strikes, 23904., 24000., "PE") == (23900., 23950.)
    assert study.neighbors(strikes, 23900., 24000., "PE") == (23900.,)
    assert not study.neighbors(strikes, 23964., 24000., "PE")
    assert not study.neighbors([23850., 23950.], 23900., 24000., "PE")


def test_next_observation_uses_only_complete_bars_and_risk_bound():
    now = datetime.fromisoformat("2026-11-05T10:16:59+05:30")
    dates = pd.date_range("2026-11-05 09:40", periods=8, freq="5min")
    rows = [(106., 96., 100.)] * 7 + [(140., 3., 135.)]
    frame = pd.DataFrame(rows, columns=["high", "low", "close"], index=dates)
    signal = study.trade_signal(frame, now, 101., (1, 100., 40.))
    assert signal.bar_ts == "2026-11-05 10:10:00"
    assert signal.stop_underlying == pytest.approx(91.)
    assert signal.target_underlying == pytest.approx(121.)
    assert signal == study.trade_signal(frame.iloc[:-1], now, 101., (1, 100., 40.))
    assert study.trade_signal(frame, now, 120., (1, 100., 40.)) is None
