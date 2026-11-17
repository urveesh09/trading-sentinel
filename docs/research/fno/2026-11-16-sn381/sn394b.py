"""SN394 follow-up (disclosed, Nov 16, after SN394's numbers and before any forward freeze): is the CHEAP-open result
robust, or the lucky split among the ~10 groups tried in SN385 / SN391 / SN393 / SN394?
Same rows and causal terciles as sn383_394. Reported for CHEAP: per-session net at Rs 205 / 400 by period (before / from
Sep 7, 2026) and by source (match row / 09:15-open fallback); without the best day; weeks positive; and a 5,000-draw
permutation p-value: the share of random subsets of the same size (from the 124 sessions with a reading) whose
per-session net is at least CHEAP's at BOTH stresses. Freeze a forward arm only if p < 0.05 AND CHEAP is > 0 at Rs 205 in
both periods.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn383_394 as M  # noqa: E402

R, V, gl, sn353b = M.R, M.V, M.gl, M.sn353b
OUT = HERE / "results-sn394b.json"


def net(r, st):
    return (r["ITM"].get(f"60m@{st}") or 0.0) if r["ITM"]["state"] == "FILLED" else 0.0


def main():
    if OUT.exists():
        raise SystemExit("run once")
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("ALL", raw, gl.DEV_LO, gl.TEST_HI)
    days = [d for d in smp.days if smp.s[d]["day"] != smp.s[d]["expiry"]]
    au = sn353b.auctions([d for d in days if sn353b.LO <= d < sn353b.HI])
    auc = {d: (1 if a["g"] > 0 else -1) for d, a in au.items() if a["g"] != 0}
    rows = R.run(smp, days, auc, {d: a["how"] for d, a in au.items()})
    jump, histj = {}, []
    for a, d in zip(smp.days, smp.days[1:]):
        s, sp = smp.s[d], smp.s[a]
        if s["day"] == s["expiry"] or sp["expiry"] != s["expiry"]:
            continue
        io, ip = V.straddle_iv(smp, s, 1), V.straddle_iv(smp, sp, 345)
        if io is None or ip is None:
            continue
        j = 100.0 * (io - ip)
        if len(histj) >= 60:
            srt = sorted(histj)
            lo, hi = srt[len(srt) // 3], srt[(2 * len(srt)) // 3]
            jump[d] = "CHEAP" if j < lo else "RICH" if j > hi else "MID"
        histj.append(j)
    withr = [r for r in rows if r["day"] in jump]
    cheap = [r for r in withr if jump[r["day"]] == "CHEAP"]
    res = {"with_reading": len(withr), "cheap": len(cheap)}
    for st in (205, 400):
        xs = [net(r, st) for r in cheap]
        res[f"per_session@{st}"] = round(float(np.mean(xs)), 1)
        res[f"without_best_day@{st}"] = round(float((sum(xs) - max(xs)) / (len(xs) - 1)), 1)
        for per in ("pre", "post"):
            ys = [net(r, st) for r in cheap if r["period"] == per]
            res[f"{per}@{st}"] = {"n": len(ys), "per_session": round(float(np.mean(ys)), 1) if ys else None}
        for src in ("match_row", "fallback_0915_open"):
            ys = [net(r, st) for r in cheap if r["src"] == src]
            res[f"{src}@{st}"] = {"n": len(ys), "per_session": round(float(np.mean(ys)), 1) if ys else None}
    wk = {}
    for r in cheap:
        w = str(np.datetime64(r["day"]).astype("datetime64[W]"))
        wk[w] = wk.get(w, 0.0) + net(r, 205)
    res["weeks"] = len(wk)
    res["weeks_positive"] = sum(v > 0 for v in wk.values())
    obs = (res["per_session@205"], res["per_session@400"])
    a205 = np.array([net(r, 205) for r in withr])
    a400 = np.array([net(r, 400) for r in withr])
    rng = random.Random(394)
    idx = list(range(len(withr)))
    hits = 0
    for _ in range(5000):
        rng.shuffle(idx)
        sub = idx[:len(cheap)]
        if a205[sub].mean() >= obs[0] and a400[sub].mean() >= obs[1]:
            hits += 1
    res["permutation_p_both_stresses"] = hits / 5000
    res["freeze_forward"] = bool(res["permutation_p_both_stresses"] < 0.05 and (res["pre@205"]["per_session"] or -1) > 0 and (res["post@205"]["per_session"] or -1) > 0)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
