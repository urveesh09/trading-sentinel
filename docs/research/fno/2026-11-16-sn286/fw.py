"""SN289 qualification and the frozen forward scorers SN291 (+ SN294 / SN295 diagnostics, SN296 exit challenger) and
SN293, on one recorded NIFTY session (PLAN.md; rules fixed before the forward window). Research only: reads a local copy
of a tick-recorder day folder; places nothing; no runtime module.

Session rules fixed here, before the window starts (Nov 17):
  - the front future = the NIFTY future with the nearest expiry AFTER the session date (never the expiring one);
  - the front weekly = the nearest NIFTY option expiry after the session date; a session that IS a NIFTY option
    expiry day is skipped (expiry mornings are SN297, deferred);
  - decisions 09:30-14:30 IST; one open position per arm; Zerodha charges + Rs 205 (and Rs 400) per lot;
  - a fill is the first option packet received 0.5-2.5 s after the decision, at its best ask, with best-ask quantity
    >= one lot (else "missed"); an exit is at the best bid of the first packet at or after the planned time; the
    Rs 3,000 stop is checked on every option packet at its best bid."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-16-sn251"))
import gl  # noqa: E402
import tk  # noqa: E402

W0, W1 = 15 * 60, 5 * 3600 + 15 * 60          # 09:30 .. 14:30 in seconds after 09:15
STOP = 3000.0
LAT0, LAT1 = 0.5, 2.5


def charges(buy, sell, qty):
    return gl.wk.charges(buy, sell, qty, "NFO")


class Day:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.day = self.folder.name[-10:]
        self.meta, self.D = tk.load_day(folder)
        m = self.meta
        self.idx = next((t for t, x in m.items() if x["tradingsymbol"] == "NIFTY 50"), None)
        futs = sorted((x["expiry"], t) for t, x in m.items() if x["type"] == "FUT" and x["underlying"] == "NIFTY" and x["expiry"] > self.day)
        self.fut = futs[0][1] if futs else None
        sfuts = sorted((x["expiry"], t) for t, x in m.items() if x["type"] == "FUT" and x["underlying"] == "SENSEX" and x["expiry"] > self.day)
        self.sfut = sfuts[0][1] if sfuts else None
        exps = sorted({x["expiry"] for x in m.values() if x["underlying"] == "NIFTY" and x["type"] in ("CE", "PE")})
        self.expiry_day = self.day in exps
        later = [e for e in exps if e > self.day]
        self.front = later[0] if later else None
        self.second = later[1] if len(later) > 1 else None
        self.opt = {(x["expiry"], int(round(x["strike"])), x["type"]): t for t, x in m.items() if x["type"] in ("CE", "PE") and x["underlying"] == "NIFTY"}
        self.lot = next((int(x["lot_size"]) for x in m.values() if x["underlying"] == "NIFTY" and x["type"] in ("CE", "PE")), 65)

    def fmid(self, tok):
        d = self.D[tok]
        b, a = d["bid"], d["ask"]
        return np.where((b > 0) & (a > 0), (b + a) / 2.0, d["ltp"])

    def atm(self, t):
        v, _age = tk.asof(self.D[self.idx], t, "ltp")
        return None if v is None else int(round(v / 50.0) * 50)


# ---- SN289 -----------------------------------------------------------------------------------------------------
def qualify(day: Day):
    out = {"day": day.day, "tokens": len(day.D), "expiry_day": day.expiry_day, "front": day.front, "future": day.meta.get(day.fut, {}).get("tradingsymbol")}
    if day.fut is None or day.fut not in day.D or day.idx not in day.D:
        out["ok"] = False
        out["why"] = "no future or index"
        return out
    ft = day.D[day.fut]["t"]
    inwin = ft[(ft >= W0) & (ft <= W1)]
    mins = np.unique((inwin // 60).astype(int))
    gaps = np.diff(np.concatenate([[W0], inwin, [W1]]))
    out["future_minute_coverage"] = round(len(mins) / ((W1 - W0) / 60), 3)
    out["future_max_gap_s"] = round(float(gaps.max()), 1)
    cov = []
    for mnt in range(W0 // 60, W1 // 60):
        K = day.atm(mnt * 60 + 30)
        ok = 0
        for o in ("CE", "PE"):
            tok = day.opt.get((day.front, K, o)) if K else None
            if tok in day.D:
                tt = day.D[tok]["t"]
                ok += bool(np.any((tt >= mnt * 60) & (tt < mnt * 60 + 60)))
        cov.append(ok == 2)
    out["atm_minute_coverage"] = round(float(np.mean(cov)), 3)
    ev = (day.folder / "events.jsonl").read_text(encoding="utf-8").splitlines() if (day.folder / "events.jsonl").exists() else []
    out["events"] = [e for e in ev if '"down"' in e or '"refused"' in e or '"capped"' in e]
    out["ok"] = bool(not day.expiry_day and out["future_minute_coverage"] >= 0.95 and out["future_max_gap_s"] <= 60
                     and out["atm_minute_coverage"] >= 0.95)
    return out


# ---- trade mechanics --------------------------------------------------------------------------------------------
def fill(day, tok, td):
    d = day.D.get(tok)
    if d is None:
        return None
    k = tk.first_after(d, td + LAT0)
    if k is None or d["t"][k] > td + LAT1 or d["ask"][k] <= 0 or d["aq"][k] < day.lot:
        return None
    return k


def hold(day, tok, k, t_exit, stress, exit_rule=None):
    """From fill index k: (net, exit time, reason); exit_rule(t, net) -> True exits at that packet."""
    d = day.D[tok]
    a = d["ask"][k]
    q = day.lot
    j = k + 1
    while j < len(d["t"]):
        b = d["bid"][j]
        if b > 0:
            net = (b - a) * q - charges(a, b, q) - stress
            if net <= -STOP:
                return net, d["t"][j], "stop"
            if exit_rule is not None and exit_rule(d["t"][j], net):
                return net, d["t"][j], "signal"
            if t_exit is not None and d["t"][j] >= t_exit:
                return net, d["t"][j], "time"
        j += 1
    b = d["bid"][len(d["t"]) - 1]
    return ((b - a) * q - charges(a, b, q) - stress if b > 0 else None), d["t"][-1], "end"


# ---- SN291 + SN294 / SN295 / SN296 --------------------------------------------------------------------------------
def sn291(day: Day):
    f = day.D[day.fut]
    fm = day.fmid(day.fut)
    imb = (f["b5"] - f["a5"]) / np.maximum(f["b5"] + f["a5"], 1.0)
    sf = day.D.get(day.sfut)
    sfm = day.fmid(day.sfut) if sf is not None else None
    imp, last = [], -1e9
    for k in range(len(f["t"])):
        t = f["t"][k]
        if t < W0 or t > W1 or t - last < 120:
            continue
        k0 = np.searchsorted(f["t"], t - 30, side="right") - 1
        if k0 < 0:
            continue
        dlt = fm[k] - fm[k0]
        if abs(dlt) >= 0.0006 * fm[k0]:
            imp.append((t, 1 if dlt > 0 else -1, abs(dlt)))
            last = t
    res = {"impulses": len(imp), "candidate": [], "control": [], "challenger": [], "next_expiry": [], "sensex_confirmed": []}
    busy = {"candidate": -1, "control": -1}
    for t, s, mag in imp:
        td = t + 5
        win = (f["t"] >= t - 10) & (f["t"] <= t)
        mi = float(imb[win].mean()) if win.any() else 0.0
        kd = np.searchsorted(f["t"], td, side="right") - 1
        held = s * (fm[kd] - fm[np.searchsorted(f["t"], t, side="right") - 1]) >= -0.5 * mag
        cond = (np.sign(mi) == s) and abs(mi) >= 0.20 and held
        K = day.atm(td)
        tok = day.opt.get((day.front, K, "CE" if s > 0 else "PE")) if K else None
        for arm in ("candidate", "control"):
            if arm == "candidate" and not cond:
                continue
            if td < busy[arm]:
                continue
            k = fill(day, tok, td) if tok is not None else None
            if k is None:
                res[arm].append({"t": round(t, 1), "s": s, "missed": True})
                continue
            prem = day.D[tok]["ask"][k] * day.lot
            if prem > 15000.0:
                res[arm].append({"t": round(t, 1), "s": s, "missed": True, "why": "premium"})
                continue
            tf = day.D[tok]["t"][k]
            n205, tx, why = hold(day, tok, k, tf + 60, 205.0)
            n400, _tx, _w = hold(day, tok, k, tf + 60, 400.0)
            busy[arm] = tx
            row = {"t": round(t, 1), "s": s, "imb": round(mi, 3), "net205": n205, "net400": n400, "why": why, "latency": round(tf - td, 3)}
            res[arm].append(row)
            if arm == "candidate":
                # SN296: exit when the supporting imbalance turns after a positive net mark (cap 300 s), identical fill
                seen_pos = {"v": False}

                def rule(tt, net, s=s):
                    if net > 0:
                        seen_pos["v"] = True
                    if not seen_pos["v"]:
                        return False
                    w = (f["t"] >= tt - 10) & (f["t"] <= tt)
                    return w.any() and np.sign(float(imb[w].mean())) == -s
                c205, ctx, cwhy = hold(day, tok, k, tf + 300, 205.0, rule)
                res["challenger"].append({"t": round(t, 1), "fixed205": n205, "challenger205": c205, "why": cwhy, "hold_s": round(ctx - tf, 1)})
                # SN294: the next-expiry ATM option, identical timing
                tok2 = day.opt.get((day.second, K, "CE" if s > 0 else "PE")) if day.second else None
                k2 = fill(day, tok2, td) if tok2 is not None else None
                if k2 is not None:
                    tf2 = day.D[tok2]["t"][k2]
                    res["next_expiry"].append({"t": round(t, 1), "front205": n205, "next205": hold(day, tok2, k2, tf2 + 60, 205.0)[0]})
                # SN295: SENSEX future confirmation within +2 s
                if sfm is not None:
                    a0 = np.searchsorted(sf["t"], t - 30, side="right") - 1
                    a1 = np.searchsorted(sf["t"], t + 2, side="right") - 1
                    conf = a0 >= 0 and a1 >= 0 and np.sign(sfm[a1] - sfm[a0]) == s and abs(sfm[a1] - sfm[a0]) >= 0.0004 * sfm[a0]
                    res["sensex_confirmed"].append({"t": round(t, 1), "confirmed": bool(conf), "net205": n205})
    return res


# ---- SN293 ------------------------------------------------------------------------------------------------------
def grid(day, tok, field_fn, T):
    d = day.D.get(tok)
    if d is None or not len(d["t"]):
        return None, None
    k = np.searchsorted(d["t"], T, side="right") - 1
    vals = field_fn(d)
    g = np.where(k >= 0, vals[np.maximum(k, 0)], np.nan)
    age = np.where(k >= 0, T - d["t"][np.maximum(k, 0)], np.inf)
    return g, age


def sn293(day: Day):
    T = np.arange(0, 22500, 1.0)
    fg, _ = grid(day, day.fut, lambda d: np.where((d["bid"] > 0) & (d["ask"] > 0), (d["bid"] + d["ask"]) / 2, d["ltp"]), T)
    ig, _ = grid(day, day.idx, lambda d: d["ltp"], T)
    mid = lambda d: np.where((d["bid"] > 0) & (d["ask"] > 0), (d["bid"] + d["ask"]) / 2, np.nan)  # noqa: E731
    cache = {}

    def og(tok):
        if tok not in cache:
            cache[tok] = grid(day, tok, mid, T)
        return cache[tok]
    res = {"triggers": 0, "candidate": [], "control": []}
    busy, last = -1.0, -1e9
    for t in range(W0, W1):
        if t - last < 30 or t < busy or np.isnan(fg[t]) or np.isnan(fg[t - 5]):
            continue
        dF = fg[t] - fg[t - 5]
        if abs(dF) < 0.0004 * fg[t - 5]:
            continue
        last = t
        res["triggers"] += 1
        s = 1 if dF > 0 else -1
        K0 = int(round(ig[t] / 50.0) * 50)
        info = []
        for jj in range(-3, 4):
            tok = day.opt.get((day.front, K0 + 50 * jj, "CE" if s > 0 else "PE"))
            if tok is None:
                continue
            g, age = og(tok)
            if g is None:
                continue
            xs = np.arange(t - 600, t - 5, 5)
            dx = fg[xs + 5] - fg[xs]
            dy = g[xs + 5] - g[xs]
            ok = ~(np.isnan(dx) | np.isnan(dy))
            if ok.sum() < 30 or np.var(dx[ok]) == 0:
                continue
            beta = float(np.cov(dx[ok], dy[ok])[0, 1] / np.var(dx[ok], ddof=1))
            exp_ = beta * dF
            obs = g[t] - g[t - 5]
            if np.isnan(obs) or exp_ <= 0:
                continue
            info.append({"tok": tok, "ratio": obs / exp_, "exp": exp_, "obs": obs, "age": float(age[t])})
        lag = [x for x in info if x["ratio"] <= 0.4 and x["age"] <= 1.0]
        moved = [x for x in info if x["ratio"] >= 0.7]
        if not lag or len([x for x in moved if x not in lag]) < 2:
            continue
        tgt = min(lag, key=lambda x: x["ratio"])
        d = day.D[tgt["tok"]]
        kk = np.searchsorted(d["t"], t, side="right") - 1
        if kk < 0 or d["ask"][kk] <= 0 or d["bid"][kk] <= 0:
            continue
        room = (tgt["exp"] - tgt["obs"]) * day.lot - (d["ask"][kk] - d["bid"][kk]) * day.lot - charges(d["ask"][kk], d["bid"][kk], day.lot) - 205.0
        if room <= 0:
            continue
        ctl = max(moved, key=lambda x: x["ratio"])
        for arm, x in (("candidate", tgt), ("control", ctl)):
            k = fill(day, x["tok"], float(t))
            if k is None:
                res[arm].append({"t": t, "missed": True})
                continue
            tf = day.D[x["tok"]]["t"][k]
            n205, tx, why = hold(day, x["tok"], k, tf + 15, 205.0)
            n400 = hold(day, x["tok"], k, tf + 15, 400.0)[0]
            res[arm].append({"t": t, "ratio": round(x["ratio"], 3), "net205": n205, "net400": n400, "why": why})
            if arm == "candidate":
                busy = tx
    return res


# ---- SN298: the corrected holiday shadow (research ledger) ------------------------------------------------------------
# Pre-holiday sessions under SN286's rule from the engine's 2026 NSE list: Nov 23 (before Nov 24) is NIFTY's shifted
# weekly expiry, so it is excluded; Dec 24 (before Dec 25) qualifies. Later dates are added only from a published NSE
# calendar, before the date.
PRE_HOLIDAY = {"2026-12-24"}


def sn298(day: Day):
    if day.day not in PRE_HOLIDAY or day.expiry_day:
        return None
    t920, t1510 = 5 * 60, 355 * 60
    K = day.atm(t920)
    tok = day.opt.get((day.front, K - 50, "CE")) if K else None
    k = fill(day, tok, float(t920)) if tok is not None else None
    if k is None:
        return {"day": day.day, "missed": True}
    n205, tx, why = hold(day, tok, k, t1510, 205.0)
    return {"day": day.day, "net205": n205, "exit_s": round(tx, 1), "why": why}


def run(folder):
    day = Day(folder)
    q = qualify(day)
    out = {"qualify": q}
    if q["ok"]:
        out["SN291"] = sn291(day)
        out["SN293"] = sn293(day)
    out["SN298"] = sn298(day)
    return out
