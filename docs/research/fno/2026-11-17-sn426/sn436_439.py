"""SN436 / SN437 / SN438 / SN439 (own; PLAN.md section 2, frozen at 123301ac; details fixed here before any number).
Learning only; no Gold change follows from these slots.

SN436 widen Gold's feed: DEPLOYED (N11 + R0.85) plus one more book at a time - the panel books R0.95, N15, N25, X0.75,
       X1.25, NO_STAND, NO_LOSS, NO_ADD, NO_VOL, DOUBLE and the controls N08, N10 (2022 from SN366's exam evaluations,
       2023-26 from N11's own); Rs 205 / 400; trades, trading days, net; HELPS only if 2022 and 2023-26 both improve at
       Rs 205.
SN437 where Gold's edge lives: Gold's DEPLOYED 2022-26 trades at Rs 205, net per lot (net / lots0) by entry hour (<= 10:30,
       10:30-12:00, 12:00-13:30, > 13:30), weekday, sessions to the trade's expiry (1, 2, 3+; Breeze's daily calendar),
       and year; a cutoff is named only if a bucket is negative in both 2022 and 2023-26 with >= 10 trades each.
SN438 size by expert: Gold's size rule "setup" (full lots for the named experts on volatility days, half otherwise) with
       {EFF}, {EFF, TPB}, {TPB} against the deployed "vol"; 2022 and 2023-26; Rs 205 / 400.
Disclosed fix (Nov 17, after the first run crashed at +N08, before any +N08 number): N08's trades carry no n091_entry, so
its stream is built from the tradingsymbol (robust_stream); every other book uses sn392.stream unchanged.
SN439 Gold's exit headroom: on every DEPLOYED 2022-26 trade (Rs 205), from Gold's own option record (bar closes, the bid
       Gold's walk uses): the best close before the trade's stop between entry and its realized exit, and within the
       first 60 minutes; headroom per lot against the realized exit; the share of trades whose best close came in the
       first hour.
"""
from __future__ import annotations

import bisect
import collections
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn411"))
import gold  # noqa: E402

OUT = {436: HERE / "results-sn436.json", 437: HERE / "results-sn437.json", 438: HERE / "results-sn438.json", 439: HERE / "results-sn439.json"}
HIST = Path(r"C:/Users/Urveesh/sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite")
PANEL = ("R0.95", "N15", "N25", "X0.75", "X1.25", "NO_STAND", "NO_LOSS", "NO_ADD", "NO_VOL", "DOUBLE")
CTRL = ("N08", "N10")
for b in PANEL:
    gold.P.SRC.setdefault(b, ("panel", b, f"panel|{b}"))
for b in CTRL:
    gold.P.SRC.setdefault(b, ("controls", b, f"ctrl|{b}"))
gw = gold.T.Q.gw
_walk = None
HEAD: list = []
_sn392_stream = gold._orig_stream


def robust_stream(year, book="N11"):
    """sn392.stream, except for N08 (its trades predate N09.1 and carry no n091_entry): the same fields from the
    tradingsymbol (NIFTYyymddSTRIKE{CE|PE}) - disclosed fix after the first run crashed on +N08, before any +N08 number."""
    if book != "N08":
        return _sn392_stream(year, book)
    import json as _j
    phase, name, exam = gold.P.SRC[book]
    if year == "2022":
        key = _j.loads((gold.P.SN366L / "keys-exam-2022.json").read_text(encoding="utf-8"))[exam]
        data = _j.loads((gold.P.SN366L / "exam-evals-2022" / f"{key}.json").read_text(encoding="utf-8"))
    else:
        key = _j.loads((gold.P.N11L / f"keys-{phase}-{year}.json").read_text(encoding="utf-8"))[name]
        data = _j.loads((gold.P.N11L / "evals" / f"{key}.json").read_text(encoding="utf-8"))
    out = []
    for t in data["trades"]:
        sym = t["tradingsymbol"]
        opt = sym[-2:]
        strike = int(sym[11:-2])
        out.append({"day": t["entry_time"][:10], "i": gold.B.minute_of(t["entry_time"]), "j": gold.B.minute_of(t["exit_time"]),
                    "strike": strike, "opt": opt, "expiry": f"20{sym[5:7]}-{sym[7:9]}-{sym[9:11]}", "reason": t["exit_reason"],
                    "expert": t["entry_expert"], "gate": t.get("entry_gate") or "", "book": book,
                    "sig_key": (t["entry_time"][:16], strike, opt == "CE")})
    return out


gold._orig_stream = robust_stream


def headroom_walk(S, rec, ask, lots, i, j_n11, d, v, room, wallet):
    net, j, px = _walk(S, rec, ask, lots, i, j_n11, d, v, room, wallet)
    a, bo, bh, bl, bc, bm, tr = rec
    stop = gw.LOG[-1]["stop"] if gw.LOG else None
    bids = [float(bc[k]) if tr[k] else float(bm[k]) for k in range(i + 1, j + 1)]
    lows = [float(bl[k]) for k in range(i + 1, j + 1)]
    best, best_k = None, None
    for n_, (b, lo) in enumerate(zip(bids, lows)):
        if stop is not None and lo <= stop:
            break
        if not np.isnan(b) and (best is None or b > best):
            best, best_k = b, n_
    first_hour = [b for b in bids[:60] if not np.isnan(b)]
    HEAD.append({"day": S.day, "i": i, "j": j, "lots": lots, "ask": float(ask), "px": float(px), "net": float(net),
                 "best": best, "best_minute": None if best_k is None else best_k + 1, "best_first_hour": max(first_hour) if first_hour else None})
    return net, j, px


def main():
    global _walk
    if all(p.exists() for p in OUT.values()):
        raise SystemExit("SN436-SN439 are run once")
    res436 = {}
    for name, books in [("DEPLOYED", gold.DEPLOYED)] + [(f"+{b}", (*gold.DEPLOYED, b)) for b in PANEL + CTRL]:
        for p, years in (("2022", gold.Y22), ("2023-2026", gold.Y2326)):
            for st in (205.0, 400.0):
                days, log, _ = gold.run(years, books, st)
                s = gold.summary(days, log)
                s["trading_days"] = len({x["day"] for x in log})
                res436[f"{name} | {p} @{int(st)}"] = {k: s[k] for k in ("net", "trades", "trading_days", "months_positive", "worst_month")}
                print("436", name, p, int(st), s["net"], s["trades"], s["trading_days"], flush=True)
    assert res436["DEPLOYED | 2023-2026 @205"]["net"] in (850882, 850883)
    b22, b26 = res436["DEPLOYED | 2022 @205"]["net"], res436["DEPLOYED | 2023-2026 @205"]["net"]
    res436["HELPS"] = [n for n in ["+" + b for b in PANEL + CTRL] if res436[f"{n} | 2022 @205"]["net"] > b22 and res436[f"{n} | 2023-2026 @205"]["net"] > b26]
    OUT[436].write_text(json.dumps(res436, indent=1), encoding="utf-8")
    # SN437 + SN439 from one instrumented DEPLOYED 2022-26 run
    gold.install()
    _walk = gold.L.walk
    gold.L.walk = headroom_walk
    try:
        days, log, _ = gold.run(gold.Y2226, gold.DEPLOYED, 205.0)
    finally:
        gold.L.walk = _walk
    con = sqlite3.connect(f"file:{HIST.as_posix()}?mode=ro", uri=True)
    cal = sorted({r[0][:10] for r in con.execute("SELECT datetime FROM candles WHERE underlying='NIFTY' AND kind='daily' AND interval='1day' AND datetime>='2022-01-01'")})
    exp_of = {}
    for y in gold.Y2226:
        for S in gold.C.years()[y].ordered():
            exp_of[S.day] = S.s["expiry"]
    rows = []
    for x in log:
        mins = 555 + x["i"]
        hh = "<=10:30" if mins <= 630 else "10:30-12:00" if mins <= 720 else "12:00-13:30" if mins <= 810 else ">13:30"
        e = exp_of.get(x["day"])
        dte = None if e is None else bisect.bisect_right(cal, e) - bisect.bisect_right(cal, x["day"])
        rows.append({"day": x["day"], "year": x["day"][:4], "hour": hh, "weekday": dt.date.fromisoformat(x["day"]).strftime("%a"),
                     "dte": None if dte is None else ("1" if dte <= 1 else "2" if dte == 2 else "3+"), "per_lot": x["net"] / max(1, x.get("lots0") or 1),
                     "expert": x.get("expert")})
    res437 = {"trades": len(rows)}
    for dim in ("hour", "weekday", "dte", "year", "expert"):
        tab = {}
        for v in sorted({r[dim] for r in rows if r[dim] is not None}):
            sub = [r for r in rows if r[dim] == v]
            s22 = [r["per_lot"] for r in sub if r["year"] == "2022"]
            s26 = [r["per_lot"] for r in sub if r["year"] != "2022"]
            tab[v] = {"n": len(sub), "per_lot": round(float(np.mean([r["per_lot"] for r in sub])), 1), "n_2022": len(s22),
                      "per_lot_2022": round(float(np.mean(s22)), 1) if s22 else None, "n_2023_26": len(s26), "per_lot_2023_26": round(float(np.mean(s26)), 1) if s26 else None}
            tab[v]["CUTOFF"] = bool(len(s22) >= 10 and len(s26) >= 10 and tab[v]["per_lot_2022"] < 0 and tab[v]["per_lot_2023_26"] < 0)
        res437[dim] = tab
    OUT[437].write_text(json.dumps(res437, indent=1), encoding="utf-8")
    hs = [h for h in HEAD if h["best"] is not None]
    lot = gw.M.LOT
    res439 = {"trades": len(HEAD), "with_best": len(hs),
              "headroom_per_lot_mean": round(float(np.mean([(h["best"] - h["px"]) * lot for h in hs])), 1),
              "headroom_per_lot_median": round(float(np.median([(h["best"] - h["px"]) * lot for h in hs])), 1),
              "realized_per_lot_mean": round(float(np.mean([(h["px"] - h["ask"]) * lot for h in hs])), 1),
              "best_per_lot_mean": round(float(np.mean([(h["best"] - h["ask"]) * lot for h in hs])), 1),
              "first_hour_best_per_lot_mean": round(float(np.mean([(h["best_first_hour"] - h["ask"]) * lot for h in hs if h["best_first_hour"] is not None])), 1),
              "share_best_in_first_hour": round(float(np.mean([h["best_minute"] <= 60 for h in hs])), 3),
              "median_best_minute": float(np.median([h["best_minute"] for h in hs])), "median_hold_minutes": float(np.median([h["j"] - h["i"] for h in HEAD])),
              "losers_whose_best_was_above_entry": sum(1 for h in hs if h["net"] < 0 and h["best"] > h["ask"]), "losers": sum(1 for h in hs if h["net"] < 0)}
    OUT[439].write_text(json.dumps(res439, indent=1), encoding="utf-8")
    # SN438
    res438 = {}
    for name, vx in (("vol (deployed)", {}), ("setup EFF", {"size": "setup", "full_for": ("EFF",)}), ("setup EFF+TPB", {"size": "setup", "full_for": ("EFF", "TPB")}),
                     ("setup TPB", {"size": "setup", "full_for": ("TPB",)})):
        for p, years in (("2022", gold.Y22), ("2023-2026", gold.Y2326)):
            for st in (205.0, 400.0):
                days, log, _ = gold.run(years, gold.DEPLOYED, st, **vx)
                s = gold.summary(days, log)
                res438[f"{name} | {p} @{int(st)}"] = {k: s[k] for k in ("net", "trades", "months_positive", "worst_month")}
                print("438", name, p, int(st), s["net"], flush=True)
    OUT[438].write_text(json.dumps(res438, indent=1), encoding="utf-8")
    print(json.dumps(res437, indent=1))
    print(json.dumps(res439, indent=1))


if __name__ == "__main__":
    main()
