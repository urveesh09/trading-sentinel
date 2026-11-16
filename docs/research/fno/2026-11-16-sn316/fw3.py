"""SN320 / SN321 on tick-recorder packets, and SN325's wallet test (PLAN.md, frozen before Nov 18's session is collected).

The same chart sequence as sn319_322.py, on the traded underlying: the NIFTY front future's mid, sampled each second as
of the last packet received (fw2.Day). The option is the front weekly ATM call (up) or put (down) at the event, from the
index. Execution is sn301/fw2.py's contract (fresh two-sided books, depth for one lot, 0.5-2.5 s fills, exit 300 s after
the fill, Rs 3,000 stop executed as an exit order, unresolved = the premium lost). Decisions 09:30-14:30.
Scored ONCE, on the same first 20 verified, qualified sessions as SN300a, after its verdict (session 20 = Dec 23):
  python fw3.py verdict
Pass for B (SN320): net per event > A's and C's at Rs 205 and 400; B > 0 at both; positive without its best session;
>= 30 trades on >= 10 sessions; the FLAT-session subset > 0; the one-wallet net on FLAT sessions > 0 (fwd2's contract).
G (SN321) the same against B. Unknown Gold labels, < 8 FLAT sessions or < 30 trades: INSUFFICIENT."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
import fw2  # noqa: E402
import fwd2  # noqa: E402

N = 22500
W0, W1 = 15 * 60, 5 * 3600 + 15 * 60
HOLD, LIFE = 300.0, 120
STRESSES = fw2.STRESSES


def grid(day, tok, fn):
    d = day.D.get(tok)
    T = np.arange(N, dtype=float)
    if d is None or not len(d["t"]):
        return None
    k = np.searchsorted(d["t"], T, side="right") - 1
    v = fn(d)
    g = np.where(k >= 0, v[np.maximum(k, 0)], np.nan)
    return fwd_fill(g)


def fwd_fill(x):
    out = x.copy()
    last = np.nan
    for i in range(len(out)):
        if np.isnan(out[i]):
            out[i] = last
        else:
            last = out[i]
    return out


class Under:
    def __init__(self, day):
        mid = lambda d: np.where((d["bid"] > 0) & (d["ask"] > 0), (d["bid"] + d["ask"]) / 2, d["ltp"])  # noqa: E731
        self.c = grid(day, day.fut, mid)
        self.h = self.l = self.c
        nb = N // 60
        self.mh = np.nanmax(self.c[: nb * 60].reshape(nb, 60), 1)
        self.ml = np.nanmin(self.c[: nb * 60].reshape(nb, 60), 1)

    def level(self, start):
        m0 = start // 60
        if m0 < 3:
            return None, None
        return float(np.nanmax(self.mh[m0 - 3:m0])), float(np.nanmin(self.ml[m0 - 3:m0]))


def events(U):
    out, last, prev = [], -10 ** 9, 0
    for b in range(N // 30):
        start = b * 30
        te = start + 29
        hi, lo = U.level(start)
        c = U.c[te]
        if hi is None or np.isnan(c):
            prev = 0
            continue
        s = 1 if c > hi else (-1 if c < lo else 0)
        fresh = s != 0 and s != prev
        prev = s
        if fresh and W0 <= te <= W1 and te - last >= 300:
            out.append({"te": te, "s": s, "lvl": hi if s > 0 else lo})
            last = te
    return out


def pattern(U, e, width=5):
    s, lvl, te = e["s"], e["lvl"], e["te"]
    q = (te + 1 + width - 1) // width
    prev = None
    while True:
        a, end = q * width, q * width + width - 1
        if end + 1 > te + LIFE or end >= N:
            return None
        seg = U.c[a:end + 1]
        if (np.nanmin(seg) <= lvl) if s > 0 else (np.nanmax(seg) >= lvl):
            return None
        c = U.c[end]
        p = U.c[a - 1] if prev is None else prev
        if s * (c - p) < 0:
            a2, end2 = end + 1, end + width
            if end2 >= N or end2 + 1 > te + LIFE:
                return None
            seg2 = U.c[a2:end2 + 1]
            if (np.nanmin(seg2) <= lvl) if s > 0 else (np.nanmax(seg2) >= lvl):
                return None
            if s * (U.c[end2] - c) > 0:
                return end2 + 1
        prev = c
        q += 1


def gate(day, K, t):
    ce, pe = day.opt.get((day.front, K, "CE")), day.opt.get((day.front, K, "PE"))
    if ce is None or pe is None:
        return False

    def mid_at(tok, x):
        d = day.D.get(tok)
        if d is None:
            return None
        k = int(np.searchsorted(d["t"], x, side="right")) - 1
        return None if k < 0 or d["bid"][k] <= 0 or d["ask"][k] <= 0 else (d["bid"][k] + d["ask"][k]) / 2
    a1, a0, b1, b0 = mid_at(ce, t), mid_at(ce, t - 30), mid_at(pe, t), mid_at(pe, t - 30)
    if None in (a1, a0, b1, b0):
        return False
    dC, dP = a1 - a0, b1 - b0
    common, direc = (dC + dP) / 2, (dC - dP) / 2
    return bool(common > 0 and common > 0.25 * abs(direc))


def run(folder, loaded=None):
    day = fw2.Day(folder, loaded)
    q = fw2.fw.qualify(day)
    out = {"qualify": q, "rows": []}
    if not q["ok"]:
        return out
    U = Under(day)
    for e in events(U):
        te = float(e["te"])
        K = day.atm(te)
        tok = day.opt.get((day.front, K, "CE" if e["s"] > 0 else "PE")) if K else None
        if tok is None:
            continue
        sb = pattern(U, e)
        r = {"te": te, "s": e["s"], "b_fired": sb is not None}
        for name, td in (("A", te + 1), ("C", te + 31), ("B", None if sb is None else float(sb))):
            r[name] = None if td is None else fw2.trade(day, tok, td, HOLD)
        r["G_skip"] = None if sb is None else gate(day, K, float(sb))
        out["rows"].append(r)
    return out


def arm_net(rows, name, stress, gated=False):
    key = f"net{int(stress)}"
    vals = []
    for r in rows:
        t = r.get(name if name != "G" else "B")
        if name == "G" and r.get("G_skip"):
            t = None
        vals.append(None if not t or t.get("missed") else t[key])
    return vals


def verdict():
    out = HERE / "results-sn320-forward.json"
    if out.exists():
        raise SystemExit("SN320 forward is scored once")
    if not (FNO / "2026-11-16-sn301" / "results-sn300a.json").exists():
        raise SystemExit("SN320 forward is scored after SN300a's verdict, on the same sessions")
    sa = json.loads((FNO / "2026-11-16-sn301" / "results-sn300a.json").read_text(encoding="utf-8"))
    q, labels = sa["sessions"], sa["labels"]
    per_day = {d: run(fwd2.ARCH / d)["rows"] for d in q}
    res = {"sessions": q, "events": sum(len(v) for v in per_day.values())}
    nets = {}
    for name in ("A", "B", "C", "G"):
        for st in STRESSES:
            day_net = {d: sum(x or 0.0 for x in arm_net(rows, name, st)) for d, rows in per_day.items()}
            trades = sum(1 for rows in per_day.values() for x in arm_net(rows, name, st) if x is not None)
            sess = sum(1 for rows in per_day.values() if any(x is not None for x in arm_net(rows, name, st)))
            tot = sum(day_net.values())
            flat = [d for d in q if labels[d] == "FLAT"]
            # the one-wallet contract on FLAT sessions: debit <= Gold's wallet that day - Rs 15,000; a full stop must fit the room
            wallet_net = 0.0
            for d in flat:
                rec = json.loads((fwd2.REC / f"{d}.json").read_text(encoding="utf-8"))
                w = float((rec.get("gold") or {}).get("wallet_before") or 30000.0)
                realized = 0.0
                for r in per_day[d]:
                    t = r.get(name if name != "G" else "B")
                    if (name == "G" and r.get("G_skip")) or not t or t.get("missed") or t["debit"] > w - fwd2.RESERVE or 0.2 * w + realized < fw2.STOP:
                        continue
                    realized += t[f"net{int(st)}"]
                wallet_net += realized
            nets[(name, st)] = {"net": round(tot), "per_event": round(tot / max(1, res["events"]), 1), "trades": trades, "sessions": sess,
                                "without_best": round(tot - max(day_net.values(), default=0.0)), "flat_net": round(sum(day_net[d] for d in flat)),
                                "flat_sessions": len(flat), "wallet_flat_net": round(wallet_net)}
            res[f"{name} @{int(st)}"] = nets[(name, st)]
    v = {}
    for name, ref in (("B", ("A", "C")), ("G", ("B",))):
        x = nets[(name, 205.0)]
        if any(lab == "UNKNOWN" for lab in labels.values()) or x["flat_sessions"] < 8 or x["trades"] < 30 or x["sessions"] < 10:
            v[name] = "INSUFFICIENT"
            continue
        ok = all(nets[(name, st)]["net"] > 0 and all(nets[(name, st)]["per_event"] > nets[(r, st)]["per_event"] for r in ref) for st in STRESSES)
        ok &= x["without_best"] > 0 and x["flat_net"] > 0 and x["wallet_flat_net"] > 0
        v[name] = "PASS" if ok else "FAIL"
    res["verdict"] = v
    print(json.dumps(res, indent=1), flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1] == "verdict":
        verdict()
    elif sys.argv[1] == "dev":
        r = run(Path(sys.argv[2]))
        print("qualify", r["qualify"].get("ok"), "events", len(r["rows"]), "B fired", sum(x["b_fired"] for x in r["rows"]))
