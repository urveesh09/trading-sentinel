"""SN173 - the opening gap (PLAN.md). Rs 15k. Gap = (today's open - yesterday's close) / yesterday's close, in units
of yesterday's daily ATR (the lab's vol table). Variants: g in {0.3, 0.5, 0.8} x mode {fade (buy against the gap),
follow} x entry {09:20, 09:30}: the 1-OTM option, wage +Rs 1,500 / stop -Rs 1,500, one attempt. Leave-one-year-out
choice; matched null: the same days and minute with a random side (500 draws)."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import p3  # noqa: E402
import pml  # noqa: E402
import pw  # noqa: E402

L = pw.L
GS, MODES, ENTRIES = (0.3, 0.5, 0.8), ("fade", "follow"), (5, 15)


def gap_atr(S):
    a = L.VOLT.get(S.day, (None, None))[0]
    return S.F["gap"] / a if a else None


def one(S, i, d):
    opt = "CE" if d > 0 else "PE"
    r = pw.trade(S, i, opt, pw.atm(S, i) + d * pw.STEP, 15000.0, target=1500.0, stop=-1500.0)
    return None if r is None else r["net"]


if __name__ == "__main__":
    out_path = HERE / "results-sn173.json"
    if out_path.exists():
        raise SystemExit("SN173 is scored once")
    ss = pw.dev_sessions()
    days = [S.day for S in ss]
    ga = {S.day: gap_atr(S) for S in ss}
    vn = {}
    for g, mode, i in itertools.product(GS, MODES, ENTRIES):
        dn = {}
        for S in ss:
            x = ga[S.day]
            if x is None or abs(x) < g:
                continue
            d = (-1 if x > 0 else 1) if mode == "fade" else (1 if x > 0 else -1)
            n = one(S, i, d)
            if n is not None:
                dn[S.day] = n
        vn[f"gap {g} {mode} @{'09:20' if i == 5 else '09:30'}"] = dn
    res = {"in_sample": {v: pml.summary(dn, days) for v, dn in vn.items()}}
    ch, total, pos = p3.loyo(vn)
    rng = np.random.default_rng(173)
    sess = {S.day: S for S in ss}
    tots = []
    for _ in range(500):
        t = 0.0
        for y in p3.YEARS:
            v = ch[y]["variant"]
            i = 5 if v.endswith("09:20") else 15
            for d in vn[v]:
                if d[:4] == y:
                    t += one(sess[d], i, 1 if rng.random() < 0.5 else -1) or 0.0
        tots.append(t)
    res.update({"loyo": ch, "loyo_total": total, "years_positive": pos, "null_mean": round(float(np.mean(tots))),
                "null_p95": round(float(np.percentile(tots, 95)))})
    res["dev_pass"] = bool(total > 0 and pos >= 3 and total > res["null_p95"])
    res["final_variant"] = max(vn, key=lambda v: sum(vn[v].values()))
    print("SN173", json.dumps({k: v for k, v in res.items() if k != "in_sample"}), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
