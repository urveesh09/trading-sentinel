"""SN78 - a 1-second book for the days SN Gold sits out (research only).

Data: the sealed 1-second archive (sec_data.py): NIFTY index + the opening-ATM call and put, Apr 6 - Jul 27 2026
(77 sessions incl. expiry days). Signals on 30-second bars of the index, known at each bar's last second; buy the
opening-ATM call (up) or put (down) at that second's ask (close + half the year datasets' 75th-pct spread); exits
checked EVERY second on printed seconds: premium stop, target, trail, time stop; flat at 15:00 (13:30 on expiry
days, the owner's "only till 1 or 2 o'clock"). One lot, one position, Rs 30k wallet's 20% day limit, shipped charges
+ Rs 100 / Rs 205 per lot per trade. Days: all, or Gold-empty by a rule known before the open (yesterday's ADX < 30,
or an expiry day, where N11 never trades). Choose on Apr-May, score once on Jun-Jul, against random entries.
"""
from __future__ import annotations

import itertools
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-12-sn01")]
import sec_data as SD  # noqa: E402
import sn01_sim as M  # noqa: E402

LOT = 65
BAR = 30
SPLIT = "2026-06-01"
END_NORMAL = (15 * 60 + 0 - 555) * 60
END_EXPIRY = (13 * 60 + 30 - 555) * 60


def ask_vec(x):
    x = np.asarray(x, dtype=float)
    half = np.select([x < 50, x < 100, x < 150, x < 200, x < 300, x < 450], [0.05, 0.10, 0.15, 0.225, 0.30, 0.40], 0.40)
    return np.maximum(M._bid_vec(x) + 0.05, np.ceil((x + half) / 0.05 - 1e-9) * 0.05)


class Day:
    def __init__(self, day, rec, gold_traded, adx):
        self.day = day
        s = rec["series"]
        self.idx = np.nan_to_num(s["INDEX"].astype(float), nan=np.nan)
        c = self.idx[3].copy()
        last = np.nan
        for k in range(len(c)):           # carry the index forward through a missing second
            if np.isnan(c[k]):
                c[k] = last
            else:
                last = c[k]
        first = np.flatnonzero(~np.isnan(c))
        c[: first[0]] = c[first[0]]
        self.c = c
        self.opt = {}
        for side in ("CE", "PE"):
            a = s[side].astype(float)
            self.opt[side] = (a, M._bid_vec(np.nan_to_num(a[1], nan=0.05)), M._bid_vec(np.nan_to_num(a[2], nan=0.05)),
                              M._bid_vec(np.nan_to_num(a[3], nan=0.05)), np.isfinite(a[3]))
        self.expiry = rec["meta"]["CE"][1] == day
        self.end = END_EXPIRY if self.expiry else END_NORMAL
        nb = len(c) // BAR
        blk = c[: nb * BAR].reshape(nb, BAR)
        self.bc = blk[:, -1]
        self.bh, self.bl = blk.max(1), blk.min(1)
        tr = np.maximum(self.bh - self.bl, np.abs(self.bh - np.concatenate([[self.bc[0]], self.bc[:-1]])))
        atr = np.empty(nb)
        acc = max(tr[:10].mean(), 0.5)
        for b in range(nb):
            acc += (tr[b] - acc) / 20.0
            atr[b] = acc
        self.atr = atr
        self.twap = np.cumsum(self.bc) / np.arange(1, nb + 1)
        self.gold_traded = gold_traded
        self.adx = adx

    def gold_free(self):
        return self.expiry or (self.adx is not None and self.adx < 30)


def fresh(cond):
    out = cond.copy()
    out[1:] &= ~cond[:-1]
    return out


def signals(D, fam, seed=0):
    nb = len(D.bc)
    up = np.zeros(nb, bool)
    dn = np.zeros(nb, bool)
    k = fam["kind"]
    if k == "ORB":
        n = fam["n"] * 2                 # minutes -> 30-second bars
        hi, lo = D.bh[:n].max(), D.bl[:n].min()
        hold = fam["hold"] // BAR + 1
        a = np.convolve((D.bc > hi + fam["buf"] * D.atr).astype(int), np.ones(hold, int), "full")[:nb] >= hold
        b = np.convolve((D.bc < lo - fam["buf"] * D.atr).astype(int), np.ones(hold, int), "full")[:nb] >= hold
        up[n:], dn[n:] = a[n:], b[n:]
    elif k == "MOMO":
        L = fam["k"]
        mv = np.zeros(nb)
        mv[L:] = D.bc[L:] - D.bc[:-L]
        up = mv >= fam["z"] * D.atr * np.sqrt(L)
        dn = mv <= -fam["z"] * D.atr * np.sqrt(L)
    elif k == "TWAPX":
        prev = np.concatenate([[D.twap[0]], D.twap[:-1]])
        up = (D.bc > D.twap + fam["buf"] * D.atr) & (D.twap > prev)
        dn = (D.bc < D.twap - fam["buf"] * D.atr) & (D.twap < prev)
    elif k == "FADE":
        dev = (D.bc - D.twap) / D.atr
        back = np.concatenate([[0.0], np.diff(D.bc)])
        dn = (dev >= fam["z"]) & (back < 0)
        up = (dev <= -fam["z"]) & (back > 0)
    elif k == "RANDOM":
        rng = np.random.default_rng((fam["seed"] * 7919 + int(D.day.replace("-", ""))) & 0xFFFFFFFF)
        hit = rng.random(nb) < fam["p"]
        side = rng.random(nb) < 0.5
        out = np.zeros(nb, np.int8)
        out[hit & side], out[hit & ~side] = 1, -1
        out[:10] = 0
        return out
    out = np.zeros(nb, np.int8)
    out[fresh(up)] = 1
    out[fresh(dn) & (out == 0)] = -1
    out[:10] = 0                         # nothing in the first 5 minutes
    return out


def play_day(D, cfg, stress, wallet=30000.0):
    sig = signals(D, cfg["fam"])
    realized, n, free = 0.0, 0, 0
    loss = 0.2 * wallet
    for b in np.flatnonzero(sig):
        s0 = (b + 1) * BAR - 1
        if s0 < free or s0 >= D.end - 60 or n >= cfg["max_trades"]:
            continue
        side = "CE" if sig[b] > 0 else "PE"
        a, bh, bl, bc, ok = D.opt[side]
        if not ok[s0]:
            continue
        ask = float(ask_vec([a[3][s0]])[0])
        if ask * LOT > wallet:
            continue
        seg = slice(s0 + 1, D.end + 1)
        okk, lo, hi, cl = ok[seg], bl[seg], bh[seg], bc[seg]
        stop = ask * (1 - cfg["stop"])
        stop = max(stop, ask - (loss + realized - M.charges(ask, ask, LOT) - stress) / LOT)
        tgt = ask * (1 + cfg["target"])
        peak = np.maximum.accumulate(np.where(okk, cl, ask))
        trail = np.where(peak >= ask * (1 + cfg["act"]), peak - cfg["give"] * (peak - ask), -np.inf) if cfg["act"] else np.full(len(cl), -np.inf)
        trail = np.concatenate([[-np.inf], trail[:-1]])          # a trail set by a second applies from the next one
        stop_line = np.maximum(stop, trail)
        hit_stop = okk & (lo <= stop_line)
        hit_tgt = okk & (hi >= tgt)
        t_end = min(len(cl) - 1, cfg["time"] * 60)
        i_stop = int(np.argmax(hit_stop)) if hit_stop.any() else 10 ** 9
        i_tgt = int(np.argmax(hit_tgt)) if hit_tgt.any() else 10 ** 9
        i = min(i_stop, i_tgt, t_end)
        if i == i_stop:
            px = float(stop_line[i])
        elif i == i_tgt:
            px = float(tgt)
        else:
            j = i
            while j > 0 and not okk[j]:
                j -= 1
            px = float(cl[j]) if okk[j] else ask
        realized += (px - ask) * LOT - M.charges(ask, px, LOT) - stress
        n += 1
        free = s0 + 1 + i + 1
        if loss + realized < 0.05 * loss:
            break
    return realized, n


ENTRY = ([{"kind": "ORB", "n": n, "buf": bf, "hold": h} for n in (5, 15, 30) for bf in (0.0, 0.5) for h in (10, 30)] +
         [{"kind": "MOMO", "k": k, "z": z} for k in (2, 4, 10) for z in (1.5, 2.5, 3.5)] +
         [{"kind": "TWAPX", "buf": bf} for bf in (0.0, 1.0, 2.0)] +
         [{"kind": "FADE", "z": z} for z in (3.0, 5.0)])
EXITS = [{"stop": s, "target": t, "act": a, "give": 0.5, "time": tm} for s in (0.10, 0.20) for t in (0.15, 0.30, 0.60)
         for a in (0.0, 0.10, 0.20) for tm in (5, 15, 45)]


def evaluate(days, cfg, stress, gate):
    rows = []
    for D in days:
        if gate == "gold_free" and not D.gold_free():
            continue
        if gate == "gold_empty" and D.gold_traded:
            continue
        x, n = play_day(D, cfg, stress)
        rows.append((D.day, x, n))
    return rows


def summary(rows):
    nets = [x for _d, x, _n in rows]
    return {"net": round(sum(nets)), "trades": sum(n for *_x, n in rows), "days": len(rows), "won": sum(x > 0 for x in nets),
            "lost": sum(x < 0 for x in nets), "none": sum(x == 0 for x in nets), "worst": round(min(nets)) if nets else 0}


if __name__ == "__main__":
    stress = float(sys.argv[1]) if len(sys.argv) > 1 else 100.0
    raw = SD.load()["days"]
    gd = {r["day"]: r for r in json.loads((HERE.parent / "2026-11-13-sn76" / "_local" / "days.json").read_text(encoding="utf-8"))}
    adx = json.loads((HERE.parent / "2026-11-12-sn06" / "_local" / "daily.json").read_text(encoding="utf-8"))
    days = [Day(d, r, bool(gd.get(d, {}).get("trades")), (adx.get(d) or {}).get("adx")) for d, r in sorted(raw.items())
            if "PE" in r["series"] and "CE" in r["series"]]
    A = [D for D in days if D.day < SPLIT]
    B = [D for D in days if D.day >= SPLIT]
    print("days", len(days), "choose", len(A), "score", len(B), "gold-free (rule)", sum(D.gold_free() for D in days),
          "gold traded", sum(D.gold_traded for D in days), "expiry", sum(D.expiry for D in days), flush=True)
    rng = random.Random(78)
    nulls = [{"kind": "RANDOM", "p": p, "seed": rng.randrange(1, 10 ** 6)} for p in (0.01, 0.02, 0.05) for _ in range(9)]
    out = {"stress": stress, "split": SPLIT}
    for gate in ("gold_free", "all"):
        for kind, fams in (("real", ENTRY), ("null", nulls)):
            best, best_cfg, pos = None, None, 0
            for fam, ex, mt in itertools.product(fams, EXITS, (1, 3)):
                cfg = {"fam": fam, **ex, "max_trades": mt}
                s = summary(evaluate(A, cfg, stress, gate))
                if s["trades"] < 15:
                    continue
                pos += s["net"] > 0
                if best is None or s["net"] > best["net"]:
                    best, best_cfg = s, cfg
            sb = summary(evaluate(B, best_cfg, stress, gate))
            sb_empty = summary(evaluate(B, best_cfg, stress, "gold_empty"))
            out[f"{gate}|{kind}"] = {"pick": best_cfg, "choose_half": best, "score_half": sb, "score_half_gold_empty_days": sb_empty,
                                     "share_positive_on_choose_half": pos}
            print(f"{gate:9s} {kind:4s} pick {json.dumps(best_cfg)[:150]}", flush=True)
            print(f"           Apr-May {best} -> Jun-Jul {sb} | on Gold's empty Jun-Jul days {sb_empty} | configs positive Apr-May {pos}", flush=True)
    (HERE / f"results-{int(stress)}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
