"""Fixtures for goldx's switches (run: python test_goldx.py). Synthetic sessions only; no market data."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import goldx  # noqa: E402

M, L, gw = goldx.M, goldx.L, goldx.gw
N = 380


def session(c):
    c = np.asarray(c, float)
    return SimpleNamespace(day="2099-01-01", F={"c": c, "atr": np.full(N, 10.0)})


def option(bid):
    bid = np.asarray(bid, float)
    px = bid + 0.5
    a = np.vstack([px, px, px, px])
    tr = np.ones(N, bool)
    return (a, bid.copy(), bid.copy(), bid.copy(), bid.copy(), bid.copy(), tr)


V = {"in_atr": 1.0, "in_full": True, "extend": False, "ext_x": 0.25, "ext_k": 3.0}


def base_paths():
    c = np.full(N, 100.0)
    bid = np.full(N, 100.0)
    c[20:] = 111.0            # +1.1 ATR at minute 20: the add
    bid[20:] = 110.0
    c[40:] = 99.0             # back through the entry level (100) at minute 40
    bid[40:] = 99.0
    bid[41:] = 98.0
    return c, bid


def walk(c, bid, v, j_n11=100, lots=1, wallet=30000.0):
    S = session(c)
    rec = option(bid)
    gw.CUR["sg"] = {"expert": "EFF", "opt": "CE", "strike": 100, "j": j_n11}
    goldx.LOG.clear()
    out = goldx.walk(S, rec, M.ask_of(100.0), lots, 10, j_n11, 1, v, 6000.0, wallet)
    return out, goldx.LOG[-1]


def test_failed_add_sells_only_the_add():
    c, bid = base_paths()
    (net, j, px), log = walk(c, bid, {**V, "fail_theta": 0.0})
    assert log["adds"] and log["adds"][0]["added"] >= 1
    f = log["fail"]
    assert f is not None and f["j_sig"] == 40 and f["j_exec"] == 41 and f["px"] == 98.0
    assert f["lots"] == log["adds"][0]["added"]
    assert len(log["pieces"]) == 1 and log["pieces"][0][1] == 1          # the original lot stays to the N11 exit
    assert j == 100 and log["reason"] == "n11"


def test_off_equals_gold_walk():
    c, bid = base_paths()
    (net, j, px), _ = walk(c, bid, V)
    S, rec = session(c), option(bid)
    gw.CUR["sg"] = {"expert": "EFF", "opt": "CE"}
    ref = gw.walk(S, rec, M.ask_of(100.0), 1, 10, 100, 1, {**V, "cash": "mtm"}, 6000.0, 30000.0)
    assert abs(ref[0] - net) < 1e-9 and ref[1] == j and ref[2] == px


def test_full_exit_takes_precedence():
    c, bid = base_paths()
    (net, j, px), log = walk(c, bid, {**V, "fail_theta": 0.0}, j_n11=41)   # N11 exits the whole position at minute 41
    assert log["fail"] is None and j == 41 and len(log["pieces"]) == 2


def test_stop_takes_precedence():
    c, bid = base_paths()
    bid[41:] = 1.0                                                        # the bid collapses through any stop at 41
    (net, j, px), log = walk(c, bid, {**V, "fail_theta": 0.0})
    assert log["fail"] is None and log["reason"] == "stop" and j == 41


def test_no_add_no_rule():
    c, bid = base_paths()
    c[20:40] = 105.0                                                      # never +1 ATR: no add
    (net0, j0, _), _ = walk(c, bid, V)
    (net1, j1, _), log = walk(c, bid, {**V, "fail_theta": 0.0})
    assert log["fail"] is None and abs(net0 - net1) < 1e-9 and j0 == j1


def test_no_add_experts_and_close_stop():
    c, bid = base_paths()
    (_n, _j, _p), log = walk(c, bid, {**V, "no_add": frozenset({"EFF"})})
    assert not log["adds"]
    bid2 = np.full(N, 100.0)
    bid2[30] = 1.0                                                        # a one-minute touch: bar-low stops, close rule also (close = 1)
    (_n, j, _p), log = walk(np.full(N, 100.0), bid2, {**V, "stop_rule": "close"})
    assert log["reason"] == "stop" and j == 30 and log["px"] == 1.0


if __name__ == "__main__":
    goldx.install()
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
