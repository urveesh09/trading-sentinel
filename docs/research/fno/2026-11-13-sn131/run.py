"""Shared policy runner for SN132-SN140 (frozen with PLAN.md): thresholds per quarter from the nested validation."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sm  # noqa: E402

TARGETS = [f"{o}{h}" for o in sm.SIDES for h in sm.HZ]
GROSS = [f"{o}{h}g" for o in sm.SIDES for h in (5, 15, 30)]
GF = sm.FEATURES.index("gold_free")


def cached_wf(name, data, targets, **kw):
    p = sm.LOCAL / f"wf_{name}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    out = sm.walk_forward(data, targets, **kw)
    p.write_bytes(pickle.dumps(out))
    return out


def submask(data, which):
    m = np.ones(len(data["day"]), bool)
    if which == "gold-free":
        m &= data["X"][:, GF] == 1.0
    return m


def policy(data, preds, val, which="all days", room=3000.0, thetas=None, choices=None, stress_shift=0.0, late=False, lots=None):
    sub = submask(data, which)
    day = data["day"]
    nets, trades, chosen = {}, [], {}
    for q0, q1 in zip(sm.QUARTERS, sm.QUARTERS[1:]):
        test = (day >= q0) & (day < q1) & sub
        if not test.any():
            continue
        if thetas is not None:
            th = thetas[q0]
        else:
            vq = {}
            for t, (vm, p) in val[q0].items():
                if choices is None or t in choices:
                    vq[t] = (vm & sub, p[sub[vm]])
            th, _v = sm.choose_theta(data, vq, room, choices)
        chosen[q0] = th
        n, tr = sm.simulate(data, preds, test, th, room, choices, stress_shift, late, lots)
        nets.update(n)
        trades += tr
    return nets, trades, chosen
