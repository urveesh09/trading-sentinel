"""SN302-SN309: the amended forward scorer (PLAN.md, frozen at 94c772cd before any recorded day is scored).

The signals and thresholds are SN291's and SN293's, copied from sn286/fw.py (d5168b0f), which stays unchanged and is still
run beside this file. What changes is the evidence a trade needs (SN302), the controls (SN304), what is recorded for
affordability (SN305), and the comparisons on the same events (SN306-SN309). Research only: reads a local, verified copy
of a tick-recorder day folder; places nothing.

SN302 execution contract:
  valid book   best bid > 0, best ask > 0, ask > bid;
  fresh book   (receipt - exchange timestamp) - the day's offset <= 2 s (offset = median on the front future);
  entry        the first valid fresh option packet received 0.5-2.5 s after the decision whose five ask levels hold one
               lot; price = the ask walk for one lot; else missed (reason kept);
  exit         planned at T: the first valid fresh packet received >= T + 0.5 s whose five bid levels hold one lot, at the
               bid walk; on time within T + 10 s, late up to T + 120 s, else unresolved (the whole premium lost);
  stop         triggered on a valid fresh packet whose best bid makes the net <= -Rs 3,000; executed as an exit order from
               that receipt (so the slippage is booked);
  clocks       a decision at t uses packets received <= t only.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pytz

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn286"))
sys.path.insert(0, str(FNO / "2026-11-16-sn251"))
import fw  # noqa: E402  (the original frozen scorer; only its constants and helpers are reused)
import tk  # noqa: E402

W0, W1 = fw.W0, fw.W1
STOP = 3000.0
FRESH = 2.0
ON_TIME, LATE = 10.0, 120.0
EXIT_LAT = 0.5
ENTRY_WIN = (0.5, 2.5)
CAP_TICKS = 0.10
STRESSES = (205.0, 400.0)
LAT_GRID = (0.5, 1.0, 2.0, 5.0)
IST = pytz.timezone("Asia/Kolkata")


def charges(buy, sell, qty):
    return fw.charges(buy, sell, qty)


# ---- loading (tk.load_day plus the exchange timestamp) -------------------------------------------------------------
def load_day(folder):
    folder = Path(folder)
    meta = tk.instruments(folder)
    acc = {}
    for ch in sorted(folder.glob("chunk-*.bin.xz")):
        for r in tk.read_chunk(ch):
            acc.setdefault(r["token"], []).append(r)
    t0 = IST.localize(dt.datetime.fromisoformat(folder.name[-10:] + "T09:15:00")).timestamp()
    out = {}
    for tok, rows in acc.items():
        rows.sort(key=lambda r: r["recv_ns"])
        ep = np.array([r["recv_ns"] / 1e9 for r in rows])
        d = {"t": ep - t0, "ltp": np.array([r["ltp"] for r in rows]),
             "lag": ep - np.array([float(r.get("exchange_ts") or 0) for r in rows])}
        if "bids" in rows[0]:
            z5 = [{"price": 0, "qty": 0}] * 5
            bp = np.array([[lv["price"] for lv in r.get("bids", z5)] for r in rows]).T
            ap = np.array([[lv["price"] for lv in r.get("asks", z5)] for r in rows]).T
            bq = np.array([[lv["qty"] for lv in r.get("bids", z5)] for r in rows], dtype=float).T
            aq = np.array([[lv["qty"] for lv in r.get("asks", z5)] for r in rows], dtype=float).T
            d.update(bids=bp, asks=ap, bidq=bq, askq=aq, bid=bp[0], ask=ap[0], bq=bq[0], aq=aq[0], b5=bq.sum(0), a5=aq.sum(0))
        out[tok] = d
    return meta, out


class Day(fw.Day):
    """fw.Day's session rules (front future, front weekly, expiry skip, option map, lot) on the amended loader."""

    def __init__(self, folder, loaded=None):
        self.folder = Path(folder)
        self.day = self.folder.name[-10:]
        self.meta, self.D = loaded if loaded is not None else load_day(folder)
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
        fl = self.D[self.fut]["lag"] if self.fut in self.D else np.array([])
        fl = fl[np.abs(fl) < 3600]
        self.offset = float(np.median(fl)) if len(fl) else 0.0
        for d in self.D.values():
            if "bid" in d:
                d["ok"] = (d["bid"] > 0) & (d["ask"] > 0) & (d["ask"] > d["bid"]) & ((d["lag"] - self.offset) <= FRESH)


# ---- SN302 mechanics ------------------------------------------------------------------------------------------------
def walk(prices, qtys, need):
    got, cost = 0.0, 0.0
    for p, q in zip(prices, qtys):
        if p <= 0 or q <= 0:
            continue
        take = min(q, need - got)
        cost += take * p
        got += take
        if got >= need:
            return cost / need
    return None


def entry(day, tok, td, lat0=ENTRY_WIN[0], width=ENTRY_WIN[1] - ENTRY_WIN[0], cap=None):
    """((k, price), 'filled') or (None, reason)."""
    d = day.D.get(tok)
    if d is None or "ok" not in d:
        return None, "no_instrument"
    k = int(np.searchsorted(d["t"], td + lat0, side="left"))
    why = "no_packet"
    while k < len(d["t"]) and d["t"][k] <= td + lat0 + width:
        if not d["ok"][k]:
            why = "invalid_or_stale"
        elif d["a5"][k] < day.lot:
            why = "no_depth"
        else:
            px = walk(d["asks"][:, k], d["askq"][:, k], day.lot)
            if cap is not None and px > cap + 1e-9:
                return None, "capped"
            return (k, px), "filled"
        k += 1
    return None, why


def exit_at(day, tok, T, lat=EXIT_LAT):
    """(price, receipt, status) for an exit order sent at T; status on_time / late / unresolved."""
    d = day.D[tok]
    k = int(np.searchsorted(d["t"], T + lat, side="left"))
    while k < len(d["t"]) and d["t"][k] <= T + LATE:
        if d["ok"][k] and d["b5"][k] >= day.lot:
            return walk(d["bids"][:, k], d["bidq"][:, k], day.lot), float(d["t"][k]), ("on_time" if d["t"][k] <= T + ON_TIME else "late")
        k += 1
    return None, None, "unresolved"


def net_of(px_in, px_out, q, stress):
    if px_out is None:
        return -px_in * q - charges(px_in, 0.0, q) - stress
    return (px_out - px_in) * q - charges(px_in, px_out, q) - stress


def hold(day, tok, k, px_in, T, stress, exit_rule=None, exit_lat=EXIT_LAT):
    """One lot from fill index k at px_in, planned exit at T: dict(net, tx, why, status)."""
    d = day.D[tok]
    q = day.lot
    j = k + 1
    why, Tsend = "time", T
    while j < len(d["t"]) and d["t"][j] < T:
        if d["ok"][j]:
            mark = (d["bid"][j] - px_in) * q - charges(px_in, d["bid"][j], q) - stress
            if mark <= -STOP:
                why, Tsend = "stop", float(d["t"][j])
                break
            if exit_rule is not None and exit_rule(float(d["t"][j]), mark):
                why, Tsend = "signal", float(d["t"][j])
                break
        j += 1
    px, tx, st = exit_at(day, tok, Tsend, exit_lat)
    return {"net": round(net_of(px_in, px, q, stress), 2), "tx": tx if tx is not None else float(d["t"][-1]) if len(d["t"]) else T,
            "why": why, "status": st, "px_out": px}


def trade(day, tok, td, hold_s, cap=None, exit_rule_fn=None, lat0=ENTRY_WIN[0], exit_lat=EXIT_LAT):
    """A complete SN302 trade decided at td: dict with fill facts and net205 / net400 (or missed)."""
    got, why = entry(day, tok, td, lat0=lat0, cap=cap)
    if got is None:
        return {"missed": True, "why": why}
    k, px = got
    d = day.D[tok]
    tf = float(d["t"][k])
    row = {"missed": False, "fill_t": round(tf, 3), "latency": round(tf - td, 3), "px_in": px, "debit": round(px * day.lot + charges(px, 0.0, day.lot), 2),
           "premium": round(px * day.lot, 2), "decision_ask": None}
    for s in STRESSES:
        rule = exit_rule_fn() if exit_rule_fn is not None else None
        h = hold(day, tok, k, px, tf + hold_s, s, rule, exit_lat)
        row[f"net{int(s)}"] = h["net"]
        if s == STRESSES[0]:
            row.update(tx=round(h["tx"], 3), why=h["why"], status=h["status"])
    return row


def asof_ask(day, tok, t):
    d = day.D.get(tok)
    if d is None or "ask" not in d:
        return None
    k = int(np.searchsorted(d["t"], t, side="right")) - 1
    return float(d["ask"][k]) if k >= 0 and d["ask"][k] > 0 else None


def with_variants(day, tok, td, hold_s, base):
    """SN306 (entry / exit latency grid) and SN307 (price cap) on one decision; base is the on-time SN302 trade."""
    if base.get("missed"):
        return base
    a0 = asof_ask(day, tok, td)
    base["decision_ask"] = a0
    base["entry_lat"] = {str(L): trade(day, tok, td, hold_s, lat0=L).get("net205") for L in LAT_GRID}
    base["exit_lat"] = {str(L): trade(day, tok, td, hold_s, exit_lat=L).get("net205") for L in LAT_GRID}
    capped = trade(day, tok, td, hold_s, cap=(a0 + CAP_TICKS) if a0 else None)
    base["capped205"] = 0.0 if capped.get("missed") else capped["net205"]
    base["capped_skip"] = bool(capped.get("missed"))
    return base


# ---- SN291 amended (signal copied from fw.sn291) ---------------------------------------------------------------------
def futures_arrays(day):
    f = day.D[day.fut]
    fm = day.fmid(day.fut)
    imb = (f["b5"] - f["a5"]) / np.maximum(f["b5"] + f["a5"], 1.0)
    # SN308: best-level order-flow imbalance per packet (Cont, Kukanov and Stoikov)
    b, a, bq, aq = f["bid"], f["ask"], f["bq"], f["aq"]
    e = np.zeros(len(b))
    e[1:] = ((b[1:] >= b[:-1]) * bq[1:] - (b[1:] <= b[:-1]) * bq[:-1] - (a[1:] <= a[:-1]) * aq[1:] + (a[1:] >= a[:-1]) * aq[:-1])
    return f, fm, imb, np.cumsum(e)


def impulses(day, f, fm):
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
            imp.append((float(t), 1 if dlt > 0 else -1, float(abs(dlt)), float(fm[k0])))
            last = t
    return imp


def sn291(day: Day):
    f, fm, imb, cofi = futures_arrays(day)
    imp = impulses(day, f, fm)
    ev = []
    for t, s, mag, start in imp:
        td = t + 5
        win = (f["t"] >= t - 10) & (f["t"] <= t)
        mi = float(imb[win].mean()) if win.any() else 0.0
        kd = np.searchsorted(f["t"], td, side="right") - 1
        kt = np.searchsorted(f["t"], t, side="right") - 1
        held = s * (fm[kd] - fm[kt]) >= -0.5 * mag
        cond = bool((np.sign(mi) == s) and abs(mi) >= 0.20 and held)
        k10 = np.searchsorted(f["t"], t - 10, side="right") - 1
        ofi = float(cofi[kt] - cofi[max(k10, 0)])
        K = day.atm(td)
        tok = day.opt.get((day.front, K, "CE" if s > 0 else "PE")) if K else None
        ev.append({"t": round(t, 1), "s": s, "mag": mag, "start": start, "td": td, "imb": round(mi, 3), "held": bool(held), "cond": cond,
                   "ofi_ok": bool(np.sign(ofi) == s and held), "tok": tok})

    def premise_rule(e):
        def make():
            def rule(tt, _net):
                w = (f["t"] >= tt - 10) & (f["t"] <= tt)
                if w.any():
                    m = float(imb[w].mean())
                    if np.sign(m) == -e["s"] and abs(m) >= 0.20:
                        return True
                k = np.searchsorted(f["t"], tt, side="right") - 1
                return k >= 0 and e["s"] * (fm[k] - e["start"]) < 0
            return rule
        return make

    def run_arm(select, variants=False, rule=None):
        rows, busy = [], -1.0
        for e in ev:
            if not select(e) or e["td"] < busy:
                continue
            if e["tok"] is None:
                rows.append({"t": e["t"], "s": e["s"], "missed": True, "why": "no_strike"})
                continue
            r = trade(day, e["tok"], e["td"], 60.0, exit_rule_fn=rule(e) if rule else None)
            if not r["missed"] and r["premium"] > 15000.0:
                r = {"missed": True, "why": "premium", "premium": r["premium"]}
            r.update(t=e["t"], s=e["s"], td=e["td"], imb=e["imb"])
            if not r["missed"]:
                busy = r["tx"]
                if variants:
                    with_variants(day, e["tok"], e["td"], 60.0, r)
            rows.append(r)
        return rows

    res = {"impulses": len(ev), "candidate": run_arm(lambda e: e["cond"], variants=True),
           "control_all": run_arm(lambda e: True),
           "ofi": run_arm(lambda e: e["ofi_ok"]), "ofi_and_static": run_arm(lambda e: e["ofi_ok"] and e["cond"]),
           "premise_exit": run_arm(lambda e: e["cond"], rule=premise_rule)}
    # SN304: the matched control, one per candidate decision, used once, traded standalone
    used, pairs = set(), []
    for c in res["candidate"]:
        pool = [(abs(e["t"] - c["t"]), i) for i, e in enumerate(ev)
                if not e["cond"] and e["s"] == c["s"] and i not in used and abs(e["t"] - c["t"]) <= 3600
                and abs(e["mag"] / next(x["mag"] for x in ev if x["t"] == c["t"]) - 1) <= 0.5 and e["tok"] is not None]
        if not pool:
            pairs.append({"t": c["t"], "control": None})
            continue
        _dist, i = min(pool)
        used.add(i)
        e = ev[i]
        r = trade(day, e["tok"], e["td"], 60.0)
        if not r["missed"] and r["premium"] > 15000.0:
            r = {"missed": True, "why": "premium"}
        pairs.append({"t": c["t"], "control_t": e["t"], "cand205": c.get("net205"), "ctrl205": r.get("net205"),
                      "cand_missed": c.get("missed", True), "ctrl_missed": r["missed"]})
    res["pairs"] = pairs
    return res


# ---- SN293 amended (signal copied from fw.sn293; target freshness on the exchange clock) ------------------------------
def sn293(day: Day):
    T = np.arange(0, 22500, 1.0)
    fg, _ = fw.grid(day, day.fut, lambda d: np.where((d["bid"] > 0) & (d["ask"] > 0), (d["bid"] + d["ask"]) / 2, d["ltp"]), T)
    ig, _ = fw.grid(day, day.idx, lambda d: d["ltp"], T)
    mid = lambda d: np.where((d["bid"] > 0) & (d["ask"] > 0), (d["bid"] + d["ask"]) / 2, np.nan)  # noqa: E731
    cache = {}

    def og(tok):
        if tok not in cache:
            g, _age = fw.grid(day, tok, mid, T)
            d = day.D[tok]
            k = np.searchsorted(d["t"], T, side="right") - 1
            xt = d["t"] - (d["lag"] - day.offset)                      # exchange time on the receipt clock
            xage = np.where(k >= 0, T - xt[np.maximum(k, 0)], np.inf)
            cache[tok] = (g, xage)
        return cache[tok]
    res = {"triggers": 0, "candidate": [], "control_most": [], "pairs": []}
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
            if tok is None or tok not in day.D:
                continue
            g, xage = og(tok)
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
            info.append({"tok": tok, "ratio": obs / exp_, "exp": exp_, "obs": obs, "age": float(xage[t]), "beta": beta})
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
        r = trade(day, tgt["tok"], float(t), 15.0)
        r.update(t=t, ratio=round(tgt["ratio"], 3), beta=round(tgt["beta"], 4))
        if not r["missed"]:
            busy = r["tx"]
            with_variants(day, tgt["tok"], float(t), 15.0, r)
        res["candidate"].append(r)
        most = max(moved, key=lambda x: x["ratio"])
        rm = trade(day, most["tok"], float(t), 15.0)
        rm.update(t=t, ratio=round(most["ratio"], 3))
        res["control_most"].append(rm)
        others = [x for x in moved if x["tok"] != tgt["tok"]]
        mt = min(others, key=lambda x: abs(x["beta"] - tgt["beta"]))
        rc = trade(day, mt["tok"], float(t), 15.0)
        res["pairs"].append({"t": t, "cand205": r.get("net205"), "ctrl205": rc.get("net205"), "cand_missed": r["missed"],
                             "ctrl_missed": rc["missed"], "ctrl_beta": round(mt["beta"], 4)})
    return res


# ---- SN298 under the amended execution ------------------------------------------------------------------------------------
def sn298(day: Day):
    if day.day not in fw.PRE_HOLIDAY or day.expiry_day:
        return None
    t920, t1510 = 5 * 60.0, 355 * 60.0
    K = day.atm(t920)
    tok = day.opt.get((day.front, K - 50, "CE")) if K else None
    if tok is None:
        return {"day": day.day, "missed": True, "why": "no_strike"}
    got, why = entry(day, tok, t920)
    if got is None:
        return {"day": day.day, "missed": True, "why": why}
    k, px = got
    h = hold(day, tok, k, px, t1510, 205.0)
    return {"day": day.day, "net205": h["net"], "status": h["status"], "why": h["why"]}


def run(folder, loaded=None):
    day = Day(folder, loaded)
    q = fw.qualify(day)
    out = {"qualify": q, "offset_s": round(day.offset, 3)}
    if q["ok"]:
        out["SN291"] = sn291(day)
        out["SN293"] = sn293(day)
    out["SN298"] = sn298(day)
    return out
