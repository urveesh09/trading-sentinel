"""SN410 (own): did NSE's September 7, 2026 pre-open change remove the opening edge? (PLAN.md section 2, frozen at
00693405; details fixed here before any SN410 number.)

A. Breeze (Dec 8, 2025 - Oct 28, 2026; sn353b's AUCTION sessions with g != 0), on the auction contract's 1-minute futures:
   gap = A - C0 (points); first-minute drift = (09:15 close - A) x dir (the price at 09:16:00 against the match);
   follow-through = (10:15 close - 09:15 close) x dir (09:16:00 -> 10:16:00, the HONEST hour); share = follow / |gap|.
   Per period (before / from Sep 7): mean, median, t, share positive, the mean |gap|; and the HONEST ITM trade's mid change
   split as SN397 (delta / vega / theta / residual, costs) by period.
B. The real-quote archive (sealed days Sep 10 - Nov 13, non-expiry for the NIFTY front weekly): for front-week options
   within 100 points of the front future's last price, the snapshot in each window [09:16, 09:17), [10:16, 10:17),
   [11:00, 11:01): per-lot top-of-book spread and the one-lot walked ask over the mid. Medians by window (post-change
   only: the archive starts Sep 10).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import op  # noqa: E402
import sn396  # noqa: E402
import sn397  # noqa: E402

gl = op.gl
OUT = HERE / "results-sn410.json"
HIST = op.sn353b.HIST


def stats(xs):
    xs = np.array([x for x in xs if x is not None], float)
    if len(xs) < 2:
        return {"n": int(len(xs))}
    return {"n": int(len(xs)), "mean": round(float(xs.mean()), 2), "median": round(float(np.median(xs)), 2),
            "t": round(float(xs.mean() / (xs.std(ddof=1) / np.sqrt(len(xs)))), 2), "share_positive": round(float((xs > 0).mean()), 3)}


def part_a(smp, au):
    con = sqlite3.connect(f"file:{HIST.as_posix()}?mode=ro", uri=True, timeout=60)
    q = ("SELECT close FROM candles WHERE kind='future' AND underlying='NIFTY' AND expiry=? AND strike=0 AND opt='' AND interval='1minute' AND datetime=?")
    rows = []
    for d, a in sorted(au.items()):
        if a["g"] == 0:
            continue
        f0 = con.execute(q, (a["expiry"], d + " 09:15:00")).fetchone()
        f60 = con.execute(q, (a["expiry"], d + " 10:15:00")).fetchone()
        if not f0 or not f60:
            continue
        dr = 1 if a["g"] > 0 else -1
        gap = a["A"] - a["C0"]
        r = {"day": d, "period": "post" if d >= op.SPLIT else "pre", "src": a["how"], "gap_pts": gap, "abs_gap": abs(gap),
             "drift": (float(f0[0]) - a["A"]) * dr, "follow": (float(f60[0]) - float(f0[0])) * dr}
        r["share"] = r["follow"] / abs(gap) if abs(gap) > 0 else None
        s = smp.s[d]
        side = "CE" if a["g"] > 0 else "PE"
        p0, _dep, state, _jf = op.leg(smp, s, side, 1, "HONEST", 0.0)
        r["dec"] = sn397.decompose(smp, s, p0, side) if p0 is not None else None
        rows.append(r)
    out = {}
    for per in ("pre", "post"):
        rs = [r for r in rows if r["period"] == per]
        out[per] = {"sessions": len(rs), "abs_gap_pts": stats([r["abs_gap"] for r in rs]), "first_minute_drift_pts": stats([r["drift"] for r in rs]),
                    "follow_through_pts": stats([r["follow"] for r in rs]), "follow_share_of_gap": stats([r["share"] for r in rs]),
                    "match_rows": sum(r["src"] == "match_row" for r in rs)}
        dec = [r["dec"] for r in rs if r["dec"]]
        if dec:
            out[per]["ITM_mid_change_split_per_lot"] = {k: round(float(np.mean([x[k] for x in dec])), 1) for k in ("dmid", "delta", "vega", "theta", "resid", "cost")}
            out[per]["ITM_decomposed_n"] = len(dec)
    return out, rows


def walk(levels, need):
    got = cost = 0.0
    for p, q in levels:
        take = min(q, need - got)
        cost += take * p
        got += take
        if got >= need:
            return cost / need
    return None


def part_b():
    man = json.loads((sn396.EXPORT / "manifest.json").read_text(encoding="utf-8"))
    sealed = [d for d in man["quote_days"] if d not in set(man["unsealed_days"])]
    win = {"09:16": ("09:16:00", "09:17:00"), "10:16": ("10:16:00", "10:17:00"), "11:00": ("11:00:00", "11:01:00")}
    acc = {w: {"spread": [], "walk_over_mid": []} for w in win}
    used = 0
    for d in sealed:
        A = sn396.archive_day(d)
        exps = sorted({k[1] for k in A if k[0] != "FUT" and k[1] >= d})
        if not exps or exps[0] == d:
            continue
        front = exps[0]
        futs = sorted(k for k in A if k[0] == "FUT")
        if not futs:
            continue
        used += 1
        for w, (lo, hi) in win.items():
            fs = sn396.snap(A[futs[0]], lo, hi)
            if fs is None or not fs.get("ltp"):
                continue
            F = float(fs["ltp"])
            for k, recs in A.items():
                if k[0] == "FUT" or k[1] != front or abs(k[2] - F) > 100:
                    continue
                x = sn396.snap(recs, lo, hi)
                if x is None:
                    continue
                b, a_ = x["bids"][0][0], x["asks"][0][0]
                mid = 0.5 * (a_ + b)
                wa = walk(x["asks"], op.LOT)
                acc[w]["spread"].append((a_ - b) * op.LOT)
                if wa is not None and mid:
                    acc[w]["walk_over_mid"].append((wa - mid) * op.LOT)
    out = {"days": used}
    for w, v in acc.items():
        out[w] = {"quotes": len(v["spread"]), "spread_per_lot_median": round(float(np.median(v["spread"])), 2) if v["spread"] else None,
                  "spread_per_lot_p90": round(float(np.percentile(v["spread"], 90)), 2) if v["spread"] else None,
                  "walk_over_mid_per_lot_median": round(float(np.median(v["walk_over_mid"])), 2) if v["walk_over_mid"] else None,
                  "walk_over_mid_per_lot_p90": round(float(np.percentile(v["walk_over_mid"], 90)), 2) if v["walk_over_mid"] else None}
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN410 is run once")
    smp, _days, au = op.setup()
    a, _rows = part_a(smp, au)
    b = part_b()
    OUT.write_text(json.dumps({"A": a, "B": b}, indent=1), encoding="utf-8")
    print(json.dumps({"A": a, "B": b}, indent=1))


if __name__ == "__main__":
    main()
