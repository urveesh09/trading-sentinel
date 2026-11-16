"""SN319-SN322: the partner's chart sequence on one-second data (PLAN.md, frozen before any number).

Data: NIFTY index + the opening-ATM call and put, one second each (Breeze OHLC; a fill needs a printed second).
  dev   Apr 6 - Nov 12 2026: SN78's sealed pickles (seconds.pkl, seconds-1112.pkl), seen;
  test  Jan 16 - Apr 2 2026: SN316's sealed copy (_local/seconds-2026q1.sqlite), scored once, after SN78's picks
        are scored there once (`python sn319_322.py sn78`).
Event: the first completed 30-second index bar (aligned to :00/:30) closing outside the high / low of the 3 completed
one-minute bars before it; calls up, puts down; one event per 300 s; decisions 09:30-14:30; non-expiry sessions; only
when the archive's strike is within 100 points of the index.
Arms (one lot of 65, the house ask in / bid out on the second's close, Zerodha charges + Rs 205 / 400, exit 300 s after
entry or the Rs 3,000 stop on the second's bid low, filled at min(stop, the second's bid open)):
  A  enter at the first second after the break bar;
  B  (SN320) wait for the first completed 5-second bar that closes against the move with its extreme still outside the
     level, then the next completed 5-second bar closing with the move; enter at the next second; a 5-second bar
     reaching back inside the level first cancels; lifetime 120 s;
  C  enter 30 s after the break, no condition;
  G  (SN321) B, skipped when, over the 30 s before B's entry, common = (dC + dP) / 2 > 0 and > 0.25 x |(dC - dP) / 2|.
SN319 stores per event: held at +30 s, B's pattern, the same pattern on 10-second bars, entries at +5 / +10 / +30 / +60 s,
and B on a 5-second grid shifted by 2 s. SN322: the hindsight ceiling (best ask-to-bid round trip, entry within 120 s,
exit within 300 s of it, after costs) and whether Rs 750 net was reachable before the stop, for A and B.
Pass (test, once): B's net per event > A's and > C's at both stresses, B > 0 at both, positive without its best day,
>= 30 trades on >= 10 sessions; G the same against B."""
from __future__ import annotations

import collections
import hashlib
import json
import pickle
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path[:0] = [str(FNO / "2026-11-13-sn78"), str(FNO / "2026-11-12-sn01")]
import sn01_sim as M  # noqa: E402

N = 22500
LOT = 65
W0, W1 = 15 * 60, 5 * 3600 + 15 * 60
HOLD, LIFE, STOP = 300, 120, 3000.0
STRESSES = (205.0, 400.0)
SN78L = FNO / "2026-11-13-sn78" / "_local"
S2026 = HERE / "_local" / "seconds-2026q1.sqlite"
ADX = json.loads((FNO / "2026-11-12-sn06" / "_local" / "daily.json").read_text(encoding="utf-8"))


def ask_of(x):
    half = 0.05 if x < 50 else 0.10 if x < 100 else 0.15 if x < 150 else 0.225 if x < 200 else 0.30 if x < 300 else 0.40
    return max(M.bid_of(x) + 0.05, np.ceil((x + half) / 0.05 - 1e-9) * 0.05)


# ---- loading ------------------------------------------------------------------------------------------------------
def dev_days():
    out = {}
    for name in ("seconds.pkl", "seconds-1112.pkl"):
        with open(SN78L / name, "rb") as fh:
            out.update(pickle.load(fh)["days"])
    return out


def test_days():
    con = sqlite3.connect(f"file:{S2026.as_posix()}?mode=ro", uri=True)
    days = collections.defaultdict(lambda: {"series": {}, "meta": {}, "count": collections.Counter()})
    for kind, exp, k, opt, stamp, o, h, l, c in con.execute("SELECT kind, expiry, strike, opt, datetime, open, high, low, close FROM candles ORDER BY datetime"):
        d = stamp[:10]
        s = (int(stamp[11:13]) * 60 + int(stamp[14:16]) - 555) * 60 + int(stamp[17:19])
        if not 0 <= s < N or c is None:
            continue
        key = "INDEX" if kind == "index" else (opt, int(round(float(k))), exp[:10])
        rec = days[d]
        a = rec["series"].setdefault(key, np.full((4, N), np.nan, dtype=np.float32))
        a[:, s] = (o, h, l, c)
        rec["count"][key] += 1
    con.close()
    out = {}
    for d, rec in days.items():
        ser = {"INDEX": rec["series"].get("INDEX")}
        meta = {}
        for side in ("CE", "PE"):
            keys = [k for k in rec["series"] if k != "INDEX" and k[0] == side]
            if keys:
                best = max(keys, key=lambda k: rec["count"][k])
                ser[side] = rec["series"][best]
                meta[side] = (float(best[1]), best[2])
        if ser["INDEX"] is not None and "CE" in ser and "PE" in ser:
            out[d] = {"series": ser, "meta": meta}
    return out


def carry(x):
    out = x.astype(float).copy()
    last = np.nan
    for k in range(len(out)):
        if np.isnan(out[k]):
            out[k] = last
        else:
            last = out[k]
    ok = np.flatnonzero(~np.isnan(out))
    if len(ok):
        out[: ok[0]] = out[ok[0]]
    return out


class Day:
    def __init__(self, day, rec):
        self.day = day
        s = rec["series"]
        ix = s["INDEX"].astype(float)
        self.c = carry(ix[3])
        self.h = np.where(np.isnan(ix[1]), self.c, ix[1])
        self.l = np.where(np.isnan(ix[2]), self.c, ix[2])
        self.strike = {k: rec["meta"][k][0] for k in ("CE", "PE")}
        self.expiry = rec["meta"]["CE"][1][:10] == day
        self.opt = {}
        for side in ("CE", "PE"):
            a = s[side].astype(float)
            self.opt[side] = {"o": a[0], "l": a[2], "c": a[3], "ok": np.isfinite(a[3]), "cc": carry(a[3])}
        self.mh = self.h[: (N // 60) * 60].reshape(-1, 60).max(1)
        self.ml = self.l[: (N // 60) * 60].reshape(-1, 60).min(1)
        adx = (ADX.get(day) or {}).get("adx")
        self.gold_free = adx is not None and adx < 30

    def level(self, start):
        m0 = start // 60
        if m0 < 3:
            return None, None
        return float(self.mh[m0 - 3:m0].max()), float(self.ml[m0 - 3:m0].min())

    def bars(self, width, offset=0):
        nb = (N - offset) // width
        idx = np.arange(nb) * width + offset
        c = self.c[idx + width - 1]
        o = self.c[np.maximum(idx - 1, 0)]
        h = self.h[offset: offset + nb * width].reshape(nb, width).max(1)
        l = self.l[offset: offset + nb * width].reshape(nb, width).min(1)
        return idx, o, h, l, c


# ---- the events ---------------------------------------------------------------------------------------------------
def events(D):
    idx, _o, _h, _l, c = D.bars(30)
    out, last, prev_out = [], -10 ** 9, 0
    for b in range(len(idx)):
        start = int(idx[b])
        te = start + 29
        hi, lo = D.level(start)
        if hi is None:
            continue
        s = 1 if c[b] > hi else (-1 if c[b] < lo else 0)
        fresh = s != 0 and s != prev_out
        prev_out = s
        if not fresh or te < W0 or te > W1 or te - last < 300:
            continue
        side = "CE" if s > 0 else "PE"
        if abs(D.c[te] - D.strike[side]) > 100:
            continue
        out.append({"te": te, "s": s, "lvl": hi if s > 0 else lo, "side": side})
        last = te
    return out


def pattern(D, e, width, offset=0):
    """The entry second of B's sequence on `width`-second bars (or None), and whether the break failed first."""
    s, lvl, te = e["s"], e["lvl"], e["te"]
    q0 = (te + 1 - offset + width - 1) // width
    prev = None
    q = q0
    while True:
        a = q * width + offset
        end = a + width - 1
        if end + 1 > te + LIFE or end >= N:
            return None, False
        c = D.c[end]
        ext_back = D.l[a:end + 1].min() <= lvl if s > 0 else D.h[a:end + 1].max() >= lvl
        if ext_back:
            return None, True
        p = D.c[a - 1] if prev is None else prev
        if s * (c - p) < 0:                          # a pullback bar, still outside the level
            a2, end2 = end + 1, end + width
            if end2 >= N or end2 + 1 > te + LIFE:
                return None, False
            c2 = D.c[end2]
            if (D.l[a2:end2 + 1].min() <= lvl) if s > 0 else (D.h[a2:end2 + 1].max() >= lvl):
                return None, True
            if s * (c2 - c) > 0:
                return end2 + 1, False
        prev = c
        q += 1


def trade(D, side, s0, stress):
    o = D.opt[side]
    k = s0
    while k < min(N, s0 + 6) and not o["ok"][k]:
        k += 1
    if k >= min(N, s0 + 6):
        return None
    ask = ask_of(float(o["c"][k]))
    stop = ask - (STOP - M.charges(ask, ask, LOT) - stress) / LOT
    end = min(N - 1, k + HOLD)
    px = None
    for j in range(k + 1, end + 1):
        if o["ok"][j] and M.bid_of(float(o["l"][j])) <= stop:
            px = min(stop, M.bid_of(float(o["o"][j])))
            break
    if px is None:
        j = end
        while j > k and not o["ok"][j]:
            j -= 1
        px = M.bid_of(float(o["c"][j])) if o["ok"][j] else ask
    return (px - ask) * LOT - M.charges(ask, px, LOT) - stress


def reach(D, side, s0, stress, target=750.0):
    o = D.opt[side]
    if not o["ok"][min(s0, N - 1)]:
        return None
    ask = ask_of(float(o["c"][s0]))
    stop = ask - (STOP - M.charges(ask, ask, LOT) - stress) / LOT
    tgt = ask + (target + M.charges(ask, ask, LOT) + stress) / LOT
    for j in range(s0 + 1, min(N, s0 + HOLD + 1)):
        if o["ok"][j]:
            if M.bid_of(float(o["l"][j])) <= stop:
                return False
            if M.bid_of(float(o["c"][j])) >= tgt:
                return True
    return False


def ceiling(D, side, te, stress):
    o = D.opt[side]
    bidc = np.where(o["ok"], [M.bid_of(float(x)) if np.isfinite(x) else -np.inf for x in o["c"]], -np.inf) if "bidc" not in o else o["bidc"]
    o["bidc"] = bidc
    best = -np.inf
    for e in range(te + 1, min(N, te + LIFE + 1), 5):
        if not o["ok"][e]:
            continue
        ask = ask_of(float(o["c"][e]))
        mx = float(np.max(bidc[e + 1: min(N, e + HOLD + 1)])) if e + 1 < N else -np.inf
        if mx > -np.inf:
            best = max(best, (mx - ask) * LOT - M.charges(ask, mx, LOT) - stress)
    return None if best == -np.inf else best


def gate(D, s0):
    if s0 < 31:
        return False
    dC = D.opt["CE"]["cc"][s0 - 1] - D.opt["CE"]["cc"][s0 - 31]
    dP = D.opt["PE"]["cc"][s0 - 1] - D.opt["PE"]["cc"][s0 - 31]
    common, direc = (dC + dP) / 2.0, (dC - dP) / 2.0
    return bool(common > 0 and common > 0.25 * abs(direc))


def study_day(D):
    rows = []
    for e in events(D):
        te, side = e["te"], e["side"]
        sb, failed = pattern(D, e, 5)
        s10, _f10 = pattern(D, e, 10)
        sb2, _f2 = pattern(D, e, 5, offset=2)
        r = {"day": D.day, "te": te, "s": e["s"], "gold_free": D.gold_free, "b_fired": sb is not None, "b_failed_break": failed,
             "b_delay": None if sb is None else sb - te, "ten_fired": s10 is not None,
             "held30": bool(e["s"] * (D.c[min(N - 1, te + 30)] - e["lvl"]) > 0)}
        for st in STRESSES:
            k = int(st)
            r[f"A{k}"] = trade(D, side, te + 1, st)
            r[f"C{k}"] = trade(D, side, te + 31, st)
            r[f"B{k}"] = trade(D, side, sb, st) if sb is not None else None
            r[f"G{k}"] = None if sb is None or gate(D, sb) else r[f"B{k}"]
            r[f"B2_{k}"] = trade(D, side, sb2, st) if sb2 is not None else None
            r[f"T10_{k}"] = trade(D, side, s10, st) if s10 is not None else None
            for lag in (5, 10, 30, 60):
                r[f"at{lag}_{k}"] = trade(D, side, te + 1 + lag, st)
        r["gate_skip"] = None if sb is None else gate(D, sb)
        r["ceiling205"] = ceiling(D, side, te, 205.0)
        r["reach750_A"] = reach(D, side, te + 1, 205.0)
        r["reach750_B"] = reach(D, side, sb, 205.0) if sb is not None else None
        rows.append(r)
    return rows


# ---- scoring ----------------------------------------------------------------------------------------------------
def arm(rows, key):
    per = collections.defaultdict(float)
    n = 0
    for r in rows:
        v = r.get(key)
        per[r["day"]] += v or 0.0
        n += v is not None
    tot = sum(per.values())
    return {"net": round(tot), "per_event": round(tot / len(rows), 1) if rows else None, "trades": n,
            "sessions": sum(1 for r_d in {r["day"] for r in rows if r.get(key) is not None}), "without_best_day": round(tot - max(per.values(), default=0.0)),
            "worst_day": round(min(per.values(), default=0.0))}


def summary(rows):
    out = {"events": len(rows), "sessions": len({r["day"] for r in rows}), "b_fired": sum(r["b_fired"] for r in rows),
           "b_failed_break": sum(r["b_failed_break"] for r in rows),
           "runaways": sum(1 for r in rows if not r["b_fired"] and not r["b_failed_break"] and (r["A205"] or 0) > 0),
           "runaway_A_net": round(sum(r["A205"] or 0 for r in rows if not r["b_fired"] and not r["b_failed_break"] and (r["A205"] or 0) > 0)),
           "b_delay_median": float(np.median([r["b_delay"] for r in rows if r["b_delay"] is not None])) if any(r["b_fired"] for r in rows) else None}
    for st in STRESSES:
        k = int(st)
        out[f"@{k}"] = {name: arm(rows, f"{name}{k}" if name in "ABCG" else f"{name}{k}") for name in ("A", "B", "C", "G")}
        out[f"@{k}"]["B shifted 2 s"] = arm(rows, f"B2_{k}")
        out[f"@{k}"]["ten-second pattern"] = arm(rows, f"T10_{k}")
        for lag in (5, 10, 30, 60):
            out[f"@{k}"][f"enter +{lag}s"] = arm(rows, f"at{lag}_{k}")
        held = [r for r in rows if r["held30"]]
        out[f"@{k}"]["A when held at +30 s"] = arm(held, f"A{k}")
        out[f"@{k}"]["A when not held"] = arm([r for r in rows if not r["held30"]], f"A{k}")
    ce = [r["ceiling205"] for r in rows if r["ceiling205"] is not None]
    out["SN322"] = {"ceiling_mean": round(float(np.mean(ce))) if ce else None, "ceiling_share_ge_750": round(float(np.mean([x >= 750 for x in ce])), 3) if ce else None,
                    "reach750_A": round(float(np.mean([bool(r["reach750_A"]) for r in rows if r["reach750_A"] is not None])), 3),
                    "reach750_B": round(float(np.mean([bool(r["reach750_B"]) for r in rows if r["reach750_B"] is not None])), 3) if any(r["b_fired"] for r in rows) else None}
    return out


def verdict(s):
    v = {}
    for name, ref in (("B", ("A", "C")), ("G", ("B",))):
        ok = True
        for st in STRESSES:
            x = s[f"@{int(st)}"]
            ok &= x[name]["net"] > 0 and all(x[name]["per_event"] > x[r]["per_event"] for r in ref)
        x = s["@205"][name]
        ok &= x["without_best_day"] > 0 and x["trades"] >= 30 and x["sessions"] >= 10
        v[name] = "PASS" if ok else "FAIL"
    return v


def run(raw):
    rows = []
    for d in sorted(raw):
        D = Day(d, raw[d])
        if D.expiry:
            continue
        rows.extend(study_day(D))
    return rows


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "sn78":
        out = HERE / "results-sn78-discharge.json"
        if out.exists():
            raise SystemExit("SN78's picks were scored on Jan-Apr 2026 once")
        import sn78 as S8
        import sn79
        raw = test_days()
        gd = {}
        days = [S8.Day(d, r, False, (ADX.get(d) or {}).get("adx")) for d, r in sorted(raw.items())]
        known = [D for D in days if D.expiry or D.adx is not None]
        res = {"days": len(days)}
        for name, cfg in (("C1", sn79.C1), ("C2", sn79.C2)):
            for stress in (100.0, 0.0):
                res[f"{name}|{int(stress)}|all"] = S8.summary(S8.evaluate(days, cfg, stress, "all"))
                res[f"{name}|{int(stress)}|gold_free"] = S8.summary(S8.evaluate(known, cfg, stress, "gold_free"))
        print(json.dumps(res, indent=1), flush=True)
        out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    elif mode == "dev":
        out = HERE / "results-sn319-322-dev.json"
        if out.exists():
            raise SystemExit("dev is reported once")
        rows = run(dev_days())
        res = {"all": summary(rows), "gold_free": summary([r for r in rows if r["gold_free"]])}
        print(json.dumps(res, indent=1)[:6000], flush=True)
        out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    elif mode == "test":
        out = HERE / "results-sn319-322-test.json"
        if out.exists():
            raise SystemExit("the test is scored once")
        if not (HERE / "results-sn78-discharge.json").exists():
            raise SystemExit("score SN78's picks on this window first: python sn319_322.py sn78")
        rows = run(test_days())
        res = {"all": summary(rows), "gold_free": summary([r for r in rows if r["gold_free"]])}
        res["verdict"] = verdict(res["all"])
        print(json.dumps(res, indent=1)[:6000], flush=True)
        out.write_text(json.dumps(res, indent=1), encoding="utf-8")
