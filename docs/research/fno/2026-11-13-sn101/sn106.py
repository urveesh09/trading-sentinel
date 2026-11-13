"""SN106 - SN95-L transplanted unchanged to SENSEX on N012's Round 36 panel (145 ordinary dates, read in place,
SHA-256 checked; PLAN.md). Front future for R_today, the panel's one later expiry for the straddle (strike step 100),
BFO costs, lot 20, house spread model, strict stress, Rs 3k room, hold to 15:10. Compared on common dates with NIFTY's
own 10:00 straddle and a pre-decision choice. Partial evidence (one expiry a day, 145 dates)."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pa  # noqa: E402

C, M = pa.C, pa.M
DB = M.ROOT / "docs/research/simulation/2026-11-05-fno-n12/_local/round36/breeze.sqlite"
SHA = "0fdd615963cbc7ea5b08b7e64924076568da4e81a8fe8585b5882b08b89bfd29"
LOT_SX, STEP_SX = 20, 100
_SNAP = []


def bfo_charges(entry, exit_, qty):
    if not _SNAP:
        from cost_schedules import options_cost_snapshot
        from fno_costs import calc_fno_costs_from_snapshot
        _SNAP.extend([options_cost_snapshot("BFO"), calc_fno_costs_from_snapshot])
    return _SNAP[1](entry, exit_, qty, _SNAP[0])


def minute(st):
    return int(st[11:13]) * 60 + int(st[14:16]) - 555


def load_days():
    h = hashlib.sha256()
    with open(DB, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    assert h.hexdigest() == SHA, "Round 36 panel hash mismatch"
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    days = [r[0] for r in con.execute("SELECT DISTINCT substr(datetime,1,10) FROM candles WHERE kind='option' ORDER BY 1")]
    out = {}
    for d in days:
        fexp = con.execute("SELECT min(expiry) FROM candles WHERE kind='future' AND expiry >= ? AND datetime >= ? AND datetime < ?",
                           (d, d, d + "~")).fetchone()[0]
        fut = np.full(375, np.nan)
        for st, c in con.execute("SELECT datetime, close FROM candles WHERE kind='future' AND expiry=? AND datetime >= ? AND datetime < ?",
                                 (fexp, d, d + "~")):
            i = minute(st)
            if 0 <= i < 375:
                fut[i] = c
        exps = [r[0] for r in con.execute("SELECT DISTINCT expiry FROM candles WHERE kind='option' AND datetime >= ? AND datetime < ?", (d, d + "~"))]
        exp = min(exps)
        opts = {}
        for st, k, o, c in con.execute("SELECT datetime, strike, opt, close FROM candles WHERE kind='option' AND expiry=? AND datetime >= ? AND datetime < ?",
                                       (exp, d, d + "~")):
            i = minute(st)
            if 0 <= i < 375:
                opts.setdefault((int(round(k)), o), np.full(375, np.nan))[i] = c
        out[d] = {"fut": fut, "expiry": exp, "opts": opts}
    con.close()
    return out


def mark(a, j, stale=5):
    col = a[: j + 1]
    ok = np.flatnonzero(~np.isnan(col))
    return None if not len(ok) or j - ok[-1] > stale else float(col[ok[-1]])


def sx_day(d, rec, room=3000.0, stress=205.0):
    fut, opts = rec["fut"], rec["opts"]
    i = pa.I10
    if np.isnan(fut[i]):
        return None
    K = int(round(fut[i] / STEP_SX) * STEP_SX)
    ce, pe = opts.get((K, "CE")), opts.get((K, "PE"))
    if ce is None or pe is None or np.isnan(ce[i]) or np.isnan(pe[i]):
        return None
    n = C.sessions_until(d, rec["expiry"])
    tau = (375 - (i + 1)) + 375.0 * n + C.OVERNIGHT_MIN * n
    fc = fut[5: i + 1]
    fc = fc[~np.isnan(fc)]
    if len(fc) < 20 or tau <= 0:
        return None
    s_imp = (ce[i] + pe[i]) / (0.7979 * fut[i] * math.sqrt(tau))
    rt = float(np.std(np.diff(np.log(fc)))) / s_imp
    asks = [M.ask_of(float(ce[i])), M.ask_of(float(pe[i]))]
    last, j_out = None, pa.FLAT
    for j in range(i + 1, pa.FLAT + 1):
        b1, b2 = mark(ce, j), mark(pe, j)
        if b1 is None or b2 is None:
            continue
        bids = [M.bid_of(b1), M.bid_of(b2)]
        v = sum((b - a) * LOT_SX for a, b in zip(asks, bids)) - sum(bfo_charges(a, b, LOT_SX) for a, b in zip(asks, bids)) - 2 * stress
        last = v
        if v <= -room:
            j_out = j
            break
    return {"r_today": rt, "premium": sum(asks) * LOT_SX, "net": last if last is not None else -2 * stress, "exit": j_out,
            "dte": n, "expiry": rec["expiry"]}


if __name__ == "__main__":
    out_path = HERE / "results-sn106.json"
    if out_path.exists():
        raise SystemExit("SN106 is scored once")
    C.years()
    adm = pa.admission()
    panel = load_days()
    rows, hist = [], []
    for d in sorted(panel):
        r = sx_day(d, panel[d])
        if r is None:
            rows.append({"day": d, "priced": False})
            continue
        flag = r["r_today"] >= np.quantile(hist, 0.8) if len(hist) >= 30 else None
        hist.append(r["r_today"])
        r.update({"day": d, "priced": True, "flag": flag, "gold_free": C.gold_free(d)})
        Ys = C.years()
        S = Ys[d[:4]].sessions.get(d) if d[:4] in Ys else None
        nf = pa.path(S, pa.I10) if S is not None else None
        r["nifty_net"] = None if nf is None or nf[1] > 15000 else pa.settle(nf[2], pa.I10, 3000.0)[0]
        r["nifty_flag"] = adm.get((d, "10:00", "R_today", 0.2, "top")) if S is not None else None
        r["nifty_r"] = C.r_today(S, pa.I10) if S is not None else None
        rows.append(r)
    pr = [r for r in rows if r["priced"]]
    flagged = [r for r in pr if r["flag"] is not None]
    common = [r for r in flagged if r["nifty_net"] is not None and r["nifty_flag"] is not None]

    def tot(xs, k="net"):
        return {"n": len(xs), "net": round(sum(x[k] for x in xs)), "won": sum(x[k] > 0 for x in xs),
                "by_year": {y: round(sum(x[k] for x in xs if x["day"][:4] == y)) for y in ("2025", "2026")}}
    choice = []
    for r in common:
        if r["flag"] and r["nifty_flag"]:
            choice.append(r["net"] if r["r_today"] >= r["nifty_r"] else r["nifty_net"])
        elif r["flag"]:
            choice.append(r["net"])
        elif r["nifty_flag"]:
            choice.append(r["nifty_net"])
    res = {"dates": len(panel), "priced": len(pr), "with_causal_flag": len(flagged), "common_with_nifty": len(common),
           "sensex_every_day": tot(flagged), "sensex_admitted": tot([r for r in flagged if r["flag"]]),
           "sensex_admitted_gold_free": tot([r for r in flagged if r["flag"] and r["gold_free"]]),
           "sensex_admitted_premium_under_15k": tot([r for r in flagged if r["flag"] and r["premium"] <= 15000]),
           "common_sensex_every_day": tot(common), "common_nifty_every_day": tot(common, "nifty_net"),
           "common_sensex_admitted": tot([r for r in common if r["flag"]]),
           "common_nifty_admitted": tot([r for r in common if r["nifty_flag"]], "nifty_net"),
           "common_choice": {"n": len(choice), "net": round(sum(choice)), "won": sum(x > 0 for x in choice)},
           "corr_r_today_sensex_vs_nifty": float(np.corrcoef([r["r_today"] for r in common], [r["nifty_r"] for r in common])[0, 1]) if len(common) > 5 else None,
           "mean_premium_sensex": round(float(np.mean([r["premium"] for r in pr])))}
    print(json.dumps(res, indent=1), flush=True)
    res["rows"] = rows
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
