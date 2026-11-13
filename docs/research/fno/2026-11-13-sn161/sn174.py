"""SN174 - quiet-day VWAP reversion (PLAN.md). Rs 15k. Quiet day: SN171's HAR forecast / implied < 1.0 at 10:00
(the fold's HAR, fitted without the scored year). From 10:00 to 14:30, when the index first stretches >= k x the
1-minute ATR from VWAP (k in {1.5, 2, 2.5}), buy the ATM option toward VWAP; sell when the index touches VWAP (minute
close), at +Rs 1,500 / -Rs 1,500 or 15:10; up to two attempts. Leave-one-year-out choice of k; matched null: the
same entry minutes with a random side (300 draws). Not-quiet days reported for contrast."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import p3  # noqa: E402
import pml  # noqa: E402
import pw  # noqa: E402

KS = (1.5, 2.0, 2.5)


def touched_vwap(d):
    def cond(S, j):
        c, vw = S.F["c"], S.F["vwap"]
        return (c[j] - vw[j]) * d >= 0
    return cond


def day(S, k, rng=None):
    c, vw, atr = S.F["c"], S.F["vwap"], S.F["atr"]
    net, tries, i = 0.0, 0, p3.I1000
    while i <= pw.I_MAX and tries < 2 and net < 1500.0 and net > -3000.0:
        far = abs(c[i] - vw[i]) >= k * atr[i]
        was = abs(c[i - 1] - vw[i - 1]) >= k * atr[i - 1]
        if far and not was:
            d = -1 if c[i] > vw[i] else 1
            if rng is not None:
                d = 1 if rng.random() < 0.5 else -1
            opt = "CE" if d > 0 else "PE"
            r = p3.trade_until(S, i, opt, pw.atm(S, i), 15000.0, 1500.0 - net, -min(1500.0, 3000.0 + net), touched_vwap(d))
            tries += 1
            if r is not None:
                net += r["net"]
                i = r["j"] + 1
                continue
        i += 1
    return net if tries else None


if __name__ == "__main__":
    out_path = HERE / "results-sn174.json"
    if out_path.exists():
        raise SystemExit("SN174 is scored once")
    ss = pw.dev_sessions()
    days = [S.day for S in ss]
    har = p3.HAR(ss)
    folds = {y: p3.rho_table(har, ss, lambda d, y=y: d[:4] != y) for y in p3.YEARS}
    raw = {k: {S.day: day(S, k) for S in ss} for k in KS}
    res = {"loyo": {}}
    for y in p3.YEARS:
        quiet = {d for d, r in folds[y].items() if r < 1.0}
        vn = {f"k {k}": {d: n for d, n in raw[k].items() if n is not None and d in quiet} for k in KS}
        ch, _t, _p = p3.loyo(vn)
        res["loyo"][y] = ch[y]
    total = sum(v["net"] for v in res["loyo"].values())
    pos = sum(v["net"] > 0 for v in res["loyo"].values())
    rng = np.random.default_rng(174)
    sess = {S.day: S for S in ss}
    tots = []
    for _ in range(300):
        t = 0.0
        for y in p3.YEARS:
            k = float(res["loyo"][y]["variant"].split()[1])
            quiet = {d for d, r in folds[y].items() if r < 1.0}
            for d in quiet:
                if d[:4] == y and raw[k].get(d) is not None:
                    t += day(sess[d], k, rng) or 0.0
        tots.append(t)
    rho_all = p3.rho_table(har, ss, lambda d: True)
    res.update({"loyo_total": total, "years_positive": pos, "null_mean": round(float(np.mean(tots))),
                "null_p95": round(float(np.percentile(tots, 95)))})
    res["dev_pass"] = bool(total > 0 and pos >= 3 and total > res["null_p95"])
    res["in_sample_quiet"] = {f"k {k}": pml.summary({d: n for d, n in raw[k].items() if n is not None and rho_all.get(d, 9) < 1.0}, days) for k in KS}
    res["in_sample_not_quiet"] = {f"k {k}": pml.summary({d: n for d, n in raw[k].items() if n is not None and rho_all.get(d, 0) >= 1.0}, days) for k in KS}
    res["final_variant"] = max(res["in_sample_quiet"], key=lambda v: res["in_sample_quiet"][v]["net"])
    print("SN174", json.dumps({k: v for k, v in res.items() if not k.startswith("in_sample")}), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
