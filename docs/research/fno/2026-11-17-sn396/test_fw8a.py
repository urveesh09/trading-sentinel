"""SN400 fixtures for fw8a (synthetic only; run: python -m pytest test_fw8a.py -q). The first is the auditor's third
reproduced case: a ten-lot increment signed against a 90-second-old quote."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fw8a  # noqa: E402

T = 1_800_000_000.0


def pkt(t, v, ltp, last_qty, last_trade_ts):
    return {"recv_ns": int(t * 1e9), "volume": v, "ltp": ltp, "last_qty": last_qty, "last_trade_ts": last_trade_ts}


def test_ninety_second_old_quote_is_unsigned():
    row = pkt(T + 90, 1650, 101.0, 650, int(T + 90))
    old = (T, 99.0, 100.0, int(T))
    sgn, dv, why = fw8a.strict_sign(row, 1000, old)
    assert sgn == 0 and dv == 650 and why == "stale_quote"
    assert (1 if row["ltp"] >= old[2] > 0 else 0) == 1                     # fw8's rule signed all ten lots as a buy


def test_fresh_single_trade_is_signed_both_ways():
    q = (T, 99.0, 100.0, int(T))
    assert fw8a.strict_sign(pkt(T + 1, 1065, 100.0, 65, int(T + 1)), 1000, q)[:2] == (1, 65.0)
    assert fw8a.strict_sign(pkt(T + 1, 1065, 99.0, 65, int(T + 1)), 1000, q)[:2] == (-1, 65.0)
    assert fw8a.strict_sign(pkt(T + 1, 1065, 99.5, 65, int(T + 1)), 1000, q)[2] == "inside_spread"


def test_multi_trade_crossed_and_noncausal_are_unsigned():
    q = (T, 99.0, 100.0, int(T))
    assert fw8a.strict_sign(pkt(T + 1, 1130, 100.0, 65, int(T + 1)), 1000, q)[2] == "multi_trade"
    assert fw8a.strict_sign(pkt(T + 1, 1065, 100.0, 65, int(T + 1)), 1000, (T, 100.0, 100.0, int(T)))[2] == "crossed_or_missing"
    assert fw8a.strict_sign(pkt(T + 1, 1065, 100.0, 65, int(T - 5)), 1000, q)[2] == "noncausal"
    assert fw8a.strict_sign(pkt(T + 1, 1000, 100.0, 65, int(T + 1)), 1000, q) == (0, 0.0, None)


def test_clustered_ols_recovers_a_slope():
    import numpy as np
    rng = np.random.default_rng(0)
    x = rng.normal(size=400)
    y = 2.0 * x + rng.normal(size=400)
    b, se = fw8a.clustered_ols(y, [x], [i // 20 for i in range(400)])
    assert abs(b[1] - 2.0) < 0.2 and b[1] / se[1] > 10
