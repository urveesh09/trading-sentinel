"""SN448: the London open as an outside information clock (PLAN.md section 1, frozen at f56f5807; details fixed here before
any number). Index-level description; no direction is taken from the calendar.

Data: NIFTY index 1-minute bars (Breeze history, read only; bars labelled by start), regular sessions Jan 2, 2020 - Oct 28,
2026 with >= 370 bars. close_at(T) = the close of the bar labelled T - 1 minute.
Clock: LSE's 08:00 London open = 12:30 IST on British Summer Time (last Sunday of March to last Sunday of October), 13:30 IST
on GMT. LSE-closed days: England & Wales bank holidays 2020-2026 as coded below (dated exceptions included).
Activity: |5-minute return| in bp for windows starting every 5 minutes 11:30-14:25. A(c) = the mean over the three windows
starting at clock c (c, c+5, c+10); level-free version rel(c) = A(c) / the day's mean over all windows 11:30-14:25.
  diff = rel(12:30) - rel(13:30) per day; DiD = mean(diff | BST, LSE open) - mean(diff | GMT, LSE open)
  (positive if the active window moves with London), also within 28 calendar days of each clock change, by year, and on
  LSE-closed days as a placebo; 2,000 day-bootstrap resamples (seed 448) for DiD.
Residual after the first completed local bar (LSE-open days): r1 = close_at(L + 5) / close_at(L) - 1 at the London clock L;
  continuation = sign(r1) x (close_at(L + 35) - close_at(L + 5)) in points: hit share and mean; mean |move| L+5 -> L+35 in
  points against the option hurdle (Rs 313 / 508 a lot at Rs 205 / 400, SN127's midpoint, / (0.6 x 65) points); the same at
  the other IST clock on the same days as the control.
The signed UK-surprise test is BLOCKED (no eligible UK futures / opening-basket series).
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sqlite3
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "results-sn448.json"
DB = "file:C:/Users/Urveesh/sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite?mode=ro"
UK_HOL = {
    "2020-01-01", "2020-04-10", "2020-04-13", "2020-05-08", "2020-05-25", "2020-08-31", "2020-12-25", "2020-12-28",
    "2021-01-01", "2021-04-02", "2021-04-05", "2021-05-03", "2021-05-31", "2021-08-30", "2021-12-27", "2021-12-28",
    "2022-01-03", "2022-04-15", "2022-04-18", "2022-05-02", "2022-06-02", "2022-06-03", "2022-08-29", "2022-09-19",
    "2022-12-26", "2022-12-27",
    "2023-01-02", "2023-04-07", "2023-04-10", "2023-05-01", "2023-05-08", "2023-05-29", "2023-08-28", "2023-12-25", "2023-12-26",
    "2024-01-01", "2024-03-29", "2024-04-01", "2024-05-06", "2024-05-27", "2024-08-26", "2024-12-25", "2024-12-26",
    "2025-01-01", "2025-04-18", "2025-04-21", "2025-05-05", "2025-05-26", "2025-08-25", "2025-12-25", "2025-12-26",
    "2026-01-01", "2026-04-03", "2026-04-06", "2026-05-04", "2026-05-25", "2026-08-31", "2026-12-25", "2026-12-28"}
HURDLE_RS = {205: 313.0, 400: 508.0}


def last_sunday(y, m):
    d = dt.date(y, m + 1, 1) - dt.timedelta(days=1) if m < 12 else dt.date(y, 12, 31)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def bst(d):
    y = d.year
    return last_sunday(y, 3) <= d < last_sunday(y, 10)


def mi(hm):
    return int(hm[:2]) * 60 + int(hm[3:5]) - 555


def load():
    c = sqlite3.connect(DB, uri=True)
    out = {}
    for t, cl in c.execute("SELECT datetime, close FROM candles WHERE kind='index' AND underlying='NIFTY' AND expiry='' AND strike=0 AND opt='' "
                           "AND interval='1minute' AND datetime >= '2020-01-01' AND datetime < '2026-10-29' ORDER BY datetime"):
        i = mi(t[11:16])
        if 0 <= i < 375:
            out.setdefault(t[:10], np.full(375, np.nan))[i] = cl
    return {d: a for d, a in out.items() if np.isfinite(a).sum() >= 370}


def close_at(a, hm):
    i = mi(hm) - 1
    return a[i] if 0 <= i < 375 else np.nan


def hm_add(hm, k):
    t = int(hm[:2]) * 60 + int(hm[3:5]) + k
    return f"{t // 60:02d}:{t % 60:02d}"


def main():
    if OUT.exists():
        raise SystemExit("SN448 is run once")
    data = load()
    starts = [hm_add("11:30", 5 * k) for k in range(36)]
    rows = []
    for d, a in sorted(data.items()):
        dd = dt.date.fromisoformat(d)
        r = {}
        for s in starts:
            x0, x1 = close_at(a, s), close_at(a, hm_add(s, 5))
            r[s] = abs(x1 / x0 - 1) * 1e4 if np.isfinite(x0) and np.isfinite(x1) else np.nan
        allm = np.nanmean(list(r.values()))
        A = lambda c: np.nanmean([r[hm_add(c, k)] for k in (0, 5, 10)])  # noqa: E731
        row = {"day": d, "bst": bst(dd), "lse_open": d not in UK_HOL, "A1230": A("12:30"), "A1330": A("13:30"), "all": allm}
        row["diff"] = (row["A1230"] - row["A1330"]) / allm if allm > 0 else np.nan
        dchg = [last_sunday(dd.year, 3), last_sunday(dd.year, 10)]
        row["near_change"] = any(abs((dd - x).days) <= 28 for x in dchg)
        for name, L in (("london", "12:30" if row["bst"] else "13:30"), ("other", "13:30" if row["bst"] else "12:30")):
            c0, c5, c35 = close_at(a, L), close_at(a, hm_add(L, 5)), close_at(a, hm_add(L, 35))
            if np.isfinite(c0 + c5 + c35):
                s1 = np.sign(c5 - c0)
                row[f"{name}_cont_pts"] = float(s1 * (c35 - c5)) if s1 != 0 else None
                row[f"{name}_abs_pts"] = float(abs(c35 - c5))
                row[f"{name}_first_bar_bp"] = float(abs(c5 / c0 - 1) * 1e4)
                row[f"{name}_level"] = float(c5)
        rows.append(row)
    rows = [r for r in rows if np.isfinite(r["diff"])]

    def did(sel):
        b = [r["diff"] for r in sel if r["bst"]]
        g = [r["diff"] for r in sel if not r["bst"]]
        return (float(np.mean(b)) - float(np.mean(g))) if b and g else None, len(b), len(g)

    def boot(sel, n=2000, seed=448):
        rng = random.Random(seed)
        b = [r["diff"] for r in sel if r["bst"]]
        g = [r["diff"] for r in sel if not r["bst"]]
        xs = []
        for _ in range(n):
            xs.append(np.mean([b[rng.randrange(len(b))] for _k in b]) - np.mean([g[rng.randrange(len(g))] for _k in g]))
        return [round(float(np.percentile(xs, 5)), 4), round(float(np.percentile(xs, 95)), 4)]
    res = {"sessions": len(rows), "lse_closed_indian_sessions": sum(not r["lse_open"] for r in rows)}
    op_ = [r for r in rows if r["lse_open"]]
    v, nb, ng = did(op_)
    res["DiD_all_open"] = {"did": round(v, 4), "bst_days": nb, "gmt_days": ng, "ci90": boot(op_)}
    for lab, sel in (("BST", [r for r in op_ if r["bst"]]), ("GMT", [r for r in op_ if not r["bst"]])):
        res[f"activity_{lab}_bp"] = {"A1230": round(float(np.mean([r["A1230"] for r in sel])), 2), "A1330": round(float(np.mean([r["A1330"] for r in sel])), 2),
                                     "day_mean": round(float(np.mean([r["all"] for r in sel])), 2)}
    near = [r for r in op_ if r["near_change"]]
    v, nb, ng = did(near)
    res["DiD_near_clock_change"] = {"did": round(v, 4), "bst_days": nb, "gmt_days": ng, "ci90": boot(near)}
    cl = [r for r in rows if not r["lse_open"]]
    v, nb, ng = did(cl)
    res["DiD_placebo_lse_closed"] = {"did": None if v is None else round(v, 4), "bst_days": nb, "gmt_days": ng}
    res["DiD_by_year"] = {}
    for y in sorted({r["day"][:4] for r in op_}):
        v, nb, ng = did([r for r in op_ if r["day"][:4] == y])
        res["DiD_by_year"][y] = None if v is None else round(v, 4)
    res["profile_bp"] = {}
    for lab, cond in (("BST", True), ("GMT", False)):
        sel = [r["day"] for r in op_ if r["bst"] == cond]
        prof = {}
        for s in starts:
            vals = []
            for d in sel:
                a = data[d]
                x0, x1 = close_at(a, s), close_at(a, hm_add(s, 5))
                if np.isfinite(x0 + x1):
                    vals.append(abs(x1 / x0 - 1) * 1e4)
            prof[s] = round(float(np.mean(vals)), 2)
        res["profile_bp"][lab] = prof
    for name in ("london", "other"):
        cs = [r[f"{name}_cont_pts"] for r in op_ if r.get(f"{name}_cont_pts") is not None]
        ab = [r[f"{name}_abs_pts"] for r in op_ if r.get(f"{name}_abs_pts") is not None]
        res[f"residual_{name}"] = {"n": len(cs), "hit_share": round(float(np.mean([x > 0 for x in cs])), 3), "mean_cont_pts": round(float(np.mean(cs)), 2),
                                   "mean_abs_move_30m_pts": round(float(np.mean(ab)), 1),
                                   **{f"hurdle_pts@{k}": round(v / (0.6 * 65), 1) for k, v in HURDLE_RS.items()},
                                   **{f"share_abs_move_above_hurdle@{k}": round(float(np.mean([x > v / (0.6 * 65) for x in ab])), 3) for k, v in HURDLE_RS.items()}}
    res["surprise_test"] = "BLOCKED: no eligible timestamped UK futures or opening-basket series"
    res["rows"] = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in rows]
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=float))


if __name__ == "__main__":
    main()
