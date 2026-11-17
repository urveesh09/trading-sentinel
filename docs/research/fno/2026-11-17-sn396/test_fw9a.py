"""SN396 C fixtures for fw7b / fw9a (synthetic only; run: python -m pytest test_fw9a.py -q)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3] / "python-engine"))
import fw7b  # noqa: E402  (puts sn381 / sn351 / sn301 on the path)
import fw7a  # noqa: E402
import fw9a  # noqa: E402


def test_limit_counts_only_levels_at_or_below_the_cap():
    prices, qtys = [100.0, 100.15, 0, 0, 0], [64, 1, 0, 0, 0]
    assert abs(fw7a.walk_cost(prices, qtys, 65) - 100.0023) < 1e-3          # the old rule: VWAP 100.0023 <= 100.10, "filled"
    px, got = fw7b.legal_walk(prices, qtys, 65, 100.10)
    assert px is None and got == 64                                          # only 64 units were offered at or below the limit


def test_stale_or_skewed_straddle_has_no_reading():
    ce = {"t": np.array([59.0]), "ok": np.array([True]), "bid": np.array([99.0]), "ask": np.array([101.0])}
    pe = {"t": np.array([-50.0]), "ok": np.array([True]), "bid": np.array([79.0]), "ask": np.array([81.0])}
    assert fw9a.straddle_mids(ce, pe, 60.0) is None                         # fw9 took 100 / 80 here
    pe2 = {"t": np.array([58.5]), "ok": np.array([True]), "bid": np.array([79.0]), "ask": np.array([81.0])}
    assert fw9a.straddle_mids(ce, pe2, 60.0) == (100.0, 80.0)


def test_exact_zero_gap_is_no_signal():
    assert fw7b.side_of(0.0) is None and fw7b.side_of(None) is None
    assert fw7b.side_of(0.001) == "CE" and fw7b.side_of(-0.001) == "PE"
    g = 0.0
    assert ("CE" if g > 0 else "PE") == "PE"                                 # fw7a's rule sent it to the put side


class FakeDay:
    def __init__(self, D, lot=65):
        self.D, self.lot = D, lot


def book(ts, asks, askq, bids, bidq, ok):
    n = len(ts)
    A, AQ, B, BQ = (np.zeros((5, n)) for _ in range(4))
    for k in range(n):
        A[: len(asks[k]), k], AQ[: len(askq[k]), k] = asks[k], askq[k]
        B[: len(bids[k]), k], BQ[: len(bidq[k]), k] = bids[k], bidq[k]
    return {"t": np.array(ts, float), "ok": np.array(ok), "asks": A, "askq": AQ, "bids": B, "bidq": BQ,
            "ask": A[0], "bid": B[0], "a5": AQ.sum(0), "b5": BQ.sum(0)}


def test_pending_partial_then_fill_and_partial_only_miss():
    d = book([60.6, 61.0], [[100.0, 100.15], [100.05]], [[64, 1], [65]], [[99.0], [99.0]], [[65], [65]], [True, True])
    got, why, partials = fw7b.entry_legal(FakeDay({"x": d}), "x", 60.0, 100.10)
    assert why == "filled" and partials == 1 and got[0] == 1 and abs(got[1] - 100.05) < 1e-9
    d2 = book([60.6, 61.0], [[100.0, 100.15], [100.0, 100.20]], [[64, 1], [30, 35]], [[99.0], [99.0]], [[65], [65]], [True, True])
    got, why, partials = fw7b.entry_legal(FakeDay({"x": d2}), "x", 60.0, 100.10)
    assert got is None and why == "partial_only" and partials == 2


def test_unresolved_exit_is_recorded_per_stress():
    ts = [60.6, 70.0] + [80.0 + 10 * k for k in range(20)] + [3720.0]
    n = len(ts)
    asks = [[100.0]] * n
    askq = [[65]] * n
    bids = [[99.0], [59.5]] + [[59.0]] * 20 + [[90.0]]
    bidq = [[65], [65]] + [[65]] * 20 + [[65]]
    ok = [True, True] + [False] * 20 + [True]
    day = FakeDay({"x": book(ts, asks, askq, bids, bidq, ok)})
    r = fw7b.trade_legal(day, "x", 60.0, 3600.0, 100.10)
    assert r["status_by_stress"]["400"] == "unresolved"                      # the Rs 400 mark hits the stop at t = 70; no bid follows
    assert r["status_by_stress"]["205"] in ("on_time", "late")              # the Rs 205 position is held and exits at 3720
    assert r["unresolved_any"] and fw7b.state_of(r) == "UNRESOLVED"
    assert r["net400"] < -6500 + 1                                           # the whole premium (100 x 65) lost plus charges and stress


def test_previous_exchange_session_and_holiday_list():
    import market_calendar
    assert fw9a.HOLIDAYS == {d.isoformat() for d in market_calendar.NSE_HOLIDAYS_STATIC}
    assert fw9a.prev_exchange_session("2026-11-25") == "2026-11-23"          # Nov 24 is a holiday
    assert fw9a.prev_exchange_session("2026-11-11") == "2026-11-09"          # Nov 10 is a holiday
    assert fw9a.prev_exchange_session("2026-11-16") == "2026-11-13"          # the weekend


def test_fresh_at_respects_age_and_validity():
    t = np.array([10.0, 58.5, 59.5])
    ok = np.array([True, True, False])
    assert fw9a.fresh_at(t, ok, 60.0) == 1
    assert fw9a.fresh_at(t, ok, 61.0) is None                               # 2.5 s old
    assert fw9a.fresh_at(t, None, 60.0) == 2
