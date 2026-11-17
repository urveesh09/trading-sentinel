"""SN444: an honest five-second execution companion (PLAN.md section 1, frozen at f56f5807; details fixed here before any
number). Built and frozen now; scored once on future recorder sessions. `python fx5.py mechanics` runs the plumbing check on
the Nov 16 copy (labelled plumbing, before the forward start).

One decision = (recorder day, option token, decision time t, hold_s). ask0 / bid0 = the inside ask / bid of the last fresh valid
packet at or before t (fw2's validity: bid > 0, ask > bid, receipt lag - the day's offset <= 2 s); cap = ask0 + 2 ticks.
Fills use fw7b.entry_legal (only ask levels <= cap count; the full lot in one packet, 0.5 - 2.5 s after the order).
Every arm exits by fw2.hold at the SAME planned time T = t + hold_s (the Rs 3,000 stop on fresh marks; an exit unresolved
120 s after T books the premium lost); one lot; Zerodha charges and the stress.
  IMMEDIATE   the order at t
  DELAY-5     the order at t + 5, unconditionally (the control for the delay itself)
  CONFIRM-5   the order at t + 5 only if persistence was OBSERVED over (t, t + 5]:
                every valid fresh packet there has inside ask <= ask0 and five-level ask depth >= one lot;
                the first such packet arrives <= GAP after t, the last >= t + 5 - GAP, and no two consecutive are more than
                GAP apart (GAP = 2.0 s, the house freshness rule); else NOT_CONFIRMED (no order)
  PASSIVE-5   a resting buy at L = bid0 + 1 tick for 5 s (MARKETABLE -> IMMEDIATE if L >= ask0). It fills at L only on
              trade-through evidence: a fresh valid packet with ask <= L and the ask levels <= L holding a lot, or a trade
              strictly below L (ltp < L and changed from the previous packet). Else at t + 5 it crosses like DELAY-5.
Per original decision: state, fill price, net per stress (misses count 0), and the paired fill improvement per lot against
IMMEDIATE; the missed IMMEDIATE winners are counted.
PROSPECTIVE (frozen): decisions = fw7c's opening decision on every recorder session after this freeze, plus Production's
FNO_PAPER NIFTY directional signals (SN443's admission and dedupe) on those sessions, hold 60 minutes (fw7c: its own hold).
Read once when 60 decisions exist. CONFIRM-5 is worth a paper companion only if, per original decision, it beats BOTH
IMMEDIATE and DELAY-5 at Rs 205 and 400, with the missed winners charged.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn396"))
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
sys.path.insert(0, str(FNO / "2026-11-16-sn351"))
import fw2  # noqa: E402
import fw7b  # noqa: E402

TICK, GAP, W = 0.05, 2.0, 5.0
STRESSES = (205.0, 400.0)
OUT = HERE / "results-sn444-mechanics.json"


def last_fresh(d, t):
    k = int(np.searchsorted(d["t"], t, side="right")) - 1
    while k >= 0 and not d["ok"][k]:
        k -= 1
    return k if k >= 0 and t - d["t"][k] <= GAP else None


def confirmed(d, t, ask0, lot, w=W, gap=GAP):
    """(True, 'confirmed') or (False, reason): persistence must be observed across the whole window."""
    m = (d["t"] > t) & (d["t"] <= t + w) & d["ok"]
    ts = d["t"][m]
    if not len(ts):
        return False, "no_packet"
    if ts[0] - t > gap:
        return False, "late_first_packet"
    if ts[-1] < t + w - gap:
        return False, "window_end_unobserved"
    if len(ts) > 1 and float(np.max(np.diff(ts))) > gap:
        return False, "gap_inside_window"
    if not (np.all(d["ask"][m] <= ask0 + 1e-9) and np.all(d["a5"][m] >= lot)):
        return False, "ask_rose_or_thin"
    return True, "confirmed"


def passive_fill(d, t, L, lot, w=W):
    idx = np.flatnonzero((d["t"] > t) & (d["t"] <= t + w))
    for k in idx:
        if d["ok"][k]:
            qty = sum(q for p, q in zip(d["asks"][:, k], d["askq"][:, k]) if 0 < p <= L + 1e-9)
            if d["ask"][k] <= L + 1e-9 and qty >= lot:
                return int(k)
        if k > 0 and d["ltp"][k] < L - 1e-9 and d["ltp"][k] != d["ltp"][k - 1]:
            return int(k)
    return None


def _book(day, tok, k, px, T):
    out = {"px": round(float(px), 4)}
    for s in STRESSES:
        h = fw2.hold(day, tok, k, px, T, s)
        out[f"net{int(s)}"] = h["net"]
        out[f"status{int(s)}"] = h["status"]
    return out


def decide(day, tok, t, hold_s):
    d = day.D.get(tok)
    if d is None or "ok" not in d:
        return {"state": "NO_INSTRUMENT"}
    j = last_fresh(d, t)
    if j is None:
        return {"state": "NO_FRESH_QUOTE"}
    ask0, bid0 = float(d["ask"][j]), float(d["bid"][j])
    cap = ask0 + 2 * TICK
    T = t + hold_s
    r = {"state": "DECIDED", "ask0": ask0, "bid0": bid0, "cap": round(cap, 2)}

    def at(ta):
        got, why, _p = fw7b.entry_legal(day, tok, ta, cap)
        if got is None:
            return {"state": "MISSED", "why": why}
        k, px = got
        return {"state": "FILLED", "fill_t": round(float(d["t"][k]), 3), **_book(day, tok, k, px, T)}
    r["IMMEDIATE"] = at(t)
    r["DELAY-5"] = at(t + W)
    ok, why = confirmed(d, t, ask0, day.lot)
    r["CONFIRM-5"] = at(t + W) if ok else {"state": "NOT_CONFIRMED", "why": why}
    L = round(bid0 + TICK, 2)
    if L >= ask0 - 1e-9:
        r["PASSIVE-5"] = dict(r["IMMEDIATE"], passive="MARKETABLE")
    else:
        k = passive_fill(d, t, L, day.lot)
        r["PASSIVE-5"] = {"state": "FILLED", "passive": "AT_LIMIT", **_book(day, tok, k, L, T)} if k is not None else dict(r["DELAY-5"], passive="CROSSED")
    return r


def score(rows):
    res = {"decisions": len(rows)}
    base = [r for r in rows if r.get("state") == "DECIDED"]
    for arm in ("IMMEDIATE", "DELAY-5", "CONFIRM-5", "PASSIVE-5"):
        blk = {"filled": sum(1 for r in base if r[arm]["state"] == "FILLED")}
        for s in STRESSES:
            S = int(s)
            xs = [r[arm][f"net{S}"] if r[arm]["state"] == "FILLED" else 0.0 for r in base]
            blk[f"per_decision@{S}"] = round(float(np.mean(xs)), 1) if xs else None
            blk[f"missed_immediate_winners@{S}"] = sum(1 for r in base if r[arm]["state"] != "FILLED" and r["IMMEDIATE"]["state"] == "FILLED" and r["IMMEDIATE"][f"net{S}"] > 0)
        both = [r for r in base if r[arm]["state"] == "FILLED" and r["IMMEDIATE"]["state"] == "FILLED"]
        blk["paired_fill_improvement_per_lot"] = round(float(np.mean([(r["IMMEDIATE"]["px"] - r[arm]["px"]) for r in both])) * 65, 1) if both else None
        res[arm] = blk
    res["confirm_reasons"] = {}
    for r in base:
        w = r["CONFIRM-5"].get("why", "confirmed")
        res["confirm_reasons"][w] = res["confirm_reasons"].get(w, 0) + 1
    res["passive_states"] = {}
    for r in base:
        w = r["PASSIVE-5"].get("passive", "?")
        res["passive_states"][w] = res["passive_states"].get(w, 0) + 1
    return res


def mechanics():
    if OUT.exists():
        raise SystemExit("SN444 mechanics are run once")
    import fw5  # noqa: E402
    folder = Path(r"C:\Users\Urveesh\AppData\Local\Temp\claude\f191b6166a36c84a\b7c0aa9b-c954-4f08-9df8-57422081ea0c\scratchpad\rec\2026-11-16")
    day = fw2.Day(folder, fw5.load_open(folder))
    rows = []
    for t in range(60, 3601, 60):
        atm = day.atm(float(t))
        if atm is None:
            continue
        for side in ("CE", "PE"):
            for dep in (0, 1):
                k = atm + (-dep * 50 if side == "CE" else dep * 50)
                tok = day.opt.get((day.front, k, side))
                if tok is None:
                    continue
                r = decide(day, tok, float(t), 300.0)
                r.update(t=t, side=side, depth=dep)
                rows.append(r)
    res = {"label": "PLUMBING (Nov 16 recorder copy, before the forward start; hold 300 s)", **score(rows), "rows": rows}
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=float))


if __name__ == "__main__":
    if sys.argv[1:] == ["mechanics"]:
        mechanics()
