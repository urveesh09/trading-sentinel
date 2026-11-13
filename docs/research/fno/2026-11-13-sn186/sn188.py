"""SN188 - a small fixed target on hot empty days (PLAN.md). Gold's empty days (development) whose R_today at 10:00 is
in the causal top 40% of all earlier sessions (>= 60 earlier). The first close beyond the 09:45-10:00 range after 10:00
buys 1 lot ATM on that side; target +goal (Rs 1,000 / 1,500) / stop -s (Rs 1,000 / 1,500) as house fills; after an
exit a fresh break may trade again (2 attempts); the day stops at the goal or 2 x the goal lost. LOYO over the 4
variants; matched null: random side at the same entry minutes (200). Robustness: Rs 400 per lot, 1 minute late."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402

pw, C, ph = pe.pw, pe.C, pe.pw.ph
GRID = list(itertools.product((1000.0, 1500.0), (1000.0, 1500.0)))


def picker(rng=None):
    def pick(S, i0, realized):
        hi, lo = float(np.max(S.F["h"][30:45])), float(np.min(S.F["l"][30:45]))
        c = S.F["c"]
        for i in range(max(i0, 45), pw.I_MAX + 1):
            d = 1 if (c[i] > hi and c[i - 1] <= hi) else (-1 if (c[i] < lo and c[i - 1] >= lo) else 0)
            if d:
                if rng is not None:
                    d = 1 if rng.random() < 0.5 else -1
                return i, "CE" if d > 0 else "PE", pw.atm(S, i)
        return None
    return pick


def day(S, goal, stop, rng=None, stress=pw.STRESS, late=0):
    net, tr = pw.play(S, picker(rng), 1e9, goal, stop, attempts=2, day_limit=2 * goal, stress=stress, max_lots=1, late=late)
    return net if tr else None


def hot_days():
    q = ph.CausalQ(min_n=60)
    out = set()
    for S in pw.sessions():
        r = C.r_today(S, 45)
        thr = q.thr(0.4)
        if r is not None and thr is not None and r >= thr:
            out.add(S.day)
        q.add(r)
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn188.json"
    if out_path.exists():
        raise SystemExit("SN188 is scored once")
    hot = hot_days()
    ss = [S for S in pe.empty_sessions() if S.day in hot]
    days = [S.day for S in pe.empty_sessions()]
    vn = {}
    for g, s in GRID:
        dn = {S.day: day(S, g, s) for S in ss}
        vn[f"goal {g:.0f} stop {s:.0f}"] = {d: n for d, n in dn.items() if n is not None}
    res = {"hot_empty_days": len(ss), "in_sample": {k: pe.goal_stats(dn, days, float(k.split()[1])) for k, dn in vn.items()}}
    ch, total, pos = pe.loyo(vn)
    rng = np.random.default_rng(188)
    sess = {S.day: S for S in ss}
    tots = []
    for _ in range(200):
        t = 0.0
        for y in pe.YEARS:
            g, s = (float(x) for x in ch[y]["variant"].split()[1::2])
            t += sum((day(sess[d], g, s, rng) or 0.0) for d in vn[ch[y]["variant"]] if d[:4] == y)
        tots.append(t)
    res.update({"loyo": ch, "loyo_total": total, "years_positive": pos, "null_mean": round(float(np.mean(tots))),
                "null_p95": round(float(np.percentile(tots, 95)))})
    robust = {"stress_400": 0.0, "late_1": 0.0}
    held = []
    for y in pe.YEARS:
        g, s = (float(x) for x in ch[y]["variant"].split()[1::2])
        for d, n in vn[ch[y]["variant"]].items():
            if d[:4] == y:
                held.append(n)
                robust["stress_400"] += day(sess[d], g, s, stress=400.0) or 0.0
                robust["late_1"] += day(sess[d], g, s, late=1) or 0.0
    held.sort(reverse=True)
    res["robust_loyo"] = {k: round(v) for k, v in robust.items()} | {"without_best_5": round(sum(held[5:]))}
    res["final_variant"] = max(vn, key=lambda k: sum(vn[k].values()))
    res["dev_pass"] = bool(total > 0 and pos >= 3 and total > res["null_p95"] and robust["stress_400"] > 0
                           and robust["late_1"] > 0 and sum(held[5:]) > 0)
    print("SN188", json.dumps({k: v for k, v in res.items() if k != "in_sample"}), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
