"""SN471 (own): positioning and Gold's own trades (PLAN.md section 3, frozen at 83e1b444; details fixed here before any number).
Diagnostic only; Gold is not changed either way.

Trades: Gold's replay logs, DEPLOYED at Rs 205, 2022 (gold.Y22) and 2023-26 (gold.Y2326, parity 8,50,882 / 883).
z_d: SN456's primary feature on the trade's day (feat456; report d-1 ON_TIME or ASSUMED). Trades without z are counted, not used.
AGREE = (CE and z > 0) or (PE and z < 0). Statistic: mean net per trade AGREE - DISAGREE, per period and pooled.
CI: 2,000 resamples of trade DAYS with replacement (seed 471). Placebo: the z series (futures calendar order, dates with z) shifted
circularly by 20..219 sessions (200 shifts), the statistic recomputed. Worth a forward look only if the sign is the same in
2022 and 2023-26, the pooled CI excludes 0, and the pooled statistic lies beyond the placebo's 95th percentile on its side.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-17-sn411"))
import feat456 as F  # noqa: E402
import gold  # noqa: E402

OUT = HERE / "results-sn471.json"


def stat(tr, zmap):
    a = [t["net"] for t in tr if t["day"] in zmap and zmap[t["day"]] != 0 and ((t["opt"] == "CE") == (zmap[t["day"]] > 0))]
    b = [t["net"] for t in tr if t["day"] in zmap and zmap[t["day"]] != 0 and ((t["opt"] == "CE") != (zmap[t["day"]] > 0))]
    if not a or not b:
        return None, len(a), len(b)
    return float(np.mean(a) - np.mean(b)), len(a), len(b)


def boot(tr, zmap, seed=471, B=2000):
    rng = np.random.default_rng(seed)
    days = sorted({t["day"] for t in tr if t["day"] in zmap})
    by = {d: [t for t in tr if t["day"] == d] for d in days}
    out = []
    for _ in range(B):
        pick = [days[i] for i in rng.integers(0, len(days), len(days))]
        s, _a, _b = stat([t for d in pick for t in by[d]], zmap)
        if s is not None:
            out.append(s)
    return [round(float(np.percentile(out, 5)), 1), round(float(np.percentile(out, 95)), 1)]


def main():
    if OUT.exists():
        raise SystemExit("SN471 is scored once")
    cal, rows, _rep = F.features()
    zd = [d for d in cal if rows[d].get("z") is not None]
    zmap = {d: rows[d]["z"] for d in zd}
    logs = {}
    for name, years in (("2022", gold.Y22), ("2023-26", gold.Y2326)):
        days, log, _ = gold.run(years, gold.DEPLOYED, 205.0)
        if name == "2023-26":
            assert gold.summary(days, log)["net"] in (850882, 850883)
        logs[name] = [{"day": x["day"], "opt": x["opt"], "net": float(x["net"])} for x in log]
    res = {}
    allt = logs["2022"] + logs["2023-26"]
    for name, tr in (("2022", logs["2022"]), ("2023-26", logs["2023-26"]), ("pooled", allt)):
        s, na, nb = stat(tr, zmap)
        res[name] = {"trades": len(tr), "with_z": sum(t["day"] in zmap for t in tr), "agree": na, "disagree": nb,
                     "agree_minus_disagree_per_trade": None if s is None else round(s, 1),
                     "mean_agree": round(float(np.mean([t["net"] for t in tr if t["day"] in zmap and ((t["opt"] == "CE") == (zmap[t["day"]] > 0))])), 1),
                     "mean_disagree": round(float(np.mean([t["net"] for t in tr if t["day"] in zmap and ((t["opt"] == "CE") != (zmap[t["day"]] > 0))])), 1),
                     "ci90": boot(tr, zmap)}
    obs = res["pooled"]["agree_minus_disagree_per_trade"]
    plc = []
    for k in range(20, 220):
        sh = {zd[i]: zmap[zd[(i - k) % len(zd)]] for i in range(len(zd))}
        s, _a, _b = stat(allt, sh)
        plc.append(s)
    res["placebo"] = {"shifts": len(plc), "p05": round(float(np.percentile(plc, 5)), 1), "p95": round(float(np.percentile(plc, 95)), 1),
                      "share_beyond_observed": round(float(np.mean([p >= obs for p in plc]) if obs > 0 else np.mean([p <= obs for p in plc])), 3)}
    same = (res["2022"]["agree_minus_disagree_per_trade"] or 0) * (res["2023-26"]["agree_minus_disagree_per_trade"] or 0) > 0
    excl = res["pooled"]["ci90"][0] > 0 or res["pooled"]["ci90"][1] < 0
    beyond = obs > res["placebo"]["p95"] if obs > 0 else obs < res["placebo"]["p05"]
    res["worth_forward_look"] = bool(same and excl and beyond)
    res["checks"] = {"same_sign_both_periods": bool(same), "pooled_ci_excludes_0": bool(excl), "beyond_placebo": bool(beyond)}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
