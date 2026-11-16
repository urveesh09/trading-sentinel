"""SN376: the opening direction through a vega-light (in-the-money) option (PLAN.md section 2, frozen at 3740b461).

Same samples and directions as SN371 (GAP 2022-2026 with |gap| >= 0.10%, AUCTION Dec 2025 - Oct 2026), non-expiry.
Leg: 1 strike in the money on the direction's side (CE: ATM - 50, PE: ATM + 50), or 2 strikes when one lot of the
2-ITM costs <= Rs 15,000 at the model ask (the wallet - Rs 15,000 room of a Rs 30,000 wallet); gl's executable model.
Entry clocks: 09:16 (minute 1) and 10:15 (minute 60, SN371's cap: skip when traveled >= +0.4%). Holds 20 and 60 minutes,
Rs 3,000 stop, stress 0 / 205 / 400.
Compared on the same sessions: ATM on the direction's side (same clock and hold), and a coin-flip side at the same
in-the-money depth.
Advance (as SN371, per clock x hold; all four reported, the multiplicity noted): net at Rs 205 > 0 on GAP (>= 200
trades, >= 3 of 5 years positive) and AUCTION (>= 60 trades), both above the coin flip.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn371 as S  # noqa: E402

gl, sn353b = S.gl, S.sn353b
OUT = HERE / "results-sn376.json"
CLOCKS = {"09:16": 1, "10:15": 60}
HOLDS = (20, 60)


def leg(smp, s, side, i, stress, depth_choice=None):
    atm = gl.atm(smp, s, i)
    step = 50
    sgn = -1 if side == "CE" else 1
    for depth in ((2, 1) if depth_choice is None else (depth_choice,)):
        k = atm + sgn * depth * step
        pos = gl.Pos(smp, s, [(k, side, +1)], i, lots=1, stress=stress)
        if pos.ok and (depth == 1 or pos.premium <= 15000.0):
            return pos, depth
    return None, None


def run(smp, days, dirs):
    rows = []
    for d in days:
        if d not in dirs:
            continue
        s = smp.s[d]
        sgn = dirs[d]
        idx = s["index"][3]
        if np.isnan(idx[1]) or np.isnan(idx[60]):
            continue
        T = (float(idx[60]) / float(idx[1]) - 1.0) * sgn
        side = "CE" if sgn > 0 else "PE"
        coin = random.Random(f"sn376-{d}").choice(("CE", "PE"))
        r = {"day": d, "year": d[:4]}
        for cname, i in CLOCKS.items():
            if cname == "10:15" and T >= 0.004:
                continue
            for arm, sd in (("ITM", side), ("COIN_ITM", coin), ("ATM", side)):
                for st in (0.0, 205.0, 400.0):
                    if arm == "ATM":
                        pos = gl.Pos(smp, s, [(gl.atm(smp, s, i), sd, +1)], i, lots=1, stress=st)
                        dep = 0 if pos.ok else None
                    else:
                        pos, dep = leg(smp, s, sd, i, st)
                    if pos is None or not pos.ok:
                        continue
                    for H in HOLDS:
                        net, _j, _w = gl.walk(pos, s, i, i + H, room=S.STOP)
                        if net is not None:
                            r[f"{cname} {arm} {H}m@{int(st)}"] = round(net, 2)
                    r[f"{cname} {arm} depth"] = dep
                    r[f"{cname} {arm} premium"] = round(pos.premium)
        rows.append(r)
    return rows


def summarize(rows):
    out = {"sessions": len(rows)}
    for cname in CLOCKS:
        for arm in ("ITM", "COIN_ITM", "ATM"):
            for H in HOLDS:
                for st in (0, 205, 400):
                    k = f"{cname} {arm} {H}m@{st}"
                    xs = [r[k] for r in rows if k in r]
                    out[k] = {"n": len(xs), "per_trade": round(float(np.mean(xs)), 1) if xs else None}
        deps = [r.get(f"{cname} ITM depth") for r in rows if r.get(f"{cname} ITM depth")]
        out[f"{cname} ITM depth2 share"] = round(float(np.mean([x == 2 for x in deps])), 3) if deps else None
        prem = [r.get(f"{cname} ITM premium") for r in rows if r.get(f"{cname} ITM premium")]
        out[f"{cname} ITM premium mean"] = round(float(np.mean(prem))) if prem else None
        for H in HOLDS:
            yrs = {}
            for r in rows:
                x = r.get(f"{cname} ITM {H}m@205")
                if x is not None:
                    yrs.setdefault(r["year"], []).append(x)
            out[f"{cname} ITM {H}m@205 by year"] = {y: round(float(np.mean(v)), 1) for y, v in sorted(yrs.items())}
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN376 is run once")
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("ALL", raw, gl.DEV_LO, gl.TEST_HI)
    days = [d for d in smp.days if smp.s[d]["day"] != smp.s[d]["expiry"]]
    gap = {}
    for d in days:
        pb = smp.prev_bar(d)
        o = smp.s[d]["index"][0][0]
        if pb is None or np.isnan(o):
            continue
        g = float(o) / float(pb[3]) - 1.0
        if abs(g) >= 0.001:
            gap[d] = 1 if g > 0 else -1
    au = sn353b.auctions([d for d in days if sn353b.LO <= d < sn353b.HI])
    auc = {d: (1 if a["g"] > 0 else -1) for d, a in au.items() if a["g"] != 0}
    res = {"GAP": summarize(run(smp, days, gap)), "AUCTION": summarize(run(smp, days, auc))}
    adv = {}
    for cname in CLOCKS:
        for H in HOLDS:
            g, a = res["GAP"], res["AUCTION"]
            k = f"{cname} ITM {H}m@205"
            c = f"{cname} COIN_ITM {H}m@205"
            yrs = g[f"{cname} ITM {H}m@205 by year"]
            adv[f"{cname} {H}m"] = bool(g[k]["per_trade"] is not None and g[k]["per_trade"] > 0 and g[k]["n"] >= 200 and sum(v > 0 for v in yrs.values()) >= 3
                                        and a[k]["per_trade"] is not None and a[k]["per_trade"] > 0 and a[k]["n"] >= 60
                                        and g[k]["per_trade"] > (g[c]["per_trade"] or -1e9) and a[k]["per_trade"] > (a[c]["per_trade"] or -1e9))
    res["advance"] = adv
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for smpl in ("GAP", "AUCTION"):
        for cname in CLOCKS:
            for H in HOLDS:
                print(smpl, cname, H, "ITM", [res[smpl][f"{cname} ITM {H}m@{st}"]["per_trade"] for st in (0, 205, 400)],
                      "ATM", [res[smpl][f"{cname} ATM {H}m@{st}"]["per_trade"] for st in (0, 205, 400)],
                      "COIN_ITM", [res[smpl][f"{cname} COIN_ITM {H}m@{st}"]["per_trade"] for st in (0, 205, 400)],
                      "n", res[smpl][f"{cname} ITM {H}m@205"]["n"], flush=True)
        print(smpl, "depth2", res[smpl]["09:16 ITM depth2 share"], "premium", res[smpl]["09:16 ITM premium mean"], "years 09:16 20m", res[smpl]["09:16 ITM 20m@205 by year"])
    print("advance", adv)


if __name__ == "__main__":
    main()
