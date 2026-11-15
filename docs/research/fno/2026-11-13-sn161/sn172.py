"""SN172 - the afternoon window (PLAN.md). Rs 15k. Variants entered at 13:15 (minute 240):
  strangle  - 1-OTM CE + PE held to 15:10 inside Rs 3,000 (skipped above Rs 15k);
  strangle wage - the same with the wage lock at +Rs 1,500;
  RB ATM / RB OTM1 - the first close beyond the 13:00-13:15 range after 13:15 (up to 14:30) buys that side's ATM / 1-OTM
  option, wage +Rs 1,500 / stop -Rs 1,500, one attempt.
Leave-one-year-out choice; matched null (random days for the structures, a random side at the same minute for the
range breaks). Rs 30k: the ATM straddle at 13:15 held inside Rs 6,000 (reported)."""
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

I1300, I1315 = 225, 240


def rb_after(S, off, rnd=None):
    hi, lo = float(np.max(S.F["h"][I1300:I1315])), float(np.min(S.F["l"][I1300:I1315]))
    c = S.F["c"]
    for i in range(I1315, pw.I_MAX + 1):
        d = 1 if (c[i] > hi and c[i - 1] <= hi) else (-1 if (c[i] < lo and c[i - 1] >= lo) else 0)
        if d:
            if rnd is not None:
                d = 1 if rnd.random() < 0.5 else -1
            opt = "CE" if d > 0 else "PE"
            r = pw.trade(S, i, opt, pw.atm(S, i) + d * off * pw.STEP, 15000.0, target=1500.0, stop=-1500.0)
            return None if r is None else r["net"]
    return None


if __name__ == "__main__":
    out_path = HERE / "results-sn172.json"
    if out_path.exists():
        raise SystemExit("SN172 is scored once")
    ss = pw.dev_sessions()
    days = [S.day for S in ss]
    vn = {"strangle": {}, "strangle wage": {}, "RB ATM": {}, "RB OTM1": {}}
    for S in ss:
        for name, tgt in (("strangle", None), ("strangle wage", 1500.0)):
            n = p3.structure(S, I1315, "strangle1", 15000.0, 3000.0, tgt)
            if n is not None:
                vn[name][S.day] = n
        for name, off in (("RB ATM", 0), ("RB OTM1", 1)):
            n = rb_after(S, off)
            if n is not None:
                vn[name][S.day] = n
    res = {"in_sample": {v: pml.summary(dn, days) for v, dn in vn.items()}}
    ch, total, pos = p3.loyo(vn)
    counts = {y: ch[y]["trades"] for y in p3.YEARS}
    nulls = []
    rng = np.random.default_rng(172)
    for y in p3.YEARS:
        v = ch[y]["variant"]
        if v.startswith("RB"):
            off = 0 if v == "RB ATM" else 1
            draws = []
            for _ in range(200):
                draws.append(sum((rb_after(S, off, rng) or 0.0) for S in ss if S.day[:4] == y))
            nulls.append(draws)
        else:
            pool = [n for d, n in vn[v].items() if d[:4] == y]
            nulls.append(list(rng.choice(pool, size=(200, min(counts[y], len(pool)))).sum(axis=1)) if pool else [0.0] * 200)
    tot_null = np.sum(np.array(nulls), axis=0)
    res.update({"loyo": ch, "loyo_total": total, "years_positive": pos, "null_mean": round(float(tot_null.mean())),
                "null_p95": round(float(np.percentile(tot_null, 95)))})
    res["dev_pass"] = bool(total > 0 and pos >= 3 and total > res["null_p95"])
    res["final_variant"] = max(vn, key=lambda v: sum(vn[v].values()))
    st30 = {S.day: p3.structure(S, I1315, "straddle", 30000.0, 6000.0) for S in ss}
    res["Rs 30k straddle 13:15"] = pml.summary({d: n for d, n in st30.items() if n is not None}, days, 30000.0, 3000.0)
    print("SN172", json.dumps({k: v for k, v in res.items() if k != "in_sample"}), "\nin-sample", json.dumps(res["in_sample"]), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
