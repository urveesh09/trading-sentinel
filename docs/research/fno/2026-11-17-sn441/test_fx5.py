"""SN444 fixtures: CONFIRM-5 needs persistence observed across the whole window (the auditor's one-packet failure)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fx5  # noqa: E402


def book(times, asks=None, depth=130.0):
    n = len(times)
    return {"t": np.array(times, dtype=float), "ok": np.ones(n, bool), "ask": np.array(asks if asks else [100.0] * n),
            "a5": np.full(n, depth)}


def test_single_packet_at_0_9s_is_not_confirmed():
    ok, why = fx5.confirmed(book([100.9]), 100.0, 100.0, 65)
    assert not ok and why == "window_end_unobserved"


def test_gap_over_two_seconds_fails():
    ok, why = fx5.confirmed(book([100.5, 101.5, 104.0]), 100.0, 100.0, 65)
    assert not ok and why == "gap_inside_window"


def test_late_first_packet_fails():
    ok, why = fx5.confirmed(book([102.5, 103.5, 104.5]), 100.0, 100.0, 65)
    assert not ok and why == "late_first_packet"


def test_full_window_passes():
    ok, why = fx5.confirmed(book([100.5, 101.5, 102.5, 103.5, 104.5]), 100.0, 100.0, 65)
    assert ok and why == "confirmed"


def test_ask_rise_fails():
    ok, why = fx5.confirmed(book([100.5, 101.5, 102.5, 103.5, 104.5], [100, 100, 100.05, 100, 100]), 100.0, 100.0, 65)
    assert not ok and why == "ask_rose_or_thin"


def test_thin_depth_fails():
    ok, why = fx5.confirmed(book([100.5, 101.5, 102.5, 103.5, 104.5], depth=40.0), 100.0, 100.0, 65)
    assert not ok


def test_passive_fills_only_on_trade_through():
    d = {"t": np.array([100.5, 101.0, 102.0]), "ok": np.ones(3, bool), "ask": np.array([100.0, 100.0, 99.0]),
         "asks": np.array([[100.0, 100.0, 99.0]] + [[0, 0, 0]] * 4), "askq": np.array([[65, 65, 65]] + [[0, 0, 0]] * 4),
         "ltp": np.array([99.5, 99.5, 99.5])}
    assert fx5.passive_fill(d, 100.0, 99.0, 65) == 2          # the ask reached the limit with a lot
    d2 = dict(d, ask=np.array([100.0, 100.0, 100.0]), asks=np.array([[100.0] * 3] + [[0] * 3] * 4), ltp=np.array([99.5, 98.9, 98.9]))
    assert fx5.passive_fill(d2, 100.0, 99.0, 65) == 1         # a trade printed strictly below the limit
    d3 = dict(d2, ltp=np.array([99.5, 99.5, 99.5]))
    assert fx5.passive_fill(d3, 100.0, 99.0, 65) is None      # nothing traded through
