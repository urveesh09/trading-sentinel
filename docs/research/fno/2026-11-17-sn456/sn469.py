"""SN469: can the test detect an edge of the intended size? (PLAN.md section 2, frozen at 83e1b444; details fixed here before
any number). Synthetic outcomes only; the real books supply spreads, staleness and the market's own noise.

Books: SN441's common two-sided cells rebuilt here (SN412 archive, walked one-lot books, clocks 10:00 / 11:00 / 13:00, both
1-ITM sides ENTERED and resolved at both stresses; parity: 98 cells on 37 dates).
Generator (labels never reach the scorer):
  a session draws one of the 37 dates (uniform, with replacement); the predictor fires with probability q; the favoured side
  is a fair coin (the predictor "knows" it); ONE-CLOCK mode trades one of the date's cells (uniform), THREE-CLOCK mode trades
  every cell of the date on the same favoured side (within-day dependence).
  Injection on the favoured side's bid after entry: + delta x (t - e) / (x - e) for e < t <= x, + delta after x.
  The ask at entry is untouched.
  STALE: 20% of the bid snapshots after entry blanked (50 seeded masks a cell side); the scorer scores an UNRESOLVED exit as the
  premium lost (debit + entry charges + stress).
  LARGE: the injection reaches only 5% of trades, at 20 x delta (a few large winners).
Truth (from the labels): the injected net = the unmodified scheduled-exit net (no stop, the original first bid at or after
x within 5 minutes) + delta x 65 on injected trades; delta solved so the truth per market session = mu at Rs 205.
Scorer: sn441.legal on the modified books (stop on an observed mark, legal exit), per-session sums, zeros on no-trade
sessions. Its population mean (100,000 sessions) against the truth = the recovery bias.
Scenarios (12): mu 0 / 50 / 154 x coverage 0.3 / 1.0 (one clock); THREE-CLOCK q 1.0 mu 0 / 154; STALE q 1.0 mu 0 / 154;
LARGE q 1.0 mu 50 / 154.
Horizons 20 / 60 / 120 / 250 / 500 sessions, 1,000 replications each (seed 469); per replication:
  CI0     the 90% bootstrap CI (300 resamples of sessions) of the per-session mean at Rs 205 wholly above 0
  SN449   PASS when that CI is wholly above 154, FAIL when wholly below, else INSUFFICIENT
  FW7A    >= 15 trades, per-session mean > 0 at 205 and 400, sum without the best session > 0 (no controls)
Reported: the false-positive rate (mu = 0), the detection rate, and the recovered mean against the truth. A horizon with
detection < 80% or bias > 20% of mu fails the design check.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn441"))
import sn441  # noqa: E402

sn428, C, qa = sn441.sn428, sn441.C, sn441.qa
LOT, GRACE, STOP = sn441.LOT, sn441.GRACE, sn441.STOP
OUT = HERE / "results-sn469.json"
CACHE = HERE / "_local" / "sn469_cells.npz"
HORIZONS = (20, 60, 120, 250, 500)
R, B, NPOP, NMASK = 1000, 300, 100_000, 50


def cells():
    """[(day, clock, label, {side: (ask, bid, e, x)})] for SN441's common cells."""
    man = qa.manifest()
    days = [d for d in man["quote_days"] if d not in set(man["unsealed_days"])]
    gold_days = {x["day"] for x in json.loads(C.RUNS.read_text(encoding="utf-8"))["2023-2026 DEPLOYED @205"]["log"]}
    out = []
    for d in days:
        q = qa.load(d)
        cons = sn428.contracts(q, d)
        exps = sorted({k[1] for k in cons})
        if not exps:
            continue
        front = exps[0]
        expiring = front == d
        lab = sn441.label_of(d, front, gold_days)
        fut = qa.front_fut(q, "NIFTY")
        for c, e in sn441.CLOCKS.items():
            if expiring and e >= 255:
                continue
            F = fut["ltp"][e] if fut is not None else np.nan
            if np.isnan(F):
                continue
            atm = int(round(F / 50.0) * 50)
            x = min(e + 60, 255 if expiring else 355)
            sides, ok = {}, True
            for s in ("CE", "PE"):
                v = cons.get(("NIFTY", front, atm + (-50 if s == "CE" else 50), s))
                if v is None:
                    ok = False
                    break
                ask, bid = C.walked(v, "ask"), C.walked(v, "bid")
                for st in (205.0, 400.0):
                    if sn441.legal(ask, bid, e, x, st)[0] != "ENTERED":
                        ok = False
                sides[s] = (np.asarray(ask, float), np.asarray(bid, float), e, x)
            if ok:
                out.append((d, c, lab, sides))
    return out


def first_bid(bid, x):
    for t in range(x, min(x + GRACE + 1, len(bid))):
        if not np.isnan(bid[t]):
            return float(bid[t])
    return None


def truth_net(ask, bid, e, x, delta, stress):
    a, b = float(ask[e]), first_bid(bid, x)
    b += delta
    return (b - a) * LOT - C.charges(a, b) - stress


def inject(bid, e, x, delta):
    b = bid.copy()
    n = len(b)
    for t in range(e + 1, n):
        b[t] += delta * min(1.0, (t - e) / max(1, x - e))
    return b


def scorer_net(ask, bid, e, x, stress):
    st, n, _x, _b = sn441.legal(ask, bid, e, x, stress)
    if st == "UNRESOLVED":
        a = float(ask[e])
        return -a * LOT - C.charges(a, 0.0) - stress
    return n


def masks(n, e, x, k, seed):
    rng = np.random.default_rng(seed)
    idx = np.arange(e + 1, min(n, x + GRACE + 1))
    out = [np.zeros(n, bool)]
    for _ in range(k):
        m = np.zeros(n, bool)
        m[idx[rng.random(len(idx)) < 0.2]] = True
        out.append(m)
    return out


class Machine:
    def __init__(self, cl):
        self.cl = cl
        self.days = sorted({c[0] for c in cl})
        self.by_day = [[i for i, c in enumerate(cl) if c[0] == d] for d in self.days]
        self.base = {st: np.array([[truth_net(*c[3][s], 0.0, st) for s in ("CE", "PE")] for c in cl]) for st in (205.0, 400.0)}

    def table(self, delta, stale):
        """NET[st]: (cells, 2 sides, variants) scorer nets; variant 0 = no blanking, 1..NMASK masks (stale only)."""
        nv = NMASK + 1 if stale else 1
        out = {st: np.zeros((len(self.cl), 2, nv)) for st in (205.0, 400.0)}
        for i, c in enumerate(self.cl):
            for j, s in enumerate(("CE", "PE")):
                ask, bid, e, x = c[3][s]
                bi = inject(bid, e, x, delta) if delta else bid
                ms = masks(len(bid), e, x, NMASK, 469_000 + i * 2 + j) if stale else [np.zeros(len(bid), bool)]
                for v, m in enumerate(ms):
                    bb = bi.copy()
                    bb[m] = np.nan
                    for st in (205.0, 400.0):
                        out[st][i, j, v] = scorer_net(ask, bb, e, x, st)
        return out

    def sessions(self, n, q, three, rng, tables, large=None):
        """(per-session nets {st: (n,)}, trades (n,), truth {st: (n,)}); tables = {'base': T0, 'inj': T1} scorer tables."""
        out = {st: np.zeros(n) for st in (205.0, 400.0)}
        tru = {st: np.zeros(n) for st in (205.0, 400.0)}
        trades = np.zeros(n, int)
        di = rng.integers(0, len(self.days), n)
        fire = rng.random(n) < q
        side = rng.integers(0, 2, n)
        for k in range(n):
            if not fire[k]:
                continue
            cs = self.by_day[di[k]] if three else [self.by_day[di[k]][rng.integers(0, len(self.by_day[di[k]]))]]
            for ci in cs:
                trades[k] += 1
                inj = True if large is None else (rng.random() < large["share"])
                T = tables["inj"] if inj else tables["base"]
                v = rng.integers(1, T[205.0].shape[2]) if T[205.0].shape[2] > 1 else 0
                for st in (205.0, 400.0):
                    out[st][k] += T[st][ci, side[k], v]
                    tru[st][k] += self.base[st][ci, side[k]] + (tables["delta_eff"] * LOT if inj else 0.0)
        return out, trades, tru


def ci90(x, rng):
    n = len(x)
    idx = rng.integers(0, n, (B, n))
    m = x[idx].mean(axis=1)
    return float(np.percentile(m, 5)), float(np.percentile(m, 95))


def judge(nets, trades, rng):
    m205, m400 = float(nets[205.0].mean()), float(nets[400.0].mean())
    lo, hi = ci90(nets[205.0], rng)
    sn449 = "PASS" if lo > 154 else ("FAIL" if hi < 154 else "INSUFFICIENT")
    fw7a = trades.sum() >= 15 and m205 > 0 and m400 > 0 and (nets[205.0].sum() - nets[205.0].max()) > 0
    return {"mean205": m205, "ci0": lo > 0, "sn449": sn449, "fw7a": bool(fw7a)}


def scenario(M, name, mu, q, three=False, stale=False, large=False):
    cpd = np.mean([len(b) for b in M.by_day]) if three else 1.0
    base_mean = float(M.base[205.0].mean())
    need = mu / (q * cpd) - base_mean                    # injected rupees a trade
    if large:
        delta_eff = need / LOT / 0.05
        lg = {"share": 0.05}
    else:
        delta_eff, lg = need / LOT, None
    tables = {"base": M.table(0.0, stale), "inj": M.table(delta_eff, stale), "delta_eff": delta_eff}
    if not large:
        tables["base"] = tables["inj"]
    rng = np.random.default_rng(469)
    pop, ptr, ptru = M.sessions(NPOP, q, three, rng, tables, lg)
    res = {"mu": mu, "q": q, "three_clock": three, "stale": stale, "large": large, "delta_rupees_per_unit": round(delta_eff, 3),
           "truth_per_session_205": round(float(ptru[205.0].mean()), 1), "scorer_population_205": round(float(pop[205.0].mean()), 1),
           "scorer_population_400": round(float(pop[400.0].mean()), 1), "trades_per_session": round(float(ptr.mean()), 3),
           "sd_per_session_205": round(float(pop[205.0].std()), 1)}
    res["recovery_bias_205"] = round(res["scorer_population_205"] - res["truth_per_session_205"], 1)
    hz = {}
    for N in HORIZONS:
        js = []
        for r in range(R):
            nets, tr, _t = M.sessions(N, q, three, rng, tables, lg)
            js.append(judge(nets, tr, rng))
        hz[str(N)] = {"ci0_pass": round(float(np.mean([j["ci0"] for j in js])), 3),
                      "sn449_pass": round(float(np.mean([j["sn449"] == "PASS" for j in js])), 3),
                      "sn449_fail": round(float(np.mean([j["sn449"] == "FAIL" for j in js])), 3),
                      "fw7a_pass": round(float(np.mean([j["fw7a"] for j in js])), 3),
                      "mean_estimate_205": round(float(np.mean([j["mean205"] for j in js])), 1),
                      "estimate_p05_p95": [round(float(np.percentile([j["mean205"] for j in js], p)), 1) for p in (5, 95)]}
    res["horizons"] = hz
    print(name, json.dumps({k: v for k, v in res.items() if k != "horizons"}), flush=True)
    return res


SCEN = [("NULL q1", 0, 1.0), ("SUPP q1", 50, 1.0), ("WAGE q1", 154, 1.0),
        ("NULL q.3", 0, 0.3), ("SUPP q.3", 50, 0.3), ("WAGE q.3", 154, 0.3),
        ("NULL 3clk", 0, 1.0, True), ("WAGE 3clk", 154, 1.0, True),
        ("NULL stale", 0, 1.0, False, True), ("WAGE stale", 154, 1.0, False, True),
        ("SUPP large", 50, 1.0, False, False, True), ("WAGE large", 154, 1.0, False, False, True)]


def main():
    if OUT.exists():
        raise SystemExit("SN469 is scored once")
    random.seed(469)
    cl = cells()
    assert len(cl) == 98 and len({c[0] for c in cl}) == 37, (len(cl), len({c[0] for c in cl}))
    M = Machine(cl)
    res = {"cells": len(cl), "dates": len(M.days), "base_unmodified_mean_per_trade_205": round(float(M.base[205.0].mean()), 1),
           "base_unmodified_mean_per_trade_400": round(float(M.base[400.0].mean()), 1), "scenarios": {}}
    for sc in SCEN:
        name, mu, q, *rest = sc
        res["scenarios"][name] = scenario(M, name, mu, q, *rest)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
