"""SN125 - the last half-hour, holding to 15:25 (PLAN.md): buy the ATM option at 15:00 in the direction of
(a) previous close -> 09:45, (b) 14:30 -> 15:00, (c) the opening gap, (d) a and b agreeing; sell at the bid at 15:25.
1 lot, strict; Gold-free (primary) and all days; LOYO over the 4 signals; random side (2,000 draws) as NULL."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pg  # noqa: E402

C, M = pg.C, pg.M
I_IN, I_OUT = 345, 370


def leg(S, d, stress=205.0, late=0):
    i = I_IN + late
    K = int(round(S.F["c"][i] / M.STEP) * M.STEP)
    rec = S.option(K, "CE" if d > 0 else "PE")
    if rec is None or not rec[6][i]:
        return None
    ask = M.ask_of(float(rec[0][3][i]))
    if ask * M.LOT > 15000:
        return None
    m = pg.mark(S, K, "CE" if d > 0 else "PE", I_OUT)
    if m is None:
        return None
    b = M.bid_of(m)
    return (b - ask) * M.LOT - M.charges(ask, b, M.LOT) - stress


def signals(S):
    c, o = S.F["c"], S.F["o"]
    pdc = S.s["prev"][3] if S.s.get("prev") else o[0]
    a = int(np.sign(c[29] - pdc))
    b = int(np.sign(c[344] - c[314]))
    g = int(np.sign(o[0] - pdc))
    return {"first half-hour": a, "14:30-15:00": b, "gap": g, "both agree": a if a == b else 0}


if __name__ == "__main__":
    out_path = HERE / "results-sn125.json"
    if out_path.exists():
        raise SystemExit("SN125 is scored once")
    sessions = pg.all_sessions()
    rng = np.random.default_rng(125)
    res = {}
    for dname, ok in (("gold-free", C.gold_free), ("all days", lambda d: C.adx(d) is not None)):
        rows = {}
        for S in sessions:
            if not ok(S.day):
                continue
            rows[S.day] = {"sig": signals(S), "ce": leg(S, 1), "pe": leg(S, -1), "ce400": leg(S, 1, 400.0), "pe400": leg(S, -1, 400.0),
                           "ce_late": leg(S, 1, late=1), "pe_late": leg(S, -1, late=1)}

        def net(r, s, suffix=""):
            if s == 0:
                return 0.0
            v = r[("ce" if s > 0 else "pe") + suffix]
            return v if v is not None else 0.0
        tab = {}
        for k in ("first half-hour", "14:30-15:00", "gap", "both agree"):
            per = {}
            for y in C.YEARS:
                xs = [net(r, r["sig"][k]) for d, r in rows.items() if d[:4] == y and r["sig"][k] != 0]
                per[y] = {"net": round(sum(xs)), "green": sum(x > 0 for x in xs), "red": sum(x < 0 for x in xs), "trades": len(xs)}
            tab[k] = per
        Lr = C.loyo(tab, "profit")
        held_days = {d: net(r, r["sig"][Lr[d[:4]]["pick"]]) for d, r in rows.items() if r["sig"][Lr[d[:4]]["pick"]] != 0}
        draws = []
        keys = list(held_days)
        for _ in range(2000):
            s = 0.0
            for d in keys:
                r = rows[d]
                v = r["ce"] if rng.random() < 0.5 else r["pe"]
                s += v if v is not None else 0.0
            draws.append(s)
        rob = {"stress 400": round(sum(net(rows[d], rows[d]["sig"][Lr[d[:4]]["pick"]], "400") for d in keys)),
               "1 minute late": round(sum(net(rows[d], rows[d]["sig"][Lr[d[:4]]["pick"]], "_late") for d in keys))}
        xs = sorted(held_days.values(), reverse=True)
        held = [Lr[y]["net"] for y in C.YEARS]
        verdict = {"held_out": Lr["sum"]["net"], "years": held, "trades": len(keys), "random_95th": round(float(np.percentile(draws, 95))),
                   "without_best_5": round(sum(xs[5:])), "robust": rob}
        verdict["PASS"] = bool(Lr["sum"]["net"] > 0 and sum(x > 0 for x in held) >= 3 and Lr["sum"]["net"] > verdict["random_95th"]
                               and all(v > 0 for v in rob.values()))
        res[dname] = {"tables": tab, "loyo": Lr, "verdict": verdict, "heldout_day_nets": held_days}
        print(f"=== SN125 {dname}")
        for k, per in tab.items():
            print(f"   {k:16s}", [per[y]["net"] for y in C.YEARS], sum(per[y]["net"] for y in C.YEARS), "trades", sum(per[y]["trades"] for y in C.YEARS))
        print("   LOYO", {y: (Lr[y]["pick"], Lr[y]["net"]) for y in C.YEARS}, "VERDICT", verdict, flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
