"""SN411 fixtures for fw7c (synthetic only; run: python -m pytest test_fw7c.py -q). The first two are the auditor's
reproduced cases."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fw7c  # noqa: E402
import fw7a  # noqa: E402

PRE0 = 1_800_000_000.0           # today's 09:00:00
CONT0 = PRE0 + 900.0              # today's 09:15:00


def test_old_trade_in_a_new_packet_is_not_the_first_trade():
    rows = [{"t": 4.0, "ltp": 25010.0, "last_trade_ts": PRE0 - 86400.0},     # received 09:15:04, last trade yesterday
            {"t": 6.0, "ltp": 25022.0, "last_trade_ts": CONT0 + 6.0}]
    assert fw7a.auction_price(rows, 60.0, PRE0)[:2] == (25010.0, "FIRST_TRADE")   # the old rule took yesterday's price
    px, src, t, qonly = fw7c.auction_price_c(rows, 60.0, PRE0, CONT0)
    assert (px, src, t, qonly) == (25022.0, "FIRST_TRADE", 6.0, 1)


def test_no_trade_today_before_the_decision_is_no_signal():
    rows = [{"t": 4.0, "ltp": 25010.0, "last_trade_ts": PRE0 - 86400.0}, {"t": 61.0, "ltp": 25022.0, "last_trade_ts": CONT0 + 61.0}]
    assert fw7c.auction_price_c(rows, 60.0, PRE0, CONT0)[1] == "NO_SIGNAL"


def test_match_is_unchanged():
    rows = [{"t": -400.0, "ltp": 25005.0, "last_trade_ts": PRE0 + 541.0}]
    assert fw7c.auction_price_c(rows, 60.0, PRE0, CONT0)[:2] == (25005.0, "MATCH")


def test_fifty_five_second_old_book_cannot_set_the_cap():
    t = np.array([5.0])
    ok = np.array([True])
    assert fw7c.fresh_index(t, ok, 60.0) is None                           # fw7b's book_at used this packet
    assert fw7c.fresh_index(np.array([5.0, 58.5]), np.array([True, True]), 60.0) == 1
    assert fw7c.fresh_index(np.array([5.0, 58.5]), np.array([True, False]), 60.0) is None


def test_offset_uses_pre_decision_packets_only():
    t = np.array([-600.0, -300.0, 10.0, 50.0, 3600.0, 7200.0, 9000.0])
    lag = np.array([0.30, 0.31, 0.29, 0.30, 5.0, 5.0, 5.0])
    assert abs(fw7c.pre_decision_offset(t, lag) - 0.30) < 1e-9
    assert np.median(lag) == 0.31 or True                                  # the whole-day median would mix later packets
    assert fw7c.pre_decision_offset(np.array([100.0]), np.array([0.3])) is None
