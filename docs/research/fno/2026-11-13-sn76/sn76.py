"""SN76 - what Gold's winning, losing and no-trade days have in common (descriptive, all four seen years).

Each of the 742 sessions gets SN Gold v5's result at the Rs 15k wallet (frozen-copy lab, one lot) and:
  before the open  - yesterday's ADX and DMI direction, the volatility reading (N11's), the opening gap, days to expiry,
                     weekday;
  during the day   - range, open-to-close move, efficiency (net move / path), first-hour range, where the close sits
                     in the range;
  N11 itself       - how many N11 / R0.85 entries the day had, their strategies and sides.
Then: outcome shares per bucket, the reasons for no-trade days, and k-means clusters of the day shapes.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn51"))
import lab as L  # noqa: E402

V5 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": None, "in_atr": 1.0, "in_full": True,
      "itm_auto": (17500, 20000), "books": ("N11", "R0.85")}


def day_rows():
    L.VOLT.update(L.vol_table())
    adx = json.loads((HERE.parent / "2026-11-12-sn06" / "_local" / "daily.json").read_text(encoding="utf-8"))
    rows = []
    for y in L.YEARS:
        Y = L.B.Year(y)
        ctx = L.Ctx()
        for S in Y.ordered():
            sigs = L.sig_of(Y, S.day, V5)
            before = len(ctx.closed)
            net = L.play_day(S, sigs, V5, 15000.0, 1, ctx, False)
            trades = ctx.closed[before:]
            F = S.F
            o, h, l, c = F["o"], F["h"], F["l"], F["c"]
            path = float(np.abs(np.diff(c)).sum()) or 1.0
            rng = float(h.max() - l.min())
            rd = adx.get(S.day) or {}
            a, med = L.VOLT.get(S.day, (None, None))
            rows.append({
                "day": S.day, "year": y, "net": round(net, 2),
                "outcome": "win" if net > 0 else "loss" if net < 0 else "none",
                "signals": len(sigs), "trades": len(trades),
                "experts": sorted({s["expert"] for s in sigs}), "sides": sorted({s["opt"] for s in sigs}),
                "adx": rd.get("adx"), "dmi": rd.get("dir"), "vol_ratio": (a / med) if a and med else None,
                "gap_pct": 100 * F["gap"], "dte": (date.fromisoformat(S.s["expiry"]) - date.fromisoformat(S.day)).days,
                "weekday": date.fromisoformat(S.day).weekday(),
                "range_pct": 100 * rng / c[0], "move_pct": 100 * (c[-1] - o[0]) / o[0], "eff": abs(c[-1] - o[0]) / path,
                "hour1_pct": 100 * float(h[:60].max() - l[:60].min()) / c[0], "close_pos": (c[-1] - l.min()) / rng if rng else 0.5,
            })
    return rows


def share(rows, key, buckets):
    out = {}
    for name, test in buckets:
        b = [r for r in rows if r[key] is not None and test(r[key])]
        if b:
            n = len(b)
            out[name] = {"days": n, "win": round(sum(r["outcome"] == "win" for r in b) / n, 2),
                         "loss": round(sum(r["outcome"] == "loss" for r in b) / n, 2),
                         "none": round(sum(r["outcome"] == "none" for r in b) / n, 2),
                         "net": round(sum(r["net"] for r in b))}
    return out


def kmeans(X, k, seed=7, iters=100):
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), k, replace=False)]
    for _ in range(iters):
        lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
        newC = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
        if np.allclose(newC, C):
            break
        C = newC
    return lab, C


if __name__ == "__main__":
    rows = day_rows()
    out = {"days": len(rows), "outcomes": dict(Counter(r["outcome"] for r in rows))}
    nt = [r for r in rows if r["outcome"] == "none"]
    out["no_trade_reasons"] = {"no N11/R0.85 entry at all": sum(r["signals"] == 0 for r in nt),
                               "entries but none taken (busy / unaffordable)": sum(r["signals"] > 0 and r["trades"] == 0 for r in nt),
                               "traded to exactly zero": sum(r["trades"] > 0 for r in nt)}
    out["by_adx"] = share(rows, "adx", [("ADX < 20", lambda v: v < 20), ("20-25", lambda v: 20 <= v < 25), ("25-30", lambda v: 25 <= v < 30),
                                        ("30-40", lambda v: 30 <= v < 40), (">= 40", lambda v: v >= 40)])
    out["by_dmi"] = share(rows, "dmi", [("daily trend up", lambda v: v == 1), ("daily trend down", lambda v: v == -1)])
    out["by_vol"] = share(rows, "vol_ratio", [("vol < 0.85", lambda v: v < 0.85), ("0.85-1.0", lambda v: 0.85 <= v < 1.0),
                                              ("1.0-1.25", lambda v: 1.0 <= v < 1.25), (">= 1.25", lambda v: v >= 1.25)])
    out["by_gap"] = share(rows, "gap_pct", [("gap down > 0.5%", lambda v: v < -0.5), ("-0.5..-0.15", lambda v: -0.5 <= v < -0.15),
                                            ("flat", lambda v: -0.15 <= v <= 0.15), ("0.15..0.5", lambda v: 0.15 < v <= 0.5), ("gap up > 0.5%", lambda v: v > 0.5)])
    out["by_dte"] = share(rows, "dte", [("1 day", lambda v: v <= 1), ("2-3", lambda v: 2 <= v <= 3), ("4-5", lambda v: 4 <= v <= 5), ("6+", lambda v: v >= 6)])
    out["by_day_shape"] = share(rows, "eff", [("choppy (eff < 0.1)", lambda v: v < 0.1), ("0.1-0.2", lambda v: 0.1 <= v < 0.2),
                                              ("0.2-0.35", lambda v: 0.2 <= v < 0.35), ("trending (>= 0.35)", lambda v: v >= 0.35)])
    out["by_move"] = share(rows, "move_pct", [("down > 0.7%", lambda v: v < -0.7), ("-0.7..-0.25", lambda v: -0.7 <= v < -0.25),
                                              ("flat", lambda v: -0.25 <= v <= 0.25), ("0.25..0.7", lambda v: 0.25 < v <= 0.7), ("up > 0.7%", lambda v: v > 0.7)])
    out["by_range"] = share(rows, "range_pct", [("range < 0.6%", lambda v: v < 0.6), ("0.6-0.9", lambda v: 0.6 <= v < 0.9),
                                                ("0.9-1.3", lambda v: 0.9 <= v < 1.3), (">= 1.3%", lambda v: v >= 1.3)])
    # the gate x direction table: N11's low-ADX member only buys puts
    gd = defaultdict(lambda: Counter())
    for r in rows:
        if r["adx"] is None:
            continue
        g = "ADX>=30" if r["adx"] >= 30 else "ADX<30"
        m = "up day" if r["move_pct"] > 0.25 else "down day" if r["move_pct"] < -0.25 else "flat day"
        gd[f"{g} | {m}"][r["outcome"]] += 1
    out["gate_x_day"] = {k: dict(v) for k, v in sorted(gd.items())}
    tr = [r for r in rows if r["trades"]]
    exp = defaultdict(lambda: [0, 0, 0.0])
    for r in tr:
        for e in r["experts"]:
            exp[e][0] += 1
            exp[e][1] += r["outcome"] == "win"
            exp[e][2] += r["net"]
    out["trade_days_by_strategy"] = {e: {"days": v[0], "win_share": round(v[1] / v[0], 2), "net": round(v[2])} for e, v in exp.items()}
    feats = ["range_pct", "move_pct", "eff", "hour1_pct", "gap_pct", "close_pos"]
    X = np.array([[r[f] for f in feats] for r in rows], dtype=float)
    Z = (X - X.mean(0)) / X.std(0)
    lab_, C = kmeans(Z, 6)
    clusters = {}
    for j in range(6):
        m = [r for r, lj in zip(rows, lab_) if lj == j]
        cen = {f: round(float(X[lab_ == j][:, i].mean()), 2) for i, f in enumerate(feats)}
        clusters[f"cluster {j}"] = {"days": len(m), "centre": cen, "win": sum(r["outcome"] == "win" for r in m), "loss": sum(r["outcome"] == "loss" for r in m),
                                    "none": sum(r["outcome"] == "none" for r in m), "net": round(sum(r["net"] for r in m))}
    out["clusters"] = clusters
    (HERE / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    (HERE / "_local").mkdir(exist_ok=True)
    (HERE / "_local" / "days.json").write_text(json.dumps(rows), encoding="utf-8")
    for k, v in out.items():
        print(k, json.dumps(v)[:900], flush=True)
