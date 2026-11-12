"""SN10 - expiry-day MORNINGS on 10-second option bars, Rs 15,000 wallet (research only).

Owner (Nov 12): trade expiry days too, but only until 13:00 or 14:00 ("after that the market becomes erratic").
Data: the 10-second Breeze bars of the opening-ATM NIFTY call and put on 56 full expiry days (Sep 2025 - Oct 2026,
`2026-11-03-expiry-year/_local/data`), with index / future minutes from the sealed year datasets.
Entries: index setups (SN01 families) judged at minute closes from 09:20 to the window end; buy the opening-ATM call
(up) or put (down) at the ask of the 10-second bar that closes with that minute. Exits on every 10-second bar: premium
stop, premium target, the owner's "exit when it rises before it dips" trail (after +act, sell when the bid falls give x
the gain from its best), and a hard exit 30 minutes after the window ends. One lot, one position, Rs 3,000 day limit,
spread as the year datasets' model, Zerodha charges + Rs 205 per lot per trade. Expiry days are read for the first
time by an SN rule; choose on Sep 2025 - Mar 2026, score once on Apr - Oct 2026, with a random-entry NULL.
"""
from __future__ import annotations

import csv
import json
import math
import random
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "2026-11-12-sn01"), str(HERE.parent / "2026-11-12-sn01")]
import sn01_data as D  # noqa: E402
import sn01_search as S1  # noqa: E402
import sn01_sim as M  # noqa: E402

TEN = M.ROOT / "docs/research/simulation/2026-11-03-expiry-year/_local/data"
LOCAL = HERE / "_local"
NBAR = 375 * 6
STRESS, LOSS = 205.0, 3000.0
SPLIT = "2026-04-01"


def load_day(path: Path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    day = rows[0]["datetime_ist"][:10]
    legs = {}
    for r in rows:
        t = r["datetime_ist"]
        k = (int(t[11:13]) * 60 + int(t[14:16]) - 555) * 6 + int(t[17:19]) // 10
        if not 0 <= k < NBAR:
            continue
        a = legs.setdefault(r["opt"], np.full((4, NBAR), np.nan))
        a[:, k] = [float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])]
    return day, legs


def index_minutes(day: str):
    ds = D.DATASETS["2025" if day < "2026-01-01" else "2026"]
    con = sqlite3.connect(f"file:{(ds / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
    idx = np.full((5, 375), np.nan)
    for st, o, h, l, c in con.execute("SELECT datetime, open, high, low, close FROM candles WHERE kind='index' AND "
                                      "datetime >= ? AND datetime < ? ORDER BY datetime", (day, day + "~")):
        i = D.minute_index(st)
        if 0 <= i < 375:
            idx[:4, i] = (o, h, l, c)
    fut_exp = con.execute("SELECT min(expiry) FROM candles WHERE kind='future' AND expiry >= ?", (day,)).fetchone()[0]
    fut = np.full((5, 375), np.nan)
    for st, o, h, l, c, v in con.execute("SELECT datetime, open, high, low, close, volume FROM candles WHERE "
                                         "kind='future' AND expiry=? AND datetime >= ? AND datetime < ? ORDER BY "
                                         "datetime", (fut_exp, day, day + "~")):
        i = D.minute_index(st)
        if 0 <= i < 375:
            fut[:, i] = (o, h, l, c, v or 0.0)
    prev = con.execute("SELECT substr(datetime,1,10) d FROM candles WHERE kind='index' AND datetime < ? "
                       "ORDER BY datetime DESC LIMIT 1", (day,)).fetchone()
    prev_bar = None
    if prev:
        r = con.execute("SELECT open, max(high), min(low) FROM candles WHERE kind='index' AND datetime >= ? AND "
                        "datetime < ?", (prev[0], prev[0] + "~")).fetchone()
        c = con.execute("SELECT close FROM candles WHERE kind='index' AND datetime < ? ORDER BY datetime DESC LIMIT 1",
                        (prev[0] + "~",)).fetchone()[0]
        prev_bar = (r[0], r[1], r[2], c)
    con.close()
    for a in (idx, fut):
        for k in range(a.shape[0]):
            a[k] = D._ffill(a[k])
    fut[4] = np.nan_to_num(fut[4])
    return {"index": idx, "future": fut, "prev": prev_bar, "prev_days": [prev_bar] * 12 if prev_bar else []}


def build() -> None:
    days = {}
    for p in sorted(TEN.glob("NIFTY-*-ATM-10second.csv")):
        day, legs = load_day(p)
        if set(legs) != {"CE", "PE"}:
            continue
        s = index_minutes(day)
        if np.isnan(s["index"][3]).all():
            continue
        days[day] = {"legs": {k: v.astype(np.float32) for k, v in legs.items()}, "s": s}
    LOCAL.mkdir(exist_ok=True)
    import pickle
    with open(LOCAL / "expiry10.pkl", "wb") as fh:
        pickle.dump(days, fh)
    print("expiry days", len(days), min(days), max(days), flush=True)


class Day:
    def __init__(self, day, rec):
        self.day = day
        self.seed = int(day.replace("-", ""))
        self.s = {**rec["s"], "day": day}
        self.F = M.features(self.s)
        self.legs = {}
        for opt, a in rec["legs"].items():
            a = a.astype(np.float64)
            close = D._ffill(a[3].copy())
            self.legs[opt] = (a, M._bid_vec(np.nan_to_num(a[1], nan=0.05)), M._bid_vec(np.nan_to_num(a[2], nan=0.05)),
                              M._bid_vec(close), ~np.isnan(a[3]), close)


def run_day(Dy: Day, g: dict, wallet=15000.0, loss=LOSS, stress=STRESS) -> dict:
    sig = M.signals(Dy.F, {"families": g["families"], "bias": g["bias"]}, Dy.seed)
    end_min = g["end"]
    realized, n, k_free = 0.0, 0, 0
    for i in np.flatnonzero(sig[: end_min + 1]):
        if i < 5 or n >= g["max_trades"]:
            continue
        k0 = i * 6 + 5                      # the 10-second bar closing with minute i
        if k0 < k_free:
            continue
        opt = "CE" if sig[i] > 0 else "PE"
        a, bh, bl, bc, traded, close = Dy.legs[opt]
        if not traded[k0]:
            continue
        ask = M.ask_of(float(close[k0]))
        if ask * M.LOT > wallet:
            continue
        qty = M.LOT
        est = M.charges(ask, ask, qty) + stress
        room = loss + realized
        stop = max(ask * (1 - g["stop"]), M._ceil_tick(ask - (room - est) / qty))
        tgt = ask * (1 + g["target"]) if g["target"] else np.inf
        peak, exit_px = ask, None
        hard = min(NBAR - 1, (end_min + 30) * 6 + 5)
        for k in range(k0 + 1, hard + 1):
            if not traded[k]:
                continue
            s_eff = stop
            if g["act"] and peak >= ask * (1 + g["act"]):
                s_eff = max(s_eff, peak - g["give"] * (peak - ask))
            if bl[k] <= s_eff:
                exit_px = s_eff
                break
            if bh[k] >= tgt:
                exit_px = tgt
                break
            peak = max(peak, bc[k])
        if exit_px is None:
            k = hard
            exit_px = float(bc[k])
        net = (exit_px - ask) * qty - M.charges(ask, exit_px, qty) - stress
        realized += net
        n += 1
        k_free = k + 1
        if loss + realized < loss * 0.05:
            break
    return {"day": Dy.day, "net": realized, "trades": n}


GENES = {"stop": [0.10, 0.20, 0.30], "target": [0.0, 0.20, 0.40, 0.80], "act": [0.0, 0.10, 0.20, 0.40],
         "give": [0.3, 0.5], "max_trades": [1, 2, 3], "end": [225, 285], "bias": ["none", "puts", "calls"]}


def random_genome(rng, null):
    fam = S1._family(rng, null)
    while fam["kind"] in ("FADE", "PDX", "EMAX") and not null:
        fam = S1._family(rng, null)
    g = {"families": [fam], "null": null}
    g.update({k: rng.choice(v) for k, v in GENES.items()})
    return g


if __name__ == "__main__":
    if sys.argv[1:] == ["build"]:
        build()
        raise SystemExit
    import pickle
    days = [Day(d, r) for d, r in sorted(pickle.load(open(LOCAL / "expiry10.pkl", "rb")).items())]
    A = [x for x in days if x.day < SPLIT]
    Bh = [x for x in days if x.day >= SPLIT]
    rng = random.Random(20261116)
    pool = [random_genome(rng, False) for _ in range(1500)] + [random_genome(rng, True) for _ in range(750)]
    rows = []
    for g in pool:
        ra = [run_day(x, g)["net"] for x in A]
        rows.append({"g": g, "A": sum(ra), "A_trades": sum(1 for x in ra if x != 0), "A_days": len(A)})
    out = {"days": [x.day for x in days], "split": SPLIT, "A_days": len(A), "B_days": len(Bh), "picks": {}}
    for kind in ("real", "null"):
        cand = [r for r in rows if r["g"]["null"] == (kind == "null") and r["A_trades"] >= len(A) * 0.4]
        cand.sort(key=lambda r: r["A"], reverse=True)
        top = cand[:10]
        res = []
        for r in top:
            rb = [run_day(x, r["g"]) for x in Bh]
            nets = [z["net"] for z in rb]
            res.append({"genome": r["g"], "A": round(r["A"]), "B": round(sum(nets)), "B_won": sum(x > 0 for x in nets),
                        "B_lost": sum(x < 0 for x in nets), "B_none": sum(x == 0 for x in nets)})
        out["picks"][kind] = res
        print(kind, "top-1 A", res[0]["A"], "-> B", res[0]["B"], "won/lost/none", res[0]["B_won"], res[0]["B_lost"], res[0]["B_none"],
              "| top-10 mean B", round(sum(x["B"] for x in res) / len(res)), flush=True)
    allA = [r["A"] for r in rows if not r["g"]["null"]]
    print("REAL pool on A: share positive", round(sum(x > 0 for x in allA) / len(allA), 3), "median", round(float(np.median(allA))))
    print("pick", out["picks"]["real"][0]["genome"])
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
