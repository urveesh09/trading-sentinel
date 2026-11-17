"""SN472 (own): the power of every scheduled forward verdict (PLAN.md section 3, frozen at 83e1b444; details fixed here before
any number). SN469's books, injection and legal scorer; each verdict's own horizon and point rule. Synthetic outcomes only.

Common: a trade = one of SN441's common cells (real walked books, legal exits, Rs 3,000 stop); the candidate trades the
favoured side, which carries an injected drift delta (SN469's form); a COIN control trades a seeded random side of the same
cell (the drift reaches it only when it lands on the favoured side). delta is solved from the labels for the stated true edge.
  fw9a    eligible (CHEAP) with probability 1/3 per session, one cell; verdict at 15 fills or 60 sessions; INSUFFICIENT below
          15 fills; PASS iff the per-eligible-session mean > 0 at 205 and 400, the sum without the best day > 0, and the
          paired mean against COIN > 0 with >= 10 common fills (fw7a.judge without its ATM control: an upper bound)
  SN300a  20 sessions, every cell of the day (within-day dependence); INSUFFICIENT unless >= 30 trades, >= 10 trading
          sessions, >= 8 EMPTY-label sessions, >= 20 pairs; PASS iff the total > 0 at 205 and 400, the pair mean > 0, the total
          without the best session > 0 and the EMPTY-session net > 0 (the wallet test is approximated by the EMPTY net)
  F1      30 triggers, one cell each; PASS iff the mean > 0 at 205 and 400, the sum without the best 5 trades > 0 and the paired
          mean against COIN > 0 (the other two controls and the futures-reversal t are not modelled: an upper bound)
  fx5     60 decisions resampled from SN444's 240 Nov 16 rows (an unfilled arm = 0 for that decision); CONFIRM-5 shifted by s
          so that its mean paired difference against IMMEDIATE = e; PASS iff the mean paired difference against IMMEDIATE and
          against DELAY-5 are both > 0 at 205 and 400 (one morning's rows: their dependence is not modelled)
True edges: per market session 0 / 50 / 154 (fw9a, SN300a), per trade 0 / 50 / 154 (F1, fx5); and fw9a at the cheap
opener's development claim, SN419's +22.8k over ~210 sessions at Rs 205 (~109 a session), shrunk by SN455's median
unseen / development ratio (-0.22 x) as well. 2,000 replications each (seed 472).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn469  # noqa: E402

OUT = HERE / "results-sn472.json"
REPS = 2000
LOT = sn469.LOT


class World:
    def __init__(self):
        self.M = sn469.Machine(sn469.cells())
        self.lab = [c[2] for c in self.M.cl]
        self.tables = {}

    def tab(self, delta):
        k = round(delta, 6)
        if k not in self.tables:
            self.tables[k] = self.M.table(delta, False)
        return self.tables[k]

    def delta_for(self, per_trade):
        return (per_trade - float(self.M.base[205.0].mean())) / LOT

    def trade(self, rng, T, T0, ci):
        fav = int(rng.integers(0, 2))
        coin = int(rng.integers(0, 2))
        c205, c400 = T[205.0][ci, fav, 0], T[400.0][ci, fav, 0]
        k205 = T[205.0][ci, fav, 0] if coin == fav else T0[205.0][ci, coin, 0]
        k400 = T[400.0][ci, fav, 0] if coin == fav else T0[400.0][ci, coin, 0]
        return c205, c400, k205, k400

    def cell(self, rng):
        d = int(rng.integers(0, len(self.M.days)))
        b = self.M.by_day[d]
        return d, b[int(rng.integers(0, len(b)))]


def fw9a(W, per_session, reps, rng):
    q = 1 / 3
    T, T0 = W.tab(W.delta_for(per_session / q)), W.tab(0.0)
    out = {"PASS": 0, "FAIL": 0, "INSUFFICIENT": 0}
    for _ in range(reps):
        rows = []
        for s in range(60):
            if rng.random() < q:
                _d, ci = W.cell(rng)
                rows.append(W.trade(rng, T, T0, ci))
            if len(rows) >= 15:
                break
        if len(rows) < 15:
            out["INSUFFICIENT"] += 1
            continue
        a = np.array(rows)
        ok = a[:, 0].mean() > 0 and a[:, 1].mean() > 0 and a[:, 0].sum() - a[:, 0].max() > 0 and (a[:, 0] - a[:, 2]).mean() > 0
        out["PASS" if ok else "FAIL"] += 1
    return {k: round(v / reps, 3) for k, v in out.items()}


def sn300a(W, per_session, reps, rng):
    cpd = float(np.mean([len(b) for b in W.M.by_day]))
    T, T0 = W.tab(W.delta_for(per_session / cpd)), W.tab(0.0)
    out = {"PASS": 0, "FAIL": 0, "INSUFFICIENT": 0}
    for _ in range(reps):
        tot205 = tot400 = flat = 0.0
        sess, pairs, flat_n, trades = [], [], 0, 0
        for s in range(20):
            d = int(rng.integers(0, len(W.M.days)))
            net = 0.0
            empty = all(W.lab[ci] == "EMPTY" for ci in W.M.by_day[d])
            flat_n += empty
            for ci in W.M.by_day[d]:
                c205, c400, k205, _k400 = W.trade(rng, T, T0, ci)
                net += c205
                tot400 += c400
                pairs.append(c205 - k205)
                trades += 1
            tot205 += net
            sess.append(net)
            if empty:
                flat += net
        if trades < 30 or len(sess) < 10 or flat_n < 8 or len(pairs) < 20:
            out["INSUFFICIENT"] += 1
            continue
        ok = tot205 > 0 and tot400 > 0 and np.mean(pairs) > 0 and tot205 - max(sess) > 0 and flat > 0
        out["PASS" if ok else "FAIL"] += 1
    return {k: round(v / reps, 3) for k, v in out.items()}


def f1(W, per_trade, reps, rng):
    T, T0 = W.tab(W.delta_for(per_trade)), W.tab(0.0)
    out = {"PASS": 0, "FAIL": 0}
    for _ in range(reps):
        a = np.array([W.trade(rng, T, T0, W.cell(rng)[1]) for _ in range(30)])
        top5 = np.sort(a[:, 0])[-5:].sum()
        ok = a[:, 0].mean() > 0 and a[:, 1].mean() > 0 and a[:, 0].sum() - top5 > 0 and (a[:, 0] - a[:, 2]).mean() > 0
        out["PASS" if ok else "FAIL"] += 1
    return {k: round(v / reps, 3) for k, v in out.items()}


def fx5_rows():
    d = json.loads((HERE.parent / "2026-11-17-sn441" / "results-sn444-mechanics.json").read_text(encoding="utf-8"))
    out = []
    for r in d["rows"]:
        if r.get("state") != "DECIDED":
            continue
        g = lambda arm, st: float(r[arm].get(f"net{st}", 0.0)) if r[arm].get("state") == "FILLED" else 0.0  # noqa: E731
        out.append([g("CONFIRM-5", 205), g("CONFIRM-5", 400), g("IMMEDIATE", 205), g("IMMEDIATE", 400), g("DELAY-5", 205), g("DELAY-5", 400)])
    return np.array(out)


def fx5(rows, per_decision, reps, rng):
    s = per_decision - float((rows[:, 0] - rows[:, 2]).mean())
    out = {"PASS": 0, "FAIL": 0}
    for _ in range(reps):
        a = rows[rng.integers(0, len(rows), 60)].copy()
        a[:, 0] += s
        a[:, 1] += s
        ok = all(x > 0 for x in ((a[:, 0] - a[:, 2]).mean(), (a[:, 1] - a[:, 3]).mean(), (a[:, 0] - a[:, 4]).mean(), (a[:, 1] - a[:, 5]).mean()))
        out["PASS" if ok else "FAIL"] += 1
    return {k: round(v / reps, 3) for k, v in out.items()}


def main():
    if OUT.exists():
        raise SystemExit("SN472 is scored once")
    W = World()
    rng = np.random.default_rng(472)
    claim = 22800 / 210
    res = {"fw9a_cheap_opener": {}, "SN300a_packets": {}, "F1_banknifty": {}, "fx5": {}}
    for e in (0.0, 50.0, 154.0):
        res["fw9a_cheap_opener"][f"edge_per_session_{int(e)}"] = fw9a(W, e, REPS, rng)
        res["SN300a_packets"][f"edge_per_session_{int(e)}"] = sn300a(W, e, REPS, rng)
        res["F1_banknifty"][f"edge_per_trade_{int(e)}"] = f1(W, e, REPS, rng)
    res["fw9a_cheap_opener"]["edge_dev_claim_109"] = fw9a(W, claim, REPS, rng)
    res["fw9a_cheap_opener"]["edge_dev_claim_x_minus_0.22"] = fw9a(W, -0.22 * claim, REPS, rng)
    rows = fx5_rows()
    res["fx5"]["decisions_in_pool"] = len(rows)
    for e in (0.0, 50.0, 154.0):
        res["fx5"][f"edge_per_decision_{int(e)}"] = fx5(rows, e, REPS, rng)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
