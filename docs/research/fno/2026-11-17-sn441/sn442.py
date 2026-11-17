"""SN442: the value of waiting once a signal exists, contract locked (PLAN.md section 1, frozen at f56f5807; details fixed
here before any number). Hindsight diagnostics plus fixed-wait arms; never strategy P&L.

Panel and exits as SN441 (sn441.legal: stop on an observed mark, the first usable walked bid at or after the scheduled exit
within 5 minutes, else UNRESOLVED). A decision = day x clock x side (CE / PE), the 1-ITM contract on the front expiry at the
clock, locked (strike, expiry, side); maximum debit Rs 15,000 (one lot + entry charges).
Realistic arms (entry minute m, the walked ask there; NO_FILL if none or unaffordable):
  NOW m = e;  WAIT-k m = e + k (k = 1, 5, 15)
Hindsight arms:
  BEST-PRICE-30   the minute in [e, e+30] with the lowest affordable walked ask (earliest on ties), locked contract
  FWD-LOCKED      the best NET over entry minutes in [e, e+30], locked contract
  FWD-RECHOSEN    the best NET over entry minutes in [e, e+30], each minute's own 1-ITM contract
  TIMING-428      SN428's TIMING: best net over [e-30, e+30], each minute's own 1-ITM, own 60-minute exit, SN428's old exit
Exit A (main): the common deadline x = min(e + 60, cutoff); exit B (diagnostic): 60 minutes from the arm's own entry,
min(m + 60, cutoff). Cutoff 355 (15:10), or 255 (13:30) for an expiring contract; entries no later than cutoff - 1.
Reported per stress (205 / 400): on decisions where NOW resolves, each arm's mean (misses = 0) and paired mean against NOW,
fills, by label and clock; and on the coin side alone (SN428's decisions) the TIMING-428 -> FWD-RECHOSEN -> FWD-LOCKED ->
BEST-PRICE-30 -> NOW ladder.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn441  # noqa: E402

sn428, C, qa = sn441.sn428, sn441.C, sn441.qa
OUT = HERE / "results-sn442.json"
CLOCKS = sn441.CLOCKS
LOT, ROOM = sn441.LOT, sn441.ROOM


def afford(a):
    return not np.isnan(a) and a * LOT + C.charges(a, 0.0) <= ROOM


def main():
    if OUT.exists():
        raise SystemExit("SN442 is run once")
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
        walked = {k: (C.walked(v, "ask"), C.walked(v, "bid")) for k, v in cons.items()}

        def leg(side, m):
            F = fut["ltp"][m] if fut is not None and 0 <= m < len(fut["ltp"]) else np.nan
            if np.isnan(F):
                return None
            atm = int(round(F / 50.0) * 50)
            return walked.get(("NIFTY", front, atm + (-50 if side == "CE" else 50), side))
        for c, e in CLOCKS.items():
            if expiring and e >= cut:
                continue
            coin = random.Random(f"sn428-{d}-{c}").choice(("CE", "PE"))
            x_dead = min(e + 60, cut)
            for side in ("CE", "PE"):
                lg = leg(side, e)
                if lg is None:
                    continue
                ask, bid = lg
                r = {"day": d, "clock": c, "label": lab, "side": side, "coin_side": side == coin}
                for st in (205.0, 400.0):
                    S = int(st)

                    def at(m, own):
                        if m >= cut or not afford(ask[m]):
                            return "NO_FILL", None
                        x = min(m + 60, cut) if own else x_dead
                        if x <= m:
                            return "NO_FILL", None
                        state, n, _x, _b = sn441.legal(ask, bid, m, x, st)
                        return state, n
                    for name, m in (("NOW", e), ("WAIT-1", e + 1), ("WAIT-5", e + 5), ("WAIT-15", e + 15)):
                        for ex, own in (("A", False), ("B", True)):
                            stt, n = at(m, own)
                            r[f"{name}|{ex}@{S}"] = n if stt == "ENTERED" else None
                            r[f"{name}|{ex}@{S}|state"] = stt
                    cand = [m for m in range(e, min(e + 31, cut)) if afford(ask[m])]
                    if cand:
                        mbest = min(cand, key=lambda m: (ask[m], m))
                        for ex, own in (("A", False), ("B", True)):
                            stt, n = at(mbest, own)
                            r[f"BEST-PRICE-30|{ex}@{S}"] = n if stt == "ENTERED" else None
                        r["best_price_delay"] = mbest - e
                        r["best_price_saving_per_lot"] = round(float((ask[e] - ask[mbest]) * LOT), 2) if afford(ask[e]) else None
                    for ex, own in (("A", False), ("B", True)):
                        vals = [at(m, own) for m in cand]
                        vals = [n for s_, n in vals if s_ == "ENTERED"]
                        r[f"FWD-LOCKED|{ex}@{S}"] = max(vals) if vals else None
                    fr = []
                    for m in range(e, min(e + 31, cut)):
                        lg2 = leg(side, m)
                        if lg2 is None or not afford(lg2[0][m]):
                            continue
                        stt, n, _x, _b = sn441.legal(lg2[0], lg2[1], m, min(m + 60, cut), st)
                        if stt == "ENTERED":
                            fr.append(n)
                    r[f"FWD-RECHOSEN|B@{S}"] = max(fr) if fr else None
                    tm = []
                    for m in range(max(1, e - 30), e + 31):
                        lg2 = leg(side, m)
                        if lg2 is None:
                            continue
                        v = sn428.trade(lg2[0], lg2[1], m, min(m + 60, cut), st, False)
                        if v is not None:
                            tm.append(v)
                    r[f"TIMING-428|B@{S}"] = max(tm) if tm else None
                rows.append(r)
    res = {"decisions": len(rows)}
    arms = ["NOW|A", "WAIT-1|A", "WAIT-5|A", "WAIT-15|A", "BEST-PRICE-30|A", "FWD-LOCKED|A",
            "NOW|B", "WAIT-1|B", "WAIT-5|B", "WAIT-15|B", "BEST-PRICE-30|B", "FWD-LOCKED|B", "FWD-RECHOSEN|B", "TIMING-428|B"]
    for S in (205, 400):
        for lab in ("ALL", "EMPTY", "GOLD", "EXPIRY", "NO_REPLAY"):
            base = [r for r in rows if (lab == "ALL" or r["label"] == lab) and r.get(f"NOW|A@{S}") is not None]
            blk = {"decisions": len(base)}
            for a in arms:
                xs = [r.get(f"{a}@{S}") for r in base]
                filled = [x for x in xs if x is not None]
                blk[a] = {"filled": len(filled), "mean_misses_zero": round(float(np.mean([x if x is not None else 0.0 for x in xs]))) if xs else None,
                          "paired_vs_NOW": round(float(np.mean([r[f"{a}@{S}"] - r[f"NOW|{a.split('|')[1]}@{S}"] for r in base
                                                                if r.get(f"{a}@{S}") is not None and r.get(f"NOW|{a.split('|')[1]}@{S}") is not None]))) if filled else None}
            res[f"{lab} @{S}"] = blk
        coin = [r for r in rows if r["coin_side"] and r.get(f"NOW|A@{S}") is not None]
        res[f"coin-side ladder @{S}"] = {"decisions": len(coin), **{a: round(float(np.mean([r[f"{a}@{S}"] for r in coin if r.get(f"{a}@{S}") is not None])))
                                                                   for a in ("TIMING-428|B", "FWD-RECHOSEN|B", "FWD-LOCKED|B", "FWD-LOCKED|A", "BEST-PRICE-30|A", "WAIT-5|A", "NOW|A")}}
        for c in CLOCKS:
            base = [r for r in rows if r["clock"] == c and r.get(f"NOW|A@{S}") is not None]
            res[f"clock {c} @{S}"] = {a: round(float(np.mean([r[f"{a}@{S}"] if r.get(f"{a}@{S}") is not None else 0.0 for r in base]))) if base else None
                                      for a in ("NOW|A", "WAIT-1|A", "WAIT-5|A", "WAIT-15|A", "BEST-PRICE-30|A", "FWD-LOCKED|A")}
    sv = [r["best_price_saving_per_lot"] for r in rows if r.get("best_price_saving_per_lot") is not None]
    dl = [r["best_price_delay"] for r in rows if "best_price_delay" in r]
    res["best_price"] = {"mean_saving_per_lot": round(float(np.mean(sv)), 1), "median_saving_per_lot": round(float(np.median(sv)), 1),
                         "share_at_e": round(float(np.mean([x == 0 for x in dl])), 3), "median_delay_min": float(np.median(dl))}
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=float))


if __name__ == "__main__":
    main()
