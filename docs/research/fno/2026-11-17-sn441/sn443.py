"""SN443: a discount while the directional premise holds, on Production's own signal stream with real quotes (PLAN.md
section 1, frozen at f56f5807; details fixed here before any number). Development evidence only.

Decisions: fno_signals in the sealed export, NIFTY, leg FNO_PAPER, direction LONG / SHORT, evaluated on a sealed quote day
(Sep 10 - Nov 13), accepted or rejected after the signal formed (POST below). Per (day, direction): the first, then later
ones at least 15 minutes after the last kept. Decision snapshot i = the evaluated minute + 1 (the next minute's snapshot is
surely after the decision). Contract: the signal's own (expiry, strike, type) if the archive recorded it, else UNRECORDED.
Premise: LONG fails if the front future's last price < or_high, SHORT if > or_low; without levels, a 0.15% adverse move.
Delta at i: (V_K - K (V_{K+50} - V_{K-50}) / 100) / F from same-snapshot best mids (bounded 0.05 - 0.98 in size), else
the signal's recorded delta. Window: snapshots i+1 .. i+5. D = Rs 1.00 a unit.
  NOW        the walked ask at i
  DELAY-k    the walked ask at i + k (k = 1, 2, 3, 5); NO_FILL if that snapshot is unusable or unaffordable
  PLAIN      the first window snapshot with walked ask <= ask0 - D, while the premise holds (checked at each snapshot
             first); CANCELLED when the premise fails or the window ends
  DISCOUNT   the same with walked ask <= ask0 + delta (F_t - F0) - D
Exit for all arms: the deadline i + 60 (13:30 for an expiring contract) by sn441.legal, ₹3,000 stop; one lot (65).
Reported per stress: per original decision (misses = 0) mean, fills, missed NOW winners, paired price improvement per lot.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn441  # noqa: E402

C, qa = sn441.C, sn441.qa
OUT = HERE / "results-sn443.json"
DB = (r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
      r"\_local\exports\20261116T103002Z\fno-replay.sqlite")
POST = {"", "expiry_day_block", "trades_per_day", "kill_switches_clear", "concurrency", "reward_risk_below_min",
        "already_holding_this_contract", "pool_below_min_viable", "correlated_exposure_open"}
LOT, D, W = 65, 1.00, 5
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def decisions(sealed):
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = c.execute("SELECT evaluated_at, direction, accepted, reject_reason, strike, opt_type, expiry, premium, delta, fut_price, or_high, or_low "
                     "FROM fno_signals WHERE underlying='NIFTY' AND leg='FNO_PAPER' AND direction IN ('LONG','SHORT') ORDER BY evaluated_at").fetchall()
    out, last = [], {}
    for ev, dr, acc, rr, k, typ, ex, prem, dl, fp, oh, ol in rows:
        t = dt.datetime.fromisoformat(ev.replace("Z", "+00:00")).astimezone(IST)
        day = t.strftime("%Y-%m-%d")
        if day not in sealed or (rr or "") not in POST:
            continue
        m = t.hour * 60 + t.minute - 555
        key = (day, dr)
        if key in last and m - last[key] < 15:
            continue
        last[key] = m
        out.append({"day": day, "at": t.strftime("%H:%M:%S"), "m": m, "dir": dr, "accepted": acc, "reason": rr or "", "strike": int(round(k)),
                    "type": typ, "expiry": ex, "premium": prem, "delta_rec": dl, "or_high": oh, "or_low": ol})
    return out


def mid(rec, i):
    b, a = rec["bid"][i], rec["ask"][i]
    return (b + a) / 2 if rec["usable"][i] and not np.isnan(b) and not np.isnan(a) else np.nan


def main():
    if OUT.exists():
        raise SystemExit("SN443 is run once")
    man = qa.manifest()
    sealed = set(man["quote_days"]) - set(man["unsealed_days"])
    decs = decisions(sealed)
    rows = []
    cache = {}
    for s in decs:
        if s["day"] not in cache:
            cache[s["day"]] = qa.load(s["day"])
        q = cache[s["day"]]
        r = dict(s)
        rec = q["opt"].get(("NIFTY", s["expiry"], s["strike"], s["type"]))
        i = s["m"] + 1
        cut = 255 if s["expiry"] == s["day"] else 355
        fut = qa.front_fut(q, "NIFTY")
        if rec is None or fut is None:
            r["state"] = "UNRECORDED"
            rows.append(r)
            continue
        if i >= cut - 1:
            r["state"] = "AFTER_CUTOFF"
            rows.append(r)
            continue
        ask_w, bid_w = C.walked(rec, "ask"), C.walked(rec, "bid")
        if np.isnan(ask_w[i]) or ask_w[i] * LOT + C.charges(ask_w[i], 0.0) > sn441.ROOM:
            r["state"] = "NO_ENTRY_QUOTE"
            rows.append(r)
            continue
        r["state"] = "PRICED"
        F0 = fut["ltp"][i]
        sgn = 1 if s["dir"] == "LONG" else -1
        lo = rec_n = q["opt"].get(("NIFTY", s["expiry"], s["strike"] - 50, s["type"]))
        hi = q["opt"].get(("NIFTY", s["expiry"], s["strike"] + 50, s["type"]))
        delta = None
        if lo is not None and hi is not None and not np.isnan(F0):
            vk, vl, vh = mid(rec, i), mid(lo, i), mid(hi, i)
            if not np.isnan(vk + vl + vh):
                dd = (vk - s["strike"] * (vh - vl) / 100.0) / F0
                if 0.05 <= abs(dd) <= 0.98 and np.sign(dd) == sgn:
                    delta = float(dd)
                    r["delta_src"] = "neighbours"
        del rec_n
        if delta is None and s["delta_rec"] is not None:
            delta = float(s["delta_rec"])
            r["delta_src"] = "recorded"
        r["delta"] = delta

        def premise(t):
            F = fut["ltp"][t]
            if np.isnan(F):
                return True
            if s["dir"] == "LONG":
                return F >= s["or_high"] if s["or_high"] else F >= F0 * (1 - 0.0015)
            return F <= s["or_low"] if s["or_low"] else F <= F0 * (1 + 0.0015)
        ask0 = float(ask_w[i])
        fills = {"NOW": (i, ask0)}
        for k in (1, 2, 3, 5):
            t = i + k
            ok = t < cut and rec["usable"][t] and not np.isnan(ask_w[t]) and ask_w[t] * LOT + C.charges(ask_w[t], 0.0) <= sn441.ROOM
            fills[f"DELAY-{k}"] = (t, float(ask_w[t])) if ok else None
        for name in ("PLAIN", "DISCOUNT"):
            got, why = None, "WINDOW_END"
            if name == "DISCOUNT" and delta is None:
                why = "NO_DELTA"
            else:
                for t in range(i + 1, min(i + W + 1, cut)):
                    if not premise(t):
                        why = "PREMISE_FAILED"
                        break
                    if not rec["usable"][t] or np.isnan(ask_w[t]):
                        continue
                    F = fut["ltp"][t]
                    lim = ask0 - D if name == "PLAIN" else (ask0 + delta * (F - F0) - D if not np.isnan(F) else np.nan)
                    if not np.isnan(lim) and ask_w[t] <= lim + 1e-9:
                        got = (t, float(ask_w[t]))
                        break
            fills[name] = got
            r[f"{name}_why"] = "FILLED" if got else why
        x = min(i + 60, cut)
        for st in (205.0, 400.0):
            S = int(st)
            for name, f in fills.items():
                if f is None or x <= f[0]:
                    r[f"{name}@{S}"] = None
                    continue
                arr = ask_w.copy()
                arr[f[0]] = f[1]
                state, n, _x, _b = sn441.legal(arr, bid_w, f[0], x, st)
                r[f"{name}@{S}"] = n if state == "ENTERED" else None
                r[f"{name}_px"] = f[1]
                r[f"{name}_t"] = f[0]
        rows.append(r)
    res = {"signals_kept": len(decs), "states": {}}
    for r in rows:
        res["states"][r["state"]] = res["states"].get(r["state"], 0) + 1
    pr = [r for r in rows if r["state"] == "PRICED"]
    res["days"] = len({r["day"] for r in pr})
    res["delta_src"] = {k: sum(1 for r in pr if r.get("delta_src") == k) for k in ("neighbours", "recorded")}
    res["why"] = {n: {w: sum(1 for r in pr if r.get(f"{n}_why") == w) for w in ("FILLED", "PREMISE_FAILED", "WINDOW_END", "NO_DELTA")} for n in ("PLAIN", "DISCOUNT")}
    arms = ("NOW", "DELAY-1", "DELAY-2", "DELAY-3", "DELAY-5", "PLAIN", "DISCOUNT")
    for S in (205, 400):
        base = [r for r in pr if r.get(f"NOW@{S}") is not None]
        blk = {"decisions": len(base)}
        for a in arms:
            xs = [r.get(f"{a}@{S}") for r in base]
            fl = [r for r in base if r.get(f"{a}@{S}") is not None]
            blk[a] = {"fills": len(fl), "per_decision_misses_zero": round(float(np.mean([x if x is not None else 0.0 for x in xs]))) if base else None,
                      "mean_on_fills": round(float(np.mean([r[f"{a}@{S}"] for r in fl]))) if fl else None,
                      "paired_vs_NOW_on_fills": round(float(np.mean([r[f"{a}@{S}"] - r[f"NOW@{S}"] for r in fl]))) if fl else None,
                      "price_improvement_per_lot": round(float(np.mean([(r["NOW_px"] - r[f"{a}_px"]) * LOT for r in fl])), 1) if fl else None,
                      "missed_NOW_winners": sum(1 for r in base if r.get(f"{a}@{S}") is None and r[f"NOW@{S}"] > 0),
                      "missed_NOW_net": round(sum(r[f"NOW@{S}"] for r in base if r.get(f"{a}@{S}") is None))}
        res[f"@{S}"] = blk
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=float))


if __name__ == "__main__":
    main()
