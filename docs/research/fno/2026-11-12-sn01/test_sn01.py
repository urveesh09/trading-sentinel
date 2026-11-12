"""SN01 tests: causality, fill rules, day stops, charges, wallet ledger."""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sn01_ledger as LG  # noqa: E402
import sn01_search as SR  # noqa: E402
import sn01_sim as M  # noqa: E402

N = 375


def synthetic(seed=1, premium=100.0, option_path=None):
    rng = np.random.default_rng(seed)
    c = 25000 + np.cumsum(rng.normal(0, 6, N))
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) + rng.random(N) * 3
    l = np.minimum(o, c) - rng.random(N) * 3
    idx = np.vstack([o, h, l, c, np.zeros(N)])
    fut = np.vstack([o + 50, h + 50, l + 50, c + 50, rng.integers(1000, 5000, N).astype(float)])
    opts = {}
    for strike in range(24500, 25550, 50):
        for opt in ("CE", "PE"):
            path = option_path if option_path is not None else premium + np.cumsum(rng.normal(0, 1, N))
            path = np.maximum(path, 1.0)
            po = np.concatenate([[path[0]], path[:-1]])
            opts[(strike, opt)] = np.vstack([po, np.maximum(po, path) + 0.5, np.minimum(po, path) - 0.5, path,
                                             np.full(N, 100.0)]).astype(np.float32)
    return {"day": "2026-03-03", "expiry": "2026-03-05", "index": idx, "future": fut, "options": opts,
            "prev": (25000.0, 25100.0, 24900.0, 25000.0), "prev_days": [(25000.0, 25100.0, 24900.0, 25000.0)] * 25}


ALL_FAMILIES = [
    {"kind": "ORB", "n": 15, "buf": 0.25}, {"kind": "MOMO", "k": 3, "z": 1.0, "vwap": True},
    {"kind": "TPB", "fast": 9, "slow": 21, "look": 5, "touch": 0.25}, {"kind": "VWAPX", "fast": 9, "buf": 0.0},
    {"kind": "EMAX", "fast": 5, "slow": 21}, {"kind": "FADE", "z": 3.0}, {"kind": "PDX", "buf": 0.0},
    {"kind": "RANDOM", "p": 0.05, "seed": 7},
]


@pytest.mark.parametrize("fam", ALL_FAMILIES, ids=lambda f: f["kind"])
def test_signals_are_causal(fam):
    s = synthetic(3)
    base = M.signals(M.features(s), {"families": [fam], "bias": "none"}, 20260303)
    for cut in (40, 150, 300):
        t = synthetic(3)
        rng = np.random.default_rng(99)
        for arr in (t["index"], t["future"]):
            arr[:4, cut + 1:] += rng.normal(0, 40, (4, N - cut - 1))
        t["future"][4, cut + 1:] = rng.integers(1, 99999, N - cut - 1)
        other = M.signals(M.features(t), {"families": [fam], "bias": "none"}, 20260303)
        assert np.array_equal(base[: cut + 1], other[: cut + 1]), (fam["kind"], cut)


def _genome(**kw):
    g = {"families": [{"kind": "RANDOM", "p": 1.0, "seed": 1}], "bias": "calls", "offset": 0, "max_lots": 1,
         "cash": 1.0, "stop": 0.10, "target": 0.10, "hold": 60, "trail_act": 0.0, "trail_give": 0.5, "max_trades": 1,
         "start": 1, "last_entry": 330, "lock": 0.0}
    g.update(kw)
    return g


def test_stop_wins_when_both_levels_touch_in_one_minute():
    path = np.full(N, 100.0)
    s = synthetic(1, option_path=path)
    for a in s["options"].values():
        a[1, 3] = 130.0   # minute 3: high far above the target ...
        a[2, 3] = 70.0    # ... and low far below the stop
    S = M.Session(s)
    r = M.run_day(S, _genome(), 15000, 1500, 3000, record=True)
    assert r["detail"][0]["reason"] == "stop"
    assert r["detail"][0]["i"] == 1 and r["detail"][0]["j"] == 3


def test_day_target_ends_the_day_and_is_net_of_charges():
    path = np.concatenate([np.full(10, 100.0), np.linspace(100, 200, N - 10)])
    s = synthetic(1, option_path=path)
    S = M.Session(s)
    g = _genome(target=1.0, stop=0.30, max_trades=20, max_lots=2)
    r = M.run_day(S, g, 15000, 1500, 3000, record=True)
    assert r["end"] == "target"
    assert r["net"] >= 1500 - 1e-6
    assert r["net"] < 1500 + 2 * 65 * 0.5   # the limit sells at the target price, not above it


def test_loss_limit_caps_the_day_when_prices_move_smoothly():
    path = np.concatenate([np.full(5, 150.0), np.linspace(150, 5, N - 5)])
    s = synthetic(1, option_path=path)
    S = M.Session(s)
    g = _genome(stop=0.05, max_trades=50, hold=500, max_lots=1)
    r = M.run_day(S, g, 15000, 1500, 3000)
    assert -3000 - 60 <= r["net"] < 0


def test_charges_match_the_shipped_model():
    from fno_costs import calc_fno_costs
    assert abs(M.charges(100.0, 110.0, 65) - calc_fno_costs(100.0, 110.0, 65)) < 1e-9


def test_bid_ask_match_the_year_dataset_model():
    sys.path.insert(0, str(M.ROOT / "docs/research/fno/2026-10-29-year-genome"))
    import yeardata
    for p in (12.3, 49.95, 99.1, 140.0, 199.95, 260.0, 512.35):
        b, a = yeardata.bid_ask(p)
        assert (M.bid_of(p), M.ask_of(p)) == (b, a)
        assert abs(M._bid_vec(np.array([p]))[0] - b) < 1e-9


def test_ledger_steps_wallet_after_a_full_wallet_of_net_profit(monkeypatch):
    nets = iter([1500.0] * 10 + [-3000.0] + [1500.0] * 30)

    def fake(S, g, wallet, target, loss, stress, record=False):
        return {"day": S.day, "net": next(nets), "trades": 1, "end": "target"}

    class S:
        day = "x"
    monkeypatch.setattr(M, "run_day", fake)
    r = LG.play([S()] * 41, {}, "every2", 0.0)
    # 10 x 1500 = 15,000 -> wallet 22,500; then -3,000 and 30 x 1,500 = 42,000 -> one more step (needs 22,500)
    assert r["wallet_steps"] == 2
    assert r["final_wallet"] == round(15000 * 1.5 * 1.5)
    assert r["refilled"] == 3000
    assert LG.target_for("every2", 1, 22500) == 1500 and LG.target_for("every2", 2, 33750) == 2250
    assert LG.target_for("every3", 2, 33750) == 1500 and LG.target_for("every3", 3, 50625) == 2250


def test_genomes_round_trip_and_mutate_inside_the_space():
    rng = random.Random(5)
    for null in (False, True):
        for _ in range(200):
            g = SR.random_genome(rng, null)
            m = SR.mutate(g, rng)
            for x in (g, m):
                assert x["null"] == null
                assert x["start"] < x["last_entry"]
                assert all((f["kind"] == "RANDOM") == null for f in x["families"])
                assert SR.key(x) == SR.key(SR.normalise(x))
