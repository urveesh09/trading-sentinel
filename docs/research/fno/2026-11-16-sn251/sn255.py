"""SN255 - the literal ask, a buyer active every session (PLAN.md): the cost of activity, not a candidate.
(a) ATM option at 09:20 in the 09:15-09:20 direction; (b) ATM option at 09:45 in the 09:15-09:45 drive direction;
(c) a random side at 09:20, 200 seeds; (d) the 10:00 ATM straddle every day. Rs 3,000 stop, exit 15:10, one lot.
DEV, TEST, EXAM-N, EXAM-S."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402
import legs as LG  # noqa: E402

SAMPLES = ("DEV", "TEST", "EXAMN", "EXAMS")


def r_dir(smp, d, i):
    s = smp.s[d]
    o, c = float(s["index"][0][0]), float(s["index"][3][i])
    return 0 if c == o else (1 if c > o else -1)


def a920(smp, d):
    sd = r_dir(smp, d, 5)
    return None if not sd else LG.intraday(smp, d, LG.side_legs(smp, smp.s[d], 5, sd), 5, gl.FLAT)


def b945(smp, d):
    sd = r_dir(smp, d, 30)
    return None if not sd else LG.intraday(smp, d, LG.side_legs(smp, smp.s[d], 30, sd), 30, gl.FLAT)


def d1000(smp, d):
    return LG.intraday(smp, d, LG.straddle(smp, smp.s[d], 45), 45, gl.FLAT)


def rnd(seed):
    def f(smp, d):
        r = np.random.default_rng((seed * 1_000_003 + int(d.replace("-", ""))) & 0xFFFFFFFF)
        sd = 1 if r.random() < 0.5 else -1
        return LG.intraday(smp, d, LG.side_legs(smp, smp.s[d], 5, sd), 5, gl.FLAT)
    return f


if __name__ == "__main__":
    out_path = HERE / "results-sn255.json"
    if out_path.exists():
        raise SystemExit("SN255 is run once")
    gl.SEALED["EXAMN"] = gl.SEALED["EXAMS"] = True        # a control, opened by the plan
    res = {}
    for name, rule in (("(a) 09:20 first-5-minute side", a920), ("(b) 09:45 drive side", b945), ("(d) 10:00 straddle every day", d1000)):
        res[name] = {}
        for n in SAMPLES:
            smp = gl.sample(n)
            st = gl.stats(gl.book(smp, rule))
            res[name][n] = st
            print("SN255", name, n, json.dumps({k: st[k] for k in ("trades", "net", "per_trade", "win_pct", "worst", "years_positive", "years",
                                                                   "months_positive", "months", "by_year")}), flush=True)
    res["(c) 09:20 random side, 200 seeds"] = {}
    for n in SAMPLES:
        smp = gl.sample(n)
        both = {}
        for d in smp.days:                      # each day's call and put once; a seed picks one per day
            ce = LG.intraday(smp, d, LG.side_legs(smp, smp.s[d], 5, 1), 5, gl.FLAT)
            pe_ = LG.intraday(smp, d, LG.side_legs(smp, smp.s[d], 5, -1), 5, gl.FLAT)
            both[d] = (0.0 if ce is None else ce["net"], 0.0 if pe_ is None else pe_["net"])
        tot = []
        for k in range(200):
            x = 0.0
            for d in smp.days:
                r = np.random.default_rng((k * 1_000_003 + int(d.replace("-", ""))) & 0xFFFFFFFF)
                x += both[d][0] if r.random() < 0.5 else both[d][1]
            tot.append(x)
        res["(c) 09:20 random side, 200 seeds"][n] = {"mean": round(float(np.mean(tot))), "p5": round(float(np.percentile(tot, 5))),
                                                       "p95": round(float(np.percentile(tot, 95))), "positive_seeds": int(sum(t > 0 for t in tot))}
        print("SN255 (c) random", n, res["(c) 09:20 random side, 200 seeds"][n], flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
