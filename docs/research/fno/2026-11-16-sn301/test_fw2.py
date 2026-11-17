"""SN302 acceptance: synthetic books give the declared outcomes (PLAN.md). Also reproduces the auditor's defects in the
original fw.hold, which stays frozen. Run: python -m pytest -q test_fw2.py (research venv)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fw2  # noqa: E402

LOT = 65


class FakeDay:
    def __init__(self, D):
        self.D, self.lot, self.offset = D, LOT, 0.6


def book(rows):
    """rows: (t, bid, ask, bid_qty, ask_qty[, lag]) -> one instrument's arrays (single level; levels 2-5 empty)."""
    n = len(rows)
    t = np.array([r[0] for r in rows], float)
    bid = np.array([r[1] for r in rows], float)
    ask = np.array([r[2] for r in rows], float)
    bq = np.array([r[3] for r in rows], float)
    aq = np.array([r[4] for r in rows], float)
    lag = np.array([r[5] if len(r) > 5 else 0.6 for r in rows], float)
    z = np.zeros((4, n))
    d = {"t": t, "ltp": (bid + ask) / 2, "lag": lag, "bid": bid, "ask": ask, "bq": bq, "aq": aq, "b5": bq, "a5": aq,
         "bids": np.vstack([bid, z]), "asks": np.vstack([ask, z]), "bidq": np.vstack([bq, z]), "askq": np.vstack([aq, z])}
    d["ok"] = (bid > 0) & (ask > 0) & (ask > bid) & ((lag - 0.6) <= fw2.FRESH)
    return d


def day_of(rows):
    return FakeDay({1: book(rows)})


def steady(t0, t1, bid=100.0, ask=100.5, q=650, step=1.0):
    return [(t, bid, ask, q, q) for t in np.arange(t0, t1, step)]


def test_zero_ask_depth_is_missed():
    day = day_of([(10.0, 100, 100.5, 650, 650), (10.7, 100, 100.5, 650, 0), (11.6, 100, 100.5, 650, 30), (13.0, 100, 100.5, 650, 650)])
    got, why = fw2.entry(day, 1, 10.0)
    assert got is None and why == "no_depth"           # the 13.0 packet is outside 0.5-2.5 s


def test_entry_walks_levels_and_waits_for_depth():
    day = day_of([(10.7, 100, 100.5, 650, 0), (11.2, 100, 100.6, 650, 650)])
    got, why = fw2.entry(day, 1, 10.0)
    assert why == "filled" and got[1] == pytest.approx(100.6)


def test_crossed_and_stale_books_are_not_fills():
    day = day_of([(10.6, 101, 100.5, 650, 650), (11.0, 100, 100.5, 650, 650, 4.0), (11.5, 100, 100.5, 650, 650)])
    got, why = fw2.entry(day, 1, 10.0)
    assert why == "filled" and day.D[1]["t"][got[0]] == pytest.approx(11.5)


def test_same_frame_packet_is_not_used():
    day = day_of([(10.0, 100, 99.0, 650, 650), (10.0, 100, 100.5, 650, 650), (12.8, 100, 100.5, 650, 650)])
    got, why = fw2.entry(day, 1, 10.0)
    assert got is None and why == "no_packet"


def test_exit_needs_bid_depth_and_is_late_or_unresolved():
    rows = steady(0, 70) + [(70.6, 100.0, 100.5, 0, 650), (75.0, 100.0, 100.5, 10, 650), (95.0, 101.0, 101.5, 650, 650)]
    day = day_of(rows)
    px, tx, st = fw2.exit_at(day, 1, 70.0)
    assert px == pytest.approx(101.0) and tx == pytest.approx(95.0) and st == "late"
    day2 = day_of(steady(0, 70) + [(70.6, 100.0, 100.5, 0, 650), (300.0, 100.0, 100.5, 650, 650)])
    assert fw2.exit_at(day2, 1, 70.0)[2] == "unresolved"


def test_missing_exit_books_the_whole_premium():
    day = day_of(steady(0, 30))
    got, _ = fw2.entry(day, 1, 5.0)
    h = fw2.hold(day, 1, got[0], got[1], day.D[1]["t"][got[0]] + 60, 205.0)
    assert h["status"] == "unresolved"
    assert h["net"] == pytest.approx(-100.5 * LOT - fw2.charges(100.5, 0.0, LOT) - 205.0)


def test_stop_is_causal_and_slips():
    rows = steady(0, 20) + [(20.0, 52.0, 52.5, 650, 650), (20.3, 50.0, 50.5, 650, 650), (20.9, 45.0, 45.5, 650, 650)] + steady(21.5, 90, 45, 45.5)
    day = day_of(rows)
    got, _ = fw2.entry(day, 1, 5.0)
    k, px = got
    h = fw2.hold(day, 1, k, px, day.D[1]["t"][k] + 60, 205.0)
    assert h["why"] == "stop"
    # triggered at 20.0 (bid 52 -> net about -3,200), executed from 20.5: the 20.9 packet at 45 (slippage booked)
    assert h["px_out"] == pytest.approx(45.0) and h["net"] < -3000 - 6 * LOT


def test_original_fw_hold_defects_reproduced():
    """The frozen fw.hold sells a lot into a bid with zero quantity, and books the last packet before the planned exit."""
    import fw
    rows = steady(0, 30) + [(30.0, 120.0, 120.5, 0, 650)]
    day = day_of(rows)
    day.D[1]["aq"][:] = 650
    k = 6
    net, tx, why = fw.hold(day, 1, k, 6.0 + 60, 205.0)
    assert why == "end" and tx == pytest.approx(30.0)                  # planned exit at 66 s was never observed
    assert net > 0                                                     # booked at the zero-quantity bid of 120
    h = fw2.hold(day, 1, k, float(day.D[1]["ask"][k]), 66.0, 205.0)
    assert h["status"] == "unresolved" and h["net"] < -6000


# ---- SN300a: the verdict cannot pass on missing evidence (the auditor's fixture) ----------------------------------------
import fwd2  # noqa: E402


def _fixture(label="FLAT", pairs=True, n_days=20, per_day=2, net=500.0):
    days = [f"2026-12-{i + 1:02d}" for i in range(n_days)]
    res, labels = {}, {}
    for d in days:
        cand = [{"missed": False, "net205": net, "net400": net - 200, "fill_t": 3600.0 + 300 * k, "tx": 3660.0 + 300 * k,
                 "debit": 9000.0, "status": "on_time", "entry_lat": {}, "exit_lat": {}} for k in range(per_day)]
        pr = [{"cand_missed": False, "ctrl_missed": False, "cand205": net, "ctrl205": 0.0}] * per_day if pairs else []
        res[d] = {"v2": {"SN291": {"candidate": cand, "pairs": pr}}}
        labels[d] = {"label": label, "wallet_before": 30000.0, "positions": []}
    return days, res, labels


def test_verdict_unknown_gold_days_are_insufficient():
    q, res, labels = _fixture(label="UNKNOWN")
    out, _ = fwd2.slot_verdict("SN291", q, res, labels)
    assert out["verdict"] == "INSUFFICIENT"


def test_verdict_empty_control_is_insufficient():
    q, res, labels = _fixture(pairs=False)
    out, _ = fwd2.slot_verdict("SN291", q, res, labels)
    assert out["verdict"] == "INSUFFICIENT" and out["pairs"] == 0


def test_verdict_clean_positive_fixture_passes_and_losing_one_fails():
    q, res, labels = _fixture()
    assert fwd2.slot_verdict("SN291", q, res, labels)[0]["verdict"] == "PASS"
    q, res, labels = _fixture(net=-100.0)
    assert fwd2.slot_verdict("SN291", q, res, labels)[0]["verdict"] == "FAIL"


def test_wallet_contract_blocks_unaffordable_debit():
    q, res, labels = _fixture()
    for d in q:
        for r in res[d]["v2"]["SN291"]["candidate"]:
            r["debit"] = 16000.0                                   # > 30,000 - 15,000
    out, _ = fwd2.slot_verdict("SN291", q, res, labels)
    assert out["wallet_admitted"] == 0 and out["verdict"] == "FAIL" and out["fits_strict_3000_debit"] == 0
