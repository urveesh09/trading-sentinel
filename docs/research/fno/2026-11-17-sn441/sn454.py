"""SN454 (own): passive entry at the touch with a conservative fill model (hftbacktest's lesson: a resting order fills only
when price trades through it) (PLAN.md section 2, frozen at f56f5807; details fixed here before any number).

A. Panel (minute snapshots; SN441's decisions: day x clock x side, 1-ITM front contract):
   L = best bid at e + 1 tick (Rs 0.05). If L >= best ask at e the order is marketable: MARKETABLE, filled as NOW.
   m = the first usable snapshot in (e, e + 2]. PASSIVE fills at L when m's best ask <= L and the ask levels priced <= L
   hold >= one lot (65); else it crosses at m's walked ask (no miss). DELAY-1 = the walked ask at m; NOW = the walked
   ask at e. Exit for all: the common deadline min(e + 60, cutoff) by sn441.legal (stop on an observed mark).
   Reported per stress: fill share, paired price improvement against NOW and DELAY-1 per lot, net (misses none), and the
   NOW outcome of decisions where PASSIVE filled against those where it did not (adverse selection).
B. Seconds (Nov 16 recorder plumbing copy, SN432's decisions: every minute 09:16-10:18, ATM / 1-ITM CE / PE, front
   weekly): bid_t / ask_t from the last fresh valid packet at or before t; L = bid_t + 1 tick (MARKETABLE if >= ask_t).
   PASSIVE fills at L if within (t, t + 5] a fresh valid packet shows ask <= L with the ask levels <= L holding a lot, or
   a trade prints strictly below L (ltp < L and ltp changed from the previous packet); else at t + 5 it crosses with
   fw2.entry and the cap ask_t + 2 ticks. IMMEDIATE = fw2.entry at t; DELAY-5 = fw2.entry at t + 5 (same cap).
   Outcome as SN432: the walked bid of the first fresh packet >= t + 60 / t + 300 s, gross per lot. Plumbing only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-17-sn426"))
import sn441  # noqa: E402
import sn432  # noqa: E402

sn428, C, qa = sn441.sn428, sn441.C, sn441.qa
fw2, fw5 = sn432.fw2, sn432.fw5
OUT = HERE / "results-sn454.json"
LOT, TICK = 65, 0.05


def panel():
    man = qa.manifest()
    days = [d for d in man["quote_days"] if d not in set(man["unsealed_days"])]
    gold_days = {x["day"] for x in json.loads(C.RUNS.read_text(encoding="utf-8"))["2023-2026 DEPLOYED @205"]["log"]}
    rows = []
    for d in days:
        q = qa.load(d)
        cons = sn428.contracts(q, d)
        exps = sorted({k[1] for k in cons})
        if not exps:
            continue
        front = exps[0]
        expiring = front == d
        cut = 255 if expiring else 355
        lab = sn441.label_of(d, front, gold_days)
        fut = qa.front_fut(q, "NIFTY")
        for c, e in sn441.CLOCKS.items():
            if expiring and e >= cut:
                continue
            F = fut["ltp"][e] if fut is not None else np.nan
            if np.isnan(F):
                continue
            atm = int(round(F / 50.0) * 50)
            for side in ("CE", "PE"):
                k = ("NIFTY", front, atm + (-50 if side == "CE" else 50), side)
                rec = cons.get(k)
                if rec is None:
                    continue
                ask_w, bid_w = C.walked(rec, "ask"), C.walked(rec, "bid")
                if np.isnan(ask_w[e]) or not rec["usable"][e] or not sn442_afford(ask_w[e]):
                    continue
                m = next((x for x in (e + 1, e + 2) if x < cut and rec["usable"][x] and not np.isnan(ask_w[x])), None)
                r = {"day": d, "clock": c, "label": lab, "side": side}
                L = round(float(rec["bid"][e]) + TICK, 2)
                if np.isnan(rec["bid"][e]) or L >= rec["ask"][e] - 1e-9:
                    r["passive_state"] = "MARKETABLE"
                    p_pass = float(ask_w[e]); m_pass = e
                elif m is None:
                    r["passive_state"] = "NO_NEXT_SNAPSHOT"
                    p_pass = None; m_pass = None
                else:
                    lv = [(rec["askp"][j, m], rec["askq"][j, m]) for j in range(5)]
                    qty = sum(qq for pp, qq in lv if not np.isnan(pp) and pp <= L + 1e-9)
                    if rec["ask"][m] <= L + 1e-9 and qty >= LOT:
                        r["passive_state"] = "FILLED_AT_LIMIT"
                        p_pass = L
                    else:
                        r["passive_state"] = "CROSSED"
                        p_pass = float(ask_w[m])
                    m_pass = m
                x_dead = min(e + 60, cut)
                for st in (205.0, 400.0):
                    S = int(st)
                    for name, mm, px in (("NOW", e, float(ask_w[e])), ("DELAY-1", m, None if m is None else float(ask_w[m])), ("PASSIVE", m_pass, p_pass)):
                        if mm is None or px is None or x_dead <= mm:
                            r[f"{name}@{S}"] = None
                            continue
                        arr = ask_w.copy()
                        arr[mm] = px
                        state, n, _x, _b = sn441.legal(arr, bid_w, mm, x_dead, st)
                        r[f"{name}@{S}"] = n if state == "ENTERED" else None
                        r[f"{name}_px"] = px
                rows.append(r)
    return rows


def sn442_afford(a):
    return a * LOT + C.charges(a, 0.0) <= sn441.ROOM


def seconds():
    day = fw2.Day(sn432.FOLDER, fw5.load_open(sn432.FOLDER))
    rows = []
    for t in range(60, 3781, 60):
        atm = day.atm(float(t))
        if atm is None:
            continue
        for side in ("CE", "PE"):
            for dep in (0, 1):
                kk = atm + (-dep * 50 if side == "CE" else dep * 50)
                tok = day.opt.get((day.front, kk, side))
                d = None if tok is None else day.D.get(tok)
                if d is None or "ask" not in d:
                    continue
                j = sn432.last_fresh(d, float(t))
                if j is None:
                    continue
                ask_t, bid_t = float(d["ask"][j]), float(d["bid"][j])
                cap = ask_t + 2 * TICK
                r = {"t": t, "side": side, "depth": dep, "ask_t": ask_t, "bid_t": bid_t}
                g, _ = fw2.entry(day, tok, float(t), cap=cap)
                r["IMMEDIATE"] = None if not g else {"px": g[1], **sn432.outcome(day, tok, g[0], g[1], float(t))}
                g5, _ = fw2.entry(day, tok, float(t + 5), cap=cap)
                r["DELAY-5"] = None if not g5 else {"px": g5[1], **sn432.outcome(day, tok, g5[0], g5[1], float(t))}
                L = round(bid_t + TICK, 2)
                if L >= ask_t - 1e-9:
                    r["passive_state"] = "MARKETABLE"
                    r["PASSIVE"] = r["IMMEDIATE"]
                else:
                    filled = False
                    idx = np.flatnonzero((d["t"] > t) & (d["t"] <= t + 5))
                    for k in idx:
                        if d["ok"][k]:
                            qty = sum(q for p, q in zip(d["asks"][:, k], d["askq"][:, k]) if 0 < p <= L + 1e-9)
                            if d["ask"][k] <= L + 1e-9 and qty >= day.lot:
                                filled = True
                                break
                        if k > 0 and d["ltp"][k] < L - 1e-9 and d["ltp"][k] != d["ltp"][k - 1]:
                            filled = True
                            break
                    if filled:
                        r["passive_state"] = "FILLED_AT_LIMIT"
                        r["PASSIVE"] = {"px": L, **sn432.outcome(day, tok, None, L, float(t))}
                    else:
                        r["passive_state"] = "CROSSED"
                        r["PASSIVE"] = r["DELAY-5"]
                rows.append(r)
    return day.day, rows


def main():
    if OUT.exists():
        raise SystemExit("SN454 is run once")
    rows = panel()
    res = {"A_panel": {"decisions": len(rows), "states": {}}}
    for r in rows:
        res["A_panel"]["states"][r["passive_state"]] = res["A_panel"]["states"].get(r["passive_state"], 0) + 1
    for S in (205, 400):
        for lab in ("ALL", "EMPTY", "GOLD", "EXPIRY", "NO_REPLAY"):
            base = [r for r in rows if (lab == "ALL" or r["label"] == lab) and r.get(f"NOW@{S}") is not None and r.get(f"PASSIVE@{S}") is not None]
            if not base:
                continue
            blk = {"decisions": len(base)}
            for a in ("NOW", "DELAY-1", "PASSIVE"):
                xs = [r[f"{a}@{S}"] for r in base if r.get(f"{a}@{S}") is not None]
                blk[a] = round(float(np.mean(xs))) if xs else None
            both = [r for r in base if r.get(f"DELAY-1@{S}") is not None]
            blk["PASSIVE_minus_DELAY-1"] = round(float(np.mean([r[f"PASSIVE@{S}"] - r[f"DELAY-1@{S}"] for r in both]))) if both else None
            blk["PASSIVE_minus_NOW"] = round(float(np.mean([r[f"PASSIVE@{S}"] - r[f"NOW@{S}"] for r in base])))
            fl = [r for r in base if r["passive_state"] == "FILLED_AT_LIMIT"]
            nf = [r for r in base if r["passive_state"] != "FILLED_AT_LIMIT"]
            blk["limit_fills"] = len(fl)
            blk["NOW_outcome_when_limit_filled"] = round(float(np.mean([r[f"NOW@{S}"] for r in fl]))) if fl else None
            blk["NOW_outcome_when_not"] = round(float(np.mean([r[f"NOW@{S}"] for r in nf]))) if nf else None
            blk["price_saving_per_lot_on_limit_fills"] = round(float(np.mean([(r["NOW_px"] - r["PASSIVE_px"]) * LOT for r in fl])), 1) if fl else None
            res["A_panel"][f"{lab} @{S}"] = blk
    day, srows = seconds()
    B = {"day": day, "decisions": len(srows), "states": {}}
    for r in srows:
        B["states"][r["passive_state"]] = B["states"].get(r["passive_state"], 0) + 1
    for h in (60, 300):
        for a in ("IMMEDIATE", "DELAY-5", "PASSIVE"):
            xs = [r[a][f"net{h}"] for r in srows if r[a] and r[a].get(f"net{h}") is not None]
            B[f"{a} mean net{h}"] = round(float(np.mean(xs)), 1) if xs else None
            B[f"{a} filled"] = sum(1 for r in srows if r[a])
        both = [r for r in srows if r["IMMEDIATE"] and r["PASSIVE"] and r["IMMEDIATE"].get(f"net{h}") is not None and r["PASSIVE"].get(f"net{h}") is not None]
        B[f"PASSIVE_minus_IMMEDIATE net{h} (paired)"] = round(float(np.mean([r["PASSIVE"][f"net{h}"] - r["IMMEDIATE"][f"net{h}"] for r in both])), 1) if both else None
        bd = [r for r in srows if r["DELAY-5"] and r["PASSIVE"] and r["DELAY-5"].get(f"net{h}") is not None and r["PASSIVE"].get(f"net{h}") is not None]
        B[f"PASSIVE_minus_DELAY-5 net{h} (paired)"] = round(float(np.mean([r["PASSIVE"][f"net{h}"] - r["DELAY-5"][f"net{h}"] for r in bd])), 1) if bd else None
        fl = [r for r in srows if r["passive_state"] == "FILLED_AT_LIMIT" and r["IMMEDIATE"] and r["IMMEDIATE"].get(f"net{h}") is not None]
        nf = [r for r in srows if r["passive_state"] != "FILLED_AT_LIMIT" and r["IMMEDIATE"] and r["IMMEDIATE"].get(f"net{h}") is not None]
        B[f"IMMEDIATE net{h} when limit filled / not"] = [round(float(np.mean([r["IMMEDIATE"][f"net{h}"] for r in fl])), 1) if fl else None,
                                                         round(float(np.mean([r["IMMEDIATE"][f"net{h}"] for r in nf])), 1) if nf else None]
    res["B_seconds_plumbing"] = B
    res["rows_A"] = rows
    res["rows_B"] = srows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if not k.startswith("rows")}, indent=1, default=float))


if __name__ == "__main__":
    main()
