"""SN152 - yesterday hot, today? (PLAN.md) Yesterday's full-session R (sigma of 1-minute returns 09:20-15:10 / implied
sigma at 15:10), only when yesterday is the previous trading day in the cache; a straddle today at 09:20 or 09:45
when that R is in the causal top 20% / 33%. Grid 4; LOYO; random-day control; robustness."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ph  # noqa: E402

C = ph.C
ENTRIES = {"09:20": 5, "09:45": 30}
QS = (0.20, 0.33)


def day_r(S):
    c = S.F["c"]
    r = np.diff(np.log(c[5: C.FLAT + 1]))
    si = C.sigma_imp(S, C.FLAT)
    return float(np.std(r)) / si if si else None


def flags(day_ok):
    ss = ph.sessions()
    q = ph.CausalQ()
    out = {}
    for k, S in enumerate(ss):
        prev = ss[k - 1] if k else None
        if prev is not None and ph.C._CAL[ph.C.bisect.bisect_left(ph.C._CAL, S.day) - 1] == prev.day and day_ok(S.day):
            x = day_r(prev)
            out[S.day] = (S, {qq: (x is not None and q.thr(qq) is not None and x >= q.thr(qq)) for qq in QS})
        if prev is not None:
            q.add(day_r(prev))
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn152.json"
    if out_path.exists():
        raise SystemExit("SN152 is scored once")
    res = {}
    for dname, ok in (("gold-free", C.gold_free), ("all days", lambda d: C.adx(d) is not None)):
        F = flags(ok)
        variants = {f"{en} top{int(qq * 100)}": (i, qq) for (en, i), qq in itertools.product(ENTRIES.items(), QS)}

        def nets(i, qq, **kw):
            o = {}
            for d, (S, f) in F.items():
                if f[qq]:
                    v = ph.straddle(S, i, **kw)
                    if v is not None:
                        o[d] = v
            return o
        N = {k: nets(*v) for k, v in variants.items()}
        tabs = {k: ph.table(v) for k, v in N.items()}
        L = C.loyo(tabs, "profit")
        held = {d: v for y in ph.YEARS for d, v in N[L[y]["pick"]].items() if d[:4] == y}
        s400 = sum(v for y in ph.YEARS for d, v in nets(*variants[L[y]["pick"]], stress=400.0).items() if d[:4] == y)
        late = sum(v for y in ph.YEARS for d, v in nets(*variants[L[y]["pick"]], late=1).items() if d[:4] == y)
        pool = {}
        for d, (S, _f) in F.items():
            v = ph.straddle(S, 5)
            if v is not None:
                pool.setdefault(d[:4], []).append(v)
        rm, r95 = ph.random_control({y: L[y]["trades"] for y in ph.YEARS}, pool, seed=152)
        v = ph.verdict(held, [L[y]["net"] for y in ph.YEARS], r95, round(s400), round(late))
        res[dname] = {"tables": tabs, "loyo": L, "random_mean": rm, "verdict": v, "heldout_day_nets": held}
        print(f"=== SN152 {dname}")
        for k, t in tabs.items():
            print(f"   {k:16s} {[t[y]['net'] for y in ph.YEARS]} total {ph.tot(t):>8} trades {sum(t[y]['trades'] for y in ph.YEARS)}")
        print("   LOYO", {y: (L[y]["pick"], L[y]["net"]) for y in ph.YEARS}, "| VERDICT", v | {"random_mean": rm}, flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
