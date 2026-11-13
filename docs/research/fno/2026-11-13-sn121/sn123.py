"""SN123 - the "+Rs 6-7k moment" for a machine (PLAN.md). A partner-like scalper on every causal Gold-free day,
Rs 25k, 2 lots (1 when 2 do not fit): `random` (entry chance 6% a minute when flat, random side) and `burst` (fresh
3-minute move >= 1.5 ATR x sqrt 3, its direction). Each trade: ATM option at the ask; first of a -15% premium stop
(bid low; stop wins ties), +20% target (bid high) or 5-minute clock; entries 09:20-15:00. Touch table; day lock grid
(target x stop, checked at trade closes) chosen leave-one-year-out for `burst`, same procedure on `random` (NULL)."""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pg  # noqa: E402

C, M = pg.C, pg.M
TARGETS = (1500.0, 3000.0, 6000.0, None)
STOPS = (2500.0, 5000.0)
WALLET = 25000.0


def trade(S, i, d, stress, late=0):
    e = i + late
    if e > 345:
        return None
    K = int(round(S.F["c"][e] / M.STEP) * M.STEP)
    rec = S.option(K, "CE" if d > 0 else "PE")
    if rec is None or not rec[6][e]:
        return None
    ask = M.ask_of(float(rec[0][3][e]))
    lots = 2 if 2 * ask * M.LOT <= WALLET else (1 if ask * M.LOT <= WALLET else 0)
    if not lots:
        return None
    a, bo, bh, bl, bc, bm, tr = rec
    stop, tgt = ask * 0.85, ask * 1.20
    px, j = None, e
    for j in range(e + 1, min(e + 5, 360) + 1):
        if tr[j] and bl[j] <= stop:
            px = min(stop, bo[j])
            break
        if tr[j] and bh[j] >= tgt:
            px = max(tgt, bo[j]) if bo[j] >= tgt else tgt
            break
    if px is None:
        px = bc[j] if tr[j] else bm[j]
    if px is None or np.isnan(px):
        px = ask
    qty = lots * M.LOT
    return (float(px) - ask) * qty - M.charges(ask, float(px), qty) - stress * lots, j


def day_sequence(S, family, stress, late=0):
    c, atr = S.F["c"], S.F["atr"]
    rng = np.random.default_rng(S.seed * 7 + 123)
    nets, i = [], 5
    while i <= 345:
        d = 0
        if family == "random":
            if rng.random() < 0.06:
                d = 1 if rng.random() < 0.5 else -1
        elif i >= 3:
            mv = c[i] - c[i - 3]
            prev = c[i - 1] - c[i - 4] if i >= 4 else 0.0
            thr = 1.5 * atr[i] * math.sqrt(3)
            if abs(mv) >= thr and abs(prev) < 1.5 * atr[i - 1] * math.sqrt(3):
                d = 1 if mv > 0 else -1
        if d:
            got = trade(S, i, d, stress, late)
            if got is not None:
                nets.append(got[0])
                i = got[1] + 1
                continue
        i += 1
    return nets


def day_result(nets, T, Sx):
    cum = 0.0
    for x in nets:
        cum += x
        if (T is not None and cum >= T) or cum <= -Sx:
            return cum
    return cum


if __name__ == "__main__":
    out_path = HERE / "results-sn123.json"
    if out_path.exists():
        raise SystemExit("SN123 is scored once")
    days = [S for S in pg.all_sessions() if C.gold_free(S.day)]
    seqs = {}
    for fam in ("burst", "random"):
        for stress, late in ((205.0, 0), (400.0, 0), (205.0, 1), (0.0, 0)):
            seqs[(fam, stress, late)] = {S.day: day_sequence(S, fam, stress, late) for S in days}
        print("sequences built", fam, flush=True)
    touch = {}
    for fam in ("burst", "random"):
        for stress in (205.0, 0.0):
            sq = seqs[(fam, stress, 0)]
            peaks, finals = [], []
            for d, nets in sq.items():
                cum = np.cumsum(nets) if nets else np.array([0.0])
                peaks.append(float(cum.max()))
                finals.append(float(cum[-1]))
            peaks, finals = np.array(peaks), np.array(finals)
            touch[f"{fam} | stress {int(stress)}"] = {
                "days": len(finals), "trades_per_day": round(float(np.mean([len(v) for v in sq.values()])), 1),
                **{f"touched_+{x // 1000}k": round(float(np.mean(peaks >= x)), 3) for x in (2000, 4000, 6000)},
                "ended_green": round(float(np.mean(finals > 0)), 3), "mean_day": round(float(finals.mean())),
                "total": round(float(finals.sum())), "mean_day_given_back_from_peak": round(float((peaks - finals).mean()))}
    for k, v in touch.items():
        print(f"TOUCH {k:22s}", v, flush=True)

    def table(fam, stress=205.0, late=0):
        sq = seqs[(fam, stress, late)]
        out = {}
        for T, Sx in itertools.product(TARGETS, STOPS):
            per = {}
            for y in C.YEARS:
                xs = [day_result(n, T, Sx) for d, n in sq.items() if d[:4] == y]
                per[y] = {"net": round(sum(xs)), "green": sum(x > 0 for x in xs), "red": sum(x < 0 for x in xs)}
            out[f"target {T} stop {Sx}"] = per
        return out
    real, null = table("burst"), table("random")
    Lr, Ln = C.loyo(real, "profit"), C.loyo(null, "profit")
    rob = {"stress 400": sum(table("burst", 400.0)[Lr[y]["pick"]][y]["net"] for y in C.YEARS),
           "1 minute late": sum(table("burst", 205.0, 1)[Lr[y]["pick"]][y]["net"] for y in C.YEARS)}
    held = [Lr[y]["net"] for y in C.YEARS]
    ok = Lr["sum"]["net"] > 0 and sum(x > 0 for x in held) >= 3 and Lr["sum"]["net"] > Ln["sum"]["net"] and all(v > 0 for v in rob.values())
    for k, per in real.items():
        print(f"  burst  {k:26s}", [per[y]["net"] for y in C.YEARS], sum(per[y]["net"] for y in C.YEARS))
    for k, per in null.items():
        print(f"  random {k:26s}", [per[y]["net"] for y in C.YEARS], sum(per[y]["net"] for y in C.YEARS))
    print("LOYO burst", {y: (Lr[y]["pick"], Lr[y]["net"]) for y in C.YEARS}, "sum", Lr["sum"]["net"])
    print("LOYO random (NULL) sum", Ln["sum"]["net"], "| robust", rob, "| PASS" if ok else "| NOT PROVEN", flush=True)
    heldout_days = {}
    for y in C.YEARS:
        T, Sx = (None if Lr[y]["pick"].split()[1] == "None" else float(Lr[y]["pick"].split()[1])), float(Lr[y]["pick"].split()[3])
        for d, n in seqs[("burst", 205.0, 0)].items():
            if d[:4] == y:
                heldout_days[d] = day_result(n, T, Sx)
    out_path.write_text(json.dumps({"touch": touch, "real": real, "null": null, "loyo_real": Lr, "loyo_null": Ln, "robust": rob,
                                    "PASS": bool(ok), "heldout_day_nets": heldout_days}, indent=1, default=float), encoding="utf-8")
