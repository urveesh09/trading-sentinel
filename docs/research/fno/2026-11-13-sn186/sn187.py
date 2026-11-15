"""SN187 - the 91% trade, both sides (PLAN.md). Gold's empty days (development). Buy 1 lot ATM CE + 1 lot ATM PE
(Rs 30k wallet; Rs 205 per leg) at 09:20 or 10:00. Exits on minute closes:
  pair  - close both when the pair's net >= +goal (Rs 1,000 / 1,500), stop at -Rs 2,000 / -3,000, else 15:10;
  first - when either leg's own net reaches +Rs 1,500, close both that minute; stop at -Rs 3,000, else 15:10.
LOYO over the 10 variants; matched null: the chosen variant at a random minute 09:30-14:30 on the same days (200)."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402

pw = pe.pw
ENTRIES = {"09:20": 5, "10:00": 45}
PAIR = list(itertools.product((1000.0, 1500.0), (2000.0, 3000.0)))


def legs(S, i, stress=pe.LEG_STRESS):
    K = pw.atm(S, i)
    ce, pe_ = pe.leg_vals(S, i, K, "CE", stress), pe.leg_vals(S, i, K, "PE", stress)
    if ce is None or pe_ is None:
        return None
    r1, r2 = S.option(K, "CE"), S.option(K, "PE")
    cost = (pw.M.ask_of(float(r1[0][3][i])) + pw.M.ask_of(float(r2[0][3][i]))) * pw.LOT
    return None if cost > 30000.0 else (ce, pe_)


def play(S, i, variant, stress=pe.LEG_STRESS, late=0):
    i = i + late
    got = legs(S, i, stress)
    if got is None:
        return None
    ce, pe_ = got
    if variant[0] == "pair":
        return pe.settle(ce + pe_, i, target=variant[1], stop=variant[2])[0]
    last = None
    for j in range(i + 1, pw.FLAT + 1):
        a, b = ce[j], pe_[j]
        if a != a or b != b:
            continue
        last = a + b
        if last <= -3000.0 or a >= 1500.0 or b >= 1500.0:
            return last
    return last


def variants():
    out = {}
    for name, i in ENTRIES.items():
        for g, s in PAIR:
            out[f"pair {name} goal {g:.0f} stop {s:.0f}"] = (i, ("pair", g, s))
        out[f"first-leg {name}"] = (i, ("first",))
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn187.json"
    if out_path.exists():
        raise SystemExit("SN187 is scored once")
    ss = pe.empty_sessions()
    days = [S.day for S in ss]
    V = variants()
    vn = {}
    for name, (i, v) in V.items():
        dn = {}
        for S in ss:
            n = play(S, i, v)
            if n is not None:
                dn[S.day] = n
        vn[name] = dn
    res = {"empty_days": len(ss), "in_sample": {k: pe.goal_stats(dn, days, 1000.0 if "1000" in k else 1500.0) for k, dn in vn.items()}}
    ch, total, pos = pe.loyo(vn)
    rng = np.random.default_rng(187)
    sess = {S.day: S for S in ss}
    tots = []
    for _ in range(200):
        t = 0.0
        for y in pe.YEARS:
            _i, v = V[ch[y]["variant"]]
            for d in vn[ch[y]["variant"]]:
                if d[:4] == y:
                    t += play(sess[d], int(rng.integers(pw.I_MIN, pw.I_MAX + 1)), v) or 0.0
        tots.append(t)
    res.update({"loyo": ch, "loyo_total": total, "years_positive": pos, "null_mean": round(float(np.mean(tots))),
                "null_p95": round(float(np.percentile(tots, 95)))})
    res["final_variant"] = max(vn, key=lambda k: sum(vn[k].values()))
    res["dev_pass_partial"] = bool(total > 0 and pos >= 3 and total > res["null_p95"])
    robust = {"stress_400": 0.0, "late_1": 0.0}
    for y in pe.YEARS:
        i0, v = V[ch[y]["variant"]]
        for d in vn[ch[y]["variant"]]:
            if d[:4] == y:
                robust["stress_400"] += play(sess[d], i0, v, stress=400.0) or 0.0
                robust["late_1"] += play(sess[d], i0, v, late=1) or 0.0
    held = sorted((vn[ch[d[:4]]["variant"]][d] for y in pe.YEARS for d in vn[ch[y]["variant"]] if d[:4] == y), reverse=True)
    res["robust_loyo"] = {k: round(v) for k, v in robust.items()} | {"without_best_5": round(sum(held[5:]))}
    res["dev_pass"] = bool(res["dev_pass_partial"] and robust["stress_400"] > 0 and robust["late_1"] > 0 and sum(held[5:]) > 0)
    print("SN187", json.dumps({k: v for k, v in res.items() if k != "in_sample"}), flush=True)
    for k, s in res["in_sample"].items():
        print(f"   {k:34s} net {s['net']:>9,} goal days {s['goal_days']:3d}/{s['trade_days']:3d} red {s['red_days']:3d} worst {s['worst_day']:>7,}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
