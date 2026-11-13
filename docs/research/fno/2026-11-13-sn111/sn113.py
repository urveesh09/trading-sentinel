"""SN113 - does Gold share the straddle's mechanism? (PLAN.md)
1. Gold v5's trades at Rs 15k and Rs 30k by R_today at the entry minute (terciles of a causal expanding rank), by year.
2. Skip a Gold entry when its R_today is below the causal q-quantile of all earlier Gold entry ratios (>= 30 earlier),
   q in {0.10, 0.20, 0.33}; LOYO at every wallet against v5; SN92's Gold pass rule; robustness; every wallet."""
from __future__ import annotations

import bisect
import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pb  # noqa: E402

C, pa = pb.C, pb.pa
sys.path.insert(0, str(C.HERE))
import sn99  # noqa: E402  (SN92's Gold pass rule)

QS = (0.10, 0.20, 0.33)
R, THR, RANK = {}, {q: {} for q in QS}, {}


def key(day, sg):
    return (day, sg["i"], sg["sig_key"])


def build_ratios():
    Ys = C.years()
    seen = []
    for y in C.YEARS:
        Y = Ys[y]
        for S in Y.ordered():
            for sg in sorted(C.L.sig_of(Y, S.day, C.V5), key=lambda s: s["i"]):
                r = C.r_today(S, sg["i"])
                k = key(S.day, sg)
                R[k] = r
                if r is None:
                    continue
                if len(seen) >= 30:
                    srt = sorted(seen)
                    for q in QS:
                        THR[q][k] = float(np.quantile(srt, q))
                    RANK[k] = bisect.bisect_left(srt, r) / len(srt)
                seen.append(r)


_orig = C.gold_one


def gold_one_skip(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss):
    q = v.get("skip_r")
    if q:
        k = key(S.day, sg)
        thr, r = THR[q].get(k), R.get(k)
        if thr is not None and r is not None and r < thr:
            return None
    return _orig(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss)


def diagnostic():
    C.RECORD[0] = True
    C.TRADES.clear()
    C.run(C.V5, wallets=(C.STD_WALLETS[0], C.STD_WALLETS[2]))
    C.RECORD[0] = False
    Ys = C.years()
    sigs = {}
    for y in C.YEARS:
        Y = Ys[y]
        for S in Y.ordered():
            for sg in C.L.sig_of(Y, S.day, C.V5):
                sigs[(S.day, sg["i"])] = key(S.day, sg)
    out = {}
    for wname, W in (("A 15k", 15000.0), ("C 30k", 30000.0)):
        acc = collections.defaultdict(list)
        for t in C.TRADES:
            if t["wallet"] != W:
                continue
            rk = RANK.get(sigs.get((t["day"], t["i"])))
            b = "unranked" if rk is None else ("low third" if rk < 1 / 3 else "middle third" if rk < 2 / 3 else "high third")
            acc[(b, t["day"][:4])].append(t["net"] / t["lots"])
            acc[(b, "all")].append(t["net"] / t["lots"])
        out[wname] = {f"{b} | {y}": {"trades": len(v), "net_per_lot_sum": round(sum(v)), "mean": round(float(np.mean(v)))}
                      for (b, y), v in sorted(acc.items())}
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn113.json"
    if out_path.exists():
        raise SystemExit("SN113 is scored once")
    C.years()
    build_ratios()
    C.gold_one = gold_one_skip
    diag = diagnostic()
    for w, t in diag.items():
        print(f"--- Gold v5 trades at {w} by R_today at entry (causal rank)")
        for k, v in t.items():
            if k.endswith("| all"):
                print("  ", k, v)
        for k, v in t.items():
            if not k.endswith("| all"):
                print("     ", k, v)
    vs = {"SN Gold v5": dict(C.V5), **{f"SN113 skip below q{q}": {**C.V5, "skip_r": q} for q in QS}}
    res = {k: C.run(v) for k, v in vs.items()}
    assert all(C.totals(res["SN Gold v5"])[k] == x for k, x in C.V5_TOTALS.items())
    for k, r in res.items():
        t = C.totals(r)
        print(f"{k:24s} " + " ".join(f"{w.split()[0]} {t[w]:>8}" for w in ("A 15k 1 lot", "B 20k 1 lot", "C 30k sized", "G3 (Gold)", "G5")), flush=True)
    Lw = {w: C.loyo_wallet(res, w) for w in ("A 15k 1 lot", "B 20k 1 lot", "C 30k sized", "G3 (Gold)", "G5")}
    for w, L_ in Lw.items():
        print(f"  held out {w:12s} sum {L_['sum']['net']:>8} (v5 {C.totals(res['SN Gold v5'])[w]})", [(L_[y]['pick'], L_[y]['net']) for y in C.YEARS], flush=True)
    detail, ok = sn99.gold_pass(res, Lw)
    rob = {}
    for label, extra in (("stress 400", None), ("1 minute late", {"late": 1})):
        for w in ("C 30k sized", "G3 (Gold)"):
            sp = sv = 0
            for y in C.YEARS:
                old = C.L.STRESS
                if extra is None:
                    C.L.STRESS = 400.0
                try:
                    sp += C.run({**vs[Lw[w][y]["pick"]], **(extra or {})})[w][y]["net"]
                    sv += C.run({**C.V5, **(extra or {})})[w][y]["net"]
                finally:
                    C.L.STRESS = old
            rob[f"{label} | {w}"] = {"held_out_picks": sp, "v5": sv}
    survives = all(v["held_out_picks"] > v["v5"] for v in rob.values())
    print("GOLD PASS RULE", detail, "| robust:", rob, "| PASS" if (ok and survives) else "| NOT PROVEN", flush=True)
    big = {k: C.panel(C.run(vs[k], C.BIG_WALLETS)) for k in vs}
    for k, p in big.items():
        print(f"--- {k}: " + " | ".join(f"{w} {r['net']} (worst {r['worst']})" for w, r in p.items() if w in ("30k fixed", "30k grow stop 3", "50k grow stop 3")))
    out_path.write_text(json.dumps({"diagnostic": diag, "totals": {k: C.totals(r) for k, r in res.items()}, "loyo": Lw,
                                    "pass_detail": detail, "robust": rob, "PASS": bool(ok and survives), "every_wallet": big},
                                   indent=1, default=str), encoding="utf-8")
