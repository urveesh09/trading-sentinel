"""SN80-SN83 (research only): the web's day-type predictors, and a breakout book for Gold's empty days built on them.

SN80 (descriptive): do the retail "narrow CPR -> trend day" and "tight opening range coils" claims hold on NIFTY
     2023-Oct 2026? CPR from yesterday's H/L/C: P=(H+L+C)/3, BC=(H+L)/2, TC=2P-BC, width=|TC-BC|/P; ranked against the
     previous 20 sessions. Opening range = 09:15-09:45. Target: today's range % and efficiency.
SN81-83: on Gold-free days (yesterday's ADX < 30, before the open), the first 1-minute close beyond the 30-minute
     opening range (buffer x ATR) after 09:45, in the break's direction, ONLY on predicted-expansion days (narrow CPR,
     tight OR, both, or no filter); exits: HOLD (index trail k x 1-minute ATR, 25% premium backstop, flat 15:00) or
     QUICK (index target 0.5 / 1 R of the stop, 45-minute clock). One lot, Rs 30k day limit, charges + Rs 205 per lot.
     NULL: the same days and minutes with a random side. Leave one year out over the small grid.
"""
from __future__ import annotations

import itertools
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
for p in ("2026-11-12-sn01", "2026-11-12-sn03", "2026-11-12-sn04"):
    sys.path.insert(0, str(HERE.parent / p))
import sn01_data as D  # noqa: E402
import sn01_sim as M  # noqa: E402
import sn04 as Q  # noqa: E402
from sn03_run import loyo  # noqa: E402

YEARS = ("2023", "2024", "2025", "2026")


def day_table():
    adx = json.loads((HERE.parent / "2026-11-12-sn06" / "_local" / "daily.json").read_text(encoding="utf-8"))
    out = {}
    for y in YEARS:
        widths, ors = [], []
        for day, s in sorted(D.load_year(y)["sessions"].items()):
            S = M.Session(s)
            prev = s.get("prev")
            if not prev:
                continue
            H, Lw, C = prev[1], prev[2], prev[3]
            P = (H + Lw + C) / 3
            BC = (H + Lw) / 2
            TC = 2 * P - BC
            w = abs(TC - BC) / P * 100
            F = S.F
            orr = (F["h"][:30].max() - F["l"][:30].min()) / F["c"][0] * 100
            cw = sum(x < w for x in widths[-20:]) / max(1, len(widths[-20:])) if len(widths) >= 10 else None
            orank = sum(x < orr for x in ors[-20:]) / max(1, len(ors[-20:])) if len(ors) >= 10 else None
            widths.append(w)
            ors.append(orr)
            c, o, h, l = F["c"], F["o"], F["h"], F["l"]
            out[day] = {"S": S, "cpr_w": w, "cpr_rank": cw, "or_pct": orr, "or_rank": orank, "adx": (adx.get(day) or {}).get("adx"),
                        "range_pct": (h.max() - l.min()) / c[0] * 100, "after_or_range": (h[30:].max() - l[30:].min()) / c[0] * 100,
                        "eff": abs(c[-1] - o[0]) / (np.abs(np.diff(c)).sum() or 1), "year": y}
    return out


def or_break_sig(S, buf):
    F = S.F
    c, atr = F["c"], F["atr"]
    hi, lo = F["h"][:30].max(), F["l"][:30].min()
    sig = np.zeros(len(c), np.int8)
    for i in range(30, 300):
        if c[i] > hi + buf * atr[i]:
            sig[i] = 1
            break
        if c[i] < lo - buf * atr[i]:
            sig[i] = -1
            break
    return sig


EXITS = {"HOLD k3": {"stop_k": 3.0, "target_r": 0.0, "trail_r": 0.5, "trail_k": 3.0, "time": 400, "backstop": 0.25},
         "HOLD k6": {"stop_k": 6.0, "target_r": 0.0, "trail_r": 1.0, "trail_k": 6.0, "time": 400, "backstop": 0.25},
         "QUICK 0.5R": {"stop_k": 3.0, "target_r": 0.5, "trail_r": 0.0, "trail_k": 3.0, "time": 45, "backstop": 0.25},
         "QUICK 1R": {"stop_k": 3.0, "target_r": 1.0, "trail_r": 0.0, "trail_k": 3.0, "time": 45, "backstop": 0.25}}
GATES = ("none", "cpr_narrow", "or_tight", "both")


def gate_ok(r, gate):
    if r["adx"] is None or r["adx"] >= 30:
        return False
    if gate == "none":
        return True
    cn = r["cpr_rank"] is not None and r["cpr_rank"] <= 0.33
    ot = r["or_rank"] is not None and r["or_rank"] <= 0.33
    return {"cpr_narrow": cn, "or_tight": ot, "both": cn and ot}[gate]


if __name__ == "__main__":
    T = day_table()
    rows = list(T.values())
    out = {"sn80": {}}
    for key in ("cpr_rank", "or_rank"):
        b = {}
        for name, lo, hi in (("narrow third", -1, 0.33), ("middle third", 0.33, 0.67), ("wide third", 0.67, 2)):
            g = [r for r in rows if r[key] is not None and lo < r[key] <= hi]
            b[name] = {"days": len(g), "mean_range_pct": round(float(np.mean([r["range_pct"] for r in g])), 3),
                       "mean_range_after_09:45": round(float(np.mean([r["after_or_range"] for r in g])), 3),
                       "share_range_ge_1.3": round(float(np.mean([r["range_pct"] >= 1.3 for r in g])), 3),
                       "mean_eff": round(float(np.mean([r["eff"] for r in g])), 3)}
        out["sn80"][key] = b
    print("SN80", json.dumps(out["sn80"], indent=0)[:1400], flush=True)
    table = {}
    rng = random.Random(80)
    for gate, buf, (ename, ex), null in itertools.product(GATES, (0.0, 0.25), EXITS.items(), (False, True)):
        g = {"start": 30, "last_entry": 300, "max_trades": 1, "offset": 0, **ex}
        per = {}
        for y in YEARS:
            nets = []
            for day, r in T.items():
                if r["year"] != y or not gate_ok(r, gate):
                    continue
                sig = or_break_sig(r["S"], buf)
                if null and sig.any():
                    sig = sig * (1 if rng.random() < 0.5 else -1)
                nets.append(Q.run_day(r["S"], g, 15000.0, 3000.0, 205.0, sig=sig)["net"])
            per[y] = {"net": round(sum(nets)), "green": sum(v > 0 for v in nets), "red": sum(v < 0 for v in nets),
                      "none": sum(v == 0 for v in nets), "refilled": round(sum(-v for v in nets if v < 0)), "days": len(nets)}
        table[f"{'NULL ' if null else ''}{gate} buf{buf} {ename}"] = per
    real = {k: v for k, v in table.items() if not k.startswith("NULL")}
    nul = {k: v for k, v in table.items() if k.startswith("NULL")}
    for k, v in sorted(table.items(), key=lambda kv: -sum(x["net"] for x in kv[1].values()))[:10]:
        print(f"{k:34s}", [v[y]["net"] for y in YEARS], sum(v[y]["net"] for y in YEARS), "won/lost", sum(v[y]["green"] for y in YEARS), sum(v[y]["red"] for y in YEARS))
    Lr, Ln = loyo(real, "profit"), loyo(nul, "profit")
    print("LOYO real", {y: (Lr[y]["pick"], Lr[y]["net"]) for y in YEARS}, "sum", Lr["sum"]["net"])
    print("LOYO null", {y: Ln[y]["net"] for y in YEARS}, "sum", Ln["sum"]["net"])
    out["table"], out["loyo_real"], out["loyo_null"] = table, Lr, Ln
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
