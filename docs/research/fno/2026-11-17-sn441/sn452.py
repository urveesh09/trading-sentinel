"""SN452 (own): a future-blind check of Gold, after freqtrade's lookahead analysis (recompute every decision with the future
removed and compare) (PLAN.md section 2, frozen at f56f5807; details fixed here before any number). Pass = zero mismatches.

A. Decisions. Gold v5 (DEPLOYED, Rs 205) is run on 2022 and 2023-26. At every call of common.gold_one, before the real
   call, the same call is made on a copy of the session whose index, future and every option array are NaN after the entry
   minute i (a fresh feature build and option cache from the truncated arrays). Its walk is replaced by a recorder that
   stops the call, so nothing is booked. The real call records the same fields. Compared: entry minute, exit-minute argument,
   lots, the model ask, the room, and the strike (found from the session's option cache). Signals the real call does not
   trade (None) must also be None when truncated.
B. Volatility table. lab.vol_table (yesterday's ATR% and the prior median, which sets Gold's low-volatility halving) is
   recomputed with one day's own index bars replaced by a scaled copy (x 1.5 around the open), for 20 seeded Gold trade days
   per path; the entry for that day must not change.
C. Signal clocks. For every N11 / R0.85 evaluation trade feeding the stream (2023-26 panel keys; 2022 exam keys): the
   signal bar (bar_ts, 5-minute bars labelled by start) must close before the entry: entry_time >= bar_ts + 5 minutes.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import random
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn411"))
import gold  # noqa: E402

OUT = HERE / "results-sn452.json"
gw = gold.T.Q.gw
Lb = gold.L
M = Lb.M
P = gold.P


class _Stop(Exception):
    pass


REC = {"cur": None}
STATS = {"calls": 0, "compared": 0, "mismatch": [], "both_none": 0}


def _strike_of(S, rec):
    for (k, o), r in S._bids.items():
        if r is rec:
            return k
    return None


def truncated(S, i):
    s2 = dict(S.s)
    s2["index"] = np.array(S.s["index"], dtype=np.float64, copy=True)
    s2["index"][:, i + 1:] = np.nan
    s2["future"] = np.array(S.s["future"], dtype=np.float64, copy=True)
    s2["future"][:, i + 1:] = np.nan
    opts = {}
    for k, a in S.s["options"].items():
        b = np.array(a, dtype=np.float64, copy=True)
        b[:, i + 1:] = np.nan
        opts[k] = b
    s2["options"] = opts
    S2 = copy.copy(S)
    S2.s = s2
    S2.F = M.features(s2)
    S2._bids = {}
    return S2


def main():
    if OUT.exists():
        raise SystemExit("SN452 is run once")
    gold.install()
    orig_one = gw._ORIG["gold_one"]
    real_walk = gold.L.walk

    def capture(S, rec, ask, lots, i, j, d, v, room, wallet):
        REC["cur"] = {"i": i, "j": j, "lots": lots, "ask": round(float(ask), 4), "room": round(float(room), 2), "strike": _strike_of(S, rec)}
        raise _Stop

    def recording(S, rec, ask, lots, i, j, d, v, room, wallet):
        REC["cur"] = {"i": i, "j": j, "lots": lots, "ask": round(float(ask), 4), "room": round(float(room), 2), "strike": _strike_of(S, rec)}
        return real_walk(S, rec, ask, lots, i, j, d, v, room, wallet)

    def blind(S, sg, *a, **kw):
        STATS["calls"] += 1
        S2 = truncated(S, sg["i"])
        REC["cur"] = None
        gold.L.walk = capture
        try:
            r2 = orig_one(S2, sg, *a, **kw)
            t = None if r2 is None else "RETURNED_WITHOUT_WALK"
        except _Stop:
            t = REC["cur"]
        finally:
            gold.L.walk = real_walk
        REC["cur"] = None
        gold.L.walk = recording
        try:
            r = orig_one(S, sg, *a, **kw)
        finally:
            gold.L.walk = real_walk
        real = REC["cur"] if r is not None else None
        if real is None and t is None:
            STATS["both_none"] += 1
        else:
            STATS["compared"] += 1
            if real != t:
                STATS["mismatch"].append({"day": S.day, "i": sg["i"], "real": real, "truncated": t})
        return r
    res = {}
    for p, years in (("2022", gold.Y22), ("2023-2026", gold.Y2326)):
        STATS.update(calls=0, compared=0, mismatch=[], both_none=0)
        gw._ORIG["gold_one"] = blind
        try:
            days, log, _ = gold.run(years, gold.DEPLOYED, 205.0)
        finally:
            gw._ORIG["gold_one"] = orig_one
        s = gold.summary(days, log)
        res[f"A {p}"] = {"net_with_check": s["net"], "trades": s["trades"], "calls": STATS["calls"], "compared": STATS["compared"],
                         "both_none": STATS["both_none"], "mismatches": len(STATS["mismatch"]), "mismatch_rows": STATS["mismatch"][:20]}
        print("A", p, res[f"A {p}"]["net_with_check"], res[f"A {p}"]["trades"], STATS["calls"], STATS["compared"], len(STATS["mismatch"]), flush=True)
        # B. the volatility table, one day perturbed at a time
        tdays = sorted({x["day"] for x in log})
        pick = random.Random(f"sn452-{p}").sample(tdays, min(20, len(tdays)))
        for mod in (gold.B, gold.L, gold.C):
            mod.YEARS = years
        gold.D.DATASETS["2022"] = P.SN366L / "dataset-nifty-2022"
        base = Lb.vol_table()
        real_connect = sqlite3.connect
        changed = []
        for dd in pick:
            class Con:
                def __init__(self, *a, **kw):
                    self.c = real_connect(*a, **kw)

                def execute(self, q, *a):
                    rows = self.c.execute(q, *a).fetchall()
                    if "kind='index'" in q:
                        out = []
                        o0 = next((r[1] for r in rows if r[0][:10] == dd), None)
                        for r in rows:
                            if r[0][:10] == dd and o0:
                                out.append((r[0],) + tuple(o0 + 1.5 * (x - o0) for x in r[1:]))
                            else:
                                out.append(r)
                        return out
                    return rows

                def close(self):
                    self.c.close()
            sqlite3.connect = Con
            try:
                pert = Lb.vol_table()
            finally:
                sqlite3.connect = real_connect
            if pert.get(dd) != base.get(dd):
                changed.append({"day": dd, "base": base.get(dd), "perturbed": pert.get(dd)})
        res[f"B {p}"] = {"days_checked": len(pick), "changed": len(changed), "rows": changed}
        print("B", p, len(pick), len(changed), flush=True)
    # C. signal clocks
    bad, n, gaps = [], 0, []
    N11L, SN366L = P.N11L, P.SN366L
    for year in ("2022", "2023", "2024", "2025", "2026"):
        for book in ("N11", "R0.85"):
            phase, name, exam = P.SRC[book]
            if year == "2022":
                key = json.loads((SN366L / "keys-exam-2022.json").read_text(encoding="utf-8"))[exam]
                data = json.loads((SN366L / "exam-evals-2022" / f"{key}.json").read_text(encoding="utf-8"))
            else:
                key = json.loads((N11L / f"keys-{phase}-{year}.json").read_text(encoding="utf-8"))[name]
                data = json.loads((N11L / "evals" / f"{key}.json").read_text(encoding="utf-8"))
            for t in data["trades"]:
                n += 1
                bt = dt.datetime.fromisoformat(t["bar_ts"])
                et = dt.datetime.fromisoformat(t["entry_time"][:19])
                g = (et - bt).total_seconds() - 300
                gaps.append(g)
                if g < 0 or bt.minute % 5:
                    bad.append({"year": year, "book": book, "bar_ts": t["bar_ts"], "entry_time": t["entry_time"]})
    res["C"] = {"trades": n, "violations": len(bad), "rows": bad[:20], "min_seconds_after_bar_close": min(gaps) if gaps else None,
                "median_seconds_after_bar_close": float(np.median(gaps)) if gaps else None}
    res["pass"] = all(res[f"A {p}"]["mismatches"] == 0 and res[f"B {p}"]["changed"] == 0 for p in ("2022", "2023-2026")) and not bad
    OUT.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: (v if k != "C" else {x: y for x, y in v.items() if x != "rows"}) for k, v in res.items()}, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
