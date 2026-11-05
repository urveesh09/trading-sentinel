from collections import Counter
from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

import round16 as study


AT = datetime.fromisoformat("2026-02-02T11:00:59+05:30")


def test_compression_requires_completed_and_contiguous_bars():
    bars = [(10., 60., 10., 34.)] * 12 + [(34., 38., 31., 35.)] * 9
    index = pd.date_range("2026-02-02 09:15", periods=len(bars), freq="5min")
    frame = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=index)
    assert study.width_after_compression(frame, "2026-02-02", AT) == 50.
    assert study.width_after_compression(frame, "2026-02-02", AT - timedelta(minutes=1)) is None
    assert study.width_after_compression(frame.iloc[1:], "2026-02-02", AT) is None


def test_second_leg_is_not_filled_from_a_later_clock_and_reservation_rechecks():
    engine = study.StraddleReplay.__new__(study.StraddleReplay)
    engine.notes = Counter()
    engine.mark = lambda _obs, token, _now, **_kwargs: {1: 20., 2: 55.}[token]
    book = SimpleNamespace(equity=250000., entries_today=Counter())
    ticket = study.Ticket("2026-02-02", "2026-02-04", (1, 2), 100., AT)
    engine._buy(ticket, book, None, AT + timedelta(minutes=1))
    assert ticket.stage == "SECOND" and ticket.buys == {1: 20.}
    engine._buy(ticket, book, None, AT + timedelta(minutes=3))
    assert ticket.stage == "CLOSE" and ticket.reason == "straddle_abandoned"
    assert ticket.buys == {1: 20.}
    assert book.entries_today[AT.date()] == 1
    assert study.reserve((20., 55.)) < 9000.
    assert study.reserve((80., 80.)) > 9000.


def test_trade_net_charges_each_contract_and_fixed_stress():
    gross, fees, stress, net = study.amounts({1: 25., 2: 35.}, {1: 20., 2: 53.})
    assert gross == 845. and fees > 0. and stress == 400.
    assert net == pytest.approx(gross - fees - stress)
