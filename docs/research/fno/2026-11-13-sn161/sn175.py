"""SN175 - the 1-second impulse with a learned exit (PLAN.md). Sealed 1-second archives (Apr 6 - Nov 12 2026, both
copies; SN157's prep). Entry: a fresh 60-second index move >= 2 sigma of the 60-second moves of the last 30 minutes
(10:00-15:00, opening-ATM strike within 100 points) buys that side's opening-ATM option, one lot at the house ask.
States every 10 s up to 10 minutes: the trade's net now (bid from a print within 10 s), its peak, seconds held, the
index's 10/30/60-second moves in sigma units, the time of day, the side. Label: is the net 60 s later more than Rs 100
higher? Days: TEST = the latest 5% of 1-second days (SN181); development = the rest, split in time: the first 75% train,
the last 25% choose phi in {0.3, 0.4, 0.5} and compare against fixed holds of 60 s and 180 s (SN157's). Final model on
all development writes TEST predictions to _local for SN181. Every entry is scored on its own (not one at a time)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn151"))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn131"))
import pml  # noqa: E402
import sn135  # noqa: E402
import sn157  # noqa: E402

M = sn157.M
PHIS = (0.3, 0.4, 0.5)
CAP = 600
PARAMS = {"min_data_in_leaf": 200}


def load_days():
    A = sn135.SD.load()["days"]
    sn135.SD.CACHE = HERE.parent / "2026-11-13-sn78" / "_local" / "seconds-1112.pkl"
    B = {d: v for d, v in sn135.SD.load()["days"].items() if d > "2026-07-27"}
    out = {}
    for d in sorted(set(A) | set(B)):
        p = sn157.prep(d, A.get(d) or B.get(d))
        if p is not None:
            out[d] = p
    return out


def entries(p, k=2.0):
    ic, K = p["ic"], p["K"]
    out, prev = [], False
    for s in range(sn157.S10, sn157.S15 + 1, 10):
        m60 = ic[s] - ic[s - 60]
        hist = ic[s - 1800: s: 10] - ic[s - 1860: s - 60: 10]
        sd = float(np.nanstd(hist)) if len(hist) > 20 else np.nan
        hit = sd > 0 and abs(m60) >= k * sd
        if hit and not prev and abs(ic[s] - K) <= 100:
            out.append((s, 1 if m60 > 0 else -1, sd))
        prev = hit
    return out


def walk(p, s, d, sd):
    o = "CE" if d > 0 else "PE"
    px = p["oc"][o][s]
    if np.isnan(px):
        return None
    ask = M.ask_of(float(px))
    ic, lp = p["ic"], p["lp"][o]

    def net(t):
        if t >= len(ic) or t - lp[t] > 10:
            return None
        b = M.bid_of(float(p["oc"][o][lp[t]]))
        return (b - ask) * M.LOT - M.charges(ask, b, M.LOT) - 205.0
    seq, peak = [], -1e18
    for t in range(s + 10, s + CAP + 1, 10):
        v = net(t)
        if v is None:
            continue
        peak = max(peak, v)
        f = net(t + 60)
        y = None if f is None else int(f > v + 100.0)
        r = [(ic[t] - ic[t - w]) / sd * d for w in (10, 30, 60)]
        seq.append((t, v, y, [v, peak, t - s, *r, t / 3600.0, d]))
    fixed = {h: net(s + h) for h in (60, 180)}
    return {"s": s, "d": d, "seq": seq, "fixed": fixed}


def learned(e, P, phi):
    for (t, v, _y, _x), pr in zip(e["seq"], P):
        if pr == pr and pr < phi:
            return v
    return e["seq"][-1][1] if e["seq"] else None


if __name__ == "__main__":
    out_path = HERE / "results-sn175.json"
    if out_path.exists():
        raise SystemExit("SN175 is scored once")
    P_ = load_days()
    days = sorted(P_)
    n_test = round(len(days) * 0.05)
    dev_days, test_days = days[:-n_test], days[-n_test:]
    cut = dev_days[int(len(dev_days) * 0.75)]
    E = []
    for d in days:
        for s, side, sd in entries(P_[d]):
            w = walk(P_[d], s, side, sd)
            if w is not None and w["seq"]:
                w["day"] = d
                E.append(w)
    rows = [(i, k) for i, e in enumerate(E) for k in range(len(e["seq"]))]
    X = np.array([E[i]["seq"][k][3] for i, k in rows], dtype=np.float32)
    Y = np.array([E[i]["seq"][k][2] if E[i]["seq"][k][2] is not None else -1 for i, k in rows])
    rday = np.array([E[i]["day"] for i, k in rows])
    ok = Y >= 0
    tr = ok & (rday < cut)
    m = pml.fit(X[tr], Y[tr] == 1, PARAMS)
    va = (rday >= cut) & (rday < test_days[0])
    Pva = np.full(len(rows), np.nan)
    Pva[va] = m.predict(X[va])
    res = {"days": len(days), "dev_days": len(dev_days), "test_days": test_days, "train_until": cut, "entries": len(E)}
    val_E = [i for i, e in enumerate(E) if cut <= e["day"] < test_days[0]]
    start = {}
    for r, (i, k) in enumerate(rows):
        start.setdefault(i, r)
    out = {}
    for h in (60, 180):
        xs = [E[i]["fixed"][h] for i in val_E if E[i]["fixed"][h] is not None]
        out[f"hold {h}s"] = {"trades": len(xs), "net": round(sum(xs)), "per_trade": round(float(np.mean(xs)), 1)}
    for phi in PHIS:
        xs = []
        for i in val_E:
            a = start[i]
            v = learned(E[i], Pva[a: a + len(E[i]["seq"])], phi)
            if v is not None:
                xs.append(v)
        out[f"learned phi {phi}"] = {"trades": len(xs), "net": round(sum(xs)), "per_trade": round(float(np.mean(xs)), 1)}
    res["validation"] = out
    best = max(PHIS, key=lambda f: out[f"learned phi {f}"]["net"])
    res["chosen_phi"] = best
    res["dev_pass"] = bool(out[f"learned phi {best}"]["net"] > 0 and out[f"learned phi {best}"]["net"] > max(out["hold 60s"]["net"], out["hold 180s"]["net"]))
    devrows = ok & (rday < test_days[0])
    mf = pml.fit(X[devrows], Y[devrows] == 1, PARAMS)
    te = rday >= test_days[0]
    Pte = np.full(len(rows), np.nan)
    if te.any():
        Pte[te] = mf.predict(X[te])
    print("SN175", json.dumps(res), flush=True)
    pml.save("sn175_test.pkl", {"E_test": [E[i] for i in range(len(E)) if E[i]["day"] >= test_days[0]],
                                "P_rows": Pte, "rows": rows, "phi": best, "test_days": test_days})
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
