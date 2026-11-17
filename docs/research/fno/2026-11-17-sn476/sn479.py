"""SN479: the recoverable part of stop slippage (PLAN.md SN479, frozen at bf895633; A3 fixes the sample before any number).

A. The planned sample: Production F&O paper stop exits (export 20261117T103003Z, fno_positions) by data: on a tick-recorder day
   (packets), on a quote-archive day (minute snapshots; the archive samples futures ~every 40-50 s and options ~once a minute), or
   neither. A stop needs packets to be decomposed; with none, the planned verdict is INCONCLUSIVE (SN460 holds the minute view).
B. Mechanism on real packets (A3): the recorder days 2026-11-16 and 2026-11-17 (read-only copies). Synthetic one-lot longs on the
   front-weekly 1-ITM call and put (the earliest expiry after the day; ATM = the future's last price rounded to 50) opened every
   300 s from 09:30 to 14:45. Two stop types:
     U  underlying stop at the open future price -/+ 0.15% (trigger: the first future packet through it)
     P  premium stop at 85% of the option's bid at the open (trigger: the first option packet whose last price is at or under it;
        the exchange triggers stop orders on the last price)
   CURRENT = the engine's path: a management tick every 55 s from the open; at the first tick at or after the trigger where the
   condition holds on the latest packet (U: the future through the level; P: the bid at or under the level), a market sale walks the
   5-level bid for one lot at the first usable packet >= tick + 0.5 s; a touch that recovers between ticks is not acted on; no tick
   condition by 15:10 -> sold at 15:10.
   STOP_LIMIT = packet-driven: at trigger + 0.5 s a sell limit at L = mark - max(Rs 0.50, 1%) (U; mark = the bid at the trigger) or
   level - max(Rs 0.50, 1%) (P); filled at the first packet within 5 s whose bid levels at or above L hold one lot (walked over those
   levels only); else cancelled and a market sale walks the book at the first usable packet >= trigger + 5.5 s.
   Per event (Rs a lot): paired = (STOP_LIMIT exit - CURRENT exit) x lot; when CURRENT acts within 120 s of the trigger:
   unrecoverable = (mark - STOP_LIMIT fill) x lot, delay = (STOP_LIMIT fill - CURRENT fill) x lot. 90% CI by a block bootstrap over
   time-ordered events (block 10, 10,000 draws, seed 479); tails = the 5th percentile of each path's exit minus mark; counts of
   limit fills, fallbacks, unfilled limits, touches CURRENT never acted on; sold quantity is one lot by construction.
   This is mechanism evidence on synthetic triggers, not a verdict on real stops.
"""
from __future__ import annotations

import collections
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn286"))
import tk  # noqa: E402

OUT = HERE / "results-sn479.json"
REC = Path(r"C:\Users\Urveesh\AppData\Local\Temp\claude\f191b6166a36c84a\b7c0aa9b-c954-4f08-9df8-57422081ea0c\scratchpad\rec2")
EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel\_local\exports\20261117T103003Z")
DAYS = ("2026-11-16", "2026-11-17")
TICK, LAT, WAIT, END = 55.0, 0.5, 5.0, 21300.0          # seconds; END = 15:10 from 09:15
U_PCT, P_PCT = 0.0015, 0.15


def sample_a():
    con = sqlite3.connect(f"file:{(EXPORT / 'fno-replay.sqlite').as_posix()}?mode=ro", uri=True)
    rows = con.execute("SELECT exit_date, exit_reason, underlying FROM fno_positions WHERE exit_reason IN ('underlying_stop','premium_backstop','trail_stop')").fetchall()
    m = json.loads((EXPORT / "manifest.json").read_text(encoding="utf-8"))
    archive = set(m["quote_days"])
    rec = set(DAYS)
    c = collections.Counter("recorder (packets)" if d in rec else ("quote archive (minutes)" if d in archive else "neither") for d, _r, _u in rows)
    return {"stops": len(rows), "by_data": dict(c), "verdict": "INCONCLUSIVE" if not c.get("recorder (packets)") else "SCORED"}


def last(d, t):
    k = int(np.searchsorted(d["t"], t, side="right")) - 1
    return k if k >= 0 else None


def ok(d, k):
    return d["bid"][k] > 0 and d["ask"][k] > d["bid"][k]


def walk(d, k, need, floor=None):
    left, cost = need, 0.0
    for lv in range(5):
        p, q = d["bids"][lv, k], d["bidq"][lv, k]
        if p <= 0 or q <= 0 or (floor is not None and p < floor) or left <= 0:
            continue
        take = min(left, q)
        cost += take * p
        left -= take
    return None if left > 0 else cost / need


def market_after(d, t0, lot, until=None):
    k = int(np.searchsorted(d["t"], t0, side="left"))
    for j in range(k, len(d["t"])):
        if until is not None and d["t"][j] > until:
            return None
        if ok(d, j):
            px = walk(d, j, lot)
            if px is not None:
                return px, float(d["t"][j])
    return None


def load(day):
    folder = REC / day
    meta = tk.instruments(folder)
    futs = sorted((x["expiry"], t) for t, x in meta.items() if x.get("type") == "FUT" and x.get("underlying") == "NIFTY" and x["expiry"] >= day)
    ftok = futs[0][1]
    exps = sorted({x["expiry"] for x in meta.values() if x.get("underlying") == "NIFTY" and x.get("type") in ("CE", "PE") and x["expiry"] > day})
    exp = exps[0]
    F = tk.load_day(folder, keep=lambda tok, x: tok == ftok)[ftok]
    lo, hi = float(np.min(F["ltp"][F["ltp"] > 0])), float(np.max(F["ltp"]))
    want = {t for t, x in meta.items() if x.get("underlying") == "NIFTY" and x.get("type") in ("CE", "PE") and x["expiry"] == exp
            and lo - 400 <= float(x["strike"]) <= hi + 400}
    D = tk.load_day(folder, keep=lambda tok, x: tok in want)
    opt = {(int(round(float(meta[t]["strike"]))), meta[t]["type"]): t for t in want if t in D}
    lot = int(next(x["lot_size"] for x in meta.values() if x.get("underlying") == "NIFTY" and x.get("type") in ("CE", "PE")))
    return F, D, opt, lot, exp


def events(day):
    F, D, opt, lot, exp = load(day)
    out = []
    for S0 in np.arange(900.0, 19801.0, 300.0):
        kf = last(F, S0)
        if kf is None:
            continue
        f0 = float(F["ltp"][kf])
        atm = int(round(f0 / 50.0) * 50)
        for side, d_ in (("CE", 1), ("PE", -1)):
            tok = opt.get((atm - 50 * d_, side))
            if tok is None:
                continue
            od = D[tok]
            k0 = last(od, S0)
            if k0 is None or not ok(od, k0):
                continue
            for kind in ("U", "P"):
                if kind == "U":
                    level = f0 * (1 - d_ * U_PCT)
                    js = np.flatnonzero((F["t"] > S0) & (F["t"] <= END) & ((F["ltp"] - level) * d_ <= 0) & (F["ltp"] > 0))
                    if not len(js):
                        continue
                    tau = float(F["t"][js[0]])
                else:
                    level = float(od["bid"][k0]) * (1 - P_PCT)
                    js = np.flatnonzero((od["t"] > S0) & (od["t"] <= END) & (od["ltp"] > 0) & (od["ltp"] <= level))
                    if not len(js):
                        continue
                    tau = float(od["t"][js[0]])
                km = last(od, tau)
                while km is not None and km >= 0 and not ok(od, km):
                    km -= 1
                if km is None or km < 0:
                    continue
                mark = float(od["bid"][km])
                L = (mark - max(0.5, 0.01 * mark)) if kind == "U" else (level - max(0.5, 0.01 * level))
                sl, how = None, None
                k1 = int(np.searchsorted(od["t"], tau + LAT, side="left"))
                for j in range(k1, len(od["t"])):
                    if od["t"][j] > tau + LAT + WAIT:
                        break
                    if ok(od, j):
                        px = walk(od, j, lot, floor=L)
                        if px is not None:
                            sl, how = (px, float(od["t"][j])), "limit"
                            break
                if sl is None:
                    sl = market_after(od, tau + LAT + WAIT, lot)
                    how = "fallback" if sl is not None else "unfilled"
                cur, cur_how = None, None
                tk_ = S0 + TICK * np.ceil((tau - S0) / TICK)
                while tk_ <= END:
                    if kind == "U":
                        kk = last(F, tk_)
                        hit = kk is not None and (F["ltp"][kk] - level) * d_ <= 0
                    else:
                        kk = last(od, tk_)
                        hit = kk is not None and ok(od, kk) and od["bid"][kk] <= level
                    if hit:
                        cur = market_after(od, tk_ + LAT, lot)
                        cur_how = "tick" if tk_ - tau <= 120 else "later_tick"
                        break
                    tk_ += TICK
                if cur is None:
                    cur = market_after(od, END, lot)
                    cur_how = "held_to_1510"
                if sl is None or cur is None:
                    continue
                row = {"day": day, "S0": float(S0), "side": side, "kind": kind, "tau": round(tau, 2), "mark": mark, "sl_px": round(sl[0], 2),
                       "sl_t": round(sl[1] - tau, 2), "sl_how": how, "cur_px": round(cur[0], 2), "cur_t": round(cur[1] - tau, 2), "cur_how": cur_how,
                       "paired": round((sl[0] - cur[0]) * lot, 1)}
                if cur_how == "tick":
                    row["unrecoverable"] = round((mark - sl[0]) * lot, 1)
                    row["delay"] = round((sl[0] - cur[0]) * lot, 1)
                out.append(row)
    return out, lot, exp


def block_ci(x, block=10, draws=10000, seed=479):
    x = np.asarray(x, float)
    n = len(x)
    if n == 0:
        return None
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(draws, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(draws, -1)[:, :n] % n
    m = x[idx].mean(axis=1)
    return [round(float(np.quantile(m, 0.05)), 1), round(float(np.quantile(m, 0.95)), 1)]


def summary(rows, lot):
    if not rows:
        return {"events": 0}
    p = [r["paired"] for r in rows]
    same = [r for r in rows if r["cur_how"] == "tick"]
    return {"events": len(rows), "mean_paired_per_lot": round(float(np.mean(p)), 1), "ci90_mean": block_ci(p),
            "share_paired_positive": round(float(np.mean([x > 0 for x in p])), 3),
            "sl_how": dict(collections.Counter(r["sl_how"] for r in rows)), "cur_how": dict(collections.Counter(r["cur_how"] for r in rows)),
            "median_sl_seconds_after_trigger": float(np.median([r["sl_t"] for r in rows])),
            "median_current_seconds_after_trigger": float(np.median([r["cur_t"] for r in rows])),
            "same_episode": {"events": len(same), "mean_unrecoverable": round(float(np.mean([r["unrecoverable"] for r in same])), 1) if same else None,
                             "mean_delay": round(float(np.mean([r["delay"] for r in same])), 1) if same else None,
                             "ci90_delay": block_ci([r["delay"] for r in same])},
            "tail_p5_exit_minus_mark": {"STOP_LIMIT": round(float(np.quantile([(r["sl_px"] - r["mark"]) * lot for r in rows], 0.05)), 1),
                                        "CURRENT": round(float(np.quantile([(r["cur_px"] - r["mark"]) * lot for r in rows], 0.05)), 1)}}


def main():
    if OUT.exists():
        raise SystemExit("SN479 is scored once")
    res = {"A_planned_sample": sample_a(), "B_mechanism": {}}
    allrows = []
    for day in DAYS:
        rows, lot, exp = events(day)
        allrows += rows
        res["B_mechanism"][day] = {"expiry": exp, "lot": lot, **{k: summary([r for r in rows if r["kind"] == k], lot) for k in ("U", "P")}}
    res["B_mechanism"]["pooled"] = {k: summary([r for r in allrows if r["kind"] == k], lot) for k in ("U", "P")}
    res["events"] = allrows
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "events"}, indent=1))


if __name__ == "__main__":
    main()
