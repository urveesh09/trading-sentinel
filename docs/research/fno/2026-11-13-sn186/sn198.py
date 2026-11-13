"""SN198 - the frozen TEST (PLAN.md): Gold's empty days of 2026-08-20 ... 10-28, scored once.
Candidates (the forward watches, frozen): SN95-L (causal admission, Rs 15k), SN171 (development HAR beta, kappa 1.1,
Rs 15k strangle / Rs 30k straddle), the SN197 leg; matched nulls = random TEST empty days with the same structure.
For the record (all failed development): SN187 / SN188 / SN189 / SN190 finals, SN191 LSTM entry and SN193 LSTM
direction with their saved TEST predictions."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402
import sn187  # noqa: E402
import sn188  # noqa: E402
import sn189  # noqa: E402
import sn191  # noqa: E402
import sn193  # noqa: E402
import sn197  # noqa: E402

pw, p3, pa, pb, C = pe.pw, pe.p3, pe.pa, pe.pb, pe.C
SN161_LOCAL = HERE.parent / "2026-11-13-sn161" / "_local"


def null(pool, k, draws=2000, seed=198):
    rng = np.random.default_rng(seed)
    if not pool or not k:
        return 0, 0
    t = [float(np.sum(rng.choice(pool, min(k, len(pool)), replace=False))) for _ in range(draws)]
    return round(float(np.mean(t))), round(float(np.percentile(t, 95)))


if __name__ == "__main__":
    out_path = HERE / "results-sn198.json"
    if out_path.exists():
        raise SystemExit("SN198 is scored once")
    E = pe.empty_sessions(test=True)
    edays = [S.day for S in E]
    f171 = pickle.loads((SN161_LOCAL / "sn171_final.pkl").read_bytes())
    har = p3.HAR(E)
    rho = {}
    for S in E:
        fs, si = har.sigma(S.day, f171["beta"], f171["s2"]), C.sigma_imp(S, p3.I1000)
        if fs and si:
            rho[S.day] = fs / si
    adm = pa.admission()
    res = {"test_empty_days": len(E), "from": edays[0], "to": edays[-1], "candidates": {}, "record": {}}
    struct = {"SN95-L": lambda S: (lambda g: None if g is None or g[1] > 15000.0 else pb.net(g))(pa.path(S, pa.I10)),
              "SN171 Rs 15k strangle": lambda S: p3.structure(S, p3.I1000, "strangle1", 15000.0, 3000.0),
              "SN171 Rs 30k straddle": lambda S: p3.structure(S, p3.I1000, "straddle", 30000.0, 6000.0)}
    admit = {"SN95-L": lambda d: adm.get((d, "10:00", "R_today", 0.2, "top"), False),
             "SN171 Rs 15k strangle": lambda d: rho.get(d, 0) >= 1.1, "SN171 Rs 30k straddle": lambda d: rho.get(d, 0) >= 1.1}
    for name in struct:
        allv = {S.day: struct[name](S) for S in E}
        dn = {d: n for d, n in allv.items() if n and admit[name](d)}
        nm, n95 = null([n for n in allv.values() if n], len(dn))
        res["candidates"][name] = {"net": round(sum(dn.values())), "trades": len(dn), "days": sorted(dn), "null_mean": nm, "null_p95": n95,
                                   "PASS": bool(sum(dn.values()) >= 0 and (not dn or sum(dn.values()) > n95))}
    r126 = json.loads((C.FNO / "2026-11-13-sn121" / "results-sn126.json").read_text(encoding="utf-8"))
    s126 = {d: v for d, v in r126["heldout_day_nets"].items() if v}
    for key, wallet in (("Rs 15k", 15000.0), ("Rs 30k", 30000.0)):
        leg = sn197.leg_nets(E, wallet, rho, adm, s126)
        res["candidates"][f"SN197 leg {key}"] = {**pe.goal_stats(leg, edays, 1000.0), "days": sorted(leg)}
    res["record"]["SN187 pair 10:00 goal 1500 stop 2000"] = round(sum((sn187.play(S, 45, ("pair", 1500.0, 2000.0)) or 0.0) for S in E))
    hot = sn188.hot_days()
    res["record"]["SN188 goal 1000 stop 1000 (hot)"] = round(sum((sn188.day(S, 1000.0, 1000.0) or 0.0) for S in E if S.day in hot))
    res["record"]["SN189 fly kappa 0.75 goal 1500 stop 3000"] = round(sum((sn189.fly(S, 1500.0, 3000.0) or 0.0) for S in E if rho.get(S.day, 9) < 0.75))
    d191 = sn191.build()
    t191 = pickle.loads((pe.LOCAL / "sn191_test.pkl").read_bytes())
    dn, _c = sn191.policy(d191, t191["P_test"], set(edays), t191["theta"])
    res["record"]["SN191 LSTM entry"] = {"net": round(sum(dn.values())), "trade_days": len(dn)}
    d193 = sn193.build()
    t193 = pickle.loads((pe.LOCAL / "sn193_test.pkl").read_bytes())
    dec = {}
    for r in np.flatnonzero(~np.isnan(t193["P_test"])):
        dec.setdefault(d193["day"][r], []).append((int(d193["i"][r]), float(t193["P_test"][r])))
    tot, nd = 0.0, 0
    for S in E:
        n, _k = sn193.day_trades(S, dec.get(S.day, []), t193["theta"])
        if n is not None:
            tot += n
            nd += 1
    res["record"]["SN193 LSTM direction"] = {"net": round(tot), "trade_days": nd}
    print("SN198", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
