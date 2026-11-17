"""SN351: where is a profitable bought-option move still available? (PLAN.md section 1; the details below are amendment
A4, fixed in this docstring before any SN351 number.)

Decisions: 09:30, 10:30, 11:30, 12:30, 13:30 (non-overlapping 60-minute horizons); the front-weekly ATM CE and PE, one lot
each; non-expiry sessions. Samples: gl's DEV (NIFTY Apr 2022 - Aug 19, 2026, modelled quotes) and the real-quote archive
(Sep 10 - Nov 13, 2026 non-expiry days, walked one-lot ask / bid of usable quotes; the ATM strike from the front future's
mid rounded to 50).
State at the decision, from the index (DEV) or the front future's mid (archive), r(a, b) = the return from minute a to b:
  JUST_MOVED  |r(t-15, t)| >= 0.25%
  SETTLED     |r(t-30, t-15)| >= 0.25% and |r(t-15, t)| < 0.10%      (on the archive also: the option's spread at or
              below its own session median; DEV spreads are a table, so the spread test is archive-only)
  QUIET       |r(t-15, t)| < 0.10% and not SETTLED
  OTHER       everything else
  Side relation for JUST_MOVED / SETTLED: WITH (CE after an up move, PE after a down move) or AGAINST.
Per position, the path v(j) = net rupees if sold at minute j (charges, no stress), j = 1..60:
  quoted cost = (ask - bid) x lot at entry + round-trip charges at the entry price;
  first +300 / +750: the first minute v(j) >= 300 / 750 (stress 0), before any stop;
  stopped first: v(j) - stress <= -3,000 before v(j) >= +300 (reported at Rs 205);
  net at 5 / 20 / 60 minutes at stress 0 / 205 / 400, with the Rs 3,000 stop applied at that stress;
  hindsight ceiling = max v(j) over 60 minutes (stress 0), kept apart from realized returns.
Room (frozen): a state x side has room if its mean 20- or 60-minute net at Rs 205 > 0 with >= 100 decisions on DEV and the
same sign on the archive. A state with room is a target for a predictor, never a strategy.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn251"))
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
import gl  # noqa: E402
import qa  # noqa: E402

qa.EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
                 r"\_local\exports\20261116T103002Z")
OUT = HERE / "results-sn351.json"
CLOCKS = {"09:30": 15, "10:30": 75, "11:30": 135, "12:30": 195, "13:30": 255}
HOR = 60
STOP = 3000.0
LOT = 65


def state(series, t):
    def r(a, b):
        x, y = series(a), series(b)
        return None if x is None or y is None or x <= 0 else y / x - 1.0
    r1, r0 = r(t - 15, t), r(t - 30, t - 15)
    if r1 is None:
        return None, 0
    if abs(r1) >= 0.0025:
        return "JUST_MOVED", 1 if r1 > 0 else -1
    if r0 is not None and abs(r0) >= 0.0025 and abs(r1) < 0.001:
        return "SETTLED", 1 if r0 > 0 else -1
    if abs(r1) < 0.001:
        return "QUIET", 0
    return "OTHER", 0


def path_stats(v, cost):
    """v: list of (j, value at stress 0) for j = 1..60 (missing minutes absent)."""
    out = {"cost": cost, "ceiling": max((x for _j, x in v), default=None)}
    for tgt in (300, 750):
        hit = next((j for j, x in v if x >= tgt), None)
        out[f"t{tgt}"] = hit
    for st in (0.0, 205.0, 400.0):
        for H in (5, 20, 60):
            net = None
            for j, x in v:
                if j > H:
                    break
                if x - st <= -STOP:
                    net = x - st
                    break
                net = x - st
            out[f"n{H}@{int(st)}"] = net
    s205 = next((j for j, x in v if x - 205.0 <= -STOP), None)
    t300 = out["t300"]
    out["stopped_first"] = s205 is not None and (t300 is None or s205 < t300)
    return out


def dev_rows():
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("DEV", raw, gl.DEV_LO, gl.TEST_LO)
    rows = []
    for d in smp.days:
        s = smp.s[d]
        if s["day"] == s["expiry"]:
            continue
        idx = s["index"][3]

        def ser(i, idx=idx):
            return None if i < 0 or i >= len(idx) or np.isnan(idx[i]) else float(idx[i])
        for c, i in CLOCKS.items():
            stt, sg = state(ser, i)
            if stt is None:
                continue
            k = gl.atm(smp, s, i)
            for side in ("CE", "PE"):
                pos = gl.Pos(smp, s, [(k, side, +1)], i, lots=1, stress=0.0)
                if not pos.ok:
                    continue
                v = [(j - i, x) for j in range(i + 1, i + HOR + 1) if (x := pos.value(s, j)) is not None]
                f = pos.fills[0]
                p = gl.opx(s, k, side, i)
                cost = (f - gl.wk.bid(gl.wk.NIFTY, p)) * LOT + gl.wk.charges(f, f, LOT, "NFO")
                rel = None if sg == 0 else ("WITH" if (side == "CE") == (sg > 0) else "AGAINST")
                rows.append({"day": d, "clock": c, "state": stt, "rel": rel, "side": side, **path_stats(v, cost)})
    return rows


def arch_rows():
    rows = []
    for d in qa.days():
        q = qa.load(d)
        exps = sorted({k[1] for k in q["opt"] if k[0] == "NIFTY" and k[1] >= d})
        if not exps or exps[0] == d:
            continue
        e = exps[0]
        fut = qa.front_fut(q, "NIFTY")
        if fut is None:
            continue

        def ser(i, fut=fut):
            j = None if i < 0 else qa.last_before(fut, i, max(0, i - 2))
            return None if j is None else 0.5 * (fut["bid"][j] + fut["ask"][j])
        for c, i in CLOCKS.items():
            stt, sg = state(ser, i)
            if stt is None:
                continue
            m = ser(i)
            k = int(round(m / 50.0) * 50)
            for side in ("CE", "PE"):
                rec = q["opt"].get(("NIFTY", e, k, side))
                if rec is None:
                    continue
                i0 = qa.last_before(rec, i, i - 1)
                if i0 is None:
                    continue
                entry = qa.walk_cost(rec["askp"][:, i0], rec["askq"][:, i0], LOT)
                if entry is None:
                    continue
                spread = rec["ask"][i0] - rec["bid"][i0]
                ok_sp = np.array([rec["ask"][x] - rec["bid"][x] for x in range(qa.NM) if rec["usable"][x]])
                calm = bool(len(ok_sp)) and spread <= float(np.median(ok_sp))
                stt2 = stt if not (stt == "SETTLED" and not calm) else "OTHER"
                v = []
                for j in range(i0 + 1, min(qa.NM, i0 + HOR + 1)):
                    if not rec["usable"][j]:
                        continue
                    b = qa.walk_cost(rec["bidp"][:, j], rec["bidq"][:, j], LOT)
                    if b is not None:
                        v.append((j - i0, (b - entry) * LOT - gl.wk.charges(entry, b, LOT, "NFO")))
                cost = spread * LOT + gl.wk.charges(entry, entry, LOT, "NFO")
                rel = None if sg == 0 else ("WITH" if (side == "CE") == (sg > 0) else "AGAINST")
                rows.append({"day": d, "clock": c, "state": stt2, "rel": rel, "side": side, **path_stats(v, cost)})
    return rows


def summarize(rows):
    out = {}
    groups = {}
    for r in rows:
        key = r["state"] + ("" if r["rel"] is None else f" {r['rel']}")
        groups.setdefault(key, []).append(r)
        groups.setdefault("ALL", []).append(r)
    for key, rs in sorted(groups.items()):
        g = {"n": len(rs), "cost": round(float(np.mean([r["cost"] for r in rs])), 1),
             "p_hit300": round(float(np.mean([r["t300"] is not None for r in rs])), 3),
             "p_hit750": round(float(np.mean([r["t750"] is not None for r in rs])), 3),
             "median_t300": None, "p_stopped_first@205": round(float(np.mean([r["stopped_first"] for r in rs])), 3),
             "ceiling_mean": round(float(np.mean([r["ceiling"] for r in rs if r["ceiling"] is not None])), 1)}
        hits = [r["t300"] for r in rs if r["t300"] is not None]
        if hits:
            g["median_t300"] = float(np.median(hits))
        for H in (5, 20, 60):
            for st in (0, 205, 400):
                xs = [r[f"n{H}@{st}"] for r in rs if r[f"n{H}@{st}"] is not None]
                g[f"n{H}@{st}"] = round(float(np.mean(xs)), 1) if xs else None
        xs = [r["n20@205"] for r in rs if r["n20@205"] is not None]
        g["se20@205"] = round(float(np.std(xs, ddof=1) / math.sqrt(len(xs))), 1) if len(xs) > 1 else None
        out[key] = g
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN351 is run once")
    dv, ar = dev_rows(), arch_rows()
    res = {"DEV": summarize(dv), "ARCHIVE": summarize(ar), "DEV_by_clock": {c: summarize([r for r in dv if r["clock"] == c]).get("ALL") for c in CLOCKS}}
    room = {}
    for key, g in res["DEV"].items():
        if key == "ALL":
            continue
        a = res["ARCHIVE"].get(key, {})
        for H in (20, 60):
            x = g.get(f"n{H}@205")
            y = a.get(f"n{H}@205")
            if g["n"] >= 100 and x is not None and x > 0 and y is not None and y > 0:
                room[f"{key} {H}m"] = {"dev": x, "archive": y, "dev_n": g["n"], "archive_n": a.get("n")}
    res["room"] = room
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for k in ("DEV", "ARCHIVE"):
        for key, g in res[k].items():
            print(k, key, json.dumps({x: g[x] for x in ("n", "cost", "p_hit300", "p_stopped_first@205", "ceiling_mean", "n20@0", "n20@205", "n60@0", "n60@205")}), flush=True)
    print("room", json.dumps(room))


if __name__ == "__main__":
    main()
